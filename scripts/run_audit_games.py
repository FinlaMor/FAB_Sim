"""scripts/run_audit_games.py

Run N games with random agents and log every decision transition to
an audit SQLite database (no torch dependency).

Usage:
    python scripts/run_audit_games.py --games 1000 --db data/audit.db
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card import CardDB
from engine.actions import Action, ActionType, legal_actions
from engine.state import GameState, Step
from engine.engine import new_game
from config import SLUG_INDEX_PATH


# ---------------------------------------------------------------------------
# Audit DB
# ---------------------------------------------------------------------------

def _ensure_audit_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_games (
            game_id INTEGER PRIMARY KEY AUTOINCREMENT,
            p1_hero TEXT,
            p2_hero TEXT,
            winner INTEGER,
            turns INTEGER,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_transitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER,
            step_idx INTEGER,
            player_id INTEGER,
            phase TEXT,
            legal_action_types TEXT,
            chosen_type TEXT,
            chosen_card TEXT,
            chosen_pitch TEXT,
            chosen_defend TEXT,
            chosen_slot TEXT,
            p1_hp INTEGER,
            p2_hp INTEGER,
            p1_hand_size INTEGER,
            p2_hand_size INTEGER,
            in_combat INTEGER,
            combat_attacker INTEGER,
            combat_power INTEGER,
            combat_keywords TEXT,
            stack_depth INTEGER,
            stack_top TEXT,
            full_obs TEXT
        )
    """)
    conn.commit()


def _card_slug(card) -> str | None:
    if card is None:
        return None
    return getattr(card, 'slug', None)


def _snapshot_state(state: GameState, player_id: int) -> dict:
    p1 = state.players[1]
    p2 = state.players[2]

    in_combat = state.combat is not None
    combat_info: dict = {}
    if in_combat:
        c = state.combat
        combat_info = {
            "attacker_id": c.attacker_id,
            "attack_power": getattr(c, 'attack_power', None),
            "base_power": getattr(c, 'base_power', None),
            "keywords": list(getattr(c, 'keywords', []) or []),
            "defending_cards": [_card_slug(x) for x in (getattr(c, 'defending_cards', []) or [])],
            "defending_equipment": [_card_slug(x) for x in (getattr(c, 'defending_equipment', []) or [])],
            "defender_used_hand_card": getattr(c, 'defender_used_hand_card', False),
            "from_weapon": getattr(c, 'from_weapon', False),
            "is_stealth_attack": getattr(c, 'is_stealth_attack', False),
        }

    stack_entries = []
    for entry in (getattr(state, 'stack', []) or []):
        stack_entries.append({
            "player_id": getattr(entry, 'player_id', None),
            "card": _card_slug(getattr(entry, 'card', None)),
            "is_attack": getattr(entry, 'is_attack', False),
        })

    return {
        "turn": state.turn_number,
        "phase": state.step.value if hasattr(state.step, 'value') else str(state.step),
        "active_player": state.active_player,
        "priority_player": state.priority_player,
        "p1_hp": p1.health,
        "p2_hp": p2.health,
        "p1_hand_size": len(p1.hand.cards),
        "p2_hand_size": len(p2.hand.cards),
        "p1_resources": getattr(p1, 'resources', 0),
        "p2_resources": getattr(p2, 'resources', 0),
        "p1_action_points": getattr(p1, 'action_points', 0),
        "p2_action_points": getattr(p2, 'action_points', 0),
        "in_combat": in_combat,
        "combat": combat_info,
        "stack_depth": len(stack_entries),
        "stack": stack_entries,
    }


