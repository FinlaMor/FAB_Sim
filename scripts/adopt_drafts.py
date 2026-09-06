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
import functools
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Python 3.11+ puts the SCRIPT's directory on sys.path, not the cwd, so
# `import engine` failed here for every draft and _compiles() reported all 773
# as "does not compile: No module named 'engine'". Fail-closed, so nothing bad
# was adopted -- but nothing good was either, and the reason printed was a lie
# about the card. The compile gate is load-bearing; it must not be able to pass
# or fail for a reason that has nothing to do with the card.
sys.path.insert(0, str(ROOT))

J = ROOT / "engine" / "card_effects" / "json"
DRAFTS = J / ".drafts"
REVIEW = J / ".draft-review"


@functools.lru_cache(maxsize=1)
def _flagged() -> frozenset:
    """Slugs any sweep in grade_drafts.py flagged for reading."""
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "grade_drafts.py"),
                          "--detail"], capture_output=True, text=True,
                         cwd=str(ROOT)).stdout
    return frozenset(l.strip() for l in out.splitlines()
                     if re.match(r"^  [a-z0-9_]+$", l))


@functools.lru_cache(maxsize=1)
def _unread_params() -> frozenset:
    """Slugs whose draft names a parameter the compiler never reads.

    This gate was NAMED in the prose but never run: adoption checked the
    sweeps, the review verdict and (later) compilation, and an unread parameter
    passes all three. It is the quietest defect the corpus has -- the card
    loads, the ability fires, and one clause of the printed text simply is not
    there. Running it here rather than trusting the list.
    """
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "audit_params.py"),
                          "--path", str(DRAFTS)], capture_output=True, text=True,
                         cwd=str(ROOT)).stdout
    return frozenset(l.strip() for l in out.splitlines()
                     if re.match(r"^   [a-z0-9_]+$", l))


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
    # Import OUTSIDE the try that judges the card: an engine that cannot be
    # imported is a broken harness, not a broken draft, and blaming the card
    # for it is how this gate spent its life rejecting everything.
    from engine.card_effects.dsl.loader import _compile_ability
    try:
        for ab in raw.get("abilities") or []:
            _compile_ability(ab)
    except Exception as exc:
        return f"does not compile: {type(exc).__name__}: {exc}"
    return ""


#: Directories under json/ that hold a *_work_queue.json but are not sets.
#: `batch/` is the candidate-selection queue the pipeline writes (1000 rows
#: spanning every set); `needs_review/` is where the pipeline parks cards it
#: could not finish. Neither names a destination, and because the scan below
#: used to `setdefault` in rglob order, batch/ won the race for 35 slugs and
#: would have filed real cards into a scratch directory.
_NOT_A_SET = {"batch", "needs_review", "drafts", "candidates"}


def _set_from_card_data(slug: str) -> str:
    """Fallback for a slug no set queue names: the card's OWN set identifier.

    This is what IMPLEMENTATION_GUIDE step 4 says to do -- derive the folder
    from `setIdentifiers` (SUP092 -> sup), never from the card's class.
    """
    for code in sorted(_printed_set_codes(slug)):
        if (J / code).is_dir():
            return code
    return ""


@functools.lru_cache(maxsize=1)
def _card_index() -> dict:
    try:
        return json.loads((ROOT / "card_data" / "slug_index.json")
                          .read_text(encoding="utf-8"))["by_slug"]
    except Exception:
        return {}


def _slug_to_set() -> dict[str, str]:
    """Where each card belongs, taken from the per-set work queues rather than
    the card DB's `sets` list -- a card printed in four products has four set
    names and only one directory."""
    out: dict[str, str] = {}
    for q in J.rglob("*_work_queue.json"):
        if q.parent.name in _NOT_A_SET or q.parent.name.startswith("."):
            continue
        try:
            rows = json.loads(q.read_text(encoding="utf-8"))
        except Exception:
            continue
        for row in rows:
            if isinstance(row, dict) and row.get("slug"):
                out.setdefault(row["slug"], q.parent.name)
    for path in DRAFTS.glob("*.json"):
        slug = path.stem
        # A queue can name a folder the card was never printed in -- the queues
        # are authoring TODO lists, not provenance. tests/test_card_json_hygiene
        # requires the folder to be one of the card's own set identifiers, and
        # 33 adoptions failed it before this check existed. Card data wins over
        # the queue whenever they disagree; the queue still decides between the
        # several sets a reprinted card legitimately belongs to.
        printed = _printed_set_codes(slug)
        if printed and out.get(slug) not in printed:
            out.pop(slug, None)
        if slug not in out:
            found = _set_from_card_data(slug)
            if found:
                out[slug] = found
    return out


