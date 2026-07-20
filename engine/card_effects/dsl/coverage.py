"""Runtime execution coverage for DSL card effects.

The hygiene checks in tests/test_card_json_hygiene.py prove a card's JSON is
*well-formed*. They cannot prove it ever *runs* — an ability whose trigger the
engine never dispatches is structurally perfect and completely inert. That
class of bug (Blacktek Whisperers' graveyard static, Savor Bloodshed's queued
draw) is only visible by playing games and watching what fires.

Usage:

    from engine.card_effects.dsl import coverage
    tracker = coverage.start()
    ...play games...
    tracker = coverage.stop()
    tracker.effects   # {(slug, effect_type), ...} actually executed

Disabled by default: when no tracker is active the instrumentation is a single
module-global identity check, so normal games and the test suite are unaffected.
"""
from __future__ import annotations


class CoverageTracker:
    """Records which authored DSL constructs actually executed."""

    def __init__(self) -> None:
        self.effects: set[tuple[str, str]] = set()    # (card slug, effect_type)
        self.abilities: set[tuple[str, str]] = set()  # (card slug, ability key)

    def record_effect(self, slug: str, effect_type: str) -> None:
        self.effects.add((slug, effect_type))

    def record_ability(self, slug: str, key: str) -> None:
        self.abilities.add((slug, key))

    def merge(self, other: "CoverageTracker") -> None:
        self.effects |= other.effects
        self.abilities |= other.abilities


_TRACKER: CoverageTracker | None = None


def start(tracker: CoverageTracker | None = None) -> CoverageTracker:
    """Begin recording. Returns the active tracker."""
    global _TRACKER
    _TRACKER = tracker or CoverageTracker()
    return _TRACKER


def stop() -> CoverageTracker | None:
    """Stop recording and return the tracker that was active."""
    global _TRACKER
    tracker, _TRACKER = _TRACKER, None
    return tracker


def active() -> CoverageTracker | None:
    return _TRACKER
