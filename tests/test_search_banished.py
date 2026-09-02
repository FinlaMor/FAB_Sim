"""Prismatic Lens ran a different card's effect, backwards.

Printed: "**Once per Turn Instant** - 0: Reveal the top card of your deck. Put a
Mechanologist item of the same color from your banished zone on top of your
deck."

Authored: `SEARCH_BANISH_FACE_DOWN`, which is trap_door's effect -- search your
DECK, banish what you find FACE-DOWN, then SHUFFLE. Every noun is the wrong way
round. A free activation milled a card out of the deck and shuffled it, where
the card retrieves one INTO the deck; its `destination: "deck_top"` was read by
nothing, because that effect takes no destination.

The shuffle is the part worth naming separately: putting a card on top of your
deck and then shuffling puts it nowhere. A destination of "on top" and a shuffle
cannot both be right, so the default here follows the destination rather than
the zone.

"OF THE SAME COLOR" is a comparison against the card just revealed, not a
colour. The old version hard-coded `color: "yellow"` inside an effect-level
condition -- the wrong question (the lens is yellow; the cards it fetches need
not be) asked at the wrong moment (before anything was revealed).
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
SLUG = "prismatic_lens_yellow"


def _state():
    st = _make_state()
    st.card_db = DB
    st.active_player = 1
    return st


def _item(name, color, classes=("Mechanologist",), subtypes=("Item",)):
    """A REAL Mechanologist item: type Action, subtype Item.

    "Item" is a SUBTYPE. A card typed ["Item"] is not a deck-card at all
    (state._DECK_CARD_TYPES), so putting one into a deck comes back CANCELED and
    a working effect looks broken -- the same trap conftest.owned_card records
    for Ally.
    """
    c = Card(slug=name, name=name, raw_types=["Action"])
    c.types, c.subtypes = ["Action"], list(subtypes)
    c.classes = list(classes)
    c.color = color
    c.owner = c.controller = 1
    return c


def _top(color):
    c = Card(slug="top_card", name="Top Card", raw_types=["Action"])
    c.types = ["Action"]
    c.color = color
    c.owner = c.controller = 1
    return c


def _activate(st):
    ab = [a for a in get_card(SLUG).abilities
          if a.ability_type.upper() == "ACTIVATE"][0]
    run_ability(ab, owned_card(1, SLUG, types=["Item"]), None, st)


def test_it_puts_a_matching_item_on_top_of_the_deck():
    st = _state()
    st.players[1].deck.cards = [_top("Yellow"), _top("Red")]
    match = _item("cog_yellow", "Yellow")
    st.players[1].banished.add(match)

    _activate(st)

    assert st.players[1].deck.cards[0] is match, (
        "the item is not on top of the deck; deck is %s"
        % [c.slug for c in st.players[1].deck.cards])
    assert match not in st.players[1].banished.cards


def test_it_does_not_shuffle_the_deck():
    """Putting a card on top and then shuffling puts it nowhere. The effect this
    card used to run shuffled every time."""
    st = _state()
    order = [_top("Yellow")] + [_top("Red") for _ in range(6)]
    for i, c in enumerate(order):
        c.slug = "deck_%d" % i
    st.players[1].deck.cards = list(order)
    st.players[1].banished.add(_item("cog_yellow", "Yellow"))

    _activate(st)

    after = [c.slug for c in st.players[1].deck.cards[1:]]
    assert after == [c.slug for c in order], (
        "the rest of the deck was reordered: %s" % after)


def test_the_colour_must_match_the_card_revealed_not_the_lens():
    """The lens is yellow. The item it fetches has to match the REVEALED card,
    which is why the old hard-coded colour was wrong even when it 'worked'."""
    st = _state()
    st.players[1].deck.cards = [_top("Red")]
    yellow = _item("cog_yellow", "Yellow")
    st.players[1].banished.add(yellow)

    _activate(st)

    assert yellow in st.players[1].banished.cards, (
        "a yellow item was fetched after revealing a RED card")


def test_a_red_item_is_fetched_when_a_red_card_is_revealed():
    st = _state()
    st.players[1].deck.cards = [_top("Red")]
    red = _item("cog_red", "Red")
    st.players[1].banished.add(red)

    _activate(st)

    assert st.players[1].deck.cards[0] is red


def test_it_only_fetches_mechanologist_items():
    st = _state()
    st.players[1].deck.cards = [_top("Yellow")]
    wrong_class = _item("guardian_thing", "Yellow", classes=("Guardian",))
    wrong_type = _item("some_aura", "Yellow", subtypes=("Aura",))
    for c in (wrong_class, wrong_type):
        st.players[1].banished.add(c)

    _activate(st)

    assert st.players[1].deck.cards[0].slug == "top_card", (
        "something that is not a Mechanologist item was fetched")


def test_nothing_is_taken_from_the_deck():
    """The effect it used to run searched the DECK and banished a card from it.
    Nothing about this card removes anything from the deck."""
    st = _state()
    st.players[1].deck.cards = [_top("Yellow"), _top("Yellow")]
    before = len(st.players[1].deck.cards)
    st.players[1].banished.cards = []

    _activate(st)

    assert len(st.players[1].deck.cards) == before
    assert not st.players[1].banished.cards, "it banished a card from the deck"


def test_the_once_per_turn_limit_comes_from_the_card_data():
    """Not authored in the JSON: the DB parses "Once per Turn" from the printed
    text and play.py enforces it when the activation is offered. A second copy
    in the JSON would be a second implementation of the same rule."""
    card = DB.get(SLUG)
    assert card.has_per_turn_limit and card.activations == 1
    ab = [a for a in get_card(SLUG).abilities
          if a.ability_type.upper() == "ACTIVATE"][0]
    assert "once_per_turn" not in (ab.params or {})
