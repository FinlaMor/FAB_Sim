from __future__ import annotations
import inspect
import re, json
from os import environ
from typing import Callable, Optional
from numpy.random import random

from engine.card import CardDB, Card
from engine.state import GameState, Step, EventManager, Event, Player, CombatState, ChainLink, StackEntry
from engine.deck import load_deck, create_player
from engine.actions import legal_actions, Action, ActionType, get_defendable_cards, get_pitchable_cards, can_pay_cost
from engine.effects import EffectManager
from engine.card_effects.triggers import register_card_triggers, register_hero_triggers

def new_game(
        p1_deck_path: Optional[str],
        p2_deck_path: Optional[str],
        p1_agent: Callable,
        p2_agent: Callable,
        card_db: CardDB,
        p1_seed: Optional[int] = None,
        p2_seed: Optional[int] = None,
    debug_file: Optional[str] = None,
    max_turns: int = 200,
) -> GameState:
    """Create a new game state with the given deck paths and card database."""
    agents = {1: p1_agent, 2: p2_agent}

    if debug_file:
        environ['debug_file'] = debug_file
        environ['debug'] = 'True'
        print(f'DEBUG ACTIVE')
    else:
        environ.setdefault('debug', 'False')

    if sum([x is None for x in (p1_deck_path, p2_deck_path)]) == 2:
        raise ValueError("At least one deck path must be provided.")

    if max_turns <= 0:
        raise ValueError("max_turns must be > 0")

    if sum([x is None for x in (p1_deck_path, p2_deck_path)]) == 1:
        p1_deck_path = p2_deck_path if p1_deck_path is None else p1_deck_path
        p2_deck_path = p1_deck_path if p2_deck_path is None else p2_deck_path

    # Start of Game
    ## Reveal Heroes - for future code, reveal hero cards to both players then they decide on which cards to include in deck.
    ## For now, pre-sideboard decks in txt files.

    # Initialize event manager and effect manager
    event_mngr = EventManager()
    effect_mngr = EffectManager()

    p1_deck = load_deck(p1_deck_path, card_db)
    p2_deck = load_deck(p2_deck_path, card_db)

    p1 = create_player(p1_deck, player_id=1, card_db=card_db, seed=p1_seed)
    p2 = create_player(p2_deck, player_id=2, card_db=card_db, seed=p2_seed)

    ## Player is selected to decide who goes first
    # Use a seeded RNG for reproducibility when seeds are provided (P3-6)
    import numpy.random as _npr
    _coin_seed = (p1_seed or 0) ^ (p2_seed or 0) ^ 0xFAB
    _coin_rng = _npr.RandomState(_coin_seed)
    first_player = 1 if _coin_rng.random() < 0.5 else 2

    state = GameState(
        players={1: p1, 2:p2},
        player_agents=agents,
        active_player=first_player,
        step=Step.BEGIN_GAME,
        turn_number=0,
        individual_turns=0,
        done=False,
        max_turns=max_turns,
        card_db=card_db,
        event_manager=event_mngr,
        effect_manager=effect_mngr,
        priority_player=first_player,
        consecutive_passes=0,
        combat=None,
        winner=None
        )

    # Register a single dispatcher for keyword static abilities (e.g. Piercing).
    # One permanent listener is cheaper than registering/deregistering per combat.
    _setup_static_ability_listeners(state)

    # Player that won coin flip decides who goes first (only once at game start)
    if state.step == Step.BEGIN_GAME:
        first_player_chose = get_turn_player_choice(state, 'Who goes first?')
        if environ['debug'] == 'True':
            with open(environ['debug_file'], 'a') as f:
                f.write(f'\nplayer {first_player} chose {first_player_chose}\n')

        state.active_player = first_player_chose
        state.priority_player = first_player_chose
        state.step = Step.START_PHASE  # Advance out of BEGIN_GAME so prompt never repeats

    # Draw opening hands
    _draw_cards(p1, p1.intellect)
    _draw_cards(p2, p2.intellect)

    # Register triggers and prevention effects for all public cards (hero, equipment, weapons)
    for player_id in state.players:
        for card in state.players[player_id].public_cards:
            register_card_triggers(card, event_mngr)
            effect_mngr.register_prevention_effects(card, state)
        # Register passive hero triggers from HERO_TRIGGERS (B2/B3)
        register_hero_triggers(state.players[player_id].hero, state.players[player_id], event_mngr)

    # 9.3.3: global listener — when a marked hero is hit, remove marked condition.
    # Registered AFTER card triggers so on-hit effects (e.g. Mark of the Black Widow)
    # can check is_marked before it's cleared.
    def _clear_marked_on_hit(event, game_state):
        if not game_state.combat:
            return
        defender_id = 3 - game_state.combat.attacker_id
        defender = game_state.players[defender_id]
        if defender.marked:
            defender.marked = False

    event_mngr.register('hit', _clear_marked_on_hit)

    # Scan all deck cards for Transcend keyword; if found, register a blue-card-played
    # hook so effect_transcend() can check whether to flip the card to hand.
    _setup_transcend_hook_if_needed(state, event_mngr)

    # 4.1.8: start of game event — no priority (4.1.1)
    event_mngr.emit('start_of_game', state)
    _resolve_all_triggers(state)

    # Run the game loop
    _game_loop(state)

    return state


def _setup_transcend_hook_if_needed(state: GameState, event_mngr: EventManager) -> None:
    """Scan all deck cards for the Transcend keyword.
    If any player's deck contains a Transcend card, register a single global
    'on_play' listener that sets 'blue_card_played_this_turn' in current_turn_effects
    whenever a blue (pitch=3) card is played.  This flag is what Transcend checks.
    """
    has_transcend = False
    for player in state.players.values():
        for card in player.deck.cards:
            if "Transcend" in (card.keywords or []):
                has_transcend = True
                break
        if has_transcend:
            break

    if not has_transcend:
        return

    def _blue_card_played_hook(event, game_state):
        card = event.data.get('card') if isinstance(event.data, dict) else None
        if card is None:
            return
        # Check pitch value: blue cards pitch for 3
        if (card.base_pitch or 0) != 3:
            return
        pid = getattr(card, 'controller', None) or getattr(card, 'owner', None)
        if pid is None or pid not in game_state.players:
            return
        player = game_state.players[pid]
        if 'blue_card_played_this_turn' not in player.current_turn_effects:
            player.current_turn_effects.append('blue_card_played_this_turn')

    event_mngr.register('on_play', _blue_card_played_hook)


def _end_game_on_turn_cap(state: GameState) -> None:
    """Terminate a game that has reached its configured turn cap.

    Winner is determined by life total; equal life totals are recorded as a draw.
    """
    p1_life = state.players[1].health
    p2_life = state.players[2].health

    if p1_life > p2_life+30:  # Player 1 wins by 30+ life lead at turn cap
        winner = 1
    elif p2_life > p1_life+30:  # Player 2 wins by 30+ life lead at turn cap
        winner = 2
    else:
        winner = None

    state.done = True
    state.winner = winner
    state.ended_on_turn_cap = True
    state.step = Step.END_GAME
    state._next_phase = "end_game"
    for event_name in state._static_listeners:
        state.event_manager.unregister(event_name, _meta_dispatcher)


def _game_loop(state: GameState) -> None:
    """Iterative main game loop — avoids deep recursion from turn/combat cycling."""
    state._next_phase = "start_of_turn"

    while not state.done:
        phase = state._next_phase
        # Prevent pathological long games from generating runaway data volume.
        if phase == "start_of_turn" and state.turn_number >= state.max_turns:
            _end_game_on_turn_cap(state)
            break

        if phase == "start_of_turn":
            _start_of_turn_phase(state)
        elif phase == "action_phase":
            _action_phase_iter(state)
        elif phase == "continue_action_phase":
            _continue_action_phase(state)
        elif phase == "combat_phase":
            _combat_phase_iter(state)
        elif phase == "end_phase":
            _end_phase_iter(state)
        else:
            break

# ---------------------------------------------------------------------------
# State-based actions (checked continuously)
# ---------------------------------------------------------------------------

def check_state_based_actions(state: GameState) -> bool:
    """Check state-based actions. Returns True if game has ended.
    Called after any resolution, damage, or action application.

    CR 1.10.2b: Living objects (heroes and allies) with 0 or less life are
    destroyed simultaneously, then triggers from those deaths are ordered.
    """
    from engine.card_effects.keywords import _move_to_graveyard

    # Hero death — check both players first (simultaneous)
    dead_heroes = [pid for pid in state.players if state.players[pid].health <= 0]
    if dead_heroes:
        # Last player standing wins; if both die simultaneously it's a draw (no winner set)
        if len(dead_heroes) == 1:
            state.winner = 3 - dead_heroes[0]
        state.done = True
        state.step = Step.END_GAME
        return True

    # CR 1.10.2b: Ally death — collect all allies at 0 life, destroy simultaneously
    dead_allies: list = []
    for pid in state.players:
        for ally in list(state.players[pid].allies.cards):
            life = getattr(ally, 'current_life', getattr(ally, 'life', None))
            if life is not None and life <= 0:
                dead_allies.append((pid, ally))

    for pid, ally in dead_allies:
        _move_to_graveyard(ally, state)

    if dead_allies:
        _resolve_all_triggers(state)
        if state.done:
            return True

    return False

# ---------------------------------------------------------------------------
# Start Phase (4.2) — no priority (4.2.1)
# ---------------------------------------------------------------------------

