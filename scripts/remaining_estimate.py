#!/usr/bin/env python3
"""How many cards are ACTUALLY left to implement, as opposed to how many slugs.

Summing the per-set work queues gives ~3,500 and is wrong in three directions
at once:

  * reprints double-count. Over 2,000 of the ~4,600 cards list more than one
    set, so a card pending in four sets is counted four times;
  * many cards have no functional text at all, or text that is nothing but
    keywords the engine already implements from the card DB. Those need a JSON
    file, but not an implementation;
  * card text REPEATS. Colour variants of one card differ only in a number, and
    unrelated cards share whole sentences. Once one member of a text-group is
    implemented, the rest are a copy rather than a fresh reading.

This script buckets the remaining slugs so the number that matters -- distinct
pieces of card behaviour nobody has written yet -- is separated from the slug
count.

    python scripts/remaining_estimate.py
    python scripts/remaining_estimate.py --show-groups 25
    python scripts/remaining_estimate.py --extendable      # implemented -> pending

IT IS AN ESTIMATE AND ERRS OPTIMISTIC ON GROUPING. Two cards with identical
text really are one implementation, but "differs only in a number" is judged on
the text alone: a card whose numbers are wired to different mechanics still
reads as a variant here. Treat the grouped figure as a floor on the work and the
distinct-text figure as the honest target.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

JSON_ROOT = ROOT / "engine" / "card_effects" / "json"

#: Bold runs are keyword markup (**Go again**, **Ward 1**). A card whose whole
#: functional text is keywords needs no DSL effects -- the engine implements
#: them from the card DB `keywords` field.
_BOLD = re.compile(r"\*\*.*?\*\*")
_NUM = re.compile(r"\d+")
_COLOUR_SUFFIX = re.compile(r"_(red|yellow|blue)$")


def implemented_slugs() -> set[str]:
    """Slugs with a card JSON, skipping pipeline artifacts and queues.

    Never a bare rglob: the drafting pipeline writes candidate JSON into
    dot-directories under the card tree, and ~48 test files once counted those
    as implemented cards.
    """
    out = set()
    for path in JSON_ROOT.rglob("*.json"):
        rel = path.relative_to(JSON_ROOT)
        if path.stem.endswith("_work_queue") or any(
                p.startswith(".") or p == "needs_review" for p in rel.parts):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(raw, dict) and raw.get("slug"):
            out.add(raw["slug"])
    return out


def text_of(entry: dict) -> str:
    return (entry.get("functionalText") or "").strip()


def is_keyword_only(entry: dict) -> bool:
    """Nothing left once keyword markup and punctuation are stripped."""
    left = _BOLD.sub("", text_of(entry))
    return not re.sub(r"[^A-Za-z0-9]", "", left)


def signature(entry: dict, blur_numbers: bool) -> str:
    """A card's text with its own name and (optionally) its numbers removed.

    The name substitution matters: "If Promise of Plenty hits" and "If Fervent
    Forerunner hits" are the same sentence about different cards, and comparing
    raw text would call them distinct.
    """
    text = text_of(entry).lower()
    name = (entry.get("name") or "").lower()
    if name:
        text = text.replace(name, "@self")
        short = (entry.get("shortName") or "").lower()
        if short and short != name:
            text = text.replace(short, "@self")
    text = re.sub(r"\s+", " ", text)
    if blur_numbers:
        text = _NUM.sub("#", text)
    return text.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--show-groups", type=int, default=0,
                    help="list the N largest unimplemented text-groups")
    ap.add_argument("--extendable", action="store_true",
                    help="list pending cards whose text an IMPLEMENTED card already covers")
    args = ap.parse_args()

    idx = json.loads((ROOT / "card_data" / "slug_index.json")
                     .read_text(encoding="utf-8"))["by_slug"]
    have = implemented_slugs()

    # Tokens, card backs and expansion slots are not cards anyone plays.
    playable = {s: e for s, e in idx.items()
                if not e.get("isCardBack") and not e.get("isExpansionSlot")}

    pending = {s: e for s, e in playable.items() if s not in have}

    blank = {s for s, e in pending.items() if not text_of(e)}
    kw_only = {s for s, e in pending.items()
               if s not in blank and is_keyword_only(e)}
    substantive = {s: e for s, e in pending.items()
                   if s not in blank and s not in kw_only}

    # What an implemented card already covers.
    impl_exact = collections.defaultdict(list)
    impl_blur = collections.defaultdict(list)
    for slug in have:
        entry = idx.get(slug)
        if not entry or not text_of(entry):
            continue
        impl_exact[signature(entry, False)].append(slug)
        impl_blur[signature(entry, True)].append(slug)

    covered_exact, covered_blur = {}, {}
    for slug, entry in substantive.items():
        sig = signature(entry, False)
        if sig in impl_exact:
            covered_exact[slug] = impl_exact[sig][0]
            continue
        sig_b = signature(entry, True)
        if sig_b in impl_blur:
            covered_blur[slug] = impl_blur[sig_b][0]

    novel = {s: e for s, e in substantive.items()
             if s not in covered_exact and s not in covered_blur}

    # Among the genuinely novel, how many DISTINCT texts are there?
    groups_exact = collections.defaultdict(list)
    groups_blur = collections.defaultdict(list)
    for slug, entry in novel.items():
        groups_exact[signature(entry, False)].append(slug)
        groups_blur[signature(entry, True)].append(slug)

    if args.extendable:
        print("PENDING CARDS AN IMPLEMENTED CARD ALREADY COVERS\n")
        print("-- identical text (a copy, modulo the slug) --")
        for slug, src in sorted(covered_exact.items()):
            print("  %-38s <- %s" % (slug, src))
        print("\n-- identical but for the numbers (a copy plus an amount) --")
        for slug, src in sorted(covered_blur.items()):
            print("  %-38s <- %s" % (slug, src))
        return 0

    if args.show_groups:
        print("LARGEST UNIMPLEMENTED TEXT-GROUPS "
              "(one implementation covers the whole row)\n")
        for sig, slugs in sorted(groups_blur.items(),
                                 key=lambda kv: -len(kv[1]))[:args.show_groups]:
            print("  %2d  %s" % (len(slugs), ", ".join(sorted(slugs)[:4])
                                 + ("..." if len(slugs) > 4 else "")))
            print("      %s" % sig[:150].replace("\n", " "))
        return 0

    total = len(playable)
    print("SLUG COUNTS")
    print("  playable cards in the DB      %5d" % total)
    print("  implemented                   %5d" % len(have & set(playable)))
    print("  pending (slugs)               %5d" % len(pending))
    print()
    print("WHAT THE PENDING SLUGS ACTUALLY ARE")
    print("  no functional text at all     %5d   nothing to implement" % len(blank))
    print("  keyword-only text             %5d   the engine already does it"
          % len(kw_only))
    print("  text an implemented card has  %5d   copy an existing file"
          % (len(covered_exact) + len(covered_blur)))
    print("      of which identical        %5d" % len(covered_exact))
    print("      of which differs by number%5d" % len(covered_blur))
    print("  genuinely unwritten behaviour %5d" % len(novel))
    print()
    print("THE NUMBER THAT MATTERS")
    print("  distinct texts among those    %5d   ignoring numeric variants"
          % len(groups_blur))
    print("  distinct exact texts          %5d   counting numeric variants apart"
          % len(groups_exact))
    print()
    dup = len(novel) - len(groups_blur)
    print("  So the ~%d pending slugs are ~%d distinct pieces of behaviour;"
          % (len(pending), len(groups_blur)))
    print("  %d are free or near-free (blank, keyword-only, or already-written"
          % (len(blank) + len(kw_only) + len(covered_exact) + len(covered_blur)))
    print("  text) and a further %d are variants of another pending card." % dup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
