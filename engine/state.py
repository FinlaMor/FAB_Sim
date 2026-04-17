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
from engine.context import is_effect_context
from engine.continuous_effects import ContinuousEffectManager
from engine.effects import EffectManager

# ---------------------------------------------------------------------------
# Zone entry rules (CR 3.0.11 / 3.0.12 / 3.0.12a)
# ---------------------------------------------------------------------------

# CR 1.3.2c — deck-card types
_DECK_CARD_TYPES = frozenset({
    "Action", "AttackReaction", "Attack Reaction", "Block",
    "DefenseReaction", "Defense Reaction", "Instant", "Mentor", "Resource",
})

# CR 1.3.2 — deck-card subtypes that allow entry to the permanent zone
_PERMANENT_SUBTYPES = frozenset({
    "Affliction", "Ally", "Ash", "Aura", "Construct",
    "Figment", "Invocation", "Item", "Landmark",
})

# Equipment slot subtypes per zone (CR 3.2.2a, 3.5.2a, 3.10.2a, 3.12.2a, 3.16.2a)
_EQUIPMENT_ZONE_SUBTYPES: dict[str, frozenset[str]] = {
    "arms":    frozenset({"Arms"}),
    "chest":   frozenset({"Chest"}),
    "head":    frozenset({"Head"}),
    "legs":    frozenset({"Legs"}),
    "weapon":  frozenset({"Weapon", "OffHand", "Off-Hand", "Quiver"}),
    "weapon1": frozenset({"Weapon", "OffHand", "Off-Hand", "Quiver"}),
    "weapon2": frozenset({"Weapon", "OffHand", "Off-Hand", "Quiver"}),
}


def _is_token(card: Card) -> bool:
    types = [t.lower() for t in (card.raw_types or card.types or [])]
    return "token" in types


def _is_deck_card(card: Card) -> bool:
    types = set(card.raw_types or card.types or [])
    return bool(types & _DECK_CARD_TYPES)


def _has_permanent_subtype(card: Card) -> bool:
    subtypes = set(card.raw_subtypes or card.subtypes or [])
    return bool(subtypes & _PERMANENT_SUBTYPES)


class ZoneEntryResult:
    """Outcome of a zone entry rule check."""
    ALLOW = "allow"
    CLEAR = "clear"            # redirect to graveyard (rule path, CR 3.0.12)
    CEASE_TO_EXIST = "cease"   # token/macro — just removed (CR 3.0.12a)
    FAIL = "fail"              # effect path — move simply doesn't happen (CR 3.0.11)


def _check_zone_entry(zone: "Zone", card: Card, source: str) -> str:
    """Return a ZoneEntryResult for card entering zone from the given source.

    source: "rule" (engine-initiated) or "effect" (card-effect-initiated).
    """
    name = zone.name

    # --- owner-only zones (hand, deck, pitch, graveyard, banished, arsenal) ---
    if name in ("hand", "deck", "pitch", "graveyard", "banished", "arsenal"):
        # Tokens cease to exist on entry to graveyard/banished (CR 3.0.12a)
        if name in ("graveyard", "banished") and _is_token(card):
            return ZoneEntryResult.CEASE_TO_EXIST
        # Non-deck-cards can't enter hand/deck/pitch/arsenal (CR 3.9.2, 3.7.2, 3.14.2, 3.3.2)
        if name in ("hand", "deck", "pitch", "arsenal") and not _is_deck_card(card):
            return ZoneEntryResult.FAIL if source == "effect" else ZoneEntryResult.CLEAR
        # Wrong owner
        if zone.owner_id is not None and card.owner != zone.owner_id:
            return ZoneEntryResult.FAIL if source == "effect" else ZoneEntryResult.CLEAR
        # Arsenal full (CR 3.3.2a — both rule and effect fail; rule "clears" = would redirect to grave)
        if name == "arsenal" and zone.player is not None:
            # check all arsenal zones for this player
            arsenal_zones = [z for z in _get_player_zones(zone.player) if z.name == "arsenal"]
            if all(len(z.cards) >= 1 for z in arsenal_zones):
                return ZoneEntryResult.FAIL if source == "effect" else ZoneEntryResult.CLEAR

    # --- equipment slot zones (CR 3.2.2a, 3.5.2a, 3.10.2a, 3.12.2a, 3.16.2a) ---
    if name in _EQUIPMENT_ZONE_SUBTYPES:
        allowed_subtypes = _EQUIPMENT_ZONE_SUBTYPES[name]
        card_subtypes = set(card.raw_subtypes or card.subtypes or [])
        card_types = set(card.raw_types or card.types or [])
        # Must have matching subtype OR type Weapon (for weapon zones)
        has_match = bool(card_subtypes & allowed_subtypes) or (
            name in ("weapon", "weapon1", "weapon2") and "Weapon" in card_types
        )
        if not has_match:
            return ZoneEntryResult.FAIL if source == "effect" else ZoneEntryResult.CLEAR

    # --- hero zone (CR 3.11.2) ---
    if name == "hero":
        card_types = set(card.raw_types or card.types or [])
        if "Hero" not in card_types:
            return ZoneEntryResult.FAIL if source == "effect" else ZoneEntryResult.CLEAR

    # --- permanent zone (CR 3.13.2, 1.3.2c/d) ---
    if name == "permanents":
        # deck-cards only allowed if they have a permanent subtype
        if _is_deck_card(card) and not _has_permanent_subtype(card):
            return ZoneEntryResult.FAIL if source == "effect" else ZoneEntryResult.CLEAR

    return ZoneEntryResult.ALLOW


