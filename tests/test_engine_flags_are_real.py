"""The audit's allowlist of engine-written flags must be true.

audit_run.py flags a FLAG_SET on a name nothing sets, because such a condition is
permanently false and the ability CAN NEVER FIRE — the largest defect class found
in the corpus. ENGINE_FLAGS is the allowlist of names the ENGINE writes rather
than a card, and it was hand-written.

"die_rolled_six" was in it and set by nothing at all. So the audit certified a
dead flag as legitimate for the entire sweep, and reckless_charge_blue's "if
you've rolled a 6 this turn, draw a card" silently never drew. An allowlist entry
that is wrong suppresses precisely the defect the audit exists to find, which is
worse than having no allowlist.

This asserts each entry is really written somewhere in engine/.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import audit_run as A

ENGINE_SOURCES = [p for p in (ROOT / "engine").rglob("*.py")]
ENGINE_TEXT = "\n".join(p.read_text(encoding="utf-8", errors="ignore")
                        for p in ENGINE_SOURCES)


@pytest.mark.parametrize("flag", sorted(A.ENGINE_FLAGS))
def test_each_allowlisted_flag_is_written_by_the_engine(flag):
    assert flag in ENGINE_TEXT, (
        f"{flag!r} is allowlisted as engine-written, so the audit will never "
        "question a card that gates on it — but no engine source mentions it. "
        "Either the engine stopped writing it or it never did; every card "
        "reading it has an ability that can never fire."
    )


def test_the_allowlist_is_not_empty():
    # Guards the guard: an empty ENGINE_FLAGS would make the check above pass
    # vacuously while the audit lost its allowlist entirely.
    assert len(A.ENGINE_FLAGS) >= 8


def test_die_rolled_six_is_gone():
    # The specific regression. Rolls are now recorded as turn events
    # ("did_this_turn:roll:6"), which is also turn-scoped as the card text
    # requires — an earlier roll this turn counts.
    assert "die_rolled_six" not in A.ENGINE_FLAGS


def test_no_card_still_gates_on_the_dead_flag():
    live = [p for p in (ROOT / "engine" / "card_effects" / "json").rglob("*.json")
            if not any(part.startswith(".") for part in p.parts)]
    # Search the ABILITIES only. A "_comment" may legitimately name the flag to
    # record why the card stopped using it; what matters is that nothing gates
    # on it.
    import json
    offenders = []
    for p in live:
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        if re.search(r"DIE_ROLLED_SIX", json.dumps(raw.get("abilities", [])),
                     re.IGNORECASE):
            offenders.append(p.stem)
    assert not offenders, f"still reading a flag nothing sets: {offenders}"
