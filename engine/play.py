"""Programs for card playability and available actions"""

from engine.actions import ALTERNATE_COSTS, Action, ActionType
from engine.card import Card
from engine.state import GameState, Player

def available_actions(state, player_id) -> list[Action]:
    """ Finds all legal card activations/plays, builds an action list from those cards,
    then returns the list of the affordable and legal actions.
    Always returns at least PASS"""

    # First find all cards that are theoretically possible to be play/activated
    # Check for continuous effects that affect playability like gravy's watery grave check or bounding demigon's NAA requirement
    recalculate_playable(state, player_id)
    recalculate_activatable(state, player_id)

    player = state.players[player_id]
    playable_cards = [c for c in player.all_cards if c.playable]
    activatable_cards = [c for c in player.all_cards if c.activatable]

    # 2nd, filter down based on keyword type requirements
    legal_playable_cards = []
    legal_activatable_cards = []
    for card in playable_cards:
        if _legality_check(state, card, player_id):
            legal_playable_cards.append(card)
    for card in activatable_cards:
        if _legality_check(state, card, player_id):
            legal_activatable_cards.append(card)

    # 3rd, filter down based on what cards are actually affordable, and playable/activatable based on card specific conditions

    affordable_actions = []
    for card in legal_playable_cards:
        action = Action(ActionType.PLAY_CARD, player_id, card, from_arsenal=True if card.zone == 'arsenal' else None)
        can_play, action = _cost_check(state, card, player_id, action, playable=True)
        if can_play:
            affordable_actions.append(action)
    for card in activatable_cards:
        can_activate, action = _cost_check(state, card, player_id, action, playable=False):
        if can_activate:
            affordable_actions.append(action)
    
    affordable_actions.append(Action(ActionType.PASS)) #can always choose to pass

    return affordable_actions

def _legality_check(state, card, player_id) -> bool:
        
    legal_flag = True

    if 'action' in card.base_text_box or 'action' in card.base_functional_text:
        legal_flag &= _action_legal_check(state, card, player_id)
    if 'attack_reaction' in card.base_text_box or 'attack_reaction' in card.base_functional_text:
        legal_flag &= _attack_reaction_legal_check(state, card, player_id)
    if 'defense_reaction' in card.base_text_box or 'defense_reaction' in card.base_functional_text:
        legal_flag &= _defense_reaction_legal_check(state, card, player_id)
    if 'instant' in card.base_text_box or 'instant' in card.base_functional_text:
        legal_flag &= _instant_legal_check(state, card, player_id)

    return legal_flag

def _cost_check(state, card, player_id, action, playable) -> tuple[bool, Action]:
    """ Check if player can afford to play/activate a card based on the asset-costs per 
    CR 5.1.6. Returns True if affordable, False if not. 
    """
    # Turn card into action
    player = state.players[player_id]
    can_afford = True

    try:
        from engine.engine import _calculate_resource_cost
        resource_cost = _calculate_resource_cost(state, action)
    except ImportError:
        # Fallback to raw card cost if engine not importable (e.g. during early init)
        resource_cost = card.cost if playable else card.activation_cost

    exclude = card if card is not None else None
    
    effective_resources = player.resources

    x_in_cost = 'X' in str(resource_cost) or 'x' in str(resource_cost)
    if x_in_cost:
        cost_with_x = resource_cost
        base_cost = int(str(resource_cost).strip(r'Xx\s')) #ie '3X' cost on imposing visage means 'pay at least 3
        if base_cost > 0:
            resource_cost = base_cost

    # --- 1. Resource cost ---
    if not can_pay_resource_cost(player.hand.cards, resource_cost, effective_resources, exclude_card=exclude):
            
            # Alternative-cost effect-cost checks (CR 5.1.3c / 5.1.8)
            # Check alternate costs if resource cost can't be paid.
            if getattr(card, 'alternate_costs', None) is not None:
                 if ALTERNATE_COSTS.get(card.slug) is not None:
                    cost_fn = ALTERNATE_COSTS.get(card.slug)
                    if cost_fn and cost_fn(state, action, check=True):
                        can_afford &= True  
                        setattr(action, 'alternate_cost', True)
                        setattr(action, 'resource_cost', 0)
                    else:
                        can_afford &= False
            else:
                can_afford &= False
    else:
        can_afford &= True
        setattr(action, 'resource_cost', cost_with_x if x_in_cost else resource_cost)
    

    # --- 2. Life cost ---
    if hasattr(card, 'life_cost')and (card.life_cost or 0) > 0 and player.hero is not None:
        life_cost = card.life_cost
        setattr(action, 'life_cost', life_cost)
        if life_cost > 0 and player.health <= life_cost:
            can_afford &= False
        else:
            can_afford &= True

    # --- 3. effect-costs ---
    if getattr(card, 'mandatory_additional_costs', None) is not None:
        if card is not None:
            from engine.card_effects.additional_costs import ADDITIONAL_COSTS
            if card in ADDITIONAL_COSTS.keys():
                cost_func = ADDITIONAL_COSTS[card.slug]
                can_afford &= cost_func(state, player_id, check=True)
                setattr(action, 'additional_costs', True)

    # --- 4. additional conditions ---
    if playable:
        add_cond = getattr(card, 'play_conditions', None) is not None
    else:
        add_cond = getattr(card, 'activation_conditions', None) is not None
    
    if add_cond:
        from engine.card_effects.additional_conditions import ADDITIONAL_CONDITIONS
        cond_func = ADDITIONAL_CONDITIONS[card.slug]
        can_afford &= cond_func(state, player_id, check=True)
        setattr(action, 'additional_conditions', True)
    
    return can_afford, action