def _get_player_zones(player) -> list["Zone"]:
    """Return all Zone objects owned by player (for arsenal-full check)."""
    return [v for v in vars(player).values() if isinstance(v, Zone)]


def _clear_sub_cards(card: "Card") -> None:
    """CR 3.0.14e: when a top-card ceases to exist, its sub-cards are cleared.

    Each sub-card has its is_sub_card / top_card back-ref cleared and its zone
    set to 'ceased_to_exist' so lookups don't find stale references.
    """
    for sub in list(getattr(card, "cards_underneath", [])):
        sub.is_sub_card = False
        sub.top_card = None
        sub.zone = "ceased_to_exist"
    card.cards_underneath = []


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
    """A named collection of Card objects. The fundamental building block of OO game state.
    Total of 15 zones per 3.15:

        Shared zones:
            stack,
            combat chain

        Public zones (one per player):
            weapon (broken down further by engine into weapon1 and weapon2), 
            arms,
            banished,
            chest,
            graveyard,
            head,
            hero,
            legs,
            permanent,
            pitch  
        
        Private zones (one per player):
            arsenal,
            deck,
            hand
        
        Zones solely created for/by the engine:
            inventory (not TECHNICALLY a zone)
            staging (an internal implementation zone - cards pass through it briefly during initialization before entering an actual game zone)
    """

    def __init__(self, name: str, owner_id: Optional[int] = None, player=None):
        self.name = name
        self.owner_id = owner_id
        self.player = player  # back-reference to Player; set after Player.__init__
        self.players: Optional[dict] = None  # back-reference to all players; set by GameState.__post_init__
        self.cards: list[Card] = []

    @property
    def is_public(self) -> bool:
        return self.name not in ('hand', 'deck', 'arsenal', 'inventory')

    def add(self, card: Card, is_public: Optional[bool] = None) -> str:
        """Move card into this zone, updating card.prev_zone / card.zone / card.is_public.

        Returns a ZoneEntryResult indicating what happened:
          ALLOW           — card entered normally
          FAIL            — effect-source move rejected; card not moved
          CLEAR           — rule-source violation; caller should redirect to graveyard
          CEASE_TO_EXIST  — token entered a zone it can't occupy; card removed from game
        """
        source = "effect" if is_effect_context() else "rule"
        result = _check_zone_entry(self, card, source)

        if result == ZoneEntryResult.FAIL:
            return result
        if result == ZoneEntryResult.CEASE_TO_EXIST:
            # CR 3.0.12a: token simply leaves its current zone and ceases to exist
            if self.player is not None:
                for z in _get_player_zones(self.player):
                    if card in z.cards:
                        z.cards.remove(card)
                        break
            # CR 3.0.14e: clear sub-cards when top-card ceases to exist
            _clear_sub_cards(card)
            card.zone = "ceased_to_exist"
            return result
        if result == ZoneEntryResult.CLEAR:
            # CR 3.0.12: redirect to the card owner's graveyard
            owner_player = None
            if self.players is not None and card.owner is not None:
                owner_player = self.players.get(card.owner)
            elif self.player is not None:
                owner_player = self.player
            if owner_player is not None:
                inner = owner_player.graveyard.add(card, is_public)
                # Propagate CEASE_TO_EXIST (e.g. token→hand→graveyard chain)
                return inner if inner == ZoneEntryResult.CEASE_TO_EXIST else ZoneEntryResult.CLEAR
            # No player ref — fall through and allow (best-effort)

        next_is_public = self.is_public if is_public is None else is_public
        card.remember_last_known_state()
        was_in_arena = card.is_in_arena
        was_on_stack = card.zone == 'stack'
        card.prev_zone = card.zone
        card.zone = self.name
        if next_is_public == False and card.is_public == True: #3.0.9 If an object enters a zone that is not in the arena and is not the stack zone, or a public object becomes private while it is not in the arena, it resets - its previous existence ceases to exist and it becomes a new object with no relation to its previous existence.
            card.reset_to_base_state()
        if (was_in_arena or was_on_stack) and not card.is_in_arena:
            card.reset_to_base_state()
        card.is_public = next_is_public
        if card not in self.cards:
            self.cards.append(card)
        return ZoneEntryResult.ALLOW

    def remove(self, card: Card) -> bool:
        if card in self.cards:
            self.cards.remove(card)
            # CR 3.0.14e: clearing sub-cards when top-card leaves its zone
            _clear_sub_cards(card)
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

    def add_under(self, sub_card: "Card") -> bool:
        """Place sub_card underneath top_card in this zone (CR 3.0.14).

        top_card must already be in this zone. sub_card is appended to
        top_card.cards_underneath — it does not appear in zone.cards directly.

        CR 3.0.14b: becoming a sub-card causes the card to cease to exist as its
        previous self and become a new object (reset). is_sub_card is set True.
        CR 3.0.14d: sub-card inherits top-card's visibility.
        Returns True on success, False if top_card is not in this zone.
        """
        top_card = self.top if len(self.cards) > 0 else None
        if top_card not in self.cards :
            return False
        # CR 3.0.14b: card becomes new object on entering as sub-card
        sub_card.reset_to_base_state()
        sub_card.prev_zone = sub_card.zone
        sub_card.zone = self.name
        sub_card.is_sub_card = True
        if top_card:
            sub_card.top_card = top_card
            # CR 3.0.14d: inherit visibility from top-card
            sub_card.is_public = top_card.is_public
            top_card.cards_underneath.append(sub_card)
        else:
            sub_card.is_public = self.is_public
        return True

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
    
    @property
    def is_public(self) -> bool:
        return self.parent.is_public

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

    def add_under(self, sub_card: "Card") -> bool:
        return self.parent.add_under(sub_card)

    def _matches(self, card: Card) -> bool:
        return getattr(card, 'permanent_subtype', None) == self.subtype

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


