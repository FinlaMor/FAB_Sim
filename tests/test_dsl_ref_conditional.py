"""Behavioral tests for the ref-family + CONDITIONAL DSL primitives:
PUT_REF_BOTTOM / PUT_REF_TOP, TAP_REF, CONDITIONAL/IF, and the conditions
ATTACK_BASE_POWER_LTE/GTE and IN_GRAVEYARD.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.card import Card, CardDB
from engine.state import CombatState
from engine.card_effects.dsl.effect_types import compile_effect
from engine.card_effects.dsl.condition_types import compile_condition
from engine.card_effects.dsl.loader import load_all_cards
from engine.context import effect_context, set_ref, push_refs, pop_refs
from tests.conftest import _make_state

load_all_cards()


def _state():
    st = _make_state()
    st.card_db = CardDB()
    return st


def _dummy(pid, slug="dummy_card"):
    c = Card(slug=slug, name=slug, types=["Action"])
    c.owner = c.controller = pid
    return c


def test_conditional_runs_then_when_condition_holds():
    st = _state()
    src = _dummy(1)
    st.players[1].current_turn_effects.append("gate")
    eff = compile_effect("CONDITIONAL", {
        "when": [{"type": "FLAG_SET", "flag": "gate"}],
        "then": [{"type": "SET_FLAG", "flag": "then_ran"}],
        "else": [{"type": "SET_FLAG", "flag": "else_ran"}],
    })
    with effect_context():
        eff(src, None, st)
    assert "then_ran" in st.players[1].current_turn_effects
    assert "else_ran" not in st.players[1].current_turn_effects


def test_conditional_runs_else_when_condition_fails():
    st = _state()
    src = _dummy(1)  # no "gate" flag -> condition fails
    eff = compile_effect("CONDITIONAL", {
        "when": [{"type": "FLAG_SET", "flag": "gate"}],
        "then": [{"type": "SET_FLAG", "flag": "then_ran"}],
        "else": [{"type": "SET_FLAG", "flag": "else_ran"}],
    })
    with effect_context():
        eff(src, None, st)
    assert "else_ran" in st.players[1].current_turn_effects
    assert "then_ran" not in st.players[1].current_turn_effects


def test_put_ref_bottom_moves_referenced_card_to_deck_bottom():
    st = _state()
    src = _dummy(1)
    marker = _dummy(1, slug="marker_card")
    # stock the deck so 'bottom' is observable
    for _ in range(5):
        st.players[1].deck.cards.append(_dummy(1))
    eff = compile_effect("PUT_REF_BOTTOM", {"ref": "looked"})
    with effect_context():
        push_refs()
        set_ref("looked", marker)
        eff(src, None, st)
        pop_refs()
    assert st.players[1].deck.cards[-1] is marker


def test_tap_ref_taps_referenced_card():
    st = _state()
    src = _dummy(1)
    target = _dummy(1, slug="weapon_card")
    target.tapped = False
    eff = compile_effect("TAP_REF", {"ref": "chosen"})
    with effect_context():
        push_refs()
        set_ref("chosen", target)
        eff(src, None, st)
        pop_refs()
    assert target.tapped is True


def test_attack_base_power_lte():
    st = _state()
    atk = _dummy(1, slug="swing")
    atk.base_power = 2
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=2,
                            attack_card=atk, keywords=[])
    st.combat.base_attack_power = 2
    assert compile_condition("ATTACK_BASE_POWER_LTE", {"amount": 3})(atk, None, st) is True
    assert compile_condition("ATTACK_BASE_POWER_LTE", {"amount": 1})(atk, None, st) is False
    assert compile_condition("ATTACK_BASE_POWER_GTE", {"amount": 2})(atk, None, st) is True


def test_in_graveyard_condition():
    st = _state()
    src = _dummy(1)
    fn = compile_condition("IN_GRAVEYARD", {"name": "kiss_of_death"})
    assert fn(src, None, st) is False
    st.players[1].graveyard.cards.append(_dummy(1, slug="kiss_of_death"))
    assert fn(src, None, st) is True
