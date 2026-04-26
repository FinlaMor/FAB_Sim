"""Compile JSON cost objects into (check_fn, pay_fn) callables."""
from __future__ import annotations
from typing import Any, Callable


def compile_cost(ctype: str, params: dict[str, Any]) -> tuple[Callable, Callable]:
    """Return (check_fn, pay_fn). check_fn(card, state)->bool; pay_fn(card, state)->None."""

    if ctype == "REMOVE_COUNTERS":
        counter_type = params.get("counter_type", "")
        amount = params.get("amount", 1)

        def _check(card, state, _ct=counter_type, _a=amount):
            from engine.card_effects.ability_keywords import _controller_id
            pid = _controller_id(card)
            total = sum(v for k, v in state.players[pid].counters.items() if k[2] == _ct)
            return total >= _a

        def _pay(card, state, _ct=counter_type, _a=amount):
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

        return _check, _pay

    if ctype == "BANISH_FROM_GRAVEYARD":
        card_type = params.get("card_type", "")
        amount = params.get("amount", 1)

        def _check(card, state, _ct=card_type, _a=amount):
            from engine.card_effects.ability_keywords import _controller_id
            pid = _controller_id(card)
            graveyard = state.players[pid].graveyard
            matches = [c for c in graveyard.cards
                       if not _ct or _ct.upper() in [t.upper() for t in (c.types or [])]]
            return len(matches) >= _a

        def _pay(card, state, _ct=card_type, _a=amount):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import banish as _ek_banish
            pid = _controller_id(card)
            graveyard = state.players[pid].graveyard
            matches = [c for c in graveyard.cards
                       if not _ct or _ct.upper() in [t.upper() for t in (c.types or [])]]
            for c in matches[:_a]:
                _ek_banish(state, c, pid, "graveyard")

        return _check, _pay

    if ctype == "DISCARD_CARD":
        amount = params.get("amount", 1)
        type_filter = params.get("type_filter", "")

        def _check(card, state, _a=amount, _tf=type_filter):
            from engine.card_effects.ability_keywords import _controller_id
            pid = _controller_id(card)
            hand = state.players[pid].hand
            if _tf:
                matches = [c for c in hand.cards
                           if _tf.upper() in [t.upper() for t in (c.types or [])]]
                return len(matches) >= _a
            return len(hand.cards) >= _a

        def _pay(card, state, _a=amount):
            from engine.card_effects.ability_keywords import _controller_id, effect_discard
            effect_discard(state, _controller_id(card), _a, random_discard=True)

        return _check, _pay

    if ctype == "PAY_LIFE":
        amount = params.get("amount", 1)

        def _check(card, state, _a=amount):
            from engine.card_effects.ability_keywords import _controller_id
            return state.players[_controller_id(card)].life > _a

        def _pay(card, state, _a=amount):
            from engine.card_effects.ability_keywords import _controller_id, effect_lose_life
            effect_lose_life(state, _controller_id(card), _a)

        return _check, _pay

    if ctype == "DESTROY_PERMANENT":
        perm_type = params.get("permanent_type", "")

        def _check(card, state, _pt=perm_type):
            from engine.card_effects.ability_keywords import _controller_id
            pid = _controller_id(card)
            permanents = state.players[pid].permanents
            if _pt:
                return any(_pt.upper() in [t.upper() for t in (c.types or [])]
                           for c in permanents.cards)
            return len(permanents.cards) > 0

        def _pay(card, state, _pt=perm_type):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import destroy as _ek_destroy
            pid = _controller_id(card)
            permanents = state.players[pid].permanents
            targets = ([c for c in permanents.cards
                        if _pt.upper() in [t.upper() for t in (c.types or [])]]
                       if _pt else list(permanents.cards))
            if targets:
                _ek_destroy(state, targets[0], None)

        return _check, _pay

    # Unknown cost — always payable, no-op pay
    return (lambda card, state: True), (lambda card, state: None)
