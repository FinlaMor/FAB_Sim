"""Auras never reached the arena, and WARD crashed the game.

Both found by replaying real Talishar transitions and comparing the resulting
state (scripts/talishar_outcome_diff.py). Talishar is an independent
implementation, so a disagreement about where a card ends up is a disagreement
about the rules, not about style.

PERMANENTS WENT TO THE GRAVEYARD. CR 1.3.2c: a deck-card with a permanent
subtype enters the arena. `resolve_stack` clears whatever is still in the stack
zone to the graveyard, and only defense reactions were moving themselves out
first -- so every Aura, Item and Ally ACTION CARD in the corpus was played
straight into the graveyard. The permanent never existed, which also means every
"while you control an aura", every aura count and every on-enter trigger was
reading an empty board.

Talishar put Blessing of Bellona into `auras`; we put it into `graveyard`. That
one-line disagreement is what surfaced it.

WARD AND ARCANE_BARRIER WERE CALLED WITH THEIR ARGUMENTS TRANSPOSED.
`ward(card, amount, state)` was being called as `ward(state, card, _a)`, so the
amount arrived where the state belonged and the first thing the function did was
`int.effect_manager`. Every WARD resolution raised AttributeError and took the
game down with it -- 11 cards for WARD, 5 for ARCANE_BARRIER. A crash rather
than a wrong answer, which is why no outcome test caught it: the card could
never resolve at all.
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
from engine.actions import ActionType
from engine.card import CardDB
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.play import apply_action, available_actions
from engine.state import Step, _PERMANENT_SUBTYPES
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()
IDX = json.loads((ROOT / "card_data" / "slug_index.json")
                 .read_text(encoding="utf-8"))["by_slug"]


def _play(slug):
    st = _make_state()
    st.card_db = DB
    st.active_player = 1
    st.step = Step.ACTION
    st.players[1].resources = 9
    st.players[1].action_points = 1
    card = copy.deepcopy(DB.get(slug))
    assert card is not None, slug
    card.owner = card.controller = 1
    st.players[1].hand.add(card)
    offers = [a for a in available_actions(st, 1)
              if getattr(a.card, "slug", None) == slug
              and a.type == ActionType.PLAY_CARD]
    assert offers, "%s was not offered" % slug
    apply_action(st, offers[0])
    E.resolve_stack(st)
    return st


# --- permanents enter the arena ---------------------------------------------

@pytest.mark.parametrize("slug,zone", [
    ("blessing_of_bellona_yellow", "auras"),
    ("blessing_of_deliverance_red", "auras"),
    ("sigil_of_protection_red", "auras"),
])
def test_an_aura_action_card_enters_the_arena(slug, zone):
    st = _play(slug)
    p = st.players[1]
    assert [c.slug for c in getattr(p, zone).cards] == [slug], (
        "%s did not enter %s; graveyard=%s"
        % (slug, zone, [c.slug for c in p.graveyard.cards]))
    assert not p.graveyard.cards, "it also went to the graveyard"


def test_a_non_permanent_action_still_goes_to_the_graveyard():
    """The other half. Sending everything to the arena would be the same bug
    pointing the other way, and a non-attack action has to be cleared."""
    st = _play("aether_dart_red")
    p = st.players[1]
    assert [c.slug for c in p.graveyard.cards] == ["aether_dart_red"]
    assert not p.auras.cards and not p.items.cards and not p.allies.cards


def test_every_implemented_aura_action_card_reaches_the_arena():
    """Swept rather than sampled: the defect was uniform, so a fix that works on
    three cards and not the rest would look identical on a parametrised test."""
    missed = []
    for slug, entry in IDX.items():
        subs = set(entry.get("subtypes") or [])
        if "Aura" not in subs or "Action" not in (entry.get("types") or []):
            continue
        if get_card(slug) is None or DB.get(slug) is None:
            continue
        if (DB.get(slug).cost or 0) > 9:
            continue
        try:
            st = _play(slug)
        except Exception:
            continue          # unrelated failure; this test is about placement
        if not st.players[1].auras.cards:
            missed.append(slug)
    assert not missed, (
        "%d aura action cards did not reach the arena: %s"
        % (len(missed), ", ".join(sorted(missed)[:10])))


# --- ward / arcane barrier no longer crash -----------------------------------

def _cards_using(effect_type):
    out = []
    root = ROOT / "engine" / "card_effects" / "json"

    def walk(node, found):
        if isinstance(node, dict):
            if node.get("type") == effect_type:
                found.append(True)
            for v in node.values():
                walk(v, found)
        elif isinstance(node, list):
            for v in node:
                walk(v, found)
        return found

    for path in root.rglob("*.json"):
        if path.stem.endswith("_work_queue") or any(
                p.startswith(".") or p == "needs_review" for p in path.parts):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(raw, dict) and walk(raw.get("abilities"), []):
            out.append(raw["slug"])
    return sorted(out)


@pytest.mark.parametrize("effect_type", ["WARD", "ARCANE_BARRIER"])
def test_the_keyword_effect_does_not_crash(effect_type):
    slugs = _cards_using(effect_type)
    assert slugs, "no card uses %s any more; this test is measuring nothing" % effect_type
    from engine.card_effects.dsl.effect_types import compile_effect
    st = _make_state()
    st.card_db = DB
    card = copy.deepcopy(DB.get(slugs[0]))
    card.owner = card.controller = 1
    st.players[1].auras.add(card)
    # The bug was an argument transposition, so it raised on the FIRST call.
    compile_effect(effect_type, {"amount": 1})(card, None, st)


def test_ward_destroys_the_card_it_is_on():
    """CR 8.3.20 — ward destroys its source to prevent damage. Not crashing is
    necessary but not sufficient; the effect has to happen."""
    from engine.card_effects.dsl.effect_types import compile_effect
    st = _make_state()
    st.card_db = DB
    card = copy.deepcopy(DB.get("sigil_of_protection_red"))
    card.owner = card.controller = 1
    st.players[1].auras.add(card)

    compile_effect("WARD", {"amount": 1})(card, None, st)

    assert card not in st.players[1].auras.cards, "ward did not destroy its source"
