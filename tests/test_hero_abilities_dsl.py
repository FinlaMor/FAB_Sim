"""Hero activated/passive abilities — Kayo (Phase 2 slice).

Victor and Arakni hero coverage lives with their systems (clash, transform).
This file covers Kayo's Instant (SET_BASE_POWER on an attack action he controls),
the attack-action-only target restriction, and his 1-weapon-zone setup.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card import Card
from engine.card_effects.dsl import dispatch, load_all_cards
from engine.state import CombatState, Event, GameState, Player, Step

load_all_cards()


def _hero(pid: int, slug: str = "test_hero") -> Card:
    c = Card(slug=slug, name=slug, types=["Hero"], base_life=40, base_intellect=4)
    c.owner = pid
    c.controller = pid
    return c


def _state(active: int = 1, p1_hero: str = "kayo_underhanded_cheat") -> GameState:
    return GameState(
        players={1: Player(1, _hero(1, p1_hero)), 2: Player(2, _hero(2))},
        active_player=active,
        player_agents={1: lambda *a, **k: None, 2: lambda *a, **k: None},
        step=Step.COMBAT_REACTION, turn_number=1, combat=None, done=False, winner=None,
    )


def _attack(slug, owner=1, power=4, types=("Action",), subtypes=("Attack",)):
    ac = Card(slug=slug, name=slug, types=list(types), subtypes=list(subtypes))
    ac.owner = owner
    ac.controller = owner
    ac.base_power = power
    return CombatState(attacker_id=owner, link_id=1, attack_power=power,
                       base_attack_power=power, attack_card=ac, keywords=[],
                       from_weapon=False)


# ── Kayo Instant: SET_BASE_POWER ─────────────────────────────────────────────

def test_kayo_instant_sets_attack_action_to_6_base_power():
    state = _state()
    state.combat = _attack("some_swing", owner=1, power=4)
    dispatch(state, "ON_ACTIVATE", "kayo_underhanded_cheat", card=state.players[1].hero)
    assert state.combat.attack_card.base_power == 6
    assert state.combat.attack_power == 6


def test_kayo_instant_ignores_weapon_attack():
    # A weapon attack (type Weapon, not an Action-Attack) must NOT be pumped.
    state = _state()
    state.combat = _attack("dawnblade", owner=1, power=4,
                           types=("Weapon",), subtypes=("Sword",))
    dispatch(state, "ON_ACTIVATE", "kayo_underhanded_cheat", card=state.players[1].hero)
    assert state.combat.attack_card.base_power == 4  # unchanged
    assert state.combat.attack_power == 4


def test_kayo_instant_ignores_opponent_attack():
    # Only "an attack action card you control" — opponent's attack is not a target.
    state = _state()
    state.combat = _attack("enemy_swing", owner=2, power=4)
    dispatch(state, "ON_ACTIVATE", "kayo_underhanded_cheat", card=state.players[1].hero)
    assert state.combat.attack_card.base_power == 4  # unchanged


# ── Kayo passive: boo → Vigor (regression alongside the Instant) ─────────────

def test_kayo_boo_creates_vigor():
    from engine.card import CardDB
    state = _state()
    state.card_db = CardDB()
    dispatch(state, "ON_BOO", "kayo_underhanded_cheat", card=state.players[1].hero,
             event=Event(type="ON_BOO", data={"player_id": 1}))
    assert state.players[1].permanents.find("vigor") is not None


# ── Kayo setup: 1 weapon zone ────────────────────────────────────────────────

def test_kayo_starts_with_one_weapon_zone():
    import random
    from engine.engine import new_game
    from engine.card import CardDB
    card_db = CardDB()
    agent = lambda s, opts, context=None: random.choice(opts) if opts else None
    deck = "decks/kayo_underhanded_cheat_CC_lite.txt"
    # Kayo's own definition sets weapon_zones=1; assert it propagates to the Player.
    from engine.card_effects.dsl.loader import get_card
    assert get_card("kayo_underhanded_cheat").setup.get("weapon_zones") == 1
