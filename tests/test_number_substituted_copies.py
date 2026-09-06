"""Cards derived from one that reads the same apart from a single number.

The identical-text copier requires the two printed texts to match exactly, and
the commonest colour variant does not: "Deal 1 arcane damage" and "Deal 3
arcane damage" are one sentence with one number changed. 188 pending cards
matched an implemented card that way, so the derivation carries the number
across and records it in `_substituted`.

WHY THAT IS SAFE HERE AND NOT IN GENERAL. Three conditions have to hold before
a card is derived, and each rules out a distinct way of getting it wrong:

  exactly one number differs      counted as DISTINCT pairs, not positions: a
                                  card may print one number in several places
                                  ("Deal 2 arcane damage ... Surge - if this
                                  deals more than 2 damage") and every
                                  occurrence changes together. Two DIFFERENT
                                  differences mean two clauses changed and
                                  nothing says which JSON value is which.
  the abilities mention it as     if the JSON mentions the number a different
  often as the printed text       number of times from the text, which
                                  occurrences correspond is not established;
                                  not at all and the number the text changed is
                                  not modelled, so the copy would silently keep
                                  the source's value.
  every number in the abilities   a JSON number the printed text does not
  also appears in the text        contain is something else -- an internal
                                  amount, a duration, an index -- and its
                                  presence means the JSON's numbers and the
                                  text's numbers are not in correspondence, so
                                  the one-occurrence test proves nothing.

THE DERIVATION IS PINNED, NOT TRUSTED. Every test below re-derives the card
from its source's CURRENT abilities and requires the result to match what is on
disk. An edit to either card that breaks the correspondence fails here, rather
than leaving the pair silently out of step -- the insult_to_injury failure,
where three printings of one sentence got three implementations and the blue
one was missing a gate the other two had.
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
from scripts.copy_identical_text_cards import (_apply_substitution,
                                               _rename_self_references)
from tests.conftest import card_json_files

load_all_cards()

JSON_ROOT = ROOT / "engine" / "card_effects" / "json"
IDX = json.loads((ROOT / "card_data" / "slug_index.json")
                 .read_text(encoding="utf-8"))["by_slug"]
_NUM = re.compile(r"\d+")


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
DERIVED = sorted(s for s, raw in CARDS.items() if raw.get("_derived_from"))


def _signature(slug, blur):
    """Printed text with the card's own name substituted out, and optionally
    its numbers blurred -- the same normalisation the generator used."""
    entry = IDX.get(slug) or {}
    text = (entry.get("functionalText") or "").lower()
    for name in (entry.get("name"), entry.get("shortName")):
        if name:
            text = text.replace(str(name).lower(), "@self")
    text = re.sub(r"\s+", " ", text).strip()
    return _NUM.sub("#", text) if blur else text


def test_there_are_derived_cards_to_check():
    """A premise. If the marker were ever dropped, every test below would pass
    by iterating an empty list."""
    assert len(DERIVED) > 150, len(DERIVED)


@pytest.mark.parametrize("slug", DERIVED)
def test_the_derivation_still_reproduces_the_card(slug):
    """Re-run the substitution against the source's CURRENT abilities."""
    raw = CARDS[slug]
    source = raw["_derived_from"]
    assert source in CARDS, (
        slug + " was derived from " + source + ", which no longer exists")
    sub = raw.get("_substituted") or {}
    expected = _rename_self_references(
        _apply_substitution(CARDS[source]["abilities"], sub["from"], sub["to"]),
        source, slug)
    assert raw["abilities"] == expected, (
        slug + " no longer matches " + source + " with " + str(sub["from"])
        + " -> " + str(sub["to"]) + " applied. If it genuinely needs to differ, "
        "drop its _derived_from marker and say why in its _comment.")


@pytest.mark.parametrize("slug", DERIVED)
def test_the_two_texts_still_differ_in_exactly_that_number(slug):
    """The justification for sharing an implementation is that the sentences
    are the same sentence. A card DB update that changes either text -- or
    changes a SECOND number -- withdraws that justification."""
    raw = CARDS[slug]
    source = raw["_derived_from"]
    assert _signature(slug, blur=True) == _signature(source, blur=True), (
        "the printed texts of " + slug + " and " + source + " no longer match "
        "even with numbers blurred")
    a = _NUM.findall(_signature(source, blur=False))
    b = _NUM.findall(_signature(slug, blur=False))
    # DISTINCT pairs, not positions. A card may print one number in several
    # places -- "Deal 2 arcane damage ... Surge - if this deals more than 2
    # damage" -- and every occurrence changes together in the colour variant.
    # That is still ONE substitution; counting positions rejected the whole
    # Surge family for differing "twice".
    diffs = {(x, y) for x, y in zip(a, b) if x != y}
    sub = raw["_substituted"]
    assert diffs == {(sub["from"], sub["to"])}, (
        slug + " and " + source + " now differ in " + str(sorted(diffs))
        + ", not just the recorded " + str(sub["from"]) + " -> " + str(sub["to"]))


@pytest.mark.parametrize("slug", DERIVED)
def test_the_substituted_number_reached_the_json(slug):
    """The whole point. A derivation that recorded a substitution but shipped
    the SOURCE's number would be a card that reads +3{p} and gives +1{p} --
    which is exactly what a plain copy of a colour variant does, and why this
    family exists instead of one."""
    raw = CARDS[slug]
    sub = raw["_substituted"]
    blob = json.dumps(raw["abilities"])
    whole = re.compile(r"(?<![\d.])%s(?![\d.])" % re.escape(str(sub["to"])))
    assert whole.search(blob), (
        slug + " records a substitution to " + str(sub["to"])
        + " that does not appear in its abilities")


@pytest.mark.parametrize("slug", DERIVED)
def test_a_derived_card_compiles(slug):
    assert get_card(slug) is not None, slug + " does not load"


@pytest.mark.parametrize("slug", DERIVED)
def test_a_derived_card_does_not_carry_the_wrong_card_level_metadata(slug):
    """activation_cost / per_turn / setup describe one specific printing. They
    may travel between colour variants of a card; they must not travel between
    two cards that merely read alike."""
    source = CARDS[slug]["_derived_from"]
    strip = re.compile(r"_(red|yellow|blue)$")
    if strip.sub("", slug) == strip.sub("", source):
        return
    for key in ("activation_cost", "per_turn", "setup", "cost", "cost_modifiers"):
        assert key not in CARDS[slug], (
            slug + " carries " + key + " derived from the unrelated card " + source)
