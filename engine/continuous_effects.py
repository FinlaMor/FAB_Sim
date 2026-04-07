"""Continuous effect staging system (CR 6.3) and cost modifier pipeline (CR 5.1.6a)."""
from __future__ import annotations
import itertools
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Optional

_global_timestamp = itertools.count()


def next_timestamp() -> int:
    return next(_global_timestamp)


@dataclass
class ContinuousEffect:
    """A single continuous effect in the CR 6.3 staging system.

    stage: 1-8
    substage:
        stages 1-6: 0=independent, 1=dependent
        stages 7-8: 1=add/remove property, 2=set, 3=multiply, 4=divide,
                    5=add, 6=subtract, 7=dependent
    timestamp: from next_timestamp(), determines order within same substage
    prop: which property ('power', 'keywords', 'types', 'defense', 'cost', etc.)
    source_slug: slug of the card/ability that generated this
    effect_id: unique string id for removal
    apply_fn: fn(current_value, state, card) -> new_value
              For prop='cost': fn(current_value, state, card, action) -> new_value
    dependency_fn: optional fn(state, card) -> int — returns highest stage
                  this effect depends on (0 if independent).  If > self.stage,
                  effect is moved to that stage at substage 7.
    persistent: if False, removed after first application
    condition_fn: optional fn(state, card) -> bool — skip if False
                  For prop='cost': fn(card, action, state) -> bool  (CR 5.1.6a)
    owner_player_id: for cost effects, which player's pipeline this belongs to
    """

    stage: int
    substage: int
    timestamp: int
    prop: str
    source_slug: str
    apply_fn: Callable  # (current_value, state, card[, action]) -> new_value
    effect_id: str = ""
    dependency_fn: Optional[Callable] = None
    persistent: bool = True
    condition_fn: Optional[Callable] = None
    owner_player_id: Optional[int] = None


class ContinuousEffectManager:
    """Applies all active continuous effects in CR 6.3 stage order.

    Used for:
    - attack power recalculation (stages 7-8, prop='power')
    - keyword recalculation (stage 6, prop='keywords')
    - defense value (stages 7-8, prop='defense')
    - type modification (stage 4, prop='types')

    Usage::

        manager = ContinuousEffectManager()
        manager.add(effect)
        power = manager.recalculate(state, card, 'power', card.base_power or 0)
    """

    def __init__(self) -> None:
        self._effects: list[ContinuousEffect] = []

    def add(self, effect: ContinuousEffect) -> None:
        self._effects.append(effect)

    def remove_by_id(self, effect_id: str) -> None:
        self._effects = [e for e in self._effects if e.effect_id != effect_id]

    def remove_by_source(self, source_slug: str) -> None:
        self._effects = [e for e in self._effects if e.source_slug != source_slug]

    def remove_by_prop(self, prop: str) -> None:
        self._effects = [e for e in self._effects if e.prop != prop]

    def clear_transient(self) -> None:
        """Remove all non-persistent effects (called at end of turn)."""
        self._effects = [e for e in self._effects if e.persistent]

    def clear_cost_modifiers(self, player_id: int) -> None:
        """Remove all cost modifier effects owned by player_id (called at end of turn)."""
        self._effects = [
            e for e in self._effects
            if not (e.prop == 'cost' and e.owner_player_id == player_id)
        ]

    def remove_cost_modifier_by_id(self, effect_id: str) -> None:
        """Remove a specific cost modifier by effect_id."""
        self._effects = [
            e for e in self._effects
            if not (e.prop == 'cost' and e.effect_id == effect_id)
        ]

    def recalculate(self, state: Any, card: Any, prop: str, base_value: Any,
                    action: Any = None) -> Any:
        """Apply all active effects on *prop* for *card*, in stage order.

        For prop='cost', pass action= so that condition_fn(card, action, state)
        and apply_fn(value, state, card, action) work correctly (CR 5.1.6a).

        Returns the final computed value.
        """
        is_cost = (prop == 'cost')

        if is_cost:
            # Cost conditions take (card, action, state) — filter with action context.
            relevant = [
                e for e in self._effects
                if e.prop == prop
                and (e.condition_fn is None or e.condition_fn(card, action, state))
            ]
        else:
            relevant = [
                e for e in self._effects
                if e.prop == prop
                and (e.condition_fn is None or e.condition_fn(state, card))
            ]

        if not relevant:
            return base_value

        # CR 6.3.2a: check dependency — re-stage dependent effects
        staged: list[ContinuousEffect] = []
        for effect in relevant:
            if effect.dependency_fn is not None:
                dep_stage = effect.dependency_fn(state, card)
                if dep_stage > effect.stage:
                    staged.append(replace(effect, stage=dep_stage, substage=7))
                    continue
            staged.append(effect)

        # Sort: stage → substage → timestamp
        staged.sort(key=lambda e: (e.stage, e.substage, e.timestamp))

        value = base_value
        consumed_ids: list[str] = []
        for effect in staged:
            if is_cost:
                value = effect.apply_fn(value, state, card, action)
            else:
                value = effect.apply_fn(value, state, card)
            if not effect.persistent and effect.effect_id:
                consumed_ids.append(effect.effect_id)

        for eid in consumed_ids:
            self.remove_by_id(eid)

        return value

    # ------------------------------------------------------------------
    # Cost modifier helpers (CR 5.1.6a)
    # ------------------------------------------------------------------
    # Substage mapping for cost pipeline:
    #   set      → substage 2  (CR 5.1.6a step 2)
    #   increase → substage 5  (CR 5.1.6a step 3)
    #   decrease → substage 6  (CR 5.1.6a step 4)
    # All at stage 7, consistent with numeric property modifications.

    _COST_KIND_SUBSTAGE = {"set": 2, "increase": 5, "decrease": 6}

    def add_cost_modifier(
        self,
        kind: str,                        # "set" | "increase" | "decrease"
        amount: Optional[int],            # None → treat as 0 for set
        owner_player_id: int,
        effect_id: str = "",
        condition_fn: Optional[Callable] = None,  # (card, action, state) -> bool
        consume_on_apply: bool = False,
        source_slug: str = "",
    ) -> None:
        """Register a cost modifier effect (CR 5.1.6a) in the staging system.

        kind: 'set' applies at substage 2, 'increase' at substage 5,
              'decrease' at substage 6, all in timestamp order within each
              substage — matching CR 5.1.6a exactly.
        consume_on_apply: if True, the modifier is removed after its first
                          successful application (one-shot effects).
        """
        substage = self._COST_KIND_SUBSTAGE.get(kind)
        if substage is None:
            raise ValueError(f"Unknown cost modifier kind: {kind!r}")

        _amount = amount if amount is not None else 0

        if kind == "set":
            def apply_fn(value, state, card, action, _a=_amount):
                return _a
        elif kind == "increase":
            def apply_fn(value, state, card, action, _a=_amount):
                return value + _a
        else:  # decrease
            def apply_fn(value, state, card, action, _a=_amount):
                return value - _a

        self._effects.append(ContinuousEffect(
            stage=7,
            substage=substage,
            timestamp=next_timestamp(),
            prop='cost',
            source_slug=source_slug,
            apply_fn=apply_fn,
            effect_id=effect_id,
            persistent=not consume_on_apply,
            condition_fn=condition_fn,
            owner_player_id=owner_player_id,
        ))
