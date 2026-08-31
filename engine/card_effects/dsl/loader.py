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

# JSON files that failed to compile in the last load_all_cards() pass:
# file stem → "path: error". These slugs count as unimplemented.
LOAD_ERRORS: dict[str, str] = {}

# Slugs defined by more than one JSON file: slug → [paths]. Two files claiming
# one slug used to mean the last one walked silently won, so which definition
# the engine ran came down to filesystem order — and the loser could be the
# correct one. A duplicated slug is an ambiguous definition, so it is treated
# as NO definition (see load_all_cards) rather than an arbitrary pick.
DUPLICATE_SLUGS: dict[str, list[str]] = {}

# True once load_all_cards() has run; get_card() lazy-loads on first lookup.
_LOADED = False

class MissingCardImplementation(NotImplementedError):
    """Raised when a card in play has no DSL definition.

    Every card the engine touches must have a JSON definition under
    engine/card_effects/json/ (a card with no abilities still needs a stub
    with "abilities": []). This error names exactly which JSON to author.
    """

    def __init__(self, slugs):
        self.slugs = sorted(set(slugs)) if not isinstance(slugs, str) else [slugs]
        lines = []
        for s in self.slugs:
            if s in LOAD_ERRORS:
                lines.append(f"{s}  [JSON failed to load: {LOAD_ERRORS[s]}]")
            else:
                lines.append(s)
        listing = "\n  ".join(lines)
        super().__init__(
            f"No DSL implementation for {len(self.slugs)} card(s). "
            f"Author JSON under engine/card_effects/json/:\n  {listing}"
        )


def require_card(slug: str) -> "CardDef":
    """Return the DSL definition for *slug*, or raise MissingCardImplementation."""
    cd = get_card(slug)
    if cd is None:
        raise MissingCardImplementation(slug)
    return cd


def validate_slugs(slugs) -> None:
    """Raise MissingCardImplementation listing every slug with no DSL definition."""
    missing = [s for s in slugs if s and get_card(s) is None]
    if missing:
        raise MissingCardImplementation(missing)


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
    costs = [_compile_cost(c) for c in raw.get("cost", [])]
    additional_costs = [_compile_cost(c) for c in raw.get("additional_cost", [])]
    alternative_costs = [_compile_cost(c) for c in raw.get("alternative_cost", [])]

    target_raw = raw.get("target", {})
    target_filter = [_compile_condition(c) for c in target_raw.get("filter", [])]

    choose = raw.get("choose", 0)
    choose_max = raw.get("choose_max", 0)
    modes = [_compile_effect(m) for m in raw.get("modes", [])]

    # Ability-level extras not captured by structured fields (e.g. a REPLACEMENT
    # ability's "replacement" kind). Keep raw scalars for engine-side lookup.
    _structured = {"ability_type", "trigger", "optional", "conditions", "effects",
                   "cost", "additional_cost", "alternative_cost", "target",
                   "choose", "choose_max", "modes"}
    ab_params = {k: v for k, v in raw.items()
                 if k not in _structured and not k.startswith("_")}

    return AbilityDef(
        ability_type=atype,
        trigger=trigger,
        effects=effects,
        conditions=conditions,
        costs=costs,
        additional_costs=additional_costs,
        alternative_costs=alternative_costs,
        is_optional=is_optional,
        target_filter=target_filter,
        choose=choose,
        choose_max=choose_max,
        modes=modes,
        params=ab_params,
    )


def compile_card(raw: dict[str, Any]) -> CardDef:
    """Compile a raw JSON dict into a CardDef."""
    slug = raw.get("slug", "")
    abilities = [_compile_ability(a) for a in raw.get("abilities", [])]
    play_cost = None
    raw_cost = raw.get("cost")
    if isinstance(raw_cost, dict):
        play_cost = _compile_cost(raw_cost)
    setup = raw.get("setup", {}) or {}
    activation_cost = raw.get("activation_cost")
    per_turn = raw.get("per_turn")
    cost_modifiers = []
    for cm in raw.get("cost_modifiers", []) or []:
        cond_raw = cm.get("condition")
        cond = _compile_condition(cond_raw) if isinstance(cond_raw, dict) else None
        cost_modifiers.append({"cond": cond, "delta": int(cm.get("delta", 0))})
    declared = raw.get("conditional_keywords") or []
    if isinstance(declared, str):
        declared = [declared]
    return CardDef(slug=slug, abilities=abilities, play_cost=play_cost, setup=setup,
                   activation_cost=activation_cost, per_turn=per_turn,
                   cost_modifiers=cost_modifiers,
                   conditional_keywords=list(declared))


