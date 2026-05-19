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
        # Next weapon attack gets +N power.
        # Consumed by _apply_turn_attack_effects in engine.py (weapon-only gate).
        amt = params.get("amount", 0)
        def _fn(card, event, state, _a=amt):
            if _a:
                state.active().current_turn_effects.append(f"next_weapon_attack_+{_a}")
        return _fn

    if etype == "NEXT_WEAPON_ATTACK_KEYWORD":
        # Grant a keyword to the next weapon attack this turn.
        # keyword: "go_again" | "hit_go_again" → sets "next_weapon_attack_<keyword>" turn flag.
        kw = params.get("keyword", "go_again")
        def _fn(card, event, state, _kw=kw):
            state.active().current_turn_effects.append(f"next_weapon_attack_{_kw}")
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

    if etype == "PUT_HAND_CARD_BOTTOM":
        # Choose a card from hand and put it on the bottom of the deck (no draw).
        # player: "SELF" (default) | "OPPONENT" — whose hand is affected.
        player_target = params.get("player", "SELF")
        def _fn(card, event, state, _pt=player_target):
            from engine.card_effects.ability_keywords import _ask_player, _controller_id
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
                player.hand.remove(target)
                player.deck.add_bottom(target)
        return _fn

    if etype == "CREATE_AURA_TOKEN":
        token_slug = params.get("token", "")
        def _fn(card, event, state, _slug=token_slug):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.card import Card
            pid = _controller_id(card)
            player = state.players[pid]
            token = Card(slug=_slug, name=_slug, types=["Token"])
            token.owner = pid
            token.controller = pid
            player.auras.add(token)
        return _fn

    if etype == "PUT_SELF_BOTTOM_DECK":
        # Remove this card from the graveyard and put it on the bottom of its owner's deck.
        # Used for replacement effects like Drone of Brutality.
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import _controller_id
            pid = _controller_id(card)
            player = state.players[pid]
            if hasattr(player, 'graveyard') and hasattr(player.graveyard, 'cards'):
                if card in player.graveyard.cards:
                    player.graveyard.cards.remove(card)
            player.deck.add_bottom(card)
            card.zone = "deck"
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
        power_bonus = params.get("power_bonus", 0)
        def _fn(card, event, state, _a=amt, _pg=power_gte, _ap=ap_gain,
                _dr=draw_count, _ga=go_again, _pb=power_bonus):
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
                if _pb and state.combat:
                    state.combat.attack_power = (state.combat.attack_power or 0) + _pb
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
        def _fn(card, event, state, _tok=token, _cnt=count, _pt=player_target):
            from engine.card_effects.ability_keywords import create_token, _controller_id
            cid = _controller_id(card)
            tid = (3 - cid) if _pt.upper() in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            create_token(state, tid, _tok, _cnt)
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

    if etype == "DESTROY_SELF":
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import _controller_id
            pid = _controller_id(card)
            player = state.players[pid]
            for zone_name in ('permanents', 'items', 'auras', 'allies'):
                zone = getattr(player, zone_name, None)
                if zone and hasattr(zone, 'cards') and card in zone.cards:
                    try:
                        from engine.effect_keywords import destroy as _ek_destroy
                        _ek_destroy(state, card, None)
                    except Exception:
                        zone.cards.remove(card)
                    return
        return _fn

    if etype == "ROLL_DIE_BRANCHES":
        # Roll a die; execute effects from the matching range branch.
        # branches: [{"range": [low, high], "effects": [{...}, ...]}, ...]
        faces = params.get("faces", 6)
        raw_branches = params.get("branches", [])
        compiled_branches = []
        for branch in raw_branches:
            lo, hi = branch.get("range", [1, faces])
            inner_effs = [
                compile_effect(e.get("type", "").upper(),
                               {k: v for k, v in e.items() if k != "type"})
                for e in branch.get("effects", [])
            ]
            compiled_branches.append((lo, hi, inner_effs))
        def _fn(card, event, state, _f=faces, _cb=compiled_branches):
            from engine.card_effects.ability_keywords import roll_die, _controller_id
            result = roll_die(state, _controller_id(card), faces=_f)
            for lo, hi, effs in _cb:
                if lo <= result <= hi:
                    for eff_fn in effs:
                        eff_fn(card, event, state)
                    break
        return _fn

    if etype == "ALL_WEAPONS_BONUS":
        # All weapon attacks this turn gain +N{p} (biting_blade reprise).
        amt = params.get("amount", 0)
        def _fn(card, event, state, _a=amt):
            state.active().current_turn_effects.append(f"all_weapon_attacks_+{_a}")
        return _fn

    if etype == "MODIFY_POWER_PER_CHAIN_HIT":
        # +amount_per_hit × (number of prior chain-link hits) (fluster_fist).
        amt_per = params.get("amount_per_hit", 1)
        def _fn(card, event, state, _a=amt_per):
            n_hits = len(getattr(state, 'chain_links', []))
            if state.combat and n_hits:
                state.combat.attack_power = (state.combat.attack_power or 0) + _a * n_hits
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
        # Put the opponent's arsenal card on the bottom of their deck (disable).
        player_target = params.get("player", "OPPONENT")
        def _fn(card, event, state, _pt=player_target):
            from engine.card_effects.ability_keywords import _controller_id
            cid = _controller_id(card)
            tid = (3 - cid) if _pt.upper() in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            player = state.players[tid]
            arsenal = getattr(player, 'arsenal', None)
            if arsenal and hasattr(arsenal, 'cards') and arsenal.cards:
                card_to_move = arsenal.cards[0]
                arsenal.cards.remove(card_to_move)
                player.deck.cards.append(card_to_move)
        return _fn

    if etype == "REDUCE_NEXT_CARD_COST":
        # Sets a cost-reduction flag consumed when the next qualifying card is played.
        # filter_types: ["attack"] restricts to attack action cards; empty = any card.
        # filter_classes: ["Guardian"] restricts to specific class.
        amt = params.get("amount", 0)
        filter_types = [t.lower() for t in params.get("filter_types", [])]
        filter_classes = [c.lower() for c in params.get("filter_classes", [])]
        def _fn(card, event, state, _a=amt, _ft=filter_types, _fc=filter_classes):
            from engine.card_effects.ability_keywords import _controller_id
            parts = []
            if "attack" in _ft:
                parts.append("attack_action")
            if _fc:
                parts.append("_".join(_fc))
            qualifier = ("_" + "_".join(parts)) if parts else ""
            state.active().current_turn_effects.append(f"next{qualifier}_cost_-{_a}")
        return _fn

    if etype == "SHUFFLE_HAND_TO_DECK_DRAW":
        # hope_merchants_hood: shuffle any number of hand cards into deck, draw same count.
        # Simulation: shuffles all hand cards (agent has no partial-choice mechanism).
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import effect_draw, _controller_id
            import random as _random
            cid = _controller_id(card)
            player = state.players[cid]
            n = len(player.hand.cards)
            if not n:
                return
            for c in list(player.hand.cards):
                player.hand.cards.remove(c)
                player.deck.cards.append(c)
            _random.shuffle(player.deck.cards)
            effect_draw(state, cid, n)
        return _fn

    if etype == "CHOOSE_ONE":
        # Present N option-lists; randomly pick one and execute its effects.
        # options: [[{effect}, ...], [{effect}, ...], ...]
        options_raw = params.get("options", [])
        compiled_options = [
            [compile_effect(e.get("type", "").upper(),
                            {k: v for k, v in e.items() if k != "type"})
             for e in opt]
            for opt in options_raw
        ]
        def _fn(card, event, state, _opts=compiled_options):
            if not _opts:
                return
            import random as _random
            for eff_fn in _random.choice(_opts):
                eff_fn(card, event, state)
        return _fn

    if etype == "DESTROY_PERMANENT":
        target = params.get("target", "self")
        def _fn(card, event, state, _t=target):
            from engine.card_effects.ability_keywords import _controller_id
            pid = _controller_id(card)
            player = state.players[pid]
            if _t == "self":
                for zone_name in ('permanents', 'items', 'auras', 'allies'):
                    zone = getattr(player, zone_name, None)
                    if zone and hasattr(zone, 'cards') and card in zone.cards:
                        try:
                            from engine.effect_keywords import destroy as _ek_destroy
                            _ek_destroy(state, card, None)
                        except Exception:
                            zone.cards.remove(card)
                        return
        return _fn

    if etype in ("MODIFY_DEFENSE_VALUE", "MODIFY_DEFENSE_POWER"):
        amt = params.get("amount", 0)
        def _fn(card, event, state, _a=amt):
            if state.combat:
                state.combat.total_defense = (getattr(state.combat, 'total_defense', 0) or 0) + _a
        return _fn

    if etype == "ATTACK":
        # Weapon attack initiation is handled by the engine's ACTIVATE pathway.
        # This DSL effect is a no-op placeholder for harmonized_kodachi / romping_club.
        def _fn(card, event, state):
            pass
        return _fn

    if etype == "RETURN_DR_FROM_GRAVEYARD":
        # Return a defense reaction card from any graveyard to its owner's hand.
        # Simplified: searches controller's graveyard first, then opponent's.
        def _fn(card, event, state):
            from engine.card_effects.ability_keywords import _controller_id
            cid = _controller_id(card)
            for pid in (cid, 3 - cid):
                player = state.players.get(pid)
                if not player:
                    continue
                for c in list(getattr(player.graveyard, 'cards', [])):
                    types = [t.lower() for t in (getattr(c, 'types', None) or [])]
                    subtypes = [st.lower() for st in (getattr(c, 'subtypes', None) or [])]
                    if 'defense reaction' in types or 'defense_reaction' in subtypes:
                        player.graveyard.cards.remove(c)
                        owner_player = state.players.get(c.owner if c.owner is not None else pid)
                        if owner_player:
                            owner_player.hand.add(c)
                        return
        return _fn

    if etype == "GAIN_POWER_FROM_ROLL":
        # Roll a die, gain that many attack power (Swing Big style).
        faces = params.get("faces", 6)
        def _fn(card, event, state, _f=faces):
            from engine.card_effects.ability_keywords import roll_die, _controller_id
            pid = _controller_id(card)
            result = roll_die(state, pid, faces=_f)
            if state.combat:
                state.combat.attack_power = (state.combat.attack_power or 0) + result
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
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import deal_damage, DamageType
            cid = _controller_id(card)
            tid = (3 - cid) if _t.upper() in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            deal_damage(state, _a, DamageType.GENERIC, target_player_id=tid, source_card=card)
        return _fn

    if etype == "ROLL_ATTACK_BONUS":
        # Roll a die; if result >= threshold, grant +N power to the current attack.
        faces = params.get("faces", 6)
        threshold = params.get("threshold", 4)
        bonus = params.get("bonus", 0)
        def _fn(card, event, state, _f=faces, _th=threshold, _b=bonus):
            from engine.card_effects.ability_keywords import roll_die, _controller_id
            pid = _controller_id(card)
            result = roll_die(state, pid, faces=_f)
            if result >= _th and state.combat:
                state.combat.attack_power = (state.combat.attack_power or 0) + _b
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
            cid = _controller_id(card)
            tid = (3 - cid) if _pt.upper() in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            player = state.players[tid]
            if hasattr(player, 'arsenal') and player.arsenal.cards:
                player.arsenal.cards.clear()
        return _fn

    # ── unknown → no-op ────────────────────────────────────────────────────
    def _noop(card, event, state, _et=etype):
        pass  # unknown effect type; silently skip
    return _noop
