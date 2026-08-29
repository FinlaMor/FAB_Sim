"""Three more ported cards, one of which I nearly "fixed" by breaking it.

    cheers_blue           "when this ENTERS OR LEAVES the arena, the crowd
                          cheers you"
    chest_puff_red        "it gets -1{p} UNLESS you pay {r}"
    flash_of_brilliance   "you MAY discard a Lightning card"

cheers_blue looks defective and is not. Its text has two halves and its JSON
authors only ON_LEAVE_PLAY, which is exactly the shape of a real defect found
elsewhere ("attacks OR DEFENDS" implemented on one side only). But
TheCrowdCheers is a PRINTED keyword, and build_keyword_triggers already
registers an on_play effect_crowd_cheers for it (triggers.py:376). The enter
half is therefore covered by the card database, and authoring ON_ENTER_PLAY +
CROWD_CHEERS on top would cheer TWICE on every normal play -- the
keyword-reimplemented defect recorded for heroic_pose_blue and
shining_courage_red.

So the test here guards the ABSENCE. Someone reading the text and the JSON side
by side will eventually "fix" this card, and this is what tells them not to.
The card's own _comment reached that conclusion before I did; I checked the
keyword registration rather than take it on faith, and it was right.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.card_effects.triggers.triggers import build_keyword_triggers
from tests.conftest import (_card_json, _make_state, attack_with,
                            give_permanent, owned_card, recalculate_attack)

load_all_cards()
DB = CardDB()


def _state():
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="": o[0]
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    return st


def _src(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _cheered(st, pid):
    return st.players[pid].current_turn_effects.count("crowd_cheered")


# --- the enter half belongs to the KEYWORD, not the JSON ---------------------

def test_the_printed_keyword_supplies_the_enter_half():
    """The premise for leaving ON_ENTER_PLAY unauthored. If this stops being
    true the card really does need the enter half written."""
    card = _src("cheers_blue")
    events = [t.event_type for t in build_keyword_triggers(card)]
    assert "on_play" in events, (
        "TheCrowdCheers no longer registers an on_play trigger, so the ENTER "
        "half of this card is now genuinely missing and must be authored")


def test_cheers_blue_does_not_author_an_enter_trigger():
    """Guarding an ABSENCE. Reading the text against the JSON invites a fix
    that would cheer twice on every play."""
    raw = json.loads(_card_json(ROOT / "engine" / "card_effects" / "json",
                                "cheers_blue.json").read_text(encoding="utf-8"))
    triggers = [a.get("trigger") for a in raw["abilities"]]
    assert "ON_ENTER_PLAY" not in triggers, (
        "an ON_ENTER_PLAY was added, but TheCrowdCheers already cheers on "
        "play -- this now cheers TWICE, which is the heroic_pose_blue defect")


def test_cheers_blue_cheers_once_when_it_leaves():
    st = _state()
    src = _src("cheers_blue")

    run_ability(get_card("cheers_blue").abilities[0], src, None, st)

    assert _cheered(st, 1) == 1, (
        f"expected exactly one cheer on leaving, got {_cheered(st, 1)}")


# --- "unless you pay" -------------------------------------------------------

def test_chest_puff_loses_power_when_the_payment_is_declined():
    st = _state()
    st.players[1].resources = 0
    card = attack_with(st, _src("chest_puff_red"))
    base = st.combat.attack_power

    run_ability(get_card("chest_puff_red").abilities[0], card, None, st)

    assert st.combat.attack_power == base - 1, (
        "with no resources the -1 should apply; 'unless you pay' is the whole "
        "card")


def test_chest_puff_keeps_its_power_when_paid():
    st = _state()
    st.players[1].resources = 3
    card = attack_with(st, _src("chest_puff_red"))
    base = st.combat.attack_power

    run_ability(get_card("chest_puff_red").abilities[0], card, None, st)

    assert st.combat.attack_power == base, (
        "paid the {r} and still lost power -- the payment is not being "
        "honoured")


# --- "you MAY discard" ------------------------------------------------------

def _flash(st, lightning_in_hand):
    give_permanent(st, 1, owned_card(1, "real_aura", types=["Action"]),
                   subtype="Aura")
    if lightning_in_hand:
        c = owned_card(1, "bolt", types=["Action"])
        c.talents = ["Lightning"]
        c.classes = ["Lightning"]
        st.players[1].hand.add(c)
    run_ability(get_card("flash_of_brilliance").abilities[0],
                _src("flash_of_brilliance"), None, st)
    return len(list(st.players[1].auras.cards))


def test_flash_of_brilliance_returns_an_aura_when_it_can_discard():
    """The aura is typed Action, as a real FAB aura is. A ["Token"] fixture is
    rejected by the hand's zone-entry rules, put_object comes back CANCELED,
    and the card looks like it drops its second clause."""
    assert _flash(_state(), lightning_in_hand=True) == 0, (
        "discarded a Lightning card but did not return the aura")


def test_flash_of_brilliance_does_nothing_without_a_lightning_card():
    assert _flash(_state(), lightning_in_hand=False) == 1, (
        "returned an aura with no Lightning card to discard")


def test_the_printed_text_still_says_what_these_assert():
    idx = json.loads((ROOT / "card_data" / "slug_index.json")
                     .read_text(encoding="utf-8"))["by_slug"]
    assert "enters or leaves the arena" in (
        idx["cheers_blue"].get("functionalText") or "").lower()
    assert "unless you pay" in (
        idx["chest_puff_red"].get("functionalText") or "").lower()
    assert "lightning card" in (
        idx["flash_of_brilliance"].get("functionalText") or "").lower()
