"""WTR crush vertical slice — DSL-authoritative behaviour.

Covers the four migrated WTR crush cards end-to-end:
  * cranial_crush_blue  — opponent can't draw during their next action phase
  * debilitate_*        — opponent's first attack next turn gets -2{p}
  * disable_*           — opponent's arsenal card goes to bottom of deck
  * spinal_crush_red    — opponent's go again is suppressed next turn

These exercise the consumption side (the effect actually changing play) plus
the ON_CRUSH gating and the removal of the legacy Python fallback.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import engine.engine as E
from engine.card import Card
from engine.card_effects.dsl import dispatch, load_all_cards
from engine.card_effects.dsl.loader import get_card as _dsl_get_card
from engine.effect_keywords import draw
from engine.state import CombatState, Event, GameState, Player, Step

load_all_cards()


def _hero(pid: int) -> Card:
    c = Card(slug="test_hero", name="H", types=["Hero"], base_life=40, base_intellect=4)
    c.owner = pid
    c.controller = pid
    return c


def _state(active: int = 1) -> GameState:
    return GameState(
        players={1: Player(1, _hero(1)), 2: Player(2, _hero(2))},
        active_player=active,
        player_agents={1: lambda *a, **k: None, 2: lambda *a, **k: None},
        step=Step.ACTION, turn_number=1, combat=None, done=False, winner=None,
    )


def _attack(slug: str, owner: int = 1, power: int = 9) -> CombatState:
    ac = Card(slug=slug, name=slug, types=["Action"], subtypes=["Attack"])
    ac.owner = owner
    ac.controller = owner
    ac.zone = "combat_chain"
    return CombatState(attacker_id=owner, link_id=1, attack_power=power,
                       attack_card=ac, keywords=[], from_weapon=False)


def _crush(state: GameState, slug: str, damage: int = 5):
    dispatch(state, "ON_CRUSH", slug, card=state.combat.attack_card,
             event=Event(type="ON_CRUSH", data={"damage": damage}))


# --- migration wiring --------------------------------------------------------

def test_crush_cards_are_migrated():
    for s in ("cranial_crush_blue", "debilitate_blue", "debilitate_red",
              "debilitate_yellow", "disable_blue", "disable_red",
              "disable_yellow", "spinal_crush_red"):
        assert _dsl_get_card(s) is not None, s


def test_no_python_fallback_for_crush_cards():
    from engine.card_effects.triggers import CARD_TRIGGERS
    for base in ("cranial_crush", "debilitate", "disable", "spinal_crush"):
        assert base not in CARD_TRIGGERS


# --- cranial_crush: can't draw next action phase -----------------------------

def test_cranial_crush_blocks_opponent_action_phase_draw():
    s = _state()
    s.combat = _attack("cranial_crush_blue")
    _crush(s, "cranial_crush_blue")
    # roll the flag into the opponent's turn
    opp = s.players[2]
    opp.current_turn_effects = opp.next_turn_effects[:]
    for i in range(3):
        c = Card(slug=f"d{i}", name="d", types=["Action"])
        c.owner = 2
        opp.deck.add(c)
    before = len(opp.hand.cards)
    draw(s, 2, number=2)
    assert len(opp.hand.cards) == before  # draws suppressed


def test_cranial_crush_does_not_block_after_flag_cleared():
    s = _state()
    c = Card(slug="d0", name="d", types=["Action"]); c.owner = 2
    s.players[2].deck.add(c)
    draw(s, 2, number=1)
    assert len(s.players[2].hand.cards) == 1  # normal draw works


# --- debilitate: first attack next turn -2p ----------------------------------

def test_debilitate_reduces_first_attack_power():
    s = _state(active=2)
    s.players[2].current_turn_effects.append("first_attack_-2p")
    atk = Card(slug="opp_atk", name="a", types=["Action"], subtypes=["Attack"])
    atk.owner = 2; atk.controller = 2; atk.power = 6; atk.cost = 1
    s.combat = CombatState(attacker_id=2, link_id=1, attack_power=6,
                           attack_card=atk, keywords=[], from_weapon=False)
    E._apply_turn_attack_effects(s, atk)
    assert "first_attack_-2p" not in s.players[2].current_turn_effects
    # a -2 power CardEffect was attached
    powered = [e for e in getattr(atk, "effects", []) if e.prop == "power"]
    assert powered and powered[0].fn(6) == 4


# --- disable: opponent arsenal -> bottom of deck -----------------------------

def test_disable_moves_opponent_arsenal_to_deck():
    s = _state()
    arc = Card(slug="opp_arsenal", name="a", types=["Action"]); arc.owner = 2
    s.players[2].arsenal.add(arc)
    s.combat = _attack("disable_blue")
    _crush(s, "disable_blue")
    assert len(s.players[2].arsenal.cards) == 0
    assert s.players[2].deck.cards[-1].slug == "opp_arsenal"


# --- spinal_crush: suppress go again -----------------------------------------

def test_spinal_crush_sets_cant_go_again_on_opponent():
    s = _state()
    s.combat = _attack("spinal_crush_red")
    _crush(s, "spinal_crush_red")
    assert "cant_go_again" in s.players[2].next_turn_effects
