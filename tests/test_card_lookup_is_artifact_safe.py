"""No test may find a card by walking the tree and taking the first hit.

engine/card_effects/json holds cards. It also holds .quarantine/ here, and in
the pipeline worktree it holds .drafts/, .review/, .triage/ and .draft-review/
-- results filed under the SAME SLUGS as the cards they are about.

`next(root.rglob(f"{slug}.json"))` returns whatever the walk reaches first, and
".review" sorts before every set directory. So in the worktree that first hit
was a REVIEW VERDICT: an object with no "abilities". Seventy-seven tests failed
there, in 22 files, each looking like a product bug in the card it named, and
the whole suite had been red for long enough that nobody could tell which
failures were real.

The fix is one helper, conftest._card_json / card_json_files, which skips
dot-directories -- the rule the loader itself applies. This test is what stops
the pattern coming back, because the bare version is shorter to write and looks
correct in this repo, where it usually is.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"

#: A card lookup that takes the first rglob hit, in the spellings that have
#: actually appeared here.
_BARE = re.compile(
    r"next\(\s*\w+\.rglob\(|"           # next(root.rglob(...))
    r"next\(\s*p for p in \w+\.rglob\(|"  # next(p for p in root.rglob(...))
    r"\.rglob\(\s*f?\"\{?slug",          # root.rglob(f"{slug}.json")
)

#: These define their own equivalent helper rather than importing one.
_ALLOWED = {"test_transcend.py", "test_wrong_player_effects.py",
            "test_card_lookup_is_artifact_safe.py"}


def test_no_test_finds_a_card_by_first_rglob_hit():
    offenders = []
    for path in sorted(TESTS.glob("test_*.py")):
        if path.name in _ALLOWED:
            continue
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if _BARE.search(line):
                offenders.append(f"{path.name}:{i}: {line.strip()}")
    assert offenders == [], (
        "use conftest._card_json(root, name) instead -- a bare rglob picks up "
        "pipeline results filed under the same slug:\n  "
        + "\n  ".join(offenders))


def test_the_helper_actually_skips_dot_directories():
    """The premise. If _card_json stopped filtering, the test above would still
    pass while every lookup it protects went back to being wrong."""
    from tests.conftest import _card_json, card_json_files

    json_root = ROOT / "engine" / "card_effects" / "json"
    for p in card_json_files(json_root):
        assert not any(part.startswith(".") for part in p.parts), p

    # and it must still find a real card
    found = _card_json(json_root, "alpha_rampage_red.json")
    assert found.parent.name == "wtr", found
