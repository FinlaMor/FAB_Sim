"""Three cards that sent a card to the bottom of the DECK to mean "the arena".

"Put an item from your hand INTO THE ARENA" was authored as PUT_CARDS_BOTTOM on
two of the three cards that say it. That is not a weaker reading of the printed
effect, it is close to its opposite: instead of gaining a permanent you lose a
card off the top of your hand into the deck, and on Urgent Delivery it happened
whether or not you wanted it, because the "you may" was a bare OPT node in front
of a mandatory effect.

metex_red already spells it correctly -- MOVE_MATCHING to_zone "permanents" --
and was fixed in an earlier pass. Its two siblings were not, because that pass
was about a different clause (COUNT_BOOSTS) and never looked at the verb. A
card fixed in isolation is the cheapest place to find the next one: the sweep
below is over the printed phrase, not over what any reviewer flagged.

Crankshaft is the same shape one step along: "put a steam counter on a HYPER
DRIVER you control" had target "self", so the counter went on Crankshaft --
which by then is in the BANISHED zone, having just been banished from boosting.
It also carried a CONTROLS_TOKEN_TYPE gate asking whether a Hyper Driver
existed and then did nothing with the answer.
"""
from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import engine.engine as E
from engine.card import Card, CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

JSON_ROOT = ROOT / "engine" / "card_effects" / "json"


def _state():
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="": o[0]
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    st.individual_turns = 1
    return st


def _src(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _item(slug, pid=1, cost=0):
    # A real item card's TYPE is Action and "Item" is a SUBTYPE (CR 1.3.2 /
    # 2.10.6a). Built with types=["Item"] it is not a deck card at all, and the
    # hand rejects it -- a fixture the zone rules would reroute, which proves
    # nothing about the effect under test.
    c = Card(slug=slug, name=slug, types=["Action"],
             subtypes=["Item", "NonAttack"])
    c.owner = c.controller = pid
    c.cost = cost
    c.raw_cost = cost
    c.classes = ["Mechanologist"]
    c.card_class = "Mechanologist"
    return c


# --- pour_the_mold_blue -----------------------------------------------------

def test_pour_the_mold_puts_the_item_into_the_arena():
    st = _state()
    item = _item("cost_zero_item", cost=0)
    st.players[1].hand.add(item)
    deck_before = len(st.players[1].deck.cards)

    run_ability(get_card("pour_the_mold_blue").abilities[0], _src("pour_the_mold_blue"),
                None, st)

    assert item in st.players[1].permanents.cards, "the item never reached the arena"
    assert len(st.players[1].deck.cards) == deck_before, (
        "a card went into the deck; the text says the arena")


def test_the_steam_counter_lands_on_the_deployed_item_not_the_action():
    st = _state()
    item = _item("cost_zero_item", cost=0)
    st.players[1].hand.add(item)
    st.players[1].current_turn_effects.append("boosted_this_turn")
    src = _src("pour_the_mold_blue")

    run_ability(get_card("pour_the_mold_blue").abilities[0], src, None, st)

    assert (getattr(item, "counters", None) or {}).get("steam", 0) == 1, (
        "'put a steam counter on IT' means the item just deployed")
    assert (getattr(src, "counters", None) or {}).get("steam", 0) == 0, (
        "the counter went on Pour the Mold itself")


def test_no_steam_counter_without_a_boost():
    st = _state()
    item = _item("cost_zero_item", cost=0)
    st.players[1].hand.add(item)

    run_ability(get_card("pour_the_mold_blue").abilities[0],
                _src("pour_the_mold_blue"), None, st)

    assert item in st.players[1].permanents.cards, "the item clause is conditional"
    assert (getattr(item, "counters", None) or {}).get("steam", 0) == 0


# --- urgent_delivery_yellow -------------------------------------------------

def test_urgent_delivery_puts_the_item_into_the_arena():
    st = _state()
    item = _item("cheap_item", cost=0)
    st.players[1].hand.add(item)
    deck_before = len(st.players[1].deck.cards)

    run_ability(get_card("urgent_delivery_yellow").abilities[0],
                _src("urgent_delivery_yellow"), None, st)

    assert item in st.players[1].permanents.cards
    assert len(st.players[1].deck.cards) == deck_before, (
        "it bottomed a card instead of deploying one")


# --- crankshaft_blue --------------------------------------------------------

def test_crankshaft_puts_the_counter_on_the_hyper_driver():
    st = _state()
    driver = Card(slug="hyper_driver", name="Hyper Driver", types=["Action"],
                  subtypes=["Item", "NonAttack"])
    driver.owner = driver.controller = 1
    st.players[1].permanents.add(driver)
    src = _src("crankshaft_blue")
    st.players[1].current_turn_effects.append("boosted_this_turn")

    run_ability(get_card("crankshaft_blue").abilities[0], src, None, st)

    assert (getattr(driver, "counters", None) or {}).get("steam", 0) == 1, (
        "the steam counter never reached the Hyper Driver")
    assert (getattr(src, "counters", None) or {}).get("steam", 0) == 0, (
        "it went on Crankshaft, which has just been banished")


# --- the guard --------------------------------------------------------------

def test_no_card_bottoms_a_card_where_its_text_says_the_arena():
    """Derived from the printed phrase, so it keeps probing as the other 15
    cards saying it are implemented."""
    idx = json.load(open(ROOT / "card_data" / "slug_index.json",
                         encoding="utf-8"))["by_slug"]
    phrase = re.compile(r"from your hand into the arena", re.I)
    bad = []
    for path in JSON_ROOT.rglob("*.json"):
        rel = path.relative_to(JSON_ROOT)
        if (path.stem.endswith("_work_queue")
                or any(p.startswith(".") or p == "needs_review"
                       for p in rel.parts)):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        slug = raw.get("slug")
        if not phrase.search(idx.get(slug, {}).get("functionalText") or ""):
            continue
        if "PUT_CARDS_BOTTOM" in json.dumps(raw.get("abilities")):
            bad.append(slug)
    assert bad == [], (
        f"cards whose text says 'into the arena' that bottom a card: {bad}")
