"""Masked Card Prediction pre-training for GameTransformerEncoder.

Trains the transformer's self-attention to learn card relationships by
randomly masking one card token and predicting its slug index.  This is
analogous to BERT's masked language modelling — the model must understand
which cards co-occur, which zones they belong to, and how they interact
to predict the hidden card.

Usage:
    from encoder.pretrain_masked import MaskedPretrainer, pretrain_loop

    pretrainer = MaskedPretrainer(transformer, mask_ratio=0.15)
    pretrain_loop(pretrainer, packed_states, num_steps=5000)
"""

from __future__ import annotations

import random
import time
from typing import Optional

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from encoder.game_transformer import (
    GameTransformerEncoder,
    MAX_STORAGE_SEQ_LEN,
    _N_META,
    META,
)


# Special index used for the [MASK] token — slug_vocab_size is the last valid
# index (padding), so MASK uses slug_vocab_size itself (the embedding is learned).
# We rely on the transformer's slug_embed having slug_vocab_size+1 entries,
# where index 0 = padding.  We'll add one more entry for the mask token.


class MaskedPretrainer(nn.Module):
    """Wraps a GameTransformerEncoder with a masked-card classification head.

    During forward:
    1. Unpack the state features (same as forward_packed_batch)
    2. Randomly mask ``mask_ratio`` of non-padding card tokens
    3. Run the transformer
    4. Classify masked positions against the slug vocabulary
    5. Return cross-entropy loss
    """

    def __init__(
        self,
        transformer: GameTransformerEncoder,
        mask_ratio: float = 0.15,
    ):
        super().__init__()
        self.transformer = transformer
        self.mask_ratio = mask_ratio

        d_model = transformer.d_model
        vocab_size = transformer.slug_vocab_size  # prediction target size

        # Classification head: hidden state → slug prediction
        self.cls_head = nn.Sequential(
            nn.Linear(d_model, d_model),
            nn.GELU(),
            nn.LayerNorm(d_model),
            nn.Linear(d_model, vocab_size + 1),  # +1 for padding index 0
        )

        # Learnable [MASK] embedding (replaces the card token embedding)
        self.mask_embed = nn.Parameter(torch.randn(d_model) * 0.02)

    def forward(
        self,
        packed: torch.Tensor,  # (B, packed_size)
    ) -> dict[str, torch.Tensor]:
        """Run masked prediction and return loss + metrics.

        Returns dict with:
            loss: scalar cross-entropy loss
            accuracy: fraction of correctly predicted masked tokens
            n_masked: total number of masked tokens in batch
        """
        device = packed.device
        B = packed.shape[0]
        T = MAX_STORAGE_SEQ_LEN
        gt = self.transformer

        # ── Unpack (mirrors forward_packed_batch) ────────────────────────
        seq_lens       = packed[:, 0].long()
        hero_positions = packed[:, 1].long()
        meta_vecs      = packed[:, 2:2 + _N_META]

        offset_slug = 2 + _N_META
        offset_zone = offset_slug + T
        offset_pos  = offset_zone + T

        slug_idxs = packed[:, offset_slug:offset_zone].long().clamp(min=0, max=gt.slug_vocab_size)
        zone_segs = packed[:, offset_zone:offset_pos].long().clamp(min=0)
        pos_idxs  = packed[:, offset_pos:offset_pos + T].long().clamp(min=0)

        # ── Create mask: select random non-padding card positions ────────
        # valid_mask: True where there's a real token
        arange_t = torch.arange(T, device=device).unsqueeze(0).expand(B, -1)
        valid_mask = arange_t < seq_lens.unsqueeze(1)  # (B, T)

        # Don't mask the hero token (important context signal)
        hero_mask = torch.zeros_like(valid_mask)
        for i in range(B):
            hp = hero_positions[i].item()
            if 0 <= hp < T:
                hero_mask[i, hp] = True
        maskable = valid_mask & ~hero_mask  # (B, T)

        # Random mask: each maskable position has mask_ratio chance
        rand_vals = torch.rand(B, T, device=device)
        to_mask = maskable & (rand_vals < self.mask_ratio)  # (B, T)

        # Ensure at least one token is masked per sample (if possible)
        n_masked_per_sample = to_mask.sum(dim=1)
        for i in range(B):
            if n_masked_per_sample[i] == 0 and maskable[i].any():
                candidates = maskable[i].nonzero(as_tuple=False).squeeze(-1)
                idx = candidates[torch.randint(len(candidates), (1,))].item()
                to_mask[i, idx] = True

        # Save original slug indices as labels before masking
        labels = slug_idxs.clone()  # (B, T)

        # ── Build token embeddings (same as forward_packed_batch) ────────
        slug_emb = gt.slug_embed(slug_idxs)
        seg_emb  = gt.zone_segment_embed(zone_segs)
        pos_emb  = gt.position_embed(pos_idxs)
        card_feats = gt.card_feats_lookup[slug_idxs]
        card_proj  = gt.card_feat_proj(card_feats)

        card_token_embs = slug_emb + seg_emb + pos_emb + card_proj  # (B, T, d_model)

        # Replace masked positions with [MASK] embedding
        mask_expanded = to_mask.unsqueeze(-1).float()  # (B, T, 1)
        mask_emb = self.mask_embed.unsqueeze(0).unsqueeze(0).expand(B, T, -1)
        # Keep zone + position embeddings so the model knows WHERE the mask is,
        # but replace the slug + card_feat content
        card_token_embs = card_token_embs * (1 - mask_expanded) + \
            (mask_emb + seg_emb + pos_emb) * mask_expanded

        # ── Build full sequence with CLS + META ──────────────────────────
        meta_proj_out = gt.meta_proj(meta_vecs)
        cls_exp = gt.cls_token.expand(B, -1).unsqueeze(1)

        meta_zone_idx = torch.full((B, 1), META, dtype=torch.long, device=device)
        meta_pos_idx  = torch.zeros(B, 1, dtype=torch.long, device=device)
        meta_seg_emb  = gt.zone_segment_embed(meta_zone_idx)
        meta_pos_emb  = gt.position_embed(meta_pos_idx)
        meta_token_embs = meta_seg_emb + meta_pos_emb + meta_proj_out.unsqueeze(1)

        token_embs = torch.cat([cls_exp, meta_token_embs, card_token_embs], dim=1)

        # Padding mask
        seq_with_prefix = seq_lens + 2
        arange_full = torch.arange(2 + T, device=device).unsqueeze(0).expand(B, -1)
        padding_mask = arange_full >= seq_with_prefix.unsqueeze(1)

        # ── Run transformer ──────────────────────────────────────────────
        out = gt.transformer(token_embs, src_key_padding_mask=padding_mask)

        # ── Extract masked positions and classify ────────────────────────
        # Card tokens start at position 2 in the full sequence
        card_out = out[:, 2:, :]  # (B, T, d_model)

        # Gather only masked positions
        masked_hidden = card_out[to_mask]   # (N_masked, d_model)
        masked_labels = labels[to_mask]     # (N_masked,)

        if masked_hidden.shape[0] == 0:
            return {
                "loss": torch.tensor(0.0, device=device, requires_grad=True),
                "accuracy": 0.0,
                "n_masked": 0,
            }

        logits = self.cls_head(masked_hidden)  # (N_masked, vocab_size+1)
        loss = F.cross_entropy(logits, masked_labels)

        with torch.no_grad():
            preds = logits.argmax(dim=-1)
            accuracy = (preds == masked_labels).float().mean().item()

        return {
            "loss": loss,
            "accuracy": accuracy,
            "n_masked": int(masked_hidden.shape[0]),
        }


