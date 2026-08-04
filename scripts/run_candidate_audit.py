#!/usr/bin/env python3
"""Play the generated audit decks (scripts/build_audit_decks.py) and audit them,
so the candidate corpus is actually exercised in real games. Reports three things
per run: games that CRASHED (an unverified candidate broke a live game — the most
valuable finding), rules-invariant VIOLATIONS (from game_transcript_audit), and
how many distinct candidate cards were reached.

Usage:
  python scripts/run_candidate_audit.py --seeds 4 --max-turns 60
"""
from __future__ import annotations
import argparse
import itertools
import json
import random
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from engine.card import CardDB
from engine.engine import new_game
from engine.recorder import JsonlRecorder
from rl_agents.random_agent import RandomAgent
import game_transcript_audit as audit

GEN_DIR = ROOT / "decks" / "audit"
HANDLES = ["victor", "kayo", "arakni", "marlynn", "vynnset"]


def _slugs_seen(path: Path) -> set[str]:
    """Distinct card slugs a game actually touched — cards played/activated and
    cards pitched (engine.recorder writes these under action_applied.action)."""
    seen = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("kind") != "action_applied":
                continue
            action = rec.get("action") or {}
            if action.get("card"):
                seen.add(action["card"])
            for pitched in action.get("pitch") or []:
                seen.add(pitched)
    return seen


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=4)
    ap.add_argument("--max-turns", type=int, default=60)
    ap.add_argument("--out-dir", default=str(Path(__file__).resolve().parent.parent
                                             / "data_collection" / "candidate_audit"))
    args = ap.parse_args()

    decks = {h: GEN_DIR / f"audit_{h}.txt" for h in HANDLES}
    missing = [h for h, p in decks.items() if not p.exists()]
    if missing:
        print(f"missing audit decks {missing}; run build_audit_decks.py first")
        sys.exit(2)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    db = CardDB()

    crashes, violations, seen = [], [], set()
    games = 0
    for a, b in itertools.permutations(HANDLES, 2):
        for seed in range(args.seeds):
            name = f"audit_{a}_vs_{b}_seed{seed}"
            path = out_dir / f"{name}.jsonl"
            rec = JsonlRecorder(str(path), snapshot_on={"decision"})
            random.seed(seed)
            games += 1
            try:
                new_game(str(decks[a]), str(decks[b]),
                         RandomAgent(seed=seed), RandomAgent(seed=seed + 1),
                         db, p1_seed=seed, p2_seed=seed + 1,
                         max_turns=args.max_turns, recorders=[rec])
            except Exception as exc:
                crashes.append((name, f"{type(exc).__name__}: {exc}"))
                traceback.print_exc()
                continue
            _n, findings, _info, _open = audit.audit_game(str(path))
            for f in findings:
                violations.append((name, f))
            seen |= _slugs_seen(path)

    print("\n==== candidate-deck audit ====")
    print(f"games played      : {games}")
    print(f"crashed games     : {len(crashes)}")
    for n, e in crashes:
        print(f"    CRASH {n}: {e}")
    print(f"rules violations  : {len(violations)}")
    for n, v in violations:
        print(f"    VIOLATION {n}: {v}")
    print(f"distinct cards hit : {len(seen)}")


if __name__ == "__main__":
    main()
