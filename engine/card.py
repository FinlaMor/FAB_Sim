"""Card data model and database wrapper for FAB card data (OO rewrite)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional
import os, sys

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from config import SLUG_INDEX_PATH


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
    name: str

    # Stats
    types: list[str] = field(default_factory=list)
    subtypes: list[str] = field(default_factory=list)
    supertypes: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    category: str = "deck"
    base_pitch: Optional[int] = None
    base_cost: Optional[int] = None
    base_power: Optional[int] = None
    base_defense: Optional[int] = None
    base_life: Optional[int] = None
    base_intellect: Optional[int] = None
    base_color: Optional[str] = None
    base_text_box: str = ""
    base_functional_text: str = ""
    effects: list[tuple[str, function]] = field(default_factory=list)

    # Zone tracking
    zone: str = "inventory"
    prev_zone: str = ""
    owner: int = 0
    controller: Optional[int] = None
    is_public: bool = False

    # State
    tapped: bool = False
    exhausted: bool = False

    # ---------------------------------------------------------------------------
    # Computed properties
    # ---------------------------------------------------------------------------
    @property
    def pitch(self):
        if self.base_pitch is None:
            return None
        val = self.base_pitch
        for func in [x[1] for x in self.effects if x[0] == 'base_pitch']:
            val = func(self.base_pitch)
        return val


    @property
    def cost(self):
        if self.base_cost is None:
            return None

        val = self.base_cost
        for func in [x[1] for x in self.effects if x[0] == 'base_cost']:
            val = func(self.base_cost)
        return val

    @property
    def power(self):
        if self.base_power is None:
            return None
        val = self.base_power
        for func in [x[1] for x in self.effects if x[0] == 'base_power']:
            val = func(self.base_power)
        return val

    @property
    def defense(self):
        if self.base_defense is None:
            return None
        val = self.base_defense
        for func in [x[1] for x in self.effects if x[0] == 'base_defense']:
            val = func(self.base_defense)
        return val
    
    @property
    def life(self):
        if self.base_life is None:
            return None
        val = self.base_life
        for func in [x[1] for x in self.effects if x[0] == 'base_life']:
            val = func(self.base_life)
        return val
    
    @property
    def intellect(self):
        if self.base_intellect is None:
            return None
        val = self.base_intellect
        for func in [x[1] for x in self.effects if x[0] == 'base_intellect']:
            val = func(self.base_intellect)
        return val
    
    @property
    def color(self):
        if self.base_color is None:
            return None
        val = self.base_color
        for func in [x[1] for x in self.effects if x[0] == 'base_color']:
            val = func(self.base_color)
        return val

    @property
    def text_box(self):
        if self.base_text_box is None:
            return None
        val = self.base_text_box
        for func in [x[1] for x in self.effects if x[0] == 'base_text_box']:
            val = func(self.base_text_box)
        return val
    
    @property
    def functional_text(self):
        if self.base_functional_text is None:
            return None
        val = self.base_functional_text
        for func in [x[1] for x in self.effects if x[0] == 'base_functional_text']:
            val = func(self.base_functional_text)
        return val

    @property
    def has_defense(self) -> bool:
        return self.defense is not None

    @property
    def is_targetable(self) -> bool:
        return self.is_public and (self.is_in_arena or self.zone.lower() == 'stack')

    @property
    def is_in_arena(self) -> bool:
        return self.zone.lower() in (
            'arms', 'chest', 'combat chain', 'head', 'hero', 'legs', 'permanent', 'weapon'
        )

    @property
    def is_from_hand(self) -> bool:
        return self.prev_zone.lower() == 'hand'

    @property
    def is_attack(self) -> bool:
        return "Attack" in self.types

    @property
    def is_action(self) -> bool:
        return "Action" in self.types

    @property
    def is_instant(self) -> bool:
        return "Instant" in self.types

    @property
    def is_weapon(self) -> bool:
        return "Weapon" in self.types

    @property
    def is_equipment(self) -> bool:
        return "Equipment" in self.types

    @property
    def is_hero(self) -> bool:
        return "Hero" in self.types

    @property
    def is_defense_reaction(self) -> bool:
        return "Defense Reaction" in self.types

    @property
    def has_go_again(self) -> bool:
        return any(k.lower() == "go again" for k in self.keywords)

    @property
    def has_dominate(self) -> bool:
        return any(k.lower() == "dominate" for k in self.keywords)

    @property
    def has_on_hit(self) -> bool:
        return any(k.lower() == "on hit" for k in self.keywords)

    @property
    def has_reprise(self) -> bool:
        return any(k.lower() == "reprise" for k in self.keywords)
    
    def to_dict(self) -> dict:
        """Convert card object to dict type object for outputting during debug
        """
        return {
            'name': self.name
        }
class CardDB:
    """Wraps slug_index.json for card lookups."""

    def __init__(self, path: Optional[str] = None):
        path = path or SLUG_INDEX_PATH
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self._by_slug: dict[str, dict] = data.get("by_slug", {})
        self._by_name: dict[str, list[str]] = data.get("by_name", {})

    def resolve_slug(self, slug: str) -> Optional[str]:
        """Resolve a slug to the canonical slug in the database.
        Handles mismatches from slugify differences (e.g. unicode normalization)."""
        if slug in self._by_slug:
            return slug
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
        name_key = base.replace("_", " ")
        candidates = self._name_normalized.get(name_key, [])
        if color_suffix:
            for cand in candidates:
                if cand.endswith(f"_{color_suffix}"):
                    return cand
        elif candidates:
            return candidates[0]
        return None

    def get(self, slug: str) -> Optional[Card]:
        if slug is None:
            return None
        resolved = self.resolve_slug(slug)
        if resolved is None:
            return None
        raw = self._by_slug[resolved]
        slug = resolved  # use canonical slug

        raw_defense = raw.get("defense")
        defense_val = _int_or_none(raw_defense)

        raw_pitch = raw.get("pitch")
        pitch_val = _int_or_none(raw_pitch)
        # Ensure pitch is at least 0 for arithmetic safety
        if pitch_val is None:
            pitch_val = 0

        raw_cost = raw.get("cost")
        cost_val = _int_or_none(raw_cost)

        raw_power = raw.get("power")
        power_val = _int_or_none(raw_power)
        life_val = _int_or_none(raw.get("health"))
        intellect_val = _int_or_none(raw.get("intelligence"))

        types = raw.get("types") or []
        keywords = raw.get("card_keywords") or raw.get("keywords") or []
        functional_text = raw.get("functional_text") or ""

        # Derive color from pitch
        color: Optional[str] = None
        if pitch_val == 1:
            color = "red"
        elif pitch_val == 2:
            color = "yellow"
        elif pitch_val == 3:
            color = "blue"
        if color:
            assert slug.endswith(color), "Slug '{}' does not match derived color '{}'".format(slug, color)

        return Card(
            slug=slug,
            name=raw.get("name", slug),
            types=if_not_none(types),
            subtypes=if_not_none(raw.get("subtypes") or []),
            supertypes=if_not_none(raw.get("supertypes") or []),
            keywords=if_not_none(keywords),
            category=if_not_none(_derive_category(raw)),
            base_pitch=if_not_none(pitch_val),
            base_cost=if_not_none(cost_val),
            base_power=if_not_none(power_val),
            base_defense=if_not_none(defense_val),
            base_life=if_not_none(life_val),
            base_intellect=if_not_none(intellect_val),
            base_color=if_not_none(color),
            base_text_box=if_not_none(raw.get("text") or ""),
            base_functional_text=if_not_none(functional_text),
            zone="inventory",
            prev_zone="",
            owner=0,
            controller=None,
            is_public=False,
            tapped=False,
            exhausted=False,
        )

    def __contains__(self, slug: str) -> bool:
        return slug in self._by_slug

def load_card(slug: str, db: CardDB) -> Optional[Card]:
    """Helper to load a card from the database."""
    return db.get(slug)

def if_not_none(value, default=None):
    return value if value is not None else default
