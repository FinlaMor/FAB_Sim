"""encoder/card_embedder.py — Maps a Card (or masked placeholder) to a d_model vector.

Each card is embedded as:
    slug embedding          (card identity)
    + color embedding       (color: none/red/yellow/blue)
    + zone embedding        (where the card currently is)
    + numeric projection    (properties + state flags + counters + ability metadata)
    + types projection      (multi-hot over card types)
    + keyword pooling       (variable-length keyword set pooled to fixed-width vector)
    → final linear → LayerNorm → d_model

Opponent's hidden cards are represented as masked tokens (slug_idx=0),
preserving zone info but zeroing out all identity features.
"""

import json
import re
from typing import Optional

import torch
import torch.nn as nn

from encoder.feature_schema import (
    CARD_KEYWORDS,
    COUNTER_OOV_TYPE,
    COUNTER_TYPES,
    KEYWORD_OOV_TOKEN,
    PARAMETERIZED_KEYWORD_NORMALIZERS,
    build_schema_metadata,
    normalize_counter,
    validate_schema_metadata,
)
from engine.card import Card


# ---------------------------------------------------------------------------
# Vocabulary constants — add to these lists freely; unknown values → index 0
# ---------------------------------------------------------------------------

CARD_TYPES = [
    "Action", "Attack", "Defense Reaction", "Attack Reaction",
    "Equipment", "Weapon", "Aura", "Ally", "Token", "Hero", "Item", "Instant",
]

CARD_SUBTYPES = [
    # Equipment zones
    "Head", "Chest", "Arms", "Legs", "Off-Hand",
    # Weapon types
    "1H", "2H", "Bow", "Gun", "Staff", "Sword", "Axe", "Dagger", "Hammer", "Club", "Pistol", "Rifle",
    # Attack subtypes
    "Attack", "Arrow",
    # Permanent subtypes
    "Aura", "Item", "Ally", "Affliction",
    # Other
    "Ash", "Construct", "Figment", "Invocation", "Landmark", "Quiver",
]

CARD_SUPERTYPES = [
    # Classes (17)
    "Adjudicator", "Assassin", "Bard", "Brute", "Guardian",
    "Illusionist", "Mechanologist", "Merchant", "Necromancer",
    "Ninja", "Pirate", "Ranger", "Runeblade", "Shapeshifter",
    "Thief", "Warrior", "Wizard",
    # Talents (12)
    "Chaos", "Draconic", "Earth", "Elemental", "Ice", "Light",
    "Lightning", "Mystic", "Revered", "Reviled", "Royal", "Shadow",
    # Generic
    "Generic",
]

CARD_ZONES = [
    "hand", "deck", "graveyard", "arsenal", "banished",
    "head", "chest", "arms", "legs", "weapon",
    "weapon1", "weapon2",
    "soul",
    "hero", "pitch", "stack", "combat chain", "inventory", "permanents",
    "equipment",
]

CARD_COLORS = ["none", "red", "yellow", "blue"]

# Index maps — index 0 reserved for unknown/missing in all categorical embeddings
N_TYPES     = len(CARD_TYPES)
N_SUBTYPES  = len(CARD_SUBTYPES)
N_SUPERTYPES = len(CARD_SUPERTYPES)
N_KEYWORDS  = len(CARD_KEYWORDS)
N_COUNTER_TYPES = len(COUNTER_TYPES)
N_ZONES     = len(CARD_ZONES) + 1    # 0 = unknown
N_COLORS    = len(CARD_COLORS) + 1  # 0 = unknown

_TYPE_IDX     = {t: i for i, t in enumerate(CARD_TYPES)}
_SUBTYPE_IDX  = {s: i for i, s in enumerate(CARD_SUBTYPES)}
_SUPERTYPE_IDX = {s: i for i, s in enumerate(CARD_SUPERTYPES)}
_KW_IDX       = {k.lower(): i for i, k in enumerate(CARD_KEYWORDS)}
_ZONE_IDX     = {z: i + 1 for i, z in enumerate(CARD_ZONES)}
_COLOR_IDX    = {c: i + 1 for i, c in enumerate(CARD_COLORS)}
_KW_OOV_IDX   = _KW_IDX[KEYWORD_OOV_TOKEN.lower()]

