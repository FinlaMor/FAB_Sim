"""
loader.py — Convert DB rows into TriggerDef / CARD_TRIGGERS entries at startup.

The loader reads from the DB and builds TriggerDef objects that plug directly
into the existing trigger system. It does NOT replace triggers.py — it
augments it. Cards in the DB shadow the same-slug entries in triggers.py,
so you can migrate a card to the DB by adding its rows and removing from triggers.py.

Usage (in triggers.py or engine startup):
    from engine.card_effects.db.loader import load_db_triggers
    load_db_triggers(CARD_TRIGGERS)   # merges DB triggers into the existing dict
"""
from __future__ import annotations

import json
from typing import Callable

from engine.card_effects.db.db import get_db, init_db, params


# ---------------------------------------------------------------------------
# Generic effect executors — data-driven effects that need no bespoke Python
# ---------------------------------------------------------------------------

def _make_effect(effect_type: str, effect_params: dict,
                 custom_fn_ref: Callable | None) -> Callable:
    """Return a (card, event, state) -> None callable for the given effect row."""

    if effect_type == "custom" and custom_fn_ref is not None:
        return custom_fn_ref

    if effect_type == "gain_life":
        amt = effect_params.get("amount", 0)
        def _fn(card, event, state, _amt=amt):
            from engine.card_effects.ability_keywords import effect_gain_life, _controller_id
            effect_gain_life(state, _controller_id(card), _amt)
        return _fn

    if effect_type == "lose_life":
        amt = effect_params.get("amount", 0)
        def _fn(card, event, state, _amt=amt):
            from engine.card_effects.ability_keywords import effect_lose_life, _controller_id
            effect_lose_life(state, _controller_id(card), _amt)
        return _fn

    if effect_type == "deal_damage":
        amt = effect_params.get("amount", 0)
        tgt = effect_params.get("target", "opponent")  # 'opponent' | 'self'
        def _fn(card, event, state, _amt=amt, _tgt=tgt):
            from engine.card_effects.ability_keywords import effect_deal_damage, _controller_id
            cid = _controller_id(card)
            target_id = (3 - cid) if _tgt == "opponent" else cid
            effect_deal_damage(state, target_id, _amt, card)
        return _fn

    if effect_type == "deal_arcane":
        amt = effect_params.get("amount", 0)
        tgt = effect_params.get("target", "opponent")
        def _fn(card, event, state, _amt=amt, _tgt=tgt):
            from engine.card_effects.ability_keywords import effect_deal_arcane, _controller_id
            cid = _controller_id(card)
            target_id = (3 - cid) if _tgt == "opponent" else cid
            effect_deal_arcane(state, target_id, _amt, card)
        return _fn

    if effect_type == "draw":
        amt = effect_params.get("amount", 1)
        def _fn(card, event, state, _amt=amt):
            from engine.card_effects.ability_keywords import effect_draw, _controller_id
            effect_draw(state, _controller_id(card), _amt)
        return _fn

    if effect_type == "create_token":
        token = effect_params.get("token", "")
        count = effect_params.get("count", 1)
        def _fn(card, event, state, _tok=token, _cnt=count):
            from engine.card_effects.ability_keywords import create_token, _controller_id
            create_token(state, _controller_id(card), _tok, _cnt)
        return _fn

    if effect_type == "grant_go_again":
        def _fn(card, event, state):
            if state.combat:
                if "go_again" not in state.combat.keywords:
                    state.combat.grant_keyword("go_again")
        return _fn

    if effect_type == "intimidate":
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import effect_intimidate, _controller_id
            cid = _controller_id(card)
            effect_intimidate(state, 3 - cid)
        return _fn

    if effect_type == "dominate":
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import effect_dominate, _controller_id
            effect_dominate(state, _controller_id(card))
        return _fn

    if effect_type == "mark":
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import effect_mark, _controller_id
            cid = _controller_id(card)
            effect_mark(state, 3 - cid)
        return _fn

    if effect_type == "amp":
        amt = effect_params.get("amount", 1)
        def _fn(card, event, state, _amt=amt):
            from engine.card_effects.ability_keywords import effect_amp, _controller_id
            effect_amp(state, _controller_id(card), _amt)
        return _fn

    if effect_type == "gain_resources":
        amt = effect_params.get("amount", 1)
        def _fn(card, event, state, _amt=amt):
            from engine.card_effects.ability_keywords import effect_gain_resources, _controller_id
            effect_gain_resources(state, _controller_id(card), _amt)
        return _fn

    if effect_type == "set_flag":
        flag = effect_params.get("flag", "")
        scope = effect_params.get("scope", "current")
        def _fn(card, event, state, _flag=flag, _scope=scope):
            from engine.card_effects.ability_keywords import _controller_id
            player = state.players[_controller_id(card)]
            if _scope == "next" and hasattr(player, "next_turn_effects"):
                player.next_turn_effects.append(_flag)
            else:
                player.current_turn_effects.append(_flag)
        return _fn

    if effect_type == "put_counter":
        ctype = effect_params.get("counter_type", "")
        def _fn(card, event, state, _ct=ctype):
            from engine.card_effects.ability_keywords import effect_put_counter
            effect_put_counter(state, card, _ct)
        return _fn

    if effect_type == "power_bonus":
        amt = effect_params.get("amount", 0)
        def _fn(card, event, state, _amt=amt):
            if state.combat and state.combat.attack_card:
                state.combat.attack_power = (state.combat.attack_power or 0) + _amt
        return _fn

    if effect_type == "discard":
        amt = effect_params.get("amount", 1)
        random_discard = effect_params.get("random", False)
        def _fn(card, event, state, _amt=amt, _rand=random_discard):
            from engine.card_effects.ability_keywords import effect_discard, _controller_id
            effect_discard(state, _controller_id(card), _amt, random_discard=_rand)
        return _fn

    if effect_type == "deal_physical":
        amt = effect_params.get("amount", 0)
        tgt = effect_params.get("target", "opponent")
        def _fn(card, event, state, _amt=amt, _tgt=tgt):
            from engine.card_effects.ability_keywords import effect_deal_damage, _controller_id
            cid = _controller_id(card)
            target_id = (3 - cid) if _tgt == "opponent" else cid
            effect_deal_damage(state, target_id, _amt, card, damage_type="physical")
        return _fn

    if effect_type == "grant_keyword":
        kw = effect_params.get("keyword", "")
        def _fn(card, event, state, _kw=kw):
            if state.combat:
                if _kw not in state.combat.keywords:
                    state.combat.grant_keyword(_kw)
        return _fn

    if effect_type == "remove_counter":
        ctype = effect_params.get("counter_type", "")
        amt = effect_params.get("amount", 1)
        def _fn(card, event, state, _ct=ctype, _amt=amt):
            from engine.card_effects.ability_keywords import effect_remove_counter
            effect_remove_counter(state, card, _ct, _amt)
        return _fn

    if effect_type == "banish_top_deck":
        amt = effect_params.get("amount", 1)
        face_up = effect_params.get("face_up", True)
        def _fn(card, event, state, _amt=amt, _fu=face_up):
            from engine.card_effects.ability_keywords import effect_banish_top_deck, _controller_id
            effect_banish_top_deck(state, _controller_id(card), _amt, face_up=_fu)
        return _fn

    if effect_type == "reload":
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import effect_reload, _controller_id
            effect_reload(state, _controller_id(card))
        return _fn

    if effect_type == "opt":
        amt = effect_params.get("amount", 1)
        def _fn(card, event, state, _amt=amt):
            from engine.card_effects.ability_keywords import effect_opt, _controller_id
            effect_opt(state, _controller_id(card), _amt)
        return _fn

    if effect_type == "charge":
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import effect_charge, _controller_id
            cid = _controller_id(card)
            player = state.players[cid]
            if player.hand.cards:
                slugs = [c.slug for c in player.hand.cards]
                from engine.card_effects.ability_keywords import _ask_player
                choice = _ask_player(state, cid, slugs,
                                     context="Choose a card to charge (put into soul)")
                chosen = player.hand.find(choice)
                if chosen is None:
                    chosen = player.hand.cards[0]
                effect_charge(state, cid, chosen)
        return _fn

    # Unknown / unhandled effect — no-op with warning
    def _noop(card, event, state, _et=effect_type):
        pass  # unknown effect_type: silently skip
    return _noop


