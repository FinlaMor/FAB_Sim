"""Card data model and database wrapper for FAB card data (OO rewrite)."""

from __future__ import annotations

import json
import re
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
    base_arcane_damage: Optional[int] = None
    base_color: Optional[str] = None
    base_text_box: str = ""
    base_functional_text: str = ""
    activation_cost: Optional[int] = None  # For weapon/equipment activated abilities
    abilities_and_effects: list[str] = field(default_factory=list)  # From slug_index
    effects: list[tuple[str, function]] = field(default_factory=list)
    counters: dict[str, int] = field(default_factory=dict)  # Card-specific counters

    # Zone tracking
    zone: str = "inventory"
    prev_zone: str = ""
    owner: int = 0
    controller: Optional[int] = None
    is_public: bool = False

    # State
    tapped: bool = False
    exhausted: bool = False
    face_down: bool = False  # CR 8.5.24: face-down = private, face-up = public

    # Ability structure flags (Gap #1 fix - Round 9)
    # Activated abilities (CR 5.2)
    has_activated_ability: bool = False
    has_once_per_turn_limit: bool = False
    has_action_activation: bool = False
    has_instant_activation: bool = False
    has_attack_reaction_activation: bool = False
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
    # Targeting requirements (CR 1.4, Gap #2 fix - Round 9)
    requires_target: bool = False
    can_target_hero: bool = False
    can_target_attack: bool = False
    can_target_permanent: bool = False
    # Multi-ability decomposition (Gap #3 fix - Round 9)
    has_multiple_ability_types: bool = False
    ability_type_count: int = 0  # Count of distinct ability types (0-3)

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
    def arcane_damage(self):
        if self.base_arcane_damage is None:
            return None
        val = self.base_arcane_damage
        for func in [x[1] for x in self.effects if x[0] == 'base_arcane_damage']:
            val = func(self.base_arcane_damage)
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
    
    def get_keyword_value(self, keyword_name: str) -> Optional[int]:
        """Extract numeric value from a keyword (e.g., 'Ward 10' -> 10).
        Returns None if keyword not found or has no numeric value."""
        import re
        for kw in self.keywords:
            # Match keyword with optional number
            match = re.match(rf'^{re.escape(keyword_name)}\s+(\d+)$', kw, re.IGNORECASE)
            if match:
                return int(match.group(1))
            # Also check exact match without number
            if kw.lower() == keyword_name.lower():
                return None
        return None
    
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
        arcane_val = _int_or_none(raw.get("arcane"))

        types = raw.get("types") or []
        subtypes_list = raw.get("subtypes") or []
        supertypes_list = raw.get("supertypes") or []
        keywords = raw.get("card_keywords") or raw.get("keywords") or []
        functional_text = raw.get("functional_text") or ""
        abilities_list = raw.get("abilities_and_effects") or []
        
        # Parse activation cost from abilities (e.g., "Once per Turn Action - {r}{r}" -> cost=2)
        activation_cost_val = None
        if abilities_list:
            import re
            for ability in abilities_list:
                # Match patterns like "{r}", "{r}{r}", "{r}{r}{r}" for resource cost
                match = re.search(r'\{([rR])\}', ability)
                if match:
                    # Count all {r} occurrences
                    activation_cost_val = ability.count('{r}') + ability.count('{R}')
                    break

        # Parse ability structure flags (Gap #1 fix - Round 9)
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
                ability_flags['has_activated_ability'] = True
                if 'Once per Turn' in ability_type:
                    ability_flags['has_once_per_turn_limit'] = True
                if 'Action' in ability_type and 'Reaction' not in ability_type:
                    ability_flags['has_action_activation'] = True
                if 'Instant' in ability_type:
                    ability_flags['has_instant_activation'] = True
                if 'Attack Reaction' in ability_type or 'Defense Reaction' in ability_type:
                    ability_flags['has_attack_reaction_activation'] = True
        
        # Parse from functional_text (detailed ability patterns)
        if functional_text:
            func_lower = functional_text.lower()
            
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
                    ability_flags['has_non_resource_activation_cost'] = True
            
            # Triggered abilities (CR 5.4.6) - refined pattern to reduce false positives
            trigger_pattern = r'\b(when|whenever|at the)\b'
            if re.search(trigger_pattern, func_lower):
                # Exclude "when you play this" patterns (those are play-static, not triggered)
                # Use word boundary to avoid excluding "when you play this and..." compound triggers
                if not re.search(r'\b(when you play this|this is played)\b(?!\s+and)', func_lower):
                    ability_flags['has_triggered_ability'] = True
                    
                    if 'when this hits' in func_lower or 'when this attacks' in func_lower:
                        ability_flags['has_on_hit_trigger'] = True
                    
                    # ETB triggers - expanded patterns (Round 9 fix)
                    etb_patterns = [
                        'enters the arena',
                        'this enters',
                        'as this enters',
                        r'as (this|~|[A-Z][a-z]+) enters',  # "As ~ enters" or "As Name enters"
                    ]
                    if any(re.search(pattern, func_lower) for pattern in etb_patterns):
                        ability_flags['has_etb_trigger'] = True
                    
                    if 'leaves the arena' in func_lower or 'this leaves' in func_lower:
                        ability_flags['has_leaves_arena_trigger'] = True
                    if 'start of' in func_lower and 'turn' in func_lower:
                        ability_flags['has_start_of_turn_trigger'] = True
                    if 'end of' in func_lower and 'turn' in func_lower:
                        ability_flags['has_end_of_turn_trigger'] = True
            
            # Static abilities (CR 5.4)
            if 'while ' in func_lower:
                ability_flags['has_static_ability'] = True
                ability_flags['has_while_condition'] = True
            
            # Continuous buffs (modify other cards)
            if re.search(r'(attack|card|equipment|weapon)s? (you control|get|gain)', func_lower):
                ability_flags['has_static_ability'] = True
                ability_flags['has_continuous_buff'] = True
            
            # Replacement/prevention effects (CR 6.4)
            if 'instead' in func_lower or 'prevent' in func_lower:
                ability_flags['has_replacement_effect'] = True
                if 'prevent' in func_lower and 'damage' in func_lower:
                    ability_flags['has_prevention_effect'] = True
            
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
                ability_flags['requires_target'] = True
                
                # Determine target types from functional text (flexible patterns allow modifiers)
                # Hero/player targeting: "target [modifiers] hero/player"
                if re.search(r'target\b.*?\b(hero|player)\b', func_lower):
                    ability_flags['can_target_hero'] = True
                
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
                            ability_flags['can_target_attack'] = True
                
                # Permanent targeting: "target [modifiers] card/equipment/weapon/ally/permanent/aura"
                if re.search(r'target\b.*?\b(card|equipment|weapon|ally|permanent|aura)\b', func_lower):
                    ability_flags['can_target_permanent'] = True
                
                # Support CR 1.8.5 alternate format: "[DESCRIPTION] (target)"
                # Look for object types before "(target)" or "(targets)"
                if re.search(r'\(targets?\)', func_lower):
                    target_phrase = re.search(r'([^.;:]*)\(targets?\)', func_lower)
                    if target_phrase:
                        phrase = target_phrase.group(1)
                        if re.search(r'\b(hero|player)\b', phrase):
                            ability_flags['can_target_hero'] = True
                        if re.search(r'\battack\b', phrase):
                            ability_flags['can_target_attack'] = True
                        if re.search(r'\b(card|equipment|weapon|ally|permanent|aura)\b', phrase):
                            ability_flags['can_target_permanent'] = True
        
        # Multi-ability decomposition (Gap #3 fix - Round 9)
        ability_type_count = 0
        if ability_flags['has_activated_ability']:
            ability_type_count += 1
        if ability_flags['has_triggered_ability']:
            ability_type_count += 1
        if ability_flags['has_static_ability']:
            ability_type_count += 1
        ability_flags['ability_type_count'] = ability_type_count
        ability_flags['has_multiple_ability_types'] = ability_type_count >= 2

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
            subtypes=if_not_none(subtypes_list),
            supertypes=if_not_none(supertypes_list),
            keywords=if_not_none(keywords),
            category=if_not_none(_derive_category(raw)),
            base_pitch=if_not_none(pitch_val),
            base_cost=if_not_none(cost_val),
            base_power=if_not_none(power_val),
            base_defense=if_not_none(defense_val),
            base_life=if_not_none(life_val),
            base_intellect=if_not_none(intellect_val),
            base_arcane_damage=if_not_none(arcane_val),
            base_color=if_not_none(color),
            base_text_box=if_not_none(raw.get("text") or ""),
            base_functional_text=if_not_none(functional_text),
            activation_cost=if_not_none(activation_cost_val),
            abilities_and_effects=if_not_none(abilities_list),
            zone="inventory",
            prev_zone="",
            owner=0,
            controller=None,
            is_public=False,
            tapped=False,
            exhausted=False,
            **ability_flags,
        )

    def __contains__(self, slug: str) -> bool:
        return slug in self._by_slug

def load_card(slug: str, db: CardDB) -> Optional[Card]:
    """Helper to load a card from the database."""
    return db.get(slug)

def if_not_none(value, default=None):
    return value if value is not None else default
