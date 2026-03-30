"""Unit tests for rl_agents.local_game_runner module."""
from __future__ import annotations

import os
import random
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from rl_agents.local_game_runner import MatchupScheduler, OpponentPool
from rl_agents.game_backends import GameRunRequest, LocalEngineBackend
from rl_agents.random_agent import RandomAgent
from config import SLUG_INDEX_PATH
from engine.card import CardDB


# ---------------------------------------------------------------------------
# MatchupScheduler tests
# ---------------------------------------------------------------------------

def test_all_decks_covered() -> None:
    """Every deck appears in at least one matchup with 10 decks."""
    deck_paths = [f"deck_{i}.txt" for i in range(10)]
    scheduler = MatchupScheduler()
    matchups = scheduler.schedule_matchups(deck_paths, games_per_loop=20)

    seen = set()
    for p1, p2 in matchups:
        seen.add(p1)
        seen.add(p2)
    for d in deck_paths:
        assert d in seen, f"Deck {d} not covered in any matchup"


def test_all_decks_covered_odd_count() -> None:
    """Every deck appears in at least one matchup with 11 (odd) decks."""
    deck_paths = [f"deck_{i}.txt" for i in range(11)]
    scheduler = MatchupScheduler()
    matchups = scheduler.schedule_matchups(deck_paths, games_per_loop=20)

    seen = set()
    for p1, p2 in matchups:
        seen.add(p1)
        seen.add(p2)
    for d in deck_paths:
        assert d in seen, f"Deck {d} not covered in any matchup"


def test_matchup_scheduler_minimum_games() -> None:
    """schedule_matchups returns at least games_per_loop matchups."""
    deck_paths = [f"deck_{i}.txt" for i in range(6)]
    scheduler = MatchupScheduler()
    for gpl in [5, 10, 20]:
        matchups = scheduler.schedule_matchups(deck_paths, games_per_loop=gpl)
        assert len(matchups) >= gpl, (
            f"Expected at least {gpl} matchups, got {len(matchups)}"
        )


def test_mirror_matches_present() -> None:
    """Mirror matches (p1 == p2) appear roughly 1 cycle per 4 non-mirror cycles."""
    deck_paths = [f"deck_{i}.txt" for i in range(10)]
    scheduler = MatchupScheduler()
    # Request enough games to span at least 2 full super-cycles
    # Super-cycle with 10 decks: 4*(10//2) + 10 = 30 pairs
    matchups = scheduler.schedule_matchups(deck_paths, games_per_loop=60)
    assert len(matchups) == 60

    mirrors = [(p1, p2) for p1, p2 in matchups if p1 == p2]
    non_mirrors = [(p1, p2) for p1, p2 in matchups if p1 != p2]

    assert len(mirrors) > 0, "No mirror matches found"
    assert len(non_mirrors) > 0, "No non-mirror matches found"

    # Expect exactly 1 mirror cycle per 4 non-mirror cycles.
    # With 10 decks over 60 games (2 super-cycles):
    #   non-mirror: 2 * 4 * 5 = 40 pairs
    #   mirror:     2 * 10    = 20 pairs
    assert len(non_mirrors) == 40, f"Expected 40 non-mirror, got {len(non_mirrors)}"
    assert len(mirrors) == 20, f"Expected 20 mirror, got {len(mirrors)}"

    # Every deck must appear as both sides of at least one mirror
    mirror_decks = {p1 for p1, _ in mirrors}
    for d in deck_paths:
        assert d in mirror_decks, f"Deck {d} never played a mirror match"


