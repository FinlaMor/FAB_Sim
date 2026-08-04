"""Regression guard: the three functional decks must play rules-clean games.

Plays a handful of seeded random games across the Victor / Kayo / Arakni CC decks,
records full JSONL transcripts, and runs the rules-invariant checks from
scripts/game_transcript_audit.py (card conservation, life/winner integrity, zone
sanity). Any violation fails the suite — so an engine or card change that lets a
card be created from nothing, drives life below zero in a live state, etc., is
caught here instead of only by an ad-hoc audit run.

Kept small (seeded random agents, a few games) so it stays in the normal suite.
"""
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from engine.card import CardDB
from engine.engine import new_game
from engine.recorder import JsonlRecorder
from rl_agents.random_agent import RandomAgent
import game_transcript_audit as audit

DECKS_DIR = ROOT / "decks"
DECKS = {
    "victor": "victor_goldmane_high_and_mighty_CC_lite.txt",
    "kayo": "kayo_underhanded_cheat_CC_lite.txt",
    "arakni": "arakni_marionette_CC_lite.txt",
}
# A couple of seeds per matchup — enough to exercise each deck, small enough to
# stay in the normal suite.
MATCHUPS = [("victor", "kayo"), ("kayo", "arakni"), ("victor", "arakni")]
SEEDS = [0, 1]


@pytest.mark.parametrize("p1,p2", MATCHUPS)
@pytest.mark.parametrize("seed", SEEDS)
def test_functional_decks_play_rules_clean(p1, p2, seed, tmp_path):
    db = CardDB()
    path = tmp_path / f"{p1}_vs_{p2}_seed{seed}.jsonl"
    rec = JsonlRecorder(str(path), snapshot_on={"decision"})
    random.seed(seed)
    state = new_game(
        str(DECKS_DIR / DECKS[p1]),
        str(DECKS_DIR / DECKS[p2]),
        RandomAgent(seed=seed),
        RandomAgent(seed=seed + 1),
        db, p1_seed=seed, p2_seed=seed + 1,
        max_turns=60, recorders=[rec],
    )
    # Game reached a terminal state (a winner, or the turn cap) without crashing.
    assert state is not None

    _name, findings, _info, _opening = audit.audit_game(str(path))
    assert findings == [], (
        f"{p1} vs {p2} seed{seed}: rules-invariant violations:\n  "
        + "\n  ".join(findings)
    )
