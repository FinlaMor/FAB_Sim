"""Compile JSON effect objects into (card, event, state) -> None callables."""
from __future__ import annotations
from typing import Any, Callable


def compile_effect(etype: str, params: dict[str, Any]) -> Callable:
    """Return a (card, event, state)->None callable."""

    # ── life / damage ──────────────────────────────────────────────────────
    if etype == "GAIN_LIFE":
        amt = params.get("amount", 0)
        def _fn(card, event, state, _a=amt):
            from engine.card_effects.ability_keywords import effect_gain_life, _controller_id
            effect_gain_life(state, _controller_id(card), _a)
        return _fn

    if etype == "LOSE_LIFE":
        amt = params.get("amount", 0)
        def _fn(card, event, state, _a=amt):
            from engine.card_effects.ability_keywords import effect_lose_life, _controller_id
            effect_lose_life(state, _controller_id(card), _a)
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
        face_up = params.get("face_up", True)
        from_zone = params.get("from_zone", "TOP_DECK")
        def _fn(card, event, state, _a=amt, _fu=face_up, _fz=from_zone):
            from engine.card_effects.ability_keywords import effect_banish_top_deck, _controller_id
            if _fz.upper() == "TOP_DECK":
                effect_banish_top_deck(state, _controller_id(card), _a, face_up=_fu)
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

    # ── resources ──────────────────────────────────────────────────────────
    if etype == "GAIN_RESOURCES":
        amt = params.get("amount", 1)
        def _fn(card, event, state, _a=amt):
            from engine.card_effects.ability_keywords import effect_gain_resources, _controller_id
            effect_gain_resources(state, _controller_id(card), _a)
        return _fn

    if etype == "GAIN_RESOURCES_FROM_ROLL":
        # Roll a die, optionally scale the result, gain that many resources.
        # "gain {r} equal to half the number rolled, rounded down" ->
        #   {"type": "GAIN_RESOURCES_FROM_ROLL", "faces": 6, "divisor": 2}
        faces = params.get("faces", 6)
        divisor = params.get("divisor", 1)
        def _fn(card, event, state, _f=faces, _d=divisor):
            from engine.card_effects.ability_keywords import roll_die, effect_gain_resources, _controller_id
            pid = _controller_id(card)
            result = roll_die(state, pid, faces=_f)
            amount = result // _d
            if amount > 0:
                effect_gain_resources(state, pid, amount)
        return _fn

    # ── attack / combat ────────────────────────────────────────────────────
    if etype == "MODIFY_ATTACK_POWER":
        amt = params.get("amount", 0)
        def _fn(card, event, state, _a=amt):
            if state.combat:
                state.combat.attack_power = (state.combat.attack_power or 0) + _a
        return _fn

    if etype == "GO_AGAIN":
        def _fn(card, event, state):
            if state.combat and "go_again" not in (state.combat.keywords or []):
                state.combat.grant_keyword("go_again")
        return _fn

    if etype == "GRANT_KEYWORD":
        kw = params.get("keyword", "")
        def _fn(card, event, state, _kw=kw):
            if state.combat and _kw not in (state.combat.keywords or []):
                state.combat.grant_keyword(_kw)
        return _fn

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

    if etype == "NEXT_ATTACK_BONUS":
        amt = params.get("amount", 0)
        key = f"next_attack_+{amt}"
        def _fn(card, event, state, _key=key):
            state.active().current_turn_effects.append(_key)
        return _fn

    if etype == "NEXT_ATTACK_HIT_DRAW":
        # Queue a one-shot ON_HIT draw for the NEXT attack this turn.
        # Stored as "next_attack_hit_draw_N" in current_turn_effects;
        # consume_card_attack_bonuses in engine.py injects it as a TriggerDef.
        amt = params.get("amount", 1)
        key = f"next_attack_hit_draw_{amt}"
        def _fn(card, event, state, _key=key):
            state.active().current_turn_effects.append(_key)
        return _fn

    if etype == "ALL_ATTACKS_BONUS":
        # +N power to every attack this turn (persistent — not consumed after first attack).
        # Stored as "all_attacks_+N" in current_turn_effects.
        amt = params.get("amount", 0)
        key = f"all_attacks_+{amt}"
        def _fn(card, event, state, _key=key):
            state.active().current_turn_effects.append(_key)
        return _fn

    if etype == "ALL_ATTACKS_HIT_DRAW":
        # Every attack that hits this turn draws N cards.
        # Stored as "all_attacks_hit_draw_N" in current_turn_effects;
        # consume_card_attack_bonuses re-injects an ON_HIT TriggerDef each attack.
        amt = params.get("amount", 1)
        key = f"all_attacks_hit_draw_{amt}"
        def _fn(card, event, state, _key=key):
            state.active().current_turn_effects.append(_key)
        return _fn

    if etype == "NEXT_WEAPON_ATTACK_BONUS":
        # Next weapon attack gets +N power. Optionally also gets go again or hit: go again.
        # Stored as "next_weapon_attack_+N" (and related flags) in current_turn_effects.
        # Consumed by _apply_turn_attack_effects in engine.py (weapon-only gate).
        amt = params.get("amount", 0)
        go_again = params.get("go_again", False)
        hit_go_again = params.get("hit_go_again", False)
        def _fn(card, event, state, _a=amt, _ga=go_again, _hga=hit_go_again):
            player = state.active()
            if _a:
                player.current_turn_effects.append(f"next_weapon_attack_+{_a}")
            if _ga:
                player.current_turn_effects.append("next_weapon_attack_go_again")
            if _hga:
                player.current_turn_effects.append("next_weapon_attack_hit_go_again")
        return _fn

    if etype == "NEXT_LOW_COST_ATTACK_BONUS":
        # Next attack action card with cost ≤1 gets +N power.
        # Stored as "next_low_cost_attack_+N" in current_turn_effects.
        amt = params.get("amount", 0)
        def _fn(card, event, state, _a=amt):
            state.active().current_turn_effects.append(f"next_low_cost_attack_+{_a}")
        return _fn

    if etype == "NEXT_HIGH_COST_ATTACK_BONUS":
        # Next attack action card with cost ≥2 gets +N power.
        # Stored as "next_high_cost_attack_+N" in current_turn_effects.
        amt = params.get("amount", 0)
        def _fn(card, event, state, _a=amt):
            state.active().current_turn_effects.append(f"next_high_cost_attack_+{_a}")
        return _fn

    if etype == "RETURN_TO_HAND":
        # Return this card to the controller's hand.
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.context import effect_context
            cid = _controller_id(card)
            player = state.players[cid]
            # Remove from current zone
            current_zone = card.zone if card.zone else None
            if current_zone:
                zone_obj = player.zone_by_name(current_zone) if hasattr(player, 'zone_by_name') else None
                if zone_obj and card in zone_obj.cards:
                    zone_obj.remove(card)
            with effect_context():
                player.hand.add(card)
        return _fn

    if etype == "PUT_BOTTOM_DRAW":
        # Player chooses a card from hand to put on the bottom of their deck, then draws.
        # If no hand cards or player declines, nothing happens.
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import _ask_player, _controller_id, effect_draw
            cid = _controller_id(card)
            player = state.players[cid]
            if not player.hand.cards:
                return
            options = [c.slug for c in player.hand.cards] + ["decline"]
            choice = _ask_player(state, cid, options,
                                 context="Choose a card to put on the bottom of your deck, then draw")
            if choice == "decline":
                return
            target = player.hand.find(choice)
            if target:
                player.hand.remove(target)
                player.deck.add_bottom(target)
                effect_draw(state, cid, 1)
        return _fn

    if etype == "SEARCH_DECK":
        # Search your deck for any card, put it in hand, then shuffle.
        # Player may "fail to find" (CR 8.5.19). Follows the nimby pattern.
        filter_types = params.get("filter_types", None)   # optional list of card types
        filter_slug_contains = params.get("slug_contains", None)  # optional substring
        def _fn(card, event, state, _ft=filter_types, _fsc=filter_slug_contains):
            from engine.card_effects.ability_keywords import _ask_player, _controller_id
            from engine.card_effects.triggers.card_triggers_extended import effect_shuffle
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
                    controller.deck.cards.remove(target)
                    target.owner = cid
                    target.controller = cid
                    controller.hand.add(target)
                    state.set_card_visibility(target, True)
            effect_shuffle(state, cid)
        return _fn

    if etype == "GAIN_ACTION_POINTS":
        amt = params.get("amount", 1)
        def _fn(card, event, state, _a=amt):
            from engine.card_effects.ability_keywords import _controller_id
            state.players[_controller_id(card)].action_points += _a
        return _fn

    if etype == "DISCARD_RANDOM_CONDITIONAL":
        # Discard N cards at random. If a discarded card has power >= power_gte:
        #   - gain ap_gain action points (if ap_gain > 0)
        #   - draw draw_count cards (if draw_count > 0)
        #   - grant go again (if go_again is True)
        amt = params.get("amount", 1)
        power_gte = params.get("power_gte", 6)
        ap_gain = params.get("ap_gain", 0)
        draw_count = params.get("draw", 0)
        go_again = params.get("go_again", False)
        def _fn(card, event, state, _a=amt, _pg=power_gte, _ap=ap_gain,
                _dr=draw_count, _ga=go_again):
            from engine.card_effects.ability_keywords import effect_discard, _controller_id
            cid = _controller_id(card)
            discarded = effect_discard(state, cid, _a, random_discard=True)
            if discarded and any((getattr(c, 'power', None) or 0) >= _pg for c in discarded):
                if _ap:
                    state.players[cid].action_points += _ap
                if _dr:
                    from engine.card_effects.ability_keywords import effect_draw
                    effect_draw(state, cid, _dr)
                if _ga and state.combat:
                    state.combat.grant_keyword("go_again")
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
        def _fn(card, event, state, _tok=token, _cnt=count):
            from engine.card_effects.ability_keywords import create_token, _controller_id
            create_token(state, _controller_id(card), _tok, _cnt)
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
        def _fn(card, event, state, _f=flag, _s=scope):
            from engine.card_effects.ability_keywords import _controller_id
            player = state.players[_controller_id(card)]
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

    # ── unknown → no-op ────────────────────────────────────────────────────
    def _noop(card, event, state, _et=etype):
        pass  # unknown effect type; silently skip
    return _noop