def can_pay_resource_cost(hand_cards: list[Card], target_cost: int, current_resources: int = 0, exclude_card: Card | None = None) -> bool:
    """Return True if total pitchable value in hand can cover the cost.

    This is the fast-path check used during legal-action enumeration.  The actual
    pitch cards are chosen later at apply-time via sequential binary decisions.
    """
    if target_cost is None or target_cost <= 0:
        return True
    needed = target_cost - current_resources
    if needed <= 0:
        return True
    total_pitch = sum(
        (c.pitch or 0)
        for c in hand_cards
        if c is not exclude_card and c.pitch is not None and c.pitch > 0
    )
    return total_pitch >= needed

def recalculate_playable(state, player_id):
    player = state.players[player_id]
    mgr = state.continuous_effect_manager

    for card in player.hand.cards + player.arsenal.cards:
        if card.base_playable:
            card.playable = True

    for card in player.all_cards:
        if card not in player.hand.cards + player.arsenal.cards:
            card.playable = False
        mgr.recalculate(state, card, 'playable', card.playable)
    state.event_manager.emit('recalculate_playable', state)

def recalculate_activatable(state, player_id):
    player = state.players[player_id]
    mgr = state.continuous_effect_manager

    for card in player.arena.cards:
        card.activatable = card.base_activatable

    for card in player.all_cards:
        if card not in player.arena.cards:
            card.activatable = False
        mgr.recalculate(state, card, 'activatable', card.activatable)
    state.event_manager.emit('recalculate_activatable', state)

def _action_legal_check(state, card, player_id) -> bool:
    # CR 8.1.1: Requirements for playing/activating a card with the "action" keyword
    # 8.1.1a: Stack must be empty
    can_play_or_activate = True
    if len(state.stack.slugs) > 0:
        can_play_or_activate = False
    
    # 8.1.1b: Actions can't be played/activated during combat except during resolution phase
    if 'combat' in state.step:
        if not state.step.endswith('resolution'):
            can_play_or_activate = False
        # 7.6.3a: During resolution, the attacking hero may play/activate an attack action
        if 'attack' in card.base_text_box or 'attack' in card.base_functional_text:
            if player_id != state.combat.attacker_id:
                can_play_or_activate = False
    
    # 8.1.1c: Actions have an additional asset cost of one action-point
    if state.players[player_id].action_points < 1:
        can_play_or_activate = False
    
    # 8.1.1d: Actions that can be 'played as an instant' only require priority.
    if 'play_as_instant' not in state.effect_manager.continuous_effects:
        can_play_or_activate = False

    return can_play_or_activate

def _attack_reaction_legal_check(state, card, player_id) -> bool:
    # CR 8.1.2: Requirements for playing/activating a card with the "attack reaction" keyword
    can_play_or_activate = True
    # 8.1.2a An attack reaction card/activated ability can only be played/activated by a player who controls the attack during the Reaction Step of combat
    if not hasattr(state, 'combat') or state.combat is None:
        can_play_or_activate = False
    if state.step != 'combat_reaction':
        can_play_or_activate = False
    if player_id != state.combat.attacker_id:
        can_play_or_activate = False
    
    # 8.1.2b: When an attack reaction card resolves as a layer on the stack, it is cleared.

    # 8.1.2c: An attack reaction card/activated ability is considered to be a reaction card/ability.

    return can_play_or_activate

def _defense_reaction_legal_check(state, card, player_id) -> bool:
    # CR 8.1.3: Requirements for playing/activating a card with the "defense reaction" keyword
    can_play_or_activate = True

    # 8.1.3a A defense reaction card/activated ability can only be played/activated by a player who controls a hero as an attack-target during the Reaction Step of combat.
    if not hasattr(state, 'combat') or state.combat is None:
        can_play_or_activate = False
    if state.step != 'combat_reaction':
        can_play_or_activate = False
    if state.players[player_id].hero.slug != state.combat.attack_target.slug:
        can_play_or_activate = False
    
    # 8.1.3b When a defense reaction card resolves as a layer on the stack, it becomes a defending card on the active chain link.
    # 8.1.3c A defense reaction card/activated ability is considered to be a reaction card/ability.

    return can_play_or_activate

def _instant_legal_check(state, card, player_id) -> bool:
    # CR 8.1.6: Requirements for playing/activating a card with the "instant" keyword
    can_play_or_activate = True

    # 8.1.6a A card/activated ability with the type instant can be played/activated any time the player has priority.
    if state.priority_player_id != player_id:
        can_play_or_activate = False

    return can_play_or_activate