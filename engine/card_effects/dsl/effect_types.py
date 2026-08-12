"""Compile JSON effect objects into (card, event, state) -> None callables."""
from __future__ import annotations
from typing import Any, Callable


def _track_injected_effect(slug: str, effect_type: str) -> None:
    """Record a coverage hit for an effect that fires via an injected trigger
    (INJECT_TRIGGER one-shots / turn / chain hooks). These run through the engine's
    trigger machinery, not the interpreter's run_ability, so the interpreter's
    _track_effect never sees them — without this they read as authored-but-dead in
    scripts/dsl_coverage.py. No-op unless a coverage tracker is active."""
    from engine.card_effects.dsl import coverage as _cov
    tracker = _cov.active()
    if tracker is not None:
        tracker.record_effect(slug, effect_type)


def _resolve_amount(amount: Any, state) -> int | float:
    """Resolve a dynamic amount token to a numeric value.

    Two authoring forms are accepted: a bare string token ("ROLL_NUMBER") and a
    nested expression dict ({"type": "HALF", "value": {"type": "ROLL_RESULT"}}).
    Both appear in card JSON; an unresolved dict used to flow through as a dict
    and blow up the arithmetic in the calling effect.
    """
    roll = getattr(state, '_roll_result', 0) or 0
    if isinstance(amount, str):
        if amount in ("ROLL_NUMBER", "ROLL_RESULT"):
            return roll
        if amount == "ROLL_NUMBER_HALF_ROUND_DOWN":
            return roll // 2
        return 0
    if isinstance(amount, dict):
        atype = (amount.get("type") or "").upper()
        if atype in ("ROLL_NUMBER", "ROLL_RESULT"):
            return roll
        if atype in ("HALF", "HALF_ROUND_DOWN"):
            return int(_resolve_amount(amount.get("value", 0), state)) // 2
        if atype in ("VALUE", "CONSTANT", "LITERAL"):
            return _resolve_amount(amount.get("value", 0), state)
        return 0
    return amount


