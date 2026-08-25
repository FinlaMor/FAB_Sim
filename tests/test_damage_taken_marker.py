""""Has been dealt damage" asked the attacker's question of the defender.

Turn markers answer "did you do X this turn". Damage was recorded once, against
the player who DEALT it, under the event name `damage`. Runaways activates
"only if YOUR HERO HAS BEEN DEALT damage this turn" -- the other direction --
and gated on that same marker, so it read whether its controller had dealt
damage. The two coincide often enough in a real game (you attack, they attack
back) that the gate looks like it works; they part company exactly in the state
the card is for -- you have been hit and have done nothing yet.

`damage_taken` is recorded against the player whose object was damaged, so the
two directions cannot be confused by a later card asking either one.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.effect_keywords import DamageType, deal_damage
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

HERO = "kayo_strong_arm"
OTHER_HERO = "gravy_bones"


def _card(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _state():
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="": o[0]
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    st.individual_turns = 1
    st.players[1].hero = _card(HERO, 1)
    st.players[2].hero = _card(OTHER_HERO, 2)
    st.players[1].permanents.add(_card("runaways", 1))
    return st


def _can_activate(st):
    """The observable form of the gate: is activating Runaways a legal action?"""
    from engine.actions import ActionType
    from engine.play import available_actions
    return any(a.type == ActionType.ACTIVATE_CARD
               and getattr(a.card, "slug", None) == "runaways"
               for a in available_actions(st, 1))


def _hit_player_one(st, amount=2):
    deal_damage(st, amount, DamageType.PHYSICAL, 2, st.players[1].hero, "effect")


# --- the marker -------------------------------------------------------------

def test_the_victim_gets_a_marker_and_the_dealer_does_not_get_the_victims():
    from engine.effect_keywords import TURN_EVENT_MARKER
    st = _state()

    _hit_player_one(st)

    # Markers are normalised (underscores stripped) on the way in, which is
    # also how EVENT_THIS_TURN spells the name it looks up.
    taken = TURN_EVENT_MARKER + "damagetaken:hero"
    assert taken in st.players[1].current_turn_effects, (
        "the damaged player recorded nothing")
    assert taken not in st.players[2].current_turn_effects, (
        "the dealing player recorded the victim's marker")


def test_dealing_damage_still_records_against_the_dealer():
    """The existing direction must keep working -- many cards ask it."""
    from engine.effect_keywords import TURN_EVENT_MARKER
    st = _state()

    _hit_player_one(st)

    assert (TURN_EVENT_MARKER + "damage:hero") in st.players[2].current_turn_effects


# --- the card ---------------------------------------------------------------

def test_runaways_cannot_activate_before_your_hero_is_hit():
    st = _state()

    assert not _can_activate(st)


def test_runaways_activates_once_your_hero_has_been_hit():
    st = _state()
    _hit_player_one(st)

    assert _can_activate(st), (
        "your hero has been dealt damage; the gate is still shut")


def test_dealing_damage_yourself_does_not_open_the_gate():
    """The defect: the old gate read the DEALER's marker, so hitting the
    opponent unlocked a card that asks whether YOU were hit."""
    st = _state()
    deal_damage(st, 2, DamageType.PHYSICAL, 1, st.players[2].hero, "effect")

    assert not _can_activate(st), (
        "hitting the opponent unlocked a card gated on being hit yourself")
