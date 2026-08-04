"""Compile JSON cost objects into (check_fn, pay_fn) pairs for the DSL.

All callables use the signature (card, event, state) -> bool/None to match
the convention used by condition_types and effect_types.
"""
from __future__ import annotations
import random
from typing import Any, Callable


def compile_cost(ctype: str, params: dict[str, Any]) -> tuple[Callable, Callable]:
    """Return (check_fn, pay_fn).

    check_fn(card, event, state) -> bool  — True if cost is payable
    pay_fn(card, event, state) -> None    — deduct/resolve the cost
    """

    # ── mandatory additional costs ─────────────────────────────────────────

    if ctype == "DESTROY_SELF":
        # "Destroy <this>: …" — the activation cost is destroying the source card
        # (e.g. Blacktek Whisperers' attack reaction).
        def can_pay(card, event, state):
            return True
        def pay(card, event, state):
            from engine.effect_keywords import destroy as _destroy
            _destroy(state, card, card)
        return can_pay, pay

    if ctype == "DISCARD_SELF":
        # "Instant - Discard this: …" — the activation cost is discarding this
        # card from hand. Marks the ability as a from-hand instant so the engine
        # offers it (see play._add_hand_instant_activations).
        def can_pay(card, event, state):
            from engine.card_effects.ability_keywords import _controller_id
            pid = _controller_id(card)
            return pid is not None and card in state.players[pid].hand.cards
        def pay(card, event, state):
            from engine.card_effects.ability_keywords import _controller_id
            pid = _controller_id(card)
            if pid is not None and card in state.players[pid].hand.cards:
                state.players[pid].hand.remove(card)
                state.players[pid].graveyard.add(card)
        return can_pay, pay

    if ctype == "DISCARD_RANDOM":
        # "As an additional cost to play X, discard a random card."
        amount = params.get("amount", 1)
        def can_pay(card, event, state, _a=amount):
            from engine.card_effects.ability_keywords import _controller_id
            return len(state.players[_controller_id(card)].hand.cards) >= _a
        def pay(card, event, state, _a=amount):
            from engine.card_effects.ability_keywords import effect_discard, _controller_id
            effect_discard(state, _controller_id(card), _a, random_discard=True)
        return can_pay, pay

    if ctype == "DISCARD_CARD":
        # Discard cost with an optional type or class filter (e.g. "discard an
        # Assassin card"). When filtered, the controller chooses which matching
        # card to discard; unfiltered discards are random.
        amount = params.get("amount", 1)
        type_filter = params.get("type_filter", "")
        class_filter = params.get("class_filter", "")

        def _matches(c, _tf=type_filter, _cf=class_filter):
            if _tf and _tf.upper() not in [t.upper() for t in (getattr(c, 'types', None) or [])]:
                return False
            if _cf and _cf.upper() not in [x.upper() for x in (getattr(c, 'classes', None) or [])]:
                return False
            return True

        def can_pay(card, event, state, _a=amount):
            from engine.card_effects.ability_keywords import _controller_id
            hand = state.players[_controller_id(card)].hand
            if type_filter or class_filter:
                return len([c for c in hand.cards if _matches(c)]) >= _a
            return len(hand.cards) >= _a

        def pay(card, event, state, _a=amount):
            from engine.card_effects.ability_keywords import _controller_id, _ask_player, effect_discard
            from engine.effect_keywords import discard as _ek_discard
            cid = _controller_id(card)
            if not (type_filter or class_filter):
                effect_discard(state, cid, _a, random_discard=True)
                return
            hand = state.players[cid].hand
            for _ in range(_a):
                eligible = [c for c in hand.cards if _matches(c)]
                if not eligible:
                    break
                pick = _ask_player(state, cid, [c.slug for c in eligible],
                                   context="Choose a card to discard as a cost")
                chosen = next((c for c in eligible if c.slug == pick), eligible[0])
                _ek_discard(state, chosen, card, origin="hand")
        return can_pay, pay

    if ctype == "REVEAL_CARD_COST_GTE":
        # "Reveal a card with cost N or greater from hand" — play restriction only, no state change
        amount = params.get("amount", 0)
        def can_pay(card, event, state, _a=amount):
            from engine.card_effects.ability_keywords import _controller_id
            return any(
                (getattr(c, 'cost', None) or 0) >= _a
                for c in state.players[_controller_id(card)].hand.cards
            )
        def pay(card, event, state):
            pass  # reveal is informational
        return can_pay, pay

    if ctype == "REVEAL_CARD_COST_LTE":
        # "Reveal a card with cost N or less from hand" — play restriction only
        amount = params.get("amount", 999)
        def can_pay(card, event, state, _a=amount):
            from engine.card_effects.ability_keywords import _controller_id
            return any(
                (getattr(c, 'cost', None) or 0) <= _a
                for c in state.players[_controller_id(card)].hand.cards
            )
        def pay(card, event, state):
            pass
        return can_pay, pay

    if ctype == "BANISH_NAMED_GRAVEYARD_OPTIONAL":
        # "You may banish [slug_contains] from your graveyard. If you do, [bonus via flag]."
        # Always payable (optional). Sets a turn flag if a matching card was banished.
        slug_contains = params.get("slug_contains", "")
        flag = params.get("flag", f"banished_{slug_contains}")
        def can_pay(card, event, state):
            return True  # optional — always legal to play
        def pay(card, event, state, _sc=slug_contains, _f=flag):
            from engine.card_effects.ability_keywords import _controller_id
            cid = _controller_id(card)
            graveyard = state.players[cid].graveyard.cards
            target = next((c for c in graveyard if _sc in c.slug), None)
            if target:
                graveyard.remove(target)
                state.players[cid].banished.add(target)
                state.players[cid].current_turn_effects.append(_f)
        return can_pay, pay

    if ctype == "PUT_HAND_CARD_BOTTOM":
        # "Put a card from your hand on the bottom of your deck" (enlightened_strike)
        def can_pay(card, event, state):
            from engine.card_effects.ability_keywords import _controller_id
            return len(state.players[_controller_id(card)].hand.cards) >= 1
        def pay(card, event, state):
            from engine.card_effects.ability_keywords import _controller_id
            cid = _controller_id(card)
            hand = state.players[cid].hand.cards
            if not hand:
                return
            # Agent sets state.cost_choices["PUT_HAND_CARD_BOTTOM"] = int index before
            # applying the action. Consumed here; absent → random fallback.
            choice = state.cost_choices.pop("PUT_HAND_CARD_BOTTOM", None)
            if choice is not None and isinstance(choice, int) and 0 <= choice < len(hand):
                target = hand[choice]
            else:
                target = random.choice(hand)
            hand.remove(target)
            state.players[cid].deck.cards.append(target)
        return can_pay, pay

    if ctype == "TAP_SELF":
        # {t}: tap the activating card (hero/permanent). Payable if not tapped.
        def can_pay(card, event, state):
            return not getattr(card, 'tapped', False)
        def pay(card, event, state):
            card.tapped = True
        return can_pay, pay

    if ctype == "PAY_LIFE":
        amount = params.get("amount", 1)
        # Coerce a stray/dynamic string amount to an int so the life comparison and
        # subtraction can't TypeError mid-game (a candidate authored it as a string).
        try:
            amount = max(0, int(amount))
        except (TypeError, ValueError):
            amount = 1
        def can_pay(card, event, state, _a=amount):
            from engine.card_effects.ability_keywords import _controller_id
            return state.players[_controller_id(card)].life > _a
        def pay(card, event, state, _a=amount):
            from engine.card_effects.ability_keywords import _controller_id
            try:
                from engine.card_effects.ability_keywords import effect_lose_life
                effect_lose_life(state, _controller_id(card), _a)
            except ImportError:
                state.players[_controller_id(card)].life -= _a
        return can_pay, pay

    if ctype == "DESTROY_PERMANENT":
        target = params.get("target", "")        # "self" -> destroy the activating card itself
        perm_type = params.get("permanent_type", "")
        slug_filter = params.get("slug", "")

        if target == "self":
            # Destroy the card that is paying this cost (e.g. equipment that destroys itself).
            # destroy() resolves the card's actual zone (chest/head/items/...), so this works
            # for equipment in slot zones as well as permanents.
            def can_pay(card, event, state):
                return True  # card must exist to be activating
            def pay(card, event, state):
                from engine.effect_keywords import destroy as _ek_destroy
                _ek_destroy(state, card, None)
            return can_pay, pay

        def can_pay(card, event, state, _pt=perm_type, _sl=slug_filter):
            from engine.card_effects.ability_keywords import _controller_id
            pid = _controller_id(card)
            permanents = getattr(state.players[pid], 'permanents', None)
            if permanents is None:
                return False
            candidates = permanents.cards
            if _sl:
                candidates = [c for c in candidates if c.slug == _sl]
            elif _pt:
                candidates = [c for c in candidates
                              if _pt.upper() in [t.upper() for t in (getattr(c, 'types', None) or [])]]
            return len(candidates) > 0
        def pay(card, event, state, _pt=perm_type, _sl=slug_filter):
            from engine.card_effects.ability_keywords import _controller_id
            pid = _controller_id(card)
            permanents = getattr(state.players[pid], 'permanents', None)
            if not permanents:
                return
            candidates = permanents.cards
            if _sl:
                candidates = [c for c in candidates if c.slug == _sl]
            elif _pt:
                candidates = [c for c in candidates
                              if _pt.upper() in [t.upper() for t in (getattr(c, 'types', None) or [])]]
            if candidates:
                try:
                    from engine.effect_keywords import destroy as _ek_destroy
                    _ek_destroy(state, candidates[0], None)
                except (ImportError, Exception):
                    permanents.cards.remove(candidates[0])
        return can_pay, pay

    # ── alternative costs (pay INSTEAD of normal resource cost) ───────────

    if ctype == "REMOVE_COUNTERS":
        # Generic counter removal (any zone)
        counter_type = params.get("counter_type", "")
        amount = params.get("amount", 1)
        def can_pay(card, event, state, _ct=counter_type, _a=amount):
            from engine.card_effects.ability_keywords import _controller_id
            pid = _controller_id(card)
            total = sum(v for k, v in state.players[pid].counters.items() if k[2] == _ct)
            return total >= _a
        def pay(card, event, state, _ct=counter_type, _a=amount):
            from engine.card_effects.ability_keywords import _controller_id
            pid = _controller_id(card)
            remaining = _a
            keys = [k for k in state.players[pid].counters if k[2] == _ct]
            for key in keys:
                if remaining <= 0:
                    break
                available = state.players[pid].counters[key]
                remove = min(available, remaining)
                state.players[pid].counters[key] = available - remove
                remaining -= remove
        return can_pay, pay

    if ctype == "REMOVE_COUNTERS_FROM_AURAS":
        # e.g. 10000-year-reunion-red: "Remove 3 +1{p} counters from auras you control"
        counter_type = params.get("counter_type", "+1{p}")
        amount = params.get("amount", 1)
        def can_pay(card, event, state, _ct=counter_type, _a=amount):
            from engine.card_effects.ability_keywords import _controller_id
            cid = _controller_id(card)
            total = sum(
                state.players[cid].counters.get(
                    (aura.slug, getattr(aura, 'zone', 'auras'), _ct), 0
                )
                for aura in getattr(state.players[cid], 'auras', [])
            )
            return total >= _a
        def pay(card, event, state, _ct=counter_type, _a=amount):
            from engine.card_effects.ability_keywords import _controller_id
            cid = _controller_id(card)
            remaining = _a
            for aura in list(getattr(state.players[cid], 'auras', [])):
                key = (aura.slug, getattr(aura, 'zone', 'auras'), _ct)
                have = state.players[cid].counters.get(key, 0)
                use = min(have, remaining)
                state.players[cid].counters[key] = have - use
                remaining -= use
                if remaining <= 0:
                    break
        return can_pay, pay

    if ctype == "BANISH_FROM_GRAVEYARD":
        # Scrap: banish N items/equipment from graveyard
        # Supports both card_type (str) and card_types (list) for backwards compat
        card_types_raw = params.get("card_types", params.get("card_type", ""))
        if isinstance(card_types_raw, str):
            card_types = [card_types_raw] if card_types_raw else []
        else:
            card_types = list(card_types_raw)
        amount = params.get("amount", 1)
        def can_pay(card, event, state, _types=card_types, _a=amount):
            from engine.card_effects.ability_keywords import _controller_id
            gy = state.players[_controller_id(card)].graveyard.cards
            eligible = [
                c for c in gy
                if not _types or any(
                    t.upper() in [x.upper() for x in (getattr(c, 'types', None) or [])]
                    for t in _types
                )
            ]
            return len(eligible) >= _a
        def pay(card, event, state, _types=card_types, _a=amount):
            from engine.card_effects.ability_keywords import _controller_id
            cid = _controller_id(card)
            gy = state.players[cid].graveyard.cards
            eligible = [
                c for c in gy
                if not _types or any(
                    t.upper() in [x.upper() for x in (getattr(c, 'types', None) or [])]
                    for t in _types
                )
            ]
            for c in eligible[:_a]:
                gy.remove(c)
                state.players[cid].banished.add(c)
        return can_pay, pay

    if ctype == "PAY_RESOURCES":
        amount = params.get("amount", 0)
        def can_pay(card, event, state, _a=amount):
            from engine.card_effects.ability_keywords import _controller_id
            return state.players[_controller_id(card)].resources >= _a
        def pay(card, event, state, _a=amount):
            from engine.card_effects.ability_keywords import _controller_id
            state.players[_controller_id(card)].resources -= _a
        return can_pay, pay

    if ctype == "PITCH":
        # "pitch a card" / "pitch N" as an activation cost. The controller chooses
        # which card(s) to pitch (CR 8.5.44: to the pitch zone, gaining resources
        # equal to pitch value). Optional pitch-value filter (e.g. "pitch a red
        # card" -> pitch_value 1). Payable iff enough matching cards are in hand.
        amount = params.get("amount", 1)
        pv_filter = params.get("pitch_value")  # 1=red, 2=yellow, 3=blue; None=any

        def _matches(c, _pv=pv_filter):
            if _pv is None:
                return True
            return (getattr(c, 'pitch', None) or getattr(c, 'raw_pitch', None) or 0) == _pv

        def can_pay(card, event, state, _a=amount):
            from engine.card_effects.ability_keywords import _controller_id
            hand = state.players[_controller_id(card)].hand
            return len([c for c in hand.cards if _matches(c)]) >= _a

        def pay(card, event, state, _a=amount):
            from engine.card_effects.ability_keywords import _controller_id, _ask_player
            from engine.effect_keywords import pitch as _ek_pitch
            cid = _controller_id(card)
            for _ in range(_a):
                hand = state.players[cid].hand
                eligible = [c for c in hand.cards if _matches(c)]
                if not eligible:
                    break
                pick = _ask_player(state, cid, [c.slug for c in eligible],
                                   context="Choose a card to pitch as a cost")
                chosen = next((c for c in eligible if c.slug == pick), eligible[0])
                _ek_pitch(state, chosen, cid)
        return can_pay, pay

    # Unknown cost types are authoring errors — fail at JSON load time rather
    # than treating the cost as free (fail-open let bad JSON go unnoticed).
    raise ValueError(f"Unknown DSL cost type: {ctype!r} (params: {params!r})")
