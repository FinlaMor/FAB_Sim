"""scripts/run_talishar_games.py

Demo script showing how to run FAB games through the Talishar backend.

Prerequisites
-------------
1. Talishar Docker container running on localhost:8080
   (from third_party/Talishar_official: ``bash start.sh``)
2. The patched ProcessInput.php with ``returnState=1`` support
   (already applied in this repo) for fused-call optimisation.

Usage
-----
    # Single PvP game (both seats random, verbose)
    python scripts/run_talishar_games.py

    # 4 parallel games, practice-dummy mode
    python scripts/run_talishar_games.py --mode dummy --num-games 4

    # Custom decks + turn cap
    python scripts/run_talishar_games.py \\
        --p1-deck decks/oscillio_constella_intelligence_CC_lite.txt \\
        --p2-deck decks/kayo_underhanded_cheat_CC_lite.txt \\
        --max-turns 30

    # Benchmark: run 10 PvP games in parallel, print timing
    python scripts/run_talishar_games.py --num-games 10 --benchmark
"""
from __future__ import annotations

import argparse
import glob
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

# Prevent rl_agents/__init__.py from pulling in torch (not needed here).
# Register a placeholder package so "from rl_agents.game_backends" resolves
# without executing the heavy __init__.py.
import types as _types
if "rl_agents" not in sys.modules:
    _pkg = _types.ModuleType("rl_agents")
    _pkg.__path__ = [os.path.join(_ROOT, "rl_agents")]
    _pkg.__package__ = "rl_agents"
    sys.modules["rl_agents"] = _pkg

from rl_agents.game_backends import (  # noqa: E402
    TalisharBackend,
    TalisharClient,
    TalisharGameResult,
    TalisharIQLAgent,
    _deck_file_to_talishar_slugs,
    _run_talishar_pvp_game,
    _run_talishar_random_game,
)
from rl_agents.game_data import (  # noqa: E402
    DeckMeta,
    GameDataStore,
    TransitionCollector,
)

_DEFAULT_P1_DECK = os.path.join(_ROOT, "decks", "oscillio_constella_intelligence_CC_lite.txt")
_DEFAULT_P2_DECK = os.path.join(_ROOT, "decks", "kayo_underhanded_cheat_CC_lite.txt")
_DECKS_DIR = os.path.join(_ROOT, "decks")


def _discover_decks() -> list[str]:
    """Return all .txt deck files in decks/ and decks/generated/."""
    files = glob.glob(os.path.join(_DECKS_DIR, "*.txt"))
    files += glob.glob(os.path.join(_DECKS_DIR, "generated", "*.txt"))
    return sorted(set(files))


def _pick_random_decks(rng: random.Random, mode: str = "pvp") -> tuple[str, str]:
    """Pick two random decks (with replacement, so mirrors are possible).

    In dummy mode only P1 is randomized; P2 is ignored by Talishar.
    """
    decks = _discover_decks()
    if not decks:
        print(f"ERROR: No .txt deck files found in {_DECKS_DIR}")
        sys.exit(1)
    p1 = rng.choice(decks)
    p2 = rng.choice(decks) if mode != "dummy" else p1  # P2 unused in dummy mode
    return p1, p2


class _CancelToken:
    """Thread-safe cancellation flag passed into game loops."""
    def __init__(self):
        self._cancelled = threading.Event()

    def cancel(self):
        self._cancelled.set()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()


def _run_with_timeout(fn, timeout_s: float | None, *args, cancel_token: _CancelToken | None = None, **kwargs):
    """Run *fn* in a daemon thread, returning its result or None on timeout.

    When the timeout fires, sets cancel_token so the game loop can exit early
    instead of continuing to make HTTP calls.
    """
    if timeout_s is None or timeout_s <= 0:
        return fn(*args, **kwargs)
    result_box: list = [None]
    error_box: list = [None]
    def _target():
        try:
            result_box[0] = fn(*args, **kwargs)
        except Exception as e:
            error_box[0] = e
    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout=timeout_s)
    if t.is_alive():
        if cancel_token:
            cancel_token.cancel()
        return None          # timed out — daemon thread dies at process exit
    if error_box[0] is not None:
        raise error_box[0]
    return result_box[0]


