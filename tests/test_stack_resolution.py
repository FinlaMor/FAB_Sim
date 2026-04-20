"""Tests confirming that order_stack is only called when new triggers arrive,
not after every resolution in _resolve_all_triggers.

CR 6.6.6b: triggered abilities are ordered once when they simultaneously appear on
the stack. Existing ordering must be preserved across subsequent resolutions.
"""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch, call

from tests.conftest import _make_state, _make_card
from engine.state import StackEntry
from engine.engine import _resolve_all_triggers, order_stack


def _make_triggered_entry(card, player_id=1, effect_fn=None):
    """Build a triggered-layer StackEntry (no stack zone tracking needed for unit tests)."""
    return StackEntry(
        player_id=player_id,
        card=card,
        layer_type='triggered',
        is_triggered=True,
        effect_fn=effect_fn,
    )


# ---------------------------------------------------------------------------
# Existing order preserved — no re-ordering prompts after each resolution
# ---------------------------------------------------------------------------

def test_existing_trigger_order_preserved_after_one_resolves():
    """Two ordered triggers; first resolves; second remains in correct position.

    order_stack must NOT be re-called (no new triggers arrived), so the
    second trigger's position is untouched.
    """
    state = _make_state()
    card_a = _make_card("card_a")
    card_b = _make_card("card_b")

    resolved = []
    entry_a = _make_triggered_entry(card_a, player_id=1,
                                    effect_fn=lambda c, s: resolved.append('A'))
    entry_b = _make_triggered_entry(card_b, player_id=1,
                                    effect_fn=lambda c, s: resolved.append('B'))

    # Stack is LIFO: append order = [B, A] means A resolves first (pop from end)
    state.stack_entries = [entry_b, entry_a]

    _resolve_all_triggers(state)

    # Both should resolve; A first (was at end), then B
    assert resolved == ['A', 'B']
    # Stack should be empty when done
    assert state.stack_entries == []


def test_no_reorder_when_no_new_triggers():
    """order_stack is called exactly once (initial) when triggers don't generate new ones."""
    state = _make_state()
    card_a = _make_card("card_a")
    card_b = _make_card("card_b")

    entry_a = _make_triggered_entry(card_a, player_id=1)
    entry_b = _make_triggered_entry(card_b, player_id=1)
    state.stack_entries = [entry_b, entry_a]

    order_call_count = []

    original_order_stack = order_stack

    def counting_order_stack(gs):
        order_call_count.append(1)
        original_order_stack(gs)

    with patch('engine.engine.order_stack', side_effect=counting_order_stack):
        _resolve_all_triggers(state)

    # Should be called exactly once (the initial ordering before the loop)
    assert len(order_call_count) == 1, (
        f"order_stack was called {len(order_call_count)} times; expected 1 "
        "(no new triggers generated, so no re-ordering should happen)"
    )


def test_order_stack_called_when_new_trigger_arrives():
    """If resolving a trigger generates a NEW entry, order_stack fires again for it."""
    state = _make_state()
    card_a = _make_card("card_a")
    card_b = _make_card("card_b")

    def spawn_new_trigger(c, s):
        """Effect: push a new triggered entry onto the stack."""
        new_entry = _make_triggered_entry(card_b, player_id=1)
        s.stack_entries.append(new_entry)

    entry_a = _make_triggered_entry(card_a, player_id=1, effect_fn=spawn_new_trigger)
    state.stack_entries = [entry_a]

    order_call_count = []
    original_order_stack = order_stack

    def counting_order_stack(gs):
        order_call_count.append(1)
        original_order_stack(gs)

    with patch('engine.engine.order_stack', side_effect=counting_order_stack):
        _resolve_all_triggers(state)

    # Initial call + one more when the new trigger arrived = 2
    assert len(order_call_count) == 2, (
        f"order_stack was called {len(order_call_count)} times; expected 2 "
        "(initial ordering + one re-order when new trigger was generated)"
    )
