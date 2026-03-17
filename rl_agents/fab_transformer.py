"""Encoding-only transformer for Talishar FAB game states.

Converts raw Talishar JSON state dicts into learned d_model representations via:
1. Card tokenizer: extracts card slugs from each zone in the JSON state
2. Card embedder: slug_id → learned embedding + static attribute projection
3. Segment/position embeddings per zone
4. TransformerEncoder (encoding-only, self-attention)

Also provides an ActionEncoder for embedding Talishar action dicts.

Usage (preprocessing):
    vocab, attrs = build_card_vocab_and_attrs("card_data/slug_index.json")
    state_feats = featurize_state(state_json, vocab)
    action_feats = featurize_action(action_json, vocab)

Usage (training):
    encoder = FABTransformerEncoder(config, attr_table=attrs)
    state_emb = encoder(state_feats)  # (batch, d_model)
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import numpy as np
import torch
import torch.nn as nn


# ── Constants ─────────────────────────────────────────────────────────

# Zone IDs for card tokens
ZONE_PAD = 0
ZONE_HAND = 1
ZONE_EQUIP = 2
ZONE_OPP_EQUIP = 3
ZONE_ARSENAL = 4
ZONE_OPP_ARSENAL = 5
ZONE_COMBAT_ATK = 6
ZONE_COMBAT_DEF = 7
ZONE_AURA = 8
ZONE_OPP_AURA = 9
NUM_ZONES = 10

# Segment IDs for transformer position encoding
SEG_CLS = 0
SEG_META = 1
SEG_HAND = 2
SEG_BOARD = 3
SEG_OPP_BOARD = 4
SEG_COMBAT = 5
NUM_SEGMENTS = 6

# Card types (shared with engine vocabulary)
CARD_TYPE_LIST = [
    "Action", "Attack", "Defense Reaction", "Attack Reaction",
    "Equipment", "Weapon", "Aura", "Ally", "Token", "Hero", "Item", "Instant",
]
CARD_TYPE_TO_IDX = {t: i for i, t in enumerate(CARD_TYPE_LIST)}
NUM_CARD_TYPES = len(CARD_TYPE_LIST)

# Card attribute dimensions: pitch, cost, power, defense, color + type flags
CARD_ATTR_DIM = 5 + NUM_CARD_TYPES  # 17

# Max cards per zone in tokenized state
MAX_HAND = 12
MAX_EQUIP = 10
MAX_OPP_EQUIP = 10
MAX_ARSENAL = 2
MAX_OPP_ARSENAL = 2
MAX_COMBAT_ATK = 2
MAX_COMBAT_DEF = 6
MAX_COMBAT = MAX_COMBAT_ATK + MAX_COMBAT_DEF  # 8
MAX_AURA = 6
MAX_OPP_AURA = 6
MAX_TOTAL_CARDS = (MAX_HAND + MAX_EQUIP + MAX_OPP_EQUIP + MAX_ARSENAL
                   + MAX_OPP_ARSENAL + MAX_COMBAT + MAX_AURA + MAX_OPP_AURA)  # 56

# Meta feature dimension (global game state scalars)
META_DIM = 28

# Color mapping for attribute table
_COLOR_MAP = {"": 0, "none": 0, "red": 1, "yellow": 2, "blue": 3,
              "Red": 1, "Yellow": 2, "Blue": 3}

# Turn phase vocabulary
TURN_PHASES = ["M", "B", "D", "A", "ARS", "P", "CHOOSEHAND", "CHOOSEHANDCANCEL"]
TURN_PHASE_TO_IDX = {p: i + 1 for i, p in enumerate(TURN_PHASES)}  # 0 = unknown
NUM_TURN_PHASES = len(TURN_PHASES) + 1

# Decision type vocabulary
DECISION_TYPES = [
    "pass", "pitch", "choose_effect", "defend_block", "defense_reaction",
    "attack_reaction", "play_card", "activate_equipment", "arsenal", "button", "other",
]
DECISION_TYPE_TO_IDX = {d: i + 1 for i, d in enumerate(DECISION_TYPES)}  # 0 = unknown
NUM_DECISION_TYPES = len(DECISION_TYPES) + 1

# Action mode vocabulary (Talishar action codes)
ACTION_MODE_LIST = [0, 5, 16, 21, 25, 27, 37, 38, 99]
ACTION_MODE_TO_IDX = {m: i + 1 for i, m in enumerate(ACTION_MODE_LIST)}  # 0 = unknown
NUM_ACTION_MODES = len(ACTION_MODE_LIST) + 1


# ── Vocabulary & Attribute Table ──────────────────────────────────────


def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None or val == "" or val == "*":
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def build_card_vocab_and_attrs(slug_index_path: str) -> tuple[dict[str, int], np.ndarray]:
    """Build slug→id vocab and static attribute lookup table from slug_index.json.

    Returns:
        vocab: dict mapping slug → int ID (0=PAD, 1=UNK, 2+=cards)
        attrs: ndarray (vocab_size, CARD_ATTR_DIM) with normalized card attributes
    """
    with open(slug_index_path, encoding="utf-8") as f:
        data = json.load(f)

    by_slug = data.get("by_slug", data)

    vocab: dict[str, int] = {"<PAD>": 0, "<UNK>": 1}
    attrs_list: list[list[float]] = [
        [0.0] * CARD_ATTR_DIM,  # PAD
        [0.0] * CARD_ATTR_DIM,  # UNK
    ]

    for slug, info in by_slug.items():
        vocab[slug] = len(vocab)

        pitch = _safe_float(info.get("pitch"), 0) / 3.0
        cost = _safe_float(info.get("cost"), 0) / 3.0
        power = _safe_float(info.get("power"), 0) / 10.0
        defense = _safe_float(info.get("defense"), 0) / 4.0
        color = _COLOR_MAP.get(info.get("color", ""), 0) / 3.0

        type_flags = [0.0] * NUM_CARD_TYPES
        for t in info.get("types", []):
            idx = CARD_TYPE_TO_IDX.get(t)
            if idx is not None:
                type_flags[idx] = 1.0

        attrs_list.append([pitch, cost, power, defense, color] + type_flags)

    return vocab, np.array(attrs_list, dtype=np.float32)


# ── Featurization (JSON → numpy arrays for HDF5) ─────────────────────


def _extract_card_ids(
    card_dicts: list[dict] | None,
    vocab: dict[str, int],
    max_cards: int,
) -> list[int]:
    """Extract slug vocab IDs from a list of Talishar card dicts."""
    if not card_dicts or not isinstance(card_dicts, list):
        return [0] * max_cards
    ids = []
    for cd in card_dicts[:max_cards]:
        slug = cd.get("cardNumber", "") if isinstance(cd, dict) else ""
        ids.append(vocab.get(slug, 1))  # 1 = UNK
    # Pad
    ids.extend([0] * (max_cards - len(ids)))
    return ids


def featurize_state(state: dict, vocab: dict[str, int]) -> dict[str, np.ndarray]:
    """Convert a Talishar JSON state dict to preprocessed numpy arrays.

    Returns dict with:
        card_ids:  (MAX_TOTAL_CARDS,) int16
        card_zones: (MAX_TOTAL_CARDS,) int8
        card_mask: (MAX_TOTAL_CARDS,) bool
        meta: (META_DIM,) float32
        turn_phase_id: int8
        decision_type_id: int8  (always 0 here — set by caller)
    """
    card_ids: list[int] = []
    card_zones: list[int] = []

    def _add_zone(dicts: list[dict] | None, zone_id: int, max_n: int):
        ids = _extract_card_ids(dicts, vocab, max_n)
        card_ids.extend(ids)
        card_zones.extend([zone_id if ids[i] != 0 else ZONE_PAD for i in range(max_n)])

    _add_zone(state.get("playerHand"), ZONE_HAND, MAX_HAND)
    _add_zone(state.get("playerEquipment"), ZONE_EQUIP, MAX_EQUIP)
    _add_zone(state.get("opponentEquipment"), ZONE_OPP_EQUIP, MAX_OPP_EQUIP)
    _add_zone(state.get("playerArse"), ZONE_ARSENAL, MAX_ARSENAL)
    _add_zone(state.get("opponentArse"), ZONE_OPP_ARSENAL, MAX_OPP_ARSENAL)

    # Combat chain cards
    acl = state.get("activeChainLink")
    combat_atk_cards = []
    combat_def_cards = []
    if isinstance(acl, dict):
        atk = acl.get("attackingCard")
        if isinstance(atk, dict):
            combat_atk_cards.append(atk)
        reactions = acl.get("reactions")
        if isinstance(reactions, list):
            combat_def_cards = reactions

    _add_zone(combat_atk_cards, ZONE_COMBAT_ATK, MAX_COMBAT_ATK)
    _add_zone(combat_def_cards, ZONE_COMBAT_DEF, MAX_COMBAT_DEF)

    _add_zone(state.get("playerAuras"), ZONE_AURA, MAX_AURA)
    _add_zone(state.get("opponentAuras"), ZONE_OPP_AURA, MAX_OPP_AURA)

    card_mask = [cid != 0 for cid in card_ids]

    # Meta features — extracted from the JSON state directly
    def _si(key: str, default: int = 0) -> int:
        v = state.get(key)
        if isinstance(v, (int, float)):
            return int(v)
        return default

    def _zone_len(key: str) -> int:
        v = state.get(key)
        return len(v) if isinstance(v, list) else 0

    p_hp = _si("playerHealth", 20)
    o_hp = _si("opponentHealth", 20)
    acl_dict = acl if isinstance(acl, dict) else {}

    meta = np.array([
        p_hp / 40.0,
        o_hp / 40.0,
        _zone_len("playerHand") / 12.0,
        _zone_len("opponentHand") / 12.0,
        _zone_len("playerDeck") / 80.0,
        _zone_len("opponentDeck") / 80.0,
        _si("playerAP", 0) / 5.0,
        _safe_float(state.get("playerPitchCount"), 0) / 10.0,
        float(bool(acl)),
        _safe_float(acl_dict.get("totalPower"), 0) / 20.0,
        _safe_float(acl_dict.get("totalDefense"), 0) / 20.0,
        0.0,  # is_turn_player — set by caller from denormalized col
        _zone_len("playerDiscard") / 40.0,
        _zone_len("opponentDiscard") / 40.0,
        _zone_len("playerBanish") / 40.0,
        _zone_len("opponentBanish") / 40.0,
        _zone_len("playerPitch") / 20.0,
        _zone_len("opponentPitch") / 20.0,
        _zone_len("playerEquipment") / 10.0,
        _zone_len("opponentEquipment") / 10.0,
        float(bool(state.get("playerArse"))),
        float(bool(state.get("opponentArse"))),
        len(state.get("combatChainLinks", [])) / 10.0,
        float(bool(acl_dict.get("goAgain"))),
        0.0,  # num_actions — set by caller
        0.0,  # hp_delta — set by caller
        0.0,  # opp_hp_delta — set by caller
        0.0,  # game_progress — set by caller
    ], dtype=np.float32)

    # Turn phase
    tp = state.get("turnPhase")
    if isinstance(tp, dict):
        tp = tp.get("turnPhase", "")
    tp_str = str(tp or "").upper()
    turn_phase_id = TURN_PHASE_TO_IDX.get(tp_str, 0)

    return {
        "card_ids": np.array(card_ids, dtype=np.int16),
        "card_zones": np.array(card_zones, dtype=np.int8),
        "card_mask": np.array(card_mask, dtype=bool),
        "meta": meta,
        "turn_phase_id": np.int8(turn_phase_id),
        "decision_type_id": np.int8(0),
    }


def featurize_action(action: dict, vocab: dict[str, int]) -> dict[str, np.ndarray]:
    """Convert a Talishar action JSON dict to preprocessed numpy arrays.

    Returns dict with:
        card_id: int16
        mode_id: int8
    """
    slug = action.get("cardNumber", "") if isinstance(action, dict) else ""
    card_id = vocab.get(slug, 1) if slug else 0

    mode = action.get("mode", 0) if isinstance(action, dict) else 0
    mode_id = ACTION_MODE_TO_IDX.get(mode, 0)

    return {
        "card_id": np.int16(card_id),
        "mode_id": np.int8(mode_id),
    }


# ── Transformer Encoder ──────────────────────────────────────────────


@dataclass
class FABTransformerConfig:
    d_model: int = 128
    num_heads: int = 4
    num_layers: int = 3
    ff_dim: int = 256
    dropout: float = 0.1
    slug_vocab_size: int = 4563
    # Dimensions for sub-embeddings
    d_slug: int = 64
    d_zone: int = 16
    d_attr: int = 48       # projected from CARD_ATTR_DIM


class FABTransformerEncoder(nn.Module):
    """Encoding-only transformer that produces a d_model state embedding.

    Input: preprocessed state features (card_ids, card_zones, card_mask, meta,
           turn_phase_id).
    Output: (batch, d_model) state embedding from the CLS token.
    """

    def __init__(self, config: FABTransformerConfig, attr_table: torch.Tensor | None = None):
        super().__init__()
        self.config = config

        # Card token embeddings
        self.slug_embed = nn.Embedding(
            config.slug_vocab_size, config.d_slug, padding_idx=0,
        )
        self.zone_embed = nn.Embedding(NUM_ZONES, config.d_zone, padding_idx=0)
        self.attr_proj = nn.Linear(CARD_ATTR_DIM, config.d_attr)

        # Static attribute lookup (frozen, not trained)
        if attr_table is not None:
            self.register_buffer("attr_table", attr_table)
        else:
            self.register_buffer(
                "attr_table",
                torch.zeros(config.slug_vocab_size, CARD_ATTR_DIM),
            )

        # Project card token components to d_model
        card_in_dim = config.d_slug + config.d_zone + config.d_attr
        self.card_proj = nn.Linear(card_in_dim, config.d_model)

        # Meta token
        self.meta_proj = nn.Sequential(
            nn.Linear(META_DIM, config.d_model),
            nn.GELU(),
            nn.Linear(config.d_model, config.d_model),
        )

        # Turn phase & decision type embeddings (added to meta)
        self.turn_phase_embed = nn.Embedding(NUM_TURN_PHASES, config.d_model)
        self.decision_type_embed = nn.Embedding(NUM_DECISION_TYPES, config.d_model)

        # CLS token
        self.cls_token = nn.Parameter(torch.randn(config.d_model) * 0.02)

        # Segment & position embeddings
        self.segment_embed = nn.Embedding(NUM_SEGMENTS, config.d_model)
        max_seq = 2 + MAX_TOTAL_CARDS  # CLS + META + cards
        self.position_embed = nn.Embedding(max_seq, config.d_model)

        # Transformer encoder
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=config.d_model,
            nhead=config.num_heads,
            dim_feedforward=config.ff_dim,
            dropout=config.dropout,
            batch_first=True,
            norm_first=True,
            activation="gelu",
        )
        self.encoder = nn.TransformerEncoder(
            encoder_layer, num_layers=config.num_layers,
        )
        self.final_norm = nn.LayerNorm(config.d_model)

        # Static zone→segment mapping (registered as buffer for device tracking)
        self.register_buffer("_zone_to_seg", torch.tensor(
            [SEG_META,       # ZONE_PAD → META (will be masked)
             SEG_HAND,       # ZONE_HAND
             SEG_BOARD,      # ZONE_EQUIP
             SEG_OPP_BOARD,  # ZONE_OPP_EQUIP
             SEG_BOARD,      # ZONE_ARSENAL
             SEG_OPP_BOARD,  # ZONE_OPP_ARSENAL
             SEG_COMBAT,     # ZONE_COMBAT_ATK
             SEG_COMBAT,     # ZONE_COMBAT_DEF
             SEG_BOARD,      # ZONE_AURA
             SEG_OPP_BOARD], # ZONE_OPP_AURA
            dtype=torch.long,
        ))

    def forward(
        self,
        card_ids: torch.Tensor,      # (B, MAX_TOTAL_CARDS) int/long
        card_zones: torch.Tensor,     # (B, MAX_TOTAL_CARDS) int/long
        card_mask: torch.Tensor,      # (B, MAX_TOTAL_CARDS) bool — True=real
        meta: torch.Tensor,           # (B, META_DIM) float
        turn_phase_id: torch.Tensor,  # (B,) int/long
        decision_type_id: torch.Tensor,  # (B,) int/long
    ) -> torch.Tensor:
        """Encode state features → (B, d_model) state embedding."""
        B = card_ids.size(0)
        device = card_ids.device
        C = MAX_TOTAL_CARDS

        # ── Card tokens ──
        slug_emb = self.slug_embed(card_ids.long())          # (B, C, d_slug)
        zone_emb = self.zone_embed(card_zones.long())        # (B, C, d_zone)
        card_attrs = self.attr_table[card_ids.long()]        # (B, C, CARD_ATTR_DIM)
        attr_emb = self.attr_proj(card_attrs)                # (B, C, d_attr)
        card_tokens = self.card_proj(
            torch.cat([slug_emb, zone_emb, attr_emb], dim=-1)
        )                                                    # (B, C, d_model)

        # ── Meta token ──
        meta_token = self.meta_proj(meta)                    # (B, d_model)
        meta_token = (meta_token
                      + self.turn_phase_embed(turn_phase_id.long())
                      + self.decision_type_embed(decision_type_id.long()))
        meta_token = meta_token.unsqueeze(1)                 # (B, 1, d_model)

        # ── CLS token ──
        cls_token = self.cls_token.unsqueeze(0).unsqueeze(0).expand(B, 1, -1)

        # ── Assemble sequence: [CLS, META, cards...] ──
        tokens = torch.cat([cls_token, meta_token, card_tokens], dim=1)  # (B, 2+C, d_model)
        seq_len = tokens.size(1)

        # Segment IDs: CLS=0, META=1, then zone-based segments for cards
        seg_ids = torch.zeros(B, seq_len, dtype=torch.long, device=device)
        seg_ids[:, 1] = SEG_META
        seg_ids[:, 2:] = self._zone_to_seg.to(device)[card_zones.long()]

        # Position IDs
        pos_ids = torch.arange(seq_len, dtype=torch.long, device=device).unsqueeze(0).expand(B, -1)

        tokens = tokens + self.segment_embed(seg_ids) + self.position_embed(pos_ids)

        # ── Attention mask: mask out padding cards ──
        # True in src_key_padding_mask = position is ignored
        pad_mask = torch.zeros(B, seq_len, dtype=torch.bool, device=device)
        pad_mask[:, 2:] = ~card_mask  # padding cards are masked

        # ── Transformer ──
        encoded = self.encoder(tokens, src_key_padding_mask=pad_mask)
        encoded = self.final_norm(encoded)

        # CLS output
        return encoded[:, 0, :]  # (B, d_model)


class ActionEncoder(nn.Module):
    """Encodes a Talishar action dict into a d_model embedding vector.

    Uses the same slug embedding table as FABTransformerEncoder for card identity,
    plus a learned mode embedding.
    """

    def __init__(self, config: FABTransformerConfig, slug_embed: nn.Embedding | None = None):
        super().__init__()
        self.config = config

        if slug_embed is not None:
            self.slug_embed = slug_embed  # share weights with state encoder
        else:
            self.slug_embed = nn.Embedding(config.slug_vocab_size, config.d_slug, padding_idx=0)

        self.mode_embed = nn.Embedding(NUM_ACTION_MODES, 32)

        self.proj = nn.Sequential(
            nn.Linear(config.d_slug + 32, config.d_model),
            nn.GELU(),
            nn.Linear(config.d_model, config.d_model),
            nn.LayerNorm(config.d_model),
        )

    def forward(
        self,
        card_id: torch.Tensor,   # (B,) int/long
        mode_id: torch.Tensor,   # (B,) int/long
    ) -> torch.Tensor:
        """Returns (B, d_model) action embedding."""
        slug_emb = self.slug_embed(card_id.long())   # (B, d_slug)
        mode_emb = self.mode_embed(mode_id.long())   # (B, 32)
        return self.proj(torch.cat([slug_emb, mode_emb], dim=-1))
