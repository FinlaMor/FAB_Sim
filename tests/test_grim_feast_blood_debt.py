"""Grim Feast, and what a printed keyword must NOT be re-implemented as.

Printed: "You may play this from your banished zone. If you do, it costs {r}{r}
less to play. / Gain 3{h} / **Blood Debt**"

What was authored: an additional_cost of PAY_LIFE 2, a GAIN of 3 health, and a
SET_FLAG BLOOD_DEBT_FLAG. Neither printed clause about the banished zone existed
at all, and the keyword was re-implemented as a cost.

THE COST IS THE SERIOUS PART. CR 8.3.11: "Blood debt means 'While this is in
your banished zone, at the beginning of your end phase, lose 1{h}'." It is a
triggered-static, it fires from the BANISHED zone, it costs 1 and not 2, and it
has nothing to do with playing the card. The engine already implements it
generically (ability_keywords.blood_debt, wired up in triggers.py), so the JSON
needed to say nothing about it whatsoever.

Modelling it as an additional_cost does not merely duplicate the keyword -- it
changes when the card can be played. Costs block play legality, by design and by
this project's rules, so Grim Feast was unplayable at 2 life or less. A card
whose entire purpose is to GAIN life could not be played by a player who needed
it. That is the exact failure mode of writing a payoff as a cost, arriving from
the opposite direction to the usual one.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card import CardDB
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.play import available_actions
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()
SLUG = "grim_feast_red"


def _state():
    st = _make_state()
    st.card_db = DB
    st.active_player = 1
    st.players[1].resources = 9
    st.players[1].action_points = 1
    return st


def _copy(pid=1):
    import copy
    c = copy.deepcopy(DB.get(SLUG))
    c.owner = c.controller = pid
    return c


def _cost_of(st, card, pid=1):
    from engine.actions import Action, ActionType
    from engine.play import _calculate_resource_cost
    return _calculate_resource_cost(
        st, Action(type=ActionType.PLAY_CARD, card=card, player_id=pid))


def test_it_can_be_played_from_the_banished_zone():
    st = _state()
    card = _copy()
    st.players[1].banished.add(card)
    card.is_public = True
    slugs = {getattr(a.card, "slug", None) for a in available_actions(st, 1)}
    assert SLUG in slugs, "the printed 'you may play this from your banished zone' does nothing"


def test_it_costs_two_less_from_banish_and_full_price_from_hand():
    st = _state()
    in_hand = _copy()
    st.players[1].hand.add(in_hand)
    in_banish = _copy()
    st.players[1].banished.add(in_banish)
    in_banish.is_public = True

    assert _cost_of(st, in_hand) == 3, "printed cost is 3"
    assert _cost_of(st, in_banish) == 1, (
        "the {r}{r} discount for playing from banish is missing")


def test_it_is_playable_at_low_life():
    """The invented PAY_LIFE 2 cost made a life-GAIN card unplayable by a player
    who needed the life. Costs block legality -- that is what they are for --
    so a cost the card does not print removes plays that are legal."""
    st = _state()
    card = _copy()
    st.players[1].hand.add(card)
    st.players[1].life = 1

    slugs = {getattr(a.card, "slug", None) for a in available_actions(st, 1)}
    assert SLUG in slugs, "an unprinted life cost is blocking a legal play"


def test_playing_it_does_not_charge_life():
    st = _state()
    cd = get_card(SLUG)
    play = [a for a in cd.abilities if a.ability_type.upper() == "PLAY"][0]
    assert not getattr(play, "additional_costs", []), (
        "Blood Debt is a triggered-static (CR 8.3.11), not a cost to play")


def test_blood_debt_is_not_re_implemented_in_the_json():
    """The keyword is printed and handled generically. A JSON that also models
    it is a second implementation that can disagree with the first -- and this
    one did, on amount, timing and zone at once."""
    assert "BloodDebt" in DB.get(SLUG).keywords
    cd = get_card(SLUG)
    effects = [e.effect_type for a in cd.abilities for e in a.effects]
    assert "PAY_LIFE" not in effects
    assert "SET_FLAG" not in effects


def test_it_still_gains_three_life():
    """The one clause that did work must survive the rewrite."""
    st = _state()
    card = _copy()
    st.players[1].life = 20
    from engine.card_effects.dsl.interpreter import run_ability
    cd = get_card(SLUG)
    play = [a for a in cd.abilities if a.ability_type.upper() == "PLAY"][0]
    run_ability(play, card, None, st)
    assert st.players[1].life == 23, (
        "gain 3 life, got %s" % st.players[1].life)
