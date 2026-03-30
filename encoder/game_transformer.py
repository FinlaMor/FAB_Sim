"""encoder/game_transformer.py — Transformer-based game state encoder.

Replaces GameStateEmbedder's sum-pooled flat vector with a proper transformer
that lets every card token attend to every other card token before producing a
single CLS-token embedding.

Drop-in replacement signature:
    forward(state: GameState, perspective_player: int) -> torch.Tensor  shape (d_model,)

Architecture:
    1. Build a sequence of card tokens (one per card slot) plus one META token
       and one learnt CLS token.
    2. Each token = slug_emb + zone_segment_emb + position_emb + card_feature_proj
    3. TransformerEncoder (batch_first=True) over the sequence.
    4. Return LayerNorm(CLS output).
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import torch
import torch.nn as nn

from encoder.card_embedder import (
    SlugVocab,
    card_to_features,
    N_NUMERIC,
)
from encoder.feature_schema import (
    STEP_VOCABULARY,
    build_schema_metadata,
    validate_schema_metadata,
)
from engine.state import GameState, Player
from engine.card import Card


# ---------------------------------------------------------------------------
# Zone segment IDs
# ---------------------------------------------------------------------------

OWN_HERO           = 1
OWN_WEAPON         = 2
OWN_EQUIPMENT      = 3
OWN_HAND           = 4
OWN_ARSENAL        = 5
OWN_GRAVEYARD      = 6
OWN_BANISHED       = 7
OWN_PERMANENTS     = 8
OWN_DECK           = 9
OWN_PITCH          = 10
OWN_SOUL           = 11

OPP_HERO           = 12
OPP_WEAPON         = 13
OPP_EQUIPMENT      = 14
OPP_HAND_MASKED    = 15
OPP_ARSENAL_FACEDOWN = 16
OPP_ARSENAL_FACEUP = 17
OPP_GRAVEYARD      = 18
OPP_BANISHED       = 19
OPP_PERMANENTS     = 20
OPP_PITCH_HISTORY  = 21

META               = 22
CLS_SEGMENT        = 23

N_ZONE_SEGMENTS    = 24  # 0 reserved (unused)

# Sentinel slug index for masked/unknown cards (appended beyond vocab)
# We set this to 0 (SlugVocab.MASK) — same as CardEmbedder's padding_idx.
MASK_SLUG_IDX = SlugVocab.MASK


# ---------------------------------------------------------------------------
# Meta feature dimension
# 1 (turn) + len(STEP_VOCABULARY) (step one-hot) + 1 (is_active) +
# 1 (is_priority) + 1 (own_hp) + 1 (opp_hp) + 1 (own_resources) +
# 1 (own_ap) + 1 (in_combat) + 1 (attack_power) + 1 (total_defense)
# ---------------------------------------------------------------------------
_N_META = 1 + len(STEP_VOCABULARY) + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1


# ---------------------------------------------------------------------------
# Per-card numeric feature dim (same as card_embedder.N_NUMERIC)
# ---------------------------------------------------------------------------
_N_CARD_FEATS = N_NUMERIC


def _safe_card_features(
    card: Optional[Card],
    masked: bool = False,
) -> torch.Tensor:
    """Return a (N_NUMERIC,) numeric feature tensor for one card.

    Uses card_to_features but strips the categorical part — we only want the
    numeric vector here; the categorical embeddings (slug, color, zone) are
    handled separately via the segment / slug embeddings.
    """
    if card is None or masked:
        t = torch.zeros(_N_CARD_FEATS, dtype=torch.float32)
        if masked:
            t[0] = -1.0  # pitch unknown
            t[1] = -1.0  # cost unknown
        return t
    feats = card_to_features(card, _DUMMY_VOCAB, masked=False)
    return feats["numeric"]


# A global dummy vocab used only for numeric feature extraction from cards.
# The slug index from this vocab is NOT used — we look up slugs ourselves.
_DUMMY_VOCAB: SlugVocab = SlugVocab()  # all slugs → UNK, which is fine for numeric feats


# ---------------------------------------------------------------------------
# Sequence truncation limits (number of tokens per zone, in priority order)
# ---------------------------------------------------------------------------
_LIMITS = {
    "own_graveyard":    30,
    "own_deck":         20,
    "opp_graveyard":    20,
    "own_permanents":   10,
    "opp_permanents":   10,
    "opp_pitch_history": 20,
    "own_banished":     15,
    "opp_banished":     15,
}

MAX_TURNS_FOR_TEMPORAL = 50

# ---------------------------------------------------------------------------
# Storage format constants (end-to-end training)
# ---------------------------------------------------------------------------

# Maximum tokens stored per state in the packed format (truncated for DB efficiency).
# Must be <= max_seq_len used at training time.
MAX_STORAGE_SEQ_LEN = 128

# Total float32 values in a packed state array:
#   2 scalars (seq_len, hero_pos) + _N_META meta features +
#   3 * MAX_STORAGE_SEQ_LEN (slug, zone, pos arrays for each token)
# Computed lazily below after _N_META is defined; accessed via the property.
# Exposed as a module-level function so callers can compute it without an instance.
def _state_packed_size() -> int:
    return 2 + _N_META + 3 * MAX_STORAGE_SEQ_LEN


# ---------------------------------------------------------------------------
# GameTransformerEncoder
# ---------------------------------------------------------------------------

class GameTransformerEncoder(nn.Module):
    """Transformer-based game state encoder.

    Accepts a GameState and a perspective player ID; produces a (d_model,)
    embedding vector (CLS token after n_layers of self-attention).

    Parameters
    ----------
    slug_vocab_size : int
        Size of the slug vocabulary (from SlugVocab).
    d_model : int
        Hidden dimension for the transformer. Default 256.
    n_heads : int
        Number of attention heads. Default 8.
    n_layers : int
        Number of transformer encoder layers. Default 4.
    dim_feedforward : int
        FFN inner dimension per layer. Default 1024 (= 4 * d_model).
    dropout : float
        Dropout rate. Default 0.1.
    max_seq_len : int
        Maximum token sequence length (tokens beyond this are dropped).
        Default 256.
    """

    def __init__(
        self,
        slug_vocab_size: int,
        d_model: int = 256,
        n_heads: int = 8,
        n_layers: int = 4,
        dim_feedforward: int = 1024,
        dropout: float = 0.1,
        max_seq_len: int = 256,
        hero_head_dim: int = 64,
    ):
        super().__init__()
        self.d_model = d_model
        self.n_heads = n_heads
        self.n_layers = n_layers
        self.dim_feedforward = dim_feedforward
        self.slug_vocab_size = slug_vocab_size
        self.max_seq_len = max_seq_len
        self.hero_head_dim = hero_head_dim

        # --- Token component embeddings ---
        # +1 for MASK_SLUG_IDX sentinel (index 0); vocab indices 0..slug_vocab_size-1
        # but MASK_SLUG_IDX=0 is already in the range, so total = slug_vocab_size
        self.slug_embed = nn.Embedding(slug_vocab_size + 1, d_model, padding_idx=MASK_SLUG_IDX)
        self.zone_segment_embed = nn.Embedding(N_ZONE_SEGMENTS, d_model)
        self.position_embed = nn.Embedding(MAX_TURNS_FOR_TEMPORAL + max_seq_len + 1, d_model)

        # Card numeric features → d_model projection
        self.card_feat_proj = nn.Linear(_N_CARD_FEATS, d_model, bias=True)

        # Meta features → d_model projection
        self.meta_proj = nn.Linear(_N_META, d_model, bias=True)

        # Learned CLS token
        self.cls_token = nn.Parameter(torch.zeros(1, d_model))
        nn.init.trunc_normal_(self.cls_token, std=0.02)

        # Transformer encoder
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=n_heads,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            batch_first=True,
            norm_first=False,
        )
        self.transformer = nn.TransformerEncoder(
            encoder_layer=encoder_layer,
            num_layers=n_layers,
            norm=nn.LayerNorm(d_model),
            enable_nested_tensor=False,  # DML/DirectML doesn't support nested tensors
        )

        # Output layer norm (applied to CLS token)
        self.output_norm = nn.LayerNorm(d_model)

        # Hero head: projects the OWN_HERO token's contextual output into a
        # dedicated hero-specific representation that is concatenated to the CLS
        # output.  This gives the IQL networks a direct, undiluted signal about
        # which hero is playing and how it relates to the current board, beyond
        # what the CLS token alone captures.
        if hero_head_dim > 0:
            self.hero_head_proj = nn.Linear(d_model, hero_head_dim, bias=True)
            self.hero_head_norm = nn.LayerNorm(hero_head_dim)
        else:
            self.hero_head_proj = None
            self.hero_head_norm = None

        # Device anchor — register a buffer so .to(device) propagates
        # We access it via self._dev_anchor.device in forward()
        self.register_buffer("_dev_anchor", torch.zeros(1))

        # card_feats_lookup[slug_idx] = (N_CARD_FEATS,) precomputed numeric features.
        # Populated by set_card_feats_lookup(card_db). Zeros until then.
        self.register_buffer(
            "card_feats_lookup",
            torch.zeros(slug_vocab_size + 1, _N_CARD_FEATS),
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def packed_feature_size(self) -> int:
        """Size of the packed state feature array (float32 values)."""
        return _state_packed_size()

    def set_card_feats_lookup(self, card_db) -> None:
        """Pre-compute numeric card features for every slug in the vocab and cache them.

        Must be called once after prime_dummy_vocab(card_db) before training.
        """
        table = torch.zeros(self.slug_vocab_size + 1, _N_CARD_FEATS)
        for slug in card_db._by_slug:
            idx = _DUMMY_VOCAB.get(slug)
            if idx > 0:
                card = card_db.get(slug)
                if card is not None:
                    feats = _safe_card_features(card, masked=False)
                    table[idx] = feats
        self.card_feats_lookup.copy_(table)

    def get_output_dim(self) -> int:
        """Returns CLS dim + hero head dim."""
        return self.d_model + self.hero_head_dim

    def get_schema_metadata(self) -> dict:
        return build_schema_metadata(
            embedder="game_transformer",
            d_model=self.d_model,
            extra={
                "n_heads": self.n_heads,
                "n_layers": self.n_layers,
                "vocab_size": self.slug_vocab_size,
                "hero_head_dim": self.hero_head_dim,
                "output_dim": self.get_output_dim(),
            },
        )

    def validate_schema(
        self,
        schema_metadata: Optional[dict],
        strict: bool = True,
    ) -> tuple[bool, list[str]]:
        if schema_metadata is None:
            return False, ["schema metadata is missing"]
        return validate_schema_metadata(self.get_schema_metadata(), schema_metadata, strict=strict)

    # ------------------------------------------------------------------
    # forward
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Token collection (shared by forward, tokenize_to_packed, forward_packed_batch)
    # ------------------------------------------------------------------

    def _collect_tokens(
        self,
        state: GameState,
        perspective_player: int,
    ) -> tuple[list[tuple[int, int, int, torch.Tensor]], Optional[int], torch.Tensor]:
        """Collect all card tokens for a game state.

        Returns:
            (tokens, own_hero_token_idx, meta_vec)
            tokens: list of (slug_idx, zone_seg, pos_idx, feat_tensor)
            own_hero_token_idx: index into tokens list of OWN_HERO token, or None
            meta_vec: (_N_META,) float32 meta feature tensor
        """
        me = state.players[perspective_player]
        opp_id = 3 - perspective_player
        opp = state.players[opp_id]

        tokens: list[tuple[int, int, int, torch.Tensor]] = []
        own_hero_token_idx: Optional[int] = None

        def _add(slug_idx: int, zone_seg: int, pos_idx: int, feat: torch.Tensor) -> None:
            tokens.append((slug_idx, zone_seg, pos_idx, feat))

        meta_vec = self._build_meta_vec(state, perspective_player, me, opp)

        # ── OWN ZONES ──────────────────────────────────────────────────────
        if me.hero is not None:
            own_hero_token_idx = len(tokens)
            _add(self._slug(me.hero), OWN_HERO, 0, _safe_card_features(me.hero))

        for wi, wzone in enumerate([me.weapon1, me.weapon2]):
            if wzone.cards:
                wcard = wzone.cards[0]
                _add(self._slug(wcard), OWN_WEAPON, wi, _safe_card_features(wcard))
            else:
                _add(MASK_SLUG_IDX, OWN_WEAPON, wi, torch.zeros(_N_CARD_FEATS))

        for ei, ezone in enumerate([me.head, me.chest, me.arms, me.legs]):
            if ezone.cards:
                ec = ezone.cards[0]
                _add(self._slug(ec), OWN_EQUIPMENT, ei, _safe_card_features(ec))
            else:
                _add(MASK_SLUG_IDX, OWN_EQUIPMENT, ei, torch.zeros(_N_CARD_FEATS))

        for pos, ac in enumerate(me.arsenal.cards):
            _add(self._slug(ac), OWN_ARSENAL, pos, _safe_card_features(ac))

        for pos, hc in enumerate(me.hand.cards):
            _add(self._slug(hc), OWN_HAND, pos, _safe_card_features(hc))

        gyard_own = list(reversed(me.graveyard.cards))[: _LIMITS["own_graveyard"]]
        for pos, gc in enumerate(gyard_own):
            _add(self._slug(gc), OWN_GRAVEYARD, pos, _safe_card_features(gc))

        banished_own = me.banished.cards[: _LIMITS["own_banished"]]
        for pos, bc in enumerate(banished_own):
            _add(self._slug(bc), OWN_BANISHED, pos, _safe_card_features(bc))

        perms_own = me.permanents.cards[: _LIMITS["own_permanents"]]
        for pos, pc in enumerate(perms_own):
            _add(self._slug(pc), OWN_PERMANENTS, pos, _safe_card_features(pc))

        for pos, sc in enumerate(me.soul.cards):
            _add(self._slug(sc), OWN_SOUL, pos, _safe_card_features(sc))

        for pos, ptc in enumerate(me.pitch.cards):
            _add(self._slug(ptc), OWN_PITCH, pos, _safe_card_features(ptc))

        deck_own = me.deck.cards[: _LIMITS["own_deck"]]
        for pos, dc in enumerate(deck_own):
            _add(self._slug(dc), OWN_DECK, pos, _safe_card_features(dc))

        # ── OPPONENT ZONES ─────────────────────────────────────────────────
        if opp.hero is not None:
            _add(self._slug(opp.hero), OPP_HERO, 0, _safe_card_features(opp.hero))

        for wi, wzone in enumerate([opp.weapon1, opp.weapon2]):
            if wzone.cards:
                wcard = wzone.cards[0]
                _add(self._slug(wcard), OPP_WEAPON, wi, _safe_card_features(wcard))
            else:
                _add(MASK_SLUG_IDX, OPP_WEAPON, wi, torch.zeros(_N_CARD_FEATS))

        for ei, ezone in enumerate([opp.head, opp.chest, opp.arms, opp.legs]):
            if ezone.cards:
                ec = ezone.cards[0]
                _add(self._slug(ec), OPP_EQUIPMENT, ei, _safe_card_features(ec))
            else:
                _add(MASK_SLUG_IDX, OPP_EQUIPMENT, ei, torch.zeros(_N_CARD_FEATS))

        if opp.arsenal.cards:
            ac = opp.arsenal.cards[0]
            if ac.is_public:
                _add(self._slug(ac), OPP_ARSENAL_FACEUP, 0, _safe_card_features(ac))
            else:
                _add(MASK_SLUG_IDX, OPP_ARSENAL_FACEDOWN, 0, _safe_card_features(None, masked=True))

        for slot in range(len(opp.hand.cards)):
            _add(MASK_SLUG_IDX, OPP_HAND_MASKED, slot, _safe_card_features(None, masked=True))

        gyard_opp = list(reversed(opp.graveyard.cards))[: _LIMITS["opp_graveyard"]]
        for pos, gc in enumerate(gyard_opp):
            _add(self._slug(gc), OPP_GRAVEYARD, pos, _safe_card_features(gc))

        perms_opp = opp.permanents.cards[: _LIMITS["opp_permanents"]]
        for pos, pc in enumerate(perms_opp):
            _add(self._slug(pc), OPP_PERMANENTS, pos, _safe_card_features(pc))

        banished_opp = opp.banished.cards[: _LIMITS["opp_banished"]]
        for pos, bc in enumerate(banished_opp):
            _add(self._slug(bc), OPP_BANISHED, pos, _safe_card_features(bc))

        opp_pitch_history = self._get_pitch_history(state, opp_id)
        pitch_tokens_added = 0
        for turn_num, slugs in opp_pitch_history:
            for slug in slugs:
                if pitch_tokens_added >= _LIMITS["opp_pitch_history"]:
                    break
                temporal_pos = min(int(turn_num), MAX_TURNS_FOR_TEMPORAL)
                _add(self._slug_from_str(slug), OPP_PITCH_HISTORY, temporal_pos,
                     torch.zeros(_N_CARD_FEATS))
                pitch_tokens_added += 1
            if pitch_tokens_added >= _LIMITS["opp_pitch_history"]:
                break

        return tokens, own_hero_token_idx, meta_vec

    def forward(self, state: GameState, perspective_player: int = 1) -> torch.Tensor:
        """Embed the game state from one player's perspective.

        Args:
            state: GameState object.
            perspective_player: Player ID (1 or 2).

        Returns:
            Tensor of shape (d_model + hero_head_dim,) — CLS token concatenated
            with the projected OWN_HERO contextual output.
        """
        device = self._dev_anchor.device

        tokens, own_hero_token_idx, meta_vec = self._collect_tokens(state, perspective_player)

        # Truncate to max_seq_len - 2 to leave room for CLS and META tokens
        max_card_tokens = self.max_seq_len - 2
        if len(tokens) > max_card_tokens:
            tokens = tokens[:max_card_tokens]

        # Now build tensors for each token type
        total_len = 2 + len(tokens)  # CLS + META + card tokens
        slug_idxs   = torch.zeros(total_len, dtype=torch.long, device=device)
        zone_segs   = torch.zeros(total_len, dtype=torch.long, device=device)
        pos_idxs    = torch.zeros(total_len, dtype=torch.long, device=device)
        # feat_matrix: (total_len, _N_CARD_FEATS) — card numeric features (slots 2+)
        # Slot 0 (CLS) and slot 1 (META) will be overridden; their rows stay zero here.
        feat_matrix = torch.zeros(total_len, _N_CARD_FEATS, dtype=torch.float32, device=device)

        # Slot 0: CLS zone segment
        zone_segs[0] = CLS_SEGMENT
        # Slot 1: META zone segment (no card feat; projected separately via meta_proj)
        zone_segs[1] = META

        # Slots 2+: card tokens
        for i, (s_idx, z_seg, p_idx, feat) in enumerate(tokens):
            tok_i = i + 2
            slug_idxs[tok_i]  = max(s_idx, 0)
            zone_segs[tok_i]  = z_seg
            pos_idxs[tok_i]   = min(p_idx, MAX_TURNS_FOR_TEMPORAL + self.max_seq_len)
            feat_matrix[tok_i] = feat.to(device)

        # ── Compute embeddings ───────────────────────────────────────
        slug_emb  = self.slug_embed(slug_idxs)          # (T, d_model)
        seg_emb   = self.zone_segment_embed(zone_segs)  # (T, d_model)
        pos_emb   = self.position_embed(pos_idxs)       # (T, d_model)
        card_proj = self.card_feat_proj(feat_matrix)    # (T, d_model)

        token_embs = slug_emb + seg_emb + pos_emb + card_proj   # (T, d_model)

        # Override slot 1 (META)
        meta_proj_out = self.meta_proj(meta_vec.to(device))      # (d_model,)
        token_embs[1] = slug_emb[1] + seg_emb[1] + pos_emb[1] + meta_proj_out

        # Override slot 0 (CLS): use learned CLS token parameter only
        token_embs[0] = self.cls_token.squeeze(0)

        # Add batch dimension: (1, T, d_model)
        token_embs = token_embs.unsqueeze(0)

        # No padding mask needed (all tokens are real — we truncated already)
        out = self.transformer(token_embs)   # (1, T, d_model)
        cls_out = out[0, 0]                  # (d_model,)
        cls_normed = self.output_norm(cls_out)

        # Hero head: extract the OWN_HERO token's contextual output
        if self.hero_head_proj is not None:
            if own_hero_token_idx is not None:
                hero_slot_idx = own_hero_token_idx + 2   # +2 for CLS and META
                if hero_slot_idx < out.shape[1]:
                    hero_ctx = out[0, hero_slot_idx]     # (d_model,)
                else:
                    hero_ctx = torch.zeros(self.d_model, device=device)
            else:
                hero_ctx = torch.zeros(self.d_model, device=device)
            hero_out = self.hero_head_norm(self.hero_head_proj(hero_ctx))  # (hero_head_dim,)
            return torch.cat([cls_normed, hero_out], dim=0)   # (d_model + hero_head_dim,)

        return cls_normed   # hero_head_dim == 0 fallback

    def tokenize_to_packed(
        self,
        state: GameState,
        perspective_player: int,
    ) -> "np.ndarray":
        """Tokenize a game state to a flat float32 array for DB storage.

        Shape: (packed_feature_size,) = (_state_packed_size(),) floats.
        Used at game-collection time instead of forward() when end-to-end training
        is enabled.  At training time, forward_packed_batch() reconstructs
        embeddings from these arrays.

        Card numeric features are NOT stored — they are looked up from
        card_feats_lookup at training time (differentiable lookup table).
        """
        tokens, own_hero_token_idx, meta_vec = self._collect_tokens(state, perspective_player)

        # Truncate to storage limit (-2 for CLS and META slots)
        tokens = tokens[: MAX_STORAGE_SEQ_LEN - 2]
        seq_len = len(tokens)
        hero_pos = own_hero_token_idx if own_hero_token_idx is not None else -1

        packed_size = _state_packed_size()
        buf = np.zeros(packed_size, dtype=np.float32)
        buf[0] = float(seq_len)
        buf[1] = float(hero_pos)
        buf[2:2 + _N_META] = meta_vec.numpy()

        offset_slug = 2 + _N_META
        offset_zone = offset_slug + MAX_STORAGE_SEQ_LEN
        offset_pos  = offset_zone + MAX_STORAGE_SEQ_LEN

        for i, (s_idx, z_seg, p_idx, _feat) in enumerate(tokens):
            buf[offset_slug + i] = float(max(s_idx, 0))
            buf[offset_zone + i] = float(z_seg)
            buf[offset_pos  + i] = float(min(p_idx, MAX_TURNS_FOR_TEMPORAL + MAX_STORAGE_SEQ_LEN))

        return buf

    def forward_packed_batch(self, packed: torch.Tensor) -> torch.Tensor:
        """Run batched transformer forward from packed state feature arrays.

        Args:
            packed: (B, packed_feature_size) float32 tensor on self.device
        Returns:
            (B, d_model + hero_head_dim) embeddings
        """
        device = self._dev_anchor.device
        B = packed.shape[0]

        seq_lens       = packed[:, 0].long()          # (B,)
        hero_positions = packed[:, 1].long()          # (B,) — may be -1
        meta_vecs      = packed[:, 2:2 + _N_META]     # (B, N_META)

        offset_slug = 2 + _N_META
        offset_zone = offset_slug + MAX_STORAGE_SEQ_LEN
        offset_pos  = offset_zone + MAX_STORAGE_SEQ_LEN

        T = MAX_STORAGE_SEQ_LEN
        slug_idxs_all = packed[:, offset_slug:offset_zone].long().clamp(min=0, max=self.slug_vocab_size)  # (B, T)
        zone_segs_all = packed[:, offset_zone:offset_pos].long().clamp(min=0)
        pos_idxs_all  = packed[:, offset_pos:offset_pos + T].long().clamp(min=0)

        # Build embeddings for all card tokens in batch
        slug_emb  = self.slug_embed(slug_idxs_all)         # (B, T, d_model)
        seg_emb   = self.zone_segment_embed(zone_segs_all) # (B, T, d_model)
        pos_emb   = self.position_embed(pos_idxs_all)      # (B, T, d_model)

        # Card feats from lookup table (differentiable — gradient flows through card_feat_proj)
        card_feats = self.card_feats_lookup[slug_idxs_all]  # (B, T, N_CARD_FEATS)
        card_proj  = self.card_feat_proj(card_feats)         # (B, T, d_model)

        card_token_embs = slug_emb + seg_emb + pos_emb + card_proj  # (B, T, d_model)

        # META token: project meta_vec for each batch item
        meta_proj_out = self.meta_proj(meta_vecs)  # (B, d_model)

        # Build CLS + META + card token sequence: (B, 2+T, d_model)
        cls_exp = self.cls_token.expand(B, -1).unsqueeze(1)  # (B, 1, d_model)

        # META token: zone_segment_embed(META) + position_embed(0) + meta_proj
        meta_zone_idx = torch.full((B, 1), META, dtype=torch.long, device=device)
        meta_pos_idx  = torch.zeros(B, 1, dtype=torch.long, device=device)
        meta_seg_emb  = self.zone_segment_embed(meta_zone_idx)  # (B, 1, d_model)
        meta_pos_emb  = self.position_embed(meta_pos_idx)       # (B, 1, d_model)
        meta_token_embs = meta_seg_emb + meta_pos_emb + meta_proj_out.unsqueeze(1)  # (B, 1, d_model)

        token_embs = torch.cat([cls_exp, meta_token_embs, card_token_embs], dim=1)  # (B, 2+T, d_model)

        # Padding mask: tokens beyond seq_len are padding (True = ignored by transformer)
        # seq_len+2 accounts for CLS and META (always real tokens)
        seq_with_prefix = seq_lens + 2  # (B,)
        arange = torch.arange(2 + T, device=device).unsqueeze(0).expand(B, -1)
        padding_mask = arange >= seq_with_prefix.unsqueeze(1)  # (B, 2+T), True = pad

        out = self.transformer(token_embs, src_key_padding_mask=padding_mask)  # (B, 2+T, d_model)
        cls_out = out[:, 0, :]  # (B, d_model)
        cls_normed = self.output_norm(cls_out)

        if self.hero_head_proj is not None:
            # hero_positions is the card-token index (0-based in tokens list)
            # Offset by +2 for CLS and META
            hero_slot_idxs = (hero_positions + 2).clamp(min=0, max=2 + T - 1)  # (B,)
            has_hero = (hero_positions >= 0).float()  # (B,)

            batch_idx = torch.arange(B, device=device)
            hero_ctx = out[batch_idx, hero_slot_idxs]  # (B, d_model)
            # Zero out hero ctx for states without hero token
            hero_ctx = hero_ctx * has_hero.unsqueeze(1)
            hero_out = self.hero_head_norm(self.hero_head_proj(hero_ctx))  # (B, hero_head_dim)
            return torch.cat([cls_normed, hero_out], dim=1)  # (B, d_model + hero_head_dim)

        return cls_normed  # (B, d_model) when hero_head_dim=0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _slug(self, card: Optional[Card]) -> int:
        """Return the slug's integer index, clamped to vocab size."""
        if card is None:
            return MASK_SLUG_IDX
        slug = getattr(card, "slug", None)
        return self._slug_from_str(slug)

    def _slug_from_str(self, slug: Optional[str]) -> int:
        """Look up a slug string in the *module-local* dummy vocab.

        The dummy vocab only knows what has been added; unknown slugs → UNK (1).
        For the transformer we primarily rely on the slug_embed table which
        is sized slug_vocab_size+1, so UNK (1) and MASK (0) are valid indices.
        """
        if not slug:
            return MASK_SLUG_IDX
        # We use the dummy vocab for consistent mapping; the model's slug_embed
        # is trained end-to-end so index identity is what matters.
        return _DUMMY_VOCAB.get(slug)  # returns UNK for unknown slugs

    def _build_meta_vec(
        self,
        state: GameState,
        perspective_player: int,
        me: Player,
        opp: Player,
    ) -> torch.Tensor:
        """Build the (_N_META,) global meta feature vector."""
        # Turn number (normalized)
        turn_norm = state.turn_number / 50.0

        # Step one-hot
        step_val = state.step.value if hasattr(state.step, "value") else str(state.step)
        step_onehot = torch.zeros(len(STEP_VOCABULARY))
        try:
            step_idx = STEP_VOCABULARY.index(step_val)
            step_onehot[step_idx] = 1.0
        except ValueError:
            pass

        is_active   = float(state.active_player == perspective_player)
        is_priority = float(state.priority_player == perspective_player)

        own_hp  = me.health  / 40.0
        opp_hp  = opp.health / 40.0
        own_res = me.resources    / 10.0
        own_ap  = me.action_points / 4.0

        in_combat    = float(state.combat is not None)
        attack_power = 0.0
        total_def    = 0.0
        if state.combat is not None:
            attack_power = (state.combat.attack_power or 0) / 20.0
            total_def    = (state.combat.total_defense or 0) / 20.0

        scalars = torch.tensor(
            [turn_norm, is_active, is_priority,
             own_hp, opp_hp, own_res, own_ap,
             in_combat, attack_power, total_def],
            dtype=torch.float32,
        )
        return torch.cat([scalars[:1], step_onehot, scalars[1:]], dim=0)  # (_N_META,)

    @staticmethod
    def _get_pitch_history(
        state: GameState, player_id: int
    ) -> list[tuple[int, list[str]]]:
        """Return opponent pitch history as list of (turn_number, [slug, ...]).

        Reads from GameState.pitch_history (dict[player_id, dict[turn, [slugs]]]).
        Falls back to the player's current-turn pitch zone if no history exists.
        """
        history = getattr(state, "pitch_history", {})
        player_history: dict = history.get(player_id, {})
        if player_history:
            return sorted(player_history.items(), key=lambda x: x[0])
        # Fallback: current-turn pitch zone only
        player = state.players.get(player_id)
        if player is None:
            return []
        current_turn = state.turn_number
        slugs = [c.slug for c in player.pitch.cards]
        return [(current_turn, slugs)] if slugs else []


# ---------------------------------------------------------------------------
# Convenience: populate _DUMMY_VOCAB from a CardDB at module load time
# (called by run_local_pipeline.py and embedder_bundle helpers)
# ---------------------------------------------------------------------------

def prime_dummy_vocab(card_db) -> None:
    """Populate the module-level _DUMMY_VOCAB from a CardDB.

    This must be called before the first forward() pass so that slug lookups
    return consistent indices matching the trained slug_embed table.
    The slug_vocab used here should match the one used to size slug_embed.
    """
    for slug in card_db._by_slug:
        _DUMMY_VOCAB.add(slug)