# ---------------------------------------------------------------------------
# Game History (CR-agnostic; human-readable + IQL-embeddable)
# ---------------------------------------------------------------------------

@dataclass
class HistoryEntry:
    """One recorded event in the game log."""
    seq: int                          # global monotonic sequence number
    turn: int                         # state.turn_number when emitted
    individual_turn: int              # state.individual_turns (per-player counter)
    active_player_id: int             # state.active_player when emitted
    event_type: str                   # Event.type string
    data: dict = field(default_factory=dict)
    text: str = ""                    # pre-rendered human-readable line

    def __repr__(self) -> str:
        return f"[T{self.turn}|P{self.active_player_id}] {self.text or self.event_type}"


# Human-readable renderers per event type
_EVENT_RENDERERS: dict[str, "Callable[[HistoryEntry], str]"] = {}

def _render(entry: "HistoryEntry") -> str:
    renderer = _EVENT_RENDERERS.get(entry.event_type)
    if renderer:
        try:
            return renderer(entry)
        except Exception:
            pass
    # fallback: event_type + data keys
    parts = [f"{k}={v}" for k, v in entry.data.items() if v is not None]
    return f"{entry.event_type}({', '.join(parts)})" if parts else entry.event_type


def _reg(event_type: str):
    """Decorator to register a human-readable renderer for an event type."""
    def decorator(fn):
        _EVENT_RENDERERS[event_type] = fn
        return fn
    return decorator


