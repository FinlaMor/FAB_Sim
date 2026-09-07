#!/usr/bin/env python3
"""Bring drafts and their reviews across from the drafting worktree.

The drafting passes run in an ISOLATED git worktree
(`C:\\Users\\Joseph\\Desktop\\FAB_Sim_oxalpha`, branch `oxalpha-cards`) so an
unvetted model never writes where in-flight work lives. Their output is
`.drafts/<slug>.json` plus `.draft-review/<slug>.json`, and adoption happens
HERE, through scripts/adopt_drafts.py, because a card JSON in a set directory
is loaded by every game.

This is the one step between the two, and it is deliberately dumb: copy, never
adopt. Everything that decides whether a draft becomes a card stays in
adopt_drafts.py, where it is gated and tested.

TWO RULES, both learned by breaking them:

  * NEVER OVERWRITE AN IMPLEMENTED CARD'S DRAFT. A slug already implemented
    here has been through the gate, and its draft is now history -- copying a
    newer draft over it would re-open a decision that was already made, and
    adopt_drafts refuses to overwrite a card anyway, so the copy would be pure
    noise in the queue.
  * A DRAFT WITHOUT ITS REVIEW IS NOT USABLE. adopt_drafts requires a verdict
    of `status: ok`; a draft copied without one is skipped as "unreviewed" and
    sits in the queue looking like work that failed. Copy the pair or neither.

    python scripts/sync_drafts_from_worktree.py            # what would move
    python scripts/sync_drafts_from_worktree.py --write
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

J = ROOT / "engine" / "card_effects" / "json"
DEFAULT_WORKTREE = Path(r"C:\Users\Joseph\Desktop\FAB_Sim_oxalpha")

#: Directories under json/ that are pass artifacts rather than the live corpus.
NOT_LIVE = {".drafts", ".draft-review", ".draft-notes", ".review", ".triage",
            ".quarantine", "batch", "needs_review", ".modelbench"}


def implemented_here() -> set[str]:
    out = set()
    for path in J.rglob("*.json"):
        if path.name.endswith("_work_queue.json"):
            continue
        if set(path.relative_to(J).parts) & NOT_LIVE:
            continue
        out.add(path.stem)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--worktree", type=Path, default=DEFAULT_WORKTREE)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    src = args.worktree / "engine" / "card_effects" / "json"
    if not (src / ".drafts").is_dir():
        print(f"no .drafts under {src}")
        return 2

    have = implemented_here()
    (J / ".drafts").mkdir(exist_ok=True)
    (J / ".draft-review").mkdir(exist_ok=True)

    moved, skipped = [], {"already implemented": 0, "no review yet": 0,
                          "already here and unchanged": 0}
    for draft in sorted((src / ".drafts").glob("*.json")):
        slug = draft.stem
        if slug.startswith("_"):
            continue
        if slug in have:
            skipped["already implemented"] += 1
            continue
        review = src / ".draft-review" / draft.name
        if not review.exists():
            skipped["no review yet"] += 1
            continue
        here = J / ".drafts" / draft.name
        if here.exists() and here.read_bytes() == draft.read_bytes():
            skipped["already here and unchanged"] += 1
            continue
        moved.append((draft, review))

    print(f"{len(moved)} draft/review pairs to bring across")
    for key, n in skipped.items():
        if n:
            print(f"   skipped {n:5d}  {key}")
    if not args.write:
        for draft, _ in moved[:15]:
            print("   would copy", draft.stem)
        if len(moved) > 15:
            print(f"   ... and {len(moved) - 15} more")
        print("\n(dry run -- pass --write to copy)")
        return 0

    for draft, review in moved:
        shutil.copy2(draft, J / ".drafts" / draft.name)
        shutil.copy2(review, J / ".draft-review" / review.name)
    print(f"copied {len(moved)} pairs")
    print("now gate them:  python scripts/adopt_drafts.py --all-sets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
