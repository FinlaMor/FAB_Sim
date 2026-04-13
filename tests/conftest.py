"""Shared test fixtures and helpers for FAB_Sim test suite."""

import json
import os
import sys

import pytest

from engine.card import Card
from engine.state import CombatState, GameState, Player, Step, Zone


# ---------------------------------------------------------------------------
# Test helper factories (extracted from tests/test_loader_conditions.py)
# ---------------------------------------------------------------------------

def _make_hero(pid: int = 1) -> Card:
    c = Card(slug="test_hero", raw_name="Test Hero", raw_types=["Hero"], raw_life=40,
            raw_intellect=4)
    c.owner = pid
    c.controller = pid
    return c


def _make_player(pid: int = 1) -> Player:
    return Player(pid, _make_hero(pid))


def _mock_agent(state, options, context, **kwargs):
    if options:
        return options[0]
    return None


def _make_state() -> GameState:
    p1 = _make_player(1)
    p2 = _make_player(2)
    return GameState(
        players={1: p1, 2: p2},
        active_player=1,
        player_agents={1: _mock_agent, 2: _mock_agent},
        step=Step.ACTION,
        turn_number=1,
        combat=None,
        done=False,
        winner=None,
    )


def _make_card(slug: str = "test_card", name: str = "Test Card",
               types: list[str] | None = None) -> Card:
    """Create a Card with sensible defaults, overridable via kwargs.
    Defaults to type 'Action' so cards can legally enter hand/deck zones.
    """
    raw_types = types if types is not None else ["Action"]
    return Card(slug=slug, raw_name=name, raw_types=raw_types)


def _make_combat(attacker_id: int = 1, attack_card: Card | None = None) -> CombatState:
    """Create a minimal CombatState for testing combat-related cards."""
    if attack_card is None:
        attack_card = _make_card(
            slug="test_attack",
            name="Test Attack",
            types=["Action", "Attack"])
        
        attack_card.base_power=3
        attack_card.owner = attacker_id
        attack_card.controller = attacker_id

        opp = 3 - attacker_id
        opp_hero = _make_hero(opp)

    return CombatState(
        attacker_id=attacker_id,
        attack_target=opp_hero,
        link_id=1,
        attack_power=attack_card.base_power or 0,
        attack_card=attack_card,
        keywords=[],
    )


# ---------------------------------------------------------------------------
# Dynamic parametrization hook for card_slug fixture
# ---------------------------------------------------------------------------

def pytest_generate_tests(metafunc):
    """Parametrize tests that request a 'card_slug' fixture with all slugs
    from slug_index.json.  Only fires when 'card_slug' is explicitly listed
    in fixture names — will NOT interfere with other tests."""
    if "card_slug" in metafunc.fixturenames:
        from config import SLUG_INDEX_PATH

        with open(SLUG_INDEX_PATH, "r", encoding="utf-8") as f:
            slug_index = json.load(f)
        slugs = sorted(slug_index["by_slug"].keys())
        metafunc.parametrize("card_slug", slugs)
