"""Smashing Performance — "discarded this way" and a random arena target.

    "When this attacks draw a card, then discard a random card. If a card with
     6 or more {p} is discarded this way, destroy a random item in the arena."

It sat on test_invented_refs.py's KNOWN_UNFIXED with the diagnosis "destroy a
RANDOM item in the arena -- object targets prompt, never roll". Two separate
things were wrong:

  * DESTROY_REF read ref "ITEM", a name nothing sets, so the destroy was a
    silent no-op.
  * DISCARDED_CARD_POWER_GTE could not see the discard. It consulted the EVENT
    (an on-discard trigger, where the discarded card is the event) and
    `discarded_for_this` (a discard paid as an additional COST), but not the
    "discarded" ref an effect-discard sets. So "discarded THIS WAY" was dead on
    every card whose discard is an EFFECT rather than a cost -- a class, not
    just this card.

The item is PICKED, not prompted: prompting would hand the controller a choice
the card explicitly denies them.

TWO SETUP TRAPS, both hit while writing this file.

Items must be added through `player.items`, not `player.permanents`.
SubZoneView.add() stamps `permanent_subtype`, and a card placed straight into
the parent zone is invisible to the items view -- a probe built that way reports
0 items and every assertion here passes for the wrong reason.
test_the_setup_is_real guards that.

THE DISCARD IS GENUINELY RANDOM, and the DRAW HAPPENS FIRST. Seeding the hand
with one card of the power you want is not enough: the draw adds a second card,
and the discard then picks between them. A first version of this file did that
and passed about half the time -- which is worse than no test, because it looked
like a regression when an unrelated change landed. Both the hand AND the deck
are stocked with the same power class here, so whichever card the discard picks,
the gate sees the intended answer.
"""
import copy
import io
import json
from pathlib import Path

import pytest

from engine.card import CardDB
from engine.card_effects.dsl.loader import load_all_cards
from engine.state import CombatState, Step
from scripts.talishar_attack_replay import _announce_attack, _replay_agent
from tests.conftest import _make_state
import engine.engine as E

load_all_cards()
DB = CardDB()

CARD = "smashing_performance_yellow"
ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def fodder():
    si = json.load(io.open(ROOT / "card_data" / "slug_index.json",
                           encoding="utf-8"))["by_slug"]
    big = next(s for s, e in si.items() if (e.get("power") or 0) >= 6 and DB.get(s))
    small = next(s for s, e in si.items()
                 if (e.get("power") or 0) in (1, 2)
                 and "Attack" in (e.get("subtypes") or []) and DB.get(s))
    item = next(s for s, e in si.items()
                if "Item" in (e.get("subtypes") or []) and DB.get(s))
    return big, small, item


def _run(hand_slug, item_slug, filler, items_for=(1, 2)):
    st = _make_state()
    st.card_db = DB
    st.step = Step.ACTION
    st.active_player = 1
    st.combat = None
    st.player_agents = {1: _replay_agent, 2: _replay_agent}
    E._setup_dsl_listeners(st)
    for pid in items_for:
        c = copy.deepcopy(DB.get(item_slug))
        c.owner = c.controller = pid
        st.players[pid].items.add(c)      # through the VIEW -- see module docstring
    # The draw resolves BEFORE the discard, so the deck card ends up in hand and
    # is an equally likely discard. Stock both with the same power class so the
    # random pick cannot change the answer.
    if hand_slug:
        h = copy.deepcopy(DB.get(hand_slug))
        h.owner = h.controller = 1
        st.players[1].hand.add(h)
    d = copy.deepcopy(DB.get(filler))
    d.owner = d.controller = 1
    st.players[1].deck.add(d)

    before = sum(len(st.players[p].items.cards) for p in (1, 2))
    card = copy.deepcopy(DB.get(CARD))
    card.owner = card.controller = 1
    power = card.raw_power or 0
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=power,
                            attack_card=card, keywords=[])
    st.combat.base_attack_power = power
    E._apply_turn_attack_effects(st, card)
    E._register_card_continuous_effects(st, card)
    _announce_attack(st, card)
    E._recalculate_attack_power(st)
    after = sum(len(st.players[p].items.cards) for p in (1, 2))
    return st, before, after


def test_the_setup_is_real(fodder):
    """Guard for every other test here. An item added to `permanents` instead of
    through `items` is invisible to the view, and then "no item was destroyed"
    is indistinguishable from "there was never an item"."""
    _big, small, item = fodder
    st, before, _after = _run(None, item, small)
    assert before == 2, "two items must actually be in the arena"


def test_a_big_discard_destroys_an_item(fodder):
    big, _small, item = fodder
    _st, before, after = _run(big, item, big)   # deck card is big too
    assert (before, after) == (2, 1)


def test_a_small_discard_destroys_nothing(fodder):
    """The gate is real: 'if a card with 6 or more {p} is discarded this way'."""
    _big, small, item = fodder
    _st, before, after = _run(small, item, small)
    assert (before, after) == (2, 2)


def test_it_draws_and_discards_regardless_of_the_gate(fodder):
    """The draw and the discard are unconditional -- only the destroy is gated.
    Hand starts with 1, draws 1, discards 1 at random, so it ends at 1."""
    _big, small, item = fodder
    st, _b, _a = _run(small, item, small)
    assert len(st.players[1].hand.cards) == 1
    assert len(st.players[1].graveyard.cards) >= 1, "something was discarded"


def test_it_can_destroy_an_item_the_opponent_controls(fodder):
    """"in the arena" is the shared play area, not your own items."""
    big, _small, item = fodder
    _st, before, after = _run(big, item, big, items_for=(2,))
    assert (before, after) == (1, 0)