def _printed_set_codes(slug: str) -> set:
    r"""Every set folder this card may legitimately live in.

    Derived exactly as tests/test_card_json_hygiene._set_codes does -- strip
    every non-letter and lowercase -- because that test is the rule this has to
    satisfy. A regex of the shape ^([A-Za-z]{3})\d looks equivalent and is not:
    identifiers include "1HP106" (History Pack, leading digit) and two-letter
    codes, so it silently produced NO code for those cards. Using it here moved
    33 History Pack cards out of the correct hp/ folder.
    """
    entry = _card_index().get(slug) or {}
    return {"".join(ch for ch in str(ident) if ch.isalpha()).lower()
            for ident in (entry.get("setIdentifiers") or [])}


def _all_sets(args) -> int:
    """Adopt across every set in one pass, sharing the two gate sweeps."""
    where = _slug_to_set()
    codes = sorted({c for s, c in where.items()
                    if (DRAFTS / f"{s}.json").exists() and (J / c).is_dir()})
    total = 0
    for code in codes:
        sub = argparse.Namespace(set_code=code, write=args.write,
                                 limit=args.limit, all_sets=False)
        n = _adopt_one(sub, where, quiet=True)
        total += n
        if n:
            print(f"  {code:5s} {n}")
    verb = "adopted" if args.write else "adoptable"
    print(f"\n{total} {verb} across {len(codes)} set(s)")
    if not args.write:
        print("(dry run -- pass --write to move them)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", dest="set_code")
    ap.add_argument("--all-sets", action="store_true",
                    help="every set a draft names, in one pass (the two gate "
                         "sweeps walk all 773 drafts, so running them once "
                         "beats re-running them per set)")
    ap.add_argument("--write", action="store_true", help="actually move them")
    ap.add_argument("--limit", type=int, help="adopt at most N (a first batch)")
    args = ap.parse_args()

    if args.all_sets:
        return _all_sets(args)
    if not args.set_code:
        print("pass --set CODE or --all-sets")
        return 2

    dest = J / args.set_code
    if not dest.is_dir():
        print(f"no such set directory: {dest}")
        return 2
    _adopt_one(args, _slug_to_set(), quiet=False)
    return 0


def _adopt_one(args, where, quiet: bool) -> int:
    """Gate and (optionally) adopt one set's drafts; returns how many."""
    dest = J / args.set_code
    flagged = _flagged()
    unread = _unread_params()

    picked, skipped = [], {"flagged": 0, "unreviewed": 0, "findings": 0,
                           "other set": 0, "already implemented": 0,
                           "does not compile": 0, "unread parameter": 0}
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
        if slug in unread:
            skipped["unread parameter"] += 1
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

    if not quiet:
        print(f"set {args.set_code}: {len(picked)} adoptable")
        for k, v in skipped.items():
            if v:
                print(f"   skipped {v:4d}  {k}")
        print()
        for p in picked:
            print(("adopt  " if args.write else "would  ") + p.stem)

    if not args.write:
        if not quiet:
            print("\n(dry run -- pass --write to move them)")
        return len(picked)

    for p in picked:
        shutil.copy2(p, dest / p.name)
    if not quiet:
        print(f"\nmoved {len(picked)} into {dest}")
        print("now refresh the queue:")
        print(f"   python scripts/dsl_work_queue.py --set {args.set_code} --write-queue")
    return len(picked)


if __name__ == "__main__":
    raise SystemExit(main())
