"""The Bones cycle: "discard a card OR destroy the top card of your deck".

    jittery_bones / restless_bones   ...if that card has watery grave, go again
    angry_bones                      ...if that card has watery grave, +1{p}

Six pending cards in the first family and three in the second, all reading one
sentence that burly_bones already implements with a different payoff -- so one
card written per payoff and the copier does the rest.

TWO THINGS ARE EASY TO GET WRONG HERE, and both are silent.

"THAT CARD" IS WHICHEVER ONE THE PLAYER MOVED, so both halves of the choice
must record the SAME ref: the discard stores what it discarded, and the deck
branch LOOKS at the top card before destroying it. Destroying it without
looking leaves nothing to ask about, and re-reading the graveyard afterwards
would find every card put there this turn instead of this one -- which is not a
smaller version of the clause but a much larger one.

THE PRINTED GO AGAIN SPLITS THE TWO FAMILIES. Jittery and Restless list GoAgain
in the card DB because it flattens the sentence, so it has to be withdrawn or
the gate is decoration and the attack always has it. Angry Bones prints no
keyword at all, and a withdrawal there would take away something the card does
not have -- the same bug inverted. Both directions asserted.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import (conditional_keywords, get_card,
                                            load_all_cards)
from tests.conftest import _make_state, attack_with, recalculate_attack

load_all_cards()
DB = CardDB()

FAMILIES = {"jittery_bones_blue": "go again", "angry_bones_blue": "power"}


def _card(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _state(choice=0, accept=True):
    """`choice` picks the discard (0) or the deck branch (1)."""
    st = _make_state()
    st.card_db = DB

    def agent(state, options, context="", **kw):
        """Two prompts arrive and they look alike -- ['yes','no'] for the MAY
        and ['0','1'] for the CHOOSE. A first version keyed on "two string
        options" and answered 'no' to the MAY whenever it meant to pick the
        second BRANCH, so the deck half never ran and its tests failed against
        a correct card."""
        from engine.card_effects.ability_keywords import DECLINE, NO
        opts = list(options)
        if "yes" in opts or NO in opts or DECLINE in opts:
            if not accept:
                for opt in (NO, DECLINE, "no"):
                    if opt in opts:
                        return opt
            return "yes" if "yes" in opts else opts[0]
        return opts[min(choice, len(opts) - 1)]

    st.player_agents = {1: agent, 2: agent}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    return st


@pytest.fixture(scope="module")
def watery():
    """A real card with the Watery Grave keyword, and one without."""
    import io, json
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    idx = json.load(io.open(root / "card_data" / "slug_index.json",
                            encoding="utf-8"))["by_slug"]
    with_kw = next(s for s, e in idx.items()
                   if any(str(k).lower().replace(" ", "") == "waterygrave"
                          for k in (e.get("keywords") or [])) and DB.get(s))
    without = next(s for s, e in idx.items()
                   if not any(str(k).lower().replace(" ", "") == "waterygrave"
                              for k in (e.get("keywords") or [])) and DB.get(s)
                   and "Hero" not in (e.get("types") or []))
    return with_kw, without


def test_the_probes_are_what_they_claim(watery):
    """Guards every test below: if the fixture stopped finding a Watery Grave
    card the gate would be false everywhere and the negatives would pass for
    the wrong reason."""
    with_kw, without = watery
    assert any(str(k).lower().replace(" ", "") == "waterygrave"
               for k in (DB.get(with_kw).keywords or []))
    assert not any(str(k).lower().replace(" ", "") == "waterygrave"
                   for k in (DB.get(without).keywords or []))


def _run(slug, st, hand=(), deck=()):
    for s in hand:
        st.players[1].hand.add(_card(s))
    for s in deck:
        st.players[1].deck.add(_card(s))
    attacker = attack_with(st, _card(slug))
    run_ability(get_card(slug).abilities[0], attacker, None, st)
    return attacker


def _has_go_again(st):
    return "goagain" in {str(k).lower().replace(" ", "").replace("_", "")
                         for k in (st.combat.keywords or [])}


# ------------------------------------------------------------- the discard

def test_discarding_a_watery_grave_card_pays_off(watery):
    with_kw, _ = watery
    st = _state(choice=0)
    _run("jittery_bones_blue", st, hand=[with_kw])
    assert _has_go_again(st)


def test_discarding_an_ordinary_card_does_not(watery):
    _, without = watery
    st = _state(choice=0)
    _run("jittery_bones_blue", st, hand=[without])
    assert not _has_go_again(st)


# ------------------------------------------------------ the deck-top branch

def test_destroying_a_watery_grave_card_off_the_deck_pays_off(watery):
    with_kw, _ = watery
    st = _state(choice=1)
    _run("jittery_bones_blue", st, deck=[with_kw])
    assert _has_go_again(st)


def test_the_deck_branch_actually_removes_the_card(watery):
    """It LOOKS then DESTROYS. A branch that only looked would leave the card
    on the deck and the whole cost would be free."""
    with_kw, _ = watery
    st = _state(choice=1)
    _run("jittery_bones_blue", st, deck=[with_kw])
    assert st.players[1].deck.cards == [], (
        "the deck kept the card that was supposed to be destroyed")


# --------------------------------------------------------------- declining

def test_declining_costs_nothing_and_pays_nothing(watery):
    with_kw, _ = watery
    st = _state(accept=False)
    _run("jittery_bones_blue", st, hand=[with_kw])
    assert not _has_go_again(st)
    assert len(st.players[1].hand.cards) == 1, "it discarded despite declining"


# ------------------------------------------------------------- angry bones

def test_angry_bones_pumps_instead_of_granting_a_keyword(watery):
    with_kw, _ = watery
    st = _state(choice=0)
    attacker = _run("angry_bones_blue", st, hand=[with_kw])
    assert recalculate_attack(st) == (attacker.base_power or 0) + 1
    assert not _has_go_again(st), "it granted a keyword it does not have"


def test_angry_bones_does_not_pump_without_watery_grave(watery):
    _, without = watery
    st = _state(choice=0)
    attacker = _run("angry_bones_blue", st, hand=[without])
    assert recalculate_attack(st) == (attacker.base_power or 0)


# ------------------------------------------------------- printed keywords

def test_only_the_family_that_prints_go_again_withdraws_it():
    assert "GoAgain" in (DB.get("jittery_bones_blue").keywords or [])
    assert "goagain" in conditional_keywords("jittery_bones_blue")

    assert not (DB.get("angry_bones_blue").keywords or []), \
        "angry bones prints no keyword"
    assert not conditional_keywords("angry_bones_blue"), \
        "withdrawing a keyword this card does not print takes away nothing, " \
        "but it is the same mistake inverted and would hide a real one later"