@_reg("discard")
def _r_discard(e):
    card = e.data.get("target") or e.data.get("discard_target", "?")
    return f"P{e.active_player_id} discarded {card}"

@_reg("draw")
def _r_draw(e):
    n = e.data.get("total_drawn", 1)
    pid = e.data.get("draw_player", e.active_player_id)
    return f"P{pid} drew {n} card{'s' if n != 1 else ''}"

@_reg("gain")
def _r_gain(e):
    pid = e.data.get("target_player_id", e.active_player_id)
    return f"P{pid} gained {e.data.get('amount')} {e.data.get('asset_type','?')}"

@_reg("lose")
def _r_lose(e):
    pid = e.data.get("target_player_id", e.active_player_id)
    return f"P{pid} lost {e.data.get('amount')} {e.data.get('asset_type','?')}"

@_reg("deal_damage")
def _r_damage(e):
    tgt = e.data.get("target") or e.data.get("damage_target", "?")
    return f"P{e.active_player_id} dealt {e.data.get('amount')} {e.data.get('damage_type','generic')} dmg to {tgt}"

@_reg("destroy")
def _r_destroy(e):
    return f"{e.data.get('target','?')} destroyed"

@_reg("banish")
def _r_banish(e):
    return f"{e.data.get('target','?')} banished"

@_reg("put_object")
def _r_put(e):
    return f"{e.data.get('target','?')} → {e.data.get('destination_zone','?')} (P{e.data.get('destination_player_id','?')})"

@_reg("play_card")
def _r_play(e):
    pid = e.data.get("player_id", e.active_player_id)
    return f"P{pid} played {e.data.get('card','?')}"

@_reg("attack")
def _r_attack(e):
    pid = e.data.get("player_id", e.active_player_id)
    return f"P{pid} attacks with {e.data.get('card','?')} (power={e.data.get('power','?')})"

@_reg("pitch")
def _r_pitch(e):
    return f"P{e.active_player_id} pitched {e.data.get('target','?')} for {e.data.get('pitch_value','?')}r"

@_reg("put_counter")
def _r_put_counter(e):
    return f"+{e.data.get('amount',1)} {e.data.get('counter_type','?')} counter on {e.data.get('target','?')}"

@_reg("remove_counter")
def _r_rm_counter(e):
    return f"-{e.data.get('actual_removed',1)} {e.data.get('counter_type','?')} counter from {e.data.get('target','?')}"

@_reg("tap")
def _r_tap(e):    return f"{e.data.get('target','?')} tapped"

@_reg("untap")
def _r_untap(e):  return f"{e.data.get('target','?')} untapped"

@_reg("create_token")
def _r_token(e):
    pid = e.data.get("target_player_id", e.active_player_id)
    return f"P{pid} created {e.data.get('token_type','?')} token"

@_reg("gain_control")
def _r_gain_ctrl(e):
    return f"P{e.data.get('new_controller_id','?')} gained control of {e.data.get('target','?')}"

@_reg("shuffle")
def _r_shuffle(e):
    return f"P{e.data.get('target_player_id','?')} shuffled deck"

@_reg("reveal")
def _r_reveal(e):
    targets = e.data.get("targets", [])
    return f"P{e.active_player_id} revealed {', '.join(targets)}"

@_reg("search")
def _r_search(e):
    chosen = e.data.get("chosen")
    if chosen:
        return f"P{e.data.get('search_player_id','?')} searched → {chosen}"
    return f"P{e.data.get('search_player_id','?')} searched (failed)"

@_reg("clash")
def _r_clash(e):
    w = e.data.get("winner_id")
    return f"Clash: P{w} wins" if w else "Clash: tie"

@_reg("intimidate")
def _r_intimidate(e):
    tgt = e.data.get("target_player_id", "?")
    card = e.data.get("banished_card")
    return f"P{e.active_player_id} intimidated P{tgt}" + (f" → banished {card}" if card else "")

