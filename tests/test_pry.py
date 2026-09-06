"""Pry — a reveal whose follow-up choice belongs to the other player.

    "Target hero reveals 2 cards from their hand. If Pry is played during an
     opponent's turn, instead they reveal all cards in their hand.
     You may choose a card revealed this way. If you do, that hero puts it on
     the bottom of their deck then draws a card."

It was on test_invented_refs.py's KNOWN_UNFIXED, reading refs REVEALED_CARDS and
SELECTED_CARD via REVEAL_HAND_MARK_IF_TYPE -- which reveals the whole hand and
MARKS, storing nothing and ignoring `amount`. Neither the count nor the choice
worked.

TWO PLAYERS MAKE TWO DIFFERENT CHOICES here, and conflating them is invisible in
the resulting board: the hand's OWNER picks what to reveal, and PRY'S CONTROLLER
picks what to bottom. SELECT_FROM_ZONE defaults to asking the source's
controller, so the reveal passes chooser:OWNER.

COUNTS ARE A USELESS ASSERTION for this card: bottom-then-draw is net neutral,
so hand and deck sizes are unchanged whether or not anything happened. The tests
below read the deck BOTTOM instead, which is the only thing that distinguishes
the branches.
"""
import copy

import pytest

from engine.card import CardDB
from engine.card_effects.dsl import dispatch
from engine.card_effects.dsl.loader import load_all_cards
from scripts.talishar_attack_replay import _accepting_agent, _replay_agent
from tests.conftest import _make_state
import engine.engine as E

load_all_cards()
DB = CardDB()

IN_HAND = "head_jab_red"        # what the opponent holds
IN_DECK = "surging_strike_red"  # what sits on the bottom already


def _play(agent, my_turn=True, hand=3, deck=3):
    st = _make_state()
    st.card_db = DB
    st.active_player = 1 if my_turn else 2
    st.player_agents = {1: agent, 2: agent}
    E._setup_dsl_listeners(st)
    for _ in range(hand):
        c = copy.deepcopy(DB.get(IN_HAND))
        c.owner = c.controller = 2
        st.players[2].hand.add(c)
    for _ in range(deck):
        c = copy.deepcopy(DB.get(IN_DECK))
        c.owner = c.controller = 2
        st.players[2].deck.add(c)
    card = copy.deepcopy(DB.get("pry_yellow"))
    card.owner = card.controller = 1
    dispatch(st, "ON_PLAY", "pry_yellow", card=card, event=None)
    return st


def _bottom(st):
    return st.players[2].deck.cards[-1].slug if st.players[2].deck.cards else None


@pytest.mark.parametrize("my_turn", [True, False])
def test_taking_a_revealed_card_bottoms_it(my_turn):
    """A HAND card ends up on the bottom of their deck. Both turn branches, so
    the "reveal all on their turn" path is covered too."""
    st = _play(_accepting_agent, my_turn=my_turn)
    assert _bottom(st) == IN_HAND


@pytest.mark.parametrize("my_turn", [True, False])
def test_declining_leaves_the_deck_alone(my_turn):
    """"You MAY choose" -- declining must bottom nothing. The deck bottom is
    still the card that was already there."""
    st = _play(_replay_agent, my_turn=my_turn)
    assert _bottom(st) == IN_DECK


def test_the_reveal_count_does_not_limit_the_choice_on_their_turn():
    """On the opponent's turn the reveal is ALL, not 2. With a hand larger than
    2 the effect must still work -- an `amount` of "ALL" resolving to 0 made the
    whole selection silently pick nothing, which looked exactly like a decline.
    """
    st = _play(_accepting_agent, my_turn=False, hand=5)
    assert _bottom(st) == IN_HAND


def test_bottom_and_draw_leave_the_counts_unchanged():
    """Net neutral by design -- documented so a future reader does not "fix" a
    passing count assertion into a false one."""
    st = _play(_accepting_agent)
    assert len(st.players[2].hand.cards) == 3
    assert len(st.players[2].deck.cards) == 3
