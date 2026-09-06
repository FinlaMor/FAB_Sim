#!/usr/bin/env python3
"""Rank the unimplemented corpus by how many cards ONE authored card unlocks.

Hand-authoring is the expensive step, so the question worth asking is not
"which card should I write next" but "which card, once written, writes the
others". `copy_identical_text_cards.py --substitute-numbers` will propagate an
implementation to every pending card whose printed text is the same sentence,
allowing for one number -- so a group of six pending cards that share a
sentence costs ONE card to implement and yields six.

That is the whole ordering. 814 of the ~2,400 pending cards sit in groups of
three or more with no printing implemented, which is exactly why the copier had
nothing to copy from: the group is unimplemented as a unit.

    python scripts/group_work_queue.py              # top 40 groups
    python scripts/group_work_queue.py --limit 200
    python scripts/group_work_queue.py --min-size 2
    python scripts/group_work_queue.py --json out.json

The suggested card is the alphabetically-first of the group, but any member
does: the copier's `_rank` picks the most structurally compatible source for
each target, and prefers an exact text match over a substituted one. Prefer a
member whose printed keywords and card types are the group's most common, since
those two differences are what hold a copy back.

WHAT THIS DOES NOT MEASURE. Group size is a multiplier, not a difficulty. A
six-card group whose sentence needs a primitive that does not exist is worse
value than a three-card group of plain arcane damage. Read the text before
committing to one.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.remaining_estimate import (implemented_slugs, is_keyword_only,  # noqa: E402
                                        signature, text_of)


def groups(min_size: int):
    idx = json.loads((ROOT / "card_data" / "slug_index.json")
                     .read_text(encoding="utf-8"))["by_slug"]
    have = implemented_slugs()
    pending = {
        slug: entry for slug, entry in idx.items()
        if slug not in have
        and not entry.get("isCardBack") and not entry.get("isExpansionSlot")
        and text_of(entry) and not is_keyword_only(entry)
        # Heroes carry setup and activation metadata about the printing rather
        # than the text, so they are never copy targets and do not belong in a
        # queue ordered by copy yield.
        and "Hero" not in (entry.get("types") or [])
    }
    by_text = collections.defaultdict(list)
    for slug, entry in pending.items():
        by_text[signature(entry, True)].append(slug)
    out = [(len(v), sorted(v), idx[sorted(v)[0]]) for v in by_text.values()
           if len(v) >= min_size]
    out.sort(key=lambda row: (-row[0], row[1][0]))
    return out, len(pending)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--min-size", type=int, default=3,
                    help="smallest group to list (default 3)")
    ap.add_argument("--json", dest="json_path",
                    help="also write the full ranking to this file")
    args = ap.parse_args()

    rows, pending = groups(args.min_size)
    covered = sum(n for n, _, _ in rows)
    print(f"{pending} pending cards; {len(rows)} groups of >={args.min_size} "
          f"cover {covered} of them ({covered * 100 // max(pending, 1)}%)\n")

    for n, slugs, entry in rows[:args.limit]:
        text = (entry.get("functionalText") or "").replace("\n", " / ")
        print(f"{n:>3}x  {slugs[0]}")
        print(f"      {text[:150]}")
        if len(slugs) > 1:
            print(f"      + {', '.join(slugs[1:])}")

    if args.json_path:
        Path(args.json_path).write_text(json.dumps(
            [{"unlocks": n, "author": s[0], "group": s,
              "text": (e.get("functionalText") or "")}
             for n, s, e in rows], indent=2), encoding="utf-8")
        print(f"\nwrote {args.json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
