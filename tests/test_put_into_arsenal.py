"""Four cards used the only arsenal effect that existed, in the wrong direction.

PUT_ARSENAL_BOTTOM moves a card OUT of the arsenal onto the bottom of a deck,
and defaults to the OPPONENT's arsenal. Four cards whose text says "put it face
up INTO YOUR arsenal" reached for it anyway, because nothing else mentioned the
arsenal:

  heat_seeker_red          tracked in KNOWN_UNIMPLEMENTED for exactly this gap
  blessing_of_focus_red    "reveal the top card ... if it's an arrow, put it
  blessing_of_focus_blue    face up into your arsenal with an aim counter"
  conduit_of_frostburn     a granted ability that says DESTROY a card in their
                           arsenal, which bottoms it instead — the card
                           survives, in their deck, to be drawn again

The Blessing printings carried TWO defects, and the outer one hid the inner
one: they nested their payoff inside REVEAL_TOP_DECK's "effects", and
REVEAL_TOP_DECK does not read a nested effects list — it stores the revealed
cards under "into" and returns. So the wrong-direction node was never reached,
and the cards did nothing at all rather than milling anyone. Fixing only the
nesting would have turned a dead card into a card that bottoms the opponent's
arsenal, which is why both are fixed together here.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.effect_types import compile_effect
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

ARROW = "amplifying_arrow_yellow"
NOT_ARROW = "brutal_assault_red"


def _card(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    st.individual_turns = 1
    return st


def _stock(st, top_slug, pid=1, filler=3):
    """deck.add() stamps card.zone; assigning deck.cards leaves cards claiming
    to be in 'inventory' and the movement effects refuse to touch them."""
    top = _card(top_slug, pid)
    st.players[pid].deck.add(top)
    for _ in range(filler):
        st.players[pid].deck.add(_card(NOT_ARROW, pid))
    return top


# --- the primitive ----------------------------------------------------------

def test_the_top_card_of_the_deck_reaches_the_arsenal_face_up():
    st = _state()
    top = _stock(st, ARROW)

    compile_effect("PUT_INTO_ARSENAL",
                   {"from": "DECK_TOP", "player": "SELF", "face_up": True})(
        _card("heat_seeker_red"), None, st)

    assert top in st.players[1].arsenal.cards, "it never reached the arsenal"
    assert top not in st.players[1].deck.cards, "it is still in the deck as well"
    assert top.is_public is True, "it arrived face down"


def test_it_does_not_reach_into_the_opponents_deck():
    """PUT_ARSENAL_BOTTOM defaults to OPPONENT; this one must not inherit that."""
    st = _state()
    mine = _stock(st, ARROW, pid=1)
    theirs = _stock(st, ARROW, pid=2)

    compile_effect("PUT_INTO_ARSENAL",
                   {"from": "DECK_TOP", "player": "SELF", "face_up": True})(
        _card("heat_seeker_red"), None, st)

    assert mine in st.players[1].arsenal.cards
    assert theirs in st.players[2].deck.cards, "it moved the opponent's card"


def test_a_full_arsenal_is_a_no_op_not_a_replacement():
    """The arsenal holds one card and Zone.add drops the overflow."""
    st = _state()
    sitting = _card(ARROW)
    st.players[1].arsenal.add(sitting)
    top = _stock(st, ARROW)

    compile_effect("PUT_INTO_ARSENAL",
                   {"from": "DECK_TOP", "player": "SELF"})(
        _card("heat_seeker_red"), None, st)

    assert sitting in st.players[1].arsenal.cards, "it evicted the arsenal card"
    assert top not in st.players[1].arsenal.cards


# --- blessing_of_focus ------------------------------------------------------

@pytest.mark.parametrize("slug", ["blessing_of_focus_red", "blessing_of_focus_blue"])
def test_an_arrow_on_top_is_arsenaled_with_an_aim_counter(slug):
    st = _state()
    top = _stock(st, ARROW)
    source = _card(slug)
    st.players[1].permanents.add(source)

    run_ability(get_card(slug).abilities[0], source, None, st)

    assert top in st.players[1].arsenal.cards, (
        "the revealed arrow never reached the arsenal")
    assert top.is_public is True, "it arrived face down"
    assert (top.counters or {}).get("aim", 0) == 1, "it got no aim counter"


@pytest.mark.parametrize("slug", ["blessing_of_focus_red", "blessing_of_focus_blue"])
def test_a_non_arrow_on_top_is_left_in_the_deck(slug):
    st = _state()
    top = _stock(st, NOT_ARROW)
    source = _card(slug)
    st.players[1].permanents.add(source)

    run_ability(get_card(slug).abilities[0], source, None, st)

    assert st.players[1].arsenal.cards == [], (
        "a card that is not an arrow was put into the arsenal")


@pytest.mark.parametrize("slug", ["blessing_of_focus_red", "blessing_of_focus_blue"])
def test_it_does_not_mill_the_opponents_arsenal(slug):
    """A regression guard, not a reproduction: the wrong-direction node was
    unreachable behind the nesting bug, so this never actually happened. It is
    what fixing ONLY the nesting would have produced — PUT_ARSENAL_BOTTOM with
    card_type "arrow" against the opponent's arsenal by default."""
    st = _state()
    _stock(st, ARROW)
    # An ARROW, because the old node carried card_type "arrow" — a non-arrow in
    # their arsenal would be spared by that filter and the test would pass
    # against the very behaviour it is meant to rule out.
    theirs = _card(ARROW, 2)
    st.players[2].arsenal.add(theirs)
    # Face UP as well as an arrow: the old node carried card_type "arrow" AND
    # face_up, so a card failing either filter would be spared and the test
    # would pass against the very behaviour it is meant to rule out.
    theirs.is_public = True
    source = _card(slug)
    st.players[1].permanents.add(source)

    run_ability(get_card(slug).abilities[0], source, None, st)

    assert theirs in st.players[2].arsenal.cards, (
        "it bottomed the opponent's arsenal card")


# --- conduit_of_frostburn ---------------------------------------------------

def test_frostburn_destroys_rather_than_bottoms():
    """"DESTROY a frozen card in their arsenal". Bottoming keeps the card, in
    their deck, to be drawn again — and the file's own comment claimed it
    destroyed one, so the gap was invisible to a reader."""
    grant = (get_card("conduit_of_frostburn").abilities[0]
             .effects[0].params["grant_ability"])
    types = [e.get("type") for e in grant["effects"]]

    assert "PUT_ARSENAL_BOTTOM" not in types, types
    assert "DESTROY_ARSENAL" in types, types

    st = _state()
    theirs = _card(NOT_ARROW, 2)
    st.players[2].arsenal.add(theirs)

    compile_effect("DESTROY_ARSENAL", {"player": "OPPONENT"})(
        _card("conduit_of_frostburn"), None, st)

    assert theirs not in st.players[2].arsenal.cards
    assert theirs not in st.players[2].deck.cards, (
        "the card was bottomed rather than destroyed")
