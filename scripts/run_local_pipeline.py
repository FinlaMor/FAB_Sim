"""scripts/run_local_pipeline.py

Local-engine training and evolution pipeline:
    1. Validate decks           — check legality, weapon/equipment
    2. Run games                — local engine with mixed opponents
    3. Upload data              — verify DB has rows (data recorded during sim)
    4. Train player model       — IQL on collected transitions
    5. Train deck bot           — deck evaluator on game outcomes
    6. Evolve decks             — evolutionary search with evaluator
    7. Benchmark                — player bot vs random/heuristic/prev
    8. Loop                     — repeat stages 1-7

Usage:
    # Single loop
    python scripts/run_local_pipeline.py --games-per-loop 200

    # Multi-loop with evolution
    python scripts/run_local_pipeline.py --loops 5 --games-per-loop 200

    # Loop forever until Ctrl+C
    python scripts/run_local_pipeline.py --loop-forever --games-per-loop 100
"""
from __future__ import annotations

import argparse
import os
import random
import signal
import subprocess
import sqlite3
import sys

# Ensure project root is on the path so `rl_agents`, `engine`, etc. are importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
CHECKPOINT_DIR = ROOT / "checkpoints"
GENERATED_DIR = ROOT / "decks" / "generated"
PYTHON = sys.executable

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_interrupted = False


def _handle_signal(sig, frame):
    global _interrupted
    _interrupted = True
    print("\nPipeline interrupt received — finishing current step...")


def run_step(description: str, cmd: list[str], allow_fail: bool = False) -> int:
    """Run a subprocess step, printing its output in real time.

    On KeyboardInterrupt the entire child process *tree* is killed (Windows:
    taskkill /F /T; POSIX: os.killpg) so no orphaned workers are left behind.
    """
    print()
    print("=" * 70)
    print(f"  {description}")
    print("=" * 70)
    print(f"  CMD: {' '.join(cmd)}")
    print()

    t0 = time.time()

    import platform
    if platform.system() == "Windows":
        proc = subprocess.Popen(cmd, cwd=str(ROOT),
                                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    else:
        proc = subprocess.Popen(cmd, cwd=str(ROOT), start_new_session=True)

    try:
        proc.wait()
    except KeyboardInterrupt:
        # Kill the entire process tree so no workers are orphaned.
        if platform.system() == "Windows":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
            )
        else:
            import os, signal
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.wait()
        raise

    elapsed = time.time() - t0
    rc = proc.returncode

    if rc != 0:
        status = f"FAILED (exit {rc})"
        if not allow_fail:
            print(f"\n  {status} after {elapsed:.1f}s")
            print(f"  Pipeline halted. Fix the error above and re-run.")
            sys.exit(1)
    else:
        status = "OK"

    print(f"\n  [{status}] {description} ({elapsed:.1f}s)")
    return rc


def db_row_count(db_path: Path, table: str) -> int:
    """Count rows in a SQLite table, or 0 if table/db doesn't exist."""
    if not db_path.exists():
        return 0
    try:
        conn = sqlite3.connect(str(db_path))
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0


def find_best_checkpoint(prefix: str) -> Path | None:
    """Find the best checkpoint matching a prefix."""
    best = CHECKPOINT_DIR / f"{prefix}_best.pt"
    if best.exists():
        return best
    final = CHECKPOINT_DIR / f"{prefix}_final.pt"
    if final.exists():
        return final
    return None


def print_summary(label: str, items: dict[str, str | int | float]) -> None:
    """Print a summary block."""
    print()
    print(f"  --- {label} ---")
    for k, v in items.items():
        print(f"  {k:<30} {v}")
    print()


# ---------------------------------------------------------------------------
# Pipeline steps (stages 1-3)
# ---------------------------------------------------------------------------

def step_validate_decks(args) -> list[str]:
    """Stage 1: Validate all generated decks for legality and equipment."""
    print()
    print("=" * 70)
    print("  Stage 1: Validate decks")
    print("=" * 70)
    print()

    t0 = time.time()

    from rl_agents.deck_validator import validate_all_decks
    from engine.card import CardDB
    from config import SLUG_INDEX_PATH
    import json

    # Load card_db and slug_index for validation
    if args._card_db is None:
        args._card_db = CardDB(str(SLUG_INDEX_PATH))
    with open(SLUG_INDEX_PATH, encoding="utf-8") as f:
        si_data = json.load(f)
    slug_index = si_data.get("by_slug", si_data)

    deck_dir = str(GENERATED_DIR)
    valid_paths, invalid_report = validate_all_decks(deck_dir, args._card_db, slug_index)

    elapsed = time.time() - t0

    # Report invalid decks
    if invalid_report:
        print(f"  Invalid decks ({len(invalid_report)}):")
        for deck_path, violations in invalid_report.items():
            print(f"    {Path(deck_path).name}:")
            for v in violations:
                print(f"      - {v}")

    if len(valid_paths) == 0:
        print(f"\n  FATAL: Zero valid decks in {deck_dir}")
        print(f"  Pipeline halted. Fix deck files and re-run.")
        sys.exit(1)

    print_summary("Deck validation results", {
        "Valid decks": len(valid_paths),
        "Invalid decks": len(invalid_report),
        "Deck directory": deck_dir,
        "Elapsed": f"{elapsed:.1f}s",
    })

    print(f"\n  [OK] Stage 1: Validate decks ({elapsed:.1f}s)")
    return valid_paths


