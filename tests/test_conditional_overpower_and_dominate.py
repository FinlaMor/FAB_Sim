"""Six more gated-keyword cards, and an engine defect three of them sat on.

    hydraulic_press_blue      "if IT SCRAPPED a card, this gets overpower"
    spectral_rider_red        "if you control a Spectral Shield, this gains
                              overpower"
    the_golden_son_yellow     "you may destroy a Gold. If you do, +3{p} and
                              overpower"
    burly_bones_red/blue      "discard a card OR destroy the top card of your
                              deck. If that card has watery grave, overpower"
    writhing_beast_hulk_red   "banish 3 random cards from your graveyard. If a
                              card with 6+ {p} is banished this way, dominate"

Only one of these was merely mis-shaped. The rest were implemented against
something the card does not say, and each failed in a way that left the printed
keyword paying out regardless:

  hydraulic_press   gated on HAS_KEYWORD "Scrap" -- whether the card PRINTS the
                    keyword, which it always does. The gate was a tautology.

  spectral_rider    granted a SUBTYPE called "Overpower" (GRANT_SUBTYPE), not
                    the keyword. Nothing reads a subtype by that name.

  burly_bones       did BOTH halves of an "or", MANDATORILY, and gated the
                    payoff on REF_PITCH_IS "watery_grave" -- a card's PITCH
                    VALUE compared against a keyword name, which can never be
                    true.

EFFECT_DOMINATE WAS ERASING ITSELF, and that is not specific to these cards. It
appended "Dominate" straight to combat.keywords, bypassing grant_keyword, so it
never entered keyword_effects -- and _recalculate_attack_power rebuilds
combat.keywords from scratch on every recalculation and unions back only
keyword_effects. Every granted Dominate was wiped by the next recalculation of
the attack it was granted to. Five cards use the effect. Nothing failed loudly:
the defending player simply got to block with as many cards as they liked.

That defect was invisible until Writhing Beast Hulk's printed Dominate was
stripped. While the printed keyword applied unconditionally it covered for the
grant, so the card looked correct in every test -- which is the same reason
this whole class of defect survives audits.
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
from engine.card_effects.ability_keywords import effect_dominate
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import (_kw_key, conditional_keywords,
                                            get_card, load_all_cards)
from engine.effect_keywords import TURN_EVENT_MARKER
from tests.conftest import (_card_json, _make_state, attack_with, owned_card,
                            recalculate_attack)

load_all_cards()
DB = CardDB()
JSON_ROOT = ROOT / "engine" / "card_effects" / "json"

OVERPOWER_CARDS = ["hydraulic_press_blue", "spectral_rider_red",
                   "the_golden_son_yellow", "burly_bones_red",
                   "burly_bones_blue"]


def _state(picker=None):
    st = _make_state()
    st.card_db = DB
    pick = picker or (lambda s, o, context="": o[0])
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    return st


def _has(st, word):
    return any(_kw_key(k) == _kw_key(word) for k in st.combat.keywords)


def _play(st, slug, setup=None):
    card = copy.deepcopy(DB.get(slug))
    assert card is not None, slug
    card.owner = card.controller = 1
    attack_with(st, card)
    if setup:
        setup(st, card)
    for ability in get_card(slug).abilities:
        run_ability(ability, card, None, st)
    recalculate_attack(st)
    return card


def _raw(slug):
    return json.loads(_card_json(JSON_ROOT, slug + ".json")
                      .read_text(encoding="utf-8"))


@pytest.mark.parametrize("slug", OVERPOWER_CARDS)
def test_the_printed_overpower_is_conditional_now(slug):
    assert "overpower" in conditional_keywords(slug), slug


# --- "if IT scrapped a card" ------------------------------------------------

def test_hydraulic_press_gains_overpower_only_if_it_scrapped():
    st = _state()
    st.players[1].current_turn_effects.append(
        TURN_EVENT_MARKER + "scrap:hydraulicpressblue")
    _play(st, "hydraulic_press_blue")

    assert _has(st, "overpower"), "it scrapped a card, so overpower is due"


def test_hydraulic_press_withholds_overpower_if_it_scrapped_nothing():
    st = _state()
    _play(st, "hydraulic_press_blue")

    assert not _has(st, "overpower"), (
        "overpower with nothing scrapped -- the gate is decoration again")


def test_hydraulic_press_no_longer_asks_whether_it_prints_scrap():
    """The old gate was HAS_KEYWORD "Scrap": whether the card PRINTS the
    keyword, which it always does. A tautology reads exactly like a working
    condition -- real type, real parameter, always true."""
    conditions = [c["type"] for a in _raw("hydraulic_press_blue")["abilities"]
                  for c in a.get("conditions", [])]
    assert "HAS_KEYWORD" not in conditions
    assert "SCRAPPED" in conditions


# --- "if you control a Spectral Shield" -------------------------------------

def _shield(st, card):
    token = owned_card(1, "spectral_shield", types=["Token"])
    token.name = "Spectral Shield"
    token.subtypes = ["Spectral Shield"]
    st.players[1].permanents.add(token)


def test_spectral_rider_gains_overpower_with_a_shield():
    st = _state()
    _play(st, "spectral_rider_red", _shield)

    assert _has(st, "overpower"), "a Spectral Shield is out, so overpower is due"


def test_spectral_rider_withholds_overpower_without_one():
    st = _state()
    _play(st, "spectral_rider_red")

    assert not _has(st, "overpower"), (
        "overpower with no Spectral Shield -- the gate is decoration again")


def test_spectral_rider_grants_a_keyword_not_a_subtype():
    """It used GRANT_SUBTYPE subtype "Overpower", which adds a SUBTYPE by that
    name. Nothing reads one, so the clause did nothing at all."""
    raw = _raw("spectral_rider_red")
    assert not any(e.get("type") == "GRANT_SUBTYPE"
                   for a in raw["abilities"] for e in a.get("effects", []))
    assert any(e.get("type") == "GAIN" and _kw_key(e.get("keyword", "")) == "overpower"
               for a in raw["abilities"] for e in a.get("effects", []))


# --- "you may destroy a Gold" -----------------------------------------------

def _gold(st, card):
    token = owned_card(1, "gold", types=["Token"])
    token.name = "Gold"
    token.subtypes = ["Gold"]
    st.players[1].permanents.add(token)


def test_the_golden_son_pays_off_when_a_gold_is_destroyed():
    st = _state()
    card = _play(st, "the_golden_son_yellow", _gold)

    assert st.combat.attack_power == (card.base_power or 0) + 3, "the +3{p} half"
    assert _has(st, "overpower"), "destroyed a Gold, so overpower is due"


def test_the_golden_son_gives_nothing_when_the_gold_is_kept():
    st = _state(lambda s, o, context="": o[-1])
    card = _play(st, "the_golden_son_yellow", _gold)

    assert st.combat.attack_power == (card.base_power or 0)
    assert not _has(st, "overpower"), (
        "kept the Gold and got overpower anyway -- the trade is free again")


def test_the_golden_son_gives_nothing_with_no_gold_at_all():
    st = _state()
    card = _play(st, "the_golden_son_yellow")

    assert st.combat.attack_power == (card.base_power or 0)
    assert not _has(st, "overpower")


# --- "discard a card OR destroy the top card of your deck" ------------------

def _burly(branch, watery, decline=False):
    def pick(s, options, context=""):
        if "discard a card or destroy" in str(context).lower():
            return options[-1] if decline else options[0]
        return options[branch] if len(options) > branch else options[0]

    st = _state(pick)
    hand_card = owned_card(1, "hand_card", types=["Action"])
    deck_card = owned_card(1, "deck_card", types=["Action"])
    if watery == "hand":
        hand_card.keywords = ["WateryGrave"]
    if watery == "deck":
        deck_card.keywords = ["WateryGrave"]
    st.players[1].hand.add(hand_card)
    st.players[1].deck.add(deck_card)
    # "the top card of YOUR deck". The opponent's deck is stocked so a
    # wrong-deck regression is visible: LOOK_AT defaults to the OPPONENT's deck
    # when the player is not named, and five cards were reading the wrong one.
    st.players[2].deck.add(owned_card(2, "their_card", types=["Action"]))
    _play(st, "burly_bones_red")
    return st


def test_burly_bones_discard_branch_pays_off_on_watery_grave():
    st = _burly(branch=0, watery="hand")

    assert [c.slug for c in st.players[1].graveyard.cards] == ["hand_card"]
    assert [c.slug for c in st.players[1].deck.cards] == ["deck_card"], (
        "the deck was touched too -- the OR is being done as an AND again")
    assert _has(st, "overpower")


def test_burly_bones_discard_branch_withholds_without_watery_grave():
    st = _burly(branch=0, watery=None)
    assert not _has(st, "overpower")


def test_burly_bones_destroy_branch_pays_off_on_watery_grave():
    st = _burly(branch=1, watery="deck")

    assert [c.slug for c in st.players[1].graveyard.cards] == ["deck_card"]
    assert [c.slug for c in st.players[1].hand.cards] == ["hand_card"], (
        "the hand was discarded too -- the OR is being done as an AND again")
    assert [c.slug for c in st.players[2].deck.cards] == ["their_card"], (
        "destroyed the OPPONENT's deck top; the card says YOUR deck")
    assert _has(st, "overpower")


def test_burly_bones_destroy_branch_withholds_without_watery_grave():
    st = _burly(branch=1, watery=None)
    assert not _has(st, "overpower")


def test_burly_bones_can_be_declined_entirely():
    """"You MAY discard a card or destroy the top card." The old version did
    both, mandatorily, every attack."""
    st = _burly(branch=0, watery="hand", decline=True)

    assert not st.players[1].graveyard.cards, "discarded despite declining"
    assert [c.slug for c in st.players[1].deck.cards] == ["deck_card"]
    assert not _has(st, "overpower")


def test_burly_bones_no_longer_tests_a_pitch_value_against_a_keyword():
    """REF_PITCH_IS compares a stored card's PITCH VALUE. "watery grave" is a
    keyword, so the condition could never be true."""
    abilities = json.dumps(_raw("burly_bones_red")["abilities"])
    assert "REF_PITCH_IS" not in abilities
    assert "REF_HAS_KEYWORD" in abilities


def test_the_two_burly_bones_printings_share_an_implementation():
    assert _raw("burly_bones_red")["abilities"] == _raw("burly_bones_blue")["abilities"]


# --- the engine defect: a granted Dominate used to erase itself -------------

def test_a_granted_dominate_survives_recalculation():
    """effect_dominate appended straight to combat.keywords, bypassing
    grant_keyword, so it never entered keyword_effects -- and
    _recalculate_attack_power rebuilds combat.keywords from scratch and unions
    back only keyword_effects. Five cards use this effect."""
    st = _state()
    attacker = owned_card(1, "plain_attack", types=["Action"], base_power=4)
    attacker.subtypes = ["Attack"]
    attack_with(st, attacker)

    effect_dominate(st, 1)
    assert _has(st, "dominate"), "premise: the grant lands at all"

    recalculate_attack(st)

    assert _has(st, "dominate"), (
        "the granted Dominate was erased by a recalculation of the very attack "
        "it was granted to")


def test_a_granted_dominate_is_not_listed_twice():
    """CR 8.3.4 is a static ability, and grant_keyword refuses a duplicate.
    Granting it to an attack that already prints it should not double-list."""
    st = _state()
    attacker = owned_card(1, "dominating", types=["Action"], base_power=4)
    attacker.subtypes = ["Attack"]
    attacker.keywords = ["Dominate"]
    attack_with(st, attacker)

    effect_dominate(st, 1)

    listed = [k for k in st.combat.keywords if _kw_key(k) == "dominate"]
    assert len(listed) == 1, listed


# --- "if a card with 6 or more {p} is banished this way" --------------------

def _hulk(powers):
    st = _state()
    card = copy.deepcopy(DB.get("writhing_beast_hulk_red"))
    card.owner = card.controller = 1
    for i, power in enumerate(powers):
        st.players[1].graveyard.add(
            owned_card(1, "gy%d" % i, types=["Action"], base_power=power))
    attack_with(st, card)
    for ability in get_card("writhing_beast_hulk_red").abilities:
        run_ability(ability, card, None, st)
    recalculate_attack(st)
    return st


def test_writhing_beast_hulk_gains_dominate_for_a_big_banish():
    st = _hulk([6, 1, 1])

    assert len(st.players[1].banished.cards) == 3, "the cost was paid"
    assert _has(st, "dominate"), "a 6-power card was banished, so dominate is due"


def test_writhing_beast_hulk_withholds_dominate_for_small_banishes():
    st = _hulk([1, 1, 1])

    assert len(st.players[1].banished.cards) == 3
    assert not _has(st, "dominate"), (
        "dominate off three 1-power cards -- the gate is decoration again")


def test_writhing_beast_hulk_keeps_its_cost_on_the_ability():
    """Forced, not stylistic. The power test reads a REF the cost stores, and
    refs are scoped to ONE ability execution -- moving the cost to card level
    would pay it in play.py, outside that scope, and the ref would be gone."""
    raw = _raw("writhing_beast_hulk_red")
    assert raw.get("cost") is None
    costed = [a for a in raw["abilities"] if a.get("additional_cost")]
    assert costed and costed[0]["ability_type"] == "PLAY"


# --- premise ----------------------------------------------------------------

def test_the_printed_text_still_says_what_these_assert():
    idx = json.loads((ROOT / "card_data" / "slug_index.json")
                     .read_text(encoding="utf-8"))["by_slug"]

    def text(slug):
        return (idx[slug].get("functionalText") or "").lower()

    assert "if it scrapped a card" in text("hydraulic_press_blue")
    assert "spectral shield" in text("spectral_rider_red")
    assert "destroy a gold you control" in text("the_golden_son_yellow")
    assert "or destroy the top card of your deck" in text("burly_bones_red")
    assert "watery grave" in text("burly_bones_red")
    assert "6 or more {p} is banished this way" in text("writhing_beast_hulk_red")
    for slug in OVERPOWER_CARDS:
        printed = [str(k).lower() for k in (idx[slug].get("keywords") or [])]
        assert "overpower" in printed, slug + " no longer prints Overpower"
    assert "dominate" in [
        str(k).lower() for k in (idx["writhing_beast_hulk_red"].get("keywords") or [])]
