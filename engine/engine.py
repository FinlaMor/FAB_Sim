from __future__ import annotations
import inspect
import re, json
from os import environ
from typing import Callable, Optional
from numpy.random import random

from engine.card import CardDB, Card
from engine.state import GameState, Step, EventManager, Event, Player, CombatState, ChainLink, StackEntry
from engine.deck import load_deck, create_player
from engine.actions import legal_actions, Action, ActionType, get_defendable_cards, can_pay_cost
from engine.effects import EffectManager
from engine.card_effects.triggers import register_card_triggers, register_hero_triggers
from engine.card_effects.costs.effect_costs import KEYWORD_COSTS
from engine.card_effects.costs.alt_costs import ALTERNATE_COSTS
from engine.play import (available_actions, apply_action,
                         _pitch_for_cost, evaluate_play_cost,
                         _apply_play_card, _calculate_resource_cost,
                         _apply_defend)

def new_game(
        p1_deck_path: Optional[str],
        p2_deck_path: Optional[str],
        p1_agent: Callable,
        p2_agent: Callable,
        card_db: CardDB,
        p1_seed: Optional[int] = None,
        p2_seed: Optional[int] = None,
    max_turns: int = 200,
    recorders: Optional[list] = None,
) -> GameState:
    """Create a new game state with the given deck paths and card database."""
    agents = {1: p1_agent, 2: p2_agent}

    if sum([x is None for x in (p1_deck_path, p2_deck_path)]) == 2:
        raise ValueError("At least one deck path must be provided.")

    if max_turns <= 0:
        raise ValueError("max_turns must be > 0")

    if sum([x is None for x in (p1_deck_path, p2_deck_path)]) == 1:
        p1_deck_path = p2_deck_path if p1_deck_path is None else p1_deck_path
        p2_deck_path = p1_deck_path if p2_deck_path is None else p2_deck_path

    # Start of Game CR 4.1

    # Initialize event manager and effect manager
    event_mngr = EventManager()
    effect_mngr = EffectManager()

    p1_deck = load_deck(p1_deck_path, card_db)
    p2_deck = load_deck(p2_deck_path, card_db)

    p1 = create_player(p1_deck, player_id=1, card_db=card_db, seed=p1_seed)
    p2 = create_player(p2_deck, player_id=2, card_db=card_db, seed=p2_seed)

    # Every card in the game must have a DSL definition (JSON under
    # engine/card_effects/json/). Fail fast at game start with the full list
    # of missing implementations rather than mid-game.
    from engine.card_effects.dsl.loader import validate_slugs
    from engine.card_effects.dsl import load_all_cards as _dsl_load_all
    _dsl_load_all()
    _game_slugs = set()
    for _p in (p1, p2):
        _game_slugs.update(c.slug for c in _p.all_cards)
        if _p.hero is not None:
            _game_slugs.add(_p.hero.slug)
    validate_slugs(_game_slugs)

    ## CR 4.1.2 Reveal Heroes - for future code, reveal hero cards to both players then they decide on which cards to include in deck.
    ## For now, pre-sideboard decks in txt files.

    ## CR 4.1.3: Player is selected to decide who goes first
    # Use a seeded RNG for reproducibility when seeds are provided
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

    # Observability: attach recorders BEFORE any setup so they see everything —
    # the coin-flip decision, start-of-game event, opening draws, every step.
    if recorders:
        from engine.recorder import attach as _attach_recorder
        for _rec in recorders:
            _attach_recorder(state, _rec)

    # Register a single dispatcher for keyword static abilities (e.g. Piercing).
    # One permanent listener is cheaper than registering/deregistering per combat.
    _setup_static_ability_listeners(state)

    # Load DSL-defined card effects and register event listeners.
    _setup_dsl_listeners(state)
    _setup_material_statics(state)

    # Player that won coin flip decides who goes first (once at game start)
    if state.step == Step.BEGIN_GAME:
        first_player_chose = get_turn_player_choice(state, 'Who goes first?')
        state.active_player = first_player_chose
        state.priority_player = first_player_chose
        state.step = Step.START_PHASE  # Advance out of BEGIN_GAME so prompt never repeats

    # CR 4.1.4: Players choose arena cards. Placeholder for future implementation.
    # For now, the deck txt files are pre-sideboarded at 5/6 arena cards.

    # CR 4.1.5: Players choose deck cards. Placeholder for future implementation.
    # For now, the deck txt files are pre-sideboarded at 60 deck cards.

    # Register triggers and prevention effects for all public cards (hero, equipment, weapons)
    for player_id in state.players:
        for card in state.players[player_id].public_cards:
            register_card_triggers(card, event_mngr)
            effect_mngr.register_prevention_effects(card, state)
        # Register passive hero triggers from HERO_TRIGGERS
        register_hero_triggers(state.players[player_id].hero, state.players[player_id], event_mngr)

    # Register hero DSL REPLACEMENT abilities (e.g. Victor's fail-clash retry),
    # consulted by the clash keyword function.
    state.clash_fail_retry = {}
    from engine.card_effects.dsl.loader import get_card as _dsl_get_card
    for player_id, _pl in state.players.items():
        _hero = _pl.hero
        if _hero is None:
            continue
        _hdef = _dsl_get_card(_hero.slug)
        if _hdef is None:
            continue
        for _ab in _hdef.abilities:
            if _ab.ability_type.upper() == "REPLACEMENT" and \
                    _ab.params.get("replacement") == "fail_clash_retry":
                state.clash_fail_retry[player_id] = "fail_clash_retry"

    # CR 4.1.5b: Check metastatic abilities for heroes that allows deck cards to start in
    # a different zone ie Fai's pheonix flame, or Dash IE's item.

    # CR 4.1.6: All cards not chosen are put in inventory. Not applicable yet.
    # All cards start in inventory "zone" by default

    # CR 4.1.7: Decks presented to opponent for shuffling. Not applicable.

    # Populate each player's inventory with temporary Reviled attack actions
    # (0 power, 3 defense) so effects that reveal from inventory (e.g. Outside
    # Interference) have targets. The sim does not yet sideboard from decks.
    _populate_reviled_inventory(state)

    # CR 4.1.8: Cards are equipped. Any cards to be put in different zones are put there. "start of game" event fires.
    # Start of game event — no priority
    event_mngr.emit('start_of_game', state)
    _resolve_all_triggers(state)

    # CR 4.1.9: Both players draw up to their intellect and the first-turn player begins their first turn.
    _draw_cards(p1, p1.intellect)
    _draw_cards(p2, p2.intellect)

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

    from engine.recorder import notify as _rec_notify
    _rec_notify(state, 'on_game_start')

    # Run the game loop
    _game_loop(state)

    return state

