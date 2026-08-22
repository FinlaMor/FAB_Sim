"""Mechanical hygiene invariants for every DSL card JSON.

These are the checks that catch the failure modes an AI card-author actually
produces: JSON that is well-formed and loads cleanly, but is filed in the
wrong set, registered under a slug nothing can look up, or authored with an
ability that has no effects. None of these raise at load time, so without
this file they reach the engine as silent no-ops.

Deliberately mechanical and fast — no game is played here. Semantic review
("does this JSON match the printed text?") is a separate, slower pass.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from engine.card_effects.dsl.loader import LOAD_ERRORS, load_all_cards

ROOT = Path(__file__).resolve().parent.parent
JSON_ROOT = ROOT / "engine" / "card_effects" / "json"
SLUG_INDEX = ROOT / "card_data" / "slug_index.json"

# Ability types that legitimately carry no "effects" list: COST_MODIFIER only
# adjusts a cost, and REPLACEMENT is wired in replacement_abilities.py with
# the JSON entry acting as a declaration.
# DEFEND_RESTRICTION carries conditions only: it gates whether the card may be
# declared as a defender at all, so it has nothing to resolve.
NO_EFFECTS_REQUIRED = {"COST_MODIFIER", "REPLACEMENT", "DEFEND_RESTRICTION"}

# Bold runs are keyword markup (**Ward 1**, **Go again**). A card whose entire
# functional text is keywords needs no DSL effects — the engine implements
# them. Anything left over after stripping them is real text that must be
# implemented.
_BOLD = re.compile(r"\*\*.*?\*\*")

# Cards whose printed text CANNOT be expressed with the current DSL, listed
# explicitly so the gap is tracked rather than papered over with an ability
# that does the wrong thing. Removing an entry is the definition of done for
# the primitive it names.
#
# It briefly held embrace_adversity and overcome_adversity ("this may only
# defend an attack if ..."), which are now implemented by the DEFEND_RESTRICTION
# ability type — enforced in actions.get_defendable_cards, the path
# engine._defend_step actually uses.
KNOWN_UNIMPLEMENTED: set[str] = {
    # "put the top card of your deck face up into your arsenal". Authored as
    # PUT_TOP_DECK_BOTTOM — a type that does not exist, and whose name says the
    # BOTTOM OF THE DECK, the opposite destination. It sat inside an
    # INJECT_TRIGGER, so it compiled lazily and raised ValueError at the end
    # phase of any turn this hit rather than failing at load. Removed rather
    # than left as a crash; there is no deck-to-arsenal effect to write it with
    # (PUT_ARSENAL_BOTTOM moves the other way). Definition of done: that
    # primitive exists and this entry goes.
    "heat_seeker_red",
    # "Damage that would be dealt by Malign can't be prevented." Needs the
    # damage pipeline to skip prevention for a NAMED SOURCE, which no primitive
    # expresses. It had been authored as a STATIC granting WARD with
    # ward_type "UNPREVENTABLE" — giving the card a prevention shield it does
    # not have while still not implementing the clause it does have. Removed
    # rather than left as the opposite of the text. Definition of done: a
    # source-scoped prevention bypass exists and this entry goes.
    "malign_yellow",
    # "If you've created a Seismic Surge this turn, this gets spellvoid 3."
    # Prevention keywords are registered ONCE from card.keywords
    # (EffectManager.register_prevention_effects, called at game start and on
    # token creation), so a CONDITIONAL prevention keyword has no path — nothing
    # re-registers when the condition becomes true. It had been authored as
    # GRANT_SUBTYPE "Spellvoid", and Spellvoid is a keyword, not a subtype.
    # Definition of done: conditional prevention re-registration exists.
    "volcanic_vice",
    # "The SECOND attack action card with 2 or less base {p} you play each turn
    # has +1{p} and 'Damage that would be dealt by this can't be prevented.'"
    # Two absent mechanics: an ordinal over qualifying cards PLAYED each turn,
    # and unpreventable damage scoped to a source (the same gap malign_yellow
    # is tracked for). It had been a STATIC granting +1{p} and a WARD the card
    # does not have.
    "tiger_stripe_shuko",
    # "Cards they own lose all colors until the end of their next turn."
    # Colour drives pitch value and every colour-gated condition in the corpus,
    # and there is no mechanism for suppressing it. It had been a flag nothing
    # reads plus a STATIC applying -1{d}, a defence penalty found nowhere in the
    # card's text.
    "blanch_yellow",
    # "Their first attack during their next turn costs an additional {r}."
    # There is no cost INCREASE path: the queued cost mods only reduce, and none
    # is scoped to an opponent's next attack. It had been a delayed
    # "pay 1 or take 1 damage" gated on a ref nothing stores.
    "hamstring_shot_red",
    # "When this defends, effects don't trigger when an attack hits this chain
    # link unless the attacking hero pays {r}" — a trigger-suppression
    # replacement gated on an optional payment by the OPPONENT. Also "can only
    # be played from arsenal", a play-legality restriction. It had been a
    # PAY_OR_DAMAGE dealing 1 damage, which is neither.
    "tripwire_trap_red",
}


def _card_files() -> list[Path]:
    """Every JSON the loader would treat as a card definition."""
    out = []
    for path in sorted(JSON_ROOT.rglob("*.json")):
        rel = path.relative_to(JSON_ROOT)
        if path.stem.endswith("_work_queue"):
            continue  # authoring TODO lists
        if any(part.startswith(".") for part in rel.parts):
            continue  # tooling state (.omc/), mirrors loader.load_all_cards
        out.append(path)
    return out


def _slug_index() -> dict:
    with open(SLUG_INDEX, encoding="utf-8") as f:
        raw = json.load(f)
    return raw.get("by_slug", raw)


def _set_codes(entry: dict) -> set[str]:
    """All set codes a card was printed in (HNT012 -> hnt). Reprints are common
    — over 2000 cards list more than one, so any of them is a valid folder."""
    return {
        "".join(ch for ch in ident if ch.isalpha()).lower()
        for ident in (entry.get("setIdentifiers") or [])
    }


CARD_FILES = _card_files()
INDEX = _slug_index()


def _ids(paths):
    return [str(p.relative_to(JSON_ROOT)).replace("\\", "/") for p in paths]


def test_all_card_json_loads_without_error():
    """A file in LOAD_ERRORS is an unimplemented card that looks implemented."""
    load_all_cards()
    assert LOAD_ERRORS == {}, f"card JSON failed to compile: {LOAD_ERRORS}"


@pytest.mark.parametrize("path", CARD_FILES, ids=_ids(CARD_FILES))
def test_slug_field_matches_filename(path: Path):
    """The loader registers cards under the JSON's own 'slug'. If it disagrees
    with the filename, lookups by the real slug silently miss the card."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw.get("slug") == path.stem, (
        f"{path.name}: 'slug' field is {raw.get('slug')!r} but filename stem is "
        f"{path.stem!r} — the card would be registered under an unreachable slug"
    )


