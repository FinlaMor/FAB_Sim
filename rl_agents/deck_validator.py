"""deck_validator.py — Standalone deck validation gate for training pipelines.

Wraps validate_deck_legality() from fab_constants.py and adds weapon/equipment
presence checks.  Used to filter deck pools before training or evolution runs.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from engine.card import CardDB
from engine.deck import load_deck
from rl_agents.fab_constants import validate_deck_legality

logger = logging.getLogger(__name__)


_HERO_SLUG_ALIASES: dict[str, str] = {
    "jarl_vetreii": "jarl_vetreidi",
    "fab_jarl_vetreii_deck_analysis_": "jarl_vetreidi",
}


def validate_single_deck(
    deck_path: str,
    card_db: CardDB,
    slug_index: dict,
    fmt: str = "cc",
) -> tuple[bool, list[str]]:
    """Validate a single deck file.

    Checks:
      (a) class/talent legality via validate_deck_legality()
      (b) at least 1 weapon present
      (c) at least 1 equipment piece present

    Args:
        deck_path:   path to the deck text file.
        card_db:     CardDB instance for card lookups.
        slug_index:  the ``by_slug`` dict from slug_index.json.
        fmt:         format key for banned-card lookup (default ``"cc"``).

    Returns:
        (is_valid, violations) where *violations* is a list of human-readable
        strings (empty when the deck is legal).
    """
    violations: list[str] = []

    # ── load deck ──────────────────────────────────────────────────────────
    try:
        deck_data = load_deck(deck_path, card_db)
    except Exception as exc:
        violations.append(f"Failed to load deck: {exc}")
        return False, violations

    hero_slug: str | None = deck_data.get("hero")
    if hero_slug:
        hero_slug = _HERO_SLUG_ALIASES.get(hero_slug, hero_slug)
    weapon_slug: str | None = deck_data.get("weapon")
    equipment: dict = deck_data.get("equipment", {})
    cards: list = deck_data.get("cards", [])

    # ── (b) weapon check ──────────────────────────────────────────────────
    # Gravy Bones is the only CC-legal hero who intentionally runs no weapon.
    # Kayo has a single weapon zone by design, so only one weapon is expected.
    _WEAPONLESS_HEROES: frozenset[str] = frozenset({"gravy_bones_shipwrecked_looter"})
    _SINGLE_WEAPON_SLOT_HEROES: frozenset[str] = frozenset({"kayo_underhanded_cheat"})
    weapons: list = deck_data.get("weapons", [weapon_slug] if weapon_slug else [])
    # A 2H weapon occupies both weapon slots by FAB rules — one slug is sufficient.
    weapon_is_2h = False
    if weapons:
        w_card = card_db.get(weapons[0])
        if w_card is not None:
            w_tokens = set((w_card.types or []) + (w_card.subtypes or []))
            weapon_is_2h = "2H" in w_tokens or "TwoHanded" in w_tokens
    if not weapons and hero_slug not in _WEAPONLESS_HEROES:
        violations.append("Deck has no weapon.")
    elif (len(weapons) < 2
          and not weapon_is_2h
          and hero_slug not in _WEAPONLESS_HEROES
          and hero_slug not in _SINGLE_WEAPON_SLOT_HEROES):
        violations.append("Deck has only one weapon (both weapon slots should be filled).")

    # ── (c) equipment check ───────────────────────────────────────────────
    if not equipment:
        violations.append("Deck has no equipment.")

    # ── (a) class/talent legality ─────────────────────────────────────────
    if hero_slug:
        hero_entry = slug_index.get(hero_slug) or slug_index.get(
            hero_slug.replace("-", "_")
        )
        if hero_entry is None:
            violations.append(f"Hero slug {hero_slug!r} not found in slug_index.")
        else:
            hero_types: list[str] = hero_entry.get("types", []) or []
            hero_keywords: list[str] = hero_entry.get("card_keywords", []) or []
            hero_enum: str = hero_entry.get("hero", "")

            # Build card dicts expected by validate_deck_legality
            deck_cards = [{"card_slug": s} for s in cards]
            equip_cards = [{"card_slug": s} for s in equipment.values()]
            if weapon_slug:
                equip_cards.append({"card_slug": weapon_slug})

            legality_violations = validate_deck_legality(
                deck_cards=deck_cards,
                equipment=equip_cards,
                hero_types=hero_types,
                slug_index=slug_index,
                hero_keywords=hero_keywords,
                hero_name=hero_entry.get("name", ""),
                hero_enum=hero_enum,
                fmt=fmt,
            )
            violations.extend(legality_violations)
    else:
        violations.append("Deck has no hero.")

    is_valid = len(violations) == 0
    if not is_valid:
        logger.warning("Deck %s has %d violation(s):", deck_path, len(violations))
        for v in violations:
            logger.warning("  - %s", v)

    return is_valid, violations


def validate_all_decks(
    deck_dir: str,
    card_db: CardDB,
    slug_index: dict,
) -> tuple[list[str], dict[str, list[str]]]:
    """Validate every ``.txt`` deck file in *deck_dir*.

    Args:
        deck_dir:    directory containing deck text files.
        card_db:     CardDB instance for card lookups.
        slug_index:  the ``by_slug`` dict from slug_index.json.

    Returns:
        (valid_paths, invalid_report) where *valid_paths* is a list of paths
        that passed all checks and *invalid_report* maps each failing path to
        its list of violation strings.
    """
    valid_paths: list[str] = []
    invalid_report: dict[str, list[str]] = {}

    deck_dir_path = Path(deck_dir)
    if not deck_dir_path.is_dir():
        logger.error("Deck directory does not exist: %s", deck_dir)
        return valid_paths, invalid_report

    deck_files = sorted(deck_dir_path.glob("*.txt"))
    logger.info("Validating %d deck file(s) in %s", len(deck_files), deck_dir)

    for deck_file in deck_files:
        path_str = str(deck_file)
        is_valid, violations = validate_single_deck(path_str, card_db, slug_index)
        if is_valid:
            valid_paths.append(path_str)
        else:
            invalid_report[path_str] = violations

    logger.info(
        "Validation complete: %d valid, %d invalid",
        len(valid_paths),
        len(invalid_report),
    )
    return valid_paths, invalid_report
