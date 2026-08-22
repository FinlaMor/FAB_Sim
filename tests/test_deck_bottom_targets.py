""""Put a card on the bottom of your deck" went to four different wrong places.

PUT_HAND_CARD_BOTTOM reads `player`, `to`, `optional` and `amount`. Four cards
named something else, and each landed somewhere different:

  disarm_yellow             "the ATTACKING HERO puts a card from their hand on
                            the bottom" used target:"opponent", which it does
                            not read, so it fell back to SELF: a card that
                            punishes the attacker punished its controller.
  sink_below_red            "IF YOU DO, draw a card" was a conditional_effect
                            key it does not read - the entire payoff half of
                            the card was absent.
  stacked_in_your_favor_red "ON TOP of your deck" used position:"top", so the
                            card went to the BOTTOM: the opposite end, and for
                            a card whose point is setting up the next draw, the
                            opposite effect.
  tough_smashup_blue        "your revealed card" is the CLASH reveal, not a
                            card in hand - the wrong zone and the wrong card.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.ability_keywords import DECLINE
from engine.card_effects.dsl.condition_types import compile_condition
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

ACTION = "brutal_assault_red"
OTHER = "autumns_touch_red"


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


def _stock(st, pid=1, n=4):
    for _ in range(n):
        st.players[pid].deck.add(_card(OTHER, pid))


def _run(slug, st, source=None, index=0):
    source = source or _card(slug)
    run_ability(get_card(slug).abilities[index], source, None, st)
    return source


# --- disarm_yellow ----------------------------------------------------------

def _disarm_state():
    st = _state()
    shield = _card("disarm_yellow", 1)
    st.combat = CombatState(attacker_id=2, link_id=1, attack_power=0,
                            attack_card=None, keywords=[])
    st.combat.defending_cards = [shield]
    for pid in (1, 2):
        st.players[pid].hand.add(_card(ACTION, pid))
        _stock(st, pid)
    return st, shield


def test_disarm_takes_a_card_from_the_attacker_not_its_controller():
    st, shield = _disarm_state()
    shield.defense = 6
    mine = st.players[1].hand.cards[0]
    theirs = st.players[2].hand.cards[0]

    _run("disarm_yellow", st, source=shield, index=1)

    assert theirs not in st.players[2].hand.cards, (
        "the attacking hero kept their card")
    assert mine in st.players[1].hand.cards, (
        "it took a card from its OWN controller's hand")


def test_disarm_does_nothing_below_six_defense():
    st, shield = _disarm_state()
    shield.defense = 5
    theirs = st.players[2].hand.cards[0]

    _run("disarm_yellow", st, source=shield, index=1)

    assert theirs in st.players[2].hand.cards


def test_the_gate_reads_defence_not_a_count_of_defence_counters():
    """It was COUNTER_GTE counter:"DEFENSE" amount:6 - six defence COUNTERS,
    which is zero on a fresh card and only rises when something DEBUFFS it. The
    gate was false exactly when the card is strong."""
    st, shield = _disarm_state()
    shield.defense = 6

    assert compile_condition("DEFENSE_GTE", {"amount": 6})(shield, None, st) is True
    old = compile_condition("COUNTER_GTE", {"counter": "DEFENSE", "amount": 6})
    assert old(shield, None, st) is False, (
        "the old gate was supposed to be blind to the card's actual {d}")


def test_the_attacker_cannot_decline():
    """"the attacking hero PUTS a card" is mandatory; it was optional, so the
    affected player could simply refuse."""
    st, shield = _disarm_state()
    shield.defense = 6
    st.player_agents[2] = lambda s, o, context="": (
        DECLINE if DECLINE in o else o[0])
    theirs = st.players[2].hand.cards[0]

    _run("disarm_yellow", st, source=shield, index=1)

    assert theirs not in st.players[2].hand.cards, "the attacker declined"


# --- sink_below_red ---------------------------------------------------------

def test_sink_below_draws_after_bottoming():
    st = _state()
    st.players[1].hand.add(_card(ACTION))
    _stock(st)
    before = len(st.players[1].hand.cards)

    _run("sink_below_red", st)

    assert len(st.players[1].hand.cards) == before, (
        "one card out, one card in - the draw half never happened")


def test_sink_below_does_not_draw_when_declined():
    """"You MAY ... IF YOU DO" - declining must not still draw."""
    st = _state(agent=lambda s, o, context="": (DECLINE if DECLINE in o else o[0]))
    kept = _card(ACTION)
    st.players[1].hand.add(kept)
    _stock(st)

    _run("sink_below_red", st)

    assert kept in st.players[1].hand.cards, "it bottomed a card anyway"
    assert len(st.players[1].hand.cards) == 1, "it drew after declining"


def test_sink_below_does_not_draw_on_an_empty_hand():
    st = _state()
    st.players[1].hand.cards = []
    _stock(st)

    _run("sink_below_red", st)

    assert st.players[1].hand.cards == [], "it drew with nothing to bottom"


# --- stacked_in_your_favor_red ----------------------------------------------

def test_stacked_puts_the_card_on_top_not_the_bottom():
    st = _state()
    st.players[1].permanents.add(_card("stacked_in_your_favor_red"))
    _stock(st)
    keeper = _card(ACTION)
    st.players[1].hand.add(keeper)

    _run("stacked_in_your_favor_red", st, index=1)

    deck = st.players[1].deck.cards
    assert keeper in deck, "the card never reached the deck"
    assert deck[0] is keeper, (
        f"it went to the bottom; top of deck is {deck[0].slug}")


# --- tough_smashup_blue -----------------------------------------------------

def test_smashup_gives_the_token_to_the_clash_winner():
    """"THE WINNER creates a Toughness token" - it was a bare CREATE_TOKEN
    after the clash, so the controller got it whoever won."""
    st = _state()
    st.combat = CombatState(attacker_id=2, link_id=1, attack_power=0,
                            attack_card=None, keywords=[])
    # Player 2 wins the clash: the higher printed cost on top wins, so the
    # OPPONENT gets the expensive card. Deliberately not the controller —
    # a controller win is indistinguishable from the bare CREATE_TOKEN this
    # replaces, and the test would pass either way.
    st.players[1].deck.add(_card("brutal_assault_red", 1))      # cost 2
    st.players[2].deck.add(_card("autumns_touch_red", 2))       # cost 3
    _stock(st, 1)
    _stock(st, 2)

    _run("tough_smashup_blue", st)

    mine = [c.slug for c in st.players[1].permanents.cards]
    theirs = [c.slug for c in st.players[2].permanents.cards]
    assert "toughness" in theirs, f"the winner got no token (theirs={theirs})"
    assert "toughness" not in mine, (
        f"the loser created a token as well (mine={mine})")


def test_smashup_does_not_bottom_a_card_from_hand():
    """"your REVEALED card" is the clash reveal, not a card in hand."""
    st = _state()
    st.combat = CombatState(attacker_id=2, link_id=1, attack_power=0,
                            attack_card=None, keywords=[])
    _stock(st, 1)
    _stock(st, 2)
    in_hand = _card(ACTION)
    st.players[1].hand.add(in_hand)

    _run("tough_smashup_blue", st)

    assert in_hand in st.players[1].hand.cards, (
        "it took a card out of hand instead of using the clash reveal")
