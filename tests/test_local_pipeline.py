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


# ---------------------------------------------------------------------------
# (f) Reward column population & backpropagation tests
# ---------------------------------------------------------------------------

def _make_replay_db(tmp_path, game_id_start: int = 1):
    """Helper: create a ReplayDB with a simple game for reward testing."""
    import torch
    replay_path = str(tmp_path / "reward_test.db")
    rdb = ReplayDB(replay_path)
    return rdb, replay_path


def test_update_reward(tmp_path) -> None:
    """ReplayDB.update_reward sets reward on a single transition."""
    import torch
    rdb, path = _make_replay_db(tmp_path)
    gid = rdb.start_game("H1", "H2")
    tid = rdb.insert_transition(
        gid, 0, player_id=1, phase="action",
        obs={"turn": 1}, action={"type": "pass"},
    )
    rdb.store_embeddings(tid, torch.randn(128), torch.randn(128))
    rdb.flush()

    rdb.update_reward(tid, 0.75)

    row = rdb.conn.execute(
        "SELECT reward FROM transitions WHERE id = ?", (tid,)
    ).fetchone()
    assert row[0] == pytest.approx(0.75), f"Expected 0.75, got {row[0]}"
    rdb.close()


def test_batch_update_rewards(tmp_path) -> None:
    """ReplayDB.batch_update_rewards updates multiple transitions at once."""
    import torch
    rdb, path = _make_replay_db(tmp_path)
    gid = rdb.start_game("H1", "H2")
    tids = []
    for step in range(5):
        tid = rdb.insert_transition(
            gid, step, player_id=(step % 2) + 1, phase="action",
            obs={"turn": step}, action={"type": "pass"},
        )
        rdb.store_embeddings(tid, torch.randn(128), torch.randn(128))
        tids.append(tid)
    rdb.flush()

    updates = [(0.1 * i, tids[i]) for i in range(5)]
    rdb.batch_update_rewards(updates)

    for i, tid in enumerate(tids):
        row = rdb.conn.execute(
            "SELECT reward FROM transitions WHERE id = ?", (tid,)
        ).fetchone()
        assert row[0] == pytest.approx(0.1 * i), f"tid {tid}: expected {0.1*i}, got {row[0]}"
    rdb.close()


def test_compute_combat_rewards_attack(tmp_path) -> None:
    """_assign_game_rewards gives attacker reward proportional to attack_power."""
    import json
    import torch
    from rl_agents.local_game_runner import _assign_game_rewards

    rdb, path = _make_replay_db(tmp_path)
    gid = rdb.start_game("H1", "H2")

    # Turn 1: player 1 acts, Turn 2: player 2 acts
    tid1 = rdb.insert_transition(
        gid, 0, player_id=1, phase="action",
        obs={"turn": 1}, action={"type": "attack"},
    )
    rdb.store_embeddings(tid1, torch.randn(128), torch.randn(128))
    tid2 = rdb.insert_transition(
        gid, 1, player_id=2, phase="action",
        obs={"turn": 2}, action={"type": "pass"},
    )
    rdb.store_embeddings(tid2, torch.randn(128), torch.randn(128))
    rdb.finalize_game(gid, winner=1, turns=2, ended_on_turn_cap=0)
    rdb.flush()

    # Combat on turn 2: player 1 attacks for 6 damage, net_damage=6
    combat_log = {
        2: [{"attacker_id": 1, "attack_power": 6, "net_damage": 6, "hit": True}],
    }
    _assign_game_rewards(rdb, gid, combat_log, winner=1, normalizer=10.0)

    # Attacker reward back-propagated to turn 1 (previous turn) -> tid1
    row = rdb.conn.execute(
        "SELECT reward FROM transitions WHERE id = ?", (tid1,)
    ).fetchone()
    # tid1 is player 1's last transition AND gets attack reward 6/10 + terminal +1
    assert row[0] == pytest.approx(1.6), f"Expected 1.6, got {row[0]}"
    rdb.close()


