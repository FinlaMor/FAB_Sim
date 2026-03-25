"""Unit tests for template builder functions in triggers.py.

Verify all template builders return valid TriggerDef with correct event_type
and that effect_fn is callable.
"""

from __future__ import annotations

import pytest

from engine.card_effects.triggers import (
    TriggerDef,
    # hit templates
    on_hit_draw,
    on_hit_damage,
    on_hit_arcane,
    on_hit_discard,
    on_hit_gain_life,
    on_hit_create_token,
    on_hit_intimidate,
    on_hit_banish_top,
    on_hit_lose_life,
    on_hit_go_again,
    # attack templates
    on_attack_power_bonus,
    on_attack_draw,
    on_attack_create_token,
    on_attack_discard,
    on_attack_go_again_conditional,
    # play templates
    on_play_draw,
    on_play_deal_arcane,
    on_play_deal_damage,
    on_play_create_token,
    on_play_power_bonus,
    on_play_defense_bonus,
    on_play_gain_resources,
    on_play_gain_action_point,
    on_play_intimidate,
    on_play_opt,
    on_play_banish_top,
    on_play_shuffle,
    on_play_amp,
    on_play_discard,
    on_play_gain_life,
    on_play_mark,
    # defend templates
    on_defend_defense_bonus,
    on_defend_draw,
    on_defend_create_token,
    on_defend_gain_resources,
    # keyword-condition templates
    crush_trigger,
    reprise_trigger,
    surge_trigger,
    combo_trigger,
    rupture_trigger,
)


# ---------------------------------------------------------------------------
# Parametrized: (builder_call, expected_event_type)
# ---------------------------------------------------------------------------

_NOOP_EFFECT = lambda c, e, s: None

TEMPLATE_CASES = [
    # hit
    (on_hit_draw, (), {}, "hit"),
    (on_hit_draw, (2,), {}, "hit"),
    (on_hit_damage, (3,), {}, "hit"),
    (on_hit_damage, (3,), {"damage_type": "arcane"}, "hit"),
    (on_hit_arcane, (2,), {}, "hit"),
    (on_hit_discard, (), {}, "hit"),
    (on_hit_discard, (2,), {}, "hit"),
    (on_hit_gain_life, (1,), {}, "hit"),
    (on_hit_create_token, ("seismic_surge",), {}, "hit"),
    (on_hit_create_token, ("seismic_surge", 2), {}, "hit"),
    (on_hit_intimidate, (), {}, "hit"),
    (on_hit_banish_top, (), {}, "hit"),
    (on_hit_banish_top, (3,), {}, "hit"),
    (on_hit_lose_life, (1,), {}, "hit"),
    (on_hit_go_again, (), {}, "hit"),
    # attacking
    (on_attack_power_bonus, (2,), {}, "attacking"),
    (on_attack_draw, (), {}, "attacking"),
    (on_attack_draw, (2,), {}, "attacking"),
    (on_attack_create_token, ("seismic_surge",), {}, "attacking"),
    (on_attack_discard, (), {}, "attacking"),
    (on_attack_go_again_conditional, (_NOOP_EFFECT,), {}, "attacking"),
    # on_play
    (on_play_draw, (), {}, "on_play"),
    (on_play_draw, (3,), {}, "on_play"),
    (on_play_deal_arcane, (2,), {}, "on_play"),
    (on_play_deal_damage, (3,), {}, "on_play"),
    (on_play_create_token, ("seismic_surge",), {}, "on_play"),
    (on_play_power_bonus, (2,), {}, "on_play"),
    (on_play_defense_bonus, (1,), {}, "on_play"),
    (on_play_gain_resources, (2,), {}, "on_play"),
    (on_play_gain_action_point, (), {}, "on_play"),
    (on_play_intimidate, (), {}, "on_play"),
    (on_play_opt, (2,), {}, "on_play"),
    (on_play_banish_top, (), {}, "on_play"),
    (on_play_shuffle, (), {}, "on_play"),
    (on_play_amp, (1,), {}, "on_play"),
    (on_play_discard, (), {}, "on_play"),
    (on_play_gain_life, (2,), {}, "on_play"),
    (on_play_mark, (), {}, "on_play"),
    # defend
    (on_defend_defense_bonus, (1,), {}, "defend"),
    (on_defend_draw, (), {}, "defend"),
    (on_defend_create_token, ("seismic_surge",), {}, "defend"),
    (on_defend_gain_resources, (1,), {}, "defend"),
    # keyword-condition templates
    (crush_trigger, (_NOOP_EFFECT,), {}, "damage_dealt"),
    (reprise_trigger, (_NOOP_EFFECT,), {}, "on_play"),
    (surge_trigger, (3, _NOOP_EFFECT), {}, "damage_dealt"),
    (combo_trigger, (["Leg Tap"],  _NOOP_EFFECT), {}, "on_play"),
    (rupture_trigger, (_NOOP_EFFECT,), {}, "on_play"),
]


CASE_IDS = [
    f"{fn.__name__}({', '.join(repr(a) for a in args)})"
    for fn, args, kwargs, evt in TEMPLATE_CASES
]


@pytest.mark.parametrize("builder,args,kwargs,expected_event", TEMPLATE_CASES, ids=CASE_IDS)
def test_template_returns_valid_triggerdef(builder, args, kwargs, expected_event):
    """Each template builder should return a TriggerDef with correct event_type."""
    result = builder(*args, **kwargs)

    assert isinstance(result, TriggerDef), f"{builder.__name__} did not return TriggerDef"
    assert result.event_type == expected_event, (
        f"{builder.__name__} event_type={result.event_type!r}, expected {expected_event!r}"
    )
    assert callable(result.effect_fn), f"{builder.__name__} effect_fn is not callable"


@pytest.mark.parametrize("builder,args,kwargs,expected_event", TEMPLATE_CASES, ids=CASE_IDS)
def test_template_condition_fn_is_callable_or_none(builder, args, kwargs, expected_event):
    """condition_fn should be None or callable."""
    result = builder(*args, **kwargs)
    assert result.condition_fn is None or callable(result.condition_fn)


# ---------------------------------------------------------------------------
# Keyword-condition templates should set condition_fn
# ---------------------------------------------------------------------------

KEYWORD_CONDITION_BUILDERS = [
    (crush_trigger, (_NOOP_EFFECT,)),
    (reprise_trigger, (_NOOP_EFFECT,)),
    (surge_trigger, (3, _NOOP_EFFECT)),
    (combo_trigger, (["Leg Tap"], _NOOP_EFFECT)),
    (rupture_trigger, (_NOOP_EFFECT,)),
]


@pytest.mark.parametrize("builder,args", KEYWORD_CONDITION_BUILDERS,
                         ids=lambda x: x.__name__ if callable(x) else "")
def test_keyword_condition_templates_have_condition_fn(builder, args):
    """Keyword-condition templates must set a non-None condition_fn."""
    result = builder(*args)
    assert result.condition_fn is not None, f"{builder.__name__} should set condition_fn"
    assert callable(result.condition_fn)
