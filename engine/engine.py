from __future__ import annotations
import inspect
import re, json
from os import environ
from typing import Callable, Optional
from numpy.random import random

from engine.card import CardDB, Card
from engine.state import GameState, Step, EventManager, Event, Player, CombatState, ChainLink, StackEntry
from engine.deck import load_deck, create_player
from engine.actions import legal_actions, Action, ActionType
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
    fx_mngr = EventManager()
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
        done=False,
        max_turns=max_turns,
        card_db=card_db,
        event_manager=fx_mngr,
        effect_manager=effect_mngr,
        priority_player=first_player,
        consecutive_passes=0,
        combat=None,
        winner=None
        )

    # Player that won coin flip decides who goes first
    first_player_chose = get_turn_player_choice(state)
    if environ['debug'] == 'True':
        with open(environ['debug_file'], 'a') as f:
            f.write(f'\nplayer {first_player} chose {first_player_chose}\n')

    state.active_player = first_player_chose
    state.priority_player = first_player_chose

    # Draw opening hands
    _draw_cards(p1, p1.intellect)
    _draw_cards(p2, p2.intellect)

    # Register triggers and prevention effects for all public cards (hero, equipment, weapons)
    for player_id in state.players:
        for card in state.players[player_id].public_cards:
            register_card_triggers(card, fx_mngr)
            effect_mngr.register_prevention_effects(card, state)
        # Register passive hero triggers from HERO_TRIGGERS (B2/B3)
        register_hero_triggers(state.players[player_id].hero, state.players[player_id], fx_mngr)

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

    fx_mngr.register('hit', _clear_marked_on_hit)

    # 4.1.8: start of game event — no priority (4.1.1)
    fx_mngr.emit('start_of_game', state)
    _resolve_all_triggers(state)

    # Run the game loop
    _game_loop(state)

    return state


def _end_game_on_turn_cap(state: GameState) -> None:
    """Terminate a game that has reached its configured turn cap.

    Winner is determined by life total; ties resolve to the active player to keep
    the outcome deterministic for replay/training pipelines.
    """
    p1_life = state.players[1].health
    p2_life = state.players[2].health

    if p1_life > p2_life:
        winner = 1
    elif p2_life > p1_life:
        winner = 2
    else:
        winner = state.active_player

    state.done = True
    state.winner = winner
    state.ended_on_turn_cap = True
    state.step = Step.END_GAME
    state._next_phase = "end_game"


