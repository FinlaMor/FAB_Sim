"""Behavioral tests for the engine recorder hooks (engine/recorder.py).

A recorder attached via new_game(recorders=[...]) must observe everything:
every event, every decision (the exact options presented to the agent AND the
chosen option), every applied action, step transitions, layer resolutions,
and game start/end — and all of it must be JSON-serializable.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card import CardDB
from engine.engine import new_game
from engine.recorder import JsonlRecorder, MemoryRecorder, snapshot_state
from rl_agents.random_agent import RandomAgent

DB = CardDB()
DECK1 = str(ROOT / "decks" / "victor_goldmane_high_and_mighty_CC_lite.txt")
DECK2 = str(ROOT / "decks" / "kayo_underhanded_cheat_CC_lite.txt")


def _run_recorded_game(recorder, max_turns: int = 20):
    return new_game(DECK1, DECK2, RandomAgent(seed=7), RandomAgent(seed=8),
                    DB, p1_seed=1, p2_seed=2, max_turns=max_turns,
                    recorders=[recorder])


def test_memory_recorder_captures_all_hook_kinds():
    rec = MemoryRecorder()
    state = _run_recorded_game(rec)

    kinds = {r["kind"] for r in rec.records}
    assert "game_start" in kinds
    assert "event" in kinds
    assert "decision" in kinds
    assert "action_applied" in kinds
    assert "step_change" in kinds
    assert "layer_resolved" in kinds
    assert "game_end" in kinds

    # The game actually finished and the end record reflects it.
    end = rec.of_kind("game_end")[-1]
    assert end["winner"] == state.winner
    assert end["snapshot"]["done"] is True


def test_decisions_record_options_and_choice():
    rec = MemoryRecorder()
    _run_recorded_game(rec)

    decisions = rec.of_kind("decision")
    assert decisions, "a full game must contain decision points"
    for d in decisions:
        # Every decision carries the full option list presented to the model…
        assert isinstance(d["options"], list) and len(d["options"]) >= 1
        assert d["legal_actions_count"] == len(d["options"])
        # …and the choice that was made.
        assert "chosen" in d
        assert d["player_id"] in (1, 2)
        # When the chosen object is one of the presented options (the normal
        # case), its index is recorded for action-masked training.
        if d["chosen_index"] is not None:
            assert 0 <= d["chosen_index"] < len(d["options"])

    # At least one decision is a main-action choice with a PASS option
    # (i.e. the options are serialized Actions, not just scalars).
    assert any(
        any(isinstance(o, dict) and o.get("type") == "pass" for o in d["options"])
        for d in decisions
    )


def test_all_records_are_json_serializable():
    rec = MemoryRecorder(snapshot_on={"decision"})
    _run_recorded_game(rec, max_turns=8)
    text = json.dumps(rec.records, default=str)
    assert len(text) > 1000
    # Snapshots embedded on decisions include full zone information.
    d = rec.of_kind("decision")[0]
    snap = d["snapshot"]
    for pid in ("1", 1):
        if pid in snap["players"]:
            player_snap = snap["players"][pid]
            break
    assert "hand" in player_snap and "deck_count" in player_snap
    assert "life" in player_snap and "equipment" in player_snap


def test_jsonl_recorder_writes_parseable_lines(tmp_path):
    path = tmp_path / "game.jsonl"
    rec = JsonlRecorder(str(path))
    _run_recorded_game(rec, max_turns=8)
    rec.close()

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) > 50
    parsed = [json.loads(line) for line in lines]
    kinds = [p["kind"] for p in parsed]
    # Pre-game decisions (the coin flip) are recorded before game_start —
    # recorders attach before the start-of-game procedure on purpose.
    assert "game_start" in kinds[:5]
    assert kinds[-1] == "game_end"


def test_snapshot_state_standalone():
    rec = MemoryRecorder()
    state = _run_recorded_game(rec, max_turns=6)
    snap = snapshot_state(state)
    assert snap["done"] is True
    assert set(snap["players"].keys()) == {1, 2}
    total_p1 = (len(snap["players"][1]["hand"]) + snap["players"][1]["deck_count"]
                + len(snap["players"][1]["graveyard"]) + len(snap["players"][1]["pitch"])
                + len(snap["players"][1]["arsenal"]) + len(snap["players"][1]["banished"]))
    assert total_p1 >= 55  # deck cards accounted for across zones
    json.dumps(snap, default=str)  # fully serializable
