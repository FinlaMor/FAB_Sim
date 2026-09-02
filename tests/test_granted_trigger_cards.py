"""Two cards that hand a trigger to an attack, and the target Rage Baiters lost.

Both wrote their injected trigger in the STRING form with a top-level
`conditions`. The loader pops that key and compiles it as an EFFECT-level gate,
so the condition is asked when the granting ability RESOLVES and the injected
trigger then fires unconditionally. For a condition about the hit -- "when this
hits a hero" -- that is the wrong moment, and nothing about the JSON says so.

    rage_baiters       "Target attack with stealth gets 'When this hits a hero,
                       mark them.'"
    light_the_way_red  "When this hits, if a yellow card was charged this way,
                       this gets go again."

light_the_way_red got the right ANSWER from the wrong question: the charge is
paid before its PLAY ability resolves, so a grant-time reading of
CHARGED_THIS_WAY sees the truth. It was right by coincidence, and the same shape
on rage_baiters was not. Since go again is stripped from that card by
conditional_keywords, a trigger that fires when it should not is the difference
between the printed card and a free extra action.

RAGE BAITERS ALSO HAD NO TARGET RESTRICTION. "TARGET ATTACK WITH STEALTH" is a
legality rule, and the ability carried no `target` block at all, so the reaction
could be played on any attack whatsoever. That is not a subtle mis-gating: it is
the whole condition on which the card may be used, absent.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card_effects.dsl.loader import get_card, load_all_cards
from tests.conftest import _make_combat, _make_state, owned_card

load_all_cards()
IDX = json.loads((ROOT / "card_data" / "slug_index.json")
                 .read_text(encoding="utf-8"))["by_slug"]


def _reaction(slug="rage_baiters"):
    return get_card(slug).abilities[0]


# --- rage_baiters: the target restriction ------------------------------------

def _stealth_state(keywords):
    st = _make_state()
    st.combat = _make_combat(attacker_id=1)
    st.combat.keywords = list(keywords)
    return st


def test_rage_baiters_may_only_target_an_attack_with_stealth():
    ab = _reaction()
    assert ab.target_filter, (
        "'target attack WITH STEALTH' has no target filter, so the reaction "
        "can be played on any attack")
    card = owned_card(1, "rage_baiters")

    with_stealth = _stealth_state(["Stealth"])
    assert all(c.fn(card, None, with_stealth) for c in ab.target_filter)

    without = _stealth_state(["Go Again"])
    assert not all(c.fn(card, None, without) for c in ab.target_filter), (
        "the reaction is legal against an attack with no stealth")


def test_the_target_filter_is_what_the_printed_text_says():
    """The premise. If the text changes, fail here rather than keep enforcing a
    restriction the card no longer has."""
    assert "stealth" in (IDX["rage_baiters"].get("functionalText") or "").lower()


# --- both: the condition is on the trigger, not on the grant -----------------

@pytest.mark.parametrize("slug,expected", [
    ("rage_baiters", "ATTACK_TARGET_IS_HERO"),
    ("light_the_way_red", "CHARGED_THIS_WAY"),
])
def test_the_condition_reaches_the_trigger(slug, expected):
    """Compiled, not read off the file: the file could carry the dict form and
    still lose the conditions if the loader changed."""
    cd = get_card(slug)
    nodes = []

    def walk(ability):
        for e in ability.effects:
            if e.effect_type == "INJECT_TRIGGER":
                nodes.append(e)

    for ab in cd.abilities:
        walk(ab)
    assert nodes, f"{slug} has no INJECT_TRIGGER"
    for e in nodes:
        spec = e.params.get("trigger")
        assert isinstance(spec, dict), (
            f"{slug} is back on the string form, where the loader eats the "
            "conditions before compile_effect sees them")
        inner = [c.get("type") for c in (spec.get("conditions") or [])]
        assert expected in inner, (
            f"{slug}: the trigger fires with conditions {inner}")
        assert not e.conditions, (
            f"{slug} still has an effect-level gate; the condition is about "
            "the HIT, so asking it at grant time is asking it too early")


def test_light_the_way_still_declares_its_keyword_conditional():
    """The whole reason its trigger has to be right: the printed go again is
    stripped, so the injected trigger is the only thing that can give it back."""
    from engine.card_effects.dsl.loader import conditional_keywords, _kw_key
    assert _kw_key("go again") in {_kw_key(k) for k in
                                   conditional_keywords("light_the_way_red")}
