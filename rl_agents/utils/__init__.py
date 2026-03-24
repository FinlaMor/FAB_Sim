"""rl_agents.utils — Shared utilities for RL agent training and evaluation.

Consolidates helper functions that were previously duplicated across
iql.py, talishar_iql.py, train_iql.py, train_transformer_iql.py,
evaluate_iql_vs_random.py, collect_iql_mixed_data.py, and others.
"""
from __future__ import annotations

from rl_agents.utils.device import default_device, resolve_device
from rl_agents.utils.mlp import build_mlp, expectile_loss
from rl_agents.utils.seed import resolve_base_seed
from rl_agents.utils.card_helpers import card_slug, normalise_action_for_embedder, safe_float, safe_int
from rl_agents.utils.matchups import DECK_BY_HERO, MATCHUP_SPECS

__all__ = [
    "resolve_device",
    "default_device",
    "build_mlp",
    "expectile_loss",
    "resolve_base_seed",
    "card_slug",
    "normalise_action_for_embedder",
    "safe_int",
    "safe_float",
    "DECK_BY_HERO",
    "MATCHUP_SPECS",
]
