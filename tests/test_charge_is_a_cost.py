"""A cost modelled as an effect makes the ability legal when it cannot be paid.

v_for_valor_yellow: "**Attack Reaction** - {r}, destroy this, **charge** your
hero's soul: Target attack gains +2{p}."

The charge is part of the COST. Authored as an ON_PLAY effect it did two wrong
things at once:

  legality  the reaction was activatable with an EMPTY HAND. The ability
            resolved, the attack got its +2{p}, and the cost was simply never
            paid -- the one thing a cost must never allow.
  choice    CHARGE took `hand.cards[0]`. Nobody chose, so a player could lose
            the card they most wanted to keep. Same shape as the discard that
            took hand position 0.

CR 8.5.29: to charge a card, move it from the player's hand to their hero's
soul. 8.5.29b: moving a card to the soul by any other route is NOT charging,
which is why this goes through effect_keywords.charge rather than a zone move.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.cost_types import compile_cost
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

PLAIN = "brutal_assault_red"
OTHER = "amplifying_arrow_yellow"


def _card(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _state(agent=None):
    st = _make_state()
    st.card_db = DB
    pick = agent or (lambda s, o, context="": o[0])
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    st.individual_turns = 1
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=_card(PLAIN, 1), keywords=[])
    return st


def _charge_cost(amount=1):
    return compile_cost("CHARGE", {"amount": amount})


# --- legality ---------------------------------------------------------------

def test_an_empty_hand_cannot_pay():
    """The whole point of modelling it as a cost."""
    st = _state()
    can_pay, _pay = _charge_cost()

    assert can_pay(_card("v_for_valor_yellow"), None, st) is False


def test_a_card_in_hand_can_pay():
    st = _state()
    st.players[1].hand.add(_card(PLAIN))
    can_pay, _pay = _charge_cost()

    assert can_pay(_card("v_for_valor_yellow"), None, st) is True


def test_the_cost_is_on_the_ability_not_in_its_effects():
    """A charge in `effects` resolves after the ability is already legal."""
    ability = get_card("v_for_valor_yellow").abilities[0]
    costs = [type(c).__name__ for c in (getattr(ability, "costs", None) or [])]
    assert costs, "the ability declares no costs at all"

    import json
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    raw = json.loads(next(root.rglob("v_for_valor_yellow.json"))
                     .read_text(encoding="utf-8"))
    ab = raw["abilities"][0]
    assert any(c.get("type") == "CHARGE" for c in ab.get("cost", [])), ab
    assert not any(e.get("type") == "CHARGE" for e in ab.get("effects", [])), (
        "the charge is still authored as an effect")


# --- paying it moves the chosen card to the soul ----------------------------

def test_paying_puts_the_card_into_the_soul():
    st = _state()
    held = _card(PLAIN)
    st.players[1].hand.add(held)
    _can, pay = _charge_cost()

    pay(_card("v_for_valor_yellow"), None, st)

    assert held in st.players[1].soul.cards, f"it is in {held.zone!r}"
    assert held not in st.players[1].hand.cards


def test_the_player_chooses_which_card():
    """It took hand position 0 with nobody choosing."""
    st = _state(agent=lambda s, o, context="": OTHER if OTHER in o else o[0])
    first = _card(PLAIN)
    wanted = _card(OTHER)
    st.players[1].hand.add(first)
    st.players[1].hand.add(wanted)
    _can, pay = _charge_cost()

    pay(_card("v_for_valor_yellow"), None, st)

    assert wanted in st.players[1].soul.cards, "the choice was ignored"
    assert first in st.players[1].hand.cards, "it charged hand position 0"


def test_paying_with_an_empty_hand_charges_nothing():
    st = _state()
    _can, pay = _charge_cost()

    pay(_card("v_for_valor_yellow"), None, st)

    assert st.players[1].soul.cards == []


# --- the payoff still works -------------------------------------------------

def test_the_reaction_still_adds_its_power():
    st = _state()
    st.players[1].hand.add(_card(PLAIN))
    before = st.combat.attack_power

    run_ability(get_card("v_for_valor_yellow").abilities[0],
                _card("v_for_valor_yellow"), None, st)

    assert st.combat.attack_power == before + 2


def test_resolving_the_ability_does_not_charge_a_second_card():
    """The charge belongs to the cost; running the effects must not repeat it."""
    st = _state()
    st.players[1].hand.add(_card(PLAIN))
    st.players[1].hand.add(_card(OTHER))

    run_ability(get_card("v_for_valor_yellow").abilities[0],
                _card("v_for_valor_yellow"), None, st)

    assert st.players[1].soul.cards == [], (
        "the effects charged a card as well as the cost")
