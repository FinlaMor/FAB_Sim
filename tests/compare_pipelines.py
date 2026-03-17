"""compare_pipelines.py — Side-by-side data comparison of Local Engine vs Talishar Adapter.

Runs a short game through each pipeline with random agents, captures state/action
snapshots at decision points, and writes them to a JSON file for review.

Usage:
    python tests/compare_pipelines.py
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DECKS_DIR, SLUG_INDEX_PATH
from engine.actions import Action, ActionType
from engine.card import CardDB
from engine.engine import new_game
from engine.state import GameState, Step
from rl_agents.game_backends import (
    TalisharClient,
    _deck_file_to_talishar_slugs,
    _pick_talishar_random_fallback_action,
)
from rl_agents.talishar_adapter import (
    talishar_state_to_observed_game_state,
    talishar_actions_to_engine_actions,
    talishar_phase_to_step,
)

SEED = 42
MAX_TURNS = 8
MAX_SNAPSHOTS = 30

P1_DECK = os.path.join(DECKS_DIR, "kayo_underhanded_cheat_CC_lite.txt")
P2_DECK = os.path.join(DECKS_DIR, "oscillio_constella_intelligence_CC_lite.txt")

OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pipeline_comparison.json")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _card_slug(c) -> str | None:
    if c is None:
        return None
    return c.slug if hasattr(c, "slug") else str(c)


def _zone_summary(zone) -> dict:
    cards = list(zone.cards) if hasattr(zone, "cards") else []
    return {
        "count": len(cards),
        "slugs": [_card_slug(c) for c in cards],
    }


def _combat_summary(combat) -> dict | None:
    if combat is None:
        return None
    return {
        "attack_card": _card_slug(getattr(combat, "attack_card", None)),
        "attack_power": getattr(combat, "total_attack_power", None),
        "total_defense": getattr(combat, "total_defense", None),
        "chain_link_number": getattr(combat, "chain_link_number", None),
        "has_go_again": getattr(combat, "has_go_again", None),
        "defending_cards": [_card_slug(c) for c in getattr(combat, "defending_cards", [])],
    }


def _action_summary(action: Action) -> dict:
    return {
        "type": action.type.value,
        "card": _card_slug(action.card),
        "from_arsenal": action.from_arsenal,
        "pitch_cards": [_card_slug(c) for c in action.pitch_cards] if action.pitch_cards else [],
        "targets": [_card_slug(t) for t in action.targets] if action.targets else [],
        "is_melded": getattr(action, "is_melded", None),
        "alternative_cost_used": getattr(action, "alternative_cost_used", None),
        "modes_selected": list(action.modes_selected) if action.modes_selected else [],
        "has_go_again": getattr(action, "has_go_again", None),
        "is_instant_speed": getattr(action, "is_instant_speed", None),
        "action_cost": getattr(action, "action_cost", None),
        "resource_cost": getattr(action, "resource_cost", None),
        "source_zone": getattr(action, "source_zone", None),
        "slot": action.slot,
    }


def _state_snapshot(state: GameState, player_id: int, source: str) -> dict:
    p = state.players.get(player_id)
    opp = state.players.get(3 - player_id)
    if p is None or opp is None:
        return {"error": f"Player {player_id} not found", "source": source}

    snapshot: dict[str, Any] = {
        "source": source,
        "turn_number": state.turn_number,
        "step": state.step.value if hasattr(state.step, "value") else str(state.step),
        "active_player": state.active_player,
        "priority_player": state.priority_player,
        "consecutive_passes": state.consecutive_passes,
        "done": state.done,
        "winner": state.winner,
        "player": {
            "id": player_id,
            "health": p.health,
            "action_points": getattr(p, "action_points", None),
            "resources": getattr(p, "resources", None),
            "hero": _card_slug(p.hero),
            "hand": _zone_summary(p.hand),
            "deck": {"count": len(p.deck)},
            "graveyard": _zone_summary(p.graveyard),
            "pitch": _zone_summary(p.pitch),
            "arsenal": _zone_summary(p.arsenal) if hasattr(p, "arsenal") else None,
            "equipment": {
                slot: _card_slug(getattr(p, slot, None))
                for slot in ("head", "chest", "arms", "legs", "weapon1", "weapon2")
                if getattr(p, slot, None) is not None
            },
        },
        "opponent": {
            "id": 3 - player_id,
            "health": opp.health,
            "hand": {"count": len(opp.hand)},
            "deck": {"count": len(opp.deck)},
            "graveyard": _zone_summary(opp.graveyard),
        },
        "combat": _combat_summary(state.combat),
        "stack_entries": len(state.stack_entries) if hasattr(state, "stack_entries") else 0,
    }

    # Talishar-specific metadata (only present on adapter-produced states)
    if hasattr(state, "talishar_phase_code"):
        snapshot["talishar_meta"] = {
            "phase_code": getattr(state, "talishar_phase_code", None),
            "turn_phase": getattr(state, "talishar_turn_phase", None),
            "tracker": getattr(state, "talishar_tracker", None),
            "layer_target": getattr(state, "talishar_layer_target", None),
            "player_effects": getattr(state, "talishar_player_effects", None),
            "opponent_effects": getattr(state, "talishar_opponent_effects", None),
        }

    return snapshot


# ---------------------------------------------------------------------------
# Pipeline 1: Local Engine
# ---------------------------------------------------------------------------

def run_local_engine(card_db: CardDB) -> list[dict]:
    snapshots: list[dict] = []
    rng1 = random.Random(SEED)
    rng2 = random.Random(SEED + 1)
    snap_count = [0]

    class SnapshotAgent:
        def __init__(self, pid, rng):
            self.pid = pid
            self.rng = rng

        def __call__(self, state, options, context=None):
            if (
                snap_count[0] < MAX_SNAPSHOTS
                and isinstance(options, (list, tuple))
                and len(options) > 0
                and isinstance(options[0], Action)
            ):
                snap = _state_snapshot(state, self.pid, "local_engine")
                snap["num_legal_actions"] = len(options)
                snap["legal_actions"] = [_action_summary(a) for a in options[:15]]  # cap for readability
                snap["context"] = context
                snapshots.append(snap)
                snap_count[0] += 1

            if isinstance(options, (list, tuple)):
                return self.rng.choice(options)
            return options

    agent1 = SnapshotAgent(1, rng1)
    agent2 = SnapshotAgent(2, rng2)

    print("[local] Running local engine game...")
    t0 = time.time()
    final = new_game(
        P1_DECK, P2_DECK, agent1, agent2,
        card_db=card_db, p1_seed=SEED, p2_seed=SEED + 1,
        max_turns=MAX_TURNS,
    )
    elapsed = time.time() - t0
    print(f"[local] Done in {elapsed:.1f}s — turns={final.turn_number}, winner=P{final.winner}, snapshots={len(snapshots)}")
    return snapshots


# ---------------------------------------------------------------------------
# Pipeline 2: Talishar Adapter
# ---------------------------------------------------------------------------

def run_talishar_pipeline(card_db: CardDB) -> list[dict]:
    snapshots: list[dict] = []

    client = TalisharClient(base_url="http://localhost:8080/game")
    p1_deck = _deck_file_to_talishar_slugs(P1_DECK)
    p2_deck = _deck_file_to_talishar_slugs(P2_DECK)

    game_name, p1_auth = client.create_game(p1_deck, deck_test_mode=False)
    p2_auth = client.join_game(game_name, p2_deck, player_id=2)
    if not client.start_game(game_name, p1_auth):
        raise RuntimeError("Talishar start failed")
    print(f"[talishar] Game {game_name} started")

    p1_rng = random.Random(SEED)
    p2_rng = random.Random(SEED + 1)
    total_actions = 0
    stall = 0

    for _ in range(MAX_TURNS * 80):
        state1 = client.get_state(game_name, p1_auth, player_id=1)
        state2 = client.get_state(game_name, p2_auth, player_id=2)

        turn_num = int(state1.get("turnNo", 0))
        if turn_num >= MAX_TURNS:
            break

        over, winner = client.is_game_over(state1)
        if over:
            print(f"[talishar] Game over — winner=P{winner}")
            break

        # Determine who acts
        if bool(state1.get("havePriority")):
            actor_id, actor_state, actor_auth, actor_rng = 1, state1, p1_auth, p1_rng
        elif bool(state2.get("havePriority")):
            actor_id, actor_state, actor_auth, actor_rng = 2, state2, p2_auth, p2_rng
        else:
            stall += 1
            if stall > 100:
                print("[talishar] Stall limit reached")
                break
            time.sleep(0.05)
            continue
        stall = 0

        # Capture snapshot: raw Talishar JSON + adapter-converted state + adapter-converted actions
        if len(snapshots) < MAX_SNAPSHOTS:
            try:
                adapted_state = talishar_state_to_observed_game_state(
                    actor_state, player_id=actor_id, card_db=card_db
                )
                adapted_actions = talishar_actions_to_engine_actions(
                    actor_state, card_db=card_db, player_id=actor_id
                )
                snap = _state_snapshot(adapted_state, actor_id, "talishar_adapter")
                snap["num_legal_actions"] = len(adapted_actions)
                snap["legal_actions"] = [_action_summary(a) for a in adapted_actions[:15]]

                # Include key raw Talishar fields for comparison
                snap["talishar_raw"] = {
                    "turnNo": actor_state.get("turnNo"),
                    "turnPhase": actor_state.get("turnPhase"),
                    "tracker": actor_state.get("tracker"),
                    "havePriority": actor_state.get("havePriority"),
                    "playerHealth": actor_state.get("playerHealth"),
                    "opponentHealth": actor_state.get("opponentHealth"),
                    "playerAP": actor_state.get("playerAP"),
                    "opponentAP": actor_state.get("opponentAP"),
                    "canPassPhase": actor_state.get("canPassPhase"),
                    "amIActivePlayer": actor_state.get("amIActivePlayer"),
                    "hand_count": len(actor_state.get("playerHand", [])),
                    "equipment_count": len(actor_state.get("playerEquipment", [])),
                    "active_chain_link": bool(actor_state.get("activeChainLink")),
                }
                snapshots.append(snap)
            except Exception as e:
                print(f"  [talishar] Adapter error at action #{total_actions}: {e}")

        # Pick and submit action
        actions = client.get_available_actions(actor_state)
        if not actions:
            if actor_state.get("canPassPhase"):
                client.process_input(game_name, actor_auth, 99, player_id=actor_id)
                total_actions += 1
            else:
                stall += 1
                if stall > 100:
                    break
                time.sleep(0.05)
            continue

        action = _pick_talishar_random_fallback_action(actor_state, actions, actor_rng)
        client.submit_action(game_name, actor_auth, action, player_id=actor_id)
        total_actions += 1

    print(f"[talishar] Done — actions={total_actions}, snapshots={len(snapshots)}")
    return snapshots


# ---------------------------------------------------------------------------
# Comparison output
# ---------------------------------------------------------------------------

def build_comparison(local_snaps: list[dict], talishar_snaps: list[dict]) -> dict:
    """Build a structured comparison summary."""

    def _field_coverage(snaps: list[dict], source_name: str) -> dict:
        """Summarize which fields are populated vs empty/None across snapshots."""
        if not snaps:
            return {}

        # Collect all step values seen
        steps_seen: set[str] = set()
        action_types_seen: set[str] = set()
        has_combat_count = 0
        has_stack_count = 0
        health_range = {"min": 999, "max": 0}
        total_actions = []

        for s in snaps:
            steps_seen.add(s.get("step", "?"))
            for a in s.get("legal_actions", []):
                action_types_seen.add(a.get("type", "?"))
            if s.get("combat") is not None:
                has_combat_count += 1
            se = s.get("stack_entries", 0)
            if se > 0:
                has_stack_count += 1
            ph = s.get("player", {}).get("health", 0)
            health_range["min"] = min(health_range["min"], ph)
            health_range["max"] = max(health_range["max"], ph)
            total_actions.append(s.get("num_legal_actions", 0))

        return {
            "source": source_name,
            "snapshot_count": len(snaps),
            "steps_seen": sorted(steps_seen),
            "action_types_seen": sorted(action_types_seen),
            "snapshots_with_combat": has_combat_count,
            "snapshots_with_stack": has_stack_count,
            "player_health_range": health_range,
            "avg_legal_actions": round(sum(total_actions) / len(total_actions), 1) if total_actions else 0,
            "max_legal_actions": max(total_actions) if total_actions else 0,
        }

    comparison = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "seed": SEED,
        "max_turns": MAX_TURNS,
        "p1_deck": os.path.basename(P1_DECK),
        "p2_deck": os.path.basename(P2_DECK),
        "summary": {
            "local_engine": _field_coverage(local_snaps, "local_engine"),
            "talishar_adapter": _field_coverage(talishar_snaps, "talishar_adapter"),
        },
        "local_engine_snapshots": local_snaps,
        "talishar_adapter_snapshots": talishar_snaps,
    }
    return comparison


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("PIPELINE COMPARISON: Local Engine vs Talishar Adapter")
    print("=" * 70)

    card_db = CardDB(SLUG_INDEX_PATH)

    local_snaps = run_local_engine(card_db)
    print()

    try:
        talishar_snaps = run_talishar_pipeline(card_db)
    except Exception as e:
        print(f"[talishar] FAILED: {e}")
        talishar_snaps = []

    print()
    comparison = build_comparison(local_snaps, talishar_snaps)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2, default=str)

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    for src in ("local_engine", "talishar_adapter"):
        s = comparison["summary"].get(src, {})
        if not s:
            print(f"\n  {src}: NO DATA")
            continue
        print(f"\n  {src}:")
        print(f"    Snapshots captured : {s['snapshot_count']}")
        print(f"    Steps seen         : {s['steps_seen']}")
        print(f"    Action types seen  : {s['action_types_seen']}")
        print(f"    Combat snapshots   : {s['snapshots_with_combat']}")
        print(f"    Stack snapshots    : {s['snapshots_with_stack']}")
        print(f"    Health range       : {s['player_health_range']}")
        print(f"    Avg legal actions  : {s['avg_legal_actions']}")
        print(f"    Max legal actions  : {s['max_legal_actions']}")

    # Side-by-side field comparison for first few snapshots
    print(f"\n{'=' * 70}")
    print("FIRST 5 SNAPSHOTS — SIDE BY SIDE KEY FIELDS")
    print("=" * 70)

    n = min(5, len(local_snaps), len(talishar_snaps))
    for i in range(n):
        l = local_snaps[i]
        t = talishar_snaps[i]
        print(f"\n--- Snapshot {i+1} ---")
        for field in ("turn_number", "step", "active_player", "priority_player", "consecutive_passes"):
            lv = l.get(field, "?")
            tv = t.get(field, "?")
            match = "OK" if str(lv) == str(tv) else "DIFF"
            print(f"  {field:25s}  local={str(lv):20s}  talishar={str(tv):20s}  [{match}]")

        lp = l.get("player", {})
        tp = t.get("player", {})
        for field in ("health", "action_points", "resources"):
            lv = lp.get(field, "?")
            tv = tp.get(field, "?")
            match = "OK" if str(lv) == str(tv) else "DIFF"
            print(f"  player.{field:17s}  local={str(lv):20s}  talishar={str(tv):20s}  [{match}]")

        print(f"  player.hand.count          local={str(lp.get('hand', {}).get('count', '?')):20s}  talishar={str(tp.get('hand', {}).get('count', '?')):20s}")
        print(f"  num_legal_actions          local={str(l.get('num_legal_actions', '?')):20s}  talishar={str(t.get('num_legal_actions', '?')):20s}")

        # Action type distribution
        l_types = [a["type"] for a in l.get("legal_actions", [])]
        t_types = [a["type"] for a in t.get("legal_actions", [])]
        l_dist = {}
        for at in l_types:
            l_dist[at] = l_dist.get(at, 0) + 1
        t_dist = {}
        for at in t_types:
            t_dist[at] = t_dist.get(at, 0) + 1
        print(f"  action_type_dist           local={str(l_dist):40s}")
        print(f"  {'':25s}  talishar={str(t_dist):40s}")

    print(f"\nFull data written to: {OUT_PATH}")
    print("=" * 70)


if __name__ == "__main__":
    main()
