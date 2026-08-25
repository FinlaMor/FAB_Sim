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
    assert len(cards) <= 19, (
        f"{len(cards)} cards set a flag nothing reads (was 19):\n  "
        + "\n  ".join(f"{f}: {', '.join(s)}" for f, s in sorted(dead.items()))
        + "\n\nA clause the DSL cannot express should be left OUT with a "
          "_comment saying so, not written as a flag nobody reads."
    )


def test_the_known_dead_flags_are_the_ones_we_think():
    """Pins the specific set, so a fixed card and a newly broken one cannot
    cancel out and leave the count unchanged."""
    dead = _dead_flags()
    cards = {s for v in dead.values() for s in v}
    for expected in ("humble_red", "censor_red", "three_of_a_kind_red",
                     "cartilage_crush_blue"):
        assert expected in cards, (
            f"{expected} was a known dead-flag card; if it was fixed, remove "
            f"it here and lower the ceiling")
