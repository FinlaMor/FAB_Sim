"""More behavioural cover for ported cards, on the shapes that go wrong quietly.

Three cards, each chosen for a failure mode an audit cannot see:

    disperse_blue   gated on HAVING BEEN CHEERED this turn -- a turn-scoped
                    marker, so the ungated version works perfectly in any test
                    that happens to cheer first.
    dig_in_red      "pay up to {r}{r}{r}, create THAT MANY tokens" -- a dynamic
                    amount. A card that creates a fixed 3 passes any test that
                    pays 3.
    hold_firm       "Activate this ONLY IF you have less {h} than each other
                    hero", and it PRINTS "Go again" while its JSON also grants
                    GO_AGAIN. If both paid, one activation would refund two
                    action points -- the free-permanent-go-again class arriving
                    through adoption rather than authoring.

As in test_ported_card_gates, each negative case was checked by deleting the
gate and confirming the test then fails.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import engine.engine as E
from engine.card import Card, CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()


def _state():
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="": o[0]
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    st.players[1].action_points = 1
    return st


def _src(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _tokens(state, pid, name="toughness"):
    """Tokens the player controls, counted ONCE.

    `auras` is a view over the same objects `permanents` holds -- verified by
    identity, not assumed -- so summing the zones counts every aura token
    twice. That made three correct tokens look like six and reported two
    working cards as broken. Dedupe by identity.
    """
    seen, out = set(), []
    player = state.players[pid]
    for attr in ("permanents", "tokens", "arena", "auras"):
        zone = getattr(player, attr, None)
        if zone is None:
            continue
        for c in list(getattr(zone, "cards", zone) or []):
            if id(c) in seen:
                continue
            seen.add(id(c))
            out.append(c)
    return [c for c in out if name in str(getattr(c, "slug", "")).lower()]


# --- a turn-scoped marker ----------------------------------------------------

def test_disperse_makes_a_token_only_after_being_cheered():
    st = _state()
    st.players[1].current_turn_effects.append("crowd_cheered")
    src = _src("disperse_blue")

    run_ability(get_card("disperse_blue").abilities[0], src, None, st)

    assert _tokens(st, 1), "cheered this turn, so a Toughness token is due"


def test_disperse_makes_nothing_without_the_cheer():
    st = _state()
    src = _src("disperse_blue")

    run_ability(get_card("disperse_blue").abilities[0], src, None, st)

    assert not _tokens(st, 1), (
        "created a token without having been cheered -- the marker is not "
        "gating")


# --- a dynamic amount --------------------------------------------------------

def test_dig_in_creates_as_many_tokens_as_were_paid():
    """"Create THAT MANY" -- a card hard-coding 3 passes only by luck."""
    st = _state()
    st.players[1].resources = 2
    src = _src("dig_in_red")

    run_ability(get_card("dig_in_red").abilities[0], src, None, st)

    made = len(_tokens(st, 1))
    assert made <= 3, f"created {made} tokens for a cap of 3"
    assert made == 2, (
        f"paid 2 resources but created {made} tokens -- the amount is not "
        "reading what was actually paid")


# --- "activate only if", and a keyword that is printed AND granted -----------

def test_hold_firm_creates_three_tokens_when_behind():
    st = _state()
    st.players[1].life = 5
    st.players[2].life = 20
    src = _src("hold_firm")
    st.players[1].permanents.add(src)

    run_ability(get_card("hold_firm").abilities[0], src, None, st)

    assert len(_tokens(st, 1)) == 3, (
        f"expected 3 Toughness tokens, got {len(_tokens(st, 1))}")


def test_hold_firm_does_nothing_when_ahead():
    """"Activate this ONLY IF you have less {h} than each other hero." """
    st = _state()
    st.players[1].life = 20
    st.players[2].life = 5
    src = _src("hold_firm")
    st.players[1].permanents.add(src)

    run_ability(get_card("hold_firm").abilities[0], src, None, st)

    assert not _tokens(st, 1), (
        "activated while AHEAD on life -- 'only if' is not being enforced")


def test_hold_firm_gives_exactly_one_action_point():
    """It PRINTS "Go again" and its JSON also grants GO_AGAIN. Two payments for
    one activation is the free-go-again class, arriving through adoption."""
    st = _state()
    st.players[1].life = 5
    st.players[2].life = 20
    src = _src("hold_firm")
    st.players[1].permanents.add(src)

    run_ability(get_card("hold_firm").abilities[0], src, None, st)

    assert st.players[1].action_points == 2, (
        f"activation costs 1 and refunds 1, so 2; got "
        f"{st.players[1].action_points}")


# --- premise ----------------------------------------------------------------

def test_the_printed_text_still_says_what_these_assert():
    idx = json.loads((ROOT / "card_data" / "slug_index.json")
                     .read_text(encoding="utf-8"))["by_slug"]
    assert "cheered this turn" in (
        idx["disperse_blue"].get("functionalText") or "").lower()
    assert "pay up to" in (
        idx["dig_in_red"].get("functionalText") or "").lower()
    assert "only if you have less" in (
        idx["hold_firm"].get("functionalText") or "").lower()
