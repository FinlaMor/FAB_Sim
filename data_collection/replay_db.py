"""Minimal stub for data_collection.replay_db.

The real module lives outside version control (gitignored). This stub
provides the ReplayDB interface so that dependent modules can be imported
and tested without the full data collection infrastructure.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Optional


class ReplayDB:
    """Lightweight wrapper around the replay SQLite database."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

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

    def record_game(self, **kwargs: Any) -> int:
        """Record a game result. Returns game_id."""
        raise NotImplementedError("Stub: use full data_collection package for recording")

    def record_transition(self, **kwargs: Any) -> int:
        """Record a transition. Returns transition_id."""
        raise NotImplementedError("Stub: use full data_collection package for recording")
