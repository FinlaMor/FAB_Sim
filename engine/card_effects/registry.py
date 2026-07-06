"""Structural effect registries for the FAB engine.

Card-specific implementations have been removed: all card behavior is owned
by the JSON DSL under engine/card_effects/json/ and dispatched through
engine.card_effects.dsl. The registries below remain as engine hooks —
keyword-driven entries (CR section 8) may live here, but do NOT add
per-card Python effects; author a JSON card definition instead.

A card without a DSL definition is unimplemented and the engine will refuse
to run it (see engine.card_effects.dsl.loader.require_card).
"""

from engine.card import CardEffect  # noqa: F401 — re-exported for engine.py


# ---------------------------------------------------------------------------
# Static ability system
# ---------------------------------------------------------------------------
# Three registries work together through a single meta-dispatcher
# registered once at game start (_setup_static_ability_listeners in engine.py).
#
# STATIC_ABILITY_ZONES  — event_name -> fn(state) -> list[Card]
#   Defines which cards to inspect for each event type.  Adding a new event
#   here automatically wires it into the dispatcher.
#
# KEYWORD_STATIC_ABILITIES — keyword_prefix -> fn(n, state, card)
#   Generic keyword handlers that apply to any card carrying that keyword.
#   n is the numeric suffix (1 if absent).
#
# CARD_STATIC_ABILITIES — slug -> list[tuple[event_name, fn(event, state, card)]]
#   Per-card statics: empty — card statics are DSL WHILE_STATIC abilities.
# ---------------------------------------------------------------------------

def _all_arena_cards(state) -> list:
    """All permanents across both players' arenas (equipment, items, auras, allies, hero)."""
    cards = []
    for p in state.players.values():
        for zone in (p.head, p.chest, p.arms, p.legs,
                     p.weapon1, p.weapon2, p.permanents,
                     p.hero_zone, p.items, p.auras, p.allies):
            cards.extend(zone.cards)
    return cards


STATIC_ABILITY_ZONES: dict = {
    # Recalculating attack power — only the attacking card carries attack statics.
    'recalculate_attack_power': lambda state: (
        [state.combat.attack_card] if state.combat and state.combat.attack_card else []
    ),
    # Aura destroyed — any in-play permanent can react.
    'aura_destroyed': lambda state: _all_arena_cards(state),
}


def _piercing_static(n: int, state, card) -> None:
    """CR 8.3.23: Piercing — add n to attack power when blocking with equipment."""
    if any(getattr(c, 'is_equipment', False) for c in (state.combat.defending_cards or [])):
        state.combat.attack_power += n


KEYWORD_STATIC_ABILITIES: dict = {
    "piercing": _piercing_static,
}

CARD_STATIC_ABILITIES: dict = {}


# ---------------------------------------------------------------------------
# Legacy per-card registries — all empty. The engine still consults these
# hooks; card behavior must come from the DSL. Kept so the engine's lookup
# sites stay wired for keyword-driven entries if ever needed.
# ---------------------------------------------------------------------------

# Attack/defense reaction targeting conditions: slug -> fn(combat) -> bool
ATTACK_REACTION_CONDITIONS: dict = {}
DEFENSE_REACTION_CONDITIONS: dict = {}

# Equipment activation: legality conditions, cost overrides, pay-costs, effects
EQUIPMENT_ACTIVATION_CONDITIONS: dict = {}
EQUIPMENT_ACTIVATION_COST: dict = {}
EQUIPMENT_PAY_COSTS: dict = {}
EQUIPMENT_ACTIVATION_EFFECTS: dict = {}

# Hero abilities and passive triggers
HERO_ACTIVATION_CONDITIONS: dict = {}
HERO_TRIGGERS: dict = {}

# Misc per-card hooks
DISCARD_ACTIVATE_EFFECTS: dict = {}
PLAY_TARGET_CONDITIONS: dict = {}
WEAPON_ATTACK_CONDITIONS: dict = {}

# "Next attack this turn" effect templates keyed by current_turn_effects strings.
# DSL cards queue attack mods via player.dsl_queued_attack_mods instead.
TURN_ATTACK_EFFECTS: dict = {}
