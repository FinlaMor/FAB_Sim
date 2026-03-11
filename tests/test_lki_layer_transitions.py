"""Regression tests for LKI when stack layers cease to exist."""

from engine.actions import Action, ActionType
from engine.card import CardDB
from engine.card_effects.keywords import effect_negate
from engine.engine import _apply_play_card, resolve_stack
from engine.state import GameState, Player, Step


def _create_test_state():
    p1 = Player(1, CardDB().get("bravo_showstopper"))
    p2 = Player(2, CardDB().get("kayo_armed_and_dangerous"))
    return GameState(
        players={1: p1, 2: p2},
        active_player=1,
        player_agents={},
        step=Step.ACTION,
        turn_number=1,
        combat=None,
        done=False,
        winner=None,
    )


def _play_card_to_stack(state, card):
    action = Action(type=ActionType.PLAY_CARD, player_id=1, card=card)
    _apply_play_card(state, action)
    return state.stack_entries[-1]


def test_play_card_marks_card_in_stack_zone():
    state = _create_test_state()
    card = CardDB().get("pummel")
    card.owner = 1
    card.controller = 1
    state.players[1].hand.add(card)

    _play_card_to_stack(state, card)

    assert card.zone == "stack"


def test_play_instant_marks_card_in_stack_zone():
    state = _create_test_state()
    card = CardDB().get("a_drop_in_the_ocean_blue")
    card.owner = 1
    card.controller = 1
    state.players[1].hand.add(card)

    _play_card_to_stack(state, card)

    assert card.zone == "stack"


def test_resolve_card_layer_captures_stack_lki():
    state = _create_test_state()
    card = CardDB().get("pummel")
    card.owner = 1
    card.controller = 1
    state.players[1].hand.add(card)

    _play_card_to_stack(state, card)
    resolve_stack(state)

    snapshot = state.get_last_known(card)
    assert snapshot is not None
    assert snapshot["zone"] == "stack"


def test_negate_card_layer_captures_stack_lki_before_graveyard_move():
    state = _create_test_state()
    card = CardDB().get("pummel")
    card.owner = 1
    card.controller = 1
    state.players[1].hand.add(card)

    entry = _play_card_to_stack(state, card)
    effect_negate(state, entry)

    snapshot = state.get_last_known(card)
    assert snapshot is not None
    assert snapshot["zone"] == "stack"
    assert card in state.players[1].graveyard.cards
    assert card.zone == "graveyard"