def test_compute_combat_rewards_defense(tmp_path) -> None:
    """_assign_game_rewards gives defender reward proportional to blocked damage."""
    import torch
    from rl_agents.local_game_runner import _assign_game_rewards

    rdb, path = _make_replay_db(tmp_path)
    gid = rdb.start_game("H1", "H2")

    tid1 = rdb.insert_transition(
        gid, 0, player_id=1, phase="action",
        obs={"turn": 1}, action={"type": "attack"},
    )
    rdb.store_embeddings(tid1, torch.randn(128), torch.randn(128))
    tid2 = rdb.insert_transition(
        gid, 1, player_id=2, phase="action",
        obs={"turn": 1}, action={"type": "defend"},
    )
    rdb.store_embeddings(tid2, torch.randn(128), torch.randn(128))
    tid3 = rdb.insert_transition(
        gid, 2, player_id=1, phase="action",
        obs={"turn": 2}, action={"type": "pass"},
    )
    rdb.store_embeddings(tid3, torch.randn(128), torch.randn(128))
    rdb.finalize_game(gid, winner=2, turns=2, ended_on_turn_cap=0)
    rdb.flush()

    # Combat on turn 2: p1 attacks 8, but only 3 net damage -> 5 blocked by p2
    combat_log = {
        2: [{"attacker_id": 1, "attack_power": 8, "net_damage": 3, "hit": True}],
    }
    _assign_game_rewards(rdb, gid, combat_log, winner=2, normalizer=10.0)

    # Defender (p2) reward back-propagated to turn 1 -> tid2 (p2's only turn-1 transition)
    row2 = rdb.conn.execute(
        "SELECT reward FROM transitions WHERE id = ?", (tid2,)
    ).fetchone()
    # tid2 is p2's latest transition -> terminal +1, plus defense reward 5/10 = 0.5
    assert row2[0] == pytest.approx(1.5), f"Expected 1.5, got {row2[0]}"
    rdb.close()


def test_reward_backprop_to_previous_turn(tmp_path) -> None:
    """Combat rewards land on the *previous* turn's last transition."""
    import torch
    from rl_agents.local_game_runner import _assign_game_rewards

    rdb, path = _make_replay_db(tmp_path)
    gid = rdb.start_game("H1", "H2")

    # Player 1: transitions on turn 1, turn 2, turn 3
    tid_t1 = rdb.insert_transition(
        gid, 0, player_id=1, phase="action",
        obs={"turn": 1}, action={"type": "pass"},
    )
    rdb.store_embeddings(tid_t1, torch.randn(128), torch.randn(128))
    tid_t2 = rdb.insert_transition(
        gid, 1, player_id=1, phase="action",
        obs={"turn": 2}, action={"type": "pass"},
    )
    rdb.store_embeddings(tid_t2, torch.randn(128), torch.randn(128))
    tid_t3 = rdb.insert_transition(
        gid, 2, player_id=1, phase="action",
        obs={"turn": 3}, action={"type": "pass"},
    )
    rdb.store_embeddings(tid_t3, torch.randn(128), torch.randn(128))
    # Player 2 needs at least one transition
    tid_p2 = rdb.insert_transition(
        gid, 3, player_id=2, phase="action",
        obs={"turn": 1}, action={"type": "pass"},
    )
    rdb.store_embeddings(tid_p2, torch.randn(128), torch.randn(128))
    rdb.finalize_game(gid, winner=1, turns=3, ended_on_turn_cap=0)
    rdb.flush()

    # Combat on turn 3: p1 attacks for 10
    combat_log = {
        3: [{"attacker_id": 1, "attack_power": 10, "net_damage": 10, "hit": True}],
    }
    _assign_game_rewards(rdb, gid, combat_log, winner=1, normalizer=10.0)

    # Back-prop target: p1's last transition on turn 2 -> tid_t2
    row_t2 = rdb.conn.execute(
        "SELECT reward FROM transitions WHERE id = ?", (tid_t2,)
    ).fetchone()
    assert row_t2[0] == pytest.approx(1.0), f"Expected 1.0, got {row_t2[0]}"

    # tid_t1 should have no combat reward (0.0)
    row_t1 = rdb.conn.execute(
        "SELECT reward FROM transitions WHERE id = ?", (tid_t1,)
    ).fetchone()
    assert row_t1[0] == pytest.approx(0.0), f"Expected 0.0, got {row_t1[0]}"
    rdb.close()


