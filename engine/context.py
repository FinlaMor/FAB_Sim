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
