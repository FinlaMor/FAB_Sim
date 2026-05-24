"""scripts/run_experiment.py

Automated train-eval harness for IQL hyperparameter experiments.

Trains an IQL model with given hyperparameters, evaluates against a random
agent, and logs results to the experiment tracker.  A single CLI command
runs the full cycle: train → evaluate → log.

Usage:
    # Basic experiment with defaults
    python scripts/run_experiment.py --db-path data/replay.db

    # Custom hyperparameters
    python scripts/run_experiment.py --db-path data/replay.db \
        --steps 5000 --expectile 0.8 --temperature 5.0 --eval-games 50

    # See all options
    python scripts/run_experiment.py --help
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PYTHON = sys.executable
TRACKER_PATH = ROOT / "data_collection" / "experiments.jsonl"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run_step(description: str, cmd: list[str], allow_fail: bool = False) -> int:
    """Run a subprocess step, printing its output in real time."""
    print()
    print("=" * 70)
    print(f"  {description}")
    print("=" * 70)
    print(f"  CMD: {' '.join(cmd)}")
    print()

    t0 = time.time()
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(ROOT) if not existing else f"{ROOT}:{existing}"
    result = subprocess.run(cmd, cwd=str(ROOT), env=env)
    elapsed = time.time() - t0

    if result.returncode != 0:
        status = f"FAILED (exit {result.returncode})"
        if not allow_fail:
            print(f"\n  {status} after {elapsed:.1f}s")
            print(f"  Pipeline halted. Fix the error above and re-run.")
            sys.exit(1)
    else:
        status = "OK"

    print(f"\n  [{status}] {description} ({elapsed:.1f}s)")
    return result.returncode


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Automated IQL train-eval experiment harness",
    )

    # Data
    parser.add_argument("--db-path", type=str, required=True, help="Path to replay sqlite DB")
    parser.add_argument("--dataset-pt", type=str, default="", help="Optional pre-built .pt tensor dataset")

    # Training hyperparameters
    parser.add_argument("--steps", type=int, default=2000, help="Training steps")
    parser.add_argument("--batch-size", type=int, default=256, help="Batch size")
    parser.add_argument("--expectile", type=float, default=0.7, help="IQL expectile (tau)")
    parser.add_argument("--temperature", type=float, default=3.0, help="AWR temperature (beta)")
    parser.add_argument("--gamma", type=float, default=0.99, help="Discount factor")
    parser.add_argument("--hidden-dim", type=int, default=512, help="Hidden layer width")
    parser.add_argument("--hidden-layers", type=int, default=2, help="Number of hidden layers")
    parser.add_argument("--lr-q", type=float, default=3e-4, help="Q-network learning rate")
    parser.add_argument("--lr-v", type=float, default=3e-4, help="V-network learning rate")
    parser.add_argument("--lr-actor", type=float, default=3e-4, help="Actor learning rate")
    parser.add_argument("--reward-scale", type=float, default=1.0, help="Reward scaling factor")
    parser.add_argument("--max-weight", type=float, default=100.0, help="Max advantage weight")
    parser.add_argument("--lr-schedule", type=str, choices=["constant", "cosine", "linear"], default="constant")
    parser.add_argument("--lr-warmup-steps", type=int, default=0, help="LR warmup steps")
    parser.add_argument("--reward-mode", type=str, choices=["terminal", "rtg"], default="terminal")
    parser.add_argument("--filter-timeout", action="store_true", help="Exclude timeout games")
    parser.add_argument("--normalize-rewards", action="store_true", help="Normalize rewards")

    # Evaluation
    parser.add_argument("--eval-games", type=int, default=20, help="Games per matchup for evaluation")
    parser.add_argument("--max-turns", type=int, default=200, help="Max turns per eval game")

    # Output / tracking
    parser.add_argument("--out-dir", type=str, default="data_collection/iql_runs", help="Training output directory")
    parser.add_argument("--run-name", type=str, default="", help="Run name (auto-generated if empty)")
    parser.add_argument("--experiment-name", type=str, default="", help="Experiment name for grouping")
    parser.add_argument("--tracker-path", type=str, default="", help="Path to experiment JSONL tracker")
    parser.add_argument("--tags", type=str, nargs="*", default=[], help="Tags for experiment tracking")

    # Device
    parser.add_argument("--device", type=str, default="cpu", help="Torch device")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for evaluation")

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    tracker_path = Path(args.tracker_path) if args.tracker_path else TRACKER_PATH

    # Lazy import to avoid top-level dependency if just checking --help
    from rl_agents.utils.experiment_tracker import ExperimentTracker

    tracker = ExperimentTracker(tracker_path)

    # Build hyperparameters dict for tracking
    hyperparameters = {
        "db_path": args.db_path,
        "steps": args.steps,
        "batch_size": args.batch_size,
        "expectile": args.expectile,
        "temperature": args.temperature,
        "gamma": args.gamma,
        "hidden_dim": args.hidden_dim,
        "hidden_layers": args.hidden_layers,
        "lr_q": args.lr_q,
        "lr_v": args.lr_v,
        "lr_actor": args.lr_actor,
        "reward_scale": args.reward_scale,
        "max_weight": args.max_weight,
        "lr_schedule": args.lr_schedule,
        "lr_warmup_steps": args.lr_warmup_steps,
        "reward_mode": args.reward_mode,
        "filter_timeout": args.filter_timeout,
        "normalize_rewards": args.normalize_rewards,
        "eval_games": args.eval_games,
    }

    run_id = tracker.start_run(hyperparameters, tags=args.tags or None)
    run_name = args.run_name or f"experiment_{run_id}"
    run_out_dir = Path(args.out_dir) / run_name

    print(f"[experiment] run_id={run_id}")
    print(f"[experiment] tracker={tracker_path}")
    print(f"[experiment] out_dir={run_out_dir}")

    # ------------------------------------------------------------------
    # Step 1: Train IQL
    # ------------------------------------------------------------------
    train_cmd = [
        PYTHON, str(ROOT / "rl_agents" / "train_iql.py"),
        "--db-path", args.db_path,
        "--steps", str(args.steps),
        "--batch-size", str(args.batch_size),
        "--expectile", str(args.expectile),
        "--temperature", str(args.temperature),
        "--gamma", str(args.gamma),
        "--hidden-dim", str(args.hidden_dim),
        "--hidden-layers", str(args.hidden_layers),
        "--lr-q", str(args.lr_q),
        "--lr-v", str(args.lr_v),
        "--lr-actor", str(args.lr_actor),
        "--reward-scale", str(args.reward_scale),
        "--max-weight", str(args.max_weight),
        "--lr-schedule", args.lr_schedule,
        "--lr-warmup-steps", str(args.lr_warmup_steps),
        "--reward-mode", args.reward_mode,
        "--device", args.device,
        "--out-dir", args.out_dir,
        "--run-name", run_name,
    ]
    if args.dataset_pt:
        train_cmd.extend(["--dataset-pt", args.dataset_pt])
    if args.filter_timeout:
        train_cmd.append("--filter-timeout")
    if args.normalize_rewards:
        train_cmd.append("--normalize-rewards")
    if args.experiment_name:
        train_cmd.extend(["--experiment-name", args.experiment_name])

    rc = run_step("Step 1: Train IQL model", train_cmd, allow_fail=True)
    if rc != 0:
        tracker.finish_run(run_id, {"error": "training_failed"}, status="failed")
        print(f"\n[experiment] FAILED — training returned exit code {rc}")
        return 1

    # Locate the checkpoint
    checkpoint = run_out_dir / "checkpoint_final.pt"
    if not checkpoint.exists():
        tracker.finish_run(run_id, {"error": "checkpoint_not_found"}, status="failed")
        print(f"\n[experiment] FAILED — checkpoint not found at {checkpoint}")
        return 1

    # Read training metrics if available
    metrics_file = run_out_dir / "metrics.json"
    train_metrics: dict = {}
    if metrics_file.exists():
        try:
            with open(metrics_file, "r") as f:
                train_metrics = json.load(f)
            tracker.log_metrics(run_id, {
                k: v for k, v in train_metrics.items()
                if isinstance(v, (int, float))
            })
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Step 2: Evaluate against random
    # ------------------------------------------------------------------
    eval_out_dir = run_out_dir / "eval"
    eval_cmd = [
        PYTHON, str(ROOT / "rl_agents" / "evaluate_iql_vs_random.py"),
        "--checkpoint", str(checkpoint),
        "--games-per-matchup", str(args.eval_games),
        "--max-turns", str(args.max_turns),
        "--device", args.device,
        "--out-dir", str(eval_out_dir),
    ]
    if args.seed is not None:
        eval_cmd.extend(["--seed", str(args.seed)])

    rc = run_step("Step 2: Evaluate IQL vs random", eval_cmd, allow_fail=True)

    eval_metrics: dict = {}
    if rc == 0:
        # Parse evaluation summary
        summary_file = eval_out_dir / "summary.json"
        if summary_file.exists():
            try:
                with open(summary_file, "r") as f:
                    eval_summary = json.load(f)
                # Extract key metrics from eval summary
                if "overall" in eval_summary:
                    overall = eval_summary["overall"]
                    eval_metrics["win_rate"] = overall.get("model_win_rate", 0.0)
                    eval_metrics["model_wins"] = overall.get("model_wins", 0)
                    eval_metrics["random_wins"] = overall.get("random_wins", 0)
                    eval_metrics["total_games"] = overall.get("total_games", 0)
                elif "matchups" in eval_summary:
                    # Aggregate from matchups
                    total_wins = 0
                    total_games = 0
                    for m in eval_summary["matchups"]:
                        total_wins += m.get("model_wins", 0)
                        total_games += m.get("model_wins", 0) + m.get("random_wins", 0)
                    eval_metrics["win_rate"] = total_wins / max(total_games, 1)
                    eval_metrics["model_wins"] = total_wins
                    eval_metrics["total_games"] = total_games
            except Exception:
                pass
    else:
        eval_metrics["eval_error"] = "evaluation_failed"

    # ------------------------------------------------------------------
    # Step 3: Log final results
    # ------------------------------------------------------------------
    final_metrics = {**eval_metrics}
    if "final_loss" in train_metrics:
        final_metrics["final_loss"] = train_metrics["final_loss"]

    status = "completed" if rc == 0 else "completed"  # training succeeded even if eval fails
    tracker.finish_run(run_id, final_metrics, status=status)

    # Print summary
    print()
    print("=" * 70)
    print("  Experiment Summary")
    print("=" * 70)
    print(f"  run_id:       {run_id}")
    print(f"  checkpoint:   {checkpoint}")
    print(f"  tracker:      {tracker_path}")
    if "win_rate" in eval_metrics:
        print(f"  win_rate:     {eval_metrics['win_rate']:.4f}")
    if "total_games" in eval_metrics:
        print(f"  eval_games:   {eval_metrics['total_games']}")
    print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