# Approximate expected values for normalizing continuous features to [0, 1] i.e. should the model be impressed if it sees an attack bigger than x
_NORM = {"pitch": 3.0, "cost": 3.0, "power": 10.0, "defense": 4.0, 
         "life": 40.0, "intellect": 4.0, "arcane": 6.0, "activation": 3.0}

# Parameterized keywords that have numeric values.
PARAMETERIZED_KEYWORDS = sorted(PARAMETERIZED_KEYWORD_NORMALIZERS.keys())
_KW_WITH_VALUE_RE = re.compile(r"^(.+?)\s+(\d+)$")

# Number of numeric features per card:
#   pitch (-1 if none), cost (-1 if none), power, has_power, defense, has_defense,
#   life, has_life, intellect, has_intellect,
#   arcane_damage, has_arcane, activation_cost, has_activation,
#   owner, controller,
#   is_public, tapped, exhausted, played_from_hand, is_token,
#   counter_types(N_COUNTER_TYPES): shared registry with reserved slots,
#   special_states(4): face_up, face_down, is_attacking, is_defending,
#   ward_value, arcane_barrier_value, quell_value, spellvoid_value,
#   ability_flags(18): activated, once_per_turn, action_activation, instant_activation, attack_reaction_activation, non_resource_cost, conditional, 
#                     triggered, on_hit, etb, leaves_arena, start_of_turn, end_of_turn,
#                     static, while_condition, continuous_buff, replacement_effect, prevention_effect
#   targeting_flags(4): requires_target, can_target_hero, can_target_attack, can_target_permanent (Round 9 Gap #2)
#   multi_ability_flags(2): has_multiple_ability_types, ability_type_count (Round 9 Gap #3)
#   efficiency_metrics(2): power_per_cost, defense_per_cost (Round 9 refinement +2 pts)
BASE_NUMERIC_FEATURES = 55  # Everything above except counter slots.
N_NUMERIC = BASE_NUMERIC_FEATURES + N_COUNTER_TYPES


# ---------------------------------------------------------------------------
# Slug vocabulary
# ---------------------------------------------------------------------------

class SlugVocab:
    """Maps card slugs to integer indices.

    Index 0 = MASK  (opponent's hidden card — slug unknown)
    Index 1 = UNK   (slug seen at runtime but not in vocab)
    Index 2+ = actual card slugs
    """

    MASK = 0
    UNK  = 1

    def __init__(self):
        self._slug_to_idx: dict[str, int] = {}
        self._idx_to_slug: list[str] = ["<MASK>", "<UNK>"]

    @property
    def size(self) -> int:
        return len(self._idx_to_slug)

    def add(self, slug: str) -> int:
        if slug not in self._slug_to_idx:
            idx = len(self._idx_to_slug)
            self._slug_to_idx[slug] = idx
            self._idx_to_slug.append(slug)
        return self._slug_to_idx[slug]

    def get(self, slug: str) -> int:
        return self._slug_to_idx.get(slug, self.UNK)

    @classmethod
    def from_card_db(cls, card_db) -> "SlugVocab":
        """Build vocab from a loaded CardDB (requires slug_index.json)."""
        vocab = cls()
        for slug in card_db._by_slug:
            vocab.add(slug)
        return vocab

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._idx_to_slug, f)

    @classmethod
    def load(cls, path: str) -> "SlugVocab":
        vocab = cls()
        with open(path, encoding="utf-8") as f:
            slugs = json.load(f)
        for slug in slugs[2:]:  # skip MASK and UNK
            vocab.add(slug)
        return vocab


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

