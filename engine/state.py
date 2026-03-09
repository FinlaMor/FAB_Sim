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
    ACTION = "action"
    COMBAT_LAYER = 'combat_layer'
    COMBAT_ATTACK = 'combat_attack'
    COMBAT_DEFEND = "combat_defend"
    COMBAT_REACTION = "combat_reaction"
    COMBAT_DAMAGE = "combat_damage"
    COMBAT_RESOLUTION = "combat_resolution"
    COMBAT_CLOSE = "combat_close"
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

    def add(self, card: Card) -> None:
        """Move card into this zone, updating card.prev_zone / card.zone / card.is_public."""
        card.prev_zone = card.zone
        card.zone = self.name
        card.is_public = self.is_public
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

    def add_bottom(self, card: Card) -> None:
        """Add card to the bottom of this zone (e.g. bottom of deck)."""
        card.prev_zone = card.zone
        card.zone = self.name
        card.is_public = self.is_public
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

class EventManager:
    def __init__(self):
        self.listeners: dict = {}

    def register(self, event_name: str, listener) -> None:
        self.listeners.setdefault(event_name, []).append(listener)

    def emit(self, event, game_state: GameState) -> None:
        """Emit an event. Accepts an Event object or a string event type."""
        if isinstance(event, str):
            event = Event(type=event)
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
        stack_entry = StackEntry(
            player_id=self.card.owner,
            card=self.card,
            from_arsenal=False  # or True if applicable
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
        self.weapon = Zone("weapon", player_id)
        self.items = Zone("items", player_id) # \\
        self.auras = Zone("auras", player_id)#  || Actual rules text is 'permanent' zone for these four. split out for convenience.
        self.allies = Zone("allies", player_id)#||
        self.tokens = Zone("tokens", player_id)#//
        self.soul = Zone("soul", player_id)
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
    def arena_cards(self) -> list[Card]:
        arena_zones = [self.head, self.chest, self.arms, self.legs, self.weapon, self.items, self.auras, self.allies, self.soul, self.tokens, self.hero_zone]
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
                self.head, self.chest, self.arms, self.legs, self.weapon,
                self.items, self.auras, self.allies, self.soul, self.tokens,
                self.inventory, self.hero_zone, self.pitch]

    def zone_by_name(self, name: str) -> Optional[Zone]:
        return {
            "hand": self.hand, "deck": self.deck, "graveyard": self.graveyard,
            "arsenal": self.arsenal, "banished": self.banished, "head": self.head,
            "chest": self.chest, "arms": self.arms, "legs": self.legs,
            "weapon": self.weapon, "items": self.items, "auras": self.auras,
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
            "weapon":	self.weapon.to_dict(),
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
    """One card waiting to resolve on the stack (CR 3.0.1)."""
    player_id: int
    card: Card
    from_arsenal: bool = False
    is_triggered: bool = False          # True if this is a triggered ability layer
    effect_fn: Optional[Callable] = None  # effect to run on resolution (for triggered layers)

    @property
    def slug(self) -> str:
        return self.card.slug

    @property
    def is_attack(self) -> bool:
        return self.card.is_attack if self.card else False
    
    def to_dict(self):
        return {
            'player': self.player_id,
            'card': self.card.to_dict(),
            'from_arsenal': self.from_arsenal,
            'is_triggered': self.is_triggered,
            'effect_fn': self.effect_fn if self.effect_fn else None
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
    
    def attack_target(self, state: GameState) -> Player:
        if self.attack_target is None:
            self.attack_target = state.players[3 - self.attacker_id]
    
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
    card_db: Optional[object] = None  # CardDB instance for effect/trigger access
    event_manager: EventManager = field(default_factory=EventManager)
    effect_manager: Optional[object] = None  # EffectManager from engine.effects
    priority_player: int = 1
    consecutive_passes: int = 0
    chain_links: list[ChainLink] = field(default_factory=list)
    # Stack zone (CR 3.0.1): LIFO; Zone tracks which cards are on the stack;
    # stack_entries holds the parallel metadata (player_id, from_arsenal).
    stack: Zone = field(default_factory=lambda: Zone("stack"))
    stack_entries: list[StackEntry] = field(default_factory=list)
    # Combat chain zone: holds the active attack card during combat.
    combat_chain: Zone = field(default_factory=lambda: Zone("combat chain"))
    landmarks: list[tuple[int, str]] = field(default_factory=list)
    last_acted_player: Optional[int] = None

    def active(self) -> Player:
        return self.players[self.active_player]

    def inactive(self) -> Player:
        return self.players[3 - self.active_player]

    def copy(self) -> GameState:
        return copy.deepcopy(self)

    def get_zone(self, zone_name: str, player_id: Optional[int] = None) -> Optional[Zone]:
        if player_id is not None:
            p = self.players.get(player_id)
            if p:
                return p.zone_by_name(zone_name)
        return None
    
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
