"""Starfall — "if an instant card has been put into your graveyard this turn".

16 cards carry this clause; the implemented one read an invented STARFALL_FLAG
that nothing ever set, so the Starfall half could never fire.

The event is recorded in `Zone.add`, not at the call sites. A card reaches the
graveyard from 11 places across 3 files (destroy, discard, attack resolution,
chain close, landmark cleanup, the CR 3.0.12 CLEAR redirect, ...), so hooking
call sites would encode a list of paths someone remembered on one day. Zone.add
is the one gate they all pass through.
"""
import copy

import pytest

from engine.card import Card, CardDB
from engine.card_effects.dsl.condition_types import compile_condition
from engine.card_effects.dsl.loader import load_all_cards
from engine.effect_keywords import TURN_EVENT_MARKER
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

STARFALL = {"event": "graveyard", "qualifier": "instant"}


def _state():
    st = _make_state()
    st.card_db = DB
    return st


def _mk(types, slug="probe", owner=1):
    c = Card(slug=slug, name=slug, types=list(types))
    c.owner = c.controller = owner
    return c


def _starfall(card, st):
    return compile_condition("EVENT_THIS_TURN", STARFALL)(card, None, st)


# --- the recording ---------------------------------------------------------

def test_instant_entering_graveyard_is_recorded():
    st = _state()
    st.players[1].graveyard.add(_mk(["Instant"]))
    assert f"{TURN_EVENT_MARKER}graveyard:instant" in st.players[1].current_turn_effects


def test_non_instant_does_not_record_the_instant_qualifier():
    st = _state()
    st.players[1].graveyard.add(_mk(["Action"]))
    marks = st.players[1].current_turn_effects
    assert f"{TURN_EVENT_MARKER}graveyard" in marks       # the bare event still fires
    assert f"{TURN_EVENT_MARKER}graveyard:instant" not in marks


def test_recorded_against_the_graveyards_owner_only():
    st = _state()
    st.players[1].graveyard.add(_mk(["Instant"]))
    assert f"{TURN_EVENT_MARKER}graveyard:instant" not in st.players[2].current_turn_effects


def test_re_adding_the_same_card_does_not_double_count():
    # Zone.add is called defensively in places; only a real ENTRY may count, or
    # "an instant hit the graveyard" would inflate for count-based checks.
    st = _state()
    card = _mk(["Instant"])
    st.players[1].graveyard.add(card)
    st.players[1].graveyard.add(card)
    marks = st.players[1].current_turn_effects
    assert marks.count(f"{TURN_EVENT_MARKER}graveyard:instant") == 1


def test_other_graveyard_paths_also_record():
    # Not just a direct .add: the destroy keyword routes through the same gate.
    from engine.effect_keywords import destroy
    st = _state()
    card = _mk(["Instant"], slug="doomed")
    st.players[1].permanents.add(card)
    destroy(st, card)
    assert f"{TURN_EVENT_MARKER}graveyard:instant" in st.players[1].current_turn_effects


# --- the condition ---------------------------------------------------------

def test_starfall_false_before_any_instant_hits_the_graveyard():
    st = _state()
    probe = _mk(["Action"], slug="comet_collision_red")
    assert _starfall(probe, st) is False


def test_starfall_false_when_only_a_non_instant_was_binned():
    st = _state()
    st.players[1].graveyard.add(_mk(["Action"]))
    probe = _mk(["Action"], slug="comet_collision_red")
    assert _starfall(probe, st) is False


def test_starfall_true_after_an_instant_hits_the_graveyard():
    st = _state()
    st.players[1].graveyard.add(_mk(["Instant"]))
    probe = _mk(["Action"], slug="comet_collision_red")
    assert _starfall(probe, st) is True


def test_starfall_reads_your_own_graveyard_not_the_opponents():
    st = _state()
    st.players[2].graveyard.add(_mk(["Instant"], owner=2))
    probe = _mk(["Action"], slug="comet_collision_red", owner=1)
    assert _starfall(probe, st) is False


# --- migration guard -------------------------------------------------------

def test_comet_collision_no_longer_reads_an_invented_flag():
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "engine" / "card_effects" / "json"
    path = [p for p in root.rglob("comet_collision_red.json") if ".quarantine" not in p.parts][0]
    abilities = json.dumps(json.loads(path.read_text(encoding="utf-8"))["abilities"])
    assert "STARFALL_FLAG" not in abilities
    assert "EVENT_THIS_TURN" in abilities
    # "instead" must stay a then/else, never two stacked effects (3 + 4 = 7).
    assert '"then"' in abilities and '"else"' in abilities
