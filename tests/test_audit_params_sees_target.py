"""scripts/audit_params.py must not exempt the keys it exists to check.

The audit's job is to report card parameters no compiler reads. It kept one flat
STRUCTURAL_KEYS list for "keys the loader consumes", and "target" was in it —
but the loader pops exactly one key from an effect node, "conditions". So every
effect naming a target got a free pass from the one check that would have caught
it, and 33 BANISH nodes naming a player and a zone went unreported while
banishing from the wrong player's deck.

A guard whose blind spot covers the defect class is worse than no guard: it
answers "clean" and is believed. These tests pin the exemptions to what the
loader actually does.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import audit_params as A  # noqa: E402


def test_target_is_not_exempt():
    """The key the whole class hid behind."""
    assert "target" not in A.STRUCTURAL_KEYS
    assert "target" not in A.NESTED_KEYS


def test_filter_is_not_exempt():
    """"filter" is an ordinary param at effect level too — most handlers that
    are given one do read it, but the ones that don't are real findings."""
    assert "filter" not in A.STRUCTURAL_KEYS
    assert "filter" not in A.NESTED_KEYS


def test_exemptions_match_what_the_loader_pops():
    """Only "conditions" is removed from an effect's params by the loader.

    If loader._compile_effect ever pops more, this fails and the exemption list
    is updated deliberately rather than by guesswork.
    """
    import inspect
    from engine.card_effects.dsl import loader

    src = inspect.getsource(loader._compile_effect)
    popped = {"conditions"} if 'params.pop("conditions"' in src else set()
    assert popped, "loader._compile_effect no longer pops 'conditions'"
    assert A.STRUCTURAL_KEYS == {"type"} | popped


def test_an_unread_target_is_reported():
    """End to end: a node whose handler ignores `target` must be reported."""
    index = A.build_index()
    assert "target" not in index["PUT_COUNTER"], (
        "PUT_COUNTER now reads target — update this test's example")

    found = A.audit_node({"type": "PUT_COUNTER", "counter": "steam",
                          "target": {"type": "CARD"}}, index)
    assert any("target" in f for f in found), found


def test_a_read_param_is_not_reported():
    """The audit must stay quiet about params the handler does read, or the
    signal drowns and nobody reads the report."""
    index = A.build_index()
    assert "counter" in index["PUT_COUNTER"]
    assert A.audit_node({"type": "PUT_COUNTER", "counter": "steam"}, index) == []


def test_a_wholesale_handler_reports_nothing():
    """RESTRICT_DEFENDERS builds its filter from `params.items()`, so every key
    on it is read. A scan for params.get("literal") sees none of them and
    reported two correct cards as broken."""
    index = A.build_index()
    assert A.WHOLESALE in index["RESTRICT_DEFENDERS"]
    assert A.audit_node({"type": "RESTRICT_DEFENDERS", "equipment": True},
                        index) == []


def test_wholesale_is_not_handed_out_broadly():
    """The exemption must stay narrow: it suppresses every finding on a type,
    so a loose detector would silently switch the whole audit off."""
    index = A.build_index()
    wholesale = {k for k, v in index.items() if A.WHOLESALE in v}
    assert len(wholesale) <= 5, sorted(wholesale)
    assert "BANISH" not in wholesale
    assert "PUT_COUNTER" not in wholesale


def test_banish_now_reads_its_target():
    """The fix this guard was extended for."""
    index = A.build_index()
    for key in ("target", "player", "from_zone"):
        assert key in index["BANISH"], key
