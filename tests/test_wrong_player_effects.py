"""Nine cards said "they" and did it to the player who played them.

The same shape as BANISH's unread target, found in the tail of the audit rather
than at the top of it: DISCARD, SET_FLAG and PUT_CARDS_BOTTOM all decide whose
cards they touch from `player`, and these cards name the opponent under `target`
instead — a key none of them read. So "they discard a card" discarded the
caster's own, and "put a card from THEIR arsenal on the bottom of THEIR deck"
emptied the caster's hand and arsenal.

PUT_CARDS_BOTTOM was the worst of them: it had no `player` param at all, and it
moves the WHOLE zone, so Mulch bottomed its own controller's entire hand AND
arsenal for a card that bottoms one card of the opponent's.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import load_all_cards, get_card
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

FILLER = "wounded_bull_red"



def _card_json(root, name):
    """The implemented card file called `name`, ignoring pipeline artifacts.

    rglob walks EVERYTHING under the json tree, and in the pipeline worktree
    that tree also holds .drafts/, .review/ and .triage/ results filed under
    the same slug. Taking the first match there picked up a review verdict --
    a JSON object with no "abilities" -- so tests that pass here failed in the
    worktree for a reason that had nothing to do with the card.
    """
    hits = [p for p in root.rglob(name)
            if not any(part.startswith(".") for part in p.parts)]
    assert hits, f"no implemented card file for {name}"
    return hits[0]

def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    return st


def _card(slug, owner=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = owner
    return c


def _stock(st, pid, zone, n=3):
    cards = [_card(FILLER, owner=pid) for _ in range(n)]
    getattr(st.players[pid], zone).cards = cards
    return cards


def _run_type(slug, etype, card, st):
    """Run every node of the named type(s) from the card's real JSON.

    `etype` may be a list, in which case the nodes run in DOCUMENT order inside
    ONE reference scope -- which is what a card like Censor needs, because its
    restriction reads a name a preceding NAME_A_CARD chose, and refs live for
    exactly one ability execution.
    """
    import json
    from pathlib import Path
    from engine.card_effects.dsl.effect_types import compile_effect
    from engine.context import push_refs, pop_refs

    wanted = [etype] if isinstance(etype, str) else list(etype)
    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    raw = json.loads(_card_json(root, f"{slug}.json").read_text(encoding="utf-8"))
    found = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") in wanted:
                found.append(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(raw.get("abilities", []))
    for want in wanted:
        assert any(n.get("type") == want for n in found), \
            f"{slug} has no {want} node"
    push_refs()
    try:
        for spec in found:
            compile_effect(spec["type"],
                           {k: v for k, v in spec.items()
                            if k not in ("type", "conditions")})(card, None, st)
    finally:
        pop_refs()


@pytest.mark.parametrize("slug", [
    "consuming_volition_blue",
    "cut_down_to_size_yellow",
    "tear_down_the_idols_red",
])
def test_they_discard_means_the_opponent(slug):
    """"When this hits a hero, THEY discard a card"."""
    st = _state()
    _stock(st, 1, "hand", 4)
    _stock(st, 2, "hand", 4)

    _run_type(slug, "DISCARD", _card(slug), st)

    assert len(st.players[2].hand.cards) == 3, f"{slug} discarded nothing"
    assert len(st.players[1].hand.cards) == 4, (
        f"{slug} made the CASTER discard")


@pytest.mark.parametrize("slug", ["mulch_blue", "mulch_red"])
def test_mulch_bottoms_one_card_of_theirs_not_your_whole_hand(slug):
    """"put A CARD from THEIR arsenal on the bottom of THEIR deck"."""
    st = _state()
    _stock(st, 1, "hand", 4)
    _stock(st, 1, "arsenal", 1)
    _stock(st, 2, "arsenal", 2)
    theirs_deck = len(st.players[2].deck.cards)

    _run_type(slug, "PUT_CARDS_BOTTOM", _card(slug), st)

    assert len(st.players[2].arsenal.cards) == 1, "it did not bottom their card"
    assert len(st.players[2].deck.cards) == theirs_deck + 1
    assert len(st.players[1].hand.cards) == 4, "it emptied the caster's hand"
    assert len(st.players[1].arsenal.cards) == 1, "it emptied the caster's arsenal"


@pytest.mark.parametrize("slug,etypes", [
    # Censor's restriction is no longer a SET_FLAG: a flag nothing reads cannot
    # restrict anyone, whichever player it is written to. The effect type
    # changed; what this test is for did not, so it now names the effect each
    # card actually uses and asks the same question of it.
    ("censor_red", ["NAME_A_CARD", "FORBID_PLAYING_NAMED"]),
    ("fatigue_shot_red", ["SET_FLAG"]),
])
def test_the_restriction_lands_on_the_hero_it_names(slug, etypes):
    """These restrict what the HIT hero may do next turn, not the caster."""
    st = _state()
    # NAME_A_CARD offers only names the namer can see, so the caster needs a
    # hand for there to be anything to name.
    _stock(st, 1, "hand", 2)

    _run_type(slug, etypes, _card(slug), st)

    mine = list(st.players[1].current_turn_effects) + list(
        getattr(st.players[1], "next_turn_effects", []))
    theirs = list(st.players[2].current_turn_effects) + list(
        getattr(st.players[2], "next_turn_effects", []))
    assert theirs, f"{slug} set no flag on the opponent"
    assert not mine, f"{slug} restricted the caster instead: {mine}"


def test_winters_bite_is_pay_or_discard_not_an_unconditional_discard():
    """"Target hero discards a card UNLESS THEY PAY {r}{r}"."""
    st = _state()
    _stock(st, 2, "hand", 4)
    _stock(st, 1, "hand", 4)
    st.players[2].resources = 5
    # The opponent is asked whether to pay; this agent always takes the first
    # option, which is "pay".
    st.player_agents[2] = lambda s, o, context="": o[0]

    _run_type("winters_bite_yellow", "PAY_OR_ELSE", _card("winters_bite_yellow"), st)

    assert st.players[2].resources == 3, "the opponent did not pay"
    assert len(st.players[2].hand.cards) == 4, "they paid AND discarded"
    assert len(st.players[1].hand.cards) == 4, "the caster discarded"


def test_winters_bite_discards_when_they_decline():
    st = _state()
    _stock(st, 2, "hand", 4)
    st.players[2].resources = 0      # cannot pay
    _run_type("winters_bite_yellow", "PAY_OR_ELSE", _card("winters_bite_yellow"), st)
    assert len(st.players[2].hand.cards) == 3


def test_winters_bite_has_no_invented_life_cost():
    """It carried a PAY_LIFE 2 additional cost. The card has no life cost — that
    is the OPPONENT's resource payment, not the caster's life."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    raw = json.loads(_card_json(root, "winters_bite_yellow.json").read_text(encoding="utf-8"))
    for ability in raw.get("abilities") or []:
        for cost in ability.get("additional_cost") or []:
            assert cost.get("type") != "PAY_LIFE", raw


