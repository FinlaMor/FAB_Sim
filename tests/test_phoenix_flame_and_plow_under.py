"""Two cards picked because real games play them constantly.

The corpus holds 490 unimplemented attacking cards across 198,083 observed
attacks, all skipped by the audit as "not implemented". These two are near the
top, so implementing them converts thousands of real attacks from unjudgeable
into checked: phoenix_flame_red 480/480 against the spectator corpus,
plow_under_yellow 604/612.

  phoenix_flame_red   "If you control 2 or more Draconic chain links, this gets
                       +1{p}. Go again"  -- 0{p}, so the static IS the card.
  plow_under_yellow   "If there are 4 or more Earth cards in your banished zone,
                       this gets +4{p}. Decompose - ... each hero puts a card
                       from their ARSENAL on the bottom of their deck."

Phoenix Flame is itself Draconic, so it counts toward its own condition
(CR 7.0.3a/c) -- covered in test_chain_link_counting.py, and asserted here
through the card because that is the observable the card is about.
"""
import copy

import pytest

from engine.card import CardDB
from engine.card_effects.dsl.loader import load_all_cards
from engine.state import ChainLink, Step
from scripts.talishar_attack_replay import (_accepting_agent, _replay_agent,
                                            our_power)
from tests.conftest import _make_state
import engine.engine as E

load_all_cards()
DB = CardDB()

EARTH_CARD = "autumns_touch_red"     # Earth talent, an Action
AN_ACTION = "head_jab_red"


def _board(agent=_replay_agent, draconic_links=0, plain_links=0,
           banished=(), graveyard=(), arsenal=()):
    st = _make_state()
    st.card_db = DB
    st.step = Step.ACTION
    st.active_player = 1
    st.combat = None
    st.player_agents = {1: agent, 2: agent}
    E._setup_dsl_listeners(st)
    for talents in ([("Draconic",)] * draconic_links + [()] * plain_links):
        st.chain_links.append(ChainLink(
            chainlink_id=len(st.chain_links) + 1, attacker_id=1,
            attack_slug="prior", attack_power=0, net_damage=0, keywords=[],
            from_weapon=False, talents=list(talents)))
    for slug in banished:
        c = copy.deepcopy(DB.get(slug))
        c.owner = c.controller = 1
        c.is_public = True          # a face-down banish is not publicly Earth
        st.players[1].banished.add(c)
    for slug in graveyard:
        c = copy.deepcopy(DB.get(slug))
        c.owner = c.controller = 1
        st.players[1].graveyard.add(c)
    for pid in (1, 2):
        for slug in arsenal:
            c = copy.deepcopy(DB.get(slug))
            c.owner = c.controller = pid
            st.players[pid].arsenal.add(c)
    return st


def _base(slug):
    return DB.get(slug).base_power or 0


# ---------------------------------------------------------------- phoenix

def test_phoenix_needs_one_prior_draconic_link_because_it_counts_itself():
    assert our_power(_board(draconic_links=1), "phoenix_flame_red",
                     attacker_id=1) == _base("phoenix_flame_red") + 1


def test_phoenix_gets_nothing_on_an_empty_chain():
    assert our_power(_board(), "phoenix_flame_red",
                     attacker_id=1) == _base("phoenix_flame_red")


def test_phoenix_ignores_non_draconic_links():
    assert our_power(_board(plain_links=3), "phoenix_flame_red",
                     attacker_id=1) == _base("phoenix_flame_red")


def test_phoenix_go_again_is_unconditional():
    """Printed, not gated -- so the WHILE_STATIC must NOT be gated on
    SOURCE_IS_ATTACK, which is what loader.conditional_keywords reads to STRIP
    a printed keyword. Gating it there would silently remove go again."""
    from engine.card_effects.dsl.loader import conditional_keywords
    assert "GoAgain" in (DB.get("phoenix_flame_red").keywords or [])
    assert not conditional_keywords("phoenix_flame_red"), \
        "go again must not be treated as conditional"


# ---------------------------------------------------------------- plow under

def test_plow_under_static_needs_four_earth_cards_banished():
    base = _base("plow_under_yellow")
    assert our_power(_board(banished=[EARTH_CARD] * 3), "plow_under_yellow",
                     attacker_id=1) == base
    assert our_power(_board(banished=[EARTH_CARD] * 4), "plow_under_yellow",
                     attacker_id=1) == base + 4


def test_plow_under_decompose_declined_changes_nothing():
    st = _board(_replay_agent, graveyard=[EARTH_CARD, EARTH_CARD, AN_ACTION],
                arsenal=[AN_ACTION])
    our_power(st, "plow_under_yellow", attacker_id=1)
    assert len(st.players[1].graveyard.cards) == 3
    assert len(st.players[1].arsenal.cards) == 1
    assert len(st.players[2].arsenal.cards) == 1


def test_plow_under_decompose_paid_banishes_and_bottoms_both_arsenals():
    st = _board(_accepting_agent, graveyard=[EARTH_CARD, EARTH_CARD, AN_ACTION],
                arsenal=[AN_ACTION])
    our_power(st, "plow_under_yellow", attacker_id=1)
    assert len(st.players[1].graveyard.cards) == 0, "the cost was not paid"
    assert len(st.players[1].arsenal.cards) == 0
    assert len(st.players[2].arsenal.cards) == 0, "EACH hero, not just you"


def test_plow_under_decompose_is_not_offered_without_the_cost():
    """The ability-level conditions gate whether the option is offered at all,
    so an empty graveyard must leave both arsenals untouched even when the
    player would say yes to anything."""
    st = _board(_accepting_agent, arsenal=[AN_ACTION])
    our_power(st, "plow_under_yellow", attacker_id=1)
    assert len(st.players[1].arsenal.cards) == 1
    assert len(st.players[2].arsenal.cards) == 1


def test_plow_under_decompose_grants_no_power():
    """Unlike cadaverous_tilling, this Decompose pays for a tempo effect, not a
    pump -- so a paid Decompose must leave the power alone."""
    base = _base("plow_under_yellow")
    st = _board(_accepting_agent, graveyard=[EARTH_CARD, EARTH_CARD, AN_ACTION])
    assert our_power(st, "plow_under_yellow", attacker_id=1) == base
