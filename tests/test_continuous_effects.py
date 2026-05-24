"""Tests for ContinuousEffect lifetime management.

Covers:
- gets() and gets_property() clean up their ContinuousEffect when
  target card leaves the arena (Option A / no until_condition path).
- EffectManager.staging is the same object as state.continuous_effect_manager.
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from tests.conftest import _make_state, _make_card

from engine.effect_keywords import gets, gets_property
from engine.continuous_effects import ContinuousEffect, ContinuousEffectManager
from engine.state import Event


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ally_in_arena(state, slug="test_ally", power=3):
    card = _make_card(slug=slug, types=["Ally"])
    card.base_power = power
    card.power = power
    card.subtypes = ["Ally"]
    card.zone = "allies"
    state.players[1].allies.add(card)
    return card


# ---------------------------------------------------------------------------
# Part 1 — gets() arena-exit cleanup
# ---------------------------------------------------------------------------

def test_gets_persistent_cleaned_up_on_arena_exit():
    """gets(until_condition=None): effect removed when target card leaves arena."""
    state = _make_state()
    ally = _make_ally_in_arena(state)

    gets(state, prop='power', kind='add', amount=2,
         source_card=None, target_card=ally, until_condition=None)

    # Effect must be present before exit
    assert len(state.continuous_effect_manager._effects) == 1

    # Simulate card leaving arena
    state.event_manager.emit(
        Event(type='leaves_arena', data={'card': ally}), state
    )

    assert len(state.continuous_effect_manager._effects) == 0


def test_gets_property_persistent_cleaned_up_on_arena_exit():
    """gets_property(until_condition=None): effect removed when target card leaves arena."""
    state = _make_state()
    ally = _make_ally_in_arena(state)

    gets_property(state, prop='keywords', value='Go Again',
                  source_card=None, target_card=ally, until_condition=None)

    assert len(state.continuous_effect_manager._effects) == 1

    state.event_manager.emit(
        Event(type='leaves_arena', data={'card': ally}), state
    )

    assert len(state.continuous_effect_manager._effects) == 0


def test_gets_with_condition_not_cleaned_by_arena_exit():
    """gets(until_condition='end_of_turn'): arena exit must NOT remove the effect."""
    state = _make_state()
    ally = _make_ally_in_arena(state)

    gets(state, prop='power', kind='add', amount=2,
         source_card=None, target_card=ally, until_condition='end_of_turn')

    assert len(state.continuous_effect_manager._effects) == 1

    # Arena exit should not remove an effect that has its own until_condition handler
    state.event_manager.emit(
        Event(type='leaves_arena', data={'card': ally}), state
    )

    assert len(state.continuous_effect_manager._effects) == 1


def test_gets_effect_still_applies_before_exit():
    """Effect is present and registered before the card leaves play."""
    state = _make_state()
    ally = _make_ally_in_arena(state)

    result = gets(state, prop='power', kind='add', amount=5,
                  source_card=None, target_card=ally, until_condition=None)

    assert not result.canceled
    assert len(state.continuous_effect_manager._effects) == 1


def test_gets_arena_exit_only_removes_matching_card():
    """leaves_arena for a different card must NOT remove the effect."""
    state = _make_state()
    ally = _make_ally_in_arena(state, slug="ally_a")
    other = _make_ally_in_arena(state, slug="ally_b")

    gets(state, prop='power', kind='add', amount=2,
         source_card=None, target_card=ally, until_condition=None)

    # Different card exits — effect for `ally` must remain
    state.event_manager.emit(
        Event(type='leaves_arena', data={'card': other}), state
    )

    assert len(state.continuous_effect_manager._effects) == 1


# ---------------------------------------------------------------------------
# Part 2 — EffectManager.staging consolidation
# ---------------------------------------------------------------------------

def test_effect_manager_has_staging():
    """EffectManager.staging is a ContinuousEffectManager instance."""
    state = _make_state()
    assert isinstance(state.effect_manager.staging, ContinuousEffectManager)


def test_continuous_effect_manager_property_delegates():
    """state.continuous_effect_manager IS state.effect_manager.staging (identity)."""
    state = _make_state()
    assert state.continuous_effect_manager is state.effect_manager.staging


def test_staging_add_and_remove():
    """Add and remove via the property works correctly."""
    from engine.continuous_effects import next_timestamp
    state = _make_state()

    ce = ContinuousEffect(
        stage=8, substage=5, timestamp=next_timestamp(),
        prop='power', source_slug='test',
        apply_fn=lambda v, s, c: v + 1,
        effect_id='test_effect_id',
    )
    state.continuous_effect_manager.add(ce)
    assert len(state.continuous_effect_manager._effects) == 1

    state.continuous_effect_manager.remove_by_id('test_effect_id')
    assert len(state.continuous_effect_manager._effects) == 0
