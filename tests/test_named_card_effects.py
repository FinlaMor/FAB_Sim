"""Effects that name ONE specific card, and fetched or returned any card.

Three separate handlers had no way to say which card the text means:

  * SEARCH_DECK filtered by type, subtype, class and cost but not by NAME, so
    "search your deck for a Phoenix Flame" matched every card in the deck and
    fetched whichever came first.
  * RETURN_TO_HAND returned THIS card — the source — and read no target, so
    "return a Phoenix Flame from your graveyard to your hand" returned Inflame
    itself.
  * The BANISH_FROM_GRAVEYARD cost filtered by card type only, so "banish a
    Phoenix Flame from your graveyard" could be paid with any card.

A search that names a card and returns a different one is worse than a search
that fails: the card resolves, the player gets something, and nothing looks
wrong.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.loader import load_all_cards, get_card
from tests.conftest import _card_json, _make_state

load_all_cards()
DB = CardDB()

FILLER = "wounded_bull_red"
PHOENIX = "phoenix_flame_red"


def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    return st


def _card(slug, owner=1, zone=None):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = owner
    # Assigning Zone.cards directly bypasses Zone.add, which is what stamps
    # card.zone -- and put_object removes a card from the zone the CARD says it
    # is in. Without this the searched card lands in its destination while
    # still sitting in the deck: present in both at once.
    if zone is not None:
        c.zone = zone
    return c


def _run_type(slug, etype, card, st):
    import json
    from pathlib import Path
    from engine.card_effects.dsl.effect_types import compile_effect
    from engine.context import push_refs, pop_refs

    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    raw = json.loads(_card_json(root, f"{slug}.json").read_text(encoding="utf-8"))
    found = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == etype:
                found.append(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(raw.get("abilities", []))
    assert found, f"{slug} has no {etype} node"
    push_refs()
    try:
        for spec in found:
            compile_effect(etype, {k: v for k, v in spec.items()
                                   if k not in ("type", "conditions")})(card, None, st)
    finally:
        pop_refs()


def test_search_finds_the_named_card_not_the_first_one():
    """"Search your deck for a Phoenix Flame, put it into your hand"."""
    st = _state()
    decoys = [_card(FILLER, zone="deck") for _ in range(4)]
    phoenix = _card(PHOENIX, zone="deck")
    # Phoenix Flame last, so "first eligible" is a decoy.
    st.players[1].deck.cards = decoys + [phoenix]
    st.players[1].hand.cards = []

    _run_type("phoenix_bannerman_head_red", "SEARCH_DECK",
              _card("phoenix_bannerman_head_red"), st)

    got = [c.slug for c in st.players[1].hand.cards]
    assert got == [PHOENIX], f"searched for a Phoenix Flame and found {got}"
    assert PHOENIX not in [c.slug for c in st.players[1].deck.cards], (
        "the fetched card is in the hand AND still in the deck")


def test_search_finds_nothing_when_the_named_card_is_absent():
    """A named search must fail to find rather than fetch a substitute."""
    st = _state()
    st.players[1].deck.cards = [_card(FILLER) for _ in range(4)]
    st.players[1].hand.cards = []

    _run_type("phoenix_bannerman_head_red", "SEARCH_DECK",
              _card("phoenix_bannerman_head_red"), st)

    assert st.players[1].hand.cards == [], "it fetched a substitute card"


def test_search_by_keyword_matches_the_candidate_not_the_source():
    """"search your deck for a card with BLOOD DEBT, banish it".

    The blood-debt test was effect-level `conditions`, which the loader turns
    into a gate on the SOURCE card — it asked whether Shadow of Blasmophet
    itself has blood debt.
    """
    st = _state()
    # Distinct slugs: Card equality is by value, so two copies of the same slug
    # make `in`/`not in` assertions meaningless.
    marked = _card(PHOENIX, zone="deck")
    marked.keywords = ["BloodDebt"]
    plain = _card(FILLER, zone="deck")
    plain.keywords = []
    st.players[1].deck.cards = [plain, marked]

    source = _card("shadow_of_blasmophet_red")
    source.keywords = []          # the SOURCE has no blood debt
    _run_type("shadow_of_blasmophet_red", "SEARCH_DECK", source, st)

    banished = [c.slug for c in st.players[1].banished.cards]
    assert banished == [PHOENIX], (
        f"expected the blood-debt card banished, got {banished}")
    assert [c.slug for c in st.players[1].deck.cards] == [FILLER], (
        "it took the card without the keyword")


def test_inflame_returns_the_phoenix_flame_not_itself():
    """"return a PHOENIX FLAME from your graveyard to your hand"."""
    st = _state()
    source = _card("inflame_red")
    phoenix = _card(PHOENIX, zone="graveyard")
    st.players[1].graveyard.cards = [_card(FILLER, zone="graveyard"), phoenix]
    st.players[1].hand.cards = []

    _run_type("inflame_red", "RETURN_TO_HAND", source, st)

    got = [c.slug for c in st.players[1].hand.cards]
    assert got == [PHOENIX], f"returned {got} instead of the Phoenix Flame"
    assert source.slug not in got, "it returned Inflame itself"


def test_send_packing_returns_the_banished_card_to_its_owner():
    """"return THE BANISHED CARD to ITS OWNER's hand" — the opponent's."""
    from engine.context import push_refs, pop_refs, set_ref
    from engine.card_effects.dsl.effect_types import compile_effect

    st = _state()
    theirs = _card(FILLER, owner=2, zone="banished")
    st.players[2].banished.cards = [theirs]
    source = _card("send_packing_yellow")

    push_refs()
    try:
        set_ref("banished", theirs)
        compile_effect("RETURN_TO_HAND", {"ref": "banished", "to_owner": True})(
            source, None, st)
    finally:
        pop_refs()

    assert theirs in st.players[2].hand.cards, "it did not go to its owner"
    assert theirs not in st.players[1].hand.cards, "it went to the caster's hand"