def load_all_cards(json_dir: Path | None = None) -> int:
    """
    Walk json_dir (defaults to card_effects/json/) and compile all .json files.
    Returns the number of cards loaded.
    Idempotent — calling multiple times re-loads everything.
    """
    global _CARDS, _LOADED
    _LOADED = True
    _CARDS.clear()
    # Derived from _CARDS, so it must not outlive a reload.
    _CONDITIONAL_KEYWORDS.clear()
    LOAD_ERRORS.clear()
    DUPLICATE_SLUGS.clear()
    seen_paths: dict[str, str] = {}

    root = json_dir or _json_dir()
    if not root.exists():
        logger.debug("DSL json dir not found: %s (no cards loaded)", root)
        return 0

    count = 0
    for path in sorted(root.rglob("*.json")):
        if path.stem.endswith("_work_queue"):
            continue  # authoring TODO lists, not card definitions
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue  # hidden dirs (e.g. tooling state) are not card definitions
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            if not isinstance(raw, dict):
                raise ValueError("expected a JSON object")
            card = compile_card(raw)
            if not card.slug:
                raise ValueError("missing 'slug'")
            if card.slug in seen_paths:
                # Ambiguous: drop the slug entirely so require_card/validate_slugs
                # reject it at game start naming both files, instead of running a
                # definition picked by walk order.
                DUPLICATE_SLUGS.setdefault(card.slug, [seen_paths[card.slug]]).append(str(path))
                LOAD_ERRORS[card.slug] = (
                    f"slug {card.slug!r} is defined by multiple files "
                    f"({', '.join(DUPLICATE_SLUGS[card.slug])}) — delete or rename all "
                    f"but the correct one"
                )
                if _CARDS.pop(card.slug, None) is not None:
                    count -= 1
                logger.warning("Duplicate slug %s: %s", card.slug,
                               DUPLICATE_SLUGS[card.slug])
                continue
            seen_paths[card.slug] = str(path)
            _CARDS[card.slug] = card
            count += 1
        except Exception as exc:
            # A broken definition means the card is unimplemented: it will not
            # be in _CARDS, so require_card/validate_slugs reject it at game
            # start with the error recorded here.
            LOAD_ERRORS[path.stem] = f"{path}: {exc}"
            logger.warning("Failed to load %s: %s", path, exc)

    logger.debug("DSL loaded %d cards from %s (%d failed)", count, root, len(LOAD_ERRORS))
    return count


def get_card(slug: str) -> CardDef | None:
    """Return compiled CardDef for slug, or None. Lazy-loads on first lookup."""
    if not _LOADED:
        load_all_cards()
    return _CARDS.get(slug)


def all_slugs() -> list[str]:
    """Return all loaded card slugs."""
    return list(_CARDS.keys())


# Keyword names a card can GAIN through an ability, in the spellings the DSL and
# the card DB each use. Compared after normalising to alphanumerics-lowercase,
# so "GO_AGAIN", "Go Again" and "GoAgain" are one name.
_GRANTABLE_KEYWORDS = frozenset({
    "go_again", "dominate", "overpower", "intimidate", "piercing", "stealth",
    "blade_break", "battleworn", "temper", "reprise", "phantasm",
})

_CONDITIONAL_KEYWORDS: dict[str, frozenset[str]] = {}


def _kw_key(name) -> str:
    return "".join(ch for ch in str(name or "") if ch.isalnum()).lower()


def conditional_keywords(slug: str) -> frozenset[str]:
    """Keywords this card grants ITSELF only while a condition holds.

    The card DB's `keywords` list does not distinguish a keyword a card always
    has from one it only gains under a condition: Out Muscle ships as
    "GoAgain" and Over the Top as "Overpower", though both texts gate them.
    The engine treats every printed keyword as unconditional, so the gate could
    never take the keyword away — 18 cards had a free permanent buff, which is
    worse than the dead static it came from, because a dead ability at least
    does nothing.

    A card's own JSON is the finer-grained source: an ability that GRANTS the
    keyword under conditions is saying the keyword is conditional, so the
    printed one must not also be applied. Only abilities gated on
    SOURCE_IS_ATTACK count — that is what distinguishes "THIS gains go again"
    from "your Illusionist attacks get go again" (Luminaris), where the printed
    keyword belongs to some other card and the weapon's own listing is just the
    DB flattening the sentence.

    Returned normalised (alphanumeric, lowercase) for spelling-insensitive
    comparison against card.keywords.
    """
    cached = _CONDITIONAL_KEYWORDS.get(slug)
    if cached is not None:
        return cached
    found: set[str] = set()
    card_def = get_card(slug)
    if card_def is not None:
        # An EXPLICIT declaration, for cards whose grant has to stay a trigger.
        # The inference below only recognises a SOURCE_IS_ATTACK-gated static,
        # and widening it to triggered abilities is not possible: for Intimidate
        # and Overpower the same DSL name is both a keyword a card GAINS and an
        # effect a card PERFORMS, so "when this attacks a hero, intimidate them"
        # would lose the printed keyword it really has. Cards whose condition is
        # a timed event ("if this HITS", "if you DO") therefore keep the trigger
        # -- which is the correct timing -- and declare the keyword conditional
        # here rather than contorting into a shape that reads the condition at
        # the wrong moment.
        for name in (card_def.conditional_keywords or []):
            if _kw_key(str(name)) in {_kw_key(k) for k in _GRANTABLE_KEYWORDS}:
                found.add(_kw_key(str(name)))
        for ability in card_def.abilities:
            if not ability.conditions:
                continue
            if not any((c.condition_type or "").upper() == "SOURCE_IS_ATTACK"
                       for c in ability.conditions):
                continue
            for eff in ability.effects:
                etype = (eff.effect_type or "").upper()
                name = eff.params.get("keyword") if etype == "GAIN" else etype
                if _kw_key(name) in {_kw_key(k) for k in _GRANTABLE_KEYWORDS}:
                    found.add(_kw_key(name))
    result = frozenset(found)
    _CONDITIONAL_KEYWORDS[slug] = result
    return result
