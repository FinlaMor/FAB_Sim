"""Compile JSON effect objects into (card, event, state) -> None callables."""
from __future__ import annotations
from typing import Any, Callable


def _resolve_amount(amount: Any, state) -> int | float:
    """Resolve a string amount token (ROLL_NUMBER etc.) to a numeric value."""
    if isinstance(amount, str):
        roll = getattr(state, '_roll_result', 0) or 0
        if amount == "ROLL_NUMBER":
            return roll
        if amount == "ROLL_NUMBER_HALF_ROUND_DOWN":
            return roll // 2
        return 0
    return amount


def compile_effect(etype: str, params: dict[str, Any]) -> Callable:
    """Return a (card, event, state)->None callable."""

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
        def _fn(card, event, state, _a=amt):
            from engine.card_effects.ability_keywords import effect_draw, _controller_id
            effect_draw(state, _controller_id(card), _a)
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

    if etype == "PUT_HAND_CARD_BOTTOM":
        # Choose a card from hand and put it on the bottom of the deck (no draw).
        # player: "SELF" (default) | "OPPONENT" — whose hand is affected.
        player_target = params.get("player", "SELF")
        def _fn(card, event, state, _pt=player_target):
            from engine.card_effects.ability_keywords import _ask_player, _controller_id
            from engine.effect_keywords import put_object
            cid = _controller_id(card)
            tid = (3 - cid) if _pt.upper() in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            player = state.players[tid]
            if not player.hand.cards:
                return
            options = [c.slug for c in player.hand.cards] + ["decline"]
            choice = _ask_player(state, tid, options,
                                 context="Choose a card to put on the bottom of your deck")
            if choice == "decline":
                return
            target = player.hand.find(choice)
            if target:
                # position=None → zone default (append = bottom, cards[-1])
                put_object(state, target, "deck",
                           destination_player_id=tid, source_player_id=tid,
                           position=None)
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
            options = [c.slug for c in eligible] + ["fail_to_find"]
            pick = _ask_player(state, cid, options,
                               context="Search your deck for a card to banish face-down (or fail to find)")
            if pick != "fail_to_find":
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
            options = [c.slug for c in eligible] + ["fail_to_find"]
            pick = _ask_player(state, cid, options,
                               context="Search your deck for a card and put it into hand (or fail to find)")
            if pick != "fail_to_find":
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

    # ── tokens / permanents ────────────────────────────────────────────────
    if etype == "CREATE_TOKEN":
        token = params.get("token", "")
        count = params.get("count", 1)
        player_target = params.get("player", "SELF")
        destination = params.get("destination")  # e.g. "weapon_slot" to equip
        def _fn(card, event, state, _tok=token, _cnt=count, _pt=player_target, _dest=destination):
            from engine.effect_keywords import create_token as _ek_create_token
            from engine.card_effects.ability_keywords import _controller_id
            cid = _controller_id(card)
            tid = (3 - cid) if _pt.upper() in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            _ek_create_token(state, tid, _tok, _cnt, destination=_dest)
        return _fn

    if etype == "PUT_COUNTER":
        ctype = params.get("counter_type", "")
        amt = params.get("amount", 1)
        def _fn(card, event, state, _ct=ctype, _a=amt):
            from engine.card_effects.ability_keywords import effect_put_counter
            for _ in range(_a):
                effect_put_counter(state, card, _ct)
        return _fn

    if etype == "REMOVE_COUNTER":
        ctype = params.get("counter_type", "")
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
        inner_trigger = params.get("trigger", "ON_HIT")
        inner_conditions_raw = params.get("conditions", [])
        inner_effects_raw = params.get("effects", [])

        from engine.card_effects.dsl.condition_types import compile_condition as _cc

        # Pre-compile inner conditions and effects (lazy inner effect compilation via closure)
        inner_cond_fns = [_cc(ic.get("type", "none"), ic) for ic in inner_conditions_raw]
        inner_eff_specs = [(ie.get("type", "").upper(), ie) for ie in inner_effects_raw]

        def _inject_fn(card, event, state,
                       _trig=inner_trigger,
                       _icond_fns=inner_cond_fns,
                       _ieff_specs=inner_eff_specs):
            if not state.combat:
                return
            from engine.card_effects.triggers import TriggerDef
            # Compile inner effect fns now (avoids circular import at module load)
            compiled_effs = [compile_effect(et, ep) for et, ep in _ieff_specs]

            def _one_shot(c, ev, st,
                          _iconds=_icond_fns,
                          _ieffs=compiled_effs):
                for cond_fn in _iconds:
                    if cond_fn is not None and not cond_fn(c, ev, st):
                        return
                for eff_fn in _ieffs:
                    eff_fn(c, ev, st)

            td = TriggerDef(
                event_type=_trig,
                condition_fn=None,
                effect_fn=_one_shot,
                is_optional=False,
            )
            if not hasattr(state.combat, 'injected_triggers'):
                state.combat.injected_triggers = []
            state.combat.injected_triggers.append(td)
        return _inject_fn

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
        def _fn(card, event, state, _t=target):
            if _t == "self":
                # destroy() resolves the card's actual zone itself.
                from engine.effect_keywords import destroy as _ek_destroy
                _ek_destroy(state, card, None)
        return _fn

    if etype == "MODIFY_DEFENSE_VALUE":
        amt = params.get("amount", 0)
        def _fn(card, event, state, _a=amt):
            if state.combat:
                state.combat.total_defense = (getattr(state.combat, 'total_defense', 0) or 0) + _a
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
        # +N power per distinct aura name the controller has in play (Overcrowded).
        per = params.get("per", 1)
        def _fn(card, event, state, _per=per):
            from engine.card_effects.ability_keywords import _controller_id
            pid = _controller_id(card)
            auras = getattr(state.players[pid], 'auras', None)
            if not auras:
                return
            distinct = len({getattr(c, 'slug', '') for c in auras.cards})
            if distinct and state.combat:
                state.combat.attack_power = (state.combat.attack_power or 0) + distinct * _per
        return _fn

    if etype == "CROWD_BOO":
        player_target = params.get("player", "SELF")
        def _fn(card, event, state, _pt=player_target):
            from engine.card_effects.ability_keywords import effect_crowd_boos, _controller_id
            cid = _controller_id(card)
            tid = (3 - cid) if _pt.upper() in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            effect_crowd_boos(state, tid)
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
        # the resources to avoid the damage (e.g. Bloodrot Pox).
        resources = params.get("resources", 0)
        dmg = params.get("damage", 0)
        def _fn(card, event, state, _r=resources, _d=dmg):
            from engine.card_effects.ability_keywords import (
                _ask_player, _controller_id, effect_deal_damage)
            cid = _controller_id(card)
            player = state.players[cid]
            paid = False
            if player.resources >= _r:
                choice = _ask_player(state, cid, ["pay", "take_damage"],
                                     context=f"Pay {_r} to avoid {_d} damage?")
                if str(choice) == "pay":
                    player.resources -= _r
                    paid = True
            if not paid:
                effect_deal_damage(state, cid, _d, card, damage_type="generic")
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

    if etype == "LOOK":
        # "Look at the top N cards of a deck." Pops them aside into a
        # dispatch-scoped buffer; BANISH_FROM_LOOKED / PUT_LOOKED_BACK consume it.
        n = params.get("amount", 5)
        target = params.get("target", "OPP_DECK").upper()
        def _fn(card, event, state, _n=n, _t=target):
            from engine.card_effects.ability_keywords import _controller_id
            cid = _controller_id(card)
            tid = (3 - cid) if "OPP" in _t else cid
            deck = state.players[tid].deck
            looked = []
            for _ in range(min(_n, len(deck.cards))):
                looked.append(deck.pop_top())
            state.dsl_look_buffer = {"player_id": tid, "cards": looked}
        return _fn

    if etype == "BANISH_FROM_LOOKED":
        # "Banish 1 or more cards with the same name from among them." The
        # controller picks a name present in the look buffer; all copies of that
        # name are banished. Mandatory (banish at least one) when a card exists.
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import _ask_player, _controller_id
            buf = getattr(state, "dsl_look_buffer", None)
            if not buf or not buf["cards"]:
                return
            cid = _controller_id(card)
            groups: dict = {}
            for c in buf["cards"]:
                groups.setdefault(c.name, []).append(c)
            options = list(groups.keys())
            pick = _ask_player(state, cid, options,
                               context="Banish all copies of which name?")
            chosen = pick if pick in groups else options[0]
            tid = buf["player_id"]
            for c in list(groups[chosen]):
                buf["cards"].remove(c)
                state.remember_last_known(c, overwrite=False)
                state.players[tid].banished.add(c)
        return _fn

    if etype == "PUT_LOOKED_BACK":
        # "Put the rest on top of their deck in any order." The controller orders
        # the remaining look-buffer cards; the first chosen ends up on top.
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import _ask_player, _controller_id
            buf = getattr(state, "dsl_look_buffer", None)
            if not buf:
                return
            cid = _controller_id(card)
            remaining = list(buf["cards"])
            deck = state.players[buf["player_id"]].deck
            ordered = []
            while remaining:
                if len(remaining) == 1:
                    ordered.append(remaining.pop())
                    break
                pick = _ask_player(state, cid, remaining,
                                   context="Choose the next card to place on top")
                chosen = pick if pick in remaining else remaining[0]
                remaining.remove(chosen)
                ordered.append(chosen)
            # Insert so ordered[0] is on top: insert in reverse at index 0.
            for c in reversed(ordered):
                c.zone = "deck"
                deck.cards.insert(0, c)
            state.dsl_look_buffer = None
        return _fn

    if etype == "TRANSFORM_HERO":
        # Arakni: "become a random Agent of Chaos" / "return to the brood".
        mode = params.get("mode", "random_agent_of_chaos").lower()
        def _fn(card, event, state, _m=mode):
            from engine.card_effects.ability_keywords import (
                _controller_id, become_agent_of_chaos, return_to_brood)
            pid = _controller_id(card)
            if _m == "return_to_brood":
                return_to_brood(state, pid)
            else:
                become_agent_of_chaos(state, pid)
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
                elif _asset == "LIFE_POINTS":
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
        faces = params.get("faces", 6)
        def _fn(card, event, state, _f=faces):
            from engine.card_effects.ability_keywords import roll_die, _controller_id
            result = roll_die(state, _controller_id(card), faces=_f)
            state._roll_result = result
        return _fn

    if etype == "APPLY_CONTINUOUS":
        target = params.get("target", "")
        modifications = params.get("modifications", [])
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
        compiled_options = [
            [compile_effect(e.get("type", "").upper(),
                            {k: v for k, v in e.items() if k != "type"})
             for e in opt]
            for opt in options_raw
        ]
        def _fn(card, event, state, _n=choose_amt, _opts=compiled_options):
            if not _opts:
                return
            from engine.card_effects.ability_keywords import _ask_player, _controller_id
            cid = _controller_id(card)
            labels = [str(i) for i in range(len(_opts))]
            pick = _ask_player(state, cid, labels, context="Choose an effect")
            idx = int(pick) if pick and pick.isdigit() and int(pick) < len(_opts) else 0
            for eff_fn in _opts[idx]:
                eff_fn(card, event, state)
        return _fn

    # Unknown effect types are authoring errors — fail at JSON load time
    # rather than silently no-opping (fail-open let bad JSON go unnoticed).
    raise ValueError(f"Unknown DSL effect type: {etype!r} (params: {params!r})")
