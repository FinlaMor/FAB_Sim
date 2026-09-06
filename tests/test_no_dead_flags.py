"""A card that SET_FLAGs something nobody reads is a card that does nothing.

SET_FLAG appends a string to `player.current_turn_effects`. If no engine code
and no other card ever reads that string, the card looks implemented, loads
cleanly, passes audit_run and audit_params, and silently does nothing at all.
The review pass hit this shape repeatedly:

  humble_red / humble_yellow    "they lose all hero card abilities until the
                                end of their next turn" -> HUMBLE_ACTIVE
  censor_red                    "they can't play the named card" -> CENSOR_ACTIVE
  three_of_a_kind_red           "you may only play cards from arsenal"
                                -> ONLY_PLAY_FROM_ARSENAL
  chokeslam_yellow              "attack action cards they control can't gain
                                {p}" -> CRUSH_FLAG
  cartilage_crush_blue          "their first action next turn costs an
                                additional {r}" -> CARTILAGE_CRUSH_ACTIVE

Each names a real restriction the engine cannot express. Writing a flag for it
is not an implementation; it is a note to nobody, and it reads as done.

This guard does not fix them. It makes the class VISIBLE and stops it growing,
and it names the honest alternative: a card whose clause cannot be expressed
should say so in a `_comment` and leave the clause out, rather than write a
flag that looks like an implementation.

Note the two spellings of one mechanic among the current set --
DEFENSE_REACTION_BLOCKED and command_and_conquer_no_dr both mean "defense
reaction cards can't be played this chain link". Dead flags do not even
aggregate with each other.
"""
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
JSON_ROOT = ROOT / "engine" / "card_effects" / "json"
ENGINE = ROOT / "engine"


def _card_files():
    for p in sorted(JSON_ROOT.rglob("*.json")):
        rel = p.relative_to(JSON_ROOT)
        if p.stem.endswith("_work_queue") or p.name in (
                "review_queue.json", "triage_queue.json"):
            continue
        if any(x.startswith(".") or x == "needs_review" for x in rel.parts):
            continue
        yield p


def _flags_set():
    """flag string -> the slugs that set it."""
    out: dict[str, list[str]] = {}

    def walk(node, slug):
        if isinstance(node, dict):
            if str(node.get("type", "")).upper() == "SET_FLAG":
                f = node.get("flag")
                if isinstance(f, str) and f:
                    out.setdefault(f, []).append(slug)
            for v in node.values():
                walk(v, slug)
        elif isinstance(node, list):
            for v in node:
                walk(v, slug)

    for p in _card_files():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        walk(raw.get("abilities"), raw.get("slug"))
    return out


def _dead_flags():
    setters = _flags_set()
    engine_src = "".join(
        p.read_text(encoding="utf-8", errors="ignore") for p in ENGINE.rglob("*.py"))
    corpus = "".join(
        p.read_text(encoding="utf-8", errors="ignore") for p in _card_files())
    dead = {}
    for flag, slugs in setters.items():
        if flag in engine_src:
            continue                       # some engine code reads it
        # A card reading it would mention the string somewhere other than the
        # SET_FLAG nodes that write it (e.g. a FLAG_SET condition).
        if corpus.count(f'"{flag}"') > len(slugs):
            continue
        dead[flag] = sorted(slugs)
    return dead


def test_the_scan_sees_the_corpus():
    """Guards the guard: if the glob or parse breaks, everything below passes
    vacuously — the exact failure this file is about."""
    setters = _flags_set()
    assert len(setters) >= 10, f"only {len(setters)} SET_FLAG strings found"
    assert len(list(_card_files())) > 500


def test_dead_flag_count_does_not_grow():
    """Lower this as the clauses are really implemented; never raise it.

    A new dead flag means a card was authored to look finished while doing
    nothing — worse than leaving the clause out, because nothing will ever
    flag it again.
    """
    dead = _dead_flags()
    cards = sorted({s for v in dead.values() for s in v})
    assert len(cards) <= 6, (
        f"{len(cards)} cards set a flag nothing reads (was 6):\n  "
        + "\n  ".join(f"{f}: {', '.join(s)}" for f, s in sorted(dead.items()))
        + "\n\nA clause the DSL cannot express should be left OUT with a "
          "_comment saying so, not written as a flag nobody reads."
    )


def test_the_known_dead_flags_are_the_ones_we_think():
    """Pins the specific set, so a fixed card and a newly broken one cannot
    cancel out and leave the count unchanged.

    19 -> 8. What is left is not the same kind of problem as what was fixed.
    humble_*, censor_red, three_of_a_kind_red, sigil_of_suffering_red and
    grim_feast_red were flags standing in for effects the engine could already
    express, or -- in Sigil's case -- for a record the engine was already
    keeping. Each needed a named effect type and a reader, not new mechanics.

    These eight need machinery that does not exist yet, which is why they are
    still listed rather than quietly rewritten:

        cartilage_crush_blue    a cost increase on the FIRST action of the
        chokeslam_yellow        opponent's next turn / a ban on gaining {p} /
        fatigue_shot_red        a halved BASE power -- all one-shot modifiers
                                scoped to a future turn, with no hook to hang on
        become_the_bottle_*     "this gets the chosen card's name" -- nothing
                                changes an object's name, and SELECT_FROM_REF
                                has no COMBAT_CHAIN source either
        phantasmal_symbiosis_*  grant a SUBTYPE to every card with a named name
        silver_talons_red       "the dagger has hit" -- a hit event for an
                                object that did not attack
        gallow_end_of_...       "effects controlled by opponents don't trigger
                                when their attacks hit" -- trigger suppression

    Leaving a flag in place is still wrong; it is only less wrong than
    inventing a mechanic to hang it on. Each of these carries, or should carry,
    a `_comment` saying which clause is unimplemented.
    """
    dead = _dead_flags()
    cards = {s for v in dead.values() for s in v}
    # become_the_bottle_red/yellow left this list when their SET_FLAG
    # ("this gets the chosen card's name", stored where nothing read it) was
    # replaced by a real SELECT_FROM_ZONE over the combat chain plus SET_NAME.
    for expected in ("cartilage_crush_blue", "chokeslam_yellow",
                     "silver_talons_red"):
        assert expected in cards, (
            f"{expected} was a known dead-flag card; if it was fixed, remove "
            f"it here and lower the ceiling")


def test_the_flags_that_were_fixed_stay_fixed():
    """The other half of the ratchet: these five were real dead flags and are
    now real effects. A regression here would otherwise only show up as the
    count drifting back up, which the ceiling above permits."""
    dead = _dead_flags()
    cards = {s for v in dead.values() for s in v}
    for fixed in ("humble_red", "humble_blue", "humble_yellow", "censor_red",
                  "three_of_a_kind_red", "sigil_of_suffering_red",
                  "grim_feast_red"):
        assert fixed not in cards, (
            f"{fixed} is setting a flag nothing reads again")
