"""Sirens of Safe Harbor — "put into your graveyard FROM ANYWHERE".

    "When this is put into your graveyard from anywhere, gain 1{h}."

It was on test_invented_refs.py's KNOWN_UNFIXED, authored as ON_ENTER_PLAY gated
on a REF_EXISTS "GRAVEYARD" that nothing sets. It could never fire on either
count: the ref was empty, and a graveyard is not the arena.

ON_PUT_INTO_GRAVEYARD is dispatched from Zone.add, which is the one place every
graveyard route funnels through -- and "from anywhere" is exactly what makes
that the right hook. Hooking the discard path, the destroy path and the
combat-chain cleanup separately would have been three chances to miss one; the
graveyard turn-marker sitting beside it in Zone.add already makes that argument.

The routes below are the point of the test. A per-path implementation passes one
of them and fails the others.
"""
import copy

import pytest

from engine.card import CardDB
from engine.card_effects.dsl.loader import load_all_cards
from scripts.talishar_attack_replay import _replay_agent
from tests.conftest import _make_state
import engine.engine as E

load_all_cards()
DB = CardDB()

CARD = "sirens_of_safe_harbor_red"
OTHER = "head_jab_red"


def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: _replay_agent, 2: _replay_agent}
    E._setup_dsl_listeners(st)
    return st


def _card(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    c.owner = c.controller = pid
    return c


@pytest.mark.parametrize("origin", ["hand", "deck", "arsenal", "banished", None])
def test_it_gains_life_from_every_origin(origin):
    """"From anywhere" -- each of these is a different call path into the
    graveyard in real play."""
    st = _state()
    before = st.players[1].life
    card = _card(CARD)
    if origin is not None:
        zone = getattr(st.players[1], origin)
        zone.add(card)
        zone.remove(card)
    st.players[1].graveyard.add(card)
    assert st.players[1].life == before + 1


def test_another_card_entering_the_graveyard_grants_nothing():
    """The trigger belongs to the card that entered, not to whoever owns the
    graveyard -- otherwise every discard would pay out."""
    st = _state()
    before = st.players[1].life
    st.players[1].graveyard.add(_card(OTHER))
    assert st.players[1].life == before


def test_re_adding_a_card_already_there_does_not_pay_twice():
    """Zone.add guards on an actual entry. Without that a card touched twice in
    the graveyard would gain life each time."""
    st = _state()
    card = _card(CARD)
    st.players[1].graveyard.add(card)
    after_first = st.players[1].life
    st.players[1].graveyard.add(card)
    assert st.players[1].life == after_first
