"""The soul is not the graveyard, and two cards were paying from the wrong one.

Seven cards print "banish ... from your soul" as a cost. Two are implemented,
and neither paid it from the soul:

    teklovossen_the_mechropotent  "banish 2 cards from your soul" ->
                                  BANISH_FROM_GRAVEYARD
    war_cry_of_themis_yellow      "banish X cards from your soul" -> nothing at
                                  all; the cost was DISCARD_SELF alone

CR 3.11.5: a hero's soul is the collection of sub-objects under the hero card.
Substituting the graveyard is not a smaller version of the cost -- the soul is a
scarce resource a hero has to feed deliberately, and the graveyard fills up on
its own, so the ability became close to free.

X IS THE OTHER HALF. "Banish X cards from your soul: turn X target cards face
down" needs the number chosen at payment time and readable at resolution.
`{"type": "X"}` resolves to card.x_paid, and play.py stamps that only for a
card's PLAY cost -- never for an activated ability's -- so the cost has to
publish it itself. Zero is a legal choice for X, which is why the cost never
blocks the activation.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card import Card, CardDB
from engine.card_effects.dsl.cost_types import compile_cost
from engine.card_effects.dsl.loader import get_card, load_all_cards
from tests.conftest import _make_state, owned_card

load_all_cards()
DB = CardDB()


def _state(soul=0, graveyard=0):
    st = _make_state()
    st.card_db = DB
    for i in range(soul):
        c = Card(slug="soul_%d" % i, name="Soul %d" % i, raw_types=["Action"])
        c.types = ["Action"]
        c.owner = c.controller = 1
        st.players[1].soul.add(c)
    for i in range(graveyard):
        c = Card(slug="grave_%d" % i, name="Grave %d" % i, raw_types=["Action"])
        c.types = ["Action"]
        c.owner = c.controller = 1
        st.players[1].graveyard.add(c)
    return st


def _cost(**params):
    return compile_cost("BANISH_FROM_SOUL", params)


# --- the cost itself ---------------------------------------------------------

def test_it_takes_from_the_soul_and_leaves_the_graveyard_alone():
    st = _state(soul=3, graveyard=3)
    can, pay = _cost(amount=2)
    src = owned_card(1, "teklovossen_the_mechropotent")

    assert can(src, None, st)
    pay(src, None, st)

    assert len(st.players[1].soul.cards) == 1, "it did not take from the soul"
    assert len(st.players[1].graveyard.cards) == 3, (
        "it took from the graveyard, which is a different zone")
    assert len(st.players[1].banished.cards) == 2


def test_the_cards_leave_the_soul_rather_than_being_copied():
    """banish() needs origin_zone, or the card sits in both zones at once."""
    st = _state(soul=2)
    can, pay = _cost(amount=1)
    src = owned_card(1, "teklovossen_the_mechropotent")
    pay(src, None, st)

    banished = st.players[1].banished.cards[0]
    assert banished not in st.players[1].soul.cards


def test_an_empty_soul_cannot_pay_a_fixed_cost():
    """A cost that cannot be paid must block the activation, not resolve for
    free — that is the whole reason costs are costs."""
    st = _state(soul=1)
    can, _ = _cost(amount=2)
    assert not can(owned_card(1, "teklovossen_the_mechropotent"), None, st)


# --- X -----------------------------------------------------------------------

def _agent_choosing(st, value):
    st.player_agents[1] = lambda s, options, context="", **kw: (
        str(value) if str(value) in options else options[0])


def test_x_is_chosen_by_the_player_and_published():
    st = _state(soul=4)
    _agent_choosing(st, 3)
    can, pay = _cost(amount="X")
    src = owned_card(1, "war_cry_of_themis_yellow")

    assert can(src, None, st), "an X cost must never block: zero is legal"
    pay(src, None, st)

    assert len(st.players[1].banished.cards) == 3
    assert src.x_paid == 3, "X was not stamped for the payoff to read"
    assert st._paid_amount == 3


def test_x_of_zero_pays_nothing():
    st = _state(soul=4)
    _agent_choosing(st, 0)
    can, pay = _cost(amount="X")
    src = owned_card(1, "war_cry_of_themis_yellow")
    pay(src, None, st)

    assert not st.players[1].banished.cards
    assert src.x_paid == 0
    assert len(st.players[1].soul.cards) == 4


def test_x_cannot_exceed_the_soul():
    st = _state(soul=2)
    _agent_choosing(st, 5)          # more than there is
    can, pay = _cost(amount="X")
    src = owned_card(1, "war_cry_of_themis_yellow")
    pay(src, None, st)

    assert src.x_paid == 2
    assert not st.players[1].soul.cards


# --- the two cards -----------------------------------------------------------

def test_teklovossen_pays_from_the_soul():
    costs = [c.cost_type for c in
             get_card("teklovossen_the_mechropotent").abilities[0].costs]
    assert costs == ["BANISH_FROM_SOUL"], costs


def test_war_cry_pays_x_and_flips_x_face_down():
    ab = [a for a in get_card("war_cry_of_themis_yellow").abilities
          if a.ability_type.upper() == "INSTANT"][0]
    assert [c.cost_type for c in ab.costs] == ["DISCARD_SELF", "BANISH_FROM_SOUL"]

    flip = ab.effects[0]
    assert flip.effect_type == "FLIP_REF"
    assert flip.params.get("face_up") is False, (
        "the card says face-DOWN; FLIP_REF defaults to face-up, which reveals "
        "hidden information instead of hiding it")
    target = flip.params.get("target") or {}
    assert target.get("zone") == "BANISHED"
    assert target.get("controller") == "ANY", (
        "'a banished zone' is either player's")
    assert target.get("amount") == {"type": "X"}, (
        "the number of cards flipped is the X that was paid")


def test_war_cry_does_not_grant_a_second_go_again():
    """CR 8.3.5b. It is printed on the card and granted by the card DB."""
    assert DB.get("war_cry_of_themis_yellow").has_go_again
    play = [a for a in get_card("war_cry_of_themis_yellow").abilities
            if a.ability_type.upper() == "PLAY"][0]
    assert [e.effect_type for e in play.effects] == ["MODIFY_NEXT_ATTACK"]


def test_a_default_agent_pays_rather_than_opting_out():
    """This file's convention is that real options precede the opt-out, so a
    default agent acts. For an X cost, paying 0 IS the opt-out -- it makes the
    payoff do nothing -- so the counts are offered largest first. A default
    agent that always chose 0 would never exercise the card in self-play.
    """
    st = _state(soul=3)
    st.player_agents[1] = lambda s, options, context="", **kw: options[0]
    _, pay = _cost(amount="X")
    src = owned_card(1, "war_cry_of_themis_yellow")
    pay(src, None, st)
    assert src.x_paid == 3, "the default agent opted out of its own cost"


def test_the_x_amount_survives_compile_costs_flattening():
    """compile_cost coerces a non-numeric amount to 0 and keeps the original
    under `_amount_raw`. A branch reading "amount" sees 0, not "X" -- which
    here made an X cost a flat 1 card, silently. Pinned because the flattening
    happens before any branch runs and is invisible from the JSON.
    """
    st = _state(soul=4)
    _agent_choosing(st, 4)
    _, pay = _cost(amount="X")
    src = owned_card(1, "war_cry_of_themis_yellow")
    pay(src, None, st)
    assert src.x_paid == 4, (
        "X was flattened to a fixed amount; see compile_cost's preamble")
