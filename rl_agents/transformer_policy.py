"""Transformer policy model for FAB ask_agent decisions.

This module is a first implementation of the roadmap item for a transformer
that encodes:
1) priority-player hand cards,
2) public cards for both players,
3) unordered deck composition,
4) legal action options.

The model uses existing CardEmbedder and ActionEmbedder modules so it stays
consistent with the current engine and replay pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
import random
from typing import Optional, Sequence

import torch
import torch.nn as nn

from engine.actions import Action
from engine.card import CardDB
from engine.state import GameState, Player, Step
from encoder.action_embedder import ActionEmbedder
from encoder.card_embedder import (
    CardEmbedder, SlugVocab, batch_cards_to_features,
    N_NUMERIC, N_TYPES, N_SUBTYPES, N_SUPERTYPES, N_KEYWORDS, _ZONE_IDX,
)


@dataclass
class TransformerPolicyConfig:
    d_model: int = 128
    num_heads: int = 8
    num_layers: int = 4
    ff_dim: int = 512
    dropout: float = 0.1
    max_hand_cards: int = 12
    max_public_cards_per_player: int = 80
    max_deck_tokens: int = 60
    max_pitch_tokens: int = 60
    max_actions: int = 80
    max_sequence_tokens: int = 512
    deck_count_clip: int = 6


@dataclass
class TransformerDecisionOutput:
    logits: torch.Tensor
    value: torch.Tensor
    action_count: int
    token_count: int


class AskAgentTransformer(nn.Module):
    """Transformer policy/value model over state cards + legal actions.

    The forward pass scores legal actions and predicts a scalar state value.
    Encodes ordered pitch history per turn to preserve known-bottom information.
    """

    SEGMENT_CLS = 0
    SEGMENT_META = 1
    SEGMENT_HAND = 2
    SEGMENT_PUBLIC_SELF = 3
    SEGMENT_PUBLIC_OPP = 4
    SEGMENT_PITCH_SELF = 5
    SEGMENT_PITCH_OPP = 6
    SEGMENT_DECK = 7
    SEGMENT_ACTION = 8
    NUM_SEGMENTS = 9

    def __init__(
        self,
        slug_vocab: SlugVocab,
        config: Optional[TransformerPolicyConfig] = None,
        card_embedder: Optional[CardEmbedder] = None,
        action_embedder: Optional[ActionEmbedder] = None,
        card_db: Optional[CardDB] = None,
    ):
        super().__init__()
        self.slug_vocab = slug_vocab
        self._card_db = card_db
        self.config = config or TransformerPolicyConfig()

        if self.config.deck_count_clip <= 0:
            raise ValueError("deck_count_clip must be > 0")

        # Validate token budget: worst-case segment total must fit max_sequence_tokens
        worst_case = (
            1  # CLS
            + 1  # META
            + self.config.max_hand_cards
            + 2 * self.config.max_public_cards_per_player
            + 2 * self.config.max_pitch_tokens
            + self.config.max_deck_tokens
            + self.config.max_actions
        )
        if worst_case > self.config.max_sequence_tokens:
            import warnings
            warnings.warn(
                f"Configured segment caps sum to {worst_case} tokens which exceeds "
                f"max_sequence_tokens={self.config.max_sequence_tokens}. "
                f"Overflow will be handled by truncating state tokens."
            )

        if card_embedder is None:
            card_embedder = CardEmbedder(
                slug_vocab_size=self.slug_vocab.size,
                d_model=self.config.d_model,
            )
        self.card_embedder = card_embedder

        if action_embedder is None:
            action_embedder = ActionEmbedder(
                d_model=self.config.d_model,
                card_embedder=self.card_embedder,
                slug_vocab_size=self.slug_vocab.size,
                slug_vocab=self.slug_vocab,
            )
        self.action_embedder = action_embedder

        self.action_proj = nn.Linear(self.action_embedder.get_output_dim(), self.config.d_model)
        self.deck_count_proj = nn.Linear(1, self.config.d_model)

        self._step_values = [step.value for step in Step]
        self._step_to_index = {step_value: i for i, step_value in enumerate(self._step_values)}
        self.meta_dim = 23 + len(self._step_values)  # 20 base + 3 combat (go_again, attack_power, defense)
        self.meta_proj = nn.Sequential(
            nn.Linear(self.meta_dim, self.config.d_model),
            nn.GELU(),
            nn.Linear(self.config.d_model, self.config.d_model),
        )

        self.cls_token = nn.Parameter(torch.zeros(self.config.d_model))
        self.segment_embed = nn.Embedding(self.NUM_SEGMENTS, self.config.d_model)
        self.position_embed = nn.Embedding(self.config.max_sequence_tokens, self.config.d_model)
        self.input_dropout = nn.Dropout(self.config.dropout)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=self.config.d_model,
            nhead=self.config.num_heads,
            dim_feedforward=self.config.ff_dim,
            dropout=self.config.dropout,
            batch_first=True,
            norm_first=True,
            activation="gelu",
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=self.config.num_layers)
        self.final_norm = nn.LayerNorm(self.config.d_model)

        self.policy_query = nn.Linear(self.config.d_model, self.config.d_model)
        self.value_head = nn.Sequential(
            nn.Linear(self.config.d_model, self.config.d_model),
            nn.GELU(),
            nn.Linear(self.config.d_model, 1),
        )

    def _device(self) -> torch.device:
        return self.cls_token.device

    def _embed_cards(
        self,
        cards: Sequence,
        player_counters: Optional[dict],
    ) -> torch.Tensor:
        if not cards:
            return torch.empty((0, self.config.d_model), dtype=torch.float32, device=self._device())

        features = batch_cards_to_features(
            cards=list(cards),
            vocab=self.slug_vocab,
            player_counters=player_counters,
        )
        features = {k: v.to(self._device()) for k, v in features.items()}
        return self.card_embedder(features)

    @staticmethod
    def _dedupe_cards(cards: Sequence) -> list:
        seen: set[int] = set()
        deduped = []
        for card in cards:
            if card is None:
                continue
            card_id = getattr(card, "object_id", id(card))
            if card_id in seen:
                continue
            seen.add(card_id)
            deduped.append(card)
        return deduped

    def _collect_public_cards(self, state: GameState, perspective_player: int) -> tuple[list, list]:
        self_player = state.players[perspective_player]
        opp_player = state.players[3 - perspective_player]

        self_public = list(self_player.public_cards)
        opp_public = list(opp_player.public_cards)

        # Combat chain and stack cards are global zones; add them explicitly.
        for card in list(state.combat_chain.cards):
            owner = getattr(card, "owner", None)
            if owner == perspective_player:
                self_public.append(card)
            elif owner == (3 - perspective_player):
                opp_public.append(card)
            else:
                self_public.append(card)

        for entry in list(state.stack_entries):
            card = entry.card
            if card is None:
                continue
            owner = getattr(card, "owner", None)
            if owner == perspective_player:
                self_public.append(card)
            elif owner == (3 - perspective_player):
                opp_public.append(card)
            else:
                self_public.append(card)

        self_public = self._dedupe_cards(self_public)[: self.config.max_public_cards_per_player]
        opp_public = self._dedupe_cards(opp_public)[: self.config.max_public_cards_per_player]
        return self_public, opp_public

    def _build_meta_token(self, state: GameState, perspective_player: int) -> torch.Tensor:
        self_player = state.players[perspective_player]
        opp_player = state.players[3 - perspective_player]

        step_value = state.step.value if hasattr(state.step, "value") else str(state.step)
        step_one_hot = torch.zeros(len(self._step_values), dtype=torch.float32, device=self._device())
        if step_value in self._step_to_index:
            step_one_hot[self._step_to_index[step_value]] = 1.0

        # Combat features (P2-11, P2-12)
        combat = getattr(state, "combat", None)
        has_go_again = 0.0
        attack_power = 0.0
        total_defense = 0.0
        if combat is not None:
            has_go_again = float(getattr(combat, "has_go_again", False))
            attack_power = min(float(getattr(combat, "attack_power", 0)), 20.0) / 20.0
            total_defense = min(float(getattr(combat, "total_defense", 0)), 20.0) / 20.0

        base = torch.tensor(
            [
                min(float(state.turn_number), 60.0) / 60.0,
                float(state.active_player == perspective_player),
                float(state.priority_player == perspective_player),
                min(float(state.consecutive_passes), 2.0) / 2.0,
                min(float(len(state.stack_entries)), 10.0) / 10.0,
                min(float(len(state.chain_links)), 10.0) / 10.0,
                self_player.health / 50.0,
                opp_player.health / 50.0,
                min(float(self_player.resources), 10.0) / 10.0,
                min(float(opp_player.resources), 10.0) / 10.0,
                min(float(self_player.action_points), 5.0) / 5.0,
                min(float(opp_player.action_points), 5.0) / 5.0,
                min(float(len(self_player.hand.cards)), 12.0) / 12.0,
                min(float(len(opp_player.hand.cards)), 12.0) / 12.0,
                min(float(len(self_player.deck.cards)), 80.0) / 80.0,
                min(float(len(opp_player.deck.cards)), 80.0) / 80.0,
                min(float(len(self_player.graveyard.cards)), 80.0) / 80.0,
                min(float(len(opp_player.graveyard.cards)), 80.0) / 80.0,
                min(float(len(self_player.banished.cards)), 80.0) / 80.0,
                min(float(len(opp_player.banished.cards)), 80.0) / 80.0,
                has_go_again,
                attack_power,
                total_defense,
            ],
            dtype=torch.float32,
            device=self._device(),
        )

        meta_input = torch.cat([base, step_one_hot], dim=0)
        return self.meta_proj(meta_input)

    def _build_deck_tokens(self, player: Player) -> torch.Tensor:
        slug_to_count: dict[str, int] = {}
        slug_to_card: dict[str, object] = {}
        for card in player.deck.cards:
            slug_to_count[card.slug] = slug_to_count.get(card.slug, 0) + 1
            if card.slug not in slug_to_card:
                slug_to_card[card.slug] = card

        grouped = [
            (slug, slug_to_card[slug], count)
            for slug, count in slug_to_count.items()
        ]
        grouped.sort(key=lambda x: (-x[2], x[0]))
        grouped = grouped[: self.config.max_deck_tokens]

        if not grouped:
            return torch.empty((0, self.config.d_model), dtype=torch.float32, device=self._device())

        cards = [entry[1] for entry in grouped]
        counts = torch.tensor(
            [
                [min(float(entry[2]), float(self.config.deck_count_clip)) / float(self.config.deck_count_clip)]
                for entry in grouped
            ],
            dtype=torch.float32,
            device=self._device(),
        )

        card_tokens = self._embed_cards(cards, player_counters=player.counters)
        return card_tokens + self.deck_count_proj(counts)

    def _build_pitch_history_tokens(self, state: GameState, perspective_player: int, preserve_order: bool = True) -> torch.Tensor:
        """Build ordered token sequence from pitch history (known bottom cards).

        Pitch history is stored as {player_id: {turn: [slug, ...]}}.
        Uses the same CardEmbedder as all other card-token segments (P1-7).

        Args:
            state: GameState with pitch_history dictionary
            perspective_player: Which player's pitch history to encode
            preserve_order: If True (for self), preserve strict order. If False (for opp),
                          shuffle within each turn to reflect uncertainty of within-turn card order.

        Returns:
            Token tensor of shape (num_cards, d_model) in chronological order (by turn).
            Within each turn, order is strict (self) or randomized (opponent).
        """
        if not hasattr(state, 'pitch_history') or not state.pitch_history:
            return torch.empty((0, self.config.d_model), dtype=torch.float32, device=self._device())

        all_pitched_slugs = []

        # Collect pitched cards from each turn
        if perspective_player in state.pitch_history:
            for turn in sorted(state.pitch_history[perspective_player].keys()):
                slugs = list(state.pitch_history[perspective_player][turn])

                # If opponent's pitch history, shuffle within turn to reflect unknown order
                if not preserve_order:
                    random.shuffle(slugs)

                all_pitched_slugs.extend(slugs)

        # Clip to reasonable maximum
        all_pitched_slugs = all_pitched_slugs[:self.config.max_pitch_tokens]

        if not all_pitched_slugs:
            return torch.empty((0, self.config.d_model), dtype=torch.float32, device=self._device())

        # Resolve slugs to Card objects via CardDB for proper CardEmbedder encoding
        if self._card_db is not None:
            import copy
            cards = []
            for slug in all_pitched_slugs:
                card = self._card_db.get(slug)
                if card is not None:
                    card = copy.copy(card)
                    card.zone = "pitch"
                    cards.append(card)
            if cards:
                player = state.players.get(perspective_player)
                counters = player.counters if player else None
                return self._embed_cards(cards, player_counters=counters)

        # Fallback: build full feature dicts from slugs (no card_db available)
        slug_indices = [self.slug_vocab.get(slug) for slug in all_pitched_slugs]
        slug_indices = [idx for idx in slug_indices if idx is not None]
        if not slug_indices:
            return torch.empty((0, self.config.d_model), dtype=torch.float32, device=self._device())

        device = self._device()
        B = len(slug_indices)
        pitch_zone_idx = _ZONE_IDX.get("pitch", 0)
        features = {
            "slug_idx": torch.tensor(slug_indices, dtype=torch.long, device=device),
            "color_idx": torch.zeros(B, dtype=torch.long, device=device),
            "zone_idx": torch.full((B,), pitch_zone_idx, dtype=torch.long, device=device),
            "numeric": torch.zeros(B, N_NUMERIC, dtype=torch.float32, device=device),
            "types": torch.zeros(B, N_TYPES, dtype=torch.float32, device=device),
            "subtypes": torch.zeros(B, N_SUBTYPES, dtype=torch.float32, device=device),
            "supertypes": torch.zeros(B, N_SUPERTYPES, dtype=torch.float32, device=device),
            "keywords": torch.zeros(B, N_KEYWORDS, dtype=torch.float32, device=device),
        }
        return self.card_embedder(features)

    @staticmethod
    def _slug_or_passthrough(value):
        if value is None:
            return None
        return value.slug if hasattr(value, "slug") else value

    def _normalise_action_for_embedder(self, action: Action) -> Action:
        pitch_cards = [self._slug_or_passthrough(card) for card in (action.pitch_cards or [])]
        targets = [self._slug_or_passthrough(target) for target in (action.targets or [])]
        return replace(action, pitch_cards=pitch_cards, targets=targets)

    def _embed_actions(
        self,
        legal_actions: Sequence[Action],
        player_counters: Optional[dict],
    ) -> torch.Tensor:
        if not legal_actions:
            return torch.empty((0, self.config.d_model), dtype=torch.float32, device=self._device())

        action_vecs = []
        for action in legal_actions:
            safe_action = self._normalise_action_for_embedder(action)
            action_vec = self.action_embedder(safe_action, player_counters=player_counters)
            action_vecs.append(action_vec)
        action_vecs = torch.stack(action_vecs).to(self._device())
        return self.action_proj(action_vecs)

    def _append_chunk(
        self,
        chunks: list[torch.Tensor],
        segment_ids: list[int],
        chunk: torch.Tensor,
        segment: int,
    ) -> None:
        if chunk.numel() == 0:
            return
        chunks.append(chunk)
        segment_ids.extend([segment] * chunk.shape[0])

    def _build_tokens(
        self,
        state: GameState,
        legal_actions: Sequence[Action],
        perspective_player: int,
    ) -> tuple[torch.Tensor, int, int]:
        player = state.players[perspective_player]

        hand_cards = list(player.hand.cards)[: self.config.max_hand_cards]
        self_public_cards, opp_public_cards = self._collect_public_cards(state, perspective_player)
        # Only perspective player's deck composition is tokenized; opponent deck
        # is represented only by its size in the meta token (public info in FAB).
        deck_tokens = self._build_deck_tokens(player)

        action_list = list(legal_actions)[: self.config.max_actions]

        chunks: list[torch.Tensor] = []
        segment_ids: list[int] = []

        cls_token = self.cls_token.unsqueeze(0)
        self._append_chunk(chunks, segment_ids, cls_token, self.SEGMENT_CLS)

        meta_token = self._build_meta_token(state, perspective_player).unsqueeze(0)
        self._append_chunk(chunks, segment_ids, meta_token, self.SEGMENT_META)

        hand_tokens = self._embed_cards(hand_cards, player_counters=player.counters)
        self._append_chunk(chunks, segment_ids, hand_tokens, self.SEGMENT_HAND)

        self_public_tokens = self._embed_cards(self_public_cards, player_counters=player.counters)
        self._append_chunk(chunks, segment_ids, self_public_tokens, self.SEGMENT_PUBLIC_SELF)

        opp_player = state.players[3 - perspective_player]
        opp_public_tokens = self._embed_cards(opp_public_cards, player_counters=opp_player.counters)
        self._append_chunk(chunks, segment_ids, opp_public_tokens, self.SEGMENT_PUBLIC_OPP)

        pitch_self_tokens = self._build_pitch_history_tokens(state, perspective_player, preserve_order=True)
        self._append_chunk(chunks, segment_ids, pitch_self_tokens, self.SEGMENT_PITCH_SELF)

        pitch_opp_tokens = self._build_pitch_history_tokens(state, 3 - perspective_player, preserve_order=True)
        self._append_chunk(chunks, segment_ids, pitch_opp_tokens, self.SEGMENT_PITCH_OPP)

        self._append_chunk(chunks, segment_ids, deck_tokens, self.SEGMENT_DECK)

        action_start = sum(chunk.shape[0] for chunk in chunks)
        action_tokens = self._embed_actions(action_list, player_counters=player.counters)
        action_count = action_tokens.shape[0]
        self._append_chunk(chunks, segment_ids, action_tokens, self.SEGMENT_ACTION)

        tokens = torch.cat(chunks, dim=0)
        token_count = tokens.shape[0]
        if token_count > self.config.max_sequence_tokens:
            # Truncate pre-action tokens to fit budget, preserving all action tokens
            budget = self.config.max_sequence_tokens - action_count
            pre_action_tokens = tokens[:action_start][:budget]
            pre_action_seg = segment_ids[:action_start][:budget]
            tokens = torch.cat([pre_action_tokens, tokens[action_start:action_start + action_count]], dim=0)
            segment_ids = list(pre_action_seg) + segment_ids[action_start:action_start + action_count]
            action_start = pre_action_tokens.shape[0]
            token_count = tokens.shape[0]

        seg = torch.tensor(segment_ids, dtype=torch.long, device=self._device())
        pos = torch.arange(token_count, dtype=torch.long, device=self._device())
        tokens = tokens + self.segment_embed(seg) + self.position_embed(pos)
        tokens = self.input_dropout(tokens)
        return tokens, action_start, action_count

    def forward(
        self,
        state: GameState,
        legal_actions: Sequence[Action],
        perspective_player: Optional[int] = None,
    ) -> TransformerDecisionOutput:
        perspective_player = perspective_player or state.priority_player

        tokens, action_start, action_count = self._build_tokens(
            state=state,
            legal_actions=legal_actions,
            perspective_player=perspective_player,
        )

        encoded = self.encoder(tokens.unsqueeze(0)).squeeze(0)
        encoded = self.final_norm(encoded)

        state_repr = encoded[0]
        value = self.value_head(state_repr).squeeze(-1)

        if action_count > 0:
            action_repr = encoded[action_start : action_start + action_count]
            query = self.policy_query(state_repr)
            logits = torch.sum(action_repr * query.unsqueeze(0), dim=-1)
            logits = logits / math.sqrt(float(self.config.d_model))
        else:
            logits = torch.empty((0,), dtype=torch.float32, device=self._device())

        return TransformerDecisionOutput(
            logits=logits,
            value=value,
            action_count=action_count,
            token_count=int(tokens.shape[0]),
        )


class TransformerPolicyAgent:
    """Engine-compatible agent wrapper around AskAgentTransformer."""

    def __init__(
        self,
        model: AskAgentTransformer,
        player_id: Optional[int] = None,
        stochastic: bool = False,
        temperature: float = 1.0,
        fallback_seed: Optional[int] = None,
    ):
        self.model = model
        self.player_id = player_id
        self.stochastic = stochastic
        self.temperature = max(float(temperature), 1e-6)
        self.rng = random.Random(fallback_seed)

    def __call__(self, state: GameState, options, context=None):
        if not isinstance(options, (list, tuple)) or not options:
            return options

        if not isinstance(options[0], Action):
            return self.rng.choice(options)

        legal_actions = list(options)
        perspective = self.player_id or state.priority_player

        with torch.no_grad():
            output = self.model(
                state=state,
                legal_actions=legal_actions,
                perspective_player=perspective,
            )

        if output.action_count == 0:
            return self.rng.choice(legal_actions)

        considered_actions = legal_actions[: output.action_count]
        logits = output.logits

        if self.stochastic:
            probs = torch.softmax(logits / self.temperature, dim=0)
            chosen_idx = int(torch.multinomial(probs, num_samples=1).item())
        else:
            chosen_idx = int(torch.argmax(logits).item())

        return considered_actions[chosen_idx]
