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
    from engine.card_effects.ability_keywords import _ask_player
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
        from engine.card_effects.ability_keywords import banish_card
        player.graveyard.remove(target)
        banish_card(state, player, target, face_up=True)
    return True
KEYWORD_COSTS['scrap'] = _scrap_effect_cost

def _beat_chest_effect_cost(state: GameState, player_id: int, action, check: bool = True) -> bool:
    """Beat Chest (CR 8.3.33): optional additional cost — discard a card with 6+ power from hand."""
    from engine.card_effects.ability_keywords import _ask_player
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
