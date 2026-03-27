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
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
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
                action_embedding BLOB
            )"""
        )
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

    def flush(self) -> None:
        """Commit pending writes."""
        if self._conn is not None:
            self._conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def load_embedding_dataset(self, game_id: int) -> list[dict[str, Any]]:
        """Load embedded transitions for a game.

        Returns list of dicts with keys: state_emb, action_emb, reward,
        done, player_id, transition_id.
        """
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

        result = []
        for row in rows:
            result.append({
                "transition_id": row["transition_id"],
                "player_id": row["player_id"],
                "reward": row["reward"],
                "done": row["done"],
                "state_emb": torch.frombuffer(
                    bytearray(row["state_embedding"]), dtype=torch.float32
                ).clone(),
                "action_emb": torch.frombuffer(
                    bytearray(row["action_embedding"]), dtype=torch.float32
                ).clone(),
            })
        return result