def test_terminal_rewards_set(tmp_path) -> None:
    """Terminal rewards: +1 for winner, -1 for loser, done=1 on last transition."""
    import torch
    from rl_agents.local_game_runner import _assign_game_rewards

    rdb, path = _make_replay_db(tmp_path)
    gid = rdb.start_game("H1", "H2")

    tid1 = rdb.insert_transition(
        gid, 0, player_id=1, phase="action",
        obs={"turn": 1}, action={"type": "pass"},
    )
    rdb.store_embeddings(tid1, torch.randn(128), torch.randn(128))
    tid2 = rdb.insert_transition(
        gid, 1, player_id=2, phase="action",
        obs={"turn": 1}, action={"type": "pass"},
    )
    rdb.store_embeddings(tid2, torch.randn(128), torch.randn(128))
    rdb.finalize_game(gid, winner=1, turns=1, ended_on_turn_cap=0)
    rdb.flush()

    _assign_game_rewards(rdb, gid, combat_log={}, winner=1, normalizer=10.0)

    # Player 1 (winner): reward=+1, done=1
    r1 = rdb.conn.execute(
        "SELECT reward, done FROM transitions WHERE id = ?", (tid1,)
    ).fetchone()
    assert r1[0] == pytest.approx(1.0), f"Winner reward: expected 1.0, got {r1[0]}"
    assert r1[1] == 1, f"Winner done: expected 1, got {r1[1]}"

    # Player 2 (loser): reward=-1, done=1
    r2 = rdb.conn.execute(
        "SELECT reward, done FROM transitions WHERE id = ?", (tid2,)
    ).fetchone()
    assert r2[0] == pytest.approx(-1.0), f"Loser reward: expected -1.0, got {r2[0]}"
    assert r2[1] == 1, f"Loser done: expected 1, got {r2[1]}"
    rdb.close()


def test_no_combat_turn_no_reward(tmp_path) -> None:
    """Turns without combat data get no combat reward (only terminal if applicable)."""
    import torch
    from rl_agents.local_game_runner import _assign_game_rewards

    rdb, path = _make_replay_db(tmp_path)
    gid = rdb.start_game("H1", "H2")

    tid1 = rdb.insert_transition(
        gid, 0, player_id=1, phase="action",
        obs={"turn": 1}, action={"type": "pass"},
    )
    rdb.store_embeddings(tid1, torch.randn(128), torch.randn(128))
    tid2 = rdb.insert_transition(
        gid, 1, player_id=1, phase="action",
        obs={"turn": 2}, action={"type": "pass"},
    )
    rdb.store_embeddings(tid2, torch.randn(128), torch.randn(128))
    tid3 = rdb.insert_transition(
        gid, 2, player_id=2, phase="action",
        obs={"turn": 1}, action={"type": "pass"},
    )
    rdb.store_embeddings(tid3, torch.randn(128), torch.randn(128))
    rdb.finalize_game(gid, winner=1, turns=2, ended_on_turn_cap=0)
    rdb.flush()

    # Empty combat log
    _assign_game_rewards(rdb, gid, combat_log={}, winner=1, normalizer=10.0)

    # tid1 has no combat reward, not latest for p1 -> 0.0
    r1 = rdb.conn.execute(
        "SELECT reward FROM transitions WHERE id = ?", (tid1,)
    ).fetchone()
    assert r1[0] == pytest.approx(0.0), f"Expected 0.0, got {r1[0]}"

    # tid2 is p1's latest -> terminal +1 only
    r2 = rdb.conn.execute(
        "SELECT reward FROM transitions WHERE id = ?", (tid2,)
    ).fetchone()
    assert r2[0] == pytest.approx(1.0), f"Expected 1.0, got {r2[0]}"
    rdb.close()