def _print_result(result: TalisharGameResult, label: str = "") -> None:
    prefix = f"[{label}] " if label else ""
    cap = " (turn cap)" if result.ended_on_turn_cap else ""
    winner = f"P{result.winner}" if result.winner else "Draw"
    print(
        f"  {prefix}Game {result.game_name}: "
        f"Winner={winner}{cap}  Turns={result.turn_number}  "
        f"HP={result.p1_final_hp}/{result.p2_final_hp}  "
        f"Actions={result.total_actions}"
    )


# ── Single game demo ──────────────────────────────────────────────────
def run_single_game(
    base_url: str,
    mode: str,
    p1_deck: str,
    p2_deck: str,
    max_turns: int,
    seed: int,
    verbose: bool = True,
    store: GameDataStore | None = None,
    max_actions: int = 0,
    cancel_token: _CancelToken | None = None,
    p1_agent=None,
    p2_agent=None,
) -> TalisharGameResult:
    """Run one game and print the result."""
    client = TalisharClient(base_url=base_url)

    # Verify the server is reachable
    try:
        client._session.get(base_url, timeout=3)
    except Exception as exc:
        print(f"ERROR: Cannot reach Talishar at {base_url}")
        print(f"  {exc}")
        print(f"\nMake sure Docker is running:")
        print(f"  cd third_party/Talishar_official && bash start.sh")
        sys.exit(1)

    p1_sub = _deck_file_to_talishar_slugs(p1_deck)
    p2_sub = _deck_file_to_talishar_slugs(p2_deck)

    collector = TransitionCollector() if store else None

    if verbose:
        print(f"Mode      : {mode}")
        print(f"P1 hero   : {p1_sub['hero']}")
        if mode == "dummy":
            print(f"P2        : Practice Dummy")
        else:
            print(f"P2 hero   : {p2_sub['hero']}")
        print(f"Max turns : {max_turns}")
        print(f"Seed      : {seed}")
        print()

    t0 = time.time()

    if mode == "dummy":
        result = _run_talishar_random_game(
            client, p1_sub, max_turns=max_turns,
            rng=__import__("random").Random(seed), verbose=verbose,
            collector=collector,
            cancel_token=cancel_token,
        )
    else:
        result = _run_talishar_pvp_game(
            client, p1_sub, p2_sub,
            p1_agent=p1_agent, p2_agent=p2_agent,
            p1_seed=seed, p2_seed=seed + 1,
            max_turns=max_turns, max_actions=max_actions,
            verbose=verbose,
            collector=collector,
            cancel_token=cancel_token,
        )

    elapsed = time.time() - t0
    if verbose:
        print()
        _print_result(result, "result")
        print(f"  Elapsed: {elapsed:.2f}s  ({result.total_actions / max(elapsed, 0.01):.0f} actions/s)")

    # Persist game data
    if store and collector:
        collector.finalize_rewards(result.winner)
        meta = DeckMeta(
            game_id=collector.game_id,
            p1_deck_file=p1_deck,
            p2_deck_file=p2_deck,
            p1_decklist=p1_sub,
            p2_decklist=p2_sub,
            winner=result.winner,
            p1_final_hp=result.p1_final_hp,
            p2_final_hp=result.p2_final_hp,
            turn_count=result.turn_number,
            ended_on_turn_cap=result.ended_on_turn_cap,
            total_actions=result.total_actions,
            seed=seed,
            mode=mode,
        )
        store.save_game(collector, meta)

    return result