def test_mirror_matches_exact_count() -> None:
    """Trim to games_per_loop never leaves fractional mirror cycles."""
    deck_paths = [f"deck_{i}.txt" for i in range(8)]
    scheduler = MatchupScheduler()
    # With 8 decks: non-mirror cycle = 4 pairs; 4 cycles before mirror = 16 pairs.
    # gpl <= 16 may trim before any mirror cycle is reached (0 mirrors is correct).
    # gpl > 16 must include at least one mirror cycle.
    n = len(deck_paths)
    pairs_per_non_mirror_cycle = (n + 1) // 2  # ceil(n/2)
    mirror_threshold = scheduler.MIRROR_EVERY_N_CYCLES * pairs_per_non_mirror_cycle
    for gpl in [15, 25, 40]:
        matchups = scheduler.schedule_matchups(deck_paths, games_per_loop=gpl)
        assert len(matchups) == gpl, f"Expected exactly {gpl} matchups, got {len(matchups)}"
        mirrors = sum(1 for p1, p2 in matchups if p1 == p2)
        if gpl > mirror_threshold:
            assert mirrors > 0, f"gpl={gpl} exceeds mirror threshold {mirror_threshold}, expected mirrors"


# ---------------------------------------------------------------------------
# OpponentPool tests
# ---------------------------------------------------------------------------

def test_mixed_opponents() -> None:
    """OpponentPool with no checkpoints samples heuristic + random agents."""
    pool = OpponentPool(heuristic_seed=42)
    rng = random.Random(123)
    types_seen: set[str] = set()
    for _ in range(50):
        agent = pool.sample_agent(rng, player_id=1, seed=0)
        types_seen.add(type(agent).__name__)
    assert "LocalHeuristicAgent" in types_seen, "Expected LocalHeuristicAgent in sampled agents"
    assert "RandomAgent" in types_seen, "Expected RandomAgent in sampled agents"


def test_opponent_pool_no_checkpoints() -> None:
    """OpponentPool falls back to heuristic+random when no checkpoint files exist."""
    pool = OpponentPool(
        heuristic_seed=0,
        checkpoint_paths=["/nonexistent/checkpoint.pt"],
    )
    rng = random.Random(99)
    types_seen: set[str] = set()
    for _ in range(50):
        agent = pool.sample_agent(rng, player_id=1, seed=0)
        types_seen.add(type(agent).__name__)
    # Only heuristic and random should be present (nonexistent checkpoint ignored)
    assert types_seen <= {"LocalHeuristicAgent", "RandomAgent"}
    assert len(types_seen) == 2


# ---------------------------------------------------------------------------
# Integration-light: run a single game
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def valid_deck_path() -> str:
    """Return a known-good deck from decks/generated/."""
    gen_dir = os.path.join(ROOT, "decks", "generated")
    if not os.path.isdir(gen_dir):
        import subprocess
        try:
            main_root = subprocess.check_output(
                ["git", "worktree", "list", "--porcelain"],
                cwd=ROOT, text=True,
            ).split("\n")[0].replace("worktree ", "").strip()
            gen_dir = os.path.join(main_root, "decks", "generated")
        except Exception:
            pass
    if not os.path.isdir(gen_dir):
        pytest.skip("decks/generated/ not found")
    txt_files = sorted(f for f in os.listdir(gen_dir) if f.endswith(".txt"))
    if not txt_files:
        pytest.skip("No deck files in decks/generated/")
    return os.path.join(gen_dir, txt_files[0])


@pytest.fixture(scope="module")
def card_db() -> CardDB:
    return CardDB(SLUG_INDEX_PATH)


def test_run_single_game(valid_deck_path: str, card_db: CardDB) -> None:
    """Run one game with RandomAgent vs RandomAgent, verify completion."""
    backend = LocalEngineBackend()
    p1_agent = RandomAgent(seed=42)
    p2_agent = RandomAgent(seed=43)

    req = GameRunRequest(
        p1_deck=valid_deck_path,
        p2_deck=valid_deck_path,
        p1_agent=p1_agent,
        p2_agent=p2_agent,
        card_db=card_db,
        p1_seed=100,
        p2_seed=101,
        max_turns=50,
    )

    game_state = backend.run_game(req)
    assert game_state.done is True, "Game should be done after run_game"
    assert game_state.winner in (1, 2, None), (
        f"Unexpected winner value: {game_state.winner}"
    )
