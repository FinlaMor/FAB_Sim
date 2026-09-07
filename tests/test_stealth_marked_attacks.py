"""Four Stealth attacks that key off a MARKED hero, and one that does not.

    scuttle_the_canal_blue    when this attacks a marked hero, go again
    plunge_the_prospect_blue  IF THIS IS ATTACKING a marked hero, +1{p}
    whittle_from_bone_blue    when this attacks a marked hero, EQUIP a token
    sedate_blue               when this hits a hero, create an Inertia token
                              UNDER THEIR CONTROL

THE TENSE MATTERS. Scuttle and Whittle say "WHEN this attacks", which is a
trigger that fires once. Plunge says "IF THIS IS ATTACKING", which is
continuous: remove the mark mid-combat and the +1{p} has to go with it. Written
as an ON_ATTACK pump, Plunge would keep the bonus after the state that granted
it ended, and nothing in a single-attack test would notice.

TWO DEFAULTS ARE WRONG FOR THESE CARDS AND SILENT ABOUT IT:

  * an Inertia token created under the CONTROLLER punishes the wrong hero --
    Sedate reads as removal and would play as self-harm;
  * a Graphene Chelicera created with no destination lands in the arena as a
    permanent instead of a weapon zone, where it can never be activated to
    attack, so "equip" would deliver nothing usable.

Stealth is printed on all four and comes from the card DB. Go again is printed
on Scuttle ONLY, so only Scuttle withdraws it; a declaration on the others
would take away a keyword they do not have.
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

MARKED = ["scuttle_the_canal_blue", "plunge_the_prospect_blue",
          "whittle_from_bone_blue"]


def _card(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _attacking(slug, marked=False, hero_target=True):
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="", **kw: o[0]      # noqa: E731
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    if marked:
        st.players[2].class_counters["marked"] = 1
    attacker = attack_with(st, _card(slug))
    if not hero_target:
        st.combat.attack_target = _card(slug, 2)   # a permanent, not the hero
    return st, attacker


def _fire(st, slug, attacker):
    run_ability(get_card(slug).abilities[0], attacker, None, st)


def _go_again(st):
    return "goagain" in {str(k).lower().replace(" ", "").replace("_", "")
                         for k in (st.combat.keywords or [])}


# ------------------------------------------------------------ the gate

@pytest.mark.parametrize("slug", MARKED)
def test_nothing_happens_against_an_unmarked_hero(slug):
    st, attacker = _attacking(slug, marked=False)
    before_weapons = len(st.players[1].weapon1.cards) + len(st.players[1].weapon2.cards)
    _fire(st, slug, attacker)
    assert not _go_again(st)
    assert recalculate_attack(st) == (attacker.base_power or 0)
    assert (len(st.players[1].weapon1.cards)
            + len(st.players[1].weapon2.cards)) == before_weapons


def test_scuttle_gets_go_again_against_a_marked_hero():
    st, attacker = _attacking("scuttle_the_canal_blue", marked=True)
    _fire(st, "scuttle_the_canal_blue", attacker)
    assert _go_again(st)


def test_plunge_pumps_against_a_marked_hero():
    st, attacker = _attacking("plunge_the_prospect_blue", marked=True)
    E._register_card_continuous_effects(st, attacker)
    assert recalculate_attack(st) == (attacker.base_power or 0) + 1


def test_plunge_loses_the_pump_if_the_mark_goes_away():
    """"IF THIS IS ATTACKING a marked hero" is continuous. An ON_ATTACK pump
    would survive the mark being removed, and a single-attack test would never
    see the difference."""
    st, attacker = _attacking("plunge_the_prospect_blue", marked=True)
    E._register_card_continuous_effects(st, attacker)
    assert recalculate_attack(st) == (attacker.base_power or 0) + 1
    st.players[2].class_counters.pop("marked", None)
    assert recalculate_attack(st) == (attacker.base_power or 0)


def test_whittle_equips_a_weapon_rather_than_making_a_permanent():
    """A token with no destination lands in the arena, where it can never be
    activated to attack -- so "equip" would deliver something unusable."""
    st, attacker = _attacking("whittle_from_bone_blue", marked=True)
    before = len(st.players[1].permanents.cards)
    _fire(st, "whittle_from_bone_blue", attacker)
    weapons = [c for z in (st.players[1].weapon1, st.players[1].weapon2)
               for c in z.cards]
    assert any(c.slug == "graphene_chelicera" for c in weapons), (
        "not equipped; weapon zones hold %s" % [c.slug for c in weapons])
    assert len(st.players[1].permanents.cards) == before, (
        "it went to the arena as a permanent instead")


@pytest.mark.parametrize("slug", MARKED)
def test_attacking_a_permanent_is_not_attacking_a_hero(slug):
    """combat.attack_target is set only for a non-hero target, so a card that
    forgot ATTACK_TARGET_IS_HERO would fire against a permanent too."""
    st, attacker = _attacking(slug, marked=True, hero_target=False)
    _fire(st, slug, attacker)
    assert not _go_again(st)


# -------------------------------------------------------------- sedate

def test_sedate_gives_the_token_to_the_hero_it_hit():
    st, attacker = _attacking("sedate_blue")
    st.combat.hit = True
    _fire(st, "sedate_blue", attacker)
    mine = [c.slug for c in st.players[1].permanents.cards]
    theirs = [c.slug for c in st.players[2].permanents.cards]
    assert "inertia" in theirs, "the opponent has %s" % theirs
    assert "inertia" not in mine, "it punished its own controller"


# ------------------------------------------------------- printed keywords

def test_only_scuttle_withdraws_a_printed_go_again():
    assert "GoAgain" in (DB.get("scuttle_the_canal_blue").keywords or [])
    assert "goagain" in conditional_keywords("scuttle_the_canal_blue")
    for slug in ("plunge_the_prospect_blue", "sedate_blue",
                 "whittle_from_bone_blue"):
        assert "GoAgain" not in (DB.get(slug).keywords or []), slug
        assert not conditional_keywords(slug), (
            slug + " withdraws a keyword it does not print")
