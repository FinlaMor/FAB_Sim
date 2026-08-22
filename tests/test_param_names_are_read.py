"""A parameter the compiler never reads fails silently.

audit_run.py checks a node's TYPE is real. It cannot see this:

    {"type": "WEAPON_SUBTYPE_IN", "subtypes": ["sword"]}

WEAPON_SUBTYPE_IN read `values`. Three of the five cards using it authored
`subtypes` — the natural name given what the condition is called — so they
filtered on an empty list, matched nothing, and could never fire. To a type-name
audit those three cards look perfect.

The corpus had 242 cards with at least one such key. They fell into families,
and the fix for a family is to read every spelling in the compiler rather than
to edit dozens of cards: `class`/`classes`, `subtype`/`subtypes`,
`token`/`token_type`, `zone`/`from_zones`, `counter`/`counter_type`,
`duration`/`scope`. This pins those families shut.

Three of them were worse than a dropped filter:
  * CARD_IN_ZONE dropping a type filter did not disable the condition, it made
    it TOO PERMISSIVE — "an instant in your graveyard" became "any card".
  * MODIFY_DEFENSE_VALUE ignored `mod`, so "subtract" ADDED.
  * SET_FLAG ignored `value: false`, so "clear this" SET it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import audit_params as A

INDEX = A.build_index()


def test_the_detector_sees_the_compilers():
    # Guards the guard. If the AST walk goes stale every check below passes
    # vacuously, which is how a broken audit certifies a broken corpus.
    assert len(INDEX) > 150, f"only {len(INDEX)} types extracted from the compilers"


@pytest.mark.parametrize("type_name,key", [
    # singular/plural — an unread list key leaves the filter EMPTY, so the
    # condition matches nothing and the ability can never fire
    ("ATTACK_CLASS_IN", "class"),
    ("ATTACK_SUBTYPE_IN", "subtype"),
    ("WEAPON_SUBTYPE_IN", "subtypes"),
    ("ATTACK_TYPE_IN", "values"),
    ("CARD_IN_ZONE", "keyword"),
    # unread filter on CARD_IN_ZONE makes the condition too PERMISSIVE
    ("CARD_IN_ZONE", "card_type"),
    ("CARD_IN_ZONE", "subtype"),
    ("CARD_IN_ZONE", "subtypes"),
    ("CARD_IN_ZONE", "player"),
    # a token named under the wrong key is the empty slug: destroys/creates nothing
    ("DESTROY_TOKEN", "token_type"),
    ("CREATE_TOKEN", "token_slug"),
    ("CREATE_TOKEN", "zone"),
    ("CONTROLS_TOKEN_TYPE", "subtype"),
    # wrong zone is worse than no zone: PUT_CARDS_BOTTOM defaulted to
    # hand+arsenal, so a card meant to bottom its revealed cards emptied the hand
    ("PUT_CARDS_BOTTOM", "zone"),
    ("MOVE_REF", "to"),
    # these two INVERT the effect rather than weaken it
    ("MODIFY_DEFENSE_VALUE", "mod"),
    ("SET_FLAG", "value"),
    ("SET_FLAG", "duration"),
    # restriction silently doing nothing: fired on both players' turns
    ("DURING_TURN", "player"),
    # cost could never be paid, so the ability was unusable
    ("REMOVE_COUNTERS", "counter"),
    # fell back to pitch 1 (red) whatever colour the card named
    ("REF_PITCH_IS", "color"),
])
def test_known_defect_family_is_read(type_name, key):
    known = INDEX.get(type_name)
    assert known is not None, f"{type_name} is not a registered type any more"
    assert key in known, (
        f"{type_name} no longer reads {key!r}. Cards author that spelling, and a "
        "key the compiler ignores is dropped in silence — the ability fails "
        "exactly as if its type were invented, but no type-name audit can see it."
    )


def test_not_with_a_bare_flag_is_not_always_false():
    # {"type":"NOT","flag":"x"} compiled its inner condition to None, and
    # `not (None is None or ...)` is False UNCONDITIONALLY — so six once-per-turn
    # gates on the Arakni demi-heroes could never fire.
    from engine.card_effects.dsl.condition_types import compile_condition
    fn = compile_condition("NOT", {"flag": "some_flag"})
    assert fn is not None

    class _P:
        current_turn_effects: list = []

    class _S:
        players = {1: _P(), 2: _P()}

    class _C:
        owner = controller = 1
        slug = "x"

    assert fn(_C(), None, _S()) is True, \
        "NOT over an unset flag must be True; it was False for every input"


def test_inert_rules_name_a_real_type_and_key():
    # Every INERT entry is a CLAIM that honouring a key would change nothing.
    # A wrong one hides a broken card forever, which is exactly how ENGINE_FLAGS
    # certified "die_rolled_six". At minimum the type must still exist — an
    # entry for a type that has been renamed silently protects nothing and
    # would go unnoticed.
    for (type_name, key), (values, why) in A.INERT.items():
        assert type_name in INDEX, (
            f"INERT names {type_name}, which is no longer a registered type — "
            "the rule now suppresses nothing and hides its own staleness")
        assert values, f"INERT[{type_name}.{key}] allows no values"
        assert why, f"INERT[{type_name}.{key}] gives no reason"


def test_inert_only_covers_values_that_match_the_default():
    # The severity split is only trustworthy if "inert" means the value the code
    # already uses. A non-default value on the same key must still be ACTIVE —
    # "player": "OPPONENT" is a real defect even though "player": "SELF" is not.
    assert A.severity("CHOOSE", "player", "SELF") == "inert"
    assert A.severity("CHOOSE", "player", "OPPONENT") == "active"
    assert A.severity("SEARCH_DECK", "shuffle", True) == "inert"
    assert A.severity("SEARCH_DECK", "shuffle", False) == "active"
    # A key with no rule is never inert.
    assert A.severity("CHOOSE", "totally_made_up", "SELF") == "active"


def test_regression_count_does_not_grow():
    # The remaining unread keys are one-off inventions on individual cards, not
    # families — each needs its own judgement, so this pins the number rather
    # than claiming zero. Lower it when cards are fixed; a rise means a new
    # family appeared and should be closed in the compiler instead.
    findings = 0
    for path in A.card_files():
        import json
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        hits: list[str] = []
        A.walk(raw.get("abilities", []),
               lambda n: hits.extend(A.audit_node(n, INDEX)))
        if hits:
            findings += 1
    # ACTIVE findings only: a key whose value is the default anyway is redundant,
    # not broken, and counting those invites churning correct cards.
    #
    # This ceiling went 77 -> 163 without a single card getting worse. The audit
    # kept ONE flat STRUCTURAL_KEYS list of "keys the loader consumes", and
    # "target" was in it — but at effect level the loader pops only
    # "conditions". So every effect naming a target was exempt from the one
    # check that would have caught it, and the number this pins was measuring
    # the detector's blind spot as much as the corpus.
    #
    # Raising a threshold to make a test pass is normally how a regression gets
    # laundered into the baseline. It is the right move ONLY here, where the
    # rise is the detector seeing more, and the evidence is that BANISH's
    # unread target was milling its own controller's deck on 17 cards. Do not
    # raise it again without that kind of evidence: a rise from a corpus change
    # is a new family, and belongs in the compiler where it closes every card
    # at once.
    #
    # 163 -> 153: the counter effects (PUT_COUNTER / REMOVE_COUNTER /
    # REMOVE_COUNTERS) now read their target, closing twelve cards that were
    # putting their counters on the source card.
    # 153 -> 148: LOOK_AT now reads its target through the same parser BANISH
    # uses, closing twelve more -- five of which were reading the OPPONENT's
    # deck where the card says "your deck".
    # 148 -> 142: DESTROY_TOKEN was standing in for six different destroy
    # effects; the eight cards now use DESTROY_PERMANENT, DESTROY_MATCHING or
    # DESTROY_DEFENDING as their text requires.
    assert findings <= 142, (
        f"{findings} cards have an ACTIVE parameter the compiler never reads (was 142). "
        "A new one usually means a new spelling of an existing family — fix it "
        "in the compiler, where it closes every card at once."
    )
