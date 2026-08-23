""""Illusionist auras you control ARE WEAPONS" - a type change, not a buff.

Luminaris reads "During your action phase, Illusionist auras you control are
weapons with 1 base {p} and 'Once per Turn Action - 0: Attack'". Three things
had to be true at once for that to be real:

  - the aura needs a base {p} it has no printed field for;
  - the attack has to be OFFERED by legal-action generation, or the grant is
    invisible to any player;
  - both have to STOP when the condition stops.

It had been MODIFY_ATTACK_POWER_PER_UNIQUE_AURA mod:"set" - an effect that
COUNTS distinct aura names in the arena, which is a different measurement
entirely - on a plain STATIC, which nothing dispatches, gated on
CONTROLS_TOKEN_TYPE "Illusionist", which is not a token type.

GRANT_ATTACK_WHILE is re-derived on every legality pass rather than applied
once, for the same reason the conditional freeze is: "during your action phase"
is true and false repeatedly within a turn, and a one-shot grant would leave the
auras permanently armed.
"""
import copy

import pytest

import engine.engine as E
from engine.actions import ActionType
from engine.card import Card, CardDB
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.play import (GRANTED_ATTACK, _apply_granted_attack_statics,
                         available_actions)
from engine.state import Step
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

SOURCE = "luminaris"


def _card(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _state(step=Step.ACTION, active=1):
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    st.active_player = active
    st.individual_turns = 1
    st.step = step
    st.players[1].action_points = 1
    return st


def _aura(st, pid=1, illusionist=True, name="Spectral Shield"):
    """An Illusionist aura permanent. Built by hand so the test states exactly
    which properties the grant is supposed to key on."""
    a = Card(slug="test_aura", raw_name=name, raw_types=["Token"],
             raw_subtypes=["Aura"])
    a.name = name
    a.types = ["Token"]
    a.subtypes = ["Aura"]
    a.classes = ["Illusionist"] if illusionist else ["Guardian"]
    a.is_token = True
    a.owner = a.controller = pid
    st.players[pid].permanents.cards.append(a)
    a.zone = "permanents"
    return a


def _luminaris(st, pid=1):
    w = _card(SOURCE, pid)
    st.players[pid].weapon1.add(w)
    return w


def _attack_actions(st, pid=1):
    return [a for a in available_actions(st, pid)
            if a.type == ActionType.ACTIVATE_CARD
            and getattr(a, "is_attack_proxy", False)]


# --- the grant --------------------------------------------------------------

def test_an_illusionist_aura_becomes_a_one_power_weapon():
    st = _state()
    _luminaris(st)
    aura = _aura(st)
    assert aura.power is None, "the aura starts with no printed {p}"

    _apply_granted_attack_statics(st)

    assert GRANTED_ATTACK in aura.counters
    assert aura.base_power == 1 and aura.power == 1
    assert aura.activation_cost == 0


def test_a_non_illusionist_aura_is_untouched():
    st = _state()
    _luminaris(st)
    other = _aura(st, illusionist=False)

    _apply_granted_attack_statics(st)

    assert GRANTED_ATTACK not in other.counters
    assert other.power is None


def test_the_opponents_auras_are_untouched():
    """"auras YOU control"."""
    st = _state()
    _luminaris(st, 1)
    theirs = _aura(st, pid=2)

    _apply_granted_attack_statics(st)

    assert GRANTED_ATTACK not in theirs.counters


def test_the_grant_lapses_outside_your_action_phase():
    st = _state()
    _luminaris(st)
    aura = _aura(st)
    _apply_granted_attack_statics(st)
    assert GRANTED_ATTACK in aura.counters

    st.step = Step.END_PHASE_BEGINNING if hasattr(Step, "END_PHASE_BEGINNING") \
        else Step.START_PHASE
    _apply_granted_attack_statics(st)

    assert GRANTED_ATTACK not in aura.counters, (
        "the grant outlived the action phase")
    assert aura.power is None, "the granted {p} was left behind"


def test_the_grant_lapses_on_the_opponents_turn():
    st = _state()
    _luminaris(st)
    aura = _aura(st)
    _apply_granted_attack_statics(st)
    assert GRANTED_ATTACK in aura.counters

    st.active_player = 2
    _apply_granted_attack_statics(st)

    assert GRANTED_ATTACK not in aura.counters, (
        "\"during YOUR action phase\" held on the opponent's turn")


def test_the_grant_lapses_when_luminaris_leaves():
    st = _state()
    weapon = _luminaris(st)
    aura = _aura(st)
    _apply_granted_attack_statics(st)
    assert GRANTED_ATTACK in aura.counters

    st.players[1].weapon1.cards = []
    _apply_granted_attack_statics(st)

    assert GRANTED_ATTACK not in aura.counters


# --- action generation ------------------------------------------------------

def test_the_aura_attack_is_offered_as_a_legal_action():
    """A grant no action generator offers is invisible to any player."""
    st = _state()
    _luminaris(st)
    aura = _aura(st)

    offered = _attack_actions(st)

    assert any(a.card is aura for a in offered), (
        f"the aura attack was not offered ({[a.card.slug for a in offered]})")


def test_no_aura_attack_is_offered_without_luminaris():
    st = _state()
    aura = _aura(st)

    offered = _attack_actions(st)

    assert not any(a.card is aura for a in offered)


def test_the_per_turn_allowance_survives_re_derivation():
    """The pass runs on every legality check; if it reset `activations` the
    once-per-turn attack would be infinitely repeatable."""
    st = _state()
    _luminaris(st)
    aura = _aura(st)
    _apply_granted_attack_statics(st)
    assert aura.activations == 1

    aura.activations = 0          # as if the attack had been used
    for _ in range(4):
        _apply_granted_attack_statics(st)

    assert aura.activations == 0, (
        "re-deriving the grant handed back an attack that was already used")
    assert not any(a.card is aura for a in _attack_actions(st))


def test_lapsing_restores_an_auras_own_activated_ability():
    """An Illusionist aura with an activated ability of its own matches this
    filter too. Restoring blanket defaults on lapse (activation_cost None,
    has_per_turn_limit False) would silently break that ability the moment the
    grant ended, which is a bug the grant itself introduces."""
    st = _state()
    _luminaris(st)
    aura = _aura(st)
    aura.activation_cost = 2          # its own printed activated ability
    aura.has_per_turn_limit = True
    aura.activations = 1

    _apply_granted_attack_statics(st)
    assert aura.activation_cost == 0, "the grant did not take effect"

    st.active_player = 2
    _apply_granted_attack_statics(st)

    assert aura.activation_cost == 2, (
        f"its own activation cost was left as {aura.activation_cost}")
    assert aura.has_per_turn_limit is True
    assert aura.activations == 1
