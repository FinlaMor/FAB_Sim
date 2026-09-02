"""Bonds of Ancestry: an unconditional keyword, an invented cost, and a
cost reduction that was a resource gain.

Printed: "**Combo** - If a card with Gustwave in its name was the last attack
this combat chain, this costs {r}{r} less to play, and HAS **go again** and
'When this attacks, you may banish a card with combo from your graveyard. ...'"

GO AGAIN IS GATED AND WAS UNCONDITIONAL. The card DB grants every printed
keyword, and conditional_keywords reported nothing for this card, so it had go
again whether or not the combo was live. This is the class the gated-keyword
sweeps were built for, still present on a card those sweeps did not reach —
they swept by PHRASING ("this gets go again"), and this card says "has go
again" inside a Combo clause.

"COSTS {r}{r} LESS TO PLAY" WAS A GAIN OF 2 RESOURCE POINTS ON RESOLUTION.
Different in both directions. A reduction applies when the cost is CHECKED, so
it changes what you can afford to play; a resolution-time gain leaves you paying
full price and then hands you two resources to spend on something else. The
project's own rule — costs must affect play legality — cuts the same way for
discounts.

AND AN ADDITIONAL COST OF PAY_LIFE 2 WAS INVENTED. The card says nothing about
life, and because costs block legality it made the card unplayable at 2 life or
less.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card import CardDB
from engine.card_effects.dsl.loader import (conditional_keywords, get_card,
                                            load_all_cards, _kw_key)
from tests.conftest import _make_state, owned_card

load_all_cards()
DB = CardDB()
SLUG = "bonds_of_ancestry_red"


def _state(last_attack=None):
    st = _make_state()
    st.card_db = DB
    st.active_player = 1
    st.players[1].resources = 9
    st.players[1].action_points = 1
    if last_attack is not None:
        # COMBO_CONTAINS reads state.chain_links[-1].attack_slug -- the RESOLVED
        # attacks, not the combat chain zone. A card sitting in the zone answers
        # nothing, which makes a working combo look broken.
        from engine.state import ChainLink
        st.chain_links.append(ChainLink(
            chainlink_id=1, attacker_id=1, attack_slug=last_attack,
            attack_power=4, net_damage=4, keywords=[], from_weapon=False,
            hit=True))
    return st


def _copy():
    import copy
    c = copy.deepcopy(DB.get(SLUG))
    c.owner = c.controller = 1
    return c


def _cost_of(st, card):
    from engine.actions import Action, ActionType
    from engine.play import _calculate_resource_cost
    return _calculate_resource_cost(
        st, Action(type=ActionType.PLAY_CARD, card=card, player_id=1))


# --- the gated keyword -------------------------------------------------------

def test_go_again_is_declared_conditional():
    """Stripped from the card DB's unconditional grant, so the JSON's gate is
    the only thing that can give it back."""
    kws = {_kw_key(k) for k in conditional_keywords(SLUG)}
    assert _kw_key("go again") in kws, (
        "go again is still granted unconditionally; the Combo clause is "
        "decoration and the card plays stronger than printed")


def test_the_gate_is_the_combo_condition():
    ab = get_card(SLUG).abilities[0]
    assert ab.ability_type.upper() == "WHILE_STATIC"
    types = [c.condition_type for c in ab.conditions]
    assert "SOURCE_IS_ATTACK" in types
    assert "COMBO_CONTAINS" in types, (
        "the keyword is granted without asking whether the combo is live")


# --- the cost reduction ------------------------------------------------------

def test_it_costs_two_less_after_a_gustwave():
    st = _state(last_attack="whelming_gustwave_red")
    assert _cost_of(st, _copy()) == 0, (
        "printed cost is 2 and the combo takes {r}{r} off")


def test_it_costs_full_price_without_the_combo():
    st = _state(last_attack="head_jab_red")
    assert _cost_of(st, _copy()) == 2


def test_it_costs_full_price_with_no_previous_attack():
    st = _state()
    assert _cost_of(st, _copy()) == 2


def test_the_discount_is_not_a_resource_gain():
    """A gain on resolution leaves you paying full price. Whatever else the
    card does, playing it must not hand its controller resources."""
    cd = get_card(SLUG)
    effects = [e.effect_type for a in cd.abilities for e in a.effects]
    assert "GAIN" in effects, "the keyword grant is gone"
    for a in cd.abilities:
        for e in a.effects:
            if e.effect_type == "GAIN":
                assert e.params.get("asset") is None, (
                    "the cost reduction is still modelled as an asset gain: %s"
                    % e.params)


# --- the invented cost -------------------------------------------------------

def test_there_is_no_life_cost():
    cd = get_card(SLUG)
    for a in cd.abilities:
        assert not [c for c in getattr(a, "additional_costs", [])], (
            "an additional cost the card does not print")
    assert not cd.play_cost, "a card-level cost the card does not print"


def test_it_is_playable_at_one_life():
    st = _state(last_attack="whelming_gustwave_red")
    st.players[1].life = 1
    card = _copy()
    st.players[1].hand.add(card)
    from engine.play import available_actions
    slugs = {getattr(a.card, "slug", None) for a in available_actions(st, 1)}
    assert SLUG in slugs, "an unprinted life cost is blocking a legal play"
