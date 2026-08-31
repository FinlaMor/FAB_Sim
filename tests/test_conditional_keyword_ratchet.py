"""The gated-printed-keyword defect, across EVERY keyword the engine can strip.

The go-again backlog was one slice of this problem, not the problem. The same
sweep run over the other ten entries in `_GRANTABLE_KEYWORDS` found 14 more
cards -- nine Overpower, two Dominate, one Blade Break, and the two go-again
stragglers -- and several of them turned out to be the *same sentence* as a
card already fixed, with one word changed:

    torque_tuned_red/blue   <- soup_up_red            (item destroyed this turn)
    vantage_point_red       <- runerager_swarm_blue   (played or created an aura)
    glaring_impact_blue     <- light_the_way_red      (a yellow card charged)

They carried their twins' DEFECTS, not just their text. torque_tuned's clause
hung off ON_DEFEND -- the card's other half -- exactly as soup_up_red's did;
vantage_point asked only about CREATED auras, missing the played half, exactly
as runerager_swarm_blue did. Two independently authored cards do not acquire
identical defects by chance: the sentence was being read the same wrong way
every time it appeared, which is why sweeping by PHRASING finds things that
sweeping by card does not.

This file is the ratchet for the whole class. The number may only fall.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card_effects.dsl.loader import (_GRANTABLE_KEYWORDS, _kw_key,
                                            conditional_keywords,
                                            load_all_cards)
from tests.conditional_keyword_sweep import (OTHER_REFERENT, is_about_itself,
                                             unstripped)

load_all_cards()

#: Every grantable keyword, spelled as the printed text spells it.
WORDS = ["go again", "overpower", "dominate", "intimidate", "piercing",
         "stealth", "phantasm", "battleworn", "blade break", "reprise",
         "temper"]

#: Cards still carrying an unconditional printed keyword their own text gates.
#: Lower it as they are fixed; it must never rise.
#:
#: THE THREE LEFT ARE BLOCKED ON ENGINE WORK, not on judgement:
#:
#:   ebbing_arcstride_red   "Whenever this FRAGMENTS, it gets go again."
#:   ebbing_arcstride_blue  Fragment is not implemented anywhere, and its rules
#:                          text is in neither the CR nor any release notes in
#:                          docs/ref/ (Omens of the Third Age has none).
#:
#:   gloves_of_azure_waves  "High Tide - if there are 2+ blue cards in your
#:                          pitch zone, this gets +3{d} and BLADE BREAK."
#:                          Blade Break is a triggered-static (CR 8.3.3), and
#:                          triggers.build_keyword_triggers registers it
#:                          straight from the card DB without consulting
#:                          conditional_keywords -- a THIRD path, after the
#:                          attack recalculation and the non-attack layer. The
#:                          gloves are destroyed every time they defend, High
#:                          Tide or not. See engine/AGENTS.md.
UNSTRIPPED_LIMIT = 3


def test_the_sweep_still_matches_cards():
    """A premise. If the phrasings or keyword spellings moved, the ratchet
    below would pass by measuring nothing."""
    idx = json.loads((ROOT / "card_data" / "slug_index.json")
                     .read_text(encoding="utf-8"))["by_slug"]
    from tests.conditional_keyword_sweep import gated
    total = 0
    for word in WORDS:
        pattern = gated(word)
        total += sum(1 for e in idx.values()
                     if _kw_key(word) in {_kw_key(k) for k in (e.get("keywords") or [])}
                     and pattern.search(e.get("functionalText") or ""))
    assert total > 60, total


def test_every_grantable_keyword_is_swept():
    """A keyword the engine can strip but nobody sweeps for is where the next
    18-card class of free permanent buffs will accumulate."""
    swept = {_kw_key(w) for w in WORDS}
    missing = {_kw_key(k) for k in _GRANTABLE_KEYWORDS} - swept
    assert not missing, (
        "these keywords can be granted conditionally but are not swept for: "
        + ", ".join(sorted(missing)))


def test_the_unstripped_count_does_not_grow():
    found = unstripped(WORDS)
    flat = sorted(slug for hits in found.values() for slug in hits)
    assert len(flat) <= UNSTRIPPED_LIMIT, (
        "%d cards print a keyword unconditionally while their own text gates "
        "it (limit %d):\n  " % (len(flat), UNSTRIPPED_LIMIT)
        + "\n  ".join("%-26s %s" % (s, w)
                      for w, hits in sorted(found.items()) for s in hits))


#: Fixed, and they must stay fixed.
FIXED = [("torque_tuned_red", "overpower"), ("torque_tuned_blue", "overpower"),
         ("vantage_point_red", "overpower"), ("glaring_impact_blue", "overpower"),
         ("hydraulic_press_blue", "overpower"), ("spectral_rider_red", "overpower"),
         ("the_golden_son_yellow", "overpower"), ("burly_bones_red", "overpower"),
         ("burly_bones_blue", "overpower"),
         ("writhing_beast_hulk_red", "dominate")]


@pytest.mark.parametrize("slug,word", FIXED)
def test_a_fixed_card_stays_fixed(slug, word):
    assert _kw_key(word) in conditional_keywords(slug), (
        slug + " is back to an unconditional printed " + word)


#: Matched by the sweep, but NOT defects: the keyword is handed to another
#: card, so the printed listing is the DB flattening a sentence about someone
#: else. Stripping it would take a keyword from a card that is not the one the
#: sentence is about -- the Luminaris mistake.
NOT_DEFECTS = [("weave_ice_yellow", "dominate"), ("luminaris", "go again"),
               ("arakni_redback", "go again")]


@pytest.mark.parametrize("slug,word", NOT_DEFECTS)
def test_a_false_positive_stays_out_of_the_sweep(slug, word):
    found = unstripped([word])
    assert slug not in found.get(word, []), (
        slug + " is being counted as a gated-" + word + " defect, but it grants "
        "the keyword to another card")


@pytest.mark.parametrize("slug,word", NOT_DEFECTS)
def test_a_false_positive_is_not_converted(slug, word):
    assert _kw_key(word) not in conditional_keywords(slug), (
        slug + " had its printed " + word + " stripped, but the keyword belongs "
        "to a different card")


def test_the_referent_pattern_is_not_silently_broken():
    """Twice in this effort a word boundary has survived a shell heredoc as a
    literal backspace, turning a working regex into one that matches nothing
    and reporting correct cards as defective."""
    assert chr(8) not in OTHER_REFERENT.pattern
    assert OTHER_REFERENT.search("Target Assassin attack gets +3{p}.")
    assert OTHER_REFERENT.search(
        "The next Ice or Elemental attack action card you play this turn")
    assert not OTHER_REFERENT.search("Deal 3 arcane damage to target hero.")


def test_the_pronoun_rule_is_scoped_to_the_keyword_sentence():
    """A card can do BOTH -- give itself the keyword in one sentence and target
    another card in an unrelated one. Reading the whole card at once would
    excuse it from a sweep it belongs in."""
    idx = json.loads((ROOT / "card_data" / "slug_index.json")
                     .read_text(encoding="utf-8"))["by_slug"]
    entry = idx["tigrine_reflex_red"]
    text = entry.get("functionalText") or ""
    assert OTHER_REFERENT.search(text), (
        "tigrine_reflex_red no longer mentions a targeted attack, so it has "
        "stopped being a test of the scoping")
    assert is_about_itself(text, entry.get("name") or "", "go again")
