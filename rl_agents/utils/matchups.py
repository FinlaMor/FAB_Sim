"""rl_agents/utils/matchups.py — Shared matchup constants.

Consolidates DECK_BY_HERO and MATCHUP_SPECS from collect_iql_mixed_data.py
and evaluate_iql_vs_random.py.
"""
from __future__ import annotations


DECK_BY_HERO: dict[str, str] = {
    "kayo_underhanded_cheat": "kayo_underhanded_cheat_CC_lite.txt",
    "oscillio_constella_intelligence": "oscillio_constella_intelligence_CC_lite.txt",
}


MATCHUP_SPECS: list[dict[str, str]] = [
    {
        "name": "kayo_vs_kayo",
        "p1_hero": "kayo_underhanded_cheat",
        "p2_hero": "kayo_underhanded_cheat",
    },
]
