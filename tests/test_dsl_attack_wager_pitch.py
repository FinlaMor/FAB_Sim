"""Behavioural tests for the ATTACK effect, WAGER effect, and PITCH cost —
the three DSL functions surfaced by the card-implementation pipeline.

ATTACK is verified to build a rules-compliant attack PROXY (an activated-layer
StackEntry whose card is the source), not a combat shortcut.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card import Card, CardDB
from engine.card_effects.dsl.cost_types import compile_cost
from engine.card_effects.dsl.effect_types import compile_effect
from engine.card_effects.dsl.loader import load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()


def _c(slug, **kw):
    c = Card(slug=slug, name=slug, **kw)
    c.owner = c.controller = 1
    return c


# --- ATTACK: builds an attack proxy (CR 1.6.2b / 11.0) --------------------

def test_attack_effect_creates_attack_proxy():
    st = _make_state(); st.card_db = DB
    wpn = _c("test_weapon", types=["Weapon"], power=4)
    fn = compile_effect("ATTACK", {})
    n0 = len(st.stack_entries)
    fn(wpn, None, st)
    assert len(st.stack_entries) == n0 + 1
    entry = st.stack_entries[-1]
    # a proper proxy: activated layer, source is the attacking card
    assert entry.layer_type == "activated"
    assert entry.card is wpn
    assert entry.player_id == 1


def test_attacking_alias_also_supported():
    st = _make_state(); st.card_db = DB
    fn = compile_effect("ATTACKING", {})
    fn(_c("w2", types=["Weapon"], power=2), None, st)
    assert st.stack_entries and st.stack_entries[-1].layer_type == "activated"


# --- WAGER: registers a wager + prize on the current combat (CR 8.5.46) ---

def test_wager_effect_registers_on_combat():
    st = _make_state(); st.card_db = DB
    src = _c("wager_src", types=["Attack"], power=1)
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=1,
                            attack_card=src, keywords=[])
    compile_effect("WAGER", {"prize": "gold"})(src, None, st)
    # Controller and prize, not the whole tuple: entries also carry the source
    # card so a wager whose payoff is not a token ("the winner loses 1{h}") can
    # be dispatched back to the card that made it.
    assert [(w[0], w[1]) for w in st.combat.wagers] == [(1, "gold")]
    assert st.combat.wagers[0][2] is src


# --- PITCH cost: pay by pitching a chosen card (CR 8.5.44) ----------------

def test_pitch_cost_pays_by_pitching_and_gains_resources():
    st = _make_state(); st.card_db = DB
    src = _c("pitcher", types=["Action"])
    red = _c("red_card", types=["Action"], pitch=1)
    st.players[1].hand.add(red)
    check, pay = compile_cost("PITCH", {"amount": 1})
    assert check(src, None, st) is True
    r0 = st.players[1].resources
    pay(src, None, st)
    assert st.players[1].resources == r0 + 1          # pitch value gained
    assert any(c.slug == "red_card" for c in st.players[1].pitch.cards)
    assert red not in st.players[1].hand.cards


def test_pitch_cost_unpayable_with_empty_hand():
    st = _make_state(); st.card_db = DB
    check, _ = compile_cost("PITCH", {"amount": 1})
    assert check(_c("x", types=["Action"]), None, st) is False


def test_pitch_cost_value_filter():
    st = _make_state(); st.card_db = DB
    src = _c("pitcher", types=["Action"])
    st.players[1].hand.add(_c("red_card", types=["Action"], pitch=1))
    check_blue, _ = compile_cost("PITCH", {"amount": 1, "pitch_value": 3})
    assert check_blue(src, None, st) is False          # only a red in hand
    check_red, _ = compile_cost("PITCH", {"amount": 1, "pitch_value": 1})
    assert check_red(src, None, st) is True
