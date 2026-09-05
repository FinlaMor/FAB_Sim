"""Rotten Remains — an optional cost, "if you do", and a real repeat.

    "When this attacks, you may banish a card with 1{p} from each hero's
     graveyard. If you do, this gets +1{p}, then repeat this process."

The previous implementation had no MAY and hung MODIFY_ATTACK off the trigger as
a SIBLING of the banish, so the +1{p} applied whether or not anything was
banished and whether or not the player wanted it. The card was strictly stronger
than printed and "if you do" was not modelled at all — the costs-vs-effects
class. It read 0/25 against the spectator corpus and 1/3 against built states.

Three separate things have to hold, and each has a negative case here, because
an implementation that simply always pumps satisfies every positive one:

  * declining pumps nothing
  * EACH hero's graveyard — one side alone is not payment
  * "then repeat" really loops, and stops when either graveyard runs dry

`back_stab_blue` is the fuel: a real 1-power card. NOT a token — a token ceases
to exist on entry to a graveyard (CR 3.0.12a), so stocking one leaves the zone
empty and every assertion here would pass for the wrong reason.
"""
import copy

import pytest

from engine.card import CardDB
from engine.card_effects.dsl.loader import load_all_cards
from engine.state import Step
from scripts.talishar_attack_replay import (_accepting_agent, _replay_agent,
                                            our_power)
from tests.conftest import _make_state
import engine.engine as E

load_all_cards()
DB = CardDB()

CARD = "rotten_remains_blue"
FUEL = "back_stab_blue"          # a real card with 1{p}


def _board(agent, mine=(), theirs=()):
    st = _make_state()
    st.card_db = DB
    st.step = Step.ACTION
    st.active_player = 1
    st.combat = None
    st.player_agents = {1: agent, 2: agent}
    E._setup_dsl_listeners(st)
    for pid, slugs in ((1, mine), (2, theirs)):
        for slug in slugs:
            card = copy.deepcopy(DB.get(slug))
            card.owner = card.controller = pid
            st.players[pid].graveyard.add(card)
    return st


def _base():
    return DB.get(CARD).base_power or 0


def test_fuel_actually_reaches_the_graveyard():
    """Guard for every other test in this file. A token would be dropped on
    entry (CR 3.0.12a) and leave the zone empty, which makes 'declining pumps
    nothing' pass for a reason that has nothing to do with declining."""
    st = _board(_replay_agent, mine=[FUEL], theirs=[FUEL])
    assert len(st.players[1].graveyard.cards) == 1
    assert len(st.players[2].graveyard.cards) == 1


def test_declining_pumps_nothing_and_banishes_nothing():
    st = _board(_replay_agent, mine=[FUEL], theirs=[FUEL])
    assert our_power(st, CARD, attacker_id=1) == _base()
    assert len(st.players[1].graveyard.cards) == 1
    assert len(st.players[2].graveyard.cards) == 1


def test_paying_banishes_from_both_graveyards_and_pumps_once():
    st = _board(_accepting_agent, mine=[FUEL], theirs=[FUEL])
    assert our_power(st, CARD, attacker_id=1) == _base() + 1
    assert len(st.players[1].graveyard.cards) == 0
    assert len(st.players[2].graveyard.cards) == 0


def test_one_graveyard_alone_is_not_payment():
    """"EACH hero's graveyard" — with the opponent's empty the cost cannot be
    paid, so the pump does not apply AND our card is not spent for nothing."""
    st = _board(_accepting_agent, mine=[FUEL], theirs=[])
    assert our_power(st, CARD, attacker_id=1) == _base()
    assert len(st.players[1].graveyard.cards) == 1


def test_nothing_anywhere_pumps_nothing():
    st = _board(_accepting_agent)
    assert our_power(st, CARD, attacker_id=1) == _base()


def test_the_process_repeats_while_both_graveyards_can_pay():
    """The repeat. Two 1-power cards on each side is two passes, so +2 -- an
    unrolled single pass would give +1 and a missing loop +0."""
    st = _board(_accepting_agent, mine=[FUEL, FUEL], theirs=[FUEL, FUEL])
    assert our_power(st, CARD, attacker_id=1) == _base() + 2
    assert len(st.players[1].graveyard.cards) == 0
    assert len(st.players[2].graveyard.cards) == 0


def test_the_repeat_stops_when_the_shorter_graveyard_runs_dry():
    """Three on our side against one on theirs is ONE pass: the loop ends on
    the side that runs out, and the leftovers stay put."""
    st = _board(_accepting_agent, mine=[FUEL, FUEL, FUEL], theirs=[FUEL])
    assert our_power(st, CARD, attacker_id=1) == _base() + 1
    assert len(st.players[1].graveyard.cards) == 2
    assert len(st.players[2].graveyard.cards) == 0


def test_a_card_without_one_power_is_not_valid_fuel():
    """"a card with 1{p}" is a real restriction. Without the CARD_IS_POWER
    filter the cost would sweep up whatever happened to be in the graveyard."""
    heavy = next((s for s in ("surging_strike_red", "head_jab_red")
                  if (DB.get(s).base_power or 0) != 1), None)
    assert heavy, "need a graveyard card whose power is not 1"
    st = _board(_accepting_agent, mine=[heavy], theirs=[heavy])
    assert our_power(st, CARD, attacker_id=1) == _base()
    assert len(st.players[1].graveyard.cards) == 1
