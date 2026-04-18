"""
Program for 
1. Finding card playability and available actions
2. Applying actions to a Gamestate object
"""

import re
from typing import Optional

from engine.actions import Action, ActionType
from engine.card_effects.additional_conditions import ADDITIONAL_CONDITIONS
from engine.card_effects.additional_costs import ADDITIONAL_COSTS
from engine.card_effects.effect_cost import ALTERNATE_COSTS, KEYWORD_COSTS
from engine.card import Card
from engine.state import GameState, Player, Event, StackEntry

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
        can_activate, action = _cost_check(state, card, player_id, action, playable=False)
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
    """Unified cost gate for playing a card or activating an ability.

        Implements the full CR 5.1 cost sequence in one place so that the
        legality check (_legality_check) and the payment (_apply_action) always
        use identical logic.

        check=True  (CR 5.1.5 / 5.1.8a):
            Verify ALL costs are payable without changing any game state.
            Returns True if the action is affordable, False if it should be
            excluded from the legal-action list.

        check=False (CR 5.1.7 / 5.1.9):
            Deduct ALL costs from the game state.  Returns True unconditionally
            (caller is responsible for having called check=True first).

        Cost sequence per CR 5.1.6 / 1.14.2:
        1. Resource asset-cost
            • Base = card.cost (CR 2.2.2)
            • Alternative cost declared → base set to 0 (CR 5.1.6c)
            • Continuous-effect modifiers applied (CR 5.1.6a): set → increase → decrease, floor 0
            • Chi drains into resources before spending (CR 1.14.2d)
            • Pitch cards from hand to cover shortfall (CR 1.14.2d / 5.1.7)
        2. Action-point asset-cost
            • 0 for Instant-speed; 1 for action-speed (CR 5.1.6b)
            • Continuous-effect modifiers applied (CR 5.1.6a)
        3. Life asset-cost  (CR 1.14.2e)
            • Hero activations may carry a life cost registered in HERO_ACTIVATION_CONDITIONS
        4. Effect-costs  (CR 5.1.8–5.1.9)
            • Slug-registered in EFFECT_COSTS; keyword-driven (Scrap, Beat Chest)
            • check=True evaluates payability without paying
            • check=False pays them (irreversible side-effects happen here)
        """    # Turn card into action
    player = state.players[player_id]
    can_afford = True

    resource_cost = _calculate_resource_cost(state, action)

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

    for card in player.arena_cards:
        card.activatable = card.base_activatable

    for card in player.all_cards:
        if card not in player.arena_cards:
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

# Apply chosen actions to a Gamestate

def apply_action(state: GameState, action: Action) -> None:
    """Apply a player action to the game state."""
    # Sequential pitch: ask model which cards to pitch before dispatching
    _no_pitch_types = (ActionType.PASS, ActionType.DEFEND_CARDS,
                       ActionType.STORE_ARSENAL, ActionType.CHOOSE)
    if action.type not in _no_pitch_types:
        # CR 5.1.5: Verify legality BEFORE any cost payment (declare → check → pay).
        if not _legality_check(state, action.card, action.player_id):
            return
        # CR 5.1.6–5.1.9: Pay all costs (resource, chi, pitch, life, effect-costs).
        if not _pay_costs(state, action.player_id, action):
            return

    if action.type == ActionType.PLAY_CARD:
        _apply_play_card(state, action)
    elif action.type == ActionType.ACTIVATE_CARD:
        _apply_activate(state, action)
    elif action.type == ActionType.DEFEND_CARDS:
        _apply_defend(state, action)
    elif action.type == ActionType.CHOOSE:
        pass  # Choice is conveyed by selection of this Action object; no state mutation needed


def _apply_play_card(state: GameState, action: Action) -> None:
    """Play a card from hand: pitch for cost, place on stack."""
    player = state.players[action.player_id]
    card = action.card
    declared_modes, declared_targets, declared_x = _stack_declarations_from_action(action)

    # Meld-side-aware resource deduction.
    # Pitch sequences were already generated for the correct effective cost per side.
    _meld_side = getattr(action, 'meld_side', None)
    # Resource cost already deducted by evaluate_play_cost in apply_action.
    player.hand.remove(card)

    # Tag the card so on_play triggers know which side is resolving
    # (AP deduction is handled in _pay_costs — not here)
    card.meld_side = _meld_side

    # CR 3.0.1 / CR 5.3.4c: card enters stack zone (Zone.add keeps card.zone in sync)
    if card is not None:
        state.stack.add(card)

    # CR 5.1.2 / CR 3.15.4: card enters stack, on_play triggers sit above it (LIFO)
    entry = StackEntry(
        player_id=action.player_id,
        card=card,
        layer_type='card',
        layer_position=len(state.stack_entries) + 1,
        declared_modes=declared_modes,
        declared_targets=declared_targets,
        declared_x=declared_x,
    )
    if _meld_side == 'both':
        from engine.card_effects.triggers import MELD_EFFECT_REGISTRY
        _slug_base = re.sub(r'_(red|yellow|blue)$', '', card.slug)
        _meld_effs = MELD_EFFECT_REGISTRY.get(_slug_base, {})
        entry.meld_effect_bottom = _meld_effs.get('bottom')
        entry.meld_effect_top = _meld_effs.get('top')
    state.stack_entries.append(entry)
    player.cards_played_this_turn.append(card)
    state.event_manager.emit(Event(type='on_play', card=card.slug, data={'card': card, 'meld_side': _meld_side, 'target': action.target}), state)

