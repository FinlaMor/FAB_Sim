"""Registry for play_card alternate costs"""
from engine.actions import GameState
#===========================================================================
#     Keyword costs
#===========================================================================
# KEYWORD_COSTS: slug -> fn(state, player_id, action, check: bool = True) -> bool
# If check=True, return True if cost is payable (or waived), False if unpayable.
# If check=False, resolve the cost (including any player prompts) and return True if successfully.
# Keyword costs are optional additional costs triggered by keywords on the card.
KEYWORD_COSTS: dict = {}

def _scrap_effect_cost(state: GameState, player_id: int, action, check: bool = True) -> bool:
    """Scrap (CR 8.3.32): optional additional cost — banish an item or equipment from graveyard."""
    from engine.card_effects.keywords import _ask_player
    player = state.players[player_id]
    eligible = [
        c for c in player.graveyard.cards
        if any(t in (c.types or []) for t in ("Item", "Equipment"))
    ]
    if check:
        return True if eligible else False  # optional — nothing to banish, cost waived
    
    choice = True if not check and action.additional_costs and action.additional_costs.get('scrap') else False
    if not choice:
        return False  # player declined — cost is optional
    pick = _ask_player(state, player_id, [c.slug for c in eligible],
                       context="Choose item or equipment to banish for Scrap")
    target = player.graveyard.find(str(pick)) if pick is not None else None
    if target:
        from engine.card_effects.keywords import banish_card
        player.graveyard.remove(target)
        banish_card(state, player, target, face_up=True)
    return True
KEYWORD_COSTS['scrap'] = _scrap_effect_cost

def _beat_chest_effect_cost(state: GameState, player_id: int, action, check: bool = True) -> bool:
    """Beat Chest (CR 8.3.33): optional additional cost — discard a card with 6+ power from hand."""
    from engine.card_effects.keywords import _ask_player
    player = state.players[player_id]
    card = action.card
    eligible = [
        c for c in player.hand.cards
        if (c.power or 0) >= 6 and c.slug != (card.slug if card else None)
    ]
    if check and not eligible:
        return False  # optional — nothing eligible, cost waived
    choice = _ask_player(state, player_id, [True, False],
                         context="Beat Chest: discard a card with 6+ power as additional cost?")
    if not choice:
        return True  # player declined — cost is optional
    pick = _ask_player(state, player_id, [c.slug for c in eligible],
                       context="Choose a card with 6+ power to discard for Beat Chest")
    target = player.hand.find(str(pick)) if pick is not None else None
    if target:
        player.hand.remove(target)
        player.graveyard.add(target)
    action.additional_costs['beat_chest'] = True
    return True
KEYWORD_COSTS['beat_chest'] = _beat_chest_effect_cost
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
        from engine.card_effects.keywords import _ask_player
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
