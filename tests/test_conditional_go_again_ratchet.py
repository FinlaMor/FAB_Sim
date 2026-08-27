"""Cards that PRINT go again but whose text makes it conditional.

The card database has no way to mark a keyword conditional, so a printed
GoAgain is granted unconditionally. A card reading "IF <x>, this gets go again"
therefore has it always, whatever its JSON says -- the gate is decoration, and
the card is strictly stronger than printed.

`loader.conditional_keywords()` is what takes the printed keyword away, and it
recognises exactly one shape: an ability gated on SOURCE_IS_ATTACK that grants
the keyword. That is what separates "THIS gains go again" from Luminaris's
"your Illusionist attacks get go again", where the printed listing on the
weapon is the card database flattening a sentence about OTHER cards.

Aggressive Pounce was the first of these fixed, with the official release notes
confirming the timing. The sweep below found the class is far larger: 50 cards
whose text gates go again and whose JSON does not strip the printed keyword.

WHY THIS IS A RATCHET AND NOT A FIX. Of those 50, 47 already grant GO_AGAIN
with the right condition and only lack SOURCE_IS_ATTACK -- but they grant it
from TRIGGERED, PLAY or ACTIVATE abilities, and moving them to the WHILE_STATIC
form is a SEMANTIC change, not a mechanical one: it moves the condition from
being read once to being read continuously (CR 6.2.3d). Thirty-two such
conversions applied blind would be a mass edit of exactly the kind that has
already produced two self-inflicted bugs in this effort. So the count is pinned
here and the backlog is worked down deliberately, card by card, with the
printed text and the release notes in hand.

Not every hit is real: Luminaris is in the sweep and must NOT be converted --
its go again belongs to other cards.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card_effects.dsl.loader import conditional_keywords, load_all_cards

load_all_cards()

JSON_ROOT = ROOT / "engine" / "card_effects" / "json"
_COND = re.compile(r"\b(if|whenever|while)\b[^.]{0,120}?\bgo again\b", re.I)

#: Cards already converted, which must STAY converted.
FIXED = ["aggressive_pounce_red", "aggressive_pounce_blue",
         "aggressive_pounce_yellow", "scar_for_a_scar_red", "grow_wings_blue"]

#: The count of cards still carrying an unconditional printed go again their
#: text gates. Lower it as they are fixed; it must never rise.
UNFIXED_LIMIT = 48


def _unstripped():
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
        slug = raw.get("slug")
        entry = idx.get(slug) or {}
        kws = [str(k).lower() for k in (entry.get("keywords") or [])]
        text = entry.get("functionalText") or ""
        if "goagain" not in kws or not _COND.search(text):
            continue
        if "goagain" not in conditional_keywords(slug):
            out.append(slug)
    return sorted(out)


def test_the_sweep_still_matches_cards():
    """A premise: if the phrasing or the keyword spelling moved, the ratchet
    below would pass by measuring nothing."""
    idx = json.load(open(ROOT / "card_data" / "slug_index.json",
                         encoding="utf-8"))["by_slug"]
    gated = [s for s, e in idx.items()
             if "goagain" in [str(k).lower() for k in (e.get("keywords") or [])]
             and _COND.search(e.get("functionalText") or "")]
    assert len(gated) > 30, len(gated)


@pytest.mark.parametrize("slug", FIXED)
def test_a_fixed_card_stays_fixed(slug):
    assert "goagain" in conditional_keywords(slug), (
        f"{slug} is back to an unconditional printed go again")


def test_the_unfixed_count_does_not_grow():
    left = _unstripped()
    assert len(left) <= UNFIXED_LIMIT, (
        f"{len(left)} cards print go again unconditionally while their text "
        f"gates it (limit {UNFIXED_LIMIT}):\n  " + "\n  ".join(left))


def test_luminaris_is_not_converted():
    """It grants go again to OTHER cards. Its printed keyword is the database
    flattening that sentence, and the SOURCE_IS_ATTACK form would be a lie
    about what the card does."""
    assert "goagain" not in conditional_keywords("luminaris")
