#!/usr/bin/env python3
"""Move graded drafts into their set directories.

A draft only becomes a card when it lands in a set folder, and from that moment
the engine loads it in every game. So adoption is gated on all three checks
passing, not on any one of them:

    validate_drafts.py   it compiles against the live loader
    grade_drafts.py      no known defect-class sweep flags it
    .draft-review/       a reviewer looked at it and said ok

None of those is sufficient alone -- every defect cluster found in the corpus
this week compiled, read all its parameters, and had been read by someone. They
are a filter for what is worth adopting, not a proof that it is right.

Adoption is per-set and refuses to overwrite an existing implementation, so a
batch can be verified and reverted on its own.

    python scripts/adopt_drafts.py --set wtr             # show what would move
    python scripts/adopt_drafts.py --set wtr --write     # move it
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
J = ROOT / "engine" / "card_effects" / "json"
DRAFTS = J / ".drafts"
REVIEW = J / ".draft-review"


def _flagged() -> set[str]:
    """Slugs any sweep in grade_drafts.py flagged for reading."""
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "grade_drafts.py"),
                          "--detail"], capture_output=True, text=True,
                         cwd=str(ROOT)).stdout
    return {l.strip() for l in out.splitlines() if re.match(r"^  [a-z0-9_]+$", l)}


def _compiles(path) -> str:
    """Does this draft compile against the LIVE loader?

    THE GATE CLAIMED THIS AND DID NOT DO IT. The docstring above lists
    validate_drafts.py as one of three checks, and the code checked only the
    sweeps and the review verdict -- so leave_them_hanging_red was adopted into
    sup/ naming a condition type the compiler has no dispatch for.

    That failure is not quiet like the rest of this class. compile_condition
    RAISES, so the whole card refuses to load and the engine will not start a
    game containing it: one bad adoption breaks every game, not just its own
    card. Checking it here rather than trusting a prose list of gates.
    """
    import json as _json
    try:
        raw = _json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"unparseable: {exc}"
    try:
        from engine.card_effects.dsl.loader import _compile_ability
        for ab in raw.get("abilities") or []:
            _compile_ability(ab)
    except Exception as exc:
        return f"does not compile: {type(exc).__name__}: {exc}"
    return ""


def _slug_to_set() -> dict[str, str]:
    """Where each card belongs, taken from the per-set work queues rather than
    the card DB's `sets` list -- a card printed in four products has four set
    names and only one directory."""
    out: dict[str, str] = {}
    for q in J.rglob("*_work_queue.json"):
        try:
            rows = json.loads(q.read_text(encoding="utf-8"))
        except Exception:
            continue
        for row in rows:
            if isinstance(row, dict) and row.get("slug"):
                out.setdefault(row["slug"], q.parent.name)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", dest="set_code", required=True)
    ap.add_argument("--write", action="store_true", help="actually move them")
    ap.add_argument("--limit", type=int, help="adopt at most N (a first batch)")
    args = ap.parse_args()

    dest = J / args.set_code
    if not dest.is_dir():
        print(f"no such set directory: {dest}")
        return 2

    flagged = _flagged()
    where = _slug_to_set()

    picked, skipped = [], {"flagged": 0, "unreviewed": 0, "findings": 0,
                           "other set": 0, "already implemented": 0,
                           "does not compile": 0}
    for path in sorted(DRAFTS.glob("*.json")):
        if path.stem.startswith("_"):
            continue
        slug = path.stem
        if where.get(slug) != args.set_code:
            skipped["other set"] += 1
            continue
        if (dest / f"{slug}.json").exists():
            skipped["already implemented"] += 1
            continue
        if slug in flagged:
            skipped["flagged"] += 1
            continue
        v = REVIEW / f"{slug}.json"
        if not v.exists():
            skipped["unreviewed"] += 1
            continue
        try:
            verdict = json.loads(v.read_text(encoding="utf-8"))
        except Exception:
            skipped["unreviewed"] += 1
            continue
        if not isinstance(verdict, dict) or verdict.get("status") != "ok":
            skipped["findings"] += 1
            continue
        why = _compiles(path)
        if why:
            skipped["does not compile"] += 1
            print(f"   REJECT {slug}: {why}")
            continue
        picked.append(path)

    if args.limit:
        picked = picked[:args.limit]

    print(f"set {args.set_code}: {len(picked)} adoptable")
    for k, v in skipped.items():
        if v:
            print(f"   skipped {v:4d}  {k}")
    print()
    for p in picked:
        print(("adopt  " if args.write else "would  ") + p.stem)

    if not args.write:
        print("\n(dry run -- pass --write to move them)")
        return 0

    for p in picked:
        shutil.copy2(p, dest / p.name)
    print(f"\nmoved {len(picked)} into {dest}")
    print("now refresh the queue:")
    print(f"   python scripts/dsl_work_queue.py --set {args.set_code} --write-queue")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
