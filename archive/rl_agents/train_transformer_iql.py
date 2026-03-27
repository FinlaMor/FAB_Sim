"""CLI entrypoint for end-to-end transformer IQL training.

Trains the full stack jointly:
  - FABTransformerEncoder (slug embed + zone embed + attr proj + transformer)
  - ActionEncoder (slug embed shared with state encoder + mode embed)
  - Hero-specific embedding layer (per-hero additive bias on state embedding)
  - IQL Q1/Q2, V, Actor heads

Data flow:
  talishar_games.db → HDF5 cache → TransformerIQLTrainer.fit()

The HDF5 cache (at <db_path_stem>_transformer.h5) is built once and reused
on subsequent runs unless the game count changes or --force-rebuild is passed.

Usage:
    python -m rl_agents.train_transformer_iql \\
        --talishar-db data/talishar_games.db \\
        --slug-index card_data/slug_index.json \\
        --steps 20000 --device dml
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
import sys
import time

import torch

from rl_agents.dataset_adapter import build_transformer_hdf5_from_talishar_db
from rl_agents.fab_transformer import (
    build_card_vocab_and_attrs,
    build_hero_vocab,
)
from rl_agents.talishar_iql import (
    TalisharHDF5Dataset,
    TransformerIQLConfig,
    TransformerIQLTrainer,
)
from rl_agents.utils.device import default_device as _default_device


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="End-to-end transformer IQL training for FAB player bot"
    )

    # Data
    p.add_argument("--talishar-db", required=True,
                   help="Path to talishar_games.db")
    p.add_argument("--slug-index", default="card_data/slug_index.json",
                   help="Path to slug_index.json (default: card_data/slug_index.json)")
    p.add_argument("--hdf5-cache", default="",
                   help="HDF5 cache path (default: <db_stem>_transformer.h5 alongside DB)")
    p.add_argument("--force-rebuild", action="store_true",
                   help="Force HDF5 cache rebuild even if game count matches")
    p.add_argument("--game-ids", nargs="*", default=None,
                   help="Optional subset of game_id strings to include")
    p.add_argument("--reward-mode", choices=["terminal", "rtg"], default="rtg",
                   help="Reward shaping mode (default: rtg)")
    p.add_argument("--gamma", type=float, default=0.97,
                   help="Discount factor for RTG (default: 0.97)")

    # Training
    p.add_argument("--steps", type=int, default=20000,
                   help="Training steps (default: 20000)")
    p.add_argument("--batch-size", type=int, default=512,
                   help="Batch size (default: 512)")
    p.add_argument("--device", type=str, default=_default_device(),
                   help="Training device (default: auto)")
    p.add_argument("--log-every", type=int, default=50)

    # Transformer
    p.add_argument("--d-model", type=int, default=128)
    p.add_argument("--num-heads", type=int, default=4)
    p.add_argument("--num-layers", type=int, default=3)
    p.add_argument("--ff-dim", type=int, default=256)
    p.add_argument("--transformer-dropout", type=float, default=0.1)

    # IQL heads
    p.add_argument("--hidden-dim", type=int, default=512)
    p.add_argument("--mlp-dropout", type=float, default=0.1)
    p.add_argument("--hidden-layers", type=int, default=2)
    p.add_argument("--expectile", type=float, default=0.7,
                   help="Expectile for V-loss (default: 0.7, lower = more conservative)")
    p.add_argument("--temperature", type=float, default=1.0)
    p.add_argument("--max-weight", type=float, default=100.0)
    p.add_argument("--disable-advantage-normalization", action="store_true")

    # Learning rates
    p.add_argument("--lr-encoder", type=float, default=1e-4)
    p.add_argument("--lr-q", type=float, default=6e-5)
    p.add_argument("--lr-v", type=float, default=3e-4)
    p.add_argument("--lr-actor", type=float, default=3e-4)
    p.add_argument("--weight-decay", type=float, default=1e-4)
    p.add_argument("--grad-clip", type=float, default=5.0,
                   help="Legacy global grad clip (fallback)")
    p.add_argument("--grad-clip-q", type=float, default=1.0,
                   help="Grad clip for Q heads (default: 1.0)")
    p.add_argument("--grad-clip-v", type=float, default=2.0,
                   help="Grad clip for V head (default: 2.0)")
    p.add_argument("--grad-clip-actor", type=float, default=5.0,
                   help="Grad clip for actor head (default: 5.0)")
    p.add_argument("--grad-clip-encoder", type=float, default=2.0,
                   help="Grad clip for encoder (default: 2.0)")
    p.add_argument("--reward-scale", type=float, default=4.0)
    p.add_argument("--tau", type=float, default=0.005)

    # Output
    p.add_argument("--out-dir", type=str, default="data_collection/iql_runs",
                   help="Parent directory for run outputs")
    p.add_argument("--run-name", type=str, default="",
                   help="Run sub-directory name (default: timestamped)")
    p.add_argument("--resume-from", type=str, default="",
                   help="Checkpoint to resume from")
    p.add_argument("--reset-optimizers", action="store_true",
                   help="Reset optimizer states on resume (fresh Adam momentum)")

    return p


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    print(f"[tiql] python={sys.executable}", flush=True)
    print(f"[tiql] torch={torch.__version__}", flush=True)
    print(f"[tiql] device={args.device}", flush=True)

    db_path = str(args.talishar_db)
    slug_index = str(args.slug_index)

    # HDF5 cache path — default alongside DB
    if args.hdf5_cache:
        hdf5_path = args.hdf5_cache
    else:
        hdf5_path = str(Path(db_path).with_suffix("")) + "_transformer.h5"

    # Build or reuse HDF5 cache
    n_transitions = build_transformer_hdf5_from_talishar_db(
        db_path=db_path,
        slug_index_path=slug_index,
        out_path=hdf5_path,
        reward_mode=args.reward_mode,
        gamma=args.gamma,
        game_ids=args.game_ids,
        force_rebuild=args.force_rebuild,
    )

    if n_transitions == 0:
        print("[tiql] ERROR: No transitions available for training.", file=sys.stderr)
        return 1

    # Load attr_table and hero vocab for model construction
    print(f"[tiql] Loading slug index from {slug_index} ...", flush=True)
    _vocab, attrs_np = build_card_vocab_and_attrs(slug_index)
    hero_vocab = build_hero_vocab(slug_index)
    vocab_size = len(_vocab)
    hero_vocab_size = len(hero_vocab)
    attr_table = torch.tensor(attrs_np, dtype=torch.float32)

    print(
        f"[tiql] vocab_size={vocab_size}  hero_vocab_size={hero_vocab_size} "
        f"transitions={n_transitions}",
        flush=True,
    )

    # Build config
    config = TransformerIQLConfig(
        d_model=args.d_model,
        num_heads=args.num_heads,
        num_layers=args.num_layers,
        ff_dim=args.ff_dim,
        transformer_dropout=args.transformer_dropout,
        slug_vocab_size=vocab_size,
        hero_vocab_size=hero_vocab_size,
        hidden_dim=args.hidden_dim,
        hidden_layers=args.hidden_layers,
        mlp_dropout=args.mlp_dropout,
        gamma=args.gamma,
        expectile=args.expectile,
        temperature=args.temperature,
        max_weight=args.max_weight,
        normalize_advantages=not args.disable_advantage_normalization,
        batch_size=args.batch_size,
        lr_encoder=args.lr_encoder,
        lr_q=args.lr_q,
        lr_v=args.lr_v,
        lr_actor=args.lr_actor,
        weight_decay=args.weight_decay,
        grad_clip=args.grad_clip,
        grad_clip_q=args.grad_clip_q,
        grad_clip_v=args.grad_clip_v,
        grad_clip_actor=args.grad_clip_actor,
        grad_clip_encoder=args.grad_clip_encoder,
        reward_scale=args.reward_scale,
        tau=args.tau,
        device=args.device,
    )

    # Build or resume trainer
    resumed = False
    if args.resume_from and Path(args.resume_from).exists():
        # Only resume from transformer_iql checkpoints — skip legacy flat-tensor ones
        try:
            _peek = torch.load(args.resume_from, map_location="cpu", weights_only=False)
            _ckpt_type = (_peek.get("extra") or {}).get("checkpoint_type", "")
            if _ckpt_type == "transformer_iql":
                print(f"[tiql] Resuming from {args.resume_from}", flush=True)
                # Pass CLI hyperparams as overrides so they take effect on resume
                _overrides = {
                    "batch_size": config.batch_size,
                    "lr_q": config.lr_q,
                    "lr_v": config.lr_v,
                    "lr_actor": config.lr_actor,
                    "lr_encoder": config.lr_encoder,
                    "weight_decay": config.weight_decay,
                    "grad_clip": config.grad_clip,
                    "grad_clip_q": config.grad_clip_q,
                    "grad_clip_v": config.grad_clip_v,
                    "grad_clip_actor": config.grad_clip_actor,
                    "grad_clip_encoder": config.grad_clip_encoder,
                    "reward_scale": config.reward_scale,
                    "expectile": config.expectile,
                    "temperature": config.temperature,
                    "max_weight": config.max_weight,
                }
                trainer = TransformerIQLTrainer.from_checkpoint(
                    args.resume_from, attr_table=attr_table, device=args.device,
                    reset_optimizers=args.reset_optimizers,
                    config_overrides=_overrides,
                )
                resumed = True
            else:
                print(f"[tiql] Skipping resume — checkpoint is type {_ckpt_type!r}, not transformer_iql", flush=True)
            del _peek
        except Exception as e:
            print(f"[tiql] Skipping resume — failed to load checkpoint: {e}", flush=True)
    if not resumed:
        trainer = TransformerIQLTrainer(config, attr_table)

    # Dataset
    dataset = TalisharHDF5Dataset(hdf5_path, expected_vocab_size=vocab_size)
    print(f"[tiql] dataset ready: {len(dataset)} transitions", flush=True)

    # Output directory
    run_name = args.run_name or time.strftime("tiql_%Y%m%d_%H%M%S")
    run_dir = Path(args.out_dir) / run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    # Train
    history = trainer.fit(dataset, num_steps=args.steps, log_every=args.log_every)
    dataset.close()

    # Save checkpoint
    interrupted = history and history[-1].get("step", args.steps) < args.steps
    ckpt_name = "checkpoint_interrupted.pt" if interrupted else "checkpoint_final.pt"
    ckpt_path = run_dir / ckpt_name
    trainer.save_checkpoint(
        str(ckpt_path),
        extra={
            "run_name": run_name,
            "num_steps": args.steps,
            "n_transitions": n_transitions,
            "talishar_db": db_path,
            "hdf5_cache": hdf5_path,
            "slug_index": slug_index,
            "reward_mode": args.reward_mode,
            "game_ids": args.game_ids,
            # Tag so inference code can detect this is a transformer checkpoint
            "checkpoint_type": "transformer_iql",
        },
    )

    # Save metrics (same schema as train_iql.py for pipeline compatibility)
    metrics = {
        "run_name": run_name,
        "checkpoint_type": "transformer_iql",
        "dataset": {
            "n_transitions": n_transitions,
            "hdf5_cache": hdf5_path,
            "talishar_db": db_path,
            "reward_mode": args.reward_mode,
            "game_ids": args.game_ids,
        },
        "config": asdict(config),
        "final": history[-1] if history else {},
        "history_tail": history[-min(50, len(history)):],
        "checkpoint": str(ckpt_path),
    }

    metrics_path = run_dir / "metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    print(f"[tiql] checkpoint: {ckpt_path}", flush=True)
    print(f"[tiql] metrics:    {metrics_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