def _apply_activate(state: GameState, action: Action) -> None:
    """Activate an equipment/item/weapon/ally/hero/card ability: pay cost, exhaust, apply effect.

    All costs (AP, resources, exhaustion) are paid by _pay_costs() before this function is called.
    This function handles only effects: once-per-turn tracking, additional cost side-effects, and
    dispatching to the effect registry.

    Attack activations (is_attack_proxy=True) create an activated-layer StackEntry so the engine's
    stack resolution loop (_combat_phase_iter → _attack_step) can handle combat.
    """
    from engine.card_effects.registry import EQUIPMENT_ACTIVATION_EFFECTS, EQUIPMENT_PAY_COSTS
    if action.player_id is None or action.card is None:
        return
    player = state.players[action.player_id]
    card = action.card

    # CR 1.6.2b / CR 11.0: weapon and ally attacks go onto the chain as activated-layer entries.
    # All costs already paid by _pay_costs(). Just create the StackEntry.
    if getattr(action, 'is_attack_proxy', False):
        declared_modes, declared_targets, declared_x = _stack_declarations_from_action(action)
        entry = StackEntry(
            player_id=action.player_id,
            card=card,
            layer_type='activated',
            layer_position=len(state.stack_entries) + 1,
            declared_modes=declared_modes,
            declared_targets=declared_targets,
            declared_x=declared_x,
            attack_source=action.attack_source if action.attack_source is not None else card,
        )
        state.stack_entries.append(entry)
        return

    # CR 4.4.3d: Mark exhausted for "once per turn" abilities.
    if card.has_once_per_turn_limit:
        card.activations -= 1
        assert card.activations >= 0

    # Pay additional costs (destroy, tap, etc. — everything before the colon in card text)
    pay_cost_fn = EQUIPMENT_PAY_COSTS.get(card.slug)
    if callable(pay_cost_fn):
        pay_cost_fn(action, player, state, check=False)

    # Dispatch to registry callback (effect after the colon)
    effect_fn = EQUIPMENT_ACTIVATION_EFFECTS.get(card.slug)
    if callable(effect_fn):
        effect_fn(action, player, state)

def _apply_defend(state: GameState, action: Action) -> None:
    """7.3.2: apply defend declaration — move chosen cards to defending_cards."""
    combat = state.combat
    if not combat:
        return
    if action.type == ActionType.PASS:
        return
    defender = state.players[3 - combat.attacker_id]
    for card in action.card_list:
        if card in defender.hand.cards:
            defender.hand.remove(card)
            # CR 8.3.4b: track that a hand card has been used to defend (Dominate/Reprise)
            combat.defender_used_hand_card = True
        combat.defending_cards.append(card)
        defense_val = card.defense or 0
        combat.total_defense += defense_val
        if card.is_equipment:
            combat.defending_equipment_defense += defense_val
        # 7.0.5a: defend event
        state.event_manager.emit(Event(type='defend', card=card.slug), state)

def _stack_declarations_from_action(action: Action) -> tuple[list[str], list[str], Optional[int]]:
    """Extract mode/target/X declarations for stack-layer metadata."""
    declared_modes = [str(mode) for mode in (action.modes_selected or [])]

    declared_targets: list[str] = []
    if action.targets:
        declared_targets.extend([str(t) for t in action.targets if t is not None])
    if action.target is not None and not action.targets:
        if hasattr(action.target, 'slug'):
            declared_targets.append(action.target.slug)
        else:
            declared_targets.append(str(action.target))

    declared_x = action.x_value_declared
    return declared_modes, declared_targets, declared_x

