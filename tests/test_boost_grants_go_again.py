"""Boost never granted go again, because a class was read out of `types`.

CR 8.3.9: boost means "As an additional cost to play this, you may banish the
top card of your deck. If you do, if it's a Mechanologist card, this gets go
again." The check was written `if "Mechanologist" in top.types`. A card's
`types` holds Action / Attack / Equipment / Weapon; the CLASS lives in
`classes`. So the branch was false for every card ever banished, and the whole
go-again half of boost was dead — every boost paid the cost and granted nothing.

Found by differential-testing against real Talishar games rather than by
reading the code. Talishar publishes the resolved keyword flags of the live
attack, so 318,870 real attacks say what a card's keywords actually are. Twenty
cards came back with go_again true in ~100% of appearances while our data has
no such keyword — all of them Boost cards in Mechanologist decks, where the
banished card is nearly always a Mechanologist card. That was the tell.

CR 8.3.9a is the other half and it is what makes this test two-sided: the
player has boosted, and the card has been banished, *even when the banished
card is not a Mechanologist card*. Only the go-again grant is conditional. A
test that checked go again alone would pass on an implementation that skipped
the banish entirely when the class did not match.
"""
from __future__ import annotations

import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.ability_keywords import boost
from engine.card_effects.dsl.loader import load_all_cards
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

BOOSTER = "zipper_hit_red"          # Mechanologist attack with **Boost**
MECH = "t_bone_red"                 # classes == ["Mechanologist"]
GENERIC = "wounded_bull_red"        # classes == ["Generic"]


def _card(slug, owner=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = owner
    return c


def _state_with_top(slug):
    """A state whose player-1 deck has `slug` on top and who always says yes."""
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": (True if True in o else o[0]),
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    st.players[1].deck.cards = [_card(slug)]
    return st


def test_the_class_really_is_absent_from_types():
    """The premise. If card data ever moved the class into `types`, the fix
    below would be pointless and this test says so directly."""
    mech = DB.get(MECH)
    assert "Mechanologist" in (mech.classes or [])
    assert "Mechanologist" not in (mech.types or []), (
        "card data now carries the class in `types`; boost's original check "
        "would work and this whole test is measuring nothing")


def test_boosting_a_mechanologist_card_grants_go_again():
    st = _state_with_top(MECH)
    card = _card(BOOSTER)

    assert not card.has_go_again, "%s must not start with go again" % BOOSTER
    assert boost(card, st) is True

    assert card.has_go_again, "CR 8.3.9: a Mechanologist boost grants go again"


def test_boosting_a_non_mechanologist_card_grants_nothing():
    st = _state_with_top(GENERIC)
    card = _card(BOOSTER)

    assert boost(card, st) is False
    assert not card.has_go_again, (
        "CR 8.3.9 conditions go again on the banished card's class")


@pytest.mark.parametrize("top,expected_go_again", [(MECH, True), (GENERIC, False)])
def test_the_cost_is_paid_either_way(top, expected_go_again):
    """CR 8.3.9a — the card is banished and the player has boosted whichever
    class came off the deck. Only the grant is conditional."""
    st = _state_with_top(top)
    card = _card(BOOSTER)

    boost(card, st)

    p = st.players[1]
    assert [c.slug for c in p.banished.cards] == [top], "the boost cost was not paid"
    assert not p.deck.cards, "the top card was not removed from the deck"
    assert "boosted_this_turn" in p.current_turn_effects
    assert card.has_go_again is expected_go_again


def test_declining_the_boost_banishes_nothing():
    """Boost is OPTIONAL (CR 8.3.9). A player who says no keeps their card."""
    st = _state_with_top(MECH)
    st.player_agents[1] = lambda s, o, context="": (False if False in o else o[0])
    card = _card(BOOSTER)

    assert boost(card, st) is False

    p = st.players[1]
    assert not p.banished.cards and len(p.deck.cards) == 1
    assert not card.has_go_again
