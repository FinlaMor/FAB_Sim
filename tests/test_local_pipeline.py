"""Integration tests for the local training and evolution pipeline."""
from __future__ import annotations

import os
import re
import sqlite3
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from rl_agents.game_data import GameDataStore
from data_collection.replay_db import ReplayDB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_decks_dir() -> str:
    """Return path to decks/generated/, checking worktree fallback."""
    gen_dir = os.path.join(ROOT, "decks", "generated")
    if os.path.isdir(gen_dir):
        return gen_dir
    import subprocess
    try:
        main_root = subprocess.check_output(
            ["git", "worktree", "list", "--porcelain"],
            cwd=ROOT, text=True,
        ).split("\n")[0].replace("worktree ", "").strip()
        gen_dir = os.path.join(main_root, "decks", "generated")
    except Exception:
        pass
    return gen_dir


def _get_deck_paths(n: int = 2) -> list[str]:
    """Return up to *n* deck file paths from decks/generated/."""
    gen_dir = _resolve_decks_dir()
    if not os.path.isdir(gen_dir):
        pytest.skip("decks/generated/ not found")
    txt_files = sorted(f for f in os.listdir(gen_dir) if f.endswith(".txt"))
    if len(txt_files) < n:
        pytest.skip(f"Need at least {n} deck files, found {len(txt_files)}")
    return [os.path.join(gen_dir, txt_files[i]) for i in range(n)]


# ---------------------------------------------------------------------------
# (a) test_fresh_db_creation
# ---------------------------------------------------------------------------

def test_fresh_db_creation(tmp_path: pytest.TempPathFactory) -> None:
    """GameDataStore.create_fresh produces a timestamped database file."""
    store = GameDataStore.create_fresh(
        base_dir=str(tmp_path),
        prefix="test_pipeline",
    )
    try:
        assert os.path.isfile(store.db_path), "DB file should exist on disk"
        basename = os.path.basename(store.db_path)
        # Expect pattern: test_pipeline_YYYYMMDD_HHMMSS.db
        assert re.match(
            r"test_pipeline_\d{8}_\d{6}\.db$", basename
        ), f"DB filename should contain timestamp, got: {basename}"
    finally:
        store.close()


