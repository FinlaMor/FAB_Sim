"""scripts/sweep_hyperparams.py

Grid or random search over key IQL hyperparameters with automated
evaluation via run_experiment.py.

Usage:
    # Grid sweep over expectile and temperature
    python scripts/sweep_hyperparams.py --db-path data/replay.db \
        --sweep-mode grid \
        --expectile 0.7 0.8 0.9 --temperature 3.0 5.0 10.0

    # Random search with 20 trials
    python scripts/sweep_hyperparams.py --db-path data/replay.db \
        --sweep-mode random --num-trials 20

    # See all options
    python scripts/sweep_hyperparams.py --help
"""
from __future__ import annotations

import argparse
import itertools
import json
import random
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable

# ---------------------------------------------------------------------------
# Default search spaces for random mode
# ---------------------------------------------------------------------------

DEFAULT_RANDOM_SPACES: dict[str, list] = {
    "expectile": [0.5, 0.6, 0.7, 0.8, 0.9],
    "temperature": [1.0, 3.0, 5.0, 10.0, 20.0],
    "batch_size": [128, 256, 512],
    "reward_scale": [0.5, 1.0, 2.0, 5.0],
    "lr": [1e-4, 3e-4, 1e-3],
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Hyperparameter sweep over IQL via run_experiment.py",
    )

    # Sweep control
    parser.add_argument(
        "--sweep-mode",
        type=str,
        choices=["grid", "random"],
        default="grid",
        help="Sweep strategy: grid (all combinations) or random (sampled)",
    )
    parser.add_argument(
        "--num-trials",
        type=int,
        default=10,
        help="Number of trials for random sweep (ignored for grid)",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")

    # Hyperparameter lists (grid mode uses all combos; random mode samples from these)
    parser.add_argument("--expectile", type=float, nargs="+", default=[0.7], help="Expectile values to sweep")
    parser.add_argument("--temperature", type=float, nargs="+", default=[3.0], help="Temperature values to sweep")
    parser.add_argument("--batch-size", type=int, nargs="+", default=[256], help="Batch size values to sweep")
    parser.add_argument("--reward-scale", type=float, nargs="+", default=[1.0], help="Reward scale values to sweep")
    parser.add_argument("--lr", type=float, nargs="+", default=[3e-4], help="Learning rate values to sweep (applied to Q, V, and actor)")

    # Pass-through args for run_experiment.py
    parser.add_argument("--db-path", type=str, required=True, help="Path to replay sqlite DB")
    parser.add_argument("--dataset-pt", type=str, default="", help="Optional pre-built .pt tensor dataset")
    parser.add_argument("--steps", type=int, default=2000, help="Training steps per trial")
    parser.add_argument("--eval-games", type=int, default=20, help="Eval games per trial")
    parser.add_argument("--max-turns", type=int, default=200, help="Max turns per eval game")
    parser.add_argument("--gamma", type=float, default=0.99, help="Discount factor")
    parser.add_argument("--hidden-dim", type=int, default=512, help="Hidden layer width")
    parser.add_argument("--hidden-layers", type=int, default=2, help="Number of hidden layers")
    parser.add_argument("--max-weight", type=float, default=100.0, help="Max advantage weight")
    parser.add_argument("--lr-schedule", type=str, choices=["constant", "cosine", "linear"], default="constant")
    parser.add_argument("--lr-warmup-steps", type=int, default=0, help="LR warmup steps")
    parser.add_argument("--reward-mode", type=str, choices=["terminal", "rtg"], default="terminal")
    parser.add_argument("--filter-timeout", action="store_true", help="Exclude timeout games")
    parser.add_argument("--normalize-rewards", action="store_true", help="Normalize rewards")
    parser.add_argument("--out-dir", type=str, default="data_collection/iql_runs", help="Training output directory")
    parser.add_argument("--experiment-name", type=str, default="sweep", help="Experiment name for grouping")
    parser.add_argument("--tracker-path", type=str, default="", help="Path to experiment JSONL tracker")
    parser.add_argument("--tags", type=str, nargs="*", default=[], help="Tags for experiment tracking")
    parser.add_argument("--device", type=str, default="cpu", help="Torch device")
    parser.add_argument("--continue-on-failure", action="store_true", help="Continue sweep even if a trial fails")

    return parser


def _generate_grid_configs(args: argparse.Namespace) -> list[dict]:
    """Generate all combinations of swept hyperparameters."""
    keys = ["expectile", "temperature", "batch_size", "reward_scale", "lr"]
    values = [
        args.expectile,
        args.temperature,
        args.batch_size,
        args.reward_scale,
        args.lr,
    ]
    configs = []
    for combo in itertools.product(*values):
        configs.append(dict(zip(keys, combo)))
    return configs


def _generate_random_configs(args: argparse.Namespace, num_trials: int) -> list[dict]:
    """Sample random hyperparameter configurations."""
    rng = random.Random(args.seed)
    spaces = {
        "expectile": args.expectile if len(args.expectile) > 1 else DEFAULT_RANDOM_SPACES["expectile"],
        "temperature": args.temperature if len(args.temperature) > 1 else DEFAULT_RANDOM_SPACES["temperature"],
        "batch_size": args.batch_size if len(args.batch_size) > 1 else DEFAULT_RANDOM_SPACES["batch_size"],
        "reward_scale": args.reward_scale if len(args.reward_scale) > 1 else DEFAULT_RANDOM_SPACES["reward_scale"],
        "lr": args.lr if len(args.lr) > 1 else DEFAULT_RANDOM_SPACES["lr"],
    }
    configs = []
    for _ in range(num_trials):
        configs.append({k: rng.choice(v) for k, v in spaces.items()})
    return configs


def _run_trial(
    trial_idx: int,
    total: int,
    config: dict,
    args: argparse.Namespace,
) -> int:
    """Run a single experiment trial via run_experiment.py."""
    run_name = f"sweep_{args.experiment_name}_t{trial_idx:03d}"

    print()
    print("#" * 70)
    print(f"  TRIAL {trial_idx + 1}/{total}")
    print(f"  config: {json.dumps(config)}")
    print(f"  run_name: {run_name}")
    print("#" * 70)

    cmd = [
        PYTHON, str(ROOT / "scripts" / "run_experiment.py"),
        "--db-path", args.db_path,
        "--steps", str(args.steps),
        "--batch-size", str(int(config["batch_size"])),
        "--expectile", str(config["expectile"]),
        "--temperature", str(config["temperature"]),
        "--reward-scale", str(config["reward_scale"]),
        "--lr-q", str(config["lr"]),
        "--lr-v", str(config["lr"]),
        "--lr-actor", str(config["lr"]),
        "--gamma", str(args.gamma),
        "--hidden-dim", str(args.hidden_dim),
        "--hidden-layers", str(args.hidden_layers),
        "--max-weight", str(args.max_weight),
        "--lr-schedule", args.lr_schedule,
        "--lr-warmup-steps", str(args.lr_warmup_steps),
        "--reward-mode", args.reward_mode,
        "--eval-games", str(args.eval_games),
        "--max-turns", str(args.max_turns),
        "--out-dir", args.out_dir,
        "--run-name", run_name,
        "--experiment-name", args.experiment_name,
        "--device", args.device,
    ]
    if args.dataset_pt:
        cmd.extend(["--dataset-pt", args.dataset_pt])
    if args.filter_timeout:
        cmd.append("--filter-timeout")
    if args.normalize_rewards:
        cmd.append("--normalize-rewards")
    if args.tracker_path:
        cmd.extend(["--tracker-path", args.tracker_path])
    tags = list(args.tags or []) + ["sweep", f"trial-{trial_idx}"]
    for tag in tags:
        cmd.extend(["--tags", tag])

    t0 = time.time()
    result = subprocess.run(cmd, cwd=str(ROOT))
    elapsed = time.time() - t0

    status = "OK" if result.returncode == 0 else f"FAILED (exit {result.returncode})"
    print(f"\n  [{status}] Trial {trial_idx + 1}/{total} ({elapsed:.1f}s)")
    return result.returncode


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.sweep_mode == "grid":
        configs = _generate_grid_configs(args)
        print(f"[sweep] mode=grid  trials={len(configs)}")
    else:
        configs = _generate_random_configs(args, args.num_trials)
        print(f"[sweep] mode=random  trials={len(configs)}  seed={args.seed}")

    passed = 0
    failed = 0
    t0 = time.time()

    for i, config in enumerate(configs):
        rc = _run_trial(i, len(configs), config, args)
        if rc == 0:
            passed += 1
        else:
            failed += 1
            if not args.continue_on_failure:
                print(f"\n[sweep] Halting after trial {i + 1} failure. Use --continue-on-failure to keep going.")
                break

    total_time = time.time() - t0
    print()
    print("=" * 70)
    print(f"  SWEEP COMPLETE")
    print(f"  Total trials: {passed + failed}/{len(configs)}")
    print(f"  Passed: {passed}  Failed: {failed}")
    print(f"  Total time: {total_time:.1f}s")
    print("=" * 70)

    return 1 if failed > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