# ── Parallel games demo ───────────────────────────────────────────────
def run_parallel_games(
    base_url: str,
    mode: str,
    p1_deck: str,
    p2_deck: str,
    max_turns: int,
    num_games: int,
    benchmark: bool,
    store: GameDataStore | None = None,
    workers: int = 8,
) -> list[TalisharGameResult]:
    """Run multiple games in parallel, each through run_single_game."""
    print(f"Running {num_games} games in parallel (mode={mode}, max_turns={max_turns})")
    print()

    t0 = time.time()

    def _worker(seed: int) -> TalisharGameResult:
        return run_single_game(
            base_url, mode, p1_deck, p2_deck,
            max_turns, seed, verbose=not benchmark,
            store=store,
        )

    results = []
    with ThreadPoolExecutor(max_workers=min(num_games, workers)) as ex:
        futures = [ex.submit(_worker, i) for i in range(num_games)]
        from concurrent.futures import as_completed as _as_completed
        for f in _as_completed(futures):
            results.append(f.result())

    elapsed = time.time() - t0

    print("=" * 65)
    print(f"RESULTS ({num_games} games)")
    print("=" * 65)
    for r in results:
        _print_result(r)

    total_actions = sum(r.total_actions for r in results)
    p1_wins = sum(1 for r in results if r.winner == 1)
    p2_wins = sum(1 for r in results if r.winner == 2)
    draws = num_games - p1_wins - p2_wins

    print()
    print(f"  P1 wins: {p1_wins}  P2 wins: {p2_wins}  Draws: {draws}")
    print(f"  Total actions: {total_actions}")
    print(f"  Wall time: {elapsed:.2f}s")
    print(f"  Throughput: {total_actions / max(elapsed, 0.01):.0f} actions/s")
    print(f"  Avg game: {elapsed / max(num_games, 1):.2f}s")

    return results


# ── HTTP round-trip breakdown ─────────────────────────────────────────
def show_optimisation_info() -> None:
    """Print a summary of the optimisation changes."""
    print("""
HTTP Round-Trip Optimisations (applied)
=======================================

BEFORE (naive loop):
  PvP: 3 HTTP calls per action
    1. GET GetNextTurn.php (P1 state)
    2. GET GetNextTurn.php (P2 state)
    3. GET ProcessInput.php (submit action, no response body)

  Dummy: 2 HTTP calls per action
    1. GET GetNextTurn.php (state)
    2. GET ProcessInput.php (submit)

AFTER (optimised):
  PvP: 1-2 HTTP calls per action
    1. GET ProcessInput.php?returnState=1 (submit + get new state in 1 call)
    2. GET GetNextTurn.php (other player) -- only when priority switches

  Dummy: 1 HTTP call per action
    1. GET ProcessInput.php?returnState=1 (submit + get new state)

  Additional:
    - Parallel P1+P2 state fetches (ThreadPoolExecutor) when both needed
    - Lazy P2 fetch: skip P2 state when P1 has priority
    - Stall sleep reduced: 50ms -> 5ms
    - Graceful fallback: if server doesn't support returnState, falls back to
      separate GetNextTurn.php call (compatible with unpatched Talishar)

  Expected speedup: ~2-3x for PvP, ~2x for dummy mode.
""")


