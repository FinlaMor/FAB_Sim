"""WTR next-attack buff group — DSL-authoritative behaviour.

  * awakening_bellow_red/yellow/blue — intimidate + next Brute attack action +3/+2/+1{p}
  * nimblism_red/yellow/blue         — next cost<=1 attack action card +3/+2/+1{p}

Both queue a MODIFY_NEXT_ATTACK mod consumed by _apply_turn_attack_effects at attack
creation, filtered by class/type/subtype/cost. Go again comes from the printed keyword.
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
from engine.state import CombatState, GameState, Player, Step

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


def _play(state: GameState, slug: str):
    c = Card(slug=slug, name=slug, types=["Action"])
    c.owner = 1
    c.controller = 1
    dispatch(state, "ON_PLAY", slug, card=c)


def _attack(state: GameState, slug, classes, cost, power, subtypes=("Attack",)):
    a = Card(slug=slug, name=slug, types=["Action"], subtypes=list(subtypes))
    a.owner = 1
    a.controller = 1
    a.classes = list(classes)
    a.cost = cost
    a.power = power
    a.zone = "combat_chain"
    a.effects = []
    state.combat = CombatState(attacker_id=1, link_id=1, attack_power=power,
                               attack_card=a, keywords=[], from_weapon=False)
    E._apply_turn_attack_effects(state, a)
    return a


def _power(a: Card) -> int:
    val = a.power
    for eff in a.effects:
        if getattr(eff, "prop", None) == "power":
            val = eff.fn(val)
    return val


# --- migration wiring --------------------------------------------------------

def test_next_attack_cards_migrated():
    for s in ("awakening_bellow_red", "awakening_bellow_yellow", "awakening_bellow_blue",
              "nimblism_red", "nimblism_yellow", "nimblism_blue"):
        assert _dsl_get_card(s) is not None, s


def test_no_python_fallback_for_nimblism():
    from engine.card_effects.triggers import CARD_TRIGGERS
    from engine.card_effects.registry import TURN_ATTACK_EFFECTS
    assert "nimblism_blue" not in CARD_TRIGGERS
    assert "nimblism_next_attack_plus1" not in TURN_ATTACK_EFFECTS


# --- awakening_bellow: next Brute attack +N ----------------------------------

def test_awakening_bellow_red_buffs_next_brute_attack():
    state = _state()
    _play(state, "awakening_bellow_red")
    atk = _attack(state, "pack_hunt_red", ["Brute"], cost=2, power=6)
    assert _power(atk) == 9                     # 6 + 3
    assert state.players[1].dsl_queued_attack_mods == []   # consumed


def test_awakening_bellow_ignores_non_brute_attack():
    state = _state()
    _play(state, "awakening_bellow_red")
    atk = _attack(state, "ninja_strike", ["Ninja"], cost=2, power=4)
    assert _power(atk) == 4                     # no bonus
    assert len(state.players[1].dsl_queued_attack_mods) == 1   # mod retained


def test_awakening_bellow_amounts_by_color():
    for slug, amt in (("awakening_bellow_blue", 1), ("awakening_bellow_yellow", 2),
                      ("awakening_bellow_red", 3)):
        state = _state()
        _play(state, slug)
        atk = _attack(state, "pack_hunt_red", ["Brute"], cost=2, power=5)
        assert _power(atk) == 5 + amt, slug


# --- nimblism: next cost<=1 attack +N ----------------------------------------

def test_nimblism_red_buffs_low_cost_attack():
    state = _state()
    _play(state, "nimblism_red")
    atk = _attack(state, "head_jab_red", ["Ninja"], cost=0, power=3)
    assert _power(atk) == 6                     # 3 + 3


def test_nimblism_ignores_high_cost_attack():
    state = _state()
    _play(state, "nimblism_red")
    atk = _attack(state, "big_attack", ["Ninja"], cost=3, power=5)
    assert _power(atk) == 5                     # cost > 1 -> no bonus
    assert len(state.players[1].dsl_queued_attack_mods) == 1


def test_nimblism_amounts_by_color():
    for slug, amt in (("nimblism_blue", 1), ("nimblism_yellow", 2), ("nimblism_red", 3)):
        state = _state()
        _play(state, slug)
        atk = _attack(state, "head_jab_red", ["Ninja"], cost=1, power=2)
        assert _power(atk) == 2 + amt, slug
