"""rl_agents/deck_evaluator.py

Two-stage deck evaluation models for Flesh and Blood deck construction.

Stage 1 — Pool Builder:
    Given a hero, score each candidate card for inclusion in the 80-card pool
    (tournament registration). Uses a Set Transformer to capture card-card
    synergies conditioned on the hero.

Stage 2 — Matchup Selector:
    Given your 80-card pool + opponent hero, select which ~60 deck cards +
    equipment to bring to this specific match.

Both stages share the same card embedding layer.

Model progression:
    - DeepSetsEvaluator: mean/max pooling baseline (~50K params)
    - SetTransformerEvaluator: self-attention for synergy capture (~500K params)
"""
from __future__ import annotations

import json
import math
import random as _random_mod
import sqlite3
from pathlib import Path
from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F


# ---------------------------------------------------------------------------
# Vocabulary — built from fablazing_meta.db
# ---------------------------------------------------------------------------

class CardVocab:
    """Maps card slugs and hero slugs to integer indices.

    Special tokens:
        0 = <PAD>
        1 = <UNK>
    """

    def __init__(
        self,
        card_slugs: list[str],
        hero_slugs: list[str],
    ):
        self.pad_idx = 0
        self.unk_idx = 1

        self._card2idx: dict[str, int] = {"<PAD>": 0, "<UNK>": 1}
        for i, slug in enumerate(sorted(set(card_slugs)), start=2):
            self._card2idx[slug] = i
        self._idx2card = {v: k for k, v in self._card2idx.items()}

        self._hero2idx: dict[str, int] = {"<PAD>": 0, "<UNK>": 1}
        for i, slug in enumerate(sorted(set(hero_slugs)), start=2):
            self._hero2idx[slug] = i
        self._idx2hero = {v: k for k, v in self._hero2idx.items()}

    @property
    def n_cards(self) -> int:
        return len(self._card2idx)

    @property
    def n_heroes(self) -> int:
        return len(self._hero2idx)

    def card_id(self, slug: str) -> int:
        return self._card2idx.get(slug, self.unk_idx)

    def hero_id(self, slug: str) -> int:
        return self._hero2idx.get(slug, self.unk_idx)

    def card_slug(self, idx: int) -> str:
        return self._idx2card.get(idx, "<UNK>")

    def hero_slug(self, idx: int) -> str:
        return self._idx2hero.get(idx, "<UNK>")

    def encode_deck(self, card_slugs: list[str]) -> tuple[list[int], list[int]]:
        """Encode a deck as (card_ids, counts).

        Collapses duplicate slugs into counts.
        Returns parallel lists: card_ids[i] appears counts[i] times.
        """
        counter: dict[str, int] = {}
        for s in card_slugs:
            counter[s] = counter.get(s, 0) + 1
        ids = [self.card_id(s) for s in counter]
        counts = [counter[s] for s in counter]
        return ids, counts

    @classmethod
    def from_db(cls, db_path: str | Path) -> "CardVocab":
        """Build vocabulary from fablazing_meta.db."""
        conn = sqlite3.connect(str(db_path))
        card_slugs = [r[0] for r in conn.execute(
            "SELECT DISTINCT card_slug FROM card_stats"
        ).fetchall()]
        hero_slugs = [r[0] for r in conn.execute(
            "SELECT DISTINCT hero_slug FROM heroes"
        ).fetchall()]
        conn.close()
        return cls(card_slugs, hero_slugs)

    def state_dict(self) -> dict:
        return {
            "card2idx": self._card2idx,
            "hero2idx": self._hero2idx,
        }

    @classmethod
    def from_state_dict(cls, sd: dict) -> "CardVocab":
        vocab = cls.__new__(cls)
        vocab.pad_idx = 0
        vocab.unk_idx = 1
        vocab._card2idx = sd["card2idx"]
        vocab._idx2card = {v: k for k, v in vocab._card2idx.items()}
        vocab._hero2idx = sd["hero2idx"]
        vocab._idx2hero = {v: k for k, v in vocab._hero2idx.items()}
        return vocab


# ---------------------------------------------------------------------------
# Meta distribution — hero sampling weights from fablazing match counts
# ---------------------------------------------------------------------------

