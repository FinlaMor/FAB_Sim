"""Card data model and database wrapper for FAB card data (OO rewrite)."""

from __future__ import annotations

import json
import msgpack
import re
from copy import copy
from dataclasses import dataclass, field
from itertools import count
from typing import Optional
import os, sys

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from config import SLUG_INDEX_PATH


_CARD_OBJECT_ID_COUNTER = count(1)


def _int_or_none(val) -> Optional[int]:
    """Convert a value to int or None. Returns None for empty/missing values."""
    if val is None or val == "" or val == "*":
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _derive_category(raw: dict) -> str:
    """Derive card category from raw card data."""
    types = raw.get("types") or []
    if "Hero" in types:
        return "hero"
    subtypes = raw.get("subtypes") or []
    if "Token" in types or "Token" in subtypes:
        return "token"
    return "deck"


@dataclass
class Card:
    # Required fields (no defaults)
    slug: str

# "Raw" fields are derived directly from the database values for the card.
# Immutable once loaded
    raw_name: Optional[str] = None
    raw_pitch: Optional[int] = None
    raw_cost: Optional[int] = None
    raw_power: Optional[int] = None
    raw_defense: Optional[int] = None
    raw_life: Optional[int] = None
    raw_intellect: Optional[int] = None
    raw_arcane: Optional[int] = None
    raw_color: Optional[str] = None
    raw_types: Optional[list[str]] = None
    raw_text_box: str = ""
    raw_subtypes: Optional[list[str]] = None
    raw_card_keywords: Optional[list[str]] = None
    raw_functional_text: Optional[str] = None
    raw_type_text: Optional[str] = None
    raw_classes: Optional[list[str]] = None
    raw_legal_heroes: Optional[list[str]] = None
    raw_legal_formats: Optional[list[str]] = None
    raw_played_horizontally: Optional[bool] = None

# 'Base' characteristics can be changed by the effects of card if they specify 'base'
# Only fields without a 'base' value are legal_heroes, legal_formats, and played_horizontally
    base_name: Optional[str] = None
    base_pitch: Optional[int] = None
    base_cost: Optional[int] = None
    base_x_cost: Optional[int] = None
    base_power: Optional[int] = None
    base_defense: Optional[int] = None
    base_life: Optional[int] = None
    base_intellect: Optional[int] = None
    base_arcane: Optional[int] = None
    base_color: Optional[str] = None
    base_types: list[str] = field(default_factory=list)
    base_text_box: str = ""
    base_subtypes: Optional[list[str]] = None
    base_keywords: Optional[list[str]] = None
    base_functional_text: Optional[str] = None
    base_type_text: Optional[str] = None
    base_classes: Optional[list[str]] = None