# ---------------------------------------------------------------------------
# Generic condition checkers
# ---------------------------------------------------------------------------

def _make_condition(condition_type: str, condition_params: dict,
                    custom_fn_ref: Callable | None) -> Callable | None:
    """Return a (card, event, state) -> bool callable, or None (always True)."""

    if condition_type == "none":
        return None

    if condition_type == "custom" and custom_fn_ref is not None:
        return custom_fn_ref

    if condition_type == "is_attacking":
        return lambda c, e, s: (s.combat is not None and
                                 s.combat.attack_card is not None and
                                 s.combat.attack_card.slug == c.slug)

    if condition_type == "is_defending":
        return lambda c, e, s: (s.combat is not None and
                                 c in s.combat.defending_cards)

    if condition_type == "player_is_active":
        from engine.card_effects.ability_keywords import _controller_id
        return lambda c, e, s: (_controller_id(c) == s.active_player)

    if condition_type == "health_more_than_opp":
        from engine.card_effects.ability_keywords import _controller_id
        return lambda c, e, s: (s.players[_controller_id(c)].health >
                                  s.players[3 - _controller_id(c)].health)

    if condition_type == "coplayer_power_gte":
        min_power = condition_params.get("min_power", 6)
        def _cond(c, e, s, _mp=min_power):
            if not s.combat or c not in s.combat.defending_cards:
                return False
            return any(d.power is not None and d.power >= _mp
                       for d in s.combat.defending_cards if d.slug != c.slug)
        return _cond

    if condition_type == "has_counter_lt":
        ctype = condition_params.get("type", "")
        max_val = condition_params.get("max", 999)
        def _cond(c, e, s, _ct=ctype, _max=max_val):
            from engine.card_effects.ability_keywords import _controller_id
            key = (c.slug, c.zone, _ct)
            return s.players[_controller_id(c)].counters.get(key, 0) < _max
        return _cond

    if condition_type == "has_counter_gte":
        ctype = condition_params.get("counter_type", condition_params.get("type", ""))
        min_val = condition_params.get("min", 1)
        def _cond(c, e, s, _ct=ctype, _min=min_val):
            from engine.card_effects.ability_keywords import _controller_id
            key = (c.slug, c.zone, _ct)
            return s.players[_controller_id(c)].counters.get(key, 0) >= _min
        return _cond

    if condition_type == "flag_set":
        flag = condition_params.get("flag", "")
        def _cond(c, e, s, _flag=flag):
            from engine.card_effects.ability_keywords import _controller_id
            return _flag in s.players[_controller_id(c)].current_turn_effects
        return _cond

    if condition_type == "card_in_zone":
        zone = condition_params.get("zone", "")
        return lambda c, e, s, _z=zone: c.zone == _z

    if condition_type == "player_is_non_active":
        def _cond(c, e, s):
            from engine.card_effects.ability_keywords import _controller_id
            return _controller_id(c) != s.active_player
        return _cond

    if condition_type == "controller_has_card_type":
        card_type = condition_params.get("card_type", "")
        zone = condition_params.get("zone", "")
        def _cond(c, e, s, _ct=card_type, _z=zone):
            from engine.card_effects.ability_keywords import _controller_id
            player = s.players[_controller_id(c)]
            zone_obj = getattr(player, _z, None) if _z else None
            if zone_obj is not None and hasattr(zone_obj, 'cards'):
                return any(getattr(cc, 'card_type', '') == _ct for cc in zone_obj.cards)
            return False
        return _cond

    if condition_type == "opponent_has_supertype":
        supertype = condition_params.get("supertype", "")
        zone = condition_params.get("zone", "")
        def _cond(c, e, s, _st=supertype, _z=zone):
            from engine.card_effects.ability_keywords import _controller_id
            opp = s.players[3 - _controller_id(c)]
            zone_obj = getattr(opp, _z, None) if _z else None
            if zone_obj is not None and hasattr(zone_obj, 'cards'):
                return any(getattr(cc, 'supertype', '') == _st for cc in zone_obj.cards)
            return False
        return _cond

    if condition_type == "attacking_hero_is":
        hero_name = condition_params.get("hero", "")
        def _cond(c, e, s, _h=hero_name):
            if not s.combat:
                return False
            attacker = s.players[s.combat.attacker]
            return getattr(attacker, 'hero_slug', '') == _h or getattr(attacker, 'hero_name', '') == _h
        return _cond

    if condition_type == "defending_hero_is":
        hero_name = condition_params.get("hero", "")
        def _cond(c, e, s, _h=hero_name):
            if not s.combat:
                return False
            defender = s.players[s.combat.defender]
            return getattr(defender, 'hero_slug', '') == _h or getattr(defender, 'hero_name', '') == _h
        return _cond

    if condition_type == "reprise_check":
        def _cond(c, e, s):
            from engine.card_effects.ability_keywords import reprise_check
            return reprise_check(s)
        return _cond

    if condition_type == "crush_check":
        def _cond(c, e, s):
            from engine.card_effects.ability_keywords import crush_check
            return crush_check(e, s)
        return _cond

    if condition_type == "combo_check":
        combo_names = condition_params.get("combo_names", [])
        def _cond(c, e, s, _cn=combo_names):
            from engine.card_effects.ability_keywords import combo_check
            return combo_check(s, _cn)
        return _cond

    if condition_type == "surge_check":
        amount = condition_params.get("amount", 1)
        def _cond(c, e, s, _amt=amount):
            from engine.card_effects.ability_keywords import surge_check
            return surge_check(e, _amt)
        return _cond

    if condition_type == "rupture_check":
        def _cond(c, e, s):
            from engine.card_effects.ability_keywords import rupture_check
            return rupture_check(s)
        return _cond

    # Unknown condition — always True (safe fallback)
    return None


