"""MODIFY_ATTACK ignored `"mod": "subtract"` and added instead.

A card that says "target attack gets -1{p}" was giving it +1. That is the worst
direction to be wrong in — it doubles the error and flips the card's purpose.

Three cards author the spelling. Two are not mine:

    a_drop_in_the_ocean_blue   "Target attack gets -1{p}"        gave +1
    blinding_beam_yellow       "...attack action card gets -2{p}" gave +2

MODIFY_ATTACKS_THIS_TURN and MODIFY_DEFENSE_VALUE already normalise
subtract/sub/minus; MODIFY_ATTACK simply never got the same treatment, and its
`mod` fell through to the add branch for everything that was not "set" or
"multiply".

Found while implementing the Frailty token, whose -1{p} static was written the
same natural way and made the attack BIGGER.
"""
from __future__ import annotations

import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.effect_types import compile_effect
from engine.card_effects.dsl.loader import load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

BASE = 4


def _combat_state():
    st = _make_state()
    st.card_db = DB
    card = copy.deepcopy(DB.get("head_jab_red"))
    card.owner = card.controller = 1
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=BASE,
                            attack_card=card, keywords=[])
    st.combat.base_attack_power = BASE
    return st, card


@pytest.mark.parametrize("spelling", ["subtract", "sub", "minus"])
def test_subtract_reduces_the_attack(spelling):
    st, card = _combat_state()
    compile_effect("MODIFY_ATTACK", {"mod": spelling, "amount": 2})(card, None, st)
    assert st.combat.attack_power == BASE - 2


def test_add_still_adds():
    """The other half — the fix must not invert the common case. 'add' is by far
    the most-authored mod, so getting this wrong would be a much larger bug than
    the one being fixed."""
    st, card = _combat_state()
    compile_effect("MODIFY_ATTACK", {"mod": "add", "amount": 2})(card, None, st)
    assert st.combat.attack_power == BASE + 2


def test_default_mod_is_add():
    st, card = _combat_state()
    compile_effect("MODIFY_ATTACK", {"amount": 3})(card, None, st)
    assert st.combat.attack_power == BASE + 3


@pytest.mark.parametrize("mod,expected", [("set", 7), ("multiply", BASE * 2)])
def test_set_and_multiply_are_untouched(mod, expected):
    st, card = _combat_state()
    amount = 7 if mod == "set" else 2
    compile_effect("MODIFY_ATTACK", {"mod": mod, "amount": amount})(card, None, st)
    assert st.combat.attack_power == expected


def test_a_negative_amount_with_subtract_still_reduces():
    """-abs(), so an author who writes both the word and the sign does not get
    a double negative that adds."""
    st, card = _combat_state()
    compile_effect("MODIFY_ATTACK", {"mod": "subtract", "amount": -2})(card, None, st)
    assert st.combat.attack_power == BASE - 2


@pytest.mark.parametrize("slug,expected_delta", [
    ("a_drop_in_the_ocean_blue", -1),
    ("blinding_beam_yellow", -2),
])
def test_the_two_affected_cards_still_author_subtract(slug, expected_delta):
    """These are the cards the bug was actually reaching. If either is ever
    re-authored to use a negative `add` instead, this test should say so rather
    than quietly measuring nothing."""
    import json
    from pathlib import Path

    from tests.conftest import _card_json

    # _card_json, not a bare rglob: the card tree also holds dot-directories
    # (.quarantine here, .drafts/.review/ in the pipeline worktree) filed under
    # the SAME slugs, and ".review" sorts before every set directory. The guard
    # in test_card_lookup_is_artifact_safe.py caught this exact line.
    root = Path(__file__).resolve().parent.parent / "engine" / "card_effects" / "json"
    path = _card_json(root, "%s.json" % slug)
    found = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "MODIFY_ATTACK":
                found.append(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(json.loads(path.read_text(encoding="utf-8")).get("abilities"))
    assert found, "%s no longer has a MODIFY_ATTACK node" % slug
    node = found[0]
    mod = str(node.get("mod", "add")).lower()
    amount = node.get("amount")
    signed = -abs(amount) if mod in ("subtract", "sub", "minus") else amount
    assert signed == expected_delta, (
        "%s now resolves to %+d, expected %+d" % (slug, signed, expected_delta))
