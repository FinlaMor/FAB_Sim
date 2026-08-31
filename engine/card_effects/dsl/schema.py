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
    ability_type: str
    trigger: str | None = None
    effects: list[EffectDef] = field(default_factory=list)
    conditions: list[ConditionDef] = field(default_factory=list)
    costs: list[CostDef] = field(default_factory=list)
    additional_costs: list[CostDef] = field(default_factory=list)
    alternative_costs: list[CostDef] = field(default_factory=list)
    is_optional: bool = False
    target_filter: list[ConditionDef] = field(default_factory=list)  # CR 1.8.5 targeting
    choose: int = 0                                                   # MODAL: minimum modes to select
    choose_max: int = 0                                               # MODAL: maximum modes ("choose 1 or both" → choose 1, choose_max 2); 0 = exactly `choose`
    modes: list[EffectDef] = field(default_factory=list)             # MODAL: available modes
    params: dict[str, Any] = field(default_factory=dict)             # ability-level extras (e.g. REPLACEMENT kind)


@dataclass
class CardDef:
    slug: str
    abilities: list[AbilityDef] = field(default_factory=list)
    play_cost: CostDef | None = None  # additional cost paid when the card is played
    setup: dict[str, Any] = field(default_factory=dict)  # game-start config (e.g. weapon_zones)
    # Activation metadata — DSL-authoritative when set, replacing the loader's
    # printed-text heuristics for implemented cards (CR 1.7.3a / 4.4.3d).
    activation_cost: int | None = None  # resource cost to activate/attack ({r}); None = fall back to text
    per_turn: int | None = None         # activations allowed per turn; None = fall back to text (no limit)
    # Conditional resource-cost modifiers evaluated when the card is played
    # (CR 5.1.6, e.g. "if the defending hero is marked, this costs {r} less").
    # Each: {"cond": ConditionDef | None, "delta": int}. cond None = always.
    cost_modifiers: list = field(default_factory=list)
    # Printed keywords this card only has CONDITIONALLY, declared explicitly.
    # The card DB cannot express "conditional keyword" -- Out Muscle ships as
    # "GoAgain" though its text gates it -- and loader.conditional_keywords
    # normally INFERS the answer from a SOURCE_IS_ATTACK-gated static. That
    # inference cannot be widened to triggered abilities, because for keywords
    # like Intimidate the same DSL name is both a keyword a card GAINS and an
    # effect a card PERFORMS: "when this attacks a hero, intimidate them"
    # (Instill Fear) would have its real printed keyword taken away. So a card
    # whose grant must stay a trigger -- because its condition is a timed event
    # rather than a readable state -- says so here instead of being guessed at.
    conditional_keywords: list = field(default_factory=list)