@_reg("freeze")
def _r_freeze(e):
    return f"{e.data.get('target','?')} frozen until {e.data.get('until_condition','?')}"

@_reg("mark")
def _r_mark(e):
    return f"P{e.data.get('target_player_id','?')} marked"

@_reg("charge")
def _r_charge(e):
    return f"P{e.data.get('player_id','?')} charged {e.data.get('target','?')} to soul"

@_reg("become_copy")
def _r_copy(e):
    return f"{e.data.get('subject','?')} became a copy of {e.data.get('reference','?')}"


class GameHistory:
    """Records every event emitted during a game.

    Dual-mode:
    - In-memory: entries stored in self.entries (default)
    - External: pass a backend object with .append(entry_dict) to stream
      entries elsewhere (e.g. SQLite, file, network)

    Human-readable output via to_text().
    IQL-embeddable output via to_features().
    """

    def __init__(self, backend=None):
        self.entries: list[HistoryEntry] = []
        self._seq: int = 0
        self._backend = backend   # optional external sink

    def record(self, event: "Event", state: "GameState") -> None:
        """Called by EventManager.emit on every event."""
        self._seq += 1
        entry = HistoryEntry(
            seq=self._seq,
            turn=getattr(state, "turn_number", 0),
            individual_turn=getattr(state, "individual_turns", 0),
            active_player_id=getattr(state, "active_player", 0),
            event_type=event.type,
            data=dict(event.data) if getattr(event, 'data', None) is not None else {},
        )
        entry.text = _render(entry)
        self.entries.append(entry)
        if self._backend is not None:
            self._backend.append(entry.__dict__)

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def this_turn(self, turn: int) -> list[HistoryEntry]:
        return [e for e in self.entries if e.turn == turn]

    def by_player(self, player_id: int) -> list[HistoryEntry]:
        return [e for e in self.entries if e.active_player_id == player_id]

    def by_type(self, event_type: str) -> list[HistoryEntry]:
        return [e for e in self.entries if e.event_type == event_type]

    def cards_played(self, player_id: int, turn: int | None = None) -> list[str]:
        """Return slugs of cards played by player_id (optionally filtered by turn)."""
        entries = [e for e in self.entries
                   if e.event_type == "play_card"
                   and e.data.get("player_id") == player_id]
        if turn is not None:
            entries = [e for e in entries if e.turn == turn]
        return [e.data.get("card", "") for e in entries]

    # ------------------------------------------------------------------
    # Human-readable output
    # ------------------------------------------------------------------

    def to_text(self, turn: int | None = None, player_id: int | None = None) -> str:
        """Return a human-readable game log.

        Optionally filtered to a specific turn and/or player.
        Each line: [seq] [T{turn}|P{player}] {text}
        """
        entries = self.entries
        if turn is not None:
            entries = [e for e in entries if e.turn == turn]
        if player_id is not None:
            entries = [e for e in entries if e.active_player_id == player_id]
        lines = [f"[{e.seq:>4}] [T{e.turn}|P{e.active_player_id}] {e.text}" for e in entries]
        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"GameHistory({len(self.entries)} events, {self._seq} seq)"

    # ------------------------------------------------------------------
    # IQL embedding interface
    # ------------------------------------------------------------------

    def to_features(self, current_turn: int, lookback: int = 1,
                    max_events: int = 50) -> list[dict]:
        """Return recent history as a list of feature dicts for IQL embedding.

        Returns up to max_events entries from the last `lookback` turns,
        most recent first. Each dict contains:
          seq, turn, individual_turn, active_player_id, event_type, text, data
        """
        min_turn = max(0, current_turn - lookback)
        recent = [e for e in self.entries if e.turn >= min_turn]
        recent = recent[-max_events:]   # cap
        return [
            {
                "seq": e.seq,
                "turn": e.turn,
                "individual_turn": e.individual_turn,
                "active_player_id": e.active_player_id,
                "event_type": e.event_type,
                "text": e.text,
                "data": e.data,
            }
            for e in reversed(recent)   # most recent first
        ]


