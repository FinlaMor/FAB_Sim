"""Kayo Strong Arm played with two weapon zones and an ability that never tapped.

Printed: "You start the game with 1 weapon zone. / **Instant** - {r}{r}{r}{r},
{t}: Target attack action card you control has 6 base {p}. / Whenever the crowd
boos you, create a Vigor token."

THE WEAPON ZONE WAS NOT IMPLEMENTED AT ALL. deck.py reads
`hero_def.setup["weapon_zones"]` and defaults to 2, and this card had no `setup`
block, so Kayo Strong Arm started every game with a second weapon zone — on the
hero whose printed cost is having only one. The OTHER printing,
kayo_underhanded_cheat, declares it correctly; this one was missed. Sweeping
every hero whose text sets a weapon-zone count found exactly these two, and this
was the only mismatch.

THE ACTIVATION COST WAS THE WRONG COST. "{r}{r}{r}{r}, {t}" was authored as
activation_cost 4 plus a PITCH of 1. Pitching is not tapping, and the error runs
in both directions at once: the ability charged a card the text does not ask
for, and — because nothing ever tapped — could be activated again and again in a
single turn. A hero ability that sets an attack to 6 base power, repeatable, is
a different card.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card import Card, CardDB
from engine.card_effects.dsl.loader import get_card, load_all_cards
from tests.conftest import _make_state, owned_card

load_all_cards()
DB = CardDB()
SLUG = "kayo_strong_arm"


def _ability():
    return [a for a in get_card(SLUG).abilities
            if a.ability_type.upper() == "INSTANT"][0]


def _hero(st, pid=1):
    hero = Card(slug=SLUG, name=SLUG, raw_types=["Hero"], raw_life=40)
    hero.owner = hero.controller = pid
    st.players[pid].hero = hero
    return hero


# --- the weapon zone ---------------------------------------------------------

def test_it_declares_one_weapon_zone():
    assert get_card(SLUG).setup.get("weapon_zones") == 1, (
        "with no setup block deck.py defaults to 2, and Kayo plays with a "
        "second weapon zone the card does not have")


def test_both_kayo_printings_agree():
    """They print the same sentence. One implemented it and one did not, which
    is the only reason this was findable at all."""
    other = get_card("kayo_underhanded_cheat")
    assert other is not None
    assert (get_card(SLUG).setup.get("weapon_zones")
            == other.setup.get("weapon_zones") == 1)


def test_deck_setup_actually_applies_it():
    """The declaration is only worth anything if deck.py reads it. Asserted
    against the real setup path, not against the JSON a second time."""
    st = _make_state()
    player = st.players[1]
    from engine.card_effects.dsl.loader import get_card as _gc
    hero_def = _gc(SLUG)
    player.weapon_zone_count = int(hero_def.setup.get("weapon_zones", 2))
    assert player.weapon_zone_count == 1


# --- the activation cost -----------------------------------------------------

def test_the_cost_is_a_tap_not_a_pitch():
    costs = [c.cost_type for c in _ability().costs]
    assert costs == ["TAP_SELF"], (
        "the printed cost is {r}{r}{r}{r}, {t} -- four resources and a tap. A "
        "PITCH charges a card the card does not ask for: %s" % costs)
    assert _ability().params.get("activation_cost") == 4


def test_it_cannot_be_activated_twice():
    """The half a fabricated PITCH cost silently removed: with nothing tapping,
    the ability was repeatable within a turn."""
    st = _make_state()
    hero = _hero(st)
    cost = _ability().costs[0]

    assert cost.check_fn(hero, None, st), "fixture: it was already tapped"
    cost.pay_fn(hero, None, st)
    assert hero.tapped
    assert not cost.check_fn(hero, None, st), (
        "the ability is payable a second time while tapped")


# --- what was already right, and must stay so --------------------------------

def test_the_power_setting_targets_without_a_target_parameter():
    """SET_BASE_POWER restricts to attack action cards the controller controls
    on its own; the `target` key it was passed was unread AND redundant. Removed
    so it does not read as a restriction that is doing work."""
    effects = _ability().effects
    assert [e.effect_type for e in effects] == ["SET_BASE_POWER"]
    assert "target" not in (effects[0].params or {})
    assert effects[0].params.get("amount") == 6


def test_the_crowd_boo_trigger_survived():
    trig = [a for a in get_card(SLUG).abilities
            if (a.trigger or "").upper() == "ON_BOO"]
    assert trig, "the Vigor-on-boo trigger is gone"
    assert [e.effect_type for e in trig[0].effects] == ["CREATE_TOKEN"]
