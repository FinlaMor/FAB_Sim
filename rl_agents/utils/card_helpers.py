"""rl_agents/utils/card_helpers.py — Shared card/action helper functions.

Consolidates _card_slug(), _normalise_action_for_embedder(), _safe_int(),
and _safe_float() from collect_iql_mixed_data.py, evaluate_iql_vs_random.py,
heuristic_bot.py, game_data.py, and fab_transformer.py.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Optional

from engine.actions import Action


def safe_int(val: Any, default: int = 0) -> int:
    """Convert *val* to int, returning *default* on failure."""
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def safe_float(val: Any, default: float = 0.0) -> float:
    """Convert *val* to float, treating None/empty/``*`` as *default*."""
    if val is None or val == "" or val == "*":
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def card_slug(card: Any) -> Optional[str]:
    """Extract the slug string from a card object (or stringify it)."""
    if card is None:
        return None
    if hasattr(card, "slug"):
        return card.slug
    return str(card)


def normalise_action_for_embedder(action: Action, player_id: int | None = None) -> Action:
    """Normalise an Action's card references to slug strings for the embedder.

    Args:
        action: The Action dataclass to normalise.
        player_id: Optional player ID override. When provided, the returned
            Action will have its ``player_id`` set to this value.  When *None*,
            the original ``player_id`` is preserved.
    """
    pitch_cards = [(card_slug(c) or "") for c in (action.pitch_cards or [])]
    pitch_cards = [slug for slug in pitch_cards if slug]

    targets = [(card_slug(t) or "") for t in (action.targets or [])]
    targets = [slug for slug in targets if slug]

    kwargs: dict[str, Any] = {"pitch_cards": pitch_cards, "targets": targets}
    if player_id is not None:
        kwargs["player_id"] = player_id
    return replace(action, **kwargs)
