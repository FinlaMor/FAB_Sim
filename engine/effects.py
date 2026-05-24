"""Effect system for FAB engine — continuous effects, replacement effects, and staging.

Rules references:
  6.2 Continuous Effects (layer-continuous and static-continuous)
  6.3 Continuous Effect Interactions (staging system, stages 1-8, substages 1-7)
  6.4 Replacement Effects (self, identity, standard, prevention, outcome)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from engine.state import GameState
    from engine.card import Card


# ---------------------------------------------------------------------------
# Continuous Effects (6.2)
# ---------------------------------------------------------------------------

class EffectSource(Enum):
    """Where the continuous effect came from."""
    LAYER = "layer"       # 6.2.2 — from a resolved layer on the stack
    STATIC = "static"     # 6.2.3 — from a static ability on a card


class ModType(Enum):
    """How the effect modifies a numeric property (substage order per 6.3.3)."""
    ADD_PROPERTY = 1      # substage 1: add/remove a property
    SET = 2               # substage 2: set value
    MULTIPLY = 3          # substage 3: multiply
    DIVIDE = 4            # substage 4: divide
    ADD = 5               # substage 5: add to value
    SUBTRACT = 6          # substage 6: subtract from value
    DEPENDENT = 7         # substage 7: dependent effects


@dataclass
class ContinuousEffect:
    """A single continuous effect applied to the game or an object.

    Rules 6.2: continuous effects modify objects/rules and persist for a duration.
    Rules 6.3: effects are applied using the staging system (stages 1-8).
    """
    source_card: Card                      # card that generated this effect
    source_type: EffectSource              # layer or static
    stage: int                             # 1-8 per rules 6.3.2
    substage: int = 5                      # 1-7 per rules 6.3.3 (default: add)
    mod_type: ModType = ModType.ADD        # how it modifies numeric properties
    target_property: str = ""              # e.g. "power", "defense", "cost"
    value: int = 0                         # the modification value
    apply_fn: Optional[Callable] = None    # custom apply function(card, state) -> None
    condition_fn: Optional[Callable] = None  # when to apply (returns bool)
    target_fn: Optional[Callable] = None   # which cards it applies to (card, state) -> bool
    duration: Optional[str] = None         # "end_of_turn", "end_of_next_turn", "permanent", None
    timestamp: int = 0                     # for ordering within same substage (6.3.4)
    consumed: bool = False                 # for "next X" effects — consumed after first apply
    owner_id: int = 0                      # player who controls this effect

    def applies_to(self, card: Card, state: GameState) -> bool:
        """Check if this effect should apply to a given card."""
        if self.consumed:
            return False
        if self.condition_fn and not self.condition_fn(state):
            return False
        if self.target_fn and not self.target_fn(card, state):
            return False
        return True

    def apply(self, card: Card, state: GameState) -> None:
        """Apply this effect to a card."""
        if self.apply_fn:
            self.apply_fn(card, state)
        elif self.target_property:
            _apply_numeric_mod(card, self.target_property, self.mod_type, self.value)

    def is_expired(self, state: GameState) -> bool:
        """Check if this effect has expired based on duration."""
        if self.consumed:
            return True
        if self.source_type == EffectSource.STATIC:
            # Static effects last as long as source is functional (6.2.3a)
            return not self.source_card.is_public
        return False  # layer effects track duration externally


def _apply_numeric_mod(card: Card, prop: str, mod_type: ModType, value: int) -> None:
    """Apply a numeric modification to a card property."""
    base_attr = f"base_{prop}"
    if not hasattr(card, base_attr):
        return
    current = getattr(card, base_attr) or 0
    if mod_type == ModType.SET:
        card.effects.append((base_attr, lambda _: value))
    elif mod_type == ModType.ADD:
        card.effects.append((base_attr, lambda base, v=value: base + v))
    elif mod_type == ModType.SUBTRACT:
        card.effects.append((base_attr, lambda base, v=value: base - v))
    elif mod_type == ModType.MULTIPLY:
        card.effects.append((base_attr, lambda base, v=value: base * v))
    elif mod_type == ModType.DIVIDE:
        card.effects.append((base_attr, lambda base, v=value: base // v if v else base))


# ---------------------------------------------------------------------------
# Replacement Effects (6.4)
# ---------------------------------------------------------------------------

class ReplacementType(Enum):
    """Type of replacement effect per rules 6.4."""
    SELF = "self"               # 6.4.7 — replaces its own preceding effect
    IDENTITY = "identity"       # 6.4.8 — modifies how an object enters play
    STANDARD = "standard"       # 6.4.9 — general replacement
    PREVENTION = "prevention"   # 6.4.10 — prevents damage
    OUTCOME = "outcome"         # 6.4.11 — replaces outcome of an event


@dataclass
class ReplacementEffect:
    """A replacement effect that intercepts events before they occur.

    Rules 6.4: replacement effects replace events with modified events.
    Rules 6.5: ordering — self/identity first, then standard, then prevention, then outcome.
    """
    source_card: Card
    replacement_type: ReplacementType
    condition_fn: Callable          # (event, state) -> bool: should this replace?
    replace_fn: Callable            # (event, state) -> modified_event
    owner_id: int = 0
    consumed: bool = False          # for one-shot replacements
    prevention_amount: int = 0      # for prevention effects (6.4.10)
    is_shielding: bool = False      # shielding vs fixed prevention (6.4.10i/j)

    def is_active(self, event, state: GameState) -> bool:
        """Check if this replacement effect should apply to the event."""
        if self.consumed:
            return False
        return self.condition_fn(event, state)

    def apply(self, event: dict, state: GameState) -> dict:
        """Apply the replacement, returning the modified event."""
        modified = self.replace_fn(event, state)
        if not self.is_shielding and self.replacement_type == ReplacementType.PREVENTION:
            self.consumed = True
        return modified


# ---------------------------------------------------------------------------
# Effect Manager — tracks all active effects and applies staging
# ---------------------------------------------------------------------------

class EffectManager:
    """Manages all continuous and replacement effects in the game.

    Applies continuous effects using the staging system (6.3).
    Routes replacement effects in the correct order (6.5).
    """

    def __init__(self):
        from engine.continuous_effects import ContinuousEffectManager
        self.staging: ContinuousEffectManager = ContinuousEffectManager()
        self.continuous_effects: list[ContinuousEffect] = []
        self.replacement_effects: list[ReplacementEffect] = []
        self._timestamp: int = 0

    def _next_timestamp(self) -> int:
        self._timestamp += 1
        return self._timestamp

    # -- Continuous effects --

    def add_continuous(self, effect: ContinuousEffect) -> None:
        """Add a continuous effect to the game."""
        effect.timestamp = self._next_timestamp()
        self.continuous_effects.append(effect)

    def remove_expired(self, state: GameState) -> None:
        """Remove continuous effects that have expired."""
        self.continuous_effects = [e for e in self.continuous_effects if not e.is_expired(state)]

    def apply_continuous_effects(self, card: Card, state: GameState) -> None:
        """Apply all active continuous effects to a card using staging (6.3).

        Stage order (6.3.2): 1-8
        Substage order within stages 7-8 (6.3.3): 1-7
        Timestamp order within substage (6.3.4): chronological
        """
        applicable = [e for e in self.continuous_effects if e.applies_to(card, state)]
        # Sort by stage, then substage, then timestamp
        applicable.sort(key=lambda e: (e.stage, e.substage, e.timestamp))
        for effect in applicable:
            effect.apply(card, state)

    def clear_turn_effects(self) -> None:
        """Remove all layer-continuous effects that expire at end of turn.
        CR 6.2.2a: if no duration is specified, a layer-continuous effect ends at end of turn.
        """
        self.continuous_effects = [
            e for e in self.continuous_effects
            if not (e.source_type == EffectSource.LAYER and e.duration in ("end_of_turn", None))
        ]

    def clear_start_of_turn_effects(self) -> None:
        """Remove all layer-continuous effects with 'end_of_next_turn' duration (CR 4.2.2)."""
        self.continuous_effects = [
            e for e in self.continuous_effects
            if not (e.source_type == EffectSource.LAYER and e.duration == "end_of_next_turn")
        ]

    # -- Replacement effects --

    def add_replacement(self, effect: ReplacementEffect) -> None:
        """Add a replacement effect."""
        self.replacement_effects.append(effect)

    def apply_replacements(self, event, state: GameState):
        """Apply replacement effects to an event in rules order (CR 6.5).

        Order: self/identity → standard → prevention → outcome (CR 6.5.1)

        CR 6.4.5: A replacement effect can only replace a given event once.
        CR 6.5.2: When multiple prevention effects apply, the AFFECTED player
        (damage target) chooses which to apply, one at a time. After each
        application the remaining active effects are re-evaluated — the player
        keeps choosing until either all damage is prevented or no more
        prevention effects are available.

        Unpreventable damage: self-sacrifice prevention effects (Ward, Spellvoid,
        Arcane Shelter) still fire and destroy themselves — but do not reduce
        damage. The loop does NOT stop early, so every effect gets a chance to
        attempt prevention (and fail). Fixed-cost effects (Arcane Barrier, Quell)
        do not fire against unpreventable damage at all.
        """
        type_order = [
            ReplacementType.SELF,
            ReplacementType.IDENTITY,
            ReplacementType.STANDARD,
            ReplacementType.PREVENTION,
            ReplacementType.OUTCOME,
        ]
        applied_ids: set = set()
        is_unpreventable = bool(event.get("unpreventable", False))

        for rtype in type_order:
            if rtype == ReplacementType.PREVENTION:
                # Step-by-step: affected player picks one prevention effect at a time.
                while True:
                    active = [
                        r for r in self.replacement_effects
                        if r.replacement_type == rtype
                        and r.is_active(event, state)
                        and id(r) not in applied_ids
                    ]
                    if not active:
                        break
                    # Normal damage: stop once fully prevented
                    if not is_unpreventable and event.get("amount", 0) <= 0:
                        break

                    # Affected player (damage target) chooses which effect to apply next
                    chosen = _choose_prevention(active, event, state)
                    event = chosen.apply(event, state)
                    applied_ids.add(id(chosen))
                    # Purge consumed effects immediately so they don't re-appear in choices
                    self.replacement_effects = [
                        r for r in self.replacement_effects if not r.consumed
                    ]
            else:
                active = [
                    r for r in self.replacement_effects
                    if r.replacement_type == rtype
                    and r.is_active(event, state)
                    and id(r) not in applied_ids
                ]
                if not active:
                    continue
                # CR 6.5.2: affected/active player orders multiple same-type effects
                if len(active) > 1:
                    active = _order_effects(active, event, state)
                for r in active:
                    if id(r) in applied_ids:
                        continue
                    event = r.apply(event, state)
                    applied_ids.add(id(r))
                self.replacement_effects = [
                    r for r in self.replacement_effects if not r.consumed
                ]

        return event

    # -- Prevention effect builders --

    def register_prevention_effects(self, card: Card, state: GameState) -> None:
        """Register prevention replacement effects from a card's keywords.
        Called when a card enters the arena or becomes public."""
        import re
        keywords = card.base_ability_keywords or []
        for kw in keywords:
            # Normalize CamelCase keywords from card DB (e.g. "ArcaneBarrier" -> "arcane barrier")
            kw_spaced = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', kw.strip())
            kw_lower = kw_spaced.lower()
            kw_base = re.sub(r'\s+\d+$', '', kw_lower).strip()
            num_match = re.search(r'(\d+)$', kw)
            amount = int(num_match.group(1)) if num_match else 0

            if kw_base == "ward":
                self.add_replacement(_make_ward(card, amount))
            elif kw_base == "arcane barrier":
                self.add_replacement(_make_arcane_barrier(card, amount))
            elif kw_base == "spellvoid":
                self.add_replacement(_make_spellvoid(card, amount))
            elif kw_base == "quell":
                self.add_replacement(_make_quell(card, amount))
            elif kw_base == "arcane shelter":
                self.add_replacement(_make_arcane_shelter(card, amount))


# ---------------------------------------------------------------------------
# Replacement-effect ordering helpers (CR 6.5.2)
# ---------------------------------------------------------------------------

def _affected_player(event: dict, state: "GameState") -> int:
    """Return the player id of the damage target, falling back to active player."""
    pid = event.get("target_player_id")
    if pid is not None:
        return pid
    return getattr(state, "active_player", 1)


def _choose_prevention(effects: list, event: dict, state: "GameState") -> "ReplacementEffect":
    """CR 6.5.2: Affected player picks which prevention effect to apply next.

    Presents a CHOOSE action for each available effect. The context string names
    the source card so the player can identify Ward, Arcane Barrier, etc.
    Falls back to list order when no agent is available.
    """
    if len(effects) == 1:
        return effects[0]
    affected_pid = _affected_player(event, state)
    try:
        from engine.actions import Action, ActionType
        options = [
            Action(
                type=ActionType.CHOOSE,
                choose_index=i,
                card=r.source_card,
                slot=getattr(r.source_card, "slug", None),
            )
            for i, r in enumerate(effects)
        ]
        agents = getattr(state, "player_agents", {})
        agent = agents.get(affected_pid)
        if agent is not None:
            choice = agent(
                state, options,
                f"Choose which prevention effect applies next (CR 6.5.2) — "
                f"{event.get('amount', 0)} damage remaining",
            )
            idx = getattr(choice, "choose_index", 0)
            idx = max(0, min(idx, len(effects) - 1))
            return effects[idx]
    except Exception:
        pass
    return effects[0]


def _order_effects(effects: list, event: dict, state: "GameState") -> list:
    """CR 6.5.2: Affected player orders multiple same-type non-prevention effects."""
    if len(effects) <= 1:
        return effects
    affected_pid = _affected_player(event, state)
    try:
        from engine.actions import Action, ActionType
        ordered: list = []
        remaining = list(effects)
        while len(remaining) > 1:
            options = [
                Action(
                    type=ActionType.CHOOSE,
                    choose_index=i,
                    card=r.source_card,
                    slot=getattr(r.source_card, "slug", None),
                )
                for i, r in enumerate(remaining)
            ]
            agents = getattr(state, "player_agents", {})
            agent = agents.get(affected_pid)
            if agent is None:
                from numpy.random import default_rng as _rng
                rand = _rng()
                choice = options[rand.choice(range(len(options)))]
            else: 
                choice = agent(
                state, options,
                "Choose which replacement effect applies first (CR 6.5.2)",
            )
            idx = getattr(choice, "choose_index", 0)
            idx = max(0, min(idx, len(remaining) - 1))
            ordered.append(remaining.pop(idx))
        ordered.extend(remaining)
        return ordered
    except Exception:
        return effects


# ---------------------------------------------------------------------------
# Prevention effect builders
# ---------------------------------------------------------------------------

def _make_ward(source_card: Card, amount: int) -> ReplacementEffect:
    """8.3.20: Ward N — destroy this to prevent N damage. NOT optional.

    Unpreventable damage: the card still destroys itself (the cost is paid) but
    the damage amount is not reduced — Ward cannot prevent unpreventable damage.
    """
    def _condition(event, state):
        if event.get("type") != "damage" or event.get("amount", 0) <= 0:
            return False
        target_pid = event.get("target_player_id")
        cid = source_card.controller if source_card.controller is not None else source_card.owner
        return target_pid == cid and source_card.zone in (
            "head", "chest", "arms", "legs", "weapon", "permanents", "hero",
        )

    def _replace(event, state):
        from engine.effect_keywords import destroy as _ek_destroy
        _ek_destroy(state, source_card, None)  # Cost always paid (destroy this)
        if not event.get("unpreventable", False):
            prevented = min(amount, event.get("amount", 0))
            event["amount"] = event.get("amount", 0) - prevented
        return event

    return ReplacementEffect(
        source_card=source_card,
        replacement_type=ReplacementType.PREVENTION,
        condition_fn=_condition,
        replace_fn=_replace,
        owner_id=source_card.controller or source_card.owner,
        prevention_amount=amount,
        is_shielding=False,
    )


def _make_arcane_barrier(source_card: Card, amount: int) -> ReplacementEffect:
    """8.3.8: Arcane Barrier N — optional, pay N resources to prevent N arcane damage."""
    def _condition(event, state):
        if event.get("type") != "damage" or event.get("damage_type") != "arcane":
            return False
        if event.get("amount", 0) <= 0:
            return False
        if event.get("unpreventable", False):
            return False  # CR 6.4.10: fixed-cost effects cannot prevent unpreventable damage
        target_pid = event.get("target_player_id")
        cid = source_card.controller if source_card.controller is not None else source_card.owner
        return target_pid == cid and source_card.zone in (
            "head", "chest", "arms", "legs", "weapon", "permanents", "hero",
        )

    def _replace(event, state):
        from engine.card_effects.ability_keywords import arcane_barrier
        # arcane_barrier handles the player decision and pitching

        prevented = arcane_barrier(source_card, amount, state)
        event["amount"] = max(0, event.get("amount", 0) - prevented)
        return event

    return ReplacementEffect(
        source_card=source_card,
        replacement_type=ReplacementType.PREVENTION,
        condition_fn=_condition,
        replace_fn=_replace,
        owner_id=source_card.controller or source_card.owner,
        prevention_amount=amount,
        is_shielding=True,  # Can be used repeatedly
    )


def _make_spellvoid(source_card: Card, amount: int) -> ReplacementEffect:
    """8.3.15: Spellvoid N — optional, destroy this to prevent N arcane damage."""
    def _condition(event, state):
        if event.get("type") != "damage" or event.get("damage_type") != "arcane":
            return False
        if event.get("amount", 0) <= 0:
            return False
        target_pid = event.get("target_player_id")
        cid = source_card.controller if source_card.controller is not None else source_card.owner
        # Must still be in an arena zone (not already destroyed)
        return target_pid == cid and source_card.zone in (
            "head", "chest", "arms", "legs", "weapon", "permanents", "hero",
        )

    def _replace(event, state):
        from engine.card_effects.ability_keywords import spellvoid

        prevented = spellvoid(source_card, amount, state)
        event["amount"] = event.get("amount", 0) - prevented
        return event

    return ReplacementEffect(
        source_card=source_card,
        replacement_type=ReplacementType.PREVENTION,
        condition_fn=_condition,
        replace_fn=_replace,
        owner_id=source_card.controller or source_card.owner,
        prevention_amount=amount,
        is_shielding=False,
    )


def _make_quell(source_card: Card, amount: int) -> ReplacementEffect:
    """8.3.19: Quell N — optional, pay N resources to prevent N damage (any type).
    Destroyed at beginning of end phase if used."""
    def _condition(event, state):
        if event.get("type") != "damage" or event.get("amount", 0) <= 0:
            return False
        if event.get("unpreventable", False):
            return False  # fixed-cost effects cannot prevent unpreventable damage
        target_pid = event.get("target_player_id")
        cid = source_card.controller if source_card.controller is not None else source_card.owner
        return target_pid == cid and source_card.zone in (
            "head", "chest", "arms", "legs", "weapon", "permanents", "hero",
        )

    def _replace(event, state):
        from engine.card_effects.ability_keywords import quell

        prevented = quell(source_card, amount, state)
        event["amount"] = event.get("amount", 0) - prevented
        return event

    return ReplacementEffect(
        source_card=source_card,
        replacement_type=ReplacementType.PREVENTION,
        condition_fn=_condition,
        replace_fn=_replace,
        owner_id=source_card.controller or source_card.owner,
        prevention_amount=amount,
        is_shielding=True,  # Can be used repeatedly (until destroyed at end phase)
    )


def _make_arcane_shelter(source_card: Card, amount: int) -> ReplacementEffect:
    """8.3.37: Arcane Shelter N — destroy this to prevent N arcane damage. NOT optional."""
    def _condition(event, state):
        if event.get("type") != "damage" or event.get("damage_type") != "arcane":
            return False
        if event.get("amount", 0) <= 0:
            return False
        target_pid = event.get("target_player_id")
        cid = source_card.controller if source_card.controller is not None else source_card.owner
        return target_pid == cid and source_card.zone in (
            "head", "chest", "arms", "legs", "weapon", "permanents", "hero",
        )

    def _replace(event, state):
        from engine.effect_keywords import destroy as _ek_destroy
        prevented = min(amount, event.get("amount", 0))
        _ek_destroy(state, source_card, None)
        event["amount"] = event.get("amount", 0) - prevented
        return event

    return ReplacementEffect(
        source_card=source_card,
        replacement_type=ReplacementType.PREVENTION,
        condition_fn=_condition,
        replace_fn=_replace,
        owner_id=source_card.controller or source_card.owner,
        prevention_amount=amount,
        is_shielding=False,
    )
