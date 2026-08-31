"""Whose "it" is it?

The gated-go-again sweep only counts cards that grant the keyword to
THEMSELVES, because only those can have the printed keyword stripped -- that is
the Luminaris distinction. It decides by looking at the printed subject, and
"it gets go again" is the one subject that does not settle the question:

    overload_yellow   "If Overload hits, it gains go again."       -> itself
    arakni_redback    "Target Assassin attack gets +3{p}.
                       If it has stealth, it gets go again."       -> the TARGET

Read whole-card, those are indistinguishable, and Arakni sat in the backlog as
a card to "fix" -- a hero, which is never an attack, so the SOURCE_IS_ATTACK
form would have been a straightforward lie about what it does.

The rule resolves a bare pronoun against the sentence before it, and is scoped
to that window rather than the whole card ON PURPOSE. tigrine_reflex_red gives
ITSELF go again in one sentence and targets another attack in an unrelated
Attack Reaction, so a rule that reads the whole card at once would call its go
again someone else's. The card is not implemented yet, so it is not in today's
backlog either way -- which is exactly why it is worth pinning now: when it is
authored it must land in scope, and a rule that quietly excuses it would show
up as the backlog failing to grow rather than as a failure.

THE REGEX IS ITS OWN PREMISE. This file's rule was first written with a
backslash-b word boundary through a shell heredoc, which turned it into a
literal backspace character; the pattern then matched nothing, silently, and
every card looked like it was about itself. That has now happened twice in this
effort, so the boundary is asserted rather than trusted.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.test_conditional_go_again_ratchet import (_TARGET_ATTACK,
                                                     _go_again_is_about_itself,
                                                     _unstripped)

IDX = json.loads((ROOT / "card_data" / "slug_index.json")
                 .read_text(encoding="utf-8"))["by_slug"]


def _about_itself(slug):
    entry = IDX[slug]
    return _go_again_is_about_itself(entry.get("functionalText") or "",
                                     entry.get("name") or "")


# --- the premise: the pattern is not silently matching nothing --------------

def test_the_target_attack_pattern_actually_matches():
    """Twice now a word boundary has survived a shell heredoc as a literal
    backspace, turning a working regex into one that matches nothing and
    reporting correct cards as defective."""
    assert _TARGET_ATTACK.search("Target Assassin attack gets +3{p}.")
    assert chr(8) not in _TARGET_ATTACK.pattern, (
        "the pattern contains a literal backspace -- a backslash-b was eaten "
        "by a shell heredoc again, and this rule now matches nothing")


def test_the_pattern_needs_an_attack_not_just_a_target():
    """"target hero" leaves no attack for a later "it" to refer to, and Aether
    Quickening -- whose go again is its own -- opens with exactly that."""
    assert not _TARGET_ATTACK.search("Deal 3 arcane damage to target hero.")


# --- pronouns ---------------------------------------------------------------

def test_a_bare_pronoun_after_a_targeted_attack_is_not_about_itself():
    assert not _about_itself("arakni_redback")


@pytest.mark.parametrize("slug", ["overload_yellow", "aether_quickening_yellow",
                                  "path_of_same_ends_red"])
def test_a_bare_pronoun_with_no_other_referent_is_about_itself(slug):
    assert _about_itself(slug), (
        slug + " is being read as granting go again to another card, so it "
        "would silently drop out of the backlog")


def test_naming_itself_beats_the_pronoun_rule():
    """tigrine_reflex_red does BOTH: "this gets +1{p} and go again" and, in an
    unrelated Attack Reaction, "target ... attack". Scoping the lookback to the
    go again sentence is what keeps it in scope."""
    assert _about_itself("tigrine_reflex_red")
    assert _TARGET_ATTACK.search(IDX["tigrine_reflex_red"]["functionalText"]), (
        "the card no longer mentions a targeted attack, so this stops being a "
        "test of the scoping")


def test_luminaris_is_still_excluded_by_the_older_rule():
    """It never uses a pronoun at all -- "your Illusionist attacks get go
    again" -- so it is caught by the subject test, not the lookback."""
    assert not _about_itself("luminaris")


# --- and the carve-out reaches the sweep ------------------------------------

def test_arakni_redback_is_out_of_the_backlog():
    assert "arakni_redback" not in _unstripped()


def test_tigrine_reflex_is_not_swept_out_with_it():
    """A false negative here would be invisible: the backlog number would fall
    by one and look like progress."""
    entry = IDX["tigrine_reflex_red"]
    assert "goagain" in [str(k).lower() for k in (entry.get("keywords") or [])]
    assert _about_itself("tigrine_reflex_red")
