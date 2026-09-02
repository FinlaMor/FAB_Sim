"""A granted trigger that said "hits a hero" fired on hitting an ally.

Five cards grant a trigger whose printed text names a hero:

    blacktek_whisperers  "When this hits a hero, it gains go again"
    scar_tissue_red      "When this hits a hero, mark them"
    arakni_black_widow   "... they banish a card from their hand"
    arakni_funnel_web    "... banish a card in their arsenal"
    pummel_red           "... they discard a card"

None of them gated the injected trigger on ATTACK_TARGET_IS_HERO, so every one
fired on any hit. This is the same defect swept out of 28 abilities earlier,
but one level down: that sweep looked at ability-level triggers and could not
see a trigger created by an effect.

THE TRAP THAT MADE IT UNFIXABLE IN PLACE. INJECT_TRIGGER accepts two forms:

    {"trigger": "ON_HIT", "conditions": [...], "effects": [...]}   string
    {"trigger": {"trigger_type": "ON_HIT", "conditions": [...],    dict
                 "effects": [...]}}

In the STRING form the conditions never reach the trigger. The loader pops
`conditions` at effect level to build the effect's own gate (loader.py:87), so
the handler receives only `trigger` and `effects` -- confirmed by compiling one
and reading back its params. The condition is then evaluated when the trigger
is INJECTED rather than when it FIRES, which is a different question and, for
"when this hits", the wrong one.

The two kinds of condition are genuinely different and both are needed:
Black Widow's "IF IT HAS STEALTH, it gets <trigger>" gates whether the trigger
is GRANTED, and belongs at effect level where it already was; "when this hits A
HERO" gates whether it FIRES, and has to be inside the dict.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import engine.engine as E
from engine.card import Card, CardDB
from engine.card_effects.dsl.loader import load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state
from tests.conftest import _card_json, card_json_files

load_all_cards()
DB = CardDB()

GRANTERS = ["blacktek_whisperers", "scar_tissue_red", "arakni_black_widow",
            "arakni_funnel_web", "pummel_red"]
JSON_ROOT = ROOT / "engine" / "card_effects" / "json"


def _nodes(slug, wanted="INJECT_TRIGGER"):
    raw = json.loads(_card_json(JSON_ROOT, f"{slug}.json").read_text(
        encoding="utf-8"))
    found = []

    def walk(n):
        if isinstance(n, dict):
            if n.get("type") == wanted:
                found.append(n)
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(raw.get("abilities"))
    return found


# --- the mechanism ----------------------------------------------------------

def test_the_string_form_cannot_carry_trigger_conditions():
    """The trap, pinned. If this ever stops being true the dict form is no
    longer required and this whole file's premise changes."""
    from engine.card_effects.dsl.loader import _compile_effect

    eff = _compile_effect({
        "type": "INJECT_TRIGGER", "trigger": "ON_HIT",
        "conditions": [{"type": "ATTACK_TARGET_IS_HERO"}],
        "effects": [{"type": "GO_AGAIN"}]})

    assert [c.condition_type for c in eff.conditions] == ["ATTACK_TARGET_IS_HERO"], (
        "the loader no longer pops effect-level conditions")
    assert "conditions" not in eff.params, (
        "the handler now receives conditions; the string form may be safe again")


def test_the_dict_form_does_carry_them():
    from engine.card_effects.dsl.loader import _compile_effect

    eff = _compile_effect({
        "type": "INJECT_TRIGGER",
        "trigger": {"trigger_type": "ON_HIT",
                    "conditions": [{"type": "ATTACK_TARGET_IS_HERO"}],
                    "effects": [{"type": "GO_AGAIN"}]}})

    inner = eff.params["trigger"]
    assert [c["type"] for c in inner["conditions"]] == ["ATTACK_TARGET_IS_HERO"]


# --- the cards --------------------------------------------------------------

@pytest.mark.parametrize("slug", GRANTERS)
def test_the_granted_trigger_is_gated_on_hitting_a_hero(slug):
    for node in _nodes(slug):
        spec = node.get("trigger")
        assert isinstance(spec, dict), (
            f"{slug} uses the string form, where conditions never reach the "
            "trigger")
        conds = [c.get("type") for c in (spec.get("conditions") or [])]
        assert "ATTACK_TARGET_IS_HERO" in conds, conds


@pytest.mark.parametrize("slug", ["arakni_black_widow", "arakni_funnel_web",
                                  "pummel_red"])
def test_the_grant_time_condition_stays_at_effect_level(slug):
    """"If it has stealth, it GETS <trigger>" is about whether the trigger is
    granted at all. Moving it inside would ask it at the wrong moment."""
    for node in _nodes(slug):
        outer = [c.get("type") for c in (node.get("conditions") or [])]
        assert outer, (
            f"{slug} lost its grant-time gate when the inner one was added")


@pytest.mark.parametrize("slug", GRANTERS)
def test_the_card_really_says_hits_a_hero(slug):
    """The premise. If the printed text changes this should fail loudly rather
    than keep asserting a gate the card no longer wants."""
    idx = json.load(open(ROOT / "card_data" / "slug_index.json",
                         encoding="utf-8"))["by_slug"]
    text = (idx[slug].get("functionalText") or "").lower()
    assert "hits a hero" in text, text


# --- the guard --------------------------------------------------------------

def test_no_injected_trigger_hides_conditions_in_the_string_form():
    """Derived, so it keeps probing as cards are added: conditions written on a
    string-form INJECT_TRIGGER are consumed by the loader and never reach the
    trigger, which is silent."""
    bad = []
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

        def walk(n):
            if isinstance(n, dict):
                if (n.get("type") == "INJECT_TRIGGER"
                        and not isinstance(n.get("trigger"), dict)
                        and n.get("conditions")):
                    # Effect-level conditions are legitimate as a GRANT gate.
                    # What is not is an inner condition written here expecting
                    # to reach the trigger -- indistinguishable from the JSON,
                    # so the rule is simply: if you need a fire-time condition,
                    # use the dict form.
                    bad.append(f"{raw.get('slug')}: {[c.get('type') for c in n['conditions']]}")
                for v in n.values():
                    walk(v)
            elif isinstance(n, list):
                for v in n:
                    walk(v)

        walk(raw.get("abilities"))
    # Known and deliberate: these gate whether the trigger is GRANTED.
    # These three gate whether the trigger is GRANTED, which is what an
    # effect-level condition means and what their text says ("if it has
    # stealth, it GETS ...").
    #
    # Three more used to be listed here and were not deliberate at all:
    # rage_baiters and light_the_way_red wrote a FIRE-TIME condition in the
    # string form (both now use the dict form), and starfield_carapace's whole
    # ability was an INJECT_TRIGGER hung on an unrelated trigger, now declared
    # unimplemented. An allowlist that mixes "deliberate" with "not yet looked
    # at" stops being a statement about anything.
    allowed = {"arakni_black_widow", "arakni_funnel_web", "pummel_red"}
    unexpected = [b for b in bad if b.split(":")[0] not in allowed]
    assert unexpected == [], unexpected
