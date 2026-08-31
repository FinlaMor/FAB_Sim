"""Two more out of the gated-go-again backlog, plus the record of two that
CANNOT be converted yet.

    art_of_the_dragon_blood_red  "when this attacks, if IT IS DRACONIC"
    breakneck_battery_red        "if the DISCARDED CARD has 6 or more {p}"

Neither is a timed event, which is what makes the WHILE_STATIC conversion right
here (CR 6.2.3d) -- but they are safe for opposite reasons, and the difference
is worth stating because it is the judgement the conversion actually needs.

Which card an additional cost discarded is FIXED when the card is played, so
reading it continuously and reading it once give the same answer. Whether the
card IS DRACONIC is not fixed at all: Art of the Dragon: Blood is a NINJA card,
its default answer is no, and the clause only ever pays out because some other
effect makes it Draconic -- possibly after the attack is announced. Continuous
is not merely safe there, it is the only reading that lets the clause fire.

BREAKNECK BATTERY'S COST IS CARD-LEVEL, and finding out why cost two wrong
attempts. Its grant must be a WHILE_STATIC gated on SOURCE_IS_ATTACK, since
that is the only shape conditional_keywords infers from -- but the cost cannot
travel with it. interpreter._run_ability CHECKS AND PAYS an ability's
additional_costs on EVERY dispatch, so an additional_cost on a static discards
a card per attack-power recalculation, and once the hand is empty the unpayable
cost aborts the ability and takes the go again with it. Nor can the cost sit on
a separate effect-less PLAY ability: an ability with no effects is a silent
no-op the hygiene tests reject, correctly. The card-level `cost` is checked for
legality and paid exactly once, when the card is played.

TWO CARDS WERE BLOCKED HERE AND ARE NOW DONE. ram_raider_yellow and
shadow_of_ursur_blue both banish from HAND as an additional cost, and no such
cost type existed -- they were authored against DISCARD_RANDOM and
BANISH_FROM_GRAVEYARD, the wrong zones. Converting them then would have pinned
a wrong cost inside the shape that also strips their printed keyword, turning a
visible gap into an invisible one, so they stayed in the backlog until
BANISH_FROM_HAND was built. See tests/test_banish_from_hand_cost.py.

The guard below is what noticed the block had lifted: it asserted the cost type
did not exist, and failing was the signal to finish the cards.
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
from tests.conftest import (_card_json, _make_state, attack_with, owned_card,
                            recalculate_attack)

load_all_cards()
DB = CardDB()
JSON_ROOT = ROOT / "engine" / "card_effects" / "json"

CONVERTED = ["art_of_the_dragon_blood_red", "breakneck_battery_red"]
FORMERLY_BLOCKED = ["ram_raider_yellow", "shadow_of_ursur_blue"]


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


def _attacking(st, slug):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = 1
    return attack_with(st, c)


def _raw(slug):
    return json.loads(_card_json(JSON_ROOT, slug + ".json")
                      .read_text(encoding="utf-8"))


# --- the printed keyword must be stripped -----------------------------------

@pytest.mark.parametrize("slug", CONVERTED)
def test_the_printed_keyword_is_conditional_now(slug):
    assert "goagain" in conditional_keywords(slug), (
        slug + " still has an unconditional printed go again")


# --- "if it is Draconic" ----------------------------------------------------

def test_art_of_the_dragon_blood_is_not_printed_draconic():
    """The premise, and the reason the card has this clause at all. It is a
    NINJA card; "if it is Draconic" is about a state another effect puts it in,
    so the default answer is NO and the printed go again was simply free."""
    card = copy.deepcopy(DB.get("art_of_the_dragon_blood_red"))
    traits = (card.classes or []) + (card.talents or [])
    assert "Draconic" not in traits, traits


def test_art_of_the_dragon_blood_withholds_go_again_by_default():
    st = _state()
    _attacking(st, "art_of_the_dragon_blood_red")

    recalculate_attack(st)

    assert not _go_again(st), (
        "go again while NOT Draconic -- the gate is decoration again")


def test_art_of_the_dragon_blood_grants_go_again_once_made_draconic():
    st = _state()
    card = _attacking(st, "art_of_the_dragon_blood_red")
    card.talents = list(card.talents or []) + ["Draconic"]

    recalculate_attack(st)

    assert _go_again(st), (
        "made Draconic and still no go again -- the clause is unreachable, "
        "which is indistinguishable from a card that simply has no clause")


def test_art_of_the_dragon_blood_keeps_its_cost_reduction():
    """The other half is a one-shot handed out at announcement, so it stays a
    trigger. Splitting the card must not have dropped it."""
    raw = _raw("art_of_the_dragon_blood_red")
    reducers = [a for a in raw["abilities"]
                if any(e.get("type") == "MODIFY_NEXT_CARD_COST"
                       for e in a.get("effects", []))]
    assert reducers, "the three-use Draconic cost reduction was lost"
    assert reducers[0]["ability_type"] == "TRIGGERED"
    assert reducers[0]["trigger"] == "ON_ATTACK"
    assert reducers[0]["effects"][0]["uses"] == 3, (
        "'the next 3 Draconic cards' is a three-use allowance")


# --- "if the discarded card has 6 or more power" ----------------------------

def _play_paying_the_discard(st, power):
    """Put ONE card of the given power in hand and pay the real cost with it.

    Going through the cost's own pay_fn rather than stamping the card by hand
    is the point: the condition can only answer because paying the cost RECORDS
    what it took, and a test that stamped `discarded_for_this` itself would
    pass even if the cost recorded nothing."""
    card = copy.deepcopy(DB.get("breakneck_battery_red"))
    card.owner = card.controller = 1
    st.players[1].hand.add(owned_card(1, "the_discard", types=["Action"],
                                      base_power=power))

    get_card("breakneck_battery_red").play_cost.pay_fn(card, None, st)

    assert getattr(card, "discarded_for_this", None), (
        "paying the discard cost recorded nothing, so no later effect can ask "
        "what was discarded")
    return attack_with(st, card)


def test_breakneck_battery_grants_go_again_for_a_six_power_discard():
    st = _state()
    _play_paying_the_discard(st, 6)

    recalculate_attack(st)

    assert _go_again(st), "a 6-power card was discarded, so go again is due"


def test_breakneck_battery_withholds_go_again_for_a_small_discard():
    """The half that was broken. The card is a gamble on a random discard, and
    the printed keyword made it pay out every time."""
    st = _state()
    _play_paying_the_discard(st, 1)

    recalculate_attack(st)

    assert not _go_again(st), (
        "go again off a 1-power discard -- the gamble is decoration again")


def test_breakneck_battery_still_costs_a_discard_to_play():
    """If the card-level cost were dropped, this card would become free to play
    and no other test would notice."""
    card_def = get_card("breakneck_battery_red")
    costs = [c for c in [card_def.play_cost] if c is not None]
    assert costs, "the additional discard cost was lost"

    st = _state()
    card = copy.deepcopy(DB.get("breakneck_battery_red"))
    card.owner = card.controller = 1
    checks = [c.check_fn for c in costs if c.check_fn is not None]
    assert checks, "the discard cost no longer gates legality at all"
    assert not any(fn(card, None, st) for fn in checks), (
        "an EMPTY hand can still pay 'discard a random card'")

    st.players[1].hand.add(owned_card(1, "fodder", types=["Action"]))
    assert all(fn(card, None, st) for fn in checks), (
        "a card in hand cannot pay the discard, so the card is unplayable")


def test_breakneck_battery_declares_the_cost_as_a_cost():
    """It must stay an `additional_cost`, not become an effect.

    Modelling "as an additional cost, discard a random card" as a discard
    EFFECT is the recorded mistake: a cost has to block play legality, and an
    effect runs on resolution, when the card is already committed.
    """
    raw = _raw("breakneck_battery_red")
    assert raw.get("cost", {}).get("type") == "DISCARD_RANDOM", (
        "the card-level discard cost is gone")
    assert not any(e.get("type", "").startswith("DISCARD")
                   for a in raw["abilities"] for e in a.get("effects", [])), (
        "the discard came back as an EFFECT; it is a cost, and a cost has to "
        "block legality rather than run on resolution")


# --- the two that WERE blocked ---------------------------------------------

def test_the_hand_banish_cost_now_exists():
    """This test used to assert the OPPOSITE -- that BANISH_FROM_HAND did not
    exist -- as the premise for leaving two cards unfinished. Its failing is
    what said the block had lifted."""
    source = (ROOT / "engine" / "card_effects" / "dsl" / "cost_types.py"
              ).read_text(encoding="utf-8")
    assert "BANISH_FROM_HAND" in source


@pytest.mark.parametrize("slug", FORMERLY_BLOCKED)
def test_a_formerly_blocked_card_is_out_of_the_backlog(slug):
    from tests.test_conditional_go_again_ratchet import _unstripped
    assert slug not in _unstripped(), (
        slug + " is back in the backlog; its printed go again is unconditional "
        "again")


# --- premise ----------------------------------------------------------------

def test_the_printed_text_still_says_what_these_assert():
    idx = json.loads((ROOT / "card_data" / "slug_index.json")
                     .read_text(encoding="utf-8"))["by_slug"]

    def text(slug):
        return (idx[slug].get("functionalText") or "").lower()

    assert "if it is draconic" in text("art_of_the_dragon_blood_red")
    assert "discard a random card" in text("breakneck_battery_red")
    assert "6 or more {p}" in text("breakneck_battery_red")
    for slug in CONVERTED:
        printed = [str(k).lower() for k in (idx[slug].get("keywords") or [])]
        assert "goagain" in printed, (
            slug + " no longer PRINTS go again, so there is nothing to strip")
