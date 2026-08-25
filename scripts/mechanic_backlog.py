"""Rank the mechanics the corpus does not implement, from card text alone.

Three attempts to have a model survey ~3000 unimplemented cards produced
nothing: the inputs were too large, and once they were small enough the run
still returned empty. But most of this question does not need a model at all.

The insight is that **card text repeats**. A phrasing that appears on many
unimplemented cards and on NO implemented card is a mechanic nobody has built;
a phrasing that appears on implemented cards is one that demonstrably can be
expressed. Ranking the first group by card count gives the same backlog the
model pass was meant to produce, mechanically and in seconds.

This is a proxy, not an oracle:

  * a phrasing may be absent from implemented cards merely because nobody has
    got to it yet, not because it is inexpressible;
  * a card can be blocked by a clause that is individually common.

So treat the output as a RANKED SHORTLIST to read, not as a verdict. Its value
is ordering ~3000 cards by how much a single fix would unlock.

Usage:
    python scripts/mechanic_backlog.py                # top phrasings
    python scripts/mechanic_backlog.py --limit 40
    python scripts/mechanic_backlog.py --show "<phrase>"   # cards using it
"""
from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSON_ROOT = ROOT / "engine" / "card_effects" / "json"
SLUG_INDEX = ROOT / "card_data" / "slug_index.json"

#: Phrases that carry no mechanic — pure keywords fire from the card DB, and
#: reminder/flavour lines would otherwise dominate the ranking.
NOISE = re.compile(
    r"^(go again|dominate|piercing|ward \d+|intimidate|blade break|phantasm|"
    r"overpower|essence of \w+|specialization|\w+ specialization|"
    r"arcane barrier \d+|battleworn \d+|temper \d+|spellvoid \d+|"
    r"once per turn|instant|action|attack reaction|defense reaction)$", re.I)


def _implemented() -> set[str]:
    out = set()
    for p in JSON_ROOT.rglob("*.json"):
        rel = p.relative_to(JSON_ROOT)
        if p.stem.endswith("_work_queue") or p.name in (
                "review_queue.json", "triage_queue.json"):
            continue
        if any(part.startswith(".") or part == "needs_review" for part in rel.parts):
            continue
        out.add(p.stem)
    return out


def _clauses(card: dict) -> list[str]:
    """Normalised sentences, with the card's own name and all numbers blanked
    so colour variants and same-shape cards collapse together."""
    text = card.get("functionalText") or ""
    text = re.sub(r"\*\*", "", text)
    name = card.get("name") or ""
    if name:
        text = text.replace(name, "@")
    out = []
    for part in re.split(r"(?<=[.!?])\s+|\n+", text):
        part = part.strip().lower()
        if not part or NOISE.match(part):
            continue
        part = re.sub(r"\d+", "#", part)
        part = re.sub(r"[^a-z@#{} ]", " ", part)
        part = re.sub(r"\s+", " ", part).strip()
        # Collapse wordings the game uses interchangeably. Without this,
        # "target weapon attack GETS +1{p}" reads as unimplemented while
        # "target weapon attack GAINS +3{p}" is implemented -- 17 cards ranked
        # as a missing mechanic that had been built the same day.
        for a, b in (("gets", "gains"), ("deals", "deal"), ("draws", "draw"),
                     ("creates", "create"), ("puts", "put"),
                     ("destroys", "destroy"), ("becomes", "become"),
                     ("costs", "cost"), ("gain a", "gain"),
                     ("your hero s soul", "your soul")):
            part = f" {part} ".replace(f" {a} ", f" {b} ").strip()
        # Short fragments are too generic to rank on.
        if len(part.split()) >= 5:
            out.append(part)
    return out


def build():
    index = json.loads(SLUG_INDEX.read_text(encoding="utf-8"))["by_slug"]
    done = _implemented()
    impl_clauses: set[str] = set()
    pending: dict[str, list[str]] = {}
    for slug, card in index.items():
        text = (card.get("functionalText") or "").strip()
        if not text:
            continue
        cl = _clauses(card)
        if slug in done:
            impl_clauses.update(cl)
        else:
            pending[slug] = cl

    # A clause NOBODY has implemented, ranked by how many cards want it.
    counts: collections.Counter = collections.Counter()
    cards_for: dict[str, list[str]] = collections.defaultdict(list)
    for slug, cl in pending.items():
        for c in set(cl):
            if c in impl_clauses:
                continue
            counts[c] += 1
            cards_for[c].append(slug)
    return counts, cards_for, len(pending), len(impl_clauses)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--show", metavar="PHRASE")
    args = ap.parse_args()

    counts, cards_for, n_pending, n_impl = build()
    if args.show:
        key = next((c for c in counts if args.show.lower() in c), None)
        if key is None:
            print("no clause matching that text")
            return 1
        print(f"{counts[key]} cards use:\n  {key}\n")
        for slug in sorted(cards_for[key]):
            print("  ", slug)
        return 0

    print(f"{n_pending} unimplemented cards with text; "
          f"{n_impl} distinct clauses already implemented somewhere")
    print(f"\nunimplemented clauses by card count (top {args.limit}) — "
          f"a ranked shortlist to READ, not a verdict:\n")
    for clause, n in counts.most_common(args.limit):
        print(f"  {n:4d}  {clause[:96]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