class EventManager:
    def __init__(self):
        self.listeners: dict = {}

    def register(self, event_name: str, listener) -> None:
        self.listeners.setdefault(event_name, []).append(listener)

    def unregister(self, event_name: str, listener) -> None:
        if event_name in self.listeners:
            try:
                self.listeners[event_name].remove(listener)
                # Clean up empty lists
                if not self.listeners[event_name]:
                    del self.listeners[event_name]
            except ValueError:
                # Listener wasn't in the list
                pass

    def emit(self, event, game_state: GameState) -> None:
        """Emit an event. Accepts an Event object or a string event type."""
        if isinstance(event, str):
            event = Event(type=event)

        # Track coarse event history for state embedding features.
        if hasattr(game_state, 'events_this_turn') and isinstance(game_state.events_this_turn, set):
            game_state.events_this_turn.add(event.type)

        # Record into structured game history
        if hasattr(game_state, 'history') and isinstance(game_state.history, GameHistory):
            game_state.history.record(event, game_state)

        for listener in list(self.listeners.get(event.type, [])):
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
        self.life: int = hero_card.raw_life or 40
        self.intellect: int = hero_card.raw_intellect or 4
        self.resources: int = 0
        self.action_points: int = 0
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
        self.hero_zone = Zone("hero_zone", player_id)
        self.soul = Zone("soul", player_id) # Not a real zone but useful for the engine.
        self.pitch = Zone("pitch", player_id)  # cards pitched this turn (public; go to deck bottom at end of turn)
        self.pitch_history: list[Card] = []
        # Hero card setup
        hero_card.owner = player_id
        hero_card.controller = player_id
        self.hero_zone.add(hero_card)

        # Wire player back-reference into all owned zones
        for zone in _get_player_zones(self):
            zone.player = self

        # Turn tracking
        self.arsenal_limit: int = 1
        self.current_turn_counters: list[str] = []
        self.next_turn_effects: list[str] = []
        self.class_counters: dict[str, int] = {}
        self.allies_exhausted: list[bool] = []
        self.current_turn_effects: list[str] = []
        self.weapon_exhausted: bool = False

        # CR 5.1.6a: cost modifiers are now stored in GameState.continuous_effect_manager
        # as ContinuousEffect objects with prop='cost'. See ContinuousEffectManager.add_cost_modifier().

        # CR 1.14.2a: Chi resource pool.  Chi is drained before
        # floating resources when paying costs (CR 1.14.2d).
        self.chi: int = 0

        # Conditions (9.3)
        self.marked: bool = False  # 9.3: marked condition — cleared when hit by opponent

        # Equipment defense tracking (for Battleworn/Temper/Blade Break)
        self.equipment_defended_this_turn: list[str] = []

        # Cards played from hand/arsenal this turn (Card objects)
        self.cards_played_this_turn: list = []
    
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
    def playable_cards(self) -> list[Card]:
        zones = self.all_zones()
        cards = []
        for z in zones:
            cards.extend(c for c in z.cards if c.playable)
        return cards
    
    @property
    def activatable_cards(self) -> list[Card]:
        zones = self.all_zones()
        cards = []
        for z in zones:
            cards.extend(c for c in z.cards if c.has_activated_ability)
        return cards
    
    @property
    def all_cards(self) -> list[Card]:
        zones = self.all_zones()
        cards = []
        for z in zones:
            cards.extend(z.cards)
        return cards

    @property
    def defendable_cards(self) -> list[Card]:
        zones = self.all_zones()
        cards = []
        for z in zones:
            cards.extend(c for c in z.cards if c.has_defense)
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
    
    def find_all_cards(self, slug:str) -> Optional[list[Card]]:
        cards = []
        for c in self.all_cards:
            if c.slug == slug:
                cards.append(c)
        return cards

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
            "life": self.life,
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
            'equipment_defended_this_turn':getattr(self,'equipment_defended_this_turn',[]).copy(),

            # CR 5.1.6a cost modifiers live in GameState.continuous_effect_manager

            # CR 1.14.2a chi pool
            'chi': getattr(self, 'chi', 0),
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
        # Triggered layers are never the attack itself — they are triggered abilities
        # sourced from a card. Even if the source card is an attack card, the triggered
        # layer is not an attack layer and must not be treated as one by priority_loop.
        if self.layer_type == 'triggered':
            return False
        # CR 1.6.2b: Weapon attacks (activated-layer) must enter combat
        if self.layer_type == 'activated' and self.card and self.card.is_weapon:
            return True
        # CR 11.0: Ally attacks (activated-layer) must enter combat.
        # Ally is a subtype (CR 2.10), not a card type, so check subtypes.
        if self.layer_type == 'activated' and self.card and 'Ally' in (self.card.subtypes or []):
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
    attack_target: Optional["Card"] = None  # Set when attack targets a specific card (e.g. Spectra aura, ally) instead of hero
    # Wager system (CR 8.5.46): list of (controller_id, prize_token_slug_or_None)
    wagers: list[tuple[int, str | None]] = field(default_factory=list)
    # Stage-6 keyword effects added directly during this combat chain link
    # (e.g. Go Again from triggered abilities). Unioned into combat.keywords by
    # _recalculate_attack_power so all "X in combat.keywords" checks still work.
    keyword_effects: set = field(default_factory=set)

    def grant_keyword(self, keyword: str) -> None:
        """Add a keyword effect and immediately update combat.keywords for read consistency."""
        self.keyword_effects.add(keyword)
        if keyword not in self.keywords:
            self.keywords.append(keyword)

    def revoke_keyword(self, keyword: str) -> None:
        """Remove a keyword effect and immediately update combat.keywords."""
        self.keyword_effects.discard(keyword)
        if keyword in self.keywords:
            self.keywords.remove(keyword)

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
            'defending_equipment_slots': self.defending_equipment_slots,
            'keyword_effects': list(self.keyword_effects),
        }


