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
from tests.conftest import card_json_files

load_all_cards()

JSON_ROOT = ROOT / "engine" / "card_effects" / "json"
_COND = re.compile(r"\b(if|whenever|while)\b[^.]{0,120}?\bgo again\b", re.I)

#: Cards already converted, which must STAY converted.
FIXED = ["aggressive_pounce_red", "aggressive_pounce_blue",
         "aggressive_pounce_yellow", "scar_for_a_scar_red", "grow_wings_blue",
         # Converted from their already-fixed siblings, which is the safest
         # kind of conversion available here: identical printed text, a shape
         # already verified, and no new judgement about what the card means.
         "grow_wings_red", "blow_for_a_blow_red",
         # Copied wholesale from a sibling with IDENTICAL printed text that was
         # already converted. 29 backlog cards have a sibling outside the
         # backlog, but only these three had both identical text AND a sibling
         # using the verified shape -- the rest are outside it for unrelated
         # reasons, and copying to them would have been guesswork.
         "grow_wings_yellow", "promise_of_plenty_blue", "scar_for_a_scar_blue"]

#: The count of cards still carrying an unconditional printed go again their
#: text gates. Lower it as they are fixed; it must never rise.
#:
#: This was 48 before the two carve-outs below were applied. Six of those were
#: never defects: three print go again on its own line and three hand it to
#: another card. Luminaris was one of them -- counted in the backlog by the very
#: file that documents why it must never be converted.
UNFIXED_LIMIT = 37


def _prints_go_again_outright(text):
    """A line that IS the keyword is an unconditional printed go again, and a
    gated sentence elsewhere on the card is about something else. Channel the
    Thunder Steppe prints go again AND grants it to action cards you play."""
    for line in text.splitlines():
        if line.replace("*", "").replace("-", "").strip().lower() == "go again":
            return True
    return False


def _go_again_is_about_itself(text, name):
    """Luminaris's distinction, applied to the printed text rather than to the
    JSON: "the attack gets go again" hands the keyword to ANOTHER card, and the
    DB lists it here only because it flattens the sentence. Only a card that
    gives ITSELF go again can have its printed keyword stripped."""
    low = text.lower()
    subjects = ["this get", "this gain", "it get", "it gain"]
    if name:
        subjects += [name.lower() + " get", name.lower() + " gain"]
    return any(sub in low for sub in subjects)


def _unstripped():
    idx = json.load(open(ROOT / "card_data" / "slug_index.json",
                         encoding="utf-8"))["by_slug"]
    out = []
    for path in card_json_files(JSON_ROOT):
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
        # Two shapes the sweep matches but that are not defects. Without them
        # the backlog number is inflated and, worse, it moves for reasons that
        # have nothing to do with cards being fixed.
        if _prints_go_again_outright(text):
            continue
        if not _go_again_is_about_itself(text, entry.get("name") or ""):
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


#: Matched by the sweep, but not defects. Kept by name because the whole value
#: of the ratchet is that its number moves only when a card is actually fixed.
NOT_DEFECTS = ["luminaris", "bonds_of_ancestry_red", "current_funnel_blue",
               "knife_through_butter_blue", "painful_passage_red",
               "quick_succession_red"]


@pytest.mark.parametrize("slug", NOT_DEFECTS)
def test_a_false_positive_stays_out_of_the_backlog(slug):
    """These print go again outright, or grant it to another card. Counting
    them made the backlog look six cards worse than it is, and would have sent
    someone to 'fix' a correct card."""
    assert slug not in _unstripped(), (
        f"{slug} is being counted as a gated-go-again defect again")


def test_luminaris_is_not_converted():
    """It grants go again to OTHER cards. Its printed keyword is the database
    flattening that sentence, and the SOURCE_IS_ATTACK form would be a lie
    about what the card does."""
    assert "goagain" not in conditional_keywords("luminaris")
