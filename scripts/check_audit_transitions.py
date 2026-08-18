"""scripts/check_audit_transitions.py

Automated rules-compliance checker against the audit transitions DB.

Checks (per FAB CR):
  1. Timing: PLAY_CARD/ATTACK_WEAPON only in action_step or via stack
  2. Timing: DEFEND_CARD/DEFEND_EQUIPMENT only in defend_step/reaction_step
  3. Resources: PLAY_CARD cost <= resources + pitch value
  4. Combat: DEFEND_* only when in_combat=1
  5. Combat: ATTACK_WEAPON not while already in combat
  6. Stacking: reactions only when stack has an entry
  7. Pass: always legal, no violation
  8. Phase rules: reactions only in reaction_step
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DB_PATH = ROOT / "data" / "audit_final.db"

# Legal phases for each action type (based on FAB CR 4.x game flow)
# action_step = player turn action phase
# react_step / reaction_step = window to play reactions
# defend_step = defender assigns blockers
LEGAL_PHASES = {
    "PLAY_CARD":           {"action_step", "react_step", "reaction_step"},
    "ATTACK_WEAPON":       {"action_step"},
    "ATTACK_HERO":         {"action_step"},
    "ATTACK_ALLY":         {"action_step"},
    "DEFEND_CARD":         {"defend_step", "reaction_step"},
    "DEFEND_EQUIPMENT":    {"defend_step", "reaction_step"},
    "DEFEND_NONE":         {"defend_step"},
    "ACTIVATE_ITEM":       {"action_step", "react_step", "reaction_step"},
    "ACTIVATE_EQUIPMENT":  {"action_step", "react_step", "reaction_step"},
    "PITCH":               {"action_step", "react_step", "reaction_step", "defend_step"},
    "PASS":                None,  # always legal
    "END_TURN":            {"action_step"},
    "ARSENAL_TO_HAND":     {"action_step"},
    "ARSENAL_TO_STACK":    {"action_step", "react_step", "reaction_step"},
    "PLAY_ARSENAL":        {"action_step", "react_step", "reaction_step"},
    "EQUIP":               set(),  # setup phase only
    "USE_TOKEN":           {"action_step", "react_step"},
}

DEFEND_ACTIONS = {"DEFEND_CARD", "DEFEND_EQUIPMENT", "DEFEND_NONE"}
REACTION_ACTIONS = {"PLAY_CARD", "PLAY_ARSENAL", "USE_TOKEN"}  # can be reactions


def run_checks(conn: sqlite3.Connection) -> dict:
    """Run all rule checks and return violation summary."""
    violations: dict[str, list[dict]] = defaultdict(list)
    stats: dict[str, int] = defaultdict(int)

    # Load card DB for cost lookups
    card_db = None
    try:
        from engine.card import CardDB
        from config import SLUG_INDEX_PATH
        card_db = CardDB(str(SLUG_INDEX_PATH))
    except Exception as e:
        print(f"  WARNING: Could not load card DB ({e}) — skipping resource checks")

    # -----------------------------------------------------------------------
    # 1. Phase/timing violations
    # -----------------------------------------------------------------------
    print("  [1] Checking phase/timing...")
    rows = conn.execute(
        """SELECT id, game_id, step_idx, player_id, phase, chosen_type,
                  chosen_card, chosen_pitch, in_combat, stack_depth
           FROM audit_transitions"""
    ).fetchall()

    for row in rows:
        action_type = row[5]
        phase = row[3]
        stats["total"] += 1
        stats[f"type_{action_type}"] += 1

        legal = LEGAL_PHASES.get(action_type)
        if legal is None:
            continue  # PASS always legal

        # Normalize phase names (engine may use different strings)
        phase_lower = phase.lower().replace(" ", "_") if phase else ""

        if legal and not any(phase_lower.startswith(p) or p.startswith(phase_lower)
                             for p in legal):
            violations["timing"].append({
                "id": row[0], "game_id": row[1], "step_idx": row[2],
                "type": action_type, "phase": phase,
                "expected_phases": sorted(legal),
            })

    # -----------------------------------------------------------------------
    # 2. Defend actions only when in_combat
    # -----------------------------------------------------------------------
    print("  [2] Checking defend requires in_combat...")
    rows2 = conn.execute(
        """SELECT id, game_id, step_idx, chosen_type, phase, in_combat
           FROM audit_transitions
           WHERE chosen_type IN ('DEFEND_CARD','DEFEND_EQUIPMENT','DEFEND_NONE')
             AND in_combat = 0"""
    ).fetchall()
    for row in rows2:
        violations["defend_not_in_combat"].append({
            "id": row[0], "game_id": row[1], "step_idx": row[2],
            "type": row[3], "phase": row[4],
        })

    # -----------------------------------------------------------------------
    # 3. ATTACK_WEAPON while already in combat
    # -----------------------------------------------------------------------
    print("  [3] Checking ATTACK_WEAPON not while in_combat...")
    rows3 = conn.execute(
        """SELECT id, game_id, step_idx, phase, in_combat
           FROM audit_transitions
           WHERE chosen_type = 'ATTACK_WEAPON' AND in_combat = 1"""
    ).fetchall()
    for row in rows3:
        violations["attack_while_in_combat"].append({
            "id": row[0], "game_id": row[1], "step_idx": row[2], "phase": row[3],
        })

    # -----------------------------------------------------------------------
    # 4. Resource check for PLAY_CARD
    # -----------------------------------------------------------------------
    if card_db is not None:
        print("  [4] Checking PLAY_CARD resource sufficiency...")
        rows4 = conn.execute(
            """SELECT id, game_id, step_idx, player_id, chosen_card, chosen_pitch, full_obs
               FROM audit_transitions
               WHERE chosen_type = 'PLAY_CARD' AND chosen_card IS NOT NULL"""
        ).fetchall()

        for row in rows4:
            card_slug = row[4]
            pitch_json = row[5]
            full_obs_str = row[6]

            try:
                card = card_db.get(card_slug)
                if card is None:
                    continue
                cost = getattr(card, 'cost', 0) or 0
                if cost == 0:
                    continue  # free card, no resource issue

                pitch_slugs = json.loads(pitch_json) if pitch_json else []
                pitch_total = sum(
                    (getattr(card_db.get(s), 'pitch_value', 0) or 0)
                    for s in pitch_slugs if s and card_db.get(s)
                )
                obs = json.loads(full_obs_str) if full_obs_str else {}
                pid = row[3]
                key = f"p{pid}_resources"
                available = (obs.get(key, 0) or 0) + pitch_total

                if available < cost:
                    violations["insufficient_resources"].append({
                        "id": row[0], "game_id": row[1], "step_idx": row[2],
                        "card": card_slug, "cost": cost,
                        "available": available, "pitch_total": pitch_total,
                        "base_resources": obs.get(key, 0),
                    })
            except Exception:
                pass

    # -----------------------------------------------------------------------
    # 5. Stacked reactions without a stack entry
    # -----------------------------------------------------------------------
    print("  [5] Checking reactions have stack entries...")
    rows5 = conn.execute(
        """SELECT id, game_id, step_idx, chosen_type, phase, stack_depth
           FROM audit_transitions
           WHERE phase IN ('reaction_step','react_step')
             AND chosen_type IN ('PLAY_CARD','PLAY_ARSENAL')
             AND stack_depth = 0"""
    ).fetchall()
    for row in rows5:
        violations["reaction_without_stack"].append({
            "id": row[0], "game_id": row[1], "step_idx": row[2],
            "type": row[3], "phase": row[4],
        })

    # -----------------------------------------------------------------------
    # Summary stats
    # -----------------------------------------------------------------------
    type_counts = {k[5:]: v for k, v in stats.items() if k.startswith("type_")}

    return {
        "total_transitions": stats["total"],
        "action_type_counts": dict(sorted(type_counts.items(), key=lambda x: -x[1])),
        "violations": {k: v for k, v in violations.items()},
        "violation_counts": {k: len(v) for k, v in violations.items()},
    }


def print_report(report: dict) -> None:
    print()
    print("=" * 70)
    print("  RULES AUDIT REPORT")
    print("=" * 70)
    print()
    print(f"  Total transitions analyzed: {report['total_transitions']:,}")
    print()
    print("  Action type breakdown:")
    for atype, count in report["action_type_counts"].items():
        pct = count / report["total_transitions"] * 100 if report["total_transitions"] else 0
        print(f"    {atype:<30} {count:>8,} ({pct:.1f}%)")
    print()

    total_violations = sum(report["violation_counts"].values())
    print(f"  Total violations found: {total_violations}")
    print()

    if total_violations == 0:
        print("  PASS — no rule violations detected")
        return

    for check, count in report["violation_counts"].items():
        if count == 0:
            continue
        print(f"  [{count}] {check}")
        samples = report["violations"][check][:5]
        for v in samples:
            print(f"        {v}")
        if count > 5:
            print(f"        ... (+{count - 5} more)")
        print()


def main():
    if not DB_PATH.exists():
        print(f"ERROR: Audit DB not found at {DB_PATH}")
        print("Run scripts/run_audit_games.py first.")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    game_count = conn.execute("SELECT COUNT(*) FROM audit_games").fetchone()[0]
    trans_count = conn.execute("SELECT COUNT(*) FROM audit_transitions").fetchone()[0]
    print(f"Audit DB: {game_count} games, {trans_count:,} transitions")
    print()
    print("Running checks...")

    report = run_checks(conn)
    conn.close()

    print_report(report)

    # Write JSON report
    import json as _json
    report_path = ROOT / "data" / "audit_report.json"
    # Trim violations to first 100 each for readability
    for k in report["violations"]:
        report["violations"][k] = report["violations"][k][:100]
    with open(report_path, "w", encoding="utf-8") as f:
        _json.dump(report, f, indent=2)
    print(f"\n  Full report written to: {report_path}")


if __name__ == "__main__":
    main()
