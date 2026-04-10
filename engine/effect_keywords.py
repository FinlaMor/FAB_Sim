"""Centralized effect keyword functions (CR 8.5).

Each function here represents a named effect keyword from CR 8.5. All game
actions that involve these keywords should route through these functions so
that replacement effects (effect_manager) and triggers (event_manager) fire
consistently from a single callsite.

Functions accept `state: GameState` and any required targets/values.
Replacement effects are applied via `state.effect_manager.apply_replacements`
before execution. Triggers are emitted via `state.event_manager.emit` after.

CR 8.5 Effect Keywords implemented here:
    banish          (8.5.1)  — move object to banished zone
    create_token    (8.5.2)  — create a token and place it in the arena
    deal_damage     (8.5.3)  — deal generic, physical, or arcane damage
    destroy         (8.5.4)  — move object to graveyard
    discard         (8.5.5)  — move card from hand to graveyard
    draw            (8.5.6)  — move top card of deck to hand
    gain            (8.5.7)  — increase a living object's {h} or grant action points
    lose            (8.5.12) — decrease a living object's {h}
    put_counter     (8.5.14) — place a counter on an object
    remove_counter  (8.5.16) — remove a counter from an object
    search          (8.5.19) — search a zone for a card matching criteria
    shuffle         (8.5.20) — randomise a zone
    opt             (8.5.22) — look at top N cards, return in any order
    charge          (8.5.29) — put a card into a hero's soul
    equip           (8.5.41) — equip an object to the appropriate zone
    pitch           (8.5.44) — pitch a card for its resource value

Not implemented (no current card requires simulator support):
    look (8.5.11), reveal (8.5.17), roll (8.5.18), name (8.5.21),
    reload (8.5.23), turn (8.5.24), become/copy (8.5.25), negate (8.5.26),
    repeat (8.5.27), reroll (8.5.28), distribute (8.5.30), pay (8.5.31),
    add_defend (8.5.32), ignore (8.5.33), freeze (8.5.34), gain_control (8.5.35),
    transform (8.5.36), unfreeze (8.5.37), attack (8.5.38), contract (8.5.39),
    create_card (8.5.40), move_counter (8.5.42), awaken (8.5.43), clash (8.5.45),
    wager (8.5.46), amp (8.5.47), transcend (8.5.48), exchange (8.5.49),
    mark (8.5.50), retrieve (8.5.51), give (8.5.53), steal (8.5.54),
    tap (8.5.55), untap (8.5.56), crowd_cheer/boo (8.5.57)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.state import GameState
    from engine.card import Card
