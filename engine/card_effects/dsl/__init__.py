"""Public API for the card effects DSL."""
from __future__ import annotations

from engine.card_effects.dsl.loader import load_all_cards, get_card, all_slugs
from engine.card_effects.dsl.interpreter import dispatch_event
from engine.card_effects.dsl.schema import CardDef, AbilityDef, EffectDef, ConditionDef, CostDef


def dispatch(state, event_type: str, slug: str, card=None, event=None, **ctx) -> None:
    """
    Fire all DSL-defined abilities for *slug* that match *event_type*.

    Parameters
    ----------
    state      : GameState
    event_type : Engine event name (e.g. "ON_HIT", "ON_PLAY")
    slug       : Card slug
    card       : Card object (if None, uses state.combat.attack_card or creates a stub)
    event      : Event payload dict (may be None)
    **ctx      : Additional context (reserved for future use)
    """
    card_def = get_card(slug)
    if card_def is None:
        return

    if card is None and state.combat:
        card = state.combat.attack_card

    if card is None:
        from engine.card import Card as _Card
        card = _Card(slug=slug, name=slug)
        card.owner = state.active_player
        card.controller = state.active_player

    from engine.context import effect_context
    with effect_context():
        dispatch_event(card_def, event_type, card, event, state)


__all__ = [
    "dispatch",
    "load_all_cards",
    "get_card",
    "all_slugs",
    "CardDef",
    "AbilityDef",
    "EffectDef",
    "ConditionDef",
    "CostDef",
]
