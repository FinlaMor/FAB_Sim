""""Then if IT has 0{d}" needs to know what "it" was.

art_of_the_dragon_scale_red is three clauses and all three acted on the wrong
object:

  - "put a -1{d} counter on an equipment they control" named its target and the
    compiler read none of it, so the debuff aimed at the DEFENDER landed on the
    attacking card;
  - "then if it has 0{d}" was authored as COUNTER_GTE amount 0 against the
    source, which is true for every card at all times;
  - "destroy it" was DESTROY_REF with a 'target' it does not read and no ref at
    all, so it fired unconditionally on whatever ref happened to be set.

The fix is one primitive, not three: PUT_COUNTER records the object it counted
under the ref "countered", which is what both the test and the destroy read.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

SOURCE = "art_of_the_dragon_scale_red"


def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    return st


def _card(slug, pid):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _hit_effects():
    """The ON_HIT trigger the ON_ATTACK ability injects, as an ability to run."""
    ability = get_card(SOURCE).abilities[0]
    spec = ability.effects[0].params["trigger"]
    return spec


def _run_hit(st, source):
    """The trigger's effects under a reference scope, which is what makes the
    "countered" ref visible to the effects that follow it — real dispatch
    pushes one per ability."""
    from engine.card_effects.dsl.effect_types import compile_effect
    from engine.context import pop_refs, push_refs
    push_refs()
    try:
        for eff in _hit_effects()["effects"]:
            compile_effect(eff["type"], eff)(source, None, st)
    finally:
        pop_refs()


def test_the_counter_goes_on_their_equipment_not_the_attacker():
    st = _state()
    source = _card(SOURCE, 1)
    # 2{d}, so it SURVIVES the counter — a 1{d} equipment is destroyed by the
    # follow-up clause, and destruction resets the card, wiping the very
    # counter this test is about.
    gear = _card("balance_of_justice", 2)
    st.players[2].head.add(gear)   # add() stamps card.zone; assigning .cards does not

    _run_hit(st, source)

    from engine.card_effects.ability_keywords import defense_counters
    assert defense_counters(gear) == 1, "their equipment took no counter"
    assert defense_counters(source) == 0, (
        "the -1{d} counter landed on the attacking card")


def test_a_one_defense_equipment_is_destroyed():
    """1{d} minus one counter is 0{d}, which is what the card destroys."""
    st = _state()
    source = _card(SOURCE, 1)
    gear = _card("arcanite_skullcap", 2)
    assert gear.base_defense == 1
    st.players[2].head.add(gear)   # add() stamps card.zone; assigning .cards does not

    _run_hit(st, source)

    assert gear not in st.players[2].head.cards, (
        "an equipment reduced to 0{d} was not destroyed")


def test_a_tougher_equipment_survives():
    """The clause is conditional, and the condition it had was always true."""
    st = _state()
    source = _card(SOURCE, 1)
    tough = _card("balance_of_justice", 2)
    assert tough.base_defense == 2, tough.base_defense
    st.players[2].head.add(tough)

    _run_hit(st, source)

    assert tough in st.players[2].head.cards, (
        "a 2{d} equipment with one -1{d} counter was destroyed anyway")
    assert tough.defense == tough.base_defense - 1, (
        f"it should be at {tough.base_defense - 1}{{d}}, not {tough.defense}")


def test_nothing_happens_with_no_equipment_to_counter():
    st = _state()
    source = _card(SOURCE, 1)
    st.players[2].head.cards = []

    _run_hit(st, source)   # must not raise

    from engine.card_effects.ability_keywords import defense_counters
    assert defense_counters(source) == 0