def _end_game_on_turn_cap(state: GameState) -> None:
    """Terminate a game that has reached its configured turn cap.

    Winner is determined by life total if one player has 30 more life than another; <30 life difference is recorded as a draw.
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
    # Listeners are automatically cleared with game teardown in this flow.
    # Guard against missing local dispatcher reference.
    _listeners = getattr(state, "_static_listeners", []) or []
    for event_name in _listeners:
        try:
            if hasattr(state.event_manager, "listeners") and event_name in state.event_manager.listeners:
                state.event_manager.listeners[event_name] = []
        except Exception:
            pass


def _game_loop(state: GameState) -> None:
    """Iterative main game loop — avoids deep recursion from turn/combat cycling."""
    state._next_phase = "start_of_turn"

    while not state.done:
        phase = state._next_phase
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

    if state.done and getattr(state, 'recorders', None):
        from engine.recorder import notify as _rec_notify
        _rec_notify(state, 'on_game_end')

# ---------------------------------------------------------------------------
# State-based actions (checked continuously)
# ---------------------------------------------------------------------------

def check_state_based_actions(state: GameState) -> bool:
    """Check state-based actions. Returns True if game has ended.
    Called after any resolution, damage, or action application.

    CR 1.10.2b: Living objects (heroes and allies) with 0 or less life are
    destroyed simultaneously, then triggers from those deaths are ordered.
    """
    from engine.effect_keywords import destroy as _ek_destroy

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
        _ek_destroy(state, ally, None)

    if dead_allies:
        _resolve_all_triggers(state)
        if state.done:
            return True

    return False

def start_of_turn_refresh_player(state: GameState, playerid: int):
    """Restore player defaults for assets, once-per-turn effects, etc.
    """
    player = state.players[playerid]

    # "until the start of your next turn" grants (e.g. trap_door's banished
    # trap) expire at the start of this player's turn.
    player.playable_from_banished = []

    # Weapons ready at the start of the turn (CR 4.4.3d).
    player.weapon_exhausted = False

    # "if you've controlled a <thing> this turn" must count what you ALREADY
    # control when the turn begins, not only what entered during it. Zone.add
    # records arena entries, but a permanent that survived from a previous turn
    # never re-enters, so without this sweep the commonest case — the token has
    # simply been sitting there — would read as "you controlled nothing".
    from engine.effect_keywords import record_turn_event_for_player
    for card in player.arena_cards:
        record_turn_event_for_player(
            player, "controlled",
            getattr(card, "slug", None),
            getattr(card, "name", None),
            getattr(card, "types", None) or [],
            getattr(card, "subtypes", None) or [],
        )

    for card in player.arena_cards:
        if getattr(card, 'has_per_turn_limit'):
            setattr(card, 'activations', card.base_activations)

    setattr(player, 'resources', 0)
    setattr(player, 'chi', 0)
    setattr(player, 'action_points', 0)

    assert len(player.pitch.cards) == 0  # pitched cards already moved to deck bottom in end phase

    

# ---------------------------------------------------------------------------
# Start Phase (4.2) — no priority (4.2.1)
# ---------------------------------------------------------------------------

def _start_of_turn_phase(state: GameState) -> None:
    """Start Phase (4.2) — reset per-turn state, emit start_of_turn."""

    state.individual_turns += 1
    state.turn_number = (state.individual_turns - 1) // 2 # Turn 0 is drastically different from the rest of the game since BOTH players draw up at end phase.
    state.events_this_turn = set()
    player = state.active()

    # Refresh all X-per-turn activations for each player. Set assets to 0.
    start_of_turn_refresh_player(state, 1)
    start_of_turn_refresh_player(state, 2)

    # Rotate turn effects
    player.current_turn_effects = player.next_turn_effects[:]
    player.next_turn_effects = []
    # Rotate turn-scoped attack hooks (NEXT_TURN -> active this turn).
    player.turn_attack_hooks = player.next_turn_attack_hooks[:]
    player.next_turn_attack_hooks = []
    player.attacks_this_turn = 0

    # Clear equipment-defended tracking (safety net)
    player.equipment_defended_this_turn = []

    # Clear combat chain link history
    state.chain_links = []

    # Clear current turn counters
    state.active().current_turn_counters = []
    state.inactive().current_turn_counters = []

    # Clear cards played this turn
    player.cards_played_this_turn = []

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
    attack_card = attack_entry.card

    # --- 7.1 Layer Step ---
    state.step = Step.COMBAT_LAYER
    # CR 7.1.3: the attack REMAINS on the stack as the bottom layer during the
    # Layer Step; the step ends when it is the top layer and all players pass.
    # It is removed by _attack_step (7.2.3), not here, so effects that inspect
    # the stack can see it. priority_loop's only_attack branch handles the case
    # where it is the sole remaining layer.
    # 7.1.2: turn player unconditionally gains priority in the Layer Step.
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

def _consume_attack_entry(state: GameState, entry: Optional[StackEntry] = None) -> None:
    """Take the attack layer off the stack (CR 3.15.6).

    The attack stays on the stack as the bottom layer through the Layer Step so
    it is visible to effects that inspect the stack (negate target attack,
    layer counting) and new layers can be ordered above it (CR 7.1.3, 3.15.4-5).
    It leaves when the Attack Step moves it to the combat chain, or when the
    chain closes early — leaving it behind would send _continue_action_phase
    straight back into the combat phase.
    """
    if entry is not None and entry in state.stack_entries:
        state.stack_entries.remove(entry)
        return
    for e in [e for e in state.stack_entries if e.is_attack]:
        state.stack_entries.remove(e)


def _attack_step(state: GameState, attack_card: Card, entry: Optional[StackEntry] = None) -> None:
    """Attack Step (7.2)."""

    if state.done:
        return

    state.step = Step.COMBAT_ATTACK

    # CR 7.2.2: at least one declared attack-target must still be legal,
    # otherwise the Attack Step ends and the Close Step begins. No declared
    # target means the attack targets the defending hero, which always exists.
    _declared = list(getattr(entry, 'declared_targets', None) or []) if entry else []
    _resolved_target = None
    if _declared:
        _target_slug = _declared[0]
        _defender = state.players[3 - state.active_player]
        _resolved_target = _defender.permanents.find(_target_slug)
        if _resolved_target is None:
            # Also check attacker's own permanents (edge cases like self-targeting)
            _resolved_target = state.players[state.active_player].permanents.find(_target_slug)
        if _resolved_target is None:
            # Declared target left the arena — CR 7.7.3: the attack on the
            # stack is put into its owner's graveyard and the chain closes.
            _consume_attack_entry(state, entry)
            state.stack.remove(attack_card)
            _owner = state.players.get(attack_card.owner)
            if _owner is not None and not attack_card.is_weapon:
                _owner.graveyard.add(attack_card, is_public=True)
            _close_step(state)
            return

    # 7.2.3: attack moves to combat chain as chain link
    # CR 1.3.1b / 7.0.3c: the attacker controls the active attack (covers weapon
    # attack-proxies, whose card was never "played" from hand).
    attack_card.controller = state.active_player
    _consume_attack_entry(state, entry)
    state.stack.remove(attack_card)  # leaves the stack zone (CR 3.15.6)
    state.combat_chain.add(attack_card)
    state.combat = CombatState(
        attacker_id=state.active_player,
        link_id=len(state.chain_links) + 1,
        attack_power=attack_card.power or 0,
        base_attack_power=attack_card.base_power or 0,
        from_weapon=attack_card.is_weapon,
        attack_card=attack_card,
        keywords=list(attack_card.keywords),
        pitched_for_attack=list(getattr(entry, 'pitched_for_attack', None) or []) if entry else [],
    )

    # Card target resolved from declared_targets above (e.g. a Spectra aura).
    if _resolved_target is not None:
        state.combat.attack_target_card = _resolved_target
        state.combat.attack_target = state.players[3 - state.active_player]

    # Count this attack for ordinal conditions ("your second attack each turn").
    state.players[state.combat.attacker_id].attacks_this_turn += 1

    # Apply pending turn effects to this attack (may append to attack_card.effects)
    _apply_turn_attack_effects(state, attack_card)

    # Register card.effects as staged ContinuousEffects (CR 6.3 stages 7-8)
    _register_card_continuous_effects(state, attack_card)

    # Register keyword triggers for this attack card (e.g. Phantasm "defend" listener).
    # Attack action cards are not public at game start so their triggers are not registered
    # at new_game time. Register them now when the card enters combat so keyword triggers fire.
    register_card_triggers(attack_card, state.event_manager)

    # CR 7.2.3: the attack's resolution abilities (its PLAY-typed DSL abilities)
    # generate their effects as the attack resolves onto the combat chain.
    from engine.card_effects.dsl import dispatch as _dsl_dispatch
    _dsl_dispatch(state, "ON_PLAY", attack_card.slug, card=attack_card,
                  event=Event(type='on_play', card=attack_card.slug,
                              data={'card': attack_card,
                                    'meld_side': getattr(attack_card, 'meld_side', None),
                                    'target': (entry.declared_targets[0]
                                               if entry and entry.declared_targets else None)}))

    # 7.2.4: "attack" event — triggers (e.g. Big Bully, Mocking Blow, on_attack_power_bonus)
    # are now queued as StackEntry objects. They resolve during priority_loop below.
    # 'attacking' fires for any attack (weapon, attack action card, or ally).
    # 'attacking_hero' fires only when the attack targets the hero (attack_target is None = default hero target).
    # 'target_of_attack' fires when attack has a specific card target (e.g. Spectra aura).
    # "if you've attacked with a weapon this turn" / "attacked twice with
    # weapons" — recorded per attack so the count forms work, qualified by
    # whether it came from a weapon and by the attack's own identity.
    from engine.effect_keywords import _record_turn_event as _rec_turn
    _rec_turn(state, state.combat.attacker_id, "attack",
              "weapon" if state.combat.from_weapon else "nonweapon",
              getattr(attack_card, "slug", None),
              getattr(attack_card, "subtypes", None) or [],
              getattr(attack_card, "classes", None) or [],
              getattr(attack_card, "talents", None) or [])

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
    # Spinal Crush (WTR): suppress go again for the affected player's attacks this turn.
    if (any(re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', k).lower() == 'go again' for k in state.combat.keywords)
            and "cant_go_again" not in state.active().current_turn_effects):
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
        attack_card = attack_entry.card

        # New chain link starts from Layer Step. As above (CR 7.1.3) the attack
        # stays on the stack until _attack_step consumes it.
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

    # Safety net: the chain can close before the Attack Step consumes the
    # attack layer (e.g. Phantasm during the Layer Step). A leftover attack
    # entry would send _continue_action_phase straight back into combat.
    _consume_attack_entry(state)

    # 7.7.3: combat chain closes event
    state.event_manager.emit('combat_chain_close', state)

    # 7.7.4: triggers resolve without priority
    _resolve_all_triggers(state)

    # 7.7.5: permanents return to their zones
    # 7.7.6: remaining objects on combat chain are cleared
    _close_combat_chain(state)

    # Combat-chain-scoped attack hooks ("... this combat chain ...") expire now,
    # and so does the chain-scoped boost tally.
    for _p in state.players.values():
        _p.chain_attack_hooks = []
        _p.boosts_this_chain = 0

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

    # 4.4.3a: ALL allies' life totals reset to base (CR 4.4.3a — every player's allies)
    for _pid in state.players:
        for ally_card in state.players[_pid].allies.cards:
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
        state.pitch_history[pid][state.turn_number] = list(state.players[pid].pitch.cards)
        while p.pitch.cards:
            if len(p.pitch.cards) == 1:
                card = p.pitch.cards.pop(0)
                p.pitch_history.append(card)
                p.deck.add_bottom(card)
            else:
                options = [Action(type=ActionType.CHOOSE, card=c) for c in p.pitch.cards]
                choice = state.player_agents[pid](state, options, 'Choose next card for bottom of deck')
                if isinstance(choice, Action):
                    choice.player_id = pid
                card = choice.card
                if card is None:
                    card = p.pitch.cards[0]
                p.pitch_history.append(card)
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
        state.players[pid].chi = 0
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
    # Turn-scoped attack hooks created this turn expire now. (NEXT_TURN hooks live
    # on next_turn_attack_hooks and are untouched here — they activate at the
    # target player's turn start above.)
    player.turn_attack_hooks = []
    # Safety net: chain hooks normally clear at chain close; drop any that outlived
    # an unclosed chain into this turn's end. Same for the chain boost tally.
    player.chain_attack_hooks = []
    player.boosts_this_chain = 0
    player.life_gained_this_turn = 0
    player.damage_dealt_this_turn = {}
    # Unused "next attack this turn" power mods (MODIFY_NEXT_ATTACK) expire.
    if hasattr(player, 'dsl_queued_attack_mods'):
        player.dsl_queued_attack_mods = []
    # Unused "the next <card> you play this turn costs less" reductions expire
    # with the turn, exactly like the attack mods above.
    if hasattr(player, 'dsl_queued_cost_mods'):
        player.dsl_queued_cost_mods = []
    # "this turn" DSL continuous effects (APPLY_CONTINUOUS, e.g. Night's Embrace).
    if getattr(player, 'dsl_continuous_effects', None):
        player.dsl_continuous_effects = [
            ce for ce in player.dsl_continuous_effects if ce.get('span') != 'THIS_TURN']
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
        count_before = len(state.stack_entries)
        resolve_stack(state)
        if check_state_based_actions(state):
            return
        # Only re-order if new triggers arrived during resolution.
        # After one pop, count_before - 1 entries remain; more means new entries were added.
        if len(state.stack_entries) > count_before - 1:
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

    # DSL: handle next/all attack bonus flags from effect_types.py.
    import re as _re
    pid = state.active_player

    # One-shot: "next_attack_hit_draw_N" — inject ON_HIT draw, then consume.
    for key in [k for k in player.current_turn_effects
                if _re.match(r'^next_attack_hit_draw_(\d+)$', k)]:
        n = int(_re.match(r'^next_attack_hit_draw_(\d+)$', key).group(1))
        from engine.card_effects.triggers import TriggerDef
        def _hit_draw_once(c, ev, st, _n=n, _pid=pid):
            from engine.card_effects.ability_keywords import effect_draw
            effect_draw(st, _pid, _n)
        td = TriggerDef(event_type="ON_HIT", condition_fn=None,
                        effect_fn=_hit_draw_once, is_optional=False)
        if not hasattr(state.combat, 'injected_triggers'):
            state.combat.injected_triggers = []
        state.combat.injected_triggers.append(td)
        player.current_turn_effects.remove(key)

    # One-shot: "next_marked_dagger_hit_draw_N" — draw when the next dagger attack
    # hits a marked hero this turn (Savor Bloodshed). Consumed only on a qualifying
    # (dagger vs marked) attack.
    for key in [k for k in player.current_turn_effects
                if _re.match(r'^next_marked_dagger_hit_draw_(\d+)$', k)]:
        is_dagger = 'dagger' in [s.lower() for s in (getattr(attack_card, 'subtypes', None) or [])]
        defender = state.players[3 - state.active_player]
        if is_dagger and defender.class_counters.get("marked", 0) > 0:
            n = int(_re.match(r'^next_marked_dagger_hit_draw_(\d+)$', key).group(1))
            from engine.card_effects.triggers import TriggerDef
            def _md_hit_draw(c, ev, st, _n=n, _pid=pid):
                from engine.card_effects.ability_keywords import effect_draw
                effect_draw(st, _pid, _n)
            td = TriggerDef(event_type="ON_HIT", condition_fn=None,
                            effect_fn=_md_hit_draw, is_optional=False)
            if not hasattr(state.combat, 'injected_triggers'):
                state.combat.injected_triggers = []
            state.combat.injected_triggers.append(td)
            player.current_turn_effects.remove(key)

    # Persistent: "all_attacks_+N" — apply power bonus every attack, keep flag.
    from engine.card_effects.registry import CardEffect
    for key in player.current_turn_effects:
        m = _re.match(r'^all_attacks_\+(\d+)$', key)
        if m:
            n = int(m.group(1))
            attack_card.effects = list(getattr(attack_card, 'effects', []))
            attack_card.effects.append(
                CardEffect(prop="power", stage=7, substage=5,
                           fn=lambda val, _n=n: val + _n))


    # Persistent: "all_attacks_hit_draw_N" — inject ON_HIT draw every attack, keep flag.
    for key in player.current_turn_effects:
        m = _re.match(r'^all_attacks_hit_draw_(\d+)$', key)
        if m:
            n = int(m.group(1))
            from engine.card_effects.triggers import TriggerDef
            def _all_hit_draw(c, ev, st, _n=n, _pid=pid):
                from engine.card_effects.ability_keywords import effect_draw
                effect_draw(st, _pid, _n)
            td = TriggerDef(event_type="ON_HIT", condition_fn=None,
                            effect_fn=_all_hit_draw, is_optional=False)
            if not hasattr(state.combat, 'injected_triggers'):
                state.combat.injected_triggers = []
            state.combat.injected_triggers.append(td)

    # One-shot: "next_weapon_attack_+N" — apply +N to next weapon attack only.
    is_weapon_atk = getattr(attack_card, 'is_weapon', False) or (
        state.combat and getattr(state.combat, 'from_weapon', False))
    for key in [k for k in player.current_turn_effects
                if _re.match(r'^next_weapon_attack_\+(\d+)$', k)]:
        if is_weapon_atk:
            n = int(_re.match(r'^next_weapon_attack_\+(\d+)$', key).group(1))
            attack_card.effects = list(getattr(attack_card, 'effects', []))
            attack_card.effects.append(
                CardEffect(prop="power", stage=7, substage=5,
                           fn=lambda val, _n=n: val + _n))
        player.current_turn_effects.remove(key)

    # Persistent: "all_weapon_attacks_+N" — weapon-only power bonus every attack, keep flag.
    for key in player.current_turn_effects:
        m = _re.match(r'^all_weapon_attacks_\+(\d+)$', key)
        if m and is_weapon_atk:
            n = int(m.group(1))
            attack_card.effects = list(getattr(attack_card, 'effects', []))
            attack_card.effects.append(
                CardEffect(prop="power", stage=7, substage=5,
                           fn=lambda val, _n=n: val + _n))

    # One-shot: "next_weapon_attack_go_again" — grant go again on next weapon attack.
    if "next_weapon_attack_go_again" in player.current_turn_effects:
        if is_weapon_atk and state.combat:
            state.combat.grant_keyword("go_again")
        player.current_turn_effects.remove("next_weapon_attack_go_again")

    # One-shot: "next_weapon_attack_hit_go_again" — inject ON_HIT go_again for next weapon attack.
    if "next_weapon_attack_hit_go_again" in player.current_turn_effects:
        if is_weapon_atk and state.combat:
            from engine.card_effects.triggers import TriggerDef
            def _weapon_hit_ga(c, ev, st):
                if st.combat:
                    st.combat.grant_keyword("go_again")
            td = TriggerDef(event_type="ON_HIT", condition_fn=None,
                            effect_fn=_weapon_hit_ga, is_optional=False)
            if not hasattr(state.combat, 'injected_triggers'):
                state.combat.injected_triggers = []
            state.combat.injected_triggers.append(td)
        player.current_turn_effects.remove("next_weapon_attack_hit_go_again")

    # One-shot: "next_low_cost_attack_+N" — apply +N to next cost≤1 attack only.
    atk_cost = getattr(attack_card, 'cost', None) or getattr(attack_card, 'raw_cost', None) or 0
    for key in [k for k in player.current_turn_effects
                if _re.match(r'^next_low_cost_attack_\+(\d+)$', k)]:
        if atk_cost <= 1:
            n = int(_re.match(r'^next_low_cost_attack_\+(\d+)$', key).group(1))
            attack_card.effects = list(getattr(attack_card, 'effects', []))
            attack_card.effects.append(
                CardEffect(prop="power", stage=7, substage=5,
                           fn=lambda val, _n=n: val + _n))
        player.current_turn_effects.remove(key)

    # One-shot: "next_high_cost_attack_+N" — apply +N to next cost≥2 attack only.
    for key in [k for k in player.current_turn_effects
                if _re.match(r'^next_high_cost_attack_\+(\d+)$', k)]:
        if atk_cost >= 2:
            n = int(_re.match(r'^next_high_cost_attack_\+(\d+)$', key).group(1))
            attack_card.effects = list(getattr(attack_card, 'effects', []))
            attack_card.effects.append(
                CardEffect(prop="power", stage=7, substage=5,
                           fn=lambda val, _n=n: val + _n))
        player.current_turn_effects.remove(key)

    # Debilitate (WTR): "their first attack during their next turn gets -2{p}."
    # Consumed once, on the first attack of the affected player's turn.
    if "first_attack_-2p" in player.current_turn_effects:
        attack_card.effects = list(getattr(attack_card, 'effects', []))
        attack_card.effects.append(
            CardEffect(prop="power", stage=7, substage=5,
                       fn=lambda val: val - 2))
        player.current_turn_effects.remove("first_attack_-2p")

    # DSL MODIFY_NEXT_ATTACK queue (e.g. Awakening Bellow, Nimblism): each entry is
    # {"mod": "add", "amount": N, "filter": [<condition specs>]}. Apply the power mod
    # to the first attack matching the filter, then consume that entry. state.combat
    # already holds this attack, so the DSL ATTACK_* condition compilers evaluate it.
    queued = getattr(player, 'dsl_queued_attack_mods', None)
    if queued:
        from engine.card_effects.dsl.condition_types import compile_condition as _cc
        remaining = []
        for mod in queued:
            matches = True
            for spec in mod.get('filter', []):
                fn = _cc(spec.get('type', 'none'), spec)
                if fn is not None and not fn(attack_card, None, state):
                    matches = False
                    break
            if matches and mod.get('mod', 'add') == 'add':
                amt = mod.get('amount', 0)
                attack_card.effects = list(getattr(attack_card, 'effects', []))
                attack_card.effects.append(
                    CardEffect(prop="power", stage=7, substage=5,
                               fn=lambda val, _n=amt: val + _n))
                # consumed — not re-added to remaining
            elif matches and mod.get('mod') == 'grant_keyword':
                # "your NEXT attack this turn gets go again" — one-shot, so it
                # is consumed here. Authored as a turn-long flag plus a
                # flag-gated static, it would buff every attack for the rest of
                # the turn instead, which is worse than granting nothing.
                kw = mod.get('keyword') or ''
                if kw and state.combat is not None and attack_card is state.combat.attack_card:
                    if kw not in (state.combat.keywords or []):
                        state.combat.grant_keyword(kw)
                    # consumed
                else:
                    # No live combat to grant onto — keep it for the real attack.
                    remaining.append(mod)
            elif matches and mod.get('mod') == 'set_base':
                # "the next attack action card you play this turn has N base
                # {p}" (Chain of Brutality). Setting base power leaves later
                # +{p} modifiers to apply on top of it, same as SET_BASE_POWER.
                amt = mod.get('amount', 0)
                attack_card.base_power = amt
                if state.combat is not None and attack_card is state.combat.attack_card:
                    state.combat.base_attack_power = amt
                # consumed
            else:
                remaining.append(mod)
        player.dsl_queued_attack_mods = remaining

    # Turn-scoped attack hooks (DSL INJECT_TRIGGER scope=TURN/NEXT_TURN, turn-scoped
    # power mods). Re-applied to EVERY attack this turn; the hooks themselves are NOT
    # consumed here — they expire via the end-of-turn clear / next-turn rotation in
    # begin_turn / end phase. Specs are plain dicts (see state.Player.turn_attack_hooks)
    # compiled on demand so snapshots stay serializable.
    hooks = (list(getattr(player, 'turn_attack_hooks', None) or [])
             + list(getattr(player, 'chain_attack_hooks', None) or []))
    if hooks:
        from engine.card_effects.dsl.condition_types import compile_condition as _cc
        from engine.card_effects.dsl.effect_types import compile_effect as _ce
        from engine.card_effects.triggers import TriggerDef
        for hook in hooks:
            kind = hook.get('kind')
            cond_specs = hook.get('conditions', [])
            if kind == 'power_mod':
                cond_fns = [_cc(c.get('type', 'none'), c) for c in cond_specs]
                if all(fn is None or fn(attack_card, None, state) for fn in cond_fns):
                    amt = hook.get('amount', 0)
                    attack_card.effects = list(getattr(attack_card, 'effects', []))
                    attack_card.effects.append(
                        CardEffect(prop="power", stage=7, substage=5,
                                   fn=lambda val, _n=amt: val + _n))
            elif kind == 'inject_trigger' and state.combat is not None:
                event_type = hook.get('event', 'ON_HIT')
                src_slug = hook.get('source_slug', '?')
                cond_fns = [_cc(c.get('type', 'none'), c) for c in cond_specs]
                eff_fns = [((e.get('type') or '').upper(),
                            _ce((e.get('type') or '').upper(), e))
                           for e in hook.get('effects', [])]

                def _hook_fire(c, ev, st, _cf=cond_fns, _ef=eff_fns, _src=src_slug):
                    from engine.card_effects.dsl.effect_types import _track_injected_effect
                    for fn in _cf:
                        if fn is not None and not fn(c, ev, st):
                            return
                    for et, ef in _ef:
                        ef(c, ev, st)
                        _track_injected_effect(_src, et)

                td = TriggerDef(event_type=event_type, condition_fn=None,
                                effect_fn=_hook_fire, is_optional=False)
                if not hasattr(state.combat, 'injected_triggers'):
                    state.combat.injected_triggers = []
                state.combat.injected_triggers.append(td)


def _populate_reviled_inventory(state: GameState) -> None:
    """Put three temporary Reviled attack actions (0 power, 3 defense) in each
    player's inventory (CR 4.1.6) as targets for reveal-from-inventory effects
    (e.g. Outside Interference). The sim does not yet sideboard from decks."""
    from engine.card import Card
    for pid, player in state.players.items():
        for _ in range(3):
            c = Card(slug="reviled", raw_name="Reviled",
                     raw_types=["Action", "Reviled"], raw_power=0, raw_defense=3)
            c.types = ["Action", "Reviled"]
            c.subtypes = ["Attack"]
            c.power = 0; c.base_power = 0
            c.defense = 3; c.base_defense = 3
            c.owner = pid; c.controller = pid
            player.inventory.add(c)


def _setup_material_statics(state: GameState) -> None:
    """Register the two DERIVED continuous effects that implement Material.

    CR 3.0.14 / the **Material** keyword: "While this is under a permanent, that
    permanent has <property>". These are registered once per game and never
    removed, because they carry no card-specific state — each simply asks the
    card what is under it RIGHT NOW (ability_keywords.material_grants) and
    applies whatever those sub-cards declare in their own JSON.

    Registering-on-arrival was the obvious alternative and is wrong: it would
    need every path by which a sub-card stops being underneath to unregister the
    grant, and missing one leaves a permanent with phantasm it should not have.
    Deriving makes "while" true by construction — the grant cannot outlive the
    relationship it is read from.

    Stage 6 is the keyword stage and stages 7-8 the numeric ones, matching where
    _recalculate_attack_power already consults the manager, so nothing else has
    to change to see these.
    """
    from engine.card_effects.ability_keywords import material_grants
    from engine.continuous_effects import ContinuousEffect, next_timestamp

    def _keywords(value, st, card):
        granted = [g.get("keyword") for g in material_grants(card) if g.get("keyword")]
        if not granted:
            return value
        # `value` is a set at stage 6 but a list elsewhere; preserve whichever.
        if isinstance(value, set):
            return value | set(granted)
        out = list(value or [])
        return out + [k for k in granted if k not in out]

    def _power(value, st, card):
        bonus = 0
        for grant in material_grants(card):
            try:
                bonus += int(grant.get("power", 0) or 0)
            except (TypeError, ValueError):
                continue
        return (value or 0) + bonus if bonus else value

    state.continuous_effect_manager.add(ContinuousEffect(
        stage=6, substage=0, timestamp=next_timestamp(), prop='keywords',
        apply_fn=_keywords, persistent=True, source_slug='__material__'))
    state.continuous_effect_manager.add(ContinuousEffect(
        stage=7, substage=1, timestamp=next_timestamp(), prop='power',
        apply_fn=_power, persistent=True, source_slug='__material__'))


def _setup_dsl_listeners(state: GameState) -> None:
    """Load DSL card definitions and register event listeners that call dispatch().

    This is additive — existing Python CARD_TRIGGERS still fire for cards not
    yet migrated to JSON.  Once a card has a JSON file, both systems run; the
    Python triggers should be removed as part of Step 4/5.
    """
    from engine.card_effects.dsl import load_all_cards, dispatch

    load_all_cards()

    def _dsl_hit_listener(event, game_state: GameState) -> None:
        combat = game_state.combat
        if not combat or not combat.attack_card:
            return
        slug = combat.attack_card.slug
        # Fire DSL ON_HIT abilities for the attack card
        dispatch(game_state, "ON_HIT", slug,
                 card=combat.attack_card, event=event)
        # Fire and consume injected_triggers (e.g. created by INJECT_TRIGGER / Pummel)
        remaining = []
        for td in combat.injected_triggers:
            if td.event_type != "ON_HIT":
                remaining.append(td)
                continue
            cond_ok = td.condition_fn is None or td.condition_fn(
                combat.attack_card, event, game_state)
            if cond_ok:
                td.effect_fn(combat.attack_card, event, game_state)
            # consumed=True: drop after firing; keep if condition failed? Drop anyway.
        combat.injected_triggers = remaining
        # CR 8.4.2: Crush — fire ON_CRUSH abilities when this dealt 4+ damage.
        from engine.card_effects.ability_keywords import crush_check
        if crush_check(event, game_state):
            dispatch(game_state, "ON_CRUSH", slug,
                     card=combat.attack_card, event=event)
        # Hero passives that react to their controller's attack hitting
        # (e.g. Arakni's stealth-vs-marked "go again" grant). Pass the hero as
        # context so _controller_id resolves to the hero's owner; ATTACK_*
        # conditions read state.combat directly, and keyword grants act on it.
        attacker = game_state.players[combat.attacker_id]
        if attacker.hero is not None:
            dispatch(game_state, "ON_HIT", attacker.hero.slug,
                     card=attacker.hero, event=event)
        # Equipment/permanents the attacker controls that react to "when an attack
        # you control hits" (e.g. Aether Crackers: destroy this, deal 1 arcane).
        # The attack card and hero fired above; dispatch to the rest so their
        # ON_HIT abilities can trigger. dispatch() no-ops on cards without a
        # matching ON_HIT ability, so this is safe to broadcast.
        seen = {id(combat.attack_card)}
        if attacker.hero is not None:
            seen.add(id(attacker.hero))
        for zone in _dsl_permanent_zones(attacker):
            for perm in list(zone.cards):
                if id(perm) in seen:
                    continue
                seen.add(id(perm))
                dispatch(game_state, "ON_HIT", perm.slug, card=perm, event=event)

    def _dsl_permanent_zones(player):
        # Permanents plus equipment/weapon slot zones and the hero, so
        # START_OF_TURN / END_OF_TURN abilities on any of them (Fyendal's Spring
        # Tunic, Arakni's end-phase transform) fire via the DSL.
        return (player.permanents, player.items, player.auras, player.allies,
                player.tokens,
                player.head, player.chest, player.arms, player.legs,
                player.weapon1, player.weapon2, player.hero_zone)

    def _dsl_start_of_turn_listener(event, game_state: GameState) -> None:
        # "At the start of your turn" — only the turn player's permanents/equipment fire.
        player = game_state.active()
        for zone in _dsl_permanent_zones(player):
            for card in list(zone.cards):
                dispatch(game_state, "START_OF_TURN", card.slug, card=card)
        # "While this is in your graveyard, at the start of your turn …" — a
        # separate event so only graveyard-static abilities respond (Blacktek
        # Whisperers), never arena statics whose card happens to be in the yard.
        for card in list(player.graveyard.cards):
            dispatch(game_state, "START_OF_TURN_IN_GRAVEYARD", card.slug, card=card)

    def _dsl_end_of_turn_listener(event, game_state: GameState) -> None:
        # "At the end of your turn" — only the turn player's permanents/equipment fire.
        player = game_state.active()
        for zone in _dsl_permanent_zones(player):
            for card in list(zone.cards):
                dispatch(game_state, "END_OF_TURN", card.slug, card=card)

    def _dsl_start_of_end_phase_listener(event, game_state: GameState) -> None:
        # "At the beginning of the end phase" — fires for BOTH players' permanents
        # (unlike END_OF_TURN, which is turn-player-scoped for "at end of your
        # turn"). Needed for e.g. Quickdodge Flexors, which defends on the
        # opponent's turn and destroys itself at that turn's end phase.
        for pid in list(game_state.players):
            for zone in _dsl_permanent_zones(game_state.players[pid]):
                for card in list(zone.cards):
                    dispatch(game_state, "BEGINNING_OF_END_PHASE", card.slug, card=card)

    # NOTE: there is deliberately no 'on_play' → dispatch("ON_PLAY") listener.
    # A card's own resolution abilities run when its layer resolves (CR 5.3.4):
    # play.py sets StackEntry.effect_fn for non-attack card layers, and
    # _attack_step dispatches ON_PLAY for attacks (CR 7.2.3).
    # (_dsl_card_played_listener below DOES listen on 'on_play', but dispatches
    # ON_CARD_PLAYED to the player's HERO — hero text about the act of playing a
    # card. It never dispatches ON_PLAY to the played card, so the rule above
    # still holds.)

    def _dsl_start_of_action_phase_listener(event, game_state: GameState) -> None:
        # "At the beginning of your action phase" (CR 4.3.1) — distinct from the
        # start of the TURN, which is the start phase and happens earlier. The
        # engine already emitted this event; nothing dispatched it to the DSL, so
        # a card with this timing had no trigger to use.
        player = game_state.active()
        for zone in _dsl_permanent_zones(player):
            for card in list(zone.cards):
                dispatch(game_state, "START_OF_ACTION_PHASE", card.slug, card=card)

    def _dsl_attacking_listener(event, game_state: GameState) -> None:
        combat = game_state.combat
        if not combat or not combat.attack_card:
            return
        slug = event.card
        dispatch(game_state, "ON_ATTACK", slug, card=combat.attack_card, event=event)

    def _dsl_pitch_listener(event, game_state: GameState) -> None:
        # "When this is pitched" — e.g. Riches of Trōpal-Dhani creates a Gold.
        card_obj = event.data.get('card') if isinstance(event.data, dict) else None
        if card_obj is None:
            return
        dispatch(game_state, "ON_PITCH", card_obj.slug, card=card_obj, event=event)

    def _dsl_start_of_game_listener(event, game_state: GameState) -> None:
        # "When you equip …" for starting equipment fires as the game begins
        # (CR 4.1.8). Dispatch ON_EQUIP to each player's equipped cards.
        for player in game_state.players.values():
            for zone in (player.head, player.chest, player.arms, player.legs,
                         player.weapon1, player.weapon2):
                for eq in list(zone.cards):
                    dispatch(game_state, "ON_EQUIP", eq.slug, card=eq, event=event)

    def _dsl_combat_close_listener(event, game_state: GameState) -> None:
        # "When the combat chain closes …" — dispatch to the attack card (e.g.
        # Swing Big). Fires while combat still exists so combat.hit is readable.
        combat = game_state.combat
        if combat is None or combat.attack_card is None:
            return
        dispatch(game_state, "ON_COMBAT_CLOSE", combat.attack_card.slug,
                 card=combat.attack_card, event=event)

    def _dsl_defend_listener(event, game_state: GameState) -> None:
        # "When this defends" — dispatch to the actual defending card object
        # (e.g. Scowling Flesh Bag intimidates).
        card_obj = event.data.get('card') if isinstance(event.data, dict) else None
        if card_obj is None:
            return
        dispatch(game_state, "ON_DEFEND", card_obj.slug, card=card_obj, event=event)

    def _dsl_boo_listener(event, game_state: GameState) -> None:
        # "Whenever the crowd boos you" — fires on the booed player's hero.
        pid = event.data.get('player_id') if isinstance(event.data, dict) else None
        if pid is None:
            return
        hero = game_state.players[pid].hero
        if hero is not None:
            dispatch(game_state, "ON_BOO", hero.slug, card=hero, event=event)

    def _dsl_cheer_listener(event, game_state: GameState) -> None:
        # "Whenever the crowd cheers you" — fires on the cheered player's hero,
        # mirroring _dsl_boo_listener. Every card with this text is a hero
        # (Pleiades, Tuffnut, Tuffnut Bumbling Hulkster); a non-hero permanent
        # with the text would need wider dispatch, same as for ON_BOO.
        pid = event.data.get('player_id') if isinstance(event.data, dict) else None
        if pid is None:
            return
        hero = game_state.players[pid].hero
        if hero is not None:
            dispatch(game_state, "ON_CHEER", hero.slug, card=hero, event=event)

    def _dsl_transcend_listener(event, game_state: GameState) -> None:
        # CR 8.5.48 — "whenever you transcend" (Twelve Petal Kasaya). Dispatched
        # to the transcending player's hero and to their permanents: unlike boo
        # and cheer, the cards with this text are equipment, not heroes.
        pid = event.data.get('player_id') if isinstance(event.data, dict) else None
        if pid is None:
            return
        player = game_state.players[pid]
        targets = [player.hero] + list(player.permanents.cards)
        for zone in (player.head, player.chest, player.arms, player.legs,
                     player.weapon1, player.weapon2):
            targets += list(zone.cards)
        for target in targets:
            if target is not None:
                dispatch(game_state, "ON_TRANSCEND", target.slug, card=target, event=event)

    def _dsl_card_played_listener(event, game_state: GameState) -> None:
        # "Whenever you play your SECOND non-attack action card each turn, ..."
        # (Briar). Hero text keyed on the act of playing a card, which nothing
        # dispatched to the hero — so every such ability invented a private flag
        # instead. play.py already records the play as turn events, so the card
        # counts those; this only has to deliver the trigger.
        data = event.data if isinstance(getattr(event, 'data', None), dict) else {}
        played = data.get('card')
        pid = getattr(played, 'controller', None) or getattr(played, 'owner', None)
        if pid is None or pid not in game_state.players:
            return
        hero = game_state.players[pid].hero
        if hero is not None:
            dispatch(game_state, "ON_CARD_PLAYED", hero.slug, card=hero, event=event)

    def _dsl_token_created_listener(event, game_state: GameState) -> None:
        # "When you create a <token>" — dispatched to the creator's hero; the
        # DSL gates on the token slug in event.data (see TRIGGER_EVENT_GATES).
        pid = event.data.get('player_id') if isinstance(event.data, dict) else None
        if pid is None:
            return
        hero = game_state.players[pid].hero
        if hero is not None:
            dispatch(game_state, "ON_TOKEN_CREATED", hero.slug, card=hero, event=event)

    def _dsl_clash_resolved_listener(event, game_state: GameState) -> None:
        # "When you win a clash revealing this" — dispatch to the winner's
        # revealed card (e.g. Thunk, The Golden Son).
        data = event.data if isinstance(event.data, dict) else {}
        revealed = data.get('winner_card')
        if revealed is None:
            return
        dispatch(game_state, "ON_CLASH_WIN_REVEALED", revealed.slug,
                 card=revealed, event=event)

    def _dsl_recalc_listener(event, game_state: GameState) -> None:
        # WHILE_STATIC bridge: re-evaluate continuous attack-power statics on the
        # attack card, both heroes, and in-play permanents/weapons. Runs AFTER the
        # staged recalculation (this event is emitted at the end of
        # _recalculate_attack_power), so MODIFY_ATTACK effects land in stage 8.
        combat = game_state.combat
        if not combat or not combat.attack_card:
            return
        seen: set[int] = set()
        cards = [combat.attack_card]
        for p in game_state.players.values():
            if p.hero is not None:
                cards.append(p.hero)
            for zone in (p.permanents, p.items, p.auras, p.allies,
                         p.head, p.chest, p.arms, p.legs, p.weapon1, p.weapon2):
                cards.extend(zone.cards)
        for c in cards:
            if id(c) in seen:
                continue
            seen.add(id(c))
            dispatch(game_state, "RECALC_ATTACK_POWER", c.slug, card=c, event=event)

    def _dsl_deal_damage_listener(event, game_state: GameState) -> None:
        # Combat physical damage (the 'damage_dealt' event, engine _attack_step):
        # the attack card is the source. Fire its DSL ON_DEAL_DAMAGE abilities and
        # any injected ON_DEAL_DAMAGE triggers — e.g. a turn-scoped "whenever an
        # attack deals damage to a hero this turn, ..." hook (INJECT_TRIGGER
        # scope=TURN, event ON_DEAL_DAMAGE). Non-combat/ability damage flows through
        # effect_keywords.deal_damage (the 'damage' event) and is not covered here.
        combat = game_state.combat
        if not combat or not combat.attack_card:
            return
        slug = combat.attack_card.slug
        dispatch(game_state, "ON_DEAL_DAMAGE", slug,
                 card=combat.attack_card, event=event)
        # "The first time an attack action card YOU CONTROL deals damage to an
        # opposing hero, ..." is printed on the HERO (Briar), not on the attack,
        # so the hero has to hear about it too. Dispatched to the attacking
        # player's hero; the card's own conditions narrow which attacks count.
        _hero = game_state.players[combat.attacker_id].hero
        if _hero is not None:
            dispatch(game_state, "ON_DEAL_DAMAGE", _hero.slug,
                     card=_hero, event=event)
        remaining = []
        for td in combat.injected_triggers:
            if td.event_type != "ON_DEAL_DAMAGE":
                remaining.append(td)
                continue
            cond_ok = td.condition_fn is None or td.condition_fn(
                combat.attack_card, event, game_state)
            if cond_ok:
                td.effect_fn(combat.attack_card, event, game_state)
        combat.injected_triggers = remaining

    state.event_manager.register('hit', _dsl_hit_listener)
    state.event_manager.register('damage_dealt', _dsl_deal_damage_listener)
    state.event_manager.register('attacking', _dsl_attacking_listener)
    state.event_manager.register('start_of_turn', _dsl_start_of_turn_listener)
    state.event_manager.register('end_of_turn', _dsl_end_of_turn_listener)
    state.event_manager.register('start_of_end_phase', _dsl_start_of_end_phase_listener)
    state.event_manager.register('card_pitched', _dsl_pitch_listener)
    state.event_manager.register('defend', _dsl_defend_listener)
    state.event_manager.register('combat_chain_close', _dsl_combat_close_listener)
    state.event_manager.register('start_of_game', _dsl_start_of_game_listener)
    state.event_manager.register('crowd_boos', _dsl_boo_listener)
    state.event_manager.register('crowd_cheers', _dsl_cheer_listener)
    state.event_manager.register('transcend', _dsl_transcend_listener)
    state.event_manager.register('token_created', _dsl_token_created_listener)
    state.event_manager.register('on_play', _dsl_card_played_listener)
    state.event_manager.register('start_of_action_phase',
                                 _dsl_start_of_action_phase_listener)
    state.event_manager.register('clash_resolved', _dsl_clash_resolved_listener)
    state.event_manager.register('recalculate_attack_power', _dsl_recalc_listener)


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

    Clears existing per-attack staged effects first so prior chain links
    don't bleed into new ones.  Called from _attack_step after
    _apply_turn_attack_effects so any effects that function appends to
    card.effects are also captured here.
    """
    from engine.continuous_effects import ContinuousEffect, next_timestamp
    from engine.card import CardEffect
    mgr = state.continuous_effect_manager
    # Purge leftover per-attack staged effects from any previous chain link
    mgr.remove_by_prop('power')
    mgr.remove_by_prop('defense')
    mgr.remove_by_prop('keywords')
    for effect in getattr(card, 'effects', []):
        if not isinstance(effect, CardEffect):
            continue
        eid = f"card_effect_{card.slug}_{effect.prop}_{effect.stage}_{effect.substage}_{id(effect.fn)}"
        mgr.add(ContinuousEffect(
            stage=effect.stage,
            substage=effect.substage,
            timestamp=next_timestamp(),
            prop=effect.prop,
            source_slug=card.slug,
            effect_id=eid,
            apply_fn=lambda val, _s, _c, _fn=effect.fn: _fn(val),
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
    power = mgr.recalculate(state, card, 'power', base_power)

    # Permanent +1{p} power counters on the attacking card (e.g. a card given a
    # power counter by Ironfist Revelation) add to its power whenever it attacks.
    if getattr(card, 'counters', None):
        power = (power or 0) + (card.counters.get('power', 0) or 0)

    # Stage-8 per-attack power modifiers from triggered/played effects this
    # chain link (e.g. Reckless Arithmetic "+X{p}"). Re-applied on every
    # recalculation so the buff persists through later combat steps.
    for mod, amount in combat.power_mods:
        if mod == "set":
            power = amount
        elif mod == "multiply":
            power = (power or 0) * amount
        else:  # add
            power = (power or 0) + amount

    # DSL continuous effects (APPLY_CONTINUOUS, e.g. Night's Embrace: "your
    # attacks with stealth get +1{p} this turn"). Applied to the attacker's own
    # attacks that match the effect's filter. Registered on the player and
    # cleared at end of turn.
    attacker = state.players.get(combat.attacker_id)
    for ce in (getattr(attacker, "dsl_continuous_effects", None) or []):
        if ce.get("target") != "PLAYER_ATTACKS":
            continue
        filt = ce.get("filter")
        if filt is not None:
            from engine.card_effects.dsl.condition_types import compile_condition
            fn = compile_condition(filt.get("type", "none"),
                                   {k: v for k, v in filt.items() if k != "type"})
            if fn is not None and not fn(card, None, state):
                continue
        for m in ce.get("modifications", []):
            if m.get("type") != "MODIFY_ATTACK":
                continue
            mod, amt = m.get("mod", "add"), m.get("amount", 0)
            if mod == "set":
                power = amt
            elif mod == "multiply":
                power = (power or 0) * amt
            else:
                power = (power or 0) + amt

    combat.attack_power = power

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

    # CR 7.5.2: damage is dealt to the attack-target. A declared card target
    # (Spectra aura, ally, …) takes the damage instead of the defending hero.
    target_card = combat.attack_target_card
    if target_card is not None:
        if not getattr(target_card, 'is_in_arena', False):
            # CR 7.5.2b: the attack-target ceased to exist or is illegal when
            # damage is calculated — no damage is dealt, no hit-event occurs.
            net_damage = 0
        elif getattr(target_card, 'current_life', None) is None:
            # CR 8.5.3c: a non-living object cannot be dealt damage.
            net_damage = 0

    # Apply prevention/replacement effects
    damage_event = {"type": "damage", "amount": net_damage, "target_player_id": defender_id, "damage_type": "physical"}
    damage_event = state.effect_manager.apply_replacements(damage_event, state)
    net_damage = damage_event.get("amount", 0)

    if net_damage > 0:
        if target_card is not None:
            # Living card target (e.g. an ally): CR 7.5.2 / 8.5.3a.
            target_card.current_life -= net_damage
        else:
            defender.health -= net_damage
        combat.hit = True
        # CR 1.10.2a: the 0-life loss is a game-state action applied when the game
        # would transition to a priority state — BEFORE on-hit triggered-layers are
        # added to the stack and resolve (1.10.2d). If this hit is lethal, the
        # losing player loses now and the game ends; the on-hit triggers emitted
        # below must NOT resolve (a defeated player was being prompted for them).
        if check_state_based_actions(state):
            return
        # 7.5.5: hit event (physical damage from attack)
        # 'hit_hero' fires only when the hit target is the defending hero.
        # "banish the top X cards of their deck, where X is the damage dealt by
        # this attack" (Eradicate). Stored on combat so an ON_HIT ability can
        # read it: net_damage is the damage AFTER defence, which is what the
        # cards mean, and it is not recoverable from attack_power alone.
        combat.net_damage_dealt = net_damage
        state.event_manager.emit(Event(type='hit', card=combat.attack_card.slug, data={'damage': net_damage}), state)
        if target_card is None:
            state.event_manager.emit(Event(type='hit_hero', card=combat.attack_card.slug, data={'damage': net_damage}), state)
        state.event_manager.emit(Event(type='damage_dealt', data={'damage': net_damage, 'target': defender_id}), state)
    else:
        combat.hit = False

    # Check if damage killed someone (ally deaths, and the no-hit path).
    if check_state_based_actions(state):
        return

    # Store chain link result
    _atk = combat.attack_card
    link = ChainLink(
        chainlink_id=combat.link_id,
        attacker_id=combat.attacker_id,
        attack_slug=_atk.slug,
        attack_power=combat.attack_power,
        net_damage=net_damage,
        keywords=combat.keywords,
        from_weapon=combat.from_weapon,
        hit=(net_damage > 0),
        talents=list(getattr(_atk, "talents", None) or []),
        classes=list(getattr(_atk, "classes", None) or []),
        subtypes=list(getattr(_atk, "subtypes", None) or []),
    )
    state.chain_links.append(link)

    # CR 8.5.46: Resolve wagers — winner creates the prize token
    _resolve_wagers(state, combat)

def _resolve_wagers(state: GameState, combat) -> None:
    """CR 8.5.46: Resolve all wagers on the current chain link.

    If the attack hit, the controller (attacker) wins. Otherwise the
    opponent (defender) wins. The winner creates the prize token.
    """
    from engine.card_effects.ability_keywords import create_token
    if not combat.wagers:
        return

    hit = combat.hit
    for entry in combat.wagers:
        # Older entries are 2-tuples; the third element is the source card.
        controller_id, prize_slug = entry[0], entry[1]
        source = entry[2] if len(entry) > 2 else None
        opponent_id = 3 - controller_id
        winner_id = controller_id if hit else opponent_id
        # Emit wager_resolved event
        _event = Event(type='wager_resolved',
                       data={'winner': winner_id, 'loser': 3 - winner_id,
                             'hit': hit, 'prize': prize_slug,
                             'controller': controller_id})
        state.event_manager.emit(_event, state)
        # Create prize token for the winner
        if prize_slug:
            create_token(state, winner_id, prize_slug)
        # "The winner loses 1{h}" — a payoff that is not a token. Dispatched to
        # the card that made the wager, which is where that text is printed.
        if source is not None:
            from engine.card_effects.dsl import dispatch
            dispatch(state, "ON_WAGER_RESOLVED", source.slug,
                     card=source, event=_event)

    combat.wagers.clear()


def _apply_watery_grave(card, state: GameState) -> None:
    """CR 8.3.41: If card has Watery Grave and entered graveyard from the arena, turn face-down."""
    if not hasattr(card, 'keywords') or not card.keywords:
        return
    has_wg = any("watery grave" in re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', kw).lower() for kw in card.keywords)
    if not has_wg:
        return
    from engine.card_effects.ability_keywords import ARENA_ZONE_NAMES
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
    # An ON_HIT effect may have already relocated the attack (e.g. Herald of
    # Protection puts itself on the bottom of the deck, then creates a Spectral
    # Shield). put_object() can't resolve the game-level combat-chain zone, so a
    # relocated card is still listed in combat_chain.cards while its own .zone
    # already points elsewhere — that stale membership is the reliable signal.
    relocated = attack_card.zone != state.combat_chain.name
    if attack_card in state.combat_chain.cards:
        state.combat_chain.remove(attack_card)
    if combat.from_weapon:
        pass  # 7.7.5: weapon returns to equipped zone
    elif not relocated:
        # Only send the attack to the graveyard if it wasn't relocated by an
        # effect; adding it here too would duplicate it and break conservation.
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


# ---------------------------------------------------------------------------
# Stack and Priority
# ---------------------------------------------------------------------------

def _to_graveyard(owner_player, card, is_public: bool = True) -> None:
    """Put *card* into *owner_player*'s graveyard, honouring a per-card,
    turn-scoped "if it would be put into the graveyard this turn, instead banish
    it" rider (Under the Trap-Door). The flag lives in current_turn_effects keyed
    by object_id and expires with the turn."""
    key = f"gy_to_banish_{getattr(card, 'object_id', None)}"
    if key in owner_player.current_turn_effects:
        owner_player.banished.add(card)
    else:
        owner_player.graveyard.add(card, is_public=is_public)


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
                _was_on_stack = (entry.card in game_state.stack.cards
                                 and entry.card.zone == 'stack')
                game_state.stack.remove(entry.card)  # CR 3.0.1: card leaves stack zone on resolution
                # CR 5.3.7 / 3.0.12: clear the resolved card-layer to its owner's graveyard.
                if _was_on_stack:
                    _owner = game_state.players.get(entry.card.owner)
                    if _owner is not None:
                        _to_graveyard(_owner, entry.card, is_public=True)
            game_state.process_cease_to_exist(entry.card)
            card = entry.card
            if card and not entry.is_attack and card.has_go_again:
                game_state.players[entry.player_id].action_points += 1
            if getattr(game_state, 'recorders', None):
                from engine.recorder import notify as _rec_notify
                _rec_notify(game_state, 'on_layer_resolved', entry)
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
    # CR 8.2.9a: Landmark cards enter the arena as permanents instead of ceasing to exist.
    _is_landmark = (entry.layer_type == 'card' and card is not None
                    and ("Landmark" in _card_types or "Landmark" in _card_subtypes))

    if entry.effect_fn:
        # CR 5.3.4: layer effects generate while the layer is still on the stack.
        result = entry.effect_fn(card, game_state)  # call once — not twice

        if environ.get('debug') == 'True':
            with open(environ['debug_file'], 'a') as f:
                f.write(f'stack {entry} resolves: {result}\n')

    # CR 5.3.6-5.3.7: after the layer effects, the layer leaves the stack. A
    # plain card-layer still on the stack is cleared to its owner's graveyard
    # (CR 3.0.12). A card the effects already moved elsewhere (a defense
    # reaction that became defending, a card reloaded to arsenal, put to the
    # bottom of the deck, …) only has its stale stack reference dropped.
    if entry.layer_type == 'card' and card and not _is_figment and not _is_aura \
            and not _is_ally and not _is_landmark:
        _still_on_stack = card in game_state.stack.cards and card.zone == 'stack'
        game_state.stack.remove(card)  # CR 3.0.1: card leaves stack zone on resolution
        game_state.process_cease_to_exist(card)
        if _still_on_stack and not entry.is_attack:
            _owner = game_state.players.get(card.owner)
            if _owner is not None:
                _to_graveyard(_owner, card, is_public=True)

    # Figments, Auras, Allies, and Landmarks enter the arena as permanents instead of ceasing to exist.
    if _is_figment or _is_aura or _is_ally or _is_landmark:
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
            if hasattr(card, 'base_health') and card.base_health is not None:
                card.current_health = card.raw_health
            elif hasattr(card, 'life') and card.life is not None:
                card.base_health = card.current_health = card.life
        elif _is_landmark:
            # Use SubZoneView.add so permanent_subtype="Landmark" is set (needed for filter)
            player.landmarks.add(card, is_public=True)
            # CR 8.2.9b: clear all OTHER landmark permanents across all players
            for pid, p in game_state.players.items():
                for lm in list(p.landmarks.cards):
                    if lm is not card:
                        p.permanents.remove(lm)
                        p.graveyard.add(lm, is_public=True)
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
        # Spinal Crush (WTR): suppress go again for the affected player's
        # action cards / activated abilities this turn.
        if (has_effective_go_again and entry.player_id == game_state.active_player
                and "cant_go_again" not in game_state.players[entry.player_id].current_turn_effects):
            game_state.players[entry.player_id].action_points += 1

    if getattr(game_state, 'recorders', None):
        from engine.recorder import notify as _rec_notify
        _rec_notify(game_state, 'on_layer_resolved', entry)

    game_state.priority_player = game_state.active_player
    game_state.consecutive_passes = 0
    game_state.last_acted_player = None

def order_stack(game_state: GameState) -> None:
    """Order NEWLY-CREATED triggered-layers on the stack (CR 6.6.6b).

    ONLY simultaneous triggered-layers are ordered, exactly once, as they
    enter the stack. Card-layers played by players (and previously ordered
    triggers) keep their LIFO positions (CR 3.15.4) — a card played in
    response to another card is NOT reorderable."""
    new_triggers = [e for e in game_state.stack_entries
                    if e.is_triggered and not getattr(e, '_ordered', False)]
    if not new_triggers:
        return

    turn_player_id = game_state.active_player
    opponent_id = 3 - game_state.active_player
    turn_fx = [e for e in new_triggers if e.player_id == turn_player_id]
    opp_fx = [e for e in new_triggers if e.player_id == opponent_id]

    # 1.10.2d / 6.6.6b: the turn player picks who adds their triggers first
    # (only meaningful when both players have pending triggers).
    if turn_fx and opp_fx:
        goes_first = get_turn_player_choice(game_state, 'Who resolves triggers first?')
    else:
        goes_first = turn_player_id if turn_fx else opponent_id

    # Each player orders their own pending triggers.
    if len(turn_fx) > 1:
        game_state.priority_player = turn_player_id
        turn_fx = get_player_order_decision(game_state, turn_player_id, turn_fx)
    if len(opp_fx) > 1:
        game_state.priority_player = opponent_id
        opp_fx = get_player_order_decision(game_state, opponent_id, opp_fx)

    # Remove the new triggers from their tentative positions; existing layers
    # keep their order. LIFO: resolve_stack pops from the END, so the
    # goes-first player's triggers go at the end (resolve first).
    rest = [e for e in game_state.stack_entries
            if not any(e is t for t in new_triggers)]
    ordered = (opp_fx + turn_fx) if goes_first == turn_player_id else (turn_fx + opp_fx)
    for e in ordered:
        e._ordered = True
    game_state.stack_entries = rest + ordered

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
            Action(type=ActionType.CHOOSE, card=entry.card, choose_index=i)
            for i, entry in enumerate(remaining)
        ]
        choice = game_state.player_agents[player_id](game_state, options, context='Choose the next card to enter the stack')
        if isinstance(choice, Action):
            choice.player_id = player_id
        order.append(remaining.pop(choice.choose_index or 0))
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
        # CR 1.10.2: game-state actions (incl. the 0-life loss, 1.10.2a) are
        # performed when the game transitions to a priority state. A player
        # brought to <=0 in a no-priority window — e.g. a start-of-turn Bloodrot
        # Pox DoT — loses here, before being granted priority to act.
        if check_state_based_actions(state):
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

        if action is None or action.type == ActionType.PASS:
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
    legal = available_actions(state, player_id)

    # Forced pass optimization: do not route pass-only decisions through agents.
    # This avoids unnecessary embedder taps/logging for CR-mandated no-op priority passes.
    if len(legal) == 1 and legal[0].type == ActionType.PASS:
        forced = legal[0]
        forced.player_id = player_id
        return forced

    choice = state.player_agents[player_id](state, legal, context=context if context else 'What do you do?')
    if isinstance(choice, Action):
        choice.player_id = player_id
    
    if isinstance(choice.card, Card):
        # Check for additional costs
        if any(kw in (choice.card.keywords or []) for kw in KEYWORD_COSTS):
            if not hasattr(choice, "additional_costs") or not isinstance(choice.additional_costs, dict):
                choice.additional_costs = {}
            for keyword, fn in KEYWORD_COSTS.items():
                if keyword in (choice.card.keywords or []):
                    additional_cost_check = fn(state, choice.player_id, choice, check=True)
                    if additional_cost_check:
                        additional_cost_choice = state.player_agents[player_id](state, 
                                                                                [Action(type=ActionType.CHOOSE, choose_index=0), # 0 = don't pay additional cost
                                                                                 Action(type=ActionType.CHOOSE, choose_index=1)], # 1 = pay additional cost
                                                            context=f"Additional cost for {keyword} keyword on {choice.card.name}:")
                        if additional_cost_choice.choose_index == 1:
                            choice.additional_costs[keyword] = True
                        else:
                            choice.additional_costs[keyword] = False


    return choice

def get_turn_player_choice(state: GameState, context: str) -> int:
    """Get decision from turn player for which player acts first."""
    options = [
        Action(type=ActionType.CHOOSE, choose_index=0),  # 0 = self goes first
        Action(type=ActionType.CHOOSE, choose_index=1),  # 1 = opponent goes first
    ]
    choice = state.player_agents[state.active_player](state, options, context)
    if isinstance(choice, Action):
        choice.player_id = state.active_player
    return state.active_player if (choice.choose_index == 0) else 3 - state.active_player

def player_decision_raw(state: GameState, player_id: int, options, context=None) -> int:
    """Get a raw choice from player agent (index into options list)."""
    choice = state.player_agents[player_id](state, options, context if context else None)
    return choice
