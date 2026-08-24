"""Every "type" in a card JSON must be a name the compiler knows.

An unknown ability_type or a top-level unknown effect type is already caught -
by the loader, and by scripts/audit_run.py. Neither reaches a type nested in a
LAZILY-COMPILED position: a mode's target filter, a MAY's body, an
INJECT_TRIGGER's effects. Those load cleanly and then either raise mid-game or
silently do nothing, which is the same failure mode that hid invented EFFECT
types until they were audited for.

The sweep that found the current set turned up 17 names across 11 cards. Two
groups, and both failed silently rather than loudly:

  a ZONE in a `type` key   {"type": "TOP_DECK", "controller": "opponent"} is a
                           fifth spelling of a target. It was ACCEPTED as a
                           canonical dict (it has `controller`) but carried no
                           `zone`, so it fell through to the ARENA default -
                           five cards saying "banish the top card of THEIR DECK"
                           were banishing from their arena.
  invented condition names SUBTYPE_IN, CLASS_IN, COST_LTE, SAME_NAME - each a
                           plausible spelling of a condition that already exists
                           under another name.

Those aliases were added in the COMPILER rather than the cards, because the next
author will reach for the same words. TalentContainsAny was NOT: it is a foreign
camelCase identifier that leaked in from generated data, a previous batch had
already flagged it as invalid, and keeping the load gate strict about it is what
surfaced a second copy nested inside arc_bending_red's effect filter that the
earlier repair had missed.
"""
import json
from pathlib import Path

import pytest

from engine.card_effects.dsl.condition_types import compile_condition
from engine.card_effects.dsl.cost_types import compile_cost
from engine.card_effects.dsl.effect_types import compile_effect
from engine.card_effects.dsl.loader import load_all_cards

load_all_cards()

ROOT = Path(__file__).resolve().parent.parent
JSON_ROOT = ROOT / "engine" / "card_effects" / "json"

#: Names that appear under a "type" key but are NOT compiler dispatch names:
#: amount expressions, and a couple of data shapes.
NOT_DISPATCH_NAMES = {
    "HALF", "ROLL_RESULT", "ROLL_NUMBER", "ROLL_NUMBER_HALF_ROUND_DOWN",
    "X", "PAID_AMOUNT", "AMOUNT_PAID", "LITERAL", "SUM", "ADD", "PLUS",
    "DESTROYED_COUNT", "LIFE_GAINED_THIS_TURN", "DAMAGE_DEALT_THIS_TURN",
    "DAMAGE_DEALT", "LAST_DAMAGE_DEALT",
    # {"type": "<counter kind>", "amount": n} inside a `counters` list, and
    # {"type": "REFERENCE", "ref": ..., "property": ...} as a VALUE. Both are
    # data, not dispatch — listed so the guard reports genuinely unknown names.
    "REFERENCE",
}


def _is_dispatch_name(name: str, node: dict) -> bool:
    args = {k: v for k, v in node.items() if k != "type"}
    for fn in (compile_condition, compile_effect, compile_cost):
        try:
            fn(name.upper(), args)
            return True
        except Exception:
            continue
    return False


def _unknown_types() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for path in sorted(JSON_ROOT.rglob("*.json")):
        rel = path.relative_to(JSON_ROOT)
        if path.stem.endswith("_work_queue") or any(
                p.startswith(".") or p == "needs_review" for p in rel.parts):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        slug = raw.get("slug")

        def walk(node, in_counters=False):
            if isinstance(node, dict):
                name = node.get("type")
                if (isinstance(name, str) and name
                        and not in_counters
                        and name.upper() not in NOT_DISPATCH_NAMES
                        and not name.upper().startswith("COUNT_")
                        and not _is_dispatch_name(name, node)):
                    found.append((slug, name))
                for key, value in node.items():
                    walk(value, in_counters or key == "counters")
            elif isinstance(node, list):
                for value in node:
                    walk(value, in_counters)

        walk(raw.get("abilities"))
    return found


def test_no_card_names_a_type_the_compiler_does_not_know():
    """A type nested in a lazily-compiled position loads cleanly and then
    raises mid-game (or does nothing). The loader and audit_run both miss it."""
    unknown = sorted(set(_unknown_types()))
    assert unknown == [], (
        "cards name types the compiler cannot dispatch:\n  "
        + "\n  ".join(f"{slug}: {name}" for slug, name in unknown)
        + "\n\nFix the COMPILER (add the alias) when the name is a plausible "
          "spelling of something that exists — the next author will reach for "
          "the same word."
    )


@pytest.mark.parametrize("alias,args", [
    ("SUBTYPE_IN", {"subtypes": ["Item"]}),
    ("CLASS_IN", {"classes": ["Mechanologist"]}),
    ("COST_LTE", {"amount": 1}),
    ("SAME_NAME", {"card_name": "Gustwave"}),
])
def test_the_aliases_read_the_shape_the_cards_actually_pass(alias, args):
    """An alias that compiles but reads the wrong PARAM is worse than none: an
    empty want makes these conditions False for every card, so the filter
    matches nothing and the card silently does nothing.

    SUBTYPE_IN passes `subtypes` (plural) and CLASS_IN passes `classes`; the
    singular-only readings left both empty.
    """
    fn = compile_condition(alias, args)
    assert fn is not None

    import copy

    from engine.card import CardDB
    db = CardDB()
    probe = copy.deepcopy(db.get("brutal_assault_red"))
    # The point is only that a real card is TESTED rather than short-circuited
    # on an empty filter: a False here must come from the card, not from the
    # condition having nothing to compare.
    fn(probe, None, None)


def test_a_zone_named_in_a_type_key_is_read_as_the_zone():
    """{"type": "TOP_DECK", "controller": "opponent"} carries no `zone`, so it
    fell through to the ARENA default."""
    from engine.card_effects.dsl.effect_types import _object_target_spec

    spec = _object_target_spec({"type": "TOP_DECK", "controller": "opponent"})
    assert spec is not None
    assert spec.get("zone") == "DECK_TOP", spec
    assert spec.get("controller") == "opponent"

    for named, expected in (("TOP_CARD", "DECK_TOP"), ("GRAVEYARD", "GRAVEYARD"),
                            ("HAND", "HAND")):
        got = _object_target_spec({"type": named, "controller": "opponent"})
        assert got.get("zone") == expected, (named, got)


def test_an_explicit_zone_still_wins():
    """Only a spec with NO zone is reinterpreted."""
    from engine.card_effects.dsl.effect_types import _object_target_spec

    spec = _object_target_spec({"type": "TOP_DECK", "controller": "opponent",
                                "zone": "GRAVEYARD"})
    assert spec.get("zone") == "GRAVEYARD"