@pytest.mark.parametrize("path", CARD_FILES, ids=_ids(CARD_FILES))
def test_slug_exists_in_card_index(path: Path):
    """Tokens are engine-created and have no printing; every other card must
    resolve in slug_index.json or it can never be drawn."""
    if path.parent.name == "tokens":
        pytest.skip("tokens have no printed card entry")
    slug = json.loads(path.read_text(encoding="utf-8")).get("slug")
    assert slug in INDEX, (
        f"{path.name}: slug {slug!r} is not in slug_index.json — check for "
        f"hyphens vs underscores, or a misspelled slug"
    )


@pytest.mark.parametrize("path", CARD_FILES, ids=_ids(CARD_FILES))
def test_card_is_filed_under_a_set_it_was_printed_in(path: Path):
    """Set folder must match the card's actual printing, not its class.

    This is the guardrail for the recurring failure where an author infers the
    set from the card's class (a Brute card is not automatically Outsiders).
    """
    folder = path.parent.name
    if folder == "tokens":
        pytest.skip("tokens are not a printed set")
    slug = json.loads(path.read_text(encoding="utf-8")).get("slug")
    entry = INDEX.get(slug)
    if entry is None:
        pytest.skip("slug not in index — covered by test_slug_exists_in_card_index")
    codes = _set_codes(entry)
    assert folder in codes, (
        f"{slug} is filed in {folder}/ but was printed in {sorted(codes)}. "
        f"Pick the set folder from the card's setIdentifiers, never its class."
    )