def test_memorial_ground_puts_one_matching_card_on_top():
    """"Put target attack action card with cost 2 or less from your graveyard on
    TOP of your deck." PUT_CARDS_BOTTOM was the wrong direction AND moved the
    whole zone."""
    st = _state()
    cheap = _card(FILLER, owner=1)
    cheap.raw_cost = 1
    dear = _card(FILLER, owner=1)
    dear.raw_cost = 5
    st.players[1].graveyard.cards = [cheap, dear]
    deck_before = len(st.players[1].deck.cards)

    _run_type("memorial_ground_red", "MOVE_MATCHING", _card("memorial_ground_red"), st)

    assert st.players[1].deck.cards[0] is cheap, "the cheap card is not on top"
    assert len(st.players[1].deck.cards) == deck_before + 1, "it moved more than one"
    assert dear in st.players[1].graveyard.cards, "the cost filter was not applied"


def test_put_cards_bottom_without_an_amount_still_moves_the_whole_zone():
    """The Inertia token is "hand + arsenal -> bottom of deck", with no count.
    Adding an amount must not change what the countless form does."""
    from engine.card_effects.dsl.effect_types import compile_effect
    st = _state()
    _stock(st, 1, "hand", 3)
    _stock(st, 1, "arsenal", 1)

    compile_effect("PUT_CARDS_BOTTOM", {})(_card(FILLER), None, st)

    assert st.players[1].hand.cards == []
    assert st.players[1].arsenal.cards == []
