"""Game execution context tracking.

Provides a thread-local context flag that distinguishes card-effect-initiated
zone moves from rule-initiated zone moves (CR 3.0.11/3.0.12).

Usage
-----
Card effect dispatch sites wrap their calls with effect_context():

    from engine.context import effect_context

    with effect_context():
        PLAY_ABILITIES[slug](state, player_id, ...)

Zone.add() reads the flag via is_effect_context():

    from engine.context import is_effect_context

    source = "effect" if is_effect_context() else "rule"
"""
from __future__ import annotations

import threading
from contextlib import contextmanager

_ctx = threading.local()


def is_effect_context() -> bool:
    """Return True if we are currently inside an effect_context() block."""
    return getattr(_ctx, "depth", 0) > 0


def push_effect_source(card) -> None:
    """Record the card whose ability is currently executing (for effects that
    need to know their source, e.g. Ripple Away gating on 'action card effect')."""
    stack = getattr(_ctx, "source_stack", None)
    if stack is None:
        stack = _ctx.source_stack = []
    stack.append(card)


def pop_effect_source() -> None:
    stack = getattr(_ctx, "source_stack", None)
    if stack:
        stack.pop()


def current_effect_source():
    """The card whose ability is currently executing, or None."""
    stack = getattr(_ctx, "source_stack", None)
    return stack[-1] if stack else None


# ---------------------------------------------------------------------------
# Ability-scoped references
# ---------------------------------------------------------------------------
# Effects in one ability often need to share an object: "look at the top card,
# destroy IT, and if you do, THIS gets +4". Without somewhere to put that
# card, each such sentence has to collapse into a single bespoke Python
# function named after the card — which is why two thirds of the DSL's effect
# types had exactly one user.
#
# An effect writes with "into": "<name>" and a later effect reads with
# "ref": "<name>". The scope is one ability execution, pushed and popped by
# run_ability, so a nested ability (a trigger resolving mid-resolution) cannot
# clobber the outer one's references.
#
# This replaced state.dsl_look_buffer, which was the same idea with one
# unnamed slot living on the game state: it could not express two references
# at once and was never cleared between abilities.


def push_refs() -> None:
    """Begin a fresh reference scope for one ability execution."""
    stack = getattr(_ctx, "ref_stack", None)
    if stack is None:
        stack = _ctx.ref_stack = []
    stack.append({})


def pop_refs() -> None:
    stack = getattr(_ctx, "ref_stack", None)
    if stack:
        stack.pop()


def set_ref(name: str, value) -> None:
    """Store an object under *name* in the current ability's scope."""
    stack = getattr(_ctx, "ref_stack", None)
    if stack:
        stack[-1][name] = value


def get_ref(name: str, default=None):
    """Read a reference from the current scope, falling back to outer scopes.

    Falling back matters for effects injected into a nested trigger: they were
    authored alongside the outer effects and should still see their names.
    """
    stack = getattr(_ctx, "ref_stack", None) or []
    for scope in reversed(stack):
        if name in scope:
            return scope[name]
    return default


@contextmanager
def effect_context():
    """Mark all Zone.add() calls within this block as effect-sourced (CR 3.0.11).

    Reentrant — nested effect_context() blocks are safe.
    """
    _ctx.depth = getattr(_ctx, "depth", 0) + 1
    try:
        yield
    finally:
        _ctx.depth -= 1
