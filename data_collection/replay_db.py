"""Replay database for storing game transitions and embeddings.

Provides a SQLite-backed store for game results, per-step transitions,
and their corresponding state/action embeddings.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Optional


class ReplayDB:
    """Lightweight wrapper around the replay SQLite database."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_schema()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, timeout=30.0)
            self._conn.row_factory = sqlite3.Row
            # Enable WAL mode and optimize for concurrent access
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
            # Memory-map up to 4 GB of the DB file.  Lets the OS page-cache
            # serve reads directly instead of going through read() syscalls,
            # which substantially speeds up large bulk-loads of BLOB data.
            self._conn.execute("PRAGMA mmap_size=4294967296")  # 4 GB
        return self._conn

    def _ensure_schema(self) -> None:
        c = self.conn
        c.execute(
            """CREATE TABLE IF NOT EXISTS games (
                game_id INTEGER PRIMARY KEY,
                p1_hero TEXT,
                p2_hero TEXT,
                winner INTEGER,
                turns INTEGER,
                ended_on_turn_cap INTEGER,
                created_at TEXT
            )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS transitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER,
                step_idx INTEGER,
                player_id INTEGER,
                phase TEXT,
                obs TEXT,
                action TEXT,
                reward REAL DEFAULT 0.0,
                done INTEGER DEFAULT 0
            )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS embeddings (
                transition_id INTEGER PRIMARY KEY,
                state_embedding BLOB,
                action_embedding BLOB,
                state_features BLOB,
                action_features BLOB
            )"""
        )
        # Backward compat: add new columns to existing DBs that predate this schema.
        for col, ctype in [("state_features", "BLOB"), ("action_features", "BLOB")]:
            try:
                c.execute(f"ALTER TABLE embeddings ADD COLUMN {col} {ctype}")
            except Exception:
                pass  # Column already exists
        c.commit()

    def start_game(self, p1_hero: str, p2_hero: str) -> int:
        """Insert a new game row and return its game_id."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        cur = self.conn.execute(
            "INSERT INTO games (p1_hero, p2_hero, created_at) VALUES (?, ?, ?)",
            (p1_hero, p2_hero, now),
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def insert_transition(
        self,
        game_id: int,
        step_idx: int,
        player_id: int,
        phase: str,
        obs: Any,
        action: Any,
    ) -> int:
        """Insert a transition row. Returns the row id."""
        obs_str = json.dumps(obs) if not isinstance(obs, str) else obs
        action_str = json.dumps(action) if not isinstance(action, str) else action
        cur = self.conn.execute(
            """INSERT INTO transitions (game_id, step_idx, player_id, phase, obs, action)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (game_id, step_idx, player_id, phase, obs_str, action_str),
        )
        return cur.lastrowid  # type: ignore[return-value]

    def store_embeddings(
        self,
        transition_id: int,
        state_emb_tensor: Any,
        action_emb_tensor: Any,
    ) -> None:
        """Store state and action embedding tensors for a transition."""
        state_blob = state_emb_tensor.detach().cpu().numpy().tobytes()
        action_blob = action_emb_tensor.detach().cpu().numpy().tobytes()
        self.conn.execute(
            """INSERT OR REPLACE INTO embeddings (transition_id, state_embedding, action_embedding)
               VALUES (?, ?, ?)""",
            (transition_id, state_blob, action_blob),
        )

    def store_features(
        self,
        transition_id: int,
        state_feat: Any,
        action_feat: Any,
    ) -> None:
        """Store raw packed state and action feature arrays for end-to-end training.

        These are compact float32 arrays (not final embeddings) that allow the
        transformer / action_embedder to be run inside the IQL training loop with
        full gradient flow.  Use store_embeddings() for the legacy pre-computed path.
        """
        import numpy as np
        state_blob  = state_feat.astype(np.float32).tobytes()
        action_blob = action_feat.astype(np.float32).tobytes()
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO embeddings "
                "(transition_id, state_features, action_features) "
                "VALUES (?, ?, ?)",
                (transition_id, state_blob, action_blob),
            )

    def _get_conn(self):
        """Context manager yielding the connection (autocommit on exit)."""
        import contextlib

        @contextlib.contextmanager
        def _cm():
            yield self.conn
            self.conn.commit()

        return _cm()

    def finalize_game(
        self,
        game_id: int,
        winner: int,
        turns: int,
        ended_on_turn_cap: int,
    ) -> None:
        """Update a game row with final results."""
        self.conn.execute(
            """UPDATE games SET winner = ?, turns = ?, ended_on_turn_cap = ?
               WHERE game_id = ?""",
            (winner, turns, ended_on_turn_cap, game_id),
        )
        self.conn.commit()

    def game_count(self) -> int:
        """Return the number of games in the database."""
        return self.conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]

    def transition_count(self) -> int:
        """Return the number of transitions in the database."""
        return self.conn.execute("SELECT COUNT(*) FROM transitions").fetchone()[0]

    def flush(self) -> None:
        """Commit pending writes."""
        if self._conn is not None:
            self._conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def update_reward(self, transition_id: int, reward: float) -> None:
        """Update the reward for a single transition."""
        self.conn.execute(
            "UPDATE transitions SET reward = ? WHERE id = ?",
            (reward, transition_id),
        )
        self.conn.commit()

    def batch_update_rewards(self, updates: list[tuple[float, int]]) -> None:
        """Batch-update rewards. Each tuple is (reward, transition_id)."""
        BATCH = 5000
        for i in range(0, len(updates), BATCH):
            self.conn.executemany(
                "UPDATE transitions SET reward = ? WHERE id = ?",
                updates[i : i + BATCH],
            )
        self.conn.commit()

    def batch_update_done(self, updates: list[tuple[int, int]]) -> None:
        """Batch-update done flags. Each tuple is (done, transition_id)."""
        BATCH = 5000
        for i in range(0, len(updates), BATCH):
            self.conn.executemany(
                "UPDATE transitions SET done = ? WHERE id = ?",
                updates[i : i + BATCH],
            )
        self.conn.commit()

    def get_game_transitions(self, game_id: int) -> list[sqlite3.Row]:
        """Return all transitions for a game, ordered by step_idx."""
        return self.conn.execute(
            """SELECT id, step_idx, player_id, phase, obs, reward, done
               FROM transitions WHERE game_id = ? ORDER BY step_idx ASC""",
            (game_id,),
        ).fetchall()

    def load_embedding_dataset(self, game_id: int) -> list[dict[str, Any]]:
        """Load embedded transitions for a game.

        Returns list of dicts with keys: state_emb, action_emb, reward,
        done, player_id, transition_id.
        """
        import numpy as np
        import torch

        rows = self.conn.execute(
            """
            SELECT t.id as transition_id, t.player_id, t.reward, t.done,
                   e.state_embedding, e.action_embedding
            FROM transitions t
            JOIN embeddings e ON e.transition_id = t.id
            WHERE t.game_id = ?
            ORDER BY t.id
            """,
            (game_id,),
        ).fetchall()

        # np.frombuffer on raw bytes avoids the bytearray intermediate copy;
        # .copy() is required because the bytes object may be garbage-collected.
        result = []
        for row in rows:
            result.append({
                "transition_id": row["transition_id"],
                "player_id": row["player_id"],
                "reward": row["reward"],
                "done": row["done"],
                "state_emb": torch.from_numpy(
                    np.frombuffer(row["state_embedding"], dtype=np.float32).copy()
                ),
                "action_emb": torch.from_numpy(
                    np.frombuffer(row["action_embedding"], dtype=np.float32).copy()
                ),
            })
        return result

    def load_embeddings_bulk(
        self,
        game_ids: list[int],
    ) -> Optional[dict[str, Any]]:
        """Load all embeddings for multiple games in one SQL query.

        Significantly faster than calling load_embedding_dataset per game:
        - Single round-trip to SQLite
        - Pre-allocated numpy arrays (no Python list growth)
        - np.frombuffer avoids intermediate bytearray copies
        - torch.from_numpy is zero-copy

        Automatically detects whether the DB contains pre-computed embedding blobs
        (state_embedding / action_embedding) or raw packed feature arrays
        (state_features / action_features) and returns accordingly.

        Returns dict with keys:
            states            float32 ndarray (N, state_dim)   — embeddings OR packed features
            actions           float32 ndarray (N, action_dim)  — embeddings OR packed features
            rewards           float32 ndarray (N,)
            dones             float32 ndarray (N,)
            player_ids        int32 ndarray   (N,)
            transition_ids    int64 ndarray   (N,)
            game_id_per_row   int64 ndarray   (N,)
            state_dim         int
            action_dim        int
            uses_raw_features bool  — True when packed feature arrays were returned
        Returns None if no rows found.
        """
        import numpy as np

        if not game_ids:
            return None

        # Load game IDs into a temp table to avoid SQLite's 999-variable IN() limit.
        self.conn.execute("CREATE TEMP TABLE IF NOT EXISTS _bulk_game_ids (game_id INTEGER PRIMARY KEY)")
        self.conn.execute("DELETE FROM _bulk_game_ids")
        self.conn.executemany("INSERT OR IGNORE INTO _bulk_game_ids VALUES (?)", [(g,) for g in game_ids])

        # Detect which columns are populated.
        # Prefer pre-computed embeddings (from re-embedding with a trained transformer)
        # over raw packed features.  Raw features require end-to-end transformer training
        # in the IQL loop, which is very slow on non-CUDA hardware.
        detect_sql = """
            SELECT e.state_features, e.state_embedding
            FROM transitions t
            JOIN embeddings e ON e.transition_id = t.id
            JOIN _bulk_game_ids g ON g.game_id = t.game_id
            LIMIT 1
        """
        probe = None
        try:
            probe = self.conn.execute(detect_sql).fetchone()
        except Exception:
            pass  # DB predates state_features column — fall back to embeddings

        has_embeddings = (
            probe is not None
            and probe["state_embedding"] is not None
            and len(probe["state_embedding"]) > 0
        )
        has_features = (
            probe is not None
            and probe["state_features"] is not None
            and len(probe["state_features"]) > 0
        )
        # Use embeddings when available (fast frozen path), fall back to raw features
        uses_raw_features = has_features and not has_embeddings

        if uses_raw_features:
            sql = """
                SELECT t.game_id, t.id as transition_id, t.player_id, t.reward, t.done,
                       e.state_features, e.action_features
                FROM transitions t
                JOIN embeddings e ON e.transition_id = t.id
                JOIN _bulk_game_ids g ON g.game_id = t.game_id
                WHERE e.state_features IS NOT NULL
                ORDER BY t.game_id, t.id
                """
            state_col  = "state_features"
            action_col = "action_features"
            count_filter = "AND e.state_features IS NOT NULL AND e.action_features IS NOT NULL"
        else:
            sql = """
                SELECT t.game_id, t.id as transition_id, t.player_id, t.reward, t.done,
                       e.state_embedding, e.action_embedding
                FROM transitions t
                JOIN embeddings e ON e.transition_id = t.id
                JOIN _bulk_game_ids g ON g.game_id = t.game_id
                WHERE e.state_embedding IS NOT NULL
                  AND e.action_embedding IS NOT NULL
                ORDER BY t.game_id, t.id
                """
            state_col  = "state_embedding"
            action_col = "action_embedding"
            count_filter = "AND e.state_embedding IS NOT NULL AND e.action_embedding IS NOT NULL"

        # Count rows first so we can pre-allocate without fetchall().
        n = self.conn.execute(
            f"SELECT COUNT(*) FROM transitions t JOIN embeddings e ON e.transition_id = t.id "
            f"JOIN _bulk_game_ids g ON g.game_id = t.game_id {count_filter}"
        ).fetchone()[0]

        if n == 0:
            return None

        # Determine dimensions from first matching row
        first = self.conn.execute(sql).fetchone()
        state_blob  = first[state_col]
        action_blob = first[action_col]
        if state_blob is None or action_blob is None:
            return None
        state_dim  = len(np.frombuffer(state_blob,  dtype=np.float32))
        action_dim = len(np.frombuffer(action_blob, dtype=np.float32))

        # Pre-allocate output arrays
        states = np.empty((n, state_dim), dtype=np.float32)
        actions = np.empty((n, action_dim), dtype=np.float32)
        rewards = np.empty(n, dtype=np.float32)
        dones = np.empty(n, dtype=np.float32)
        player_ids = np.empty(n, dtype=np.int32)
        transition_ids = np.empty(n, dtype=np.int64)
        game_id_per_row = np.empty(n, dtype=np.int64)

        # Stream rows in chunks
        _CHUNK = 2000
        cursor = self.conn.execute(sql)
        i = 0
        while True:
            batch = cursor.fetchmany(_CHUNK)
            if not batch:
                break
            for row in batch:
                states[i] = np.frombuffer(row[state_col], dtype=np.float32)
                actions[i] = np.frombuffer(row[action_col], dtype=np.float32)
                rewards[i] = float(row["reward"])
                dones[i] = float(row["done"])
                player_ids[i] = int(row["player_id"])
                transition_ids[i] = int(row["transition_id"])
                game_id_per_row[i] = int(row["game_id"])
                i += 1
            del batch  # release raw blob memory before next chunk

        return {
            "states": states,
            "actions": actions,
            "rewards": rewards,
            "dones": dones,
            "player_ids": player_ids,
            "transition_ids": transition_ids,
            "game_id_per_row": game_id_per_row,
            "state_dim": state_dim,
            "action_dim": action_dim,
            "uses_raw_features": uses_raw_features,
        }
