"""scripts/compute_card_usage.py

Compute per-(hero, card) usage statistics from talishar_games.db transitions.

Produces a card_usage_stats table with 6 features per (hero, card) pair:
  - play_rate:           fraction of games where card was played from hand
  - block_rate:          fraction of games where card was used to block
  - pitch_rate:          fraction of games where card was pitched
  - arsenal_rate:        fraction of games where card was put in arsenal
  - avg_turn_played:     average turn number when played (0 if never played)
  - win_rate_when_played: win rate in games where the card was played

Includes Bayesian smoothing: for (hero, card) pairs with fewer than
--min-obs observations, blends hero-specific rates with global card averages.

Output is written to --output-db (default: data/card_usage_stats.db).

Usage:
    python scripts/compute_card_usage.py --games-db data/talishar_games.db
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path


def compute_card_usage(
    games_db: str,
    output_db: str,
    min_obs: int = 20,
) -> int:
    """Compute card usage stats and write to output DB.

    Returns the number of (hero, card) rows written.
    """
    conn = sqlite3.connect(games_db)
    conn.execute("PRAGMA journal_mode=WAL")

    print(f"[usage] Loading transitions from {games_db} ...")
    t0 = time.time()

    # Step 1: Build a mapping of game_id -> {player_id -> (hero, won)}
    # from the decks table
    print(f"[usage] Loading game outcomes ...", flush=True)
    game_info: dict[str, dict[int, tuple[str, bool]]] = {}
    rows = conn.execute(
        "SELECT game_id, p1_hero, p2_hero, winner FROM decks WHERE winner IS NOT NULL"
    ).fetchall()
    for game_id, p1_hero, p2_hero, winner in rows:
        game_info[game_id] = {
            1: (p1_hero, winner == 1),
            2: (p2_hero, winner == 2),
        }
    print(f"[usage] {len(game_info)} games with outcomes", flush=True)

    # Step 2: Build a mapping of (game_id, player_id) -> set of card slugs in deck
    # by parsing p1_decklist / p2_decklist JSON
    import json
    print(f"[usage] Loading decklists ...", flush=True)
    deck_cards: dict[tuple[str, int], set[str]] = {}
    rows = conn.execute(
        "SELECT game_id, p1_decklist, p2_decklist FROM decks WHERE winner IS NOT NULL"
    ).fetchall()
    for game_id, p1_json, p2_json in rows:
        for pid, deck_json in [(1, p1_json), (2, p2_json)]:
            try:
                deck = json.loads(deck_json)
                slugs: set[str] = set()
                for key in ("deck", "head", "chest", "arms", "legs", "weapons", "offhand"):
                    val = deck.get(key)
                    if isinstance(val, list):
                        slugs.update(val)
                    elif isinstance(val, str) and val and val != "-":
                        slugs.add(val)
                deck_cards[(game_id, pid)] = slugs
            except (json.JSONDecodeError, TypeError):
                pass

    # Step 3: Aggregate per-(hero, card) stats from transitions
    # We need:
    #   - For each (hero, card): how many games had this card in the deck
    #   - Of those: how many times was it played/blocked/pitched/arsenaled
    #   - Average turn when played
    #   - Win rate when played
    print(f"[usage] Querying transitions (this may take a minute) ...", flush=True)

    # Accumulator: (hero, card) -> {games_in_deck, games_played, games_blocked,
    #   games_pitched, games_arsenaled, total_play_turns, play_turn_count,
    #   wins_when_played, games_played_in}
    from collections import defaultdict

    stats: dict[tuple[str, str], dict] = defaultdict(lambda: {
        "games_in_deck": 0,
        "games_played": set(),      # game_ids where played
        "games_blocked": set(),     # game_ids where blocked
        "games_pitched": set(),     # game_ids where pitched
        "games_arsenaled": set(),   # game_ids where arsenaled
        "play_turns": [],           # turn numbers when played
        "wins_when_played": 0,
    })

    # First: count games where each card appears in each hero's deck
    for (game_id, pid), slugs in deck_cards.items():
        if game_id not in game_info:
            continue
        hero, won = game_info[game_id][pid]
        for slug in slugs:
            stats[(hero, slug)]["games_in_deck"] += 1

    # Second: scan transitions for card usage
    # Process in chunks to avoid loading all 2.5M rows at once
    CHUNK = 100000
    cursor = conn.execute(
        "SELECT game_id, player_id, card_id, decision_type, turn_number "
        "FROM transitions "
        "WHERE decision_type IN ('play_card', 'defend_block', 'pitch', 'arsenal') "
        "AND card_id IS NOT NULL AND card_id != ''"
    )

    n_rows = 0
    while True:
        batch = cursor.fetchmany(CHUNK)
        if not batch:
            break
        for game_id, pid, card_id, decision_type, turn_number in batch:
            if game_id not in game_info or pid not in game_info[game_id]:
                continue
            hero, won = game_info[game_id][pid]
            key = (hero, card_id)
            entry = stats[key]

            if decision_type == "play_card":
                entry["games_played"].add(game_id)
                entry["play_turns"].append(turn_number or 0)
                if won:
                    entry["wins_when_played"] += 1
            elif decision_type == "defend_block":
                entry["games_blocked"].add(game_id)
            elif decision_type == "pitch":
                entry["games_pitched"].add(game_id)
            elif decision_type == "arsenal":
                entry["games_arsenaled"].add(game_id)

        n_rows += len(batch)
        print(f"  ... processed {n_rows:,} transition rows", flush=True)

    conn.close()
    print(f"[usage] Processed {n_rows:,} relevant transitions in {time.time() - t0:.1f}s", flush=True)

    # Step 4: Compute global averages for Bayesian smoothing
    global_stats: dict[str, dict] = defaultdict(lambda: {
        "total_in_deck": 0,
        "total_played": 0,
        "total_blocked": 0,
        "total_pitched": 0,
        "total_arsenaled": 0,
        "total_play_turns": [],
        "total_wins_played": 0,
        "total_games_played": 0,
    })

    for (hero, card), entry in stats.items():
        g = global_stats[card]
        g["total_in_deck"] += entry["games_in_deck"]
        g["total_played"] += len(entry["games_played"])
        g["total_blocked"] += len(entry["games_blocked"])
        g["total_pitched"] += len(entry["games_pitched"])
        g["total_arsenaled"] += len(entry["games_arsenaled"])
        g["total_play_turns"].extend(entry["play_turns"])
        g["total_wins_played"] += entry["wins_when_played"]
        g["total_games_played"] += len(entry["games_played"])

    # Step 5: Write to output DB with smoothing
    print(f"[usage] Writing to {output_db} ...", flush=True)
    out = sqlite3.connect(output_db)
    out.execute("DROP TABLE IF EXISTS card_usage_stats")
    out.execute("""
        CREATE TABLE card_usage_stats (
            hero_slug       TEXT NOT NULL,
            card_slug       TEXT NOT NULL,
            games_in_deck   INTEGER NOT NULL,
            play_rate       REAL NOT NULL,
            block_rate      REAL NOT NULL,
            pitch_rate      REAL NOT NULL,
            arsenal_rate    REAL NOT NULL,
            avg_turn_played REAL NOT NULL,
            win_rate_when_played REAL NOT NULL,
            smoothed        INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (hero_slug, card_slug)
        )
    """)

    n_written = 0
    n_smoothed = 0
    for (hero, card), entry in stats.items():
        n_deck = entry["games_in_deck"]
        if n_deck == 0:
            continue

        n_played = len(entry["games_played"])
        n_blocked = len(entry["games_blocked"])
        n_pitched = len(entry["games_pitched"])
        n_arsenaled = len(entry["games_arsenaled"])

        # Raw rates
        play_rate = n_played / n_deck
        block_rate = n_blocked / n_deck
        pitch_rate = n_pitched / n_deck
        arsenal_rate = n_arsenaled / n_deck
        avg_turn = sum(entry["play_turns"]) / len(entry["play_turns"]) if entry["play_turns"] else 0.0
        wr_played = entry["wins_when_played"] / n_played if n_played > 0 else 0.5

        # Bayesian smoothing for low-count pairs
        smoothed = 0
        if n_deck < min_obs:
            g = global_stats.get(card)
            if g and g["total_in_deck"] > 0:
                # Blend: alpha * hero_specific + (1-alpha) * global
                alpha = n_deck / min_obs  # 0 to 1
                g_deck = g["total_in_deck"]
                g_play = g["total_played"] / g_deck
                g_block = g["total_blocked"] / g_deck
                g_pitch = g["total_pitched"] / g_deck
                g_arsenal = g["total_arsenaled"] / g_deck
                g_avg_turn = (sum(g["total_play_turns"]) / len(g["total_play_turns"])
                              if g["total_play_turns"] else 0.0)
                g_wr = (g["total_wins_played"] / g["total_games_played"]
                        if g["total_games_played"] > 0 else 0.5)

                play_rate = alpha * play_rate + (1 - alpha) * g_play
                block_rate = alpha * block_rate + (1 - alpha) * g_block
                pitch_rate = alpha * pitch_rate + (1 - alpha) * g_pitch
                arsenal_rate = alpha * arsenal_rate + (1 - alpha) * g_arsenal
                avg_turn = alpha * avg_turn + (1 - alpha) * g_avg_turn
                wr_played = alpha * wr_played + (1 - alpha) * g_wr
                smoothed = 1
                n_smoothed += 1

        out.execute(
            "INSERT INTO card_usage_stats VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (hero, card, n_deck, play_rate, block_rate, pitch_rate,
             arsenal_rate, avg_turn, wr_played, smoothed),
        )
        n_written += 1

    out.commit()

    # Summary stats
    out.execute("SELECT COUNT(DISTINCT hero_slug) FROM card_usage_stats")
    n_heroes = out.fetchone()[0]
    out.execute("SELECT COUNT(DISTINCT card_slug) FROM card_usage_stats")
    n_cards = out.fetchone()[0]
    out.close()

    print(f"[usage] Written {n_written:,} (hero, card) rows ({n_smoothed:,} smoothed)")
    print(f"[usage] {n_heroes} heroes, {n_cards} unique cards")
    print(f"[usage] Total time: {time.time() - t0:.1f}s")
    return n_written


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute per-(hero, card) usage stats")
    parser.add_argument("--games-db", default="data/talishar_games.db",
                        help="Path to talishar_games.db (default: data/talishar_games.db)")
    parser.add_argument("--output-db", default="data/card_usage_stats.db",
                        help="Output database path (default: data/card_usage_stats.db)")
    parser.add_argument("--min-obs", type=int, default=20,
                        help="Minimum observations before full trust (Bayesian smoothing threshold, default: 20)")
    args = parser.parse_args()

    if not Path(args.games_db).exists():
        print(f"ERROR: {args.games_db} not found", file=sys.stderr)
        return 1

    Path(args.output_db).parent.mkdir(parents=True, exist_ok=True)
    n = compute_card_usage(args.games_db, args.output_db, args.min_obs)
    return 0 if n > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
