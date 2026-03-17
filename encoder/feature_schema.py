"""Shared feature schema registries and compatibility helpers for embedders.

This module centralizes high-churn vocabularies (keywords, counters, alt-cost tags)
so Action/Card/GameState embedders stay index-aligned. It also provides lightweight
schema metadata/fingerprint utilities for checkpoint compatibility checks.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


EMBEDDER_SCHEMA_VERSION = 2


# Keep this list append-only to preserve stable keyword indices.
BASE_CARD_KEYWORDS = [
    "Go Again", "Dominate", "Phantasm", "Blood Debt", "Ward",
    "Arcane Barrier", "Boost", "Scrap", "Crush", "Intimidate",
    "Wager", "Guardwell", "Battleworn", "Temper", "Blade Break",
    "Reprise", "Combo", "Legendary", "Spellvoid", "Spectra",
    "Opt", "Charge", "Heave", "Reload", "Quell", "Negate",
    "Fuse", "Rupture", "Overpower", "Indestructible",
    "Arcane Shelter", "Beat Chest", "Cloaked", "Crank", "Meld", "Modular",
    "Perched", "Piercing", "Protect", "Rune Gate", "Ambush", "Essence",
    "Fusion", "Pairs", "Specialization", "Universal", "Watery Grave",
    "Unlimited", "Transcend", "Channel", "Galvanize", "Contract",
]
RESERVED_KEYWORD_SLOTS = [f"__reserved_keyword_{i:02d}__" for i in range(16)]
KEYWORD_OOV_TOKEN = RESERVED_KEYWORD_SLOTS[0]
CARD_KEYWORDS = BASE_CARD_KEYWORDS + RESERVED_KEYWORD_SLOTS


# Keep this list append-only to preserve stable counter indices.
BASE_COUNTER_TYPES = [
    "plus_power", "minus_power", "plus_defense", "minus_defense",
    "steam", "flow", "suspense", "verse", "energy",
    "aim", "doom", "balance", "rust", "storm", "stain", "raze", "gold", "lesson", "frost",
    "vigor", "charge", "blood_debt", "ancestral", "crouching", "hidden",
    "spectral", "illusion", "soul", "rum", "plunder", "age", "seismic", "rage", "fury", "inventory",
]
RESERVED_COUNTER_SLOTS = [f"__reserved_counter_{i:02d}__" for i in range(8)]
COUNTER_OOV_TYPE = RESERVED_COUNTER_SLOTS[0]
COUNTER_TYPES = BASE_COUNTER_TYPES + RESERVED_COUNTER_SLOTS


COUNTER_NORMALIZERS = {
    "energy": 3.0,
    "rust": 3.0,
    "stain": 3.0,
    "lesson": 3.0,
    "frost": 3.0,
}


PARAMETERIZED_KEYWORD_NORMALIZERS = {
    "Ward": 3.0,
    "Arcane Barrier": 2.0,
    "Boost": 1.0,
    "Quell": 1.0,
    "Spellvoid": 1.0,
    "Arcane Shelter": 2.0,
}


STEP_VOCABULARY = [
    "begin_game",
    "start_phase",
    "action",
    "combat_layer", "combat_attack",
    "combat_defend", "combat_reaction", "combat_damage",
    "combat_resolution", "combat_close",
    "end_phase_beginning",
    "end_phase_cleanup",
    "end_turn",
    "end_game",
]

PHASE_VOCABULARY = ["start", "action", "end"]


ACTION_ALT_COST_TYPES = [
    "rune_gate",
    "cash_in",
    "rise_above",
    "life_of_party",
    "double_down",
    "reunion",
    "soul_reaping",
    "meld",
]


def normalize_counter(counter_type: str, count: float) -> float:
    """Normalize counter counts by type-specific scales."""
    denom = COUNTER_NORMALIZERS.get(counter_type, 1.0)
    if denom <= 0:
        return float(count)
    return float(count) / float(denom)


def schema_fingerprint(payload: dict[str, Any]) -> str:
    """Create a stable short hash for schema metadata payloads."""
    stable_payload = dict(payload)
    stable_payload.pop("schema_fingerprint", None)
    blob = json.dumps(stable_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def build_schema_metadata(embedder: str, d_model: int, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build schema metadata bundle with registry snapshots and fingerprint."""
    payload: dict[str, Any] = {
        "schema_version": EMBEDDER_SCHEMA_VERSION,
        "embedder": embedder,
        "d_model": int(d_model),
        "keyword_vocab_size": len(CARD_KEYWORDS),
        "counter_vocab_size": len(COUNTER_TYPES),
        "card_keywords": list(CARD_KEYWORDS),
        "counter_types": list(COUNTER_TYPES),
    }
    if extra:
        payload.update(extra)
    payload["schema_fingerprint"] = schema_fingerprint(payload)
    return payload


def validate_schema_metadata(
    expected: dict[str, Any],
    actual: dict[str, Any],
    strict: bool = True,
) -> tuple[bool, list[str]]:
    """Validate an external schema payload against the local expected schema."""
    required_keys = [
        "schema_version",
        "embedder",
        "d_model",
        "keyword_vocab_size",
        "counter_vocab_size",
        "schema_fingerprint",
    ]
    mismatches: list[str] = []

    for key in required_keys:
        if key not in actual:
            mismatches.append(f"missing key: {key}")

    for key in required_keys:
        if key in expected and key in actual and expected[key] != actual[key]:
            mismatches.append(f"{key}: expected={expected[key]} actual={actual[key]}")

    if strict:
        return (len(mismatches) == 0, mismatches)
    return (True, mismatches)