# These characteristics are the ones most likely to be modified by effects or events.
    name: Optional[str] = None
    pitch: Optional[int] = None
    cost: Optional[int] = None
    x_cost: Optional[int] = None
    power: Optional[int] = None
    defense: Optional[int] = None
    life: Optional[int] = None
    intellect: Optional[int] = None
    arcane: Optional[int] = None
    color: Optional[str] = None
    types: list[str] = field(default_factory=list)
    text_box: str = ""
    subtypes: list[str] = field(default_factory=list)
    keywords: Optional[list[str]] = None
    functional_text: Optional[str] = None
    type_text: Optional[str] = None
    classes: Optional[list[str]] = None

    
    # Extended fields from index.ts (all optional, populated by CardDB.get)
    talents: list[str] = field(default_factory=list)
    shorthands: list[str] = field(default_factory=list)
    meta: list[str] = field(default_factory=list)
    metatypes: list[str] = field(default_factory=list)
    traits: list[str] = field(default_factory=list)
    fusions: list[str] = field(default_factory=list)
    bonds: list[str] = field(default_factory=list)
    flows: list[str] = field(default_factory=list)
    specializations: list[str] = field(default_factory=list)
    banned_formats: list[str] = field(default_factory=list)
    restricted_formats: list[str] = field(default_factory=list)
    special_cost: Optional[str] = None
    special_power: Optional[str] = None
    special_defense: Optional[str] = None
    special_life: Optional[str] = None
    special_arcane: Optional[str] = None
    hero_enum: Optional[str] = None
    young: bool = False
    is_card_back: bool = False
    opposite_side_card_identifiers: list[str] = field(default_factory=list)
    set_identifiers: list[str] = field(default_factory=list)
    sets: list[str] = field(default_factory=list)
    rarity: Optional[str] = None
    default_image: Optional[str] = None

    # Characteristics that are calculated or parsed from the 'raw' fields
    category: Optional[str] = None
    raw_playable: bool = False # Immutable. True if card isinherently playable from hand/arsenal without continuous effects.
    raw_activatable: bool = False # Immutable. True if card inherently has activated abilities without continuous effects.
    activation_cost: Optional[int] = None  
    abilities_and_effects: list[str] = field(default_factory=list)  # From slug_index
    effects: list[tuple] = field(default_factory=list)
    counters: dict[str, int] = field(default_factory=dict)  # Card-specific counters
    object_id: int = field(default_factory=lambda: next(_CARD_OBJECT_ID_COUNTER))
    last_known_state: Optional[dict] = field(default=None, repr=False)
    life_cost: Optional[int] = None  # For cards with life payment costs (e.g. "Pay 1 life")
    chi_cost: Optional[int] = None
    activation_conditions: Optional[bool] = None
    play_conditions: Optional[bool] = None
    alternate_cost: Optional[bool] = None
    mandatory_additional_costs: Optional[bool] = None
    optional_additional_costs: Optional[bool] = None

    # Zone tracking
    zone: str = "inventory"
    prev_zone: str = ""
    owner: int = 0
    controller: Optional[int] = None
    is_public: bool = False
    known_by: set = field(default_factory=set)  # player IDs who can currently see this card (CR 8.5.11)

    # State
    tapped: bool = False
    base_activations: Optional[int] = None
    activations: Optional[int] = None
    playable: bool = False  # Runtime flag for whether the card is currently playable (subject to continuous effects)
    activatable: bool = False  # Runtime flag for whether the card's activated abilities are currently usable
    exhausted: bool = False
    face_down: bool = False  # CR 8.5.24: face-down = private, face-up = public
    cards_underneath: list = field(default_factory=list)  # Cards placed "under" this card (CR 3.0.14)
    permanent_subtype: Optional[str] = None  # Set by SubZoneView when card enters items/auras/allies/tokens/soul
    is_sub_card: bool = False          # CR 3.0.14: True when this card is under a top-card
    top_card: Optional["Card"] = field(default=None, repr=False)  # Back-ref to the top-card (CR 3.0.14c)

    # Ability structure flags
    # Activated abilities (CR 5.2)
    has_activated_ability: bool = False
    has_once_per_turn_limit: bool = False
    has_action_activation: bool = False
    has_instant_activation: bool = False
    has_attack_reaction_activation: bool = False
    has_defense_reaction_activation: bool = False
    has_non_resource_activation_cost: bool = False
    has_conditional_activation: bool = False
    # Triggered abilities (CR 5.4.6)
    has_triggered_ability: bool = False
    has_on_hit_trigger: bool = False
    has_etb_trigger: bool = False
    has_leaves_arena_trigger: bool = False
    has_start_of_turn_trigger: bool = False
    has_end_of_turn_trigger: bool = False
    # Static abilities (CR 5.4, 6.2.3)
    has_static_ability: bool = False
    has_while_condition: bool = False
    has_continuous_buff: bool = False
    has_replacement_effect: bool = False
    has_prevention_effect: bool = False
    # Targeting requirements (CR 1.4)
    requires_target: bool = False
    can_target_hero: bool = False
    can_target_attack: bool = False
    can_target_permanent: bool = False
    # Multi-ability decomposition
    has_multiple_ability_types: bool = False
    ability_type_count: int = 0  # Count of distinct ability types (0-3)
    # Meld side tracking (CR 8.3.38): set by engine when the card is played
    meld_side: Optional[str] = None  # 'top', 'bottom', 'both', or None

    def __post_init__(self):
        # Copy raw → base (only if base not explicitly provided)
        if self.base_name is None:
            self.base_name = self.raw_name
        if self.base_pitch is None:
            self.base_pitch = self.raw_pitch
        if self.base_cost is None:
            self.base_cost = self.raw_cost
        if self.base_power is None:
            self.base_power = self.raw_power
        if self.base_defense is None:
            self.base_defense = self.raw_defense
        if self.base_life is None:
            self.base_life = self.raw_life
        if self.base_intellect is None:
            self.base_intellect = self.raw_intellect
        if self.base_arcane is None:
            self.base_arcane = self.raw_arcane
        if self.base_color is None:
            self.base_color = self.raw_color
        if not self.base_types:
            self.base_types = list(self.raw_types or [])
        if self.base_text_box == "":
            self.base_text_box = self.raw_text_box or ""
        if self.base_subtypes is None:
            self.base_subtypes = list(self.raw_subtypes or []) if self.raw_subtypes else None
        if self.base_keywords is None:
            self.base_keywords = list(self.raw_card_keywords or []) if self.raw_card_keywords else None
        if self.base_functional_text is None:
            self.base_functional_text = self.raw_functional_text
        if self.base_type_text is None:
            self.base_type_text = self.raw_type_text
        if self.base_classes is None:
            self.base_classes = list(self.raw_classes or []) if self.raw_classes else None

        # Copy base → current (only if current not explicitly provided)
        if self.name is None:
            self.name = self.base_name
        if self.pitch is None:
            self.pitch = self.base_pitch
        if self.cost is None:
            self.cost = self.base_cost
        if self.x_cost is None:
            self.x_cost = self.base_x_cost
        if self.power is None:
            self.power = self.base_power
        if self.defense is None:
            self.defense = self.base_defense
        if self.life is None:
            self.life = self.base_life
        if self.intellect is None:
            self.intellect = self.base_intellect
        if self.arcane is None:
            self.arcane = self.base_arcane
        if self.color is None:
            self.color = self.base_color
        if not self.types:
            self.types = list(self.base_types)
        if self.text_box == "":
            self.text_box = self.base_text_box
        if not self.subtypes:
            self.subtypes = list(self.base_subtypes or [])
        if self.keywords is None:
            self.keywords = list(self.base_keywords or []) if self.base_keywords else None
        if self.functional_text is None:
            self.functional_text = self.base_functional_text
        if self.type_text is None:
            self.type_text = self.base_type_text
        if self.classes is None:
            self.classes = list(self.base_classes or []) if self.base_classes else None

