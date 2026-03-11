"""Regression tests for LKI around card visibility transitions."""

from engine.card import CardDB
from engine.card_effects.keywords import effect_banish, watery_grave
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


def test_same_zone_hide_preserves_public_lki():
    state = _create_test_state()
    card = CardDB().get("command_and_conquer")
    card.owner = 1
    card.controller = 1
    card.zone = "arms"
    state.players[1].graveyard.add(card)

    watery_grave(card, None, state)

    snapshot = state.get_last_known(card)
    assert snapshot is not None
    assert snapshot["zone"] == "graveyard"
    assert snapshot["is_public"] is True
    assert card.zone == "graveyard"
    assert card.is_public is False


def test_face_down_banish_keeps_private_source_snapshot():
    state = _create_test_state()
    card = CardDB().get("command_and_conquer")
    card.owner = 2
    card.controller = 2
    state.players[2].hand.add(card)

    effect_banish(state, card, face_up=False, banisher_id=1)

    snapshot = state.get_last_known(card)
    assert snapshot is not None
    assert snapshot["zone"] == "hand"
    assert snapshot["is_public"] is False
    assert card.zone == "banished"
    assert card.is_public is False


def test_public_to_private_zone_move_preserves_public_source_snapshot():
    state = _create_test_state()
    card = CardDB().get("command_and_conquer")
    card.owner = 1
    card.controller = 1
    state.players[1].graveyard.add(card)

    state.players[1].graveyard.remove(card)
    state.players[1].arsenal.add(card, is_public=False)

    snapshot = state.get_last_known(card)
    assert snapshot is not None
    assert snapshot["zone"] == "graveyard"
    assert snapshot["is_public"] is True
    assert card.zone == "arsenal"
    assert card.is_public is False