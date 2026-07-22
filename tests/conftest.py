"""Shared test fixtures and helpers for FAB_Sim test suite."""

import json
import os
import sys

import pytest

from engine.card import Card
from engine.state import CombatState, GameState, Player, Step, Zone


# ---------------------------------------------------------------------------
# Opt-in DSL execution-coverage capture during the test run
# ---------------------------------------------------------------------------
# scripts/dsl_coverage.py plays random games and flags any authored effect that
# never fired. On its own that is a *weak* signal: an effect a unit test drives
# but no random game happens to reach reads as "never executed". Set
# FAB_DSL_COVERAGE_OUT=<path> to record every (slug, effect_type) the *test
# suite* executes into that JSON file; `dsl_coverage.py --merge-tests <path>`
# then folds it in, so only genuinely-dead effects remain flagged.
#
# Disabled unless the env var is set — no overhead on a normal run.

def pytest_sessionstart(session):
    out = os.environ.get("FAB_DSL_COVERAGE_OUT")
    if not out:
        return
    from engine.card_effects.dsl import coverage
    coverage.start()


def pytest_sessionfinish(session, exitstatus):
    out = os.environ.get("FAB_DSL_COVERAGE_OUT")
    if not out:
        return
    from engine.card_effects.dsl import coverage
    tracker = coverage.stop()
    effects = sorted(tracker.effects) if tracker else []
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"effects": effects}, f, indent=2)


@pytest.fixture(autouse=True, scope="module")
def _restore_dsl_registry():
    """Keep the full DSL card registry loaded around each test module.

    Some tests (and some modules at import time) call load_all_cards() on a temp
    dir or a single set folder, which replaces the module-global registry.
    Reload the full tree both before and after each module so no module runs
    against a subset polluted during collection or by a prior module.
    """
    from engine.card_effects.dsl import loader
    if loader._LOADED:
        loader.load_all_cards()
    yield
    if loader._LOADED:
        loader.load_all_cards()


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
               types: list[str] | None = None, **kwargs) -> Card:
    """Create a Card with sensible defaults, overridable via kwargs.
    Defaults to type 'Action' so cards can legally enter hand/deck zones.
    Extra kwargs (e.g. base_defense, base_power) are set as attributes on the card.
    """
    raw_types = types if types is not None else ["Action"]
    card = Card(slug=slug, raw_name=name, raw_types=raw_types)
    for attr, val in kwargs.items():
        setattr(card, attr, val)
        # Propagate base_X → X so the current field reflects the new base value
        if attr.startswith('base_'):
            current = attr[5:]
            if hasattr(card, current) and getattr(card, current) is None:
                setattr(card, current, val)
    return card


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

    opp_hero = _make_hero(3 - attacker_id)

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
