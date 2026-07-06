"""Tests for the attack activation path in engine/play.py.

Covers the architectural decision that weapon and ally attacks are activated
abilities (CR 1.6.2b, CR 11.0) routed through ACTIVATE_CARD with
is_attack_proxy=True, processed by _apply_activate → StackEntry(layer_type='activated').

All costs (AP, resources, exhaustion) live exclusively in _pay_costs so there
is one authoritative deduction site.
"""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from tests.conftest import _make_state, _make_card, _make_player

from engine.actions import Action, ActionType
from engine.play import apply_action, _ally_attack_resource_cost
from engine.state import StackEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_weapon(slug="test_sword", power=3, resource_cost=0):
    """Minimal weapon card: type=Weapon, has attack power.

    resource_cost is expressed as `{r}` tokens in functional_text so
    _weapon_cost() parses it correctly (it reads text, not activation_cost).
    """
    cost_str = "{r}" * resource_cost
    ftext = f"— {cost_str}:" if resource_cost else "— **Attack**"
    card = _make_card(slug=slug, name="Test Sword", types=["Weapon"])
    card.base_power = power
    card.power = power
    card.activation_cost = resource_cost
    card.functional_text = ftext
    # Ensure legality check fields are strings (not None)
    card.base_text_box = ""
    card.base_functional_text = ftext
    return card


def _make_ally(slug="test_ally", power=2, resource_cost=0):
    """Minimal ally card with an attack activation."""
    card = _make_card(slug=slug, name="Test Ally", types=["Ally"])
    card.base_power = power
    card.power = power
    card.cost = resource_cost
    card.subtypes = ["Ally"]
    # Ally attack activation text (so legal check doesn't block)
    card.functional_text = "**Action** — **Attack**"
    card.base_text_box = ""
    card.base_functional_text = ""
    return card


def _make_pitchable(slug="blue_card", pitch_value=3):
    """A hand card that can be pitched for resources."""
    card = _make_card(slug=slug, name="Blue Card", types=["Action"])
    card.pitch = pitch_value
    card.base_pitch = pitch_value
    card.cost = 0
    card.base_text_box = ""
    card.base_functional_text = ""
    return card


def _weapon_attack_action(weapon_card, player_id=1, target=None):
    """Build an ACTIVATE_CARD + is_attack_proxy=True action for a weapon attack."""
    a = Action(
        type=ActionType.ACTIVATE_CARD,
        player_id=player_id,
        card=weapon_card,
        attack_source=weapon_card,
        is_attack_proxy=True,
        target=target,
    )
    return a


def _ally_attack_action(ally_card, choose_index=0, player_id=1):
    """Build an ACTIVATE_CARD + is_attack_proxy=True action for an ally attack."""
    a = Action(
        type=ActionType.ACTIVATE_CARD,
        player_id=player_id,
        card=ally_card,
        choose_index=choose_index,
        attack_source=ally_card,
        is_attack_proxy=True,
    )
    return a


# ---------------------------------------------------------------------------
# Weapon attack — StackEntry creation
# ---------------------------------------------------------------------------

def test_weapon_attack_creates_activated_layer_stack_entry():
    """CR 1.6.2b: weapon attack creates an activated-layer StackEntry."""
    state = _make_state()
    weapon = _make_weapon()
    state.players[1].weapon1.add(weapon)
    state.players[1].action_points = 1
    state.players[1].resources = 0

    apply_action(state, _weapon_attack_action(weapon))

    assert len(state.stack_entries) == 1
    entry = state.stack_entries[0]
    assert entry.layer_type == 'activated'
    assert entry.card is weapon


def test_weapon_attack_stack_entry_is_attack_true():
    """StackEntry.is_attack must be True so engine routes to combat."""
    state = _make_state()
    weapon = _make_weapon()
    state.players[1].weapon1.add(weapon)
    state.players[1].action_points = 1

    apply_action(state, _weapon_attack_action(weapon))

    assert state.stack_entries[0].is_attack is True


def test_weapon_attack_exhausts_weapon():
    """_pay_costs must set player.weapon_exhausted=True as part of cost."""
    state = _make_state()
    weapon = _make_weapon()
    state.players[1].weapon1.add(weapon)
    state.players[1].action_points = 1
    state.players[1].weapon_exhausted = False

    apply_action(state, _weapon_attack_action(weapon))

    assert state.players[1].weapon_exhausted is True


def test_weapon_attack_deducts_action_point():
    """_pay_costs deducts 1 AP for a weapon attack (CR 4.4.3)."""
    state = _make_state()
    weapon = _make_weapon()
    state.players[1].weapon1.add(weapon)
    state.players[1].action_points = 2

    apply_action(state, _weapon_attack_action(weapon))

    assert state.players[1].action_points == 1


def test_weapon_attack_with_resource_cost_deducts_resources():
    """Weapon with {r} cost: resources deducted from player.resources."""
    state = _make_state()
    weapon = _make_weapon(resource_cost=1)
    state.players[1].weapon1.add(weapon)
    state.players[1].action_points = 1
    state.players[1].resources = 2

    apply_action(state, _weapon_attack_action(weapon))

    assert state.players[1].resources == 1


def test_weapon_attack_can_pitch_to_cover_resource_cost():
    """Player can pitch a hand card to cover weapon resource cost."""
    state = _make_state()
    weapon = _make_weapon(resource_cost=2)
    blue = _make_pitchable(pitch_value=2)
    state.players[1].weapon1.add(weapon)
    state.players[1].hand.add(blue)
    state.players[1].action_points = 1
    state.players[1].resources = 0  # can't pay from existing resources alone

    apply_action(state, _weapon_attack_action(weapon))

    # Pitched card should leave hand
    assert blue not in state.players[1].hand.cards
    # Stack entry still created
    assert len(state.stack_entries) == 1


