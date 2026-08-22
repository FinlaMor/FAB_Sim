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

    # Cost amounts are always numeric (resources/life/cards to pay). Candidate
    # JSON occasionally authors them as strings — either an integer literal
    # ("2") or a dynamic marker ("UP_TO_3", "RUNECHANTS_CONTROLLED") that the
    # simple cost branches here don't resolve. Both blow up in arithmetic/slicing
    # (resources >= "2", cards[:"2"]). No cost branch interprets a marker, so
    # coerce once: integer literal -> its int; any other string -> 0 (a
    # trivially-payable cost) rather than crashing a live game.
    if isinstance(params.get("amount"), str):
        try:
            params = {**params, "amount": int(params["amount"])}
        except (TypeError, ValueError):
            params = {**params, "amount": 0}

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
        # Discard cost with an optional filter (e.g. "discard an Assassin card",
        # "discard a Phoenix Flame", "discard 2 cards with yellow color
        # strips"). The controller chooses which matching card to discard.
        #
        # Only type_filter and class_filter were read, so a cost naming the card
        # by NAME or by COLOUR had no filter at all — and an unfiltered cost
        # here is not merely weaker, it is a different card in two ways: the
        # discard became RANDOM, and can_pay said yes whenever the hand was
        # non-empty, so the card was playable when its cost could not actually
        # be paid. Costs must block play legality.
        #
        # The filter vocabulary is shared with the DISCARD effect
        # (effect_types._hand_card_filter) because the cards use the same words
        # for both.
        from engine.card_effects.dsl.effect_types import _hand_card_filter
        amount = params.get("amount", 1)
        matches = _hand_card_filter(params)

        def can_pay(card, event, state, _a=amount, _m=matches):
            from engine.card_effects.ability_keywords import _controller_id
            hand = state.players[_controller_id(card)].hand
            if _m is None:
                return len(hand.cards) >= _a
            return len([c for c in hand.cards if _m(c, state)]) >= _a

        def pay(card, event, state, _a=amount, _m=matches):
            from engine.card_effects.ability_keywords import _controller_id, effect_discard
            cid = _controller_id(card)
            # Unfiltered stays random: "discard a card" as a cost is paid by a
            # card the player picks, but the corpus's unfiltered uses were
            # authored as random and changing that is a separate question.
            bound = None if _m is None else (lambda c, _s=state: _m(c, _s))
            effect_discard(state, cid, _a, random_discard=(_m is None),
                           matches=bound)
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

    if ctype == "SCRAP":
        # CR 8.3.32 — Scrap: "As an additional cost to play this, you MAY banish
        # an item or equipment from your graveyard." 8.3.32a: paying it means the
        # player has scrapped and that card was scrapped. 8.3.32b: a player
        # cannot scrap if they cannot pay it.
        #
        # Optional, so it never blocks play (can_pay is always True) — unlike a
        # mandatory additional cost, which must gate legality.
        #
        # The player is ASKED. The nearest existing optional cost
        # (BANISH_NAMED_GRAVEYARD_OPTIONAL) silently auto-pays whenever a target
        # exists, which is wrong for "you may" and is not copied here. Banishing
        # also goes through the canonical banish() so the event fires, rather
        # than moving the card between zones by hand.
        def can_pay(card, event, state):
            return True

        def pay(card, event, state):
            from engine.card_effects.ability_keywords import _controller_id, ask_yes_no, ask_optional
            from engine.effect_keywords import banish as _banish, _record_turn_event
            cid = _controller_id(card)
            player = state.players[cid]
            eligible = [c for c in player.graveyard.cards
                        if {"item", "equipment"} & {t.lower() for t in (c.types or [])}]
            if not eligible:
                return                      # 8.3.32b — cannot scrap
            if not ask_yes_no(state, cid, context="Scrap: banish an item or equipment "
                                                  "from your graveyard?"):
                return
            slugs = [c.slug for c in eligible]
            chosen = ask_optional(state, cid, slugs, context="Choose a card to scrap")
            if chosen is None:
                return
            target = next((c for c in eligible if c.slug == chosen), eligible[0])
            # origin_zone MUST be named: banish() only removes the card from its
            # old zone when told which one, so passing None adds it to banished
            # while leaving it in the graveyard — present in both at once.
            _banish(state, target, cid, "graveyard")
            # TWO identities are recorded, because the cards ask both questions:
            #   "if IT scrapped a card"        -> this card's slug
            #   "if it scrapped a HYPER DRIVER" -> the scrapped card's slug/name
            # One marker family serves both; SCRAPPED with no `name` checks the
            # asking card, and with a `name` checks what was scrapped.
            _record_turn_event(state, cid, "scrap",
                               getattr(card, "slug", None),
                               getattr(target, "slug", None),
                               getattr(target, "name", None))
        return can_pay, pay

    if ctype == "BANISH_RANDOM_FROM_GRAVEYARD":
        # "As an additional cost to play this, banish N RANDOM cards from your
        # graveyard." Mandatory and unchosen, unlike
        # BANISH_NAMED_GRAVEYARD_OPTIONAL ("you MAY banish <named>") which is
        # what the one card needing this had been given.
        #
        # Records what it banished under the same `banished_cards` ref the
        # BANISH effect uses, so "if a card with 6 or more {p} is banished THIS
        # WAY" has something to ask about. run_ability pushes the reference
        # scope before paying additional costs, so the effects see it.
        import random as _random
        try:
            amount = max(0, int(params.get("amount", 1)))
        except (TypeError, ValueError):
            amount = 1

        def can_pay(card, event, state, _a=amount):
            from engine.card_effects.ability_keywords import _controller_id
            return len(state.players[_controller_id(card)].graveyard.cards) >= _a

        def pay(card, event, state, _a=amount):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.card_effects.dsl.effect_types import _record_banished
            from engine.effect_keywords import banish as _banish
            cid = _controller_id(card)
            pool = list(state.players[cid].graveyard.cards)
            if len(pool) < _a:
                return
            picked = _random.sample(pool, _a)
            for obj in picked:
                _banish(state, obj, cid, origin_zone="graveyard")
            _record_banished(picked)
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

    if ctype == "TAP_PERMANENT":
        # "{t} an ALLY you control" — tapping something OTHER than the source.
        # TAP_SELF taps the card paying the cost, and a "target" on it is not
        # read, so a card asking to tap an ally was tapping itself. `subtype`
        # names what may be tapped; without one, any untapped permanent will do.
        subtype = str(params.get("subtype") or params.get("target") or "").lower()

        def _candidates(card, state, _sub):
            from engine.card_effects.ability_keywords import _controller_id
            cid = _controller_id(card)
            if cid not in state.players:
                return []
            out = []
            for c in state.players[cid].permanents.cards:
                if getattr(c, "tapped", False):
                    continue
                if _sub and _sub not in [s.lower() for s in (getattr(c, "subtypes", None) or [])] \
                        and _sub not in [t.lower() for t in (getattr(c, "types", None) or [])]:
                    continue
                out.append(c)
            return out

        def can_pay(card, event, state, _sub=subtype):
            return bool(_candidates(card, state, _sub))

        def pay(card, event, state, _sub=subtype):
            from engine.card_effects.ability_keywords import _ask_player, _controller_id
            pool = _candidates(card, state, _sub)
            if not pool:
                return
            cid = _controller_id(card)
            pick = _ask_player(state, cid, [c.slug for c in pool],
                               context=f"Tap which {_sub or 'permanent'}?")
            chosen = next((c for c in pool if c.slug == pick), pool[0])
            chosen.tapped = True
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

    if ctype == "BANISH_FROM_UNDER_SELF":
        # "Banish a card from under Nitro Mechanoid: Attack" — the cost consumes
        # one of the cards this permanent transformed FROM (CR 8.5.36a / 3.0.14
        # sub-cards). This is the reason transform puts objects UNDER the
        # permanent rather than destroying them: they are the ammunition.
        def can_pay(card, event, state):
            return bool(getattr(card, "cards_underneath", None))

        def pay(card, event, state):
            from engine.card_effects.ability_keywords import _ask_player, _controller_id
            from engine.effect_keywords import banish as _banish
            under = list(getattr(card, "cards_underneath", None) or [])
            if not under:
                return
            cid = _controller_id(card)
            if len(under) == 1:
                target = under[0]
            else:
                pick = _ask_player(state, cid, [c.slug for c in under],
                                   context="Choose a card to banish from under this")
                target = next((c for c in under if c.slug == pick), under[0])
            card.cards_underneath.remove(target)
            target.is_sub_card = False
            target.top_card = None
            # origin_zone is None on purpose: the card is not IN a zone's card
            # list while it is a sub-card, so naming one would try to remove it
            # from a list it was never in.
            _banish(state, target, cid)
        return can_pay, pay

    if ctype == "DESTROY_PERMANENTS_OPTIONAL":
        # "As an additional cost to play this, you MAY destroy ANY NUMBER of
        # weapons, equipment and/or non-token items you control." (Cash Out.)
        #
        # Three things the existing DESTROY_PERMANENT cost cannot do and which
        # this text needs: it is optional, it repeats until the player stops,
        # and the COUNT is the whole point ("create a Silver token for each
        # permanent destroyed this way"). It also has to see equipment, which
        # lives in the head/chest/arms/legs/weapon slot zones and never appears
        # in `permanents` — a permanents-only scan finds none of it.
        #
        # The count is published on the state for the DESTROYED_COUNT amount
        # expression, the same way PAY_UP_TO publishes _paid_amount.
        want_types = [t.lower() for t in (params.get("types") or [])]
        exclude_tokens = bool(params.get("exclude_tokens", True))

        def _pool(state, pid, _wt=want_types, _xt=exclude_tokens):
            player = state.players[pid]
            slots = [player.head, player.chest, player.arms, player.legs,
                     player.weapon1, player.weapon2]
            cards = list(player.permanents.cards) + [c for z in slots for c in z.cards]
            out = []
            for c in cards:
                if _xt and getattr(c, "is_token", False):
                    continue
                if _wt and not ({t.lower() for t in (getattr(c, "types", None) or [])}
                                & set(_wt)):
                    continue
                out.append(c)
            return out

        def can_pay(card, event, state):
            return True        # optional — never blocks play

        def pay(card, event, state):
            from engine.card_effects.ability_keywords import (
                _controller_id, ask_optional)
            from engine.effect_keywords import destroy as _ek_destroy
            cid = _controller_id(card)
            destroyed = 0
            while True:
                candidates = _pool(state, cid)
                if not candidates:
                    break
                pick = ask_optional(state, cid, [c.slug for c in candidates],
                                    context="Destroy a permanent as an additional "
                                            "cost? (or stop)")
                if pick is None:
                    break
                target = next((c for c in candidates if c.slug == pick), None)
                if target is None:
                    break
                _ek_destroy(state, target, card)
                destroyed += 1
            state._destroyed_count = destroyed
        return can_pay, pay

    # ── alternative costs (pay INSTEAD of normal resource cost) ───────────

    if ctype == "REMOVE_COUNTERS":
        # Generic counter removal (any zone)
        # "counter" as well as "counter_type": 4 nodes author the short form,
        # and an empty counter type matches no counter, so the cost could never
        # be paid and the ability was unusable.
        counter_type = (params.get("counter_type") or params.get("counter")
                        or params.get("name") or "")
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
        # "banish A PHOENIX FLAME from your graveyard" names one card, and the
        # filter was card TYPE only — so any card in the graveyard paid a cost
        # the card says only one specific card can pay.
        want_name = params.get("name") or params.get("card_name")

        def _eligible(card, state, _types, _name):
            from engine.card_effects.ability_keywords import _controller_id
            gy = state.players[_controller_id(card)].graveyard.cards
            out = [
                c for c in gy
                if not _types or any(
                    t.upper() in [x.upper() for x in (getattr(c, 'types', None) or [])]
                    for t in _types
                )
            ]
            if _name:
                def _flat(text):
                    return "".join(ch for ch in str(text).lower() if ch.isalnum())
                wanted = _flat(_name)
                out = [c for c in out
                       if wanted in (_flat(getattr(c, "name", "") or ""),
                                     _flat(getattr(c, "slug", "") or ""))]
            return out

        def can_pay(card, event, state, _types=card_types, _a=amount, _name=want_name):
            return len(_eligible(card, state, _types, _name)) >= _a

        def pay(card, event, state, _types=card_types, _a=amount, _name=want_name):
            from engine.card_effects.ability_keywords import _controller_id
            cid = _controller_id(card)
            gy = state.players[cid].graveyard.cards
            for c in _eligible(card, state, _types, _name)[:_a]:
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