def card_to_features(
    card: Card,
    vocab: SlugVocab,
    zone_override: Optional[str] = None,
    masked: bool = False,
    player_counters: Optional[dict] = None,  # NEW: for looking up counters
) -> dict[str, torch.Tensor]:
    """Convert a single Card to raw feature tensors (unbatched, on CPU).

    Args:
        card:          The card to embed.
        vocab:         Slug vocabulary for index lookup.
        zone_override: Use this zone string instead of card.zone (useful when
                       the card hasn't been moved yet but context is known).
        masked:        If True, emit a zero-identity token (opponent's hidden card).
                       Zone info is still encoded so the transformer knows a card exists.
        player_counters: Dict of counters from Player.counters (for counter lookup)
    """
    zone_str = (zone_override or card.zone or "").lower()
    zone_idx = _ZONE_IDX.get(zone_str, 0)

    if masked:
        # Masked cards (opponent's hidden cards) use:
        # - Sentinel -1.0 for pitch/cost (unknown, not 0)
        # - Zero for all other numeric features
        masked_numeric = torch.zeros(N_NUMERIC, dtype=torch.float32)
        masked_numeric[0] = -1.0  # pitch unknown
        masked_numeric[1] = -1.0  # cost unknown
        
        return {
            "slug_idx":     torch.tensor(SlugVocab.MASK, dtype=torch.long),
            "color_idx":    torch.tensor(0, dtype=torch.long),
            "zone_idx":     torch.tensor(zone_idx, dtype=torch.long),
            "numeric":      masked_numeric,
            "types":        torch.zeros(N_TYPES, dtype=torch.float32),
            "subtypes":     torch.zeros(N_SUBTYPES, dtype=torch.float32),
            "supertypes":   torch.zeros(N_SUPERTYPES, dtype=torch.float32),
            "keywords":     torch.zeros(N_KEYWORDS, dtype=torch.float32),
        }

    slug_idx  = vocab.get(card.slug)
    color_idx = _COLOR_IDX.get(card.color or "none", 0)
    
    # Calculate counter types on this card (CR 1.15.1, 1.15.2a).
    # Player snapshots are authoritative when available, but missing counter types
    # are backfilled from card-local state for sparse snapshots.
    counter_types_map = {counter_type: 0.0 for counter_type in COUNTER_TYPES}
    has_player_counter_snapshot = False
    snapshot_buckets: set[str] = set()

    card_owner = card.owner if isinstance(card.owner, int) else None
    card_controller = card.controller if isinstance(card.controller, int) else card_owner

    if player_counters and card.zone:
        for counter_key, count in player_counters.items():
            if not isinstance(counter_key, tuple):
                continue

            key_pid = None
            if len(counter_key) == 3:
                c_slug, c_zone, c_type = counter_key
            elif len(counter_key) == 4:
                key_pid, c_slug, c_zone, c_type = counter_key
            else:
                continue

            if c_slug == card.slug and c_zone == card.zone:
                if key_pid is not None and key_pid not in (card_owner, card_controller):
                    continue
                has_player_counter_snapshot = True
                bucket = c_type if c_type in counter_types_map else COUNTER_OOV_TYPE
                counter_types_map[bucket] += float(count)
                snapshot_buckets.add(bucket)

    # Preserve strict precedence for overlapping types but backfill missing types.
    for c_type, count in card.counters.items():
        bucket = c_type if c_type in counter_types_map else COUNTER_OOV_TYPE
        if has_player_counter_snapshot and bucket in snapshot_buckets:
            continue
        counter_types_map[bucket] += float(count)
    
    # Special card states (CR 7.0.4, 7.0.5, 8.5.24, 9.1.3)
    # face_up: distinct from is_public (CR 3.0.3c, 4.4.3b)
    face_up = card.is_public and (card.zone in ["arsenal", "banished", "deck"])
    # face_down: card is private/hidden (CR 8.5.24 - face-down = private, face-up = public)
    # Controller can look at face-down cards they own (CR 3.0.3a), but opponent cannot
    # Used for card effects that care about face-down status AND for masking opponent cards
    face_down = getattr(card, 'face_down', False)
    # is_attacking: card is on combat chain as attacker (CR 7.0.4)
    is_attacking = (card.zone == "combat chain" or card.zone == "weapon") and hasattr(card, '_is_attacking')
    # is_defending: card designated as defending (CR 7.0.5)
    is_defending = hasattr(card, '_is_defending') and card._is_defending
    
    # Extract keyword numeric values
    ward_value = card.get_keyword_value("Ward") or 0
    arcane_barrier_value = card.get_keyword_value("Arcane Barrier") or 0
    quell_value = card.get_keyword_value("Quell") or 0
    spellvoid_value = card.get_keyword_value("Spellvoid") or 0

    counter_features = [normalize_counter(counter_type, counter_types_map[counter_type]) for counter_type in COUNTER_TYPES]

    numeric_values = [
        (card.pitch / _NORM["pitch"]) if card.pitch is not None else -1.0,   # -1 = no pitch
        (card.cost / _NORM["cost"]) if card.cost is not None else -1.0,      # -1 = no cost
        (card.power   or 0) / _NORM["power"],
        float(card.power   is not None),   # has_power flag
        (card.defense or 0) / _NORM["defense"],
        float(card.defense is not None),   # has_defense flag
        (card.life or 0) / _NORM["life"],
        float(card.life is not None),      # has_life flag
        (card.intellect or 0) / _NORM["intellect"],
        float(card.intellect is not None), # has_intellect flag
        (card.arcane or 0) / _NORM["arcane"],
        float(card.arcane is not None),  # has_arcane flag
        (card.activation_cost or 0) / _NORM["activation"],
        float(card.activation_cost is not None),  # has_activation flag
        float(card.owner) / 2.0,           # owner (0-2, normalized)
        float(card.controller or 0) / 2.0,  # controller (default to owner)
        float(card.is_public),
        float(card.tapped),
        float(card.exhausted),
        -1.0 if card.prev_zone == "unknown" else float(card.prev_zone == "hand"),  # played from hand (-1=unknown)
        float(card.category == "token"),   # is token
        # Special states (4): CR 7.0.4, 7.0.5, 8.5.24, 9.1.3
        float(face_up),                   # face-up (distinct from is_public)
        float(face_down),                 # face-down = private (CR 8.5.24)
        float(is_attacking),              # attacking state
        float(is_defending),              # defending state
        # Keyword values (4)
        ward_value / 3.0,                 # Ward value (normalized, max ~10)
        arcane_barrier_value / 2.0,        # Arcane Barrier value (max ~5)
        quell_value / 1.0,                 # Quell value
        spellvoid_value / 1.0,             # Spellvoid value
        # Ability structure flags (18): CR 5.2, 5.4, 6.2.3 - Gap #1 fix (+20 points)
        float(card.has_activated_ability),
        float(card.has_per_turn_limit),
        float(card.has_action_activation),
        float(card.has_instant_activation),
        float(card.has_attack_reaction_activation),
        float(card.has_non_resource_activation_cost),
        float(card.has_conditional_activation),
        float(card.has_triggered_ability),
        float(card.has_on_hit_trigger),
        float(card.has_etb_trigger),
        float(card.has_leaves_arena_trigger),
        float(card.has_start_of_turn_trigger),
        float(card.has_end_of_turn_trigger),
        float(card.has_static_ability),
        float(card.has_while_condition),
        float(card.has_continuous_buff),
        float(card.has_replacement_effect),
        float(card.has_prevention_effect),
        # Targeting requirements (4): CR 1.4 - Gap #2 fix (+5 points)
        float(card.requires_target),
        float(card.can_target_hero),
        float(card.can_target_attack),
        float(card.can_target_permanent),
        # Multi-ability decomposition (2): Gap #3 fix (+3 points)
        float(card.has_multiple_ability_types),
        card.ability_type_count / 3.0,  # Normalized: 0-3 ability types
        # Cost efficiency metrics (2): Refinement (+2 points)
        (card.power if card.power is not None else 0.0) / max((card.cost if card.cost is not None else 0) + 1, 1),
        (card.defense if card.defense is not None else 0.0) / max((card.cost if card.cost is not None else 0) + 1, 1),
    ]
    numeric_values = numeric_values[:21] + counter_features + numeric_values[21:]
    numeric = torch.tensor(numeric_values, dtype=torch.float32)
    if numeric.numel() != N_NUMERIC:
        raise RuntimeError(f"card_to_features produced {numeric.numel()} numeric dims, expected {N_NUMERIC}")

    types_vec = torch.zeros(N_TYPES, dtype=torch.float32)
    for t in (card.types or []):
        if t in _TYPE_IDX:
            types_vec[_TYPE_IDX[t]] = 1.0
    
    subtypes_vec = torch.zeros(N_SUBTYPES, dtype=torch.float32)
    for st in (card.subtypes or []):
        if st in _SUBTYPE_IDX:
            subtypes_vec[_SUBTYPE_IDX[st]] = 1.0
    
    supertypes_vec = torch.zeros(N_SUPERTYPES, dtype=torch.float32)
    # Card model rework (aa9addf): classes/talents now live in card.classes.
    for st in (card.classes or []):
        if st in _SUPERTYPE_IDX:
            supertypes_vec[_SUPERTYPE_IDX[st]] = 1.0

    # Parse keywords into a weighted bag-of-keywords vector.
    # Parameterized keywords carry normalized values; unknown keywords go to OOV bucket.
    kw_vec = torch.zeros(N_KEYWORDS, dtype=torch.float32)
    for raw_keyword in (card.keywords or []):
        keyword_text = str(raw_keyword or "").strip()
        if not keyword_text:
            continue

        match = _KW_WITH_VALUE_RE.match(keyword_text)
        if match:
            base_kw, value = match.groups()
            base_kw = base_kw.strip()
            value_float = float(value)
            norm = PARAMETERIZED_KEYWORD_NORMALIZERS.get(base_kw, 1.0)
            normalized_value = value_float / norm if norm > 0 else value_float
            kw_idx = _KW_IDX.get(base_kw.lower(), _KW_OOV_IDX)
            if kw_idx == _KW_OOV_IDX:
                kw_vec[kw_idx] += 1.0
            else:
                kw_vec[kw_idx] += normalized_value
        else:
            kw_idx = _KW_IDX.get(keyword_text.lower(), _KW_OOV_IDX)
            if kw_idx == _KW_OOV_IDX:
                kw_vec[kw_idx] += 1.0
            else:
                kw_vec[kw_idx] += 1.0

    return {
        "slug_idx":     torch.tensor(slug_idx,  dtype=torch.long),
        "color_idx":    torch.tensor(color_idx, dtype=torch.long),
        "zone_idx":     torch.tensor(zone_idx,  dtype=torch.long),
        "numeric":      numeric,
        "types":        types_vec,
        "subtypes":     subtypes_vec,
        "supertypes":   supertypes_vec,
        "keywords":     kw_vec,
    }


