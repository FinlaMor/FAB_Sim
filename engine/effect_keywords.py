"""Centralized effect keyword functions (CR 8.5).

Each function here represents a named effect keyword from CR 8.5. All game
actions that involve these keywords should route through these functions so
that replacement effects (effect_manager) and triggers (event_manager) fire
consistently from a single callsite.

Functions accept `state: GameState` and any required targets/values.
Replacement effects are applied via `state.effect_manager.apply_replacements`
before execution. Triggers are emitted via `state.event_manager.emit` after.

CR 8.5 Effect Keywords implemented here

Event object expected attributes per apply_replacements:
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from engine.state import GameState
    from engine.effects import EffectManager
    from engine.card import Card

# in effect_keywords.py

@dataclass
class BanishEvent:
    """CR 8.5.1 — move an object to the banished zone.
    
    Replacement effects can modify:
        destination  — e.g. redirect to graveyard instead (card still considered banished, CR 8.5.1b)
        cancelled    — prevent the banish entirely
    """
    type: str = "banish"
    card: Card = None
    source_player_id: int = None      # who is causing the banishing
    target_player_id: int = None      # who owns the card being banished
    origin_zone: str = None           # where the card came from ("hand", "deck", etc.)
    destination: str = "banished"     # replacement effects can change this
    until_condition: str = None       # e.g. "end_of_turn" for temporary banish (CR 8.5.1c)
    cancelled: bool = False


def banish(state: GameState, card: Card, source_player_id: int,
           origin_zone: str, until_condition: str = None) -> BanishEvent:
    """CR 8.5.1 — banish a card.
    
    Returns the event so callers can inspect what actually happened
    (e.g. was it redirected? cancelled?).
    """
    target_player_id = card.owner

    event = BanishEvent(
        card=card,
        source_player_id=source_player_id,
        target_player_id=target_player_id,
        origin_zone=origin_zone,
        until_condition=until_condition,
    )

    # replacement effects fire before the move (CR 6.5)
    state.effect_manager.apply_replacements(event, state)

    if event.cancelled:
        return event

    # execute the move
    player = state.players[event.target_player_id]
    getattr(player, event.origin_zone).remove(card)
    getattr(player, event.destination).add(card)

    # trigger: "when a card is banished" listeners fire after (CR 8.5.1)
    state.event_manager.emit(event, state)

    # CR 8.5.1c: register delayed return effect if temporary
    if event.until_condition:
        _register_return_from_banish(state, card, target_player_id, event.until_condition)

    return event