class AuditRecorderAgent:
    """Wraps a random agent and logs every decision to the audit DB."""

    def __init__(self, player_id: int, game_id: int, conn: sqlite3.Connection,
                 step_counter: list[int], rng: random.Random,
                 max_per_game: int = 10000):
        self.player_id = player_id
        self.game_id = game_id
        self.conn = conn
        self.step_counter = step_counter
        self.rng = rng
        self.max_per_game = max_per_game
        self._rows: list[tuple] = []

    def __call__(self, state: GameState, options, context=None):
        if not options:
            return None

        # Guardrail
        if self.step_counter[0] >= self.max_per_game:
            state.winner = 1 if state.players[1].health >= state.players[2].health else 2
            state.done = True
            if isinstance(options[0], Action):
                pass_act = next((a for a in options if a.type == ActionType.PASS), None)
                return pass_act if pass_act is not None else options[0]
            return options[0]

        # Random choice
        if isinstance(options[0], Action):
            choice = self.rng.choice(options)
        else:
            choice = self.rng.choice(options)

        # Record if it's an Action
        if isinstance(options[0], Action) and isinstance(choice, Action):
            snap = _snapshot_state(state, self.player_id)
            legal_types = list({a.type.value for a in options})

            # Stack top
            stack_top = None
            if snap["stack"]:
                stack_top = json.dumps(snap["stack"][-1])

            # Combat fields
            in_combat = snap["in_combat"]
            combat = snap.get("combat", {})

            row = (
                self.game_id,
                self.step_counter[0],
                self.player_id,
                snap["phase"],
                json.dumps(sorted(legal_types)),
                choice.type.value,
                _card_slug(choice.card),
                json.dumps([_card_slug(c) for c in (choice.pitch_cards or [])]),
                json.dumps([_card_slug(c) for c in (choice.card_list or [])]),
                choice.slot,
                snap["p1_hp"],
                snap["p2_hp"],
                snap["p1_hand_size"],
                snap["p2_hand_size"],
                1 if in_combat else 0,
                combat.get("attacker_id") if in_combat else None,
                combat.get("attack_power") if in_combat else None,
                json.dumps(combat.get("keywords", [])) if in_combat else None,
                snap["stack_depth"],
                stack_top,
                json.dumps(snap),
            )
            self._rows.append(row)
            self.step_counter[0] += 1

            # Flush every 200 decisions
            if len(self._rows) >= 200:
                self._flush()

        return choice

    def _flush(self) -> None:
        if not self._rows:
            return
        self.conn.executemany(
            """INSERT INTO audit_transitions (
                game_id, step_idx, player_id, phase,
                legal_action_types, chosen_type, chosen_card,
                chosen_pitch, chosen_defend, chosen_slot,
                p1_hp, p2_hp, p1_hand_size, p2_hand_size,
                in_combat, combat_attacker, combat_power, combat_keywords,
                stack_depth, stack_top, full_obs
            ) VALUES (?,?,?,?, ?,?,?, ?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?)""",
            self._rows,
        )
        self.conn.commit()
        self._rows.clear()

    def flush(self) -> None:
        self._flush()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=1000)
    parser.add_argument("--db", default="data/audit.db")
    parser.add_argument("--max-turns", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    db_path = ROOT / args.db
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    _ensure_audit_schema(conn)

    card_db = CardDB(str(SLUG_INDEX_PATH))

    deck_dir = ROOT / "decks" / "generated"
    deck_files = sorted(deck_dir.glob("*.txt"))
    if not deck_files:
        print("ERROR: No deck files found in decks/generated/")
        sys.exit(1)

    print(f"Found {len(deck_files)} deck files")
    print(f"Running {args.games} games -> {db_path}")
    print()

    rng = random.Random(args.seed)
    t_start = time.time()
    crashes = 0
    total_transitions = 0

    for game_idx in range(args.games):
        d1, d2 = rng.sample(deck_files, 2)
        seed1 = rng.randint(0, 2**31)
        seed2 = rng.randint(0, 2**31)

        # Insert game row
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO audit_games (p1_hero, p2_hero, created_at) VALUES (?,?,?)",
            (d1.stem, d2.stem, now)
        )
        game_id = cur.lastrowid
        conn.commit()

        step_counter = [0]
        p1_agent = AuditRecorderAgent(1, game_id, conn, step_counter, rng)
        p2_agent = AuditRecorderAgent(2, game_id, conn, step_counter, rng)

        try:
            state = new_game(
                str(d1), str(d2),
                p1_agent, p2_agent,
                card_db,
                p1_seed=seed1, p2_seed=seed2,
                max_turns=args.max_turns,
            )
            winner = getattr(state, 'winner', None)
            turns = getattr(state, 'turn_number', 0)
        except Exception as exc:
            crashes += 1
            winner = None
            turns = 0
            print(f"  Game {game_idx+1}: CRASH — {exc}")

        # Flush remaining rows
        p1_agent.flush()
        p2_agent.flush()

        # Update game record
        conn.execute(
            "UPDATE audit_games SET winner=?, turns=? WHERE game_id=?",
            (winner, turns, game_id)
        )
        conn.commit()

        total_transitions += step_counter[0]

        if (game_idx + 1) % 100 == 0:
            elapsed = time.time() - t_start
            avg_ms = elapsed / (game_idx + 1) * 1000
            print(f"Game {game_idx+1}/{args.games} | avg {avg_ms:.1f}ms | transitions: {total_transitions} | crashes: {crashes}")

    elapsed = time.time() - t_start
    conn.close()

    print()
    print(f"=== {args.games} games ===")
    print(f"Total: {elapsed:.2f}s | Avg: {elapsed/args.games*1000:.1f}ms | Crashes: {crashes}")
    print(f"Total transitions logged: {total_transitions}")
    print(f"DB: {db_path}")


if __name__ == "__main__":
    main()
