"""Riptide's two abilities, and the two mechanics they needed.

"Whenever a TRAP you control TRIGGERS" had no event. CR 8.2.7 retired trap as a
functional subtype keyword, so there is no trap machinery to hang one on: a trap
is an ordinary card - in practice a Defense Reaction - that carries the Trap
subtype, and "triggers" means one of its abilities actually RESOLVES.
ON_TRAP_TRIGGER is therefore dispatched from interpreter._run_ability, past the
target filter, the costs, the conditions and the once-per-turn gate, so a trap
whose condition FAILED does not count as having triggered.

"You may put a card from hand FACE DOWN into your arsenal" had been removed from
the card entirely: it was authored as PUT_CARDS_BOTTOM, which bottom-decks the
whole hand and reads none of amount/face_down/destination - it would have
destroyed the player's hand on every card played.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.ability_keywords import NO
from engine.card_effects.dsl.effect_types import compile_effect
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

# A real Defense Reaction carrying the Trap subtype, with a triggered ability.
TRAP = "inertia_trap_red"
PLAIN = "brutal_assault_red"


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
    return st


def _with_riptide(st, pid=1):
    hero = _card("riptide", pid)
    st.players[pid].hero = hero
    return hero


# --- ON_TRAP_TRIGGER --------------------------------------------------------

def test_the_trap_subtype_is_what_the_engine_keys_on():
    trap = _card(TRAP)
    assert any(t.lower() == "trap" for t in (trap.subtypes or [])), (
        f"{TRAP} was chosen because it carries the Trap subtype; it now has "
        f"{trap.subtypes} and this file tests nothing")


def test_a_resolving_trap_ability_damages_the_attacking_hero():
    st = _state()
    _with_riptide(st)
    trap = _card(TRAP)
    st.combat = CombatState(attacker_id=2, link_id=1, attack_power=9,
                            attack_card=_card(PLAIN, 2), keywords=[])
    st.combat.defending_cards = [trap]
    before = st.players[2].life

    for ability in get_card(TRAP).abilities:
        run_ability(ability, trap, None, st)

    assert st.players[2].life == before - 1, (
        f"the attacking hero took no damage from the trap trigger "
        f"({st.players[2].life} vs {before})")


def test_a_non_trap_ability_does_not_fire_it():
    st = _state()
    _with_riptide(st)
    plain = _card("shining_courage_red")
    st.combat = CombatState(attacker_id=2, link_id=1, attack_power=0,
                            attack_card=None, keywords=[])
    st.combat.defending_cards = [plain]
    before = st.players[2].life

    for ability in get_card("shining_courage_red").abilities:
        run_ability(ability, plain, None, st)

    assert st.players[2].life == before, (
        "a card with no Trap subtype counted as a trap triggering")


def test_a_trap_whose_condition_fails_has_not_triggered():
    """The dispatch sits past every gate: matching is not triggering."""
    st = _state()
    _with_riptide(st)
    trap = _card(TRAP)
    # No combat at all, so the trap's own defend conditions cannot hold.
    st.combat = None
    before = st.players[2].life

    for ability in get_card(TRAP).abilities:
        run_ability(ability, trap, None, st)

    assert st.players[2].life == before, (
        "a trap whose ability did not resolve still counted as triggering")


def test_the_payoff_needs_riptide_on_the_board():
    st = _state()          # no hero set
    trap = _card(TRAP)
    st.combat = CombatState(attacker_id=2, link_id=1, attack_power=9,
                            attack_card=_card(PLAIN, 2), keywords=[])
    st.combat.defending_cards = [trap]
    before = st.players[2].life

    for ability in get_card(TRAP).abilities:
        run_ability(ability, trap, None, st)

    assert st.players[2].life == before


# --- hand -> arsenal, face down ---------------------------------------------

def test_a_card_moves_from_hand_into_the_arsenal_face_down():
    st = _state()
    hero = _with_riptide(st)
    held = _card(PLAIN)
    st.players[1].hand.add(held)

    run_ability(get_card("riptide").abilities[0], hero, None, st)

    assert held in st.players[1].arsenal.cards, "it never reached the arsenal"
    assert held not in st.players[1].hand.cards, "it is still in hand as well"
    assert held.is_public is False, "the card was put in FACE UP"


def test_the_player_may_decline():
    st = _state(agent=lambda s, o, context="": NO if NO in o else o[0])
    hero = _with_riptide(st)
    held = _card(PLAIN)
    st.players[1].hand.add(held)

    run_ability(get_card("riptide").abilities[0], hero, None, st)

    assert held in st.players[1].hand.cards, "\"you MAY\" moved it anyway"


def test_it_does_not_empty_the_hand():
    """The removed authoring was PUT_CARDS_BOTTOM, which moves EVERY card in
    the zone - on every card played."""
    st = _state()
    hero = _with_riptide(st)
    for _ in range(4):
        st.players[1].hand.add(_card(PLAIN))
    before = len(st.players[1].hand.cards)

    run_ability(get_card("riptide").abilities[0], hero, None, st)

    assert len(st.players[1].hand.cards) == before - 1, (
        f"expected one card to move, {before - len(st.players[1].hand.cards)} did")
    assert st.players[1].deck.cards == [] or all(
        c not in st.players[1].deck.cards for c in st.players[1].hand.cards), (
        "cards went to the deck rather than the arsenal")


def test_a_full_arsenal_keeps_the_card_in_hand():
    st = _state()
    hero = _with_riptide(st)
    sitting = _card(PLAIN)
    st.players[1].arsenal.add(sitting)
    held = _card("shining_courage_red")
    st.players[1].hand.add(held)

    run_ability(get_card("riptide").abilities[0], hero, None, st)

    assert sitting in st.players[1].arsenal.cards, "it evicted the arsenal card"
    assert held in st.players[1].hand.cards


def test_the_effect_reaches_hand_and_not_only_the_deck():
    """PUT_INTO_ARSENAL only knew DECK_TOP and a ref before this."""
    st = _state()
    source = _card("riptide")
    held = _card(PLAIN)
    st.players[1].hand.add(held)
    top = _card("shining_courage_red")
    st.players[1].deck.add(top)

    compile_effect("PUT_INTO_ARSENAL",
                   {"from": "HAND", "player": "SELF", "face_up": False})(
        source, None, st)

    assert held in st.players[1].arsenal.cards
    assert top in st.players[1].deck.cards, "it took the deck's top card instead"
