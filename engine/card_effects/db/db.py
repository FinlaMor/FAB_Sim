"""
db.py — SQLite database for card effect definitions.

Usage:
    from engine.card_effects.db.db import get_db, init_db
    db = get_db()   # returns initialized connection
"""
from __future__ import annotations

import json
import pathlib
import sqlite3

DB_PATH = pathlib.Path(__file__).parent / "card_effects.db"
SCHEMA_SQL = pathlib.Path(__file__).parent / "schema.sql"
SEED_SQL = pathlib.Path(__file__).parent / "seed_data.sql"

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
    """Create schema and seed data. Idempotent unless force=True."""
    db_exists = DB_PATH.exists() and DB_PATH.stat().st_size > 0
    if db_exists and not force:
        return
    conn = get_db()
    conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
    conn.executescript(SEED_SQL.read_text(encoding="utf-8"))
    conn.commit()


def query_triggers(slug: str) -> list[sqlite3.Row]:
    """Return all trigger rows for a card slug, ordered by intra_card_order."""
    conn = get_db()
    return conn.execute(
        "SELECT * FROM card_triggers WHERE slug = ? ORDER BY intra_card_order",
        (slug,)
    ).fetchall()


def query_all_triggers() -> list[sqlite3.Row]:
    """Return all trigger rows ordered by slug, intra_card_order."""
    conn = get_db()
    return conn.execute(
        "SELECT * FROM card_triggers ORDER BY slug, intra_card_order"
    ).fetchall()


def query_equipment(slug: str) -> sqlite3.Row | None:
    """Return equipment activation row for a slug, or None."""
    conn = get_db()
    return conn.execute(
        "SELECT * FROM equipment_activations WHERE slug = ?", (slug,)
    ).fetchone()


def query_turn_attack_effects() -> list[sqlite3.Row]:
    """Return all turn_attack_effects rows."""
    conn = get_db()
    return conn.execute("SELECT * FROM turn_attack_effects").fetchall()


def query_token_keywords(token_slug: str) -> list[str]:
    """Return all keywords for a token slug."""
    conn = get_db()
    rows = conn.execute(
        "SELECT keyword FROM token_keywords WHERE token_slug = ?", (token_slug,)
    ).fetchall()
    return [r["keyword"] for r in rows]


def query_token_effects(token_slug: str) -> list[sqlite3.Row]:
    """Return all continuous effect rows for a token slug."""
    conn = get_db()
    return conn.execute(
        "SELECT * FROM token_effects WHERE token_slug = ?", (token_slug,)
    ).fetchall()


def query_turn_defend_effects() -> list[sqlite3.Row]:
    """Return all turn_defend_effects rows."""
    conn = get_db()
    return conn.execute("SELECT * FROM turn_defend_effects").fetchall()


def params(row: sqlite3.Row, col: str) -> dict:
    """Parse a JSON params column from a row, returning {} on failure."""
    try:
        return json.loads(row[col] or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