def _start_of_turn_phase(state: GameState) -> None:
    """Start Phase (4.2) — reset per-turn state, emit start_of_turn."""

    state.individual_turns += 1
    state.turn_number = (state.individual_turns - 1) // 2
    state.events_this_turn = set()
    player = state.active()

    player.weapon_exhausted = False
    player.weapon_power_bonus = 0
    player.hero_power_exhausted = False
    player.resources = 0
    assert len(player.pitch.cards) == 0  # pitched cards already moved to deck bottom in end phase

    # Rotate turn effects
    player.current_turn_effects = player.next_turn_effects[:]
    player.next_turn_effects = []

    # Reset ally exhaustion
    player.allies_exhausted = [False] * len(player.allies.cards)

    # Clear equipment-defended tracking (safety net)
    player.equipment_defended_this_turn = []

    # Reset card.exhausted for all equipment in arena (covers "once per turn" and {t}-cost instants)
    for _zone in (player.head, player.chest, player.arms, player.legs):
        for _card in _zone.cards:
            _card.exhausted = False
    for _card in player.weapon.cards:
        _card.exhausted = False

    # Clear combat chain link history
    state.chain_links = []

    # Clear per-chain-link hit-tracking counters (mask_of_momentum streak etc.)
    for _key in [k for k in player.class_counters if k.startswith("current_link_hit")]:
        del player.class_counters[_key]

    # Clear per-turn class counter flags
    player.class_counters.pop("charged_this_turn", None)
    player.class_counters.pop("boosted_this_turn", None)

    # Clear cards played this turn
    player.cards_played_this_turn = []

    if environ['debug'] == 'True':
        import json
        with open(environ['debug_file'], 'a') as f:
            f.write(f'Start of turn {state.turn_number}: {json.dumps(state.to_dict())}\n')

    # 4.2.2: "effects that last until the 'start of turn' end" before the event fires
    state.effect_manager.clear_start_of_turn_effects()  # CR 4.2.2: remove end_of_next_turn ContinuousEffects
    # 4.2.2: start of turn event — no priority
    state.event_manager.emit('start_of_turn', state)
    _resolve_all_triggers(state)
    if state.done:
        return
    
    state._next_phase = "action_phase"

# ---------------------------------------------------------------------------
# Action Phase (4.3)
# ---------------------------------------------------------------------------

def _action_phase_iter(state: GameState) -> None:
    """Action Phase (4.3) — turn player gets priority to play cards."""
    state.step = Step.ACTION

    # 4.3.1: beginning of action phase event
    state.event_manager.emit('start_of_action_phase', state)

    # 4.3.2: turn player gains 1 action point
    state.active().action_points = 1

    # 4.3.3: turn player gains priority
    # Order any triggers from start_of_action_phase, then enter priority loop
    order_stack(state)
    state.priority_player = state.active_player
    state.consecutive_passes = 0
    priority_loop(state)
    if state.done:
        return

    # 4.3.4: both passed with empty stack → end phase
    # Or attack on stack → combat phase
    if state.stack_entries and any(e.is_attack for e in state.stack_entries):
        state._next_phase = "combat_phase"
    else:
        state._next_phase = "end_phase"

def _continue_action_phase(state: GameState) -> None:
    """Action Phase continues after combat closes (7.7.7).
    Does NOT reset AP or emit start_of_action_phase — those only happen once per turn (4.3.1-4.3.2)."""
    state.step = Step.ACTION

    state.priority_player = state.active_player
    state.consecutive_passes = 0
    priority_loop(state)
    if state.done:
        return

    if state.stack_entries and any(e.is_attack for e in state.stack_entries):
        state._next_phase = "combat_phase"
    else:
        state._next_phase = "end_phase"

# ---------------------------------------------------------------------------
# Combat Phase (7.0-7.7)
# ---------------------------------------------------------------------------

def _combat_phase_iter(state: GameState) -> None:
    """Full combat chain per rules 7.1-7.7. Handles multiple chain links."""
    attack_entry = next(e for e in state.stack_entries if e.is_attack)
    state.stack_entries.remove(attack_entry)
    attack_card = attack_entry.card

    # --- 7.1 Layer Step ---
    state.step = Step.COMBAT_LAYER
    # 7.1.2: turn player unconditionally gains priority in the Layer Step (CR 7.1.2).
    # Players may play instants/reactions before the attack resolves regardless of stack state.
    if state.stack_entries:
        order_stack(state)
    state.priority_player = state.active_player
    state.consecutive_passes = 0
    priority_loop(state)
    if state.done:
        return

    # --- 7.2 Attack Step ---
    _attack_step(state, attack_card, entry=attack_entry)
    if state.done or state.step == Step.COMBAT_CLOSE:
        return

    # --- 7.3 Defend Step ---
    _defend_step(state)
    if state.done or state.step == Step.COMBAT_CLOSE:
        return

    # --- 7.4 Reaction Step ---
    _reaction_step(state)
    if state.done:
        return

    # --- 7.5 Damage Step ---
    _damage_step(state)
    if state.done:
        return

    # --- 7.6 Resolution Step ---
    # _resolution_step now owns entering Close Step at the root chain-link level.
    _resolution_step(state)
    if state.done:
        return

def _attack_step(state: GameState, attack_card: Card, entry: Optional[StackEntry] = None) -> None:
    """Attack Step (7.2)."""

    if state.done:
        return

    state.step = Step.COMBAT_ATTACK

    # 7.2.3: attack moves to combat chain as chain link
    state.combat_chain.add(attack_card)
    state.combat = CombatState(
        attacker_id=state.active_player,
        link_id=len(state.chain_links) + 1,
        attack_power=attack_card.power or 0,
        base_attack_power=attack_card.base_power or 0,
        from_weapon=attack_card.is_weapon,
        attack_card=attack_card,
        keywords=list(attack_card.keywords),
    )

    # Resolve card target from declared_targets (e.g. attack targeting a Spectra aura).
    if entry and entry.declared_targets:
        target_slug = entry.declared_targets[0]
        defender = state.players[3 - state.active_player]
        target_card = defender.permanents.find(target_slug)
        if target_card is None:
            # Also check attacker's own permanents (edge cases like self-targeting)
            target_card = state.players[state.active_player].permanents.find(target_slug)
        if target_card is not None:
            state.combat.attack_target_card = target_card
            state.combat.attack_target = defender

    # Apply pending turn effects to this attack (may append to attack_card.effects)
    _apply_turn_attack_effects(state, attack_card)

    # Register card.effects as staged ContinuousEffects (CR 6.3 stages 7-8)
    _register_card_continuous_effects(state, attack_card)

    # Register keyword triggers for this attack card (e.g. Phantasm "defend" listener).
    # Attack action cards are not public at game start so their triggers are not registered
    # at new_game time. Register them now when the card enters combat so keyword triggers fire.
    register_card_triggers(attack_card, state.event_manager)

    # 7.2.4: "attack" event — triggers (e.g. Big Bully, Mocking Blow, on_attack_power_bonus)
    # are now queued as StackEntry objects. They resolve during priority_loop below.
    # 'attacking' fires for any attack (weapon, attack action card, or ally).
    # 'attacking_hero' fires only when the attack targets the hero (attack_target is None = default hero target).
    # 'target_of_attack' fires when attack has a specific card target (e.g. Spectra aura).
    state.event_manager.emit(Event(type='attacking', card=attack_card.slug), state)
    if state.combat.attack_target is None:
        state.event_manager.emit(Event(type='attacking_hero', card=attack_card.slug), state)
    if state.combat.attack_target_card is not None:
        state.event_manager.emit(Event(type='target_of_attack', card=state.combat.attack_target_card.slug), state)

    # Spectra (or similar) may have closed the chain during target_of_attack emit.
    if state.step == Step.COMBAT_CLOSE:
        return

    # 7.2.5: turn player gains priority — attack event triggers resolve here
    order_stack(state)
    state.priority_player = state.active_player
    state.consecutive_passes = 0
    priority_loop(state)

    # Spectra (or similar) may have closed the chain during priority_loop.
    if state.step == Step.COMBAT_CLOSE or state.combat is None:
        return

    # Recalculate after priority (triggered power buffs have now resolved)
    _recalculate_attack_power(state)

def _defend_step(state: GameState) -> None:
    """Defend Step (7.3) — sequential per-card binary decisions."""

    _validate_combat_state(state)

    state.step = Step.COMBAT_DEFEND

    # 7.3.2: defender declares defending cards
    defender_id = 3 - state.active_player
    defender = state.players[defender_id]
    defendable = get_defendable_cards(state)

    chosen_cards: list = []
    hand_cards_chosen = 0
    action_cards_chosen = 0
    combat_keywords = state.combat.keywords if state.combat else []

    while True:
        # Build the set of cards still available to add as blockers
        available = []
        for card in defendable:
            if card in chosen_cards:
                continue
            # Dominate constraint: ≤1 hand card defending (CR 8.3.4a)
            if "Dominate" in combat_keywords and card in defender.hand.cards and hand_cards_chosen >= 1:
                continue
            # Overpower constraint: ≤1 action card defending (CR 8.3.22a)
            if "Overpower" in combat_keywords and getattr(card, 'is_action', False) and action_cards_chosen >= 1:
                continue
            available.append(card)

        if not available:
            break

        options = [Action(type=ActionType.CHOOSE, card=c) for c in available] + [Action(type=ActionType.PASS)]
        choice = state.player_agents[defender_id](state, options, 'Add defender?')
        if isinstance(choice, Action):
            choice.player_id = defender_id

        if choice.type == ActionType.PASS:
            break

        card = choice.card
        chosen_cards.append(card)
        if card in defender.hand.cards:
            hand_cards_chosen += 1
        if getattr(card, 'is_action', False):
            action_cards_chosen += 1

    # Build and apply the combined defend action
    if chosen_cards:
        defend_action = Action(type=ActionType.DEFEND_CARDS, card_list=chosen_cards)
        defend_action.player_id = defender_id
    else:
        defend_action = Action(type=ActionType.PASS)
        defend_action.player_id = defender_id

    _apply_defend(state, defend_action)
    state.combat.defending_declared = True

    # 7.3.3: turn player gains priority — Phantasm trigger resolves here
    order_stack(state)
    state.priority_player = state.active_player
    state.consecutive_passes = 0
    priority_loop(state)

    # Phantasm (or similar) may have closed the chain during priority_loop.
    if state.step == Step.COMBAT_CLOSE or state.combat is None:
        return

