"""Load JSON card files from card_effects/json/**/*.json → compiled CardDef objects."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from engine.card_effects.dsl.schema import (
    CardDef, AbilityDef, EffectDef, ConditionDef, CostDef
)

logger = logging.getLogger(__name__)

# Registry of compiled cards: slug → CardDef
_CARDS: dict[str, CardDef] = {}


def _json_dir() -> Path:
    return Path(__file__).parent.parent / "json"


def _compile_condition(raw: dict[str, Any]) -> ConditionDef:
    from engine.card_effects.dsl.condition_types import compile_condition
    ctype = raw.get("type", "none")
    params = {k: v for k, v in raw.items() if k != "type"}
    fn = compile_condition(ctype, params)
    return ConditionDef(condition_type=ctype, params=params, fn=fn)


def _compile_effect(raw: dict[str, Any]) -> EffectDef:
    from engine.card_effects.dsl.effect_types import compile_effect
    etype = raw.get("type", "").upper()
    params = {k: v for k, v in raw.items() if k != "type"}
    # Pull out effect-level conditions before passing params to compile_effect
    conditions_raw = params.pop("conditions", [])
    conditions = [_compile_condition(c) for c in conditions_raw]
    fn = compile_effect(etype, params)
    return EffectDef(effect_type=etype, params=params, conditions=conditions, fn=fn)


def _compile_cost(raw: dict[str, Any]) -> CostDef:
    from engine.card_effects.dsl.cost_types import compile_cost
    ctype = raw.get("type", "").upper()
    params = {k: v for k, v in raw.items() if k != "type"}
    check_fn, pay_fn = compile_cost(ctype, params)
    return CostDef(cost_type=ctype, params=params, check_fn=check_fn, pay_fn=pay_fn)


def _compile_ability(raw: dict[str, Any]) -> AbilityDef:
    atype = raw.get("ability_type", "TRIGGERED").upper()
    trigger = raw.get("trigger")
    is_optional = raw.get("optional", False)

    conditions = [_compile_condition(c) for c in raw.get("conditions", [])]
    effects = [_compile_effect(e) for e in raw.get("effects", [])]
    costs = [_compile_cost(c) for c in raw.get("costs", [])]
    additional_costs = [_compile_cost(c) for c in raw.get("additional_cost", [])]
    alternative_costs = [_compile_cost(c) for c in raw.get("alternative_cost", [])]

    return AbilityDef(
        ability_type=atype,
        trigger=trigger,
        effects=effects,
        conditions=conditions,
        costs=costs,
        additional_costs=additional_costs,
        alternative_costs=alternative_costs,
        is_optional=is_optional,
    )


def compile_card(raw: dict[str, Any]) -> CardDef:
    """Compile a raw JSON dict into a CardDef."""
    slug = raw.get("slug", "")
    abilities = [_compile_ability(a) for a in raw.get("abilities", [])]
    return CardDef(slug=slug, abilities=abilities)


def load_all_cards(json_dir: Path | None = None) -> int:
    """
    Walk json_dir (defaults to card_effects/json/) and compile all .json files.
    Returns the number of cards loaded.
    Idempotent — calling multiple times re-loads everything.
    """
    global _CARDS
    _CARDS.clear()

    root = json_dir or _json_dir()
    if not root.exists():
        logger.debug("DSL json dir not found: %s (no cards loaded)", root)
        return 0

    count = 0
    for path in sorted(root.rglob("*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            if not isinstance(raw, dict):
                logger.warning("Skipping %s: expected JSON object", path)
                continue
            card = compile_card(raw)
            if not card.slug:
                logger.warning("Skipping %s: missing 'slug'", path)
                continue
            _CARDS[card.slug] = card
            count += 1
        except Exception as exc:
            logger.warning("Failed to load %s: %s", path, exc)

    logger.debug("DSL loaded %d cards from %s", count, root)
    return count


def get_card(slug: str) -> CardDef | None:
    """Return compiled CardDef for slug, or None."""
    return _CARDS.get(slug)


def all_slugs() -> list[str]:
    """Return all loaded card slugs."""
    return list(_CARDS.keys())
