"""Programs for card playability and available actions"""

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


def available_actions(state, player_id):

    recalculate_playable(state, player_id)
    recalculate_activatable(state, player_id)

    playable_cards = [c for c in player.all_cards if c.playable]
    activatable_cards = [c for c in player.all_cards if c.activatable]


    return actions