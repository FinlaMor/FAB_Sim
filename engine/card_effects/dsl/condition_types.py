"""Compile JSON condition objects into (card, event, state) -> bool callables."""
from __future__ import annotations
from typing import Any, Callable


def _attack_card_cost(attack_card) -> int:
    """Printed resource cost of the attack card (0-cost cards stay 0)."""
    cost = getattr(attack_card, 'cost', None)
    if cost is None:
        cost = getattr(attack_card, 'raw_cost', None)
    return cost if cost is not None else 0


def compile_condition(ctype: str, params: dict[str, Any]) -> Callable | None:
    """Return a (card, event, state)->bool callable, or None (always-True)."""

    if ctype in ("none", "NONE", ""):
        return None

    # ── game phase ─────────────────────────────────────────────────────────
    if ctype == "DURING_TURN":
        # CR 4.1.8b: an effect that would only trigger during a player's turn
        # does not trigger during the start-of-game procedure. individual_turns
        # is 0 all through setup and becomes >=1 once the first turn begins, so
        # this gates a turn-restricted trigger out of start-of-game.
        return lambda c, e, s: getattr(s, "individual_turns", 0) >= 1

    # ── combat presence ────────────────────────────────────────────────────
    if ctype == "IN_COMBAT":
        return lambda c, e, s: s.combat is not None

    if ctype == "ATTACK_IS_WEAPON":
        return lambda c, e, s: s.combat is not None and getattr(s.combat, 'from_weapon', False)

    if ctype == "ATTACK_IS_NOT_WEAPON":
        return lambda c, e, s: s.combat is not None and not getattr(s.combat, 'from_weapon', False)

    if ctype == "ATTACK_CLASS_IN":
        classes = [v.lower() for v in params.get("classes", [])]
        def _aci(c, e, s, _cls=classes):
            if not s.combat or not getattr(s.combat, 'attack_card', None):
                return False
            card_classes = [x.lower() for x in (getattr(s.combat.attack_card, 'classes', None) or [])]
            return any(cl in card_classes for cl in _cls)
        return _aci

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
            return _attack_card_cost(s.combat.attack_card) >= _amt
        return _acg

    if ctype == "ATTACK_COST_LTE":
        # Accept "cost" or "amount" key. Default high so a missing value never blocks.
        amount = params.get("cost", params.get("amount", 999))
        def _acl(c, e, s, _amt=amount):
            if not s.combat or not s.combat.attack_card:
                return False
            return _attack_card_cost(s.combat.attack_card) <= _amt
        return _acl

    if ctype == "ATTACK_TYPE_IN":
        types = [v.lower() for v in params.get("types", [])]
        def _ati(c, e, s, _types=types):
            if not s.combat or not getattr(s.combat, 'attack_card', None):
                return False
            card_types = [x.lower() for x in (getattr(s.combat.attack_card, 'types', None) or [])]
            return any(t in card_types for t in _types)
        return _ati

    if ctype == "ATTACK_SUBTYPE_IN":
        subtypes = [v.lower() for v in params.get("subtypes", [])]
        def _asi(c, e, s, _subs=subtypes):
            if not s.combat or not getattr(s.combat, 'attack_card', None):
                return False
            card_subs = [x.lower() for x in (getattr(s.combat.attack_card, 'subtypes', None) or [])]
            return any(st in card_subs for st in _subs)
        return _asi

    if ctype == "ATTACK_PITCH_POWER_GTE":
        # True if a card with printed power >= amount was pitched to pay for the
        # current attack (CR "pitched to attack with this"). Reads
        # combat.pitched_for_attack, NOT the pitch zone.
        amount = params.get("amount", params.get("power", 6))
        def _appg(c, e, s, _amt=amount):
            if not s.combat:
                return False
            for pc in getattr(s.combat, 'pitched_for_attack', None) or []:
                power = getattr(pc, 'power', None)
                if power is None:
                    power = getattr(pc, 'base_power', None)
                if power is not None and power >= _amt:
                    return True
            return False
        return _appg

    if ctype == "SOURCE_IS_ATTACK":
        # True when the ability's source card IS the current active attack. Used
        # by weapon self-buffs ("… to attack WITH THIS") so a WHILE_STATIC on the
        # weapon only applies to its own attack, not any attack in combat.
        def _sia(c, e, s):
            return bool(s.combat and getattr(s.combat, 'attack_card', None) is c)
        return _sia

    if ctype == "ATTACK_CONTROLLED_BY_YOU":
        # True if the current attack is controlled by this card's controller.
        def _acby(c, e, s):
            from engine.card_effects.ability_keywords import _controller_id
            if not s.combat or not getattr(s.combat, 'attack_card', None):
                return False
            return getattr(s.combat.attack_card, 'controller', None) == _controller_id(c)
        return _acby

    if ctype == "CONTROLS_ATTACK_ACTION":
        # True if you control an attack action card in the current combat —
        # the active attack you control OR a card you're defending with
        # (CR: defending with an attack action card counts as controlling it).
        def _caa(c, e, s):
            from engine.card_effects.ability_keywords import (
                _controller_id, controlled_attack_action_cards)
            return bool(controlled_attack_action_cards(s, _controller_id(c)))
        return _caa

    if ctype == "HAS_HEAD_OPP_DOESNT":
        # Headbutt: "if you have a head equipped and the defending hero doesn't".
        def _hhod(c, e, s):
            from engine.card_effects.ability_keywords import _controller_id
            cid = _controller_id(c)
            def has_head(p):
                return bool(p.head.cards) and not getattr(p.head.cards[0], 'face_down', False)
            return has_head(s.players[cid]) and not has_head(s.players[3 - cid])
        return _hhod

    if ctype == "DID_NOT_HIT":
        # True when the current combat's attack did not hit (e.g. Swing Big's
        # "when the combat chain closes, if this didn't hit …").
        return lambda c, e, s: (s.combat is not None
                                 and not getattr(s.combat, 'hit', False))

    if ctype == "DEFENDER_USED_HAND_CARD":
        return lambda c, e, s: (s.combat is not None
                                 and getattr(s.combat, 'defender_used_hand_card', False))

    if ctype == "DEFENDS_WITH_OTHER_HAND_CARD":
        # True if this card is defending together with ANOTHER card that came
        # from the defender's hand (Right Behind You). The source card itself is
        # excluded, so blocking with this card alone — even from hand — is not
        # enough; a second hand card must also be defending.
        def _dwohc(c, e, s):
            if s.combat is None:
                return False
            hand_ids = getattr(s.combat, 'hand_defender_ids', None) or set()
            return any(d is not c and getattr(d, 'object_id', None) in hand_ids
                       for d in s.combat.defending_cards)
        return _dwohc

    # ── keyword checks ─────────────────────────────────────────────────────
    if ctype == "REPRISE":
        def _reprise(c, e, s):
            from engine.card_effects.ability_keywords import reprise_check
            return reprise_check(s)
        return _reprise

    if ctype == "SELF_ATTACK_POWER_GTE":
        # "If this has N or more {p}" — the current attack's live power is at
        # least N (e.g. Chain of Brutality's 6-power threshold).
        amount = params.get("amount", 0)
        def _self_pow_gte(c, e, s, _n=amount):
            combat = s.combat
            return combat is not None and (combat.attack_power or 0) >= _n
        return _self_pow_gte

    if ctype == "ATTACK_POWER_GT_BASE":
        # "an attack with {p} greater than its base" — the current attack has
        # been pumped above its printed base power (e.g. Inertia Trap, which
        # reacts only to a boosted attack). Compares the live combat power to
        # the base recorded when the attack was declared.
        def _atk_gt_base(c, e, s):
            combat = s.combat
            if combat is None:
                return False
            return (combat.attack_power or 0) > (getattr(combat, "base_attack_power", 0) or 0)
        return _atk_gt_base

    if ctype in ("ATTACK_BASE_POWER_LTE", "ATTACK_BASE_POWER_GTE"):
        # The current attack's printed BASE power vs a threshold ("an attack with
        # base {p} N or less/greater"). Reads the base recorded when the attack was
        # declared, not the pumped live value.
        amount = params.get("amount", 0)
        lte = ctype == "ATTACK_BASE_POWER_LTE"
        def _abp(c, e, s, _a=amount, _lte=lte):
            combat = s.combat
            if combat is None:
                return False
            base = getattr(combat, "base_attack_power", None)
            if base is None:
                base = getattr(getattr(combat, "attack_card", None), "base_power", 0) or 0
            return base <= _a if _lte else base >= _a
        return _abp

    if ctype == "IN_GRAVEYARD":
        # "if you have a <name>/<type> in your graveyard" — true when the controller's
        # graveyard holds >= count cards matching an optional name / type filter.
        want_name = (params.get("name") or "").lower()
        want_types = [t.lower() for t in (params.get("types") or [])]
        count_gte = params.get("count_gte", 1)
        player_target = (params.get("player") or "SELF").upper()
        def _ing(c, e, s, _n=want_name, _t=want_types, _cge=count_gte, _pt=player_target):
            from engine.card_effects.ability_keywords import _controller_id
            cid = _controller_id(c)
            tid = (3 - cid) if _pt in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            gy = getattr(s.players[tid], "graveyard", None)
            if gy is None:
                return False
            n = 0
            for card in gy.cards:
                if _n and (getattr(card, "name", "") or "").lower() != _n \
                        and getattr(card, "slug", "") != _n:
                    continue
                if _t:
                    cts = [x.lower() for x in (getattr(card, "types", None) or [])
                           + (getattr(card, "subtypes", None) or [])]
                    if not any(x in cts for x in _t):
                        continue
                n += 1
            return n >= _cge
        return _ing

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
        zone = params.get("zone", "").lower()
        cost_gte = params.get("cost_gte")
        cost_lte = params.get("cost_lte")
        filter_types = [t.lower() for t in params.get("filter_types", [])]
        # count_gte: >= N cards match; "amount" is a legacy alias for count_gte
        count_gte = params.get("count_gte", params.get("amount"))
        count_eq  = params.get("count_eq")

        def _ciz(c, e, s, _z=zone, _cge=cost_gte, _cle=cost_lte, _ft=filter_types,
                 _nge=count_gte, _neq=count_eq):
            from engine.card_effects.ability_keywords import _controller_id
            player = s.players[_controller_id(c)]
            zone_obj = getattr(player, _z, None)
            if zone_obj is None:
                return False
            count = 0
            for card in zone_obj.cards:
                cost = getattr(card, 'cost', None) or 0
                if _cge is not None and cost < _cge:
                    continue
                if _cle is not None and cost > _cle:
                    continue
                if _ft:
                    card_types = [t.lower() for t in (getattr(card, 'subtypes', None) or [])]
                    card_types += [t.lower() for t in (getattr(card, 'types', None) or [])]
                    if not any(t in card_types for t in _ft):
                        continue
                count += 1
            if _neq is not None:
                return count == _neq
            if _nge is not None:
                return count >= _nge
            return count >= 1  # default: at least one matching card

        return _ciz

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

    if ctype == "CHAIN_HIT_COUNT_GTE":
        # True when the current chain has >= N prior hits (mask_of_momentum: 3rd+ hit).
        amount = params.get("amount", 3)
        def _cgh(c, e, s, _amt=amount):
            return len(getattr(s, 'chain_links', [])) >= _amt - 1
        return _cgh

    if ctype == "DISCARDED_CARD_POWER_GTE":
        # True when the discarded card (passed as event) has >= N base power.
        amount = params.get("amount", 0)
        def _dcpg(c, e, s, _amt=amount):
            power = getattr(e, 'power', None) or getattr(e, 'base_power', None) or 0
            return (power or 0) >= _amt
        return _dcpg

    if ctype == "CODEFENDER_POWER_GTE":
        # True when the source defends together with ANOTHER card of >= N power
        # (CR 7.0.5e). E.g. Apex Bonebreaker: "When this defends together with a
        # card with 6 or more {p}, …".
        min_power = params.get("min", params.get("power", params.get("amount", 6)))
        def _cdp(c, e, s, _min=min_power):
            if not s.combat:
                return False
            for d in (s.combat.defending_cards or []):
                if d is c:
                    continue
                if (getattr(d, 'power', None) or 0) >= _min:
                    return True
            return False
        return _cdp

    if ctype == "IS_BOOED":
        # True if the controller has been booed this turn.
        def _ib(c, e, s):
            from engine.card_effects.ability_keywords import has_been_booed, _controller_id
            return has_been_booed(s, _controller_id(c))
        return _ib

    if ctype == "OPPONENT_IS_MARKED":
        # True if the opponent hero is currently marked.
        def _oim(c, e, s):
            from engine.card_effects.ability_keywords import _controller_id
            opp = 3 - _controller_id(c)
            return s.players[opp].class_counters.get("marked", 0) > 0
        return _oim

    if ctype == "CONTROLS_TOKEN_TYPE":
        # True if the controller has >= 1 permanent of the given slug OR a
        # permanent that "counts as" that token (matched via subtype, e.g. Aurum
        # Aegis counts as a Gold). Searches all permanents (a Gold token is an
        # Item sub-zone member, not the Token sub-zone) plus equipment/weapon slots.
        token_slug = params.get("token", "")
        def _ctt(c, e, s, _slug=token_slug):
            from engine.card_effects.ability_keywords import _controller_id
            player = s.players[_controller_id(c)]
            for zone_name in ('permanents', 'head', 'chest', 'arms', 'legs',
                              'weapon1', 'weapon2'):
                zone = getattr(player, zone_name, None)
                if zone and any(
                        getattr(t, 'slug', '') == _slug
                        or _slug.lower() in [st.lower() for st in (getattr(t, 'subtypes', None) or [])]
                        for t in zone.cards):
                    return True
            return False
        return _ctt

    if ctype == "ATTACK_HAS_KEYWORD":
        # Normalise separators so "go_again", "go again" and "Go Again" all
        # match — combat.keywords stores the title-cased form ("Go Again") while
        # JSON often writes the snake_case token. Lair of the Spider never fired
        # because "go_again" != "go again" under a plain lower() comparison.
        def _norm(k):
            return k.lower().replace("_", "").replace(" ", "")
        kw = _norm(params.get("keyword", ""))
        def _ahk(c, e, s, _kw=kw):
            if not s.combat:
                return False
            return _kw in [_norm(k) for k in (s.combat.keywords or [])]
        return _ahk

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

    if ctype == "ATTACK_TARGET_IS_HERO":
        # "When this attacks A HERO" — false when the attack was declared
        # against a permanent or ally. combat.attack_target is set only for
        # those, so a hero attack leaves it None.
        def _atk_hero(c, e, s):
            combat = s.combat
            return combat is not None and getattr(combat, "attack_target", None) is None
        return _atk_hero

    if ctype == "REF_PITCH_IS":
        # Test the pitch value of a card a previous effect stored under "ref".
        # Pitch 1 = red, 2 = yellow, 3 = blue — so "if it's red" becomes a
        # condition on a referenced card rather than something baked into a
        # card-specific effect.
        ref = params.get("ref", "looked")
        want = params.get("pitch", 1)
        def _ref_pitch(c, e, s, _r=ref, _w=want):
            from engine.context import get_ref
            target = get_ref(_r)
            if target is None or isinstance(target, list):
                return False
            return (getattr(target, "pitch", None) or 0) == _w
        return _ref_pitch

    if ctype == "REF_EXISTS":
        ref = params.get("ref", "looked")
        def _ref_exists(c, e, s, _r=ref):
            from engine.context import get_ref
            target = get_ref(_r)
            return bool(target) if not isinstance(target, list) else len(target) > 0
        return _ref_exists

    if ctype == "NOT":
        # Inner condition may be nested under "condition"/"inner" (a full spec dict)
        # or flattened onto this dict via "inner_type". Never recurse with our own
        # "NOT" type (params.get("type") would re-enter here forever).
        inner_spec = params.get("condition") or params.get("inner")
        if isinstance(inner_spec, dict):
            inner = compile_condition(inner_spec.get("type", "none"), inner_spec)
        else:
            inner_t = params.get("inner_type")
            inner = compile_condition(inner_t, params) if inner_t else None
        def _not(c, e, s, _fn=inner):
            return not (_fn is None or _fn(c, e, s))
        return _not

    # Unknown condition types are authoring errors — fail at JSON load time
    # rather than silently passing (fail-open let bad JSON go unnoticed).
    raise ValueError(f"Unknown DSL condition type: {ctype!r} (params: {params!r})")