# ===============================================================================
# Computed Methods
# ===============================================================================

    @property
    def meld_cost(self):
        if self.base_cost is None:
            return None

        single_side_cost = self.cost
        if single_side_cost is None:
            return self.base_cost * 2

        # Meld doubles printed cost first, then applies the same net modifier.
        modifier_delta = single_side_cost - self.base_cost
        return (self.base_cost * 2) + modifier_delta

    @property
    def has_defense(self) -> bool:
        return self.defense is not None

    @property
    def underneath_slugs(self) -> list[str]:
        """Slugs of all cards placed under this card (e.g. transformed cards, soul charges)."""
        return [c.slug for c in self.cards_underneath]

    @property
    def is_targetable(self) -> bool:
        return self.is_public and (self.is_in_arena or self.zone.lower() == 'stack')

    @property
    def is_in_arena(self) -> bool:
        # CR 3.1.2a: a sub-card is NOT in the arena even if top-card is (CR 3.0.14b)
        if self.is_sub_card:
            return False
        return self.zone.lower() in (
            'arms', 'chest', 'combat chain', 'head', 'hero', 'legs', 'permanents', 'weapon'
        )

    @property
    def is_from_hand(self) -> bool:
        return self.prev_zone.lower() == 'hand'

    @property
    def is_attack(self) -> bool:
        return "Attack" in (self.base_types or [])

    @property
    def is_action(self) -> bool:
        return "Action" in (self.base_types or [])

    @property
    def is_instant(self) -> bool:
        return "Instant" in (self.base_types or [])

    @property
    def is_weapon(self) -> bool:
        return "Weapon" in (self.base_types or [])

    @property
    def is_equipment(self) -> bool:
        return "Equipment" in (self.base_types or [])

    @property
    def is_hero(self) -> bool:
        return "Hero" in (self.base_types or [])

    @property
    def is_defense_reaction(self) -> bool:
        return "Defense Reaction" in (self.base_types or [])

    @property
    def has_go_again(self) -> bool:
        return any(re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', k).lower() == "go again" for k in (self.keywords or []))

    @property
    def has_dominate(self) -> bool:
        return any(k.lower() == "dominate" for k in (self.keywords or []))

    @property
    def has_on_hit(self) -> bool:
        return any(k.lower() == "on hit" for k in (self.keywords or []))

    @property
    def has_reprise(self) -> bool:
        return any(k.lower() == "reprise" for k in (self.keywords or []))
    
    @property
    def is_living(self) -> bool:
        return True if hasattr(self, 'base_life') else False
    
    def get_keyword_value(self, keyword_name: str) -> Optional[int]:
        """Extract numeric value from a keyword (e.g., 'Ward 10' -> 10).
        Returns None if keyword not found or has no numeric value."""
        import re
        for kw in (self.keywords or []):
            # Match keyword with optional number
            match = re.match(rf'^{re.escape(keyword_name)}\s+(\d+)$', kw, re.IGNORECASE)
            if match:
                return int(match.group(1))
            # Also check exact match without number
            if kw.lower() == keyword_name.lower():
                return None
        return None

    def snapshot_state(self) -> dict:
        """Capture a last-known-information snapshot for this object.

        The snapshot intentionally stores resolved values rather than base_* values so
        callers can reason about the object's effective state immediately before it
        changed zones or ceased to exist.
        """
        return {
            'object_id': self.object_id,
            'slug': self.slug,
            'name': self.name,
            'zone': self.zone,
            'prev_zone': self.prev_zone,
            'owner': self.owner,
            'controller': self.controller,
            'is_public': self.is_public,
            'tapped': self.tapped,
            'exhausted': self.exhausted,
            'face_down': self.face_down,
            'pitch': self.pitch,
            'cost': self.cost,
            'power': self.power,
            'defense': self.defense,
            'life': self.life,
            'intellect': self.intellect,
            'arcane_damage': self.arcane,
            'types': list(self.base_types),
            'subtypes': list(self.subtypes),
            'keywords': list(self.keywords or []),
            'counters': dict(self.counters),
        }

    def remember_last_known_state(self, force: bool = False) -> dict:
        """Persist the current object snapshot for later last-known-information lookups.

        CR 1.2.3c: Last known information is immutable once recorded.
        Subsequent calls return the existing snapshot unless force=True.
        force=True is reserved for process_cease_to_exist() when an object
        definitively ceases to exist and we want the true final state.
        """
        if self.last_known_state is not None and not force:
            # Staging is a temporary zone, not a rules-relevant public state.
            # Allow one replacement once the card is in an actual game zone.
            if not (
                self.last_known_state.get('zone') == 'staging'
                and self.zone != 'staging'
            ):
                return self.last_known_state
        snapshot = self.snapshot_state()
        self.last_known_state = snapshot
        return snapshot

    def get_last_known_state(self) -> Optional[dict]:
        """Return the latest recorded last-known-information snapshot, if any."""
        return self.last_known_state

    def reset_to_base_state(self) -> None:
        """CR 3.0.9: Reset this object in-place — its previous existence ceases to exist.

        Clears all runtime-accumulated state (counters, effects, status flags, temp
        subtypes) and issues a new object_id so the object has no relation to its
        prior existence. Base stats and card identity are preserved.
        """
        self.object_id = next(_CARD_OBJECT_ID_COUNTER)
        self.effects = []
        self.counters = {}
        self.tapped = False
        self.exhausted = False
        self.face_down = False
        self.cards_underneath = []
        self.is_sub_card = False
        self.top_card = None
        self.meld_side = None
        self.last_known_state = None
        self.permanent_subtype = None
    
    def to_dict(self) -> dict:
        """Convert card object to dict type object for outputting during debug
        """
        return {
            'name': self.name,
            'object_id': self.object_id,
        }
class CardDB:
    """Wraps slug_index.msgpack for card lookups."""

    def __init__(self, path: Optional[str] = None):
        path = path or SLUG_INDEX_PATH
        if path.endswith(".msgpack"):
            with open(path, "rb") as f:
                data = msgpack.unpack(f, raw=False)
        else:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        self._by_slug: dict[str, dict] = data.get("by_slug", {})
        self._by_name: dict[str, list[str]] = data.get("by_name", {})
        self._card_cache: dict[str, Card] = {}  # template cache — shared across all games

    def resolve_slug(self, slug: str) -> Optional[str]:
        """Resolve a slug to the canonical slug in the database.
        Handles mismatches from slugify differences (e.g. unicode normalization)."""
        if slug in self._by_slug:
            return slug
        # Normalize hyphens to underscores (index.ts uses hyphens, slug_index uses underscores)
        normalized = slug.replace("-", "_")
        if normalized in self._by_slug:
            return normalized
        # Try by_name fallback: strip color suffix and look up by name
        color_suffix = None
        base = slug
        for c in ("_red", "_yellow", "_blue"):
            if slug.endswith(c):
                color_suffix = c[1:]
                base = slug[:-len(c)]
                break
        # Normalize: by_name keys may have hyphens/special chars.
        # Build a normalized lookup map on first use.
        if not hasattr(self, '_name_normalized'):
            import unicodedata
            self._name_normalized = {}
            for name_key, slugs in self._by_name.items():
                norm = unicodedata.normalize("NFKD", name_key).encode("ascii", "ignore").decode("ascii")
                norm = norm.lower().replace("-", " ").replace(",", "").replace("'", "")
                self._name_normalized[norm] = slugs
         # Fuzzy matching if exact name match fails (e.g. due to unicode normalization differences or minor typos)
        from thefuzz import fuzz
        if base in self._name_normalized:
            return self._name_normalized[base][0]
        max_ratio = 0
        best_match = None
        for name_key, slugs in self._name_normalized.items():
            ratio = fuzz.ratio(base, name_key)
            if ratio > max_ratio:
                max_ratio = ratio
                best_match = slugs[0]
        if max_ratio >= 80:  # Threshold for fuzzy match acceptance
            return best_match
        else:
            return None

    def get(self, slug: str) -> Optional[Card]:
        if slug is None:
            return None
        resolved = self.resolve_slug(slug)
        if resolved is None:
            return None
        if resolved in self._card_cache:
            c = copy(self._card_cache[resolved])
            c.object_id = next(_CARD_OBJECT_ID_COUNTER)  # CR 3.0.9: each retrieval is a new game object
            return c
        raw = self._by_slug[resolved]
        slug = resolved  # use canonical slug

        card = Card(slug=slug)

        # --- Map slug_index fields → Card raw_* fields ---
        # slug_index uses index.ts field names exactly (life, intellect, keywords, …)
        # All values arriving from msgpack/json are already native Python types
        # (int, list, str, bool, None) — no .isnumeric() needed.

        # Direct int stats
        card.raw_pitch        = _int_or_none(raw.get("pitch"))
        card.raw_cost         = _int_or_none(raw.get("cost"))
        card.raw_power        = _int_or_none(raw.get("power"))
        card.raw_defense      = _int_or_none(raw.get("defense"))
        card.raw_life       = _int_or_none(raw.get("life"))         
        card.raw_intellect = _int_or_none(raw.get("intellect"))
        card.raw_arcane       = _int_or_none(raw.get("arcane"))

        # String fields
        card.raw_name             = raw.get("name")
        card.raw_color            = raw.get("color")
        card.raw_functional_text  = raw.get("functionalText") or raw.get("functional_text")
        card.raw_type_text        = raw.get("typeText") or raw.get("type_text")

        # List fields
        card.raw_types        = raw.get("types") or []
        card.raw_subtypes     = raw.get("subtypes") or []
        card.raw_classes      = raw.get("classes") or []
        card.raw_card_keywords = raw.get("keywords") or raw.get("card_keywords") or []
        card.raw_legal_heroes = raw.get("legalHeroes") or raw.get("legal_heroes") or []
        card.raw_legal_formats = raw.get("legalFormats") or raw.get("legal_formats") or []

        # Bool flags
        card.raw_played_horizontally = bool(raw.get("playedHorizontally") or raw.get("played_horizontally"))

        # Extra fields stored as card attributes (not part of layer system but useful)
        card.talents          = raw.get("talents") or []
        card.shorthands       = raw.get("shorthands") or []
        card.meta             = raw.get("meta") or []
        card.metatypes        = raw.get("metatypes") or []
        card.traits           = raw.get("traits") or []
        card.fusions          = raw.get("fusions") or []
        card.bonds            = raw.get("bonds") or []
        card.flows            = raw.get("flows") or []
        card.specializations  = raw.get("specializations") or []
        card.banned_formats   = raw.get("bannedFormats") or raw.get("banned_formats") or []
        card.restricted_formats = raw.get("restrictedFormats") or raw.get("restricted_formats") or []
        card.special_cost     = raw.get("specialCost") or raw.get("special_cost")
        card.special_power    = raw.get("specialPower") or raw.get("special_power")
        card.special_defense  = raw.get("specialDefense") or raw.get("special_defense")
        card.special_life     = raw.get("specialLife") or raw.get("special_life")
        card.special_arcane   = raw.get("specialArcane") or raw.get("special_arcane")
        card.hero_enum        = raw.get("hero")
        card.young            = bool(raw.get("young"))
        card.is_card_back     = bool(raw.get("isCardBack") or raw.get("is_card_back"))
        card.opposite_side_card_identifiers = raw.get("oppositeSideCardIdentifiers") or []
        card.set_identifiers  = raw.get("setIdentifiers") or raw.get("set_identifiers") or []
        card.sets             = raw.get("sets") or []
        card.rarity           = raw.get("rarity")
        card.default_image    = raw.get("defaultImage") or raw.get("default_image")

        # Populate base_* from raw_* (base can be changed by "base" effects)
        card.base_name        = card.raw_name
        card.base_pitch       = card.raw_pitch
        card.base_cost        = card.raw_cost
        card.base_power       = card.raw_power
        card.base_defense     = card.raw_defense
        card.base_life        = card.raw_life
        card.base_intellect   = card.raw_intellect
        card.base_arcane      = card.raw_arcane
        card.base_color       = card.raw_color
        card.base_types       = list(card.raw_types or [])
        card.base_subtypes    = list(card.raw_subtypes or [])
        card.base_keywords    = list(card.raw_card_keywords or [])
        card.base_classes     = list(card.raw_classes or [])
        card.base_functional_text = card.raw_functional_text
        card.base_type_text   = card.raw_type_text

        # Parse activation cost from abilities (e.g., "Once per Turn Action - {r}{r}" -> cost=2)
        abilities_list = getattr(card, 'raw_functional_text', '').split(r"\n\n")
        if abilities_list != '':
            import re
            for ability in abilities_list:
                # Match patterns like "{r}", "{r}{r}", "{r}{r}{r}" for resource cost
                match = re.search(r'\{([rR])\}', ability)
                if match:
                    # Count all {r} occurrences
                    card.activation_cost = ability.count('{r}') + ability.count('{R}')
                    break

        import re
        ability_flags = {
            'has_activated_ability': False,
            'has_once_per_turn_limit': False,
            'has_action_activation': False,
            'has_instant_activation': False,
            'has_attack_reaction_activation': False,
            'has_non_resource_activation_cost': False,
            'has_conditional_activation': False,
            'has_triggered_ability': False,
            'has_on_hit_trigger': False,
            'has_etb_trigger': False,
            'has_leaves_arena_trigger': False,
            'has_start_of_turn_trigger': False,
            'has_end_of_turn_trigger': False,
            'has_static_ability': False,
            'has_while_condition': False,
            'has_continuous_buff': False,
            'has_replacement_effect': False,
            'has_prevention_effect': False,
            'requires_target': False,
            'can_target_hero': False,
            'can_target_attack': False,
            'can_target_permanent': False,
            'has_multiple_ability_types': False,
            'ability_type_count': 0,
        }
        
        # Parse from abilities_and_effects list (type indicators)
        for ability_type in abilities_list:
            if ability_type:
                setattr(card,'has_activated_ability', True)
                for text in ['per turn', 'action', 'instant', 'attack reaction', 'defense reaction']:
                    if text == 'per turn' and text in ability_type.lower():
                        num = 1 if 'once per turn' in ability_type.lower() else None
                        num = 2 if 'twice per turn' in ability_type.lower() else num
                        num = 3 if 'thrice per turn' in ability_type.lower() else num
                        card.base_activations = num
                        card.activations = num
                        card.has_once_per_turn_limit = True
                    else:
                        if text in ability_type.lower():
                            setattr(card, f'has_{text.replace(' ', '_')}_activation', True)
        
        # Parse from functional_text (detailed ability patterns)
        if card.raw_functional_text:
            func_lower = card.raw_functional_text.lower()
            
            # Non-resource activation costs (Round 9 fix - comprehensive)
            # Includes: destroy, discard, remove/banish, life payment, Gold tokens, counter removal
            non_resource_patterns = [
                'destroy this', 'destroy a', 'destroy another',
                'destroy',  # General destroy (equipment, Gold tokens, etc.)
                r'discard( \d+)?( cards?)?',  # "discard", "discard 2 cards"
                r'remove \w+ counter',  # "remove a steam counter", "remove X counters"
                'remove', 'banish',
                r'pay \d*{h}',  # "pay {h}", "pay 1{h}", "pay 2{h}"
                r'lose \d*{h}',  # "lose {h}", "lose 1{h}"
                'pay {g}',  # Gold payment
            ]
            if any(re.search(pattern, func_lower) for pattern in non_resource_patterns):
                if any(sep in func_lower for sep in [' - ', ': ', ',then', 'additional cost']):  # In activation cost section
                    setattr(card, 'has_non_resource_activation_cost', True)
            
            # Triggered abilities (CR 5.4.6) - refined pattern to reduce false positives
            trigger_pattern = r'\b(when|whenever|at the)\b'
            if re.search(trigger_pattern, func_lower):
                # Exclude "when you play this" patterns (those are play-static, not triggered)
                # Use word boundary to avoid excluding "when you play this and..." compound triggers
                if not re.search(r'\b(when you play this|this is played)\b(?!\s+and)', func_lower):
                    setattr(card, 'has_triggered_ability', True)
                    
                    if 'when this hits' in func_lower or 'when this attacks' in func_lower:
                        setattr(card,'has_on_hit_trigger', True)
                    
                    # ETB triggers - expanded patterns (Round 9 fix)
                    etb_patterns = [
                        'enters the arena',
                        'this enters',
                        'as this enters',
                        r'as (this|~|[A-Z][a-z]+) enters',  # "As ~ enters" or "As Name enters"
                    ]
                    if any(re.search(pattern, func_lower) for pattern in etb_patterns):
                        setattr(card,'has_etb_trigger', True)
                    
                    if 'leaves the arena' in func_lower or 'this leaves' in func_lower:
                        setattr(card,'has_leaves_arena_trigger', True)
                    if 'start of' in func_lower and 'turn' in func_lower:
                        setattr(card,'has_start_of_turn_trigger', True)
                    if 'end of' in func_lower and 'turn' in func_lower:
                        setattr(card,'has_end_of_turn_trigger', True)
            
            # Static abilities (CR 5.4)
            if 'while ' in func_lower:
                setattr(card, 'has_static_ability', True)
                setattr(card,'has_while_condition', True)
            
            # Continuous buffs (modify other cards)
            if re.search(r'(attack|card|equipment|weapon)s? (you control|get|gain)', func_lower):
                setattr(card,'has_static_ability', True)
                setattr(card,'has_continuous_buff', True)
            
            # Replacement/prevention effects (CR 6.4)
            if 'instead' in func_lower or 'prevent' in func_lower:
                setattr(card,'has_replacement_effect', True)
                if 'prevent' in func_lower and 'damage' in func_lower:
                    setattr(card,'has_prevention_effect', True)
            
            # Targeting requirements (CR 1.4, 1.8.5, Round 9 Gap #2 fix - refined)
            # CR 1.8.5: "target [DESCRIPTION]" or "[DESCRIPTION] (target/targets)"
            # DESCRIPTION must specify a legal target (hero, player, card, attack, permanent, etc.)
            # We only set requires_target=True if a valid targeting pattern is found
            
            has_valid_targeting = False
            
            # Check format 1: "target [DESCRIPTION]" where DESCRIPTION contains a target type
            if re.search(r'\btarget\b', func_lower):
                # Must be followed by a recognized target type (within reasonable distance)
                if re.search(r'\btarget\b[^.;:]*\b(hero|player|attack|card|equipment|weapon|ally|permanent|aura)\b', func_lower):
                    has_valid_targeting = True
            
            # Check format 2: "[DESCRIPTION] (target)" where DESCRIPTION contains a target type
            if re.search(r'\(targets?\)', func_lower):
                target_phrase = re.search(r'([^.;:]*)\(targets?\)', func_lower)
                if target_phrase:
                    phrase = target_phrase.group(1)
                    if re.search(r'\b(hero|player|attack|card|equipment|weapon|ally|permanent|aura)\b', phrase):
                        has_valid_targeting = True
            
            if has_valid_targeting:
                setattr(card,'requires_target', True)
                
                # Determine target types from functional text (flexible patterns allow modifiers)
                # Hero/player targeting: "target [modifiers] hero/player"
                if re.search(r'target\b.*?\b(hero|player)\b', func_lower):
                    setattr(card,'can_target_hero', True)
                
                # Attack targeting: "target [modifiers] attack" but NOT verb forms like "may attack"
                # Exclude verb patterns: "may attack", "can attack", "to attack", "cannot attack"
                if re.search(r'target\b.*?\battack\b', func_lower):
                    # Check if "attack" is used as noun (target type) or verb (effect)
                    # If "attack" is preceded by modal verbs, it's likely a verb, not a target type
                    attack_match = re.search(r'target\b(.*?)\battack\b', func_lower)
                    if attack_match:
                        context = attack_match.group(1)  # Text between "target" and "attack"
                        # If context ends with modal verbs, "attack" is likely a verb
                        if not re.search(r'\b(may|can|must|to|cannot|should|will|would)\s+$', context):
                            setattr(card,'can_target_attack', True)
                
                # Permanent targeting: "target [modifiers] card/equipment/weapon/ally/permanent/aura"
                if re.search(r'target\b.*?\b(card|equipment|weapon|ally|permanent|aura)\b', func_lower):
                    setattr(card,'can_target_permanent', True)
                
                # Support CR 1.8.5 alternate format: "[DESCRIPTION] (target)"
                # Look for object types before "(target)" or "(targets)"
                if re.search(r'\(targets?\)', func_lower):
                    target_phrase = re.search(r'([^.;:]*)\(targets?\)', func_lower)
                    if target_phrase:
                        phrase = target_phrase.group(1)
                        if re.search(r'\b(hero|player)\b', phrase):
                            setattr(card,'can_target_hero', True)
                        if re.search(r'\battack\b', phrase):
                            setattr(card,'can_target_attack', True)
                        if re.search(r'\b(card|equipment|weapon|ally|permanent|aura)\b', phrase):
                            setattr(card,'can_target_permanent', True)
        
        # Multi-ability decomposition
        ability_count = 0
        for ability in abilities_list:
            if ":" in ability:
                ability_count += 1
        
        setattr(card,'ability_type_count', ability_count)
        setattr(card, 'has_multiple_ability_types', ability_count >= 2)

        self._card_cache[resolved] = card
        return copy(card)

    def __contains__(self, slug: str) -> bool:
        return slug in self._by_slug

def load_card(slug: str, db: CardDB) -> Optional[Card]:
    """Helper to load a card from the database."""
    return db.get(slug)

def if_not_none(value, default=None):
    return value if value is not None else default
