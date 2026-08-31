"""Two cards banish from HAND as an additional cost, and there was no cost type
for it.

    ram_raider_yellow     "as an additional cost, banish a RANDOM card from
                          your hand. If a card with 6 or more {p} is banished
                          this way, this gets go again."
    shadow_of_ursur_blue  "as an additional cost, YOU MAY banish a card with
                          blood debt from your hand. If you do, it gains go
                          again."

Both were authored against the nearest cost that existed, and neither is a
weaker version of the printed cost -- each is a different one:

  DISCARD_RANDOM          puts the card in the GRAVEYARD, which a Shadow deck
  (Ram Raider)            can get back. Banishing it is the price the card
                          charges.

  BANISH_FROM_GRAVEYARD   wrong zone AND mandatory. An OPTIONAL additional cost
  (Shadow of Ursur)       must never block a play (CR 5.1.6), so this made the
                          card uncastable with no blood-debt card available --
                          strictly worse than the free go again the unconditional
                          printed keyword was handing out on the other side.

WHY THE COST IS CARD-LEVEL ON BOTH. interpreter._run_ability re-checks and
re-pays an ability's additional_costs on EVERY dispatch. Their grants are
WHILE_STATIC (the shape conditional_keywords infers from, without which the
printed go again stays unconditional), and a static runs on every attack-power
recalculation -- so an ability-level cost would banish a card per recalculation
and then abort the ability once the hand emptied. The card-level `cost` is
checked for legality and paid once.

"THIS WAY" NEEDED SOMEWHERE TO LOOK. The banished zone holds every card
banished all game, by anyone, for any reason, so it cannot answer what THIS
card's cost took. cost_types._stamp_banished records it on the card being
played, mirroring play.py's pitched_for_this and the discard stamp added for
Breakneck Battery.
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
from engine.card_effects.dsl.loader import (_kw_key, conditional_keywords,
                                            get_card, load_all_cards)
from tests.conftest import (_card_json, _make_state, attack_with, owned_card,
                            recalculate_attack)

load_all_cards()
DB = CardDB()
JSON_ROOT = ROOT / "engine" / "card_effects" / "json"

CARDS = ["ram_raider_yellow", "shadow_of_ursur_blue"]


def _state(accept=True):
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="": (o[0] if accept else o[-1])
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    return st


def _go_again(st):
    return any(_kw_key(k) == "goagain" for k in st.combat.keywords)


def _card(slug):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = 1
    return c


def _pay_and_attack(st, slug):
    card = _card(slug)
    cost = get_card(slug).play_cost
    payable = cost.check_fn(card, None, st)
    cost.pay_fn(card, None, st)
    attack_with(st, card)
    recalculate_attack(st)
    return card, payable


def _raw(slug):
    return json.loads(_card_json(JSON_ROOT, slug + ".json")
                      .read_text(encoding="utf-8"))


# --- the cost takes from the right zone -------------------------------------

@pytest.mark.parametrize("slug", CARDS)
def test_the_cost_is_a_hand_banish(slug):
    raw = _raw(slug)
    assert raw.get("cost", {}).get("type") == "BANISH_FROM_HAND", (
        slug + " is no longer paying a hand banish")


def test_ram_raider_banishes_rather_than_discards():
    """A discarded card is in the graveyard, where the deck can get it back.
    That is a different card."""
    st = _state()
    st.players[1].hand.add(owned_card(1, "fodder", types=["Action"],
                                      base_power=6))

    _pay_and_attack(st, "ram_raider_yellow")

    assert [c.slug for c in st.players[1].banished.cards] == ["fodder"]
    assert not st.players[1].graveyard.cards, (
        "the card went to the GRAVEYARD -- this is a discard, not a banish")


def test_ram_raider_grants_go_again_for_a_six_power_banish():
    st = _state()
    st.players[1].hand.add(owned_card(1, "fodder", types=["Action"],
                                      base_power=6))

    _pay_and_attack(st, "ram_raider_yellow")

    assert _go_again(st), "banished a 6-power card, so go again is due"


def test_ram_raider_withholds_go_again_for_a_small_banish():
    """The gamble the card is built around. The printed keyword paid it out
    every time."""
    st = _state()
    st.players[1].hand.add(owned_card(1, "fodder", types=["Action"],
                                      base_power=1))

    _pay_and_attack(st, "ram_raider_yellow")

    assert not _go_again(st), (
        "go again off a 1-power banish -- the 6-power gate is decoration")


def test_ram_raider_cannot_be_played_with_an_empty_hand():
    """Its cost is NOT optional, so it has to block legality. A cost that does
    not is the recorded failure mode: the card becomes playable when its price
    cannot actually be paid."""
    st = _state()
    card = _card("ram_raider_yellow")

    assert not get_card("ram_raider_yellow").play_cost.check_fn(card, None, st)

    st.players[1].hand.add(owned_card(1, "anything", types=["Action"]))
    assert get_card("ram_raider_yellow").play_cost.check_fn(card, None, st)


# --- the optional cost must never block the play ----------------------------

def _ursur(st, blood_debt):
    if blood_debt:
        bd = owned_card(1, "bd_card", types=["Action"])
        bd.keywords = ["BloodDebt"]
        st.players[1].hand.add(bd)
    st.players[1].hand.add(owned_card(1, "plain", types=["Action"]))
    return _pay_and_attack(st, "shadow_of_ursur_blue")


def test_shadow_of_ursur_is_playable_with_no_blood_debt_card():
    """The defect this replaced. As a MANDATORY graveyard banish, an empty
    graveyard made the card uncastable -- an optional additional cost that
    blocks the play is a strictly worse bug than the free keyword it sat
    next to."""
    st = _state()
    _, payable = _ursur(st, blood_debt=False)

    assert payable, (
        "an OPTIONAL additional cost is blocking the play (CR 5.1.6)")


def test_shadow_of_ursur_gains_go_again_when_it_banishes():
    st = _state()
    _ursur(st, blood_debt=True)

    assert [c.slug for c in st.players[1].banished.cards] == ["bd_card"]
    assert _go_again(st), "banished a blood debt card, so go again is due"


def test_shadow_of_ursur_withholds_go_again_when_declined():
    st = _state(accept=False)
    _ursur(st, blood_debt=True)

    assert not st.players[1].banished.cards, "banished despite declining"
    assert not _go_again(st), "declined the cost and still got go again"


def test_shadow_of_ursur_withholds_go_again_with_nothing_eligible():
    """"If you do" covers being unable to as well as choosing not to."""
    st = _state()
    _ursur(st, blood_debt=False)

    assert not st.players[1].banished.cards
    assert not _go_again(st), "go again with no blood debt card to banish"


def test_shadow_of_ursur_only_banishes_a_blood_debt_card():
    """A plain card sits in hand alongside; an unfiltered cost would take it."""
    st = _state()
    _ursur(st, blood_debt=True)

    assert "plain" not in [c.slug for c in st.players[1].banished.cards], (
        "banished a card WITHOUT blood debt -- the filter is not filtering")


# --- the printed keyword, and the shape that strips it ----------------------

@pytest.mark.parametrize("slug", CARDS)
def test_the_printed_keyword_is_conditional_now(slug):
    assert "goagain" in conditional_keywords(slug), slug


@pytest.mark.parametrize("slug", CARDS)
def test_the_cost_is_not_on_the_static(slug):
    """_run_ability re-pays an ability's additional_costs on every dispatch, and
    these grants are WHILE_STATIC -- one per attack-power recalculation."""
    raw = _raw(slug)
    assert not any(a.get("additional_cost") for a in raw["abilities"]), (
        "the cost moved onto an ability; on a WHILE_STATIC that banishes a "
        "card per recalculation and then aborts the ability when the hand runs "
        "out")


# --- premise ----------------------------------------------------------------

def test_the_printed_text_still_says_hand_and_banish():
    idx = json.loads((ROOT / "card_data" / "slug_index.json")
                     .read_text(encoding="utf-8"))["by_slug"]
    for slug in CARDS:
        text = (idx[slug].get("functionalText") or "").lower()
        assert "banish" in text and "from your hand" in text, slug
        printed = [str(k).lower() for k in (idx[slug].get("keywords") or [])]
        assert "goagain" in printed, (
            slug + " no longer prints go again, so there is nothing to strip")
    assert "you may banish" in (
        idx["shadow_of_ursur_blue"].get("functionalText") or "").lower(), (
        "the cost is no longer optional; the legality test above assumes it is")
    assert "banish a random card" in (
        idx["ram_raider_yellow"].get("functionalText") or "").lower()
