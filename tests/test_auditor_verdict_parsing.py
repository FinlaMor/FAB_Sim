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
    for marker in ("PART A", "PART B1", "PART B2", "PART B3",
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


def test_no_worked_example_names_a_card_that_could_be_audited():
    """This test asserted the OPPOSITE until the auditor was measured.

    It required the examples to name real corpus cards, on the reasoning that
    few-shot anchors should be concrete. The benchmark showed that naming them
    contaminates both the measurement and production: four of the eight catches
    were the four cited cards, and excluding them recall fell 29.6% -> 18.2%.
    The live hazard is worse than the measurement one -- auditing the ACCEPTED
    version of a cited card produced the only false positive, because the model
    read that card's old defect out of the instructions and reported it as
    present in JSON that no longer contained it.

    The examples are still concrete, still showing real JSON shapes; they just
    describe cards that do not exist.
    """
    from engine.card_effects.dsl.loader import load_all_cards
    import engine.card_effects.dsl.loader as loader
    load_all_cards()
    prompt = AIW.build_verification_prompt(CARD, ORIGINAL, "(reference)")
    instructions = prompt[prompt.index("=== PART A"):]
    cited = [slug for slug in loader._CARDS
             if len(slug) > 8 and slug in instructions]
    assert not cited, (
        "the instructions name real corpus cards, which the model reads back "
        "as findings when it audits them: " + ", ".join(sorted(cited)))


def test_the_examples_are_still_concrete():
    """Decontaminating must not have flattened them into abstractions -- the
    anchor is the JSON shape, not the card name."""
    prompt = AIW.build_verification_prompt(CARD, ORIGINAL, "(reference)")
    for shape in ('"GRANT_SUBTYPE"', '"SET_FLAG"', '"HAS_KEYWORD"',
                  '"REF_PITCH_IS"', '"GAIN", "keyword"'):
        assert shape in prompt, shape + " is no longer shown as a worked shape"


def test_the_talishar_reference_stays_out_of_the_prompt(monkeypatch):
    """This test asserted the OPPOSITE twice before the measurements landed.

    A reference implementation of the same card is the cheapest outside evidence
    available for a weakness that is semantic, so it was tried twice, against 27
    labelled before/after pairs each time:

        v3  supplied as reference material     33.3% recall / 3.7% FP  (0.30)
        v4  Part D forcing the comparison      22.2% / 7.4%            (0.15)
        v2  no Talishar at all                 37.0% / 3.7%            (0.33)

    v3 did nothing at all -- on the 12 cards with a substantive reference the
    arms scored identically, 5/12 both times, and 0 of 54 replies mentioned it.
    v4 tested the obvious diagnosis (unused context is ignored) with the obvious
    fix (make it an enumeration, which is what rescued B1) and came out WORSE
    than having no reference at all.

    So it is deleted, and this guards the deletion: ~400 tokens per card and two
    measured attempts, no gain either way. Re-adding it needs a NEW measurement,
    not a new argument -- both arguments for it have already been tried.
    """
    monkeypatch.setattr(AIW, "_talishar_reference",
                        lambda slug: "if(count($theirSoul) > 0) GiveGoAgain();")
    prompt = AIW.build_verification_prompt(CARD, ORIGINAL, "(reference)")
    assert "Talishar" not in prompt
    assert "GiveGoAgain" not in prompt
    assert "PART D" not in prompt, (
        "the forced-comparison part is back; it scored 22.2%/7.4% against "
        "37.0%/3.7% without it")
    assert "then Part C" in prompt, "the output ordering lost Part C"


def test_enumeration_is_not_assumed_to_be_a_universal_lever():
    """The one generalisation the v4 result forbids.

    Part A is produced 54/54 and B1 improved when it became a table, so
    "enumeration works where judgement does not" was the standing lesson. Part D
    was an enumeration too, and it LOST 11 points of recall. It works when what
    is being enumerated is the card's own text; it does not work when the model
    is made to reconcile two implementations in different languages, which
    manufactures divergences that are not defects.

    Kept as a test so the reasoning is attached to the prompt rather than to a
    commit message nobody reads.
    """
    prompt = AIW.build_verification_prompt(CARD, ORIGINAL, "(reference)")
    enumerations = [l for l in prompt.splitlines() if l.startswith("=== PART")]
    assert len(enumerations) == 5, enumerations
    for part in ("PART A", "PART B1", "PART B2", "PART B3", "PART C"):
        assert any(part in e for e in enumerations), part


def test_b1_is_mechanical_not_a_judgement_call():
    """B1 missed the class it was written for while Part A worked 54/54. The
    difference is that Part A is an enumeration and B1 was a yes/no over a
    conjunction. It is now a table with a syntactic rule."""
    prompt = AIW.build_verification_prompt(CARD, ORIGINAL, "(reference)")
    b1 = prompt[prompt.index("=== PART B1"):prompt.index("=== PART B2")]
    assert "one row for EVERY keyword" in b1, "B1 is no longer an enumeration"
    assert "GATED" in b1 and "PLAIN" in b1
    assert '"if", "whenever", or "while"' in b1, (
        "the syntactic rule is gone; without it GATED is a judgement again")
    assert "do not decide which ones are interesting" in b1
