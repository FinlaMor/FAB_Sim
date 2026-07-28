"""WTR equipment-activation group — DSL-authoritative behaviour.

  * barkbone_strapping  — Instant, destroy self: roll d6, gain floor(roll/2) {r}
  * scabskin_leathers   — Once per turn Action: roll d6, gain floor(roll/2) action points
  * fyendals_spring_tunic — start of turn: +1 energy (max 3); Instant, remove 3 energy: gain {r}

Exercises the DSL activation path (cost + effect) via play._apply_activate and the
START_OF_TURN energy accrual via the DSL dispatch, plus the migration wiring.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import engine.play as P
from engine.actions import Action, ActionType
from engine.card import Card
from engine.card_effects.dsl import dispatch, load_all_cards
from engine.card_effects.dsl.loader import get_card as _dsl_get_card
from engine.state import GameState, Player, Step

load_all_cards()


def _hero(pid: int) -> Card:
    c = Card(slug="test_hero", name="H", types=["Hero"], base_life=40, base_intellect=4)
    c.owner = pid
    c.controller = pid
    return c


def _state() -> GameState:
    return GameState(
        players={1: Player(1, _hero(1)), 2: Player(2, _hero(2))},
        active_player=1,
        player_agents={1: lambda *a, **k: None, 2: lambda *a, **k: None},
        step=Step.ACTION, turn_number=1, combat=None, done=False, winner=None,
    )


def _equip(state: GameState, slug: str, slot: str, pid: int = 1) -> Card:
    c = Card(slug=slug, name=slug, types=["Equipment"])
    c.owner = pid
    c.controller = pid
    c.zone = slot
    # Append directly so the card keeps its slot zone (avoids rule-source entry redirect
    # in this minimal harness); real play equips through the normal flow.
    getattr(state.players[pid], slot).cards.append(c)
    return c


def _activate(state: GameState, card: Card, slot: str, pid: int = 1):
    act = Action(type=ActionType.ACTIVATE_CARD, card=card, slot=slot)
    act.player_id = pid
    P._apply_activate(state, act)


def _energy(state: GameState, pid: int = 1) -> int:
    return sum(v for k, v in state.players[pid].counters.items() if k[2] == "energy")


# --- migration wiring --------------------------------------------------------

def test_equipment_cards_are_migrated():
    for s in ("barkbone_strapping", "scabskin_leathers", "fyendals_spring_tunic"):
        assert _dsl_get_card(s) is not None, s


def test_no_python_activation_fallback():
    from engine.card_effects.registry import (
        EQUIPMENT_ACTIVATION_EFFECTS, EQUIPMENT_ACTIVATION_CONDITIONS,
    )
    for s in ("scabskin_leathers", "fyendals_spring_tunic"):
        assert s not in EQUIPMENT_ACTIVATION_EFFECTS
    assert "fyendals_spring_tunic" not in EQUIPMENT_ACTIVATION_CONDITIONS
    from engine.card_effects.triggers import CARD_TRIGGERS
    assert "fyendals_spring_tunic" not in CARD_TRIGGERS


# --- barkbone_strapping ------------------------------------------------------

def test_barkbone_activate_destroys_self_and_gains_resource():
    state = _state()
    bk = _equip(state, "barkbone_strapping", "chest")
    r0 = state.players[1].resources
    _activate(state, bk, "chest")
    delta = state.players[1].resources - r0
    assert 0 <= delta <= 3            # floor(d6 / 2)
    assert bk not in state.players[1].chest.cards   # destroyed (cost)


# --- scabskin_leathers -------------------------------------------------------

def test_scabskin_activate_gains_action_points():
    state = _state()
    sc = _equip(state, "scabskin_leathers", "legs")
    ap0 = state.players[1].action_points
    _activate(state, sc, "legs")
    delta = state.players[1].action_points - ap0
    assert 0 <= delta <= 3
    assert sc in state.players[1].legs.cards   # NOT destroyed (Battleworn handles wear)


# --- fyendals_spring_tunic ---------------------------------------------------

def test_fyendals_start_of_turn_accrues_energy_capped_at_3():
    state = _state()
    ft = _equip(state, "fyendals_spring_tunic", "chest")
    for _ in range(5):
        dispatch(state, "START_OF_TURN", "fyendals_spring_tunic", card=ft)
    assert _energy(state) == 3   # capped


def test_fyendals_activate_spends_3_energy_for_resource():
    state = _state()
    ft = _equip(state, "fyendals_spring_tunic", "chest")
    for _ in range(3):
        dispatch(state, "START_OF_TURN", "fyendals_spring_tunic", card=ft)
    assert _energy(state) == 3
    r0 = state.players[1].resources
    _activate(state, ft, "chest")
    assert state.players[1].resources == r0 + 1
    assert _energy(state) == 0   # 3 energy spent


# --- aether_crackers ---------------------------------------------------------
# Regression for the equipment-ON_HIT engine gap: "When an attack you control
# hits a hero, you may destroy this. If you do, deal 1 arcane damage to them."
# The hit listener must dispatch ON_HIT to the attacker's *equipment*, not only
# to the attack card and hero, or this passive never fires in a real game.

def test_aether_crackers_fires_on_controlled_attack_hit():
    from engine.state import CombatState, Event
    from engine.engine import _setup_dsl_listeners
    state = _state()
    _setup_dsl_listeners(state)                 # wire the real 'hit' listener
    crackers = _equip(state, "aether_crackers", "arms", pid=1)
    # A separate attack the controller owns lands the hit (NOT the crackers).
    atk = Card(slug="hunters_klaive", name="klaive", types=["Weapon"])
    atk.owner = atk.controller = 1
    state.players[1].weapon1.cards.append(atk)
    state.combat = CombatState(attacker_id=1, link_id=1, attack_power=2,
                               keywords=[], attack_card=atk)
    h0 = state.players[2].health
    # Emit the REAL hit event (bypassing it via a direct dispatch would skip the
    # very listener this test guards).
    state.event_manager.emit(
        Event(type="hit", card=atk.slug, data={"damage": 2}), state)
    assert state.players[2].health == h0 - 1              # 1 arcane dealt
    assert crackers not in state.players[1].arms.cards     # "destroy this" happened
    assert any(c.slug == "aether_crackers"
               for c in state.players[1].graveyard.cards)
