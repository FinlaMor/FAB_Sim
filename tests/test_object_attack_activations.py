"""Objects that are not weapons could not attack, and attack costs were free.

Two defects in the attack-proxy path, found by following the same thread as the
ON_HIT split.

NOTHING OFFERED AN ALLY'S ATTACK. CR 1.4.3b's own example is one: "Cintari
Sellsword has an attack-ability that produces an attack-proxy when activated."
Allies, demi-heroes and equipment carry "Action - <cost>: Attack" exactly as
weapons do. But _add_weapon_attacks iterates the two weapon zones and requires
card.is_weapon, _add_granted_permanent_attacks offers only permanents carrying
the GRANTED_ATTACK counter (the Iris of Reality grant), and
_add_hero_dsl_activations explicitly SKIPS any ability whose effect is an
attack — "handled by _add_weapon_attacks", which did not handle these. Three
cards with printed power and a parsed activation cost could not attack at all,
so every "when this attacks" trigger on them was unreachable.

THE ABILITY'S OWN COST WAS NEVER PAID. _apply_activate returns early for a
proxy attack, before the per-turn decrement and before any DSL cost. _pay_costs
handles resources and action points, not the clause before the colon. So Teklo
Plasma Pistol's "Remove a steam counter from Teklo Plasma Pistol: Attack" left
the counter on the pistol — the attack was free, and a weapon whose whole design
is a counter economy had none.

That one is a WEAPON, so it was reachable all along and simply not charged;
worth separating from the offer gap, because it means the defect predates any
question about allies.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.actions import Action, ActionType
from engine.card import Card, CardDB
from engine.card_effects.dsl.loader import load_all_cards
from engine.play import (apply_action, attack_ability_of, available_actions,
                         _attack_ability_costs_payable)
from engine.state import Step
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()


def _state():
    st = _make_state()
    st.card_db = DB
    st.active_player = 1
    st.step = Step.ACTION
    st.players[1].resources = 9
    st.players[1].action_points = 1
    return st


def _put(st, slug, zone):
    card = copy.deepcopy(DB.get(slug))
    card.owner = card.controller = 1
    getattr(st.players[1], zone).add(card)
    assert any(c is card for c in getattr(st.players[1], zone).cards), (
        "%s was rejected by the %s zone; the fixture is wrong, not the card"
        % (slug, zone))
    return card


def _soul(st, n):
    for i in range(n):
        c = Card(slug="soul_%d" % i, name="S%d" % i, raw_types=["Action"])
        c.types = ["Action"]
        c.owner = c.controller = 1
        st.players[1].soul.add(c)


def _attack_offers(st, slug):
    return [a for a in available_actions(st, 1)
            if getattr(a.card, "slug", None) == slug
            and getattr(a, "is_attack_proxy", False)]


# --- the offer ---------------------------------------------------------------

@pytest.mark.parametrize("slug,zone", [
    ("suraya_archangel_of_erudition", "allies"),
    ("gallow_end_of_the_line_yellow", "allies"),
    ("teklovossen_the_mechropotent", "permanents"),
])
def test_a_non_weapon_with_an_attack_ability_can_attack(slug, zone):
    st = _state()
    _put(st, slug, zone)
    _soul(st, 2)                      # teklovossen's cost; harmless for the rest
    assert _attack_offers(st, slug), (
        "%s prints an attack activation and nothing offered it" % slug)


def test_the_ally_attack_is_not_blocked_by_the_weapon_restriction():
    """`weapon_exhausted` is the once-per-turn WEAPON rule. An ally is not a
    weapon, and gating its attack on that would make one weapon attack switch
    off every ally on the board."""
    st = _state()
    _put(st, "suraya_archangel_of_erudition", "allies")
    st.players[1].weapon_exhausted = True
    assert _attack_offers(st, "suraya_archangel_of_erudition")


def test_an_unpayable_ability_cost_is_not_offered():
    """Teklovossen needs two cards in the soul. With an empty soul the attack is
    not a legal action — the same as an unaffordable resource cost."""
    st = _state()
    tek = _put(st, "teklovossen_the_mechropotent", "permanents")
    assert not _attack_ability_costs_payable(st, tek)
    assert not _attack_offers(st, "teklovossen_the_mechropotent")

    _soul(st, 2)
    assert _attack_offers(st, "teklovossen_the_mechropotent")


# --- the cost is actually paid ----------------------------------------------

def test_a_weapons_attack_cost_is_paid():
    """"Remove a steam counter from Teklo Plasma Pistol: Attack." The counter
    stayed on the pistol, so the attack was free. Counters live on the player,
    keyed by (slug, zone, kind) — which is what effect_put_counter writes."""
    st = _state()
    pistol = _put(st, "teklo_plasma_pistol", "weapon1")
    pistol.zone = "weapon1"
    st.players[1].counters[(pistol.slug, pistol.zone, "steam")] = 1

    offers = _attack_offers(st, "teklo_plasma_pistol")
    assert offers, "the pistol could not attack with a steam counter available"
    apply_action(st, offers[0])

    total = sum(v for k, v in st.players[1].counters.items() if k[2] == "steam")
    assert total == 0, "the steam counter was not removed: %s" % st.players[1].counters


def test_an_allys_attack_cost_is_paid():
    st = _state()
    _put(st, "teklovossen_the_mechropotent", "permanents")
    _soul(st, 3)

    offers = _attack_offers(st, "teklovossen_the_mechropotent")
    assert offers
    apply_action(st, offers[0])

    assert len(st.players[1].soul.cards) == 1, (
        "'banish 2 cards from your soul' did not take them: %s"
        % [c.slug for c in st.players[1].soul.cards])


def test_the_per_turn_limit_is_spent():
    """The proxy branch returned before the decrement, so a "Once per Turn
    Action - ...: Attack" could be activated again as soon as the offer was
    recomputed."""
    st = _state()
    suraya = _put(st, "suraya_archangel_of_erudition", "allies")
    assert suraya.has_per_turn_limit and suraya.activations == 1

    offers = _attack_offers(st, "suraya_archangel_of_erudition")
    assert offers
    apply_action(st, offers[0])

    assert suraya.activations == 0, "the once-per-turn use was not spent"


# --- the premise -------------------------------------------------------------

def test_these_cards_really_print_an_attack_ability():
    for slug in ("suraya_archangel_of_erudition", "gallow_end_of_the_line_yellow",
                 "teklovossen_the_mechropotent", "teklo_plasma_pistol"):
        assert attack_ability_of(DB.get(slug)) is not None, slug
        assert DB.get(slug).power is not None, slug


def test_gallow_taps_to_attack_rather_than_pitching_two_cards():
    """Its printed cost is "{r}, {t}". It was authored as a PITCH of 2, which
    charged two cards the card never asks for and never exhausted the ally, so
    the attack was repeatable. Same substitution as kayo_strong_arm."""
    ability = attack_ability_of(DB.get("gallow_end_of_the_line_yellow"))
    assert [c.cost_type for c in ability.costs] == ["TAP_SELF"]
    assert ability.params.get("activation_cost") == 1
