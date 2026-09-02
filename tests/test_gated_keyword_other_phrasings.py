"""Three gated keywords the earlier sweeps could not have found.

The gated-keyword work swept for "this GETS <keyword>". These say it otherwise,
inside a gating sentence, and were never looked at:

    swift_shot_red        "When this is put face-up into your arsenal, IT gets
                          go again this turn."
    current_funnel_blue   "... THIS and the next action card you play this turn
                          get go again."
    merciless_battleaxe   "... THE ATTACK gets overpower."   (the attack is the
                          weapon itself)

A sweep finds what its pattern describes. Widening the verb to
gets/gains/has/have and requiring only a gating word turned up 34 candidates, of
which most are the known "grants to ANOTHER card" exception (Luminaris, Weave
Ice, "your next attack ...") and these three were real. That ratio is the point:
the sweep is a candidate generator, and the judgement about WHOSE keyword it is
still has to be made per card.

MERCILESS BATTLEAXE CARRIED A SECOND DEFECT. "If the attack's {p} is greater
than TWICE ITS BASE" was authored as SELF_ATTACK_POWER_GTE 2 -- "power is at
least 2" -- which is true of nearly every attack. So even after the keyword was
stripped, the gate would have handed it straight back. Both halves had to be
right for the card to be right, and the keyword fix alone would have looked like
a fix while changing nothing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card import CardDB
from engine.card_effects.dsl.condition_types import compile_condition
from engine.card_effects.dsl.loader import (conditional_keywords, get_card,
                                            load_all_cards, _kw_key)
from tests.conftest import _make_state, owned_card

load_all_cards()
DB = CardDB()
IDX = json.loads((ROOT / "card_data" / "slug_index.json")
                 .read_text(encoding="utf-8"))["by_slug"]

CASES = [("swift_shot_red", "go again"),
         ("current_funnel_blue", "go again"),
         ("merciless_battleaxe", "overpower")]


@pytest.mark.parametrize("slug,keyword", CASES)
def test_the_printed_keyword_is_stripped(slug, keyword):
    kws = {_kw_key(k) for k in conditional_keywords(slug)}
    assert _kw_key(keyword) in kws, (
        "%s prints %s and gates it in its own text; without the strip the card "
        "DB grants it unconditionally and the gate is decoration" % (slug, keyword))


@pytest.mark.parametrize("slug,keyword", CASES)
def test_the_card_really_prints_it(slug, keyword):
    """The premise. Stripping a keyword the card does not print would be a
    different bug, and a silent one."""
    printed = {_kw_key(k) for k in (IDX[slug].get("keywords") or [])}
    assert _kw_key(keyword) in printed


@pytest.mark.parametrize("slug,keyword", CASES)
def test_something_grants_it_back(slug, keyword):
    """A strip with no grant turns a fail-open bug into a fail-closed one — the
    card would then never have the keyword at all."""
    cd = get_card(slug)
    granted = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("keyword") or node.get("keywords"):
                granted.append(node.get("keyword") or node.get("keywords"))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for ab in cd.abilities:
        walk({"effects": [e.params for e in ab.effects]})
        for e in ab.effects:
            if e.effect_type in ("GO_AGAIN", "GAIN"):
                granted.append(e.effect_type)
    flat = _kw_key(json.dumps(granted))
    assert _kw_key(keyword).replace(" ", "") in flat.replace(" ", ""), (
        "%s no longer grants %s back: %s" % (slug, keyword, granted))


# --- the battleaxe's gate ----------------------------------------------------

def _combat(st, power, base):
    from engine.state import CombatState
    card = owned_card(1, "merciless_battleaxe", types=["Weapon"])
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=power,
                            attack_card=card, keywords=[])
    st.combat.base_attack_power = base
    return card


def _gate(st, card):
    ab = [a for a in get_card("merciless_battleaxe").abilities
          if (a.trigger or "").upper() == "ON_ATTACK"][0]
    return all(c.fn is None or c.fn(card, None, st) for c in ab.conditions)


def test_the_battleaxe_needs_more_than_twice_its_base():
    st = _make_state()
    st.card_db = DB
    assert _gate(st, _combat(st, power=7, base=3)), "7 is more than twice 3"


def test_exactly_twice_the_base_is_not_enough():
    """"GREATER than twice" excludes equalling it — the same GT/GTE distinction
    that has already cost this project a card."""
    st = _make_state()
    st.card_db = DB
    assert not _gate(st, _combat(st, power=6, base=3))


def test_an_unpumped_attack_does_not_qualify():
    st = _make_state()
    st.card_db = DB
    assert not _gate(st, _combat(st, power=3, base=3)), (
        "the old gate was 'power >= 2', which nearly every attack satisfies")


def test_the_multiple_defaults_to_one():
    """ATTACK_POWER_GT_BASE without a multiple must keep meaning 'greater than
    its base' for the cards already using it."""
    st = _make_state()
    st.card_db = DB
    fn = compile_condition("ATTACK_POWER_GT_BASE", {})
    card = _combat(st, power=4, base=3)
    assert fn(card, None, st)
    _combat(st, power=3, base=3)
    assert not fn(card, None, st)


# --- the battleaxe on the path it actually takes -----------------------------

def test_the_battleaxe_gets_overpower_only_when_the_gate_holds():
    """Verified through recalculate_attack, which is the path a WEAPON attack
    takes -- the weapon goes on the combat chain, so it is an attack even though
    it is not an "Attack" subtype card.

    That distinction is why it briefly landed in the non-attack layer guard,
    whose whole point is that a card must be checked on the path it uses. The
    same mistake in the other direction cost this project a card once already.
    """
    import engine.engine as E
    from tests.conftest import attack_with, recalculate_attack

    st = _make_state()
    st.card_db = DB
    card = owned_card(1, "merciless_battleaxe", types=["Weapon"])
    card.base_power = 3

    attack_with(st, card, power=3)
    st.combat.base_attack_power = 3
    for ab in get_card("merciless_battleaxe").abilities:
        if (ab.trigger or "").upper() == "ON_ATTACK":
            from engine.card_effects.dsl.interpreter import run_ability
            run_ability(ab, card, None, st)
    recalculate_attack(st)
    kws = {_kw_key(k) for k in (st.combat.keywords or [])}
    assert _kw_key("overpower") not in kws, (
        "overpower at base power; the gate is 'greater than TWICE its base'")

    st2 = _make_state()
    st2.card_db = DB
    card2 = owned_card(1, "merciless_battleaxe", types=["Weapon"])
    card2.base_power = 3
    attack_with(st2, card2, power=7)
    st2.combat.base_attack_power = 3
    for ab in get_card("merciless_battleaxe").abilities:
        if (ab.trigger or "").upper() == "ON_ATTACK":
            from engine.card_effects.dsl.interpreter import run_ability
            run_ability(ab, card2, None, st2)
    recalculate_attack(st2)
    kws2 = {_kw_key(k) for k in (st2.combat.keywords or [])}
    assert _kw_key("overpower") in kws2, (
        "7 is more than twice 3, so the axe should have overpower")
