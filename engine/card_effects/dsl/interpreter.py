"""Runtime interpreter: given a CardDef and event, execute matching abilities."""
from __future__ import annotations


def run_ability(ability, card, event, state) -> None:
    """Execute a single AbilityDef. Checks ability-level conditions, then runs effects."""
    # Check ability-level conditions (all must pass — AND logic)
    for cond in ability.conditions:
        fn = cond.fn
        if fn is not None and not fn(card, event, state):
            return

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

        # TRIGGERED: matches if ability.trigger resolves to event_type
        if atype == "TRIGGERED":
            trigger_event = TRIGGER_TO_EVENT.get(ability.trigger or "",
                                                  ability.trigger or "")
            if trigger_event == event_type:
                run_ability(ability, card, event, state)
            continue

        # PLAY / ATTACK_REACTION / DEFENSE_REACTION / ACTIVATE:
        # matches if the mapped event equals event_type
        mapped = ABILITY_TYPE_TO_EVENT.get(atype)
        if mapped and mapped == event_type:
            run_ability(ability, card, event, state)
            continue

        # STATIC: not dispatched here — handled by the static ability system
