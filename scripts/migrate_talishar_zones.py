"""scripts/migrate_talishar_zones.py

Incremental migration script that adds zone content, pitch stack, and metadata
columns to an existing talishar_games.db and backfills them from JSON state blobs.

Usage
-----
    python scripts/migrate_talishar_zones.py
    python scripts/migrate_talishar_zones.py --db data/talishar_games.db --dry-run
    python scripts/migrate_talishar_zones.py --batch-size 2000 --limit 10000
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from typing import Any

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import types as _types
if "rl_agents" not in sys.modules:
    _pkg = _types.ModuleType("rl_agents")
    _pkg.__path__ = [os.path.join(_ROOT, "rl_agents")]
    _pkg.__package__ = "rl_agents"
    sys.modules["rl_agents"] = _pkg

from rl_agents.game_data import _extract_zone_slugs  # noqa: E402

# -- New columns to add (name, type, default) --------------------------------

_NEW_COLUMNS: list[tuple[str, str]] = [
    # zone content (JSON arrays of card slugs)
    ("player_hand", "TEXT"),
    ("player_graveyard", "TEXT"),
    ("player_banished", "TEXT"),
    ("player_arsenal", "TEXT"),
    ("player_equipment", "TEXT"),
    ("player_pitch_zone", "TEXT"),
    ("player_soul", "TEXT"),
    ("player_auras", "TEXT"),
    ("player_items", "TEXT"),
    ("player_permanents", "TEXT"),
    ("opp_graveyard", "TEXT"),
    ("opp_banished", "TEXT"),
    ("opp_equipment", "TEXT"),
    ("opp_pitch_zone", "TEXT"),
    ("opp_soul", "TEXT"),
    ("opp_auras", "TEXT"),
    ("opp_items", "TEXT"),
    ("opp_permanents", "TEXT"),
    # pitch stacks
    ("player_pitch_stack", "TEXT"),
    ("opp_pitch_stack", "TEXT"),
    # deck remainder
    ("deck_remainder", "TEXT"),
    # additional metadata
    ("player_hero", "TEXT"),
    ("opp_hero", "TEXT"),
    ("combat_attack_card", "TEXT"),
    ("combat_defending_cards", "TEXT"),
    ("chain_link_history", "TEXT"),
]

# Zone key mapping: column_name -> Talishar state dict key
_ZONE_MAP: dict[str, str] = {
    "player_hand": "playerHand",
    "player_graveyard": "playerDiscard",
    "player_banished": "playerBanish",
    "player_arsenal": "playerArse",
    "player_equipment": "playerEquipment",
    "player_pitch_zone": "playerPitch",
    "player_soul": "playerSoul",
    "player_auras": "playerAuras",
    "player_items": "playerItems",
    "player_permanents": "playerPermanents",
    "opp_graveyard": "opponentDiscard",
    "opp_banished": "opponentBanish",
    "opp_equipment": "opponentEquipment",
    "opp_pitch_zone": "opponentPitch",
    "opp_soul": "opponentSoul",
    "opp_auras": "opponentAuras",
    "opp_items": "opponentItems",
    "opp_permanents": "opponentPermanents",
}


def _get_existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """Return set of column names for *table* using PRAGMA table_info."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def _add_missing_columns(conn: sqlite3.Connection, dry_run: bool) -> int:
    """Add new columns via ALTER TABLE if they don't already exist. Returns count added."""
    existing = _get_existing_columns(conn, "transitions")
    added = 0
    for col_name, col_type in _NEW_COLUMNS:
        if col_name not in existing:
            stmt = f"ALTER TABLE transitions ADD COLUMN {col_name} {col_type}"
            if dry_run:
                print(f"  [dry-run] Would execute: {stmt}")
            else:
                conn.execute(stmt)
            added += 1
    if added and not dry_run:
        conn.commit()
    return added


def _extract_hero_slug(state: dict, key: str) -> str | None:
    """Extract hero card slug from state dict."""
    hero_raw = state.get(key)
    if isinstance(hero_raw, dict):
        return hero_raw.get("cardNumber") or hero_raw.get("cardID") or None
    if isinstance(hero_raw, str) and hero_raw:
        return hero_raw
    return None


def _extract_combat_details(state: dict) -> tuple[str | None, str | None, str | None]:
    """Extract combat_attack_card, combat_defending_cards, chain_link_history."""
    acl = state.get("activeChainLink")
    combat_attack_card: str | None = None
    combat_defending_cards: str | None = None

    if isinstance(acl, dict):
        atk_card = acl.get("attackCard") or acl.get("cardNumber")
        if isinstance(atk_card, dict):
            combat_attack_card = atk_card.get("cardNumber") or atk_card.get("cardID")
        elif isinstance(atk_card, str) and atk_card:
            combat_attack_card = atk_card
        def_cards = acl.get("defendingCards")
        if isinstance(def_cards, list):
            def_slugs = []
            for dc in def_cards:
                if isinstance(dc, dict):
                    s = dc.get("cardNumber") or dc.get("cardID") or ""
                    if s:
                        def_slugs.append(s)
                elif isinstance(dc, str) and dc:
                    def_slugs.append(dc)
            combat_defending_cards = json.dumps(def_slugs, separators=(",", ":"))

    chain_links = state.get("combatChainLinks")
    chain_link_history: str | None = None
    if isinstance(chain_links, list) and chain_links:
        chain_link_history = json.dumps(chain_links, separators=(",", ":"))

    return combat_attack_card, combat_defending_cards, chain_link_history


