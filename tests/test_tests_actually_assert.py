"""Some tests in this suite assert nothing at all.

Found while fixing winters_bite_yellow. Two generated tests for it were failing,
and both turned out to encode the card's defects rather than its text: one
asserted that the CASTER discards ("target hero discards a card"), the other
that the caster loses 2 life (the card has no life cost). They were generated
from the card's JSON, and the JSON was wrong — so they faithfully certified both
bugs.

That is the structural risk with generated tests: a test written from an
implementation cannot detect that the implementation disagrees with the card.
It can only detect that the implementation changed.

The weaker version of the same problem is a test that asserts nothing at all —
`assert True  # Replace with actual assertion logic`, or no assert statement.
Those count toward a green suite and verify nothing. 46 of 1586 test functions
are in that state.

This does not rewrite them; each needs its card read, which is the same work as
implementing the card. It pins the number so it cannot grow, in the same spirit
as test_param_names_are_read's regression count.
"""
from __future__ import annotations

import ast
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent

#: Tests whose whole point is "this does not raise". They have no assert by
#: design, and naming them here keeps them out of the count without weakening it.
INTENTIONAL_SMOKE = {
    "test_dispatch_unknown_slug_no_crash",
    "test_disable_blue_no_crash_when_arsenal_empty",
    "test_alpha_rampage_red_on_attack_no_crash",
    "test_enlightened_strike_red_loads_and_dispatches_without_crash",
    "test_sink_below_red_no_crash_empty_hand",
}


def _classify(fn: ast.FunctionDef, source: str) -> str | None:
    segment = ast.get_source_segment(source, fn) or ""
    asserts = [n for n in ast.walk(fn) if isinstance(n, ast.Assert)]
    # pytest.raises / pytest.warns ARE the assertion in those tests.
    if "pytest.raises" in segment or "pytest.warns" in segment:
        return None
    if asserts and all(isinstance(a.test, ast.Constant) and bool(a.test.value)
                       for a in asserts):
        return "assert-True"
    if not asserts:
        return "no-assert"
    return None


def _vacuous_tests() -> list[str]:
    out = []
    for path in sorted(TESTS_DIR.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for fn in ast.walk(tree):
            if not (isinstance(fn, ast.FunctionDef) and fn.name.startswith("test_")):
                continue
            if fn.name in INTENTIONAL_SMOKE:
                continue
            kind = _classify(fn, source)
            if kind:
                out.append(f"{path.name}::{fn.name} ({kind})")
    return out


def test_the_scan_finds_the_test_files():
    """Guards the guard: if the glob or the parse breaks, everything below
    passes vacuously — which is the exact failure this file is about."""
    count = 0
    for path in TESTS_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        count += sum(1 for n in ast.walk(tree)
                     if isinstance(n, ast.FunctionDef) and n.name.startswith("test_"))
    assert count > 1000, f"only {count} test functions seen; the scan is stale"


def test_vacuous_test_count_does_not_grow():
    vacuous = _vacuous_tests()
    # Lower this as they are rewritten; never raise it. A new one means a test
    # was added that cannot fail, and a test that cannot fail is worse than no
    # test — it reports coverage that is not there.
    assert len(vacuous) <= 41, (
        f"{len(vacuous)} tests assert nothing (was 41):\n  "
        + "\n  ".join(vacuous))


def test_this_files_own_tests_assert_something():
    """The one file that must never appear in its own report."""
    assert not [v for v in _vacuous_tests() if Path(__file__).name in v]
