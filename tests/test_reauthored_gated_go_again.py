"""Three cards from the gated-go-again backlog that needed RE-AUTHORING, not a
shape change. Each was implemented against something the card does not say.

    man_overboard_yellow      "you may discard an ALLY. If you do, this gets
                              +1{p} and go again."
                              -> was OPT 1 (look at the top card of your deck),
                                 then an UNCONDITIONAL +1{p} and go again. No
                                 discard, no ally, no gate.

    sonata_galaxia_red        "Search your deck for a Runeblade aura with cost
                              X or less. If X IS 2 OR MORE, this gets go again."
                              -> was gated on CHAIN_HIT_COUNT_GTE 2, the number
                                 of attacks that have HIT this combat chain,
                                 which is 0 for a non-attack played outside
                                 combat. It also carried a PAY_LIFE 1 cost that
                                 appears NOWHERE in its text -- an invented
                                 cost, worse than a missing one because it
                                 silently makes the card unplayable at 1 life.

    aether_quickening_yellow  "Surge - If this deals MORE THAN 3 damage, it gets
                              go again."
                              -> was ON_CLASH_WIN_REVEALED + CHAIN_HIT_COUNT_GTE
                                 4. A clash trigger and a chain-hit count;
                                 neither word appears on the card.

In all three the gate could not fire while the PRINTED go again paid out
regardless, so each played as an unconditional go again with a dead clause
attached -- the backlog's signature, reached by three different routes.

WHAT THE ENGINE NEEDED. Every existing comparison condition names one specific
quantity (HAND_SIZE_GTE, SOUL_COUNT_GTE, CHAIN_HIT_COUNT_GTE...), so a card
asking about a quantity with no condition type of its own had nowhere to go --
which is how both of the last two ended up on CHAIN_HIT_COUNT_GTE, a condition
that at least compiled. AMOUNT_GTE/GT compares any resolvable amount, so "if X
is 2 or more" and "if this deals more than 3 damage" are now sayable.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import (_kw_key, conditional_keywords,
                                            get_card, load_all_cards)
from engine.state import StackEntry
from tests.conftest import (_card_json, _make_state, attack_with, owned_card,
                            recalculate_attack)

load_all_cards()
DB = CardDB()
JSON_ROOT = ROOT / "engine" / "card_effects" / "json"

REAUTHORED = ["man_overboard_yellow", "sonata_galaxia_red",
              "aether_quickening_yellow"]


def _state():
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="": o[0]
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    return st


def _go_again(st):
    return any(_kw_key(k) == "goagain" for k in st.combat.keywords)


def _raw(slug):
    return json.loads(_card_json(JSON_ROOT, slug + ".json")
                      .read_text(encoding="utf-8"))


def _run_all(slug):
    def _fn(card, state):
        for ability in get_card(slug).abilities:
            run_ability(ability, card, None, state)
    return _fn


def _resolve_as_layer(st, slug, setup=None):
    """Non-attack cards are paid their action point by resolve_stack, not from
    combat.keywords, so this is the path that decides whether they got go
    again."""
    card = copy.deepcopy(DB.get(slug))
    card.owner = card.controller = 1
    if setup:
        setup(st, card)
    st.players[1].action_points = 0
    st.stack.add(card)
    entry = StackEntry(player_id=1, card=card, layer_type="card",
                       effect_fn=_run_all(slug))
    assert not entry.is_attack, slug + " is not a non-attack layer"
    st.stack_entries.append(entry)
    E.resolve_stack(st)
    return st.players[1].action_points


@pytest.mark.parametrize("slug", REAUTHORED)
def test_the_printed_keyword_is_conditional_now(slug):
    assert "goagain" in conditional_keywords(slug), slug


# --- man overboard: "you may discard an ally" -------------------------------

def _man_overboard(st, ally_in_hand, accept):
    st.player_agents = {1: (lambda s, o, context="": o[0] if accept else o[-1]),
                        2: (lambda s, o, context="": o[0])}
    card = copy.deepcopy(DB.get("man_overboard_yellow"))
    card.owner = card.controller = 1
    attack_with(st, card)
    if ally_in_hand:
        # Ally is a SUBTYPE in this card data, not a type -- a ["Ally"] typed
        # fixture is rejected by the hand's zone rules and never arrives, which
        # made the correct card look broken.
        ally = owned_card(1, "an_ally", types=["Action"])
        ally.subtypes = ["Ally"]
        st.players[1].hand.add(ally)
    st.players[1].hand.add(owned_card(1, "not_an_ally", types=["Action"]))
    for ability in get_card("man_overboard_yellow").abilities:
        run_ability(ability, card, None, st)
    return card


def test_man_overboard_pays_off_when_an_ally_is_discarded():
    st = _state()
    card = _man_overboard(st, ally_in_hand=True, accept=True)
    base = card.base_power or 0

    assert recalculate_attack(st) == base + 1, "the +1{p} half"
    assert _go_again(st), "an ally was discarded, so go again is due"
    assert [c.slug for c in st.players[1].graveyard.cards] == ["an_ally"], (
        "the ally was not the card discarded")


def test_man_overboard_gives_nothing_when_the_choice_is_declined():
    st = _state()
    card = _man_overboard(st, ally_in_hand=True, accept=False)
    base = card.base_power or 0

    assert recalculate_attack(st) == base
    assert not _go_again(st), "declined the discard and still got go again"
    assert not st.players[1].graveyard.cards, "discarded despite declining"


def test_man_overboard_gives_nothing_with_no_ally_to_discard():
    """"If you do" also covers being unable to. A filtered discard with no
    match discards nothing and leaves no ref, so the payoff withholds itself."""
    st = _state()
    card = _man_overboard(st, ally_in_hand=False, accept=True)
    base = card.base_power or 0

    assert recalculate_attack(st) == base
    assert not _go_again(st), "no ally in hand, but the payoff still landed"
    assert not st.players[1].graveyard.cards, (
        "a NON-ally was discarded -- the filter is not filtering")


def test_man_overboard_no_longer_looks_at_its_deck():
    """OPT is 'look at the top card of your deck and optionally put it on the
    bottom'. It is not a discard, an ally, or a gate; it was simply a different
    card's effect."""
    assert not any(e.get("type") == "OPT"
                   for a in _raw("man_overboard_yellow")["abilities"]
                   for e in a.get("effects", []))


