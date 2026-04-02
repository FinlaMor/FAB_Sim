"""Archive old games from replay.db and game_data.db to save disk space.

Strategy:
    replay.db:
        1. DELETE embeddings for archived games (embeddings are ephemeral —
           the transformer re-creates them each loop via re-embedding).
        2. COPY games + transitions (metadata only) to replay_archive.db.
        3. DELETE the archived games + transitions from the live DB.
        4. VACUUM the live DB to reclaim space.

    game_data.db:
        1. COPY transitions for archived games to game_data_archive.db.
           (The decks table stays — the deck evaluator uses ALL game outcomes.)
        2. DELETE archived transitions from the live DB.
        3. VACUUM the live DB to reclaim space.
        Note: card_performance is a small aggregate table and stays untouched.

Usage:
    # Preview what would be archived (no changes)
    python scripts/archive_old_games.py --dry-run

    # Archive all but the 5000 most recent games
    python scripts/archive_old_games.py --keep-recent 5000

    # Archive all but the 4000 most recent (matches pipeline default)
    python scripts/archive_old_games.py
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPLAY_DB = ROOT / "data" / "replay.db"
REPLAY_ARCHIVE = ROOT / "data" / "replay_archive.db"
GAME_DATA_DB = ROOT / "data" / "game_data.db"
GAME_DATA_ARCHIVE = ROOT / "data" / "game_data_archive.db"


def _file_size_mb(path: Path) -> float:
    return path.stat().st_size / (1024 * 1024) if path.exists() else 0.0


def _count(conn: sqlite3.Connection, table: str, where: str = "") -> int:
    sql = f"SELECT COUNT(*) FROM {table}"
    if where:
        sql += f" WHERE {where}"
    return conn.execute(sql).fetchone()[0]


def _get_archive_game_ids(conn: sqlite3.Connection, keep_recent: int) -> list[int]:
    """Return game_ids to archive.

    Keeps the N most recent games **that have a winner** (usable for
    training).  Everything else is archived — including games with no
    winner, which are useless for training anyway.
    """
    # IDs we want to KEEP: the N most recent completed games
    keep_rows = conn.execute(
        "SELECT game_id FROM games WHERE winner IS NOT NULL "
        "ORDER BY game_id DESC LIMIT ?",
        (keep_recent,),
    ).fetchall()
    keep_ids = {r[0] for r in keep_rows}

    # Everything else gets archived
    all_rows = conn.execute("SELECT game_id FROM games").fetchall()
    archive_ids = [r[0] for r in all_rows if r[0] not in keep_ids]
    return sorted(archive_ids)


def _create_replay_archive_schema(conn: sqlite3.Connection) -> None:
    """Create the replay archive DB schema (matches replay_db.py)."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS games (
            game_id INTEGER PRIMARY KEY,
            p1_hero TEXT,
            p2_hero TEXT,
            winner INTEGER,
            turns INTEGER,
            ended_on_turn_cap INTEGER,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS transitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER,
            step_idx INTEGER,
            player_id INTEGER,
            phase TEXT,
            obs TEXT,
            action TEXT,
            reward REAL DEFAULT 0.0,
            done INTEGER DEFAULT 0
        );
    """)


def _create_game_data_archive_schema(src_conn: sqlite3.Connection, dst_conn: sqlite3.Connection) -> None:
    """Create game_data archive DB schema for the transitions table.

    Reads the column list from the source DB so we don't need to hardcode
    the wide schema (50+ columns).
    """
    cols = src_conn.execute("PRAGMA table_info(transitions)").fetchall()
    if not cols:
        raise ValueError("Source game_data.db has no transitions table")

    col_defs = []
    for col in cols:
        # col: (cid, name, type, notnull, default, pk)
        name, ctype, notnull, default, pk = col[1], col[2], col[3], col[4], col[5]
        parts = [name, ctype or "TEXT"]
        if pk:
            parts.append("PRIMARY KEY")
            if name == "id":
                parts.append("AUTOINCREMENT")
        if notnull and not pk:
            parts.append("NOT NULL")
        if default is not None and not pk:
            parts.append(f"DEFAULT {default}")
        col_defs.append(" ".join(parts))

    ddl = f"CREATE TABLE IF NOT EXISTS transitions ({', '.join(col_defs)})"
    dst_conn.execute(ddl)
    dst_conn.commit()


def _load_ids_to_temp(conn: sqlite3.Connection, game_ids: list[int]) -> None:
    """Load game IDs into a temp table (avoids SQLite's 999-var IN() limit)."""
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS _archive_ids (game_id INTEGER PRIMARY KEY)")
    conn.execute("DELETE FROM _archive_ids")
    conn.executemany("INSERT OR IGNORE INTO _archive_ids VALUES (?)", [(g,) for g in game_ids])


def archive_replay_db(game_ids: list[int], dry_run: bool = False) -> dict:
    """Archive old data from replay.db.

    Returns stats dict with counts and sizes.
    """
    if not REPLAY_DB.exists():
        print("  replay.db not found — skipping")
        return {}

    src = sqlite3.connect(str(REPLAY_DB), timeout=60)
    src.execute("PRAGMA journal_mode=WAL")

    _load_ids_to_temp(src, game_ids)

    # Count what we'll archive
    n_games = src.execute(
        "SELECT COUNT(*) FROM games g JOIN _archive_ids a ON g.game_id = a.game_id"
    ).fetchone()[0]
    n_transitions = src.execute(
        "SELECT COUNT(*) FROM transitions t JOIN _archive_ids a ON t.game_id = a.game_id"
    ).fetchone()[0]
    n_embeddings = src.execute(
        "SELECT COUNT(*) FROM embeddings e "
        "JOIN transitions t ON e.transition_id = t.id "
        "JOIN _archive_ids a ON t.game_id = a.game_id"
    ).fetchone()[0]

    size_before = _file_size_mb(REPLAY_DB)

    stats = {
        "games": n_games,
        "transitions": n_transitions,
        "embeddings_to_delete": n_embeddings,
        "size_before_mb": size_before,
    }

    print(f"  replay.db: {n_games:,} games, {n_transitions:,} transitions to archive")
    print(f"  replay.db: {n_embeddings:,} embeddings to DELETE (not archived)")
    print(f"  replay.db size before: {size_before:,.0f} MB")

    if dry_run:
        src.close()
        return stats

    # Open/create archive
    dst = sqlite3.connect(str(REPLAY_ARCHIVE), timeout=60)
    dst.execute("PRAGMA journal_mode=WAL")
    dst.execute("PRAGMA synchronous=NORMAL")
    _create_replay_archive_schema(dst)

    # Copy games
    print("  Copying games to archive...", end="", flush=True)
    rows = src.execute(
        "SELECT * FROM games g JOIN _archive_ids a ON g.game_id = a.game_id"
    ).fetchall()
    game_cols = [d[0] for d in src.execute("SELECT * FROM games LIMIT 0").description]
    placeholders = ", ".join(["?"] * len(game_cols))
    for row in rows:
        dst.execute(
            f"INSERT OR IGNORE INTO games ({', '.join(game_cols)}) VALUES ({placeholders})",
            row[:len(game_cols)],
        )
    dst.commit()
    print(f" {len(rows):,} rows")

    # Copy transitions in chunks
    print("  Copying transitions to archive...", end="", flush=True)
    trans_cols = [d[0] for d in src.execute("SELECT * FROM transitions LIMIT 0").description]
    t_placeholders = ", ".join(["?"] * len(trans_cols))
    cursor = src.execute(
        "SELECT t.* FROM transitions t JOIN _archive_ids a ON t.game_id = a.game_id "
        "ORDER BY t.id"
    )
    copied = 0
    while True:
        batch = cursor.fetchmany(5000)
        if not batch:
            break
        dst.executemany(
            f"INSERT OR IGNORE INTO transitions ({', '.join(trans_cols)}) VALUES ({t_placeholders})",
            batch,
        )
        copied += len(batch)
        if copied % 100_000 == 0:
            print(f"\r  Copying transitions to archive... {copied:,}", end="", flush=True)
    dst.commit()
    print(f"\r  Copying transitions to archive... {copied:,} rows")

    dst.close()

    # Delete embeddings first (biggest space saver)
    print("  Deleting archived embeddings...", end="", flush=True)
    _load_ids_to_temp(src, game_ids)  # re-load since dst operations don't share temp tables
    src.execute(
        "DELETE FROM embeddings WHERE transition_id IN "
        "(SELECT t.id FROM transitions t JOIN _archive_ids a ON t.game_id = a.game_id)"
    )
    src.commit()
    print(" done")

    # Delete archived transitions
    print("  Deleting archived transitions...", end="", flush=True)
    src.execute(
        "DELETE FROM transitions WHERE game_id IN (SELECT game_id FROM _archive_ids)"
    )
    src.commit()
    print(" done")

    # Delete archived games
    print("  Deleting archived games...", end="", flush=True)
    src.execute(
        "DELETE FROM games WHERE game_id IN (SELECT game_id FROM _archive_ids)"
    )
    src.commit()
    print(" done")

    src.close()

    # VACUUM to reclaim space
    print("  VACUUMing replay.db (this may take a while)...", end="", flush=True)
    t0 = time.time()
    vc = sqlite3.connect(str(REPLAY_DB), timeout=300)
    vc.execute("VACUUM")
    vc.close()
    elapsed = time.time() - t0
    print(f" done ({elapsed:.0f}s)")

    size_after = _file_size_mb(REPLAY_DB)
    archive_size = _file_size_mb(REPLAY_ARCHIVE)
    stats["size_after_mb"] = size_after
    stats["archive_size_mb"] = archive_size
    stats["space_saved_mb"] = size_before - size_after

    print(f"  replay.db size after: {size_after:,.0f} MB")
    print(f"  replay_archive.db size: {archive_size:,.0f} MB")
    print(f"  Space saved: {size_before - size_after:,.0f} MB")

    return stats


def archive_game_data_db(game_ids: list[int], dry_run: bool = False) -> dict:
    """Archive old transitions from game_data.db.

    Keeps all `decks` rows (deck evaluator uses full history).
    Keeps `card_performance` (small aggregate table).
    Only archives + deletes `transitions`.
    """
    if not GAME_DATA_DB.exists():
        print("  game_data.db not found — skipping")
        return {}

    src = sqlite3.connect(str(GAME_DATA_DB), timeout=60)
    src.execute("PRAGMA journal_mode=WAL")

    # game_data uses text game_ids, and its transitions.game_id references decks.game_id.
    # We need to map our integer replay game_ids to the text IDs in game_data.
    # Actually — game_data game_ids are independent from replay_db game_ids.
    # We need to find old game_ids by matching the same keep-recent logic on the decks table.
    has_transitions = src.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='transitions'"
    ).fetchone()[0]
    if not has_transitions:
        print("  game_data.db has no transitions table — skipping")
        src.close()
        return {}

    total_decks = _count(src, "decks")
    total_transitions = _count(src, "transitions")

    # Find game_ids to archive from decks table (oldest by rowid)
    # game_data uses TEXT game_ids so we can't reuse replay game_ids
    keep_recent = len(game_ids)  # placeholder — we'll recalculate below
    # Actually, we should archive the same proportion. Let's use the decks table directly.
    # The caller passes replay game_ids, but game_data is a separate DB.
    # We need a separate keep-recent count. Let's derive it from the keep_recent arg.

    src.close()
    print(f"  game_data.db: {total_decks:,} games, {total_transitions:,} transitions")
    print("  (game_data archival uses its own game ID space — see below)")

    return {"total_decks": total_decks, "total_transitions": total_transitions}


