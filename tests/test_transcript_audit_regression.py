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


# Tokens are engine-created and legitimately appear/vanish, so they are excluded
# from the object-conservation invariant below.
_TOKENS = audit.TOKENS


def _real_card_objects(state):
    """Every non-token card OBJECT currently in any player zone, keyed by a
    stable provenance stamp we attach the first time we see it."""
    objs = set()
    for _pid, pl in state.players.items():
        for attr in dir(pl):
            if attr.startswith("_"):
                continue
            try:
                zone = getattr(pl, attr)
            except Exception:
                continue
            for card in (getattr(zone, "cards", None) or []):
                slug = getattr(card, "slug", None)
                if isinstance(slug, str) and slug not in _TOKENS:
                    if not hasattr(card, "_prov_id"):
                        card._prov_id = (id(card), slug)
                    objs.add(card._prov_id)
    return objs


def test_no_real_card_created_from_nothing(tmp_path):
    """Ground-truth card conservation: stamp every card object and assert that
    no non-token card OBJECT exists at game end that wasn't present after setup.

    This is stronger than audit_game's slug-count heuristic (which reads a
    zone-selective count and can misjudge the baseline). A real duplication bug
    (e.g. an ON_HIT effect that relocates an attack while combat-close also sends
    it to the graveyard — the Herald-of-Protection class) creates a brand-new
    object and trips this immediately.
    """
    from engine.recorder import GameRecorder

    captures = {"start": None, "end": None}

    class Stamp(GameRecorder):
        def on_event(self, state, event=None, **kwargs):
            snapshot = _real_card_objects(state)
            if captures["start"] is None and all(
                pl.deck.cards for pl in state.players.values()
            ):
                captures["start"] = set(snapshot)
            captures["end"] = snapshot

    db = CardDB()
    random.seed(0)
    new_game(
        str(DECKS_DIR / DECKS["victor"]),
        str(DECKS_DIR / DECKS["kayo"]),
        RandomAgent(seed=0),
        RandomAgent(seed=1),
        db, p1_seed=0, p2_seed=1, max_turns=60, recorders=[Stamp()],
    )
    start, end = captures["start"], captures["end"]
    assert start is not None and end is not None
    created = end - start
    assert not created, f"card objects created from nothing during the game: {created}"
