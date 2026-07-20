"""Runtime interpreter: given a CardDef and event, execute matching abilities."""
from __future__ import annotations

from engine.card_effects.dsl import coverage as _coverage


def _track_effect(card, effect_type: str) -> None:
    """Record that an effect actually executed (no-op unless coverage is on)."""
    tracker = _coverage.active()
    if tracker is not None:
        tracker.record_effect(getattr(card, "slug", "?"), effect_type)


def _track_ability(card, ability) -> None:
    """Record that an ability actually fired (no-op unless coverage is on)."""
    tracker = _coverage.active()
    if tracker is not None:
        key = ability.trigger or ability.ability_type
        tracker.record_ability(getattr(card, "slug", "?"), key)


def run_ability(ability, card, event, state) -> None:
    """Execute a single AbilityDef, tracking *card* as the current effect source
    (so effects can gate on their origin, e.g. Ripple Away's 'action card effect')."""
    from engine.context import (push_effect_source, pop_effect_source,
                                push_refs, pop_refs)
    push_effect_source(card)
    # One reference scope per ability execution, so "look at a card … destroy
    # it" can share that card between effects without a bespoke function, and
    # a nested ability cannot clobber an outer one's names.
    push_refs()
    try:
        _run_ability(ability, card, event, state)
    finally:
        pop_refs()
        pop_effect_source()


def _run_ability(ability, card, event, state) -> None:
    """Execute a single AbilityDef. Checks additional costs, conditions, then runs effects."""
    # Check target filter (CR 1.8.5 — if no legal target exists, ability cannot resolve)
    for cond in getattr(ability, 'target_filter', []):
        fn = cond.fn
        if fn is not None and not fn(card, event, state):
            return

    # Check and pay additional costs (mandatory extra costs — abort if unpayable)
    for cost in getattr(ability, 'additional_costs', []):
        if cost.check_fn is not None and not cost.check_fn(card, event, state):
            return  # cost not satisfiable — abort (play.py should have blocked this)
        if cost.pay_fn is not None:
            cost.pay_fn(card, event, state)

    # Check ability-level conditions (all must pass — AND logic)
    for cond in ability.conditions:
        fn = cond.fn
        if fn is not None and not fn(card, event, state):
            return

    # Past every gate — this ability is genuinely resolving, not just matched.
    _track_ability(card, ability)

    # MODAL abilities ("Choose N"): the controller picks modes, each of which
    # is a compiled EffectDef. Non-modal abilities run their effects in order.
    if getattr(ability, 'modes', None):
        from engine.card_effects.ability_keywords import _ask_player, _controller_id
        n_choices = ability.choose or 1
        cid = _controller_id(card)
        remaining = list(range(len(ability.modes)))
        chosen = []
        for _ in range(min(n_choices, len(remaining))):
            labels = [str(i) for i in remaining]
            pick = _ask_player(state, cid, labels, context="Choose a mode")
            idx = (int(pick) if isinstance(pick, str) and pick.isdigit()
                   and int(pick) in remaining else remaining[0])
            chosen.append(idx)
            remaining.remove(idx)
        for idx in chosen:
            mode = ability.modes[idx]
            if mode.fn is not None:
                _track_effect(card, mode.effect_type)
                mode.fn(card, event, state)

    # Execute effects in order
    for eff in ability.effects:
        # Check effect-level conditions
        all_ok = True
        for cond in eff.conditions:
            fn = cond.fn
            if fn is not None and not fn(card, event, state):
                all_ok = False
                break
        if all_ok and eff.fn is not None:
            _track_effect(card, eff.effect_type)
            eff.fn(card, event, state)


def dispatch_event(card_def, event_type: str, card, event, state) -> None:
    """Fire all abilities in card_def that match event_type."""
    from engine.card_effects.dsl.trigger_types import (
        ABILITY_TYPE_TO_EVENT, TRIGGER_TO_EVENT, TRIGGER_EVENT_GATES)

    for ability in card_def.abilities:
        atype = ability.ability_type.upper()

        # Trigger-based: fire when ability.trigger resolves to event_type
        if atype in ("TRIGGERED", "STATIC_TRIGGERED", "DELAYED_TRIGGERED"):
            trigger_event = TRIGGER_TO_EVENT.get(ability.trigger or "",
                                                  ability.trigger or "")
            if trigger_event == event_type:
                # Sugar triggers (e.g. ON_GOLD_CREATED → ON_TOKEN_CREATED)
                # map to a broader engine event and gate on the payload.
                gate = TRIGGER_EVENT_GATES.get(ability.trigger or "")
                if gate is None or gate(event):
                    run_ability(ability, card, event, state)
            continue

        # WHILE_STATIC: a continuous static re-evaluated each attack-power
        # recalculation. It fires ONLY on RECALC_ATTACK_POWER so its
        # MODIFY_ATTACK lands in the stage-8 window (after the staged recalc)
        # and is not double-applied by unrelated dispatches. Conditions gate it.
        if atype == "WHILE_STATIC":
            if event_type == "RECALC_ATTACK_POWER":
                run_ability(ability, card, event, state)
            continue

        # PLAY / ACTION / MODAL / ATTACK_REACTION / DEFENSE_REACTION / ACTIVATE / INSTANT / STATIC:
        # matches if the mapped event equals event_type
        mapped = ABILITY_TYPE_TO_EVENT.get(atype)
        if mapped and mapped == event_type:
            run_ability(ability, card, event, state)
            continue
