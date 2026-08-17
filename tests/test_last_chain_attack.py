"""Combo / "last attack this combat chain" cards.

Every card here was DEAD: each read a private flag (SURGING_STRIKE_LAST_ATTACK,
LEG_TAP_LAST_ATTACK, LAST_ATTACK_WAS_DRACONIC, LAST_ATTACK_HIT, ...) that nothing
in the engine ever set, so the Combo clause could never fire.

`ChainLink` already captured everything needed — attack_slug, hit, talents,
classes, subtypes — so this needed a condition, not new engine state.

The NEGATIVE cases carry most of the weight: a condition that is always true
would satisfy every positive assertion here just as well as a correct one.
"""
import copy

import pytest

from engine.card import CardDB, Card
from engine.card_effects.dsl import dispatch
from engine.card_effects.dsl.loader import load_all_cards
from engine.state import ChainLink, CombatState
from tests.conftest import _make_state
import engine.engine as E

load_all_cards()
DB = CardDB()


def _state():
    st = _make_state()
    st.card_db = DB
    return st


def _card(slug, owner=1):
    base = DB.get(slug)
    assert base is not None, f"unknown slug {slug}"
    c = copy.deepcopy(base)
    c.owner = c.controller = owner
    return c


def _push_link(st, slug="dummy_attack", hit=True, talents=(), classes=(), subtypes=()):
    """Append a resolved chain link — the engine appends one after each attack's
    damage resolves, so during the NEXT attack this is 'the last attack'."""
    st.chain_links.append(ChainLink(
        chainlink_id=len(st.chain_links) + 1, attacker_id=1, attack_slug=slug,
        attack_power=3, net_damage=3 if hit else 0, keywords=[], from_weapon=False,
        hit=hit, talents=list(talents), classes=list(classes), subtypes=list(subtypes)))


def _attack(st, card):
    """Declare `card` as the attacking card and fire ON_ATTACK."""
    bp = getattr(card, "power", None) or 0
    st.combat = CombatState(attacker_id=1, link_id=len(st.chain_links) + 1,
                            attack_power=bp, attack_card=card, keywords=[])
    st.combat.base_attack_power = bp
    dispatch(st, "ON_ATTACK", card.slug, card=card, event=None)
    E._recalculate_attack_power(st)
    return st.combat


# --- named Combo -----------------------------------------------------------

def test_blackout_kick_gets_plus_3_after_rising_knee_thrust():
    st = _state()
    _push_link(st, "rising_knee_thrust_blue")
    card = _card("blackout_kick_yellow")
    base = card.power or 0
    combat = _attack(st, card)
    assert combat.attack_power == base + 3


def test_blackout_kick_gets_nothing_after_a_different_attack():
    st = _state()
    _push_link(st, "wounding_blow_red")
    card = _card("blackout_kick_yellow")
    base = card.power or 0
    combat = _attack(st, card)
    assert combat.attack_power == base


def test_blackout_kick_gets_nothing_as_the_first_attack():
    # No previous link at all: "was the last attack" must be false, not crash.
    st = _state()
    card = _card("blackout_kick_yellow")
    base = card.power or 0
    combat = _attack(st, card)
    assert combat.attack_power == base


def test_combo_matches_any_colour_printing_of_the_named_card():
    # "Rising Knee Thrust" names the CARD, so a red/yellow printing must satisfy
    # it too — matching the blue slug alone would silently miss two thirds.
    st = _state()
    _push_link(st, "rising_knee_thrust_red")
    card = _card("blackout_kick_yellow")
    base = card.power or 0
    combat = _attack(st, card)
    assert combat.attack_power == base + 3


def test_rising_knee_thrust_gets_plus_2_after_leg_tap():
    st = _state()
    _push_link(st, "leg_tap_blue")
    card = _card("rising_knee_thrust_blue")
    base = card.power or 0
    combat = _attack(st, card)
    assert combat.attack_power == base + 2


# --- talent Combo ----------------------------------------------------------

def test_grow_claws_gets_plus_1_after_a_draconic_attack():
    st = _state()
    _push_link(st, "some_dragon_attack", talents=["Draconic"])
    card = _card("grow_claws_blue")
    base = card.power or 0
    combat = _attack(st, card)
    assert combat.attack_power == base + 1


def test_grow_claws_gets_nothing_after_a_non_draconic_attack():
    st = _state()
    _push_link(st, "some_ninja_attack", talents=["Elemental"])
    card = _card("grow_claws_blue")
    base = card.power or 0
    combat = _attack(st, card)
    assert combat.attack_power == base


# --- hit Combo -------------------------------------------------------------

def test_push_the_point_gets_plus_2_when_the_last_attack_hit():
    st = _state()
    _push_link(st, "wounding_blow_red", hit=True)
    card = _card("push_the_point_yellow")
    base = card.power or 0
    combat = _attack(st, card)
    assert combat.attack_power == base + 2


def test_push_the_point_gets_nothing_when_the_last_attack_missed():
    st = _state()
    _push_link(st, "wounding_blow_red", hit=False)
    card = _card("push_the_point_yellow")
    base = card.power or 0
    combat = _attack(st, card)
    assert combat.attack_power == base


# --- the migration did not quietly drop the gate ---------------------------

@pytest.mark.parametrize("slug", [
    "whelming_gustwave_red", "grow_wings_blue", "grow_claws_blue",
    "rising_knee_thrust_blue", "blackout_kick_yellow",
    "vengeance_never_rests_blue", "push_the_point_yellow",
])
def test_migrated_cards_keep_a_real_condition(slug):
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "engine" / "card_effects" / "json"
    raw = next(root.rglob(f"{slug}.json")).read_text(encoding="utf-8")
    assert "FLAG_SET" not in raw, f"{slug} still reads an invented flag"
    assert "LAST_CHAIN_ATTACK" in raw, f"{slug} lost its Combo gate entirely"
    json.loads(raw)


def test_vengeance_no_longer_banishes_the_hero():
    # The previous implementation modelled "banish it" (the attack) as
    # BANISH target 'hero'. That clause is not expressible yet, and doing the
    # wrong thing is worse than doing nothing.
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "engine" / "card_effects" / "json"
    raw = next(root.rglob("vengeance_never_rests_blue.json")).read_text(encoding="utf-8")
    assert '"target": "hero"' not in raw
    assert "NEEDS_NEW_DSL" in raw, "the unexpressible clause must stay documented"
