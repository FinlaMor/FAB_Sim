"""Clash system — CR 8.5.45 — and the Victor deck's clash cards.

Covers the clash keyword function (winner by power, tie, retry), the CLASH DSL
effect on defending blocks (Test of Strength / Iron Grip / Trounce), the
"win a clash revealing this" triggers (Thunk, Golden Son), Victor's first-Gold
draw, and Victor's fail-clash retry replacement.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card import Card, CardDB
from engine.card_effects.dsl import dispatch, load_all_cards
from engine.effect_keywords import clash
from engine.state import CombatState, Event, GameState, Player, Step

load_all_cards()


def _hero(pid, slug="test_hero"):
    c = Card(slug=slug, name=slug, types=["Hero"], base_life=40, base_intellect=4)
    c.owner = pid
    c.controller = pid
    return c


def _state(active=1, p1_hero="test_hero", p2_hero="test_hero"):
    st = GameState(
        players={1: Player(1, _hero(1, p1_hero)), 2: Player(2, _hero(2, p2_hero))},
        active_player=active,
        player_agents={1: lambda *a, **k: (a[1][0] if a[1] else None),
                       2: lambda *a, **k: (a[1][0] if a[1] else None)},
        step=Step.COMBAT_DEFEND, turn_number=1, combat=None, done=False, winner=None,
    )
    st.card_db = CardDB()
    st.clash_fail_retry = {}
    return st


def _deck_card(slug, owner, power=None):
    c = Card(slug=slug, name=slug, types=["Action"], subtypes=["Attack"])
    c.owner = owner
    c.controller = owner
    if power is not None:
        c.base_power = power
        c.power = power
    return c


def _combat(attacker_id=2):
    ac = Card(slug="incoming", name="Incoming", types=["Action"], subtypes=["Attack"])
    ac.owner = attacker_id
    ac.controller = attacker_id
    return CombatState(attacker_id=attacker_id, link_id=1, attack_power=4,
                       attack_card=ac, keywords=[], from_weapon=False)


# ── clash keyword function ───────────────────────────────────────────────────

def test_clash_higher_power_wins():
    st = _state()
    st.players[1].deck.add(_deck_card("hi", 1, power=6))
    st.players[2].deck.add(_deck_card("lo", 2, power=3))
    ev = clash(st, 1, 2)
    assert ev.winner_id == 1


def test_clash_tie_no_winner():
    st = _state()
    st.players[1].deck.add(_deck_card("a", 1, power=5))
    st.players[2].deck.add(_deck_card("b", 2, power=5))
    ev = clash(st, 1, 2)
    assert ev.winner_id is None


def test_clash_empty_deck_loses():
    st = _state()
    st.players[1].deck.add(_deck_card("a", 1, power=1))
    # player 2 has an empty deck → reveals nothing → loses
    ev = clash(st, 1, 2)
    assert ev.winner_id == 1


# ── Test of Strength: winner creates a Gold ──────────────────────────────────

def test_of_strength_winner_creates_gold():
    st = _state()
    st.combat = _combat(attacker_id=2)
    st.players[1].deck.add(_deck_card("hi", 1, power=8))   # defender (controller)
    st.players[2].deck.add(_deck_card("lo", 2, power=2))   # attacker
    block = _deck_card("test_of_strength_red", 1)
    dispatch(st, "ON_DEFEND", "test_of_strength_red", card=block,
             event=Event(type="ON_DEFEND", data={"card": block}))
    assert st.players[1].permanents.find("gold") is not None


# ── Test of Iron Grip: loser discards ────────────────────────────────────────

def test_of_iron_grip_loser_discards():
    st = _state()
    st.combat = _combat(attacker_id=2)
    st.players[1].deck.add(_deck_card("hi", 1, power=8))
    st.players[2].deck.add(_deck_card("lo", 2, power=2))
    # Give the loser (attacker, player 2) a hand card to discard.
    st.players[2].hand.add(_deck_card("filler", 2))
    before = len(st.players[2].hand.cards)
    block = _deck_card("test_of_iron_grip_red", 1)
    dispatch(st, "ON_DEFEND", "test_of_iron_grip_red", card=block,
             event=Event(type="ON_DEFEND", data={"card": block}))
    assert len(st.players[2].hand.cards) == before - 1


# ── Thunk / Golden Son: win-a-clash-revealing-this ───────────────────────────

def test_thunk_revealed_in_winning_clash_creates_might():
    # The DSL ON_CLASH_WIN_REVEALED ability fires when Thunk is the winner's
    # revealed card (the clash → dispatch wiring is covered by the deck smoke).
    st = _state()
    thunk = _deck_card("thunk_blue", 1, power=6)
    dispatch(st, "ON_CLASH_WIN_REVEALED", "thunk_blue", card=thunk,
             event=Event(type="ON_CLASH_WIN_REVEALED", data={"winner_card": thunk}))
    assert st.players[1].permanents.find("might") is not None


def test_golden_son_revealed_in_winning_clash_creates_gold():
    st = _state()
    gs = _deck_card("the_golden_son_yellow", 1, power=7)
    dispatch(st, "ON_CLASH_WIN_REVEALED", "the_golden_son_yellow", card=gs,
             event=Event(type="ON_CLASH_WIN_REVEALED", data={"winner_card": gs}))
    assert st.players[1].permanents.find("gold") is not None


def test_clash_resolved_bridge_dispatches_to_winner_card():
    # Integration: a real clash where the winner reveals Thunk fires its ability
    # via the engine's clash_resolved → ON_CLASH_WIN_REVEALED bridge.
    import engine.engine as E
    st = _state()
    E._setup_dsl_listeners(st)  # registers the clash_resolved bridge
    thunk = _deck_card("thunk_blue", 1, power=6)
    st.players[1].deck.add(thunk)
    st.players[2].deck.add(_deck_card("lo", 2, power=1))
    ev = clash(st, 1, 2)
    assert ev.winner_id == 1
    assert st.players[1].permanents.find("might") is not None


# ── Victor: first Gold each turn draws a card ────────────────────────────────

def test_victor_first_gold_draws_once_per_turn():
    st = _state(p1_hero="victor_goldmane_high_and_mighty")
    st.players[1].deck.add(_deck_card("d0", 1))
    st.players[1].deck.add(_deck_card("d1", 1))
    hero = st.players[1].hero
    hand0 = len(st.players[1].hand.cards)
    # First gold → draw.
    dispatch(st, "ON_GOLD_CREATED", hero.slug, card=hero,
             event=Event(type="ON_GOLD_CREATED", data={"player_id": 1}))
    assert len(st.players[1].hand.cards) == hand0 + 1
    # Second gold same turn → no draw.
    dispatch(st, "ON_GOLD_CREATED", hero.slug, card=hero,
             event=Event(type="ON_GOLD_CREATED", data={"player_id": 1}))
    assert len(st.players[1].hand.cards) == hand0 + 1


# ── Victor: fail-clash retry replacement ─────────────────────────────────────

def test_victor_fail_clash_retry_destroys_gold_and_reclashes():
    st = _state(p1_hero="victor_goldmane_high_and_mighty")
    st.clash_fail_retry = {1: "fail_clash_retry"}
    # Victor (player 1) controls a Gold.
    from engine.effect_keywords import create_token
    create_token(st, target_player_id=1, token_slug="gold")
    assert st.players[1].permanents.find("gold") is not None
    # Victor would lose: reveals power 2 vs opponent 8. After retry (destroy Gold,
    # bottom a card, re-clash) the deck order changes; assert the Gold is consumed
    # and the retry flag is set.
    st.players[1].deck.add(_deck_card("lo", 1, power=2))
    st.players[1].deck.add(_deck_card("lo2", 1, power=2))
    st.players[2].deck.add(_deck_card("hi", 2, power=8))
    st.players[2].deck.add(_deck_card("hi2", 2, power=8))
    clash(st, 1, 2)
    assert st.players[1].permanents.find("gold") is None  # Gold destroyed
    assert "victor_clash_retry_used" in st.players[1].current_turn_effects