# ---------------------------------------------------------------------------
# Resolve custom_fn string → callable from triggers/registry modules
# ---------------------------------------------------------------------------

_custom_fn_cache: dict[str, Callable] = {}


def _resolve_fn(fn_name: str | None) -> Callable | None:
    if not fn_name:
        return None
    if fn_name in _custom_fn_cache:
        return _custom_fn_cache[fn_name]

    # Search triggers.py and registry.py namespaces
    try:
        import engine.card_effects.triggers as trig_mod
        fn = getattr(trig_mod, fn_name, None)
        if fn is not None:
            _custom_fn_cache[fn_name] = fn
            return fn
    except Exception:
        pass

    try:
        import engine.card_effects.registry as reg_mod
        fn = getattr(reg_mod, fn_name, None)
        if fn is not None:
            _custom_fn_cache[fn_name] = fn
            return fn
    except Exception:
        pass

    return None


# ---------------------------------------------------------------------------
# Main loader
# ---------------------------------------------------------------------------

def load_db_triggers(card_triggers_dict: dict) -> int:
    """
    Read all trigger rows from the DB and merge them into card_triggers_dict.
    Overwrites any existing entry for the same slug (DB takes precedence).
    Returns the number of card slugs loaded.
    """
    from engine.card_effects.triggers import TriggerDef
    init_db()

    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM card_triggers ORDER BY slug, intra_card_order"
    ).fetchall()

    # Group rows by slug
    by_slug: dict[str, list] = {}
    for row in rows:
        slug = row["slug"]
        by_slug.setdefault(slug, []).append(row)

    for slug, trigger_rows in by_slug.items():
        defs = []
        for row in trigger_rows:
            p = params(row, "condition_params")
            ep = params(row, "effect_params")
            cond_fn_ref = _resolve_fn(row["condition_fn"])
            eff_fn_ref = _resolve_fn(row["effect_fn"])
            condition = _make_condition(row["condition_type"], p, cond_fn_ref)
            effect = _make_effect(row["effect_type"], ep, eff_fn_ref)
            defs.append(TriggerDef(
                event_type=row["event_type"],
                condition_fn=condition,
                effect_fn=effect,
                is_optional=bool(row["is_optional"]),
            ))
        card_triggers_dict[slug] = defs

    return len(by_slug)