def batch_cards_to_features(
    cards: list[Card],
    vocab: SlugVocab,
    masked_indices: Optional[set] = None,
    zone_overrides: Optional[dict[int, str]] = None,
    player_counters: Optional[dict] = None,  # NEW: for counter lookup
) -> dict[str, torch.Tensor]:
    """Stack a list of cards into batched feature tensors.

    Args:
        cards:           List of Card objects (may include placeholder Cards for masked slots).
        vocab:           Slug vocabulary.
        masked_indices:  Set of list positions whose identity should be masked.
        zone_overrides:  Dict of {position: zone_string} for zone override per card.
        player_counters: Dict of counters from Player.counters (for counter lookup)
    """
    if masked_indices is None:
        masked_indices = set()
    if zone_overrides is None:
        zone_overrides = {}

    feats = [
        card_to_features(
            c,
            vocab,
            zone_override=zone_overrides.get(i),
            masked=(i in masked_indices),
            player_counters=player_counters,
        )
        for i, c in enumerate(cards)
    ]
    return {k: torch.stack([f[k] for f in feats]) for k in feats[0]}


# ---------------------------------------------------------------------------
# CardEmbedder module
# ---------------------------------------------------------------------------

class CardEmbedder(nn.Module):
    """Projects card feature tensors into a d_model embedding vector.

    Embedding breakdown (default d_model=128):
        slug        → D_SLUG      = 64   (card identity)
        color       → D_COLOR     = 8    (pitch color)
        zone        → D_ZONE      = 16   (current zone)
        numeric     → D_NUMERIC   = 88   (projected numeric feature bundle)
        types       → D_TYPES     = 16   (multi-hot card types)
        subtypes    → D_SUBTYPES  = 16   (multi-hot subtypes)
        supertypes  → D_SUPERTYPES = 16  (multi-hot classes/talents)
        keywords    → D_KW        = 16   (pooled keyword embeddings)
        ────────────────────────────────
        concat      →             = 232
        linear      → d_model
        LayerNorm   → d_model
    """

    D_SLUG      = 64
    D_COLOR     = 8
    D_ZONE      = 16
    D_NUMERIC   = 88
    D_TYPES     = 16
    D_SUBTYPES  = 16
    D_SUPERTYPES = 16
    D_KW        = 16
    D_IN        = D_SLUG + D_COLOR + D_ZONE + D_NUMERIC + D_TYPES + D_SUBTYPES + D_SUPERTYPES + D_KW  # = 240

    def __init__(self, slug_vocab_size: int, d_model: int = 128, keyword_pooling: str = "mean"):
        super().__init__()
        if keyword_pooling not in {"mean", "sum"}:
            raise ValueError("keyword_pooling must be 'mean' or 'sum'")

        self.d_model = d_model
        self.keyword_pooling = keyword_pooling

        self.slug_embed     = nn.Embedding(slug_vocab_size, self.D_SLUG, padding_idx=SlugVocab.MASK)
        self.color_embed    = nn.Embedding(N_COLORS,        self.D_COLOR,  padding_idx=0)
        self.zone_embed     = nn.Embedding(N_ZONES,         self.D_ZONE,   padding_idx=0)
        self.numeric_proj   = nn.Linear(N_NUMERIC,    self.D_NUMERIC)
        self.type_proj      = nn.Linear(N_TYPES,      self.D_TYPES)
        self.subtype_proj   = nn.Linear(N_SUBTYPES,   self.D_SUBTYPES)
        self.supertype_proj = nn.Linear(N_SUPERTYPES, self.D_SUPERTYPES)
        self.keyword_embed  = nn.Embedding(N_KEYWORDS, self.D_KW)
        self.out_proj       = nn.Linear(self.D_IN,  d_model)
        self.norm           = nn.LayerNorm(d_model)

    def _pool_keyword_embeddings(self, keyword_weights: torch.Tensor) -> torch.Tensor:
        """Pool weighted keyword embeddings to a fixed-size representation.

        Args:
            keyword_weights: (B, N_KEYWORDS) weighted bag-of-keywords tensor.

        Returns:
            (B, D_KW) pooled embedding tensor.
        """
        if keyword_weights.dim() == 1:
            keyword_weights = keyword_weights.unsqueeze(0)
        if keyword_weights.size(-1) != N_KEYWORDS:
            raise ValueError(f"Expected keyword vector width {N_KEYWORDS}, got {keyword_weights.size(-1)}")

        keyword_weights = keyword_weights.float()
        token_ids = torch.arange(N_KEYWORDS, device=keyword_weights.device)
        token_embs = self.keyword_embed(token_ids)  # (N_KEYWORDS, D_KW)
        pooled = torch.matmul(keyword_weights, token_embs)

        if self.keyword_pooling == "mean":
            denom = keyword_weights.abs().sum(dim=1, keepdim=True).clamp_min(1.0)
            pooled = pooled / denom
        return pooled

    def get_schema_metadata(self) -> dict[str, object]:
        """Return schema metadata bundle for checkpoint compatibility checks."""
        return build_schema_metadata(
            embedder="card_embedder",
            d_model=self.d_model,
            extra={
                "numeric_feature_dim": N_NUMERIC,
                "keyword_pooling": self.keyword_pooling,
                "keyword_embedding_dim": self.D_KW,
                "output_dim": self.d_model,
            },
        )

    def validate_schema(
        self,
        schema_metadata: Optional[dict[str, object]],
        strict: bool = True,
    ) -> tuple[bool, list[str]]:
        """Validate an incoming schema payload against this embedder's schema."""
        if schema_metadata is None:
            return False, ["schema metadata is missing"]
        return validate_schema_metadata(self.get_schema_metadata(), schema_metadata, strict=strict)

    def forward(self, features: dict[str, torch.Tensor]) -> torch.Tensor:
        """Embed a batch of cards.

        Args:
            features: dict from batch_cards_to_features(), each tensor is (B, ...).

        Returns:
            (B, d_model) float tensor.
        """
        slug_emb      = self.slug_embed(features["slug_idx"])      # (B, D_SLUG)
        color_emb     = self.color_embed(features["color_idx"])    # (B, D_COLOR)
        zone_emb      = self.zone_embed(features["zone_idx"])      # (B, D_ZONE)
        num_emb       = self.numeric_proj(features["numeric"])     # (B, D_NUMERIC)
        type_emb      = self.type_proj(features["types"])          # (B, D_TYPES)
        subtype_emb   = self.subtype_proj(features["subtypes"])    # (B, D_SUBTYPES)
        supertype_emb = self.supertype_proj(features["supertypes"]) # (B, D_SUPERTYPES)
        kw_emb        = self._pool_keyword_embeddings(features["keywords"])  # (B, D_KW)

        x = torch.cat([slug_emb, color_emb, zone_emb, num_emb, type_emb, 
                       subtype_emb, supertype_emb, kw_emb], dim=-1)
        return self.norm(self.out_proj(x))                         # (B, d_model)