def compile_effect(etype: str, params: dict[str, Any]) -> Callable:
    """Return a (card, event, state)->None callable."""

    # Numeric "amount" authored as an integer-literal string ("2") crashes the
    # arithmetic/range() in many branches (draw N, deal N, discard N). Coerce a
    # pure-integer string to int once here; leave dynamic markers ("X",
    # "DEFENDING_CARD_COUNT") untouched for the branches that interpret them.
    if isinstance(params.get("amount"), str):
        try:
            params = {**params, "amount": int(params["amount"])}
        except (TypeError, ValueError):
            pass

    # ── life / damage ──────────────────────────────────────────────────────
    if etype == "GAIN_LIFE_PER_CARD_IN_HAND":
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import effect_gain_life, _controller_id
            cid = _controller_id(card)
            n = len(state.players[cid].hand.cards)
            if n > 0:
                effect_gain_life(state, cid, n)
        return _fn

    if etype == "LOSE_LIFE":
        amt = params.get("amount", 0)
        tgt = params.get("player", "SELF")
        def _fn(card, event, state, _a=amt, _t=tgt):
            from engine.card_effects.ability_keywords import effect_lose_life, _controller_id
            cid = _controller_id(card)
            tid = (3 - cid) if _t.upper() in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            effect_lose_life(state, tid, _a)
        return _fn

    if etype in ("DEAL_DAMAGE", "DEAL_PHYSICAL"):
        amt = params.get("amount", 0)
        tgt = params.get("target", "OPPONENT")
        def _fn(card, event, state, _a=amt, _t=tgt):
            from engine.card_effects.ability_keywords import effect_deal_damage, _controller_id
            cid = _controller_id(card)
            _t_upper = _t.upper()
            tid = (3 - cid) if _t_upper in ("OPPONENT", "DEFENDING", "DEFENDER", "ATTACKER") else cid
            effect_deal_damage(state, tid, _a, card, damage_type="physical")
        return _fn

    if etype == "DEAL_ARCANE":
        amt = params.get("amount", 0)
        tgt = params.get("target", "OPPONENT")
        def _fn(card, event, state, _a=amt, _t=tgt):
            from engine.card_effects.ability_keywords import effect_deal_arcane, _controller_id
            cid = _controller_id(card)
            tid = (3 - cid) if _t.upper() in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            effect_deal_arcane(state, tid, _a, card)
        return _fn

    # ── cards ──────────────────────────────────────────────────────────────
    if etype == "DRAW":
        amt = params.get("amount", 1)
        player_target = params.get("player", "SELF")
        def _fn(card, event, state, _a=amt, _pt=player_target):
            from engine.card_effects.ability_keywords import effect_draw, _controller_id
            cid = _controller_id(card)
            tid = (3 - cid) if _pt.upper() in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            # Draw counts are usually ints, but candidate JSON authors dynamic
            # markers ("intellect", "hand_size", "CHAIN_HIT_COUNT"). Resolve the
            # ones we can; an unknown marker draws 0 rather than crashing draw().
            n = _a
            if isinstance(n, str):
                marker = n.strip().upper()
                if marker == "INTELLECT":
                    n = getattr(state.players[tid], "intellect", 0)
                elif marker == "HAND_SIZE":
                    n = len(state.players[tid].hand.cards)
                elif marker == "CHAIN_HIT_COUNT":
                    n = len(getattr(state, "chain_links", []) or [])
                else:
                    try:
                        n = int(n)
                    except (TypeError, ValueError):
                        n = 0
            if isinstance(n, int) and n > 0:
                effect_draw(state, tid, n)
        return _fn

    if etype == "DISCARD":
        amt = params.get("amount", 1)
        player_target = params.get("player", "SELF")
        random_discard = params.get("random", False)
        def _fn(card, event, state, _a=amt, _pt=player_target, _rand=random_discard):
            from engine.card_effects.ability_keywords import effect_discard, _controller_id
            cid = _controller_id(card)
            tid = (3 - cid) if _pt.upper() in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            effect_discard(state, tid, _a, random_discard=_rand)
        return _fn

    if etype == "OPT":
        amt = params.get("amount", 1)
        def _fn(card, event, state, _a=amt):
            from engine.card_effects.ability_keywords import effect_opt, _controller_id
            effect_opt(state, _controller_id(card), _a)
        return _fn

    if etype == "RELOAD":
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import effect_reload, _controller_id
            effect_reload(state, _controller_id(card))
        return _fn

    if etype == "BANISH":
        amt = params.get("amount", 1)
        from_zone = params.get("from_zone", "TOP_DECK")
        player_target = params.get("player", "SELF")
        def _fn(card, event, state, _a=amt, _fz=from_zone, _pt=player_target):
            from engine.card_effects.ability_keywords import _ask_player, _controller_id
            from engine.effect_keywords import banish as _ek_banish
            cid = _controller_id(card)
            tid = (3 - cid) if _pt.upper() in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            fz = _fz.upper()
            # amount may arrive as a dynamic token or a stray string; coerce to a
            # non-negative int so it can index/slice a zone (bad values -> no-op,
            # never a TypeError that aborts the game).
            _a = _resolve_amount(_a, state)
            try:
                _a = max(0, int(_a))
            except (TypeError, ValueError):
                _a = 0
            if fz in ("TOP_DECK", "DECK"):
                targets = state.players[tid].deck.cards[:_a]
                for t in targets:
                    _ek_banish(state, t, tid, origin_zone="deck")
            elif fz == "HAND":
                hand = state.players[tid].hand.cards
                if not hand:
                    return
                for _ in range(min(_a, len(hand))):
                    options = [c.slug for c in state.players[tid].hand.cards]
                    pick = _ask_player(state, tid, options, context="Choose a card to banish from hand")
                    target = next((c for c in state.players[tid].hand.cards if c.slug == pick), None)
                    if target:
                        _ek_banish(state, target, tid, origin_zone="hand")
            elif fz == "GRAVEYARD":
                gy = state.players[tid].graveyard.cards
                if not gy:
                    return
                for _ in range(min(_a, len(gy))):
                    options = [c.slug for c in state.players[tid].graveyard.cards]
                    pick = _ask_player(state, tid, options, context="Choose a card to banish from graveyard")
                    target = next((c for c in state.players[tid].graveyard.cards if c.slug == pick), None)
                    if target:
                        _ek_banish(state, target, tid, origin_zone="graveyard")
            elif fz == "ARSENAL":
                arsenal = state.players[tid].arsenal.cards
                for _ in range(min(_a, len(arsenal))):
                    if not state.players[tid].arsenal.cards:
                        break
                    options = [c.slug for c in state.players[tid].arsenal.cards]
                    pick = _ask_player(state, tid, options, context="Choose a card to banish from arsenal")
                    target = next((c for c in state.players[tid].arsenal.cards if c.slug == pick), None)
                    if target:
                        _ek_banish(state, target, tid, origin_zone="arsenal")
        return _fn

    if etype == "CHARGE":
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import effect_charge, _controller_id
            cid = _controller_id(card)
            player = state.players[cid]
            if player.hand.cards:
                chosen = player.hand.cards[0]
                effect_charge(state, cid, chosen)
        return _fn

    # ── attack / combat ────────────────────────────────────────────────────
    if etype == "DOMINATE":
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import effect_dominate, _controller_id
            effect_dominate(state, _controller_id(card))
        return _fn

    if etype == "INTIMIDATE":
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import effect_intimidate, _controller_id
            cid = _controller_id(card)
            effect_intimidate(state, 3 - cid)
        return _fn

    if etype == "RETURN_TO_HAND":
        # Return this card to the controller's hand.
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import put_object
            cid = _controller_id(card)
            put_object(state, target_card=card, destination_zone="hand",
                       destination_player_id=cid, source_player_id=cid)
        return _fn

    if etype in ("PUT_HAND_CARD_BOTTOM", "PUT_HAND_CARD_TOP"):
        # Choose a card from hand and put it on the deck (no draw).
        # player:   "SELF" (default) | "OPPONENT" — whose hand is affected.
        # to:       "BOTTOM" (default) | "TOP" — where it lands. PUT_HAND_CARD_TOP
        #           is sugar for to="TOP".
        # optional: True (default) allows declining. Cards worded "they put a
        #           card…" are mandatory (e.g. Boulder Drop) and must pass false,
        #           or the affected player can simply refuse the effect.
        player_target = params.get("player", "SELF")
        to_top = (etype == "PUT_HAND_CARD_TOP"
                  or str(params.get("to", "BOTTOM")).upper() == "TOP")
        optional = params.get("optional", True)
        def _fn(card, event, state, _pt=player_target, _top=to_top, _opt=optional):
            from engine.card_effects.ability_keywords import _ask_player, _controller_id, DECLINE
            from engine.effect_keywords import put_object
            cid = _controller_id(card)
            tid = (3 - cid) if _pt.upper() in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            player = state.players[tid]
            if not player.hand.cards:
                return
            where = "top" if _top else "bottom"
            options = [c.slug for c in player.hand.cards]
            if _opt:
                options = options + [DECLINE]
            choice = _ask_player(state, tid, options,
                                 context=f"Choose a card to put on the {where} of your deck")
            if choice == DECLINE:
                return
            target = player.hand.find(choice)
            if target:
                # position "top" → cards[0]; None → zone default (bottom, cards[-1])
                put_object(state, target, "deck",
                           destination_player_id=tid, source_player_id=tid,
                           position=("top" if _top else None))
        return _fn

    if etype == "PUT_SELF_BOTTOM_DECK":
        # Remove this card from its current zone and put it on the bottom of its owner's deck.
        # Used for replacement effects like Drone of Brutality.
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import put_object
            pid = _controller_id(card)
            # position=None → zone default (append = bottom, cards[-1])
            put_object(state, card, "deck",
                       destination_player_id=pid, source_player_id=pid,
                       position=None)
        return _fn

    if etype == "SEARCH_BANISH_FACE_DOWN":
        # trap_door on-become: "you may search your deck for a card, banish it
        # face-down, then shuffle. If it's a trap, you may play it until the
        # start of your next turn." Optional (may fail to find).
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import _ask_player, _controller_id
            from engine.effect_keywords import shuffle as _shuffle, banish as _banish
            cid = _controller_id(card)
            controller = state.players[cid]
            eligible = list(controller.deck.cards)
            from engine.card_effects.ability_keywords import ask_optional, FAIL_TO_FIND
            pick = ask_optional(state, cid, [c.slug for c in eligible], sentinel=FAIL_TO_FIND,
                                context="Search your deck for a card to banish face-down (or fail to find)")
            if pick is not None:
                target = next((c for c in eligible if c.slug == pick), None)
                if target is not None:
                    _banish(state, target, cid, origin_zone="deck")
                    if target in controller.banished.cards:
                        target.is_public = False  # banished face-down
                    subtypes = [s.lower() for s in (target.subtypes or [])]
                    if "trap" in subtypes:
                        # "If it's a trap, you may play it from banished until the
                        # start of your next turn." Cleared in start_of_turn_refresh.
                        controller.playable_from_banished.append(target)
            _shuffle(state, cid)
        return _fn

    if etype == "SEARCH_DECK":
        # Search your deck for any card, put it in hand, then shuffle.
        # Player may "fail to find" (CR 8.5.19). Follows the nimby pattern.
        filter_types = params.get("filter_types", None)   # optional list of card types
        filter_slug_contains = params.get("slug_contains", None)  # optional substring
        def _fn(card, event, state, _ft=filter_types, _fsc=filter_slug_contains):
            from engine.card_effects.ability_keywords import _ask_player, _controller_id
            from engine.effect_keywords import shuffle as effect_shuffle
            cid = _controller_id(card)
            controller = state.players[cid]
            eligible = list(controller.deck.cards)
            if _ft:
                eligible = [c for c in eligible if any(t in (c.types or []) for t in _ft)]
            if _fsc:
                eligible = [c for c in eligible if _fsc in c.slug]
            from engine.card_effects.ability_keywords import ask_optional, FAIL_TO_FIND
            pick = ask_optional(state, cid, [c.slug for c in eligible], sentinel=FAIL_TO_FIND,
                                context="Search your deck for a card and put it into hand (or fail to find)")
            if pick is not None:
                target = next((c for c in eligible if c.slug == pick), None)
                if target:
                    from engine.effect_keywords import put_object
                    # Assign ownership before the move so put_object resolves dest correctly.
                    target.owner = cid
                    target.controller = cid
                    # is_public=True: searched cards are revealed when put into hand.
                    put_object(state, target, "hand",
                               destination_player_id=cid, source_player_id=cid,
                               is_public=True)
            effect_shuffle(state, cid)
        return _fn

    if etype == "SEARCH_GRAVEYARD":
        # Search your graveyard for a matching card and put it into hand (CR
        # 8.5.19 "fail to find" allowed). Unlike SEARCH_DECK the graveyard is a
        # public, ordered zone, so there is no shuffle afterward. Filters:
        #   slug_contains / name_contains — substring match (case-insensitive);
        #   filter_types — any of these card types.
        filter_types = params.get("filter_types", None)
        slug_contains = params.get("slug_contains", None)
        name_contains = params.get("name_contains", None)
        def _fn(card, event, state, _ft=filter_types, _sc=slug_contains, _nc=name_contains):
            from engine.card_effects.ability_keywords import (
                _controller_id, ask_optional, FAIL_TO_FIND)
            from engine.effect_keywords import put_object
            cid = _controller_id(card)
            controller = state.players[cid]
            eligible = list(controller.graveyard.cards)
            if _ft:
                eligible = [c for c in eligible if any(t in (c.types or []) for t in _ft)]
            if _sc:
                eligible = [c for c in eligible if _sc.lower() in c.slug.lower()]
            if _nc:
                eligible = [c for c in eligible
                            if _nc.lower() in (getattr(c, "name", "") or "").lower()]
            if not eligible:
                return
            pick = ask_optional(state, cid, [c.slug for c in eligible], sentinel=FAIL_TO_FIND,
                                context="Search your graveyard for a card and put it into hand (or fail to find)")
            if pick is None:
                return
            target = next((c for c in eligible if c.slug == pick), None)
            if target is not None:
                target.owner = cid
                target.controller = cid
                put_object(state, target, "hand",
                           destination_player_id=cid, source_player_id=cid,
                           is_public=True)
        return _fn

    if etype == "AMP":
        amt = params.get("amount", 1)
        def _fn(card, event, state, _a=amt):
            from engine.card_effects.ability_keywords import effect_amp, _controller_id
            effect_amp(state, _controller_id(card), _a)
        return _fn

    if etype == "MARK":
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import effect_mark, _controller_id
            cid = _controller_id(card)
            effect_mark(state, 3 - cid)
        return _fn

    if etype == "REVEAL_HAND_MARK_IF_TYPE":
        # "Target opposing hero reveals their hand. If a card of <card_type> is
        # revealed this way, mark them." Revealing sets the cards public; the
        # mark lands only when the named type is present.
        want_type = params.get("card_type", "AttackReaction")
        def _fn(card, event, state, _t=want_type):
            from engine.card_effects.ability_keywords import effect_mark, _controller_id
            cid = _controller_id(card)
            opp = state.players[3 - cid]
            for c in opp.hand.cards:
                c.is_public = True
            if any(_t in (getattr(c, "types", None) or []) for c in opp.hand.cards):
                effect_mark(state, 3 - cid)
        return _fn

    # ── tokens / permanents ────────────────────────────────────────────────
    if etype == "CREATE_TOKEN":
        # The token to create: authored under "token" (a slug), "token_name", or
        # "token_type" (a display name like "Seismic Surge"). Only "token" was
        # read, so cards using the name keys created an empty token; create_token
        # slugifies a display name, so pass whichever was given.
        token = (params.get("token") or params.get("token_name")
                 or params.get("token_type") or "")
        count = params.get("count", 1)
        # Whose control the token enters. Cards author it under "player" OR
        # "controller" (~13 usages used the latter, which was unread -> the token
        # wrongly defaulted to SELF). Opponent-side values: opponent/defending/
        # defender/target_hero (the hit hero).
        player_target = params.get("player") or params.get("controller") or "SELF"
        destination = params.get("destination")  # e.g. "weapon_slot" to equip
        def _fn(card, event, state, _tok=token, _cnt=count, _pt=player_target, _dest=destination):
            from engine.effect_keywords import create_token as _ek_create_token
            from engine.card_effects.ability_keywords import _controller_id
            cid = _controller_id(card)
            tid = (3 - cid) if _pt.upper() in (
                "OPPONENT", "DEFENDING", "DEFENDER", "TARGET_HERO") else cid
            # count may be a dynamic expression, e.g. Spreading Plague's
            # "X = the number of defending cards this chain link".
            if isinstance(_cnt, str):
                n = 0
                if _cnt.upper() == "DEFENDING_CARD_COUNT" and state.combat is not None:
                    n = len(getattr(state.combat, "defending_cards", []) or [])
                _cnt = n
            if _cnt <= 0:
                return
            _ek_create_token(state, tid, _tok, _cnt, destination=_dest)
        return _fn

    if etype == "PUT_COUNTER":
        # Cards author the counter kind under EITHER "counter_type" or "counter";
        # only "counter_type" was read, so ~47 usages put an empty-typed counter.
        ctype = params.get("counter_type") or params.get("counter") or ""
        amt = params.get("amount", 1)
        def _fn(card, event, state, _ct=ctype, _a=amt):
            from engine.card_effects.ability_keywords import effect_put_counter
            for _ in range(_a):
                effect_put_counter(state, card, _ct)
        return _fn

    if etype == "REMOVE_COUNTER":
        ctype = params.get("counter_type") or params.get("counter") or ""
        amt = params.get("amount", 1)
        def _fn(card, event, state, _ct=ctype, _a=amt):
            from engine.card_effects.ability_keywords import effect_remove_counter
            effect_remove_counter(state, card, _ct, _a)
        return _fn

    if etype == "WARD":
        amt = params.get("amount", 0)
        def _fn(card, event, state, _a=amt):
            from engine.card_effects.ability_keywords import ward
            ward(state, card, _a)
        return _fn

    if etype == "ARCANE_BARRIER":
        amt = params.get("amount", 0)
        def _fn(card, event, state, _a=amt):
            from engine.card_effects.ability_keywords import arcane_barrier
            arcane_barrier(state, card, _a)
        return _fn

    # ── flags / misc ───────────────────────────────────────────────────────
    if etype == "SET_FLAG":
        flag = params.get("flag", "")
        scope = params.get("scope", "CURRENT").upper()
        player_target = params.get("player", "SELF")
        def _fn(card, event, state, _f=flag, _s=scope, _pt=player_target):
            from engine.card_effects.ability_keywords import _controller_id
            cid = _controller_id(card)
            tid = (3 - cid) if _pt.upper() in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            player = state.players[tid]
            if _s == "NEXT" and hasattr(player, "next_turn_effects"):
                player.next_turn_effects.append(_f)
            else:
                player.current_turn_effects.append(_f)
        return _fn

    if etype == "INJECT_TRIGGER":
        # Compile inner effects/conditions at load time, create one-shot TriggerDef at runtime.
        # The inner trigger may be given as a nested dict — {"trigger_type": ...,
        # "conditions": [...], "effects": [...]} — which is REQUIRED when it has inner
        # conditions: the loader pops a top-level "conditions" key and treats it as an
        # effect-level gate (evaluated at registration, when there may be no attack),
        # but a nested dict's "conditions" survive and are evaluated per-hit as intended.
        trig_spec = params.get("trigger", "ON_HIT")
        if isinstance(trig_spec, dict):
            inner_trigger = (trig_spec.get("trigger_type")
                             or trig_spec.get("trigger") or "ON_HIT")
            inner_conditions_raw = trig_spec.get("conditions", [])
            inner_effects_raw = trig_spec.get("effects", [])
        else:
            inner_trigger = trig_spec
            inner_conditions_raw = params.get("conditions", [])
            inner_effects_raw = params.get("effects", [])
        # scope: COMBAT (default) = fire once, on the current attack ("this attack
        # gains: if it hits ..."). TURN / NEXT_TURN = persistent turn-scoped hook that
        # re-injects onto EVERY attack this turn ("whenever an attack hits a hero this
        # turn ..."); NEXT_TURN activates at the target player's next turn start.
        # player: SELF (default) / OPPONENT — which player's turn the hook lives on.
        scope = (params.get("scope") or "COMBAT").upper()
        player_target = (params.get("player") or "SELF").upper()

        inner_cond_specs = [(ic.get("type", "none"), ic) for ic in inner_conditions_raw]
        inner_eff_specs = [(ie.get("type", "").upper(), ie) for ie in inner_effects_raw]

        def _inject_fn(card, event, state,
                       _trig=inner_trigger,
                       _icond_specs=inner_cond_specs,
                       _ieff_specs=inner_eff_specs,
                       _scope=scope, _pt=player_target,
                       _conds_raw=inner_conditions_raw,
                       _effs_raw=inner_effects_raw):
            from engine.card_effects.triggers import TriggerDef

            _src_slug = getattr(card, "slug", "?")

            def _make_one_shot():
                # Compile inner conditions/effects now, not at module load: it avoids a
                # circular import, and defers any unimplemented inner condition/effect
                # type to when the trigger actually fires (so an unrelated card with an
                # unknown INNER type still loads, matching the inner-effect deferral).
                from engine.card_effects.dsl.condition_types import compile_condition as _cc
                compiled_conds = [_cc(ct, cp) for ct, cp in _icond_specs]
                compiled_effs = [(et, compile_effect(et, ep)) for et, ep in _ieff_specs]

                def _one_shot(c, ev, st, _iconds=compiled_conds, _ieffs=compiled_effs,
                              _src=_src_slug):
                    for cond_fn in _iconds:
                        if cond_fn is not None and not cond_fn(c, ev, st):
                            return
                    for et, eff_fn in _ieffs:
                        eff_fn(c, ev, st)
                        _track_injected_effect(_src, et)
                return _one_shot

            if _scope in ("TURN", "NEXT_TURN", "CHAIN"):
                # Persistent scoped hook: a plain-dict spec that
                # engine._apply_turn_attack_effects re-injects into every attack for
                # the duration. Raw (uncompiled) so snapshot_state stays serializable.
                #   TURN      -> Player.turn_attack_hooks   (cleared end of turn)
                #   NEXT_TURN -> Player.next_turn_attack_hooks (activates next turn)
                #   CHAIN     -> Player.chain_attack_hooks   (cleared at chain close)
                from engine.card_effects.ability_keywords import _controller_id
                cid = _controller_id(card)
                tid = (3 - cid) if _pt in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
                tgt = state.players[tid]
                hook = {"kind": "inject_trigger", "event": _trig,
                        "conditions": _conds_raw, "effects": _effs_raw,
                        "source_slug": _src_slug}
                if _scope == "NEXT_TURN":
                    tgt.next_turn_attack_hooks.append(hook)
                else:
                    (tgt.chain_attack_hooks if _scope == "CHAIN"
                     else tgt.turn_attack_hooks).append(hook)
                    # Cover the current attack too (the source card's own hit): its
                    # _apply_turn_attack_effects already ran before this ON_PLAY, so
                    # inject directly for it.
                    if state.combat is not None and tid == state.active_player:
                        td = TriggerDef(event_type=_trig, condition_fn=None,
                                        effect_fn=_make_one_shot(), is_optional=False)
                        if not hasattr(state.combat, 'injected_triggers'):
                            state.combat.injected_triggers = []
                        state.combat.injected_triggers.append(td)
                return

            # Default COMBAT scope: one-shot into the current combat.
            if not state.combat:
                return
            td = TriggerDef(event_type=_trig, condition_fn=None,
                            effect_fn=_make_one_shot(), is_optional=False)
            if not hasattr(state.combat, 'injected_triggers'):
                state.combat.injected_triggers = []
            state.combat.injected_triggers.append(td)
        return _inject_fn

    if etype == "MODIFY_ATTACKS_THIS_TURN":
        # Persistent turn-scoped attack-power modifier ("until start of your next
        # turn, attacks that target you have -1{p}"; "your attacks this turn get
        # +N"). Applies to every attack for the duration that matches `conditions`.
        # scope: TURN (default) / NEXT_TURN. player: SELF (default) / OPPONENT.
        amount = params.get("amount", 0)
        mod = (params.get("mod") or "add").lower()
        signed = -abs(amount) if mod in ("subtract", "sub", "minus") else amount
        scope = (params.get("scope") or "TURN").upper()
        player_target = (params.get("player") or "SELF").upper()
        # Per-attack filter for WHICH attacks the modifier applies to. Uses "filter"
        # (not "conditions") because the loader pops "conditions" and would evaluate
        # it once at registration; this filter must run per attack.
        conds_raw = params.get("filter", [])

        def _fn(card, event, state, _amt=signed, _scope=scope,
                _pt=player_target, _conds=conds_raw):
            from engine.card_effects.ability_keywords import _controller_id
            cid = _controller_id(card)
            tid = (3 - cid) if _pt in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            tgt = state.players[tid]
            hook = {"kind": "power_mod", "amount": _amt, "conditions": _conds}
            if _scope == "NEXT_TURN":
                tgt.next_turn_attack_hooks.append(hook)
            else:
                tgt.turn_attack_hooks.append(hook)
        return _fn

    if etype == "REVEAL_TOP_DECK":
        # Reveal top N cards; gain gain_life{h} per card with cost >= cost_gte.
        amount = params.get("amount", 1)
        gain_life = params.get("gain_life", 0)
        cost_gte = params.get("cost_gte", None)
        def _fn(card, event, state, _a=amount, _gl=gain_life, _cg=cost_gte):
            from engine.card_effects.ability_keywords import effect_gain_life, _controller_id
            pid = _controller_id(card)
            revealed = state.players[pid].deck.cards[:_a]
            if _gl and _cg is not None:
                matching = sum(1 for c in revealed
                               if (getattr(c, 'cost', None) or 0) >= _cg)
                if matching:
                    effect_gain_life(state, pid, _gl * matching)
        return _fn

    if etype == "PUT_ARSENAL_BOTTOM":
        # Put the target player's arsenal card on the bottom of their deck.
        player_target = params.get("player", "OPPONENT")
        def _fn(card, event, state, _pt=player_target):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import put_object
            cid = _controller_id(card)
            tid = (3 - cid) if _pt.upper() in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            player = state.players[tid]
            arsenal = getattr(player, 'arsenal', None)
            if arsenal and hasattr(arsenal, 'cards') and arsenal.cards:
                card_to_move = arsenal.cards[0]
                # position=None → zone default (append = bottom, cards[-1])
                put_object(state, card_to_move, "deck",
                           destination_player_id=tid, source_player_id=tid,
                           position=None)
        return _fn

    if etype == "DESTROY_TOKEN":
        # Destroy one token of the given slug the ability's controller controls.
        token_slug = params.get("token", "")
        def _fn(card, event, state, _slug=token_slug):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import destroy as _ek_destroy
            player = state.players[_controller_id(card)]
            tok = player.permanents.find(_slug)
            if tok is not None:
                _ek_destroy(state, tok, None)
        return _fn

    if etype in ("DESTROY_PERMANENT", "DESTROY_SELF"):
        target = params.get("target", "self")
        subtype = params.get("subtype")  # "destroy a <subtype> you control" (e.g. Aura)
        def _fn(card, event, state, _t=target, _sub=subtype):
            from engine.effect_keywords import destroy as _ek_destroy
            if _t == "self" and not _sub:
                # destroy() resolves the card's actual zone itself.
                _ek_destroy(state, card, None)
                return
            # Subtype target: destroy a chosen permanent of that subtype the
            # controller controls (e.g. "you may destroy an aura you control").
            # No match -> destroy nothing (a following "if you do" clause should
            # be gated by the CONTROLS_SUBTYPE condition or a MAY so it, too,
            # falls out when there is no legal target).
            from engine.card_effects.ability_keywords import _controller_id, _ask_player
            cid = _controller_id(card)
            want = (_sub or "").lower()
            cands = [c for c in state.players[cid].permanents.cards
                     if want in [s.lower() for s in (getattr(c, "subtypes", None) or [])]]
            if not cands:
                return
            if len(cands) == 1:
                chosen = cands[0]
            else:
                pick = _ask_player(state, cid, [c.slug for c in cands],
                                   context=f"Choose a {_sub} you control to destroy")
                chosen = next((c for c in cands if c.slug == pick), cands[0])
            _ek_destroy(state, chosen, card)
        return _fn

    if etype == "MODIFY_DEFENSE_VALUE":
        amt = params.get("amount", 0)
        def _fn(card, event, state, _a=amt):
            if state.combat:
                state.combat.total_defense = (getattr(state.combat, 'total_defense', 0) or 0) + _a
        return _fn

    if etype == "ADD_DEFEND":
        # Add the ability's source card to the active chain link as a defending
        # card (e.g. Quickdodge Flexors activating from the legs zone). Optional
        # `defense` sets its {d} for this chain link before it is credited to
        # total defense.
        defense = params.get("defense")
        def _fn(card, event, state, _d=defense):
            if not state.combat:
                return
            if _d is not None:
                card.defense = _d
                card.base_defense = _d
            from engine.effect_keywords import add_defend
            add_defend(state, card)
        return _fn

    if etype == "RETURN_DR_FROM_GRAVEYARD":
        # Return a defense reaction card from any graveyard to its owner's hand.
        # Searches controller's graveyard first, then opponent's.
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import put_object
            cid = _controller_id(card)
            for pid in (cid, 3 - cid):
                player = state.players.get(pid)
                if not player:
                    continue
                for c in list(getattr(player.graveyard, 'cards', [])):
                    types = [t.lower() for t in (getattr(c, 'types', None) or [])]
                    subtypes = [st.lower() for st in (getattr(c, 'subtypes', None) or [])]
                    if 'defense reaction' in types or 'defense_reaction' in subtypes:
                        owner_pid = c.owner if c.owner is not None else pid
                        put_object(state, c, "hand",
                                   destination_player_id=owner_pid, source_player_id=pid)
                        return
        return _fn

    if etype == "MODIFY_ATTACK_POWER_PER_UNIQUE_AURA":
        # +N per distinct aura name IN THE ARENA (both players' auras, not just
        # the controller's — Overcrowded reads "among aura tokens in the
        # arena"). stat: "power" (default) applies to attack power; "defense"
        # applies to the defending total, for the "or defends" half.
        per = params.get("per", 1)
        stat = params.get("stat", "power")
        def _fn(card, event, state, _per=per, _stat=stat):
            names = set()
            for pl in state.players.values():
                auras = getattr(pl, "auras", None)
                if auras:
                    names |= {getattr(c, "slug", "") for c in auras.cards}
            n = len(names)
            if not n or state.combat is None:
                return
            if _stat == "defense":
                state.combat.total_defense = (getattr(state.combat, "total_defense", 0) or 0) + n * _per
            else:
                state.combat.attack_power = (state.combat.attack_power or 0) + n * _per
        return _fn

    if etype == "CROWD_BOO":
        player_target = params.get("player", "SELF")
        def _fn(card, event, state, _pt=player_target):
            from engine.card_effects.ability_keywords import effect_crowd_boos, _controller_id
            cid = _controller_id(card)
            tid = (3 - cid) if _pt.upper() in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            effect_crowd_boos(state, tid)
        return _fn

    if etype in ("CROWD_CHEER", "CROWD_CHEERS"):
        # "the crowd cheers you" (CR 8.5.57). Cards used to hand-roll this as
        # SET_FLAG CROWD_CHEERS, which never reached the keyword function, so a
        # cheer was invisible to every other card and to replacement effects.
        # Defaults to SELF — the crowd cheers YOU, mirroring CROWD_BOO.
        player_target = params.get("player", "SELF")
        def _fn(card, event, state, _pt=player_target):
            from engine.card_effects.ability_keywords import effect_crowd_cheers, _controller_id
            cid = _controller_id(card)
            tid = (3 - cid) if _pt.upper() in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            effect_crowd_cheers(state, tid)
        return _fn

    if etype == "DEAL_GENERIC":
        amt = params.get("amount", 0)
        tgt = params.get("target", "OPPONENT")
        def _fn(card, event, state, _a=amt, _t=tgt):
            from engine.card_effects.ability_keywords import _controller_id, effect_deal_damage
            cid = _controller_id(card)
            tid = (3 - cid) if _t.upper() in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            effect_deal_damage(state, tid, _a, card, damage_type="generic")
        return _fn

    if etype == "QUEUE_NEXT_MARKED_DAGGER_HIT_DRAW":
        # Savor Bloodshed: "The next time you hit a marked hero with a dagger this
        # turn, draw a card." Queued as a current-turn flag consumed at the attack
        # step (engine handles next_marked_dagger_hit_draw_N).
        amount = params.get("amount", 1)
        def _fn(card, event, state, _n=amount):
            from engine.card_effects.ability_keywords import _controller_id
            state.players[_controller_id(card)].current_turn_effects.append(
                f"next_marked_dagger_hit_draw_{_n}")
        return _fn

    if etype == "COPY_BANISHED_STEALTH_ATTACK":
        # Take Up the Mantle (marked rider): "you may banish an attack action card
        # with stealth from your graveyard. If you do, the target becomes a copy of
        # the banished card" — copies the banished card's printed profile onto the
        # current attack (name/base stats/keywords/abilities slug).
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import _ask_player, _controller_id
            from engine.effect_keywords import banish as _banish
            cid = _controller_id(card)
            controller = state.players[cid]
            target = state.combat.attack_card if state.combat else None
            if target is None:
                return
            stealth = [c for c in controller.graveyard.cards
                       if 'attack' in [s.lower() for s in (c.subtypes or [])]
                       and any(k.lower() == 'stealth' for k in (c.keywords or []))]
            if not stealth:
                return
            from engine.card_effects.ability_keywords import ask_optional
            pick = ask_optional(state, cid, [c.slug for c in stealth],
                                context="Banish a stealth attack from your graveyard to copy it?")
            if pick is None:
                return
            src = next((c for c in stealth if c.slug == pick), None)
            if src is None:
                return
            _banish(state, src, cid, origin_zone="graveyard")
            # "becomes a copy": adopt the banished card's slug/name/profile so its
            # DSL abilities and printed values apply to the attack. Save the
            # target's printed identity first so the copy can revert: CR 3.0.9 —
            # when the attack leaves the combat chain (an arena zone) into the
            # graveyard it resets to a new object with no relation to its previous
            # existence, i.e. its original card, not the copied one. Without the
            # revert the graveyard keeps a mislabelled duplicate of the copied card.
            _COPY_ATTRS = ("slug", "name", "base_power", "power", "base_defense",
                           "defense", "types", "subtypes", "keywords")
            _orig = {a: getattr(target, a, None) for a in _COPY_ATTRS}
            target.slug = src.slug
            target.name = src.name
            target.base_power = src.base_power
            target.power = src.power
            target.base_defense = src.base_defense
            target.defense = src.defense
            target.types = list(src.types or [])
            target.subtypes = list(src.subtypes or [])
            target.keywords = list(src.keywords or [])

            def _revert_copy(ev, s, _t=target, _o=_orig):
                for attr, val in _o.items():
                    setattr(_t, attr, val)
                s.event_manager.unregister("combat_chain_close", _revert_copy)
            state.event_manager.register("combat_chain_close", _revert_copy)

            from engine.engine import _recalculate_attack_power
            _recalculate_attack_power(state)
        return _fn

    if etype == "DAGGER_DEALS_DAMAGE":
        # "Target dagger you control deals N damage to them. If damage is dealt
        # this way, the dagger has hit." (Pain in the Backside — unlike Flick
        # Knives the dagger is not destroyed, and the active attacking dagger
        # is a legal target.) Registering the hit fires the dagger's own ON_HIT,
        # which is what "the dagger has hit" enables (e.g. marked-dagger draws).
        amount = params.get("amount", 1)
        def _fn(card, event, state, _amt=amount):
            from engine.card_effects.ability_keywords import (
                _controller_id, effect_deal_damage, ask_optional)
            from engine.card_effects.dsl import dispatch as _dsl_dispatch
            cid = _controller_id(card)
            player = state.players[cid]
            daggers = [d for zone in (player.weapon1, player.weapon2) for d in zone.cards
                       if 'dagger' in [s.lower() for s in (getattr(d, 'subtypes', None) or [])]]
            if not daggers:
                return
            pick = ask_optional(state, cid, [d.slug for d in daggers],
                                context="Which dagger you control deals damage?")
            if pick is None:
                return
            dagger = next((d for d in daggers if d.slug == pick), None)
            if dagger is None:
                return
            effect_deal_damage(state, 3 - cid, _amt, dagger, damage_type="generic")
            # "the dagger has hit" — fire its ON_HIT (not destroyed).
            _dsl_dispatch(state, "ON_HIT", dagger.slug, card=dagger, event=None)
        return _fn

    if etype == "DAGGER_DEALS_DAMAGE_AND_DESTROY":
        # Flick Knives: "Target dagger you control that isn't on the active chain
        # link deals N damage to target hero. If damage is dealt this way, the
        # dagger has hit. Destroy the dagger."
        amount = params.get("amount", 1)
        def _fn(card, event, state, _amt=amount):
            from engine.card_effects.ability_keywords import (
                _ask_player, _controller_id, effect_deal_damage)
            from engine.effect_keywords import destroy as _destroy
            from engine.card_effects.dsl import dispatch as _dsl_dispatch
            cid = _controller_id(card)
            player = state.players[cid]
            active = state.combat.attack_card if state.combat else None
            daggers = [d for zone in (player.weapon1, player.weapon2) for d in zone.cards
                       if d is not active
                       and 'dagger' in [s.lower() for s in (getattr(d, 'subtypes', None) or [])]]
            if not daggers:
                return
            from engine.card_effects.ability_keywords import ask_optional
            pick = ask_optional(state, cid, [d.slug for d in daggers],
                                context="Which dagger you control deals damage?")
            if pick is None:
                return
            dagger = next((d for d in daggers if d.slug == pick), None)
            if dagger is None:
                return
            effect_deal_damage(state, 3 - cid, _amt, dagger, damage_type="generic")
            # "the dagger has hit" — fire its ON_HIT; then destroy it.
            _dsl_dispatch(state, "ON_HIT", dagger.slug, card=dagger, event=None)
            _destroy(state, dagger, card)
        return _fn

    if etype == "STEAL_AURA_TOKEN":
        token_slug = params.get("token", "")
        def _fn(card, event, state, _slug=token_slug):
            from engine.card_effects.ability_keywords import effect_steal_token, _controller_id
            cid = _controller_id(card)
            effect_steal_token(state, cid, 3 - cid)
        return _fn

    if etype == "RETRIEVE_DAGGER":
        # Pay 1{r} to retrieve a dagger from your graveyard into the appropriate weapon slot.
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import retrieve
            cid = _controller_id(card)
            player = state.players[cid]
            daggers = [c for c in player.graveyard.cards
                       if "dagger" in [s.lower() for s in (getattr(c, 'subtypes', None) or [])]]
            if not daggers or player.resources < 1:
                return
            retrieve(state, daggers[0], cid, chose_to_pay=True)
        return _fn

    if etype == "DESTROY_ARSENAL":
        # Destroy the target player's arsenal card.
        player_target = params.get("player", "OPPONENT")
        def _fn(card, event, state, _pt=player_target):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import destroy
            cid = _controller_id(card)
            tid = (3 - cid) if _pt.upper() in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            player = state.players[tid]
            for c in list(getattr(player.arsenal, 'cards', [])):
                destroy(state, c, None)
        return _fn

    # ── new canonical effect types ─────────────────────────────────────────

    if etype == "CLASH":
        # "Clash with the attacking hero", optionally repeated, with role-based
        # outcome effects. opponent: ATTACKING_HERO (default) → the attacker in
        # combat, else the plain opponent. Outcome specs are small dicts:
        #   {"action": "create_token"|"discard", "who": ROLE, ...}
        # ROLE ∈ WINNER, LOSER, SWEEPER, SELF, OPPONENT.
        opponent_kind = params.get("opponent", "ATTACKING_HERO").upper()
        repeat = params.get("repeat", 1)
        reveal_dest = params.get("reveal_dest", "top").lower()
        on_winner = params.get("on_winner", [])
        on_loser = params.get("on_loser", [])
        on_sweep = params.get("on_sweep", [])

        def _run_outcome(spec, state, role_players):
            who = spec.get("who", "SELF").upper()
            pid = role_players.get(who)
            if pid is None:
                return
            action = spec.get("action", "")
            if action == "create_token":
                from engine.effect_keywords import create_token as _ct
                _ct(state, target_player_id=pid, token_slug=spec.get("token", ""),
                    number=spec.get("number", 1))
            elif action == "discard":
                from engine.card_effects.ability_keywords import effect_discard
                effect_discard(state, pid, count=spec.get("amount", 1),
                               random_discard=spec.get("random", True))

        def _fn(card, event, state, _opp=opponent_kind, _rep=repeat, _rd=reveal_dest,
                _ow=on_winner, _ol=on_loser, _os=on_sweep):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import clash as _clash
            cid = _controller_id(card)
            if _opp == "ATTACKING_HERO" and state.combat is not None:
                opp = state.combat.attacker_id
            else:
                opp = 3 - cid
            winners = []
            for _ in range(_rep):
                ev = _clash(state, cid, opp)
                winner = ev.winner_id
                winners.append(winner)
                revealed = {cid: ev.card1, opp: ev.card2}
                loser = None
                if winner is not None:
                    loser = opp if winner == cid else cid
                roles = {"SELF": cid, "OPPONENT": opp,
                         "WINNER": winner, "LOSER": loser}
                if winner is not None:
                    for spec in _ow:
                        _run_outcome(spec, state, roles)
                    for spec in _ol:
                        _run_outcome(spec, state, roles)
                # Move revealed cards to the bottom between clashes if instructed.
                if _rd == "bottom":
                    for pid_, rc in revealed.items():
                        if rc is not None:
                            owner = state.players[rc.owner]
                            if rc in owner.deck.cards:
                                owner.deck.cards.remove(rc)
                                owner.deck.add_bottom(rc)
            # Sweep: one hero won every clash.
            if _os and _rep >= 2 and winners and all(w == winners[0] and w is not None
                                                     for w in winners):
                sweeper = winners[0]
                roles = {"SELF": cid, "OPPONENT": opp, "SWEEPER": sweeper,
                         "WINNER": sweeper, "LOSER": (opp if sweeper == cid else cid)}
                for spec in _os:
                    _run_outcome(spec, state, roles)
        return _fn

    if etype == "PAY_OR_DAMAGE":
        # "Deals N damage to you unless you pay {r}..." — the controller may pay
        # the resources to avoid the damage (e.g. Bloodrot Pox). Also models the
        # payoff form "you may pay {r}. If you do, X" (damage 0 + on_success).
        #
        # The pay amount is authored under "resources", "resource_cost",
        # "resource", or "amount". "resource" is sometimes a resource *name*
        # ("RESOURCE_POINTS") rather than a quantity, in which case the quantity
        # lives in "amount" — taking the name as the amount raised a TypeError
        # on the `>=` below, so only numeric values are accepted as the cost.
        def _first_num(*keys):
            for k in keys:
                v = params.get(k)
                if isinstance(v, bool):
                    continue
                if isinstance(v, int) or isinstance(v, float):
                    return v
                if isinstance(v, str):
                    try:
                        return int(v)
                    except ValueError:
                        continue
            return 0
        resources = _first_num("resources", "resource_cost", "resource", "amount")
        dmg = params.get("damage", 0)
        if not isinstance(dmg, (int, float)) or isinstance(dmg, bool):
            dmg = 0
        # Compiled eagerly so a bad on_success spec fails at JSON load time like
        # every other effect, instead of raising mid-game only for the players
        # who choose to pay.
        on_success = [compile_effect((e.get("type") or "").upper(),
                                     {k: v for k, v in e.items() if k != "type"})
                      for e in (params.get("on_success") or [])]
        def _fn(card, event, state, _r=resources, _d=dmg, _win=on_success):
            from engine.card_effects.ability_keywords import (
                _ask_player, _controller_id, effect_deal_damage)
            cid = _controller_id(card)
            player = state.players[cid]
            # Paying buys nothing when there is no damage to avoid and no
            # payoff — don't offer a prompt that can only waste resources.
            if _d <= 0 and not _win:
                return
            paid = False
            if player.resources >= _r:
                choice = _ask_player(state, cid, ["pay", "take_damage"],
                                     context=f"Pay {_r} to avoid {_d} damage?")
                if str(choice) == "pay":
                    player.resources -= _r
                    paid = True
            if paid:
                for fn in _win:
                    if fn is not None:
                        fn(card, event, state)
            else:
                effect_deal_damage(state, cid, _d, card, damage_type="generic")
        return _fn

    if etype == "PAY_OR_ELSE":
        # "<player> discards a card unless they pay N" (generic: pay N resources or
        # else run on_failure). `player` picks who pays/suffers (SELF default /
        # OPPONENT). on_failure is a list of effect specs resolved when unpaid; their
        # own `player` params are relative to the SAME source card, so e.g. a DISCARD
        # with player=OPPONENT hits the same target that was asked to pay.
        # The cost is normally resources, but "destroy this UNLESS you remove a
        # steam counter from it" pays in counters instead — set counter_type and
        # the amount comes from `amount` (the recurring Crank/steam pattern).
        counter_type = params.get("counter_type") or params.get("counter")
        if counter_type:
            resources = 0
            counters_due = int(params.get("amount", 1) or 1)
        else:
            resources = params.get("resources", params.get("amount", 0))
            counters_due = 0
        player_target = (params.get("player") or "SELF").upper()
        # Eager, so a bad on_failure spec fails at load like every other effect
        # rather than only for the players who decline.
        on_fail = [compile_effect((e.get("type") or "").upper(),
                                  {k: v for k, v in e.items() if k != "type"})
                   for e in params.get("on_failure", [])]

        def _fn(card, event, state, _r=resources, _pt=player_target, _fail=on_fail,
                _ct=counter_type, _cn=counters_due):
            from engine.card_effects.ability_keywords import (
                _ask_player, _controller_id, effect_remove_counter)
            cid = _controller_id(card)
            tid = (3 - cid) if _pt in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            player = state.players[tid]
            paid = False
            if _ct:
                have = player.counters.get((card.slug, card.zone, _ct), 0)
                if have >= _cn:
                    choice = _ask_player(
                        state, tid, ["pay", "decline"],
                        context=f"Remove {_cn} {_ct} counter(s) to avoid the effect?")
                    if str(choice) == "pay":
                        effect_remove_counter(state, card, _ct, _cn)
                        paid = True
            elif _r > 0 and player.resources >= _r:
                choice = _ask_player(state, tid, ["pay", "decline"],
                                     context=f"Pay {_r} to avoid the effect?")
                if str(choice) == "pay":
                    player.resources -= _r
                    paid = True
            if not paid:
                for fn in _fail:
                    if fn is not None:
                        fn(card, event, state)
        return _fn

    if etype == "PUT_CARDS_BOTTOM":
        # Put all cards from the given zones on the bottom of the controller's
        # deck (e.g. Inertia token: hand + arsenal → bottom of deck).
        from_zones = params.get("from_zones", ["hand", "arsenal"])
        def _fn(card, event, state, _zones=from_zones):
            from engine.card_effects.ability_keywords import _controller_id
            player = state.players[_controller_id(card)]
            for zone_name in _zones:
                zone = getattr(player, zone_name, None)
                if zone is None:
                    continue
                for c in list(zone.cards):
                    zone.remove(c)
                    player.deck.add_bottom(c)
        return _fn

    # ── composable primitives ──────────────────────────────────────────────
    # These exist so a card sentence can be assembled in JSON instead of
    # compiled into one Python function named after the card. See
    # engine/context.py for how "into"/"ref" are scoped.

    if etype == "LOOK_AT":
        # Look at cards without moving them, storing them under "into" for a
        # later effect to act on. Unlike LOOK this does NOT pop cards out of
        # the deck — the card stays put until something acts on the ref.
        #   zone:   DECK_TOP (default) | ARSENAL | HAND
        #   player: OPPONENT (default) | SELF
        #   amount: how many (default 1) or "ALL"; a single card (amount 1, no
        #           filter) is stored unwrapped, otherwise a list
        #   filter: optional {keyword, face_down, subtype} — a filter always
        #           scans the whole zone and always stores a list
        zone = params.get("zone", "DECK_TOP").upper()
        who = params.get("player", "OPPONENT").upper()
        amount = params.get("amount", 1)
        into = params.get("into", "looked")
        filt = params.get("filter") or {}
        def _fn(card, event, state, _z=zone, _w=who, _n=amount, _into=into, _f=filt):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.context import set_ref
            cid = _controller_id(card)
            tid = (3 - cid) if _w in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            player = state.players[tid]
            zone_map = {"DECK_TOP": player.deck, "ARSENAL": getattr(player, "arsenal", None),
                        "HAND": player.hand}
            z = zone_map.get(_z)
            source = list(getattr(z, "cards", []) if z is not None else [])
            if _f:
                # A filter examines the whole zone, not just the top slice.
                kw = _f.get("keyword")
                sub = _f.get("subtype")
                want_fd = _f.get("face_down")
                def _ok(c):
                    if kw and not any(k.lower() == kw.lower() for k in (c.keywords or [])):
                        return False
                    if sub and sub.lower() not in [s.lower() for s in (c.subtypes or [])]:
                        return False
                    if want_fd is not None and bool(getattr(c, "is_public", False)) == bool(want_fd):
                        return False
                    return True
                pool = [c for c in source if _ok(c)]
                set_ref(_into, pool)
            elif str(_n).upper() == "ALL":
                set_ref(_into, source)
            else:
                pool = source[:_n]
                set_ref(_into, pool[0] if _n == 1 and pool else (pool if _n != 1 else None))
            set_ref(_into + "_owner", tid)
        return _fn

    if etype == "DESTROY_REF":
        # Destroy whatever a previous effect stored under "ref".
        ref = params.get("ref", "looked")
        def _fn(card, event, state, _r=ref):
            from engine.context import get_ref
            from engine.effect_keywords import destroy as _ek_destroy
            target = get_ref(_r)
            if target is None:
                return
            for obj in (target if isinstance(target, list) else [target]):
                _ek_destroy(state, obj, card)
        return _fn

    if etype == "MOVE_REF":
        # Move a referenced card to a zone.
        #   ref:      what to move
        #   to_zone:  destination zone name (e.g. "deck", "hand", "graveyard")
        #   position: "top" | "bottom" (default) — only meaningful for the deck
        #   player:   SELF | OPPONENT | OWNER (default) — whose zone
        ref = params.get("ref", "looked")
        to_zone = params.get("to_zone", "deck")
        position = params.get("position", "bottom")
        who = params.get("player", "OWNER").upper()
        def _fn(card, event, state, _r=ref, _z=to_zone, _pos=position, _w=who):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import put_object
            from engine.context import get_ref
            target = get_ref(_r)
            if not target:
                return
            cid = _controller_id(card)
            for obj in (target if isinstance(target, list) else [target]):
                if _w == "OWNER":
                    dest_pid = obj.owner
                elif _w in ("OPPONENT", "DEFENDING", "DEFENDER"):
                    dest_pid = 3 - cid
                else:
                    dest_pid = cid
                put_object(state, obj, _z, destination_player_id=dest_pid,
                           source_player_id=cid,
                           position=("top" if str(_pos).lower() == "top" else None))
        return _fn

    if etype == "PUT_COUNTER_REF":
        # Put counters on a referenced card (vs PUT_COUNTER, which targets the
        # ability's own source).
        ref = params.get("ref", "chosen")
        counter_type = params.get("counter_type", "power")
        amount = params.get("amount", 1)
        def _fn(card, event, state, _r=ref, _ct=counter_type, _a=amount):
            from engine.card_effects.ability_keywords import effect_put_counter
            from engine.context import get_ref
            target = get_ref(_r)
            if not target:
                return
            for obj in (target if isinstance(target, list) else [target]):
                for _ in range(_a):
                    effect_put_counter(state, obj, _ct)
        return _fn

    if etype == "FLIP_REF":
        # Turn a referenced face-down card face-up (or vice versa). Arsenal and
        # banished-face-down cards track visibility via is_public.
        ref = params.get("ref", "chosen")
        face_up = params.get("face_up", True)
        def _fn(card, event, state, _r=ref, _up=face_up):
            from engine.context import get_ref
            target = get_ref(_r)
            if not target:
                return
            for obj in (target if isinstance(target, list) else [target]):
                obj.is_public = bool(_up)
                if hasattr(obj, "face_down"):
                    obj.face_down = not bool(_up)
        return _fn

    if etype == "SELECT_FROM_REF":
        # Choose a subset of a referenced list of cards.
        #   ref:       list to choose from
        #   mode:      SAME_NAME — pick a name, take every copy of it (the
        #              "banish 1 or more cards with the same name" pattern)
        #              ANY       — pick individual cards, up to `max`
        #   min/max:   how many to take (ANY mode)
        #   into:      where the chosen cards go
        #   rest_into: the complement, so a later effect can act on "the rest"
        #              without recomputing the difference
        ref = params.get("ref", "looked")
        mode = params.get("mode", "ANY").upper()
        want_min = params.get("min", 1)
        want_max = params.get("max")
        into = params.get("into", "chosen")
        rest_into = params.get("rest_into")
        def _fn(card, event, state, _r=ref, _m=mode, _min=want_min,
                _max=want_max, _into=into, _rest=rest_into):
            from engine.card_effects.ability_keywords import _ask_player, _controller_id, STOP
            from engine.context import get_ref, set_ref
            pool = get_ref(_r) or []
            if not isinstance(pool, list):
                pool = [pool]
            pool = list(pool)
            cid = _controller_id(card)
            chosen: list = []
            if _m == "SAME_NAME":
                groups: dict = {}
                for c in pool:
                    groups.setdefault(c.name, []).append(c)
                if groups:
                    options = list(groups)
                    pick = _ask_player(state, cid, options,
                                       context="Select all copies of which name?")
                    chosen = list(groups[pick if pick in groups else options[0]])
            else:
                limit = _max if _max is not None else len(pool)
                remaining = list(pool)
                while remaining and len(chosen) < limit:
                    options = [c.slug for c in remaining]
                    if len(chosen) >= _min:
                        options = options + [STOP]
                    pick = _ask_player(state, cid, options, context="Select a card")
                    if pick == STOP:
                        break
                    target = next((c for c in remaining if c.slug == pick), remaining[0])
                    remaining.remove(target)
                    chosen.append(target)
            set_ref(_into, chosen)
            if _rest:
                set_ref(_rest, [c for c in pool if c not in chosen])
        return _fn

    if etype in ("PUT_REF_BOTTOM", "PUT_REF_TOP"):
        # Put a referenced card (or list) on the bottom/top of a deck — the common
        # "then put it on the bottom of your deck" rider after a look/reveal. A thin
        # convenience over MOVE_REF's deck path (which many authors reach for by name).
        ref = params.get("ref", "looked")
        pos = "top" if etype == "PUT_REF_TOP" else "bottom"
        who = params.get("player", "OWNER").upper()
        def _fn(card, event, state, _r=ref, _pos=pos, _w=who):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import put_object
            from engine.context import get_ref
            target = get_ref(_r)
            if not target:
                return
            cid = _controller_id(card)
            for obj in (target if isinstance(target, list) else [target]):
                if _w == "OWNER":
                    dest_pid = obj.owner
                elif _w in ("OPPONENT", "DEFENDING", "DEFENDER"):
                    dest_pid = 3 - cid
                else:
                    dest_pid = cid
                put_object(state, obj, "deck", destination_player_id=dest_pid,
                           source_player_id=cid,
                           position=("top" if _pos == "top" else None))
        return _fn

    if etype == "TAP_REF":
        # Tap (or, with untap:true, untap) a referenced card — "tap target ...".
        ref = params.get("ref", "chosen")
        untap = params.get("untap", False)
        def _fn(card, event, state, _r=ref, _u=untap):
            from engine.context import get_ref
            target = get_ref(_r)
            if not target:
                return
            for obj in (target if isinstance(target, list) else [target]):
                obj.tapped = not bool(_u)
        return _fn

    if etype in ("CONDITIONAL", "CONDITIONAL_EFFECT", "IF"):
        # Branch: run `then` effects if every `when` condition holds, else `else`.
        # Use "when" for the test (NOT "conditions" — the loader pops that key and
        # turns it into an effect-level gate, which would skip the whole branch and
        # never reach `else`). Inner specs are compiled lazily so an unimplemented
        # inner type defers to fire-time rather than breaking load.
        when_raw = params.get("when", params.get("if", []))
        then_raw = params.get("then", params.get("effects", []))
        else_raw = params.get("else", params.get("else_effects", []))
        def _fn(card, event, state, _w=when_raw, _t=then_raw, _e=else_raw):
            from engine.card_effects.dsl.condition_types import compile_condition as _cc
            ok = True
            for c in _w:
                fn = _cc((c.get("type") or "none"), c)
                if fn is not None and not fn(card, event, state):
                    ok = False
                    break
            for spec in (_t if ok else _e):
                compile_effect((spec.get("type") or "").upper(), spec)(card, event, state)
        return _fn

    if etype == "BANISH_REF":
        # Banish whatever a previous effect stored under "ref". Goes through the
        # canonical banish keyword (CR 8.5.1) so the event fires and replacement
        # effects can intercept it.
        # origin_zone must be passed or banish() leaves the card in place: it
        # only removes from the origin when told which one. LOOK_AT peeks
        # without moving cards, so unlike the old LOOK-then-banish pairing the
        # card is still in its zone when we get here.
        ref = params.get("ref", "chosen")
        origin = params.get("from_zone")
        def _fn(card, event, state, _r=ref, _origin=origin):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.context import get_ref
            from engine.effect_keywords import banish as _ek_banish
            target = get_ref(_r)
            if not target:
                return
            cid = _controller_id(card)
            for obj in (target if isinstance(target, list) else [target]):
                zone = _origin or getattr(obj, "zone", None)
                _ek_banish(state, obj, cid, origin_zone=zone)
        return _fn

    if etype == "REORDER_REF":
        # "Put the rest on top of their deck in any order." The controller
        # orders the referenced cards; the first chosen ends up on top.
        ref = params.get("ref", "rest")
        who = params.get("player", "OPPONENT").upper()
        def _fn(card, event, state, _r=ref, _w=who):
            from engine.card_effects.ability_keywords import _ask_player, _controller_id
            from engine.context import get_ref
            cards = get_ref(_r) or []
            if not isinstance(cards, list) or len(cards) < 1:
                return
            cid = _controller_id(card)
            tid = (3 - cid) if _w in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            deck = state.players[tid].deck
            remaining = [c for c in cards if c in deck.cards]
            if not remaining:
                return
            ordered = []
            while remaining:
                if len(remaining) == 1:
                    ordered.append(remaining.pop())
                    break
                pick = _ask_player(state, cid, [c.slug for c in remaining],
                                   context="Choose the next card to place on top")
                target = next((c for c in remaining if c.slug == pick), remaining[0])
                remaining.remove(target)
                ordered.append(target)
            for c in ordered:
                deck.cards.remove(c)
            for c in reversed(ordered):
                c.zone = "deck"
                deck.cards.insert(0, c)
        return _fn

    if etype == "MAY":
        # "You may X. If you do, Y." — an optional block of sub-effects.
        #
        # Conditions gate whether the choice is offered at all; declining runs
        # nothing in the block, which is what makes "if you do" fall out for
        # free rather than needing its own conditional plumbing.
        # A "conditions" list on the MAY itself is popped by the loader into
        # EffectDef.conditions, so it already gates whether this effect runs at
        # all — the prompt is not even offered when it fails. Sub-effects are
        # compiled here, so their own "conditions" must be honoured explicitly;
        # compiling them without this would silently drop the gate.
        prompt = params.get("prompt", "Use this optional ability?")
        # A single sub-effect is often authored as "effect": {...} instead of
        # the list form; without this the block compiled empty and accepting
        # the prompt did nothing at all.
        sub_specs = params.get("effects") or []
        if not sub_specs and isinstance(params.get("effect"), dict):
            sub_specs = [params["effect"]]
        from engine.card_effects.dsl.condition_types import compile_condition
        subs = []
        for spec in sub_specs:
            sub_params = {k: v for k, v in spec.items() if k != "type"}
            gate_specs = sub_params.pop("conditions", []) or []
            gates = [compile_condition(g.get("type", "").upper(),
                                       {k: v for k, v in g.items() if k != "type"})
                     for g in gate_specs]
            subs.append((compile_effect(spec.get("type", "").upper(), sub_params), gates))

        def _fn(card, event, state, _s=subs, _p=prompt):
            from engine.card_effects.ability_keywords import ask_yes_no, _controller_id
            cid = _controller_id(card)
            if not ask_yes_no(state, cid, context=_p):
                return
            for fn, gates in _s:
                if fn is None:
                    continue
                if all(g is None or g(card, event, state) for g in gates):
                    fn(card, event, state)
        return _fn

    if etype == "TRANSFORM_HERO":
        # Arakni: "become a random Agent of Chaos" / "return to the brood".
        # choose=true lets the controller pick the form (e.g. Mask of Deceit when
        # the attacking hero is marked) instead of a random one.
        mode = params.get("mode", "random_agent_of_chaos").lower()
        choose = params.get("choose", False)
        def _fn(card, event, state, _m=mode, _ch=choose):
            from engine.card_effects.ability_keywords import (
                _controller_id, become_agent_of_chaos, return_to_brood)
            pid = _controller_id(card)
            if _m == "return_to_brood":
                return_to_brood(state, pid)
            else:
                become_agent_of_chaos(state, pid, choose=_ch)
        return _fn

    if etype == "SET_BASE_POWER":
        # "Target attack action card you control has N base {p}" (e.g. Kayo).
        # The target is an attack action card the controller controls in the
        # current combat — the active attack OR a card they're defending with.
        # If several qualify, the controller chooses. Only attack ACTION cards
        # qualify (no weapons).
        amount = params.get("amount", 0)
        def _fn(card, event, state, _amt=amount):
            from engine.card_effects.ability_keywords import (
                _controller_id, controlled_attack_action_cards, _ask_player)
            if not state.combat:
                return
            cid = _controller_id(card)
            candidates = controlled_attack_action_cards(state, cid)
            if not candidates:
                return
            # Prefer the target declared at activation (CR 5.1.4) if it is a
            # legal candidate; otherwise use the sole candidate or ask.
            declared = getattr(event, 'target', None) if event is not None else None
            target = next((c for c in candidates if c is declared), None)
            if target is None:
                if len(candidates) == 1:
                    target = candidates[0]
                else:
                    pick = _ask_player(state, cid, [c.slug for c in candidates],
                                       context="Choose the attack action card to set to "
                                               f"{_amt} base power")
                    target = next((c for c in candidates if c.slug == pick), candidates[0])
            target.base_power = _amt
            # When the target is the active attack, recalculate rather than
            # overwrite: setting BASE power (stage 7) must leave later "+{p}"
            # modifiers (stage 8, e.g. Reckless Arithmetic's rolled +X on
            # power_mods) applied on top. Base 6 + rolled 3 = 9, not 6.
            if target is state.combat.attack_card:
                state.combat.base_attack_power = _amt
                from engine import engine as _E
                _E._recalculate_attack_power(state)
        return _fn

    if etype == "MODIFY_ATTACK":
        mod = params.get("mod", "add")
        amt = params.get("amount", 0)
        def _fn(card, event, state, _mod=mod, _a=amt):
            if not state.combat:
                return
            val = _resolve_amount(_a, state)
            # WHILE_STATIC abilities re-run this on every _recalculate_attack_power
            # (event type 'recalculate_attack_power'); those must apply transiently
            # in the stage-8 window and NOT accumulate on power_mods.
            if getattr(event, "type", None) == "recalculate_attack_power":
                if _mod == "set":
                    state.combat.attack_power = val
                elif _mod == "multiply":
                    state.combat.attack_power = (state.combat.attack_power or 0) * val
                else:
                    state.combat.attack_power = (state.combat.attack_power or 0) + val
                return
            # One-shot trigger (e.g. Reckless Arithmetic's "when this attacks,
            # +X{p}"): record on the CombatState so it is re-applied on every
            # future recalculation and survives the defend/damage steps (the
            # amount is fixed now, e.g. the rolled X), AND apply it to the live
            # power now for immediate visibility. A later recalc re-derives from
            # base + power_mods, so this immediate bump is not double-counted.
            state.combat.power_mods.append((_mod, val))
            if _mod == "set":
                state.combat.attack_power = val
            elif _mod == "multiply":
                state.combat.attack_power = (state.combat.attack_power or 0) * val
            else:
                state.combat.attack_power = (state.combat.attack_power or 0) + val
        return _fn

    if etype == "DOUBLE_BASE_POWER":
        # "This card's base {p} is doubled." Modeled as adding the current base
        # power to the attack (doubling base = +base to the total). Authored as a
        # WHILE_STATIC so it re-applies on every recalculation and stacks on top of
        # a SET-base effect in timestamp order — e.g. Kayo sets base 6, then this
        # adds 6 → 12. Gate with SOURCE_IS_ATTACK so it only affects this card's
        # own attack.
        def _fn(card, event, state):
            combat = state.combat
            if not combat or not combat.attack_card:
                return
            base = combat.attack_card.base_power or 0
            combat.attack_power = (combat.attack_power or 0) + base
        return _fn

    if etype == "CREATE_MIGHT_PER_GOLD":
        # Visit the Goldmane Estate: "if you control 3 or more Gold, create that
        # many Might tokens." Counts real Gold tokens AND permanents that count as
        # a Gold (subtype match, e.g. Aurum Aegis).
        threshold = params.get("threshold", 3)
        def _fn(card, event, state, _th=threshold):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import create_token as _ct
            cid = _controller_id(card)
            player = state.players[cid]
            n = 0
            for zn in ('permanents', 'head', 'chest', 'arms', 'legs',
                       'weapon1', 'weapon2'):
                z = getattr(player, zn, None)
                if not z:
                    continue
                for t in z.cards:
                    if (getattr(t, 'slug', '') == 'gold'
                            or 'gold' in [s.lower() for s in (getattr(t, 'subtypes', None) or [])]):
                        n += 1
            if n >= _th:
                _ct(state, target_player_id=cid, token_slug='might', number=n)
        return _fn

    if etype == "REVEAL_REVILED_FROM_INVENTORY":
        # Outside Interference: "You may reveal a Reviled attack action card from
        # your inventory and put it into your hand."
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import _ask_player, _controller_id
            cid = _controller_id(card)
            controller = state.players[cid]
            inv = getattr(controller, 'inventory', None)
            if inv is None:
                return
            reviled = [c for c in inv.cards
                       if 'reviled' in [t.lower() for t in (c.types or [])]
                       and 'attack' in [s.lower() for s in (c.subtypes or [])]]
            if not reviled:
                return
            from engine.card_effects.ability_keywords import ask_optional
            pick = ask_optional(state, cid, [c.slug for c in reviled],
                                context="Reveal a Reviled attack action from your inventory?")
            if pick is None:
                return
            target = next((c for c in reviled if c.slug == pick), reviled[0])
            inv.remove(target)
            target.is_public = True
            controller.hand.add(target)
        return _fn

    if etype == "BANISH_OPP_TOP_GRANT_PLAY":
        # Infiltrate: "banish the top card of their deck. You may play it until
        # the end of your next turn." The banished card is the opponent's; the
        # attacker (this card's controller) may play it from banish. The exact
        # two-turn deadline is approximated by the start-of-turn clear of
        # playable_from_banished.
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import banish as _banish
            cid = _controller_id(card)
            opp = state.players[3 - cid]
            if not opp.deck.cards:
                return
            top = opp.deck.cards[0]
            _banish(state, top, cid, origin_zone="deck")
            if top in opp.banished.cards:
                state.players[cid].playable_from_banished.append(top)
        return _fn

    if etype == "BANISH_TRAP_FROM_GRAVEYARD_PLAYABLE":
        # Under the Trap-Door: "Banish target trap from your graveyard. If you do,
        # you may play it this turn, and if it would be put into the graveyard
        # this turn, instead banish it." The graveyard->banish rider IS modeled
        # below via the gy_to_banish_<object_id> flag that engine._to_graveyard
        # honours (an earlier version of this comment wrongly said it was not).
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import _ask_player, _controller_id
            from engine.effect_keywords import banish as _banish
            cid = _controller_id(card)
            controller = state.players[cid]
            traps = [c for c in controller.graveyard.cards
                     if "trap" in [s.lower() for s in (c.subtypes or [])]]
            if not traps:
                return
            from engine.card_effects.ability_keywords import ask_optional
            pick = ask_optional(state, cid, [c.slug for c in traps],
                                context="Banish a trap from your graveyard to play it this turn?")
            if pick is None:
                return
            target = next((c for c in traps if c.slug == pick), None)
            if target is None:
                return
            _banish(state, target, cid, origin_zone="graveyard")
            if target in controller.banished.cards:
                controller.playable_from_banished.append(target)
                # "if it would be put into the graveyard this turn, instead banish
                # it" — engine._to_graveyard honours this per-card, turn-scoped flag.
                controller.current_turn_effects.append(f"gy_to_banish_{target.object_id}")
        return _fn

    if etype == "REDUCE_TOKEN_CREATION_THIS_TURN":
        # Ripple Away: "If an action card effect would create 1 or more tokens this
        # turn, instead it creates that many minus 1 of each of those tokens."
        # Registers a turn-scoped replacement that decrements CreateTokenEvent.number.
        def _fn(card, event, state):
            from engine.effects import ReplacementEffect, ReplacementType
            from engine.card_effects.ability_keywords import _controller_id
            cid = _controller_id(card)
            controller = state.players[cid]
            flag = "ripple_away_active"
            if flag not in controller.current_turn_effects:
                controller.current_turn_effects.append(flag)
            def _cond(ev, s, _cid=cid, _flag=flag):
                if not (isinstance(ev, dict) and 'target_player_id' in ev
                        and (ev.get('number') or 0) >= 1
                        and _flag in s.players[_cid].current_turn_effects):
                    return False
                # Only "an action card effect" — check the card whose ability is
                # currently creating the token.
                from engine.context import current_effect_source
                src = current_effect_source()
                return src is not None and 'Action' in (getattr(src, 'types', None) or [])
            def _repl(ev, s):
                ev['number'] = max(0, (ev.get('number') or 0) - 1)
                return ev
            state.effect_manager.add_replacement(ReplacementEffect(
                source_card=card, replacement_type=ReplacementType.STANDARD,
                condition_fn=_cond, replace_fn=_repl, owner_id=cid))
        return _fn

    if etype == "MAY_DESTROY_SILVERS_TO_EQUIP":
        # Blacktek Whisperers graveyard static: "you may destroy N Silvers you
        # control. If you do, equip this (from the graveyard)."
        amount = params.get("amount", 2)
        def _fn(card, event, state, _n=amount):
            from engine.card_effects.ability_keywords import _ask_player, _controller_id
            from engine.effect_keywords import destroy as _destroy, equip as _equip
            cid = _controller_id(card)
            player = state.players[cid]
            silvers = [t for zn in ('permanents', 'items', 'tokens')
                       for t in getattr(player, zn, player.permanents).cards
                       if getattr(t, 'slug', '') == 'silver']
            # de-dupe (items can be a view of permanents)
            seen, uniq = set(), []
            for s in silvers:
                if id(s) not in seen:
                    seen.add(id(s)); uniq.append(s)
            if len(uniq) < _n:
                return
            from engine.card_effects.ability_keywords import ask_yes_no
            if not ask_yes_no(state, cid,
                              context=f"Destroy {_n} Silvers to equip Blacktek Whisperers?"):
                return
            for s in uniq[:_n]:
                _destroy(state, s, card)
            slot = next((sl for sl in ("head", "chest", "arms", "legs")
                         if sl.title() in (card.subtypes or [])), "arms")
            _equip(state, card, slot, cid)
        return _fn

    if etype == "GRANT_SUBTYPE":
        # "This counts as a <subtype>" (e.g. Aurum Aegis counts as a Gold). Adds
        # the subtype to this card so subtype-aware checks (CONTROLS_TOKEN_TYPE)
        # see it. Applied on equip; the subtype persists while the card is in play.
        subtype = params.get("subtype", "")
        def _fn(card, event, state, _sub=subtype):
            if not _sub:
                return
            subs = list(card.subtypes or [])
            if _sub not in subs:
                subs.append(_sub)
                card.subtypes = subs
        return _fn

    if etype == "RESTRICT_DEFENSE_TO_HEAD_EQUIPMENT":
        # Headbutt: "This can't be defended by non-head equipment." Set on the
        # active combat while this card attacks; get_defendable_cards honours it.
        def _fn(card, event, state):
            if state.combat is not None:
                state.combat.head_equipment_only = True
        return _fn

    if etype == "CRUSH_MINUS_DEF_OPP_HEAD":
        # Headbutt's Crush: "put a -1{d} counter on a head they have equipped,
        # then if it has 0{d}, destroy it." Applies to the defending hero's head.
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import destroy as _destroy
            opp = state.players[3 - _controller_id(card)]
            head = opp.head.cards[0] if opp.head.cards else None
            if head is None:
                return
            head.counters["minus_defense"] = head.counters.get("minus_defense", 0) + 1
            head.defense = (head.defense or 0) - 1
            head.base_defense = (head.base_defense or 0) - 1
            if (head.defense or 0) <= 0:
                _destroy(state, head, card)
        return _fn

    if etype == "MODIFY_ATTACK_PER_HIGH_DEFENDER":
        # Show of Strength: "This gets -1{p} for each card with 6 or more {p}
        # defending it." Authored as a WHILE_STATIC, so it re-evaluates each
        # recalculation as defenders are declared. Gate with SOURCE_IS_ATTACK.
        per = params.get("amount", -1)
        threshold = params.get("threshold", 6)
        def _fn(card, event, state, _per=per, _th=threshold):
            combat = state.combat
            if not combat:
                return
            n = sum(1 for d in combat.defending_cards if (d.power or 0) >= _th)
            if n:
                combat.attack_power = (combat.attack_power or 0) + _per * n
        return _fn

    if etype == "CLASH_DESTROY_TOP_OR_COUNTER":
        # Miller's Grindstone: "When this hits a hero, clash with them. If you win,
        # destroy the top card of their deck. If they win, put a -1{p} counter on
        # this." (Miller's is the attacker; its controller clashes the defender.)
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import clash as _clash, destroy as _destroy
            cid = _controller_id(card)
            opp = 3 - cid
            ev = _clash(state, cid, opp)
            if ev.winner_id == cid:
                deck = state.players[opp].deck
                if deck.cards:
                    _destroy(state, deck.cards[0], card)
            elif ev.winner_id == opp:
                card.counters["power"] = card.counters.get("power", 0) - 1
        return _fn

    if etype == "EACH_HERO_ARSENAL_FROM_ZONE_THEN_DISCARD":
        # Codex of Frailty / Inertia: "Each hero puts a card [from graveyard /
        # top of deck] face down into their arsenal. Each hero that does, discards
        # a card." source: "graveyard" (attack action cards) | "deck" (top card).
        source = params.get("source", "deck")
        def _fn(card, event, state, _src=source):
            from engine.card_effects.ability_keywords import _ask_player, effect_discard
            for pid, player in state.players.items():
                if len(player.arsenal.cards) >= getattr(player, 'arsenal_limit', 1):
                    continue
                target = None
                if _src == "graveyard":
                    attacks = [c for c in player.graveyard.cards
                               if 'attack' in [s.lower() for s in (c.subtypes or [])]]
                    if not attacks:
                        continue
                    from engine.card_effects.ability_keywords import ask_optional
                    pick = ask_optional(state, pid, [c.slug for c in attacks],
                                        context="Put an attack action from your graveyard facedown into arsenal?")
                    if pick is None:
                        continue
                    target = next((c for c in attacks if c.slug == pick), None)
                    if target is not None:
                        player.graveyard.remove(target)
                else:  # top of deck
                    if not player.deck.cards:
                        continue
                    target = player.deck.cards.pop(0)
                if target is None:
                    continue
                player.arsenal.add(target)
                target.face_down = True
                target.is_public = False
                if player.hand.cards:  # "each hero that does, discards a card"
                    effect_discard(state, pid, 1, random_discard=True)
        return _fn

    if etype == "EACH_HERO_SHUFFLE_TOP_TO_ARSENAL":
        # Schism of Chaos: "each hero shuffles, then puts the top card of their
        # deck facedown into their arsenal."
        def _fn(card, event, state):
            from engine.effect_keywords import shuffle as _shuffle
            for pid, player in state.players.items():
                _shuffle(state, pid)
                limit = getattr(player, 'arsenal_limit', 1)
                if player.deck.cards and len(player.arsenal.cards) < limit:
                    top = player.deck.cards.pop(0)
                    player.arsenal.add(top)
                    top.face_down = True
                    top.is_public = False
        return _fn

    if etype == "MODIFY_NEXT_ATTACK":
        mod = params.get("mod", "add")
        amt = params.get("amount", 0)
        # "filter" holds raw condition specs describing which future attacks qualify.
        # Using "filter" (not "conditions") so the loader does not pop these as
        # EffectDef gate conditions — they are pass-through data for the engine.
        filter_specs = params.get("filter", [])
        def _fn(card, event, state, _mod=mod, _a=amt, _filt=filter_specs):
            # Queue on the card's controller, not the turn player — an
            # instant-speed card using this effect must buff its own controller.
            from engine.card_effects.ability_keywords import _controller_id
            player = state.players[_controller_id(card)]
            if not hasattr(player, 'dsl_queued_attack_mods'):
                player.dsl_queued_attack_mods = []
            player.dsl_queued_attack_mods.append({
                "mod": _mod,
                "amount": _resolve_amount(_a, state),
                "filter": _filt,
            })
        return _fn

    if etype in ("GRANT_NEXT_ATTACK", "GRANT_NEXT_ATTACK_KEYWORD"):
        # "Your next attack this turn gets <keyword>" (Agility token, Driving
        # Blade). Queued on the same one-shot list as MODIFY_NEXT_ATTACK and
        # consumed by _apply_turn_attack_effects on the first attack matching
        # "filter" — the ONLY correct shape for "next", since a SET_FLAG plus a
        # flag-gated static grants the keyword to every attack for the rest of
        # the turn.
        keyword = params.get("keyword", "")
        kw = "Go Again" if str(keyword).lower().replace("_", " ") == "go again" else keyword
        filter_specs = params.get("filter", [])
        def _fn(card, event, state, _kw=kw, _filt=filter_specs):
            from engine.card_effects.ability_keywords import _controller_id
            player = state.players[_controller_id(card)]
            if not hasattr(player, 'dsl_queued_attack_mods'):
                player.dsl_queued_attack_mods = []
            player.dsl_queued_attack_mods.append({
                "mod": "grant_keyword",
                "keyword": _kw,
                "filter": _filt,
            })
        return _fn

    if etype == "GAIN":
        asset = params.get("asset")
        keyword = params.get("keyword")
        amt = params.get("amount", 0)
        if asset:
            def _fn(card, event, state, _asset=asset, _a=amt):
                from engine.card_effects.ability_keywords import _controller_id
                cid = _controller_id(card)
                val = _resolve_amount(_a, state)
                if _asset == "RESOURCE_POINTS":
                    from engine.card_effects.ability_keywords import effect_gain_resources
                    effect_gain_resources(state, cid, val)
                elif _asset in ("LIFE_POINTS", "LIFE", "HEALTH", "HEALTH_POINTS"):
                    # "gain N{h}" — cards author the life asset under several
                    # names; all mean gain that much life. Only LIFE_POINTS was
                    # handled before, so HEALTH/HEALTH_POINTS/LIFE (~19 cards)
                    # silently gained nothing.
                    from engine.card_effects.ability_keywords import effect_gain_life
                    effect_gain_life(state, cid, val)
                elif _asset == "ACTION_POINTS":
                    from engine.effect_keywords import gain as _ek_gain, AssetType as _AssetType
                    _ek_gain(state, _AssetType.ACTION_POINTS, val,
                             source_player_id=cid, target_player_id=cid)
                elif _asset == "CHI_POINTS":
                    from engine.effect_keywords import gain as _ek_gain, AssetType as _AssetType
                    _ek_gain(state, _AssetType.CHI, val,
                             source_player_id=cid, target_player_id=cid)
            return _fn
        if keyword:
            # Canonicalise go-again spellings so the resolution-step check
            # (which matches "go again") recognises it.
            kw = "Go Again" if keyword.lower().replace("_", " ") == "go again" else keyword.lower()
            def _fn(card, event, state, _kw=kw):
                if state.combat and _kw not in (state.combat.keywords or []):
                    state.combat.grant_keyword(_kw)
            return _fn

    if etype == "GO_AGAIN":
        # The attack gains go again (CR 8.3.5): its controller gains an action
        # point when the chain link resolves. Used inside INJECT_TRIGGER ON_HIT
        # (e.g. Blacktek Whisperers) and as a direct effect.
        def _fn(card, event, state):
            if state.combat and "Go Again" not in (state.combat.keywords or []):
                state.combat.grant_keyword("Go Again")
        return _fn

    if etype == "ROLL":
        # Cards author the die size as "faces" or "sides". Effects that consume
        # the result ("gain action points equal to half the number rolled") are
        # authored under "on_success" and run after the roll — they read the
        # result through _resolve_amount's ROLL_RESULT/HALF tokens.
        faces = params.get("faces", params.get("sides", 6))
        after = [compile_effect((e.get("type") or "").upper(),
                                {k: v for k, v in e.items() if k != "type"})
                 for e in (params.get("on_success") or [])]
        def _fn(card, event, state, _f=faces, _after=after):
            from engine.card_effects.ability_keywords import roll_die, _controller_id
            cid = _controller_id(card)
            result = roll_die(state, cid, faces=_f)
            state._roll_result = result
            # "If you've rolled a 6 on a die this turn" (a recurring Kayo
            # template) reads back across every roll in the turn, not just this
            # one — record it turn-scoped so any later card can check the flag.
            if result == 6:
                player = state.players[cid]
                if "DIE_ROLLED_SIX" not in player.current_turn_effects:
                    player.current_turn_effects.append("DIE_ROLLED_SIX")
            for fn in _after:
                if fn is not None:
                    fn(card, event, state)
        return _fn

    if etype == "APPLY_CONTINUOUS":
        target = params.get("target", "")
        # Single modification authored as "effect": {...} rather than the
        # "modifications" list (the recalc consumer reads the list only).
        modifications = params.get("modifications") or []
        if not modifications and isinstance(params.get("effect"), dict):
            modifications = [params["effect"]]
        span = params.get("span", "THIS_TURN")
        filter_raw = params.get("filter")
        def _fn(card, event, state, _tgt=target, _mods=modifications,
                _span=span, _filt=filter_raw):
            player = state.active()
            if not hasattr(player, 'dsl_continuous_effects'):
                player.dsl_continuous_effects = []
            player.dsl_continuous_effects.append({
                "target": _tgt,
                "modifications": _mods,
                "span": _span,
                "filter": _filt,
            })
        return _fn

    if etype == "DISCARD_RANDOM":
        amt = params.get("amount", 1)
        def _fn(card, event, state, _a=amt):
            from engine.card_effects.ability_keywords import effect_discard, _controller_id
            effect_discard(state, _controller_id(card), _a, random_discard=True)
        return _fn

    if etype == "REMOVE_COUNTERS":
        ctype = params.get("counter_type", "")
        amt = params.get("amount", 1)
        def _fn(card, event, state, _ct=ctype, _a=amt):
            from engine.card_effects.ability_keywords import effect_remove_counter
            effect_remove_counter(state, card, _ct, _a)
        return _fn

    if etype == "CHOOSE":
        choose_amt = params.get("amount", 1)
        options_raw = params.get("options", [])
        # An option is either a bare list of effect specs, or a named block
        # {"name": "Head Jab", "effects": [...]} — cards use both. Iterating the
        # dict form as a list yielded its KEYS and crashed on `str.get`.
        compiled_options, labels = [], []
        for i, opt in enumerate(options_raw):
            if isinstance(opt, dict):
                specs = opt.get("effects") or []
                labels.append(str(opt.get("name") or i))
            else:
                specs = opt or []
                labels.append(str(i))
            compiled_options.append(
                [compile_effect((e.get("type") or "").upper(),
                                {k: v for k, v in e.items() if k != "type"})
                 for e in specs])

        def _fn(card, event, state, _n=choose_amt, _opts=compiled_options, _labels=labels):
            if not _opts:
                return
            from engine.card_effects.ability_keywords import _ask_player, _controller_id
            cid = _controller_id(card)
            pick = _ask_player(state, cid, _labels, context="Choose an effect")
            idx = _labels.index(pick) if pick in _labels else 0
            for eff_fn in _opts[idx]:
                if eff_fn is not None:
                    eff_fn(card, event, state)
        return _fn

    # ── attack / wager ─────────────────────────────────────────────────────
    if etype in ("ATTACK", "ATTACKING"):
        # "Action - [cost]: Attack" on a weapon/hero. The attack is represented by
        # an ATTACK-PROXY on the stack (CR 1.6.2b / 11.0): an activated-layer
        # StackEntry whose card is the source, which the engine's combat step
        # (_combat_phase_iter -> _attack_step) resolves as a real attack — never a
        # shortcut into combat. NOTE: a weapon with printed power + activation_cost
        # is already offered its attack by play._add_weapon_attacks (which builds
        # the same proxy), and play._add_hero_dsl_activations SKIPS abilities whose
        # effect is ATTACK, so this _fn does not double-fire on weapon activation;
        # it is the proxy-builder for any context that invokes the effect directly
        # (e.g. a granted extra attack).
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.state import StackEntry
            pid = _controller_id(card)
            entry = StackEntry(
                player_id=pid, card=card, layer_type='activated',
                layer_position=len(state.stack_entries) + 1,
            )
            entry.pitched_for_attack = []
            state.stack_entries.append(entry)
        return _fn

    if etype == "WAGER":
        # CR 8.5.46: Wager — a continuous effect on the current attack. If the
        # attack hits, the controller wins and creates the prize token; otherwise
        # the opponent wins it. Resolves automatically at chain-link resolution
        # (engine._resolve_wagers), so this only registers the wager + prize.
        prize = params.get("prize") or params.get("token")
        def _fn(card, event, state, _prize=prize):
            from engine.card_effects.ability_keywords import add_wager, _controller_id
            add_wager(state, _controller_id(card), _prize)
        return _fn

    if etype == "PREVENT_DAMAGE":
        # "Prevent the next N damage that would be dealt to you." Registers a
        # one-shot PREVENTION replacement effect (CR 6.4.10) on the controller,
        # so the engine's damage pipeline (effect_manager.apply_replacements)
        # reduces the next damage event to this hero by up to N and then consumes
        # the shield. Used from injected ON_DAMAGE reactions like Steadfast.
        try:
            amount = int(params.get("amount", 0))
        except (TypeError, ValueError):
            amount = 0
        def _fn(card, event, state, _amt=amount):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effects import ReplacementEffect, ReplacementType
            cid = _controller_id(card)
            def _cond(ev, st, _cid=cid):
                return (ev.get("type") == "damage"
                        and ev.get("amount", 0) > 0
                        and not ev.get("unpreventable", False)
                        and ev.get("target_player_id") == _cid)
            def _replace(ev, st, _a=_amt):
                prevented = min(_a, ev.get("amount", 0))
                ev["amount"] = ev.get("amount", 0) - prevented
                return ev
            state.effect_manager.add_replacement(ReplacementEffect(
                source_card=card,
                replacement_type=ReplacementType.PREVENTION,
                condition_fn=_cond,
                replace_fn=_replace,
                owner_id=cid,
                prevention_amount=_amt,
                is_shielding=False,
            ))
        return _fn

    if etype == "PLAY_ACTIVATE_ATTACK":
        # "Play that card as an attack, and it's activated" — a granted extra
        # attack sourced from a card the surrounding effect located (e.g. Bonds
        # of Ancestry's injected trigger, which searches for a Gustwave). Modeling
        # the full free-play-into-combat grant is out of scope; this documented
        # best-effort resolves a stored "ref" (when the caller left one) and, if
        # it is an attack card in a play-adjacent zone, builds the same ATTACK
        # proxy the ATTACK effect uses so it enters the combat step normally.
        # With no usable ref it no-ops rather than crashing the game — the card
        # remains loadable and audit-safe.
        ref = params.get("ref", "chosen")
        def _fn(card, event, state, _r=ref):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.context import get_ref
            from engine.state import StackEntry
            target = get_ref(_r)
            if not target:
                return
            obj = target[0] if isinstance(target, list) else target
            if obj is None:
                return
            pid = _controller_id(card)
            entry = StackEntry(
                player_id=pid, card=obj, layer_type='activated',
                layer_position=len(state.stack_entries) + 1,
            )
            entry.pitched_for_attack = []
            state.stack_entries.append(entry)
        return _fn

    # Unknown effect types are authoring errors — fail at JSON load time
    # rather than silently no-opping (fail-open let bad JSON go unnoticed).
    raise ValueError(f"Unknown DSL effect type: {etype!r} (params: {params!r})")