@pytest.mark.parametrize("path", CARD_FILES, ids=_ids(CARD_FILES))
def test_card_with_functional_text_implements_something(path: Path):
    """A card with non-keyword rules text must author at least one ability."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    slug = raw.get("slug")
    entry = INDEX.get(slug)
    if entry is None:
        pytest.skip("no printed entry (token or unindexed slug)")
    # A card-level `cost` is a play-time additional cost: it is compiled to
    # play_cost and both checked and paid by engine/play.py, so a card whose only
    # implementable clause is that cost (Scrap, CR 8.3.32) HAS implemented
    # something. Counting abilities alone reported such a card as untouched.
    if raw.get("abilities") or raw.get("setup") or raw.get("cost"):
        return
    if slug in KNOWN_UNIMPLEMENTED:
        pytest.xfail(f"{slug}: no DSL primitive for this text yet (see KNOWN_UNIMPLEMENTED)")
    prose = _BOLD.sub("", entry.get("functionalText") or "").strip(" \n\t-—,.")
    assert not prose, (
        f"{slug} has no abilities and no setup, but its text is not purely "
        f"keywords — unimplemented remainder: {prose!r}"
    )


@pytest.mark.parametrize("path", CARD_FILES, ids=_ids(CARD_FILES))
def test_replacement_abilities_resolve_to_a_handler(path: Path):
    """A REPLACEMENT ability carries no effects — its behavior lives in
    replacement_abilities.py, looked up by name. A typo'd or unregistered name
    would otherwise be a card that declares an ability and never runs it, and
    the empty-effects check deliberately exempts these."""
    from engine.card_effects.replacement_abilities import REPLACEMENT_ABILITIES

    raw = json.loads(path.read_text(encoding="utf-8"))
    for i, ability in enumerate(raw.get("abilities") or []):
        if (ability.get("ability_type") or "").upper() != "REPLACEMENT":
            continue
        name = ability.get("replacement")
        assert name, f"{raw.get('slug')} ability[{i}]: REPLACEMENT has no 'replacement' name"
        assert name in REPLACEMENT_ABILITIES, (
            f"{raw.get('slug')} ability[{i}]: replacement {name!r} is not registered "
            f"in REPLACEMENT_ABILITIES — the ability would never fire"
        )


@pytest.mark.parametrize("path", CARD_FILES, ids=_ids(CARD_FILES))
def test_every_ability_declares_a_type(path: Path):
    """A missing ability_type is silently defaulted to TRIGGERED by the loader.

    A TRIGGERED ability with no matching trigger never fires, so a PLAY ability
    that loses its ability_type (e.g. an edit that drops the key) becomes a dead
    no-op that still loads cleanly and passes every other check.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    for i, ability in enumerate(raw.get("abilities") or []):
        assert ability.get("ability_type"), (
            f"{raw.get('slug')} ability[{i}] has no 'ability_type' — the loader "
            f"would default it to TRIGGERED and it would never fire"
        )


@pytest.mark.parametrize("path", CARD_FILES, ids=_ids(CARD_FILES))
def test_every_ability_has_effects(path: Path):
    """An ability with an empty effects list compiles fine and does nothing."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    slug = raw.get("slug")
    for i, ability in enumerate(raw.get("abilities") or []):
        atype = (ability.get("ability_type") or "").upper()
        if atype in NO_EFFECTS_REQUIRED:
            continue
        assert ability.get("effects") or ability.get("modes") or ability.get("options"), (
            f"{slug} ability[{i}] ({atype or 'no ability_type'}) has no effects, "
            f"modes, or options — it will resolve as a no-op"
        )
