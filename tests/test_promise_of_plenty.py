"""An effect whose NAME ends in THEN_DISCARD made a card discard that doesn't.

Promise of Plenty (red and blue): "If Promise of Plenty hits, each hero who
doesn't have a card in their arsenal puts the top card of their deck face down
into their arsenal."

Not one word about discarding. Both variants were authored on
EACH_HERO_ARSENAL_FROM_ZONE_THEN_DISCARD, which ends with "each hero that does,
discards a card" at RANDOM. So playing this card made BOTH players discard --
a symmetric invented downside that hurt the caster too, and the worst kind of
wrong effect because it fires and looks deliberate.

Codex of Frailty and Inertia genuinely do discard, so the discard stays the
default and the cards that do not say it turn it off.

`face_down` and `condition` were unread as well. They named what the handler
already did, so the tempting fix was an INERT exemption in the audit -- but an
exemption is a claim about behaviour that goes stale (that is exactly how
RETURN_TO_HAND's `zone` came to bounce the wrong card). They are read instead.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.effect_types import compile_effect
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

PLAIN = "brutal_assault_red"
OTHER = "amplifying_arrow_yellow"


def _card(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _state():
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="": o[0]
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    st.individual_turns = 1
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=_card(PLAIN, 1), keywords=[])
    st.combat.hit = True
    return st


def _stock(st):
    """Both players: a card on top of deck and two in hand."""
    tops = {}
    for pid in (1, 2):
        top = _card(OTHER, pid)
        st.players[pid].deck.add(top)
        for _ in range(2):
            st.players[pid].hand.add(_card(PLAIN, pid))
        tops[pid] = top
    return tops


@pytest.mark.parametrize("slug", ["promise_of_plenty_red",
                                  "promise_of_plenty_blue"])
def test_nobody_discards(slug):
    """The whole defect: an effect named THEN_DISCARD on a card that doesn't."""
    st = _state()
    _stock(st)
    hands = {pid: len(st.players[pid].hand.cards) for pid in (1, 2)}

    run_ability(get_card(slug).abilities[0], _card(slug, 1), None, st)

    for pid in (1, 2):
        assert len(st.players[pid].hand.cards) == hands[pid], (
            f"player {pid} discarded {hands[pid] - len(st.players[pid].hand.cards)} "
            f"card(s) for a card that never mentions discarding")


@pytest.mark.parametrize("slug", ["promise_of_plenty_red",
                                  "promise_of_plenty_blue"])
def test_each_hero_arsenals_the_top_of_their_deck(slug):
    st = _state()
    tops = _stock(st)

    run_ability(get_card(slug).abilities[0], _card(slug, 1), None, st)

    for pid in (1, 2):
        assert tops[pid] in st.players[pid].arsenal.cards, (
            f"player {pid}'s top card is in {tops[pid].zone!r}")


@pytest.mark.parametrize("slug", ["promise_of_plenty_red",
                                  "promise_of_plenty_blue"])
def test_it_goes_in_face_down(slug):
    st = _state()
    tops = _stock(st)

    run_ability(get_card(slug).abilities[0], _card(slug, 1), None, st)

    for pid in (1, 2):
        assert tops[pid].face_down is True
        assert tops[pid].is_public is False


@pytest.mark.parametrize("slug", ["promise_of_plenty_red",
                                  "promise_of_plenty_blue"])
def test_a_hero_who_already_has_an_arsenal_card_is_skipped(slug):
    """"each hero WHO DOESN'T HAVE A CARD IN THEIR ARSENAL"."""
    st = _state()
    tops = _stock(st)
    sitting = _card(PLAIN, 2)
    st.players[2].arsenal.add(sitting)

    run_ability(get_card(slug).abilities[0], _card(slug, 1), None, st)

    assert tops[1] in st.players[1].arsenal.cards, "the empty arsenal was skipped"
    assert tops[2] in st.players[2].deck.cards, (
        "a hero who already had an arsenal card still drew into it")
    assert sitting in st.players[2].arsenal.cards


# --- the discard flag itself ------------------------------------------------

def test_the_discard_still_happens_by_default():
    """Codex of Frailty / Inertia genuinely say "each hero that does, discards
    a card" — turning it off for everyone would break them."""
    st = _state()
    _stock(st)
    before = len(st.players[1].hand.cards)

    compile_effect("EACH_HERO_ARSENAL_FROM_ZONE_THEN_DISCARD",
                   {"zone": "deck", "amount": 1})(_card(PLAIN, 1), None, st)

    assert len(st.players[1].hand.cards) == before - 1


def test_discard_false_turns_it_off():
    st = _state()
    _stock(st)
    before = len(st.players[1].hand.cards)

    compile_effect("EACH_HERO_ARSENAL_FROM_ZONE_THEN_DISCARD",
                   {"zone": "deck", "amount": 1, "discard": False})(
        _card(PLAIN, 1), None, st)

    assert len(st.players[1].hand.cards) == before