def pretrain_loop(
    pretrainer: MaskedPretrainer,
    packed_states: torch.Tensor,
    num_steps: int = 5000,
    batch_size: int = 128,
    lr: float = 1e-4,
    log_every: int = 100,
    device: Optional[torch.device] = None,
    checkpoint_dir: Optional[str] = None,
) -> list[dict]:
    """Run the masked card prediction pre-training loop.

    Args:
        pretrainer: MaskedPretrainer wrapping the transformer
        packed_states: (N, packed_size) tensor of packed state features
        num_steps: number of training steps
        batch_size: batch size
        lr: learning rate
        log_every: log metrics every N steps
        device: device to train on (default: CPU)
        checkpoint_dir: if set, save checkpoints every 1000 steps

    Returns:
        List of metric dicts from logged steps
    """
    if device is None:
        device = torch.device("cpu")

    pretrainer = pretrainer.to(device)
    pretrainer.train()
    packed_states = packed_states.to(device)

    N = len(packed_states)
    optimizer = torch.optim.AdamW(pretrainer.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=num_steps, eta_min=lr * 0.01,
    )

    rng = torch.Generator(device="cpu").manual_seed(42)
    history: list[dict] = []
    t0 = time.time()

    print(f"[pretrain] starting masked card prediction: {num_steps} steps, "
          f"batch_size={batch_size}, N={N}, device={device}", flush=True)

    for step in range(1, num_steps + 1):
        idx = torch.randint(0, N, (batch_size,), generator=rng)
        batch = packed_states[idx]

        result = pretrainer(batch)
        loss = result["loss"]

        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        nn.utils.clip_grad_norm_(pretrainer.parameters(), 5.0)
        optimizer.step()
        scheduler.step()

        if log_every > 0 and (step == 1 or step % log_every == 0 or step == num_steps):
            elapsed = time.time() - t0
            entry = {
                "step": step,
                "loss": float(loss.item()),
                "accuracy": result["accuracy"],
                "n_masked": result["n_masked"],
                "elapsed": elapsed,
            }
            history.append(entry)
            print(
                f"[pretrain] step={step:6d} loss={entry['loss']:.4f} "
                f"acc={entry['accuracy']:.3f} masked={entry['n_masked']} "
                f"({elapsed:.1f}s)",
                flush=True,
            )

        if checkpoint_dir and step % 1000 == 0:
            from pathlib import Path
            ckpt_path = Path(checkpoint_dir) / f"pretrain_step{step}.pt"
            ckpt_path.parent.mkdir(parents=True, exist_ok=True)
            torch.save({
                "transformer_state_dict": pretrainer.transformer.state_dict(),
                "cls_head_state_dict": pretrainer.cls_head.state_dict(),
                "mask_embed": pretrainer.mask_embed.data,
                "optimizer_state_dict": optimizer.state_dict(),
                "step": step,
            }, str(ckpt_path))

    return history
