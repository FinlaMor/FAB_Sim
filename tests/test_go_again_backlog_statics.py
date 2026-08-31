"""Six more out of the gated-go-again backlog: the ones whose condition is a
CONTINUOUS STATE rather than an event.

    soul_cleaver_blue/yellow   "if the defending hero has 1+ cards in their soul"
    scour_the_battlescape_blue "if played from arsenal"
    photon_rush_red            "if you've played a Lightning card this turn"
    runerager_swarm_blue       "if you've played or created an aura this turn"
    soup_up_red                "if an item you control has been destroyed this turn"

These were separated from the rest of the backlog on purpose. WHILE_STATIC
moves a condition from being read ONCE to being read at all times (CR 6.2.3d),
which is a semantic change, and it is only safe where the printed text is a
bare "if <state>" rather than "when this attacks, if ...". Every card here
reads as a state, so the two readings cannot disagree. The remaining backlog
cards say "when this attacks" or "if you do", and are NOT interchangeable this
way -- converting them blind would grant go again on a condition that became
true after the moment the real card checks it.

TWO OF THEM WERE UNREACHABLE, NOT MERELY MIS-SHAPED. photon_rush_red and
runerager_swarm_blue were authored as ACTIVATE abilities with no cost, which a
player can never activate, so the clause never ran at all -- and because the
printed keyword applied regardless, the card played as an UNCONDITIONAL go
again while its gate did nothing. That is the same fail-open shape as the rest
of this backlog, reached by a different route.

runerager_swarm_blue also had a second defect the conversion exposed: it asked
only about CREATED auras, so "played ... an aura" -- the half a Runeblade deck
actually does -- did not count.

Both directions are asserted for every card. The negative alone proves nothing:
an ability that never runs withholds go again exactly as well as a correctly
gated one, which is precisely how these five hid.
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
from engine.effect_keywords import _record_turn_event
from engine.card import CardDB
from engine.card_effects.dsl.loader import (_kw_key, conditional_keywords,
                                            load_all_cards)
from tests.conftest import (_card_json, _make_state, attack_with, owned_card,
                            recalculate_attack)

load_all_cards()
DB = CardDB()
JSON_ROOT = ROOT / "engine" / "card_effects" / "json"

CONVERTED = ["soul_cleaver_blue", "soul_cleaver_yellow",
             "scour_the_battlescape_blue", "photon_rush_red",
             "runerager_swarm_blue", "soup_up_red"]

SOUL_CLEAVERS = ["soul_cleaver_blue", "soul_cleaver_yellow"]


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


# --- the printed keyword must be stripped, or the gate is decoration ---------

@pytest.mark.parametrize("slug", CONVERTED)
def test_the_printed_keyword_is_conditional_now(slug):
    assert "goagain" in conditional_keywords(slug), (
        f"{slug} still has an unconditional printed go again")


@pytest.mark.parametrize("slug", CONVERTED)
def test_the_grant_uses_the_only_shape_that_strips(slug):
    raw = json.loads(_card_json(JSON_ROOT, slug + ".json")
                     .read_text(encoding="utf-8"))
    granting = []
    for ab in raw["abilities"]:
        for eff in ab.get("effects", []):
            name = eff.get("keyword") if eff.get("type") == "GAIN" else eff.get("type")
            if _kw_key(str(name or "")) == "goagain":
                granting.append(ab)
                break
    assert granting, slug + " no longer grants go again at all"
    for ab in granting:
        assert ab["ability_type"] == "WHILE_STATIC", ab["ability_type"]
        types = [c.get("type") for c in ab.get("conditions", [])]
        assert "SOURCE_IS_ATTACK" in types, types


# --- soul cleaver: the DEFENDING hero's soul, not your own ------------------

@pytest.mark.parametrize("slug", SOUL_CLEAVERS)
def test_soul_cleaver_grants_go_again_against_a_stocked_soul(slug):
    st = _state()
    st.players[2].soul.add(owned_card(2, "souled", types=["Action"]))
    _attacking(st, slug)

    recalculate_attack(st)

    assert _go_again(st), "the defending soul is stocked, so go again is due"


@pytest.mark.parametrize("slug", SOUL_CLEAVERS)
def test_soul_cleaver_withholds_go_again_against_an_empty_soul(slug):
    st = _state()
    _attacking(st, slug)

    recalculate_attack(st)

    assert not _go_again(st), (
        "go again against an EMPTY soul -- the gate is decoration again")


@pytest.mark.parametrize("slug", SOUL_CLEAVERS)
def test_soul_cleaver_reads_the_defenders_soul_not_the_attackers(slug):
    """"the DEFENDING hero" is explicit, and reading the wrong player is the
    civic_duty defect: a correct-looking condition pointed at the wrong hero."""
    st = _state()
    st.players[1].soul.add(owned_card(1, "my_soul", types=["Action"]))
    _attacking(st, slug)

    recalculate_attack(st)

    assert not _go_again(st), (
        "go again off the ATTACKER's own soul -- the player is inverted")


# --- "played from arsenal" --------------------------------------------------

def test_scour_the_battlescape_grants_go_again_from_arsenal():
    st = _state()
    card = _attacking(st, "scour_the_battlescape_blue")
    card.played_from_zone = "arsenal"

    recalculate_attack(st)

    assert _go_again(st), "played from arsenal, so go again is due"


def test_scour_the_battlescape_withholds_go_again_from_hand():
    st = _state()
    card = _attacking(st, "scour_the_battlescape_blue")
    card.played_from_zone = "hand"

    recalculate_attack(st)

    assert not _go_again(st), (
        "go again when played from HAND -- the arsenal gate is decoration")


def test_scour_the_battlescape_keeps_its_draw_clause():
    """The conversion rewrote the file, so the unrelated first ability has to
    survive it."""
    raw = json.loads(_card_json(JSON_ROOT, "scour_the_battlescape_blue.json")
                     .read_text(encoding="utf-8"))
    draws = [a for a in raw["abilities"]
             if any(e.get("type") == "DRAW" for e in a.get("effects", []))]
    assert draws, "the put-back-and-draw clause was lost in the conversion"
    assert draws[0].get("additional_cost"), (
        "the draw is no longer gated on putting a card on the bottom")


# --- "if you've played a Lightning card this turn" --------------------------

def test_photon_rush_grants_go_again_after_a_lightning_card():
    st = _state()
    st.players[1].current_turn_effects.append("played_lightning")
    _attacking(st, "photon_rush_red")

    recalculate_attack(st)

    assert _go_again(st), "a Lightning card was played, so Lightning Flow is on"


def test_photon_rush_withholds_go_again_without_one():
    st = _state()
    _attacking(st, "photon_rush_red")

    recalculate_attack(st)

    assert not _go_again(st), (
        "go again with no Lightning card played -- the gate is decoration")


# --- "played OR created an aura" -------------------------------------------

def _swarm(st):
    _attacking(st, "runerager_swarm_blue")
    recalculate_attack(st)
    return _go_again(st)


def test_runerager_swarm_counts_a_created_aura():
    st = _state()
    _record_turn_event(st, 1, "create", "aura")

    assert _swarm(st), "created an aura this turn, so go again is due"


def test_runerager_swarm_counts_a_played_aura():
    """The half the card was missing. It asked only about CREATED auras, so
    playing one -- the commoner action, and the one the sentence names first --
    did not count."""
    st = _state()
    _record_turn_event(st, 1, "play", "aura")

    assert _swarm(st), (
        "played an aura this turn and got no go again; the condition still "
        "only asks about CREATED auras")


def test_runerager_swarm_withholds_go_again_with_no_aura():
    assert not _swarm(_state()), (
        "go again with no aura played or created -- the gate is decoration")


# --- "if an item you control has been destroyed this turn" ------------------

def test_soup_up_grants_go_again_after_an_item_is_destroyed():
    st = _state()
    st.players[1].current_turn_effects.append("destroyed_this_turn:item")
    _attacking(st, "soup_up_red")

    recalculate_attack(st)

    assert _go_again(st), "an item was destroyed this turn, so go again is due"


def test_soup_up_withholds_go_again_with_no_destruction():
    st = _state()
    _attacking(st, "soup_up_red")

    recalculate_attack(st)

    assert not _go_again(st), (
        "go again with no item destroyed -- the gate is decoration")


def test_soup_up_keeps_its_galvanize_defence_trigger():
    """The go again clause was wrongly hung off ON_DEFEND, next to Galvanize.
    Moving it must not have taken Galvanize with it."""
    raw = json.loads(_card_json(JSON_ROOT, "soup_up_red.json")
                     .read_text(encoding="utf-8"))
    defends = [a for a in raw["abilities"] if a.get("trigger") == "ON_DEFEND"]
    assert len(defends) == 1, (
        "expected exactly the Galvanize defend trigger, got %d" % len(defends))
    assert any(e.get("type") == "MAY" for e in defends[0]["effects"])


# --- premise ----------------------------------------------------------------

def test_the_printed_text_still_says_what_these_assert():
    idx = json.loads((ROOT / "card_data" / "slug_index.json")
                     .read_text(encoding="utf-8"))["by_slug"]

    def text(slug):
        return (idx[slug].get("functionalText") or "").lower()

    assert "1 or more cards in their soul" in text("soul_cleaver_blue")
    assert "played from arsenal" in text("scour_the_battlescape_blue")
    assert "played a lightning card this turn" in text("photon_rush_red")
    assert "played or created an aura this turn" in text("runerager_swarm_blue")
    assert "has been destroyed this turn" in text("soup_up_red")
    for slug in CONVERTED:
        printed = [str(k).lower() for k in (idx[slug].get("keywords") or [])]
        assert "goagain" in printed, (
            slug + " no longer PRINTS go again, so there is nothing to strip "
            "and this whole file is measuring nothing")
