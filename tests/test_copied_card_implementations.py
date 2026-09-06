"""471 cards implemented by copying a card with identical printed text.

Card text repeats. Colour variants of one card are the same sentence, and
unrelated cards share whole sentences outright -- "Deal 4 arcane damage to any
target" is both Aether Hail and Ice Bolt. Where the printed text is IDENTICAL
after substituting each card's own name, the DSL is identical too: cost, pitch,
power and colour all come from the card DB, not from the JSON.

THE COPIES ARE PINNED, NOT TRUSTED. Every one carries `_copied_from`, and this
file asserts that its abilities still match that source's and that the two
printed texts still agree. Without that, an edit to one printing quietly leaves
the others behind -- which is exactly the insult_to_injury failure: three
printings of one sentence with three different implementations, and the blue one
missing a gate the other two had. Copying at this scale would industrialise that
failure if nothing held the group together.

WHAT WAS DELIBERATELY NOT COPIED. 30 cards matched on text and were held back,
because identical text does not always mean identical implementation:

    hero cards (16)        heroes carry `setup` (weapon zones) and activation
                           metadata that belongs to the printing, not the text
    card types differ (8)  a Block behaves differently from an Action reading
                           the same sentence
    unread parameters (4)  the source has an audit_params finding -- a clause
                           the compiler never reads, which silently does
                           nothing. Copying turns one defective card into
                           three, and the first run of the generator did
                           exactly that, taking audit_params from 15 findings
                           to 21 before those four were withdrawn.
    printed keywords       the DB grants keywords, so a source declaring
    differ (1)             `conditional_keywords` for a keyword the target does
                           not print carries a meaningless declaration
    metadata + different   activation_cost / per_turn are DSL-authoritative and
    name (1)               about one specific card

`scripts/copy_identical_text_cards.py --held-back` lists them.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card_effects.dsl.loader import get_card, load_all_cards
from tests.conftest import card_json_files

load_all_cards()

JSON_ROOT = ROOT / "engine" / "card_effects" / "json"
IDX = json.loads((ROOT / "card_data" / "slug_index.json")
                 .read_text(encoding="utf-8"))["by_slug"]


def _all_cards():
    out = {}
    for path in card_json_files(JSON_ROOT):
        rel = path.relative_to(JSON_ROOT)
        if path.stem.endswith("_work_queue") or any(
                p.startswith(".") or p == "needs_review" for p in rel.parts):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(raw, dict) and raw.get("slug"):
            out[raw["slug"]] = raw
    return out


CARDS = _all_cards()
COPIES = sorted(s for s, raw in CARDS.items() if raw.get("_copied_from"))


def _signature(slug):
    """Printed text with the card's own name substituted out, so "If Promise of
    Plenty hits" and "If Fervent Forerunner hits" compare equal."""
    entry = IDX.get(slug) or {}
    text = (entry.get("functionalText") or "").lower()
    for name in (entry.get("name"), entry.get("shortName")):
        if name:
            text = text.replace(str(name).lower(), "@self")
    return re.sub(r"\s+", " ", text).strip()


def test_there_are_copies_to_check():
    """A premise. If the copies were ever inlined or the marker dropped, every
    test below would pass by iterating an empty list."""
    assert len(COPIES) > 400, len(COPIES)


@pytest.mark.parametrize("slug", COPIES)
def test_a_copy_still_matches_its_source(slug):
    from scripts.copy_identical_text_cards import _rename_self_references

    source = CARDS[slug]["_copied_from"]
    assert source in CARDS, (
        slug + " was copied from " + source + ", which no longer exists")
    # ONE thing legitimately differs: a string in which the source names ITSELF
    # by slug. ability_keywords.fuse writes its marker as f"fused_{card.slug}",
    # so a copy carrying `{"flag": "fused_buzz_bolt_blue"}` would ask whether a
    # DIFFERENT card had been fused -- false in every state, and silent. Thirty
    # copies shipped that way. The copy repoints those at itself, so the
    # comparison has to apply the same repointing to the source.
    expected = _rename_self_references(CARDS[source]["abilities"], source, slug)
    assert CARDS[slug]["abilities"] == expected, (
        slug + " has drifted from " + source + ". They implement one printed "
        "sentence; if this one genuinely needs to differ, drop its "
        "_copied_from marker and say why in its _comment.")


def test_no_card_gates_on_another_cards_identity():
    """The defect the repointing exists to prevent, checked corpus-wide.

    A flag named after a DIFFERENT card, or a `source_slug` pointing at one, is
    a gate that can never be true. It loads, it compiles, it reads all its
    parameters -- and the clause under it never runs. Nothing else in the suite
    would notice.
    """
    import json as _json
    bad = []
    for slug, raw in CARDS.items():
        blob = _json.dumps(raw.get("abilities") or [])
        for other in (raw.get("_copied_from"), raw.get("_derived_from")):
            if other and other != slug and other in blob:
                bad.append(slug + " names " + other)
    assert not bad, (
        "these cards gate on another card's identity, so the gate is false in "
        "every state:\n  " + "\n  ".join(sorted(bad)))


@pytest.mark.parametrize("slug", COPIES)
def test_the_two_printed_texts_still_agree(slug):
    """The justification for the copy is that the texts are the same. If a card
    DB update changes one of them, the shared implementation stops being
    justified and this is where that shows up."""
    source = CARDS[slug]["_copied_from"]
    assert _signature(slug) == _signature(source), (
        "the printed texts of " + slug + " and " + source + " no longer match, "
        "so sharing an implementation is no longer justified")


@pytest.mark.parametrize("slug", COPIES)
def test_a_copy_compiles(slug):
    assert get_card(slug) is not None, slug + " does not load"


@pytest.mark.parametrize("slug", COPIES)
def test_a_copy_does_not_carry_the_wrong_card_level_metadata(slug):
    """activation_cost / per_turn / setup are DSL-authoritative and describe one
    specific printing. They may travel between colour variants of a card; they
    must not travel between two cards that merely read alike."""
    source = CARDS[slug]["_copied_from"]
    strip = re.compile(r"_(red|yellow|blue)$")
    if strip.sub("", slug) == strip.sub("", source):
        return
    for key in ("activation_cost", "per_turn", "setup", "cost", "cost_modifiers"):
        assert key not in CARDS[slug], (
            slug + " carries " + key + " copied from the unrelated card "
            + source)


def test_no_copy_came_from_a_card_with_unread_parameters():
    """An unread parameter is a clause the compiler never reads: it fails
    exactly like an invented type, silently. Copying such a card multiplies the
    defect, and four copies had to be withdrawn for this reason."""
    from scripts.audit_params import audit_node, build_index

    index = build_index()

    def findings(node, out):
        if isinstance(node, dict):
            out.extend(audit_node(node, index) or [])
            for value in node.values():
                findings(value, out)
        elif isinstance(node, list):
            for value in node:
                findings(value, out)
        return out

    bad = []
    for slug in COPIES:
        source = CARDS[slug]["_copied_from"]
        if findings(CARDS[source].get("abilities"), []):
            bad.append("%s <- %s" % (slug, source))
    assert not bad, (
        "these copies were taken from cards with unread parameters, so one "
        "silent defect is now several:\n  " + "\n  ".join(bad))


def test_every_copy_records_where_it_came_from():
    """The marker is what makes the group checkable. A copy without it is
    indistinguishable from an independently authored card that happens to
    agree."""
    for slug in COPIES:
        assert CARDS[slug].get("_comment"), slug + " has no _comment"
        assert CARDS[slug]["_copied_from"] in CARDS[slug]["_comment"], (
            slug + "'s comment does not name the card it was copied from")
