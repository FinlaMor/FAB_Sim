"""Censor: "name a card. They can't play the named card until the end of their
next turn."

The card was a SET_FLAG CENSOR_ACTIVE, and its own `_comment` records that an
earlier pass had already found and fixed the WRONG half of the problem -- it
moved the restriction from the controller to the opponent, which was correct as
far as it went, and left it pointing at a flag name nothing reads. Fixing which
player a dead flag is written to does not bring it to life.

It also never named a card. Even a reader would have had nothing to enforce,
because "name a card" was not in the implementation at all -- so the clause the
whole card is about was missing, not merely mis-wired.

KEYED ON THE NAME, NOT THE SLUG. A player naming "Censor" names every printing
of it; red, yellow and blue share a name and not a slug. Storing the slug would
forbid exactly one printing and let the others through.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card import CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.play import available_actions
from tests.conftest import _make_combat, _make_state, owned_card

load_all_cards()
DB = CardDB()


def _state():
    st = _make_state()
    st.card_db = DB
    return st


def _victim_holds(st, *names):
    """Put cards in player 2's hand, playable, and return them."""
    out = []
    for name in names:
        c = owned_card(2, slug=name.lower().replace(" ", "_"), name=name,
                       types=["Action"], raw_cost=0)
        c.cost = 0
        st.players[2].hand.add(c)
        out.append(c)
    st.players[2].resources = 5
    st.players[2].action_points = 1
    return out


def _land_censor(st, named, controller=1):
    """Fire Censor's ON_HIT, with the agent naming `named`.

    NAME_A_CARD offers only names the namer can SEE -- their own cards plus
    anything public -- so the namer is given a copy of the card here. That is a
    real narrowing of the printed rule (in FAB you may name any card at all,
    which is the whole point of naming something you expect them to draw), and
    it is a property of NAME_A_CARD rather than of Censor; every card that names
    one inherits it. Recorded here because a fixture that quietly worked around
    it would hide it.
    """
    known = owned_card(controller, slug="_nameable", name=named,
                       types=["Action"], raw_cost=0)
    st.players[controller].hand.add(known)
    card = owned_card(controller, "censor_red")
    st.combat = _make_combat(attacker_id=controller, attack_card=card)
    st.combat.attack_target = None      # a hero attack names no other target
    st.player_agents[controller] = (
        lambda state, options, context, **kw: named if named in options
        else (options[0] if options else None))
    run_ability(get_card("censor_red").abilities[0], card, None, st)


def _playable_names(st, pid=2):
    st.active_player = pid
    return {getattr(a.card, "name", None) for a in available_actions(st, pid)}


def test_the_named_card_cannot_be_played():
    st = _state()
    _victim_holds(st, "Head Jab", "Scar for a Scar")
    assert "Head Jab" in _playable_names(st), "fixture: it was never playable"

    _land_censor(st, "Head Jab")
    names = _playable_names(st)
    assert "Head Jab" not in names, "the named card is still playable"
    assert "Scar for a Scar" in names, (
        "Censor forbade more than the card it named")


def test_it_restricts_the_hero_that_was_hit_not_the_controller():
    st = _state()
    _victim_holds(st, "Head Jab")
    mine = owned_card(1, slug="head_jab", name="Head Jab", types=["Action"],
                      raw_cost=0)
    mine.cost = 0
    st.players[1].hand.add(mine)
    st.players[1].resources = 5
    st.players[1].action_points = 1

    _land_censor(st, "Head Jab", controller=1)

    assert "Head Jab" not in _playable_names(st, 2)
    assert "Head Jab" in _playable_names(st, 1), (
        "Censor restricted its own controller")


def test_every_printing_of_the_named_card_is_forbidden():
    """Naming a card names its NAME. A slug-keyed restriction would stop the
    red printing and wave the blue one through."""
    st = _state()
    red = owned_card(2, slug="head_jab_red", name="Head Jab", types=["Action"],
                     raw_cost=0)
    blue = owned_card(2, slug="head_jab_blue", name="Head Jab", types=["Action"],
                      raw_cost=0)
    for c in (red, blue):
        c.cost = 0
        st.players[2].hand.add(c)
    st.players[2].resources = 5
    st.players[2].action_points = 1

    _land_censor(st, "Head Jab")
    playable = [a for a in available_actions(st, 2)
                if getattr(a.card, "name", None) == "Head Jab"]
    assert not playable, "a second printing of the named card slipped through"


def test_it_lasts_through_the_victims_next_turn_and_then_stops():
    st = _state()
    _victim_holds(st, "Head Jab")
    _land_censor(st, "Head Jab")
    assert "Head Jab" not in _playable_names(st)

    p2 = st.players[2]
    p2.current_turn_effects = p2.next_turn_effects[:]
    p2.next_turn_effects = []
    assert "Head Jab" not in _playable_names(st), (
        "the restriction expired before the victim's next turn")

    p2.current_turn_effects = []
    assert "Head Jab" in _playable_names(st), (
        "the restriction outlived the end of the victim's next turn")
