"""Compiled card definition dataclasses for the JSON DSL."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Any


@dataclass
class ConditionDef:
    condition_type: str
    params: dict[str, Any] = field(default_factory=dict)
    # Compiled at load time:
    fn: Callable | None = field(default=None, compare=False, repr=False)


@dataclass
class EffectDef:
    effect_type: str
    params: dict[str, Any] = field(default_factory=dict)
    conditions: list[ConditionDef] = field(default_factory=list)
    # Compiled at load time:
    fn: Callable | None = field(default=None, compare=False, repr=False)


@dataclass
class CostDef:
    cost_type: str
    params: dict[str, Any] = field(default_factory=dict)
    # Compiled at load time:
    check_fn: Callable | None = field(default=None, compare=False, repr=False)
    pay_fn: Callable | None = field(default=None, compare=False, repr=False)


@dataclass
class AbilityDef:
    ability_type: str  # PLAY|TRIGGERED|ACTIVATE|STATIC|ATTACK_REACTION|DEFENSE_REACTION
    trigger: str | None = None        # event name for TRIGGERED abilities
    effects: list[EffectDef] = field(default_factory=list)
    conditions: list[ConditionDef] = field(default_factory=list)
    costs: list[CostDef] = field(default_factory=list)
    additional_costs: list[CostDef] = field(default_factory=list)   # mandatory extra costs (block play if unpayable)
    alternative_costs: list[CostDef] = field(default_factory=list)  # pay INSTEAD of normal resource cost
    is_optional: bool = False


@dataclass
class CardDef:
    slug: str
    abilities: list[AbilityDef] = field(default_factory=list)