def _reaction_step(state: GameState) -> None:
    """Reaction Step (7.4)."""

    _validate_combat_state(state)

    state.step = Step.COMBAT_REACTION

    # 7.4.2: turn player gains priority
    order_stack(state)
    state.priority_player = state.active_player
    state.consecutive_passes = 0
    priority_loop(state)

    # Phantasm (or similar) may have closed the chain during priority_loop.
    if state.step == Step.COMBAT_CLOSE or state.combat is None:
        return

    # Recalculate after reactions (e.g. Kayo ability, Pummel, attack reactions)
    _recalculate_attack_power(state)

def _damage_step(state: GameState) -> None:
    """Damage Step (7.5)."""

    _validate_combat_state(state)

    state.step = Step.COMBAT_DAMAGE

    # 7.5.2: calculate and apply damage
    _resolve_damage(state)
    if state.done:
        return

    # 7.5.3: turn player gains priority
    order_stack(state)
    state.priority_player = state.active_player
    state.consecutive_passes = 0
    priority_loop(state)

def _resolution_step(state: GameState, _is_root: bool = True) -> None:
    """Resolution Step (7.6)."""

    _validate_combat_state(state)
    
    state.step = Step.COMBAT_RESOLUTION

    # 7.6.2: chain link resolves, go again check
    state.event_manager.emit('chain_link_resolves', state)
    # CR 8.3.5b: Go Again grants +1 AP at Resolution Step.
    # Keywords may appear as "Go again", "Go Again", or "go_again" depending on source.
    if any(re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', k).lower() == 'go again' for k in state.combat.keywords):
        state.active().action_points += 1

    # 7.6.3: turn player gains priority
    order_stack(state)
    state.priority_player = state.active_player
    state.consecutive_passes = 0
    priority_loop(state)
    if state.done:
        return

    # 7.6.3a: if attack added to stack during resolution → Layer Step (new chain link)
    if state.stack_entries and any(e.is_attack for e in state.stack_entries):
        attack_entry = next(e for e in state.stack_entries if e.is_attack)
        state.stack_entries.remove(attack_entry)
        attack_card = attack_entry.card

        # New chain link starts from Layer Step
        state.step = Step.COMBAT_LAYER
        if state.stack_entries:
            order_stack(state)
            state.priority_player = state.active_player
            state.consecutive_passes = 0
            priority_loop(state)
            if state.done:
                return

        _attack_step(state, attack_card, entry=attack_entry)
        if state.done or state.step == Step.COMBAT_CLOSE:
            return
        _defend_step(state)
        if state.done or state.step == Step.COMBAT_CLOSE:
            return
        _reaction_step(state)
        if state.done:
            return
        _damage_step(state)
        if state.done:
            return
        _resolution_step(state, _is_root=False)  # Recursive for further chain links
        if state.done:
            return

    # 7.7 Close Step: execute exactly once after all chain links in this combat chain are done.
    if _is_root and not state.done:
        _close_step(state)

def _close_step(state: GameState) -> None:
    """Close Step (7.7) — no priority (7.7.1)."""
    state.step = Step.COMBAT_CLOSE

    # 7.7.3: combat chain closes event
    state.event_manager.emit('combat_chain_close', state)

    # 7.7.4: triggers resolve without priority
    _resolve_all_triggers(state)

    # 7.7.5: permanents return to their zones
    # 7.7.6: remaining objects on combat chain are cleared
    _close_combat_chain(state)

    state.combat = None

    if state.done:
        return

    # 7.7.7: combat chain closes, action phase continues (not restarts)
    state._next_phase = "continue_action_phase"

# ---------------------------------------------------------------------------
# End Phase (4.4) — no priority (4.4.1)
# ---------------------------------------------------------------------------

def _end_phase_iter(state: GameState) -> None:
    """End Phase (4.4) — end of turn procedure."""
    state.step = Step.END_PHASE_BEGINNING   # CR 4.4.2
    player = state.active()

    # 4.4.1/4.4.2: no real priority is granted during End Phase.
    # Triggered layers resolve as if all players pass in succession until stack is empty.
    state.event_manager.emit('start_of_end_phase', state)
    _resolve_all_triggers(state)
    if state.done:
        return

    # 4.4.3: end-of-turn cleanup (no priority — CR 4.4.3)
    state.step = Step.END_PHASE_CLEANUP

    # 4.4.3a: ally life totals reset (CR 4.4.3a)
    # Reset each ally's current life to its printed life value at end of turn
    for ally_card in player.allies.cards:
        if hasattr(ally_card, 'base_life') and ally_card.base_life is not None:
            ally_card.current_life = ally_card.base_life
        elif hasattr(ally_card, 'life') and ally_card.life is not None:
            ally_card.current_life = ally_card.life

    # 4.4.3b: turn player may arsenal a card from hand
    if player.hand.cards and hasattr(player, 'arsenal') and len(player.arsenal.cards) < player.arsenal_limit:
        options = [
            Action(type=ActionType.STORE_ARSENAL, card=c) for c in player.hand.cards
        ] + [Action(type=ActionType.PASS)]
        choice = state.player_agents[state.active_player](state, options, 'Arsenal a card?')
        if isinstance(choice, Action):
            choice.player_id = state.active_player
        if choice.type == ActionType.STORE_ARSENAL and choice.card is not None:
            player.hand.remove(choice.card)
            player.arsenal.add(choice.card)
    _resolve_all_triggers(state)
    if state.done:
        return

    # 4.4.3c: each player moves their pitch zone to bottom of deck (CR 4.4.3c)
    # Sequential PLAY_CARD choices let the agent pick the order cards go to the
    # bottom, which matters for long games where the deck cycles back around.
    for pid in state.players:
        p = state.players[pid]
        while p.pitch.cards:
            if len(p.pitch.cards) == 1:
                card = p.pitch.cards.pop(0)
                p.deck.add_bottom(card)
            else:
                options = [Action(type=ActionType.CHOOSE, card=c) for c in p.pitch.cards]
                choice = state.player_agents[pid](state, options, 'Choose next card for bottom of deck')
                if isinstance(choice, Action):
                    choice.player_id = pid
                card = choice.card
                if card is None:
                    card = p.pitch.cards[0]
                p.pitch.cards.remove(card)
                p.deck.add_bottom(card)
    _resolve_all_triggers(state)
    if state.done:
        return

    # 4.4.3d: turn player untaps all permanents
    for card in player.arena_cards:
        card.tapped = False
    _resolve_all_triggers(state)  # CR 4.4.3: trigger window after each step
    if state.done:
        return

    # 4.4.3e: all players lose all action points and resource points
    for pid in state.players:
        state.players[pid].action_points = 0
        state.players[pid].resources = 0
    _resolve_all_triggers(state)
    if state.done:
        return

    # 4.4.3f: turn player draws up to intellect
    cards_to_draw = max(0, player.intellect - len(player.hand.cards))
    _draw_cards(player, cards_to_draw, state)
    # Turn 0 (opening player's first turn): non-turn-player also draws up
    if state.turn_number == 0:
        opp = state.inactive()
        opp_draw = max(0, opp.intellect - len(opp.hand.cards))
        _draw_cards(opp, opp_draw, state)
    _resolve_all_triggers(state)
    if state.done:
        return

    # 4.4.4: turn ends, effects that last "until end of turn" / "this turn" end
    player.current_turn_effects = []
    state.effect_manager.clear_turn_effects()  # CR 4.4.4 / CR 6.2.2a: remove end_of_turn ContinuousEffects
    state.continuous_effect_manager.clear_transient()  # CR 6.3: remove non-persistent staged effects
    state.continuous_effect_manager.clear_cost_modifiers(state.active_player)  # CR 5.1.6a: turn-scoped cost effects
    state.event_manager.emit('end_of_turn', state)
    _resolve_all_triggers(state)
    if state.done:
        return

    # Switch active player and start next turn
    state.active_player = 3 - state.active_player
    state.priority_player = state.active_player
    state._next_phase = "start_of_turn"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _draw_cards(player: Player, count: int, state: Optional[GameState] = None) -> None:
    """Draw up to count cards from deck into hand.
    Pass state to emit card_drawn events (omit for pre-trigger opening hand draws)."""
    for _ in range(count):
        if not player.deck.cards:
            return
        card = player.deck.pop_top()
        if card is not None:
            player.hand.add(card)
            if state is not None:
                state.event_manager.emit(
                    Event(type='card_drawn', data={'card': card, 'player_id': player.player_id}),
                    state)

def _resolve_all_triggers(state: GameState) -> None:
    """Order and resolve all triggers on the stack without giving players priority."""
    order_stack(state)
    _iters = 0
    _MAX_TRIGGER_ITERS = 500
    while state.stack_entries:
        _iters += 1
        if _iters > _MAX_TRIGGER_ITERS:
            import logging
            logging.warning(
                "trigger loop exceeded %d iterations on turn %d — clearing stack",
                _MAX_TRIGGER_ITERS, state.turn_number,
            )
            state.stack_entries.clear()
            return
        resolve_stack(state)
        if check_state_based_actions(state):
            return
        if state.stack_entries:
            order_stack(state)

def _apply_turn_attack_effects(state: GameState, attack_card: Card) -> None:
    """Consume pending turn effects that modify the next attack (from registry).

    Effects marked with ``persistent=True`` are NOT consumed — they apply
    to every attack for the rest of the turn (e.g. ``all_attacks_+N``).
    """
    from engine.card_effects.registry import TURN_ATTACK_EFFECTS
    player = state.active()
    consumed = []
    for effect_key in player.current_turn_effects:
        cfg = TURN_ATTACK_EFFECTS.get(effect_key)
        if cfg is None:
            continue
        cond_fn = cfg.get("condition_fn")
        if cond_fn and not cond_fn(attack_card, player, state):
            continue
        cfg["apply_fn"](attack_card, player, state)
        if not cfg.get("persistent", False):
            consumed.append(effect_key)
    for key in consumed:
        player.current_turn_effects.remove(key)


def _setup_static_ability_listeners(state: GameState) -> None:
    """Register the static ability meta-dispatcher for every event in STATIC_ABILITY_ZONES.

    One dispatcher handles all static ability events.  Adding a new event to
    STATIC_ABILITY_ZONES in registry.py automatically wires it here at game start.
    """
    from engine.card_effects.registry import (
        CARD_STATIC_ABILITIES,
        KEYWORD_STATIC_ABILITIES,
        STATIC_ABILITY_ZONES,
    )

    def _meta_dispatcher(event, state: GameState) -> None:
        zone_fn = STATIC_ABILITY_ZONES.get(event.type)
        if not zone_fn:
            return
        for card in zone_fn(state):
            if card is None:
                continue
            # Per-card statics
            for ev_name, handler in CARD_STATIC_ABILITIES.get(getattr(card, 'slug', ''), []):
                if ev_name == event.type:
                    handler(event, state, card)
            # Keyword statics (e.g. Piercing) — checked for every card in the zone
            for kw in getattr(card, 'keywords', []):
                kw_base = kw.lower().split()[0]
                kw_handler = KEYWORD_STATIC_ABILITIES.get(kw_base)
                if kw_handler:
                    parts = kw.split()
                    n = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
                    kw_handler(n, state, card)

    for event_name in STATIC_ABILITY_ZONES:
        state.event_manager.register(event_name, _meta_dispatcher)

    state._static_listeners = list(STATIC_ABILITY_ZONES.keys())  # Track registered events

def destroy_aura(state: GameState, player_id: int, card) -> None:
    """Remove an aura from a player's zone and emit 'aura_destroyed' for static listeners.

    All code that destroys auras should call this instead of player.auras.remove()
    directly, so Merciful Retribution and similar statics fire correctly.
    """
    from engine.state import Event
    state.players[player_id].auras.remove(card)
    state.event_manager.emit(
        Event(type='aura_destroyed', data={'card': card, 'player_id': player_id}),
        state,
    )

def _validate_combat_state(state: GameState) -> None:
    if not state.combat or state.done:
        raise RuntimeError("Invalid combat state: no active combat or game already ended")

def _register_card_continuous_effects(state: GameState, card: Card) -> None:
    """Register card.effects list as ContinuousEffects for the current attack.

    Clears existing per-attack power/keyword effects first so prior chain links
    don't bleed into new ones.  Called from _attack_step after
    _apply_turn_attack_effects so any effects that function appends to
    card.effects are also captured here.
    """
    from engine.continuous_effects import ContinuousEffect, next_timestamp
    mgr = state.continuous_effect_manager
    # Purge leftover per-attack staged effects from any previous chain link
    mgr.remove_by_prop('power')
    mgr.remove_by_prop('keywords')
    for effect_type, fn in getattr(card, 'effects', []):
        if effect_type == "base_power":
            # Stage 7 substage 2 (set-like transform — fn takes current and returns new)
            eid = f"card_effect_{card.slug}_{effect_type}_{id(fn)}"
            mgr.add(ContinuousEffect(
                stage=7,
                substage=2,
                timestamp=next_timestamp(),
                prop='power',
                source_slug=card.slug,
                effect_id=eid,
                apply_fn=lambda val, _s, _c, _fn=fn: _fn(val),
                persistent=False,
            ))
        elif effect_type == "base_power_multiply":
            # Stage 7 substage 3 (multiply)
            eid = f"card_effect_{card.slug}_{effect_type}_{id(fn)}"
            mgr.add(ContinuousEffect(
                stage=7,
                substage=3,
                timestamp=next_timestamp(),
                prop='power',
                source_slug=card.slug,
                effect_id=eid,
                apply_fn=lambda val, _s, _c, _fn=fn: _fn(val),
                persistent=False,
            ))


def _recalculate_attack_power(state: GameState) -> None:
    """Recalculate attack power using the CR 6.3 staging system.

    Stage 6: keywords/abilities (Go Again, Dominate, Overpower, Stealth, etc.)
    Stage 7: base numeric values (set, multiply, add) — from card.effects
    Stage 8: transient power bonuses (static abilities like Piercing)

    After the staged calculation, any keywords added directly to
    combat.keyword_effects (by triggered abilities during this chain link) are
    unioned in so all "X in combat.keywords" checks see them.
    """
    combat = state.combat
    card = combat.attack_card
    mgr = state.continuous_effect_manager

    # Stage 6: rebuild effective keywords from printed + staged effects + direct additions
    base_keywords: set = set(card.keywords or [])
    effective_keywords: set = mgr.recalculate(state, card, 'keywords', base_keywords)
    # Union with keywords added directly to combat this chain link
    effective_keywords = effective_keywords | set(combat.keyword_effects)
    combat.keywords = list(effective_keywords)

    # Stages 7-8: recalculate effective power via staged effects
    base_power = card.base_power or 0
    combat.attack_power = mgr.recalculate(state, card, 'power', base_power)

    # Fire the static ability event so CARD_STATIC_ABILITIES and
    # KEYWORD_STATIC_ABILITIES can also apply (they modify combat.attack_power
    # and combat.keywords directly, which is fine — they run AFTER staged calc).
    state.event_manager.emit('recalculate_attack_power', state)

def _resolve_damage(state: GameState) -> None:
    """Damage Step (7.5.2) — calculate and apply damage."""
    combat = state.combat
    defender_id = 3 - combat.attacker_id
    defender = state.players[defender_id]

    # Recalculate attack power from continuous effects before damage
    _recalculate_attack_power(state)

    total_defense = sum((c.defense or 0) for c in combat.defending_cards)
    combat.total_defense = total_defense

    # 7.5.2: net damage = attack power - total defense (min 0)
    net_damage = max(0, combat.attack_power - total_defense)

    # Apply prevention/replacement effects
    damage_event = {"type": "damage", "amount": net_damage, "target_player_id": defender_id, "damage_type": "physical"}
    damage_event = state.effect_manager.apply_replacements(damage_event, state)
    net_damage = damage_event.get("amount", 0)

    if net_damage > 0:
        defender.health -= net_damage
        # 7.5.5: hit event (physical damage from attack)
        # 'hit' fires for any hit (hero or ally — ally-hit path to be added).
        # 'hit_hero' fires only when the hit target is the hero (current _resolve_damage always targets the hero).
        state.event_manager.emit(Event(type='hit', card=combat.attack_card.slug, data={'damage': net_damage}), state)
        state.event_manager.emit(Event(type='hit_hero', card=combat.attack_card.slug, data={'damage': net_damage}), state)
        state.event_manager.emit(Event(type='damage_dealt', data={'damage': net_damage, 'target': defender_id}), state)
        combat.hit = True
    else:
        combat.hit = False

    # Check if damage killed someone
    check_state_based_actions(state)

    # Store chain link result
    link = ChainLink(
        chainlink_id=combat.link_id,
        attacker_id=combat.attacker_id,
        attack_slug=combat.attack_card.slug,
        attack_power=combat.attack_power,
        net_damage=net_damage,
        keywords=combat.keywords,
        from_weapon=combat.from_weapon,
        hit=(net_damage > 0),
    )
    state.chain_links.append(link)

    # CR 8.5.46: Resolve wagers — winner creates the prize token
    _resolve_wagers(state, combat)

def _resolve_wagers(state: GameState, combat) -> None:
    """CR 8.5.46: Resolve all wagers on the current chain link.

    If the attack hit, the controller (attacker) wins. Otherwise the
    opponent (defender) wins. The winner creates the prize token.
    """
    from engine.card_effects.keywords import create_token
    if not combat.wagers:
        return

    hit = combat.hit
    for controller_id, prize_slug in combat.wagers:
        opponent_id = 3 - controller_id
        winner_id = controller_id if hit else opponent_id
        # Emit wager_resolved event
        state.event_manager.emit(
            Event(type='wager_resolved',
                  data={'winner': winner_id, 'loser': 3 - winner_id,
                        'hit': hit, 'prize': prize_slug,
                        'controller': controller_id}),
            state)
        # Create prize token for the winner
        if prize_slug:
            create_token(state, winner_id, prize_slug)

    combat.wagers.clear()


def _apply_watery_grave(card, state: GameState) -> None:
    """CR 8.3.41: If card has Watery Grave and entered graveyard from the arena, turn face-down."""
    if not hasattr(card, 'keywords') or not card.keywords:
        return
    has_wg = any("watery grave" in re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', kw).lower() for kw in card.keywords)
    if not has_wg:
        return
    from engine.card_effects.keywords import ARENA_ZONE_NAMES
    if card.prev_zone in ARENA_ZONE_NAMES:
        card.face_down = True
        card.is_public = False


def _close_combat_chain(state: GameState) -> None:
    """7.7.5-7.7.6: move cards to appropriate zones after combat."""
    combat = state.combat
    if combat is None:
        return

    attacker = state.players[combat.attacker_id]
    defender = state.players[3 - combat.attacker_id]

    # Attack card: weapons stay equipped, non-permanent attacks go to graveyard
    attack_card = combat.attack_card
    state.remember_last_known(attack_card)
    if attack_card in state.combat_chain.cards:
        state.combat_chain.remove(attack_card)
    if combat.from_weapon:
        pass  # 7.7.5: weapon returns to equipped zone
    else:
        attacker.graveyard.add(attack_card)
        _apply_watery_grave(attack_card, state)

    # Defending cards: hand/arsenal cards go to graveyard.
    # Equipment zone transitions are owned entirely by keyword triggers
    # (Blade Break → graveyard, Temper → graveyard if d≤0, Battleworn/Guardwell → stay).
    # Those triggers already fired in _resolve_all_triggers above, so this loop
    # does nothing for equipment.
    for card in combat.defending_cards:
        state.remember_last_known(card)
        if card.is_equipment:
            pass  # handled by keyword trigger (or stays equipped if no keyword)
        else:
            defender.graveyard.add(card)
            _apply_watery_grave(card, state)

    # Defense reactions played from arsenal were added to state.combat_chain; move to graveyard now.
    for chain_card in list(state.combat_chain.cards):
        ctrl = chain_card.controller if chain_card.controller is not None else chain_card.owner
        if ctrl in state.players:
            state.remember_last_known(chain_card)
            state.combat_chain.remove(chain_card)
            state.players[ctrl].graveyard.add(chain_card)
            _apply_watery_grave(chain_card, state)

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

# ---------------------------------------------------------------------------
# Stack and Priority
# ---------------------------------------------------------------------------

def resolve_stack(game_state: GameState) -> None:
    """Resolve one stack entry from the top of the stack."""

    entry = game_state.stack_entries.pop()  # LIFO: resolve the top (last-added) layer first (CR 3.15.5)

    # CR 5.3.4d: Meld card layers resolve twice — first the right-side (bottom/Shock), then the
    # left-side (top). A priority window exists between the two resolutions.
    if (entry.layer_type == 'card' and entry.card
            and getattr(entry.card, 'meld_side', None) == 'both'):
        if entry.resolution_count == 0:
            # First resolution: right-side (Shock) fires, layer stays on stack
            if entry.meld_effect_bottom:
                entry.meld_effect_bottom(entry.card, game_state)
            entry.resolution_count = 1
            game_state.stack_entries.append(entry)  # re-push for second resolution
            game_state.priority_player = game_state.active_player
            game_state.consecutive_passes = 0
            game_state.last_acted_player = None
            return
        else:
            # Second resolution: left-side (Comet Storm/Consign/Null) fires, layer leaves stack
            if entry.meld_effect_top:
                top_params = len(inspect.signature(entry.meld_effect_top).parameters)
                if top_params >= 3:
                    entry.meld_effect_top(entry.card, game_state, entry)
                else:
                    entry.meld_effect_top(entry.card, game_state)
            if entry.card is not None:
                game_state.stack.remove(entry.card)  # CR 3.0.1: card leaves stack zone on resolution
            game_state.process_cease_to_exist(entry.card)
            card = entry.card
            if card and not entry.is_attack and card.has_go_again:
                game_state.players[entry.player_id].action_points += 1
            game_state.priority_player = game_state.active_player
            game_state.consecutive_passes = 0
            game_state.last_acted_player = None
            return

    # CR 5.3.4c: card-type layers cease to exist on resolution; capture LKI while still at stack zone.
    # activated/triggered layers leave their source card in its zone — do NOT freeze its LKI here.
    # Exception: Figment cards and Aura cards enter the arena instead of ceasing to exist.
    # CR 8.2.16a: Figments enter the arena as permanents.
    # CR 8.x (Aura rule): Aura-type cards (including Instant+Aura) enter the arena as permanents.
    card = entry.card
    _card_types = card.types or [] if card else []
    _is_figment = (entry.layer_type == 'card' and card is not None
                   and "Figment" in _card_types)
    _is_aura = (entry.layer_type == 'card' and card is not None
                and "Aura" in _card_types and not _is_figment)
    # CR 2.10: "Ally" is a subtype, not a card type. Check both fields for
    # compatibility with slug_index data where Ally cards have types=[] and
    # subtypes=['Ally', ...].
    _card_subtypes = card.subtypes or [] if card else []
    _is_ally = (entry.layer_type == 'card' and card is not None
                and ("Ally" in _card_types or "Ally" in _card_subtypes))

    if entry.layer_type == 'card' and card and not _is_figment and not _is_aura and not _is_ally:
        game_state.stack.remove(card)  # CR 3.0.1: card leaves stack zone on resolution
        game_state.process_cease_to_exist(card)

    if entry.effect_fn:
        result = entry.effect_fn(card, game_state)  # call once — not twice

        if environ['debug'] == 'True':
            with open(environ['debug_file'], 'a') as f:
                f.write(f'stack {entry} resolves: {result}\n')

    # Figments, Auras, and Allies enter the arena as permanents instead of ceasing to exist.
    if _is_figment or _is_aura or _is_ally:
        player_id = entry.player_id
        player = game_state.players[player_id]
        # Remove from stack zone tracking (triggered layers add here; card layers may not)
        game_state.stack.remove(card)
        # Allies enter the allies zone; Figments/Auras enter permanents
        if _is_ally:
            player.allies.add(card, is_public=True)
            # Ensure allies_exhausted list is long enough
            while len(player.allies_exhausted) < len(player.allies.cards):
                player.allies_exhausted.append(False)
            # Set initial life
            if hasattr(card, 'base_life') and card.base_life is not None:
                card.current_life = card.base_life
            elif hasattr(card, 'life') and card.life is not None:
                card.current_life = card.life
        else:
            if "Ally" in _card_types or "Ally" in _card_subtypes:
                card.permanent_subtype = "Ally"
            player.permanents.add(card, is_public=True)
        # Register triggers for the card now that it's in the arena
        from engine.card_effects.triggers import register_card_triggers
        register_card_triggers(card, game_state.event_manager)
        # Emit enters_arena event so CARD_TRIGGERS can fire
        game_state.event_manager.emit(
            Event(type='enters_arena', data={'card': card, 'player_id': player_id}),
            game_state)

    # CR 5.3.5 / 8.3.5a: non-attack card layers with go again grant an action point on resolution.
    # CR 8.5.7b: non-turn-players cannot gain action points — check player is turn-player.
    # (Attack go again is handled separately in _resolution_step via combat.keywords.)
    # Only applies to 'card' layer types — triggered/activated layers sourced from attack cards
    # must not grant Go Again even if the source card has the keyword.
    # Check both printed keywords AND any "Go Again" granted via continuous effects (CR 6.2).
    if card and not entry.is_attack and entry.layer_type == 'card':
        base_kws = set(card.keywords or [])
        effective_kws = game_state.continuous_effect_manager.recalculate(
            game_state, card, 'keywords', base_kws)
        _ga_strings = {"Go Again", "Go again", "go again"}
        has_effective_go_again = bool(effective_kws & _ga_strings) or card.has_go_again
        if has_effective_go_again and entry.player_id == game_state.active_player:
            game_state.players[entry.player_id].action_points += 1

    game_state.priority_player = game_state.active_player
    game_state.consecutive_passes = 0
    game_state.last_acted_player = None

def order_stack(game_state: GameState) -> None:
    """Order triggered abilities on the stack (6.6.6b).
    ONLY orders — does NOT resolve. Called once when triggers first appear."""
    if not game_state.stack_entries:
        return

    turn_player_id = game_state.active_player
    opponent_id = 3 - game_state.active_player

    turn_fx = [e for e in game_state.stack_entries if e.player_id == turn_player_id]
    opp_fx = [e for e in game_state.stack_entries if e.player_id == opponent_id]

    if turn_fx and opp_fx:
        goes_first = get_turn_player_choice(game_state, 'Who resolves triggers first?')
    elif turn_fx:
        goes_first = turn_player_id
    elif opp_fx:
        goes_first = opponent_id
    else:
        return

    # Preserve attack entry separately (stays at bottom)
    attack_entry = next((e for e in game_state.stack_entries if e.is_attack), None)
    if attack_entry:
        game_state.stack_entries.remove(attack_entry)

    order_fx(game_state, goes_first, attack=attack_entry)

def order_fx(game_state: GameState, goes_first: int, attack=None) -> None:
    """Order triggered abilities by player priority (6.6.6b)."""
    turn_player_triggers = [
        e for e in game_state.stack_entries
        if e.player_id == game_state.active_player
    ]
    opponent_triggers = [
        e for e in game_state.stack_entries
        if e.player_id != game_state.active_player
    ]

    if turn_player_triggers:
        game_state.priority_player = game_state.active_player
        turn_player_triggers = get_player_order_decision(
            game_state, game_state.active_player, turn_player_triggers)

    if opponent_triggers:
        game_state.priority_player = 3 - game_state.active_player
        opponent_triggers = get_player_order_decision(
            game_state, 3 - game_state.active_player, opponent_triggers)

    # LIFO: stack is resolved from the END (pop()), so goes_first player's triggers must be at the END.
    # The attack entry (lowest layer, resolves last) goes at index 0.
    if goes_first == game_state.active_player:
        game_state.stack_entries = opponent_triggers + turn_player_triggers
    else:
        game_state.stack_entries = turn_player_triggers + opponent_triggers
    if attack:
        game_state.stack_entries.insert(0, attack)  # attack at front = resolves last (CR 3.15.4)

def get_player_order_decision(game_state, player_id, triggered_abilities):
    """Let player reorder their triggered abilities."""
    order = []
    remaining = list(triggered_abilities)
    for _ in range(len(triggered_abilities)):
        if len(remaining) == 1:
            order.append(remaining.pop(0))
            break
        options = [
            Action(type=ActionType.CHOOSE, card=entry.card, card_idx=i)
            for i, entry in enumerate(remaining)
        ]
        choice = game_state.player_agents[player_id](game_state, options, context=remaining)
        if isinstance(choice, Action):
            choice.player_id = player_id
        order.append(remaining.pop(choice.card_idx or 0))
    return order

def priority_loop(state: GameState) -> None:
    """Priority system per CR.
    Stack is ordered ONCE when triggers appear. Players can only add new layers.
    When both pass consecutively:
      - If stack has non-attack entries → resolve top, check SBAs, repeat
      - If stack is empty or only attack → exit
    """
    state.consecutive_passes = 0
    _loop_iters = 0
    _MAX_PRIORITY_ITERS = 2000

    while True:
        if state.done:
            return
        if state.step == Step.COMBAT_CLOSE:
            return  # A triggered ability closed the chain; exit immediately

        _loop_iters += 1
        if _loop_iters > _MAX_PRIORITY_ITERS:
            # Pathological trigger/priority loop — force exit
            import logging
            logging.warning(
                "priority_loop exceeded %d iterations on turn %d, step %s — forcing exit",
                _MAX_PRIORITY_ITERS, state.turn_number, state.step,
            )
            return

        current_player = state.priority_player
        action = get_player_decision(state, current_player)

        if action is None or action.type in (ActionType.PASS, ActionType.REACTION_PASS):
            state.consecutive_passes += 1
            if state.consecutive_passes >= 2:
                if state.stack_entries:
                    only_attack = (
                        len(state.stack_entries) == 1 and
                        state.stack_entries[0].is_attack
                    )
                    if only_attack:
                        return  # Exit — caller handles the attack

                    # Both passed — resolve top non-attack entry
                    resolve_stack(state)
                    if check_state_based_actions(state):
                        return
                    # New triggers from resolution get ordered
                    order_stack(state)
                    state.consecutive_passes = 0
                    state.priority_player = state.active_player
                else:
                    return  # Stack empty, both passed — exit
            else:
                state.priority_player = 3 - current_player
        else:
            # Player acted — apply the action, new layers added to stack
            state.consecutive_passes = 0
            state.last_acted_player = current_player
            apply_action(state, action)
            if check_state_based_actions(state):
                return
            # New triggers from the action get ordered on top
            order_stack(state)
            # CR 1.11.5: acting player regains priority after playing/activating
            state.priority_player = current_player

# ---------------------------------------------------------------------------
# Player decisions
# ---------------------------------------------------------------------------

def get_player_decision(state: GameState, player_id: int, context: str | None = None) -> Action:
    """Get action decision from player agent."""
    legal = legal_actions(state, state.card_db)

    # Forced pass optimization: do not route pass-only decisions through agents.
    # This avoids unnecessary embedder taps/logging for CR-mandated no-op priority passes.
    if len(legal) == 1 and legal[0].type in (ActionType.PASS, ActionType.REACTION_PASS):
        forced = legal[0]
        forced.player_id = player_id
        return forced

    choice = state.player_agents[player_id](state, legal, context=context if context else 'What do you do?')
    if isinstance(choice, Action):
        choice.player_id = player_id
    return choice

def get_turn_player_choice(state: GameState, context: str) -> int:
    """Get decision from turn player for which player acts first."""
    options = [
        Action(type=ActionType.CHOOSE, card_idx=0),  # 0 = self goes first
        Action(type=ActionType.CHOOSE, card_idx=1),  # 1 = opponent goes first
    ]
    choice = state.player_agents[state.active_player](state, options, context)
    if isinstance(choice, Action):
        choice.player_id = state.active_player
    return state.active_player if (choice.card_idx == 0) else 3 - state.active_player

def player_decision_raw(state: GameState, player_id: int, options, context=None) -> int:
    """Get a raw choice from player agent (index into options list)."""
    choice = state.player_agents[player_id](state, options, context if context else None)
    return choice

# ---------------------------------------------------------------------------
# Apply action
# ---------------------------------------------------------------------------

def _get_base_resource_cost(state: GameState, action: Action) -> int:
    """Compute the base resource cost for an action before any modifiers.

    Renamed from _get_action_resource_cost — call _calculate_resource_cost
    for the full CR 5.1.6a modifier pipeline.
    """
    card = action.card
    if action.type == ActionType.PLAY_CARD:
        ms = getattr(action, 'meld_side', None)
        if ms == 'bottom':
            return 0
        elif ms == 'both':
            return card.meld_cost or 0
        else:
            return card.cost or 0

    elif action.type in (ActionType.PLAY_ARSENAL, ActionType.PLAY_BANISH):
        return card.cost or 0

    elif action.type == ActionType.ATTACK_WEAPON:
        text = card.functional_text or ""
        match = re.search(r'[-\u2014]\s*((?:\{r\})+)(?:,\s*\{t\})?\s*:', text)
        return match.group(1).count('{r}') if match else 0

    elif action.type in (ActionType.ACTIVATE_ITEM, ActionType.ACTIVATE_EQUIPMENT, ActionType.ACTIVATE_WEAPON):
        from engine.card_effects.registry import EQUIPMENT_ACTIVATION_COST as _ACT_COST
        _cost_val = _ACT_COST.get(card.slug)
        if _cost_val is not None:
            player = state.players[action.player_id]
            if callable(_cost_val):
                import inspect as _ins
                return _cost_val(player, state) if len(_ins.signature(_cost_val).parameters) >= 2 else _cost_val(player)
            return _cost_val
        if card.cost is not None:
            return card.cost
        from engine.actions import _parse_activation_cost_from_text
        return _parse_activation_cost_from_text(card.functional_text or "")

    elif action.type == ActionType.ACTIVATE_HERO:
        from engine.card_effects.registry import HERO_ACTIVATION_CONDITIONS
        player = state.players[action.player_id]
        hero_cfg = HERO_ACTIVATION_CONDITIONS.get(player.hero.slug, {})
        cost_raw = hero_cfg.get("cost", 0)
        return cost_raw(player, state) if callable(cost_raw) else cost_raw

    elif action.type in (ActionType.PLAY_ATTACK_REACTION, ActionType.PLAY_DEFENSE_REACTION):
        return card.cost or 0

    return 0


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
    alt = getattr(action, 'alternative_cost_used', None)
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


def _apply_chi_toward_resources(state: GameState, player_id: int, needed_cost: int) -> None:
    """CR 1.14.2d: Drain chi into floating resources before spending resources.

    Chi converts 1-for-1 into resources for the purpose of the current payment.
    Only converts as much chi as needed to cover the shortfall.
    """
    player = state.players[player_id]
    chi = getattr(player, 'chi', 0)
    if chi <= 0 or needed_cost <= 0:
        return
    shortfall = needed_cost - player.resources
    if shortfall <= 0:
        return
    chi_applied = min(chi, shortfall)
    player.resources += chi_applied
    player.chi -= chi_applied


def _check_still_legal(state: GameState, action: Action) -> bool:
    """CR 5.1.5: Re-verify legality after cost declarations but before payment.

    Checks that fundamental preconditions still hold — primarily that the player
    still has the action point(s) required.  Returns False if the action should
    be cancelled.
    """
    player = state.players[action.player_id]
    _action_speed_types = (
        ActionType.PLAY_CARD, ActionType.PLAY_ARSENAL, ActionType.PLAY_BANISH,
        ActionType.ATTACK_WEAPON, ActionType.ACTIVATE_ITEM,
        ActionType.ACTIVATE_EQUIPMENT, ActionType.ACTIVATE_WEAPON,
        ActionType.ACTIVATE_HERO, ActionType.ATTACK_ALLY,
    )
    if action.type in _action_speed_types:
        if player.action_points < 1:
            return False
    return True


# ---------------------------------------------------------------------------
# Effect-costs (CR 5.1.8–5.1.9)
# ---------------------------------------------------------------------------

# EFFECT_COSTS: slug -> fn(state, player_id, action) -> bool
# Returns True if cost successfully paid (or waived), False if unresolvable.
# Called in apply_action BEFORE _apply_play_card puts the card on the stack.
EFFECT_COSTS: dict = {}


def _10000_year_reunion_effect_cost(state: GameState, player_id: int, action,
                                    check: bool = False) -> bool:
    """10,000 Year Reunion alt cost: remove 3 +1{p} counters from controlled auras.

    Only fires when alternative_cost_used == "remove_p_counters".
    Normal 8{r} payment path returns True immediately (no effect-cost).
    check=True: verify ≥3 counters exist without removing them.
    check=False: agent chooses one aura per counter to remove (one at a time, 3 total).
    """
    if getattr(action, 'alternative_cost_used', None) != "remove_p_counters":
        return True  # Normal cost path — no effect-cost applies
    player = state.players[player_id]
    total = sum(
        player.counters.get((c.slug, "permanents", "+1{p}"), 0)
        for c in player.auras.cards
    )
    if total < 3:
        return False
    if not check:
        from engine.card_effects.keywords import _ask_player
        remaining = 3
        while remaining > 0:
            eligible = [
                c for c in player.auras.cards
                if player.counters.get((c.slug, "permanents", "+1{p}"), 0) > 0
            ]
            if not eligible:
                break
            pick = _ask_player(
                state, player_id, [c.slug for c in eligible],
                context=f"10,000 Year Reunion: choose an aura to remove a +1{{p}} counter from ({remaining} remaining)",
            )
            chosen = next((c for c in eligible if c.slug == str(pick)), eligible[0])
            key = (chosen.slug, "permanents", "+1{p}")
            player.counters[key] = player.counters.get(key, 0) - 1
            remaining -= 1
    return True


EFFECT_COSTS["10000_year_reunion_red"] = _10000_year_reunion_effect_cost


def _scrap_effect_cost(state: GameState, player_id: int, action) -> bool:
    """Scrap (CR 8.3.32): optional additional cost — banish an item or equipment from graveyard."""
    from engine.card_effects.keywords import _ask_player
    player = state.players[player_id]
    eligible = [
        c for c in player.graveyard.cards
        if any(t in (c.types or []) for t in ("Item", "Equipment"))
    ]
    if not eligible:
        return True  # optional — nothing to banish, cost waived
    choice = _ask_player(state, player_id, [True, False],
                         context="Scrap: banish an item/equipment from your graveyard as additional cost?")
    if not choice:
        return True  # player declined — cost is optional
    pick = _ask_player(state, player_id, [c.slug for c in eligible],
                       context="Choose item or equipment to banish for Scrap")
    target = player.graveyard.find(str(pick)) if pick is not None else None
    if target:
        from engine.card_effects.keywords import banish_card
        player.graveyard.remove(target)
        banish_card(state, player, target, face_up=True)
    action.additional_cost_paid = True
    return True


def _beat_chest_effect_cost(state: GameState, player_id: int, action) -> bool:
    """Beat Chest (CR 8.3.33): optional additional cost — discard a card with 6+ power from hand."""
    from engine.card_effects.keywords import _ask_player
    player = state.players[player_id]
    card = action.card
    eligible = [
        c for c in player.hand.cards
        if (c.power or 0) >= 6 and c.slug != (card.slug if card else None)
    ]
    if not eligible:
        return True  # optional — nothing eligible, cost waived
    choice = _ask_player(state, player_id, [True, False],
                         context="Beat Chest: discard a card with 6+ power as additional cost?")
    if not choice:
        return True  # player declined
    pick = _ask_player(state, player_id, [c.slug for c in eligible],
                       context="Choose a card with 6+ power to discard for Beat Chest")
    target = player.hand.find(str(pick)) if pick is not None else None
    if target:
        player.hand.remove(target)
        player.graveyard.add(target)
    action.additional_cost_paid = True
    return True


def _pay_effect_costs(state: GameState, action: Action) -> bool:
    """CR 5.1.8–5.1.9: Calculate and pay effect-costs before the card enters the stack.

    Returns True if all effect-costs were paid successfully (or there were none).
    Returns False if a mandatory effect-cost could not be paid (action cancelled).
    """
    card = action.card
    if card is None:
        return True
    # Slug-registered effect costs take priority
    cost_fn = EFFECT_COSTS.get(card.slug)
    if cost_fn is not None:
        return cost_fn(state, action.player_id, action)
    # Keyword-based effect costs: Scrap and Beat Chest are additional costs on the card
    player_id = action.player_id
    if player_id is None:
        return True
    keywords_lower = [k.lower() for k in (card.keywords or [])]
    if any(k == "scrap" or k.startswith("scrap ") for k in keywords_lower):
        if not _scrap_effect_cost(state, player_id, action):
            return False
    if any(k == "beat chest" or k.startswith("beat chest ") for k in keywords_lower):
        if not _beat_chest_effect_cost(state, player_id, action):
            return False
    return True


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
    exclude = action.card if action.type in (
        ActionType.PLAY_CARD, ActionType.PLAY_ATTACK_REACTION,
        ActionType.PLAY_DEFENSE_REACTION,
    ) else None

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
            from engine.card_effects.keywords import _ask_player as _apk
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


def evaluate_play_cost(state: GameState, action: Action, check: bool) -> bool:
    """Unified cost gate for playing a card or activating an ability.

    Implements the full CR 5.1 cost sequence in one place so that the
    legality check (legal_actions) and the payment (apply_action) always
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
    """
    if action.player_id is None:
        return True
    player = state.players[action.player_id]

    # --- 1. Resource asset-cost -------------------------------------------
    resource_cost = _calculate_resource_cost(state, action)

    if check:
        # CR 5.1.6a / 1.14.2b: can the player cover the cost via resources + pitch?
        exclude = action.card if action.type in (
            ActionType.PLAY_CARD, ActionType.PLAY_ATTACK_REACTION,
            ActionType.PLAY_DEFENSE_REACTION,
        ) else None
        chi = getattr(player, 'chi', 0)
        effective_resources = player.resources + chi
        if effective_resources < resource_cost:
            if not can_pay_cost(player.hand.cards, resource_cost,
                                effective_resources, exclude_card=exclude):
                return False
    else:
        # CR 1.14.2d: drain chi first, then pitch to cover remainder
        _apply_chi_toward_resources(state, action.player_id, resource_cost)
        _pitch_for_cost(state, action, resource_cost)
        # Deduct final resource cost using the pre-calculated modified value
        action.resource_cost = resource_cost
        player.resources -= resource_cost

    # --- 2. Action-point asset-cost ----------------------------------------
    # (Already checked by _check_still_legal / legal_actions AP guards;
    #  the actual deduction is handled inside each _apply_* dispatcher since
    #  it interacts with Instant-speed and meld-side logic there.)

    # --- 3. Life asset-cost (CR 1.14.2e) ------------------------------------
    life_cost: int = 0
    if action.type == ActionType.ACTIVATE_HERO and player.hero is not None:
        from engine.card_effects.registry import HERO_ACTIVATION_CONDITIONS
        hero_cfg = HERO_ACTIVATION_CONDITIONS.get(player.hero.slug, {})
        raw_life = hero_cfg.get("life_cost", 0)
        _lv = raw_life(player, state) if callable(raw_life) else raw_life
        life_cost = _lv if isinstance(_lv, int) else 0

    if life_cost > 0:
        if check:
            if player.health <= life_cost:  # CR 1.14.2b: must be able to pay in full
                return False
        else:
            player.health -= life_cost

    # --- 4. Effect-costs (CR 5.1.8–5.1.9) ----------------------------------
    if action.type in (ActionType.PLAY_CARD, ActionType.PLAY_ARSENAL, ActionType.PLAY_BANISH):
        card = action.card
        if card is not None:
            if check:
                # CR 5.1.8a: verify each effect-cost is resolvable before paying any
                cost_fn = EFFECT_COSTS.get(card.slug)
                if cost_fn is not None:
                    # Registered cost functions support a dry-run check= kwarg if the
                    # function accepts it; otherwise assume payable (optional costs).
                    import inspect as _ins
                    sig = _ins.signature(cost_fn)
                    if 'check' in sig.parameters:
                        if not cost_fn(state, action.player_id, action, check=True):
                            return False
                # Keyword effect-costs: Scrap requires graveyard item/equipment;
                # Beat Chest requires a 6+ power card in hand.
                kws = [k.lower() for k in (card.keywords or [])]
                if any(k == "scrap" or k.startswith("scrap ") for k in kws):
                    eligible = [
                        c for c in player.graveyard.cards
                        if "Item" in (c.types or []) or "Equipment" in (c.types or [])
                    ]
                    if not eligible:
                        return False  # mandatory Scrap with no valid target
                # Beat Chest is optional — never blocks legality
            else:
                # Pay effect-costs
                if not _pay_effect_costs(state, action):
                    return False

    return True


def apply_action(state: GameState, action: Action) -> None:
    """Apply a player action to the game state."""
    # Sequential pitch: ask model which cards to pitch before dispatching
    _no_pitch_types = (ActionType.PASS, ActionType.REACTION_PASS, ActionType.DEFEND_CARDS,
                       ActionType.STORE_ARSENAL, ActionType.DISCARD_ACTIVATE, ActionType.ATTACK_ALLY,
                       ActionType.CHOOSE)
    if action.type not in _no_pitch_types:
        # CR 5.1.5: Verify legality BEFORE any cost payment (declare → check → pay).
        if not _check_still_legal(state, action):
            return
        # CR 5.1.6–5.1.9: Pay all costs (resource, chi, pitch, life, effect-costs).
        if not evaluate_play_cost(state, action, check=False):
            return

    if action.type == ActionType.PLAY_CARD:
        _apply_play_card(state, action)
    elif action.type in (ActionType.ACTIVATE_ITEM, ActionType.ACTIVATE_EQUIPMENT, ActionType.ACTIVATE_WEAPON):
        _apply_activate(state, action)
    elif action.type == ActionType.ACTIVATE_HERO:
        _apply_activate_hero(state, action)
    elif action.type == ActionType.PLAY_ARSENAL:
        _apply_play_arsenal(state, action)
    elif action.type == ActionType.PLAY_BANISH:
        _apply_play_banish(state, action)
    elif action.type == ActionType.ATTACK_WEAPON:
        _apply_weapon_attack(state, action)
    elif action.type == ActionType.DEFEND_CARDS:
        _apply_defend(state, action)
    elif action.type in (ActionType.PLAY_ATTACK_REACTION, ActionType.PLAY_DEFENSE_REACTION):
        _apply_react(state, action)
    elif action.type == ActionType.ATTACK_ALLY:
        _apply_ally_attack(state, action)
    elif action.type == ActionType.DISCARD_ACTIVATE:
        _apply_discard_activate(state, action)
    elif action.type == ActionType.CHOOSE:
        pass  # Choice is conveyed by selection of this Action object; no state mutation needed


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

    # Meld-side-aware action point deduction.
    # 'top' / 'both' are explicit action-speed plays → spend 1 AP.
    # 'bottom' is instant-speed → no AP.
    # None = regular card or meld card played at instant-speed → use Instant-type check.
    if _meld_side in ('top', 'both'):
        player.action_points -= 1
    elif "Instant" not in (card.types or []):
        player.action_points -= 1

    # Tag the card so on_play triggers know which side is resolving
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

def _apply_play_arsenal(state: GameState, action: Action) -> None:
    """Play a card from arsenal: pitch from hand for cost, place on stack (CR 3.3.4, CR 5.1.1a)."""
    player = state.players[action.player_id]
    card = action.card
    declared_modes, declared_targets, declared_x = _stack_declarations_from_action(action)

    # Resource cost already deducted by evaluate_play_cost in apply_action.
    player.arsenal.remove(card)

    if "Instant" not in (card.types or []):
        player.action_points -= 1

    # CR 3.0.1 / CR 5.3.4c: card enters stack zone (Zone.add keeps card.zone in sync)
    if card is not None:
        state.stack.add(card)

    # CR 5.1.2: card moves to stack first, then on_play triggered layers sit above it (LIFO resolves them first)
    # CR 3.15.4: layer position is N+1 where N is existing layers
    entry = StackEntry(
        player_id=action.player_id,
        card=card,
        from_arsenal=True,
        layer_type='card',
        layer_position=len(state.stack_entries) + 1,
        declared_modes=declared_modes,
        declared_targets=declared_targets,
        declared_x=declared_x,
    )
    state.stack_entries.append(entry)
    player.cards_played_this_turn.append(card)
    state.event_manager.emit(Event(type='on_play', card=card.slug, data={'card': card, 'target': action.target}), state)

def _apply_play_banish(state: GameState, action: Action) -> None:
    """Play a card from the banish zone (e.g. via Under the Trap-Door trap_door_playable_ flag)."""
    player = state.players[action.player_id]
    card = action.card
    declared_modes, declared_targets, declared_x = _stack_declarations_from_action(action)

    # Resource cost already deducted by evaluate_play_cost in apply_action.
    player.banished.remove(card)
    # Consume the playable flag (trap-door or infiltrate)
    for prefix in (f"trap_door_playable_{card.slug}", f"infiltrate_play_{card.slug}"):
        if prefix in player.current_turn_effects:
            player.current_turn_effects.remove(prefix)
        if hasattr(player, 'next_turn_effects') and prefix in player.next_turn_effects:
            player.next_turn_effects.remove(prefix)

    if "Instant" not in (card.types or []):
        player.action_points -= 1

    # CR 3.0.1 / CR 5.3.4c: card enters stack zone (Zone.add keeps card.zone in sync)
    if card is not None:
        state.stack.add(card)

    # CR 3.15.4: layer position is N+1 where N is existing layers
    entry = StackEntry(
        player_id=action.player_id,
        card=card,
        layer_type='card',
        layer_position=len(state.stack_entries) + 1,
        declared_modes=declared_modes,
        declared_targets=declared_targets,
        declared_x=declared_x,
    )
    state.stack_entries.append(entry)
    state.event_manager.emit(Event(type='on_play', card=card.slug, data={'card': card, 'target': action.target}), state)

def _apply_weapon_attack(state: GameState, action: Action) -> None:
    """Attack with a weapon: exhaust weapon, place attack on stack."""
    player = state.players[action.player_id]
    player.weapon_exhausted = True
    player.action_points -= 1

    # Pay "banish a card from under" cost if required (e.g., Nitro Mechanoid)
    weapon_card = action.card
    text = getattr(weapon_card, 'functional_text', '') or ''
    if "banish a card from under" in text.lower():
        underneath = getattr(weapon_card, 'cards_underneath', [])
        if underneath:
            from engine.card_effects.keywords import banish_card
            banished = underneath.pop(0)
            banish_card(state, player, banished, face_up=True)

    # Pay "{t} a cog you control" cost if required (e.g., Spitfire)
    if "{t} a cog you control" in text and "Attack" in text:
        # Only tap as cost when cog-tap appears before the Attack keyword (i.e. it's a cost)
        cost_part = text.split("**Attack**")[0] if "**Attack**" in text else text.split(": Attack")[0]
        if "{t} a cog you control" in cost_part:
            cog = next(
                (c for c in player.items.cards if "Cog" in (c.types or []) and not c.tapped),
                None,
            )
            if cog is not None:
                cog.tapped = True

    declared_modes, declared_targets, declared_x = _stack_declarations_from_action(action)

    # CR 1.6.2b: Weapon attack is an activated ability (activated-layer)
    # CR 3.15.4: layer position is N+1 where N is existing layers
    entry = StackEntry(
        player_id=action.player_id, 
        card=action.card,
        layer_type='activated',
        layer_position=len(state.stack_entries) + 1,
        declared_modes=declared_modes,
        declared_targets=declared_targets,
        declared_x=declared_x,
    )
    state.stack_entries.append(entry)

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


def _apply_ally_attack(state: GameState, action: Action) -> None:
    """Ally attacks (CR 11.0): exhaust the ally, place attack on stack."""
    player = state.players[action.player_id]
    ally_card = action.card

    # Spend one action point and deduct resource cost
    player.action_points -= 1
    resource_cost = _ally_attack_resource_cost(ally_card)
    player.resources -= resource_cost

    # Mark the ally exhausted so it cannot attack again this turn
    idx = action.card_idx
    if idx is not None and idx < len(player.allies_exhausted):
        player.allies_exhausted[idx] = True
    elif ally_card in player.allies.cards:
        i = list(player.allies.cards).index(ally_card)
        while len(player.allies_exhausted) <= i:
            player.allies_exhausted.append(False)
        player.allies_exhausted[i] = True

    declared_modes, declared_targets, declared_x = _stack_declarations_from_action(action)

    # CR 1.6.2b: Ally attack is an activated ability (activated-layer)
    entry = StackEntry(
        player_id=action.player_id,
        card=ally_card,
        layer_type='activated',
        layer_position=len(state.stack_entries) + 1,
        declared_modes=declared_modes,
        declared_targets=declared_targets,
        declared_x=declared_x,
    )
    state.stack_entries.append(entry)


def _apply_activate(state: GameState, action: Action) -> None:
    """Activate an equipment/item/weapon ability: pay cost, exhaust, apply effect."""
    from engine.card_effects.registry import EQUIPMENT_ACTIVATION_EFFECTS
    player = state.players[action.player_id]
    card = action.card

    # Use EQUIPMENT_ACTIVATION_COST override when available (handles tokens/items with resource
    # cost embedded in functional text and a cost field that doesn't reflect activation cost).
    from engine.card_effects.registry import EQUIPMENT_ACTIVATION_COST as _ACT_COST
    _cost_val = _ACT_COST.get(card.slug)
    if _cost_val is not None:
        import inspect as _ins
        activation_cost = _cost_val(player, state) if (callable(_cost_val) and len(_ins.signature(_cost_val).parameters) >= 2) else (_cost_val(player) if callable(_cost_val) else _cost_val)
    else:
        activation_cost = card.cost or 0
    player.resources -= activation_cost

    # CR 4.4.3d / 8.x: Mark exhausted for "once per turn" abilities.
    # {t} (tap symbol as activation cost) → tapped=True, not exhausted.
    # Tapped permanents untap at end of turn (4.4.3d), so effects can re-enable
    # them mid-turn. exhausted=True is a harder "once per turn" gate.
    text = card.functional_text or ""
    _first_colon = text.find(':')
    _cost_section = text[:_first_colon] if _first_colon >= 0 else ""
    if "per turn" in text.lower():
        card.exhausted = True
    if re.search(r'\{t\}', _cost_section, re.IGNORECASE):
        card.tapped = True

    # Use action point if it's an Action-speed ability (not Instant)
    if re.search(r'\*\*(?:\w+ per turn )?Action\*\*', text):
        player.action_points -= 1

    # Pay additional costs (destroy, tap, etc. — everything before the colon)
    from engine.card_effects.registry import EQUIPMENT_PAY_COSTS
    pay_cost_fn = EQUIPMENT_PAY_COSTS.get(card.slug)
    if callable(pay_cost_fn):
        pay_cost_fn(action, player, state)
    elif (action.type == ActionType.ACTIVATE_EQUIPMENT and ':' in text
          and re.search(r'\bDestroy\b', text[:text.rfind(':')], re.IGNORECASE)):
        # Generic fallback: equipment with "Destroy [this/CardName]:" activation cost
        # not covered by an explicit EQUIPMENT_PAY_COSTS entry.
        # Remove from the equipment slot and move to graveyard.
        slot = getattr(action, 'slot', None)
        if slot:
            zone = player.zone_by_name(slot)
            if zone and card in zone.cards:
                zone.remove(card)
                player.graveyard.add(card)

    # Dispatch to registry callback (effect after the colon)
    effect_fn = EQUIPMENT_ACTIVATION_EFFECTS.get(card.slug)
    if callable(effect_fn):
        effect_fn(action, player, state)

def _apply_activate_hero(state: GameState, action: Action) -> None:
    """Activate a hero ability: tap if required, apply effect."""
    from engine.card_effects.registry import HERO_ACTIVATION_CONDITIONS
    player = state.players[action.player_id]

    hero_cfg = HERO_ACTIVATION_CONDITIONS.get(player.hero.slug, {})
    cost_raw = hero_cfg.get("cost", 0)
    cost = cost_raw(player, state) if callable(cost_raw) else cost_raw
    player.resources -= cost

    # Action-timing abilities consume an action point
    hero_timing = hero_cfg.get("timing", "action")
    if hero_timing == "action":
        player.action_points -= 1

    # Tap hero if required
    if hero_cfg.get("requires_tap", False):
        player.hero.tapped = True

    # Pay additional costs (e.g. destroy Gold, discard instant — before the colon)
    pay_cost_fn = hero_cfg.get("pay_cost_fn")
    if callable(pay_cost_fn):
        pay_cost_fn(player, state)

    # Dispatch to registry callback (effect after the colon)
    effect_fn = hero_cfg.get("effect_fn")
    if callable(effect_fn):
        effect_fn(action, player, state)

def _apply_react(state: GameState, action: Action) -> None:
    """Play a reaction card (defense reaction or attack reaction)."""
    player = state.players[action.player_id]
    card = action.card
    declared_modes, declared_targets, declared_x = _stack_declarations_from_action(action)

    # Resource cost already deducted by evaluate_play_cost in apply_action.

    # Reactions can be played from hand or arsenal; remove from the declared source zone.
    if action.from_arsenal:
        removed = player.arsenal.remove(card)
        if not removed:
            # Fallback safety to avoid ghost copies if metadata gets out of sync.
            player.hand.remove(card)
    else:
        removed = player.hand.remove(card)
        if not removed:
            # Fallback safety for legacy actions incorrectly marked as hand plays.
            player.arsenal.remove(card)
        # CR 8.3.4b: a DR played from hand counts as "defender used hand card" for Dominate/Reprise
        if state.combat is not None and "Defense Reaction" in (card.types or []):
            state.combat.defender_used_hand_card = True

    # CR 3.0.1 / CR 5.3.4c: card enters stack zone.
    # Defense reactions played from arsenal are additionally placed on the combat chain so
    # _close_combat_chain() moves them to graveyard at chain close rather than leaving them
    # in limbo (zone='stack' but absent from every Zone collection).
    if action.from_arsenal and state.combat is not None and "Defense Reaction" in (card.types or []):
        state.combat_chain.add(card)  # zone='combat chain', is_public=True
    else:
        card.prev_zone = card.zone
        card.zone = 'stack'

    # CR 5.1.2: card moves to stack first, then on_play triggered layers sit above it (LIFO resolves them first)
    # CR 3.15.4: layer position is N+1 where N is existing layers
    entry = StackEntry(
        player_id=action.player_id,
        card=card,
        layer_type='card',
        layer_position=len(state.stack_entries) + 1,
        declared_modes=declared_modes,
        declared_targets=declared_targets,
        declared_x=declared_x,
    )
    state.stack_entries.append(entry)
    state.event_manager.emit(Event(type='on_play', card=card.slug, data={'card': card, 'target': action.target}), state)

def _apply_discard_activate(state: GameState, action: Action) -> None:
    """Activate a 'Instant - Discard this:' hand ability. Cost: discard the card."""
    from engine.card_effects.registry import DISCARD_ACTIVATE_EFFECTS
    player = state.players[action.player_id]
    card = action.card
    # Pay cost: discard the card to graveyard
    state.remember_last_known(card)
    player.hand.remove(card)
    player.graveyard.add(card)
    # Apply effect
    effect_fn = DISCARD_ACTIVATE_EFFECTS.get(card.slug)
    if callable(effect_fn):
        effect_fn(action, player, state)