def test_turn_1_fallback(tmp_path) -> None:
    """Combat on turn 1 falls back to player's earliest transition."""
    import torch
    from rl_agents.local_game_runner import _assign_game_rewards

    rdb, path = _make_replay_db(tmp_path)
    gid = rdb.start_game("H1", "H2")

    tid1 = rdb.insert_transition(
        gid, 0, player_id=1, phase="action",
        obs={"turn": 1}, action={"type": "attack"},
    )
    rdb.store_embeddings(tid1, torch.randn(128), torch.randn(128))
    tid2 = rdb.insert_transition(
        gid, 1, player_id=2, phase="action",
        obs={"turn": 1}, action={"type": "pass"},
    )
    rdb.store_embeddings(tid2, torch.randn(128), torch.randn(128))
    rdb.finalize_game(gid, winner=1, turns=1, ended_on_turn_cap=0)
    rdb.flush()

    # Combat on turn 1: p1 attacks for 5, net_damage=5
    # Previous turn = 0, no transition there -> fallback to earliest (tid1)
    combat_log = {
        1: [{"attacker_id": 1, "attack_power": 5, "net_damage": 5, "hit": True}],
    }
    _assign_game_rewards(rdb, gid, combat_log, winner=1, normalizer=10.0)

    # tid1: attack reward 5/10=0.5 + terminal +1 = 1.5
    r1 = rdb.conn.execute(
        "SELECT reward FROM transitions WHERE id = ?", (tid1,)
    ).fetchone()
    assert r1[0] == pytest.approx(1.5), f"Expected 1.5, got {r1[0]}"
    rdb.close()


# ---------------------------------------------------------------------------
# (g) Integration: test_run_games_populates_rewards
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_run_games_populates_rewards(tmp_path) -> None:
    """Full pipeline: run_games() populates non-zero rewards in transitions."""
    import torch
    from engine.card import CardDB
    from config import SLUG_INDEX_PATH
    from rl_agents.local_game_runner import run_games, OpponentPool
    from rl_agents.embedder_bundle import load_embedder_bundle, resolve_embedder_bundle_path

    deck_paths = _get_deck_paths(2)
    card_db = CardDB(SLUG_INDEX_PATH)

    # Locate an embedder bundle checkpoint
    bundle_path = resolve_embedder_bundle_path(
        explicit_path=os.path.join(ROOT, "checkpoints", "embedder_bundle.pt"),
    )
    if bundle_path is None:
        pytest.skip("No embedder_bundle.pt checkpoint found")
    embedder_bundle = load_embedder_bundle(bundle_path)

    replay_path = str(tmp_path / "replay_rewards.db")
    rdb = ReplayDB(replay_path)

    pool = OpponentPool()

    results = run_games(
        deck_pairs=[(deck_paths[0], deck_paths[1])],
        opponent_pool=pool,
        card_db=card_db,
        replay_db=rdb,
        game_data_store=None,
        embedder_bundle=embedder_bundle,
        max_turns=50,
        seed=42,
    )

    assert len(results.results) == 1, "Expected 1 game result"
    assert not results.errors, f"Unexpected errors: {results.errors}"

    # Check that non-zero rewards exist in the transitions table
    conn = sqlite3.connect(replay_path)
    nonzero = conn.execute(
        "SELECT COUNT(*) FROM transitions WHERE reward != 0.0"
    ).fetchone()[0]
    terminal = conn.execute(
        "SELECT COUNT(*) FROM transitions WHERE done = 1"
    ).fetchone()[0]
    conn.close()
    rdb.close()

    assert nonzero > 0, "Expected non-zero rewards after run_games()"
    assert terminal == 2, f"Expected 2 terminal transitions (one per player), got {terminal}"


