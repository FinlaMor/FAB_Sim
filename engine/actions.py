"""Action types and legal action generation for FAB self-play engine (OO rewrite)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import sys
from itertools import count, combinations
sys.path.insert(0, r"C:\Users\Joseph\Desktop\FAB_Coach")

from engine.card import CardDB, Card
from engine.state import GameState, Step, Zone
from engine.card_effects.registry import EQUIPMENT_ACTIVATION_CONDITIONS, EQUIPMENT_ACTIVATION_COST, ATTACK_REACTION_CONDITIONS, DEFENSE_REACTION_CONDITIONS, HERO_ACTIVATION_CONDITIONS, DISCARD_ACTIVATE_EFFECTS, PLAY_TARGET_CONDITIONS


class ActionType(Enum):
    PASS = "pass"
    ATTACK_WEAPON = "attack_weapon"
    PLAY_CARD = "play_card"
    PLAY_ARSENAL = "play_arsenal"
    DEFEND_CARDS = "defend_cards"
    DEFEND_EQUIPMENT = "defend_equipment"
    STORE_ARSENAL = "store_arsenal"
    PLAY_ATTACK_REACTION = "play_attack_reaction"
    PLAY_DEFENSE_REACTION = "play_defense_reaction"
    REACTION_PASS = "reaction_pass"
    ACTIVATE_ITEM = "activate_item"
    ATTACK_ALLY = "attack_ally"
    ACTIVATE_EQUIPMENT = "activate_equipment"
    ACTIVATE_WEAPON = "activate_weapon"
    ACTIVATE_HERO = "activate_hero"
    DISCARD_ACTIVATE = "discard_activate"
    PLAY_BANISH = "play_banish"  # Play a card from the banish zone (e.g. Under the Trap-Door)


@dataclass
class Action:
    type: ActionType
    player_id: Optional[int] = None
    card: Optional[Card] = None
    card_idx: Optional[int] = None
    pitch_cards: list[str] = field(default_factory=list)
    from_arsenal: bool = False
    slot: Optional[str] = None
    card_list: Optional[list[Card]] = None
    target: Optional[Card] = None
    targets: Optional[list[str]] = None       # Multi-target declarations (CR 1.8.5c)
    attack_source: Optional[Card] = None      # Source object for attack proxies/layers (CR 1.4.3, 1.4.4)
    is_attack_proxy: Optional[bool] = None    # Attack represented by a proxy object
    is_attack_layer: Optional[bool] = None    # Attack represented by a non-card layer
    
    # Game context (added Round 3 for CR compliance)
    phase: Optional[str] = None              # "start", "action", "end" (CR 4.0.3)
    step: Optional[Step] = None              # Current game step (CR 4.0.4)
    chain_link_number: Optional[int] = None  # Position in combat chain, 0 if none (CR 7.0.3b)
    priority_player: Optional[int] = None    # Which player has priority (CR 1.10)
    
    # Action economy (added Round 5 for CR 4.3.2, 5.1.6-7, 8.1.1c, 8.3.5)
    action_points_available: Optional[int] = None  # Current action points (CR 4.3.2)
    resources_available: Optional[int] = None      # Floating resources (CR 5.1.6)
    action_cost: Optional[int] = None              # Action point cost (CR 8.1.1c)
    resource_cost: Optional[int] = None            # Resource cost (CR 5.1.7)
    has_go_again: Optional[bool] = None            # Action chaining (CR 8.3.5)
    
    # Action speed (added Round 6 for CR 8.1.1a/b/c, 8.1.6a)
    is_instant_speed: Optional[bool] = None        # Card/ability is Instant type (CR 8.1.6a)
    is_action_speed: Optional[bool] = None         # Card/ability is Action type (CR 8.1.1a/b)
    played_as_instant: Optional[bool] = None       # Action played "as though instant" (CR 8.1.1d)
    
    # Modal and optional choices (added Round 9 for CR 1.7.5, 5.1.3 - Gap #1 fix +10 points)
    modes_selected: Optional[list[int]] = None     # Indices of selected modes (CR 1.7.5)
    x_value_declared: Optional[int] = None         # X-cost value declared (CR 1.12.2, 5.1.3a)
    is_melded: Optional[bool] = None               # Legacy meld flag (kept for compat)
    meld_side: Optional[str] = None                # Meld side: 'top', 'bottom', 'both', or None (CR 8.3.38)
    alternative_cost_used: Optional[str] = None    # Alternative cost name if used (CR 5.1.3c)

    def __repr__(self):
        parts = [self.type.value]
        if self.card_idx is not None:
            parts.append(f"card_index={self.card_idx}")
        if self.card is not None:
            parts.append(f"card={self.card}")
        if self.pitch_cards:
            parts.append(f"pitch={self.pitch_cards}")
        if self.from_arsenal:
            parts.append("from_arsenal")
        if self.slot is not None:
            parts.append(f"slot={self.slot}")
        if self.target is not None:
            parts.append(f"target={self.target}")
        if self.targets:
            parts.append(f"targets={self.targets}")
        if self.attack_source is not None:
            parts.append(f"attack_source={self.attack_source}")
        if self.is_attack_proxy:
            parts.append("attack_proxy")
        if self.is_attack_layer:
            parts.append("attack_layer")
        return f"Action({', '.join(parts)})"


# ---------------------------------------------------------------------------
# Pitch helpers — work with Zone objects directly (Card objects, no card_db needed)
# ---------------------------------------------------------------------------

def find_all_valid_pitch_sequences(hand_cards: list[Card], target_cost: int, current_resources: int = 0) -> list[list[Card]]:
    """
    Find all legal ordered pitch sequences for paying target_cost.

    CR 5.1.6/5.1.7: Pitching is sequential. After each card is pitched the game
    checks whether the cost is now satisfied; if it is, pitching stops immediately.
    This means a legal sequence s = [c1, ..., ck] must satisfy:
        - Every proper prefix sum(s[:i]) < needed  (cost not yet met after i-1 cards)
        - sum(s) >= needed                         (cost met by final card)

    Order matters: [red(1), blue(3)] for cost=3 is legal (red doesn't cover cost;
    blue then does), but [blue(3), red(1)] is NOT (blue alone covers cost so red
    can never be pitched after it).

    Returns a list of ordered Card lists.
    """
    if target_cost is None or target_cost <= 0:
        return [[]]  # No pitching needed — empty sequence is always valid

    pitchable_indices = [
        i for i, card in enumerate(hand_cards)
        if card.pitch is not None and card.pitch > 0
    ]

    needed = target_cost - current_resources

    if needed <= 0:
        return [[]]

    card_sequences: list[list[Card]] = []

    def _dfs(remaining: list[int], running: int, seq: list[Card]) -> None:
        for j, idx in enumerate(remaining):
            v = _get_pitch_value(hand_cards[idx])
            new_total = running + v
            new_seq = seq + [hand_cards[idx]]
            if new_total >= needed:
                # This card satisfies the cost — record the complete legal sequence
                card_sequences.append(new_seq)
            else:
                # Cost not yet satisfied — keep building the sequence
                rest = remaining[:j] + remaining[j + 1:]
                _dfs(rest, new_total, new_seq)

    _dfs(pitchable_indices, 0, [])
    return card_sequences

def _get_pitch_value(card: Card) -> int:
    """Get the pitch/resource value of a card."""
    return card.pitch or 0

def _weapon_can_attack(weapon_card) -> bool:
    text = weapon_card.functional_text or ""
    if "**Attack**" not in text and ": Attack" not in text:
        return False
    # Weapons with "Banish a card from under" cost require cards underneath
    if "banish a card from under" in text.lower():
        if not getattr(weapon_card, 'cards_underneath', None):
            return False
    return True

def _weapon_cost(weapon_card) -> int:
    text = weapon_card.functional_text or ""
    match = re.search(r'[-\u2014]\s*((?:\{r\})+)(?:,\s*\{t\})?\s*:', text)
    if match:
        return match.group(1).count('{r}')
    return 0


# ---------------------------------------------------------------------------
# Legal action dispatch
# ---------------------------------------------------------------------------

def legal_actions(state: GameState, card_db: CardDB) -> list[Action]:
    """Return all legal actions for the current acting player in the current step."""
    step = state.step
    if step == Step.ACTION:
        actions = _legal_action_step(state, card_db)
    elif step == Step.COMBAT_LAYER:
        # CR 7.0.1a: players may play instants and activate abilities at instant speed during Layer Step
        actions = _legal_action_step(state, card_db)
    elif step == Step.COMBAT_ATTACK:
        actions = _legal_action_step(state, card_db)
    elif step == Step.COMBAT_DEFEND:
        if state.combat and state.combat.defending_declared:
            actions = _legal_action_step(state, card_db)
        else:
            actions = _legal_defend_step(state, card_db)
    elif step == Step.COMBAT_REACTION:
        actions = _legal_reaction_step(state, card_db)
    elif step == Step.COMBAT_DAMAGE:
        actions = _legal_action_step(state, card_db)
    elif step == Step.COMBAT_RESOLUTION:
        actions = _legal_action_step(state, card_db)
    elif step in (Step.END_PHASE_BEGINNING, Step.END_TURN):
        actions = _legal_end_turn_step(state, card_db)
    else:
        return []

    # Populate action economy metadata so encoders/JSONL always have these fields
    pp = state.priority_player
    player = state.players.get(pp)
    if player:
        ap = player.action_points
        res = player.resources
        for a in actions:
            if a.action_points_available is None:
                a.action_points_available = ap
            if a.resources_available is None:
                a.resources_available = res
            if a.card:
                if a.resource_cost is None:
                    ms = a.meld_side
                    if ms == 'bottom':
                        a.resource_cost = 0
                    elif ms == 'both':
                        a.resource_cost = a.card.meld_cost or 0
                    else:
                        a.resource_cost = a.card.cost or 0
                if a.action_cost is None:
                    ms = a.meld_side
                    if ms == 'bottom':
                        a.action_cost = 0
                    elif ms in ('top', 'both'):
                        a.action_cost = 1
                    else:
                        a.action_cost = 0 if "Instant" in (a.card.types or []) else 1
                if a.has_go_again is None:
                    a.has_go_again = bool(a.card.has_go_again)
    return actions


def _is_null_meld_card(card: Optional[Card]) -> bool:
    if card is None:
        return False
    return re.sub(r'_(red|yellow|blue)$', '', card.slug) == 'null__shock'


def _stack_instant_target_entries(state: GameState) -> list:
    return [
        e for e in (state.stack_entries or [])
        if e.card is not None and "Instant" in (e.card.types or [])
    ]


# ---------------------------------------------------------------------------
# ACTION step
# ---------------------------------------------------------------------------

def _legal_action_step(state: GameState, card_db: CardDB) -> dict[Action, list[int]]:
    actions: list[Action] = []
    pp = state.priority_player
    player = state.players[pp]

    actions.append(Action(type=ActionType.PASS)) # Always legal to pass in action phase, always no pitch required.

    if pp == state.active_player and not state.stack_entries:
        # ATTACK_WEAPON
        weapon_card = player.weapon.top
        if weapon_card is not None and player.action_points > 0 and not player.weapon_exhausted and not weapon_card.tapped:
            if _weapon_can_attack(weapon_card):
                weapon_cost_val = _weapon_cost(weapon_card)
                weapon_attack_pitch_seqs = find_all_valid_pitch_sequences(
                    player.hand.cards, 
                    weapon_cost_val,
                    current_resources=player.resources
                )
                for seq in weapon_attack_pitch_seqs:
                    if seq is not None:
                        actions.append(Action(
                            type=ActionType.ATTACK_WEAPON,
                            card=weapon_card,
                            pitch_cards=seq,
                            attack_source=weapon_card,
                            is_attack_proxy=True,
                        ))

        # Cards that can't be played from hand
        CANT_PLAY_FROM_HAND = {"death_touch"}

        # PLAY_CARD from hand
        for i, card in enumerate(player.hand.cards):
            if card.slug in CANT_PLAY_FROM_HAND:
                continue
            if "Attack Reaction" in card.types or "Defense Reaction" in card.types:
                continue
            is_instant = "Instant" in card.types
            if not card.is_action and not is_instant:
                continue
            is_meld = "Meld" in (card.keywords or [])
            if is_meld:
                # Meld cards expose three distinct action-time plays:
                # TOP side   — action-speed (e.g. Comet Storm), costs card.cost, AP required
                # BOTTOM side — instant-speed (Shock "1 arcane" / Life "gain 1{h}"), free, no AP
                # MELDED     — action-speed, costs 2× base cost plus modifiers, AP required, dual resolution
                null_targets = _stack_instant_target_entries(state) if _is_null_meld_card(card) else None
                if player.action_points > 0:
                    top_seqs = find_all_valid_pitch_sequences(
                        player.hand.cards, card.cost or 0, current_resources=player.resources)
                    for seq in top_seqs:
                        if null_targets is not None:
                            for target_entry in null_targets:
                                actions.append(Action(
                                    type=ActionType.PLAY_CARD,
                                    card_idx=i,
                                    card=card,
                                    pitch_cards=seq,
                                    meld_side='top',
                                    target=target_entry.card,
                                    targets=[f"oid:{target_entry.card.object_id}"],
                                ))
                        else:
                            actions.append(Action(type=ActionType.PLAY_CARD, card_idx=i, card=card,
                                                  pitch_cards=seq, meld_side='top'))
                # Bottom side is always playable at instant speed (no AP needed)
                bottom_seqs = find_all_valid_pitch_sequences(
                    player.hand.cards, 0, current_resources=player.resources)
                for seq in bottom_seqs:
                    actions.append(Action(type=ActionType.PLAY_CARD, card_idx=i, card=card,
                                          pitch_cards=seq, meld_side='bottom'))
                # Melded requires an action point
                if player.action_points > 0:
                    meld_cost = card.meld_cost or 0
                    meld_seqs = find_all_valid_pitch_sequences(
                        player.hand.cards, meld_cost, current_resources=player.resources)
                    for seq in meld_seqs:
                        if null_targets is not None:
                            for target_entry in null_targets:
                                actions.append(Action(
                                    type=ActionType.PLAY_CARD,
                                    card_idx=i,
                                    card=card,
                                    pitch_cards=seq,
                                    meld_side='both',
                                    target=target_entry.card,
                                    targets=[f"oid:{target_entry.card.object_id}"],
                                ))
                        else:
                            actions.append(Action(type=ActionType.PLAY_CARD, card_idx=i, card=card,
                                                  pitch_cards=seq, meld_side='both'))
            else:
                if card.is_action and player.action_points <= 0:
                    continue
                # CR 5.1.4a: cards with required targets cannot be played without a valid target
                _card_base_slug = re.sub(r'_(red|yellow|blue)$', '', card.slug)
                _ptc = PLAY_TARGET_CONDITIONS.get(_card_base_slug)
                if _ptc is not None and not _ptc(state, pp):
                    continue
                # General: card can ONLY target attacks → requires active combat
                if (getattr(card, 'can_target_attack', False)
                        and not getattr(card, 'can_target_hero', False)
                        and not getattr(card, 'can_target_permanent', False)
                        and state.combat is None):
                    continue
                effective_cost = card.cost
                play_card_pitch_seqs = find_all_valid_pitch_sequences(
                    player.hand.cards,
                    effective_cost,
                    current_resources=player.resources
                )
                for seq in play_card_pitch_seqs:
                    actions.append(Action(type=ActionType.PLAY_CARD, card_idx=i, card=card, pitch_cards=seq))

        # PLAY_ARSENAL — only face-up (public) cards can be played (CR 3.0.4b, CR 5.1.2b)
        arsenal_card = player.arsenal.top
        if arsenal_card is not None and arsenal_card.is_public:
            is_ar = "Attack Reaction" in arsenal_card.types
            is_dr = "Defense Reaction" in arsenal_card.types
            is_instant = "Instant" in arsenal_card.types
            if (arsenal_card.is_action or is_instant) and not is_ar and not is_dr:
                if is_instant or player.action_points > 0:
                    # CR 5.1.4a: block play if required target is missing
                    _ab_slug = re.sub(r'_(red|yellow|blue)$', '', arsenal_card.slug)
                    _aptc = PLAY_TARGET_CONDITIONS.get(_ab_slug)
                    _no_target = ((_aptc is not None and not _aptc(state, pp))
                                  or (getattr(arsenal_card, 'can_target_attack', False)
                                      and not getattr(arsenal_card, 'can_target_hero', False)
                                      and not getattr(arsenal_card, 'can_target_permanent', False)
                                      and state.combat is None))
                    if not _no_target:
                        effective_cost = arsenal_card.cost
                        arsenal_pitch_seqs = find_all_valid_pitch_sequences(
                            player.hand.cards,
                            effective_cost,
                            current_resources=player.resources
                        )
                        null_targets = _stack_instant_target_entries(state) if _is_null_meld_card(arsenal_card) else None
                        if not (null_targets is not None and not null_targets):
                            for seq in arsenal_pitch_seqs:
                                if seq is not None:
                                    if null_targets is not None:
                                        for target_entry in null_targets:
                                            actions.append(Action(
                                                type=ActionType.PLAY_ARSENAL,
                                                card=arsenal_card,
                                                pitch_cards=seq,
                                                from_arsenal=True,
                                                target=target_entry.card,
                                                targets=[f"oid:{target_entry.card.object_id}"],
                                            ))
                                    else:
                                        actions.append(Action(
                                            type=ActionType.PLAY_ARSENAL,
                                            card=arsenal_card,
                                            pitch_cards=seq,
                                            from_arsenal=True,
                                        ))

        # ACTIVATE_ITEM
        for i, card in enumerate(player.items.cards):
            text = card.functional_text or ""
            if "**Instant**" in text or ("**Action**" in text and player.action_points > 0):
                effective_cost = card.cost
                item_pitch_seqs = find_all_valid_pitch_sequences(
                    player.hand.cards, 
                    effective_cost,
                    current_resources=player.resources
                )
                for seq in item_pitch_seqs:
                    if seq is not None:
                        actions.append(Action(
                            type=ActionType.ACTIVATE_ITEM, 
                            card_idx=i, 
                            card=card, 
                            pitch_cards=seq
                            ))

        # ACTIVATE_EQUIPMENT (non-weapon)
        for slot_name in ("head", "chest", "arms", "legs"):
            equip_zone = player.zone_by_name(slot_name)
            if not equip_zone or not equip_zone.cards:
                continue
            equip_card = equip_zone.cards[0]
            if getattr(equip_card, 'face_down', False):
                continue  # Face-down/cloaked equipment can't be activated
            equip_slug = equip_card.slug
            text = equip_card.functional_text or ""
            has_action = bool(re.search(r'\*\*(?:\w+ per turn )?Action\*\*', text))
            has_instant = bool(re.search(r'\*\*(?:\w+ per turn )?Instant\*\*', text))
            if not (has_action or has_instant):
                continue
            if has_action and not has_instant and player.action_points <= 0:
                continue
            if equip_card.exhausted:
                continue
            if equip_card.tapped:
                continue

            # Check additonal activation conditions from registry
            cond_fn = EQUIPMENT_ACTIVATION_CONDITIONS.get(equip_slug)
            if cond_fn is not None:
                import inspect as _inspect
                _sig = _inspect.signature(cond_fn)
                _cond_result = cond_fn(player, slot_name, equip_card, state) if len(_sig.parameters) >= 4 else cond_fn(player, slot_name, equip_card)
                if not _cond_result:
                    continue
            
            cost_override = EQUIPMENT_ACTIVATION_COST.get(equip_slug)
            if cost_override is not None:
                if callable(cost_override):
                    import inspect
                    effective_cost = cost_override(player, state) if len(inspect.signature(cost_override).parameters) >= 2 else cost_override(player)
                else:
                    effective_cost = cost_override
            else:
                effective_cost = equip_card.cost
            equipment_pitch_seqs = find_all_valid_pitch_sequences(
                player.hand.cards,
                effective_cost,
                current_resources=player.resources
            )
            for seq in equipment_pitch_seqs:
                if seq is not None:
                    actions.append(Action(
                        type=ActionType.ACTIVATE_EQUIPMENT,
                        card=equip_card,
                        pitch_cards=seq,
                        slot=slot_name
                        ))

        # ACTIVATE_WEAPON activate abilities (e.g. Hammerhead Harpoon Cannon)
        if not player.weapon_exhausted and weapon_card is not None and not _weapon_can_attack(weapon_card):
            text = weapon_card.functional_text or ""
            can_activate_weapon = False
            if (("**Action**" in text or "Action" in text) and player.action_points > 0) or "**Instant**" in text or "Instant" in text:
                can_activate_weapon = True
                weapon_slug = weapon_card.slug
                # Block "Once per Turn" weapons that have already been activated this turn
                if ("once per" in text.lower()) and weapon_card.exhausted:
                    can_activate_weapon = False
                # Check weapon-specific conditions
                cond_fn = EQUIPMENT_ACTIVATION_CONDITIONS.get(weapon_slug)
                if cond_fn is not None and not cond_fn(player, "weapon", weapon_card):
                    can_activate_weapon = False
            if can_activate_weapon:
                cost_override = EQUIPMENT_ACTIVATION_COST.get(weapon_slug)
                if cost_override is not None:
                    cost = cost_override(player) if callable(cost_override) else cost_override
                else:
                    cost = weapon_card.cost
                activate_weapon_pitch_seqs = find_all_valid_pitch_sequences(
                    player.hand.cards,
                    cost,
                    current_resources=player.resources
                )
                for seq in activate_weapon_pitch_seqs:
                    if seq is not None:
                        actions.append(Action(
                            type=ActionType.ACTIVATE_WEAPON,
                            card=weapon_card,
                            pitch_cards=seq,
                        ))

        # ATTACK_ALLY — allies can attack once per turn (CR 11.0)
        if player.action_points > 0 and not state.stack_entries:
            for i, ally_card in enumerate(player.allies.cards):
                exhausted = player.allies_exhausted[i] if i < len(player.allies_exhausted) else False
                if not exhausted and ally_card.power is not None and ally_card.power > 0:
                    actions.append(Action(
                        type=ActionType.ATTACK_ALLY,
                        card_idx=i,
                        card=ally_card,
                        player_id=pp,
                        is_attack_proxy=False,
                        attack_source=ally_card,
                    ))

    # DISCARD_ACTIVATE — "Instant - Discard this:" hand abilities (no pitch cost)
    for card in player.hand.cards:
        if card.slug in DISCARD_ACTIVATE_EFFECTS:
            actions.append(Action(type=ActionType.DISCARD_ACTIVATE, card=card, player_id=pp))

    # PLAY_BANISH — cards in the banish zone marked as playable this turn
    # (e.g. traps banished by Under the Trap-Door, or cards banished by Infiltrate)
    all_turn_effects = player.current_turn_effects + getattr(player, 'next_turn_effects', [])
    for card in player.banished.cards:
        if (f"trap_door_playable_{card.slug}" in all_turn_effects
                or f"infiltrate_play_{card.slug}" in all_turn_effects):
            is_instant = "Instant" in (card.types or [])
            if card.is_action and player.action_points <= 0 and not is_instant:
                continue
            banish_pitch_seqs = find_all_valid_pitch_sequences(
                player.hand.cards,
                card.cost,
                current_resources=player.resources
            )
            for seq in banish_pitch_seqs:
                actions.append(Action(type=ActionType.PLAY_BANISH, card=card, pitch_cards=seq, player_id=pp))

    # ACTIVATE_HERO — instant-speed hero abilities (available whenever player has priority)
    hero_card = player.hero
    hero_slug = hero_card.slug if hero_card else None
    hero_cfg = HERO_ACTIVATION_CONDITIONS.get(hero_slug) if hero_slug else None
    if hero_cfg is not None:
        cond_fn = hero_cfg.get("condition_fn")
        if cond_fn and cond_fn(player, state):
            hero_cost_raw = hero_cfg.get("cost", 0)
            hero_cost = hero_cost_raw(player, state) if callable(hero_cost_raw) else hero_cost_raw
            hero_pitch_seqs = find_all_valid_pitch_sequences(
                player.hand.cards,
                hero_cost,
                current_resources=player.resources
            )
            target_fn = hero_cfg.get("target_fn")
            if target_fn:
                targets = target_fn(player, state)
                for target_card in targets:
                    for seq in hero_pitch_seqs:
                        actions.append(Action(
                            type=ActionType.ACTIVATE_HERO,
                            card=hero_card,
                            pitch_cards=seq,
                            target=target_card,
                        ))
            else:
                for seq in hero_pitch_seqs:
                    actions.append(Action(
                        type=ActionType.ACTIVATE_HERO,
                        card=hero_card,
                        pitch_cards=seq,
                    ))

    return actions


# ---------------------------------------------------------------------------
# DEFEND step
# ---------------------------------------------------------------------------

def _legal_defend_step(state: GameState, card_db: CardDB) -> list[Action]:
    actions: list[Action] = []
    combat = state.combat
    defender = state.players[3 - state.active_player]

    # Always include the option to defend with nothing
    actions.append(Action(type=ActionType.PASS))

    # If the attack targets an ally (not the hero), defender cannot declare defending cards
    # (Rules Reprise: "Nic cannot declare any defending cards, because their hero is not the one being attacked")
    if combat.attack_target is not None and combat.attack_target is not defender:
        return actions

    # List all hand cards able to block
    defendable_cards = []
    for i, card in enumerate(defender.hand.cards):
        if 'Defense Reaction' in card.types:
            continue
        if not card.has_defense:
            continue
        defendable_cards.append(card)
    
    # List all equipment able to block (face-down/cloaked equipment cannot defend)
    for slot_name in ("head", "chest", "arms", "legs"):
        equip_zone = defender.zone_by_name(slot_name)
        if not equip_zone or not equip_zone.cards:
            continue
        equip_card = equip_zone.cards[0]
        if getattr(equip_card, 'face_down', False):
            continue
        if not equip_card.has_defense:
            continue
        defendable_cards.append(equip_card)

    # Generate all possible non-empty subsets of defendable cards
    for r in range(1, len(defendable_cards) + 1):
        for combo in combinations(defendable_cards, r):
            valid = True
            if "Dominate" in combat.keywords:
                # CR 8.3.4a: total hand cards defending (already defending + new combo) must be ≤ 1
                already_defending_hand = [c for c in combat.defending_cards if c in defender.hand.cards]
                new_hand = [c for c in combo if c in defender.hand.cards]
                if len(already_defending_hand) + len(new_hand) > 1:
                    valid = False
            if "Overpower" in combat.keywords:
                # CR 8.3.22a: total action cards defending (already + new) must be ≤ 1
                already_defending_action = sum(1 for c in combat.defending_cards if c.is_action)
                new_action = sum(1 for c in combo if c.is_action)
                if already_defending_action + new_action > 1:
                    valid = False
            if valid:
                actions.append(Action(type=ActionType.DEFEND_CARDS, card_list=list(combo)))
 
    return actions


# ---------------------------------------------------------------------------
# REACTION step
# ---------------------------------------------------------------------------

def _legal_reaction_step(state: GameState, card_db: CardDB) -> list[Action]:
    actions: list[Action] = []
    combat = state.combat

    if combat is None:
        raise ValueError("Combat must be non-None for reaction step")

    # Always include the option to pass on reactions
    actions.append(Action(type=ActionType.REACTION_PASS))

    pp = state.priority_player
    player = state.players[pp]
    attacker_id = combat.attacker_id
    defender_id = 3 - attacker_id

    # Instants from hand (at reaction/instant speed — no action point consumed)
    for i, card in enumerate(player.hand.cards):
        if "Instant" not in card.types:
            continue
        is_meld = "Meld" in (card.keywords or [])
        if is_meld:
            # Top side at instant speed (meld_side=None → _apply_play_card uses Instant check → no AP)
            null_targets = _stack_instant_target_entries(state) if _is_null_meld_card(card) else None
            top_seqs = find_all_valid_pitch_sequences(
                player.hand.cards, card.cost or 0, current_resources=player.resources)
            for seq in top_seqs:
                if null_targets is not None:
                    for target_entry in null_targets:
                        actions.append(Action(
                            type=ActionType.PLAY_CARD,
                            card_idx=i,
                            card=card,
                            pitch_cards=seq,
                            target=target_entry.card,
                            targets=[f"oid:{target_entry.card.object_id}"],
                        ))
                else:
                    actions.append(Action(type=ActionType.PLAY_CARD, card_idx=i, card=card,
                                          pitch_cards=seq))  # meld_side=None = instant-speed top
            # Bottom side at instant speed: always cost 0
            bottom_seqs = find_all_valid_pitch_sequences(
                player.hand.cards, 0, current_resources=player.resources)
            for seq in bottom_seqs:
                actions.append(Action(type=ActionType.PLAY_CARD, card_idx=i, card=card,
                                      pitch_cards=seq, meld_side='bottom'))
        else:
            # CR 5.1.4a: check required target exists
            _ri_base_slug = re.sub(r'_(red|yellow|blue)$', '', card.slug)
            _ri_ptc = PLAY_TARGET_CONDITIONS.get(_ri_base_slug)
            if _ri_ptc is not None and not _ri_ptc(state, pp):
                continue
            effective_cost = card.cost
            hand_pitch_seqs = find_all_valid_pitch_sequences(
                player.hand.cards,
                effective_cost,
                current_resources=player.resources
            )
            for seq in hand_pitch_seqs:
                actions.append(Action(type=ActionType.PLAY_CARD, card_idx=i, card=card, pitch_cards=seq))

    # Instants from arsenal
    for i, card in enumerate(player.arsenal.cards):
        if "Instant" not in card.types:
            continue
        effective_cost = card.cost
        arsenal_pitch_seqs = find_all_valid_pitch_sequences(
            player.hand.cards, 
            effective_cost,
            current_resources=player.resources
        )
        null_targets = _stack_instant_target_entries(state) if _is_null_meld_card(card) else None
        if null_targets is not None and not null_targets:
            # Null's top side requires a legal instant target at declaration time.
            continue
        for seq in arsenal_pitch_seqs:
            if null_targets is not None:
                for target_entry in null_targets:
                    actions.append(Action(
                        type=ActionType.PLAY_ARSENAL,
                        card_idx=i,
                        card=card,
                        pitch_cards=seq,
                        target=target_entry.card,
                        targets=[f"oid:{target_entry.card.object_id}"],
                    ))
            else:
                actions.append(Action(type=ActionType.PLAY_ARSENAL, card_idx=i, card=card, pitch_cards=seq))

    # ACTIVATE_EQUIPMENT (non-weapon) in reaction step
    for slot_name in ("head", "chest", "arms", "legs"):
        equip_zone = player.zone_by_name(slot_name)
        if not equip_zone or not equip_zone.cards:
            continue
        equip_card = equip_zone.cards[0]
        if getattr(equip_card, 'face_down', False):
            continue  # Face-down/cloaked equipment can't be activated
        equip_slug = equip_card.slug
        text = equip_card.functional_text or ""
        has_reaction = bool(re.search(r'\*\*(?:\w+ per turn )?(?:Defense |Attack )?Reaction\*\*', text))
        has_instant = bool(re.search(r'\*\*(?:\w+ per turn )?Instant\*\*', text))
        if not (has_reaction or has_instant):
            continue
        if has_reaction and not has_instant and player.action_points <= 0:
            continue
        if equip_card.exhausted:  # exhausted covers "once per turn" AND {t} (exhaust-cost) equipment
            continue
        if equip_card.tapped:
            continue
        
        # Check additonal activation conditions from registry
        cond_fn = EQUIPMENT_ACTIVATION_CONDITIONS.get(equip_slug)
        if cond_fn is not None:
            import inspect as _inspect_r
            _sig_r = _inspect_r.signature(cond_fn)
            _cond_r = cond_fn(player, slot_name, equip_card, state) if len(_sig_r.parameters) >= 4 else cond_fn(player, slot_name, equip_card)
            if not _cond_r:
                continue

        cost_override = EQUIPMENT_ACTIVATION_COST.get(equip_slug)
        if cost_override is not None:
            if callable(cost_override):
                import inspect
                effective_cost = cost_override(player, state) if len(inspect.signature(cost_override).parameters) >= 2 else cost_override(player)
            else:
                effective_cost = cost_override
        else:
            effective_cost = equip_card.cost
        equipment_pitch_seqs = find_all_valid_pitch_sequences(
            player.hand.cards,
            effective_cost,
            current_resources=player.resources
        )
        for seq in equipment_pitch_seqs:
            if seq is not None:
                actions.append(Action(
                    type=ActionType.ACTIVATE_EQUIPMENT,
                    card=equip_card,
                    pitch_cards=seq,
                    slot=slot_name
                    ))

    # ACTIVATE_ITEM (Instant)
    for i, card in enumerate(player.items.cards):
        if "**Instant**" in (card.functional_text or ""):
            effective_cost = card.cost
            item_pitch_seqs = find_all_valid_pitch_sequences(
                player.hand.cards, 
                effective_cost,
                current_resources=player.resources
            )
            for seq in item_pitch_seqs:
                actions.append(Action(type=ActionType.ACTIVATE_ITEM, card=card, pitch_cards=seq))

    if pp == attacker_id:
        # Attack reactions from hand
        for i, card in enumerate(player.hand.cards):
            if "Attack Reaction" not in card.types:
                continue
            cond_fn = ATTACK_REACTION_CONDITIONS.get(card.slug)
            if cond_fn is not None and not cond_fn(combat):
                continue
            effective_cost = card.cost
            ar_pitch_seqs = find_all_valid_pitch_sequences(
                player.hand.cards, 
                effective_cost,
                current_resources=player.resources
            )
            for seq in ar_pitch_seqs:
                actions.append(Action(type=ActionType.PLAY_ATTACK_REACTION, card=card, pitch_cards=seq))
        
        # Attack reactions from arsenal
        for i, card in enumerate(player.arsenal.cards):
            if "Attack Reaction" not in card.types:
                continue
            cond_fn = ATTACK_REACTION_CONDITIONS.get(card.slug)
            if cond_fn is not None and not cond_fn(combat):
                continue
            effective_cost = card.cost
            ar_arsenal_pitch_seqs = find_all_valid_pitch_sequences(
                player.hand.cards, 
                effective_cost,
                current_resources=player.resources
            )
            for seq in ar_arsenal_pitch_seqs:
                actions.append(
                    Action(
                        type=ActionType.PLAY_ATTACK_REACTION,
                        card=card,
                        pitch_cards=seq,
                        from_arsenal=True,
                    )
                )

    elif pp == defender_id:
        # If attack targets an ally (not the hero), defender cannot play DRs
        defender_player = state.players[defender_id]
        target_is_hero = (combat.attack_target is None or combat.attack_target is defender_player)
        if target_is_hero and not combat.no_defense_reactions:
            dominate_blocks = "Dominate" in combat.keywords and combat.defender_used_hand_card
            if not dominate_blocks:
                for i, card in enumerate(player.hand.cards):
                    if "Defense Reaction" not in card.types:
                        continue
                    cond_fn = DEFENSE_REACTION_CONDITIONS.get(card.slug)
                    if cond_fn is not None and not cond_fn(combat):  # Issue 8 fix: call the function
                        continue
                    effective_cost = card.cost
                    dr_pitch_seqs = find_all_valid_pitch_sequences(
                        player.hand.cards, 
                        effective_cost,
                        current_resources=player.resources
                    )
                    for seq in dr_pitch_seqs:
                        actions.append(Action(type=ActionType.PLAY_DEFENSE_REACTION, card=card, pitch_cards=seq))

            # Defense reaction from arsenal — blocked by no_defense_reactions (CR 7.4.2c),
            # but NOT by dominate (CR 8.3.4b scopes dominate to "from hand" only).
            # Also blocked if attack targets an ally (not the hero).
            if target_is_hero and not combat.no_defense_reactions:
                for i, card in enumerate(player.arsenal.cards):
                    if "Defense Reaction" not in card.types:
                        continue
                    cond_fn = DEFENSE_REACTION_CONDITIONS.get(card.slug)
                    if cond_fn is not None and not cond_fn(combat):
                        continue
                    effective_cost = card.cost
                    dr_arsenal_pitch_seqs = find_all_valid_pitch_sequences(
                        player.hand.cards,
                        effective_cost,
                        current_resources=player.resources
                    )
                    for seq in dr_arsenal_pitch_seqs:
                        actions.append(
                            Action(
                                type=ActionType.PLAY_DEFENSE_REACTION,
                                card=card,
                                pitch_cards=seq,
                                from_arsenal=True,
                            )
                        )

    return actions

# ---------------------------------------------------------------------------
# END_TURN step
# ---------------------------------------------------------------------------

def _legal_end_turn_step(state: GameState, card_db: CardDB) -> list[Action]:
    actions: list[Action] = []
    player = state.active()

    actions.append(Action(type=ActionType.PASS))

    if len(player.arsenal.cards) == 0:
        for i in range(len(player.hand)):
            actions.append(Action(type=ActionType.STORE_ARSENAL, card_idx=i))

    return actions
