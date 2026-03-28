"""scripts/run_pipeline.py

Automated pipeline for the FAB deck bot:
    1. (Optional) Scrape fablazing meta data  — skipped by default, use --scrape
    2. Generate heuristic decks
    3. Bootstrap-train the deck evaluator
    4. Run Talishar games to collect real data
    5. Fine-tune the evaluator on game outcomes
    6. Export evolved decks (replaces heuristic decks for next loop)
    7. Run tournament benchmark
    8. (Optional) Loop: games -> fine-tune -> export -> benchmark

Player-bot (IQL) training is integrated into each loop:
    4.5  Train IQL player bot on collected transitions (requires --min-iql-transitions)
    4.6  Benchmark candidate vs random; accept only if beats threshold + margin
         Benchmarking is phase-gated (skipped until 5k transitions, then every 3rd
         loop until 50k, every loop until 200k, then every 3rd loop again)

Usage:
    # First data collection run (scraping skipped by default)
    python scripts/run_pipeline.py --loops 5 --games-per-loop 100

    # Enable fablazing scraping
    python scripts/run_pipeline.py --scrape

    # Skip game collection (no Docker / just want to benchmark bootstrap)
    python scripts/run_pipeline.py --skip-games

    # Multiple iteration loops
    python scripts/run_pipeline.py --loops 3 --games-per-loop 200

    # Resume from existing checkpoint
    python scripts/run_pipeline.py --skip-bootstrap --resume checkpoints/deck_eval_bootstrap_best.pt
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sqlite3
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
META_DB = ROOT / "data" / "fablazing_meta.db"
GAMES_DB = ROOT / "data" / "talishar_games.db"
CHECKPOINT_DIR = ROOT / "checkpoints"
DECKS_DIR = ROOT / "decks"
GENERATED_DIR = ROOT / "decks" / "generated"
IQL_BEST_CKPT = CHECKPOINT_DIR / "player_bot_best.pt"     # accepted player bot checkpoint
IQL_BEST_RATE_FILE = CHECKPOINT_DIR / "player_bot_best_win_rate.txt"  # stored win rate

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


def talishar_reachable(base_url: str) -> bool:
    """Check if a Talishar server responds."""
    try:
        import requests
        r = requests.get(base_url, timeout=3)
        return r.status_code < 500
    except Exception:
        return False


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
# Pipeline steps
# ---------------------------------------------------------------------------

def step_scrape(args) -> None:
    """Step 1: Scrape fablazing meta data."""
    run_step(
        "Step 1: Scrape fablazing.com meta data",
        [PYTHON, str(ROOT / "scripts" / "scrape_fablazing.py"),
         "--db", str(META_DB)],
    )
    n_heroes = db_row_count(META_DB, "heroes")
    n_cards = db_row_count(META_DB, "card_stats")
    print_summary("Scrape results", {
        "Heroes": n_heroes,
        "Card-hero entries": n_cards,
        "Database": str(META_DB),
    })


def step_generate_decks(args) -> None:
    """Step 2: Generate heuristic decks."""
    run_step(
        "Step 2: Generate heuristic decks from play-rate data",
        [PYTHON, str(ROOT / "scripts" / "generate_heuristic_decks.py"),
         "--all", "--mutate", str(args.mutate_variants),
         "--db", str(META_DB),
         "--output-dir", str(GENERATED_DIR)],
    )
    n_decks = len(list(GENERATED_DIR.glob("*.txt"))) if GENERATED_DIR.exists() else 0
    print_summary("Deck generation results", {
        "Generated decks": n_decks,
        "Output dir": str(GENERATED_DIR),
    })


def step_bootstrap_train(args) -> Path:
    """Step 3: Bootstrap-train the deck evaluator."""
    cmd = [
        PYTHON, str(ROOT / "scripts" / "train_deck_evaluator.py"),
        "--bootstrap",
        "--model", args.model,
        "--epochs", str(args.epochs),
        "--batch-size", str(args.batch_size),
        "--samples-per-hero", str(args.samples_per_hero),
        "--seed", str(args.seed),
        "--meta-db", str(META_DB),
    ]
    if args.resume:
        cmd.extend(["--resume", str(args.resume)])

    run_step("Step 3: Bootstrap-train deck evaluator", cmd)

    ckpt = find_best_checkpoint("deck_eval_bootstrap")
    if ckpt:
        print_summary("Bootstrap training results", {
            "Model": args.model,
            "Checkpoint": str(ckpt),
        })
    else:
        print("  WARNING: No checkpoint found after training")
        ckpt = CHECKPOINT_DIR / "deck_eval_bootstrap_final.pt"

    return ckpt


def _get_recent_game_ids(db_path: Path, max_games: int) -> list[int] | None:
    """Return game IDs of the most recent max_games games with outcomes, or None for all."""
    if max_games <= 0 or not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(str(db_path))
        # Use `decks` table (actual schema) ordered by rowid descending → most recent first
        rows = conn.execute(
            """
            SELECT game_id FROM decks
            WHERE winner IS NOT NULL
            ORDER BY rowid DESC
            LIMIT ?
            """,
            (max_games,),
        ).fetchall()
        conn.close()
        return [r[0] for r in rows] or None
    except Exception:
        return None


def _bench_phase(n_transitions: int) -> tuple[bool, int]:
    """Return (should_ever_bench, bench_every_N_loops) based on data phase.

    Phase 1 (<5k):    no benchmarking — value estimates too noisy
    Phase 2 (5k-50k): bench every 3 loops — learning fast, high variance
    Phase 3 (50k-200k): bench every loop — stable incremental gains
    Phase 4 (200k+):  bench every 3 loops — improvements shrink
    """
    if n_transitions < 5_000:
        return False, 0
    elif n_transitions < 50_000:
        return True, 3
    elif n_transitions < 200_000:
        return True, 1
    else:
        return True, 3


def _read_best_win_rate() -> float:
    """Return the stored best player-bot win rate, or 0.0 if none exists."""
    if IQL_BEST_RATE_FILE.exists():
        try:
            return float(IQL_BEST_RATE_FILE.read_text().strip())
        except Exception:
            pass
    return 0.0


def _write_best_win_rate(rate: float) -> None:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    IQL_BEST_RATE_FILE.write_text(f"{rate:.6f}")


def step_train_player_bot(args, loop_num: int = 0) -> Path | None:
    """Step 4.5: Train IQL player bot on collected game transitions."""
    n_transitions = db_row_count(GAMES_DB, "transitions")
    min_transitions = args.min_iql_transitions
    if n_transitions < min_transitions:
        print()
        print("=" * 70)
        print(f"  Step 4.5: Train player bot — SKIPPED ({n_transitions} transitions, need {min_transitions}+)")
        print("=" * 70)
        print()
        return None

    run_dir = ROOT / "data_collection" / "iql_runs" / f"loop{loop_num}"
    cmd = [
        PYTHON, "-m", "rl_agents.train_iql",
        "--db-path", str(GAMES_DB),
        "--steps", str(args.iql_steps),
        "--batch-size", str(args.iql_batch_size),
        "--device", args.iql_device,
        "--out-dir", str(run_dir.parent),
        "--run-name", run_dir.name,
    ]

    # Replay buffer cap: only train on the most recent N games to avoid
    # off-policy contamination from old weak-policy trajectories.
    recent_ids = _get_recent_game_ids(GAMES_DB, args.iql_replay_buffer_games)
    if recent_ids is not None:
        cmd += ["--game-ids"] + [str(g) for g in recent_ids]

    label = "Step 4.5: Train IQL player bot"
    if loop_num > 0:
        label += f" (loop {loop_num})"
    run_step(label, cmd, allow_fail=True)

    candidate = run_dir / "checkpoint_final.pt"
    if not candidate.exists():
        print("  WARNING: IQL training produced no checkpoint.")
        return None
    print_summary("Player bot training results", {
        "Transitions used": n_transitions,
        "Recent games cap": args.iql_replay_buffer_games or "unlimited",
        "Checkpoint": str(candidate),
    })
    return candidate


def step_bench_player_bot(
    args,
    candidate_ckpt: Path,
    loop_num: int = 0,
) -> Path | None:
    """Step 4.6: Benchmark candidate IQL checkpoint vs random.

    Phase-gated: only runs when enough data exists and at the right loop cadence.
    Accepts only if win_rate > max(0.50, previous_best) + acceptance_margin.
    Returns the accepted checkpoint path, or None if rejected.
    """
    n_transitions = db_row_count(GAMES_DB, "transitions")
    should_bench, every_n = _bench_phase(n_transitions)
    if not should_bench:
        print()
        print("=" * 70)
        print(f"  Step 4.6: Bench player bot — SKIPPED (phase 1: only {n_transitions} transitions, need 5000+)")
        print("=" * 70)
        print()
        return IQL_BEST_CKPT if IQL_BEST_CKPT.exists() else None

    if every_n > 1 and loop_num % every_n != 0:
        print()
        print("=" * 70)
        phase = 2 if n_transitions < 50_000 else 4
        print(f"  Step 4.6: Bench player bot — SKIPPED (phase {phase}: bench every {every_n} loops, loop={loop_num})")
        print("=" * 70)
        print()
        return IQL_BEST_CKPT if IQL_BEST_CKPT.exists() else None

    prev_best = _read_best_win_rate()
    margin = getattr(args, "acceptance_margin", 0.02)
    threshold = max(0.50, prev_best) + margin

    urls = [u.strip() for u in args.talishar_urls.split(",") if u.strip()]
    live_urls = [u for u in urls if talishar_reachable(u)]
    if not live_urls:
        print()
        print("=" * 70)
        print("  Step 4.6: Bench player bot — SKIPPED (no Talishar server)")
        print("=" * 70)
        print()
        return IQL_BEST_CKPT if IQL_BEST_CKPT.exists() else None

    base_url = ",".join(live_urls)
    cmd = [
        PYTHON, str(ROOT / "scripts" / "bench_player_bot.py"),
        "--checkpoint", str(candidate_ckpt),
        "--base-url", base_url,
        "--games", str(args.iql_bench_games),
        "--max-turns", str(args.max_turns),
        "--workers", str(args.game_workers),
        "--device", args.iql_device,
        "--seed", str(args.seed + loop_num * 7),
    ]
    label = "Step 4.6: Benchmark player bot vs random"
    if loop_num > 0:
        label += f" (loop {loop_num})"

    import subprocess as _sp
    print()
    print("=" * 70)
    print(f"  {label}")
    print("=" * 70)
    t0 = time.time()
    proc = _sp.run(cmd, cwd=str(ROOT), text=True, stdout=_sp.PIPE, stderr=None)
    elapsed = time.time() - t0
    output = proc.stdout or ""
    print(output)

    # Parse win rate from output
    win_rate = None
    for line in output.splitlines():
        if line.startswith("PLAYER_BOT_WIN_RATE"):
            try:
                win_rate = float(line.split()[1])
            except (IndexError, ValueError):
                pass

    if win_rate is None:
        print(f"  WARNING: Could not parse win rate from bench output.")
        return IQL_BEST_CKPT if IQL_BEST_CKPT.exists() else None

    accepted = win_rate > threshold
    print(f"\n  Candidate win rate : {win_rate:.3f}")
    print(f"  Threshold          : {threshold:.3f}  (prev_best={prev_best:.3f} + margin={margin:.2f})")
    print(f"  Decision           : {'ACCEPT' if accepted else 'REJECT'}")

    if accepted:
        import shutil as _shutil
        _shutil.copy2(str(candidate_ckpt), str(IQL_BEST_CKPT))
        _write_best_win_rate(win_rate)
        print(f"  Saved to           : {IQL_BEST_CKPT}")
        print_summary("Player bot benchmark", {
            "Win rate": f"{win_rate:.3f}",
            "Previous best": f"{prev_best:.3f}",
            "Checkpoint": str(IQL_BEST_CKPT),
            "Elapsed": f"{elapsed:.1f}s",
        })
        return IQL_BEST_CKPT
    else:
        print(f"  Checkpoint rejected — keeping previous best ({IQL_BEST_CKPT if IQL_BEST_CKPT.exists() else 'none'})")
        return IQL_BEST_CKPT if IQL_BEST_CKPT.exists() else None


def step_run_games(args, loop_num: int = 0, iql_agent_ckpt: Path | None = None) -> int:
    """Step 4: Run Talishar games for data collection."""
    # Check server availability
    urls = [u.strip() for u in args.talishar_urls.split(",") if u.strip()]
    live_urls = [u for u in urls if talishar_reachable(u)]

    if not live_urls:
        print()
        print("=" * 70)
        print("  Step 4: Run Talishar games — SKIPPED (no server reachable)")
        print("=" * 70)
        print()
        print("  Talishar servers not found at:")
        for u in urls:
            print(f"    {u}")
        print()
        print("  To start Talishar:")
        print("    cd third_party/Talishar_official && docker compose up -d")
        print()
        print("  Or skip game collection:")
        print("    python scripts/run_pipeline.py --skip-games")
        print()
        return 0

    n_games = args.games_per_loop
    base_url = ",".join(live_urls)
    seed = args.seed + loop_num * 10000

    cmd = [
        PYTHON, str(ROOT / "scripts" / "run_talishar_games.py"),
        "--base-url", base_url,
        "--random-decks",
        "--num-games", str(n_games),
        "--workers", str(args.game_workers),
        "--max-turns", str(args.max_turns),
        "--game-timeout", "0",
        "--benchmark",
        "--seed", str(seed),
        "--db", str(GAMES_DB),
    ]
    # Use IQL agent for P1 if an accepted checkpoint exists.
    # Pass the checkpoint as both --iql-agent and --iql-bundle so the
    # TalisharIQLAgent can extract the embedded bundle from extra["embedder_bundle"].
    if iql_agent_ckpt and iql_agent_ckpt.exists():
        cmd += [
            "--iql-agent", str(iql_agent_ckpt),
            "--iql-bundle", str(iql_agent_ckpt),
            "--iql-device", args.iql_device,
        ]

    label = f"Step 4: Run {n_games} Talishar games"
    if loop_num > 0:
        label += f" (loop {loop_num})"

    run_step(label, cmd, allow_fail=True)

    n_total = db_row_count(GAMES_DB, "decks")
    print_summary("Game collection results", {
        "Games this run": n_games,
        "Total games in DB": n_total,
        "Servers used": len(live_urls),
        "Database": str(GAMES_DB),
    })
    return n_total


def step_finetune(args, resume_ckpt: Path, loop_num: int = 0) -> Path:
    """Step 5: Fine-tune evaluator on game outcomes."""
    n_games = db_row_count(GAMES_DB, "decks")
    if n_games < 10:
        print()
        print("=" * 70)
        print(f"  Step 5: Fine-tune — SKIPPED (only {n_games} games, need 10+)")
        print("=" * 70)
        print()
        return resume_ckpt

    cmd = [
        PYTHON, str(ROOT / "scripts" / "train_deck_evaluator.py"),
        "--games-db", str(GAMES_DB),
        "--resume", str(resume_ckpt),
        "--model", args.model,
        "--epochs", str(args.finetune_epochs),
        "--batch-size", str(args.batch_size),
        "--seed", str(args.seed + loop_num),
    ]

    label = "Step 5: Fine-tune on game outcomes"
    if loop_num > 0:
        label += f" (loop {loop_num})"

    run_step(label, cmd)

    ckpt = find_best_checkpoint("deck_eval_finetune")
    if ckpt:
        print_summary("Fine-tuning results", {
            "Games used": n_games,
            "Checkpoint": str(ckpt),
        })
    else:
        ckpt = resume_ckpt
        print("  WARNING: No fine-tune checkpoint found, using bootstrap")

    return ckpt


def step_export_decks(args, checkpoint: Path, loop_num: int = 0) -> None:
    """Step 6: Export evolved pools as playable deck files."""
    cmd = [
        PYTHON, "-m", "rl_agents.deck_search", "export",
        "--checkpoint", str(checkpoint),
        "--output-dir", str(GENERATED_DIR),
        "--pop-size", str(args.pool_pop),
        "--generations", str(args.pool_gens),
        "--seed", str(args.seed + loop_num * 100),
    ]

    label = "Step 6: Export evolved decks"
    if loop_num > 0:
        label += f" (loop {loop_num})"

    run_step(label, cmd)

    n_decks = len(list(GENERATED_DIR.glob("*.txt"))) if GENERATED_DIR.exists() else 0
    print_summary("Deck export results", {
        "Deck files": n_decks,
        "Output dir": str(GENERATED_DIR),
    })


def step_tournament(args, checkpoint: Path, loop_num: int = 0) -> None:
    """Step 6: Run tournament benchmark."""
    cmd = [
        PYTHON, "-m", "rl_agents.deck_search", "tournament",
        "--checkpoint", str(checkpoint),
        "--players", str(args.players),
        "--rounds", str(args.rounds),
        "--pool-pop", str(args.pool_pop),
        "--pool-gens", str(args.pool_gens),
        "--strategy", args.strategy,
        "--seed", str(args.seed + loop_num * 100),
    ]

    label = f"Step 7: Tournament benchmark ({args.players} players, {args.rounds} rounds)"
    if loop_num > 0:
        label += f" (loop {loop_num})"

    run_step(label, cmd)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Run the full deck bot pipeline end-to-end",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Skip flags
    skip = parser.add_argument_group("skip steps")
    skip.add_argument("--scrape", action="store_true", default=False,
                      help="Run fablazing.com scraping (off by default — data rarely changes)")
    skip.add_argument("--skip-scrape", action="store_true", default=True,
                      help=argparse.SUPPRESS)  # deprecated; scraping now off by default
    skip.add_argument("--skip-decks", action="store_true",
                      help="Skip heuristic deck generation")
    skip.add_argument("--skip-bootstrap", action="store_true",
                      help="Skip bootstrap training (requires --resume)")
    skip.add_argument("--skip-games", action="store_true",
                      help="Skip Talishar game collection")
    skip.add_argument("--skip-finetune", action="store_true",
                      help="Skip fine-tuning on game data")
    skip.add_argument("--skip-export", action="store_true",
                      help="Skip exporting evolved decks")
    skip.add_argument("--skip-tournament", action="store_true",
                      help="Skip tournament benchmark")
    skip.add_argument("--skip-player-bot-train", action="store_true",
                      help="Skip IQL player bot training")
    skip.add_argument("--skip-player-bot-bench", action="store_true",
                      help="Skip player bot benchmark (do not update best checkpoint)")

    # Model settings
    model_g = parser.add_argument_group("model")
    model_g.add_argument("--model", default="deepsets",
                         choices=["deepsets", "set_transformer"],
                         help="Evaluator architecture (default: deepsets)")
    model_g.add_argument("--resume", type=Path, default=None,
                         help="Resume from existing checkpoint")

    # Training settings
    train_g = parser.add_argument_group("training")
    train_g.add_argument("--epochs", type=int, default=50,
                         help="Bootstrap training epochs (default: 50)")
    train_g.add_argument("--finetune-epochs", type=int, default=50,
                         help="Fine-tuning epochs (default: 50)")
    train_g.add_argument("--batch-size", type=int, default=64,
                         help="Training batch size (default: 64)")
    train_g.add_argument("--samples-per-hero", type=int, default=100,
                         help="Synthetic samples per hero for bootstrap (default: 100)")

    # Game collection settings
    games_g = parser.add_argument_group("game collection")
    games_g.add_argument("--talishar-urls", default="http://localhost:8080/game",
                         help="Comma-separated Talishar server URLs "
                              "(default: http://localhost:8080/game)")
    games_g.add_argument("--games-per-loop", type=int, default=100,
                         help="Games to collect per loop iteration (default: 100)")
    games_g.add_argument("--game-workers", type=int, default=4,
                         help="Parallel game workers (default: 4)")
    games_g.add_argument("--max-turns", type=int, default=50,
                         help="Turn cap per game (default: 50)")

    # Deck generation
    deck_g = parser.add_argument_group("deck generation")
    deck_g.add_argument("--mutate-variants", type=int, default=3,
                        help="Mutated deck variants per hero (default: 3)")

    # Tournament settings
    tourney_g = parser.add_argument_group("tournament")
    tourney_g.add_argument("--players", type=int, default=128,
                           help="Tournament player count (default: 128)")
    tourney_g.add_argument("--rounds", type=int, default=5,
                           help="Tournament Swiss rounds (default: 5)")
    tourney_g.add_argument("--pool-pop", type=int, default=50,
                           help="Evolutionary population size (default: 50)")
    tourney_g.add_argument("--pool-gens", type=int, default=20,
                           help="Evolutionary generations (default: 20)")
    tourney_g.add_argument("--strategy", default="per_round",
                           choices=["per_round", "locked"],
                           help="Pool selection strategy (default: per_round)")

    # Player bot (IQL) settings
    bot_g = parser.add_argument_group("player bot (IQL)")
    bot_g.add_argument("--iql-steps", type=int, default=20000,
                       help="IQL training steps per loop (default: 20000)")
    bot_g.add_argument("--iql-batch-size", type=int, default=256,
                       help="IQL training batch size (default: 256)")
    bot_g.add_argument("--iql-device", default="cpu",
                       help="Torch device for IQL training/inference (default: cpu)")
    bot_g.add_argument("--iql-bench-games", type=int, default=100,
                       help="Games to run when benchmarking player bot (default: 100)")
    bot_g.add_argument("--min-iql-transitions", type=int, default=5000,
                       help="Minimum DB transitions before IQL training starts (default: 5000)")
    bot_g.add_argument("--iql-replay-buffer-games", type=int, default=0,
                       help="Cap replay buffer to the N most recent games (0=unlimited, default: 0)")
    bot_g.add_argument("--acceptance-margin", type=float, default=0.02,
                       help="Win-rate margin above threshold required to accept a checkpoint (default: 0.02)")

    # Loop settings
    loop_g = parser.add_argument_group("iteration loop")
    loop_g.add_argument("--loops", type=int, default=1,
                        help="Number of game-train-benchmark loops (default: 1)")

    # General
    parser.add_argument("--seed", type=int, default=42, help="Global RNG seed")

    args = parser.parse_args()

    # Validation
    if args.skip_bootstrap and not args.resume:
        existing = find_best_checkpoint("deck_eval_bootstrap")
        if existing:
            args.resume = existing
            print(f"Found existing checkpoint: {existing}")
        else:
            parser.error("--skip-bootstrap requires --resume or an existing checkpoint")

    # Signal handling
    signal.signal(signal.SIGINT, _handle_signal)
    if sys.platform == "win32":
        signal.signal(signal.SIGBREAK, _handle_signal)

    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    (ROOT / "data").mkdir(parents=True, exist_ok=True)

    pipeline_start = time.time()

    print()
    print("#" * 70)
    print("#  FAB Deck Bot Pipeline")
    print("#" * 70)
    print()
    print(f"  Model:          {args.model}")
    print(f"  Seed:           {args.seed}")
    print(f"  Loops:          {args.loops}")
    print(f"  Games/loop:     {args.games_per_loop}")
    print(f"  Tournament:     {args.players} players, {args.rounds} rounds")
    print(f"  Strategy:       {args.strategy}")
    if args.resume:
        print(f"  Resume from:    {args.resume}")

    steps_skipped = []
    if not args.scrape:
        steps_skipped.append("scrape")
    if args.skip_decks:
        steps_skipped.append("decks")
    if args.skip_bootstrap:
        steps_skipped.append("bootstrap")
    if args.skip_games:
        steps_skipped.append("games")
    if args.skip_finetune:
        steps_skipped.append("finetune")
    if args.skip_export:
        steps_skipped.append("export")
    if args.skip_tournament:
        steps_skipped.append("tournament")
    if args.skip_player_bot_train:
        steps_skipped.append("player-bot-train")
    if args.skip_player_bot_bench:
        steps_skipped.append("player-bot-bench")
    if steps_skipped:
        print(f"  Skipping:       {', '.join(steps_skipped)}")

    # -----------------------------------------------------------------------
    # Step 1: Scrape (opt-in only)
    # -----------------------------------------------------------------------
    if args.scrape:
        step_scrape(args)
        if _interrupted:
            sys.exit(0)
    else:
        n = db_row_count(META_DB, "heroes")
        print(f"\n  [SKIP] Scrape — use --scrape to refresh ({n} heroes in DB)")

    # -----------------------------------------------------------------------
    # Step 2: Generate decks
    # -----------------------------------------------------------------------
    if not args.skip_decks:
        step_generate_decks(args)
        if _interrupted:
            sys.exit(0)
    else:
        print(f"\n  [SKIP] Deck generation")

    # -----------------------------------------------------------------------
    # Step 3: Bootstrap training
    # -----------------------------------------------------------------------
    if not args.skip_bootstrap:
        checkpoint = step_bootstrap_train(args)
        if _interrupted:
            sys.exit(0)
    else:
        checkpoint = args.resume
        print(f"\n  [SKIP] Bootstrap — using checkpoint: {checkpoint}")

    # -----------------------------------------------------------------------
    # Loop: games -> fine-tune -> player-bot train -> bench -> export -> tournament
    # -----------------------------------------------------------------------
    # Load accepted player bot checkpoint if one exists from a previous run
    active_iql_ckpt: Path | None = IQL_BEST_CKPT if IQL_BEST_CKPT.exists() else None

    for loop in range(args.loops):
        if _interrupted:
            break

        if args.loops > 1:
            print()
            print("#" * 70)
            print(f"#  Loop {loop + 1}/{args.loops}")
            print("#" * 70)

        # Step 4: Run games (uses IQL agent for P1 if available, random otherwise)
        if not args.skip_games:
            step_run_games(args, loop_num=loop, iql_agent_ckpt=active_iql_ckpt)
            if _interrupted:
                break

        # Step 4.5: Train IQL player bot on collected transitions
        if not args.skip_player_bot_train:
            iql_candidate = step_train_player_bot(args, loop_num=loop)
            if _interrupted:
                break

            # Step 4.6: Benchmark candidate vs random; accept only if beats threshold
            if iql_candidate and not args.skip_player_bot_bench:
                accepted = step_bench_player_bot(args, iql_candidate, loop_num=loop)
                if accepted:
                    active_iql_ckpt = accepted
                if _interrupted:
                    break
        else:
            print(f"\n  [SKIP] Player bot training")

        # Step 5: Fine-tune deck evaluator on game outcomes
        if not args.skip_finetune:
            checkpoint = step_finetune(args, checkpoint, loop_num=loop)
            if _interrupted:
                break

        # Step 6: Export evolved decks (for next loop's game collection)
        if not args.skip_export:
            step_export_decks(args, checkpoint, loop_num=loop)
            if _interrupted:
                break

        # Step 7: Tournament benchmark
        if not args.skip_tournament:
            step_tournament(args, checkpoint, loop_num=loop)
            if _interrupted:
                break

    # -----------------------------------------------------------------------
    # Final summary
    # -----------------------------------------------------------------------
    elapsed = time.time() - pipeline_start

    print()
    print("#" * 70)
    print("#  Pipeline Complete")
    print("#" * 70)

    n_heroes = db_row_count(META_DB, "heroes") if META_DB.exists() else 0
    n_cards = db_row_count(META_DB, "card_stats") if META_DB.exists() else 0
    n_games = db_row_count(GAMES_DB, "decks")
    n_decks = len(list(GENERATED_DIR.glob("*.txt"))) if GENERATED_DIR.exists() else 0

    print_summary("Final state", {
        "Meta DB heroes": n_heroes,
        "Meta DB card entries": n_cards,
        "Generated decks": n_decks,
        "Games collected": n_games,
        "Best checkpoint": str(checkpoint),
        "Total pipeline time": f"{elapsed:.1f}s ({elapsed/60:.1f}m)",
    })

    if _interrupted:
        print("  (Pipeline was interrupted early)")

    print()


if __name__ == "__main__":
    main()