# --- sonata galaxia: "if X is 2 or more" ------------------------------------

@pytest.mark.parametrize("x,expected", [(0, 0), (1, 0), (2, 1), (3, 1)])
def test_sonata_galaxia_grants_go_again_only_from_x_of_two(x, expected):
    st = _state()

    points = _resolve_as_layer(st, "sonata_galaxia_red",
                               setup=lambda s, c: setattr(c, "x_paid", x))

    assert points == expected, (
        "X=%d should give %d action point(s), got %d" % (x, expected, points))


def test_sonata_galaxia_has_no_invented_life_cost():
    """A PAY_LIFE 1 additional cost appeared nowhere in the printed text. An
    invented cost is worse than a missing one: it silently makes the card
    unplayable at 1 life, and nothing about the card says why."""
    raw = _raw("sonata_galaxia_red")
    assert raw.get("cost") is None
    assert not any(c.get("type") == "PAY_LIFE"
                   for a in raw["abilities"]
                   for c in (a.get("additional_cost") or []))


def test_sonata_galaxia_bounds_its_search_by_the_same_x():
    """"cost X or less" and "if X is 2 or more" are the SAME X, so both read
    the one expression rather than a literal."""
    searches = [e for a in _raw("sonata_galaxia_red")["abilities"]
                for e in a.get("effects", []) if e.get("type") == "SEARCH_DECK"]
    assert searches, "the search clause was lost"
    assert searches[0]["max_cost"] == {"type": "X"}, searches[0].get("max_cost")


# --- aether quickening: Surge -----------------------------------------------

def _amp(n):
    return lambda st, card: st.players[1].class_counters.__setitem__("amp", n)


def test_aether_quickening_deals_its_three_and_grants_nothing():
    """Exactly 3 is the normal case, and "more than 3" excludes it."""
    st = _state()
    before = st.players[2].life

    points = _resolve_as_layer(st, "aether_quickening_yellow")

    assert before - st.players[2].life == 3, "the printed 3 arcane damage"
    assert points == 0, (
        "go again off exactly 3 damage -- Surge says MORE than 3")


@pytest.mark.parametrize("amp,damage", [(1, 4), (3, 6)])
def test_aether_quickening_surges_when_amped_above_three(amp, damage):
    """Surge asks how much damage ACTUALLY landed, which the printed 3 does not
    answer -- amp raises it (CR 8.5.47) and prevention can lower it."""
    st = _state()
    before = st.players[2].life

    points = _resolve_as_layer(st, "aether_quickening_yellow", setup=_amp(amp))

    assert before - st.players[2].life == damage, "amp %d applied" % amp
    assert points == 1, (
        "dealt %d damage, more than 3, and Surge did not fire" % damage)


def test_aether_quickening_is_not_a_clash_card():
    """It was gated on ON_CLASH_WIN_REVEALED. Nothing on this card clashes."""
    raw = _raw("aether_quickening_yellow")
    triggers = [a.get("trigger") for a in raw["abilities"]]
    assert not any(t and "CLASH" in t for t in triggers), triggers
    assert not any(c.get("type") == "CHAIN_HIT_COUNT_GTE"
                   for a in raw["abilities"] for c in a.get("conditions", []))


# --- premise ----------------------------------------------------------------

def test_the_printed_text_still_says_what_these_assert():
    idx = json.loads((ROOT / "card_data" / "slug_index.json")
                     .read_text(encoding="utf-8"))["by_slug"]

    def text(slug):
        return (idx[slug].get("functionalText") or "").lower()

    assert "you may discard an ally" in text("man_overboard_yellow")
    assert "if x is 2 or more" in text("sonata_galaxia_red")
    assert "cost x or less" in text("sonata_galaxia_red")
    assert "more than 3 damage" in text("aether_quickening_yellow")
    assert "{h}" not in text("sonata_galaxia_red"), (
        "Sonata Galaxia's text now mentions life; re-check whether the "
        "PAY_LIFE cost that was removed as invented is real after all")
    for slug in REAUTHORED:
        printed = [str(k).lower() for k in (idx[slug].get("keywords") or [])]
        assert "goagain" in printed, slug + " no longer prints go again"
