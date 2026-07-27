"""rl_agents/utils/matchups.py — Shared matchup constants.

Single source of truth for DECK_BY_HERO and MATCHUP_SPECS, imported by both
collect_iql_mixed_data.py (data collection) and evaluate_iql_vs_random.py
(evaluation) so collection and eval always agree on the deck set.

The playable set is the three functional CC test decks (Victor / Kayo / Arakni),
covered end-to-end by the game-transcript audit. MATCHUP_SPECS is their
round-robin (each distinct cross pairing).
"""
from __future__ import annotations


DECK_BY_HERO: dict[str, str] = {
    "kayo_underhanded_cheat": "kayo_underhanded_cheat_CC_lite.txt",
    "victor_goldmane_high_and_mighty": "victor_goldmane_high_and_mighty_CC_lite.txt",
    "arakni_marionette": "arakni_marionette_CC_lite.txt",
}


MATCHUP_SPECS: list[dict[str, str]] = [
    {
        "name": "victor_vs_kayo",
        "p1_hero": "victor_goldmane_high_and_mighty",
        "p2_hero": "kayo_underhanded_cheat",
    },
    {
        "name": "victor_vs_arakni",
        "p1_hero": "victor_goldmane_high_and_mighty",
        "p2_hero": "arakni_marionette",
    },
    {
        "name": "kayo_vs_arakni",
        "p1_hero": "kayo_underhanded_cheat",
        "p2_hero": "arakni_marionette",
    },
]
