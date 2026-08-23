""""Your next attack WITH IT costs {r} less" needs to name an object.

The queued one-shot cost reduction matches on card PROPERTIES - "the next blue
card", "the next Runeblade card" - which cannot distinguish one sword from an
identical one. sharp_incline_red's second sentence is about the SAME object its
first sentence sharpened, so it had no way to be written and was left out.

Three pieces close it:
  - SHARPEN records the sword it sharpened under the ref "sharpened";
  - MODIFY_NEXT_CARD_COST takes `object_ref` and pins its queue entry to that
    object's object_id;
  - _cost_mod_matches honours object_id.

The gate needed a new condition as well: "if IT has 1 or more +1{p} counters"
is about the SWORD, and HAS_COUNTER reads the SOURCE card - here the action
card, which never carries power counters - so the gate would have been false
whatever the sword looked like.
"""
import copy

import pytest

import engine.engine as E
from engine.actions import Action, ActionType
from engine.card import CardDB
from engine.card_effects.dsl.condition_types import compile_condition
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.play import _calculate_resource_cost, _cost_mod_matches
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

SOURCE = "sharp_incline_red"


def _card(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _sword(pid=1):
    """A Sword weapon with a resource activation cost, so a reduction shows."""
    import json
    idx = json.load(open("card_data/slug_index.json", encoding="utf-8"))["by_slug"]
    for slug, e in idx.items():
        if ("Sword" in (e.get("subtypes") or [])
                and "Weapon" in (e.get("types") or [])):
            c = DB.get(slug)
            if c is not None and (c.activation_cost or 0) >= 1:
                got = copy.deepcopy(c)
                got.owner = got.controller = pid
                return got
    pytest.skip("no Sword weapon with a resource activation cost in the DB")


def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    st.individual_turns = 1
    return st


def _equip(st, sword, pid=1):
    st.players[pid].weapon1.add(sword)
    return sword


def _activate_cost(st, card, pid=1):
    action = Action(type=ActionType.ACTIVATE_CARD, player_id=pid, card=card)
    return _calculate_resource_cost(st, action)


# --- the pieces -------------------------------------------------------------

def test_sharpen_records_which_sword_it_sharpened():
    """run_ability pushes its OWN reference scope and pops it, so the ref is
    gone by the time the caller could read it - that is the point of the scope.
    The effect is therefore compiled and run inside one scope here."""
    from engine.card_effects.dsl.effect_types import compile_effect
    from engine.context import get_ref, pop_refs, push_refs

    st = _state()
    sword = _equip(st, _sword())
    push_refs()
    try:
        compile_effect("SHARPEN", {"subtype": "Sword", "amount": 1})(
            _card(SOURCE), None, st)
        assert get_ref("sharpened") is sword, (
            "SHARPEN did not record which sword it sharpened")
        assert sword.counters.get("power") == 1
    finally:
        pop_refs()


def test_the_gate_reads_the_sword_not_the_action_card():
    st = _state()
    sword = _equip(st, _sword())
    source = _card(SOURCE)
    from engine.context import pop_refs, push_refs, set_ref

    fn = compile_condition("REF_HAS_COUNTER",
                           {"ref": "sharpened", "counter": "power", "amount": 1})
    push_refs()
    try:
        set_ref("sharpened", sword)
        assert fn(source, None, st) is False, "an unsharpened sword passed"
        sword.counters["power"] = 1
        assert fn(source, None, st) is True
        # The source card never carries power counters, which is why reading it
        # made the gate unconditionally false.
        old = compile_condition("HAS_COUNTER", {"counter": "power"})
        assert old(source, None, st) is False
    finally:
        pop_refs()


def test_a_pinned_mod_does_not_match_another_copy_of_the_same_card():
    st = _state()
    a, b = _sword(), _sword()
    assert a.slug == b.slug and a.object_id != b.object_id
    mod = {"object_id": a.object_id, "amount": 1, "filter": []}

    assert _cost_mod_matches(st, mod, a) is True
    assert _cost_mod_matches(st, mod, b) is False, (
        "a second copy of the same sword consumed a reduction meant for the first")


# --- the card ---------------------------------------------------------------

def test_the_sharpened_sword_costs_one_less_to_activate():
    st = _state()
    sword = _equip(st, _sword())
    full = _activate_cost(st, sword)

    run_ability(get_card(SOURCE).abilities[0], _card(SOURCE), None, st)

    assert _activate_cost(st, sword) == full - 1, (
        f"activation still costs {_activate_cost(st, sword)}, expected {full - 1}")


def test_a_different_sword_is_unaffected():
    st = _state()
    sharpened = _equip(st, _sword())
    other = _sword()
    st.players[1].weapon2.add(other)
    other_full = _activate_cost(st, other)

    run_ability(get_card(SOURCE).abilities[0], _card(SOURCE), None, st)

    assert _activate_cost(st, other) == other_full, (
        "the reduction applied to a sword this card never sharpened")
    assert _activate_cost(st, sharpened) == other_full - 1


def test_it_does_nothing_with_no_sword_to_sharpen():
    st = _state()
    before = list(getattr(st.players[1], "dsl_queued_card_mods", None) or [])

    run_ability(get_card(SOURCE).abilities[0], _card(SOURCE), None, st)

    after = list(getattr(st.players[1], "dsl_queued_card_mods", None) or [])
    assert after == before, (
        "it queued an UNPINNED reduction with no sword to pin it to, which "
        "would have applied to whatever came next")
