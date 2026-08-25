"""Twenty-nine abilities that said "a hero" and fired against anything.

The DSL ON_HIT listener is registered on the generic `hit` event
(engine.py: `register('hit', _dsl_hit_listener)`), which is emitted for every
damaged target -- allies included. ON_ATTACK fires on declaration, whatever was
attacked. So "When this hits A HERO, banish the top card of their deck" fired
when the attack hit an ally, and "When this attacks A HERO, they reveal X cards
from their hand" fired at a permanent.

ATTACK_TARGET_IS_HERO already existed and reads combat.attack_target, which is
set only for non-hero targets. Twenty-eight cards were missing it. The reviewer
flagged nine; the sweep over the printed phrase found the rest, and matching the
VERB ("hits a hero" -> ON_HIT, "attacks a hero" -> ON_ATTACK) rather than the
card kept it off the abilities carrying a different clause.

hot_on_their_heels_red was the odd one out: it already had the corrected
ability, and a DUPLICATE of the same clause sitting in front of it, gated on
CONTROLS_TOKEN_TYPE "Draconic" -- a subtype no card or token in the DB has.
Left alone it was inert; repaired along with everything else it would have
marked twice. It is deleted rather than gated.

Three other cards look duplicated by the same structural check
(stir_the_wildwood red/blue, dread_triptych_blue) and are NOT: each prints two
clauses with the same effect under different conditions.
"""
from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import engine.engine as E
from engine.card import Card, CardDB
from engine.card_effects.dsl import dispatch, load_all_cards
from engine.card_effects.dsl.loader import get_card
from engine.state import CombatState, Event, Player, Step

from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

JSON_ROOT = ROOT / "engine" / "card_effects" / "json"


def _state():
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="": o[0]
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    st.individual_turns = 1
    return st


def _combat(st, slug, target=None):
    ac = copy.deepcopy(DB.get(slug))
    assert ac is not None, slug
    ac.owner = ac.controller = 1
    ac.zone = "combat_chain"
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=5,
                            attack_card=ac, keywords=[], from_weapon=False)
    st.combat.attack_target = target
    return ac


def _ally(pid=2):
    a = Card(slug="an_ally", name="an_ally", types=["Action"],
             subtypes=["Ally"], base_life=3)
    a.owner = a.controller = pid
    a.current_life = 3
    return a


# --- kiss_of_death_red: "when this hits a hero, they lose 1 life" -----------

def _hit(st, slug):
    dispatch(st, "ON_HIT", slug, card=st.combat.attack_card,
             event=Event(type="hit", data={"damage": 3}))


def test_it_fires_when_the_attack_hit_the_hero():
    st = _state()
    _combat(st, "kiss_of_death_red", target=None)
    before = st.players[2].life

    _hit(st, "kiss_of_death_red")

    assert st.players[2].life == before - 1, "the hero clause did not fire"


def test_it_does_not_fire_when_the_attack_hit_an_ally():
    st = _state()
    ally = _ally()
    st.players[2].permanents.add(ally)
    _combat(st, "kiss_of_death_red", target=ally)
    before = st.players[2].life

    _hit(st, "kiss_of_death_red")

    assert st.players[2].life == before, (
        "hitting an ally triggered a clause that says 'hits a hero'")


# --- destructive_deliberation_yellow: creates a token ----------------------

def _ponders(st):
    return [c for c in st.players[1].permanents.cards
            if "ponder" in (c.slug or "").lower()]


def test_a_token_clause_fires_only_off_a_hero_hit():
    st = _state()
    _combat(st, "destructive_deliberation_yellow", target=None)
    _hit(st, "destructive_deliberation_yellow")
    assert len(_ponders(st)) == 1, "the Ponder token was not created"

    st = _state()
    ally = _ally()
    st.players[2].permanents.add(ally)
    _combat(st, "destructive_deliberation_yellow", target=ally)
    _hit(st, "destructive_deliberation_yellow")
    assert _ponders(st) == [], "an ally hit created the token"


# --- hot_on_their_heels_red -------------------------------------------------

def test_hot_on_their_heels_has_one_mark_ability_not_two():
    abilities = get_card("hot_on_their_heels_red").abilities
    marks = [a for a in abilities if a.trigger == "ON_HIT"]
    assert len(marks) == 1, (
        f"the duplicate mark ability is still there: {len(marks)} ON_HIT")
    assert any(c.condition_type == "ATTACK_TARGET_IS_HERO"
               for c in marks[0].conditions), (
        "the surviving one is not the gated version")


# --- the guard --------------------------------------------------------------

def test_every_hero_clause_carries_the_hero_gate():
    """Derived from the printed phrase and matched on the VERB, so an ability
    carrying a different clause on the same card is not implicated."""
    idx = json.load(open(ROOT / "card_data" / "slug_index.json",
                         encoding="utf-8"))["by_slug"]
    hits = re.compile(r"hits a hero", re.I)
    attacks = re.compile(r"attacks a hero", re.I)
    bad = []
    for path in JSON_ROOT.rglob("*.json"):
        rel = path.relative_to(JSON_ROOT)
        if (path.stem.endswith("_work_queue")
                or any(p.startswith(".") or p == "needs_review"
                       for p in rel.parts)):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        slug = raw.get("slug")
        text = idx.get(slug, {}).get("functionalText") or ""
        says_hit, says_attack = bool(hits.search(text)), bool(attacks.search(text))
        if not (says_hit or says_attack):
            continue
        for i, ab in enumerate(raw.get("abilities") or []):
            trigger = ab.get("trigger")
            if trigger == "ON_HIT" and not says_hit:
                continue
            if trigger == "ON_ATTACK" and not says_attack:
                continue
            if trigger not in ("ON_HIT", "ON_ATTACK"):
                continue
            if "ATTACK_TARGET_IS_HERO" not in json.dumps(ab):
                bad.append(f"{slug}#{i} {trigger}")
    assert bad == [], (
        "abilities whose text says 'a hero' that fire against any target: "
        f"{bad}")
