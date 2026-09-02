"""Phase 1 — engine→DSL event bridges, WHILE_STATIC recalc bridge, pitch tracking.

Behavioral coverage for the generic mechanisms that the three test decks need:
  * ON_PITCH   — Riches of Trōpal-Dhani creates a Gold when pitched
  * ON_DEFEND  — Scowling Flesh Bag intimidates the attacker when it defends
  * ON_BOO     — Kayo creates a Vigor token when the crowd boos him
  * WHILE_STATIC recalc bridge — Anothos +2{p}; Savage Claw pitch-for-attack +1{p}
  * Arakni continuous +1{p} + ON_HIT go again vs a marked hero with stealth
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


def _state(active: int = 1, p1_hero: str = "test_hero", p2_hero: str = "test_hero") -> GameState:
    return GameState(
        players={1: Player(1, _hero(1, p1_hero)), 2: Player(2, _hero(2, p2_hero))},
        active_player=active,
        player_agents={1: lambda *a, **k: None, 2: lambda *a, **k: None},
        step=Step.ACTION, turn_number=1, combat=None, done=False, winner=None,
    )
    # card_db is set below by callers that create tokens


def _with_db(state: GameState) -> GameState:
    from engine.card import CardDB
    state.card_db = CardDB()
    return state


def _attack(slug: str, owner: int = 1, power: int = 3, keywords=None,
            subtypes=("Attack",)) -> CombatState:
    ac = Card(slug=slug, name=slug, types=["Action"], subtypes=list(subtypes))
    ac.owner = owner
    ac.controller = owner
    ac.zone = "combat_chain"
    return CombatState(attacker_id=owner, link_id=1, attack_power=power,
                       base_attack_power=power, attack_card=ac,
                       keywords=list(keywords or []), from_weapon=False)


# ── ON_PITCH: Riches of Trōpal-Dhani ─────────────────────────────────────────

def test_riches_pitch_creates_gold():
    state = _with_db(_state())
    card = Card(slug="riches_of_tropal_dhani_yellow", name="Riches", types=["Resource"])
    card.owner = 1
    card.controller = 1
    dispatch(state, "ON_PITCH", "riches_of_tropal_dhani_yellow", card=card,
             event=Event(type="ON_PITCH", data={"card": card}))
    assert state.players[1].permanents.find("gold") is not None


# ── ON_DEFEND: Scowling Flesh Bag ────────────────────────────────────────────

def test_scowling_defend_intimidates_attacker():
    state = _with_db(_state())
    # Attacker is player 2; scowling belongs to defender player 1.
    state.combat = _attack("some_attack", owner=2)
    # Give the attacker a hand card so intimidate has something to banish.
    victim = Card(slug="filler", name="Filler", types=["Action"])
    victim.owner = 2
    state.players[2].hand.add(victim)
    scowling = Card(slug="scowling_flesh_bag", name="Scowling", types=["Equipment"],
                    subtypes=["Head"])
    scowling.owner = 1
    scowling.controller = 1
    before = len(state.players[2].hand.cards)
    dispatch(state, "ON_DEFEND", "scowling_flesh_bag", card=scowling,
             event=Event(type="ON_DEFEND", data={"card": scowling}))
    # Intimidate banishes a random card from the attacker's hand.
    assert len(state.players[2].hand.cards) == before - 1


# ── ON_BOO: Kayo ─────────────────────────────────────────────────────────────

def test_kayo_boo_creates_vigor():
    state = _with_db(_state(p1_hero="kayo_underhanded_cheat"))
    hero = state.players[1].hero
    dispatch(state, "ON_BOO", "kayo_underhanded_cheat", card=hero,
             event=Event(type="ON_BOO", data={"player_id": 1}))
    assert state.players[1].permanents.find("vigor") is not None


# ── WHILE_STATIC recalc bridge: Savage Claw ──────────────────────────────────

def test_savage_claw_bonus_when_6power_pitched_for_attack():
    state = _state()
    combat = _attack("savage_claw", owner=1, power=3)
    pitched = Card(slug="big", name="Big", types=["Action"])
    pitched.base_power = 6
    combat.pitched_for_attack = [pitched]
    state.combat = combat
    dispatch(state, "RECALC_ATTACK_POWER", "savage_claw", card=combat.attack_card)
    assert state.combat.attack_power == 4  # 3 + 1


def test_savage_claw_no_bonus_when_nothing_pitched_for_attack():
    state = _state()
    combat = _attack("savage_claw", owner=1, power=3)
    # A 6-power card sits in the pitch zone but was NOT pitched for this attack.
    stray = Card(slug="big", name="Big", types=["Action"])
    stray.base_power = 6
    state.players[1].pitch.add(stray)
    combat.pitched_for_attack = []  # Claw paid from floating resources
    state.combat = combat
    dispatch(state, "RECALC_ATTACK_POWER", "savage_claw", card=combat.attack_card)
    assert state.combat.attack_power == 3  # unchanged


def test_savage_claw_no_bonus_when_low_power_pitched():
    state = _state()
    combat = _attack("savage_claw", owner=1, power=3)
    small = Card(slug="small", name="Small", types=["Action"])
    small.base_power = 4
    combat.pitched_for_attack = [small]
    state.combat = combat
    dispatch(state, "RECALC_ATTACK_POWER", "savage_claw", card=combat.attack_card)
    assert state.combat.attack_power == 3  # 4 < 6


# ── Arakni: continuous stealth-vs-marked buff + ON_HIT go again ──────────────

def _arakni_state(marked: bool, stealth: bool):
    state = _state(p1_hero="arakni_marionette")
    kws = ["Stealth"] if stealth else []
    state.combat = _attack("some_dagger", owner=1, power=4, keywords=kws)
    if marked:
        state.players[2].class_counters["marked"] = 1
    return state


def test_arakni_buff_applies_when_stealth_and_marked():
    state = _arakni_state(marked=True, stealth=True)
    dispatch(state, "RECALC_ATTACK_POWER", "arakni_marionette", card=state.players[1].hero)
    assert state.combat.attack_power == 5  # 4 + 1


def test_arakni_buff_absent_when_not_marked():
    state = _arakni_state(marked=False, stealth=True)
    dispatch(state, "RECALC_ATTACK_POWER", "arakni_marionette", card=state.players[1].hero)
    assert state.combat.attack_power == 4


def test_arakni_buff_absent_without_stealth():
    state = _arakni_state(marked=True, stealth=False)
    dispatch(state, "RECALC_ATTACK_POWER", "arakni_marionette", card=state.players[1].hero)
    assert state.combat.attack_power == 4


def test_arakni_hit_grants_go_again_when_stealth_and_marked():
    state = _arakni_state(marked=True, stealth=True)
    dispatch(state, "ON_ANY_HIT", "arakni_marionette", card=state.players[1].hero,
             event=Event(type="ON_HIT", data={"damage": 4}))
    assert any(k.lower() == "go again" for k in state.combat.keywords)


def test_arakni_hit_no_go_again_when_not_marked():
    state = _arakni_state(marked=False, stealth=True)
    dispatch(state, "ON_ANY_HIT", "arakni_marionette", card=state.players[1].hero,
             event=Event(type="ON_HIT", data={"damage": 4}))
    assert not any(k.lower() == "go again" for k in state.combat.keywords)