def step_run_games(args, valid_decks: list[str], loop_num: int,
                   opponent_pool) -> int:
    """Stage 2: Run games via local engine with mixed opponents."""
    print()
    print("=" * 70)
    label = "Stage 2: Run local-engine games"
    if loop_num > 0:
        label += f" (loop {loop_num})"
    print(f"  {label}")
    print("=" * 70)
    print()

    t0 = time.time()

    from rl_agents.local_game_runner import MatchupScheduler, run_games

    scheduler = MatchupScheduler()
    deck_pairs = scheduler.schedule_matchups(valid_decks, args.games_per_loop)

    print(f"  Scheduled {len(deck_pairs)} matchups across {len(valid_decks)} decks")

    results = run_games(
        deck_pairs=deck_pairs,
        opponent_pool=opponent_pool,
        card_db=args._card_db,
        replay_db=args._replay_db,
        game_data_store=args._game_data_store,
        embedder_bundle=args._embedder_bundle,
        max_turns=args.max_turns,
        seed=args.seed + loop_num * 10000,
    )

    elapsed = time.time() - t0

    n_games = args._replay_db.game_count()
    n_transitions = args._replay_db.transition_count()

    print_summary("Game collection results", {
        "Games this batch": results.completed,
        "Errors": results.failed,
        "Total games in DB": n_games,
        "Total transitions in DB": n_transitions,
        "Elapsed": f"{elapsed:.1f}s",
    })

    print(f"\n  [OK] {label} ({elapsed:.1f}s)")
    return n_games


def step_upload_data(args) -> None:
    """Stage 3: Verify data is recorded (no-op — data written during sim)."""
    print()
    print("=" * 70)
    print("  Stage 3: Verify data upload")
    print("=" * 70)
    print()

    t0 = time.time()

    n_games = args._replay_db.game_count()
    n_transitions = args._replay_db.transition_count()

    if n_games == 0:
        print("  WARNING: No games recorded in database.")
    if n_transitions == 0:
        print("  WARNING: No transitions recorded in database.")

    elapsed = time.time() - t0

    print_summary("Data verification", {
        "Games in DB": n_games,
        "Transitions in DB": n_transitions,
        "Database": str(args._replay_db.db_path),
        "Elapsed": f"{elapsed:.1f}s",
    })

    print(f"\n  [OK] Stage 3: Verify data upload ({elapsed:.1f}s)")


# ---------------------------------------------------------------------------
# Pipeline steps (stages 4-7)
# ---------------------------------------------------------------------------

def _update_bundle_from_checkpoint(ckpt_path: Path) -> None:
    """Overwrite the on-disk embedder bundle with trained e2e weights from an IQL checkpoint.

    This ensures evaluation and future game collection use the improved encoder
    weights rather than the stale initial bundle.
    """
    import torch as _torch
    bundle_path = CHECKPOINT_DIR / "embedder_bundle.pt"
    if not bundle_path.exists():
        return

    try:
        payload = _torch.load(str(ckpt_path), map_location="cpu", weights_only=False)
        bundle = _torch.load(str(bundle_path), map_location="cpu", weights_only=False)
        updated = False

        if "transformer_state_dict" in payload:
            bundle["game_transformer_state_dict"] = payload["transformer_state_dict"]
            updated = True
        if "action_embedder_state_dict" in payload:
            # The checkpoint stores the full action_embedder state_dict (including card_embedder).
            # Split it back into the bundle's separate sections.
            full_ae_sd = payload["action_embedder_state_dict"]
            card_keys = {k: v for k, v in full_ae_sd.items() if k.startswith("card_embedder.")}
            ae_keys = {k: v for k, v in full_ae_sd.items() if not k.startswith("card_embedder.")}
            if card_keys:
                bundle["card_embedder_state_dict"] = {
                    k.removeprefix("card_embedder."): v for k, v in card_keys.items()
                }
            bundle["action_embedder_state_dict"] = ae_keys
            updated = True

        if updated:
            _torch.save(bundle, str(bundle_path))
            print(f"  Updated embedder bundle at {bundle_path} with trained e2e weights")
    except Exception as e:
        print(f"  WARNING: Could not update embedder bundle from checkpoint: {e}")