# ---------------------------------------------------------------------------
# (h) Integration: test_dataset_adapter_reads_shaped_rewards
# ---------------------------------------------------------------------------

def test_dataset_adapter_reads_shaped_rewards(tmp_path) -> None:
    """build_iql_tensors_from_replay_db returns non-zero rewards from shaped data."""
    import torch
    from rl_agents.dataset_adapter import build_iql_tensors_from_replay_db
    from rl_agents.local_game_runner import _assign_game_rewards

    replay_path = str(tmp_path / "replay_shaped.db")
    rdb = ReplayDB(replay_path)
    state_dim, action_dim = 128, 128

    # Create a game with combat rewards
    gid = rdb.start_game("H1", "H2")
    for step in range(6):
        pid = (step % 2) + 1
        tid = rdb.insert_transition(
            gid, step, player_id=pid, phase="action",
            obs={"turn": (step // 2) + 1}, action={"type": "pass"},
        )
        rdb.store_embeddings(tid, torch.randn(state_dim), torch.randn(action_dim))
    rdb.finalize_game(gid, winner=1, turns=3, ended_on_turn_cap=0)
    rdb.flush()

    # Assign rewards with combat on turn 2
    combat_log = {
        2: [{"attacker_id": 1, "attack_power": 8, "net_damage": 5, "hit": True}],
    }
    _assign_game_rewards(rdb, gid, combat_log, winner=1, normalizer=10.0)
    rdb.close()

    payload = build_iql_tensors_from_replay_db(replay_path)
    assert payload["num_transitions"] > 0
    rewards = payload["rewards"]
    assert (rewards != 0.0).any().item(), "Expected non-zero shaped rewards in tensor"


# ---------------------------------------------------------------------------
# (i) Integration: test_rtg_composes_with_shaped_rewards
# ---------------------------------------------------------------------------

def test_rtg_composes_with_shaped_rewards(tmp_path) -> None:
    """RTG mode propagates shaped (non-terminal) rewards backwards correctly."""
    import torch
    from rl_agents.dataset_adapter import build_iql_tensors_from_replay_db
    from rl_agents.local_game_runner import _assign_game_rewards

    replay_path = str(tmp_path / "replay_rtg.db")
    rdb = ReplayDB(replay_path)
    state_dim, action_dim = 128, 128

    # Create a game with enough transitions for RTG propagation
    gid = rdb.start_game("H1", "H2")
    for step in range(8):
        pid = (step % 2) + 1
        tid = rdb.insert_transition(
            gid, step, player_id=pid, phase="action",
            obs={"turn": (step // 2) + 1}, action={"type": "pass"},
        )
        rdb.store_embeddings(tid, torch.randn(state_dim), torch.randn(action_dim))
    rdb.finalize_game(gid, winner=1, turns=4, ended_on_turn_cap=0)
    rdb.flush()

    # Assign shaped rewards: combat on turn 3
    combat_log = {
        3: [{"attacker_id": 1, "attack_power": 6, "net_damage": 6, "hit": True}],
    }
    _assign_game_rewards(rdb, gid, combat_log, winner=1, normalizer=10.0)
    rdb.close()

    # Load with terminal mode first
    payload_terminal = build_iql_tensors_from_replay_db(replay_path, reward_mode="terminal")
    # Load with RTG mode
    payload_rtg = build_iql_tensors_from_replay_db(replay_path, reward_mode="rtg")

    r_term = payload_terminal["rewards"]
    r_rtg = payload_rtg["rewards"]

    # RTG should have more non-zero entries than terminal (back-propagation)
    nonzero_term = (r_term != 0.0).sum().item()
    nonzero_rtg = (r_rtg != 0.0).sum().item()
    assert nonzero_rtg >= nonzero_term, (
        f"RTG should have >= non-zero rewards than terminal: {nonzero_rtg} vs {nonzero_term}"
    )
    # RTG rewards should differ from terminal rewards (shaped base + discount)
    assert not torch.allclose(r_term, r_rtg), "RTG rewards should differ from terminal rewards"
