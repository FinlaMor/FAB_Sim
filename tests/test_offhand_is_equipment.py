"""An off-hand is equipment, but it is not in the equipment zone.

Reinforce Steel: "Remove a -1{d} counter from a GUARDIAN OFF-HAND you control
with 2 or less base {d}." Two independent reasons it could never find one:

  the zone    the target searched zone EQUIPMENT, which resolved to the four
              body slots (head/chest/arms/legs). CR 3.16.2a equips an off-hand
              to a WEAPON zone, so the pool never contained one.
  the filter  "off-hand" was authored as HAS_KEYWORD. CR 2.10.6a lists Off-Hand
              among the functional SUBTYPES; HAS_KEYWORD reads card.keywords,
              which is populated only from the DB keywords field, so it matched
              nothing.

Either alone makes the card a no-op, which is why fixing one would have proved
nothing. Weapons stay out of the equipment pool: Weapon is a TYPE of its own,
and "equipment you control" does not mean the sword.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import engine.engine as E
from engine.card import Card, CardDB
from engine.card_effects.dsl.effect_types import _object_zone_cards
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()


def _state():
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="": o[0]
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    st.individual_turns = 1
    return st


def _equip(pid, slug, types, subtypes, defense=2):
    c = Card(slug=slug, name=slug, types=types, subtypes=subtypes,
             base_defense=defense)
    c.owner = c.controller = pid
    return c


# --- the zone ---------------------------------------------------------------

def test_the_equipment_pool_includes_an_offhand_in_the_weapon_zone():
    st = _state()
    body = _equip(1, "a_helm", ["Equipment"], ["Head"])
    off = _equip(1, "an_offhand", ["Equipment"], ["Off-Hand"])
    st.players[1].head.add(body)
    st.players[1].weapon2.add(off)

    pool = _object_zone_cards(st.players[1], "EQUIPMENT")

    assert body in pool
    assert off in pool, "an off-hand is equipment (CR 2.10.6a / 3.16.2a)"


def test_a_weapon_is_not_equipment():
    st = _state()
    sword = _equip(1, "a_sword", ["Weapon"], ["1H"])
    st.players[1].weapon1.add(sword)

    assert sword not in _object_zone_cards(st.players[1], "EQUIPMENT")


# --- the card ---------------------------------------------------------------

def _reinforce(st, target):
    src = copy.deepcopy(DB.get("reinforce_steel_yellow"))
    src.owner = src.controller = 1
    run_ability(get_card("reinforce_steel_yellow").abilities[0], src, None, st)
    return target


def test_reinforce_steel_removes_the_counter_from_a_guardian_offhand():
    st = _state()
    off = _equip(1, "guardian_offhand", ["Equipment"], ["Off-Hand"])
    off.card_class = "Guardian"
    off.classes = ["Guardian"]
    off.counters = {"-1d": 1}
    st.players[1].weapon2.add(off)

    _reinforce(st, off)

    assert off.counters.get("-1d", 0) == 0, (
        "the -1{d} counter is still on the off-hand")


def test_it_leaves_a_non_guardian_offhand_alone():
    st = _state()
    off = _equip(1, "brute_offhand", ["Equipment"], ["Off-Hand"])
    off.card_class = "Brute"
    off.classes = ["Brute"]
    off.counters = {"-1d": 1}
    st.players[1].weapon2.add(off)

    _reinforce(st, off)

    assert off.counters.get("-1d", 0) == 1, "it is not a Guardian off-hand"
