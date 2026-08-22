"""-1{d} counters were bookkeeping: applied, recorded, and never subtracted.

Two independent halves of the engine put -1{d} counters on cards and neither
one reduced any card's {d} for longer than a single call.

The KEYWORD half (Battleworn, Temper, Guardwell — all three are defined in the
CR *in terms of* -1{d} counters) wrote the tally onto the PLAYER under
(slug, zone, "minus_defense") and mutated card.defense once. But
_recalculate_total_defense resets every defender to card.base_defense, the
PRINTED value, before re-deriving the one-shot mods — so the counter was erased
the next time that equipment defended, and every time after. Battleworn is a
downside keyword that cost the player nothing.

The DSL half (PUT_COUNTER with counter "-1d") wrote card.counters and stopped
there; nothing anywhere read it.

The fix makes the CARD's tally authoritative — per object, so two copies of the
same equipment wear their counters independently — and re-applies it inside the
reset, which is what makes a permanent modification permanent.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.ability_keywords import (
    _apply_defense_counter, battleworn, defense_counters, guardwell, temper)
from engine.card_effects.dsl.effect_types import compile_effect
from engine.card_effects.dsl.loader import load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

# 1{d} head equipment, so one counter takes it to exactly zero.
EQUIP = "arcanite_skullcap"


def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    return st


def _equip(st, pid=1, slug=EQUIP):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    st.players[pid].head.cards = [c]
    return c


def _defend_with(st, card, attacker_id=2):
    """Run the defence recalculation the damage step runs."""
    st.combat = CombatState(attacker_id=attacker_id, link_id=1, attack_power=0,
                            attack_card=None, keywords=[])
    st.combat.defending_cards = [card]
    return E._recalculate_total_defense(st)


def test_a_counter_survives_the_next_combat():
    """The reset restored the printed {d}; the counter is not a one-shot mod."""
    st = _state()
    gear = _equip(st)
    printed = gear.base_defense
    assert printed == 1

    _apply_defense_counter(gear, st, 1)
    assert gear.defense == 0

    total = _defend_with(st, gear)

    assert gear.defense == 0, (
        f"the -1{{d}} counter was erased: {gear.slug} is back to {gear.defense}{{d}}")
    assert total == 0, f"it still contributed {total} to the defending total"


def test_the_counter_survives_repeated_combats():
    st = _state()
    gear = _equip(st)
    _apply_defense_counter(gear, st, 1)

    for _ in range(3):
        _defend_with(st, gear)

    assert gear.defense == 0


def test_the_printed_value_is_not_rewritten():
    """base_defense is what the reset restores TO, so nothing may edit it —
    a counter that decremented it would be double-counted by the reset."""
    st = _state()
    gear = _equip(st)
    _apply_defense_counter(gear, st, 1)
    _defend_with(st, gear)

    assert gear.base_defense == 1, (
        "the printed {d} was rewritten; the counter is now counted twice")


def test_battleworn_actually_wears_the_equipment_down():
    st = _state()
    gear = _equip(st)
    battleworn(gear, None, st)
    _defend_with(st, gear)

    assert gear.defense == 0, "Battleworn cost this equipment nothing"


def test_guardwell_takes_the_equipment_to_zero_and_it_stays():
    st = _state()
    gear = _equip(st, slug="arcanite_skullcap")
    guardwell(gear, None, st)
    _defend_with(st, gear)

    assert gear.defense == 0


def test_counters_are_per_object_not_per_slug_and_zone():
    """Two copies of the same equipment wear their counters independently. The
    player-level tally is keyed by (slug, zone) and cannot express that."""
    st = _state()
    worn = _equip(st)
    fresh = copy.deepcopy(DB.get(EQUIP))
    fresh.owner = fresh.controller = 1
    fresh.zone = worn.zone

    _apply_defense_counter(worn, st, 1)

    assert defense_counters(worn) == 1
    assert defense_counters(fresh) == 0, (
        "counters on one copy were shared with the other")
    assert _defend_with(st, fresh) == 1, "the untouched copy defended for less"


def test_the_dsl_counter_reaches_the_same_place_as_the_keyword_one():
    """PUT_COUNTER "-1d" recorded a counter that nothing subtracted."""
    st = _state()
    gear = _equip(st)
    source = copy.deepcopy(DB.get("art_of_the_dragon_scale_red"))
    source.owner = source.controller = 2

    compile_effect("PUT_COUNTER", {
        "counter": "-1d", "amount": 1,
        "target": {"controller": "OPPONENT", "zone": "EQUIPMENT", "amount": 1},
    })(source, None, st)

    assert gear.defense == 0, "the DSL's -1{d} counter did not reduce {d}"
    assert _defend_with(st, gear) == 0
