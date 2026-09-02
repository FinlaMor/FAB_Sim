"""Painful Passage buffed the wrong card, in both of its branches.

Printed: "You may banish an attack action card from your hand. If you do, IT
gets +3{p} or **go again** until end of turn."

"It" is the card just banished. Talishar pins the effect to that object's unique
id and applies it when that card is PLAYED, which settles the pronoun: this is
not "your next attack" and not "cards you play this turn".

Neither branch was pinned to anything:

    +3{p}      MODIFY_NEXT_ATTACK with a property filter, so the buff landed on
               whichever attack was played next
    go again   GRANT_KEYWORD_TO_PLAYED, which by its own docstring covers EVERY
               matching card for the rest of the turn rather than one

The second is the worse of the two: a one-shot printed on the card became a
repeating grant of a keyword, for the rest of the turn, to every attack action
played. The pronoun defect and the scope defect compound.

The attack queue now pins by object_id, which the played-card queue
(dsl_queued_card_mods) has done since "your next attack WITH IT" needed it — the
same fix, on the queue that had not had it yet.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card import Card, CardDB
from engine.card_effects.dsl.effect_types import compile_effect
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.context import pop_refs, push_refs, set_ref
from tests.conftest import _make_state, owned_card

load_all_cards()
DB = CardDB()
SLUG = "painful_passage_red"


def _state():
    st = _make_state()
    st.card_db = DB
    st.active_player = 1
    return st


def _attack(slug, oid):
    c = Card(slug=slug, name=slug, raw_types=["Action"])
    c.types, c.subtypes = ["Action"], ["Attack"]
    c.owner = c.controller = 1
    c.object_id = oid
    return c


def _queue(st, effect_type, params, subject):
    """Queue the mod as the card does: with `subject` stored under the ref."""
    push_refs()
    try:
        set_ref("passage", subject)
        compile_effect(effect_type, params)(owned_card(1, SLUG), None, st)
    finally:
        pop_refs()


# --- the attack queue is pinned to one object --------------------------------

def test_the_power_buff_is_pinned_to_the_banished_card():
    st = _state()
    banished, other = _attack("banished_card", 101), _attack("other_card", 202)
    _queue(st, "MODIFY_NEXT_ATTACK",
           {"mod": "add", "amount": 3, "object_ref": "passage"}, banished)

    mods = st.players[1].dsl_queued_attack_mods
    assert len(mods) == 1
    assert mods[0]["object_id"] == 101, (
        "the buff is not pinned; it will land on the next attack instead")


def test_an_unpinned_queue_entry_is_unchanged():
    """object_ref is opt-in. "Your next attack this turn gets +1{p}" must keep
    matching on properties alone."""
    st = _state()
    _queue(st, "MODIFY_NEXT_ATTACK", {"mod": "add", "amount": 1}, None)
    mods = st.players[1].dsl_queued_attack_mods
    assert len(mods) == 1 and mods[0]["object_id"] is None


def test_a_missing_object_queues_nothing():
    """If the banish did not happen there is nothing to buff. Queueing an
    unpinned entry would silently widen the buff to any attack."""
    st = _state()
    _queue(st, "MODIFY_NEXT_ATTACK",
           {"mod": "add", "amount": 3, "object_ref": "passage"}, None)
    assert not getattr(st.players[1], "dsl_queued_attack_mods", [])


def test_the_engine_skips_a_pinned_mod_for_a_different_attack():
    """The consumer half. A pinned entry must survive an attack it does not
    match, rather than being spent on it."""
    import engine.engine as E
    st = _state()
    banished, other = _attack("banished_card", 101), _attack("other_card", 202)
    _queue(st, "MODIFY_NEXT_ATTACK",
           {"mod": "add", "amount": 3, "object_ref": "passage"}, banished)

    E._apply_turn_attack_effects(st, other)
    assert len(st.players[1].dsl_queued_attack_mods) == 1, (
        "the buff was consumed by an attack it was not about")
    assert not getattr(other, "effects", []), "the wrong card was buffed"

    E._apply_turn_attack_effects(st, banished)
    assert not st.players[1].dsl_queued_attack_mods, (
        "the buff was not consumed by the card it was pinned to")
    assert getattr(banished, "effects", []), "the right card was not buffed"


# --- the go-again branch is one card, not the whole turn ---------------------

def test_go_again_goes_on_the_played_card_queue_not_the_turn_wide_grant():
    cd = get_card(SLUG)
    types = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type"):
                types.append(node["type"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for ab in cd.abilities:
        for e in ab.effects:
            walk(e.params)
    assert "GRANT_KEYWORD_TO_PLAYED" not in types, (
        "that grant covers EVERY matching card for the rest of the turn; the "
        "card gives go again to one")
    assert "MODIFY_NEXT_CARD" in types


def test_both_branches_name_the_banished_card():
    cd = get_card(SLUG)
    refs = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("object_ref"):
                refs.append(node["object_ref"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for ab in cd.abilities:
        for e in ab.effects:
            walk(e.params)
    assert refs == ["passage", "passage"], (
        "a branch is unpinned and will buff the wrong card: %s" % refs)


def test_go_again_is_not_granted_twice():
    """CR 8.3.5b — it is printed on the card and granted by the card DB."""
    assert DB.get(SLUG).has_go_again
    cd = get_card(SLUG)
    top = [e.effect_type for e in cd.abilities[0].effects]
    assert "GO_AGAIN" not in top, (
        "the JSON grants a keyword the card already prints")
