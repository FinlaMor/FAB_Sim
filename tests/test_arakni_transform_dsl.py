"""Arakni, Marionette — Agent of Chaos transform and demi-hero abilities.

Covers the END_OF_TURN transform (become a random Agent of Chaos when an
opponent is marked), the demi-hero "return to the brood" revert, and the
Tarantula dagger-hit passive. The complex demi-hero Attack Reactions are
documented TODOs and not asserted here.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card import Card
from engine.card_effects.dsl import dispatch, load_all_cards
from engine.card_effects.ability_keywords import AGENT_OF_CHAOS_SLUGS
from engine.state import CombatState, Event, GameState, Player, Step

load_all_cards()


def _hero(pid, slug="arakni_marionette"):
    c = Card(slug=slug, name=slug, types=["Chaos", "Assassin", "Hero"],
             base_life=40, base_intellect=4)
    c.owner = pid
    c.controller = pid
    return c


def _state(p1_hero="arakni_marionette"):
    return GameState(
        players={1: Player(1, _hero(1, p1_hero)), 2: Player(2, _hero(2, "test_hero"))},
        active_player=1,
        player_agents={1: lambda *a, **k: None, 2: lambda *a, **k: None},
        step=Step.END_PHASE_BEGINNING, turn_number=1, combat=None, done=False, winner=None,
    )


def _dagger_combat(attacker_id=1):
    ac = Card(slug="kiss_of_death_red", name="Kiss", types=["Action"],
              subtypes=["Attack", "Dagger"])
    ac.owner = attacker_id
    ac.controller = attacker_id
    return CombatState(attacker_id=attacker_id, link_id=1, attack_power=3,
                       attack_card=ac, keywords=[], from_weapon=False)


# ── transform / return to the brood ──────────────────────────────────────────

def test_marionette_transforms_when_opponent_marked():
    st = _state()
    st.players[2].class_counters["marked"] = 1
    dispatch(st, "END_OF_TURN", "arakni_marionette", card=st.players[1].hero)
    assert st.players[1].hero.slug in AGENT_OF_CHAOS_SLUGS


def test_marionette_no_transform_when_not_marked():
    st = _state()
    dispatch(st, "END_OF_TURN", "arakni_marionette", card=st.players[1].hero)
    assert st.players[1].hero.slug == "arakni_marionette"


def test_demi_hero_returns_to_brood():
    st = _state(p1_hero="arakni_redback")
    dispatch(st, "END_OF_TURN", "arakni_redback", card=st.players[1].hero)
    assert st.players[1].hero.slug == "arakni_marionette"


def test_all_agent_of_chaos_slugs_load():
    from engine.card_effects.dsl.loader import get_card
    for slug in AGENT_OF_CHAOS_SLUGS:
        assert get_card(slug) is not None, slug


# ── Tarantula passive: a dagger you own hitting a hero costs them 1 life ──────

def test_tarantula_dagger_hit_drains_opponent_life():
    st = _state(p1_hero="arakni_tarantula")
    st.combat = _dagger_combat(attacker_id=1)
    st.players[2].life = 40
    dispatch(st, "ON_HIT", "arakni_tarantula", card=st.players[1].hero,
             event=Event(type="ON_HIT", data={"damage": 3}))
    assert st.players[2].life == 39


def test_tarantula_non_dagger_hit_no_drain():
    st = _state(p1_hero="arakni_tarantula")
    ac = Card(slug="plain_swing", name="Swing", types=["Action"], subtypes=["Attack"])
    ac.owner = 1
    ac.controller = 1
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=ac, keywords=[], from_weapon=False)
    st.players[2].life = 40
    dispatch(st, "ON_HIT", "arakni_tarantula", card=st.players[1].hero,
             event=Event(type="ON_HIT", data={"damage": 3}))
    assert st.players[2].life == 40
