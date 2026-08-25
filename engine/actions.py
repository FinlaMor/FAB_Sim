"""Action types and legal action generation for FAB self-play engine (OO rewrite)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from itertools import count

from engine.card import CardDB, Card
from engine.state import GameState, Step, Zone
from engine.card_effects.registry import EQUIPMENT_ACTIVATION_CONDITIONS, EQUIPMENT_ACTIVATION_COST, ATTACK_REACTION_CONDITIONS, DEFENSE_REACTION_CONDITIONS, HERO_ACTIVATION_CONDITIONS, DISCARD_ACTIVATE_EFFECTS, PLAY_TARGET_CONDITIONS, WEAPON_ATTACK_CONDITIONS
from engine.card_effects.costs.effect_costs import KEYWORD_COSTS
from engine.card_effects.costs.alt_costs import ALTERNATE_COSTS

class ActionType(Enum):
    PASS = "pass"
    # ATTACK_WEAPON = "attack_weapon"
    PLAY_CARD = "play_card"
    # PLAY_ARSENAL = "play_arsenal"
    DEFEND_CARDS = "defend_cards"
    # DEFEND_EQUIPMENT = "defend_equipment"
    STORE_ARSENAL = "store_arsenal"
    # PLAY_ATTACK_REACTION = "play_attack_reaction"
    # PLAY_DEFENSE_REACTION = "play_defense_reaction"
    REACTION_PASS = "reaction_pass"
    ACTIVATE_CARD = "activate_card"
    # ACTIVATE_ITEM = "activate_item"
    # ACTIVATE_ALLY = "activate_ally"
    # ATTACK_ALLY = "attack_ally"   # subsumed by ACTIVATE_CARD with is_attack_proxy=True
    # ACTIVATE_EQUIPMENT = "activate_equipment"
    # ACTIVATE_WEAPON = "activate_weapon"
    # ACTIVATE_HERO = "activate_hero"
    DISCARD_ACTIVATE = "discard_activate"  # "Instant - Discard this:" hand ability
    # PLAY_BANISH = "play_banish"  # Play a card from the banish zone
    CHOOSE = "choose"              # Generic choice action for multi-option prompts (e.g. modal abilities, target selection)
    PITCH_CARD = "pitch_card"       # Pay for a cost by pitching a hand card
    PITCH_TO_DECK = "pitch_to_deck"  # End-phase ordering: place pitched card to bottom of deck


@dataclass
class Action:
    type: ActionType
    player_id: Optional[int] = None
    card: Optional[Card] = None
    choose_index: Optional[int] = None
    #: WHICH activated ability of the card this action activates. A card
    #: printing two "Instant - {r}:" abilities (barbed_castaway) offered
    #: one indistinguishable action and play._apply_activate raised
    #: NotImplementedError rather than guess, so activating it aborted the
    #: game. None means "the only one", which is every other card.
    ability_index: Optional[int] = None
    pitch_cards: list[str] = field(default_factory=list)
    from_arsenal: bool = False
    slot: Optional[str] = None
    card_list: Optional[list[Card]] = None
    target: Optional[Card] = None
    targets: Optional[list[str]] = None       # Multi-target declarations (CR 1.8.5c)
    attack_source: Optional[Card] = None      # Source object for attack proxies/layers (CR 1.4.3, 1.4.4)
    is_attack_proxy: Optional[bool] = None    # Attack represented by a proxy object
    is_attack_layer: Optional[bool] = None    # Attack represented by a non-card layer
    has_go_again: Optional[bool] = None            # Action chaining (CR 8.3.5)
    played_as_instant: Optional[bool] = None       # Action played "as though instant" (CR 8.1.1d)
    
    modes_selected: Optional[list[int]] = None     # Indices of selected modes (CR 1.7.5)
    x_value_declared: Optional[int] = None         # X-cost value declared (CR 1.12.2, 5.1.3a)
    is_melded: Optional[bool] = None               # Legacy meld flag (kept for compat)
    meld_side: Optional[str] = None                # Meld side: 'top', 'bottom', 'both', or None (CR 8.3.38)
    alternate_cost_declared: Optional[bool] = None
    additional_costs_declared: Optional[dict[str, bool]] = None

    resource_cost: Optional[int] = None
    alternate_cost: Optional[bool] = None  # Alternate cost names declared by player (CR 5.1.3c)
    additional_costs: Optional[bool] = None           # CR 5.1.9: effect-costs have been paid
    life_cost: Optional[int] = None                      # Life cost (CR 1.14.2e)

    action_points_available: Optional[int] = None
    resources_available: Optional[int] = None
    action_cost: Optional[int] = None

    def __repr__(self):
        parts = [self.type.value]
        if self.choose_index is not None:
            parts.append(f"choose_index={self.choose_index}")
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

def get_pitchable_cards(hand_cards: list[Card], exclude_card: Card | None = None) -> list[Card]:
    """Return hand cards that can be pitched (pitch > 0), excluding *exclude_card*."""
    return [
        c for c in hand_cards
        if c is not exclude_card and _card_pitch(c) > 0
    ]


def _card_pitch(card: Card) -> int:
    """Return effective pitch value, falling back to base_pitch when pitch is None."""
    v = card.pitch if card.pitch is not None else (card.base_pitch or 0)
    return v or 0


def can_pay_cost(hand_cards: list[Card], target_cost: int, current_resources: int = 0, exclude_card: Card | None = None) -> bool:
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
        _card_pitch(c)
        for c in hand_cards
        if c is not exclude_card and _card_pitch(c) > 0
    )
    return total_pitch >= needed


def find_all_valid_pitch_sequences(hand_cards: list[Card], target_cost: int, current_resources: int = 0, max_seqs: int = 10) -> list[list[Card]]:
    """
    **DEPRECATED: now uses a binary decision that cycles through pitchable cards one at a time instead of enumerating all sequences to avoid combinatorial explosion.**
    Find all legal ordered pitch sequences for paying target_cost.

    CR 5.1.6/5.1.7: Pitching is sequential. After each card is pitched the game
    checks whether the cost is now satisfied; if it is, pitching stops immediately.
    This means a legal sequence s = [c1, ..., ck] must satisfy:
        - Every proper prefix sum(s[:i]) < needed  (cost not yet met after i-1 cards)
        - sum(s) >= needed                         (cost met by final card)

    Order matters: [red(1), blue(3)] for cost=3 is legal (red doesn't cover cost;
    blue then does), but [blue(3), red(1)] is NOT (blue alone covers cost so red
    can never be pitched after it).

    Sequences that pitch the same SET of cards (regardless of order) produce
    identical game states, so only one representative per unique pitched-set is
    kept. Results are capped at *max_seqs* to prevent combinatorial explosion.

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
    seen_sets: set[frozenset[int]] = set()

    def _dfs(remaining: list[int], running: int, seq: list[Card]) -> None:
        if len(card_sequences) >= max_seqs:
            return
        for j, idx in enumerate(remaining):
            if len(card_sequences) >= max_seqs:
                return
            v = _get_pitch_value(hand_cards[idx])
            new_total = running + v
            new_seq = seq + [hand_cards[idx]]
            if new_total >= needed:
                # This card satisfies the cost — record if unique pitched set
                pitched_key = frozenset(id(c) for c in new_seq)
                if pitched_key not in seen_sets:
                    seen_sets.add(pitched_key)
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


