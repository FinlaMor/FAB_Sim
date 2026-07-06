"""LOOK / BANISH_FROM_LOOKED / PUT_LOOKED_BACK — Righteous Cleansing crush.

"Look at the top 5 cards of their deck. Banish 1 or more cards with the same
name from among them, then put the rest on top of their deck in any order."
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card import Card
from engine.card_effects.dsl import dispatch, load_all_cards
from engine.state import CombatState, Event, GameState, Player, Step

load_all_cards()


def _hero(pid):
    c = Card(slug="test_hero", name="H", types=["Hero"], base_life=40, base_intellect=4)
    c.owner = pid
    c.controller = pid
    return c


def _agent_pick_name(target_name):
    # Picks the target name when offered (BANISH_FROM_LOOKED); first option otherwise.
    def _a(state, options, context=None):
        if options and target_name in options:
            return target_name
        return options[0] if options else None
    return _a


def _state(banish_name="dupe"):
    return GameState(
        players={1: Player(1, _hero(1)), 2: Player(2, _hero(2))},
        active_player=1,
        player_agents={1: _agent_pick_name(banish_name), 2: _agent_pick_name(banish_name)},
        step=Step.COMBAT_DAMAGE, turn_number=1, combat=None, done=False, winner=None,
    )


def _card(slug, name, owner=2):
    c = Card(slug=slug, name=name, types=["Action"], subtypes=["Attack"])
    c.owner = owner
    c.controller = owner
    return c


def _combat(attacker_id=1):
    ac = _card("righteous_cleansing_yellow", "Righteous Cleansing", owner=attacker_id)
    return CombatState(attacker_id=attacker_id, link_id=1, attack_power=10,
                       attack_card=ac, keywords=[], from_weapon=False)


def test_righteous_cleansing_banishes_same_name_keeps_rest():
    st = _state(banish_name="Dupe")
    st.combat = _combat(attacker_id=1)
    # Opponent (player 2) top 5: two copies named "Dupe", three unique.
    deck = st.players[2].deck
    top5 = [_card("a", "Dupe"), _card("b", "Unique1"), _card("c", "Dupe"),
            _card("d", "Unique2"), _card("e", "Unique3")]
    for c in top5:
        deck.add(c)
    # Cards deeper in the deck should be untouched.
    deep = _card("deep", "Deep")
    deck.add(deep)

    dispatch(st, "ON_CRUSH", "righteous_cleansing_yellow", card=st.combat.attack_card,
             event=Event(type="ON_CRUSH", data={"damage": 8}))

    banished_names = [c.name for c in st.players[2].banished.cards]
    assert banished_names.count("Dupe") == 2  # both copies banished
    remaining_names = [c.name for c in deck.cards]
    assert "Dupe" not in remaining_names          # none left in deck
    assert remaining_names.count("Unique1") == 1  # kept
    assert "Deep" in remaining_names              # untouched
    # The 3 kept looked cards are back on top, ahead of the deeper card.
    assert deck.cards[-1].name == "Deep"


def test_righteous_cleansing_short_deck_no_crash():
    st = _state(banish_name="Solo")
    st.combat = _combat(attacker_id=1)
    st.players[2].deck.add(_card("only", "Solo"))
    dispatch(st, "ON_CRUSH", "righteous_cleansing_yellow", card=st.combat.attack_card,
             event=Event(type="ON_CRUSH", data={"damage": 8}))
    assert [c.name for c in st.players[2].banished.cards] == ["Solo"]
    assert len(st.players[2].deck.cards) == 0
