"""CARD_TYPE_IN was a name three authors reached for and the compiler rejected.

An unknown condition type does not fail quietly the way most defects in this
effort do: `compile_condition` raises, so the WHOLE CARD refuses to load and
the engine will not start a game containing it. Three separately-authored
drafts used `CARD_TYPE_IN` with a `types` list, by obvious analogy with
`ATTACK_TYPE_IN` and `WEAPON_SUBTYPE_IN`, which really do exist.

So the name is the natural one, and the fix belongs in the compiler rather than
in three card files -- the same reasoning the existing alias group already
encodes for SELF_IS_TYPE and SUBTYPE_IN, and the same reasoning
test_no_unknown_type_names states in its own failure message.

The `types` parameter matters as much as the name. Reading only the singular
spellings left `wants` empty, and an empty `wants` returns False for every
card: a filter matching NOTHING rather than the type it names -- which is the
quiet version of this bug and the one that actually costs cards.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card import Card
from engine.card_effects.dsl.condition_types import compile_condition


def _card(types=(), subtypes=()):
    return Card(slug="x", name="x", types=list(types), subtypes=list(subtypes))


@pytest.mark.parametrize("ctype", ["CARD_TYPE_IN", "CARD_IS_TYPE",
                                   "SELF_IS_TYPE", "SUBTYPE_IN"])
def test_the_spelling_compiles(ctype):
    fn = compile_condition(ctype, {"types": ["Hero"]})
    assert fn is not None, f"{ctype} does not compile"


def test_card_type_in_matches_the_named_type():
    fn = compile_condition("CARD_TYPE_IN", {"types": ["Hero"]})
    assert fn(_card(types=["Hero"]), None, None) is True


def test_card_type_in_rejects_a_different_type():
    fn = compile_condition("CARD_TYPE_IN", {"types": ["Hero"]})
    assert fn(_card(types=["Action"]), None, None) is False


def test_the_types_param_is_actually_read():
    """The quiet failure: an unread parameter leaves `wants` empty, and an
    empty `wants` matches NOTHING. That looks like an unmet condition rather
    than a broken one."""
    fn = compile_condition("CARD_IS_TYPE", {"types": ["Action"]})
    assert fn(_card(types=["Action"]), None, None) is True, (
        "'types' is not being read, so the filter matches nothing")


def test_subtypes_still_count():
    """"Attack" is a SUBTYPE while "Action" is a type, and a card naming either
    means the same thing by it."""
    fn = compile_condition("CARD_TYPE_IN", {"types": ["Attack"]})
    assert fn(_card(types=["Action"], subtypes=["Attack"]), None, None) is True


def test_the_older_spellings_did_not_regress():
    fn = compile_condition("CARD_IS_TYPE", {"card_type": "Hero"})
    assert fn(_card(types=["Hero"]), None, None) is True
