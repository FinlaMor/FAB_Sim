"""Cards converted out of the gated-go-again backlog, with behaviour asserted.

The backlog is 40 cards that PRINT go again while their text gates it. The
engine applies a printed keyword unconditionally, so for every one of them the
gate is decoration and the card is strictly stronger than printed.

`loader.conditional_keywords()` is what takes the printed keyword away, and it
recognises exactly one shape: a SOURCE_IS_ATTACK-gated ability that grants the
keyword. WHILE_STATIC rather than TRIGGERED because CR 6.2.3d evaluates a
conditional static-continuous effect at ALL times rather than once -- which is
also how the ruling on Aggressive Pounce reads.

These two were chosen because they need no fresh judgement: each has a sibling
printing with identical text that was converted and verified earlier, so the
conversion is a copy rather than an interpretation.

    grow_wings_red        <- grow_wings_blue
    blow_for_a_blow_red   <- scar_for_a_scar_red

Both halves are asserted: the printed keyword must be STRIPPED (or the gate
cannot bite), and the ability must actually grant go again when the condition
holds and withhold it when it does not.
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
from engine.card_effects.dsl.loader import (conditional_keywords, get_card,
                                            load_all_cards)
from tests.conftest import _card_json, _make_state, attack_with, recalculate_attack

load_all_cards()
DB = CardDB()

CONVERTED = ["grow_wings_red", "blow_for_a_blow_red"]


def _state():
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="": o[0]
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    return st


def _go_again(st):
    return any("go again" in str(k).replace("Go", "go").lower()
               for k in st.combat.keywords)


def _attacking(st, slug):
    c = copy.deepcopy(DB.get(slug))
    c.owner = c.controller = 1
    return attack_with(st, c)


# --- the printed keyword must be stripped -----------------------------------

@pytest.mark.parametrize("slug", CONVERTED)
def test_the_printed_keyword_is_conditional_now(slug):
    assert "goagain" in conditional_keywords(slug), (
        f"{slug} still has an unconditional printed go again, so its gate is "
        "decoration")


@pytest.mark.parametrize("slug", CONVERTED)
def test_the_grant_is_gated_on_source_is_attack(slug):
    """The shape is not incidental: conditional_keywords recognises only this
    one, and a TRIGGERED version leaves the printed keyword in place."""
    raw = json.loads(_card_json(ROOT / "engine" / "card_effects" / "json",
                                f"{slug}.json").read_text(encoding="utf-8"))
    granting = [a for a in raw["abilities"]
                if any(str(e.get("keyword", "")).upper() == "GO_AGAIN"
                       or str(e.get("type", "")).upper() == "GO_AGAIN"
                       for e in a.get("effects", []))]
    assert granting, f"{slug} no longer grants go again at all"
    for ab in granting:
        types = [c.get("type") for c in ab.get("conditions", [])]
        assert ab["ability_type"] == "WHILE_STATIC", ab["ability_type"]
        assert "SOURCE_IS_ATTACK" in types, types


# --- and the gate must actually bite ----------------------------------------

def test_blow_for_a_blow_grants_go_again_when_behind_on_life():
    st = _state()
    st.players[1].life = 5
    st.players[2].life = 20
    _attacking(st, "blow_for_a_blow_red")

    recalculate_attack(st)

    assert _go_again(st), "behind on life, so go again is due"


def test_blow_for_a_blow_withholds_go_again_when_ahead():
    """The half that was broken for every card in this backlog.

    NOT SUFFICIENT ON ITS OWN, and this was checked rather than assumed:
    reverting the card to its old PLAY-shaped ability leaves this test PASSING,
    because an ability that never runs withholds go again exactly as well as
    one that is correctly gated. It is the PAIR that demonstrates gating -- the
    positive test below fails on that same revert, as does the stripping test.
    Anyone converting the remaining 40 needs both halves.
    """
    st = _state()
    st.players[1].life = 20
    st.players[2].life = 5
    _attacking(st, "blow_for_a_blow_red")

    recalculate_attack(st)

    assert not _go_again(st), (
        "go again while AHEAD on life -- the gate is decoration again")


def test_blow_for_a_blow_keeps_its_other_clause():
    """"When this hits, deal 1 damage" is a separate ability and the conversion
    must not have eaten it."""
    raw = json.loads(_card_json(ROOT / "engine" / "card_effects" / "json",
                                "blow_for_a_blow_red.json")
                     .read_text(encoding="utf-8"))
    triggers = [a.get("trigger") for a in raw["abilities"]]
    assert "ON_HIT" in triggers, triggers


# --- parity with the sibling that was verified first ------------------------

def test_grow_wings_red_matches_its_already_fixed_blue_sibling():
    """Identical printed text, so identical implementation. If they ever drift
    apart, one of them is wrong."""
    root = ROOT / "engine" / "card_effects" / "json"
    red = json.loads(_card_json(root, "grow_wings_red.json")
                     .read_text(encoding="utf-8"))["abilities"]
    blue = json.loads(_card_json(root, "grow_wings_blue.json")
                      .read_text(encoding="utf-8"))["abilities"]
    assert red == blue, "the two printings no longer implement the same card"


def test_the_two_cards_still_say_what_this_assumes():
    idx = json.loads((ROOT / "card_data" / "slug_index.json")
                     .read_text(encoding="utf-8"))["by_slug"]
    assert (idx["grow_wings_red"].get("functionalText")
            == idx["grow_wings_blue"].get("functionalText")), (
        "the printings' texts have diverged, so copying the implementation is "
        "no longer justified")
    assert "less {h} than an opposing hero" in (
        idx["blow_for_a_blow_red"].get("functionalText") or "")
