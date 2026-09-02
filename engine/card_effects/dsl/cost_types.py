"""Compile JSON cost objects into (check_fn, pay_fn) pairs for the DSL.

All callables use the signature (card, event, state) -> bool/None to match
the convention used by condition_types and effect_types.
"""
from __future__ import annotations
import random
from typing import Any, Callable


def _stamp_discarded(card, discarded):
    """Record on the card being played WHICH cards its discard cost took.

    "If the DISCARDED CARD has 6 or more {p}, this gains go again" has to be
    able to look at that card later, and nothing recorded it: the condition
    read the discarded card off the EVENT, which is the play event and has no
    power, so it answered 0 and the clause could never fire. The printed
    keyword then applied unconditionally, which is why the card looked fine --
    Breakneck Battery's gamble paid out every time.

    Mirrors play.py's `pitched_for_this` stamp, and for the same reason: what
    paid for a card is a fact about that card, settled when it is played, and
    the effect asking about it runs much later.

    Appended rather than assigned, so two discard costs on one card both count.
    """
    if card is None or not discarded:
        return
    existing = list(getattr(card, "discarded_for_this", None) or [])
    card.discarded_for_this = existing + list(discarded)


def _stamp_banished(card, banished):
    """Record on the card being played WHICH cards its banish cost took.

    The banish sibling of _stamp_discarded, and needed for the same reason:
    "if a card with 6 or more {p} is banished THIS WAY" and "if you DO banish a
    card with blood debt" both ask, at resolution, about something that
    happened while paying. Nothing else records it -- the banished zone holds
    every card banished all game, so it cannot answer "this way".
    """
    if card is None or not banished:
        return
    existing = list(getattr(card, "banished_for_this", None) or [])
    card.banished_for_this = existing + list(banished)


