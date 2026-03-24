"""rl_agents/utils/seed.py — Shared seed resolution helpers.

Consolidates _resolve_base_seed() from collect_iql_mixed_data.py and
evaluate_iql_vs_random.py.
"""
from __future__ import annotations

import random


def resolve_base_seed(seed: int | None) -> int:
    """Return *seed* if provided, else generate a random 31-bit integer."""
    if seed is not None:
        return int(seed)
    return random.SystemRandom().randrange(1, 2_147_483_647)
