"""Three more cards authored to unlock their colour/equipment group.

    seekers_gilet         4 cards  "Instant - {r}, destroy this: Prevent the
                                    next 1 damage ... Opt 1"
    skybody_keikoi        4 cards  "Instant - Destroy this: Prevent the next 1
                                    damage ... only while this is face-down."
    villainous_pose_blue  3 cards  "Your next attack this turn gets +2{p}. The
                                    crowd boos you. Go again"

The two equipment pieces are nearly the same card and differ in exactly two
places, which is what makes them worth testing together: one costs {r} and the
other does not, and one may only be activated while face-down. Both differences
are LEGALITY, so they are asserted through `play.available_actions` -- the list
the game actually offers -- rather than by reading the ability. "Activate this
ability only while..." is a restriction on whether the action exists at all,
not a check performed during resolution, so an implementation that offered the
action and then did nothing would pass a resolution-shaped test and still be
wrong.

RESOLUTION IS TESTED SEPARATELY, through run_ability, because that is the layer
that resolves an ability once its costs are paid. play.py pays `costs`;
run_ability does not, so asserting "the equipment was destroyed" against
run_ability would be testing the wrong layer and would fail on a correct card.

"The crowd boos YOU" is the rare self-targeting form. CROWD_BOO defaults to the
controller, and a card reaching for the opponent-facing spelling would boo the
wrong hero -- invisible to any power assertion, so it is asserted on its own.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.effect_keywords import DamageType, deal_damage
from engine.play import available_actions
from engine.state import Step
from tests.conftest import _make_state, attack_with, recalculate_attack

load_all_cards()
DB = CardDB()


def _card(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _state(resources=3):
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="", **kw: o[0]      # noqa: E731
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    st.step = Step.ACTION
    st.players[1].resources = resources
    st.players[1].action_points = 1
    return st


def _equipped(st, slug, face_down):
    piece = _card(slug)
    piece.face_down = face_down
    piece.is_public = not face_down
    st.players[1].permanents.add(piece)
    return piece


def _offers(st, slug):
    return any(getattr(a, "card", None) is not None
               and getattr(a.card, "slug", None) == slug
               for a in available_actions(st, 1))


def _damage(st, amount, dtype=DamageType.PHYSICAL):
    """Deal `amount` to player 1's hero; return how much actually landed."""
    before = st.players[1].life
    deal_damage(st, amount, dtype, 2, st.players[1].hero, "effect")
    return before - st.players[1].life


# ----------------------------------------------------- the shields resolve

@pytest.mark.parametrize("slug", ["seekers_gilet", "skybody_keikoi"])
def test_the_shield_absorbs_one_damage(slug):
    st = _state()
    piece = _equipped(st, slug, face_down=True)
    run_ability(get_card(slug).abilities[0], piece, None, st)
    assert _damage(st, 3) == 2, "the prevention did not register"


@pytest.mark.parametrize("slug", ["seekers_gilet", "skybody_keikoi"])
def test_the_shield_is_one_shot(slug):
    """"the NEXT 1 damage" -- a shield that survived its use would absorb one
    damage from every source for the rest of the turn."""
    st = _state()
    piece = _equipped(st, slug, face_down=True)
    run_ability(get_card(slug).abilities[0], piece, None, st)
    assert _damage(st, 3) == 2
    assert _damage(st, 3) == 3, "the shield absorbed a second hit"


# ----------------------------------------------------- and the legality

def test_keikoi_is_offered_only_while_it_is_face_down():
    """"Activate this ability only while this is face-down" restricts the
    ACTION, not the resolution: a face-up Keikoi must not be offered it."""
    st = _state()
    _equipped(st, "skybody_keikoi", face_down=True)
    assert _offers(st, "skybody_keikoi"), "face-down, and not offered"

    st = _state()
    _equipped(st, "skybody_keikoi", face_down=False)
    assert not _offers(st, "skybody_keikoi"), "offered while face up"


def test_the_gilet_has_no_face_down_restriction():
    """The other half. Copying Keikoi's gate onto the Gilet -- they read almost
    identically -- would make it unusable, and nothing else here would notice."""
    st = _state()
    _equipped(st, "seekers_gilet", face_down=False)
    assert _offers(st, "seekers_gilet")


def test_the_gilet_needs_a_resource_and_the_keikoi_does_not():
    """Printed as "{r}, destroy this" against "Destroy this". Getting the
    activation cost wrong makes one of them free, which no resolution test
    would catch."""
    st = _state(resources=0)
    _equipped(st, "seekers_gilet", face_down=False)
    _equipped(st, "skybody_keikoi", face_down=True)
    assert not _offers(st, "seekers_gilet"), "activated with no resources"
    assert _offers(st, "skybody_keikoi"), "its activation is free"


# -------------------------------------------------------- villainous pose

def test_villainous_pose_boos_its_own_controller():
    st = _state()
    card = _card("villainous_pose_blue")
    run_ability(get_card("villainous_pose_blue").abilities[0], card, None, st)
    booed = [p for p in (1, 2)
             if st.players[p].class_counters.get("booed_this_turn")]
    assert booed == [1], (
        "'the crowd boos YOU' means the controller; booed=%s" % booed)


def test_villainous_pose_pumps_the_next_attack():
    st = _state()
    card = _card("villainous_pose_blue")
    run_ability(get_card("villainous_pose_blue").abilities[0], card, None, st)
    attacker = attack_with(st, _card("head_jab_red"))
    base = attacker.base_power or 0
    assert recalculate_attack(st) == base + 2