def step_pretrain_transformer(args, loop_num: int) -> None:
    """Stage 4: Pre-train transformer via masked card prediction."""
    n_transitions = args._replay_db.transition_count()
    min_transitions = 500

    if n_transitions < min_transitions:
        print()
        print("=" * 70)
        print(f"  Stage 4: Pre-train transformer — SKIPPED "
              f"({n_transitions} transitions, need {min_transitions}+)")
        print("=" * 70)
        print()
        return

    bundle_path = CHECKPOINT_DIR / "embedder_bundle.pt"
    if not bundle_path.exists():
        print("  Stage 4: Pre-train transformer — SKIPPED (no embedder bundle)")
        return

    cmd = [
        PYTHON, str(ROOT / "scripts" / "pretrain_transformer.py"),
        "--db-path", str(args._replay_db.db_path),
        "--embedder-bundle", str(bundle_path),
        "--steps", str(args.pretrain_steps),
        "--batch-size", "128",
        "--device", "cpu",
    ]

    label = f"Stage 4: Pre-train transformer (loop {loop_num})"
    run_step(label, cmd, allow_fail=True)


def step_reembed_replay(args, loop_num: int) -> None:
    """Stage 5: Re-embed replay data with updated transformer."""
    n_transitions = args._replay_db.transition_count()
    if n_transitions == 0:
        print("  Stage 5: Re-embed — SKIPPED (no transitions)")
        return

    bundle_path = CHECKPOINT_DIR / "embedder_bundle.pt"
    if not bundle_path.exists():
        print("  Stage 5: Re-embed — SKIPPED (no embedder bundle)")
        return

    cmd = [
        PYTHON, str(ROOT / "scripts" / "reembed_replay.py"),
        "--db-path", str(args._replay_db.db_path),
        "--embedder-bundle", str(bundle_path),
        "--batch-size", "256",
        "--device", "cpu",
    ]

    label = f"Stage 5: Re-embed replay data (loop {loop_num})"
    run_step(label, cmd, allow_fail=True)

    print_summary("Re-embedding results", {
        "Transitions re-embedded": n_transitions,
    })


def step_train_player_bot(args, loop_num: int) -> None:
    """Stage 6: Train IQL player bot on frozen embeddings."""
    n_transitions = args._replay_db.transition_count()
    min_transitions = 500  # minimum to begin training

    if n_transitions < min_transitions:
        print()
        print("=" * 70)
        print(f"  Stage 6: Train player bot — SKIPPED "
              f"({n_transitions} transitions, need {min_transitions}+)")
        print("=" * 70)
        print()
        return

    replay_db_path = args._replay_db.db_path
    out_dir = str(CHECKPOINT_DIR / "iql" / f"loop{loop_num}")

    # Find the most recent checkpoint from any previous loop to resume from.
    # Searches loops in descending order so loop N-1 is preferred over older loops.
    prev_ckpt = None
    for prev_loop in range(loop_num - 1, -1, -1):
        prev_dir = CHECKPOINT_DIR / "iql" / f"loop{prev_loop}"
        candidates = sorted(prev_dir.glob("*/checkpoint_final.pt")) if prev_dir.exists() else []
        if candidates:
            prev_ckpt = candidates[-1]
            break

    cmd = [
        PYTHON, "-m", "rl_agents.train_iql",
        "--db-path", str(replay_db_path),
        "--embedder-bundle", str(CHECKPOINT_DIR / "embedder_bundle.pt"),
        "--steps", str(args.iql_steps),
        "--batch-size", "256",
        "--device", args.iql_device,
        "--out-dir", out_dir,
        "--normalize-rewards",
        "--trainable-embedder",
    ]
    if prev_ckpt is not None:
        cmd.extend(["--resume-from", str(prev_ckpt)])

    label = f"Stage 6: Train IQL player bot (loop {loop_num})"
    run_step(label, cmd, allow_fail=True)

    # Check for checkpoint — train_iql saves to out_dir/<run_name>/checkpoint_final.pt
    ckpt_candidates = sorted(Path(out_dir).glob("*/checkpoint_final.pt"))
    if ckpt_candidates:
        ckpt = ckpt_candidates[-1]  # most recent run
        summary = {
            "Transitions used": n_transitions,
            "Checkpoint": str(ckpt),
        }
        if prev_ckpt is not None:
            summary["Resumed from"] = str(prev_ckpt)
        print_summary("Player bot training results", summary)

        # Update on-disk embedder bundle with trained e2e weights from IQL checkpoint
        # so that evaluation and future game collection use the improved encoder.
        _update_bundle_from_checkpoint(ckpt)
    else:
        print("  WARNING: IQL training produced no checkpoint.")


