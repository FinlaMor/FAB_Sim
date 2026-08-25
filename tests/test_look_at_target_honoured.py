"""LOOK_AT defaults to the OPPONENT, and 12 cards named their zone in `target`.

`compile_effect("LOOK_AT", ...)` read `zone`, `player`, `amount`, `into` and
`filter` — a perfectly good vocabulary — but not `target`, which is the key the
cards actually use. So every one of them fell through to the defaults, DECK_TOP
and OPPONENT.

Five say "look at the top card of YOUR deck" and were looking at the opponent's.
That is not a dead effect: it is an information leak pointing the wrong way, and
in a self-play training corpus it is a leak the agent can learn from.

Those five named a zone but never a player, and the shared target parser refuses
to guess one, so the cards themselves now say `player: SELF`. The parser is
shared with BANISH deliberately — same authors, same handful of spellings — and
the tests here pin the LOOK_AT-specific half: its zone map spells the top of the
deck DECK_TOP where the parser's canonical name is TOP_DECK.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.loader import load_all_cards, get_card
from engine.card_effects.dsl.interpreter import run_ability
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

MINE = "wounded_bull_red"
THEIRS = "art_of_desire_mind_blue"


def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    # Distinct contents per player, so "which deck did it read" is answerable.
    for pid, slug in ((1, MINE), (2, THEIRS)):
        for zone in ("deck", "hand"):
            cards = []
            for _ in range(4):
                c = copy.deepcopy(DB.get(slug))
                c.owner = c.controller = pid
                cards.append(c)
            getattr(st.players[pid], zone).cards = cards
    return st


def _card(slug, owner=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = owner
    return c


def _look_effect(slug):
    for ab in get_card(slug).abilities:
        for eff in ab.effects:
            if eff.effect_type == "LOOK_AT":
                return eff
    raise AssertionError(f"{slug} has no LOOK_AT")


def _looked(slug, st):
    """Run the card's LOOK_AT and return what it stored under its ref."""
    from engine.context import get_ref, push_refs, pop_refs
    eff = _look_effect(slug)
    push_refs()
    try:
        eff.fn(_card(slug, owner=1), None, st)
        return get_ref(eff.params.get("into", "looked"))
    finally:
        pop_refs()


def _slugs(looked):
    if looked is None:
        return []
    return [getattr(c, "slug", None)
            for c in (looked if isinstance(looked, list) else [looked])]


@pytest.mark.parametrize("slug", [
    "helmsmans_peak",
    "on_the_horizon_red",
    "on_the_horizon_yellow",
    "right_behind_you_red",
    "seerstone",
    # A later sweep found three more saying "the top of YOUR deck" that named
    # no player at all. The five above named a ZONE via `target` and were fixed
    # by reading it; these named nothing, so they fell through to the OPPONENT
    # default -- an absent parameter and an ignored one look identical from the
    # card's side, and only the second is visible to audit_params.
    "spire_sniping_red",
    "spire_sniping_yellow",
    "scouting_shot_red",
])
def test_look_at_your_own_deck_does_not_read_the_opponents(slug):
    """"look at the top card of YOUR deck"."""
    st = _state()
    seen = _slugs(_looked(slug, st))

    assert seen, f"{slug} looked at nothing"
    assert all(s == MINE for s in seen), (
        f"{slug} read the OPPONENT's deck: {seen}")


@pytest.mark.parametrize("slug", [
    "frontline_scout_red",
    "frontline_scout_yellow",
    "phantasmaclasm_red",
    "the_weakest_link_red",
])
def test_look_at_their_hand_reads_the_hand_not_the_deck(slug):
    """"look at the defending hero's hand" — their HAND, not the top of a deck.

    These four were reading the top of the opponent's DECK, which is the one
    zone the card does not mention. The player half happened to be right by
    accident, which is why an assertion on "did it see anything" would pass.
    """
    st = _state()
    # Make the opponent's hand and deck distinguishable from each other.
    for c in st.players[2].hand.cards:
        c.slug = "opp_hand_card"
    seen = _slugs(_looked(slug, st))

    assert seen, f"{slug} looked at nothing"
    assert all(s == "opp_hand_card" for s in seen), (
        f"{slug} did not read the opponent's hand: {seen}")


def test_a_zone_only_target_still_reads_the_opponent():
    """Why the five cards had to change, not just the compiler.

    Their target named a zone and no player. The parser will not invent one, so
    the OPPONENT default still applies — which is the bug. This pins the shape
    those cards used to have, so that if one is ever reverted to it the failure
    says exactly what went wrong instead of just "wrong deck".
    """
    from engine.card_effects.dsl.effect_types import compile_effect
    from engine.context import get_ref, push_refs, pop_refs
    st = _state()

    fn = compile_effect("LOOK_AT", {"target": "TOP_DECK", "into": "probe"})
    push_refs()
    try:
        fn(_card(MINE), None, st)
        seen = _slugs(get_ref("probe"))
    finally:
        pop_refs()

    assert seen == [THEIRS], (
        "a zone-only target no longer falls back to OPPONENT — if that default "
        "changed, the five 'your deck' cards may no longer need their explicit "
        "player and this test should be revisited")


def test_the_parser_is_shared_with_banish():
    """One parser, because the same spellings show up on both effects.

    A second copy would drift from this one the first time a new spelling
    appeared, and the drift would be invisible — both would still "work".
    """
    from engine.card_effects.dsl import effect_types

    assert not hasattr(effect_types, "_banish_target_spec"), (
        "the BANISH-specific parser is back; there should be one shared reader")
    assert effect_types._zone_target_spec("defending_hero_hand") == ("OPPONENT", "HAND")
    assert effect_types._zone_target_spec("OPPONENT_TOP_DECK") == ("OPPONENT", "TOP_DECK")


def test_defending_hero_is_the_opponent_not_your_own():
    """"defending_hero_hand" contains "hero", which reads as the controller's
    own side in "hero_graveyard". The opponent words must win."""
    from engine.card_effects.dsl.effect_types import _zone_target_spec

    assert _zone_target_spec("defending_hero_hand")[0] == "OPPONENT"
    assert _zone_target_spec("defending_hero_deck_top")[0] == "OPPONENT"
    assert _zone_target_spec("hero_graveyard")[0] == "SELF"


def test_an_explicit_zone_still_wins_over_the_target():
    from engine.card_effects.dsl.effect_types import compile_effect
    from engine.context import get_ref, push_refs, pop_refs
    st = _state()

    fn = compile_effect("LOOK_AT", {"target": "OPPONENT_HAND",
                                    "zone": "DECK_TOP", "player": "SELF",
                                    "into": "probe"})
    push_refs()
    try:
        fn(_card(MINE), None, st)
        seen = _slugs(get_ref("probe"))
    finally:
        pop_refs()
    assert seen and all(s == MINE for s in seen), seen
