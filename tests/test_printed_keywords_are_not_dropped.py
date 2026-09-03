"""Three cards print a keyword the upstream card index forgot to record.

The community card index populates each card's `keywords` list by hand, and it
misses one occasionally. Blood Runs Deep and Meganetic Lockwave both print a
standalone "**Go again**" line and carry an EMPTY keyword list; Mask of
Malicious Manifestations prints "**Blade break**" and lists only go again.
Nothing downstream reads functional text, so those cards simply did not have
the keyword.

All three are still unauthored, so this is PREVENTIVE rather than a live fix.
It is worth having anyway: the natural move when authoring a card is to trust
`keywords`, so the omission would have been inherited silently and the card
would have shipped without its go again.

Found by differential-testing attack keywords against real Talishar games
(scripts/talishar_combat_diff.py): Talishar reported go again in all 110
spectator observations of Blood Runs Deep attacking, with none against, while
our data claimed the card had no keywords at all.

WHY THE SCAN IS RESTRICTED TO KNOWN KEYWORDS. The first version matched any
bold standalone line and invented 254 keywords across the corpus out of things
that merely look like keyword lines — "**Ice Fusion**", "**Rhinar
Specialization**", and one card's actual misprint "**Arcane Barrer**". The
restriction to spellings other cards already use is what makes the rule safe,
so it is tested here directly rather than left as a comment.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card import CardDB, _keyword_vocabulary, _keywords_with_printed

DB = CardDB()
IDX = json.loads((ROOT / "card_data" / "slug_index.json")
                 .read_text(encoding="utf-8"))["by_slug"]


@pytest.mark.parametrize("slug,keyword", [
    ("blood_runs_deep_red", "GoAgain"),
    ("meganetic_lockwave_blue", "GoAgain"),
    ("mask_of_malicious_manifestations", "BladeBreak"),
])
def test_a_printed_keyword_reaches_the_card(slug, keyword):
    card = DB.get(slug)
    assert card is not None, slug
    assert keyword in (card.keywords or []), (
        "%s prints %s but the card object does not have it" % (slug, keyword))


def test_blood_runs_deep_has_go_again():
    """The observable consequence: has_go_again is what earns the action point
    when the layer resolves, and it was False."""
    assert DB.get("blood_runs_deep_red").has_go_again


def test_the_upstream_data_really_is_missing_it():
    """The premise. If upstream ever fixes its own data, this rule stops being
    load-bearing and the test should say so rather than silently pass."""
    raw = IDX["blood_runs_deep_red"].get("keywords") or []
    assert "GoAgain" not in raw, (
        "upstream now records the keyword; the normalisation is redundant here")
    assert re.search(r"^\s*\*\*Go again\*\*\s*$",
                     IDX["blood_runs_deep_red"]["functionalText"], re.I | re.M)


def test_a_card_that_prints_nothing_gains_nothing():
    """The other half — a keywordless card must stay keywordless."""
    assert not (DB.get("wounded_bull_red").keywords or [])


def test_the_scan_invents_no_keywords_anywhere_in_the_corpus():
    """Swept rather than sampled. The failure mode of this rule is not missing
    a card, it is adding junk to hundreds — so the assertion is about the whole
    corpus, and it names what it would have added."""
    vocabulary = _keyword_vocabulary()
    added = {}
    for slug, entry in IDX.items():
        before = entry.get("keywords") or []
        after = _keywords_with_printed(list(before), entry.get("functionalText"))
        for kw in after[len(before):]:
            added.setdefault(kw, []).append(slug)

    invented = {k: v for k, v in added.items()
                if re.sub(r"[^a-z]", "", k.lower()) not in vocabulary}
    assert not invented, "the scan invented keywords: %s" % invented
    assert sum(len(v) for v in added.values()) == 3, (
        "expected exactly the 3 known omissions, got %s"
        % {k: v for k, v in added.items()})


def test_a_keyword_is_never_added_twice():
    """CR 8.3.5b — an object cannot have two instances of a keyword. Every card
    that prints go again already lists it, so the guard runs constantly."""
    for slug in ("head_jab_red", "mask_of_malicious_manifestations"):
        kws = DB.get(slug).keywords or []
        assert len(kws) == len(set(kws)), "%s has a duplicate keyword: %s" % (slug, kws)