def test_burn_away_cost_needs_the_named_card():
    """The additional cost is "banish a PHOENIX FLAME from your graveyard"."""
    from engine.card_effects.dsl.cost_types import compile_cost

    can_pay, pay = compile_cost("BANISH_FROM_GRAVEYARD", {"name": "Phoenix Flame"})
    st = _state()
    source = _card("burn_away_red")

    st.players[1].graveyard.cards = [_card(FILLER) for _ in range(3)]
    assert can_pay(source, None, st) is False, (
        "a graveyard with no Phoenix Flame paid the cost")

    st.players[1].graveyard.cards.append(_card(PHOENIX))
    assert can_pay(source, None, st) is True
    pay(source, None, st)
    assert [c.slug for c in st.players[1].banished.cards] == [PHOENIX], (
        "it banished some other card to pay")


def test_mutated_mass_has_no_fabricated_cost():
    """"You may PLAY this FROM YOUR BANISHED ZONE" is a permission, not a cost.

    As a cost it made the card unplayable whenever the graveyard was empty. A
    wrong cost is worse than a wrong effect: it blocks legality.
    """
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    raw = json.loads(_card_json(root, "mutated_mass_blue.json").read_text(encoding="utf-8"))
    for ability in raw.get("abilities") or []:
        for key in ("cost", "additional_cost", "alternative_cost"):
            for spec in ability.get(key) or []:
                assert spec.get("type") != "BANISH_FROM_GRAVEYARD", (key, spec)


def test_pass_over_banishes_from_the_opponents_graveyard():
    """"Banish target card from an OPPOSING hero's graveyard" — an effect, not a
    cost, and not from the caster's own graveyard."""
    st = _state()
    st.players[1].graveyard.cards = [_card(FILLER, owner=1) for _ in range(2)]
    st.players[2].graveyard.cards = [_card(FILLER, owner=2) for _ in range(2)]

    _run_type("pass_over_blue", "BANISH", _card("pass_over_blue"), st)

    assert len(st.players[2].graveyard.cards) == 1, "the opponent's graveyard is untouched"
    assert len(st.players[1].graveyard.cards) == 2, "it banished from the caster's own"


def test_pass_over_is_playable_with_an_empty_own_graveyard():
    """The cost form blocked the card entirely when your graveyard was empty."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    raw = json.loads(_card_json(root, "pass_over_blue.json").read_text(encoding="utf-8"))
    for ability in raw.get("abilities") or []:
        assert not (ability.get("cost") or ability.get("additional_cost")), ability
