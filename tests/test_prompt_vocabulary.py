"""The authoring prompt must offer every type the validator accepts.

`build_dsl_reference()` extracted only `if etype == "X"` registrations, missing
every type registered as `if etype in ("X", "Y")` — 30 of them, including
EVENT_THIS_TURN, CONDITIONAL_EFFECT, DESTROYED_THIS_TURN, OR and AND.

The prompt also says "Use ONLY type names that appear in the lists above" and
"Never invent a type". So the model was told, in the same breath, that its way of
expressing "if you've done X this turn" did not exist — and it did the only thing
left: invented a private flag. That single gap is a plausible root cause for a
large share of the 154 invented flags found across the corpus.

Prompt vocabulary and validator vocabulary must stay the same set.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import auto_implement_wtr as A


def test_prompt_offers_every_type_the_validator_accepts():
    reference = A.build_dsl_reference()
    missing = sorted(t for t in A.valid_type_names() if t not in reference)
    assert not missing, (
        "these types are accepted by the loader but never shown to the model, so "
        "a card needing them looks impossible and the model invents a flag "
        f"instead: {missing}"
    )


def test_validator_vocabulary_is_not_empty():
    # Guards the guard: if the extraction regexes go stale both sides could
    # collapse to empty and the check above would pass vacuously.
    assert len(A.valid_type_names()) > 150


@pytest.mark.parametrize("name", [
    "EVENT_THIS_TURN", "DESTROYED_THIS_TURN", "CONDITIONAL_EFFECT",
    "LAST_CHAIN_ATTACK", "REPRISE", "MODIFY_NEXT_ATTACK",
    "MODIFY_ATTACKS_THIS_TURN", "ATTACK_POWER_GT_BASE",
])
def test_primitives_behind_real_defect_classes_are_offered(name):
    # Each of these replaced an invented flag in a card that could never fire.
    assert name in A.build_dsl_reference()


def test_recipes_map_card_text_to_primitives():
    # A bare list of ~200 type names does not tell the model WHEN to use one.
    # The recipe block is what makes the existing primitive findable.
    ref = A.build_dsl_reference()
    for phrase in ("this turn", "Combo", "Reprise", "instead", "ability_type"):
        assert phrase in ref, f"recipe guidance for {phrase!r} missing from the prompt"


def test_prompt_warns_against_inventing_flags():
    assert "NEVER invent a flag" in A.build_dsl_reference()


def test_amount_expression_list_is_generated_not_typed():
    # This list was hand-maintained and drifted from the engine three times in
    # one session, each time telling the model a just-added expression was
    # invalid. It is now read from _resolve_amount's own dispatch chain.
    names = A.amount_expression_names()
    assert names, "no amount expressions found — the extraction regex is stale"
    reference = A.build_dsl_reference()
    assert "{AMOUNT_EXPRESSIONS}" not in reference, "placeholder was never substituted"
    for name in names:
        assert name in reference, f"{name} is a real amount expression but absent from the prompt"


def test_a_new_amount_expression_reaches_the_prompt_automatically(tmp_path, monkeypatch):
    # The drift test: add an expression to the engine source and confirm the
    # prompt picks it up with no second edit. Guards the generation itself —
    # the test above would still pass if the list were re-hardcoded to today's
    # values.
    real = (A.DSL_DIR / "effect_types.py").read_text(encoding="utf-8")
    fake_dir = tmp_path / "dsl"
    fake_dir.mkdir()
    (fake_dir / "effect_types.py").write_text(
        real + '\n\ndef _probe():\n    if atype == "TOTALLY_NEW_EXPRESSION":\n        return 0\n',
        encoding="utf-8")
    for name in ("condition_types.py", "cost_types.py", "trigger_types.py"):
        (fake_dir / name).write_text((A.DSL_DIR / name).read_text(encoding="utf-8"),
                                     encoding="utf-8")
    monkeypatch.setattr(A, "DSL_DIR", fake_dir)
    assert "TOTALLY_NEW_EXPRESSION" in A.amount_expression_names()
    assert "TOTALLY_NEW_EXPRESSION" in A.build_dsl_reference()
