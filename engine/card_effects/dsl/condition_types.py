"""Compile JSON condition objects into (card, event, state) -> bool callables."""
from __future__ import annotations
from typing import Any, Callable


def compile_condition(ctype: str, params: dict[str, Any]) -> Callable | None:
    """Return a (card, event, state)->bool callable, or None (always-True)."""

    if ctype in ("none", "NONE", ""):
        return None

    # ── combat presence ────────────────────────────────────────────────────
    if ctype == "IN_COMBAT":
        return lambda c, e, s: s.combat is not None

    if ctype == "ATTACK_IS_WEAPON":
        return lambda c, e, s: s.combat is not None and getattr(s.combat, 'from_weapon', False)

    if ctype == "ATTACK_IS_NOT_WEAPON":
        return lambda c, e, s: s.combat is not None and not getattr(s.combat, 'from_weapon', False)

    if ctype == "WEAPON_SUBTYPE_IN":
        values = [v.upper() for v in params.get("values", [])]
        def _wsi(c, e, s, _vals=values):
            if not s.combat:
                return False
            w = getattr(s.combat, 'weapon', None) or getattr(s.combat, 'attack_card', None)
            subs = [x.upper() for x in (getattr(w, 'subtypes', None) or [])]
            return any(v in subs for v in _vals)
        return _wsi

    if ctype == "ATTACK_COST_GTE":
        amount = params.get("amount", 0)
        def _acg(c, e, s, _amt=amount):
            if not s.combat or not s.combat.attack_card:
                return False
            cost = (getattr(s.combat.attack_card, 'cost', None)
                    or getattr(s.combat.attack_card, 'raw_cost', None) or 0)
            return cost >= _amt
        return _acg

    if ctype == "DEFENDER_USED_HAND_CARD":
        return lambda c, e, s: (s.combat is not None
                                 and getattr(s.combat, 'defender_used_hand_card', False))

    # ── keyword checks ─────────────────────────────────────────────────────
    if ctype == "REPRISE":
        def _reprise(c, e, s):
            from engine.card_effects.ability_keywords import reprise_check
            return reprise_check(s)
        return _reprise

    if ctype == "CRUSH":
        def _crush(c, e, s):
            from engine.card_effects.ability_keywords import crush_check
            return crush_check(e, s)
        return _crush

    if ctype == "COMBO":
        # Accept either "names" or "combo_names" key for JSON flexibility
        combo_names = params.get("names", params.get("combo_names", []))
        def _combo(c, e, s, _cn=combo_names):
            from engine.card_effects.ability_keywords import combo_check
            return combo_check(s, _cn)
        return _combo

    if ctype == "COMBO_CONTAINS":
        # True if the last chain-link's base slug contains the given substring.
        # "base slug" strips the color suffix (e.g. "whelming_gustwave_red" → "whelming_gustwave").
        substring = params.get("substring", "")
        def _combo_contains(c, e, s, _sub=substring):
            if not s.chain_links:
                return False
            import re
            last_slug = s.chain_links[-1].attack_slug
            last_base = re.sub(r'_(red|yellow|blue)$', '', last_slug)
            return _sub in last_base or _sub in last_slug
        return _combo_contains

    if ctype == "SURGE":
        amount = params.get("amount", 1)
        def _surge(c, e, s, _amt=amount):
            from engine.card_effects.ability_keywords import surge_check
            return surge_check(e, _amt)
        return _surge

    if ctype == "RUPTURE":
        def _rupture(c, e, s):
            from engine.card_effects.ability_keywords import rupture_check
            return rupture_check(s)
        return _rupture

    if ctype == "GO_FISH":
        def _gf(c, e, s):
            from engine.card_effects.ability_keywords import effect_go_fish
            return effect_go_fish(s, e)
        return _gf

    # ── player state ───────────────────────────────────────────────────────
    if ctype == "HEALTH_GT_OPP":
        def _hgo(c, e, s):
            from engine.card_effects.ability_keywords import _controller_id
            pid = _controller_id(c)
            return s.players[pid].life > s.players[3 - pid].life
        return _hgo

    if ctype == "HEALTH_LT_OPP":
        def _hlo(c, e, s):
            from engine.card_effects.ability_keywords import _controller_id
            pid = _controller_id(c)
            return s.players[pid].life < s.players[3 - pid].life
        return _hlo

    if ctype == "DECK_EMPTY":
        def _de(c, e, s):
            from engine.card_effects.ability_keywords import _controller_id
            pid = _controller_id(c)
            return len(s.players[pid].deck.cards) == 0
        return _de

    if ctype == "PLAYED_FROM_ARSENAL":
        # card.prev_zone is 'arsenal' when played from arsenal (set by Zone tracking)
        return lambda c, e, s: getattr(c, 'prev_zone', '').lower() == 'arsenal'

    if ctype == "IS_ACTIVE_PLAYER":
        def _iap(c, e, s):
            from engine.card_effects.ability_keywords import _controller_id
            return _controller_id(c) == s.active_player
        return _iap

    # ── card / zone ────────────────────────────────────────────────────────
    if ctype == "HAS_KEYWORD":
        kw = params.get("keyword", "")
        return lambda c, e, s, _kw=kw: bool(getattr(c, 'keywords', None)) and _kw in c.keywords

    if ctype == "CARD_IN_ZONE":
        zone = params.get("zone", "")
        return lambda c, e, s, _z=zone: c.zone == _z

    if ctype == "COUNTER_GTE":
        ctype2 = params.get("counter_type", params.get("type", ""))
        min_val = params.get("min", params.get("amount", 1))
        def _cge(c, e, s, _ct=ctype2, _min=min_val):
            from engine.card_effects.ability_keywords import _controller_id
            key = (c.slug, c.zone, _ct)
            return s.players[_controller_id(c)].counters.get(key, 0) >= _min
        return _cge

    if ctype == "FLAG_SET":
        flag = params.get("flag", "")
        def _fs(c, e, s, _f=flag):
            from engine.card_effects.ability_keywords import _controller_id
            return _f in s.players[_controller_id(c)].current_turn_effects
        return _fs

    # ── boolean combinators ────────────────────────────────────────────────
    if ctype == "OR":
        sub_conds = [compile_condition(sc.get("type", "none"), sc)
                     for sc in params.get("any", [])]
        def _or(c, e, s, _subs=sub_conds):
            return any((fn is None or fn(c, e, s)) for fn in _subs)
        return _or

    if ctype == "AND":
        sub_conds = [compile_condition(sc.get("type", "none"), sc)
                     for sc in params.get("all", [])]
        def _and(c, e, s, _subs=sub_conds):
            return all((fn is None or fn(c, e, s)) for fn in _subs)
        return _and

    if ctype == "NOT":
        inner = compile_condition(params.get("inner_type", params.get("type", "none")), params)
        def _not(c, e, s, _fn=inner):
            return not (_fn is None or _fn(c, e, s))
        return _not

    # Unknown — always True (safe fallback)
    return None
