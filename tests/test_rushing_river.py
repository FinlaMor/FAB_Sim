"""Rushing River — four independently fatal defects in one card.

  1. ability_type ATTACK_REACTION on a Ninja ACTION - Attack card: nothing fired.
  2. "amount": "CHAIN_HIT_COUNT" — an invented string resolving to 0, so the
     draw drew nothing.
  3. REORDER_REF with ref "HAND" — that effect reorders cards ALREADY IN A DECK
     (it filters on `c in deck.cards`), so given hand cards it silently no-opped.
  4. COMBO_CONTAINS, the looser substring variant of the combo check.

Only (2) was visible to the audit, and only after dict-amount detection was
added. The rest are the kind that make a card look implemented while doing
nothing — which is why these tests assert observable state, not structure.
"""
import copy

import pytest

from engine.card import Card, CardDB
from engine.card_effects.dsl import dispatch
from engine.card_effects.dsl.effect_types import _resolve_amount
from engine.card_effects.dsl.loader import load_all_cards
from engine.state import ChainLink, CombatState
from tests.conftest import _make_state
import engine.engine as E

load_all_cards()
DB = CardDB()


def _first_option_agent(state, options, context=""):
    # The default conftest agent returns None, so any effect that ASKS the player
    # silently chooses nothing and the test measures the agent, not the card.
    return options[0] if options else None


# NOTE: cards must enter a zone via Zone.add, never by appending to `.cards`.
# Appending directly leaves `card.zone` unset, so put_object cannot remove the
# card from its old zone and the move half-happens — the card appears in the
# destination while remaining in hand. That is a test-setup bug that reads
# exactly like a broken effect.


def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: _first_option_agent, 2: _first_option_agent}
    for pid in (1, 2):
        for _ in range(20):
            c = Card(slug="dummy_card", name="dummy", types=["Action"])
            c.owner = c.controller = pid
            st.players[pid].deck.cards.append(c)
    return st


def _card(slug, owner=1):
    c = copy.deepcopy(DB.get(slug))
    c.owner = c.controller = owner
    return c


def _link(st, slug, hit=True, pid=1):
    st.chain_links.append(ChainLink(
        chainlink_id=len(st.chain_links) + 1, attacker_id=pid, attack_slug=slug,
        attack_power=3, net_damage=3 if hit else 0, keywords=[], from_weapon=False,
        hit=hit, talents=[], classes=[], subtypes=[]))


def _attack(st, card):
    bp = card.power or 0
    st.combat = CombatState(attacker_id=1, link_id=len(st.chain_links) + 1,
                            attack_power=bp, attack_card=card, keywords=[])
    st.combat.base_attack_power = bp
    dispatch(st, "ON_ATTACK", card.slug, card=card, event=None)
    E._recalculate_attack_power(st)
    return st.combat


# --- the combo gate --------------------------------------------------------

def test_gets_plus_1_after_torrent_of_tempo():
    st = _state()
    _link(st, "torrent_of_tempo_blue")
    card = _card("rushing_river_blue")
    base = card.power or 0
    assert _attack(st, card).attack_power == base + 1


def test_gets_nothing_after_a_different_attack():
    st = _state()
    _link(st, "wounding_blow_red")
    card = _card("rushing_river_blue")
    base = card.power or 0
    assert _attack(st, card).attack_power == base


def test_gets_nothing_as_the_first_attack_of_the_chain():
    st = _state()
    card = _card("rushing_river_blue")
    base = card.power or 0
    assert _attack(st, card).attack_power == base


# --- X = attacks that have hit this combat chain ---------------------------

def test_hit_count_expression_counts_only_hits():
    st = _state()
    _link(st, "a", hit=True)
    _link(st, "b", hit=False)
    _link(st, "c", hit=True)
    card = _card("rushing_river_blue")
    assert _resolve_amount({"type": "COUNT_CHAIN_LINKS", "hit": True}, st, card) == 2


def test_hit_count_is_zero_on_an_empty_chain():
    st = _state()
    card = _card("rushing_river_blue")
    assert _resolve_amount({"type": "COUNT_CHAIN_LINKS", "hit": True}, st, card) == 0


# --- PUT_HAND_CARD_TOP now moves N cards, not exactly one ------------------

def test_put_hand_card_top_moves_the_requested_number():
    from engine.card_effects.dsl.effect_types import compile_effect
    st = _state()
    card = _card("rushing_river_blue")
    for i in range(3):
        c = Card(slug=f"h{i}", name=f"h{i}", types=["Action"])
        c.owner = c.controller = 1
        st.players[1].hand.add(c)
    before_hand = len(st.players[1].hand.cards)
    before_deck = len(st.players[1].deck.cards)
    compile_effect("PUT_HAND_CARD_TOP", {"amount": 2, "optional": False})(card, None, st)
    assert len(st.players[1].hand.cards) == before_hand - 2
    assert len(st.players[1].deck.cards) == before_deck + 2


def test_put_hand_card_top_stops_when_the_hand_runs_out():
    from engine.card_effects.dsl.effect_types import compile_effect
    st = _state()
    card = _card("rushing_river_blue")
    c = Card(slug="only", name="only", types=["Action"])
    c.owner = c.controller = 1
    st.players[1].hand.add(c)
    compile_effect("PUT_HAND_CARD_TOP", {"amount": 5, "optional": False})(card, None, st)
    assert len(st.players[1].hand.cards) == 0


def test_put_hand_card_top_still_defaults_to_one():
    from engine.card_effects.dsl.effect_types import compile_effect
    st = _state()
    card = _card("rushing_river_blue")
    for i in range(3):
        c = Card(slug=f"h{i}", name=f"h{i}", types=["Action"])
        c.owner = c.controller = 1
        st.players[1].hand.add(c)
    before = len(st.players[1].hand.cards)
    compile_effect("PUT_HAND_CARD_TOP", {"optional": False})(card, None, st)
    assert len(st.players[1].hand.cards) == before - 1


# --- migration guard -------------------------------------------------------

def test_no_dead_constructs_remain():
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "engine" / "card_effects" / "json"
    path = [p for p in root.rglob("rushing_river_blue.json") if ".quarantine" not in p.parts][0]
    abilities = json.dumps(json.loads(path.read_text(encoding="utf-8"))["abilities"])
    assert "CHAIN_HIT_COUNT" not in abilities      # invented amount
    assert "REORDER_REF" not in abilities          # no-ops on hand cards
    assert "ATTACK_REACTION" not in abilities      # wrong card type
    assert "COMBO_CONTAINS" not in abilities       # looser substring variant
    assert "LAST_CHAIN_ATTACK" in abilities
    assert "COUNT_CHAIN_LINKS" in abilities