def step_train_deck_bot(args, loop_num: int) -> None:
    """Stage 5: Train deck evaluator on game outcomes."""
    n_games = args._game_data_store.game_count()
    min_games = 10  # minimum to begin training

    if n_games < min_games:
        print()
        print("=" * 70)
        print(f"  Stage 5: Train deck evaluator — SKIPPED "
              f"({n_games} games, need {min_games}+)")
        print("=" * 70)
        print()
        return

    game_data_db = args._game_data_store.db_path

    cmd = [
        PYTHON, str(ROOT / "scripts" / "train_deck_evaluator.py"),
        "--games-db", str(game_data_db),
    ]

    # Resume from existing checkpoint if available
    ckpt = find_best_checkpoint("deck_eval_finetune") or find_best_checkpoint("deck_eval_bootstrap")
    if ckpt:
        cmd.extend(["--resume", str(ckpt)])

    label = f"Stage 5: Train deck evaluator (loop {loop_num})"
    run_step(label, cmd, allow_fail=True)

    new_ckpt = find_best_checkpoint("deck_eval_finetune")
    if new_ckpt:
        print_summary("Deck evaluator training results", {
            "Games used": n_games,
            "Checkpoint": str(new_ckpt),
        })


def step_evolve_decks(args, loop_num: int) -> None:
    """Stage 6: Evolve decks using the trained evaluator."""
    ckpt = find_best_checkpoint("deck_eval_finetune") or find_best_checkpoint("deck_eval_bootstrap")
    if not ckpt:
        print()
        print("=" * 70)
        print("  Stage 6: Evolve decks — SKIPPED (no evaluator checkpoint)")
        print("=" * 70)
        print()
        return

    game_data_db = args._game_data_store.db_path
    cmd = [
        PYTHON, "-m", "rl_agents.deck_search", "export",
        "--checkpoint", str(ckpt),
        "--output-dir", str(GENERATED_DIR),
        "--game-data-db", str(game_data_db),
    ]

    label = f"Stage 6: Evolve decks (loop {loop_num})"
    run_step(label, cmd, allow_fail=True)

    n_decks = len(list(GENERATED_DIR.glob("*.txt"))) if GENERATED_DIR.exists() else 0
    print_summary("Deck evolution results", {
        "Deck files": n_decks,
        "Output dir": str(GENERATED_DIR),
    })


