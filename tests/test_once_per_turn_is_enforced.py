"""Every "Once per Turn" card really is limited -- from wherever that comes.

A review pass flagged 21 cards as missing the DSL `per_turn` field and called
the limit dropped. The field really is absent on all 21, and it really is what
play.py's activation check ultimately consults -- but not the way that reads.

`card.py` parses "once/twice/thrice per turn" out of the printed ability type
and sets `has_per_turn_limit` / `activations` from it. The DSL field is an
OVERRIDE layered on top (schema.py: "None = fall back to text"), so a card that
omits it inherits the printed limit and is already enforced. Adding `per_turn:
1` to those 21 changed nothing at all: measured before and after, every one
already reported has_per_turn_limit=True, activations=1.

So the finding is dropped rather than acted on, and this test is what replaces
it. It does not care WHERE the limit comes from -- only that a card whose text
says "once per turn" has one. That covers the case the review pass was really
worried about (a card with no limit) and the one it could not see (the text
parser silently stopping, which would take all 39 down at once and which no
per-card JSON field would protect against).

The lesson is the recurring one, and it has now cost two mass edits' worth of
near-misses: a mechanic can already work under a name you did not grep for.
Measure the behaviour before changing 21 files to add it.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card import CardDB
from engine.card_effects.dsl.loader import load_all_cards

load_all_cards()
DB = CardDB()

JSON_ROOT = ROOT / "engine" / "card_effects" / "json"

#: The printed wordings and the number each means.
COUNTS = {"once": 1, "twice": 2, "thrice": 3}
PHRASE = re.compile(r"\b(once|twice|thrice) per turn\b", re.I)


def _implemented_slugs_saying_per_turn():
    idx = json.load(open(ROOT / "card_data" / "slug_index.json",
                         encoding="utf-8"))["by_slug"]
    out = []
    for path in JSON_ROOT.rglob("*.json"):
        rel = path.relative_to(JSON_ROOT)
        if (path.stem.endswith("_work_queue")
                or any(p.startswith(".") or p == "needs_review"
                       for p in rel.parts)):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        # A card file is a JSON OBJECT. The pipeline worktree keeps list-shaped
        # queue files inside this tree, and this walk ran at import time, so a
        # bare raw.get() there raised during COLLECTION and took the entire
        # suite down with it rather than failing one test.
        if not isinstance(raw, dict):
            continue
        slug = raw.get("slug")
        text = idx.get(slug, {}).get("functionalText") or ""
        m = PHRASE.search(text)
        if m:
            out.append((slug, COUNTS[m.group(1).lower()]))
    return sorted(out)


SLUGS = _implemented_slugs_saying_per_turn()


def test_the_sweep_finds_cards_at_all():
    """A premise: if the phrase or the corpus moves, the parametrised test
    below would silently cover nothing."""
    assert len(SLUGS) >= 30, len(SLUGS)


@pytest.mark.parametrize("slug,expected", SLUGS)
def test_a_per_turn_card_carries_its_limit(slug, expected):
    card = DB.get(slug)
    assert card is not None, slug
    assert getattr(card, "has_per_turn_limit", False), (
        f"{slug} says 'per turn' and has no activation limit at all")
    assert getattr(card, "activations", None) == expected, (
        f"{slug} allows {getattr(card, 'activations', None)} activations, "
        f"text says {expected}")