@dataclass
class GameState:
    players: dict[int, Player]
    active_player: int
    player_agents: dict[int, Callable]
    step: Step
    turn_number: int       # Round-based: 0 = opening player's first turn; both players' turns within the same round share a number
    combat: Optional[CombatState]
    done: bool
    winner: Optional[int]
    individual_turns: int = 0  # Raw per-player-turn counter: 1 on first player's first turn, increments every _start_phase
    ended_on_turn_cap: bool = False
    max_turns: int = 200
    card_db: Optional[object] = None  # CardDB instance for effect/trigger access
    event_manager: EventManager = field(default_factory=EventManager)
    continuous_effect_manager: ContinuousEffectManager = field(default_factory=ContinuousEffectManager)
    effect_manager: EffectManager = field(default_factory=EffectManager) # EffectManager from engine.effects
    priority_player: int = 1
    consecutive_passes: int = 0
    history: GameHistory = field(default_factory=GameHistory)
    events_this_turn: set[str] = field(default_factory=set)
    chain_links: list[ChainLink] = field(default_factory=list)
    pitch_history: dict[int, dict[int, list[Card]]] = field(default_factory=lambda: {1: {}, 2: {}})  # {player_id: {turn: [slug, ...]}}
    # Stack zone (CR 3.0.1): LIFO; Zone tracks which cards are on the stack;
    # stack_entries holds the parallel metadata (player_id, from_arsenal).
    stack: Zone = field(default_factory=lambda: Zone("stack"))
    stack_entries: list[StackEntry] = field(default_factory=list)
    # Combat chain zone: holds the active attack card during combat.
    combat_chain: Zone = field(default_factory=lambda: Zone("combat chain"))
    landmarks: list[tuple[int, str]] = field(default_factory=list)
    last_acted_player: Optional[int] = None
    last_known_cache: dict[int, dict] = field(default_factory=dict)

    def __post_init__(self):
        # Wire players dict into every zone so CLEAR redirects can reach any player's graveyard.
        for player in self.players.values():
            for zone in _get_player_zones(player):
                zone.players = self.players

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
            'individual_turns': self.individual_turns,
            'max_turns': self.max_turns,
            'combat': self.combat.to_dict() if self.combat else None,
            # 'done': self.done,
            # 'winner': self.winner,
            # 'card_db': '[CardDB]' if self.card_db else None,  # Skip serializing actual CardDB
            'event_manager': '[EventManager]',  # Skip serializing EventManager
            'continuous_effects_count': len(self.continuous_effect_manager._effects),
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