def step_benchmark(args, loop_num: int) -> dict[str, float] | None:
    """Stage 9: Benchmark player bot vs random, heuristic, and previous checkpoint.

    Returns dict of win rates {"vs_random": float, "vs_heuristic": float,
    "vs_previous": float | None} or None if benchmark was skipped.
    """
    print()
    print("=" * 70)
    print(f"  Stage 9: Benchmark (loop {loop_num})")
    print("=" * 70)
    print()

    t0 = time.time()

    # Find the latest IQL checkpoint — train_iql saves inside a timestamped subdir
    iql_dir = CHECKPOINT_DIR / "iql" / f"loop{loop_num}"
    ckpt_candidates = sorted(iql_dir.glob("*/checkpoint_final.pt")) if iql_dir.exists() else []
    current_ckpt = ckpt_candidates[-1] if ckpt_candidates else None
    if not current_ckpt or not current_ckpt.exists():
        current_ckpt = find_best_checkpoint("player_bot")
    if not current_ckpt or not current_ckpt.exists():
        print("  No player bot checkpoint found — skipping benchmark.")
        print(f"\n  [SKIP] Stage 9: Benchmark ({time.time() - t0:.1f}s)")
        return None

    from rl_agents.game_backends import LocalEngineBackend, GameRunRequest
    from rl_agents.random_agent import RandomAgent
    from rl_agents.heuristic_bot import HeuristicBot

    if args._card_db is None:
        from engine.card import CardDB
        from config import SLUG_INDEX_PATH
        args._card_db = CardDB(str(SLUG_INDEX_PATH))

    backend = LocalEngineBackend()
    n_bench = 10  # games per opponent type
    results_table: dict[str, str] = {}
    rates: dict[str, float] = {}

    # Collect valid decks for benchmarking
    deck_files = sorted(GENERATED_DIR.glob("*.txt")) if GENERATED_DIR.exists() else []
    if len(deck_files) < 2:
        print("  Not enough decks for benchmark — need at least 2.")
        print(f"\n  [SKIP] Stage 9: Benchmark ({time.time() - t0:.1f}s)")
        return None

    import random as _random
    rng = _random.Random(args.seed + loop_num * 999)

    def _run_bench_games(p1_agent, p2_agent, label: str) -> float:
        """Run n_bench games and return P1 win rate."""
        wins = 0
        completed = 0
        for i in range(n_bench):
            d1, d2 = rng.sample(deck_files, 2)
            try:
                req = GameRunRequest(
                    p1_deck=str(d1),
                    p2_deck=str(d2),
                    p1_agent=p1_agent,
                    p2_agent=p2_agent,
                    card_db=args._card_db,
                    p1_seed=args.seed + i,
                    p2_seed=args.seed + i + 1,
                    max_turns=args.max_turns,
                )
                result = backend.run_game(req)
                completed += 1
                if hasattr(result, 'winner') and result.winner == 1:
                    wins += 1
            except Exception as e:
                print(f"    {label} game {i}: error — {e}")
        rate = wins / completed if completed > 0 else 0.0
        return rate

    # Load IQL agent for benchmarking
    try:
        from rl_agents.evaluate_iql_vs_random import IQLPolicyAgent
        from rl_agents.embedder_bundle import load_embedder_bundle

        embedder_bundle = args._embedder_bundle
        if embedder_bundle is None:
            import torch
            ckpt_data = torch.load(str(current_ckpt), map_location="cpu", weights_only=False)
            embedder_bundle = (ckpt_data.get("extra") or {}).get("embedder_bundle")

        if embedder_bundle is None:
            print("  No embedder bundle available — skipping benchmark.")
            print(f"\n  [SKIP] Stage 9: Benchmark ({time.time() - t0:.1f}s)")
            return None

        iql_agent = IQLPolicyAgent(
            checkpoint_path=str(current_ckpt),
            player_id=1,
            device=args.iql_device,
            seed=args.seed,
            embedder_bundle=embedder_bundle,
        )
    except Exception as e:
        print(f"  Failed to load IQL agent: {e}")
        print(f"\n  [SKIP] Stage 9: Benchmark ({time.time() - t0:.1f}s)")
        return None

    # Benchmark vs random
    random_agent = RandomAgent(seed=args.seed + 100)
    rates["vs_random"] = _run_bench_games(iql_agent, random_agent, "vs_random")
    results_table["vs Random"] = f"{rates['vs_random']:.1%} ({n_bench} games)"

    # Benchmark vs heuristic
    heuristic_agent = HeuristicBot(seed=args.seed + 200)
    rates["vs_heuristic"] = _run_bench_games(iql_agent, heuristic_agent, "vs_heuristic")
    results_table["vs Heuristic"] = f"{rates['vs_heuristic']:.1%} ({n_bench} games)"

    # Benchmark vs previous checkpoint (if exists)
    prev_ckpt = _find_previous_checkpoint(loop_num)
    if prev_ckpt is not None:
        try:
            prev_agent = IQLPolicyAgent(
                checkpoint_path=str(prev_ckpt),
                player_id=2,
                device=args.iql_device,
                seed=args.seed + 300,
                embedder_bundle=embedder_bundle,
            )
            rates["vs_previous"] = _run_bench_games(iql_agent, prev_agent, "vs_previous")
            results_table["vs Previous"] = f"{rates['vs_previous']:.1%} ({n_bench} games)"
        except Exception as e:
            results_table["vs Previous"] = f"error — {e}"
    else:
        results_table["vs Previous"] = "skipped (no prior checkpoint)"

    elapsed = time.time() - t0

    # Print win rate summary table
    print()
    print("  ┌─────────────────────┬──────────────────────────┐")
    print("  │ Opponent            │ Win Rate                 │")
    print("  ├─────────────────────┼──────────────────────────┤")
    for opp, rate_str in results_table.items():
        print(f"  │ {opp:<19} │ {rate_str:<24} │")
    print("  └─────────────────────┴──────────────────────────┘")

    print(f"\n  [OK] Stage 9: Benchmark ({elapsed:.1f}s)")
    return rates


def _find_previous_checkpoint(loop_num: int) -> Path | None:
    """Find the most recent IQL checkpoint from a previous loop."""
    for prev_l in range(loop_num - 1, -1, -1):
        prev_dir = CHECKPOINT_DIR / "iql" / f"loop{prev_l}"
        if prev_dir.exists():
            candidates = sorted(prev_dir.glob("*/checkpoint_final.pt"))
            if candidates:
                return candidates[-1]
    return None


