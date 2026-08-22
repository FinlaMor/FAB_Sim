""""Put an aim counter on IT" needs to be the card that was just flipped.

barbed_castaway's two abilities each searched the wrong zone with the wrong
test and then acted on the wrong card.

  1. "put an arrow card FROM YOUR HAND face up into your arsenal" was
     SEARCH_DECK — the deck rather than the hand, and a tutor rather than a
     move — and its 'target' was not read at all.

  2. "turn a FACE DOWN arrow in your arsenal face up" identified face-down with
     REF_PITCH_IS pitch:"face_up". REF_PITCH_IS is about pitch COLOUR, which is
     never the string "face_up", so the filter matched nothing. FLIP_REF then
     read no target either and fell back to a ref nothing had set.

  3. "If you do, put an aim counter on IT" RE-SEARCHED the arsenal for "a
     face-up arrow" rather than taking the one just flipped, so with two arrows
     in arsenal it could count one that was already face up.

The fix is two additions to the shared object-target spec: "record_as", which
names what a target chose so the next effect can say "it", and "ref", which
takes that name instead of repeating the search.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

ARROW_A = "amplifying_arrow_yellow"
ARROW_B = "barbed_barrage_red"
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
    st.players[1].resources = 5
    return st


def _run(st, index, source=None):
    source = source or _card("barbed_castaway")
    run_ability(get_card("barbed_castaway").abilities[index], source, None, st)
    return source


def _aim(card):
    return (getattr(card, "counters", None) or {}).get("aim", 0)


# --- ability 1: hand -> arsenal, face up -------------------------------------

def test_an_arrow_moves_from_hand_to_arsenal():
    st = _state()
    arrow = _card(ARROW_A)
    st.players[1].hand.add(arrow)

    _run(st, 0)

    assert arrow in st.players[1].arsenal.cards, "the arrow did not reach arsenal"
    assert arrow not in st.players[1].hand.cards, "it is still in hand as well"


def test_it_arrives_face_up():
    st = _state()
    arrow = _card(ARROW_A)
    arrow.is_public = False
    st.players[1].hand.add(arrow)

    _run(st, 0)

    assert arrow.is_public is True, "the arrow was put into arsenal face down"


def test_it_will_not_take_a_card_that_is_not_an_arrow():
    st = _state()
    other = _card(NOT_ARROW)
    st.players[1].hand.add(other)

    _run(st, 0)

    assert other in st.players[1].hand.cards, "a non-arrow was arsenaled"
    assert st.players[1].arsenal.cards == []


def test_it_does_not_reach_into_the_deck():
    """It was SEARCH_DECK, which tutors — a strictly stronger, different card."""
    st = _state()
    in_deck = _card(ARROW_A)
    st.players[1].deck.cards = [in_deck]

    _run(st, 0)

    assert in_deck in st.players[1].deck.cards, "it tutored an arrow out of the deck"


# --- ability 2: flip a face-down arrow, counter THAT arrow -------------------

def test_a_face_down_arrow_is_turned_face_up():
    st = _state()
    arrow = _card(ARROW_A)
    st.players[1].arsenal.add(arrow)   # add() puts it in face down
    assert arrow.is_public is False

    _run(st, 1)

    assert arrow.is_public is True, "the face-down arrow was not flipped"


def test_the_aim_counter_goes_on_the_arrow_that_was_flipped():
    """"If you do, put an aim counter on IT."

    The old node re-searched the arsenal for "a face-up arrow" instead of
    taking the card just flipped. Today the arsenal holds ONE card, so the
    re-search cannot land on a different arrow than the flip did — the two
    disagree only in a state the engine will not produce. What is reachable,
    and what this asserts, is that the counter tracks the flip: exactly one
    aim counter, on the arrow that changed, and none on the source card.
    """
    st = _state()
    arrow = _card(ARROW_A)
    st.players[1].arsenal.add(arrow)
    assert arrow.is_public is False

    source = _run(st, 1)

    assert arrow.is_public is True, "the arrow was not flipped"
    assert _aim(arrow) == 1, f"expected one aim counter, got {_aim(arrow)}"
    assert _aim(source) == 0, "the counter landed on Barbed Castaway itself"


def test_nothing_happens_with_no_face_down_arrow():
    """"IF YOU DO" — no flip, no counter."""
    st = _state()
    up = _card(ARROW_A)
    st.players[1].arsenal.add(up)
    up.is_public = True     # after add(), which stamps arsenal cards face down

    _run(st, 1)

    assert _aim(up) == 0, "it put an aim counter on an already face-up arrow"


def test_a_face_down_non_arrow_is_left_alone():
    st = _state()
    other = _card(NOT_ARROW)
    st.players[1].arsenal.add(other)   # add() puts it in face down

    _run(st, 1)

    assert other.is_public is False, "it flipped a card that is not an arrow"
    assert _aim(other) == 0
