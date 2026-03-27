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
import signal
import subprocess
import sqlite3
import sys
import time
from datetime import datetime
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
    """Run a subprocess step, printing its output in real time."""
    print()
    print("=" * 70)
    print(f"  {description}")
    print("=" * 70)
    print(f"  CMD: {' '.join(cmd)}")
    print()

    t0 = time.time()
    result = subprocess.run(cmd, cwd=str(ROOT))
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

    deck_dir = str(GENERATED_DIR)
    valid_paths, invalid_report = validate_all_decks(deck_dir)

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

    n_games = args._game_data_store.game_count()
    n_transitions = args._game_data_store.transition_count()

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

    n_games = args._game_data_store.game_count()
    n_transitions = args._game_data_store.transition_count()

    if n_games == 0:
        print("  WARNING: No games recorded in database.")
    if n_transitions == 0:
        print("  WARNING: No transitions recorded in database.")

    elapsed = time.time() - t0

    print_summary("Data verification", {
        "Games in DB": n_games,
        "Transitions in DB": n_transitions,
        "Database": str(args._game_data_store.db_path)
                    if hasattr(args._game_data_store, 'db_path') else "N/A",
        "Elapsed": f"{elapsed:.1f}s",
    })

    print(f"\n  [OK] Stage 3: Verify data upload ({elapsed:.1f}s)")


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
    train_g.add_argument("--iql-steps", type=int, default=20000,
                         help="IQL training steps per loop (default: 20000)")
    train_g.add_argument("--iql-device", default="cpu",
                         help="Torch device for IQL training/inference (default: cpu)")

    # Loop settings
    loop_g = parser.add_argument_group("loop settings")
    loop_g.add_argument("--loops", type=int, default=1,
                        help="Number of pipeline loop iterations (default: 1)")
    loop_g.add_argument("--loop-forever", action="store_true",
                        help="Loop until interrupted (Ctrl+C)")

    # General
    parser.add_argument("--seed", type=int, default=42,
                        help="Global RNG seed (default: 42)")

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

    # Create fresh databases for this run
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    from rl_agents.game_data import GameDataStore
    from data_collection.replay_db import ReplayDB

    game_data_store = GameDataStore.create_fresh(
        base_dir=str(ROOT / "data"),
        prefix="local_pipeline",
    )
    replay_db_path = ROOT / "data" / f"replay_{timestamp}.db"
    replay_db = ReplayDB(str(replay_db_path))

    # Attach DB objects to args for easy passing
    args._game_data_store = game_data_store
    args._replay_db = replay_db
    args._card_db = None       # lazily loaded in step_run_games
    args._embedder_bundle = None  # lazily loaded

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

            # Create opponent pool
            from rl_agents.local_game_runner import OpponentPool
            opponent_pool = OpponentPool(
                heuristic_seed=args.seed + loop_num,
                checkpoint_paths=None,  # TODO: collect prev checkpoints
                device=args.iql_device,
                embedder_bundle=args._embedder_bundle,
            )

            step_run_games(args, valid_decks, loop_num, opponent_pool)
            if _interrupted:
                break
        else:
            print(f"\n  [SKIP] Game simulation")

        # Stage 3: Verify data
        step_upload_data(args)
        if _interrupted:
            break

        # Stages 4-7 will be added in Part 2
        loop_num += 1

    # -----------------------------------------------------------------------
    # Final summary
    # -----------------------------------------------------------------------
    elapsed = time.time() - pipeline_start

    print()
    print("#" * 70)
    print("#  Pipeline Complete")
    print("#" * 70)

    n_games = game_data_store.game_count()
    n_transitions = game_data_store.transition_count()

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
