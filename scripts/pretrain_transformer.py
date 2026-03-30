"""Pre-train the GameTransformerEncoder via masked card prediction.

Loads packed state features from replay.db, trains the transformer to
predict randomly masked card tokens, and saves the updated weights back
into the embedder bundle.

Usage:
    python scripts/pretrain_transformer.py \
        --db-path data/replay.db \
        --embedder-bundle checkpoints/embedder_bundle.pt \
        --steps 5000 --batch-size 128
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from encoder.game_transformer import GameTransformerEncoder, prime_dummy_vocab
from encoder.pretrain_masked import MaskedPretrainer, pretrain_loop
from rl_agents.embedder_bundle import load_embedder_bundle


def _load_packed_states(db_path: str) -> torch.Tensor:
    """Load all packed state feature arrays from replay.db."""
    import sqlite3

    conn = sqlite3.connect(db_path)

    # Check if state_features column has data
    row = conn.execute(
        "SELECT state_features FROM embeddings WHERE state_features IS NOT NULL LIMIT 1"
    ).fetchone()
    if row is None:
        conn.close()
        raise ValueError(f"No packed state features found in {db_path}. "
                         "Run game collection with the transformer embedder first.")

    # Load all state features
    rows = conn.execute(
        "SELECT state_features FROM embeddings WHERE state_features IS NOT NULL"
    ).fetchall()
    conn.close()

    arrays = [np.frombuffer(r[0], dtype=np.float32) for r in rows]
    stacked = np.stack(arrays, axis=0)
    return torch.from_numpy(stacked)


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-train transformer via masked card prediction")
    parser.add_argument("--db-path", type=str, required=True, help="Path to replay.db")
    parser.add_argument("--embedder-bundle", type=str, required=True, help="Path to embedder_bundle.pt")
    parser.add_argument("--steps", type=int, default=5000, help="Training steps")
    parser.add_argument("--batch-size", type=int, default=128, help="Batch size")
    parser.add_argument("--lr", type=float, default=1e-4, help="Learning rate")
    parser.add_argument("--mask-ratio", type=float, default=0.15, help="Fraction of tokens to mask")
    parser.add_argument("--log-every", type=int, default=100, help="Log every N steps")
    parser.add_argument("--device", type=str, default="cpu", help="Device (cpu recommended)")
    parser.add_argument("--resume", type=str, default="", help="Resume from pretrain checkpoint")
    args = parser.parse_args()

    print(f"[pretrain] Loading packed states from {args.db_path}...", flush=True)
    packed_states = _load_packed_states(args.db_path)
    print(f"[pretrain] Loaded {len(packed_states)} states, shape={packed_states.shape}", flush=True)

    print(f"[pretrain] Loading embedder bundle from {args.embedder_bundle}...", flush=True)
    bundle = load_embedder_bundle(args.embedder_bundle)

    # Build transformer from bundle
    from engine.card import CardDB
    from encoder.card_embedder import SlugVocab
    from config import SLUG_INDEX_PATH

    card_db = CardDB(SLUG_INDEX_PATH)
    slug_vocab = SlugVocab.from_card_db(card_db)
    prime_dummy_vocab(card_db)

    gt_d_model       = int(bundle.get("game_transformer_d_model", 256))
    gt_n_heads       = int(bundle.get("game_transformer_n_heads", 8))
    gt_n_layers      = int(bundle.get("game_transformer_n_layers", 4))
    gt_hero_head_dim = int(bundle.get("game_transformer_hero_head_dim", 64))

    transformer = GameTransformerEncoder(
        slug_vocab_size=slug_vocab.size,
        d_model=gt_d_model,
        n_heads=gt_n_heads,
        n_layers=gt_n_layers,
        hero_head_dim=gt_hero_head_dim,
    )

    # Load existing weights (shape-safe)
    if "game_transformer_state_dict" in bundle:
        saved_sd = bundle["game_transformer_state_dict"]
        model_sd = transformer.state_dict()
        filtered = {k: v for k, v in saved_sd.items()
                    if k in model_sd and model_sd[k].shape == v.shape}
        transformer.load_state_dict(filtered, strict=False)
        print(f"[pretrain] Loaded {len(filtered)}/{len(model_sd)} transformer weights from bundle", flush=True)

    transformer.set_card_feats_lookup(card_db)

    # Build pretrainer
    pretrainer = MaskedPretrainer(transformer, mask_ratio=args.mask_ratio)

    # Resume from checkpoint if specified
    start_step = 0
    if args.resume and Path(args.resume).exists():
        ckpt = torch.load(args.resume, map_location="cpu", weights_only=False)
        transformer.load_state_dict(ckpt["transformer_state_dict"])
        pretrainer.cls_head.load_state_dict(ckpt["cls_head_state_dict"])
        pretrainer.mask_embed.data = ckpt["mask_embed"]
        start_step = ckpt.get("step", 0)
        print(f"[pretrain] Resumed from {args.resume} at step {start_step}", flush=True)

    device = torch.device(args.device)
    checkpoint_dir = str(Path(args.embedder_bundle).parent / "pretrain_ckpts")

    history = pretrain_loop(
        pretrainer=pretrainer,
        packed_states=packed_states,
        num_steps=args.steps,
        batch_size=args.batch_size,
        lr=args.lr,
        log_every=args.log_every,
        device=device,
        checkpoint_dir=checkpoint_dir,
    )

    # Save trained transformer weights back into the embedder bundle
    print(f"[pretrain] Updating embedder bundle at {args.embedder_bundle}...", flush=True)
    bundle["game_transformer_state_dict"] = transformer.state_dict()
    bundle["game_transformer_card_feats_populated"] = True
    torch.save(bundle, args.embedder_bundle)
    print(f"[pretrain] Bundle updated with pre-trained transformer weights", flush=True)

    if history:
        final = history[-1]
        print(f"[pretrain] Final: loss={final['loss']:.4f} accuracy={final['accuracy']:.3f}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
