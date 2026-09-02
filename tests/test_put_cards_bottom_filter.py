"""Channel Iceloch Glaze's upkeep could be paid with the wrong cards.

Printed: "**Channel Ice** - At the beginning of your end phase, put a flow
counter on this, then destroy it unless you put an ICE CARD from your pitch zone
on the bottom of your deck for each flow counter on it."

Which cards are eligible is part of the price. `PUT_CARDS_BOTTOM` read `player`,
`zone` and `amount` but not `filter`, so the pool offered was the WHOLE pitch
zone and the permanent could be kept alive with any cards at all -- cheaper than
printed, and cheaper in the resource that matters, since an Ice deck's pitch
zone is mostly not Ice.

This is the fourth unread key found on this one effect. The others are recorded
in its own comment: `zone`, `target`, `amount` and `optional` were each added
after a card was found relying on one. The pattern is not that this effect is
unusually badly written -- it is that a silently-ignored key produces a card
that still does something plausible, so nothing ever fails.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card import Card, CardDB
from engine.card_effects.dsl.effect_types import compile_effect
from engine.card_effects.dsl.loader import get_card, load_all_cards
from tests.conftest import _make_state, owned_card

load_all_cards()
DB = CardDB()


def _state():
    st = _make_state()
    st.card_db = DB
    st.active_player = 1
    return st


def _pitched(slug, card_class):
    c = Card(slug=slug, name=slug, raw_types=["Action"])
    c.types = ["Action"]
    c.classes = [card_class]
    c.owner = c.controller = 1
    return c


def _bottom(st, **params):
    fn = compile_effect("PUT_CARDS_BOTTOM", params)
    fn(owned_card(1, "channel_iceloch_glaze_blue"), None, st)


def test_only_matching_cards_are_moved():
    st = _state()
    # The non-Ice card goes in FIRST on purpose. The test agent takes the first
    # option it is offered, so with the Ice card at the front this test would
    # pass against an implementation that ignores the filter entirely.
    other = _pitched("guardian_card", "Guardian")
    ice = _pitched("ice_card", "Ice")
    for c in (other, ice):
        st.players[1].pitch.add(c)

    _bottom(st, player="SELF", zone="pitch", amount=1,
            filter=[{"type": "CARD_IS_CLASS", "card_class": "Ice"}])

    assert st.players[1].deck.cards[-1] is ice, (
        "the wrong card paid the upkeep: deck bottom is %s"
        % getattr(st.players[1].deck.cards[-1], "slug", None))
    assert other in st.players[1].pitch.cards


def test_nothing_moves_when_no_card_matches():
    """The upkeep is unpayable, which is what makes the permanent die. Offering
    a non-Ice card would keep it alive for free."""
    st = _state()
    st.players[1].pitch.add(_pitched("guardian_card", "Guardian"))
    before = len(st.players[1].deck.cards)

    _bottom(st, player="SELF", zone="pitch", amount=1,
            filter=[{"type": "CARD_IS_CLASS", "card_class": "Ice"}])

    assert len(st.players[1].deck.cards) == before
    assert len(st.players[1].pitch.cards) == 1


def test_an_unfiltered_call_is_unchanged():
    """The filter is opt-in: the Inertia-token shape (whole zone, no filter)
    must keep working."""
    st = _state()
    for slug in ("a", "b"):
        st.players[1].pitch.add(_pitched(slug, "Guardian"))

    _bottom(st, player="SELF", zone="pitch")

    assert not st.players[1].pitch.cards
    assert len(st.players[1].deck.cards) == 2


def test_the_card_still_asks_for_ice():
    """The premise: if the JSON stops carrying the filter, the engine support
    above is not enough on its own."""
    cd = get_card("channel_iceloch_glaze_blue")
    found = []

    def walk(n):
        if isinstance(n, dict):
            if n.get("type") == "PUT_CARDS_BOTTOM":
                found.append(n)
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    for ab in cd.abilities:
        for e in ab.effects:
            walk(e.params)
    assert found, "the card no longer bottoms anything"
    for node in found:
        classes = [f.get("card_class") for f in (node.get("filter") or [])]
        assert "Ice" in classes, (
            "the Ice restriction is gone from the card: %s" % node)
