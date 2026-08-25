"""Thirty-three activated abilities printed "Go again" and granted nothing.

CR 8.3.5 defines go again as "gain 1 action point", and splits on what has it:

  8.3.5b  an ability of an ATTACK on the active chain link -- the point arrives
          at the Resolution Step, so the keyword goes on the combat and the
          engine pays it out later.
  8.3.5a  an ability of a NON-ATTACK LAYER -- the controlling player gains the
          point once the other resolution abilities have resolved.

Only 8.3.5b was implemented. Both spellings wrote to state.combat.keywords, and
an activated equipment ability in the action phase has no combat at all -- so
the point was dropped on the floor. That is not a weaker card: an action-phase
activation costs an action point, and "Go again" is what gives it back. Without
it, activating Blossom of Spring to gain {r} ENDED YOUR TURN.

"Is there a combat" is exactly the discriminator the rule uses: a weapon attack
activation does have one and keeps the 8.3.5b path, so this cannot double-pay
an attack.

The two spellings -- {"type": "GO_AGAIN"} and {"type": "GAIN", "keyword":
"GO_AGAIN"} -- were separate implementations of one rule, and only finding the
second by reading a card that used it is why they now share a function.
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
from engine.card import Card, CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.state import CombatState
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
    st.players[1].action_points = 1
    return st


def _src(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _ability(slug, index=0):
    return get_card(slug).abilities[index]


# --- the GO_AGAIN spelling --------------------------------------------------

def test_an_action_phase_activation_gives_the_action_point_back():
    """Blossom of Spring: "Action - Destroy this: Gain {r}. Go again"."""
    st = _state()
    src = _src("blossom_of_spring")
    st.players[1].permanents.add(src)

    run_ability(_ability("blossom_of_spring"), src, None, st)

    assert st.players[1].action_points == 2, (
        "the printed Go again granted no action point, so the activation ate "
        "the turn")


def test_it_is_the_controller_who_gains_it():
    st = _state()
    st.players[2].action_points = 1
    src = _src("blossom_of_spring", pid=1)
    st.players[1].permanents.add(src)

    run_ability(_ability("blossom_of_spring"), src, None, st)

    assert st.players[2].action_points == 1, "the opponent gained the point"


# --- the GAIN keyword spelling ----------------------------------------------

def test_the_other_spelling_grants_it_too():
    """teklo_plasma_pistol authors {"type": "GAIN", "keyword": "GO_AGAIN"} --
    the same rule under a second name, previously a second implementation."""
    st = _state()
    src = _src("teklo_plasma_pistol")
    st.players[1].weapon1.add(src)

    run_ability(_ability("teklo_plasma_pistol", 1), src, None, st)

    assert st.players[1].action_points == 2, (
        'the GAIN keyword:"GO_AGAIN" spelling still drops the point')


# --- the attack path is untouched -------------------------------------------

def test_an_attack_still_takes_the_keyword_route():
    """CR 8.3.5b: the point arrives at the Resolution Step, so the combat must
    carry the keyword and the controller must NOT be paid early."""
    st = _state()
    src = _src("blossom_of_spring")
    attack = Card(slug="an_attack", name="an_attack", types=["Action"],
                  subtypes=["Attack"])
    attack.owner = attack.controller = 1
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=4,
                            attack_card=attack, keywords=[], from_weapon=False)

    run_ability(_ability("blossom_of_spring"), src, None, st)

    assert "Go Again" in st.combat.keywords, "the attack lost its go again"
    assert st.players[1].action_points == 1, (
        "the point was paid immediately AND queued on the combat -- twice for "
        "one resolution")


def _go_agains(combat):
    import re
    return sum(1 for k in (combat.keywords or [])
               if re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(k)).lower() == "go again")


def test_granting_it_twice_pays_once():
    """"An object cannot have more than one go again ability" (CR 8.3.5c); a
    second grant fails rather than stacking."""
    st = _state()
    src = _src("blossom_of_spring")
    attack = Card(slug="an_attack", name="an_attack", types=["Action"],
                  subtypes=["Attack"])
    attack.owner = attack.controller = 1
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=4,
                            attack_card=attack, keywords=[], from_weapon=False)

    run_ability(_ability("blossom_of_spring"), src, None, st)
    run_ability(_ability("blossom_of_spring"), src, None, st)

    assert _go_agains(st.combat) == 1, st.combat.keywords


def test_a_printed_go_again_is_not_granted_a_second_time():
    """The guard compared literals, and the two spellings never matched: the
    card DB prints "GoAgain" while a grant writes "Go Again". So an attack that
    already had go again was given another -- exactly what 8.3.5c forbids.
    """
    st = _state()
    src = _src("blossom_of_spring")
    attack = Card(slug="an_attack", name="an_attack", types=["Action"],
                  subtypes=["Attack"])
    attack.owner = attack.controller = 1
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=4,
                            attack_card=attack, keywords=["GoAgain"],
                            from_weapon=False)

    run_ability(_ability("blossom_of_spring"), src, None, st)

    assert _go_agains(st.combat) == 1, (
        f"a printed GoAgain got a second, granted one: {st.combat.keywords}")


# --- the shape --------------------------------------------------------------

def test_both_spellings_share_one_implementation():
    """They are one rule. Kept apart, a fix to either is a coin flip -- which
    is how the second one stayed broken while the first was being read."""
    import inspect

    from engine.card_effects.dsl import effect_types

    src = inspect.getsource(effect_types.compile_effect)
    assert src.count("_grant_go_again(") >= 2, (
        "GO_AGAIN and GAIN keyword:GO_AGAIN no longer route through the same "
        "function")