def _game_loop(state: GameState) -> None:
    """Iterative main game loop — avoids deep recursion from turn/combat cycling."""
    state._next_phase = "start_of_turn"

    _stalemate_health_history: list[tuple[int, int]] = []
    _STALEMATE_TURNS = 50  # end game if health unchanged for this many consecutive turns

    while not state.done:
        phase = state._next_phase
        # Prevent pathological long games from generating runaway data volume.
        if phase == "start_of_turn" and state.turn_number >= state.max_turns:
            _end_game_on_turn_cap(state)
            break
        # Stalemate detection: if health hasn't changed in _STALEMATE_TURNS turns, end game.
        if phase == "start_of_turn":
            hp = (state.players[1].health, state.players[2].health)
            _stalemate_health_history.append(hp)
            if len(_stalemate_health_history) > _STALEMATE_TURNS:
                _stalemate_health_history.pop(0)
            if (len(_stalemate_health_history) == _STALEMATE_TURNS
                    and len(set(_stalemate_health_history)) == 1):
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
    Called after any resolution, damage, or action application."""
    for pid in state.players:
        if state.players[pid].health <= 0:
            state.done = True
            state.winner = 3 - pid
            state.step = Step.END_GAME
            return True
    return False

# ---------------------------------------------------------------------------
# Start Phase (4.2) — no priority (4.2.1)
# ---------------------------------------------------------------------------

def start_of_turn(state: GameState) -> None:
    """Legacy entry point — starts the game loop."""
    _game_loop(state)


def _start_of_turn_phase(state: GameState) -> None:
    """Start Phase (4.2) — reset per-turn state, emit start_of_turn."""

    state.turn_number += 1
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
    handle_stack(state)
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
        handle_stack(state)
    state.priority_player = state.active_player
    state.consecutive_passes = 0
    priority_loop(state)
    if state.done:
        return

    # --- 7.2 Attack Step ---
    _attack_step(state, attack_card)
    if state.done:
        return

    # --- 7.3 Defend Step ---
    _defend_step(state)
    if state.done:
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

def _attack_step(state: GameState, attack_card: Card) -> None:
    """Attack Step (7.2)."""
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

    # Apply pending turn effects to this attack
    _apply_turn_attack_effects(state, attack_card)

    # 7.2.4: "attack" event — triggers (e.g. Big Bully, Mocking Blow, on_attack_power_bonus)
    # are now queued as StackEntry objects. They resolve during priority_loop below.
    state.event_manager.emit(Event(type='attacking', card=attack_card.slug), state)

    # 7.2.5: turn player gains priority — attack event triggers resolve here
    handle_stack(state)
    state.priority_player = state.active_player
    state.consecutive_passes = 0
    priority_loop(state)

    # Recalculate after priority (triggered power buffs have now resolved)
    _recalculate_attack_power(state.combat)

def _defend_step(state: GameState) -> None:
    """Defend Step (7.3)."""
    state.step = Step.COMBAT_DEFEND

    # 7.3.2: defender declares defending cards (single compound event per 7.3.2d)
    defender_id = 3 - state.active_player
    defend_action = get_player_decision(state, defender_id)
    _apply_defend(state, defend_action)
    state.combat.defending_declared = True

    # 7.3.3: turn player gains priority
    handle_stack(state)
    state.priority_player = state.active_player
    state.consecutive_passes = 0
    priority_loop(state)

def _reaction_step(state: GameState) -> None:
    """Reaction Step (7.4)."""
    state.step = Step.COMBAT_REACTION

    # 7.4.2: turn player gains priority
    handle_stack(state)
    state.priority_player = state.active_player
    state.consecutive_passes = 0
    priority_loop(state)

    # Recalculate after reactions (e.g. Kayo ability, Pummel, attack reactions)
    _recalculate_attack_power(state.combat)

def _damage_step(state: GameState) -> None:
    """Damage Step (7.5)."""
    state.step = Step.COMBAT_DAMAGE

    # 7.5.2: calculate and apply damage
    _resolve_damage(state)
    if state.done:
        return

    # 7.5.3: turn player gains priority
    handle_stack(state)
    state.priority_player = state.active_player
    state.consecutive_passes = 0
    priority_loop(state)

def _resolution_step(state: GameState, _is_root: bool = True) -> None:
    """Resolution Step (7.6)."""
    state.step = Step.COMBAT_RESOLUTION

    # 7.6.2: chain link resolves, go again check
    state.event_manager.emit('chain_link_resolves', state)
    # CR 8.3.5b: Go Again grants +1 AP at Resolution Step.
    # Keywords may appear as "Go again", "Go Again", or "go_again" depending on source.
    if any(k.lower().replace(' ', '_') == 'go_again' for k in state.combat.keywords):
        state.active().action_points += 1

    # 7.6.3: turn player gains priority
    handle_stack(state)
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
            handle_stack(state)
            state.priority_player = state.active_player
            state.consecutive_passes = 0
            priority_loop(state)
            if state.done:
                return

        _attack_step(state, attack_card)
        if state.done:
            return
        _defend_step(state)
        if state.done:
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
        options = list(range(len(player.hand.cards))) + [-1]  # -1 = decline
        choice = player_decision_raw(state, state.active_player, options)
        if choice != -1:
            card = player.hand.cards.pop(choice)
            player.arsenal.add(card)
    _resolve_all_triggers(state)
    if state.done:
        return

    # 4.4.3c: each player moves their pitch zone to bottom of deck (CR 4.4.3c)
    for pid in state.players:
        p = state.players[pid]
        while p.pitch.cards:
            if len(p.pitch.cards) == 1:
                card = p.pitch.cards.pop(0)
                p.deck.add_bottom(card)
            else:
                options = list(range(len(p.pitch.cards)))
                choice = player_decision_raw(state, pid, options)
                card = p.pitch.cards.pop(choice)
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
    _draw_cards(player, cards_to_draw)
    # First turn: non-turn-player also draws up
    if state.turn_number == 1:
        opp = state.inactive()
        opp_draw = max(0, opp.intellect - len(opp.hand.cards))
        _draw_cards(opp, opp_draw)
    _resolve_all_triggers(state)
    if state.done:
        return

    # 4.4.4: turn ends, effects that last "until end of turn" / "this turn" end
    player.current_turn_effects = []
    state.effect_manager.clear_turn_effects()  # CR 4.4.4 / CR 6.2.2a: remove end_of_turn ContinuousEffects
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

def _draw_cards(player: Player, count: int) -> None:
    """Draw up to count cards from deck into hand."""
    for _ in range(count):
        if not player.deck.cards:
            return
        card = player.deck.pop_top()
        if card is not None:
            player.hand.add(card)

def _resolve_all_triggers(state: GameState) -> None:
    """Order and resolve all triggers on the stack without giving players priority."""
    handle_stack(state)
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
            handle_stack(state)

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


def _recalculate_attack_power(combat) -> None:
    """Recalculate attack power from base power + continuous effects on the attack card."""
    card = combat.attack_card
    power = card.base_power or 0
    for effect_type, fn in getattr(card, 'effects', []):
        if effect_type == "base_power":
            power = fn(power)
    for effect_type, fn in getattr(card, 'effects', []):
        if effect_type == "base_power_multiply":
            power = fn(power)
    # CR 8.3.23: Piercing — static ability evaluated fresh each recalculation.
    # Replaces the triggered approach (keywords.py piercing() is now a noop).
    for kw in getattr(card, 'keywords', []):
        if kw.lower().startswith('piercing'):
            parts = kw.split()
            n = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
            if any(c.is_equipment for c in (combat.defending_cards or [])):
                power += n
            break
    combat.attack_power = power

def _resolve_damage(state: GameState) -> None:
    """Damage Step (7.5.2) — calculate and apply damage."""
    combat = state.combat
    defender_id = 3 - combat.attacker_id
    defender = state.players[defender_id]

    # Recalculate attack power from continuous effects before damage
    _recalculate_attack_power(combat)

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
        state.event_manager.emit(Event(type='hit', card=combat.attack_card.slug, data={'damage': net_damage}), state)
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

    # Defending cards: equipment stays, hand cards go to graveyard
    for card in combat.defending_cards:
        state.remember_last_known(card)
        if card.is_equipment:
            pass  # 7.7.5: equipment returns to equipped zone
        else:
            defender.graveyard.add(card)

    # Defense reactions played from arsenal were added to state.combat_chain; move to graveyard now.
    # (attack_card was already removed above, so only reactions remain in the zone at this point.)
    for chain_card in list(state.combat_chain.cards):
        ctrl = chain_card.controller if chain_card.controller is not None else chain_card.owner
        if ctrl in state.players:
            state.remember_last_known(chain_card)
            state.combat_chain.remove(chain_card)
            state.players[ctrl].graveyard.add(chain_card)

def _apply_defend(state: GameState, action: Action) -> None:
    """7.3.2: apply defend declaration — move chosen cards to defending_cards."""
    combat = state.combat
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

    if entry.layer_type == 'card' and card and not _is_figment and not _is_aura:
        game_state.process_cease_to_exist(card)

    if entry.effect_fn:
        result = entry.effect_fn(card, game_state)  # call once — not twice

        if environ['debug'] == 'True':
            with open(environ['debug_file'], 'a') as f:
                f.write(f'stack {entry} resolves: {result}\n')

    # Figments and Auras enter the arena as permanents instead of ceasing to exist.
    if _is_figment or _is_aura:
        player_id = entry.player_id
        player = game_state.players[player_id]
        # Remove from stack zone tracking (triggered layers add here; card layers may not)
        game_state.stack.remove(card)
        # Enter permanents zone
        if "Ally" in _card_types:
            card.permanent_subtype = "Ally"
        player.permanents.add(card, is_public=True)
        # Register triggers for the card now that it's in the arena
        from engine.card_effects.triggers import register_card_triggers
        register_card_triggers(card, game_state.event_manager)
        # Emit enters_arena event so CARD_TRIGGERS can fire
        game_state.event_manager.emit(
            Event(type='enters_arena', data={'card': card, 'player_id': player_id}),
            game_state)

    # CR 5.3.5 / 8.3.5a: non-attack layers with go again grant an action point on resolution.
    # CR 8.5.7b: non-turn-players cannot gain action points — check player is turn-player.
    # (Attack go again is handled separately in _resolution_step via combat.keywords.)
    if card and not entry.is_attack and card.has_go_again:
        if entry.player_id == game_state.active_player:
            game_state.players[entry.player_id].action_points += 1

    game_state.priority_player = game_state.active_player
    game_state.consecutive_passes = 0
    game_state.last_acted_player = None

def handle_stack(game_state: GameState) -> None:
    """Order triggered abilities on the stack (6.6.6b).
    ONLY orders — does NOT resolve. Called once when triggers first appear."""
    if not game_state.stack_entries:
        return

    turn_player_id = game_state.active_player
    opponent_id = 3 - game_state.active_player

    turn_fx = [e for e in game_state.stack_entries if e.player_id == turn_player_id]
    opp_fx = [e for e in game_state.stack_entries if e.player_id == opponent_id]

    if turn_fx and opp_fx:
        goes_first = get_turn_player_choice(game_state)
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
        choice = game_state.player_agents[player_id](game_state, list(range(len(remaining))))
        order.append(remaining.pop(choice))
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
                    handle_stack(state)
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
            handle_stack(state)
            # CR 1.11.5: acting player regains priority after playing/activating
            state.priority_player = current_player

# ---------------------------------------------------------------------------
# Player decisions
# ---------------------------------------------------------------------------

def get_player_decision(state: GameState, player_id: int) -> Action:
    """Get action decision from player agent."""
    legal = legal_actions(state, state.card_db)

    # Forced pass optimization: do not route pass-only decisions through agents.
    # This avoids unnecessary embedder taps/logging for CR-mandated no-op priority passes.
    if len(legal) == 1 and legal[0].type in (ActionType.PASS, ActionType.REACTION_PASS):
        forced = legal[0]
        forced.player_id = player_id
        return forced

    choice = state.player_agents[player_id](state, legal, context='What do you do?')
    if isinstance(choice, Action):
        choice.player_id = player_id
    return choice

def get_turn_player_choice(state: GameState) -> int:
    """Get decision from turn player for which player acts first."""
    choice = state.player_agents[state.active_player](state, ('You', 'Opponent'), 'Who goes first?')
    if choice == 'You':
        return state.active_player
    else:
        return 3 - state.active_player

def player_decision_raw(state: GameState, player_id: int, options, context=None) -> int:
    """Get a raw choice from player agent (index into options list)."""
    choice = state.player_agents[player_id](state, options, context if context else None)
    return choice

# ---------------------------------------------------------------------------
# Apply action
# ---------------------------------------------------------------------------

def apply_action(state: GameState, action: Action) -> None:
    """Apply a player action to the game state."""
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

    # Pitch cards for resources
    if action.pitch_cards:
        pitched_slugs = []
        for c in action.pitch_cards:
            player.hand.remove(c)
            player.pitch.add(c)
            pitched_slugs.append(c.slug)
            player.resources += c.pitch or 0
            state.event_manager.emit(Event(type='card_pitched', data={'card': c, 'pitcher_id': action.player_id}), state)
        state.record_pitch(action.player_id, pitched_slugs)

    # Meld-side-aware resource deduction.
    # Pitch sequences were already generated for the correct effective cost per side.
    _meld_side = getattr(action, 'meld_side', None)
    if _meld_side == 'bottom':
        pass  # bottom side (Shock/Life) is always free
    elif _meld_side == 'both':
        player.resources -= card.meld_cost or 0
    else:
        player.resources -= card.cost or 0  # top, None (instant-speed), or regular card
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

    # CR 3.0.1 / CR 5.3.4c: card enters stack zone
    card.prev_zone = card.zone
    card.zone = 'stack'

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
    state.event_manager.emit(Event(type='on_play', card=card.slug, data={'card': card, 'meld_side': _meld_side}), state)

def _apply_play_arsenal(state: GameState, action: Action) -> None:
    """Play a card from arsenal: pitch from hand for cost, place on stack (CR 3.3.4, CR 5.1.1a)."""
    player = state.players[action.player_id]
    card = action.card
    declared_modes, declared_targets, declared_x = _stack_declarations_from_action(action)

    # Pitch cards for resources (pitched from hand, not from arsenal)
    if action.pitch_cards:
        pitched_slugs = []
        for c in action.pitch_cards:
            player.hand.remove(c)
            player.pitch.add(c)
            pitched_slugs.append(c.slug)
            player.resources += c.pitch or 0
            state.event_manager.emit(Event(type='card_pitched', data={'card': c, 'pitcher_id': action.player_id}), state)
        state.record_pitch(action.player_id, pitched_slugs)

    player.resources -= card.cost or 0
    player.arsenal.remove(card)

    if "Instant" not in (card.types or []):
        player.action_points -= 1

    # CR 3.0.1 / CR 5.3.4c: card enters stack zone
    card.prev_zone = card.zone
    card.zone = 'stack'

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
    state.event_manager.emit(Event(type='on_play', card=card.slug, data={'card': card}), state)

def _apply_play_banish(state: GameState, action: Action) -> None:
    """Play a card from the banish zone (e.g. via Under the Trap-Door trap_door_playable_ flag)."""
    player = state.players[action.player_id]
    card = action.card
    declared_modes, declared_targets, declared_x = _stack_declarations_from_action(action)

    if action.pitch_cards:
        pitched_slugs = []
        for c in action.pitch_cards:
            player.hand.remove(c)
            player.pitch.add(c)
            pitched_slugs.append(c.slug)
            player.resources += c.pitch or 0
            state.event_manager.emit(Event(type='card_pitched', data={'card': c, 'pitcher_id': action.player_id}), state)
        state.record_pitch(action.player_id, pitched_slugs)

    player.resources -= card.cost or 0
    player.banished.remove(card)
    # Consume the playable flag (trap-door or infiltrate)
    for prefix in (f"trap_door_playable_{card.slug}", f"infiltrate_play_{card.slug}"):
        if prefix in player.current_turn_effects:
            player.current_turn_effects.remove(prefix)
        if hasattr(player, 'next_turn_effects') and prefix in player.next_turn_effects:
            player.next_turn_effects.remove(prefix)

    if "Instant" not in (card.types or []):
        player.action_points -= 1

    # CR 3.0.1 / CR 5.3.4c: card enters stack zone
    card.prev_zone = card.zone
    card.zone = 'stack'

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
    state.event_manager.emit(Event(type='on_play', card=card.slug, data={'card': card}), state)

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
            banished = underneath.pop(0)
            player.banished.add(banished)

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

def _apply_ally_attack(state: GameState, action: Action) -> None:
    """Ally attacks (CR 11.0): exhaust the ally, place attack on stack."""
    player = state.players[action.player_id]
    ally_card = action.card

    # Spend one action point
    player.action_points -= 1

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

    # Pitch cards for resources (allies may have resource costs)
    if action.pitch_cards:
        pitched_slugs = []
        for c in action.pitch_cards:
            player.hand.remove(c)
            player.pitch.add(c)
            pitched_slugs.append(c.slug)
            player.resources += c.pitch or 0
            state.event_manager.emit(Event(type='card_pitched', data={'card': c, 'pitcher_id': action.player_id}), state)
        state.record_pitch(action.player_id, pitched_slugs)

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
    """Activate an equipment/item/weapon ability: pitch, pay cost, exhaust, apply effect."""
    from engine.card_effects.registry import EQUIPMENT_ACTIVATION_EFFECTS
    player = state.players[action.player_id]
    card = action.card

    # Pitch cards for resources
    if action.pitch_cards:
        pitched_slugs = []
        for c in action.pitch_cards:
            player.hand.remove(c)
            player.pitch.add(c)
            pitched_slugs.append(c.slug)
            player.resources += c.pitch or 0
            state.event_manager.emit(Event(type='card_pitched', data={'card': c, 'pitcher_id': action.player_id}), state)
        state.record_pitch(action.player_id, pitched_slugs)

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
    """Activate a hero ability: pitch for cost, tap if required, apply effect."""
    from engine.card_effects.registry import HERO_ACTIVATION_CONDITIONS
    player = state.players[action.player_id]

    # Pitch cards for resources
    if action.pitch_cards:
        pitched_slugs = []
        for c in action.pitch_cards:
            player.hand.remove(c)
            player.pitch.add(c)
            pitched_slugs.append(c.slug)
            player.resources += c.pitch or 0
            state.event_manager.emit(Event(type='card_pitched', data={'card': c, 'pitcher_id': action.player_id}), state)
        state.record_pitch(action.player_id, pitched_slugs)

    hero_cfg = HERO_ACTIVATION_CONDITIONS.get(player.hero.slug, {})
    cost_raw = hero_cfg.get("cost", 0)
    cost = cost_raw(player, state) if callable(cost_raw) else cost_raw
    player.resources -= cost

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

    # Pitch cards for resources
    if action.pitch_cards:
        pitched_slugs = []
        for c in action.pitch_cards:
            player.hand.remove(c)
            player.pitch.add(c)
            pitched_slugs.append(c.slug)
            player.resources += c.pitch or 0
            state.event_manager.emit(Event(type='card_pitched', data={'card': c, 'pitcher_id': action.player_id}), state)
        state.record_pitch(action.player_id, pitched_slugs)

    player.resources -= card.cost or 0

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
    state.event_manager.emit(Event(type='on_play', card=card.slug), state)

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