def _build_pitch_stacks_for_game(
    rows: list[tuple[int, int, int, str]],
) -> dict[int, tuple[str, str, str | None]]:
    """Walk transitions for a single game in step order to reconstruct pitch stacks.

    Parameters
    ----------
    rows : list of (id, player_id, turn_number, state_json) sorted by step ASC

    Returns
    -------
    dict mapping transition id -> (player_pitch_stack, opp_pitch_stack, deck_remainder)
    """
    # Per-player tracking
    player_pitch_stacks: dict[int, list[str]] = {}
    opp_pitch_buckets: dict[int, dict[int, list[str]]] = {}
    last_pitch_zone: dict[int, set[str]] = {}

    result: dict[int, tuple[str, str, str | None]] = {}

    for tid, player_id, turn_number, state_json in rows:
        try:
            state = json.loads(state_json) if state_json else {}
        except (json.JSONDecodeError, TypeError):
            state = {}

        # --- player pitch stack (cumulative, ordered) ---
        current_pitch_slugs: list[str] = []
        pitch_cards = state.get("playerPitch")
        if isinstance(pitch_cards, list):
            for card in pitch_cards:
                if isinstance(card, dict):
                    slug = card.get("cardNumber") or card.get("cardID") or ""
                    if slug:
                        current_pitch_slugs.append(slug)

        if player_id not in player_pitch_stacks:
            player_pitch_stacks[player_id] = []
        if player_id not in last_pitch_zone:
            last_pitch_zone[player_id] = set()

        current_set = set(current_pitch_slugs)
        last_set = last_pitch_zone[player_id]
        if current_set != last_set:
            new_slugs = [s for s in current_pitch_slugs if s not in last_set]
            player_pitch_stacks[player_id].extend(new_slugs)
            last_pitch_zone[player_id] = current_set

        player_pitch_stack = json.dumps(
            player_pitch_stacks[player_id], separators=(",", ":")
        )

        # --- opponent pitch stack (turn-bucketed, alpha-sorted) ---
        opp_pitch_slugs: list[str] = []
        opp_pitch_cards = state.get("opponentPitch")
        if isinstance(opp_pitch_cards, list):
            for card in opp_pitch_cards:
                if isinstance(card, dict):
                    slug = card.get("cardNumber") or card.get("cardID") or ""
                    if slug:
                        opp_pitch_slugs.append(slug)

        if player_id not in opp_pitch_buckets:
            opp_pitch_buckets[player_id] = {}

        if opp_pitch_slugs:
            opp_pitch_buckets[player_id][turn_number] = sorted(opp_pitch_slugs)

        opp_pitch_stack = json.dumps(
            {str(k): v for k, v in sorted(opp_pitch_buckets[player_id].items())},
            separators=(",", ":"),
        )

        # --- deck remainder ---
        deck_remainder: str | None = None
        deck_cards = state.get("playerDeck")
        if isinstance(deck_cards, list):
            deck_slugs = []
            for card in deck_cards:
                if isinstance(card, dict):
                    slug = card.get("cardNumber") or card.get("cardID") or ""
                    if slug:
                        deck_slugs.append(slug)
            remaining = list(deck_slugs)
            for ps in player_pitch_stacks.get(player_id, []):
                if ps in remaining:
                    remaining.remove(ps)
            deck_remainder = json.dumps(sorted(remaining), separators=(",", ":"))

        result[tid] = (player_pitch_stack, opp_pitch_stack, deck_remainder)

    return result


def _process_row(
    state: dict,
) -> dict[str, Any]:
    """Extract all zone/metadata columns from a state dict (except pitch stacks)."""
    values: dict[str, Any] = {}

    # Zone contents
    for col_name, state_key in _ZONE_MAP.items():
        values[col_name] = _extract_zone_slugs(state, state_key)

    # Hero slugs
    values["player_hero"] = _extract_hero_slug(state, "playerHero")
    values["opp_hero"] = _extract_hero_slug(state, "opponentHero")

    # Combat details
    atk, dfc, clh = _extract_combat_details(state)
    values["combat_attack_card"] = atk
    values["combat_defending_cards"] = dfc
    values["chain_link_history"] = clh

    return values


