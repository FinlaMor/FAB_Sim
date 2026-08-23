"""BANISH names a player and a zone, and until now read neither.

`compile_effect("BANISH", ...)` read `from_zone` and `player` but not `target`,
which is the key 33 cards actually use. Every one of them fell back to the
defaults — TOP_DECK and SELF — so "banish the top card of THEIR deck" milled the
controller's OWN deck, and "banish a card from their graveyard" did not touch a
graveyard at all.

That is the inverted-effect shape this codebase keeps turning up: not a card
that does nothing, but a card that does something to the wrong player. These
tests drive the compiled effect against a real GameState and check WHICH zone
of WHICH player lost a card, since asserting only "a card was banished" passes
just as happily on the broken behaviour.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.effect_types import _zone_target_spec
from engine.card_effects.dsl.loader import load_all_cards, get_card
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

FILLER = "wounded_bull_red"


def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    return st


def _stock(st, pid, zone, n=3):
    """Put n distinct filler cards into player `pid`'s `zone`."""
    cards = []
    for _ in range(n):
        c = copy.deepcopy(DB.get(FILLER))
        c.owner = c.controller = pid
        cards.append(c)
    getattr(st.players[pid], zone).cards = cards
    return cards


def _card(slug, owner=1):
    c = copy.deepcopy(DB.get(slug))
    c.owner = c.controller = owner
    return c


def _banish_effects(slug):
    return [e for a in get_card(slug).abilities for e in a.effects
            if e.effect_type == "BANISH"]


def _counts(st):
    return {(pid, z): len(getattr(st.players[pid], z).cards)
            for pid in (1, 2)
            for z in ("deck", "graveyard", "hand", "arsenal", "soul")}


# ── the wrong-player half ──────────────────────────────────────────────────
@pytest.mark.parametrize("slug", [
    "art_of_desire_mind_blue",
    "impulsive_desire_blue",
    "minds_desire_red",
    "plunder_the_poor_yellow",
    "vile_inquisition_blue",
])
def test_banish_top_of_their_deck_does_not_mill_your_own(slug):
    """"banish the top card of THEIR deck" — the opponent's, not the caster's."""
    st = _state()
    for pid in (1, 2):
        _stock(st, pid, "deck", 4)
    before = _counts(st)

    _banish_effects(slug)[0].fn(_card(slug, owner=1), None, st)

    assert len(st.players[1].deck.cards) == before[(1, "deck")], (
        f"{slug} banished from its OWN controller's deck")
    assert len(st.players[2].deck.cards) == before[(2, "deck")] - 1
    assert len(st.players[2].banished.cards) == 1


def test_banish_from_their_graveyard_hits_the_graveyard_not_the_deck():
    """bonds_of_attraction_red: top of their deck, THEN their graveyard."""
    st = _state()
    for pid in (1, 2):
        _stock(st, pid, "deck", 4)
        _stock(st, pid, "graveyard", 3)
    before = _counts(st)

    card = _card("bonds_of_attraction_red", owner=1)
    for eff in _banish_effects("bonds_of_attraction_red"):
        eff.fn(card, None, st)

    assert len(st.players[2].deck.cards) == before[(2, "deck")] - 1
    assert len(st.players[2].graveyard.cards) == before[(2, "graveyard")] - 1
    # Nothing of the controller's own was touched.
    assert len(st.players[1].deck.cards) == before[(1, "deck")]
    assert len(st.players[1].graveyard.cards) == before[(1, "graveyard")]


def test_banish_from_their_arsenal():
    """send_packing_yellow: {"zone": "arsenal", "controller": "opponent"}."""
    st = _state()
    for pid in (1, 2):
        _stock(st, pid, "deck", 4)
        _stock(st, pid, "arsenal", 2)
    before = _counts(st)

    _banish_effects("send_packing_yellow")[0].fn(
        _card("send_packing_yellow", owner=1), None, st)

    assert len(st.players[2].arsenal.cards) == before[(2, "arsenal")] - 1
    assert len(st.players[1].deck.cards) == before[(1, "deck")]
    assert len(st.players[2].deck.cards) == before[(2, "deck")]