def load_meta_weights(db_path: str | Path, fmt: str = "cc") -> dict[str, float]:
    """Load hero meta share as sampling weights (proportional to match count).

    Returns dict mapping hero_slug -> weight (sums to 1.0).
    """
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT hero_slug, total_matches FROM heroes WHERE format = ?",
        (fmt,),
    ).fetchall()
    conn.close()

    total = sum(m for _, m in rows if m)
    if total == 0:
        # uniform fallback
        return {slug: 1.0 / len(rows) for slug, _ in rows}
    return {slug: (matches or 0) / total for slug, matches in rows}


# ---------------------------------------------------------------------------
# Shared card embedding layer
# ---------------------------------------------------------------------------

class CardEmbedding(nn.Module):
    """Embeds a card as: concat(learned_embedding, count_projection) -> projection.

    Concatenation gives the model richer interaction between card identity
    and copy count than a simple additive combination.

    Input:  card_ids [B, S], counts [B, S]
    Output: [B, S, embed_dim]
    """

    def __init__(self, n_cards: int, embed_dim: int = 64, pad_idx: int = 0):
        super().__init__()
        self.embed = nn.Embedding(n_cards, embed_dim, padding_idx=pad_idx)
        count_dim = 8
        self.count_proj = nn.Linear(1, count_dim, bias=False)
        self.fuse = nn.Linear(embed_dim + count_dim, embed_dim)
        nn.init.xavier_uniform_(self.embed.weight)

    def forward(self, card_ids: torch.Tensor, counts: torch.Tensor) -> torch.Tensor:
        """
        card_ids: [B, S] long
        counts:   [B, S] float
        returns:  [B, S, embed_dim]
        """
        emb = self.embed(card_ids)  # [B, S, D]
        count_emb = self.count_proj(counts.unsqueeze(-1))  # [B, S, count_dim]
        return self.fuse(torch.cat([emb, count_emb], dim=-1))  # [B, S, D]


# ---------------------------------------------------------------------------
# DeepSets baseline
# ---------------------------------------------------------------------------

