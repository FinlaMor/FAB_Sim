"""A token created "under another hero's control" went to its own controller.

CREATE_TOKEN defaults `player` to the ability's controller, which is right for
the common case and silently wrong for the cards that name someone else. It
fails the way this whole class fails: a token IS created, so nothing errors and
nothing looks empty -- it just belongs to the wrong player.

Civic Duty is the clearest instance, because the release notes rule out the
behaviour the default produced in as many words:

    "You may not choose yourself to create the Vigor token for."

The sweep that finds these is scripts/grade_drafts.py's "token wrong
controller", which asks what the printed TEXT says rather than only what the
JSON omits -- there is nothing wrong with an untargeted CREATE_TOKEN on a card
that means its own controller, which is most of them.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from tests.conftest import _card_json, _make_state

load_all_cards()
DB = CardDB()


def _state():
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="": o[0]
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    return st


def _tokens(state, pid):
    """Every token object the player controls, wherever the engine filed it."""
    out = []
    player = state.players[pid]
    for attr in ("permanents", "tokens", "arena", "auras"):
        zone = getattr(player, attr, None)
        if zone is None:
            continue
        out.extend(list(getattr(zone, "cards", zone) or []))
    return out


def _vigor(state, pid):
    return [c for c in _tokens(state, pid)
            if "vigor" in str(getattr(c, "slug", "")).lower()]


def test_civic_duty_gives_the_vigor_to_the_other_hero():
    st = _state()
    src = copy.deepcopy(DB.get("civic_duty"))
    src.owner = src.controller = 1
    st.players[1].permanents.add(src)

    run_ability(get_card("civic_duty").abilities[0], src, None, st)

    assert _vigor(st, 2), "the other hero got no Vigor token"


def test_civic_duty_does_not_give_it_to_itself():
    """The release note, as a test: "You may not choose yourself to create the
    Vigor token for." """
    st = _state()
    src = copy.deepcopy(DB.get("civic_duty"))
    src.owner = src.controller = 1
    st.players[1].permanents.add(src)

    run_ability(get_card("civic_duty").abilities[0], src, None, st)

    assert not _vigor(st, 1), (
        "the controller created the Vigor for themselves, which the release "
        "notes forbid outright")


def test_the_card_still_names_another_hero():
    """The premise. If the printed text ever changes, this should fail loudly
    rather than keep asserting a routing the card no longer asks for."""
    idx = json.load(open(ROOT / "card_data" / "slug_index.json",
                         encoding="utf-8"))["by_slug"]
    text = (idx["civic_duty"].get("functionalText") or "").lower()
    assert "under another hero's control" in text, text


def test_the_json_says_who():
    raw = json.loads(_card_json(ROOT / "engine" / "card_effects" / "json",
                                "civic_duty.json").read_text(encoding="utf-8"))
    node = raw["abilities"][0]["effects"][0]
    assert node["type"] == "CREATE_TOKEN"
    assert node.get("player") == "OPPONENT", node
