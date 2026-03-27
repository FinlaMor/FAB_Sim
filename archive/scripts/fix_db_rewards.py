"""scripts/fix_db_rewards.py

Retroactively fixes terminal reward signals in an existing talishar_games.db.

Changes applied
---------------
1. Turn-cap terminal rewards: recomputed using per-player HP fraction
   ``(own_hp / own_start_hp) - (opp_hp / opp_start_hp)`` with overkill clamped
   to 0, instead of the old ``(own_hp - opp_hp) / max_start_hp`` formula.

2. Shaped-reward removal from turn-cap games: intermediate transitions that
   were given ``shaped_alpha * damage_dealt`` bonuses in turn-cap games had
   those rewards zeroed (non-terminal reward should be 0.0 for turn-cap games).

RTG is applied at load time in dataset_adapter, not stored, so no DB change
is needed for fix #3 (RTG per-segment).

Usage
-----
    python scripts/fix_db_rewards.py
    python scripts/fix_db_rewards.py --db data/talishar_games.db --max-start-hp 40 --dry-run
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from typing import Any

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import types as _types
if "rl_agents" not in sys.modules:
    _pkg = _types.ModuleType("rl_agents")
    _pkg.__path__ = [os.path.join(_ROOT, "rl_agents")]
    _pkg.__package__ = "rl_agents"
    sys.modules["rl_agents"] = _pkg

from rl_agents.game_data import _terminal_reward  # noqa: E402


def fix_rewards(
    db_path: str,
    max_start_hp: int = 40,
    dry_run: bool = False,
) -> None:
    conn = sqlite3.connect(db_path, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    # Phase 1: turn-cap games with a declared winner — recompute terminal rewards
    # and zero shaped intermediates.
    games_with_winner = conn.execute(
        """SELECT game_id, winner, p1_final_hp, p2_final_hp
           FROM decks
           WHERE ended_on_turn_cap = 1 AND winner IS NOT NULL"""
    ).fetchall()

    # Phase 2: turn-cap games with no winner (draws / aborted) — zero all rewards.
    draw_game_ids = [
        row[0] for row in conn.execute(
            "SELECT game_id FROM decks WHERE ended_on_turn_cap = 1 AND winner IS NULL"
        )
    ]

    print(f"Turn-cap games with winner  : {len(games_with_winner)}")
    print(f"Turn-cap games without winner (draws): {len(draw_game_ids)}")

    terminal_updates: list[tuple[float, int]] = []   # (new_reward, transition_id)
    shaped_zeros: list[int] = []                      # transition_ids to set reward=0.0

    for row in games_with_winner:
        game_id = row["game_id"]
        winner = row["winner"]
        p1_hp = row["p1_final_hp"]
        p2_hp = row["p2_final_hp"]

        transitions = conn.execute(
            "SELECT id, player_id, done, reward FROM transitions WHERE game_id = ? ORDER BY step ASC",
            (game_id,),
        ).fetchall()

        if not transitions:
            continue

        last_done_by_player: dict[int, int] = {}
        for t in transitions:
            if t["done"]:
                last_done_by_player[t["player_id"]] = t["id"]

        terminal_ids = set(last_done_by_player.values())

        for pid, tid in last_done_by_player.items():
            new_r = _terminal_reward(
                player_id=pid,
                winner=winner,
                ended_on_turn_cap=True,
                p1_final_hp=p1_hp,
                p2_final_hp=p2_hp,
                max_start_hp=max_start_hp,
                p1_start_hp=0,
                p2_start_hp=0,
            )
            terminal_updates.append((new_r, tid))

        for t in transitions:
            if t["id"] not in terminal_ids and t["reward"] != 0.0:
                shaped_zeros.append(t["id"])

    # Phase 2: zero every reward in draw/aborted cap games
    draw_zeros: list[int] = []
    BATCH = 5000
    for i in range(0, len(draw_game_ids), BATCH):
        chunk = draw_game_ids[i : i + BATCH]
        placeholders = ",".join("?" * len(chunk))
        rows = conn.execute(
            f"SELECT id FROM transitions WHERE game_id IN ({placeholders}) AND reward != 0.0",
            chunk,
        ).fetchall()
        draw_zeros.extend(r[0] for r in rows)

    print(f"  Terminal transitions to update     : {len(terminal_updates)}")
    print(f"  Shaped intermediates to zero (cap) : {len(shaped_zeros)}")
    print(f"  Draw-game rewards to zero          : {len(draw_zeros)}")

    if dry_run:
        print("Dry run — no changes written.")
        conn.close()
        return

    # Apply updates in batches
    for i in range(0, len(terminal_updates), BATCH):
        conn.executemany(
            "UPDATE transitions SET reward = ? WHERE id = ?",
            terminal_updates[i : i + BATCH],
        )

    all_zeros = shaped_zeros + draw_zeros
    for i in range(0, len(all_zeros), BATCH):
        conn.executemany(
            "UPDATE transitions SET reward = 0.0 WHERE id = ?",
            [(tid,) for tid in all_zeros[i : i + BATCH]],
        )

    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    print("Done.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix reward signals in talishar_games.db")
    parser.add_argument(
        "--db",
        default=os.path.join(_ROOT, "data", "talishar_games.db"),
        help="Path to SQLite database (default: data/talishar_games.db)",
    )
    parser.add_argument(
        "--max-start-hp", type=int, default=40,
        help="Fallback starting HP for normalization (default: 40)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report what would change without writing to DB",
    )
    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f"ERROR: Database not found: {args.db}")
        sys.exit(1)

    print(f"Database : {args.db}")
    print(f"Dry run  : {args.dry_run}")
    print()
    fix_rewards(args.db, max_start_hp=args.max_start_hp, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
