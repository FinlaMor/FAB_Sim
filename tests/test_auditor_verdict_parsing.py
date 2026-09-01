"""The auditor's verdict is read from a VERDICT line, and a non-answer keeps the card.

The auditor prompt now asks for a CLAUSE MAP before its verdict, because the map
is the part that does the work: an omitted clause has to be listed with nothing
beside it, so it cannot be skipped over silently. That reordering breaks the old
parser, which looked for "LOOKS_GOOD" in the first 40 characters of the
response -- with a map in front of it, every audit would have scored as a
correction and the auditor would have rewritten every card in the corpus from
whatever JSON-shaped text appeared first in its reasoning.

The other half of the contract matters as much: an auditor that does NOT follow
the format has not audited anything, and its output is not a mandate to rewrite
the card. A missing verdict, a missing JSON body, unparseable JSON, or a
correction carrying a DIFFERENT card's slug all keep the original. That last one
is not hypothetical for a 14B model asked to hold a 13k-token prompt.

These are parser tests and run without a model. What the auditor SAYS is a
separate question, measured by scripts/bench_triage.py.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "auto_implement_wtr", ROOT / "scripts" / "auto_implement_wtr.py")
AIW = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(AIW)

CARD = {"slug": "torque_tuned_red",
        "functional_text": "If an item you control has been destroyed this "
                           "turn, this gets **overpower**.",
        "keywords": ["Galvanize", "Overpower"]}
ORIGINAL = json.dumps({"slug": "torque_tuned_red", "abilities": []})
CORRECTED = json.dumps({"slug": "torque_tuned_red",
                        "abilities": [{"ability_type": "WHILE_STATIC",
                                       "conditions": [{"type": "SOURCE_IS_ATTACK"}],
                                       "effects": [{"type": "GAIN",
                                                    "keyword": "OVERPOWER"}]}]})

MAP_PREAMBLE = (
    "=== PART A ===\n"
    '"If an item you control has been destroyed this turn, this gets '
    'overpower"  ->  {"type": "GAIN", "keyword": "OVERPOWER"}\n'
    "=== PART B ===\n"
    "B1. NO -- the printed Overpower is granted from a SOURCE_IS_ATTACK static.\n"
    "B2. NO.\nB3. NO.\n"
    "=== PART C ===\nC1. NO.\n")


def _run(monkeypatch, response):
    monkeypatch.setattr(AIW, "run_llm", lambda *a, **k: response)
    return AIW.run_verification_pass(CARD, ORIGINAL, "(reference)", None, False)


def test_a_verdict_after_the_clause_map_is_still_read(monkeypatch):
    """The whole point of the reordering. The old parser read the first 40
    characters and would have seen the map, not the verdict."""
    assert _run(monkeypatch, MAP_PREAMBLE + "VERDICT: LOOKS_GOOD") == ORIGINAL


def test_a_correction_after_the_map_is_applied(monkeypatch):
    out = _run(monkeypatch, MAP_PREAMBLE + "VERDICT: CORRECTED\n" + CORRECTED)
    assert json.loads(out)["abilities"], "the correction was not applied"


def test_json_quoted_inside_the_map_is_not_mistaken_for_the_correction(monkeypatch):
    """Part A quotes JSON nodes by design, so JSON appears BEFORE the verdict on
    every single audit. Taking the first object would apply a fragment of the
    auditor's own reasoning as the card."""
    out = _run(monkeypatch, MAP_PREAMBLE + "VERDICT: CORRECTED\n" + CORRECTED)
    assert json.loads(out) == json.loads(CORRECTED)


def test_no_verdict_line_keeps_the_original(monkeypatch):
    """An auditor that did not follow the contract has not audited anything."""
    assert _run(monkeypatch, MAP_PREAMBLE + "Looks fine to me!") == ORIGINAL