def _dsl_activation_costs_payable(card, state: GameState) -> bool:
    """True if the DSL ACTIVATE/INSTANT ability costs for *card* are all payable.

    Used to gate legality of activating DSL-authoritative equipment/weapons
    (e.g. Fyendal's Spring Tunic's "Remove 3 energy counters" cost).
    """
    from engine.card_effects.dsl.loader import get_card as _dsl_get_card
    cd = _dsl_get_card(card.slug)
    if cd is None:
        return True
    for ability in cd.abilities:
        if ability.ability_type.upper() not in ("ACTIVATE", "INSTANT"):
            continue
        for cost in getattr(ability, 'costs', []):
            if cost.check_fn is not None and not cost.check_fn(card, None, state):
                return False
    return True


def _can_afford_action(state: GameState, action: Action) -> tuple[bool, dict[str, int]]:
    """Check whether a player can afford all costs of an action.

    Mirrors evaluate_play_cost(check=True) in engine.py but lives here to
    avoid circular imports. Uses _calculate_resource_cost for the modified
    cost so continuous-effect reductions are accounted for.

    CR 5.1.6 / 1.14.2 cost sequence checked:
      1. Resource asset-cost (card.cost modified by continuous effects + alt cost)
      2. Life asset-cost (hero activations with life_cost)
      3. Effect-costs: Scrap requires graveyard item/equipment
    """
    can_afford = True
    how_afford = {}
    if action.player_id is None:
        return can_afford, how_afford
    player = state.players[action.player_id]

    # --- 1. Resource cost ---
    # Lazy import to avoid circular dependency; _calculate_resource_cost is in engine.py
    try:
        from engine.engine import _calculate_resource_cost
        resource_cost = _calculate_resource_cost(state, action)
    except ImportError:
        # Fallback to raw card cost if engine not importable (e.g. during early init)
        resource_cost = (action.card.cost or 0) if action.card else 0

    exclude = action.card if hasattr(action, 'card') and action.card is not None else None
    chi = getattr(player, 'chi', 0)
    effective_resources = player.resources + chi
    if not can_pay_cost(player.hand.cards, resource_cost, effective_resources, exclude_card=exclude):
        can_afford = False
    else:
        can_afford = True
    how_afford['resource_cost'] = can_afford


    # --- 2. Life cost (hero activations) ---
    if hasattr(action, 'life_cost')and (action.life_cost or 0) > 0 and player.hero is not None:
        life_cost = action.life_cost
        if life_cost > 0 and player.health <= life_cost:
            can_afford = False
        else:
            can_afford = True
        how_afford['life'] = can_afford

    # --- 3. effect-costs ---
    if getattr(action, 'additional_costs', None) is not None:
        card = getattr(action, 'card', None)
        if card is not None:
            from engine.card_effects.costs.effect_costs import KEYWORD_COSTS
            for keyword, cost_fn in KEYWORD_COSTS.items():
                if keyword in ([kw.lower() for kw in (card.keywords or [])]):
                    if not cost_fn(state, action.player_id, action, check=True):
                        can_afford = False
                    else:
                        can_afford = True
                    how_afford[keyword] = can_afford

            # Alternative-cost effect-cost checks (CR 5.1.3c / 5.1.8)
            alt = getattr(action, 'alternative_costs', None)
            if alt and any(card.slug in c for c in alt.keys()):
                 if ALTERNATE_COSTS.get(card.slug) is not None:
                    cost_fn = ALTERNATE_COSTS.get(card.slug)
                    if cost_fn and cost_fn(state, action, check=True):
                        can_afford = True  # mandatory effect-cost for alt cost can't be paid
                    else:
                        can_afford = False
                    how_afford["alternate_cost"] = can_afford

    can_afford = how_afford.get('resource_cost', True) or how_afford.get('alternate_cost', False)

    return can_afford, how_afford

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


