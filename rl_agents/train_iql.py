"""CLI entrypoint for offline IQL training on ReplayDB embeddings."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

import torch

from rl_agents.dataset_adapter import ReplayDataset, build_iql_tensors_from_replay_db
from rl_agents.embedder_bundle import load_embedder_bundle, resolve_embedder_bundle_path
from rl_agents.iql import IQLConfig, IQLTrainer, ResidualAdapter
from rl_agents.utils.device import default_device as _default_device, resolve_device as _resolve_device


def _build_e2e_encoders(embedder_bundle: dict, device: str):
    """Build GameTransformerEncoder and ActionEmbedder from bundle for end-to-end training.

    Returns (transformer, action_embedder) or (None, None) if bundle lacks transformer.
    """
    if "game_transformer_state_dict" not in embedder_bundle:
        return None, None

    try:
        from engine.card import CardDB
        from encoder.card_embedder import SlugVocab
        from encoder.action_embedder import ActionEmbedder
        from encoder.game_transformer import GameTransformerEncoder, prime_dummy_vocab
        from config import SLUG_INDEX_PATH

        card_db = CardDB(SLUG_INDEX_PATH)
        slug_vocab = SlugVocab.from_card_db(card_db)
        prime_dummy_vocab(card_db)

        gt_d_model       = int(embedder_bundle.get("game_transformer_d_model", 256))
        gt_n_heads       = int(embedder_bundle.get("game_transformer_n_heads", 8))
        gt_n_layers      = int(embedder_bundle.get("game_transformer_n_layers", 4))
        gt_hero_head_dim = int(embedder_bundle.get("game_transformer_hero_head_dim", 64))

        transformer = GameTransformerEncoder(
            slug_vocab_size=slug_vocab.size,
            d_model=gt_d_model,
            n_heads=gt_n_heads,
            n_layers=gt_n_layers,
            hero_head_dim=gt_hero_head_dim,
        )
        # Shape-safe load (handles stale bundles gracefully)
        gt_sd = embedder_bundle["game_transformer_state_dict"]
        model_sd = transformer.state_dict()
        filtered_sd = {k: v for k, v in gt_sd.items() if k in model_sd and model_sd[k].shape == v.shape}
        transformer.load_state_dict(filtered_sd, strict=False)
        transformer.set_card_feats_lookup(card_db)

        d_model = int(embedder_bundle.get("d_model", 128))
        ae = ActionEmbedder(
            d_model=d_model,
            slug_vocab_size=slug_vocab.size,
            slug_vocab=slug_vocab,
        )
        ae_sd = {**{f"card_embedder.{k}": v for k, v in embedder_bundle.get("card_embedder_state_dict", {}).items()},
                 **embedder_bundle.get("action_embedder_state_dict", {})}
        ae_model_sd = ae.state_dict()
        ae_filtered = {k: v for k, v in ae_sd.items() if k in ae_model_sd and ae_model_sd[k].shape == v.shape}
        ae.load_state_dict(ae_filtered, strict=False)

        return transformer, ae
    except Exception as e:
        print(f"[iql] WARNING: could not build end-to-end encoders: {e}", flush=True)
        return None, None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train an IQL model on FAB replay embeddings")

    parser.add_argument("--db-path", type=str, default="", help="Path to replay sqlite DB")
    parser.add_argument("--dataset-pt", type=str, default="", help="Optional pre-built .pt tensor dataset")
    parser.add_argument("--embedder-bundle", type=str, default="", help="Optional path to the embedder bundle used to create the dataset")
    parser.add_argument("--game-ids", type=int, nargs="*", default=None, help="Optional subset of game IDs")
    parser.add_argument(
        "--next-state-mode",
        type=str,
        choices=["same-player", "global"],
        default="same-player",
        help="How s' is chosen from sequential transitions",
    )
    parser.add_argument("--save-dataset-pt", type=str, default="", help="Optional path to save the assembled dataset")

    parser.add_argument("--steps", type=int, default=2000)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--hidden-dim", type=int, default=512)
    parser.add_argument("--hidden-layers", type=int, default=2)
    parser.add_argument("--gamma", type=float, default=0.99)
    parser.add_argument("--expectile", type=float, default=0.7)
    parser.add_argument("--temperature", type=float, default=3.0)
    parser.add_argument("--max-weight", type=float, default=100.0)
    parser.add_argument("--lr-q", type=float, default=3e-4)
    parser.add_argument("--lr-v", type=float, default=3e-4)
    parser.add_argument("--lr-actor", type=float, default=3e-4)
    parser.add_argument("--lr-embedder", type=float, default=1e-4)
    parser.add_argument("--weight-decay", type=float, default=0.0)
    parser.add_argument("--grad-clip", type=float, default=10.0)
    parser.add_argument("--reward-scale", type=float, default=1.0)
    parser.add_argument(
        "--trainable-embedder",
        action="store_true",
        help="Enable trainable residual adapters over replay state/action embeddings",
    )
    parser.add_argument(
        "--embedder-hidden-dim",
        type=int,
        default=512,
        help="Hidden width for residual embedding adapters",
    )
    parser.add_argument(
        "--embedder-layers",
        type=int,
        default=2,
        help="Hidden layer count for residual embedding adapters",
    )
    parser.add_argument(
        "--reward-mode",
        type=str,
        choices=["terminal", "rtg"],
        default="terminal",
        help="'terminal' = sparse ±1 at game end; 'rtg' = discounted reward-to-go for every transition",
    )
    parser.add_argument(
        "--filter-timeout",
        action="store_true",
        help="Exclude games that ended on turn cap (timed-out / low-quality draws)",
    )
    parser.add_argument(
        "--normalize-rewards",
        action="store_true",
        help="Normalize rewards to zero mean and unit variance after all reward processing",
    )
    parser.add_argument(
        "--disable-advantage-normalization",
        action="store_true",
        help="Disable batch-wise advantage normalization before actor weighting",
    )
    parser.add_argument(
        "--rwbc-mode",
        action="store_true",
        help="Skip Q/V training and train the actor with return-weighted behavior cloning",
    )
    parser.add_argument("--device", type=str, default=_default_device())
    parser.add_argument("--log-every", type=int, default=100)
    parser.add_argument("--eval-ratio", type=float, default=0.1, help="Fraction of transitions held out for eval, in [0.0, 1.0). 0 disables eval.")

    parser.add_argument("--out-dir", type=str, default="data_collection/iql_runs")
    parser.add_argument("--run-name", type=str, default="")
    parser.add_argument("--resume-from", type=str, default="", help="Path to checkpoint to resume training from")
    parser.add_argument("--experiment-name", type=str, default="", help="Experiment name for grouping runs (stored in metrics)")
    parser.add_argument(
        "--lr-schedule",
        type=str,
        choices=["constant", "cosine", "linear"],
        default="constant",
        help="Learning rate schedule: constant, cosine, or linear decay",
    )
    parser.add_argument("--lr-warmup-steps", type=int, default=0, help="Number of linear warmup steps before the LR schedule takes effect")
    parser.add_argument(
        "--early-stopping-patience",
        type=int,
        default=0,
        help="Stop training if eval loss does not improve for this many eval cycles. 0 disables early stopping.",
    )
    parser.add_argument(
        "--auto-eval",
        action="store_true",
        help="Run evaluation automatically after training completes",
    )
    return parser


def _load_payload(args: argparse.Namespace) -> dict:
    if args.dataset_pt:
        payload = torch.load(args.dataset_pt, map_location="cpu", weights_only=True)
    else:
        if not args.db_path:
            raise ValueError("--db-path is required when --dataset-pt is not provided")
        payload = build_iql_tensors_from_replay_db(
            db_path=args.db_path,
            game_ids=args.game_ids,
            next_state_same_player=(args.next_state_mode == "same-player"),
            reward_mode=args.reward_mode,
            gamma=args.gamma,
            filter_timeout=args.filter_timeout,
            normalize_rewards=args.normalize_rewards,
        )

    required = {"states", "actions", "rewards", "next_states", "dones", "state_dim", "action_dim"}
    missing = required - set(payload.keys())
    if missing:
        raise ValueError(f"Dataset payload missing required keys: {sorted(missing)}")

    return payload


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    print(f"[iql] python={sys.executable}", flush=True)
    print(f"[iql] torch={torch.__version__}", flush=True)
    print(f"[iql] startup requested_device={args.device}", flush=True)
    resolved_device = _resolve_device(args.device)
    print(f"[iql] resolved_device={resolved_device}", flush=True)

    print("[iql] loading dataset...", flush=True)

    payload = _load_payload(args)
    print(f"[iql] dataset_loaded transitions={len(payload['states'])}", flush=True)
    dataset = ReplayDataset.from_tensor_dict(payload)
    print(f"[iql] replay_dataset_ready transitions={len(dataset)}", flush=True)
    embedder_bundle_path = resolve_embedder_bundle_path(
        explicit_path=args.embedder_bundle,
        db_path=args.db_path,
        dataset_pt=args.dataset_pt,
    )
    embedder_bundle = load_embedder_bundle(embedder_bundle_path) if embedder_bundle_path is not None else None

    # P1-10: Validate bundle dimensions match dataset dimensions
    if embedder_bundle is None and args.dataset_pt:
        print(
            "[iql] WARNING: no embedder bundle found for pre-built dataset. "
            "Dimension validation skipped — pass --embedder-bundle explicitly.",
            flush=True,
        )
    if embedder_bundle is not None:
        bundle_state_dim = embedder_bundle.get("state_output_dim")
        bundle_action_dim = embedder_bundle.get("action_output_dim")
        dataset_state_dim = int(payload["state_dim"])
        dataset_action_dim = int(payload["action_dim"])
        mismatches = []
        if bundle_state_dim is not None and bundle_state_dim != dataset_state_dim:
            mismatches.append(
                f"state_dim: bundle={bundle_state_dim} vs dataset={dataset_state_dim}"
            )
        if bundle_action_dim is not None and bundle_action_dim != dataset_action_dim:
            mismatches.append(
                f"action_dim: bundle={bundle_action_dim} vs dataset={dataset_action_dim}"
            )
        if mismatches:
            raise ValueError(
                f"Embedder bundle dimension mismatch with dataset: {'; '.join(mismatches)}. "
                f"Re-embed the replay data with the current embedder bundle, or use a matching bundle."
            )
        print(f"[iql] bundle_validated state_dim={dataset_state_dim} action_dim={dataset_action_dim}", flush=True)

    if args.save_dataset_pt:
        out_pt = Path(args.save_dataset_pt)
        out_pt.parent.mkdir(parents=True, exist_ok=True)
        torch.save(payload, str(out_pt))

    # Detect whether the dataset contains raw packed features (end-to-end training)
    uses_raw_features = bool(payload.get("uses_raw_features", False))
    if uses_raw_features:
        print("[iql] dataset uses raw packed features — end-to-end transformer training enabled", flush=True)

    # When using raw features, state_dim / action_dim in the payload are the PACKED sizes,
    # not the transformer output dims.  IQLConfig must use the transformer output dim.
    e2e_transformer = None
    e2e_action_embedder = None
    if uses_raw_features and embedder_bundle is not None:
        e2e_transformer, e2e_action_embedder = _build_e2e_encoders(embedder_bundle, args.device)
        if e2e_transformer is not None:
            # Override state_dim/action_dim to be the transformer OUTPUT dims
            payload["state_dim"]  = e2e_transformer.get_output_dim()
            payload["action_dim"] = e2e_action_embedder.get_output_dim()
            print(
                f"[iql] e2e encoders built: "
                f"state_dim={payload['state_dim']}, action_dim={payload['action_dim']}",
                flush=True,
            )

    config = IQLConfig(
        state_dim=int(payload["state_dim"]),
        action_dim=int(payload["action_dim"]),
        hidden_dim=args.hidden_dim,
        hidden_layers=args.hidden_layers,
        gamma=args.gamma,
        expectile=args.expectile,
        temperature=args.temperature,
        max_weight=args.max_weight,
        batch_size=args.batch_size,
        lr_q=args.lr_q,
        lr_v=args.lr_v,
        lr_actor=args.lr_actor,
        lr_embedder=args.lr_embedder,
        weight_decay=args.weight_decay,
        grad_clip=args.grad_clip,
        reward_scale=args.reward_scale,
        device=args.device,
        normalize_advantages=not args.disable_advantage_normalization,
        rwbc_mode=args.rwbc_mode,
        trainable_embedder=args.trainable_embedder,
        embedder_hidden_dim=args.embedder_hidden_dim,
        embedder_layers=args.embedder_layers,
        lr_schedule=args.lr_schedule,
        lr_warmup_steps=args.lr_warmup_steps,
        use_raw_features=uses_raw_features and e2e_transformer is not None,
    )

    # Resume from checkpoint if specified (P2-19)
    if args.resume_from:
        print(f"[iql] resuming from checkpoint: {args.resume_from}", flush=True)
        trainer = IQLTrainer.from_checkpoint(
            args.resume_from,
            device=args.device,
            transformer=e2e_transformer,
            action_embedder=e2e_action_embedder,
        )
        # Override config values that may have changed via CLI.
        # Training hyperparameters are always taken from CLI so the user can tune on resume.
        trainer.config.batch_size = config.batch_size
        trainer.config.use_raw_features = config.use_raw_features
        trainer.config.lr_schedule = config.lr_schedule
        trainer.config.lr_warmup_steps = config.lr_warmup_steps
        trainer.config.grad_clip = config.grad_clip
        trainer.config.reward_scale = config.reward_scale
        trainer.config.temperature = config.temperature
        trainer.config.expectile = config.expectile
        trainer.config.max_weight = config.max_weight
        trainer.config.normalize_advantages = config.normalize_advantages
        trainer.config.rwbc_mode = config.rwbc_mode
        if config.trainable_embedder and not trainer.config.trainable_embedder:
            print("[iql] upgrading checkpoint: enabling trainable_embedder adapters", flush=True)
            trainer.config.trainable_embedder = True
            trainer.state_adapter = ResidualAdapter(
                input_dim=config.state_dim,
                hidden_dim=config.embedder_hidden_dim,
                hidden_layers=config.embedder_layers,
                enabled=True,
            ).to(trainer.device)
            trainer.action_adapter = ResidualAdapter(
                input_dim=config.action_dim,
                hidden_dim=config.embedder_hidden_dim,
                hidden_layers=config.embedder_layers,
                enabled=True,
            ).to(trainer.device)
            trainer._embedder_params = (
                list(trainer.state_adapter.parameters()) +
                list(trainer.action_adapter.parameters())
            )
            trainer.opt_embed = torch.optim.Adam(
                trainer._embedder_params, lr=config.lr_embedder,
                weight_decay=config.weight_decay,
            )
    else:
        trainer = IQLTrainer(
            config,
            transformer=e2e_transformer,
            action_embedder=e2e_action_embedder,
        )

    run_name = args.run_name or time.strftime("iql_%Y%m%d_%H%M%S")
    run_dir = Path(args.out_dir) / run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"[iql] transitions={len(dataset)} "
        f"state_dim={config.state_dim} action_dim={config.action_dim} "
        f"device={config.device}",
        flush=True,
    )

    history = trainer.fit(dataset=dataset, num_steps=args.steps, log_every=args.log_every, eval_ratio=args.eval_ratio)

    # Early stopping based on eval loss plateau
    early_stopped = False
    if args.early_stopping_patience > 0 and len(history) > 0:
        best_eval_loss = float("inf")
        patience_counter = 0
        stop_step = None
        for entry in history:
            eval_loss = entry.get("eval_loss")
            if eval_loss is None:
                continue
            if eval_loss < best_eval_loss:
                best_eval_loss = eval_loss
                patience_counter = 0
            else:
                patience_counter += 1
            if patience_counter >= args.early_stopping_patience:
                stop_step = entry.get("step")
                break
        if stop_step is not None:
            early_stopped = True
            print(f"[iql] early_stopping triggered at step={stop_step} best_eval_loss={best_eval_loss:.6f}", flush=True)
            # Trim history to the stop point
            history = [h for h in history if h.get("step", 0) <= stop_step]

    interrupted = len(history) > 0 and history[-1].get("step", args.steps) < args.steps and not early_stopped
    ckpt_name = "checkpoint_interrupted.pt" if interrupted else "checkpoint_final.pt"
    ckpt_path = run_dir / ckpt_name
    trainer.save_checkpoint(
        str(ckpt_path),
        extra={
            "run_name": run_name,
            "num_steps": args.steps,
            "num_transitions": len(dataset),
            "db_path": args.db_path,
            "dataset_pt": args.dataset_pt,
            "embedder_bundle_path": str(embedder_bundle_path) if embedder_bundle_path is not None else "",
            "embedder_bundle_fingerprint": embedder_bundle.get("slug_vocab_size") if embedder_bundle else None,
            # Embed the full bundle so checkpoints are self-contained for inference
            "embedder_bundle": embedder_bundle,
            "game_ids": args.game_ids,
            "next_state_mode": args.next_state_mode,
        },
    )

    experiment_name = args.experiment_name or ""

    metrics = {
        "run_name": run_name,
        "experiment_name": experiment_name,
        "early_stopped": early_stopped,
        "dataset": {
            "num_transitions": len(dataset),
            "state_dim": config.state_dim,
            "action_dim": config.action_dim,
            "db_path": args.db_path,
            "game_ids": args.game_ids,
            "next_state_mode": args.next_state_mode,
        },
        "config": asdict(config),
        "final": history[-1] if history else {},
        "history_tail": history[-min(50, len(history)):],
        "checkpoint": str(ckpt_path),
    }

    metrics_path = run_dir / "metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    print(f"[iql] checkpoint: {ckpt_path}", flush=True)
    print(f"[iql] metrics: {metrics_path}", flush=True)

    if args.auto_eval and args.eval_ratio > 0 and history:
        # Extract final eval metrics from training history
        eval_entries = [h for h in history if h.get("eval_loss") is not None]
        if eval_entries:
            final_eval = eval_entries[-1]
            eval_metrics = {k: v for k, v in final_eval.items() if k.startswith("eval_") or k == "step"}
            print(f"[iql] auto_eval results: {json.dumps(eval_metrics, indent=2)}", flush=True)
            eval_path = run_dir / "eval_results.json"
            with open(eval_path, "w", encoding="utf-8") as f:
                json.dump(eval_metrics, f, indent=2)
            print(f"[iql] eval_results: {eval_path}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
