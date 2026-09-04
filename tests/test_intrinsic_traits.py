"""Colors of Aria is Earth, Ice and Lightning in every zone.

"While this is face-up in any zone, it's Earth, Ice, and Lightning." The card DB
types it Elemental only, and the card had no DSL file at all — correctly so,
because the DSL cannot express this. WHILE_STATIC is dispatched from
engine._dsl_recalc_listener, which walks the attack card, both heroes and the
in-play permanents; it never looks in a graveyard, banished zone or deck. A
static that applies "in any zone" is unreachable by every mechanism the DSL has.

WHY IT MATTERS BEYOND ITSELF, and how it was found: replaying real attacks
against Talishar (scripts/talishar_attack_replay.py) showed
felling_of_the_crown_red computing 4 power where Talishar computed 8. Its +4
needs "4 or more Earth cards in your banished zone"; with Colors of Aria sitting
face-up in banish the real count is 4 and ours was 3. An UNIMPLEMENTED card was
silently corrupting an IMPLEMENTED card's condition — a defect class that no
amount of testing Felling of the Crown on its own would ever surface.
"""
from __future__ import annotations

import copy

import pytest

from engine.card import CardDB
from engine.card_effects.dsl.condition_types import compile_condition
from engine.card_effects.dsl.loader import load_all_cards
from engine.card_effects.intrinsic_traits import INTRINSIC_TALENTS, talents_for
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

ARIA = "colors_of_aria_red"


def test_the_card_carries_all_three_talents():
    card = DB.get(ARIA)
    assert card is not None
    have = {t.lower() for t in (card.talents or [])}
    assert {"earth", "ice", "lightning"} <= have, card.talents


def test_the_printed_talent_is_kept():
    """Additive, not a replacement — it is still an Elemental card."""
    assert "Elemental" in (DB.get(ARIA).talents or [])


def test_other_cards_are_untouched():
    assert (DB.get("elemental_strike_red").talents or []) == ["Elemental"]
    assert (DB.get("autumns_touch_blue").talents or []) == ["Earth"]


def test_no_duplicates_if_a_talent_is_also_printed():
    assert talents_for(ARIA, ["Earth"]).count("Earth") == 1


def test_a_slug_with_no_entry_passes_through():
    assert talents_for("head_jab_red", ["Ninja"]) == ["Ninja"]
    assert talents_for("head_jab_red", None) == []


def test_the_table_only_names_cards_that_exist():
    """A typo'd slug here would be silently inert."""
    for slug in INTRINSIC_TALENTS:
        assert DB.get(slug) is not None, "%s is not a real card" % slug


def test_it_counts_as_earth_in_the_banished_zone():
    """The observable consequence, and the reason this exists: the condition
    felling_of_the_crown_red actually asks."""
    st = _make_state()
    st.card_db = DB
    for slug in ("autumns_touch_blue", "crumble_to_eternity_blue",
                 "sow_tomorrow_blue", ARIA):
        card = copy.deepcopy(DB.get(slug))
        card.owner = card.controller = 1
        st.players[1].banished.add(card)

    condition = compile_condition(
        "CARD_IN_ZONE",
        {"zone": "banished", "card_class": "Earth", "count_gte": 4,
         "face_up": True})
    probe = copy.deepcopy(DB.get("felling_of_the_crown_red"))
    probe.owner = probe.controller = 1

    assert condition(probe, None, st), (
        "three printed Earth cards plus Colors of Aria should satisfy "
        "'4 or more Earth cards in your banished zone'")


def test_three_earth_cards_alone_are_not_enough():
    """The other half — without Colors of Aria the count really is short, so
    the test above is measuring the card and not a broken condition."""
    st = _make_state()
    st.card_db = DB
    for slug in ("autumns_touch_blue", "crumble_to_eternity_blue",
                 "sow_tomorrow_blue"):
        card = copy.deepcopy(DB.get(slug))
        card.owner = card.controller = 1
        st.players[1].banished.add(card)

    condition = compile_condition(
        "CARD_IN_ZONE",
        {"zone": "banished", "card_class": "Earth", "count_gte": 4,
         "face_up": True})
    probe = copy.deepcopy(DB.get("felling_of_the_crown_red"))
    probe.owner = probe.controller = 1

    assert not condition(probe, None, st)
