"""Runtime interpreter: given a CardDef and event, execute matching abilities."""
from __future__ import annotations


def run_ability(ability, card, event, state) -> None:
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
            eff.fn(card, event, state)


def dispatch_event(card_def, event_type: str, card, event, state) -> None:
    """Fire all abilities in card_def that match event_type."""
    from engine.card_effects.dsl.trigger_types import ABILITY_TYPE_TO_EVENT, TRIGGER_TO_EVENT

    for ability in card_def.abilities:
        atype = ability.ability_type.upper()

        # Trigger-based: fire when ability.trigger resolves to event_type
        if atype in ("TRIGGERED", "STATIC_TRIGGERED", "DELAYED_TRIGGERED"):
            trigger_event = TRIGGER_TO_EVENT.get(ability.trigger or "",
                                                  ability.trigger or "")
            if trigger_event == event_type:
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
