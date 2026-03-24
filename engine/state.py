"""Game state data structures for FAB self-play engine (OO rewrite).

Zone reference (Talishar: Constants.php — BanishPieces=3, ChainLinksPieces=10,
CombatChainPieces=12, ArsenalPieces=7).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional
from engine.card import Card, CardDB


class Step(Enum):
    BEGIN_GAME = 'begin_game'
    START_PHASE = 'start_phase'              # CR 4.2
    ACTION = "action"
    COMBAT_LAYER = 'combat_layer'
    COMBAT_ATTACK = 'combat_attack'
    COMBAT_DEFEND = "combat_defend"
    COMBAT_REACTION = "combat_reaction"
    COMBAT_DAMAGE = "combat_damage"
    COMBAT_RESOLUTION = "combat_resolution"
    COMBAT_CLOSE = "combat_close"
    END_PHASE_BEGINNING = 'end_phase_beginning'  # CR 4.4.2
    END_PHASE_CLEANUP = 'end_phase_cleanup'      # CR 4.4.3
    END_TURN = "end_turn"
    END_GAME = "end_game"



class Zone:
    """A named collection of Card objects. The fundamental building block of OO game state."""

    def __init__(self, name: str, owner_id: Optional[int] = None):
        self.name = name
        self.owner_id = owner_id
        self.cards: list[Card] = []

    @property
    def is_public(self) -> bool:
        return self.name not in ('hand', 'deck', 'arsenal', 'inventory')

    def add(self, card: Card, is_public: Optional[bool] = None) -> None:
        """Move card into this zone, updating card.prev_zone / card.zone / card.is_public."""
        next_is_public = self.is_public if is_public is None else is_public
        card.remember_last_known_state()
        card.prev_zone = card.zone
        card.zone = self.name
        card.is_public = next_is_public
        if card not in self.cards:
            self.cards.append(card)

    def remove(self, card: Card) -> bool:
        if card in self.cards:
            self.cards.remove(card)
            return True
        return False

    def find(self, slug: str) -> Optional[Card]:
        return next((c for c in self.cards if c.slug == slug), None)

    def find_all(self, slug: str) -> list[Card]:
        return [c for c in self.cards if c.slug == slug]

    def add_bottom(self, card: Card, is_public: Optional[bool] = None) -> None:
        """Add card to the bottom of this zone (e.g. bottom of deck)."""
        next_is_public = self.is_public if is_public is None else is_public
        card.remember_last_known_state()
        card.prev_zone = card.zone
        card.zone = self.name
        card.is_public = next_is_public
        self.cards.append(card)

    def pop_top(self) -> Optional[Card]:
        return self.cards.pop(0) if self.cards else None

    def pop_last(self) -> Optional[Card]:
        """Pop from the end (LIFO / stack semantics)."""
        return self.cards.pop() if self.cards else None

    def extend(self, cards) -> None:
        """Add multiple cards, calling add() for each (updates zone tracking)."""
        for card in cards:
            self.add(card)

    @property
    def top(self) -> Optional[Card]:
        return self.cards[0] if self.cards else None

    @property
    def slugs(self) -> list[str]:
        return [c.slug for c in self.cards]

    def __len__(self) -> int:
        return len(self.cards)

    def __bool__(self) -> bool:
        return bool(self.cards)

    def __iter__(self):
        return iter(list(self.cards))

    def __repr__(self) -> str:
        return f"Zone({self.name!r}, {self.slugs})"

    def to_dict(self) -> dict:
        """Convert the Zone instance to a dictionary representation.
        
        Returns:
            dict: A dictionary containing zone name, owner_id, and card information.
        """
        return {
            'name': self.name,
            'owner_id': self.owner_id,
            'cards': [card.to_dict() for card in self.cards]
        }

class SubZoneView:
    """A filtered, mutable view over a parent Zone, selecting cards by type tag."""

    def __init__(self, parent: Zone, subtype: str):
        self.parent = parent
        self.subtype = subtype  # e.g., "Item", "Aura", "Ally", "Token", "Soul"

    @property
    def cards(self) -> list[Card]:
        return [c for c in self.parent.cards if self._matches(c)]

    def add(self, card: Card, is_public=None) -> None:
        card.permanent_subtype = self.subtype
        self.parent.add(card, is_public)

    def remove(self, card: Card) -> bool:
        return self.parent.remove(card)

    def find(self, slug: str) -> Optional[Card]:
        return next((c for c in self.cards if c.slug == slug), None)

    def find_all(self, slug: str) -> list[Card]:
        return [c for c in self.cards if c.slug == slug]

    def extend(self, cards) -> None:
        for card in cards:
            self.add(card)

    def _matches(self, card: Card) -> bool:
        if self.subtype == "Soul":
            return getattr(card, 'permanent_subtype', None) == "Soul"
        return self.subtype in getattr(card, 'types', []) or getattr(card, 'permanent_subtype', None) == self.subtype

    def __len__(self): return len(self.cards)
    def __bool__(self): return bool(self.cards)
    def __iter__(self): return iter(list(self.cards))
    def __repr__(self): return f"SubZoneView({self.parent.name!r}, {self.subtype!r}, {[c.slug for c in self.cards]})"

    def to_dict(self) -> dict:
        """Convert the SubZoneView to a dictionary representation."""
        return {
            'name': f"{self.parent.name}:{self.subtype}",
            'owner_id': self.parent.owner_id,
            'cards': [card.to_dict() for card in self.cards]
        }


class EventManager:
    def __init__(self):
        self.listeners: dict = {}

    def register(self, event_name: str, listener) -> None:
        self.listeners.setdefault(event_name, []).append(listener)

    def emit(self, event, game_state: GameState) -> None:
        """Emit an event. Accepts an Event object or a string event type."""
        if isinstance(event, str):
            event = Event(type=event)

        # Track coarse event history for state embedding features.
        if hasattr(game_state, 'events_this_turn') and isinstance(game_state.events_this_turn, set):
            game_state.events_this_turn.add(event.type)

        for listener in self.listeners.get(event.type, []):
            listener(event, game_state)

@dataclass
class Event:
    type: str
    card: Optional[str] = None
    target: Optional[str] = None
    data: dict = field(default_factory=dict)


class TriggeredAbility:
    def __init__(self, trigger_event: str, effect, card: Card):
        self.trigger_event = trigger_event
        self.effect = effect
        self.card = card

    def register(self, event_manager: EventManager) -> None:
        event_manager.register(self.trigger_event, self.trigger)
    
    def trigger(self, event: Event, game_state: GameState) -> None:
        # Put on stack instead of executing
        # CR 1.6.2c: Triggered effect (triggered-layer)
        # CR 3.15.4: layer position is N+1 where N is existing layers
        stack_entry = StackEntry(
            player_id=self.card.owner,
            card=self.card,
            layer_type='triggered',
            layer_position=len(game_state.stack_entries) + 1,
            from_arsenal=False,
            is_triggered=True,
            trigger_event=self.trigger_event
        )
        game_state.stack.add(self.card)
        game_state.stack_entries.append(stack_entry)

    def resolve(self, event: Event) -> None:
        self.effect(event)


class Player:
    """Full player state. Replaces PlayerState dict-of-lists model with Zone objects."""

    def __init__(self, player_id: int, hero_card: Card):
        self.player_id = player_id
        self.hero = hero_card
        self.health: int = hero_card.life or 40
        self.intellect: int = hero_card.intellect or 4
        self.resources: int = 0
        self.action_points: int = 1
        self.weapon_exhausted: bool = False
        self.weapon_power_bonus: int = 0
        self.hero_power_exhausted: bool = False
        self.counters: dict[tuple[str, str, str], int] = {} # e.g {["dawnblade", "weapon", "plus_attack"]:1, ["tectonic_plating", "chest", "minus_defense"]:-1}

        # All zones
        self.hand = Zone("hand", player_id)
        self.deck = Zone("deck", player_id)
        self.arsenal = Zone("arsenal", player_id)
        self.inventory = Zone("inventory", player_id) # current iteration of deck.py doesnt sideboard on initialization. 'inventory' zone is for future code
        self.graveyard = Zone("graveyard", player_id)
        self.banished = Zone("banished", player_id)
        self.head = Zone("head", player_id)
        self.chest = Zone("chest", player_id)
        self.arms = Zone("arms", player_id)
        self.legs = Zone("legs", player_id)
        # CR 3.0.2: "Each player has two weapon zones"
        self.weapon1 = Zone("weapon1", player_id)
        self.weapon2 = Zone("weapon2", player_id)
        # CR: single permanents zone with sub-zone views
        self.permanents = Zone("permanents", player_id)
        self.items = SubZoneView(self.permanents, "Item")
        self.auras = SubZoneView(self.permanents, "Aura")
        self.allies = SubZoneView(self.permanents, "Ally")
        self.tokens = SubZoneView(self.permanents, "Token")
        self.soul = SubZoneView(self.permanents, "Soul")
        self.hero_zone = Zone("hero", player_id)
        self.pitch = Zone("pitch", player_id)  # cards pitched this turn (public; go to deck bottom at end of turn)

        # Hero card setup
        hero_card.zone = "hero"
        hero_card.owner = player_id
        hero_card.controller = player_id
        hero_card.is_public = True
        self.hero_zone.cards.append(hero_card)

        # Turn tracking
        self.arsenal_limit: int = 1
        self.current_turn_effects: list[str] = []
        self.next_turn_effects: list[str] = []
        self.class_counters: dict[str, int] = {}
        self.allies_exhausted: list[bool] = []

        # Conditions (9.3)
        self.marked: bool = False  # 9.3: marked condition — cleared when hit by opponent

        # Equipment defense tracking (for Battleworn/Temper/Blade Break)
        self.equipment_defended_this_turn: list[str] = []
    
    @property
    def weapon(self) -> Zone:
        """Backward compatibility: returns weapon1.
        Use weapon1/weapon2 explicitly for CR-compliant dual-zone handling."""
        return self.weapon1

    @property
    def arena_cards(self) -> list[Card]:
        arena_zones = [self.head, self.chest, self.arms, self.legs, self.weapon1, self.weapon2, self.permanents, self.hero_zone]
        cards = []
        for z in arena_zones:
            cards.extend(z.cards)
        return cards

    @property
    def public_cards(self) -> list[Card]:
        zones = self.all_zones()
        cards = []
        for z in zones:
            cards.extend(c for c in z.cards if c.is_public)
        return cards

    @property
    def equipment(self) -> list[Card]:
        equip_zones = [self.head, self.chest, self.arms, self.legs]
        cards = []
        for z in equip_zones:
            cards.extend(z.cards)
        return cards

    def all_zones(self) -> list[Zone]:
        return [self.hand, self.deck, self.graveyard, self.arsenal, self.banished,
                self.head, self.chest, self.arms, self.legs, self.weapon1, self.weapon2,
                self.permanents,
                self.inventory, self.hero_zone, self.pitch]

    def zone_by_name(self, name: str) -> Optional[Zone]:
        return {
            "hand": self.hand, "deck": self.deck, "graveyard": self.graveyard,
            "arsenal": self.arsenal, "banished": self.banished, "head": self.head,
            "chest": self.chest, "arms": self.arms, "legs": self.legs,
            "weapon": self.weapon1, "weapon1": self.weapon1, "weapon2": self.weapon2,
            "permanents": self.permanents,
            "items": self.items, "auras": self.auras,
            "allies": self.allies, "soul": self.soul, "tokens": self.tokens,
            "inventory": self.inventory, "hero": self.hero_zone, "pitch": self.pitch,
        }.get(name)

    def find_card(self, slug: str) -> Optional[Card]:
        for z in self.all_zones():
            c = z.find(slug)
            if c:
                return c
        return None

    @property
    def arsenal_card(self) -> Optional[Card]:
        return self.arsenal.top

    @property
    def arsenal_face_up(self) -> bool:
        card = self.arsenal_card
        if card is None:
            return False
        return card.is_public
    
    def to_dict(self) -> dict:
        """Convert player state to a dictionary representation."""
        return {
            "player_id": self.player_id,
            "hero": self.hero.to_dict() if hasattr(self.hero, 'to_dict') else str(self.hero),
            "health": self.health,
            "intellect": self.intellect,
            "resources": self.resources,
            "action_points": self.action_points,
            "weapon_exhausted": self.weapon_exhausted,
            "weapon_power_bonus": self.weapon_power_bonus,
            "hero_power_exhausted": self.hero_power_exhausted,
            "counters": {str(key): value for key, value in self.counters.items()},
            
            # Zones
            "hand": self.hand.to_dict(),
            "deck": self.deck.to_dict(),
            "arsenal": self.arsenal.to_dict(),
            "inventory": self.inventory.to_dict(),
            "graveyard": self.graveyard.to_dict(),
            "banished": self.banished.to_dict(),
            "head": self.head.to_dict(),
            "chest": self.chest.to_dict(),
            "arms": self.arms.to_dict(),
            "legs": self.legs.to_dict(),
            "weapon1":	self.weapon1.to_dict(),
            "weapon2":	self.weapon2.to_dict(),
            "permanents":	self.permanents.to_dict(),
            # Backward-compat sub-zone keys
            "items":	self.items.to_dict(),
            "auras":	self.auras.to_dict(),
            "allies":	self.allies.to_dict(),
            "tokens":	self.tokens.to_dict(),
            "soul":	self.soul.to_dict(),
            "hero_zone":	self.hero_zone.to_dict(),
            "pitch":	self.pitch.to_dict(),

            # Turn tracking
            "arsenal_limit":	self.arsenal_limit,
            "current_turn_effects":	self.current_turn_effects.copy(),
            "next_turn_effects":	self.next_turn_effects.copy(),
            "class_counters":	self.class_counters.copy(),
            "allies_exhausted":[x for x in  [ally.exhausted if hasattr(ally,'exhausted') else None 
                                            for ally in  getattr(self,'allies',[])] 
                                if x is not None],

            # Conditions (9•3)
            'marked':getattr(self,'marked',False),

            # Equipment defense tracking
            'equipment_defended_this_turn':getattr(self,'equipment_defended_this_turn',[]).copy()
            }


@dataclass
class StackEntry:
    """One card waiting to resolve on the stack (CR 3.0.1).
    
    Layer System (CR 1.6.2):
    - Card-layer: card played to stack
    - Activated-layer: activated ability on stack
    - Triggered-layer: triggered effect on stack
    """
    player_id: int
    card: Card
    layer_type: str = 'card'  # 'card', 'activated', 'triggered'
    layer_position: int = 0  # N value (position in stack)
    from_arsenal: bool = False
    
    # Modal/targeting metadata (CR 1.7.5, 1.8.5, 5.1.3a)
    declared_modes: list[str] = field(default_factory=list)  # e.g., ['first_mode', 'second_mode']
    declared_targets: list[str] = field(default_factory=list)  # card slugs or 'hero'
    declared_x: Optional[int] = None  # X-cost declaration
    
    # Triggered metadata (CR 5.4.6)
    is_triggered: bool = False  # Legacy compatibility
    trigger_event: Optional[str] = None  # e.g., 'hit_hero', 'end_of_turn'
    effect_fn: Optional[Callable] = None  # effect to run on resolution

    # Meld two-pass resolution (CR 5.3.4d)
    resolution_count: int = 0          # 0=before first, 1=after first; only used for meld 'both'
    meld_effect_bottom: Optional[Callable] = None  # right-side (Shock) effect for meld 'both'
    meld_effect_top: Optional[Callable] = None     # left-side (Comet Storm/Consign/Null) effect

    @property
    def slug(self) -> str:
        return self.card.slug

    @property
    def is_attack(self) -> bool:
        # CR 1.6.2b: Weapon attacks (activated-layer) must enter combat
        if self.layer_type == 'activated' and self.card and self.card.is_weapon:
            return True
        return self.card.is_attack if self.card else False
    
    def to_dict(self):
        return {
            'player': self.player_id,
            'card': self.card.to_dict(),
            'layer_type': self.layer_type,
            'layer_position': self.layer_position,
            'from_arsenal': self.from_arsenal,
            'declared_modes': self.declared_modes.copy() if self.declared_modes else [],
            'declared_targets': self.declared_targets.copy() if self.declared_targets else [],
            'declared_x': self.declared_x,
            'is_triggered': self.is_triggered,
            'trigger_event': self.trigger_event,
            'effect_fn': self.effect_fn if self.effect_fn else None,
            'resolution_count': self.resolution_count,
        }


@dataclass
class ChainLink:
    """One resolved attack in the combat chain.

    Talishar reference: Classes/ChainLinks.php, ChainLinksPieces()=10.
    """
    chainlink_id: int
    attacker_id: int
    attack_slug: str
    attack_power: int
    net_damage: int
    keywords: list[str]
    from_weapon: bool
    hit: bool = False

    def to_dict(self):
        return {
            'link number': self.chainlink_id,
            'attack power': self.attack_power
        }

@dataclass
class CombatState:
    attacker_id: int
    link_id: int
    attack_power: int
    attack_card: Card
    keywords: list[str]
    attack_target: Optional[Player] = None    
    base_attack_power: int = 0
    from_weapon: bool = False
    attack_source: Optional[Card] = None
    defending_cards: list[Card] = field(default_factory=list)
    total_defense: int = 0
    defending_equipment_defense: int = 0
    defender_used_hand_card: bool = False
    no_defense_reactions: bool = False
    defending_declared: bool = False
    defending_equipment_zones: list[str] = field(default_factory=list)

    @property
    def attack_slug(self) -> Optional[str]:
        return self.attack_card.slug if self.attack_card else None

    @property
    def defending_slugs(self) -> list[str]:
        return [c.slug for c in self.defending_cards]

    @property
    def defending_equipment_slots(self) -> list[str]:
        return self.defending_equipment_zones
    
    def resolve_attack_target(self, state: "GameState") -> Player:
        if self.attack_target is None:
            self.attack_target = state.players[3 - self.attacker_id]
        return self.attack_target
    
    def to_dict(self) -> dict:
        """Convert CombatState to a dictionary representation."""
        return {
            'attacker_id': self.attacker_id,
            'link_id': self.link_id,
            'attack_power': self.attack_power,
            'attack_card': self.attack_card.to_dict() if self.attack_card else None,
            'keywords': self.keywords.copy(),
            'attack_target': self.attack_target.to_dict() if self.attack_target else None,
            'base_attack_power': self.base_attack_power,
            'from_weapon': self.from_weapon,
            'attack_source': self.attack_source.to_dict() if self.attack_source else None,
            'defending_cards': [card.to_dict() for card in self.defending_cards],
            'total_defense': self.total_defense,
            'defending_equipment_defense': self.defending_equipment_defense,
            'defender_used_hand_card': self.defender_used_hand_card,
            'no_defense_reactions': self.no_defense_reactions,
            'defending_declared': self.defending_declared,
            'defending_equipment_zones': self.defending_equipment_zones.copy(),
            # Include properties
            'attack_slug': self.attack_slug,
            'defending_slugs': self.defending_slugs,
            'defending_equipment_slots': self.defending_equipment_slots
        }


@dataclass
class GameState:
    players: dict[int, Player]
    active_player: int
    player_agents: dict[int, Callable]
    step: Step
    turn_number: int
    combat: Optional[CombatState]
    done: bool
    winner: Optional[int]
    ended_on_turn_cap: bool = False
    max_turns: int = 200
    card_db: Optional[object] = None  # CardDB instance for effect/trigger access
    event_manager: EventManager = field(default_factory=EventManager)
    effect_manager: Optional[object] = None  # EffectManager from engine.effects
    priority_player: int = 1
    consecutive_passes: int = 0
    events_this_turn: set[str] = field(default_factory=set)
    chain_links: list[ChainLink] = field(default_factory=list)
    pitch_history: dict[int, dict[int, list[str]]] = field(default_factory=lambda: {1: {}, 2: {}})  # {player_id: {turn: [slug, ...]}}
    # Stack zone (CR 3.0.1): LIFO; Zone tracks which cards are on the stack;
    # stack_entries holds the parallel metadata (player_id, from_arsenal).
    stack: Zone = field(default_factory=lambda: Zone("stack"))
    stack_entries: list[StackEntry] = field(default_factory=list)
    # Combat chain zone: holds the active attack card during combat.
    combat_chain: Zone = field(default_factory=lambda: Zone("combat chain"))
    landmarks: list[tuple[int, str]] = field(default_factory=list)
    last_acted_player: Optional[int] = None
    last_known_cache: dict[int, dict] = field(default_factory=dict)

    def active(self) -> Player:
        return self.players[self.active_player]

    def inactive(self) -> Player:
        return self.players[3 - self.active_player]

    def copy(self) -> GameState:
        return copy.deepcopy(self)

    def remember_last_known(self, card: Optional[Card], overwrite: bool = True) -> Optional[dict]:
        """Capture and cache last-known information for a card-like object."""
        if card is None:
            return None
        if not overwrite and card.object_id in self.last_known_cache:
            return self.last_known_cache[card.object_id]
        snapshot = card.remember_last_known_state(force=overwrite)
        self.last_known_cache[card.object_id] = snapshot
        return snapshot

    def get_last_known(self, card_or_id, default: Optional[dict] = None) -> Optional[dict]:
        """Return last-known-information snapshot for a Card or object id."""
        if card_or_id is None:
            return default

        if isinstance(card_or_id, Card):
            if card_or_id.object_id in self.last_known_cache:
                return self.last_known_cache[card_or_id.object_id]
            return card_or_id.get_last_known_state() or default

        try:
            object_id = int(card_or_id)
        except (TypeError, ValueError):
            return default

        return self.last_known_cache.get(object_id, default)

    def last_known_value(self, card_or_id, key: str, default=None):
        """Convenience accessor for a single last-known-information field."""
        snapshot = self.get_last_known(card_or_id)
        if snapshot is None:
            return default
        return snapshot.get(key, default)

    def process_cease_to_exist(self, card: Optional[Card]) -> Optional[dict]:
        """Rules hook for objects that cease to exist; caches their final known state."""
        return self.remember_last_known(card, overwrite=True)

    def set_card_visibility(self, card: Optional[Card], is_public: bool) -> Optional[dict]:
        """Update card visibility, capturing LKI for public-to-private transitions."""
        if card is None:
            return None
        if card.is_public == is_public:
            return self.get_last_known(card)
        if card.is_public and not is_public:
            self.process_cease_to_exist(card)
        card.is_public = is_public
        return self.get_last_known(card)

    def get_zone(self, zone_name: str, player_id: Optional[int] = None) -> Optional[Zone]:
        if player_id is not None:
            p = self.players.get(player_id)
            if p:
                return p.zone_by_name(zone_name)
        return None
    
    def record_pitch(self, player_id: int, card_slugs: list[str]) -> None:
        """Record cards pitched this turn for a player (CR 4.4.3c)."""
        if player_id not in self.pitch_history:
            self.pitch_history[player_id] = {}
        self.pitch_history[player_id][self.turn_number] = list(card_slugs)

    def invalidate_pitch_history(self, player_id: int) -> None:
        """Clear pitch history when deck is shuffled (CR 8.5.20: order now unknown)."""
        self.pitch_history[player_id] = {}

    def record_pass(self, player_id: int) -> bool:
        """Record a pass. Returns True if both players have passed consecutively (latest stack entry resolves)."""
        if player_id != self.last_acted_player:
            self.consecutive_passes = 1
        else:
            self.consecutive_passes += 1
        self.last_acted_player = player_id
        return self.consecutive_passes >= 2
        
    def to_dict(self) -> dict:
        """Convert GameState to a dictionary representation. Include variables to observe"""
        return {
            # 'players': {pid: player.to_dict() for pid, player in self.players.items()},
            'active_player': self.active_player,
            # 'player_agents': {pid: str(agent) for pid, agent in self.player_agents.items()},  # Can't serialize callables, just string representation
            'step': self.step.value if hasattr(self.step, 'value') else str(self.step),
            'turn_number': self.turn_number,
            'max_turns': self.max_turns,
            'combat': self.combat.to_dict() if self.combat else None,
            # 'done': self.done,
            # 'winner': self.winner,
            # 'card_db': '[CardDB]' if self.card_db else None,  # Skip serializing actual CardDB
            'event_manager': '[EventManager]',  # Skip serializing EventManager
            'effect_manager': '[EffectManager]' if self.effect_manager else None,
            'priority_player': self.priority_player,
            # 'consecutive_passes': self.consecutive_passes,
            'chain_links': [link.to_dict() for link in self.chain_links],
            # 'stack': self.stack.to_dict(),
            'stack_entries': [entry.to_dict() for entry in self.stack_entries],
            'combat_chain': self.combat_chain.to_dict(),
            # 'landmarks': [(pid, landmark) for pid, landmark in self.landmarks],
            # 'last_acted_player': self.last_acted_player
        }