# ---------------------------------------------------------------------------
# Ally attack — StackEntry creation
# ---------------------------------------------------------------------------

def test_ally_attack_creates_activated_layer_stack_entry():
    """CR 11.0: ally attack creates an activated-layer StackEntry."""
    state = _make_state()
    ally = _make_ally()
    state.players[1].allies.add(ally)
    state.players[1].allies_exhausted.append(False)
    state.players[1].action_points = 1

    apply_action(state, _ally_attack_action(ally, choose_index=0))

    assert len(state.stack_entries) == 1
    entry = state.stack_entries[0]
    assert entry.layer_type == 'activated'
    assert entry.card is ally


def test_ally_attack_stack_entry_is_attack_true():
    """StackEntry.is_attack must be True for ally (checks subtypes=['Ally'])."""
    state = _make_state()
    ally = _make_ally()
    state.players[1].allies.add(ally)
    state.players[1].allies_exhausted.append(False)
    state.players[1].action_points = 1

    apply_action(state, _ally_attack_action(ally, choose_index=0))

    assert state.stack_entries[0].is_attack is True


def test_ally_attack_marks_correct_index_exhausted():
    """_pay_costs exhausts allies_exhausted[choose_index] for ally attack."""
    state = _make_state()
    ally0 = _make_ally(slug="ally_0")
    ally1 = _make_ally(slug="ally_1")
    state.players[1].allies.add(ally0)
    state.players[1].allies.add(ally1)
    state.players[1].allies_exhausted.extend([False, False])
    state.players[1].action_points = 1

    apply_action(state, _ally_attack_action(ally1, choose_index=1))

    assert state.players[1].allies_exhausted[0] is False  # untouched
    assert state.players[1].allies_exhausted[1] is True   # exhausted


def test_ally_attack_deducts_action_point():
    """_pay_costs deducts 1 AP for ally attack (CR 11.0)."""
    state = _make_state()
    ally = _make_ally()
    state.players[1].allies.add(ally)
    state.players[1].allies_exhausted.append(False)
    state.players[1].action_points = 3

    apply_action(state, _ally_attack_action(ally))

    assert state.players[1].action_points == 2


# ---------------------------------------------------------------------------
# Non-attack ACTIVATE_CARD — immediate effect, no StackEntry
# ---------------------------------------------------------------------------

def test_non_attack_activate_does_not_create_stack_entry():
    """is_attack_proxy=False: effect resolves immediately, no StackEntry created."""
    from engine.card_effects.dsl.loader import _CARDS, _compile_ability
    from engine.card_effects.dsl.schema import CardDef

    state = _make_state()
    item = _make_card("test_item", types=["Item"])
    item.activation_cost = 0
    item.has_once_per_turn_limit = False
    item.base_text_box = ""
    item.base_functional_text = ""
    item.owner = 1
    item.controller = 1

    # Inject a DSL definition whose ACTIVATE ability draws a card.
    filler = _make_card("deck_filler")
    filler.owner = 1
    state.players[1].deck.add(filler)
    _CARDS["test_item"] = CardDef(slug="test_item", abilities=[
        _compile_ability({"ability_type": "ACTIVATE",
                          "effects": [{"type": "DRAW", "amount": 1}]}),
    ])
    try:
        action = Action(
            type=ActionType.ACTIVATE_CARD,
            player_id=1,
            card=item,
            is_attack_proxy=False,
        )
        state.players[1].action_points = 1
        hand_before = len(state.players[1].hand.cards)
        apply_action(state, action)

        assert len(state.stack_entries) == 0
        assert len(state.players[1].hand.cards) == hand_before + 1
    finally:
        del _CARDS["test_item"]


# ---------------------------------------------------------------------------
# ActionType enum — ATTACK_WEAPON and ATTACK_ALLY are gone
# ---------------------------------------------------------------------------

def test_attack_weapon_not_in_action_type_enum():
    """ATTACK_WEAPON must be commented out — no longer a valid ActionType."""
    assert not hasattr(ActionType, 'ATTACK_WEAPON'), (
        "ActionType.ATTACK_WEAPON should be commented out; "
        "weapon attacks use ACTIVATE_CARD with is_attack_proxy=True"
    )


def test_attack_ally_not_in_action_type_enum():
    """ATTACK_ALLY must be commented out — no longer a valid ActionType."""
    assert not hasattr(ActionType, 'ATTACK_ALLY'), (
        "ActionType.ATTACK_ALLY should be commented out; "
        "ally attacks use ACTIVATE_CARD with is_attack_proxy=True"
    )


# ---------------------------------------------------------------------------
# _ally_attack_resource_cost helper
# ---------------------------------------------------------------------------

def test_ally_attack_resource_cost_from_card_cost():
    """Falls back to card.cost when set."""
    ally = _make_ally(resource_cost=2)
    assert _ally_attack_resource_cost(ally) == 2


def test_ally_attack_resource_cost_zero_when_no_cost():
    """Returns 0 for allies with no cost and no matching text pattern."""
    ally = _make_ally(resource_cost=0)
    ally.cost = None
    ally.functional_text = "**Action** — **Attack**"
    assert _ally_attack_resource_cost(ally) == 0