def _evaluate_checkpoint_promotion(
    loop_num: int,
    bench_rates: dict[str, float] | None,
) -> bool:
    """Decide whether to keep the current loop's checkpoint.

    Rules:
    - First checkpoint ever (no previous): always keep
    - Otherwise keep if:
        (vs_random >= 75% AND vs_heuristic >= 75% AND vs_previous > 50%)
    - If benchmark was skipped/failed: keep (benefit of the doubt)
    """
    prev_ckpt = _find_previous_checkpoint(loop_num)
    is_first = prev_ckpt is None

    if is_first:
        print("  Checkpoint promotion: ACCEPTED (first checkpoint)")
        return True

    if bench_rates is None:
        print("  Checkpoint promotion: ACCEPTED (benchmark skipped)")
        return True

    vs_random = bench_rates.get("vs_random", 0.0)
    vs_heuristic = bench_rates.get("vs_heuristic", 0.0)
    vs_previous = bench_rates.get("vs_previous")

    # If vs_previous wasn't run (error/skip), only check absolute thresholds
    if vs_previous is None:
        if vs_random >= 0.75 and vs_heuristic >= 0.75:
            print(f"  Checkpoint promotion: ACCEPTED "
                  f"(random={vs_random:.0%}, heuristic={vs_heuristic:.0%})")
            return True
        print(f"  Checkpoint promotion: REJECTED "
              f"(random={vs_random:.0%}<75%, heuristic={vs_heuristic:.0%}<75%)")
        return False

    if vs_random >= 0.75 and vs_heuristic >= 0.75 and vs_previous > 0.50:
        print(f"  Checkpoint promotion: ACCEPTED "
              f"(random={vs_random:.0%}, heuristic={vs_heuristic:.0%}, "
              f"vs_prev={vs_previous:.0%})")
        return True

    print(f"  Checkpoint promotion: REJECTED "
          f"(random={vs_random:.0%}, heuristic={vs_heuristic:.0%}, "
          f"vs_prev={vs_previous:.0%}) — "
          f"need >=75% random+heuristic and >50% vs previous")
    return False


