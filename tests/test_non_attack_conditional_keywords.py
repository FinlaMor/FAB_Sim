"""A gated go again on a NON-ATTACK card resolves down a different code path,
and that path did not know about conditional keywords.

Attack cards get their go again from `combat.keywords`, rebuilt every
recalculation by `_recalculate_attack_power`, which has stripped conditionally
granted keywords since the gated-go-again work. A non-attack action card never
touches that function. It resolves as a layer, and `resolve_stack` pays the
action point directly (CR 5.3.5 / 8.3.5a) from `card.keywords` and
`card.has_go_again` -- neither of which was filtered.

SO THE FIX SHIPPED FOR ATTACKS WAS INERT FOR NON-ATTACKS, and worse than
inert: `effect_types._grant_go_again` pays its own action point when there is
no combat, so a card whose gate DID hold was paid TWICE. Arc Ramp, measured
before the fix:

    gate not met -> 1 action point   (should be 0 -- a free one)
    gate met     -> 2 action points  (should be 1 -- CR 8.3.5c says an object
                                      cannot have two go agains)

The combat path has always honoured 8.3.5c explicitly. The action-point path
had no such guard, because nothing was expected to grant a go again to a card
that already printed one -- which is exactly what a conditional printed keyword
does.

THIS WAS FOUND BY NOTICING A TEST THAT PASSED ON THE WRONG PATH. arc_ramp_red
was declared conditional alongside eight attack cards, and its behaviour was
asserted with `recalculate_attack` like the others. That helper exercises the
attack path, which Arc Ramp never takes, so the assertion was true and
meaningless. The parametrised guard at the bottom of this file exists so the
next non-attack card to be declared cannot be tested the same way by accident.

Fifteen cards in the corpus have this shape; twelve are not authored yet.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import engine.card_effects.dsl.loader as loader
import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.effect_types import _grant_go_again
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import (conditional_keywords, get_card,
                                            load_all_cards)
from engine.state import StackEntry
from tests.conftest import _make_state, owned_card

load_all_cards()
DB = CardDB()

#: Prints go again, text does NOT gate it, declares nothing. The control: if
#: this stops paying its action point, the stripping has gone too far.
UNGATED_CONTROL = "awakening_bellow_red"


def _state():
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="": o[0]
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    st.combat = None          # a non-attack layer resolves outside combat
    return st


def _resolve_as_layer(st, slug, effect_fn=None, setup=None):
    """Play `slug` as a non-attack card layer and return the action points its
    controller ended up with."""
    card = copy.deepcopy(DB.get(slug))
    assert card is not None, slug
    card.owner = card.controller = 1
    if setup:
        setup(st, card)
    st.players[1].action_points = 0
    st.stack.add(card)
    entry = StackEntry(player_id=1, card=card, layer_type="card",
                       effect_fn=effect_fn or (lambda c, s: None))
    assert not entry.is_attack, (
        slug + " resolves as an ATTACK layer, so this file is testing the "
        "wrong path for it")
    st.stack_entries.append(entry)
    E.resolve_stack(st)
    return st.players[1].action_points


def _run_abilities(slug):
    def _fn(card, state):
        for ability in get_card(slug).abilities:
            run_ability(ability, card, None, state)
    return _fn


def _with_lightning_flow(st, card):
    token = owned_card(1, "lightning_flow", types=["Token"])
    token.name = "Lightning Flow"
    token.subtypes = ["Lightning Flow"]
    st.players[1].permanents.add(token)


# --- the control: an ungated printed go again still pays --------------------

def test_an_ungated_printed_go_again_still_grants_its_action_point():
    """The stripping must take away ONLY what a card's own text gates. Most of
    the 161 non-attack cards printing go again are like this one."""
    assert not conditional_keywords(UNGATED_CONTROL), (
        UNGATED_CONTROL + " now declares a conditional keyword, so it is no "
        "longer a control for the unconditional case")

    assert _resolve_as_layer(_state(), UNGATED_CONTROL) == 1, (
        "a non-attack card printing go again no longer grants its action "
        "point -- the conditional stripping is taking away too much")


# --- arc ramp: the gate now bites on the path it actually resolves through --

def test_arc_ramp_grants_no_action_point_when_its_gate_is_not_met():
    st = _state()

    points = _resolve_as_layer(st, "arc_ramp_red",
                               effect_fn=_run_abilities("arc_ramp_red"))

    assert points == 0, (
        "Arc Ramp granted %d action point(s) without destroying a Lightning "
        "Flow -- the printed keyword is unconditional again on the non-attack "
        "path" % points)


def test_arc_ramp_grants_exactly_one_action_point_when_it_destroys_a_flow():
    """EXACTLY one. Two is the shape this path had: the DSL grant pays
    directly (CR 8.3.5a) and the printed keyword paid again."""
    st = _state()

    points = _resolve_as_layer(st, "arc_ramp_red",
                               effect_fn=_run_abilities("arc_ramp_red"),
                               setup=_with_lightning_flow)

    assert points == 1, (
        "expected exactly 1 action point, got %d -- CR 8.3.5c says an object "
        "cannot have two go agains" % points)


def test_arc_ramp_is_a_non_attack_card():
    """The premise for this whole file. If Arc Ramp were an attack it would go
    through _recalculate_attack_power and none of this would apply."""
    card = DB.get("arc_ramp_red")
    assert "Attack" not in (card.subtypes or [])
    assert not card.is_attack


def test_the_printed_keyword_is_still_there_to_be_stripped():
    """If Arc Ramp stopped printing go again there would be nothing to strip
    and these tests would pass while measuring nothing."""
    idx = json.loads((ROOT / "card_data" / "slug_index.json")
                     .read_text(encoding="utf-8"))["by_slug"]
    printed = [str(k).lower() for k in (idx["arc_ramp_red"].get("keywords") or [])]
    assert "goagain" in printed
    assert DB.get("arc_ramp_red").has_go_again, (
        "card.has_go_again is the SECOND reading of the printed keyword, "
        "straight off the card DB -- stripping card.keywords alone would let "
        "the free action point back in through it")


# --- the double payment, pinned directly ------------------------------------

def test_the_grant_and_the_printed_keyword_do_not_both_pay():
    """Reproduces the double payment by pretending the keyword is
    unconditional again, which is precisely the state the engine was in."""
    real = loader.conditional_keywords
    loader.conditional_keywords = lambda slug: frozenset()
    try:
        unstripped = _resolve_as_layer(
            _state(), "arc_ramp_red",
            effect_fn=lambda c, s: _grant_go_again(c, s))
    finally:
        loader.conditional_keywords = real

    assert unstripped == 2, (
        "the double payment no longer reproduces even with stripping disabled "
        "-- either _grant_go_again stopped paying on the non-attack path, or "
        "resolve_stack did, and one of them should still be paying")

    stripped = _resolve_as_layer(_state(), "arc_ramp_red",
                                 effect_fn=lambda c, s: _grant_go_again(c, s))
    assert stripped == 1, (
        "with the keyword declared conditional the card should be paid once, "
        "by its ability")


# --- and no future non-attack declaration can be tested on the wrong path ---

def _declaring_slugs():
    out = []
    json_root = ROOT / "engine" / "card_effects" / "json"
    for path in json_root.rglob("*.json"):
        rel = path.relative_to(json_root)
        if path.stem.endswith("_work_queue") or any(
                p.startswith(".") for p in rel.parts):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(raw, dict) and raw.get("conditional_keywords"):
            out.append(raw["slug"])
    return sorted(out)


DECLARING = _declaring_slugs()
NON_ATTACK_DECLARERS = [s for s in DECLARING
                        if (DB.get(s) is not None
                            and "Attack" not in (DB.get(s).subtypes or [])
                            and not DB.get(s).is_attack)]


def test_some_card_declares_a_conditional_keyword():
    """Premise: the sweep below is not vacuous."""
    assert DECLARING, "no card declares conditional_keywords any more"


@pytest.mark.parametrize("slug", NON_ATTACK_DECLARERS or ["arc_ramp_red"])
def test_a_non_attack_declarer_is_gated_on_the_layer_path(slug):
    """Declaring a keyword conditional on a card that never enters combat is
    only meaningful if resolve_stack honours it. Asserting it with
    recalculate_attack -- the natural thing to do, and what was done first --
    tests a path the card never takes."""
    assert "goagain" in conditional_keywords(slug), slug

    points = _resolve_as_layer(_state(), slug)

    assert points == 0, (
        slug + " still grants its action point on resolution with nothing "
        "having triggered, so its declaration is inert on the path it "
        "actually takes")
