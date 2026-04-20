"""Tests for Landmark card rules (CR 8.2.9).

CR 8.2.9a: When a landmark resolves as a layer on the stack, it enters the arena.
CR 8.2.9b: When a landmark enters the arena, all other landmark permanents are cleared
           (moved to owner's graveyard).
"""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.conftest import _make_state, _make_card, _make_player
from engine.state import StackEntry, SubZoneView
from engine.engine import resolve_stack


def _make_landmark(slug="test_landmark", name="Test Landmark"):
    card = _make_card(slug=slug, name=name, types=["Landmark"])
    card.base_text_box = ""
    card.base_functional_text = ""
    return card


def _push_card_entry(state, card, player_id=1):
    """Push a card-layer StackEntry and add it to the stack zone."""
    state.stack.add(card, is_public=True)
    entry = StackEntry(player_id=player_id, card=card, layer_type='card')
    state.stack_entries.append(entry)


# ---------------------------------------------------------------------------
# CR 8.2.9a — Landmark enters permanents on resolution
# ---------------------------------------------------------------------------

def test_landmark_enters_permanents():
    """Landmark resolves from stack → in player.permanents and player.landmarks."""
    state = _make_state()
    lm = _make_landmark()
    _push_card_entry(state, lm, player_id=1)

    resolve_stack(state)

    assert lm in state.players[1].permanents.cards
    assert lm in state.players[1].landmarks.cards


def test_landmark_not_in_graveyard_after_entering():
    """New landmark must NOT be moved to graveyard after entering (it stays)."""
    state = _make_state()
    lm = _make_landmark()
    _push_card_entry(state, lm, player_id=1)

    resolve_stack(state)

    assert lm not in state.players[1].graveyard.cards


def test_landmark_subzone_view_filters_by_subtype():
    """player.landmarks is a SubZoneView that only returns Landmark-subtype cards."""
    state = _make_state()
    player = state.players[1]

    lm = _make_landmark("lm1")
    non_lm = _make_card("non_lm", types=["Item"])
    player.landmarks.add(lm, is_public=True)
    player.items.add(non_lm, is_public=True)

    assert lm in player.landmarks.cards
    assert non_lm not in player.landmarks.cards


# ---------------------------------------------------------------------------
# CR 8.2.9b — Entering landmark clears all other landmark permanents
# ---------------------------------------------------------------------------

def test_landmark_clears_other_landmarks_same_player():
    """Player has landmark A in permanents; plays landmark B → A is cleared to graveyard."""
    state = _make_state()
    player = state.players[1]

    lm_a = _make_landmark("landmark_a")
    player.landmarks.add(lm_a, is_public=True)

    lm_b = _make_landmark("landmark_b")
    _push_card_entry(state, lm_b, player_id=1)

    resolve_stack(state)

    assert lm_b in player.permanents.cards        # new landmark stays
    assert lm_a not in player.permanents.cards    # old landmark cleared
    assert lm_a in player.graveyard.cards         # moved to graveyard


def test_landmark_clears_opponent_landmarks():
    """Opponent has a landmark; active player plays one → opponent's landmark cleared (CR 8.2.9b)."""
    state = _make_state()
    opp = state.players[2]

    opp_lm = _make_landmark("opp_landmark")
    opp.landmarks.add(opp_lm, is_public=True)

    new_lm = _make_landmark("new_landmark")
    _push_card_entry(state, new_lm, player_id=1)

    resolve_stack(state)

    assert new_lm in state.players[1].permanents.cards   # new stays
    assert opp_lm not in opp.permanents.cards             # opponent's cleared
    assert opp_lm in opp.graveyard.cards


def test_landmark_does_not_clear_itself():
    """The newly-entering landmark is NOT removed — only OTHER landmarks are cleared."""
    state = _make_state()
    lm = _make_landmark()
    _push_card_entry(state, lm, player_id=1)

    resolve_stack(state)

    assert lm in state.players[1].permanents.cards
    assert lm not in state.players[1].graveyard.cards


def test_no_landmark_field_on_gamestate():
    """GameState should no longer carry a `landmarks` list field (it was a data stub)."""
    state = _make_state()
    # The old field was list[tuple[int, str]]; it should be gone.
    # Player.landmarks is a SubZoneView — that's fine, but GameState.landmarks must not exist.
    assert not isinstance(getattr(state, 'landmarks', None), list), (
        "GameState.landmarks list field was not removed"
    )
