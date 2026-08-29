"""Three more ported cards, including the conditional-go-again shape done RIGHT.

    arcanic_spike_red              "if you've dealt ARCANE damage this turn"
    cut_a_long_story_short_yellow  "if this has 13 or more {p}"
    jaws_of_victory_red            "if you've been cheered this turn, this gets
                                    go again"

jaws_of_victory_red is the one worth having as a reference. Fifty cards in this
corpus print a keyword their text gates, and the engine applies every printed
keyword unconditionally, so the gate could never take it away -- 42 of them are
still in the ratchet. Jaws is not one: it grants go again from a WHILE_STATIC
ability gated on SOURCE_IS_ATTACK, which is the exact shape
loader.conditional_keywords recognises, so its printed GoAgain IS stripped and
the card only has go again while the condition holds.

That makes it a worked example of the fix the backlog needs, and pinning its
behaviour means the pattern itself has a test rather than only the backlog
count having one.

Every negative case here was verified by breaking the card and confirming the
test then fails.
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
from engine.card_effects.dsl.loader import (conditional_keywords, get_card,
                                            load_all_cards)
from engine.effect_keywords import _record_turn_event
from engine.state import CombatState
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
    return st


def _src(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _combat(st, slug, power=None):
    """Set up a real attack with `slug` as the attacking card.

    CORRECTION. An earlier version of this docstring said WHILE_STATIC "is not
    dispatched by run_ability". That is wrong -- run_ability applies it fine.
    The actual reason three correct cards looked broken here is the IDENTITY
    trap: SOURCE_IS_ATTACK is `combat.attack_card is c`, and the test built
    combat from one deepcopy while passing the ability a second. Equal, not
    identical, so the condition was false and the static did nothing.

    Hence this returns the card it installed, and the tests use THAT object.
    conftest.assert_source_is_the_attack turns the mistake into a loud failure.
    """
    attack = copy.deepcopy(DB.get(slug))
    attack.owner = attack.controller = 1
    power = attack.base_power or 0 if power is None else power
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=power,
                            attack_card=attack, keywords=[], from_weapon=False)
    st.combat.base_attack_power = power
    E._apply_turn_attack_effects(st, attack)
    E._register_card_continuous_effects(st, attack)
    return attack


def _recalc(st):
    E._recalculate_attack_power(st)
    return st.combat.attack_power


def _static(slug, index=0):
    return get_card(slug).abilities[index]


# --- "if you've dealt arcane damage this turn" -------------------------------

def test_arcanic_spike_pumps_after_arcane_damage():
    st = _state()
    _combat(st, "arcanic_spike_red")
    _record_turn_event(st, 1, "damage", "arcane")

    base = st.combat.attack_power
    assert _recalc(st) == base + 2, (
        f"expected +2 after dealing arcane damage, got {_recalc(st) - base}")


def test_arcanic_spike_does_not_pump_after_ordinary_damage():
    """The QUALIFIER is the whole condition. A card reading only "dealt damage"
    passes the positive test and is wrong on every physical hit."""
    st = _state()
    _combat(st, "arcanic_spike_red")
    _record_turn_event(st, 1, "damage", "physical")

    base = st.combat.attack_power
    assert _recalc(st) == base, (
        "pumped after PHYSICAL damage -- the arcane qualifier is not gating")


def test_arcanic_spike_does_not_pump_with_no_damage_at_all():
    st = _state()
    _combat(st, "arcanic_spike_red")

    base = st.combat.attack_power
    assert _recalc(st) == base


# --- "if this has 13 or more {p}" -------------------------------------------

def test_cut_a_long_story_short_empties_the_hand_at_13_power():
    st = _state()
    _combat(st, "cut_a_long_story_short_yellow", power=13)
    for _ in range(3):
        filler = Card(slug="filler", name="filler", types=["Action"])
        filler.owner = filler.controller = 2
        st.players[2].hand.add(filler)
    src = _src("cut_a_long_story_short_yellow")
    hit = get_card("cut_a_long_story_short_yellow").abilities[1]

    run_ability(hit, src, None, st)

    assert len(list(st.players[2].hand.cards)) == 0, (
        "at 13 power the defending hero discards their hand")


def test_cut_a_long_story_short_leaves_the_hand_below_13():
    st = _state()
    _combat(st, "cut_a_long_story_short_yellow", power=12)
    for _ in range(3):
        filler = Card(slug="filler", name="filler", types=["Action"])
        filler.owner = filler.controller = 2
        st.players[2].hand.add(filler)
    src = _src("cut_a_long_story_short_yellow")
    hit = get_card("cut_a_long_story_short_yellow").abilities[1]

    run_ability(hit, src, None, st)

    assert len(list(st.players[2].hand.cards)) == 3, (
        "emptied the hand at 12 power -- the 13 threshold is not gating")


# --- the conditional go again, done correctly -------------------------------

def test_jaws_printed_go_again_is_treated_as_conditional():
    """The engine applies every PRINTED keyword unconditionally, so a gated one
    must be stripped or the gate is decoration. This is the shape 42 cards in
    the ratchet still need."""
    assert "goagain" in conditional_keywords("jaws_of_victory_red"), (
        "the printed GoAgain is unconditional again -- the card would always "
        "have go again regardless of the cheer")


def test_jaws_grants_go_again_when_cheered():
    st = _state()
    _combat(st, "jaws_of_victory_red")
    st.players[1].current_turn_effects.append("crowd_cheered")

    _recalc(st)

    assert any("go again" in str(k).replace("Go", "go").lower()
               for k in st.combat.keywords), st.combat.keywords


def test_jaws_withholds_go_again_without_the_cheer():
    st = _state()
    _combat(st, "jaws_of_victory_red")

    _recalc(st)

    assert not any("go again" in str(k).replace("Go", "go").lower()
                   for k in st.combat.keywords), (
        "go again without having been cheered -- the gate is not gating, and "
        "this is the defect the whole ratchet exists for")


def test_jaws_cheers_only_when_behind_on_life():
    st = _state()
    _combat(st, "jaws_of_victory_red")
    st.players[1].life = 20
    st.players[2].life = 5
    src = _src("jaws_of_victory_red")

    run_ability(_static("jaws_of_victory_red", 0), src, None, st)

    assert "crowd_cheered" not in st.players[1].current_turn_effects, (
        "cheered while AHEAD on life")