def compile_cost(ctype: str, params: dict[str, Any]) -> tuple[Callable, Callable]:
    """Return (check_fn, pay_fn).

    check_fn(card, event, state) -> bool  — True if cost is payable
    pay_fn(card, event, state) -> None    — deduct/resolve the cost
    """

    # Cost amounts are always numeric (resources/life/cards to pay). Candidate
    # JSON occasionally authors them as strings — either an integer literal
    # ("2") or a dynamic marker ("X", "UP_TO_3", "RUNECHANTS_CONTROLLED") that
    # the simple cost branches here don't resolve. Both blow up in
    # arithmetic/slicing (resources >= "2", cards[:"2"]), so coerce once:
    # integer literal -> its int; any other string -> 0 rather than crashing a
    # live game.
    #
    # "No cost branch interprets a marker" was the original reason for
    # flattening to 0, and it is no longer true: DESTROY_PERMANENT resolves its
    # count through _resolve_amount. Flattening made "destroy X Gold" destroy
    # ZERO and cost nothing — a mandatory additional cost that is free. The raw
    # value is kept under "_amount_raw" for branches that CAN resolve it; the
    # rest still see 0, which is a latent trap for the next author rather than a
    # live defect (raise_an_army_yellow is the only card in the corpus with a
    # dynamic cost amount today).
    if isinstance(params.get("amount"), str):
        raw_amount = params["amount"]
        try:
            params = {**params, "amount": int(raw_amount)}
        except (TypeError, ValueError):
            params = {**params, "amount": 0, "_amount_raw": raw_amount}

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
            _stamp_discarded(card, effect_discard(state, _controller_id(card),
                                                  _a, random_discard=True))
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
            _stamp_discarded(card, effect_discard(
                state, cid, _a, random_discard=(_m is None), matches=bound))
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

    if ctype == "CHARGE":
        # CR 8.5.29 — "charge your hero's soul" as a COST, not an effect.
        # v_for_valor_yellow reads "{r}, destroy this, CHARGE your hero's soul:
        # Target attack gains +2{p}". Modelling that as an ON_PLAY effect makes
        # the reaction legal with an EMPTY HAND -- the ability resolves and the
        # cost is simply never paid, which is the one thing a cost must never
        # allow. It also charged hand position 0 with nobody choosing.
        amount = params.get("amount", 1)
        # "As an additional cost to play this, you MAY charge your hero's soul.
        # If a YELLOW card is charged this way, ..." -- 27 cards in the corpus.
        # An optional additional cost must never block the play, and the payoff
        # has to be able to ask WHAT was charged, so the colour of the charged
        # card is stamped on the card being played. A turn-scoped marker would
        # leak to the next card played this turn; "this way" is per-play.
        optional = bool(params.get("optional") or params.get("may"))

        def can_pay(card, event, state, _a=amount, _opt=optional):
            from engine.card_effects.ability_keywords import _controller_id
            if _opt:
                return True
            return len(state.players[_controller_id(card)].hand.cards) >= _a

        def pay(card, event, state, _a=amount, _opt=optional):
            from engine.card_effects.ability_keywords import (
                _ask_player, _controller_id, ask_optional)
            from engine.effect_keywords import charge as _ek_charge
            cid = _controller_id(card)
            for _ in range(_a):
                hand = state.players[cid].hand.cards
                if not hand:
                    return
                if _opt:
                    pick = ask_optional(
                        state, cid, [c.slug for c in hand],
                        context="Charge a card to your hero's soul? (optional "
                                "additional cost)")
                    if pick is None:
                        return
                    chosen = next((c for c in hand if c.slug == pick), hand[0])
                elif len(hand) == 1:
                    chosen = hand[0]
                else:
                    pick = _ask_player(state, cid, [c.slug for c in hand],
                                       context="Choose a card to charge to your "
                                               "hero's soul")
                    chosen = next((c for c in hand if c.slug == pick), hand[0])
                # Card.color is None on real cards; the printing is base_color.
                colour = (getattr(chosen, "color", None)
                          or getattr(chosen, "base_color", None) or "")
                _ek_charge(state, chosen, cid, source_player_id=cid)
                if card is not None:
                    card.dsl_charged_color = str(colour).lower()
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
        # "As an additional cost to play this, destroy X GOLD you control",
        # "{t}, destroy a Gold you control: ...".
        #
        # This read only `slug` and `permanent_type`, and neither of the two
        # cards using it says either -- both say `asset`. With no filter the
        # cost is not merely weaker: can_pay was true whenever the player
        # controlled ANY permanent, so the card was playable with no Gold at
        # all, and paying it destroyed an arbitrary permanent instead. It also
        # ignored `amount`, so "destroy X" destroyed one. Costs must block play
        # legality.
        #
        # The filter vocabulary is shared with the EFFECT of the same name
        # (effect_types._permanent_filter); the two read different subsets of it
        # before and neither read `asset`.
        target = params.get("target", "")        # "self" -> destroy the payer
        if target == "self":
            # destroy() resolves the card's actual zone (chest/head/items/...),
            # so this works for equipment in slot zones as well as permanents.
            def can_pay(card, event, state):
                return True  # card must exist to be activating

            def pay(card, event, state):
                from engine.effect_keywords import destroy as _ek_destroy
                _ek_destroy(state, card, None)
            return can_pay, pay

        from engine.card_effects.dsl.effect_types import (
            _permanent_filter, _resolve_amount)
        matches = _permanent_filter(params)
        # "_amount_raw" survives compile_cost's string->0 coercion; see the
        # note at the top of this function for why that coercion exists and why
        # a branch that resolves dynamic amounts must not use its output.
        amount = params.get("_amount_raw",
                            params.get("amount", params.get("count", 1)))

        def _pool(card, state, _m=matches):
            from engine.card_effects.ability_keywords import _controller_id
            pid = _controller_id(card)
            permanents = getattr(state.players[pid], 'permanents', None)
            if permanents is None:
                return pid, []
            cards = list(permanents.cards)
            if _m is not None:
                cards = [c for c in cards if _m(c, state)]
            return pid, cards

        def _wanted(card, state, _a=amount):
            try:
                return max(0, int(_resolve_amount(_a, state, card)))
            except (TypeError, ValueError):
                return 1

        def can_pay(card, event, state):
            _pid, cands = _pool(card, state)
            return len(cands) >= _wanted(card, state)

        def pay(card, event, state):
            from engine.card_effects.ability_keywords import _ask_player
            from engine.effect_keywords import destroy as _ek_destroy
            pid, cands = _pool(card, state)
            for _ in range(_wanted(card, state)):
                if not cands:
                    return
                if len(cands) == 1:
                    chosen = cands[0]
                else:
                    pick = _ask_player(state, pid, [c.slug for c in cands],
                                       context="Choose a permanent to destroy as a cost")
                    chosen = next((c for c in cands if c.slug == pick), cands[0])
                cands.remove(chosen)
                _ek_destroy(state, chosen, card)
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

    if ctype == "BANISH_FROM_HAND":
        # "As an additional cost to play this, banish a random card FROM YOUR
        # HAND" (Ram Raider) / "you MAY banish a card with blood debt from your
        # hand" (Shadow of Ursur).
        #
        # There was no hand-banish cost, so both cards were authored against
        # the wrong zone -- DISCARD_RANDOM and BANISH_FROM_GRAVEYARD -- which is
        # not a smaller version of the printed cost but a different one: it
        # takes from the wrong place, and on Shadow of Ursur it made an OPTIONAL
        # cost mandatory, so a hand with no blood-debt card could not play the
        # card at all.
        #
        # Filters come from the shared hand vocabulary (_hand_card_filter), so
        # "a card with blood debt" is {"keyword": "blood debt"} exactly as the
        # DISCARD_CARD cost spells it.
        from engine.card_effects.dsl.effect_types import _hand_card_filter
        amount = int(params.get("amount", 1) or 1)
        random_pick = bool(params.get("random"))
        # An OPTIONAL additional cost must never block the play (CR 5.1.6); the
        # payoff is gated on whether it was actually paid, which
        # `banished_for_this` answers.
        optional = bool(params.get("optional"))
        matches = _hand_card_filter(params)
        face_down = bool(params.get("face_down"))

        def _pool(card, state, _m=matches):
            from engine.card_effects.ability_keywords import _controller_id
            hand = state.players[_controller_id(card)].hand.cards
            if _m is None:
                return list(hand)
            return [c for c in hand if _m(c, state)]

        def can_pay(card, event, state, _a=amount, _opt=optional):
            if _opt:
                return True
            return len(_pool(card, state)) >= _a

        def pay(card, event, state, _a=amount, _rand=random_pick,
                _opt=optional, _fd=face_down):
            import random as _random
            from engine.card_effects.ability_keywords import (_controller_id,
                                                              _ask_player,
                                                              ask_optional)
            from engine.effect_keywords import banish as _ek_banish
            cid = _controller_id(card)
            taken = []
            for _ in range(_a):
                pool = _pool(card, state)
                if not pool:
                    break
                if _opt:
                    pick = ask_optional(
                        state, cid, [c.slug for c in pool],
                        context="Banish a card from your hand as an "
                                "additional cost?")
                    if pick is None:
                        break
                    chosen = next((c for c in pool if c.slug == pick), pool[0])
                elif _rand:
                    chosen = _random.choice(pool)
                elif len(pool) == 1:
                    chosen = pool[0]
                else:
                    pick = _ask_player(state, cid, [c.slug for c in pool],
                                       context="Choose a card to banish")
                    chosen = next((c for c in pool if c.slug == pick), pool[0])
                # Through the canonical keyword (CR 8.5.1) so the event fires
                # and replacement effects can intercept it. origin_zone must be
                # passed or banish leaves the card in hand while also adding it
                # to the banished zone -- present in both at once.
                _ek_banish(state, chosen, cid, origin_zone="hand",
                           face_down=_fd)
                taken.append(chosen)
            _stamp_banished(card, taken)
        return can_pay, pay

    if ctype in ("BANISH_FROM_SOUL", "BANISH_SOUL"):
        # "Banish 2 cards from your soul", "banish X cards from your soul".
        #
        # THE SOUL IS NOT THE GRAVEYARD. CR 3.11.5: a hero's soul is the
        # collection of sub-objects under the hero card. Both implemented cards
        # printing this cost paid it from somewhere else -- teklovossen from the
        # GRAVEYARD, war_cry_of_themis from nowhere at all -- and the
        # substitution is not a smaller version of the cost: the soul is a
        # scarce, deliberately-fed resource that other cards count, while the
        # graveyard fills up on its own. Paying from the graveyard is close to
        # free.
        #
        # X IS CHOSEN BY THE PLAYER when paying, and stamped on the card so the
        # payoff can read it -- `{"type": "X"}` resolves to card.x_paid, and
        # play.py only stamps that for a card's PLAY cost, not for an activated
        # ability's. Zero is a legal choice, so an X cost never blocks the
        # activation.
        # compile_cost flattens a non-numeric amount to 0 and keeps the original
        # under "_amount_raw" for branches that can resolve it -- so reading
        # "amount" here would see 0, not "X", and the ability would quietly cost
        # a flat 1 card. That is the trap the preamble's own comment warns about.
        raw_amount = params.get("_amount_raw", params.get("amount", 1))
        is_x = str(raw_amount).strip().upper() == "X"
        if is_x:
            amount = 1
        else:
            try:
                amount = int(raw_amount)
            except (TypeError, ValueError):
                amount = 1
        optional = bool(params.get("optional"))

        def _soul_pool(card, state):
            from engine.card_effects.ability_keywords import _controller_id
            player = state.players[_controller_id(card)]
            soul = getattr(player, "soul", None)
            return list(getattr(soul, "cards", []) or [])

        def can_pay(card, event, state, _a=amount, _opt=optional, _x=is_x):
            if _opt or _x:
                return True
            return len(_soul_pool(card, state)) >= _a

        def pay(card, event, state, _a=amount, _opt=optional, _x=is_x):
            from engine.card_effects.ability_keywords import (_controller_id,
                                                              _ask_player,
                                                              ask_optional)
            from engine.effect_keywords import banish as _ek_banish
            cid = _controller_id(card)
            pool = _soul_pool(card, state)
            if _x:
                # Every count the soul can actually pay, zero included --
                # LARGEST FIRST, following this file's decision convention that
                # real options precede the opt-out so a default agent acts. For
                # an X cost, paying 0 IS the opt-out: it makes the payoff do
                # nothing, and a default agent that always chose it would never
                # exercise the card in self-play.
                choices = [str(n) for n in range(len(pool), -1, -1)]
                pick = _ask_player(state, cid, choices,
                                   context="Banish how many cards from your soul?")
                try:
                    want = int(pick)
                except (TypeError, ValueError):
                    want = 0
                want = max(0, min(want, len(pool)))
            else:
                want = _a

            taken = []
            for _ in range(want):
                pool = _soul_pool(card, state)
                if not pool:
                    break
                if _opt:
                    choice = ask_optional(
                        state, cid, [c.slug for c in pool],
                        context="Banish a card from your soul as an "
                                "additional cost?")
                    if choice is None:
                        break
                    chosen = next((c for c in pool if c.slug == choice), pool[0])
                elif len(pool) == 1:
                    chosen = pool[0]
                else:
                    choice = _ask_player(state, cid, [c.slug for c in pool],
                                         context="Choose a card to banish from "
                                                 "your soul")
                    chosen = next((c for c in pool if c.slug == choice), pool[0])
                # Through the canonical keyword so the event fires, and with
                # origin_zone or the card sits in the soul and the banished zone
                # at once.
                _ek_banish(state, chosen, cid, origin_zone="soul")
                taken.append(chosen)

            # Publish what was actually paid, for "X" and for PAID_AMOUNT.
            card.x_paid = len(taken)
            state._paid_amount = len(taken)
            _stamp_banished(card, taken)
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
        # "banish a card WITH 1{p} from your graveyard" — an unread power
        # requirement let ANY card in the graveyard pay a cost the text says
        # only a 1-power card can pay. On the cost side that is not a weakened
        # effect: it legalises a play whose cost cannot actually be met.
        want_power = params.get("pitch_power", params.get("power"))
        # "You MAY banish ..." — an optional additional cost never blocks the
        # play; the payoff is gated on whether it was actually paid, via the
        # same turn flag BANISH_NAMED_GRAVEYARD_OPTIONAL uses.
        optional = bool(params.get("optional"))
        paid_flag = params.get("flag", "banished_from_graveyard")

        def _eligible(card, state, _types, _name, _power=want_power):
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
            if _power is not None:
                try:
                    need = int(_power)
                except (TypeError, ValueError):
                    need = None
                if need is not None:
                    out = [c for c in out
                           if (getattr(c, "power", None)
                               if getattr(c, "power", None) is not None
                               else getattr(c, "base_power", None)) == need]
            return out

        def can_pay(card, event, state, _types=card_types, _a=amount,
                    _name=want_name, _opt=optional):
            if _opt:
                return True
            return len(_eligible(card, state, _types, _name)) >= _a

        def pay(card, event, state, _types=card_types, _a=amount,
                _name=want_name, _opt=optional, _flag=paid_flag):
            from engine.card_effects.ability_keywords import (
                _controller_id, ask_optional)
            cid = _controller_id(card)
            gy = state.players[cid].graveyard.cards
            eligible = _eligible(card, state, _types, _name)
            if _opt:
                # "You MAY banish ... WHEN YOU DO, this gains +1{p} and go
                # again." Paying it unasked hands the player a cost they did
                # not choose; skipping the flag hands them the bonus for free.
                if not eligible:
                    return
                pick = ask_optional(state, cid, [c.slug for c in eligible],
                                    context="Banish a card from your graveyard "
                                            "as an additional cost?")
                if pick is None:
                    return
                chosen = [next((c for c in eligible if c.slug == pick),
                               eligible[0])]
            else:
                chosen = eligible[:_a]
            for c in chosen:
                gy.remove(c)
                state.players[cid].banished.add(c)
            if chosen and _flag:
                state.players[cid].current_turn_effects.append(_flag)
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
