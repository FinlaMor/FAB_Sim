""""Destroy a Gold you control" could not be paid with a Gold in play.

`_permanent_filter` is shared by the DESTROY_PERMANENT cost and the effect of
the same name, and its `target` parameter carries two different KINDS of value:

    "self"              a DIRECTIVE -- which object, not which kind
    "item"              a FILTER -- what qualifies
    "chosen"            a directive: the player picks
    "controlled_item"   both: the prefix is the directive, "item" is the filter

Only the first two were understood. "chosen" was matched as a subtype, and no
card has the subtype "chosen", so the filter was false for every permanent --
9 cards. "controlled_item" was matched whole, likewise false -- 2 more.

As an EFFECT that means destroying nothing. As a COST it is worse: `can_pay`
returns False, so Good Time Chapeau's ability could not be activated at all
while its controller held a Gold. A filter that fails closed looks exactly like
a card whose condition was not met.

Found by the corpus review, which reported the right symptom on
good_time_chapeau and the wrong cause -- it blamed Gold being routed to
`player.items` instead of `permanents`. `items` is a SubZoneView over
`permanents` and holds the same objects, so that was never it. The finding was
still worth chasing: the symptom was real and worse than reported.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.ability_keywords import create_token
from engine.card_effects.dsl.cost_types import compile_cost
from engine.card_effects.dsl.effect_types import _permanent_filter
from engine.card_effects.dsl.loader import load_all_cards
from tests.conftest import _make_state
from tests.conftest import _card_json

load_all_cards()
DB = CardDB()


def _state(tokens=()):
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    for t in tokens:
        create_token(st, 1, t)
    return st


# --- the directives are not filters ----------------------------------------

@pytest.mark.parametrize("directive", ["self", "chosen", "choice", "any"])
def test_a_directive_does_not_filter_anything_out(directive):
    st = _state(["gold"])
    gold = st.players[1].permanents.cards[0]
    fn = _permanent_filter({"target": directive})

    assert fn is None or fn(gold, st), (
        f"target={directive!r} is a targeting directive, not a card property, "
        "and matched nothing")


def test_a_type_name_in_target_still_filters():
    """The other kind of value must keep working: two cards say
    target: "item" and mean it."""
    st = _state(["gold", "runechant"])
    gold, rune = st.players[1].permanents.cards[:2]
    fn = _permanent_filter({"target": "item"})

    assert fn(gold, st) and not fn(rune, st)


def test_controlled_prefix_keeps_the_filter_half():
    """"controlled_item" is "an item you control" -- read whole it named a
    subtype no card has."""
    st = _state(["gold", "runechant"])
    gold, rune = st.players[1].permanents.cards[:2]
    fn = _permanent_filter({"target": "controlled_item"})

    assert fn(gold, st), "an item you control did not match an item"
    assert not fn(rune, st), "it matched an aura"


def test_a_directive_does_not_erase_a_real_filter():
    """target: "chosen" alongside slug: "gold" must still be gold-only."""
    st = _state(["gold", "runechant"])
    gold, rune = st.players[1].permanents.cards[:2]
    fn = _permanent_filter({"target": "chosen", "slug": "gold"})

    assert fn(gold, st) and not fn(rune, st)


# --- the card ---------------------------------------------------------------

def _chapeau_cost():
    path = _card_json(ROOT / "engine" / "card_effects" / "json",
                      "good_time_chapeau.json")
    spec = json.loads(path.read_text(encoding="utf-8"))["abilities"][0]["cost"][0]
    return compile_cost("DESTROY_PERMANENT",
                        {k: v for k, v in spec.items() if k != "type"})


def _src():
    c = copy.deepcopy(DB.get("good_time_chapeau"))
    c.owner = c.controller = 1
    return c


def test_the_cost_is_payable_with_a_gold():
    st = _state(["gold"])
    can_pay, pay = _chapeau_cost()

    assert can_pay(_src(), None, st), (
        "'Destroy a Gold you control' was unpayable with a Gold in play, so "
        "the ability could never be activated")

    pay(_src(), None, st)
    assert not [c for c in st.players[1].permanents.cards if c.slug == "gold"], (
        "the cost reported payable and destroyed no Gold")


def test_the_cost_still_blocks_without_a_gold():
    """Costs must block play legality -- a fix that made this payable with no
    Gold would be worse than the bug."""
    st = _state(["runechant"])
    can_pay, _ = _chapeau_cost()

    assert not can_pay(_src(), None, st)
