"""CLI entrypoint for offline IQL training on ReplayDB embeddings."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import time

import torch

from rl_agents.dataset_adapter import ReplayDataset, build_iql_tensors_from_replay_db
from rl_agents.iql import IQLConfig, IQLTrainer


def _default_device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train an IQL model on FAB replay embeddings")

    parser.add_argument("--db-path", type=str, default="", help="Path to replay sqlite DB")
    parser.add_argument("--dataset-pt", type=str, default="", help="Optional pre-built .pt tensor dataset")
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
    parser.add_argument("--weight-decay", type=float, default=0.0)
    parser.add_argument("--grad-clip", type=float, default=10.0)
    parser.add_argument("--reward-scale", type=float, default=1.0)
    parser.add_argument("--device", type=str, default=_default_device())
    parser.add_argument("--log-every", type=int, default=100)

    parser.add_argument("--out-dir", type=str, default="data_collection/iql_runs")
    parser.add_argument("--run-name", type=str, default="")
    return parser


def _load_payload(args: argparse.Namespace) -> dict:
    if args.dataset_pt:
        payload = torch.load(args.dataset_pt, map_location="cpu", weights_only=False)
    else:
        if not args.db_path:
            raise ValueError("--db-path is required when --dataset-pt is not provided")
        payload = build_iql_tensors_from_replay_db(
            db_path=args.db_path,
            game_ids=args.game_ids,
            next_state_same_player=(args.next_state_mode == "same-player"),
        )

    required = {"states", "actions", "rewards", "next_states", "dones", "state_dim", "action_dim"}
    missing = required - set(payload.keys())
    if missing:
        raise ValueError(f"Dataset payload missing required keys: {sorted(missing)}")

    return payload


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    payload = _load_payload(args)
    dataset = ReplayDataset.from_tensor_dict(payload)

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
        weight_decay=args.weight_decay,
        grad_clip=args.grad_clip,
        reward_scale=args.reward_scale,
        device=args.device,
    )

    trainer = IQLTrainer(config)

    run_name = args.run_name or time.strftime("iql_%Y%m%d_%H%M%S")
    run_dir = Path(args.out_dir) / run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"[iql] transitions={len(dataset)} "
        f"state_dim={config.state_dim} action_dim={config.action_dim} "
        f"device={config.device}"
    )

    history = trainer.fit(dataset=dataset, num_steps=args.steps, log_every=args.log_every)

    ckpt_path = run_dir / "checkpoint_final.pt"
    trainer.save_checkpoint(
        str(ckpt_path),
        extra={
            "run_name": run_name,
            "num_steps": args.steps,
            "num_transitions": len(dataset),
            "db_path": args.db_path,
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

    print(f"[iql] checkpoint: {ckpt_path}")
    print(f"[iql] metrics: {metrics_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
