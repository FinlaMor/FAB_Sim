"""Two attack filters that named a SUBTYPE where the condition wanted a class.

"A SWORD attack you control" and "your next ANGEL attack" were both authored as
ATTACK_CLASS_IN. That condition matches classes, talents and pitch colour --
Sword and Angel are neither; they are subtypes carried by 23 and 10 cards
respectively. A class filter handed a subtype is false for every attack in the
game, so one ability never fired at all and the other never handed out its +4.

ATTACK_SUBTYPE_IN is the condition that reads types AND subtypes, and it already
existed. The pattern is the recurring one: a mechanic under a name the author
did not guess, and a filter that fails CLOSED, which looks exactly like a card
whose condition simply was not met.

Anticipating Gaze also had "remove a +1{p} counter FROM THE SWORD" with no
target -- so it removed one from the equipment running the ability -- naming a
counter kind ("+1{p}") that nothing stores; SHARPEN records them under "power".
Three independent reasons the same clause could not work.

The guard checks every class-condition value against the classes, talents and
types that actually occur in the card data, so a subtype slipping into one of
these is caught wherever it appears next.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import engine.engine as E
from engine.card import Card, CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state
from tests.conftest import card_json_files

load_all_cards()
DB = CardDB()

JSON_ROOT = ROOT / "engine" / "card_effects" / "json"
CLASS_CONDITIONS = ("ATTACK_CLASS_IN", "CLASS_IN", "CARD_IS_CLASS")
CLASS_KEYS = ("classes", "class", "card_class", "attack_class")


def _state():
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="": o[0]
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    st.individual_turns = 1
    return st


def _attack(st, subtypes, power=5):
    a = Card(slug="an_attack", name="an_attack", types=["Action"],
             subtypes=["Attack"] + list(subtypes))
    a.owner = a.controller = 1
    a.base_power = power
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=power,
                            attack_card=a, keywords=[], from_weapon=False)
    st.combat.base_attack_power = power
    return a


def _resolved_power(st, attack):
    """A queued "next attack" mod lands as a CardEffect on the attack card, so
    the number only appears after the recalculation the engine runs."""
    E._apply_turn_attack_effects(st, attack)
    E._register_card_continuous_effects(st, attack)
    E._recalculate_attack_power(st)
    return st.combat.attack_power


def _sword(st, counters=1):
    w = Card(slug="a_sword", name="a_sword", types=["Weapon"],
             subtypes=["Sword", "1H"])
    w.owner = w.controller = 1
    w.counters = {"power": counters}
    st.players[1].weapon1.add(w)
    return w


def _gaze(st):
    src = copy.deepcopy(DB.get("anticipating_gaze"))
    src.owner = src.controller = 1
    st.players[1].permanents.add(src)
    run_ability(get_card("anticipating_gaze").abilities[0], src, None, st)
    return src


# --- anticipating_gaze ------------------------------------------------------

def test_a_sword_attack_takes_the_counter_off_the_sword():
    st = _state()
    sword = _sword(st)
    _attack(st, ["Sword"])
    before = len(st.players[1].hand.cards)
    st.players[1].deck.add(Card(slug="a_draw", name="a_draw", types=["Action"]))

    _gaze(st)

    assert sword.counters.get("power", 0) == 0, (
        "the counter never came off the sword")
    assert len(st.players[1].hand.cards) == before + 1, "it did not draw"


def test_a_non_sword_attack_leaves_it_alone():
    st = _state()
    sword = _sword(st)
    _attack(st, ["Club"])

    _gaze(st)

    assert sword.counters.get("power", 0) == 1, (
        "a Club attack triggered a Sword ability")


# --- war_cry_of_themis_yellow -----------------------------------------------

def test_war_cry_pumps_an_angel_attack():
    st = _state()
    src = copy.deepcopy(DB.get("war_cry_of_themis_yellow"))
    src.owner = src.controller = 1
    run_ability(get_card("war_cry_of_themis_yellow").abilities[0], src, None, st)

    attack = _attack(st, ["Angel"], power=4)

    power = _resolved_power(st, attack)

    assert power == 8, f"the +4 never reached the Angel attack (power {power})"


def test_war_cry_leaves_a_non_angel_attack_alone():
    st = _state()
    src = copy.deepcopy(DB.get("war_cry_of_themis_yellow"))
    src.owner = src.controller = 1
    run_ability(get_card("war_cry_of_themis_yellow").abilities[0], src, None, st)

    attack = _attack(st, ["Sword"], power=4)

    assert _resolved_power(st, attack) == 4, "it pumped a non-Angel attack"


# --- the guard --------------------------------------------------------------

def test_no_class_condition_names_something_that_is_not_a_class():
    """Derived from the card data: every value handed to a class condition must
    be a class, talent or type that some card actually has."""
    idx = json.load(open(ROOT / "card_data" / "slug_index.json",
                         encoding="utf-8"))["by_slug"]
    known = set()
    for d in idx.values():
        for key in ("cardClass", "classes", "talents", "types"):
            v = d.get(key)
            if isinstance(v, str):
                known.add(v.lower())
            elif isinstance(v, list):
                known.update(str(x).lower() for x in v)

    bad = []
    for path in card_json_files(JSON_ROOT):
        rel = path.relative_to(JSON_ROOT)
        if (path.stem.endswith("_work_queue")
                or any(p.startswith(".") or p == "needs_review"
                       for p in rel.parts)):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        def walk(node):
            if isinstance(node, dict):
                if node.get("type") in CLASS_CONDITIONS:
                    for key in CLASS_KEYS:
                        v = node.get(key)
                        if isinstance(v, str):
                            v = [v]
                        for one in (v or []):
                            if str(one).lower() not in known:
                                bad.append(f"{raw.get('slug')}: {one}")
                for x in node.values():
                    walk(x)
            elif isinstance(node, list):
                for x in node:
                    walk(x)

        walk(raw.get("abilities"))
    assert bad == [], (
        "class conditions naming something no card has as a class/talent/type "
        f"-- a subtype here is false for every card: {bad}")