def _parse_activation_cost_from_text(text: str) -> int:
    """Parse the resource cost from an equipment/ability activation line.

    Looks for patterns like '**Instant** - {r}{r}:' or '**Action** - {r}:' and
    returns the number of {r} tokens found before the colon.  Returns 0 if none.
    """
    # Match: ** ... ** - <optional non-r stuff> {r}+ <optional non-r stuff> :
    match = re.search(r'\*\*[^*]+\*\*\s*[-\u2014][^:]*?((?:\{r\})+)[^:]*:', text)
    if match:
        return match.group(1).count('{r}')
    return 0


# ---------------------------------------------------------------------------
# Targeting helpers
# ---------------------------------------------------------------------------

_RE_ANY_TARGET      = re.compile(r'\bany target\b', re.I)
_RE_TARGET_OPP_HERO = re.compile(r'\btarget (?:opposing|opponent\'?s?) hero\b', re.I)
_RE_TARGET_HERO     = re.compile(r'\btarget hero\b', re.I)


def _attackable_permanents(state: 'GameState', defender_id: int) -> list['Card']:
    """CR 1.4.5a: return permanents in the defender's arena that can be attacked.

    An object is attackable if it has a life property (allies) OR it is made
    attackable by an effect. Spectra (CR 8.3.14) is the canonical effect that
    makes an aura a legal attack target.
    """
    defender = state.players[defender_id]
    targets = []
    for card in defender.permanents.cards:
        # Allies are living (have life / health tracked externally) — always attackable
        if "Ally" in (card.subtypes or []) or "Ally" in (card.types or []):
            targets.append(card)
            continue
        # Spectra keyword makes the permanent a legal attack target (CR 8.3.14)
        if any(k.lower() == "spectra" for k in (card.keywords or [])):
            targets.append(card)
    return targets


