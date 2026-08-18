"""Scrap (CR 8.3.32) — an optional additional cost that nothing implemented.

"As an additional cost to play this, you MAY banish an item or equipment from
your graveyard." Paying it means the player has scrapped and that card was
scrapped (8.3.32a); a player cannot scrap if they cannot pay (8.3.32b).

24 cards in the corpus carry the keyword. None had the cost at all — each just
read an invented flag (SCRAPPED_CARD, SCRAPPED_HYPER_DRIVER), so both halves
were missing: the cost was never charged and the payoff could never fire.

The condition is keyed to the ASKING card's slug because the text says "if IT
scrapped a card", not "if you scrapped" — a bare player-level flag would also
fire for a different scrap card played earlier in the turn.
"""
import copy

import pytest

from engine.card import Card, CardDB
from engine.card_effects.dsl.condition_types import compile_condition
from engine.card_effects.dsl.cost_types import compile_cost
from engine.card_effects.dsl.loader import load_all_cards
from engine.effect_keywords import TURN_EVENT_MARKER
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()


def _yes_agent(state, options, context=""):
    return options[0]


def _no_agent(state, options, context=""):
    # "no" / "decline" are always offered last, so a refusing agent takes the end.
    return options[-1]


def _state(agent=_yes_agent):
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: agent, 2: agent}
    return st


def _card(slug, owner=1):
    base = DB.get(slug)
    assert base is not None, f"unknown slug {slug}"
    c = copy.deepcopy(base)
    c.owner = c.controller = owner
    return c


def _bin(st, slug="an_item", types=("Item",), name=None, pid=1):
    c = Card(slug=slug, name=name or slug, types=list(types))
    c.owner = c.controller = pid
    st.players[pid].graveyard.add(c)
    return c


def _pay_scrap(st, card):
    can_pay, pay = compile_cost("SCRAP", {})
    assert can_pay(card, None, st) is True, "scrap is optional and must never block play"
    pay(card, None, st)


# --- the cost --------------------------------------------------------------

def test_scrap_banishes_an_item_from_the_graveyard():
    st = _state()
    card = _card("scrap_prospector_blue")
    item = _bin(st)
    _pay_scrap(st, card)
    assert item not in st.players[1].graveyard.cards
    assert item in st.players[1].banished.cards


def test_scrap_is_optional_and_never_blocks_play():
    # 8.3.32 is a MAY, so can_pay must be true even with an empty graveyard —
    # a mandatory additional cost would gate legality instead.
    st = _state()
    card = _card("scrap_prospector_blue")
    can_pay, _ = compile_cost("SCRAP", {})
    assert st.players[1].graveyard.cards == []
    assert can_pay(card, None, st) is True


def test_declining_scraps_nothing():
    st = _state(agent=_no_agent)
    card = _card("scrap_prospector_blue")
    item = _bin(st)
    _pay_scrap(st, card)
    assert item in st.players[1].graveyard.cards, "declined but the card was banished anyway"
    assert not compile_condition("SCRAPPED", {})(card, None, st)


def test_cannot_scrap_a_non_item_non_equipment():
    # 8.3.32b — only an item or equipment is a legal scrap target.
    st = _state()
    card = _card("scrap_prospector_blue")
    action = _bin(st, slug="just_an_action", types=("Action",))
    _pay_scrap(st, card)
    assert action in st.players[1].graveyard.cards
    assert not compile_condition("SCRAPPED", {})(card, None, st)


def test_equipment_is_a_legal_scrap_target():
    st = _state()
    card = _card("scrap_prospector_blue")
    equip = _bin(st, slug="some_equipment", types=("Equipment",))
    _pay_scrap(st, card)
    assert equip in st.players[1].banished.cards


# --- the condition ---------------------------------------------------------

def test_scrapped_is_false_before_paying():
    st = _state()
    card = _card("scrap_prospector_blue")
    assert compile_condition("SCRAPPED", {})(card, None, st) is False


def test_scrapped_is_true_for_the_card_that_paid():
    st = _state()
    card = _card("scrap_prospector_blue")
    _bin(st)
    _pay_scrap(st, card)
    assert compile_condition("SCRAPPED", {})(card, None, st) is True


def test_scrapped_is_keyed_to_the_asking_card_not_the_player():
    # "if IT scrapped a card". A different scrap card played earlier in the turn
    # must NOT satisfy this one — a player-level flag would wrongly do so.
    st = _state()
    payer = _card("scrap_prospector_blue")
    other = _card("scrap_compactor_blue")
    _bin(st)
    _pay_scrap(st, payer)
    assert compile_condition("SCRAPPED", {})(payer, None, st) is True
    assert compile_condition("SCRAPPED", {})(other, None, st) is False


def test_scrapped_by_name_checks_what_was_scrapped():
    # speed_demon_red: "if it scrapped a HYPER DRIVER" asks about the BANISHED
    # card's identity, not the asking card's.
    st = _state()
    card = _card("speed_demon_red")
    _bin(st, slug="hyper_driver", types=("Item",), name="Hyper Driver")
    _pay_scrap(st, card)
    assert compile_condition("SCRAPPED", {"name": "Hyper Driver"})(card, None, st) is True


def test_scrapped_by_name_is_false_for_a_different_card():
    st = _state()
    card = _card("speed_demon_red")
    _bin(st, slug="some_other_item", types=("Item",), name="Some Other Item")
    _pay_scrap(st, card)
    assert compile_condition("SCRAPPED", {"name": "Hyper Driver"})(card, None, st) is False


# --- migration guard -------------------------------------------------------

@pytest.mark.parametrize("slug", [
    "scrap_prospector_blue", "scrap_compactor_blue", "speed_demon_red",
])
def test_scrap_cards_have_the_cost_and_no_invented_flag(slug):
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "engine" / "card_effects" / "json"
    path = [p for p in root.rglob(f"{slug}.json") if ".quarantine" not in p.parts][0]
    data = json.loads(path.read_text(encoding="utf-8"))
    # The cost lives at CARD level (a play-time additional cost), not inside an
    # ability: an ability existing only to carry a cost has no effects, which the
    # hygiene rule correctly rejects as a no-op.
    assert (data.get("cost") or {}).get("type") == "SCRAP",         f"{slug} carries the keyword but never charges the cost"
    abilities = json.dumps(data["abilities"])
    assert "SCRAPPED_CARD" not in abilities
    assert "SCRAPPED_HYPER_DRIVER" not in abilities
