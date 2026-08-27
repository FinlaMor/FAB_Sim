"""Charge (CR 8.5.29) — "if you've charged this turn".

Charge moves a card from hand to the hero's soul, and 8.5.29a says the player is
then considered to have charged. 65 cards touch the keyword; the two that ask
"if you've charged this turn" each read an invented CHARGED_THIS_TURN flag.

8.5.29b matters here: a card reaching the soul any OTHER way is not charging, so
the turn event is recorded inside charge() and nowhere else.
"""
import copy

import pytest

from engine.card import Card, CardDB
from engine.card_effects.dsl import dispatch
from engine.card_effects.dsl.condition_types import compile_condition
from engine.card_effects.dsl.loader import load_all_cards
from engine.effect_keywords import TURN_EVENT_MARKER, charge
from engine.state import CombatState
from tests.conftest import _card_json, _make_state

load_all_cards()
DB = CardDB()

MARKER = f"{TURN_EVENT_MARKER}charge"


def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    return st


def _card(slug, owner=1):
    base = DB.get(slug)
    assert base is not None, f"unknown slug {slug}"
    c = copy.deepcopy(base)
    c.owner = c.controller = owner
    return c


def _attacking(st, power=3, pid=1):
    """A real attack in combat. base_power MUST be set: _recalculate_attack_power
    computes from card.base_power, so a dummy with only `power` recalculates to 0
    and a correct buff looks like it did nothing."""
    atk = Card(slug="atk", name="atk", types=["Action"], subtypes=["Attack"])
    atk.owner = atk.controller = pid
    atk.power = atk.base_power = power
    atk.classes = ["Warrior"]
    st.combat = CombatState(attacker_id=pid, link_id=1, attack_power=power,
                            attack_card=atk, keywords=[])
    st.combat.base_attack_power = power
    return atk


def _hand_card(st, slug="fodder", pid=1):
    c = Card(slug=slug, name=slug, types=["Action"])
    c.owner = c.controller = pid
    st.players[pid].hand.add(c)
    return c


# --- the keyword -----------------------------------------------------------

def test_charge_moves_the_card_from_hand_to_soul():
    st = _state()
    c = _hand_card(st)
    charge(st, c, 1)
    assert c not in st.players[1].hand.cards
    assert c in st.players[1].soul.cards


def test_charge_records_the_turn_event():
    st = _state()
    c = _hand_card(st)
    assert MARKER not in st.players[1].current_turn_effects
    charge(st, c, 1)
    assert MARKER in st.players[1].current_turn_effects


def test_charge_records_against_the_charging_player_only():
    st = _state()
    c = _hand_card(st)
    charge(st, c, 1)
    assert MARKER not in st.players[2].current_turn_effects


def test_a_card_reaching_the_soul_another_way_is_not_charging():
    # CR 8.5.29b — only the charge effect counts. Putting a card into the soul
    # directly must NOT set the marker, or "if you've charged" would fire for
    # every soul-filling effect in the game.
    st = _state()
    c = _hand_card(st)
    st.players[1].hand.remove(c)
    st.players[1].soul.add(c)
    assert MARKER not in st.players[1].current_turn_effects


# --- the cards -------------------------------------------------------------

def test_resounding_courage_makes_no_token_without_a_charge():
    st = _state()
    card = _card("resounding_courage_yellow")
    _attacking(st)
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert [c for c in st.players[1].permanents.cards if c.slug == "courage"] == []


def test_resounding_courage_makes_a_token_after_charging():
    st = _state()
    charge(st, _hand_card(st), 1)
    card = _card("resounding_courage_yellow")
    _attacking(st)
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert len([c for c in st.players[1].permanents.cards if c.slug == "courage"]) == 1


def test_resounding_courage_still_buffs_the_attack_without_a_charge():
    # The card's MAIN effect was missing entirely — only the conditional token
    # was implemented, so an uncharged turn did nothing at all.
    st = _state()
    card = _card("resounding_courage_yellow")
    _attacking(st)
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    import engine.engine as E
    E._recalculate_attack_power(st)
    assert st.combat.attack_power == 5


def test_lumina_queues_a_turn_long_weapon_buff():
    st = _state()
    card = _card("lumina_ascension_yellow")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert getattr(st.players[1], "turn_attack_hooks", []), \
        "the weapon buff queued nothing"


# --- migration guard -------------------------------------------------------

@pytest.mark.parametrize("slug", ["resounding_courage_yellow", "lumina_ascension_yellow"])
def test_no_invented_flags_remain(slug):
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "engine" / "card_effects" / "json"
    path = _card_json(root, f"{slug}.json")
    abilities = json.dumps(json.loads(path.read_text(encoding="utf-8"))["abilities"])
    assert "CHARGED_THIS_TURN" not in abilities
    # Specialization is a META-STATIC deckbuilding restriction (CR 8.3.7),
    # never an in-game condition, so it must not appear as one.
    assert "SPECIALIZATION" not in abilities.upper()
