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


# ---------------------------------------------------------------------------
# CR 3.15.4: card-layers keep their LIFO positions — only newly-created
# triggered-layers are ordered (a DR played in response to an AR must NOT
# produce a trigger-ordering prompt).
# ---------------------------------------------------------------------------

def test_card_layers_are_never_reordered():
    state = _make_state()
    ar = _make_card("some_attack_reaction")
    dr = _make_card("some_defense_reaction")
    e_ar = StackEntry(player_id=1, card=ar, layer_type='card')
    e_dr = StackEntry(player_id=2, card=dr, layer_type='card')
    state.stack_entries = [e_ar, e_dr]  # DR on top (played in response)

    prompts = []
    state.player_agents[1] = lambda s, opts, context=None, **k: prompts.append(context) or opts[0]
    state.player_agents[2] = lambda s, opts, context=None, **k: prompts.append(context) or opts[0]

    order_stack(state)

    assert state.stack_entries == [e_ar, e_dr], "card layers must keep LIFO order"
    assert not prompts, "no ordering prompt may fire for card layers"


def test_new_triggers_ordered_on_top_of_card_layers():
    state = _make_state()
    card_layer = StackEntry(player_id=1, card=_make_card("played_card"), layer_type='card')
    t1 = _make_triggered_entry(_make_card("trig_a"), player_id=1)
    t2 = _make_triggered_entry(_make_card("trig_b"), player_id=1)
    state.stack_entries = [t1, card_layer, t2]  # triggers created around a card layer

    order_stack(state)

    # Card layer keeps its relative position at the bottom; both triggers sit
    # on top (end of list = resolves first) and are marked ordered.
    assert state.stack_entries[0] is card_layer
    assert {id(e) for e in state.stack_entries[1:]} == {id(t1), id(t2)}
    assert all(getattr(e, '_ordered', False) for e in (t1, t2))

    # A second order_stack call must not re-order or re-prompt.
    before = list(state.stack_entries)
    order_stack(state)
    assert state.stack_entries == before