def archive_game_data_transitions(keep_recent: int, dry_run: bool = False) -> dict:
    """Archive old transitions from game_data.db by keeping N most recent games.

    Keeps ALL decks rows and card_performance.
    """
    if not GAME_DATA_DB.exists():
        print("  game_data.db not found — skipping")
        return {}

    src = sqlite3.connect(str(GAME_DATA_DB), timeout=60)
    src.execute("PRAGMA journal_mode=WAL")

    has_transitions = src.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='transitions'"
    ).fetchone()[0]
    if not has_transitions:
        print("  game_data.db has no transitions table — skipping")
        src.close()
        return {}

    # Keep the N most recent games WITH a winner (usable for training).
    # Archive transitions for everything else.
    keep_rows = src.execute(
        "SELECT game_id FROM decks WHERE winner IS NOT NULL AND winner IN (1, 2) "
        "ORDER BY rowid DESC LIMIT ?",
        (keep_recent,),
    ).fetchall()
    keep_ids = {r[0] for r in keep_rows}

    all_game_ids = [r[0] for r in src.execute("SELECT game_id FROM decks").fetchall()]
    archive_ids = [gid for gid in all_game_ids if gid not in keep_ids]

    if not archive_ids:
        print(f"  game_data.db: only {len(all_game_ids)} games, nothing to archive")
        src.close()
        return {}
    print(f"  game_data.db: {len(archive_ids):,} games to archive transitions for "
          f"(keeping {keep_recent} most recent)")

    # Load archive IDs into temp table
    src.execute("CREATE TEMP TABLE IF NOT EXISTS _gd_archive_ids (game_id TEXT PRIMARY KEY)")
    src.execute("DELETE FROM _gd_archive_ids")
    src.executemany("INSERT OR IGNORE INTO _gd_archive_ids VALUES (?)", [(g,) for g in archive_ids])

    n_transitions = src.execute(
        "SELECT COUNT(*) FROM transitions t "
        "JOIN _gd_archive_ids a ON t.game_id = a.game_id"
    ).fetchone()[0]

    size_before = _file_size_mb(GAME_DATA_DB)

    stats = {
        "games_archived": len(archive_ids),
        "transitions": n_transitions,
        "size_before_mb": size_before,
    }

    print(f"  game_data.db: {n_transitions:,} transitions to archive")
    print(f"  game_data.db: decks table KEPT (all {len(all_game_ids):,} rows)")
    print(f"  game_data.db size before: {size_before:,.0f} MB")

    if dry_run:
        src.close()
        return stats

    # Open/create archive
    dst = sqlite3.connect(str(GAME_DATA_ARCHIVE), timeout=60)
    dst.execute("PRAGMA journal_mode=WAL")
    dst.execute("PRAGMA synchronous=NORMAL")
    _create_game_data_archive_schema(src, dst)

    # Copy transitions in chunks
    print("  Copying game_data transitions to archive...", end="", flush=True)
    trans_cols = [r[1] for r in src.execute("PRAGMA table_info(transitions)")]
    t_placeholders = ", ".join(["?"] * len(trans_cols))
    col_list = ", ".join(trans_cols)

    cursor = src.execute(
        f"SELECT t.* FROM transitions t "
        f"JOIN _gd_archive_ids a ON t.game_id = a.game_id ORDER BY t.id"
    )
    copied = 0
    while True:
        batch = cursor.fetchmany(5000)
        if not batch:
            break
        dst.executemany(
            f"INSERT OR IGNORE INTO transitions ({col_list}) VALUES ({t_placeholders})",
            batch,
        )
        copied += len(batch)
        if copied % 100_000 == 0:
            print(f"\r  Copying game_data transitions to archive... {copied:,}", end="", flush=True)
    dst.commit()
    print(f"\r  Copying game_data transitions to archive... {copied:,} rows")

    dst.close()

    # Delete archived transitions
    print("  Deleting archived game_data transitions...", end="", flush=True)
    src.execute("DELETE FROM _gd_archive_ids")
    src.executemany("INSERT OR IGNORE INTO _gd_archive_ids VALUES (?)", [(g,) for g in archive_ids])
    src.execute(
        "DELETE FROM transitions WHERE game_id IN (SELECT game_id FROM _gd_archive_ids)"
    )
    src.commit()
    print(" done")

    src.close()

    # VACUUM
    print("  VACUUMing game_data.db...", end="", flush=True)
    t0 = time.time()
    vc = sqlite3.connect(str(GAME_DATA_DB), timeout=300)
    vc.execute("VACUUM")
    vc.close()
    elapsed = time.time() - t0
    print(f" done ({elapsed:.0f}s)")

    size_after = _file_size_mb(GAME_DATA_DB)
    archive_size = _file_size_mb(GAME_DATA_ARCHIVE)
    stats["size_after_mb"] = size_after
    stats["archive_size_mb"] = archive_size
    stats["space_saved_mb"] = size_before - size_after

    print(f"  game_data.db size after: {size_after:,.0f} MB")
    print(f"  game_data_archive.db size: {archive_size:,.0f} MB")
    print(f"  Space saved: {size_before - size_after:,.0f} MB")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Archive old games to free disk space",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--keep-recent", type=int, default=4000,
        help="Keep this many most-recent games in the live DB (default: 4000, "
             "matches pipeline's --iql-replay-buffer-games)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview what would be archived without making changes",
    )
    parser.add_argument(
        "--skip-replay", action="store_true",
        help="Skip replay.db archival",
    )
    parser.add_argument(
        "--skip-game-data", action="store_true",
        help="Skip game_data.db archival",
    )
    args = parser.parse_args()

    print()
    print("=" * 60)
    print("  Game Data Archival")
    print("=" * 60)
    print(f"  Keep recent: {args.keep_recent} games")
    print(f"  Mode: {'DRY RUN (no changes)' if args.dry_run else 'LIVE'}")
    print()

    total_saved = 0.0

    # --- replay.db ---
    if not args.skip_replay and REPLAY_DB.exists():
        print("--- replay.db ---")
        conn = sqlite3.connect(str(REPLAY_DB), timeout=60)
        archive_ids = _get_archive_game_ids(conn, args.keep_recent)
        remaining = _count(conn, "games") - len(archive_ids)
        conn.close()

        if not archive_ids:
            print(f"  Nothing to archive (only {remaining} games total)")
        else:
            print(f"  Will archive {len(archive_ids):,} games, keep {remaining:,} "
                  f"(most recent with a winner)")
            stats = archive_replay_db(archive_ids, dry_run=args.dry_run)
            total_saved += stats.get("space_saved_mb", 0)
        print()

    # --- game_data.db ---
    if not args.skip_game_data and GAME_DATA_DB.exists():
        print("--- game_data.db ---")
        stats = archive_game_data_transitions(args.keep_recent, dry_run=args.dry_run)
        total_saved += stats.get("space_saved_mb", 0)
        print()

    if not args.dry_run and total_saved > 0:
        print(f"  Total space saved: {total_saved:,.0f} MB ({total_saved / 1024:.1f} GB)")
    elif args.dry_run:
        print("  (Dry run — no changes made. Remove --dry-run to execute.)")

    print()


if __name__ == "__main__":
    main()