def test_banish_from_their_soul():
    """hungering_demigon_blue banishes from the opposing hero's soul.

    Soul was missing from BANISH's zone map entirely, so even a correctly read
    target would have resolved to "unknown zone" and banished nothing.
    """
    st = _state()
    for pid in (1, 2):
        _stock(st, pid, "deck", 4)
        _stock(st, pid, "soul", 2)
    before = _counts(st)

    _banish_effects("hungering_demigon_blue")[0].fn(
        _card("hungering_demigon_blue", owner=1), None, st)

    assert len(st.players[2].soul.cards) == before[(2, "soul")] - 1
    assert len(st.players[1].soul.cards) == before[(1, "soul")]
    assert len(st.players[1].deck.cards) == before[(1, "deck")]


# ── the wrong-zone half, on the controller's own side ──────────────────────
@pytest.mark.parametrize("slug,zone", [
    ("painful_passage_red", "hand"),
    ("blossoming_spellblade_red", "graveyard"),
])
def test_banish_from_your_own_named_zone_not_your_deck(slug, zone):
    """"from your hand"/"from your graveyard" — not the top of your deck.

    Runs the whole ABILITY rather than picking the BANISH effect out of the
    top-level list. A card may legitimately wrap it — painful_passage_red's
    banish is optional and sits inside a MAY — and a guard that only walks the
    top level goes quiet exactly when the card is authored more precisely.
    """
    from engine.card_effects.dsl.interpreter import run_ability

    st = _state()
    _stock(st, 1, "deck", 4)
    _stock(st, 1, zone, 3)
    # blossoming_spellblade_red gates its banish on having been FUSED. Calling
    # the effect fn directly (as this test used to) walks straight past that;
    # running the ability honours it, so the marker has to be set or the card
    # correctly does nothing.
    st.players[1].current_turn_effects.append(f"fused_{slug}")
    before = _counts(st)

    for ability in get_card(slug).abilities:
        run_ability(ability, _card(slug, owner=1), None, st)

    assert len(getattr(st.players[1], zone).cards) == before[(1, zone)] - 1
    assert len(st.players[1].deck.cards) == before[(1, "deck")], (
        f"{slug} banished from the deck instead of the {zone}")


# ── the parser refuses to guess ────────────────────────────────────────────
@pytest.mark.parametrize("target,expected", [
    ("OPPONENT_TOP_DECK", ("OPPONENT", "TOP_DECK")),
    ("OPPONENT_DECK_TOP", ("OPPONENT", "TOP_DECK")),
    ("opponent_soul", ("OPPONENT", "SOUL")),
    ("hero_graveyard", ("SELF", "GRAVEYARD")),
    ("hand", (None, "HAND")),
    ("opponent", ("OPPONENT", None)),
    ({"type": "GRAVEYARD", "controller": "opponent"}, ("OPPONENT", "GRAVEYARD")),
    ({"type": "TOP_CARD", "controller": "opponent"}, ("OPPONENT", "TOP_DECK")),
    ({"zone": "arsenal", "controller": "opponent"}, ("OPPONENT", "ARSENAL")),
])
def test_target_spec_parses_every_spelling_in_the_corpus(target, expected):
    assert _zone_target_spec(target) == expected


@pytest.mark.parametrize("target", ["INSTANT", {"filter": []}, None, 7])
def test_unparseable_target_yields_no_guess(target):
    """A target this cannot read must leave BOTH parts to the caller's default.

    "INSTANT" is a card type, not a zone. Resolving it to something plausible
    would hide it from scripts/audit_params.py, which is the only thing that
    will ever bring it back up.
    """
    assert _zone_target_spec(target) == (None, None)


def test_explicit_from_zone_and_player_still_win():
    """Cards authored against the keys the handler already read keep working."""
    from engine.card_effects.dsl.effect_types import compile_effect
    st = _state()
    for pid in (1, 2):
        _stock(st, pid, "deck", 4)
        _stock(st, pid, "graveyard", 3)

    # target says one thing, the explicit keys say another: explicit wins.
    fn = compile_effect("BANISH", {"target": "OPPONENT_GRAVEYARD",
                                   "player": "SELF", "from_zone": "TOP_DECK"})
    fn(_card("art_of_desire_mind_blue", owner=1), None, st)

    assert len(st.players[1].deck.cards) == 3
    assert len(st.players[2].graveyard.cards) == 3
