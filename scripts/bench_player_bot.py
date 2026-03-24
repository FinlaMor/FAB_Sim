"""scripts/bench_player_bot.py

Benchmark a trained IQL player-bot checkpoint against the random agent
using the Talishar backend.

The script runs N games where P1 = IQL agent and P2 = random agent (and
N/2 more with seats swapped so first-player advantage cancels out).
It then prints a machine-readable summary line that run_pipeline.py parses:

    PLAYER_BOT_WIN_RATE 0.623

Exit code:
    0  — benchmark completed (pipeline reads win rate from stdout)
    1  — benchmark failed / could not load agent
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import types as _types
if "rl_agents" not in sys.modules:
    _pkg = _types.ModuleType("rl_agents")
    _pkg.__path__ = [os.path.join(_ROOT, "rl_agents")]
    _pkg.__package__ = "rl_agents"
    sys.modules["rl_agents"] = _pkg

from rl_agents.game_backends import (
    TalisharClient,
    TalisharGameResult,
    TalisharIQLAgent,
    _deck_file_to_talishar_slugs,
    _run_talishar_pvp_game,
)

_DECKS_DIR = os.path.join(_ROOT, "decks")
_CARD_DB_PATH = os.path.join(_ROOT, "card_data", "slug_index.json")


# ---------------------------------------------------------------------------
# Statistical helpers (stdlib only — no scipy dependency)
# ---------------------------------------------------------------------------

def _binomial_test_pvalue(wins: int, n: int, p0: float = 0.5) -> float:
    """Two-sided binomial test p-value using normal approximation.

    For large *n* this is accurate; for small *n* it is conservative enough
    for our benchmark purposes.
    """
    if n == 0:
        return 1.0
    observed = wins / n
    se = math.sqrt(p0 * (1 - p0) / n)
    if se == 0:
        return 0.0 if observed != p0 else 1.0
    z = abs(observed - p0) / se
    # Two-sided p-value via complementary error function
    p_value = math.erfc(z / math.sqrt(2))
    return p_value


def _wilson_confidence_interval(
    wins: int, n: int, z: float = 1.96,
) -> tuple[float, float]:
    """Wilson score 95 % confidence interval for a proportion."""
    if n == 0:
        return (0.0, 1.0)
    p_hat = wins / n
    denom = 1 + z * z / n
    centre = (p_hat + z * z / (2 * n)) / denom
    margin = z * math.sqrt((p_hat * (1 - p_hat) + z * z / (4 * n)) / n) / denom
    lo = max(0.0, centre - margin)
    hi = min(1.0, centre + margin)
    return (lo, hi)


def _discover_decks() -> list[str]:
    files = glob.glob(os.path.join(_DECKS_DIR, "*.txt"))
    files += glob.glob(os.path.join(_DECKS_DIR, "generated", "*.txt"))
    return sorted(set(files))


def _run_bench_game(
    base_url: str,
    p1_deck: str,
    p2_deck: str,
    seed: int,
    max_turns: int,
    iql_seat: int,          # 1 or 2 — which seat the IQL agent occupies
    iql_agent: TalisharIQLAgent,
) -> TalisharGameResult | None:
    """Run one benchmark game; returns result or None on error."""
    client = TalisharClient(base_url=base_url)
    p1_sub = _deck_file_to_talishar_slugs(p1_deck)
    p2_sub = _deck_file_to_talishar_slugs(p2_deck)
    p1_agent = iql_agent if iql_seat == 1 else None
    p2_agent = iql_agent if iql_seat == 2 else None
    try:
        return _run_talishar_pvp_game(
            client, p1_sub, p2_sub,
            p1_agent=p1_agent, p2_agent=p2_agent,
            p1_seed=seed, p2_seed=seed + 1,
            max_turns=max_turns,
        )
    except Exception as exc:
        print(f"  [bench] Game error: {exc}", flush=True)
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark IQL player bot vs random agent")
    parser.add_argument("--checkpoint", required=True,
                        help="Path to IQL checkpoint (.pt)")
    parser.add_argument("--bundle", default="",
                        help="Path to embedder bundle (.pt); if omitted, loaded from checkpoint")
    parser.add_argument("--base-url", default="http://localhost:8080/game",
                        help="Comma-separated Talishar server URLs")
    parser.add_argument("--games", type=int, default=20,
                        help="Total games to run (split 50/50 between seats; default 20)")
    parser.add_argument("--max-turns", type=int, default=50,
                        help="Turn cap per game (default 50)")
    parser.add_argument("--workers", type=int, default=4,
                        help="Parallel workers (default 4)")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--device", default="cpu",
                        help="Torch device for IQL inference (default: cpu)")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON (includes stats and CI)")
    args = parser.parse_args()

    seed = args.seed if args.seed is not None else random.randint(0, 2**31)
    rng = random.Random(seed)

    base_urls = [u.strip() for u in args.base_url.split(",") if u.strip()]
    if not base_urls:
        base_urls = ["http://localhost:8080/game"]

    # Load IQL agent.
    # bundle_path falls back to the checkpoint itself when the embedder bundle
    # was embedded in extra["embedder_bundle"] by train_iql.
    bundle_path = args.bundle or args.checkpoint
    try:
        iql_agent = TalisharIQLAgent(
            checkpoint_path=args.checkpoint,
            bundle_path=bundle_path,
            card_db_path=_CARD_DB_PATH,
            player_id=1,    # seat-aware: _get_agent(player_id) called per action
            device=args.device,
            seed=seed,
        )
    except Exception as exc:
        print(f"ERROR: Failed to load IQL agent: {exc}", file=sys.stderr)
        return 1

    decks = _discover_decks()
    if not decks:
        print(f"ERROR: No deck files found in {_DECKS_DIR}", file=sys.stderr)
        return 1

    # Build game specs: alternate IQL seat so first-player bias averages out
    n_games = max(args.games, 2)
    game_specs = []
    for i in range(n_games):
        p1 = rng.choice(decks)
        p2 = rng.choice(decks)
        gseed = rng.randint(0, 2**31)
        iql_seat = 1 if i % 2 == 0 else 2
        url = base_urls[i % len(base_urls)]
        game_specs.append((i, p1, p2, gseed, iql_seat, url))

    print(f"[bench] IQL vs Random  games={n_games}  max_turns={args.max_turns}")
    print(f"[bench] checkpoint: {args.checkpoint}")

    iql_wins = 0
    completed = 0

    def _run(spec):
        idx, p1, p2, gseed, iql_seat, url = spec
        result = _run_bench_game(url, p1, p2, gseed, args.max_turns, iql_seat, iql_agent)
        if result is None:
            return idx, iql_seat, None
        model_won = result.winner == iql_seat if result.winner else False
        return idx, iql_seat, (result, model_won)

    workers = min(n_games, args.workers)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_run, spec): spec[0] for spec in game_specs}
        from concurrent.futures import as_completed as _ac
        for f in _ac(futures):
            idx = futures[f]
            try:
                _, iql_seat, payload = f.result()
            except Exception as exc:
                print(f"  [bench] Game {idx + 1} exception: {exc}")
                continue
            if payload is None:
                print(f"  [bench] Game {idx + 1} SKIPPED (error)")
                continue
            result, model_won = payload
            completed += 1
            if model_won:
                iql_wins += 1
            w = f"P{result.winner}" if result.winner else "Draw"
            print(
                f"  [bench] game={idx + 1:>3}  iql_seat={iql_seat}  "
                f"winner={w}  iql_won={int(model_won)}  "
                f"turns={result.turn_number}  hp={result.p1_final_hp}/{result.p2_final_hp}"
            )

    if completed == 0:
        print("ERROR: No games completed", file=sys.stderr)
        return 1

    win_rate = iql_wins / completed
    ci_lo, ci_hi = _wilson_confidence_interval(iql_wins, completed)
    p_value = _binomial_test_pvalue(iql_wins, completed, p0=0.5)

    if args.json:
        result_obj = {
            "completed": completed,
            "iql_wins": iql_wins,
            "win_rate": round(win_rate, 4),
            "ci_95_lower": round(ci_lo, 4),
            "ci_95_upper": round(ci_hi, 4),
            "p_value": round(p_value, 6),
            "significant": p_value < 0.05,
            "seed": seed,
            "checkpoint": args.checkpoint,
        }
        print(json.dumps(result_obj, indent=2))
    else:
        print(f"\n[bench] completed={completed}  iql_wins={iql_wins}  win_rate={win_rate:.3f}")
        print(f"[bench] 95% CI: [{ci_lo:.3f}, {ci_hi:.3f}]  p-value: {p_value:.4f}")
        # Machine-readable line parsed by run_pipeline.py
        print(f"PLAYER_BOT_WIN_RATE {win_rate:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
