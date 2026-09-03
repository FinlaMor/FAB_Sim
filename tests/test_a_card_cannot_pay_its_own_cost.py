"""A card cannot pay its own from-hand cost.

Found by differential testing against Talishar, which is an independent
implementation of the same rules. Comparing "what may be played from hand" over
171 reconstructed Talishar states, Enlightened Strike was the only card we
allowed that Talishar forbade — and it was right.

    "As an additional cost to play Enlightened Strike, put a card from your
     hand on the bottom of your deck."

`can_pay` asked `len(hand) >= 1`. A card being played is still in hand while its
costs are checked — it does not leave for the stack until later — so with only
Enlightened Strike in hand the check counted the card paying the cost. When it
resolves there is nothing left to put anywhere.

This is the same rule the project already enforces from the other side: costs
must block play legality. A cost that can always be paid does not block
anything, and this one could always be paid by exactly one card: itself.

DISCARD_SELF is the deliberate exception. "Discard this:" is paid WITH the
source, so it must keep seeing itself in hand.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card import CardDB
from engine.card_effects.dsl.cost_types import _other_hand_cards, compile_cost
from engine.card_effects.dsl.loader import load_all_cards
from engine.play import available_actions
from engine.state import Step
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()


def _state(hand_slugs):
    st = _make_state()
    st.card_db = DB
    st.active_player = 1
    st.step = Step.ACTION
    st.players[1].resources = 9
    st.players[1].action_points = 1
    cards = []
    for slug in hand_slugs:
        c = copy.deepcopy(DB.get(slug))
        assert c is not None, slug
        c.owner = c.controller = 1
        st.players[1].hand.add(c)
        cards.append(c)
    return st, cards


def _playable(st):
    return {getattr(a.card, "slug", None) for a in available_actions(st, 1)}


def test_enlightened_strike_needs_another_card_in_hand():
    st, _ = _state(["enlightened_strike_red"])
    assert "enlightened_strike_red" not in _playable(st), (
        "its additional cost is 'put A CARD FROM YOUR HAND on the bottom', and "
        "the only card in hand is the one being played")


def test_enlightened_strike_is_playable_with_a_second_card():
    """The other half: over-correcting would make the card unplayable."""
    st, _ = _state(["enlightened_strike_red", "head_jab_red"])
    assert "enlightened_strike_red" in _playable(st)


# --- the helper itself -------------------------------------------------------

def test_the_paying_card_is_excluded_by_identity_not_by_slug():
    """Two copies of one card is the case a slug comparison gets wrong: the
    second copy is a real, different object that CAN pay."""
    st, cards = _state(["enlightened_strike_red", "enlightened_strike_red"])
    first = cards[0]
    others = _other_hand_cards(first, st)
    assert len(others) == 1
    assert others[0] is cards[1]
    assert "enlightened_strike_red" in _playable(st), (
        "a second copy in hand can pay for the first")


def test_discard_self_still_sees_itself():
    """"Discard this:" is paid WITH the source. Excluding the card there would
    make every from-hand instant unplayable — the same bug pointing the other
    way."""
    check, _pay = compile_cost("DISCARD_SELF", {})
    st, cards = _state(["head_jab_red"])
    assert check(cards[0], None, st), (
        "DISCARD_SELF must keep seeing the card in hand")


def test_a_card_outside_hand_is_unaffected():
    """The helper is used by costs on permanents too, where the source is not in
    hand at all and the exclusion must simply be a no-op."""
    st, cards = _state(["head_jab_red"])
    weapon = copy.deepcopy(DB.get("teklo_plasma_pistol"))
    weapon.owner = weapon.controller = 1
    assert len(_other_hand_cards(weapon, st)) == 1
