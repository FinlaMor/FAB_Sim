""""If an item or equipment was banished from boosting this, this gets +1{p}."

Both Sprocket Rocket printings had this as a plain STATIC, which nothing
dispatches, so the pump never applied. The condition was worse than the dead
dispatch: CONTROLS_TOKEN_TYPE with token_type "ITEM_OR_EQUIPMENT" — an invented
token type, and controlling a token has nothing to do with what boosting
banished.

CARD_WAS_BOOSTED could not have answered it either: it says only THAT a boost
happened, not what it banished, so it would fire on any boost at all. boost()
now records the banished cards on the card it boosted — the same reason
was_boosted lives there rather than in turn state, since a turn marker cannot
tell one attack's boost from another's.

Both directions are tested: an item boost pumps, a non-item boost does not.
A one-sided test would pass on CARD_WAS_BOOSTED, which is the wrong condition.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.loader import load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

ROCKET = "sprocket_rocket_blue"


def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    return st


def _card(slug, owner=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = owner
    return c


def _attack_power(st, card):
    power = card.base_power or 0
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=power,
                            attack_card=card, keywords=[])
    st.combat.base_attack_power = power
    E._apply_turn_attack_effects(st, card)
    E._register_card_continuous_effects(st, card)
    E._recalculate_attack_power(st)
    return st.combat.attack_power


def _boosted_with(slug, banished_types):
    card = _card(ROCKET)
    banished = _card("wounded_bull_red")
    banished.types = list(banished_types)
    card.was_boosted = True
    card.boost_banished = [banished]
    return card


def test_an_item_boost_pumps_the_attack():
    st = _state()
    card = _boosted_with(ROCKET, ["Item"])
    assert _attack_power(st, card) == (card.base_power or 0) + 1


def test_an_equipment_boost_pumps_the_attack():
    st = _state()
    card = _boosted_with(ROCKET, ["Equipment"])
    assert _attack_power(st, card) == (card.base_power or 0) + 1


def test_a_boost_that_banished_something_else_does_not_pump():
    """The half CARD_WAS_BOOSTED would get wrong."""
    st = _state()
    card = _boosted_with(ROCKET, ["Action"])
    assert _attack_power(st, card) == (card.base_power or 0), (
        "it pumped on a boost that banished no item or equipment")


def test_an_unboosted_attack_does_not_pump():
    st = _state()
    card = _card(ROCKET)
    assert _attack_power(st, card) == (card.base_power or 0)


def test_boost_records_what_it_banished():
    """The engine half: boost() marks the banished card on the boosted card."""
    from engine.card_effects.ability_keywords import boost

    st = _state()
    card = _card(ROCKET)
    top = _card("wounded_bull_red")
    top.types = ["Item"]
    st.players[1].deck.cards = [top]
    st.player_agents[1] = lambda s, o, context="": True   # accept the boost

    assert boost(card, st) in (True, False)     # Mechanologist-ness is not the point
    assert getattr(card, "boost_banished", None), "boost recorded nothing"
    assert card.boost_banished[0].slug == top.slug


def test_the_pump_is_confined_to_its_own_attack():
    """SOURCE_IS_ATTACK: the recalculation reaches every permanent, so without
    it a boosted Sprocket Rocket in the arena would buff someone else's attack."""
    st = _state()
    rocket = _boosted_with(ROCKET, ["Item"])
    st.players[1].permanents.cards.append(rocket)

    other = _card("wounded_bull_red")
    assert _attack_power(st, other) == (other.base_power or 0), (
        "a boosted Sprocket Rocket in the arena buffed an unrelated attack")