def _legal_targets_for_card(state: 'GameState', player_id: int, card: 'Card') -> list:
    """Return valid target Card objects for a card's explicit targeting requirement.

    - 'any target'            → any living object (heroes + allies) for either player
    - 'target opposing hero'  → opponent's hero only
    - 'target hero'           → either player's hero (self or opponent)
    - no target specifier     → [None]  (untargeted; default logic applies in effect fn)

    Returns [None] for untargeted cards so callers always get exactly one action when
    no explicit targeting is present, preserving existing behavior.
    """
    text = card.functional_text or ""
    opp_id = 3 - player_id
    player = state.players[player_id]
    opp = state.players[opp_id]

    if _RE_ANY_TARGET.search(text):
        targets: list = []
        if player.hero:
            targets.append(player.hero)
        if opp.hero:
            targets.append(opp.hero)
        for ally in list(player.allies.cards):
            if getattr(ally, 'current_life', None):
                targets.append(ally)
        for ally in list(opp.allies.cards):
            if getattr(ally, 'current_life', None):
                targets.append(ally)
        return targets if targets else [None]

    if _RE_TARGET_OPP_HERO.search(text):
        return [opp.hero] if opp.hero else [None]

    if _RE_TARGET_HERO.search(text):
        targets = []
        if player.hero:
            targets.append(player.hero)
        if opp.hero:
            targets.append(opp.hero)
        return targets if targets else [None]

    return [None]


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
        # ATTACK_WEAPON — check both weapon slots independently
        for _wzone in [player.weapon1, player.weapon2]:
            weapon_card = _wzone.top
            if (weapon_card is not None
                    and player.action_points > 0
                    and not player.weapon_exhausted
                    and not weapon_card.tapped
                    and _weapon_can_attack(weapon_card)):
                # Check slug-specific attack conditions (e.g. bank_breaker requires crank)
                weapon_cond = WEAPON_ATTACK_CONDITIONS.get(weapon_card.slug)
                if weapon_cond is None or weapon_cond(state, player):
                    weapon_cost_val = _weapon_cost(weapon_card)
                    if can_pay_cost(player.hand.cards, weapon_cost_val, player.resources):
                        # Default target: opponent's hero (target=None)
                        actions.append(Action(
                            type=ActionType.ACTIVATE_CARD,
                            card=weapon_card,
                            attack_source=weapon_card,
                            is_attack_proxy=True,
                        ))
                        # CR 1.4.5a: also offer attacks targeting each attackable permanent
                        defender_id = 3 - pp
                        for _target in _attackable_permanents(state, defender_id):
                            actions.append(Action(
                                type=ActionType.ACTIVATE_CARD,
                                card=weapon_card,
                                attack_source=weapon_card,
                                is_attack_proxy=True,
                                target=_target,
                                targets=[_target.slug],
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
                    _top_action = Action(type=ActionType.PLAY_CARD, choose_index=i, card=card, meld_side='top')
                    _top_action.player_id = pp
                    if _can_afford_action(state, _top_action):
                        if null_targets is not None:
                            for target_entry in null_targets:
                                actions.append(Action(
                                    type=ActionType.PLAY_CARD,
                                    choose_index=i,
                                    card=card,
                                    meld_side='top',
                                    target=target_entry.card,
                                    targets=[f"oid:{target_entry.card.object_id}"],
                                ))
                        else:
                            actions.append(_top_action)
                # Bottom side is always playable at instant speed (no AP needed, cost 0)
                actions.append(Action(type=ActionType.PLAY_CARD, choose_index=i, card=card,
                                      meld_side='bottom'))
                # Melded requires an action point
                if player.action_points > 0:
                    _both_action = Action(type=ActionType.PLAY_CARD, choose_index=i, card=card, meld_side='both')
                    _both_action.player_id = pp
                    if _can_afford_action(state, _both_action):
                        if null_targets is not None:
                            for target_entry in null_targets:
                                actions.append(Action(
                                    type=ActionType.PLAY_CARD,
                                    choose_index=i,
                                    card=card,
                                    meld_side='both',
                                    target=target_entry.card,
                                    targets=[f"oid:{target_entry.card.object_id}"],
                                ))
                        else:
                            actions.append(_both_action)
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
                for _t in _legal_targets_for_card(state, pp, card):
                    _play_action = Action(type=ActionType.PLAY_CARD, choose_index=i, card=card, target=_t)
                    _play_action.player_id = pp
                    if _can_afford_action(state, _play_action):
                        actions.append(_play_action)
                # CR 1.4.5a: attack action cards may also target attackable permanents
                if card.is_attack:
                    _def_id = 3 - pp
                    for _target in _attackable_permanents(state, _def_id):
                        _pa = Action(type=ActionType.PLAY_CARD, choose_index=i, card=card,
                                     target=_target, targets=[_target.slug])
                        _pa.player_id = pp
                        if _can_afford_action(state, _pa):
                            actions.append(_pa)
                else:
                    # capture non-attack actions
                    if card.is_action and not card.is_attack and player.action_points > 0:
                        action = Action(type=ActionType.PLAY_CARD, choose_index=i, card=card)
                        can_pay, how_afford = _can_afford_action(state, action)
                        if how_afford.get('life', None) is False:
                            continue  # Can't afford life cost, skip this action
                        if not can_pay:
                            continue
                        if how_afford.get('resource_cost', True) and how_afford.get('alternate_cost', False):
                            actions.append(action)

                            alt_action = action
                            setattr(alt_action, 'alternate_cost', {action.card.slug: 1})
                            actions.append(alt_action)

                        elif how_afford.get('alternate_cost', False):
                            setattr(action, 'alternate_cost', {action.card.slug: 1})
                            actions.append(action)

                        else:
                            actions.append(action)


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
                        _ars_action = Action(type=ActionType.PLAY_ARSENAL, card=arsenal_card, from_arsenal=True)
                        _ars_action.player_id = pp
                        if _can_afford_action(state, _ars_action):
                            null_targets = _stack_instant_target_entries(state) if _is_null_meld_card(arsenal_card) else None
                            if not (null_targets is not None and not null_targets):
                                if null_targets is not None:
                                    for target_entry in null_targets:
                                        actions.append(Action(
                                            type=ActionType.PLAY_ARSENAL,
                                            card=arsenal_card,
                                            from_arsenal=True,
                                            target=target_entry.card,
                                            targets=[f"oid:{target_entry.card.object_id}"],
                                        ))
                                else:
                                    for _t in _legal_targets_for_card(state, pp, arsenal_card):
                                        actions.append(Action(
                                            type=ActionType.PLAY_ARSENAL,
                                            card=arsenal_card,
                                            from_arsenal=True,
                                            target=_t,
                                        ))

        # ACTIVATE_ITEM
        for i, card in enumerate(player.items.cards):
            text = card.functional_text or ""
            if "**Instant**" in text or ("**Action**" in text and player.action_points > 0):
                for _t in _legal_targets_for_card(state, pp, card):
                    _item_action = Action(type=ActionType.ACTIVATE_ITEM, choose_index=i, card=card, target=_t)
                    _item_action.player_id = pp
                    if _can_afford_action(state, _item_action):
                        actions.append(_item_action)

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
            # Match **Action** / **Instant** only as ability-type keywords, i.e. at the
            # start of a cost-effect clause ("**Action** —", "**Once per Turn Action** —").
            # A colon or em-dash following the keyword is required to distinguish from
            # mid-sentence uses like "attack action card".
            has_action = bool(re.search(r'\*\*(?:\w+ per \w+ )?action\*\*\s*[—:\-]', text, re.IGNORECASE))
            has_instant = bool(re.search(r'\*\*(?:\w+ per \w+ )?instant\*\*\s*[—:\-]', text, re.IGNORECASE))
            if not (has_action or has_instant):
                continue
            if has_action and not has_instant and player.action_points <= 0:
                continue
            if equip_card.exhausted:
                continue
            if equip_card.tapped and r"{t}" in text:
                continue

            # Activation gate: the card's DSL ability costs must be payable
            # (e.g. Fyendal's Spring Tunic needs 3 energy counters).
            if not _dsl_activation_costs_payable(equip_card, state):
                continue

            for _t in _legal_targets_for_card(state, pp, equip_card):
                _equip_action = Action(type=ActionType.ACTIVATE_CARD, card=equip_card, slot=slot_name, target=_t)
                _equip_action.player_id = pp
                if _can_afford_action(state, _equip_action):
                    actions.append(_equip_action)

        # ACTIVATE_WEAPON activate abilities (e.g. Hammerhead Harpoon Cannon)
        if not player.weapon_exhausted and weapon_card is not None and not _weapon_can_attack(weapon_card):
            text = weapon_card.functional_text.lower() or ""
            can_activate_weapon = False
            if ((("**action**" in text) and player.action_points > 0) or "**instant**" in text) and ":" in weapon_card.base_functional_text:
                can_activate_weapon = True
                weapon_slug = weapon_card.slug
                # Block "Once per Turn" weapons that have already been activated this turn
                if ("once per" in text) and weapon_card.exhausted:
                    can_activate_weapon = False
                # Check weapon-specific conditions
                cond_fn = EQUIPMENT_ACTIVATION_CONDITIONS.get(weapon_slug)
                if cond_fn is not None and not cond_fn(player, "weapon", weapon_card):
                    can_activate_weapon = False
            if (r"{t}" in text) and weapon_card.tapped:
                can_activate_weapon = False
            if can_activate_weapon:
                for _t in _legal_targets_for_card(state, pp, weapon_card):
                    _wpn_action = Action(type=ActionType.ACTIVATE_WEAPON, card=weapon_card, target=_t)
                    _wpn_action.player_id = pp
                    if _can_afford_action(state, _wpn_action):
                        actions.append(_wpn_action)

        # ATTACK_ALLY — allies can attack once per turn (CR 11.0)
        if player.action_points > 0 and not state.stack_entries:
            for i, ally_card in enumerate(player.allies.cards):
                exhausted = player.allies_exhausted[i] if i < len(player.allies_exhausted) else False
                if exhausted or ally_card.power is None or ally_card.power <= 0:
                    continue
                # Check ally has an attack activation (built-in or granted externally)
                _ftext = ally_card.functional_text or ""
                _has_attack_activation = bool(re.search(
                    r'\*\*(?:[\w\s]+\s)?[Aa]ction\*\*\s*[-\u2014][^:]*:\s*\*\*[Aa]ttack\*\*',
                    _ftext
                ))
                _granted_key = f"ally_attack_granted_{ally_card.slug}"
                if not _has_attack_activation and _granted_key not in player.current_turn_effects:
                    continue
                # Check resource affordability (cost may be in card.cost or functional text)
                from engine.play import _ally_attack_resource_cost
                ally_cost = _ally_attack_resource_cost(ally_card)
                if player.resources < ally_cost and not can_pay_cost(
                        player.hand.cards, ally_cost, player.resources):
                    continue
                # Default target: opponent's hero (target=None)
                actions.append(Action(
                    type=ActionType.ACTIVATE_CARD,
                    choose_index=i,
                    card=ally_card,
                    player_id=pp,
                    is_attack_proxy=True,
                    attack_source=ally_card,
                ))
                # CR 1.4.5a: also offer attacks targeting each attackable permanent
                defender_id = 3 - pp
                for _target in _attackable_permanents(state, defender_id):
                    actions.append(Action(
                        type=ActionType.ACTIVATE_CARD,
                        choose_index=i,
                        card=ally_card,
                        player_id=pp,
                        is_attack_proxy=True,
                        attack_source=ally_card,
                        target=_target,
                        targets=[_target.slug],
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
            for _t in _legal_targets_for_card(state, pp, card):
                _ban_action = Action(type=ActionType.PLAY_BANISH, card=card, player_id=pp, target=_t)
                if _can_afford_action(state, _ban_action):
                    actions.append(_ban_action)

    # ACTIVATE_HERO — hero abilities (Action-timing requires AP, Instant doesn't)
    hero_card = player.hero
    hero_slug = hero_card.slug if hero_card else None
    hero_cfg = HERO_ACTIVATION_CONDITIONS.get(hero_slug) if hero_slug else None
    if hero_cfg is not None:
        hero_timing = hero_cfg.get("timing", "action")
        # Action-timing hero abilities require an action point
        if hero_timing == "action" and player.action_points <= 0:
            hero_cfg = None  # Skip — can't activate without AP
    if hero_cfg is not None:
        cond_fn = hero_cfg.get("condition_fn")
        if cond_fn and cond_fn(player, state):
            _hero_action = Action(type=ActionType.ACTIVATE_HERO, card=hero_card)
            _hero_action.player_id = pp
            if _can_afford_action(state, _hero_action):
                target_fn = hero_cfg.get("target_fn")
                if target_fn:
                    targets = target_fn(player, state)
                    for target_card in targets:
                        actions.append(Action(
                            type=ActionType.ACTIVATE_HERO,
                            card=hero_card,
                            target=target_card,
                        ))
                else:
                    actions.append(_hero_action)

    return actions


# ---------------------------------------------------------------------------
# DEFEND step
# ---------------------------------------------------------------------------

def _defend_restriction_met(state: GameState, card: Card) -> bool:
    """False when a card's own "this may only defend if ..." clause is unmet.

    A DEFEND_RESTRICTION ability carries conditions and no effects: every
    condition must hold for the card to be declarable as a defender (CR 7.3.2).
    Nothing else in the DSL can express a defend-LEGALITY restriction — an
    ordinary triggered ability fires too late, once the card is already
    defending.
    """
    from engine.card_effects.dsl.loader import get_card as _dsl_get_card
    card_def = _dsl_get_card(getattr(card, 'slug', '') or '')
    if card_def is None:
        return True
    for ability in card_def.abilities:
        if (ability.ability_type or "").upper() != "DEFEND_RESTRICTION":
            continue
        for cond in ability.conditions:
            if cond.fn is not None and not cond.fn(card, None, state):
                return False
    return True


def _restriction_blocks(state: GameState, card: Card, slot_name: str | None) -> bool:
    """True when a combat restriction forbids this card from defending.

    Each entry in combat.defender_restrictions names cards that may NOT defend:

        equipment           any equipment
        from_hand           a card defending from HAND (Benji: "can't be
                            defended by cards from hand"). The hand loop passes
                            slot_name=None and the equipment loop passes a slot,
                            so the two are already distinguishable here.
        non_head_equipment  equipment outside the head slot (Headbutt)
        card_type/subtype   a type or subtype ("Attack", "Action")
        cost_lt / cost_lte / cost_gt / cost_gte
                            a cost threshold, already resolved to a number
        max_defenders       a COUNT limit rather than a per-card filter: "can't
                            be defended by more than 2 non-block cards". Every
                            other key names WHICH cards may not defend; this one
                            names HOW MANY, so it blocks nothing until that many
                            already sit on the chain. `exclude_types` names card
                            types that do not count toward the limit (Block is a
                            card TYPE, CR 8.1.12, not a subtype).
    """
    combat = state.combat
    if combat is None:
        return False
    is_equipment = bool(getattr(card, 'is_equipment', False))
    traits = {t.lower() for t in (getattr(card, 'types', None) or [])}
    traits |= {t.lower() for t in (getattr(card, 'subtypes', None) or [])}
    cost = getattr(card, 'cost', None) or 0

    for rule in combat.defender_restrictions:
        if "max_defenders" in rule:
            # Counted against what is ALREADY defending, so the first N cards
            # are legal and the N+1th is not. A card excluded by type does not
            # count and is never blocked.
            exclude = {t.lower() for t in (rule.get("exclude_types") or [])}
            if exclude and (traits & exclude):
                continue
            counted = 0
            for d in (getattr(combat, "defending_cards", None) or []):
                d_traits = {t.lower() for t in (getattr(d, "types", None) or [])}
                d_traits |= {t.lower() for t in (getattr(d, "subtypes", None) or [])}
                if exclude and (d_traits & exclude):
                    continue
                counted += 1
            try:
                limit = int(rule["max_defenders"])
            except (TypeError, ValueError):
                continue
            if counted < limit:
                continue
            return True
        if rule.get("equipment") and not is_equipment:
            continue
        if rule.get("from_hand") and (is_equipment or slot_name is not None):
            continue
        if rule.get("non_head_equipment"):
            if not is_equipment or slot_name == "head":
                continue
        wanted = [t.lower() for t in _as_list_restriction(rule)]
        if wanted and not (traits & set(wanted)):
            continue
        if "cost_lt" in rule and not cost < rule["cost_lt"]:
            continue
        if "cost_lte" in rule and not cost <= rule["cost_lte"]:
            continue
        if "cost_gt" in rule and not cost > rule["cost_gt"]:
            continue
        if "cost_gte" in rule and not cost >= rule["cost_gte"]:
            continue
        return True
    return False


def _as_list_restriction(rule: dict) -> list:
    out = []
    for key in ("card_type", "card_types", "subtype", "subtypes", "types"):
        val = rule.get(key)
        if isinstance(val, str):
            out.append(val)
        elif isinstance(val, (list, tuple)):
            out.extend(val)
    return out


def get_defendable_cards(state: GameState) -> list[Card]:
    """Return all cards the defender may use to defend (hand cards + equipment)."""
    combat = state.combat
    defender = state.players[3 - state.active_player]

    # If the attack targets an ally (not the hero), defender cannot declare defending cards
    if combat.attack_target is not None and combat.attack_target is not defender:
        return []

    defendable_cards = []
    for card in defender.hand.cards:
        # CR 7.3.2a: only NON-defense-reaction cards may be declared as blockers
        # during the Defend Step. Defense reactions are played in the Reaction
        # Step. (is_defense_reaction normalizes "DefenseReaction"/"Defense
        # Reaction" — the card DB uses the no-space spelling.)
        if card.is_defense_reaction:
            continue
        if not card.has_defense:
            continue
        if not _defend_restriction_met(state, card):
            continue
        # "This can't be defended by <X>" — a restriction the ATTACK imposes,
        # as opposed to _defend_restriction_met, which is the card's own "may
        # only defend if ..." clause.
        if _restriction_blocks(state, card, None):
            continue
        defendable_cards.append(card)

    # Headbutt (CR 8.x): "can't be defended by non-head equipment" — expressed
    # as a defender restriction like every other "can't be defended by"; the
    # legacy boolean is still honoured so nothing that set it directly breaks.
    head_only = getattr(combat, 'head_equipment_only', False)
    for slot_name in ("head", "chest", "arms", "legs"):
        if head_only and slot_name != "head":
            continue
        equip_zone = defender.zone_by_name(slot_name)
        if not equip_zone or not equip_zone.cards:
            continue
        equip_card = equip_zone.cards[0]
        if getattr(equip_card, 'face_down', False):
            continue
        if not equip_card.has_defense:
            continue
        if not _defend_restriction_met(state, equip_card):
            continue
        if _restriction_blocks(state, equip_card, slot_name):
            continue
        defendable_cards.append(equip_card)

    return defendable_cards


def _legal_defend_step(state: GameState, card_db: CardDB) -> list[Action]:
    """Fallback for legal_actions dispatch — per-card binary defend is driven by _defend_step."""
    return [Action(type=ActionType.PASS)]


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
            null_targets = _stack_instant_target_entries(state) if _is_null_meld_card(card) else None
            if can_pay_cost(player.hand.cards, card.cost or 0, player.resources, exclude_card=card):
                if null_targets is not None:
                    for target_entry in null_targets:
                        actions.append(Action(
                            type=ActionType.PLAY_CARD,
                            choose_index=i,
                            card=card,
                            target=target_entry.card,
                            targets=[f"oid:{target_entry.card.object_id}"],
                        ))
                else:
                    actions.append(Action(type=ActionType.PLAY_CARD, choose_index=i, card=card))
            # Bottom side at instant speed: always cost 0
            actions.append(Action(type=ActionType.PLAY_CARD, choose_index=i, card=card,
                                  meld_side='bottom'))
        else:
            # CR 5.1.4a: check required target exists
            _ri_base_slug = re.sub(r'_(red|yellow|blue)$', '', card.slug)
            _ri_ptc = PLAY_TARGET_CONDITIONS.get(_ri_base_slug)
            if _ri_ptc is not None and not _ri_ptc(state, pp):
                continue
            effective_cost = card.cost
            if can_pay_cost(player.hand.cards, effective_cost, player.resources, exclude_card=card):
                for _t in _legal_targets_for_card(state, pp, card):
                    actions.append(Action(type=ActionType.PLAY_CARD, choose_index=i, card=card, target=_t))

    # Instants from arsenal
    for i, card in enumerate(player.arsenal.cards):
        if "Instant" not in card.types:
            continue
        effective_cost = card.cost
        if not can_pay_cost(player.hand.cards, effective_cost, player.resources):
            continue
        null_targets = _stack_instant_target_entries(state) if _is_null_meld_card(card) else None
        if null_targets is not None and not null_targets:
            continue
        if null_targets is not None:
            for target_entry in null_targets:
                actions.append(Action(
                    type=ActionType.PLAY_ARSENAL,
                    choose_index=i,
                    card=card,
                    target=target_entry.card,
                    targets=[f"oid:{target_entry.card.object_id}"],
                ))
        else:
            for _t in _legal_targets_for_card(state, pp, card):
                actions.append(Action(type=ActionType.PLAY_ARSENAL, choose_index=i, card=card, target=_t))

    # ACTIVATE_EQUIPMENT (non-weapon) in reaction step
    # Only attacker can activate attack reaction equipment; only defender can activate defense reaction equipment
    for slot_name in ("head", "chest", "arms", "legs"):
        equip_zone = player.zone_by_name(slot_name)
        if not equip_zone or not equip_zone.cards:
            continue
        equip_card = equip_zone.cards[0]
        if getattr(equip_card, 'face_down', False):
            continue  # Face-down/cloaked equipment can't be activated
        equip_slug = equip_card.slug
        text = equip_card.functional_text or ""
        has_attack_reaction = bool(re.search(r'\*\*(?:\w+ per \w+ )?attack reaction\*\*\s*[—:\-]', text, re.IGNORECASE))
        has_defense_reaction = bool(re.search(r'\*\*(?:\w+ per \w+ )?defense reaction\*\*\s*[—:\-]', text, re.IGNORECASE))
        has_instant = bool(re.search(r'\*\*(?:\w+ per \w+ )?instant\*\*\s*[—:\-]', text, re.IGNORECASE))

        # Only attacker can activate attack reaction equipment
        if pp == attacker_id and not (has_attack_reaction or has_instant):
            continue
        # Only defender can activate defense reaction equipment
        if pp == defender_id and not (has_defense_reaction or has_instant):
            continue
        if has_attack_reaction and pp != attacker_id:
            continue
        if has_defense_reaction and pp != defender_id:
            continue
        if has_attack_reaction and player.action_points <= 0:
            continue
        if has_defense_reaction and player.action_points <= 0:
            continue
        if equip_card.exhausted:
            continue
        if equip_card.tapped:
            continue

        # Activation gate: the card's DSL ability costs must be payable.
        if not _dsl_activation_costs_payable(equip_card, state):
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
            if effective_cost is None:
                effective_cost = _parse_activation_cost_from_text(text)
        if can_pay_cost(player.hand.cards, effective_cost, player.resources):
            for _t in _legal_targets_for_card(state, pp, equip_card):
                actions.append(Action(
                    type=ActionType.ACTIVATE_CARD,
                    card=equip_card,
                    slot=slot_name,
                    target=_t,
                ))

    # ACTIVATE_ITEM (Instant)
    for i, card in enumerate(player.items.cards):
        can_activate_item = False
        if "**instant**" in (card.functional_text.lower() or ""):
            can_activate_item = True
        if card.cost is not None and card.cost != 0:
            if can_pay_cost(player.hand.cards, card.cost, player.resources):
                can_activate_item = True
            else:
                can_activate_item = False

        # Check additonal activation conditions from registry
        item_slug = card.slug
        cond_fn = EQUIPMENT_ACTIVATION_CONDITIONS.get(item_slug)
        if cond_fn is not None:
            import inspect as _inspect_r
            _sig_r = _inspect_r.signature(cond_fn)
            _cond_r = cond_fn(player, slot_name, card, state) if len(_sig_r.parameters) >= 4 else cond_fn(player, slot_name, card)
            if not _cond_r:
                continue

        if can_activate_item:
            for _t in _legal_targets_for_card(state, pp, card):
                actions.append(Action(type=ActionType.ACTIVATE_ITEM, card=card, target=_t))

    if pp == attacker_id:
        # Attack reactions from hand
        for i, card in enumerate(player.hand.cards):
            if "Attack Reaction" not in card.types:
                continue
            cond_fn = ATTACK_REACTION_CONDITIONS.get(card.slug)
            if cond_fn is not None and not cond_fn(combat):
                continue
            effective_cost = card.cost
            if can_pay_cost(player.hand.cards, effective_cost, player.resources, exclude_card=card):
                for _t in _legal_targets_for_card(state, pp, card):
                    actions.append(Action(type=ActionType.PLAY_ATTACK_REACTION, card=card, target=_t))

        # Attack reactions from arsenal
        for i, card in enumerate(player.arsenal.cards):
            if "Attack Reaction" not in card.types:
                continue
            cond_fn = ATTACK_REACTION_CONDITIONS.get(card.slug)
            if cond_fn is not None and not cond_fn(combat):
                continue
            effective_cost = card.cost
            if can_pay_cost(player.hand.cards, effective_cost, player.resources):
                for _t in _legal_targets_for_card(state, pp, card):
                    actions.append(Action(
                        type=ActionType.PLAY_ATTACK_REACTION,
                        card=card,
                        from_arsenal=True,
                        target=_t,
                    ))

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
                    if cond_fn is not None and not cond_fn(combat):
                        continue
                    effective_cost = card.cost
                    if can_pay_cost(player.hand.cards, effective_cost, player.resources, exclude_card=card):
                        for _t in _legal_targets_for_card(state, pp, card):
                            actions.append(Action(type=ActionType.PLAY_DEFENSE_REACTION, card=card, target=_t))

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
                    if can_pay_cost(player.hand.cards, effective_cost, player.resources):
                        for _t in _legal_targets_for_card(state, pp, card):
                            actions.append(Action(
                                type=ActionType.PLAY_DEFENSE_REACTION,
                                card=card,
                                from_arsenal=True,
                                target=_t,
                            ))

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
            actions.append(Action(type=ActionType.STORE_ARSENAL, choose_index=i))

    return actions