def _calculate_resource_cost(state: GameState, action: Action) -> int:
    """CR 5.1.6: Calculate final resource cost after all modifiers.

    Order per CR 5.1.6a:
    1. Base cost (from card/ability definition)
    2. CR 5.1.6c: alternative cost replaces base resource cost with 0
    3. SET effects applied in timestamp order      (substage 2)
    4. INCREASE effects applied in timestamp order (substage 5)
    5. DECREASE effects applied in timestamp order (substage 6)
    Floored at 0.

    Delegates to ContinuousEffectManager.recalculate() with prop='cost'
    and action= context so condition_fn(card, action, state) works correctly.
    """
    card = action.card

    # CR 5.1.3c: at most one alternative cost may be declared per play — enforced by
    # the Optional[str] field (single value only).  Validate no list was smuggled in.
    alt = getattr(action, 'alternative_cost_declared', None)
    assert not isinstance(alt, (list, tuple)), \
        f"CR 5.1.3c: only one alternative cost allowed per action; got {alt!r}"

    # CR 5.1.6c: alternative cost sets base resource cost to 0
    if alt:
        base_cost = 0
    else:
        base_cost = _get_base_resource_cost(state, action)

    mgr = state.continuous_effect_manager
    cost = mgr.recalculate(state, card, 'cost', base_cost, action=action)
    return max(0, cost)  # CR 5.1.6a: floor at 0

def _get_base_resource_cost(state: GameState, action: Action) -> int:
    """Compute the base resource cost for an action before any modifiers.

    Renamed from _get_action_resource_cost — call _calculate_resource_cost
    for the full CR 5.1.6a modifier pipeline.
    """
    card = action.card
    if action.type == ActionType.PLAY_CARD:
        ms = getattr(action, 'meld_side', None)
        if ms == 'bottom':
            return card.cost or 0
        elif ms == 'both':
            return card.meld_cost or 0
        else:
            return card.cost or 0
    elif action.type == ActionType.ACTIVATE_CARD:
        if getattr(action, 'is_attack_proxy', False) and card is not None:
            if card.is_weapon:
                from engine.actions import _weapon_cost
                return _weapon_cost(card)
            else:  # ally attack
                return _ally_attack_resource_cost(card)
        return (card.activation_cost or 0) if card else 0

    return 0

def _pitch_for_cost(state: GameState, action: Action, needed_cost: int,
                    for_chi: bool = False) -> None:
    """Present pitchable hand cards and let the model choose which to pitch.

    Each iteration presents all remaining pitchable cards as options.  The model
    picks one, it is pitched, and the loop repeats until the pool >= needed_cost.
    The card being played is excluded from pitch candidates.

    for_chi=False (default): pitching fills player.resources.  Any card can be pitched.
    for_chi=True: pitching fills player.chi.  Only cards with the name 'inner_chi'
        (i.e. cards that generate chi when pitched) are eligible.  Resources CANNOT
        be pitched for chi costs (CR 1.14.2a).
    """
    player = state.players[action.player_id]
    if needed_cost is None or needed_cost <= 0:
        return

    pool = player.chi if for_chi else player.resources
    if pool >= needed_cost:
        return

    # Exclude the card being played from pitch candidates (it's still in hand at this point)
    exclude = action.card if hasattr(action, "card") else None

    pitched_slugs: list[str] = []
    while (player.chi if for_chi else player.resources) < needed_cost:
        pitchable = get_pitchable_cards(player.hand.cards, exclude_card=exclude)
        if for_chi:
            pitchable = [c for c in pitchable
                         if "Chi" in (c.types or []) or "Chi" in (c.subtypes or [])]
        if not pitchable:
            break  # nothing left to pitch
        context = 'Pitch for chi?' if for_chi else 'Pitch?'
        options = [Action(type=ActionType.CHOOSE, card=c) for c in pitchable]
        choice = state.player_agents[action.player_id](state, options, context)
        if isinstance(choice, Action):
            choice.player_id = action.player_id
        card = choice.card
        if card is None:
            break
        player.hand.remove(card)
        player.pitch.add(card)
        pitched_slugs.append(card.slug)
        pitch_val = card.base_pitch or card.pitch or 0
        if for_chi:
            player.chi += pitch_val
        elif getattr(card, 'pitch_gives_chi', False) and action.player_id is not None:
            # Cards like inner_chi can fill either pool — ask the player
            from engine.card_effects.card_keywords import _ask_player as _apk
            chi_choice = _apk(state, action.player_id, ['chi', 'resources'],
                              context=f"Pitch {card.slug} for {pitch_val} chi or {pitch_val} resources?")
            if str(chi_choice) == 'chi':
                player.chi += pitch_val
            else:
                player.resources += pitch_val
        else:
            player.resources += pitch_val
        state.event_manager.emit(
            Event(type='card_pitched', data={'card': card, 'pitcher_id': action.player_id}), state)

    if pitched_slugs:
        state.record_pitch(action.player_id, pitched_slugs)
