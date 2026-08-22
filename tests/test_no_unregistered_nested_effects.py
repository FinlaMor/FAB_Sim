"""No card may name an effect type that does not exist.

`compile_effect` raises on an unknown type, and the loader compiles every
top-level effect at load — so a bad type there fails loudly and immediately.

But effects nested inside CONDITIONAL, INJECT_TRIGGER, SEARCH_DECK and friends
are compiled LAZILY, at fire time. An invented type in one of those positions
loads clean, passes every startup check, and raises ValueError in the middle of
a game — and only in the games where that branch is reached.

Four cards were in exactly that state, and one of them, soul_bond_belief_red,
was reached on every single attack: CONDITIONAL was not reading its `condition`
either, so the branch containing the invented type ran unconditionally.

This walks every effect position in the corpus and compiles it with its real
parameters.
"""
import json
from pathlib import Path

import pytest

from engine.card_effects.dsl.effect_types import compile_effect
from engine.card_effects.dsl.loader import load_all_cards

load_all_cards()

JSON_ROOT = Path(__file__).resolve().parent.parent / "engine/card_effects/json"

#: Keys whose values hold effect specs rather than plain data.
EFFECT_POSITIONS = {"effects", "then", "else", "else_effects", "modes",
                    "on_success", "on_failure", "on_consume"}


def _card_files():
    # Same exclusions as scripts/audit_params.card_files: work queues are not
    # cards, and .quarantine / needs_review hold files deliberately kept out of
    # the loaded corpus.
    return [p for p in JSON_ROOT.rglob("*.json")
            if not p.stem.endswith("_work_queue")
            and "needs_review" not in p.parts
            and not any(part.startswith(".") for part in p.parts)]


def _effect_nodes(node, in_effects=False):
    """Every dict sitting where an effect spec belongs."""
    if isinstance(node, dict):
        if in_effects and isinstance(node.get("type"), str):
            yield node
        for key, value in node.items():
            yield from _effect_nodes(value, key in EFFECT_POSITIONS)
    elif isinstance(node, list):
        for value in node:
            yield from _effect_nodes(value, in_effects)


@pytest.mark.parametrize("path", _card_files(), ids=lambda p: p.stem)
def test_every_nested_effect_type_exists(path):
    raw = json.loads(path.read_text(encoding="utf-8"))
    unknown = []
    for node in _effect_nodes(raw.get("abilities", [])):
        params = {k: v for k, v in node.items() if k not in ("type", "conditions")}
        try:
            compile_effect(str(node["type"]).upper(), params)
        except ValueError as exc:
            if "Unknown DSL effect type" in str(exc):
                unknown.append(node["type"])
        except Exception:
            # Any other failure is this node needing runtime state to compile,
            # not a missing type. Only the type name is under test here.
            pass
    assert not unknown, (
        f"{path.stem} names effect type(s) that do not exist: {sorted(set(unknown))}. "
        "Nested effects compile lazily, so this would raise mid-game rather "
        "than at load.")
