"""Frailty's -1{p} static, which carried a "not yet expressible" TODO.

"Your attack action cards played from arsenal and weapon attacks have -1{p}."
The token only destroyed itself at end of turn; the static did nothing, so a
Frailty in play was cosmetic.

Found by replaying real attacks against Talishar
(scripts/talishar_attack_replay.py). 13 of the 25 remaining power
disagreements were this one token — millers_grindstone and
sledge_of_anvilheim as weapon attacks, leave_no_witnesses_red played from
arsenal — each computing exactly 1 higher than Talishar.

THE TRAP IS WHOSE ATTACK IT HITS. engine._dsl_recalc_listener dispatches
RECALC_ATTACK_POWER to permanents belonging to BOTH players, so a Frailty in
the DEFENDER's arena will happily shrink the attacker's attack unless the
ability is scoped with ATTACK_CONTROLLED_BY_YOU. That direction is tested
explicitly, because a one-sided test passes on the broken version.

The other half is the two categories. A weapon attack and an arsenal-played
attack action are both hit; an attack action played from HAND is not.
"""
from __future__ import annotations

import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.loader import load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

WEAPON = "millers_grindstone"          # Once per Turn Action - attack, power 4
ACTION = "leave_no_witnesses_red"      # attack action card, power 4


def _card(slug, owner=1):
    card = copy.deepcopy(DB.get(slug))
    assert card is not None, slug
    card.owner = card.controller = owner
    return card


def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    return st


def _power(st, card, from_weapon=False, played_from=None):
    power = card.base_power or 0
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=power,
                            attack_card=card, keywords=[])
    st.combat.base_attack_power = power
    st.combat.from_weapon = from_weapon
    if played_from is not None:
        card.played_from_zone = played_from
    E._apply_turn_attack_effects(st, card)
    E._register_card_continuous_effects(st, card)
    E._recalculate_attack_power(st)
    return st.combat.attack_power


def _give_frailty(st, player_id):
    token = _card("frailty", player_id)
    st.players[player_id].auras.add(token)
    return token


def test_a_weapon_attack_is_reduced():
    st = _state()
    _give_frailty(st, 1)
    card = _card(WEAPON)
    assert _power(st, card, from_weapon=True) == (card.base_power or 0) - 1


def test_an_attack_action_played_from_arsenal_is_reduced():
    st = _state()
    _give_frailty(st, 1)
    card = _card(ACTION)
    assert _power(st, card, played_from="arsenal") == (card.base_power or 0) - 1


def test_an_attack_action_played_from_hand_is_not_reduced():
    """The card names two categories, not 'all your attacks'."""
    st = _state()
    _give_frailty(st, 1)
    card = _card(ACTION)
    assert _power(st, card, played_from="hand") == (card.base_power or 0)


def test_the_defenders_frailty_does_not_shrink_your_attack():
    """RECALC_ATTACK_POWER reaches BOTH players' permanents, so without
    ATTACK_CONTROLLED_BY_YOU this is exactly how the static misfires."""
    st = _state()
    _give_frailty(st, 2)
    card = _card(WEAPON)
    assert _power(st, card, from_weapon=True) == (card.base_power or 0)


def test_no_frailty_means_no_change():
    st = _state()
    card = _card(WEAPON)
    assert _power(st, card, from_weapon=True) == (card.base_power or 0)


@pytest.mark.parametrize("count", [2, 3])
def test_each_frailty_applies(count):
    """Frailty is a token and a player can control several; nothing in the card
    makes it unique, so two of them are -2."""
    st = _state()
    for _ in range(count):
        _give_frailty(st, 1)
    card = _card(WEAPON)
    assert _power(st, card, from_weapon=True) == (card.base_power or 0) - count
