"""
db.py — SQLite database for card test gamestates.

Usage:
    from data.card_test_gamestates.db import get_db, init_db
    db = get_db()   # returns initialized connection
"""
from __future__ import annotations

import pathlib
import sqlite3

DB_PATH = pathlib.Path(__file__).parent / "card_test_gamestates.db"
SCHEMA_SQL = pathlib.Path(__file__).parent / "schema.sql"

_connection: sqlite3.Connection | None = None


def get_db() -> sqlite3.Connection:
    """Return a singleton DB connection, initializing on first call."""
    global _connection
    if _connection is None:
        _connection = _open_db()
    return _connection


def _open_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(force: bool = False) -> None:
    """Create schema. Idempotent unless force=True."""
    db_exists = DB_PATH.exists() and DB_PATH.stat().st_size > 0
    if db_exists and not force:
        return
    conn = get_db()
    conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
    conn.commit()


def insert_gamestate(
    card_slug: str,
    card_name: str,
    card_types: str = "[]",
    card_category: str = "",
    original_gamestate: str = "{}",
    post_gamestate: str = "{}",
    status: str = "pending",
    error_message: str | None = None,
) -> None:
    """Insert a new card test gamestate row."""
    conn = get_db()
    conn.execute(
        """INSERT OR REPLACE INTO card_test_gamestates
           (card_slug, card_name, card_types, card_category,
            original_gamestate, post_gamestate, status, error_message, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
        (card_slug, card_name, card_types, card_category,
         original_gamestate, post_gamestate, status, error_message),
    )
    conn.commit()


def get_gamestate(slug: str) -> sqlite3.Row | None:
    """Return a single gamestate row by card_slug, or None."""
    conn = get_db()
    return conn.execute(
        "SELECT * FROM card_test_gamestates WHERE card_slug = ?", (slug,)
    ).fetchone()


def get_all_gamestates() -> list[sqlite3.Row]:
    """Return all gamestate rows ordered by card_slug."""
    conn = get_db()
    return conn.execute(
        "SELECT * FROM card_test_gamestates ORDER BY card_slug"
    ).fetchall()


def get_gamestates_by_status(status: str) -> list[sqlite3.Row]:
    """Return all gamestate rows matching the given status."""
    conn = get_db()
    return conn.execute(
        "SELECT * FROM card_test_gamestates WHERE status = ? ORDER BY card_slug",
        (status,),
    ).fetchall()


def update_validation_result(slug: str, result: str) -> None:
    """Update the validation_result and status for a card_slug."""
    conn = get_db()
    conn.execute(
        """UPDATE card_test_gamestates
           SET validation_result = ?, status = 'validated', updated_at = datetime('now')
           WHERE card_slug = ?""",
        (result, slug),
    )
    conn.commit()


def get_status_counts() -> dict[str, int]:
    """Return a dict mapping each status to its count."""
    conn = get_db()
    rows = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM card_test_gamestates GROUP BY status"
    ).fetchall()
    return {r["status"]: r["cnt"] for r in rows}
