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
from rl_agents.iql import IQLConfig, IQLTrainer
from rl_agents.utils.device import default_device as _default_device, resolve_device as _resolve_device


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
    )

    # Resume from checkpoint if specified (P2-19)
    if args.resume_from:
        print(f"[iql] resuming from checkpoint: {args.resume_from}", flush=True)
        trainer = IQLTrainer.from_checkpoint(args.resume_from, device=args.device)
        # Override config values that may have changed via CLI
        trainer.config.batch_size = config.batch_size
    else:
        trainer = IQLTrainer(config)

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

    interrupted = len(history) > 0 and history[-1].get("step", args.steps) < args.steps
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

    metrics = {
        "run_name": run_name,
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