def _discard_loop_checkpoint(loop_num: int) -> None:
    """Remove the current loop's IQL checkpoint so the previous best stays active."""
    import shutil
    loop_dir = CHECKPOINT_DIR / "iql" / f"loop{loop_num}"
    if loop_dir.exists():
        shutil.rmtree(loop_dir)
        print(f"  Discarded checkpoint at {loop_dir}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the local-engine training and evolution pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Skip flags
    skip = parser.add_argument_group("skip steps")
    skip.add_argument("--skip-validate", action="store_true",
                      help="Skip deck validation (use all decks)")
    skip.add_argument("--skip-games", action="store_true",
                      help="Skip game simulation")
    skip.add_argument("--skip-pretrain", action="store_true",
                      help="Skip transformer pre-training (masked card prediction)")
    skip.add_argument("--skip-reembed", action="store_true",
                      help="Skip re-embedding replay data with updated transformer")
    skip.add_argument("--skip-player-train", action="store_true",
                      help="Skip IQL player bot training")
    skip.add_argument("--skip-deck-train", action="store_true",
                      help="Skip deck evaluator training")
    skip.add_argument("--skip-evolve", action="store_true",
                      help="Skip deck evolution")
    skip.add_argument("--skip-benchmark", action="store_true",
                      help="Skip player bot benchmarking")

    # Game settings
    games_g = parser.add_argument_group("game settings")
    games_g.add_argument("--games-per-loop", type=int, default=100,
                         help="Games to simulate per loop iteration (default: 100)")
    games_g.add_argument("--max-turns", type=int, default=200,
                         help="Turn cap per game (default: 200)")

    # Training settings
    train_g = parser.add_argument_group("training settings")
    train_g.add_argument("--pretrain-steps", type=int, default=5000,
                         help="Transformer pre-training steps per loop (default: 5000)")
    train_g.add_argument("--iql-steps", type=int, default=20000,
                         help="IQL training steps per loop (default: 20000)")
    train_g.add_argument("--iql-device", default="dml",
                         help="Torch device for IQL training/inference (default: dml)")

    # Loop settings
    loop_g = parser.add_argument_group("loop settings")
    loop_g.add_argument("--loops", type=int, default=1,
                        help="Number of pipeline loop iterations (default: 1)")
    loop_g.add_argument("--loop-forever", action="store_true",
                        help="Loop until interrupted (Ctrl+C)")

    # General
    parser.add_argument("--seed", type=int, default=random.randint(0, 999999),
                        help="Global RNG seed (default: random)")

    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = build_parser()
    args = parser.parse_args()

    # Signal handling
    signal.signal(signal.SIGINT, _handle_signal)
    if sys.platform == "win32":
        signal.signal(signal.SIGBREAK, _handle_signal)

    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    (ROOT / "data").mkdir(parents=True, exist_ok=True)

    # Use fixed database paths so data accumulates across runs
    from rl_agents.game_data import GameDataStore
    from data_collection.replay_db import ReplayDB

    game_data_store = GameDataStore(db_path=str(ROOT / "data" / "game_data.db"))
    replay_db_path = ROOT / "data" / "replay.db"
    replay_db = ReplayDB(str(replay_db_path))

    # Attach DB objects to args for easy passing
    args._game_data_store = game_data_store
    args._replay_db = replay_db
    args._card_db = None       # lazily loaded in step_run_games
    args._embedder_bundle = None  # initialized below

    # Initialize embedder bundle (create from scratch if missing)
    bundle_path = CHECKPOINT_DIR / "embedder_bundle.pt"
    if bundle_path.exists():
        from rl_agents.embedder_bundle import load_embedder_bundle
        args._embedder_bundle = load_embedder_bundle(str(bundle_path))
        print(f"  Loaded embedder bundle from {bundle_path}")
        if "game_transformer_state_dict" in args._embedder_bundle:
            print(f"    GameTransformerEncoder: d_model={args._embedder_bundle.get('game_transformer_d_model')},"
                  f" n_heads={args._embedder_bundle.get('game_transformer_n_heads')},"
                  f" n_layers={args._embedder_bundle.get('game_transformer_n_layers')},"
                  f" output_dim={args._embedder_bundle.get('game_transformer_output_dim')}")
    else:
        try:
            from engine.card import CardDB
            from config import SLUG_INDEX_PATH
            from encoder.card_embedder import SlugVocab
            from encoder.action_embedder import ActionEmbedder
            from encoder.gamestate_embedder import GameStateEmbedder
            from encoder.game_transformer import GameTransformerEncoder, prime_dummy_vocab
            from rl_agents.embedder_bundle import build_embedder_bundle, save_embedder_bundle

            card_db = CardDB(str(SLUG_INDEX_PATH))
            args._card_db = card_db
            slug_vocab = SlugVocab.from_card_db(card_db)

            # ActionEmbedder uses d_model=128 (unchanged)
            action_d_model = 128
            action_embedder = ActionEmbedder(
                d_model=action_d_model, slug_vocab_size=slug_vocab.size, slug_vocab=slug_vocab,
            )

            # Legacy GameStateEmbedder kept for backward compat
            state_embedder = GameStateEmbedder(
                d_model=action_d_model, slug_vocab_size=slug_vocab.size, slug_vocab=slug_vocab,
            )

            # New transformer encoder
            prime_dummy_vocab(card_db)
            gt_d_model = 256
            gt_n_heads = 8
            gt_n_layers = 4
            gt_hero_head_dim = 64
            game_transformer = GameTransformerEncoder(
                slug_vocab_size=slug_vocab.size,
                d_model=gt_d_model,
                n_heads=gt_n_heads,
                n_layers=gt_n_layers,
                hero_head_dim=gt_hero_head_dim,
            )
            # Populate the card_feats_lookup buffer so tokenize_to_packed() and
            # forward_packed_batch() can look up numeric card features by slug index.
            game_transformer.set_card_feats_lookup(card_db)

            args._embedder_bundle = build_embedder_bundle(
                action_embedder, state_embedder, game_transformer=game_transformer,
            )
            save_embedder_bundle(
                str(bundle_path), action_embedder, state_embedder,
                game_transformer=game_transformer,
            )
            print(f"  Created fresh embedder bundle at {bundle_path}")
            print(f"    GameTransformerEncoder: d_model={gt_d_model}, n_heads={gt_n_heads},"
                  f" n_layers={gt_n_layers}, output_dim={game_transformer.get_output_dim()}")
        except Exception as e:
            print(f"  FATAL: Could not create embedder bundle: {e}")
            raise

    if args._embedder_bundle is None:
        print("  FATAL: No embedder bundle available. Cannot run pipeline.")
        sys.exit(1)

    pipeline_start = time.time()

    print()
    print("#" * 70)
    print("#  FAB Local Engine Pipeline")
    print("#" * 70)
    print()
    print(f"  Seed:           {args.seed}")
    print(f"  Loops:          {'∞' if args.loop_forever else args.loops}")
    print(f"  Games/loop:     {args.games_per_loop}")
    print(f"  Max turns:      {args.max_turns}")
    print(f"  Pretrain steps: {args.pretrain_steps}")
    print(f"  IQL steps:      {args.iql_steps}")
    print(f"  IQL device:     {args.iql_device}")
    print()

    # Determine loop count
    max_loops = args.loops if not args.loop_forever else float('inf')
    loop_num = 0

    while loop_num < max_loops:
        if _interrupted:
            break

        if max_loops > 1:
            print()
            print("#" * 70)
            loop_label = f"Loop {loop_num + 1}"
            if not args.loop_forever:
                loop_label += f"/{args.loops}"
            print(f"#  {loop_label}")
            print("#" * 70)

        # Stage 1: Validate decks
        if not args.skip_validate:
            valid_decks = step_validate_decks(args)
            if _interrupted:
                break
        else:
            # Use all deck files without validation
            valid_decks = sorted(
                str(p) for p in GENERATED_DIR.glob("*.txt")
            ) if GENERATED_DIR.exists() else []
            if not valid_decks:
                print("  FATAL: No deck files found in", GENERATED_DIR)
                sys.exit(1)
            print(f"\n  [SKIP] Deck validation — using {len(valid_decks)} decks")

        # Stage 2: Run games
        if not args.skip_games:
            # Lazy-load card DB and embedder bundle
            if args._card_db is None:
                from engine.card import CardDB
                from config import SLUG_INDEX_PATH
                args._card_db = CardDB(str(SLUG_INDEX_PATH))

            # Create opponent pool:
            # P1 = current best IQL model (learner)
            # P2 = mix of current model (self-play), previous checkpoints, heuristic
            from rl_agents.local_game_runner import OpponentPool

            # Find current best checkpoint (most recent loop)
            current_ckpt = None
            for prev_l in range(loop_num, -1, -1):
                prev_loop_dir = CHECKPOINT_DIR / "iql" / f"loop{prev_l}"
                if prev_loop_dir.exists():
                    candidates = sorted(prev_loop_dir.glob("*/checkpoint_final.pt"))
                    if candidates:
                        current_ckpt = str(candidates[-1])
                        break

            # Collect older checkpoints (everything except the current best)
            prev_ckpts: list[str] = []
            for prev_l in range(loop_num):
                prev_loop_dir = CHECKPOINT_DIR / "iql" / f"loop{prev_l}"
                if prev_loop_dir.exists():
                    candidates = sorted(prev_loop_dir.glob("*/checkpoint_final.pt"))
                    for c in candidates:
                        if str(c) != current_ckpt:
                            prev_ckpts.append(str(c))

            opponent_pool = OpponentPool(
                heuristic_seed=args.seed + loop_num,
                current_checkpoint=current_ckpt,
                previous_checkpoints=prev_ckpts if prev_ckpts else None,
                device=args.iql_device,
                embedder_bundle=args._embedder_bundle,
            )

            if current_ckpt:
                print(f"  P1: IQL model ({Path(current_ckpt).parent.name})")
            else:
                print(f"  P1: Heuristic (no IQL checkpoint yet)")
            print(f"  P2 pool: {len(opponent_pool._p2_pool)} opponents "
                  f"({sum(1 for a in opponent_pool._p2_pool if a['type'] == 'iql_policy')} IQL, "
                  f"{sum(1 for a in opponent_pool._p2_pool if a['type'] == 'heuristic')} heuristic)")

            step_run_games(args, valid_decks, loop_num, opponent_pool)
            if _interrupted:
                break
        else:
            print(f"\n  [SKIP] Game simulation")

        # Stage 3: Verify data
        step_upload_data(args)
        if _interrupted:
            break

        # Stage 4: Pre-train transformer (masked card prediction)
        if not args.skip_pretrain:
            step_pretrain_transformer(args, loop_num)
            if _interrupted:
                break
        else:
            print(f"\n  [SKIP] Transformer pre-training")

        # Stage 5: Re-embed replay data with updated transformer
        if not args.skip_reembed:
            step_reembed_replay(args, loop_num)
            if _interrupted:
                break
        else:
            print(f"\n  [SKIP] Re-embedding")

        # Stage 6: Train player bot (IQL on frozen embeddings)
        if not args.skip_player_train:
            step_train_player_bot(args, loop_num)
            if _interrupted:
                break
        else:
            print(f"\n  [SKIP] Player bot training")

        # Stage 7: Train deck evaluator
        if not args.skip_deck_train:
            step_train_deck_bot(args, loop_num)
            if _interrupted:
                break
        else:
            print(f"\n  [SKIP] Deck evaluator training")

        # Stage 8: Evolve decks
        if not args.skip_evolve:
            step_evolve_decks(args, loop_num)
            if _interrupted:
                break
        else:
            print(f"\n  [SKIP] Deck evolution")

        # Stage 9: Benchmark + checkpoint promotion gate
        bench_rates = None
        if not args.skip_benchmark:
            bench_rates = step_benchmark(args, loop_num)
            if _interrupted:
                break
        else:
            print(f"\n  [SKIP] Benchmark")

        # Decide whether to keep or discard this loop's checkpoint
        if not args.skip_player_train:
            promoted = _evaluate_checkpoint_promotion(loop_num, bench_rates)
            if not promoted:
                _discard_loop_checkpoint(loop_num)

        loop_num += 1

    # -----------------------------------------------------------------------
    # Final summary
    # -----------------------------------------------------------------------
    elapsed = time.time() - pipeline_start

    print()
    print("#" * 70)
    print("#  Pipeline Complete")
    print("#" * 70)

    n_games = replay_db.game_count()
    n_transitions = replay_db.transition_count()

    print_summary("Final state", {
        "Loops completed": loop_num,
        "Games collected": n_games,
        "Transitions collected": n_transitions,
        "Total pipeline time": f"{elapsed:.1f}s ({elapsed/60:.1f}m)",
    })

    if _interrupted:
        print("  (Pipeline was interrupted early)")

    # Cleanup
    game_data_store.close()
    replay_db.close()

    print()


if __name__ == "__main__":
    main()