class DeepSetsEvaluator(nn.Module):
    """Permutation-invariant deck evaluator using mean+max pooling.

    Input:  hero_id, card_ids, counts, (optional) opp_hero_id
    Output: P(win) logit (scalar)

    ~50K params with default settings.
    """

    def __init__(
        self,
        n_cards: int,
        n_heroes: int,
        embed_dim: int = 64,
        hidden_dim: int = 128,
        pad_idx: int = 0,
    ):
        super().__init__()
        self.card_embed = CardEmbedding(n_cards, embed_dim, pad_idx)
        self.hero_embed = nn.Embedding(n_heroes, embed_dim, padding_idx=pad_idx)

        # Per-card transform (phi)
        self.phi = nn.Sequential(
            nn.Linear(embed_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
        )

        # Pool -> predict (rho)
        # Input: mean_pool + max_pool + hero_embed + opp_hero_embed = 4 * hidden/embed
        pool_dim = hidden_dim * 2 + embed_dim * 2
        self.rho = nn.Sequential(
            nn.Linear(pool_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1),
        )

    def forward(
        self,
        hero_ids: torch.Tensor,       # [B]
        card_ids: torch.Tensor,        # [B, S]
        counts: torch.Tensor,          # [B, S]
        opp_hero_ids: torch.Tensor,    # [B]
        pad_mask: torch.Tensor | None = None,  # [B, S] bool, True = pad
    ) -> torch.Tensor:
        """Returns win probability logits [B, 1]."""
        # Card embeddings
        x = self.card_embed(card_ids, counts)  # [B, S, D]
        x = self.phi(x)  # [B, S, H]

        # Mask padding
        if pad_mask is not None:
            x = x.masked_fill(pad_mask.unsqueeze(-1), 0.0)
            # For max pool, use -inf for padded positions
            x_for_max = x.masked_fill(pad_mask.unsqueeze(-1), float('-inf'))
        else:
            x_for_max = x

        # Pooling
        mean_pool = x.sum(dim=1) / (~pad_mask).sum(dim=1, keepdim=True).clamp(min=1).float() \
            if pad_mask is not None else x.mean(dim=1)
        max_pool = x_for_max.max(dim=1).values  # [B, H]

        # Hero embeddings
        hero_emb = self.hero_embed(hero_ids)      # [B, D]
        opp_emb = self.hero_embed(opp_hero_ids)    # [B, D]

        # Concatenate and predict
        combined = torch.cat([mean_pool, max_pool, hero_emb, opp_emb], dim=-1)
        return self.rho(combined)  # [B, 1]


# ---------------------------------------------------------------------------
# Set Transformer (synergy-aware)
# ---------------------------------------------------------------------------

class MultiheadSetAttention(nn.Module):
    """Multi-head self-attention block for sets (no positional encoding)."""

    def __init__(self, d_model: int, n_heads: int, dropout: float = 0.1):
        super().__init__()
        self.attn = nn.MultiheadAttention(d_model, n_heads, dropout=dropout, batch_first=True)
        self.norm1 = nn.LayerNorm(d_model)
        self.ff = nn.Sequential(
            nn.Linear(d_model, d_model * 2),
            nn.GELU(),
            nn.Linear(d_model * 2, d_model),
            nn.Dropout(dropout),
        )
        self.norm2 = nn.LayerNorm(d_model)

    def forward(self, x: torch.Tensor, key_padding_mask: torch.Tensor | None = None) -> torch.Tensor:
        # Self-attention with residual
        attn_out, _ = self.attn(x, x, x, key_padding_mask=key_padding_mask)
        x = self.norm1(x + attn_out)
        # Feed-forward with residual
        x = self.norm2(x + self.ff(x))
        return x


class SetTransformerEvaluator(nn.Module):
    """Set Transformer deck evaluator with card-card synergy attention.

    Hero token is prepended to the set so every card attends to the hero
    context. Opponent hero is concatenated at the pooling stage.

    ~500K params with default settings.
    """

    def __init__(
        self,
        n_cards: int,
        n_heroes: int,
        embed_dim: int = 64,
        n_heads: int = 4,
        n_layers: int = 2,
        hidden_dim: int = 128,
        dropout: float = 0.1,
        pad_idx: int = 0,
    ):
        super().__init__()
        self.embed_dim = embed_dim
        self.card_embed = CardEmbedding(n_cards, embed_dim, pad_idx)
        self.hero_embed = nn.Embedding(n_heroes, embed_dim, padding_idx=pad_idx)

        # Self-attention layers
        self.layers = nn.ModuleList([
            MultiheadSetAttention(embed_dim, n_heads, dropout)
            for _ in range(n_layers)
        ])

        # Pooling head: mean + max + hero_skip + opp_hero
        pool_dim = embed_dim * 2 + embed_dim * 2  # mean + max + hero + opp_hero
        self.head = nn.Sequential(
            nn.Linear(pool_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1),
        )

    def forward(
        self,
        hero_ids: torch.Tensor,       # [B]
        card_ids: torch.Tensor,        # [B, S]
        counts: torch.Tensor,          # [B, S]
        opp_hero_ids: torch.Tensor,    # [B]
        pad_mask: torch.Tensor | None = None,  # [B, S] bool, True = pad
    ) -> torch.Tensor:
        """Returns win probability logits [B, 1]."""
        B, S = card_ids.shape

        # Embed cards and hero
        card_emb = self.card_embed(card_ids, counts)     # [B, S, D]
        hero_emb = self.hero_embed(hero_ids).unsqueeze(1)  # [B, 1, D]

        # Prepend hero token to the set
        x = torch.cat([hero_emb, card_emb], dim=1)  # [B, S+1, D]

        # Extend padding mask for hero token (never padded)
        if pad_mask is not None:
            hero_pad = torch.zeros(B, 1, dtype=torch.bool, device=pad_mask.device)
            full_mask = torch.cat([hero_pad, pad_mask], dim=1)  # [B, S+1]
        else:
            full_mask = None

        # Self-attention layers
        for layer in self.layers:
            x = layer(x, key_padding_mask=full_mask)

        # Extract hero-contextualized representations (skip hero token for pooling)
        card_out = x[:, 1:, :]  # [B, S, D]

        # Masked pooling
        if pad_mask is not None:
            card_out_masked = card_out.masked_fill(pad_mask.unsqueeze(-1), 0.0)
            card_out_for_max = card_out.masked_fill(pad_mask.unsqueeze(-1), float('-inf'))
            n_valid = (~pad_mask).sum(dim=1, keepdim=True).clamp(min=1).float()
            mean_pool = card_out_masked.sum(dim=1) / n_valid
        else:
            mean_pool = card_out.mean(dim=1)
            card_out_for_max = card_out

        max_pool = card_out_for_max.max(dim=1).values.clamp(min=-1e6)  # [B, D]

        # Hero skip connection + opponent hero
        hero_skip = self.hero_embed(hero_ids)      # [B, D]
        opp_emb = self.hero_embed(opp_hero_ids)    # [B, D]

        combined = torch.cat([mean_pool, max_pool, hero_skip, opp_emb], dim=-1)
        return self.head(combined)  # [B, 1]


# ---------------------------------------------------------------------------
# Card-level scoring for pool construction (Stage 1)
# ---------------------------------------------------------------------------

class PoolScorer(nn.Module):
    """Scores individual cards for pool inclusion given a hero.

    Shares embedding layers with the evaluator via explicit weight tying.
    Pass the evaluator's card_embed.embed and hero_embed to share weights.

    Input:  hero_id [B], candidate_card_ids [B, C]
    Output: inclusion_scores [B, C]
    """

    def __init__(
        self,
        n_cards: int,
        n_heroes: int,
        embed_dim: int = 64,
        hidden_dim: int = 128,
        pad_idx: int = 0,
        card_embedding: nn.Embedding | None = None,
        hero_embedding: nn.Embedding | None = None,
    ):
        super().__init__()
        # Share embeddings with evaluator if provided, else create own
        self.card_embed = card_embedding or nn.Embedding(n_cards, embed_dim, padding_idx=pad_idx)
        self.hero_embed = hero_embedding or nn.Embedding(n_heroes, embed_dim, padding_idx=pad_idx)

        self.scorer = nn.Sequential(
            nn.Linear(embed_dim * 2, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
        )

    def forward(
        self,
        hero_ids: torch.Tensor,           # [B]
        candidate_card_ids: torch.Tensor,  # [B, C]
    ) -> torch.Tensor:
        """Returns inclusion logits [B, C]."""
        card_emb = self.card_embed(candidate_card_ids)     # [B, C, D]
        hero_emb = self.hero_embed(hero_ids).unsqueeze(1)  # [B, 1, D]
        hero_emb = hero_emb.expand_as(card_emb)            # [B, C, D]

        combined = torch.cat([card_emb, hero_emb], dim=-1)  # [B, C, 2D]
        return self.scorer(combined).squeeze(-1)  # [B, C]


# ---------------------------------------------------------------------------
# Dataset for training from game outcomes
# ---------------------------------------------------------------------------

class DeckWinDataset(torch.utils.data.Dataset):
    """Dataset of (hero, deck, opp_hero, win) tuples from game data.

    Each game produces TWO samples:
        (hero_1, deck_1, hero_2, won_1)
        (hero_2, deck_2, hero_1, won_2)

    Card lists are padded to max_cards.
    """

    def __init__(
        self,
        games_db_path: str | Path,
        vocab: CardVocab,
        max_cards: int = 80,
        include_ties: bool = False,
    ):
        self.vocab = vocab
        self.max_cards = max_cards
        self.samples: list[dict] = []

        conn = sqlite3.connect(str(games_db_path))
        rows = conn.execute(
            "SELECT p1_hero, p2_hero, p1_decklist, p2_decklist, winner "
            "FROM decks WHERE winner IS NOT NULL"
            + ("" if include_ties else " AND winner IN (1, 2)")
        ).fetchall()
        conn.close()

        for p1_hero, p2_hero, p1_deck_json, p2_deck_json, winner in rows:
            p1_deck = json.loads(p1_deck_json)
            p2_deck = json.loads(p2_deck_json)

            # Extract card lists from deck JSON
            p1_cards = self._extract_card_slugs(p1_deck)
            p2_cards = self._extract_card_slugs(p2_deck)

            # Sample 1: player 1's perspective
            self.samples.append({
                "hero_slug": p1_hero,
                "opp_hero_slug": p2_hero,
                "card_slugs": p1_cards,
                "won": 1.0 if winner == 1 else 0.0,
            })
            # Sample 2: player 2's perspective
            self.samples.append({
                "hero_slug": p2_hero,
                "opp_hero_slug": p1_hero,
                "card_slugs": p2_cards,
                "won": 1.0 if winner == 2 else 0.0,
            })

    @staticmethod
    def _extract_card_slugs(deck_dict: dict) -> list[str]:
        """Extract flat list of card slugs from a Talishar deck dict."""
        slugs: list[str] = []
        for key in ("deck", "head", "chest", "arms", "legs", "weapons", "offhand"):
            val = deck_dict.get(key)
            if isinstance(val, list):
                slugs.extend(val)
            elif isinstance(val, str) and val:
                slugs.append(val)
        return slugs

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        sample = self.samples[idx]
        card_ids, counts = self.vocab.encode_deck(sample["card_slugs"])

        # Pad / truncate to max_cards
        n = len(card_ids)
        if n > self.max_cards:
            card_ids = card_ids[:self.max_cards]
            counts = counts[:self.max_cards]
            n = self.max_cards

        pad_len = self.max_cards - n
        card_ids_padded = card_ids + [self.vocab.pad_idx] * pad_len
        counts_padded = counts + [0] * pad_len
        pad_mask = [False] * n + [True] * pad_len

        return {
            "hero_id": torch.tensor(self.vocab.hero_id(sample["hero_slug"]), dtype=torch.long),
            "opp_hero_id": torch.tensor(self.vocab.hero_id(sample["opp_hero_slug"]), dtype=torch.long),
            "card_ids": torch.tensor(card_ids_padded, dtype=torch.long),
            "counts": torch.tensor(counts_padded, dtype=torch.float),
            "pad_mask": torch.tensor(pad_mask, dtype=torch.bool),
            "label": torch.tensor(sample["won"], dtype=torch.float),
        }


# ---------------------------------------------------------------------------
# Dataset from fablazing play-rate data (bootstrap training)
# ---------------------------------------------------------------------------

class FablazingBootstrapDataset(torch.utils.data.Dataset):
    """Bootstrap training data from fablazing card play rates.

    Creates synthetic training samples across a quality spectrum:
    - "meta" decks: top cards by play rate -> label 0.75
    - "good" decks: top cards with some noise -> label 0.60
    - "mediocre" decks: mid-frequency cards -> label 0.40
    - "bad" decks: random/low-frequency cards -> label 0.20

    Labels represent deck quality (independent of hero win rate).
    Hero win rate is used as a secondary modifier (+/- 0.05).
    """

    def __init__(
        self,
        db_path: str | Path,
        vocab: CardVocab,
        samples_per_hero: int = 50,
        max_cards: int = 80,
        seed: int = 42,
    ):
        self.vocab = vocab
        self.max_cards = max_cards
        self.samples: list[dict] = []

        rng = _random_mod.Random(seed)
        conn = sqlite3.connect(str(db_path))

        # Load meta weights for opponent sampling
        meta = load_meta_weights(db_path)
        hero_slugs = list(meta.keys())
        hero_weights = [meta[h] for h in hero_slugs]

        heroes = conn.execute(
            "SELECT hero_slug, hero_name, win_rate FROM heroes WHERE format = 'cc'"
        ).fetchall()

        for hero_slug, hero_name, hero_wr in heroes:
            if hero_wr is None:
                hero_wr = 0.5
            # Hero WR modifier: small adjustment so stronger heroes get slightly higher labels
            hero_mod = (hero_wr - 0.5) * 0.1  # +/- 0.05 max

            # Get cards sorted by frequency
            cards = conn.execute(
                "SELECT card_slug, card_type, frequency, avg_copies "
                "FROM card_stats WHERE hero_slug = ? AND format = 'cc' "
                "ORDER BY frequency DESC",
                (hero_slug,),
            ).fetchall()

            if len(cards) < 10:
                continue

            equip = [(s, f, a) for s, t, f, a in cards if t == "equipment"]
            deck_cards = [(s, f, a) for s, t, f, a in cards if t != "equipment"]

            for _ in range(samples_per_hero):
                # Pick an opponent hero from meta distribution
                opp_hero = rng.choices(hero_slugs, weights=hero_weights, k=1)[0]

                # Quality tier: 25% meta, 25% good, 25% mediocre, 25% bad
                tier = rng.random()
                card_slugs: list[str] = []

                # Equipment (top 5)
                for slug, freq, avg in equip[:5]:
                    card_slugs.append(slug)

                if tier < 0.25:
                    # Meta: strict top cards by play rate
                    for slug, freq, avg_copies in deck_cards:
                        if len(card_slugs) >= 80:
                            break
                        copies = max(1, min(3, round(avg_copies or 1)))
                        card_slugs.extend([slug] * copies)
                    label = 0.75 + hero_mod
                elif tier < 0.50:
                    # Good: top cards with noise (slight shuffling)
                    noisy = list(deck_cards)
                    # Shuffle within sliding windows to preserve approximate order
                    for i in range(0, len(noisy) - 4, 4):
                        window = noisy[i:i+4]
                        rng.shuffle(window)
                        noisy[i:i+4] = window
                    for slug, freq, avg_copies in noisy:
                        if len(card_slugs) >= 80:
                            break
                        copies = max(1, min(3, round(avg_copies or 1)))
                        card_slugs.extend([slug] * copies)
                    label = 0.60 + hero_mod
                elif tier < 0.75:
                    # Mediocre: mid-frequency cards (skip top quarter)
                    mid_start = len(deck_cards) // 4
                    mid_cards = deck_cards[mid_start:] + deck_cards[:mid_start]
                    rng.shuffle(mid_cards)
                    for slug, freq, avg_copies in mid_cards:
                        if len(card_slugs) >= 80:
                            break
                        copies = rng.randint(1, 3)
                        card_slugs.extend([slug] * copies)
                    label = 0.40 + hero_mod
                else:
                    # Bad: fully random cards
                    shuffled = list(deck_cards)
                    rng.shuffle(shuffled)
                    for slug, freq, avg_copies in shuffled:
                        if len(card_slugs) >= 80:
                            break
                        copies = rng.randint(1, 3)
                        card_slugs.extend([slug] * copies)
                    label = 0.20 + hero_mod

                # Small noise on labels
                label = max(0.05, min(0.95, label + rng.gauss(0, 0.03)))

                self.samples.append({
                    "hero_slug": hero_slug,
                    "opp_hero_slug": opp_hero,
                    "card_slugs": card_slugs[:80],
                    "won": label,
                })

        conn.close()

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        sample = self.samples[idx]
        card_ids, counts = self.vocab.encode_deck(sample["card_slugs"])

        n = len(card_ids)
        if n > self.max_cards:
            card_ids = card_ids[:self.max_cards]
            counts = counts[:self.max_cards]
            n = self.max_cards

        pad_len = self.max_cards - n
        card_ids_padded = card_ids + [self.vocab.pad_idx] * pad_len
        counts_padded = counts + [0] * pad_len
        pad_mask = [False] * n + [True] * pad_len

        return {
            "hero_id": torch.tensor(self.vocab.hero_id(sample["hero_slug"]), dtype=torch.long),
            "opp_hero_id": torch.tensor(self.vocab.hero_id(sample["opp_hero_slug"]), dtype=torch.long),
            "card_ids": torch.tensor(card_ids_padded, dtype=torch.long),
            "counts": torch.tensor(counts_padded, dtype=torch.float),
            "pad_mask": torch.tensor(pad_mask, dtype=torch.bool),
            "label": torch.tensor(sample["won"], dtype=torch.float),
        }


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def build_evaluator(
    vocab: CardVocab,
    model_type: str = "deepsets",
    embed_dim: int = 64,
    hidden_dim: int = 128,
    n_heads: int = 4,
    n_layers: int = 2,
    dropout: float = 0.1,
) -> nn.Module:
    """Build a deck evaluator model.

    Args:
        vocab: CardVocab with card and hero vocabularies.
        model_type: 'deepsets' or 'set_transformer'.
    """
    if model_type == "deepsets":
        return DeepSetsEvaluator(
            n_cards=vocab.n_cards,
            n_heroes=vocab.n_heroes,
            embed_dim=embed_dim,
            hidden_dim=hidden_dim,
            pad_idx=vocab.pad_idx,
        )
    elif model_type == "set_transformer":
        return SetTransformerEvaluator(
            n_cards=vocab.n_cards,
            n_heroes=vocab.n_heroes,
            embed_dim=embed_dim,
            n_heads=n_heads,
            n_layers=n_layers,
            hidden_dim=hidden_dim,
            dropout=dropout,
            pad_idx=vocab.pad_idx,
        )
    else:
        raise ValueError(f"Unknown model type: {model_type}")


def save_checkpoint(
    path: str | Path,
    model: nn.Module,
    vocab: CardVocab,
    optimizer: Optional[torch.optim.Optimizer] = None,
    epoch: int = 0,
    metrics: Optional[dict] = None,
    model_type: str = "deepsets",
) -> None:
    """Save model checkpoint with vocabulary."""
    state = {
        "model_state_dict": model.state_dict(),
        "vocab": vocab.state_dict(),
        "model_type": model_type,
        "epoch": epoch,
        "metrics": metrics or {},
    }
    if optimizer is not None:
        state["optimizer_state_dict"] = optimizer.state_dict()
    torch.save(state, str(path))


def load_checkpoint(path: str | Path) -> dict:
    """Load model checkpoint. Returns dict with model, vocab, metadata."""
    return torch.load(str(path), map_location="cpu", weights_only=False)