def main():
    parser = argparse.ArgumentParser(
        description="Run FAB games through Talishar backend",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--base-url", default="http://localhost:8080/game",
                        help="Talishar base URL (default: http://localhost:8080/game). "
                             "For multi-container setups, use comma-separated URLs: "
                             "http://localhost:8080/game,http://localhost:8081/game,...")
    parser.add_argument("--mode", choices=["pvp", "dummy"], default="pvp",
                        help="pvp = control both seats; dummy = vs Practice Dummy")
    parser.add_argument("--p1-deck", default=_DEFAULT_P1_DECK, help="P1 deck file path")
    parser.add_argument("--p2-deck", default=_DEFAULT_P2_DECK, help="P2 deck file path")
    parser.add_argument("--random-decks", action="store_true",
                        help="Randomly select P1 and P2 decks from decks/ folder "
                             "(with replacement — mirrors possible). "
                             "For parallel runs each game gets a fresh random pairing.")
    parser.add_argument("--max-turns", type=int, default=50, help="Turn cap per game")
    parser.add_argument("--max-actions", type=int, default=0,
                        help="Action iteration cap per game. 0 = max_turns*60 (default: 0)")
    parser.add_argument("--seed", type=int, default=None,
                        help="RNG seed (default: 42, or random when --random-decks)")
    parser.add_argument("--num-games", type=int, default=1,
                        help="Number of games (>1 runs in parallel)")
    parser.add_argument("--workers", type=int, default=4,
                        help="Max parallel workers for multi-game runs (default: 4). "
                             "Reduce if Talishar Docker is on the same machine.")
    parser.add_argument("--game-timeout", type=float, default=600.0,
                        help="Per-game wall-clock timeout in seconds. "
                             "Hung games are skipped. 0 = no timeout. (default: 600)")
    parser.add_argument("--benchmark", action="store_true",
                        help="Suppress per-action output, print only summary")
    parser.add_argument("--info", action="store_true",
                        help="Print optimisation summary and exit")
    parser.add_argument("--db", default=os.path.join(_ROOT, "data", "talishar_games.db"),
                        help="SQLite database path for saving game data "
                             "(default: data/talishar_games.db)")
    parser.add_argument("--no-save", action="store_true",
                        help="Disable saving game data to SQLite")
    parser.add_argument("--iql-agent", default="",
                        help="Path to IQL checkpoint (.pt) to use as P1 agent. "
                             "P2 always uses random. Falls back to random if omitted.")
    parser.add_argument("--iql-bundle", default="",
                        help="Path to embedder bundle (.pt) for the IQL agent. "
                             "Required when --iql-agent is set and bundle is not embedded in checkpoint.")
    parser.add_argument("--iql-device", default="cpu",
                        help="Torch device for IQL inference (default: cpu)")
    args = parser.parse_args()

    if args.info:
        show_optimisation_info()
        return

    seed = args.seed if args.seed is not None else random.randint(0, 2**31)
    args.seed = seed
    rng = random.Random(seed)

    # Parse multi-container URLs (comma-separated)
    base_urls = [u.strip() for u in args.base_url.split(",") if u.strip()]
    if not base_urls:
        base_urls = ["http://localhost:8080/game"]

    # Load IQL agent if requested.
    # bundle_path defaults to the checkpoint itself; TalisharIQLAgent will
    # extract extra["embedder_bundle"] from it if no standalone bundle is given.
    iql_agent = None
    if args.iql_agent:
        import os as _os
        card_db_path = _os.path.join(_ROOT, "card_data", "slug_index.json")
        bundle_path = args.iql_bundle or args.iql_agent
        try:
            iql_agent = TalisharIQLAgent(
                checkpoint_path=args.iql_agent,
                bundle_path=bundle_path,
                card_db_path=card_db_path,
                player_id=1,
                device=args.iql_device,
                seed=seed,
            )
            print(f"IQL Agent : {args.iql_agent} (P1)")
        except Exception as exc:
            print(f"WARNING: Failed to load IQL agent ({exc}). P1 will use random.")

    # Initialize data store
    store = None
    if not args.no_save:
        store = GameDataStore(args.db)

    print("=" * 65)
    print("FAB Talishar Game Runner")
    print("=" * 65)
    if len(base_urls) == 1:
        print(f"Server    : {base_urls[0]}")
    else:
        print(f"Servers   : {len(base_urls)} containers")
        for i, u in enumerate(base_urls):
            print(f"  [{i}] {u}")
    print(f"Seed      : {seed}")
    if store:
        print(f"Database  : {args.db}")

    if args.random_decks:
        print(f"Decks     : random (from {_DECKS_DIR})")

    timeout = args.game_timeout if args.game_timeout > 0 else None
    if timeout:
        print(f"Timeout   : {timeout:.0f}s per game")

    completed = 0
    skipped = 0
    total_actions = 0
    t_start = time.time()

    if args.num_games > 1:
        if args.random_decks:
            # Build all pairings + seeds up front so the RNG sequence is deterministic
            game_specs = []
            for i in range(args.num_games):
                p1, p2 = _pick_random_decks(rng, mode=args.mode)
                game_seed = rng.randint(0, 2**31)
                # Round-robin assign each game to a container
                assigned_url = base_urls[i % len(base_urls)]
                game_specs.append((i, p1, p2, game_seed, assigned_url))

            cancel_tokens: dict[int, _CancelToken] = {}

            def _run_one(spec):
                idx, p1, p2, gseed, game_url = spec
                p1_hero = os.path.basename(p1).replace('_CC_lite.txt', '').replace('_CC.txt', '')
                token = cancel_tokens.get(idx)
                result = run_single_game(
                    game_url, args.mode,
                    p1, p2,
                    args.max_turns, gseed,
                    verbose=False,
                    store=store,
                    max_actions=args.max_actions,
                    cancel_token=token,
                    p1_agent=iql_agent,
                )
                return idx, p1_hero, result

            workers = min(args.num_games, args.workers)
            print(f"\nRunning {args.num_games} games ({workers} parallel workers)...\n")

            with ThreadPoolExecutor(max_workers=workers) as ex:
                futures = {}
                for spec in game_specs:
                    token = _CancelToken()
                    cancel_tokens[spec[0]] = token
                    f = ex.submit(_run_with_timeout, _run_one, timeout, spec, cancel_token=token)
                    futures[f] = spec[0]  # game index

                from concurrent.futures import as_completed as _as_completed
                for f in _as_completed(futures):
                    idx = futures[f]
                    try:
                        result_tuple = f.result()
                    except Exception as exc:
                        skipped += 1
                        print(f"  WARNING: Game {idx + 1} ERROR: {exc}")
                        continue
                    if result_tuple is None:
                        skipped += 1
                        print(f"  WARNING: Game {idx + 1} SKIPPED — hung (>{timeout:.0f}s timeout)")
                    else:
                        completed += 1
                        _, hero, r = result_tuple
                        total_actions += r.total_actions
                        cap = " [CAP]" if r.ended_on_turn_cap else ""
                        w = f"P{r.winner}" if r.winner else "Draw"
                        print(f"  Game {idx + 1:>2}: {hero:35s}  W={w}  T={r.turn_number:>3}  HP={r.p1_final_hp}/{r.p2_final_hp}  A={r.total_actions}{cap}")
        else:
            run_parallel_games(
                base_urls[0], args.mode,
                args.p1_deck, args.p2_deck,
                args.max_turns, args.num_games, args.benchmark,
                store=store, workers=args.workers,
            )
    else:
        if args.random_decks:
            args.p1_deck, args.p2_deck = _pick_random_decks(rng, mode=args.mode)
        result = _run_with_timeout(
            run_single_game, timeout,
            base_urls[0], args.mode,
            args.p1_deck, args.p2_deck,
            args.max_turns, args.seed,
            store=store,
            max_actions=args.max_actions,
            p1_agent=iql_agent,
        )
        if result is None:
            print(f"  WARNING: SKIPPED — game hung (>{timeout:.0f}s timeout)")
        else:
            completed = 1
            total_actions = result.total_actions

    t_elapsed = time.time() - t_start
    print(f"\n{'=' * 65}")
    print(f"Completed : {completed}/{args.num_games}  Skipped: {skipped}")
    print(f"Total time: {t_elapsed:.1f}s")
    if completed:
        print(f"Avg/game  : {t_elapsed / completed:.1f}s")
    if total_actions:
        print(f"Avg/action: {t_elapsed / total_actions * 1000:.1f}ms  ({total_actions / max(t_elapsed, 0.01):.0f} actions/s)")
    if store:
        print(f"DB games  : {store.game_count()}  DB transitions: {store.transition_count()}")
        store.close()
    print(f"{'=' * 65}")


if __name__ == "__main__":
    main()
