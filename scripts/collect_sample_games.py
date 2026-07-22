#!/usr/bin/env python3
"""Collect full-fidelity sample games for the three test decks.

Plays a round-robin of the Victor / Kayo / Arakni CC decks and writes one
JSON-lines transcript per game via engine.recorder.JsonlRecorder. Each line is
one observable moment — every agent decision (with the full options list, the
chosen index, and a complete state snapshot), every event, every applied
action, step changes, and the final outcome. This is the raw material for
analysis, debugging, and behavior cloning; the (s,a,r,s',done) tensor pipeline
for IQL lives in rl_agents/collect_iql_mixed_data.py instead.

Usage:
  python scripts/collect_sample_games.py --games 5 --out-dir data_collection/sample_games
  python scripts/collect_sample_games.py --games 20 --agent random
  python scripts/collect_sample_games.py --both-seatings   # also swap P1/P2

Games are seeded, so a given (matchup, seed) is reproducible.
"""
from __future__ import annotations

import argparse
import itertools
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import DECKS_DIR  # noqa: E402
from engine.card import CardDB  # noqa: E402
from engine.engine import new_game  # noqa: E402
from engine.recorder import JsonlRecorder  # noqa: E402

# The three functional test decks, keyed by a short handle used in filenames.
DECKS = {
    "victor": "victor_goldmane_high_and_mighty_CC_lite.txt",
    "kayo": "kayo_underhanded_cheat_CC_lite.txt",
    "arakni": "arakni_marionette_CC_lite.txt",
}


def _build_agent(kind: str, seed: int):
    if kind == "heuristic":
        from rl_agents.heuristic_bot import HeuristicBot
        return HeuristicBot(seed=seed)
    if kind == "random":
        from rl_agents.random_agent import RandomAgent
        return RandomAgent(seed=seed)
    raise ValueError(f"unknown agent kind: {kind}")


def _tally(path: Path) -> dict[str, int]:
    """Count record kinds in a written transcript (also proves it parses)."""
    kinds: dict[str, int] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            kind = json.loads(line)["kind"]
            kinds[kind] = kinds.get(kind, 0) + 1
    return kinds


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=5, help="games per matchup")
    ap.add_argument("--agent", choices=["heuristic", "random"], default="heuristic")
    ap.add_argument("--max-turns", type=int, default=100)
    ap.add_argument("--both-seatings", action="store_true",
                    help="run each pairing in both P1/P2 orders (doubles games)")
    ap.add_argument("--out-dir", default="data_collection/sample_games")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    order_fn = itertools.permutations if args.both_seatings else itertools.combinations
    pairings = list(order_fn(DECKS, 2))

    db = CardDB()
    records: list[dict] = []
    total = len(pairings) * args.games
    done = 0

    print(f"Collecting {total} games ({args.agent}) across {len(pairings)} pairings "
          f"-> {out_dir}", file=sys.stderr)

    for a, b in pairings:
        for seed in range(args.games):
            name = f"{a}_vs_{b}_seed{seed}"
            path = out_dir / f"{name}.jsonl"
            rec = JsonlRecorder(str(path), snapshot_on={"decision"})
            random.seed(seed)
            try:
                state = new_game(
                    str(Path(DECKS_DIR) / DECKS[a]),
                    str(Path(DECKS_DIR) / DECKS[b]),
                    _build_agent(args.agent, seed),
                    _build_agent(args.agent, seed + 1),
                    db, p1_seed=seed, p2_seed=seed + 1,
                    max_turns=args.max_turns, recorders=[rec],
                )
            except Exception as exc:  # a crashed game still leaves a partial log
                print(f"  ! {name}: {type(exc).__name__}: {exc}", file=sys.stderr)
                records.append({"game": name, "error": f"{type(exc).__name__}: {exc}"})
                done += 1
                continue

            kinds = _tally(path)
            rows = {
                "game": name, "matchup": f"{a}_vs_{b}",
                "p1": a, "p2": b, "seed": seed,
                "winner": state.winner,
                "turns": state.turn_number,
                "ended_on_turn_cap": state.winner is None or state.turn_number >= args.max_turns,
                "decisions": kinds.get("decision", 0),
                "events": kinds.get("event", 0),
                "actions": kinds.get("action_applied", 0),
                "file": path.name,
            }
            records.append(rows)
            done += 1
            print(f"[{done:3d}/{total}] {name:32s} winner=P{state.winner} "
                  f"turns={state.turn_number:3d} decisions={rows['decisions']}",
                  file=sys.stderr)

    completed = [r for r in records if "error" not in r]
    summary = {
        "agent": args.agent,
        "games_per_matchup": args.games,
        "both_seatings": args.both_seatings,
        "max_turns": args.max_turns,
        "total_games": len(records),
        "completed": len(completed),
        "errors": len(records) - len(completed),
        "total_decisions": sum(r.get("decisions", 0) for r in completed),
        "games": records,
    }
    summary_path = out_dir / "sample_games_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"\nwrote {len(completed)}/{len(records)} transcripts + {summary_path.name} "
          f"({summary['total_decisions']} recorded decisions)", file=sys.stderr)
    return 0 if summary["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
