"""Sigil of Temporal Manipulation banished the opponent's deck instead of its own.

Printed: "At the beginning of your action phase, destroy this. / When this leaves
the arena, banish the top card of YOUR deck. If it's a non-attack action card,
you may play it this turn as though it were an instant."

The payoff was `BANISH_OPP_TOP_GRANT_PLAY` -- Infiltrate's effect, which banishes
the top card of the OPPONENT's deck. Sitting after a BANISH of your own top card,
that made the trigger banish TWICE, once from each deck, and grant permission to
play a card the text says nothing about. Its `target: "top_deck"` was unread,
because that effect takes no target.

The condition was wrong more quietly. It asked CARD_IN_ZONE about the top of the
deck AFTER the banish had moved that card away, so it inspected whichever card
came next. "If IT is a non-attack action card" is about the card just banished --
the `banished` ref -- and "non-attack action" is two claims, not one: it IS an
Action and it is NOT an Attack. A single membership test cannot say that.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card import Card, CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from tests.conftest import _make_state, owned_card

load_all_cards()
DB = CardDB()
SLUG = "sigil_of_temporal_manipulation_blue"


def _state():
    st = _make_state()
    st.card_db = DB
    st.active_player = 1
    return st


def _deck_card(slug, types, subtypes=()):
    c = Card(slug=slug, name=slug, raw_types=list(types))
    c.types, c.subtypes = list(types), list(subtypes)
    c.owner = c.controller = 1
    return c


def _leave_play(st):
    ab = [a for a in get_card(SLUG).abilities
          if (a.trigger or "").upper() == "ON_LEAVE_PLAY"][0]
    run_ability(ab, owned_card(1, SLUG), None, st)


def _stock(st, mine, theirs=2):
    st.players[1].deck.cards = list(mine)
    st.players[2].deck.cards = [_deck_card("theirs_%d" % i, ["Action"])
                                for i in range(theirs)]
    for c in st.players[2].deck.cards:
        c.owner = c.controller = 2


def test_it_banishes_from_your_own_deck():
    st = _state()
    mine = _deck_card("my_top", ["Action"], ["NonAttack"])
    _stock(st, [mine, _deck_card("my_second", ["Action"])])

    _leave_play(st)

    assert mine in st.players[1].banished.cards, "your top card was not banished"


def test_it_does_not_touch_the_opponents_deck():
    st = _state()
    _stock(st, [_deck_card("my_top", ["Action"], ["NonAttack"])], theirs=2)
    before = len(st.players[2].deck.cards)

    _leave_play(st)

    assert len(st.players[2].deck.cards) == before, (
        "the opponent's deck was banished from; that is Infiltrate, not this card")
    assert not st.players[2].banished.cards


def test_only_one_card_is_banished():
    st = _state()
    _stock(st, [_deck_card("my_top", ["Action"], ["NonAttack"]),
                _deck_card("my_second", ["Action"])])

    _leave_play(st)

    assert len(st.players[1].banished.cards) == 1, (
        "it banished more than the one card its text names")


def test_a_non_attack_action_becomes_playable():
    st = _state()
    top = _deck_card("my_top", ["Action"], ["NonAttack"])
    _stock(st, [top, _deck_card("my_second", ["Action"])])

    _leave_play(st)

    assert any(c is top for c in st.players[1].playable_from_banished), (
        "the non-attack action was not made playable")


def test_an_attack_action_does_not():
    """The half the old condition could not ask: it inspected the NEXT card in
    the deck, so the answer had nothing to do with what was banished."""
    st = _state()
    attack = _deck_card("my_attack", ["Action"], ["Attack"])
    # A non-attack action sits SECOND. The old condition read the top of the
    # deck after the banish -- which is this card -- and would have said yes.
    _stock(st, [attack, _deck_card("my_second", ["Action"], ["NonAttack"])])

    _leave_play(st)

    assert attack in st.players[1].banished.cards
    assert not any(c is attack for c in st.players[1].playable_from_banished), (
        "an ATTACK action was made playable")


def test_a_non_action_does_not():
    st = _state()
    resource = _deck_card("my_resource", ["Resource"])
    _stock(st, [resource, _deck_card("my_second", ["Action"], ["NonAttack"])])

    _leave_play(st)

    assert not any(c is resource for c in st.players[1].playable_from_banished), (
        "a card that is not an action at all was made playable")


def test_the_self_destruct_is_only_on_your_own_turn():
    """"At the beginning of YOUR action phase." Ungated, it would also fire at
    the start of the opponent's turn and the sigil would never survive one."""
    ab = [a for a in get_card(SLUG).abilities
          if (a.trigger or "").upper() == "START_OF_TURN"][0]
    assert [c.condition_type for c in ab.conditions] == ["IS_ACTIVE_PLAYER"]
