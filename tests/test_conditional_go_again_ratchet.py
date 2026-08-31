"""Cards that PRINT go again but whose text makes it conditional.

The card database has no way to mark a keyword conditional, so a printed
GoAgain is granted unconditionally. A card reading "IF <x>, this gets go again"
therefore has it always, whatever its JSON says -- the gate is decoration, and
the card is strictly stronger than printed.

`loader.conditional_keywords()` is what takes the printed keyword away, and it
recognises exactly one shape: an ability gated on SOURCE_IS_ATTACK that grants
the keyword. That is what separates "THIS gains go again" from Luminaris's
"your Illusionist attacks get go again", where the printed listing on the
weapon is the card database flattening a sentence about OTHER cards.

Aggressive Pounce was the first of these fixed, with the official release notes
confirming the timing. The sweep below found the class is far larger: 50 cards
whose text gates go again and whose JSON does not strip the printed keyword.

WHY THIS IS A RATCHET AND NOT A FIX. Of those 50, 47 already grant GO_AGAIN
with the right condition and only lack SOURCE_IS_ATTACK -- but they grant it
from TRIGGERED, PLAY or ACTIVATE abilities, and moving them to the WHILE_STATIC
form is a SEMANTIC change, not a mechanical one: it moves the condition from
being read once to being read continuously (CR 6.2.3d). Thirty-two such
conversions applied blind would be a mass edit of exactly the kind that has
already produced two self-inflicted bugs in this effort. So the count is pinned
here and the backlog is worked down deliberately, card by card, with the
printed text and the release notes in hand.

Not every hit is real: Luminaris is in the sweep and must NOT be converted --
its go again belongs to other cards.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card_effects.dsl.loader import conditional_keywords, load_all_cards
from tests.conftest import card_json_files

load_all_cards()

JSON_ROOT = ROOT / "engine" / "card_effects" / "json"
_COND = re.compile(r"\b(if|whenever|while)\b[^.]{0,120}?\bgo again\b", re.I)

#: Cards already converted, which must STAY converted.
FIXED = ["aggressive_pounce_red", "aggressive_pounce_blue",
         "aggressive_pounce_yellow", "scar_for_a_scar_red", "grow_wings_blue",
         # Converted from their already-fixed siblings, which is the safest
         # kind of conversion available here: identical printed text, a shape
         # already verified, and no new judgement about what the card means.
         "grow_wings_red", "blow_for_a_blow_red",
         # Copied wholesale from a sibling with IDENTICAL printed text that was
         # already converted. 29 backlog cards have a sibling outside the
         # backlog, but only these three had both identical text AND a sibling
         # using the verified shape -- the rest are outside it for unrelated
         # reasons, and copying to them would have been guesswork.
         "grow_wings_yellow", "promise_of_plenty_blue", "scar_for_a_scar_blue",
         # These six had the RIGHT CONDITIONS already authored and only the
         # wrong ability shape, so a TRIGGERED grant left the printed keyword
         # in place. insult_to_injury is the cautionary one: three printings of
         # identical text had three different implementations, and the blue
         # printing also lacked the ATTACK_TARGET_IS_HERO gate and spelled the
         # keyword "go again" with a space, which an exact GO_AGAIN match skips.
         "insult_to_injury_red", "insult_to_injury_blue",
         "insult_to_injury_yellow", "frontline_scout_red",
         "frontline_scout_yellow", "fervent_forerunner_yellow",
         # The condition is a CONTINUOUS STATE ("if the defending hero has a
         # soul card", "if you've played a Lightning card this turn"), so the
         # once-vs-continuously reading cannot disagree and the conversion
         # needs no judgement about timing. Two of them -- photon_rush_red and
         # runerager_swarm_blue -- were ACTIVATE abilities with no cost, so the
         # gate was not merely mis-shaped but UNREACHABLE.
         "soul_cleaver_blue", "soul_cleaver_yellow",
         "scour_the_battlescape_blue", "photon_rush_red",
         "runerager_swarm_blue", "soup_up_red",
         # Combo ("if X was the last attack this combat chain"), Lightning Bond
         # ("if a Lightning card was pitched to play this") and one that reads
         # its own live power. All settled or continuously readable, so the
         # once-vs-continuously reading cannot disagree -- and for Chain of
         # Brutality continuous is the CORRECT reading, since a pump after
         # declaration has to count.
         "rising_knee_thrust_blue", "whelming_gustwave_red",
         "vengeance_never_rests_blue", "rushing_river_blue",
         "arc_bending_red", "chain_of_brutality_red",
         # "if it is Draconic" (a state another effect puts the card in) and
         # "if the discarded card has 6+ {p}". The latter needed an engine fix
         # first: DISCARDED_CARD_POWER_GTE read the discarded card off the
         # EVENT, which for an additional cost is the play event and has no
         # power, so the clause could never fire under ANY ability shape.
         "art_of_the_dragon_blood_red", "breakneck_battery_red",
         # These six do NOT use the static shape and must not: their condition
         # is a timed event ("if this HITS", "if you DO", "when this attacks,
         # if ..."), so a static would read it at the wrong moment. They keep
         # the trigger and DECLARE the keyword conditional instead -- see
         # CardDef.conditional_keywords for why the inference cannot just be
         # widened to cover them.
         "overload_yellow", "wild_ride_yellow", "second_strike_red",
         "second_strike_blue", "path_of_same_ends_red", "stellar_glide_blue",
         "last_ditch_effort_blue", "arc_ramp_red", "light_the_way_red",
         # RE-AUTHORED, not reshaped. Each was implemented against something
         # its text does not say -- OPT where the card says "discard an ally",
         # CHAIN_HIT_COUNT where it says "if X is 2 or more", a clash trigger
         # where it says "Surge" -- so the gate could not fire while the
         # printed keyword paid out anyway. See
         # tests/test_reauthored_gated_go_again.py.
         "man_overboard_yellow", "sonata_galaxia_red",
         "aether_quickening_yellow",
         # Unblocked by building the BANISH_FROM_HAND cost type. Both banish
         # from HAND as an additional cost and had been authored against the
         # wrong zone (DISCARD_RANDOM, BANISH_FROM_GRAVEYARD); Shadow of Ursur's
         # was also mandatory, so an OPTIONAL cost was blocking the play.
         "ram_raider_yellow", "shadow_of_ursur_blue"]

#: The count of cards still carrying an unconditional printed go again their
#: text gates. Lower it as they are fixed; it must never rise.
#:
#: THE TWO THAT ARE LEFT ARE BLOCKED ON A MECHANIC THAT DOES NOT EXIST:
#:
#:   ebbing_arcstride_red   "Whenever this FRAGMENTS, it gets go again."
#:   ebbing_arcstride_blue  Fragment is not implemented anywhere in the engine.
#:                          The clause hangs off ON_BECOME, which is emitted
#:                          only when a HERO transforms, so it can never fire.
#:                          Declaring the keyword conditional today would strip
#:                          the printed one with nothing to grant it back --
#:                          fail-OPEN becomes fail-CLOSED, which is quieter and
#:                          no more correct.
#:                          Unblocked by: the Fragment mechanic.
#:
#: Everything else is done. Four engine gaps were built along the way rather
#: than worked around: an explicit `conditional_keywords` declaration for cards
#: whose grant must stay a trigger, conditional keywords on the NON-ATTACK
#: resolution path, AMOUNT_GTE/GT for "if X is 2 or more", and the
#: BANISH_FROM_HAND cost.


UNFIXED_LIMIT = 2


def _prints_go_again_outright(text):
    """A line that IS the keyword is an unconditional printed go again, and a
    gated sentence elsewhere on the card is about something else. Channel the
    Thunder Steppe prints go again AND grants it to action cards you play."""
    for line in text.splitlines():
        if line.replace("*", "").replace("-", "").strip().lower() == "go again":
            return True
    return False


#: "Target <x> attack", which introduces ANOTHER attack for a later pronoun to
#: refer to. Deliberately requires the word "attack": "target hero" leaves no
#: attack for "it" to mean, and Aether Quickening -- whose go again really is
#: its own -- opens with exactly that.
_TARGET_ATTACK = re.compile(r"target[^.]{0,40}\battack\b", re.I)


def _go_again_is_about_itself(text, name):
    """Luminaris's distinction, applied to the printed text rather than to the
    JSON: "the attack gets go again" hands the keyword to ANOTHER card, and the
    DB lists it here only because it flattens the sentence. Only a card that
    gives ITSELF go again can have its printed keyword stripped.

    THE PRONOUN IS THE HARD PART. "It gets go again" is about the card itself on
    most cards and about someone else on Arakni, Redback -- "Target Assassin
    attack gets +3{p}. If it has stealth, it gets go again" -- where the
    referent was introduced a sentence earlier. Naming the card, or saying
    "this", settles it; a BARE PRONOUN has to be resolved by looking back.

    Scoped to the go again sentence and the one before it, because a card can
    do both. Tigrine Reflex gives ITSELF go again in one sentence and targets
    another attack in an unrelated Attack Reaction, so any rule that reads the
    whole card at once excuses it from a backlog it belongs in.
    """
    low = text.lower()
    named = ["this get", "this gain"]
    if name:
        named += [name.lower() + " get", name.lower() + " gain"]
    if any(sub in low for sub in named):
        return True
    if not any(sub in low for sub in ["it get", "it gain"]):
        return False
    # Bare pronoun: resolve it against the sentence that precedes the one
    # granting go again.
    sentences = [s for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]
    for i, sentence in enumerate(sentences):
        if "go again" not in sentence.lower():
            continue
        window = " ".join(sentences[max(0, i - 1):i + 1])
        if _TARGET_ATTACK.search(window):
            return False
    return True


def _unstripped():
    idx = json.load(open(ROOT / "card_data" / "slug_index.json",
                         encoding="utf-8"))["by_slug"]
    out = []
    for path in card_json_files(JSON_ROOT):
        rel = path.relative_to(JSON_ROOT)
        if (path.stem.endswith("_work_queue")
                or any(p.startswith(".") or p == "needs_review"
                       for p in rel.parts)):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        slug = raw.get("slug")
        entry = idx.get(slug) or {}
        kws = [str(k).lower() for k in (entry.get("keywords") or [])]
        text = entry.get("functionalText") or ""
        if "goagain" not in kws or not _COND.search(text):
            continue
        # Two shapes the sweep matches but that are not defects. Without them
        # the backlog number is inflated and, worse, it moves for reasons that
        # have nothing to do with cards being fixed.
        if _prints_go_again_outright(text):
            continue
        if not _go_again_is_about_itself(text, entry.get("name") or ""):
            continue
        if "goagain" not in conditional_keywords(slug):
            out.append(slug)
    return sorted(out)


def test_the_sweep_still_matches_cards():
    """A premise: if the phrasing or the keyword spelling moved, the ratchet
    below would pass by measuring nothing."""
    idx = json.load(open(ROOT / "card_data" / "slug_index.json",
                         encoding="utf-8"))["by_slug"]
    gated = [s for s, e in idx.items()
             if "goagain" in [str(k).lower() for k in (e.get("keywords") or [])]
             and _COND.search(e.get("functionalText") or "")]
    assert len(gated) > 30, len(gated)


@pytest.mark.parametrize("slug", FIXED)
def test_a_fixed_card_stays_fixed(slug):
    assert "goagain" in conditional_keywords(slug), (
        f"{slug} is back to an unconditional printed go again")


def test_the_unfixed_count_does_not_grow():
    left = _unstripped()
    assert len(left) <= UNFIXED_LIMIT, (
        f"{len(left)} cards print go again unconditionally while their text "
        f"gates it (limit {UNFIXED_LIMIT}):\n  " + "\n  ".join(left))


#: Matched by the sweep, but not defects. Kept by name because the whole value
#: of the ratchet is that its number moves only when a card is actually fixed.
NOT_DEFECTS = ["luminaris", "bonds_of_ancestry_red", "current_funnel_blue",
               "knife_through_butter_blue", "painful_passage_red",
               "quick_succession_red",
               # Luminaris's shape reached through a pronoun. "Target Assassin
               # attack gets +3{p}. If IT has stealth, IT gets go again" is
               # about the TARGET, but _go_again_is_about_itself only looks for
               # the words "it gets", so a sentence with a target reads exactly
               # like one about the card itself. A hero is never an attack, so
               # the SOURCE_IS_ATTACK form would be a lie about what it does.
               "arakni_redback"]


@pytest.mark.parametrize("slug", NOT_DEFECTS)
def test_a_false_positive_stays_out_of_the_backlog(slug):
    """These print go again outright, or grant it to another card. Counting
    them made the backlog look six cards worse than it is, and would have sent
    someone to 'fix' a correct card."""
    assert slug not in _unstripped(), (
        f"{slug} is being counted as a gated-go-again defect again")


def test_luminaris_is_not_converted():
    """It grants go again to OTHER cards. Its printed keyword is the database
    flattening that sentence, and the SOURCE_IS_ATTACK form would be a lie
    about what the card does."""
    assert "goagain" not in conditional_keywords("luminaris")