def get_pitchable_cards(hand_cards: list[Card], exclude_card: Card | None = None) -> list[Card]:
    """Return hand cards that can be pitched (pitch > 0), excluding *exclude_card*."""
    return [
        c for c in hand_cards
        if c is not exclude_card and c.pitch is not None and c.pitch > 0
    ]


def evaluate_play_cost(state: GameState, action: Action, check: bool) -> bool:
    """Check or pay the resource cost for an action (CR 5.1.6 / 1.14.2).

    check=True  — return True if the player can afford the action (no state change).
    check=False — pitch cards and deduct resources to pay the cost; return True.
    """
    from engine.actions import can_pay_cost
    if action.player_id is None:
        return True
    player = state.players[action.player_id]
    resource_cost = _calculate_resource_cost(state, action)
    if check:
        exclude = action.card if isinstance(getattr(action, 'card', None), Card) else None
        effective = player.resources + getattr(player, 'chi', 0)
        if effective >= resource_cost:
            return True
        return can_pay_cost(player.hand.cards, resource_cost, effective, exclude_card=exclude)
    else:
        _pitch_for_cost(state, action, resource_cost)
        action.resource_cost = resource_cost
        player.resources = max(0, player.resources - resource_cost)
        return True
def _ally_attack_resource_cost(ally_card) -> int:
    """Parse the resource cost of an ally's attack ability from functional text.
    Falls back to card.cost if set. Returns 0 if no cost found."""
    if ally_card.cost is not None:
        return int(ally_card.cost)
    text = ally_card.functional_text or ""
    # Match "Action - {r}{r}:" or "Once per Turn Action - {r}:" patterns
    match = re.search(r'\*\*(?:[\w\s]+ )?[Aa]ction\*\*\s*[-\u2014]\s*((?:\{[rR]\})*)', text)
    if match and match.group(1):
        return match.group(1).lower().count('{r}')
    return 0


def _pay_costs(state, player_id, action):

    player = state.players[player_id]
    resource_cost = _calculate_resource_cost(state, action)

    _pitch_for_cost(state, action, resource_cost)
    # Deduct final resource cost using the pre-calculated modified value
    action.resource_cost = resource_cost
    player.resources -= resource_cost

    life_cost: int = 0
    if hasattr(action, "life_cost") and (action.life_cost or 0) > 0 and player.hero is not None:
        life_cost = action.life_cost
        player.health -= life_cost

    # CR 4.4.3: action-speed plays/activations consume 1 AP
    _meld_side = getattr(action, 'meld_side', None)
    if action.type == ActionType.PLAY_CARD:
        if _meld_side in ('top', 'both'):
            player.action_points -= 1
        elif "Instant" not in (action.card.types or []):
            player.action_points -= 1
        elif not getattr(action, 'played_as_instant', False):
            player.action_points -= 1
    elif action.type == ActionType.ACTIVATE_CARD:
        if getattr(action, 'is_attack_proxy', False):
            # Weapon and ally attacks always cost 1 AP (CR 1.6.2b, CR 11.0)
            player.action_points -= 1
        else:
            _text = (action.card.functional_text or '') if action.card else ''
            if re.search(r'\*\*(?:[\w ]+ per \w+ )?[Aa]ction\*\*', _text) and not getattr(action, 'played_as_instant', False):
                player.action_points -= 1

    # CR 1.6.2b / CR 11.0: exhaust weapon or ally as part of the attack activation cost
    if action.type == ActionType.ACTIVATE_CARD and getattr(action, 'is_attack_proxy', False):
        card = action.card
        if card is not None and card.is_weapon:
            player.weapon_exhausted = True
        else:
            idx = getattr(action, 'choose_index', None)
            if idx is not None and idx < len(player.allies_exhausted):
                player.allies_exhausted[idx] = True

    _pay_effect_costs(state, action)
    return True

def _pay_effect_costs(state: GameState, action: Action) -> bool:
    """CR 5.1.8-5.1.9: Calculate and pay effect-costs before the card enters the stack.

    Returns True if all effect-costs were paid successfully (or there were none).
    Returns False if a mandatory effect-cost could not be paid (action cancelled).
    """
    card = action.card
    if card is None:
        return True
    # Slug-registered effect costs take priority
    cost_fn = ALTERNATE_COSTS.get(card.slug)
    if cost_fn is not None:
        cost_fn(state, action.player_id, action, check=False)
    # Keyword-based effect costs: Scrap and Beat Chest are additional costs on the card
    player_id = action.player_id
    if player_id is None:
        return True
    for keyword, fn in KEYWORD_COSTS.items():
        if keyword in (card.keywords or []) and hasattr(action, 'additional_costs') and keyword in action.additional_costs_declared:
            fn(state, player_id, action, check=False)
    return True