# ---------------------------------------------------------------------------
# (b) test_game_results_stored
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_game_results_stored(tmp_path: pytest.TempPathFactory) -> None:
    """Run a minimal simulation and verify data lands in both DBs."""
    import torch
    from engine.card import CardDB
    from config import SLUG_INDEX_PATH
    from rl_agents.random_agent import RandomAgent
    from rl_agents.game_backends import GameRunRequest, LocalEngineBackend

    deck_paths = _get_deck_paths(2)
    card_db = CardDB(SLUG_INDEX_PATH)

    # -- GameDataStore: verify schema exists after create_fresh --
    gds = GameDataStore.create_fresh(base_dir=str(tmp_path), prefix="gds")
    conn_gds = sqlite3.connect(gds.db_path)
    tables = {r[0] for r in conn_gds.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    conn_gds.close()
    gds.close()
    assert "decks" in tables, f"Expected 'decks' table, found: {tables}"

    # -- ReplayDB: run games and record transitions + embeddings --
    replay_path = str(tmp_path / "replay_test.db")
    rdb = ReplayDB(replay_path)
    state_dim, action_dim = 128, 128

    for g in range(2):
        game_id = rdb.start_game("HeroA", "HeroB")
        for step in range(3):
            tid = rdb.insert_transition(
                game_id, step, player_id=(step % 2) + 1, phase="action",
                obs={"turn": step}, action={"type": "pass"},
            )
            rdb.store_embeddings(tid, torch.randn(state_dim), torch.randn(action_dim))
        rdb.finalize_game(game_id, winner=1, turns=3, ended_on_turn_cap=0)
    rdb.flush()

    # Verify ReplayDB has rows in transitions + embeddings
    conn_rdb = sqlite3.connect(replay_path)
    trans_rows = conn_rdb.execute("SELECT COUNT(*) FROM transitions").fetchone()[0]
    emb_rows = conn_rdb.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    game_rows = conn_rdb.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    conn_rdb.close()
    rdb.close()
    assert game_rows == 2, f"Expected 2 game rows, got {game_rows}"
    assert trans_rows == 6, f"Expected 6 transition rows, got {trans_rows}"
    assert emb_rows == 6, f"Expected 6 embedding rows, got {emb_rows}"


# ---------------------------------------------------------------------------
# (c) test_validation_to_simulation
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_validation_to_simulation() -> None:
    """Validate real decks, then run one game with a validated pair."""
    from engine.card import CardDB
    from config import SLUG_INDEX_PATH
    from rl_agents.deck_validator import validate_all_decks
    from rl_agents.random_agent import RandomAgent
    from rl_agents.game_backends import GameRunRequest, LocalEngineBackend
    import json

    gen_dir = _resolve_decks_dir()
    if not os.path.isdir(gen_dir):
        pytest.skip("decks/generated/ not found")

    card_db = CardDB(SLUG_INDEX_PATH)
    with open(SLUG_INDEX_PATH) as f:
        slug_index = json.load(f)
    by_slug = slug_index if isinstance(slug_index, dict) and "by_slug" not in slug_index else slug_index.get("by_slug", slug_index)

    valid_paths, _ = validate_all_decks(gen_dir, card_db, by_slug)
    assert len(valid_paths) >= 2, f"Need >=2 valid decks, got {len(valid_paths)}"

    backend = LocalEngineBackend()
    req = GameRunRequest(
        p1_deck=valid_paths[0],
        p2_deck=valid_paths[1],
        p1_agent=RandomAgent(seed=10),
        p2_agent=RandomAgent(seed=11),
        card_db=card_db,
        p1_seed=200,
        p2_seed=201,
        max_turns=50,
    )
    gs = backend.run_game(req)
    assert gs.done is True, "Game should complete"


# ---------------------------------------------------------------------------
# (d) test_deck_evolution_produces_valid_decks
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_deck_evolution_produces_valid_decks(tmp_path: pytest.TempPathFactory) -> None:
    """If a deck evaluator checkpoint exists, evolved decks pass validation."""
    checkpoint_dir = os.path.join(ROOT, "checkpoints")
    ckpt_path = os.path.join(checkpoint_dir, "deck_evaluator.pt")
    if not os.path.isfile(ckpt_path):
        pytest.skip("No deck_evaluator checkpoint found")

    from rl_agents.deck_search import export_evolved_decks
    from rl_agents.deck_validator import validate_all_decks
    from engine.card import CardDB
    from config import SLUG_INDEX_PATH
    import json

    out_dir = str(tmp_path / "evolved")
    os.makedirs(out_dir, exist_ok=True)

    export_evolved_decks(checkpoint=ckpt_path, output_dir=out_dir)

    card_db = CardDB(SLUG_INDEX_PATH)
    with open(SLUG_INDEX_PATH) as f:
        slug_index = json.load(f)
    by_slug = slug_index if isinstance(slug_index, dict) and "by_slug" not in slug_index else slug_index.get("by_slug", slug_index)

    valid_paths, invalid_report = validate_all_decks(out_dir, card_db, by_slug)
    assert len(valid_paths) > 0, (
        f"No valid evolved decks. Invalid: {invalid_report}"
    )


# ---------------------------------------------------------------------------
# (e) test_simulation_to_training
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_simulation_to_training(tmp_path: pytest.TempPathFactory) -> None:
    """Run games, populate ReplayDB, then verify dataset_adapter can load tensors."""
    import torch
    from rl_agents.dataset_adapter import build_iql_tensors_from_replay_db

    replay_path = str(tmp_path / "replay_train.db")
    rdb = ReplayDB(replay_path)

    state_dim, action_dim = 128, 128

    # Insert 2 synthetic games with embeddings
    for g in range(2):
        gid = rdb.start_game("Hero1", "Hero2")
        winner = (g % 2) + 1
        for step in range(5):
            pid = (step % 2) + 1
            reward = 0.0
            done = 0
            if step == 4:
                reward = 1.0 if pid == winner else -1.0
                done = 1
            tid = rdb.insert_transition(
                gid, step, player_id=pid, phase="action",
                obs={"turn": step}, action={"type": "pass"},
            )
            rdb.store_embeddings(tid, torch.randn(state_dim), torch.randn(action_dim))
            # Update reward/done on the transition row
            rdb.conn.execute(
                "UPDATE transitions SET reward = ?, done = ? WHERE id = ?",
                (reward, done, tid),
            )
        rdb.finalize_game(gid, winner=winner, turns=5, ended_on_turn_cap=0)
    rdb.flush()
    rdb.close()

    payload = build_iql_tensors_from_replay_db(replay_path)
    assert payload["num_transitions"] > 0, "Should have loaded transitions"
    assert payload["states"].shape[1] == state_dim
    assert payload["actions"].shape[1] == action_dim
    assert payload["states"].shape[0] == payload["num_transitions"]
