#===========================================================================
#     Card specific alternate costs with effect-cost components
#     (CR 5.1.9)
#===========================================================================
# ---------------------------------------------------------------------------
# Effect-costs (CR 5.1.8–5.1.9)
# ---------------------------------------------------------------------------

# EFFECT_COSTS: slug -> fn(state, player_id, action) -> bool
# Returns True if cost successfully paid (or waived), False if unresolvable.
# Called in apply_action BEFORE _apply_play_card puts the card on the stack.

from engine.state import GameState

ALTERNATE_COSTS: dict = {}

def _10000_year_reunion_alt_cost(state: GameState, player_id: int, action,
                                    check: bool = False) -> bool:
    """10,000 Year Reunion alt cost: remove 3 +1_power counters from controlled auras.

    Only fires when alternative_cost_used == "remove_p_counters".
    Normal 8{r} payment path returns True immediately (no effect-cost).
    check=True: verify ≥3 counters exist without removing them.
    check=False: agent chooses one aura per counter to remove (one at a time, 3 total).
    """
    # Only fire if alt cost is used for this card
    alt_cost = getattr(action, 'alternative_cost_used', None)
    if not (isinstance(alt_cost, dict) and alt_cost.get(action.card.slug, 0) <= 0):
        return False  # Normal cost path — no effect-cost applies

    player = state.players[player_id]
    total = sum(c.counters.get("+1_power", 0) for c in player.auras.cards)
    if total < 3:
        return False
    if not check:
        from engine.card_effects.ability_keywords import _ask_player
        remaining = 3
        while remaining > 0:
            eligible = [
                c for c in player.auras.cards
                if c.counters.get("+1_power", 0) > 0
            ]
            if not eligible:
                break
            pick = _ask_player(
                state, player_id, [c.slug for c in eligible],
                context=f"10,000 Year Reunion: choose an aura to remove a +1_power counter from ({remaining} remaining)",
            )
            chosen = next((c for c in eligible if c.slug == str(pick)), eligible[0])
            key = "+1_power"
            chosen.counters[key] = max(chosen.counters.get(key, 0) - 1, 0)
            remaining -= 1
    return True


ALTERNATE_COSTS["10000_year_reunion_red"] = _10000_year_reunion_alt_cost