def migrate(
    db_path: str,
    batch_size: int = 5000,
    limit: int | None = None,
    dry_run: bool = False,
) -> None:
    if not os.path.exists(db_path):
        print(f"ERROR: Database not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    # Phase 1: Add missing columns
    print("Phase 1: Adding missing columns...")
    added = _add_missing_columns(conn, dry_run)
    print(f"  Columns added: {added}")

    # Phase 2: Identify rows needing backfill
    # Use player_hand IS NULL as sentinel — if it's populated, row is already migrated
    count_sql = "SELECT COUNT(*) FROM transitions WHERE player_hand IS NULL"
    total_rows = conn.execute(count_sql).fetchone()[0]
    if limit is not None:
        total_rows = min(total_rows, limit)
    print(f"Phase 2: Backfilling {total_rows} rows (batch_size={batch_size})...")

    if total_rows == 0:
        print("  Nothing to migrate.")
        conn.close()
        return

    # Phase 3: Process in batches, grouped by game for pitch stack reconstruction
    processed = 0
    t0 = time.time()

    while processed < total_rows:
        remaining = total_rows - processed
        fetch_limit = min(batch_size, remaining)

        # Fetch a batch of game_ids that have unmigrated rows
        game_ids = [
            row[0] for row in conn.execute(
                """SELECT DISTINCT game_id FROM transitions
                   WHERE player_hand IS NULL
                   LIMIT ?""",
                (fetch_limit,),
            ).fetchall()
        ]

        if not game_ids:
            break

        batch_updates: list[tuple] = []

        for game_id in game_ids:
            # Fetch all transitions for this game (need full game for pitch stack walk)
            rows = conn.execute(
                """SELECT id, player_id, turn_number, state
                   FROM transitions
                   WHERE game_id = ?
                   ORDER BY step ASC""",
                (game_id,),
            ).fetchall()

            # Build pitch stacks by walking the game in order
            pitch_data = _build_pitch_stacks_for_game(
                [(r[0], r[1], r[2], r[3]) for r in rows]
            )

            # Extract zone data for each row
            for row in rows:
                tid = row[0]
                state_json = row[3]
                try:
                    state = json.loads(state_json) if state_json else {}
                except (json.JSONDecodeError, TypeError):
                    state = {}

                vals = _process_row(state)
                ps, ops, dr = pitch_data.get(tid, ("[]", "{}", None))
                vals["player_pitch_stack"] = ps
                vals["opp_pitch_stack"] = ops
                vals["deck_remainder"] = dr

                batch_updates.append((
                    vals["player_hand"],
                    vals["player_graveyard"],
                    vals["player_banished"],
                    vals["player_arsenal"],
                    vals["player_equipment"],
                    vals["player_pitch_zone"],
                    vals["player_soul"],
                    vals["player_auras"],
                    vals["player_items"],
                    vals["player_permanents"],
                    vals["opp_graveyard"],
                    vals["opp_banished"],
                    vals["opp_equipment"],
                    vals["opp_pitch_zone"],
                    vals["opp_soul"],
                    vals["opp_auras"],
                    vals["opp_items"],
                    vals["opp_permanents"],
                    vals["player_pitch_stack"],
                    vals["opp_pitch_stack"],
                    vals["deck_remainder"],
                    vals["player_hero"],
                    vals["opp_hero"],
                    vals["combat_attack_card"],
                    vals["combat_defending_cards"],
                    vals["chain_link_history"],
                    tid,
                ))

            processed += len(rows)
            if processed >= total_rows:
                break

        if batch_updates and not dry_run:
            conn.executemany(
                """UPDATE transitions SET
                    player_hand = ?, player_graveyard = ?, player_banished = ?,
                    player_arsenal = ?, player_equipment = ?, player_pitch_zone = ?,
                    player_soul = ?, player_auras = ?, player_items = ?,
                    player_permanents = ?,
                    opp_graveyard = ?, opp_banished = ?, opp_equipment = ?,
                    opp_pitch_zone = ?, opp_soul = ?, opp_auras = ?,
                    opp_items = ?, opp_permanents = ?,
                    player_pitch_stack = ?, opp_pitch_stack = ?,
                    deck_remainder = ?,
                    player_hero = ?, opp_hero = ?,
                    combat_attack_card = ?, combat_defending_cards = ?,
                    chain_link_history = ?
                WHERE id = ?""",
                batch_updates,
            )
            conn.commit()

        elapsed = time.time() - t0
        rate = processed / elapsed if elapsed > 0 else 0
        print(f"  Processed {processed}/{total_rows} rows ({rate:.0f} rows/sec)")

    if not dry_run:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    conn.close()
    elapsed = time.time() - t0
    prefix = "[dry-run] " if dry_run else ""
    print(f"{prefix}Done. {processed} rows in {elapsed:.1f}s.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate talishar_games.db: add zone content and pitch stack columns"
    )
    parser.add_argument(
        "--db",
        default=os.path.join(_ROOT, "data", "talishar_games.db"),
        help="Path to SQLite database (default: data/talishar_games.db)",
    )
    parser.add_argument(
        "--batch-size", type=int, default=5000,
        help="Number of rows to process per batch (default: 5000)",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Maximum number of rows to migrate (default: all)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report what would change without writing to DB",
    )
    args = parser.parse_args()

    print(f"Database   : {args.db}")
    print(f"Batch size : {args.batch_size}")
    print(f"Limit      : {args.limit or 'all'}")
    print(f"Dry run    : {args.dry_run}")
    print()
    migrate(args.db, batch_size=args.batch_size, limit=args.limit, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
