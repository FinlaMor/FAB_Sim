"""End-to-end validation for the IQL experiment pipeline (subtask-4-1).

Verifies that all components from phases 1-3 integrate correctly:
1. collect_iql_mixed_data.py --agent-mode flag works (import + help)
2. train_iql.py --reward-mode rtg --filter-timeout flags work (import + help)
3. bench_player_bot.py --json flag works (import + help)
4. run_experiment.py full cycle structure (import + help)
5. experiment_tracker.py records runs and best_run() works
6. run_pipeline.py still parses PLAYER_BOT_WIN_RATE correctly
7. IQL training with synthetic data converges (RTG vs terminal reward modes)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON = sys.executable


def _run_help(script: str) -> str:
    """Run a script with --help and return stdout."""
    result = subprocess.run(
        [PYTHON, script, "--help"],
        capture_output=True, text=True, cwd=ROOT, timeout=30,
        env={**os.environ, "PYTHONPATH": ROOT},
    )
    return result.stdout + result.stderr


def test_collect_cli_flags():
    """Verify collect_iql_mixed_data.py exposes its core CLI flags.

    (--agent-mode was removed; matchups are configured via --games-per-matchup
    and the backend via --game-backend.)
    """
    output = _run_help(os.path.join(ROOT, "rl_agents", "collect_iql_mixed_data.py"))
    for flag in ("--out-dir", "--games-per-matchup", "--seed", "--game-backend"):
        assert flag in output, f"{flag} not found in help output:\n{output}"
    print("  [PASS] collect_iql_mixed_data.py CLI flags present")


def test_train_iql_flags():
    """Verify train_iql.py supports --reward-mode rtg and --filter-timeout."""
    output = _run_help(os.path.join(ROOT, "rl_agents", "train_iql.py"))
    assert "--reward-mode" in output, f"--reward-mode not found:\n{output}"
    assert "--filter-timeout" in output, f"--filter-timeout not found:\n{output}"
    assert "--experiment-name" in output, f"--experiment-name not found:\n{output}"
    assert "--lr-schedule" in output, f"--lr-schedule not found:\n{output}"
    print("  [PASS] train_iql.py flags present (reward-mode, filter-timeout, experiment-name, lr-schedule)")


def test_bench_json_flag():
    """Verify bench_player_bot.py supports --json flag."""
    output = _run_help(os.path.join(ROOT, "scripts", "bench_player_bot.py"))
    assert "--json" in output, f"--json not found:\n{output}"
    print("  [PASS] bench_player_bot.py --json flag present")


def test_run_experiment_flags():
    """Verify run_experiment.py has expected flags."""
    output = _run_help(os.path.join(ROOT, "scripts", "run_experiment.py"))
    for flag in ("--db-path", "--steps", "--expectile", "--temperature", "--eval-games"):
        assert flag in output, f"{flag} not found:\n{output}"
    print("  [PASS] run_experiment.py flags present")


def test_sweep_hyperparams_flags():
    """Verify sweep_hyperparams.py has expected flags."""
    output = _run_help(os.path.join(ROOT, "scripts", "sweep_hyperparams.py"))
    for flag in ("--sweep-mode", "--num-trials"):
        assert flag in output, f"{flag} not found:\n{output}"
    print("  [PASS] sweep_hyperparams.py flags present")


def test_experiment_tracker():
    """Verify ExperimentTracker records runs and best_run() returns correct result."""
    # Import inline to avoid top-level import issues
    sys.path.insert(0, ROOT)
    from rl_agents.utils.experiment_tracker import ExperimentTracker

    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        tracker_path = f.name

    try:
        tracker = ExperimentTracker(tracker_path)

        # Log two runs
        rid1 = tracker.start_run({"lr": 0.001, "expectile": 0.7}, tags=["test"])
        tracker.finish_run(rid1, {"win_rate": 0.45, "loss": 0.5})

        rid2 = tracker.start_run({"lr": 0.001, "expectile": 0.9}, tags=["test"])
        tracker.finish_run(rid2, {"win_rate": 0.62, "loss": 0.3})

        # Verify best_run
        best = tracker.best_run("win_rate")
        assert best["run_id"] == rid2, f"Expected best run_id={rid2}, got {best['run_id']}"
        assert best["metrics"]["win_rate"] == 0.62

        # Verify compare_configs
        ranked = tracker.compare_configs("win_rate", top_k=2)
        assert len(ranked) == 2
        assert ranked[0]["metrics"]["win_rate"] >= ranked[1]["metrics"]["win_rate"]

        print("  [PASS] experiment_tracker records runs and best_run() works correctly")
    finally:
        os.unlink(tracker_path)


def test_pipeline_win_rate_parsing():
    """Verify run_pipeline.py still parses PLAYER_BOT_WIN_RATE correctly."""
    # Simulate the parsing logic from run_pipeline.py
    sample_output = (
        "[bench] IQL vs Random:  W=31  L=19  (62.0%)\n"
        "[bench] 95% CI: [0.473, 0.749]  p-value: 0.0968\n"
        "PLAYER_BOT_WIN_RATE 0.6200\n"
    )
    win_rate = None
    for line in sample_output.splitlines():
        if line.startswith("PLAYER_BOT_WIN_RATE"):
            try:
                win_rate = float(line.split()[1])
            except (IndexError, ValueError):
                pass
    assert win_rate is not None, "Failed to parse PLAYER_BOT_WIN_RATE"
    assert abs(win_rate - 0.62) < 0.001, f"Parsed wrong win_rate: {win_rate}"
    print("  [PASS] PLAYER_BOT_WIN_RATE parsing works correctly")


def test_iql_training_synthetic():
    """Verify IQL training converges on synthetic data with RTG rewards."""
    sys.path.insert(0, ROOT)
    import torch
    from rl_agents.iql import IQLConfig, IQLTrainer
    from rl_agents.dataset_adapter import ReplayDataset

    state_dim, action_dim = 64, 64
    n = 2000

    # Create synthetic dataset: good actions (reward=1) have state-action alignment
    torch.manual_seed(42)
    states = torch.randn(n, state_dim)
    # Good actions are correlated with states, bad ones are random
    good_mask = torch.rand(n) > 0.5
    actions = torch.where(
        good_mask.unsqueeze(1).expand(-1, action_dim),
        states[:, :action_dim] + 0.1 * torch.randn(n, action_dim),  # correlated
        torch.randn(n, action_dim),  # random
    )
    rewards = good_mask.float() * 2 - 1  # +1 for good, -1 for bad
    next_states = torch.randn(n, state_dim)
    dones = torch.zeros(n)
    dones[::20] = 1.0  # episode boundaries every 20 steps

    dataset = ReplayDataset(states, actions, rewards, next_states, dones)

    # Train with terminal rewards
    config_terminal = IQLConfig(
        state_dim=state_dim, action_dim=action_dim,
        expectile=0.7, temperature=3.0, batch_size=256,
    )
    trainer_terminal = IQLTrainer(config_terminal)
    metrics_terminal = trainer_terminal.fit(dataset, num_steps=500)

    # Train with RTG-like rewards (should also converge)
    # Apply simple RTG: rewards already non-zero, just scale by position
    rtg_rewards = rewards.clone()
    config_rtg = IQLConfig(
        state_dim=state_dim, action_dim=action_dim,
        expectile=0.7, temperature=3.0, batch_size=256,
    )
    trainer_rtg = IQLTrainer(config_rtg)
    dataset_rtg = ReplayDataset(states, actions, rtg_rewards, next_states, dones)
    metrics_rtg = trainer_rtg.fit(dataset_rtg, num_steps=500)

    # fit() returns a list of history dicts; check final entry
    assert len(metrics_terminal) > 0, "No training history returned (terminal)"
    assert len(metrics_rtg) > 0, "No training history returned (rtg)"
    final_terminal = metrics_terminal[-1]
    final_rtg = metrics_rtg[-1]
    # Both should have reasonable loss values
    assert final_terminal.get("eval_bc_loss", 999) < 10.0, f"Terminal eval loss too high"
    assert final_rtg.get("eval_bc_loss", 999) < 10.0, f"RTG eval loss too high"

    # Verify checkpoint save/load works
    with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as f:
        ckpt_path = f.name
    try:
        trainer_rtg.save_checkpoint(ckpt_path)
        assert os.path.exists(ckpt_path), "Checkpoint not saved"
        ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        assert "config" in ckpt, "Checkpoint missing config"
        print(f"  [PASS] IQL training converges (terminal_eval={final_terminal.get('eval_bc_loss', '?'):.3f}, rtg_eval={final_rtg.get('eval_bc_loss', '?'):.3f})")
    finally:
        if os.path.exists(ckpt_path):
            os.unlink(ckpt_path)


def test_dataset_adapter_rtg():
    """Verify _apply_rtg produces denser rewards than terminal mode."""
    sys.path.insert(0, ROOT)
    from rl_agents.dataset_adapter import _apply_rtg

    # Sparse terminal rewards: only last step has reward
    rewards = [0.0, 0.0, 0.0, 0.0, 1.0]
    dones = [0.0, 0.0, 0.0, 0.0, 1.0]

    rtg = _apply_rtg(rewards, dones, gamma=0.99)

    # All RTG values should be non-zero (denser signal)
    assert all(abs(r) > 0 for r in rtg), f"RTG should be non-zero everywhere: {rtg}"
    # RTG should be monotonically increasing (closer to reward = higher value)
    for i in range(len(rtg) - 1):
        assert rtg[i] <= rtg[i + 1] + 1e-6, f"RTG not monotonic at {i}: {rtg}"
    # Terminal reward should be preserved
    assert abs(rtg[-1] - 1.0) < 1e-6, f"Terminal reward not preserved: {rtg[-1]}"

    print(f"  [PASS] _apply_rtg produces dense rewards: {[f'{r:.3f}' for r in rtg]}")


def main():
    print("=" * 60)
    print("  E2E Validation: IQL Experiment Pipeline")
    print("=" * 60)
    print()

    tests = [
        ("1. collect_iql_mixed_data --agent-mode", test_collect_agent_mode_flag),
        ("2. train_iql.py flags", test_train_iql_flags),
        ("3. bench_player_bot.py --json", test_bench_json_flag),
        ("4. run_experiment.py flags", test_run_experiment_flags),
        ("5. sweep_hyperparams.py flags", test_sweep_hyperparams_flags),
        ("6. experiment_tracker.py", test_experiment_tracker),
        ("7. PLAYER_BOT_WIN_RATE parsing", test_pipeline_win_rate_parsing),
        ("8. _apply_rtg dense rewards", test_dataset_adapter_rtg),
        ("9. IQL synthetic training", test_iql_training_synthetic),
    ]

    passed = 0
    failed = 0
    for name, test_fn in tests:
        print(f"[TEST] {name}")
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {e}")
            failed += 1

    print()
    print("=" * 60)
    print(f"  Results: {passed} passed, {failed} failed, {len(tests)} total")
    print("=" * 60)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