def test_a_bare_looks_good_without_the_prefix_is_not_a_verdict(monkeypatch):
    """"LOOKS_GOOD" appears in the prompt itself, so a model echoing the
    instructions must not be read as having reached a verdict."""
    assert _run(monkeypatch, "I will output LOOKS_GOOD if it passes.\n"
                             + MAP_PREAMBLE) == ORIGINAL


def test_corrected_without_json_keeps_the_original(monkeypatch):
    assert _run(monkeypatch, MAP_PREAMBLE + "VERDICT: CORRECTED\n(no json)") == ORIGINAL


def test_unparseable_correction_keeps_the_original(monkeypatch):
    assert _run(monkeypatch,
                MAP_PREAMBLE + "VERDICT: CORRECTED\n{not valid json,,}") == ORIGINAL


def test_a_correction_for_a_different_card_is_refused(monkeypatch):
    """A 14B model holding a 13k-token prompt can drift onto an example card.
    Applying that would overwrite one card with another's implementation."""
    other = json.dumps({"slug": "hydraulic_press_blue",
                        "abilities": [{"ability_type": "PLAY", "effects": []}]})
    assert _run(monkeypatch, MAP_PREAMBLE + "VERDICT: CORRECTED\n" + other) == ORIGINAL


def test_reasoning_blocks_are_stripped_before_the_verdict_is_read(monkeypatch):
    assert _run(monkeypatch,
                "<think>maybe VERDICT: CORRECTED</think>\n"
                + MAP_PREAMBLE + "VERDICT: LOOKS_GOOD") == ORIGINAL


def test_the_last_verdict_wins(monkeypatch):
    """A model that talks through the format before answering states the verdict
    more than once; the one it ends on is its answer."""
    assert _run(monkeypatch,
                "VERDICT: CORRECTED would mean a fix.\n" + MAP_PREAMBLE
                + "VERDICT: LOOKS_GOOD") == ORIGINAL


def test_a_backend_failure_keeps_the_original(monkeypatch):
    assert _run(monkeypatch, "CLAW_ERROR: backend down") == ORIGINAL
    assert _run(monkeypatch, "CLAW_TIMEOUT") == ORIGINAL


# --- the prompt itself ------------------------------------------------------

def test_the_prompt_asks_the_three_checks_and_the_clause_map():
    prompt = AIW.build_verification_prompt(CARD, ORIGINAL, "(reference)")
    for marker in ("PART A", "PART B", "B1.", "B2.", "B3.",
                   "VERDICT: LOOKS_GOOD", "VERDICT: CORRECTED"):
        assert marker in prompt, marker


def test_the_prompt_carries_the_printed_keywords():
    """B1 cannot be answered without them: the defect is a MISMATCH between the
    printed keyword list and the gating text, and the model cannot see the card
    DB."""
    prompt = AIW.build_verification_prompt(CARD, ORIGINAL, "(reference)")
    assert "Overpower" in prompt
    assert "printed keywords" in prompt


def test_the_prompt_does_not_presuppose_a_defect():
    """"There IS a problem, find it" manufactures findings -- a sweep run that
    way produced 22 of which 7 were real. The prompt must ask, not assert."""
    lowered = AIW.build_verification_prompt(CARD, ORIGINAL, "(reference)").lower()
    for banned in ("there is a problem", "find the bug", "this card is wrong",
                   "at least one"):
        assert banned not in lowered, banned


def test_every_worked_example_names_a_real_card():
    """The examples are few-shot anchors, and few-shot is the one intervention
    that measurably helped (+11 on triage). An example naming a card that does
    not exist is not an anchor, it is noise."""
    from engine.card_effects.dsl.loader import get_card, load_all_cards
    load_all_cards()
    prompt = AIW.build_verification_prompt(CARD, ORIGINAL, "(reference)")
    for slug in ("torque_tuned_red", "hydraulic_press_blue",
                 "spectral_rider_red", "burly_bones_red"):
        assert slug in prompt, slug + " is no longer cited as an example"
        assert get_card(slug) is not None, (
            slug + " is cited as a worked example but is not in the corpus")
