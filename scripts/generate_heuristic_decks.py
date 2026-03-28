"""scripts/generate_heuristic_decks.py

Generate heuristic Flesh and Blood decks for Classic Constructed using
card play-rate data from fablazing.com (stored in fablazing_meta.db).

Usage:
    python scripts/generate_heuristic_decks.py --hero kayo-underhanded-cheat
    python scripts/generate_heuristic_decks.py --all
    python scripts/generate_heuristic_decks.py --hero kayo-underhanded-cheat --mutate 5
    python scripts/generate_heuristic_decks.py --all --mutate 3

The script is also importable:
    from scripts.generate_heuristic_decks import generate_deck
    deck = generate_deck("kayo-underhanded-cheat", "data/fablazing_meta.db")
"""
from __future__ import annotations

import argparse
import copy
import html
import json
import random
import re
import sqlite3
import sys
from pathlib import Path

# Allow importing rl_agents.fab_constants without triggering __init__.py (which needs torch).
import types as _types
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if "rl_agents" not in sys.modules:
    _pkg = _types.ModuleType("rl_agents")
    _pkg.__path__ = [str(_PROJECT_ROOT / "rl_agents")]  # type: ignore[assignment]
    _pkg.__package__ = "rl_agents"
    sys.modules["rl_agents"] = _pkg
from rl_agents.fab_constants import DESCRIPTOR, validate_deck_legality, _expand_hero_classes, _parse_hybrid_supertypes, load_banned_cards  # noqa: E402

DB_PATH = Path("data/fablazing_meta.db")
OUTPUT_DIR = Path("decks/generated")
SLUG_INDEX_PATH = Path(__file__).resolve().parent.parent / "card_data" / "slug_index.json"

MIN_DECK_CARDS = 60
MAX_COPIES = 3
# Colors that can appear as slug suffixes
COLORS = {"red", "yellow", "blue"}

# Heroes with a single weapon zone — cannot equip an off-hand alongside their weapon.
_SINGLE_WEAPON_ZONE_HEROES: frozenset[str] = frozenset({
    "kayo-underhanded-cheat",
})

# Lazily loaded slug index and valid slug set from slug_index.json
_valid_slugs: set[str] | None = None
_slug_index: dict | None = None


def _load_slug_index() -> None:
    """Load slug_index.json once, populating both _slug_index and _valid_slugs."""
    global _slug_index, _valid_slugs
    if _slug_index is not None:
        return
    if SLUG_INDEX_PATH.exists():
        with open(SLUG_INDEX_PATH, encoding="utf-8") as f:
            data = json.load(f)
        _slug_index = data.get("by_slug", {})
    else:
        _slug_index = {}
    _valid_slugs = set(_slug_index.keys())


def _get_slug_index() -> dict:
    _load_slug_index()
    return _slug_index  # type: ignore[return-value]


def _get_valid_slugs() -> set[str]:
    _load_slug_index()
    return _valid_slugs  # type: ignore[return-value]


def _fuzzy_slug_match(name: str, threshold: int = 80) -> str | None:
    """Return the best-matching slug from slug_index for a card name/slug, or None.

    Uses thefuzz to find the closest key in slug_index. Returns None if the
    best score is below `threshold` or if thefuzz is unavailable.
    """
    try:
        from thefuzz import process as fuzz_process  # type: ignore[import]
    except ImportError:
        return None
    index = _get_slug_index()
    if not index:
        return None
    normalized = name.lower().replace(" ", "_").replace("-", "_")
    result = fuzz_process.extractOne(normalized, index.keys())
    if result is None:
        return None
    match_slug, score = result
    return match_slug if score >= threshold else None


def build_legal_pool(hero_slug: str) -> frozenset[str]:
    """Return all card slugs from slug_index that are legal for hero_slug.

    A card is legal if:
      (a) it has no non-descriptor types  →  Generic, OR
      (b) all of its non-descriptor types are a subset of the hero's.

    Returns frozenset() with a warning if the hero isn't found.
    """
    import warnings
    index = _get_slug_index()

    hero_entry = (
        index.get(hero_slug)
        or index.get(hero_slug.replace("-", "_"))
    )
    if hero_entry is None:
        fuzzy_key = _fuzzy_slug_match(hero_slug)
        if fuzzy_key:
            hero_entry = index.get(fuzzy_key)

    if hero_entry is None:
        warnings.warn(
            f"build_legal_pool: hero '{hero_slug}' not found in slug_index. "
            "Returning empty pool.",
            stacklevel=2,
        )
        return frozenset()

    hero_classes_frozen: frozenset[str] = _expand_hero_classes(
        hero_entry.get("types", []),
        hero_entry.get("card_keywords", []),
    )

    # Types that mark a card as non-deck-playable regardless of class legality
    _NON_PLAYABLE: frozenset[str] = frozenset({
        "hero", "macro", "companion", "invocation", "mentor",
        "placeholder card", "landmark",
    })

    legal: set[str] = set()
    for slug, entry in index.items():
        raw_types = frozenset(t.lower() for t in (entry.get("types") or []))
        # Exclude heroes and non-playable game objects
        if raw_types & _NON_PLAYABLE:
            continue

        # Check for hybrid cards via ' / ' delimiter in type_text
        type_text = entry.get("type_text", "")
        hybrid = _parse_hybrid_supertypes(type_text)
        if hybrid is not None:
            left_classes, right_classes = hybrid
            # Hybrid card is legal if EITHER side satisfies hero classes
            left_ok = not left_classes or left_classes <= hero_classes_frozen
            right_ok = not right_classes or right_classes <= hero_classes_frozen
            if left_ok or right_ok:
                legal.add(slug)
            continue

        card_classes = frozenset(
            t for t in raw_types if t not in DESCRIPTOR
        )
        if not card_classes or card_classes <= hero_classes_frozen:
            legal.add(slug)

    return frozenset(legal)


# ---------------------------------------------------------------------------
# Slug / name helpers
# ---------------------------------------------------------------------------

# Known fablazing slug → correct Talishar slug corrections.
# These arise when fablazing formats card names differently from the slug_index.
_SLUG_CORRECTIONS: dict[str, str] = {
    "orb_weaver_spinneret_red": "orbweaver_spinneret_red",
    "orb_weaver_spinneret_yellow": "orbweaver_spinneret_yellow",
    "orb_weaver_spinneret_blue": "orbweaver_spinneret_blue",
    "t_bone_red": "tbone_red",
    "t_bone_yellow": "tbone_yellow",
    "t_bone_blue": "tbone_blue",
    "riches_of_tropal_dhani_yellow": "riches_of_trpaldhani_yellow",
    "under_the_trap_door_blue": "under_the_trapdoor_blue",
    # slug_index has a typo: tigerine (extra 'e') instead of tigrine
    "tigrine_reflex_red": "tigerine_reflex_red",
}


# ---------------------------------------------------------------------------
# New-card injection system
# ---------------------------------------------------------------------------

INJECTIONS_PATH = Path(__file__).resolve().parent.parent / "card_data" / "new_card_injections.json"

_injections: dict | None = None


def _load_injections() -> dict:
    """Load new_card_injections.json once and return hero-keyed dict."""
    global _injections
    if _injections is not None:
        return _injections
    if INJECTIONS_PATH.exists():
        with open(INJECTIONS_PATH, encoding="utf-8") as f:
            raw = json.load(f)
        # Strip meta keys starting with '_'
        _injections = {k: v for k, v in raw.items() if not k.startswith("_")}
    else:
        _injections = {}
    return _injections


def _apply_injections(
    hero_slug: str,
    equipment_pool: list[dict],
    deck_pool: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Merge injection entries for hero_slug into the given pools.

    Injection rows are appended BEFORE the pools are filtered by legal_pool,
    so they participate in the same legality check as DB rows.  A card already
    present in the pool (by card_slug) is NOT duplicated — the DB row wins so
    real fablazing data always takes precedence.

    Returns updated (equipment_pool, deck_pool) tuples.
    """
    injections = _load_injections()
    hero_data = injections.get(hero_slug) or injections.get(hero_slug.replace("-", "_"))
    if not hero_data:
        return equipment_pool, deck_pool

    index = _get_slug_index()
    existing_equip_slugs = {c["card_slug"] for c in equipment_pool}
    existing_deck_slugs  = {c["card_slug"] for c in deck_pool}

    def _build_entry(raw: dict, default_type: str) -> dict:
        slug = raw["card_slug"]
        entry = index.get(slug) or index.get(slug.replace("-", "_")) or {}
        name = raw.get("card_name") or entry.get("name") or slug
        card_type = raw.get("card_type", default_type)
        return {
            "card_slug": slug,
            "card_name": name,
            "card_type": card_type,
            "frequency": float(raw.get("frequency", 0.9)),
            "avg_copies": float(raw.get("avg_copies", 1.0 if default_type == "equipment" else 3.0)),
            "win_rate": float(raw.get("win_rate", 0.5)),
            "equipment_subtype": raw.get("equipment_subtype", ""),
        }

    new_equip = []
    for raw in hero_data.get("equipment", []):
        slug = raw.get("card_slug", "")
        if not slug or slug in existing_equip_slugs:
            continue
        new_equip.append(_build_entry(raw, "equipment"))

    new_deck = []
    for raw in hero_data.get("deck_cards", []):
        slug = raw.get("card_slug", "")
        if not slug or slug in existing_deck_slugs:
            continue
        new_deck.append(_build_entry(raw, "deck"))

    return equipment_pool + new_equip, deck_pool + new_deck


def _extract_color(card_slug: str) -> str:
    """Return the color suffix from a fablazing card slug, or '' if none."""
    parts = card_slug.rsplit("_", 1)
    if len(parts) == 2 and parts[1] in COLORS:
        return parts[1]
    return ""


def _canonical_card_name(card_slug: str, fallback: str) -> str:
    """Return the authoritative card name from slug_index, falling back to fablazing DB name."""
    index = _get_slug_index()
    entry = index.get(card_slug) or index.get(card_slug.replace("-", "_"))
    if entry and entry.get("name"):
        return entry["name"]
    return fallback


def _format_card_line(card_name: str, card_slug: str, count: int) -> str:
    """Format a card entry for the FaBrary deck file.

    Returns e.g. '3x Swing Big (red)' or '1x Mandible Claw'.
    Uses slug_index as the authoritative name source so deck files always
    use the name Talishar recognises (e.g. 'Gorganian Tome', not 'Gorganian').
    """
    name = _canonical_card_name(card_slug, card_name)
    color = _extract_color(card_slug)
    if color:
        return f"{count}x {name} ({color})"
    return f"{count}x {name}"


def _slug_to_filename(hero_slug: str) -> str:
    """Convert a hero slug like 'kayo-underhanded-cheat' to a filename."""
    return hero_slug.replace("-", "_") + "_CC.txt"


# ---------------------------------------------------------------------------
# Database queries
# ---------------------------------------------------------------------------

def _fetch_hero(conn: sqlite3.Connection, hero_slug: str, fmt: str = "cc") -> dict:
    """Fetch hero metadata from the database.

    If the hero is not in the DB but is present in new_card_injections.json,
    returns a synthetic row so the deck generator can proceed with injection data.
    """
    row = conn.execute(
        "SELECT hero_name, win_rate, total_matches FROM heroes "
        "WHERE hero_slug = ? AND format = ?",
        (hero_slug, fmt),
    ).fetchone()
    if row:
        return {"hero_slug": hero_slug, "hero_name": html.unescape(row[0] or ""), "win_rate": row[1], "total_matches": row[2]}

    # Hero not in DB — check injections for display name
    injections = _load_injections()
    hero_data = injections.get(hero_slug) or injections.get(hero_slug.replace("-", "_"))
    if hero_data:
        # Fall back to slug_index name if injection doesn't supply one
        index = _get_slug_index()
        idx_entry = index.get(hero_slug) or index.get(hero_slug.replace("-", "_"))
        hero_name = (
            hero_data.get("hero_name")
            or (idx_entry.get("name") if idx_entry else None)
            or hero_slug.replace("_", " ").replace("-", " ").title()
        )
        import warnings
        warnings.warn(
            f"Hero '{hero_slug}' not in DB — using injection-only data (no fablazing stats).",
            stacklevel=3,
        )
        return {"hero_slug": hero_slug, "hero_name": hero_name, "win_rate": 0.5, "total_matches": 0}

    raise ValueError(
        f"Hero '{hero_slug}' not found in database (format={fmt}) and has no injection entry. "
        "Run scrape_fablazing.py first, or add an entry to card_data/new_card_injections.json."
    )


def _fetch_cards(
    conn: sqlite3.Connection, hero_slug: str, fmt: str = "cc"
) -> tuple[list[dict], list[dict]]:
    """Fetch card stats from the database, split into equipment and deck cards.

    Returns (equipment_cards, deck_cards), each sorted by frequency descending.
    """
    rows = conn.execute(
        "SELECT card_slug, card_name, card_type, frequency, avg_copies, win_rate, "
        "       COALESCE(equipment_subtype, '') "
        "FROM card_stats "
        "WHERE hero_slug = ? AND format = ? "
        "ORDER BY frequency DESC",
        (hero_slug, fmt),
    ).fetchall()

    equipment: list[dict] = []
    deck: list[dict] = []

    # Map DB card_type → equipment_subtype for weapon rows
    _WEAPON_TYPE_MAP = {"weapon_1h": "weapon-1h", "weapon_2h": "weapon-2h"}

    for card_slug, card_name, card_type, frequency, avg_copies, win_rate, equip_subtype in rows:
        ct = card_type or "deck"
        if ct in ("token", "hero"):
            continue
        # Apply known fablazing→Talishar slug corrections
        card_slug = _SLUG_CORRECTIONS.get(card_slug, card_slug)
        # Derive subtype: DB column wins; fall back to card_type for weapons
        if not equip_subtype and ct in _WEAPON_TYPE_MAP:
            equip_subtype = _WEAPON_TYPE_MAP[ct]
        entry = {
            "card_slug": card_slug,
            "card_name": card_name or card_slug,
            "card_type": ct,
            "frequency": frequency or 0.0,
            "avg_copies": avg_copies or 1.0,
            "win_rate": win_rate or 0.0,
            "equipment_subtype": equip_subtype or "",
        }
        if ct in ("equipment", "weapon_1h", "weapon_2h"):
            equipment.append(entry)
        else:
            deck.append(entry)

    return equipment, deck


def _list_heroes(conn: sqlite3.Connection, fmt: str = "cc") -> list[str]:
    """Return all hero slugs for the given format."""
    rows = conn.execute(
        "SELECT hero_slug FROM heroes WHERE format = ? ORDER BY total_matches DESC",
        (fmt,),
    ).fetchall()
    return [r[0] for r in rows]


def _fetch_generic_equipment(
    conn: sqlite3.Connection, hero_slug: str, fmt: str = "cc"
) -> list[dict]:
    """Fetch equipment used across many heroes, excluding hero-specific pieces.

    Returns generic/staple equipment sorted by number of heroes using it,
    then by average frequency. Used to pad heroes with fewer than 5 equipment.
    """
    rows = conn.execute(
        """
        SELECT card_slug, card_name,
               CASE
                 WHEN COALESCE(equipment_subtype,'') != '' THEN equipment_subtype
                 WHEN card_type = 'weapon_1h' THEN 'weapon-1h'
                 WHEN card_type = 'weapon_2h' THEN 'weapon-2h'
                 ELSE ''
               END as equipment_subtype,
               COUNT(DISTINCT hero_slug) as hero_count, AVG(frequency) as avg_freq
        FROM card_stats
        WHERE card_type IN ('equipment','weapon_1h','weapon_2h') AND format = ?
          AND card_slug NOT IN (
              SELECT card_slug FROM card_stats
              WHERE hero_slug = ? AND card_type IN ('equipment','weapon_1h','weapon_2h')
                AND format = ?
          )
        GROUP BY card_slug, equipment_subtype
        HAVING hero_count >= 3
        ORDER BY hero_count DESC, avg_freq DESC
        """,
        (fmt, hero_slug, fmt),
    ).fetchall()

    return [
        {
            "card_slug": slug,
            "card_name": name or slug,
            "card_type": "equipment",
            "equipment_subtype": equip_subtype,
            "frequency": avg_freq or 0.0,
            "avg_copies": 1.0,
            "win_rate": 0.5,
        }
        for slug, name, equip_subtype, _, avg_freq in rows
    ]


def _fetch_class_weapons(
    conn: sqlite3.Connection, hero_slug: str, fmt: str = "cc"
) -> list[dict]:
    """Return weapons that are legal for this hero per FAB deck-building rules.

    FAB rule: a card is legal for a hero if it is Generic OR all of the card's
    class/talent types are a subset of the hero's class+talent types.

    Filters weapons from the DB by checking their slug_index types against the
    hero's types.  Equipment-descriptor types (Weapon, 2H, Bow, etc.) are
    excluded from the subset check — only class/talent identifiers matter.
    """
    index = _get_slug_index()
    # DESCRIPTOR is imported from fab_constants — shared with deck_search.py

    hero_entry = index.get(hero_slug) or index.get(hero_slug.replace("-", "_"))
    if not hero_entry:
        return []
    hero_classes = {t.lower() for t in hero_entry.get("types", [])
                    if t.lower() not in DESCRIPTOR}
    if not hero_classes:
        return []

    # All weapons in DB not already in this hero's pool
    rows = conn.execute(
        """
        SELECT card_slug, card_name,
               COALESCE(equipment_subtype,
                        CASE card_type WHEN 'weapon_1h' THEN 'weapon-1h'
                                       WHEN 'weapon_2h' THEN 'weapon-2h'
                                       ELSE '' END) as equipment_subtype,
               AVG(frequency) as avg_freq
        FROM card_stats
        WHERE card_type IN ('weapon_1h','weapon_2h') AND format = ?
          AND card_slug NOT IN (
              SELECT card_slug FROM card_stats
              WHERE hero_slug = ? AND format = ?
          )
        GROUP BY card_slug
        ORDER BY avg_freq DESC
        """,
        (fmt, hero_slug, fmt),
    ).fetchall()

    result: list[dict] = []
    for slug, name, subtype, freq in rows:
        if not subtype or not subtype.startswith("weapon"):
            continue
        # Get weapon's class/talent types from slug_index
        w_entry = index.get(slug) or index.get(slug.replace("-", "_"))
        if not w_entry:
            continue
        w_classes = {t.lower() for t in w_entry.get("types", [])
                     if t.lower() not in DESCRIPTOR}
        # FAB rule: weapon's class types must be a subset of hero's class types
        if w_classes and not w_classes <= hero_classes:
            continue
        result.append({
            "card_slug": slug,
            "card_name": name or slug,
            "card_type": "equipment",
            "equipment_subtype": subtype,
            "frequency": freq or 0.0,
            "avg_copies": 1.0,
            "win_rate": 0.5,
        })

    return result


def _fetch_generic_deck_cards(
    conn: sqlite3.Connection, hero_slug: str, fmt: str = "cc"
) -> list[dict]:
    """Fetch deck cards used across many heroes, excluding hero-specific ones.

    Returns generic/staple deck cards sorted by number of heroes using them.
    Used to pad heroes whose card pool can't reach 60.
    """
    rows = conn.execute(
        """
        SELECT card_slug, card_name, COUNT(DISTINCT hero_slug) as hero_count,
               AVG(frequency) as avg_freq, AVG(avg_copies) as avg_copies
        FROM card_stats
        WHERE card_type = 'deck' AND format = ?
          AND card_slug NOT IN (
              SELECT card_slug FROM card_stats
              WHERE hero_slug = ? AND format = ?
          )
        GROUP BY card_slug
        HAVING hero_count >= 5
        ORDER BY hero_count DESC, avg_freq DESC
        """,
        (fmt, hero_slug, fmt),
    ).fetchall()

    return [
        {
            "card_slug": slug,
            "card_name": name or slug,
            "card_type": "deck",
            "frequency": avg_freq or 0.0,
            "avg_copies": avg_copies or 1.0,
            "win_rate": 0.5,
        }
        for slug, name, _, avg_freq, avg_copies in rows
    ]


# ---------------------------------------------------------------------------
# Core deck generation
# ---------------------------------------------------------------------------

def _pick_equipment(
    equipment_cards: list[dict],
    generic_equipment: list[dict] | None = None,
    class_weapons: list[dict] | None = None,
    hero_classes: frozenset[str] | None = None,
    hero_slug: str | None = None,
    legal_pool: frozenset[str] | None = None,
) -> list[dict]:
    """Pick equipment enforcing FAB Classic Constructed deck building rules.

    Armor slots (exactly one each): head, chest, arms, legs.
    Weapon rules:
        - weapon-1h:  optionally add one off-hand equipment
        - weapon-bow: optionally add one quiver
        - weapon-2h / weapon-other: no secondary equipment
        - no weapon:  still equip a standalone off-hand if the hero uses one

    Generic equipment is used only for armor slots (head/chest/arms/legs).
    Off-hands from the generic pool are filtered by hero_classes legality.
    Weapons come only from the hero's own pool or class_weapons fallback —
    never from the generic pool.
    """
    index = _get_slug_index()

    def _is_legal_for_hero(card: dict) -> bool:
        """Return True if this card's class types are a subset of hero_classes."""
        if hero_classes is None:
            return True  # no filter — trust data source
        slug = card.get("card_slug", "")
        entry = index.get(slug) or index.get(slug.replace("-", "_"))
        if not entry:
            return True  # unknown card — allow
        w_classes = frozenset(
            t.lower() for t in entry.get("types", []) if t.lower() not in DESCRIPTOR
        )
        return not w_classes or w_classes <= hero_classes

    # Group hero cards by subtype (always assumed legal from hero's own DB data)
    hero_by_sub: dict[str, list[dict]] = {}
    for card in equipment_cards:
        st = card.get("equipment_subtype", "") or ""
        hero_by_sub.setdefault(st, []).append(card)

    # Group generic cards by subtype — weapons excluded (never use generic weapons)
    _ARMOR_SUBTYPES = {"head", "chest", "arms", "legs", "off-hand", "quiver"}
    gen_by_sub: dict[str, list[dict]] = {}
    for card in (generic_equipment or []):
        st = card.get("equipment_subtype", "") or ""
        if st not in _ARMOR_SUBTYPES:
            continue  # skip generic weapons and unknown subtypes
        gen_by_sub.setdefault(st, []).append(card)

    picked: list[dict] = []
    used_slugs: set[str] = set()

    def _best(subtype: str, require_legal: bool = False) -> dict | None:
        """Return the highest-frequency unused card for the given subtype."""
        candidates = hero_by_sub.get(subtype, []) + gen_by_sub.get(subtype, [])
        for card in candidates:
            if card["card_slug"] in used_slugs:
                continue
            if require_legal and not _is_legal_for_hero(card):
                continue
            return card
        return None

    def _add(card: dict) -> None:
        picked.append({**card, "count": 1})
        used_slugs.add(card["card_slug"])

    def _slug_index_armor(slot: str) -> dict | None:
        """Fall back to slug_index for armor equipment legal for this hero.

        Used when neither the hero's fablazing pool nor the generic DB pool
        has a legal card for the given slot (head/chest/arms/legs).
        Filters by hero class legality; skips specialization mismatches.
        """
        slot_cap = slot.capitalize()  # "arms" -> "Arms", etc.
        candidates: list[tuple[int, str, dict]] = []
        hero_name_tokens = (hero_slug or "").replace("-", " ").replace("_", " ").lower()
        for slug, entry in index.items():
            types = entry.get("types") or []
            if slot_cap not in types or "Equipment" not in types:
                continue
            if "Token" in types or "Ally" in types:
                continue
            if slug in used_slugs:
                continue
            # Specialization check
            kws = entry.get("card_keywords") or []
            legal_spec = True
            for kw in kws:
                if "Specialization" in kw:
                    spec_hero = kw.replace(" Specialization", "").lower()
                    if spec_hero not in hero_name_tokens:
                        legal_spec = False
                        break
            if not legal_spec:
                continue
            # Class legality
            card_classes = frozenset(
                t.lower() for t in types if t.lower() not in DESCRIPTOR
            )
            if card_classes and not card_classes <= hero_classes:
                continue
            if legal_pool and slug not in legal_pool:
                continue
            priority = 1 if not card_classes else 0  # prefer class-specific
            candidates.append((priority, slug, {
                "card_slug": slug,
                "card_name": entry.get("name", slug),
                "card_type": "equipment",
                "equipment_subtype": slot,
                "frequency": 0.5,
                "avg_copies": 1.0,
                "win_rate": 0.5,
            }))
        candidates.sort(key=lambda x: (x[0], x[1]))
        for _, slug, card in candidates:
            if slug not in used_slugs:
                return card
        return None

    # Armor: exactly one of each slot — apply class legality check, then fall
    # back to slug_index for heroes whose fablazing pool lacks that slot.
    for slot in ("head", "chest", "arms", "legs"):
        card = _best(slot, require_legal=True) or _slug_index_armor(slot)
        if card:
            _add(card)

    # Weapon: hero pool only → class-matched fallback (no generic weapons)
    all_weapons: list[dict] = []
    for wtype in ("weapon-1h", "weapon-2h", "weapon-bow", "weapon-other"):
        all_weapons.extend(hero_by_sub.get(wtype, []))
    all_weapons.sort(key=lambda c: c["frequency"], reverse=True)

    chosen_weapon: dict | None = None
    for w in all_weapons:
        if w["card_slug"] not in used_slugs:
            chosen_weapon = w
            break

    # Fallback: class-matched weapons from other heroes
    if chosen_weapon is None and class_weapons:
        for w in class_weapons:
            if w["card_slug"] not in used_slugs:
                chosen_weapon = w
                break

    valid_slugs = _get_valid_slugs()

    def _hero_name_from_slug(slug: str | None) -> str:
        """Extract hero display name tokens from slug for specialization matching."""
        if not slug:
            return ""
        return slug.replace("-", " ").replace("_", " ").lower()

    def _slug_index_offhand() -> dict | None:
        """Fall back to slug_index for off-hand equipment legal for this hero.

        Filters out hero-specialization cards that don't match this hero,
        and excludes cards that aren't recognised by Talishar (not in valid_slugs).
        """
        if not hero_classes:
            return None
        hero_name_tokens = _hero_name_from_slug(hero_slug)
        candidates: list[tuple[int, str, dict]] = []  # (priority, slug, card_dict)
        for slug, entry in index.items():
            types = entry.get("types") or []
            if "Off-Hand" not in types or "Equipment" not in types:
                continue
            # Skip non-equipment tokens / allies
            if "Token" in types or "Ally" in types:
                continue
            # Skip cards with hero-specialization restrictions that don't match
            kws = entry.get("card_keywords") or []
            for kw in kws:
                if "Specialization" in kw:
                    spec_hero = kw.replace(" Specialization", "").lower()
                    if spec_hero not in hero_name_tokens:
                        break  # specialization belongs to a different hero
            else:
                # Only reach here if no specialization mismatch
                class_types = frozenset(t.lower() for t in types if t.lower() not in DESCRIPTOR)
                if class_types and not class_types <= hero_classes:
                    continue
                if legal_pool and slug not in legal_pool:
                    continue
                # Prefer class-specific (priority 0) over generic (priority 1)
                priority = 1 if not class_types else 0
                candidates.append((priority, slug, {
                    "card_slug": slug,
                    "card_name": entry.get("name", slug),
                    "card_type": "equipment",
                    "equipment_subtype": "off-hand",
                    "frequency": 0.5,
                    "avg_copies": 1.0,
                    "win_rate": 0.5,
                }))
        candidates.sort(key=lambda x: (x[0], x[1]))
        for _, slug, card in candidates:
            if slug not in used_slugs:
                return card
        return None

    def _second_weapon_as_offhand(main_weapon: dict) -> dict | None:
        """Return an off-hand copy of a 1H weapon for dual-wield heroes.

        Priority:
        1. Another 1H weapon from the hero's pool (different slug, valid in slug_index)
        2. Second copy of the same weapon (if hero has multiple 1H weapon entries)
        Falls through to None if the hero doesn't appear to dual-wield.
        """
        main_slug = main_weapon["card_slug"]
        # Check if hero has a second distinct 1H weapon in their fablazing pool
        for w in hero_by_sub.get("weapon-1h", []):
            if w["card_slug"] == main_slug:
                continue
            # Prefer valid slugs; if invalid (e.g. 'cintari_saber_r'), fall back below
            if valid_slugs and w["card_slug"] in valid_slugs:
                return w
            # Invalid slug but hero has a second weapon entry → use same weapon again
            return {**main_weapon}
        # No second distinct weapon entry — default to dual-wield with the same weapon.
        # FAB rules require both weapon zones to be filled for 1H heroes.
        return {**main_weapon}

    if chosen_weapon:
        _add(chosen_weapon)
        wtype = chosen_weapon.get("equipment_subtype", "")
        if wtype == "weapon-1h" and hero_slug not in _SINGLE_WEAPON_ZONE_HEROES:
            # Try dual-wield first (second weapon), then off-hand shield fallback.
            # Skipped for heroes with a single weapon zone (e.g. Kayo).
            oh = (
                _second_weapon_as_offhand(chosen_weapon)
                or _best("off-hand", require_legal=True)
                or _slug_index_offhand()
            )
            if oh:
                # For dual-wield: if same slug as main weapon, increment count
                # rather than adding as separate entry.
                if oh["card_slug"] == chosen_weapon["card_slug"]:
                    picked[-1] = {**picked[-1], "count": 2}
                else:
                    _add(oh)
        elif wtype == "weapon-bow":
            q = _best("quiver", require_legal=True)
            if q:
                _add(q)
        # weapon-2h / weapon-other: no secondary item
    else:
        # No weapon — still equip a standalone off-hand if the hero uses one
        oh = _best("off-hand", require_legal=True)
        if oh and oh["card_slug"] in {c["card_slug"] for c in equipment_cards}:
            _add(oh)

    return picked


def _pick_deck_cards(
    deck_cards: list[dict],
    target: int = MIN_DECK_CARDS,
    generic_deck_cards: list[dict] | None = None,
    legal_pool: frozenset[str] | None = None,
) -> list[dict]:
    """Pick deck cards greedily by frequency until we reach the target count.

    Uses avg_copies to determine how many copies to include (rounded,
    capped at MAX_COPIES, minimum 1).
    """
    picked: list[dict] = []
    total = 0
    legendary_base_names: set[str] = set()  # base names already at 1 copy (max)

    def _is_legendary(slug: str) -> bool:
        e = index.get(slug) or index.get(slug.replace("-", "_"))
        return bool(e and "Legendary" in (e.get("card_keywords") or []))

    index = _get_slug_index()
    for card in deck_cards:
        if total >= target:
            break
        copies = max(1, min(MAX_COPIES, round(card["avg_copies"])))
        # FAB rule: Legendary cards are limited to 1 copy across all colors
        slug = card["card_slug"]
        base_name = slug.rsplit("_", 1)[0] if _extract_color(slug) else slug
        if _is_legendary(slug):
            if base_name in legendary_base_names:
                continue  # already have this legendary in another color
            copies = 1
            legendary_base_names.add(base_name)
        # Don't overshoot too much -- we trim later, but be reasonable
        picked.append({**card, "count": copies})
        total += copies

    # --- Adjust to exactly `target` cards ---
    if total < target:
        deficit = target - total

        # Pass 1: add missing color variants of cards already picked,
        # but ONLY if the variant actually exists in the card database.
        valid = _get_valid_slugs()
        used_slugs = {e["card_slug"] for e in picked}
        color_variants: list[dict] = []
        for entry in list(picked):
            if deficit <= 0:
                break
            color = _extract_color(entry["card_slug"])
            if not color:
                continue
            base = entry["card_slug"].rsplit("_", 1)[0]
            for alt_color in ("red", "yellow", "blue"):
                if alt_color == color:
                    continue
                alt_slug = f"{base}_{alt_color}"
                if alt_slug in used_slugs:
                    continue
                # Only add if the card actually exists
                if valid and alt_slug not in valid:
                    continue
                if legal_pool and alt_slug not in legal_pool:
                    continue
                # Don't add a color variant of a Legendary (already at max 1)
                if _is_legendary(alt_slug):
                    continue
                copies = min(MAX_COPIES, deficit)
                if copies <= 0:
                    break
                color_variants.append({
                    "card_slug": alt_slug,
                    "card_name": entry["card_name"],
                    "card_type": "deck",
                    "frequency": entry["frequency"] * 0.5,
                    "avg_copies": copies,
                    "win_rate": entry.get("win_rate", 0.5),
                    "count": copies,
                })
                used_slugs.add(alt_slug)
                deficit -= copies
                total += copies

        picked.extend(color_variants)

        # Pass 2: bump copies of existing cards up to MAX_COPIES (skip Legendaries)
        if deficit > 0:
            for entry in picked:
                if deficit <= 0:
                    break
                if _is_legendary(entry["card_slug"]):
                    continue
                room = MAX_COPIES - entry["count"]
                if room > 0:
                    add = min(room, deficit)
                    entry["count"] += add
                    deficit -= add
                    total += add

        # Pass 3: add any remaining cards from the pool we haven't used
        if deficit > 0:
            remaining = [c for c in deck_cards if c["card_slug"] not in used_slugs]
            for card in remaining:
                if deficit <= 0:
                    break
                copies = max(1, min(MAX_COPIES, deficit))
                picked.append({**card, "count": copies})
                used_slugs.add(card["card_slug"])
                deficit -= copies
                total += copies

        # Pass 4: add generic deck cards (staples used by 5+ heroes)
        if deficit > 0 and generic_deck_cards:
            for card in generic_deck_cards:
                if deficit <= 0:
                    break
                if card["card_slug"] in used_slugs:
                    continue
                copies = max(1, min(MAX_COPIES, deficit))
                picked.append({**card, "count": copies})
                used_slugs.add(card["card_slug"])
                deficit -= copies
                total += copies

    elif total > target:
        # Trim from the bottom (lowest frequency cards) until we hit target
        surplus = total - target
        for entry in reversed(picked):
            if surplus <= 0:
                break
            reduce = min(entry["count"], surplus)
            entry["count"] -= reduce
            surplus -= reduce
        # Remove entries with 0 copies
        picked = [e for e in picked if e["count"] > 0]

    if total < target:
        import warnings
        warnings.warn(
            f"_pick_deck_cards: only reached {total}/{target} deck cards — "
            "hero may have too few cards in the database.",
            stacklevel=2,
        )

    return picked


def generate_deck(
    hero_slug: str,
    db_path: str | Path = DB_PATH,
    fmt: str = "cc",
    mutate: bool = False,
    rng: random.Random | None = None,
    banned_slugs: frozenset[str] | None = None,
) -> dict:
    """Generate a heuristic deck for the given hero.

    Args:
        hero_slug: The fablazing hero slug (e.g. 'kayo-underhanded-cheat').
        db_path: Path to the fablazing_meta.db SQLite database.
        fmt: Format string (default 'cc' for Classic Constructed).
        mutate: If True, apply random mutations to the deck.
        rng: Optional Random instance for reproducibility.
        banned_slugs: Optional override for banned card slugs. If None,
            load_banned_cards(fmt) is used automatically.

    Returns:
        A dict with keys:
            hero_name: str
            hero_slug: str
            equipment: list[dict]  -- each has card_name, card_slug, count
            deck_cards: list[dict] -- each has card_name, card_slug, count
            total_deck_cards: int
            total_arena_cards: int
    """
    # --- Step 1: Build legal pool from slug_index BEFORE any DB access ---
    # This is the authoritative gate: only cards whose class types are a subset
    # of the hero's class+talent types (or Generic) can enter the deck.
    legal_pool = build_legal_pool(hero_slug)

    # --- Step 1b: Remove banned cards from the legal pool ---
    _banned = banned_slugs if banned_slugs is not None else load_banned_cards(fmt)
    if _banned:
        legal_pool = frozenset(legal_pool - _banned)

    conn = sqlite3.connect(str(db_path))
    try:
        hero = _fetch_hero(conn, hero_slug, fmt)
        equipment_pool, deck_pool = _fetch_cards(conn, hero_slug, fmt)
        generic_equip = _fetch_generic_equipment(conn, hero_slug, fmt)
        generic_deck = _fetch_generic_deck_cards(conn, hero_slug, fmt)
        class_weap = _fetch_class_weapons(conn, hero_slug, fmt)
    finally:
        conn.close()

    # Merge injection entries (new cards / new heroes not yet in fablazing DB)
    equipment_pool, deck_pool = _apply_injections(hero_slug, equipment_pool, deck_pool)

    if not deck_pool:
        raise ValueError(
            f"No deck cards found for hero '{hero_slug}' (format={fmt}). "
            "Database may be empty -- run scrape_fablazing.py first, or add "
            "deck_cards to card_data/new_card_injections.json."
        )

    _index = _get_slug_index()
    _hero_entry = _index.get(hero_slug) or _index.get(hero_slug.replace("-", "_"))
    _hero_classes: frozenset[str] = frozenset(
        t.lower() for t in (_hero_entry or {}).get("types", [])
        if t.lower() not in DESCRIPTOR
    )

    # --- Step 2: Filter ALL DB results through legal_pool ---
    # Cards not in slug_index at all are checked via fuzzy match; if still
    # unresolvable, assume legal (Talishar may support cards not yet in our index).
    if legal_pool:
        _fuzzy_cache: dict[str, str | None] = {}

        def _in_pool(card: dict) -> bool:
            slug = card["card_slug"]
            if slug in legal_pool:
                return True
            alt = slug.replace("-", "_")
            if alt in legal_pool:
                return True
            # Card not in slug_index at all — try fuzzy, fall back to allow
            if slug not in _index and alt not in _index:
                if slug not in _fuzzy_cache:
                    _fuzzy_cache[slug] = _fuzzy_slug_match(slug)
                fuzzy = _fuzzy_cache[slug]
                return fuzzy is None or fuzzy in legal_pool
            return False  # in slug_index but not legal

        deck_pool      = [c for c in deck_pool      if _in_pool(c)]
        generic_deck   = [c for c in generic_deck   if _in_pool(c)]
        equipment_pool = [c for c in equipment_pool if _in_pool(c)]
        generic_equip  = [c for c in generic_equip  if _in_pool(c)]
        class_weap     = [c for c in class_weap     if _in_pool(c)]

    equipment = _pick_equipment(equipment_pool, generic_equipment=generic_equip,
                                class_weapons=class_weap, hero_classes=_hero_classes,
                                hero_slug=hero_slug, legal_pool=legal_pool or None)
    deck_cards = _pick_deck_cards(deck_pool, target=MIN_DECK_CARDS,
                                  generic_deck_cards=generic_deck,
                                  legal_pool=legal_pool or None)

    if mutate:
        deck_cards = _mutate_deck(deck_cards, deck_pool, rng=rng)

    total_deck = sum(e["count"] for e in deck_cards)

    # Post-generation safety net: warn on any remaining violations
    hero_types = list((_hero_entry or {}).get("types", []))
    hero_kws = list((_hero_entry or {}).get("card_keywords", []))
    violations = validate_deck_legality(deck_cards, equipment, hero_types, _index, hero_keywords=hero_kws)
    if violations:
        import warnings
        warnings.warn(
            f"Deck legality violations for {hero_slug}:\n" + "\n".join(f"  {v}" for v in violations),
            stacklevel=2,
        )

    return {
        "hero_name": hero["hero_name"],
        "hero_slug": hero_slug,
        "equipment": equipment,
        "deck_cards": deck_cards,
        "total_deck_cards": total_deck,
        "total_arena_cards": len(equipment),
    }


# ---------------------------------------------------------------------------
# Mutation
# ---------------------------------------------------------------------------

def _mutate_deck(
    deck_cards: list[dict],
    full_pool: list[dict],
    n_swaps: int | None = None,
    rng: random.Random | None = None,
) -> list[dict]:
    """Mutate a deck by swapping 5-10 random cards with alternatives from the pool.

    The mutation removes n_swaps cards (copies) from the deck and replaces them
    with cards drawn from the unused portion of the card pool, maintaining 60
    deck cards total.
    """
    rng = rng or random.Random()
    n_swaps = n_swaps or rng.randint(5, 10)

    deck = copy.deepcopy(deck_cards)
    used_slugs = {e["card_slug"] for e in deck}
    alternatives = [c for c in full_pool if c["card_slug"] not in used_slugs]

    # Remove n_swaps copies from random deck entries
    removed = 0
    attempts = 0
    while removed < n_swaps and attempts < n_swaps * 10:
        attempts += 1
        idx = rng.randint(0, len(deck) - 1)
        if deck[idx]["count"] > 0:
            deck[idx]["count"] -= 1
            removed += 1

    # Clean up zeroed entries
    deck = [e for e in deck if e["count"] > 0]

    # Add replacement cards from alternatives
    added = 0
    alt_idx = 0
    while added < removed and alt_idx < len(alternatives):
        card = alternatives[alt_idx]
        copies = max(1, min(MAX_COPIES, round(card["avg_copies"])))
        copies = min(copies, removed - added)  # don't overshoot
        deck.append({**card, "count": copies})
        added += copies
        alt_idx += 1

    # If we couldn't add enough alternatives, bump existing card copies
    deficit = removed - added
    if deficit > 0:
        for entry in deck:
            if deficit <= 0:
                break
            room = MAX_COPIES - entry["count"]
            if room > 0:
                add = min(room, deficit)
                entry["count"] += add
                deficit -= add

    return deck


# ---------------------------------------------------------------------------
# File output
# ---------------------------------------------------------------------------

def _deck_to_text(deck: dict) -> str:
    """Convert a deck dict to FaBrary format text."""
    lines: list[str] = []
    hero_name = deck["hero_name"]
    deck_name = f"{hero_name} - Heuristic"

    lines.append(f"Name: {deck_name}")
    lines.append(f"Hero: {hero_name}")
    lines.append("Format: Classic Constructed")
    lines.append("")
    lines.append("Arena cards")
    for eq in deck["equipment"]:
        lines.append(_format_card_line(eq["card_name"], eq["card_slug"], eq["count"]))
    lines.append("")
    lines.append("Deck cards")

    # Sort deck cards: red first, then yellow, then blue, then colorless.
    # Within each color group, sort by frequency descending (preserved from pick order).
    color_order = {"red": 0, "yellow": 1, "blue": 2, "": 3}

    def sort_key(entry: dict) -> tuple:
        color = _extract_color(entry["card_slug"])
        return (color_order.get(color, 3), -entry["frequency"])

    sorted_deck = sorted(deck["deck_cards"], key=sort_key)

    for card in sorted_deck:
        lines.append(_format_card_line(card["card_name"], card["card_slug"], card["count"]))
    lines.append("")

    return "\n".join(lines)


def write_deck_file(deck: dict, output_dir: Path = OUTPUT_DIR, suffix: str = "") -> Path:
    """Write a deck dict to a FaBrary-format text file.

    Returns the path to the written file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = _slug_to_filename(deck["hero_slug"])
    if suffix:
        filename = filename.replace(".txt", f"_{suffix}.txt")
    filepath = output_dir / filename
    filepath.write_text(_deck_to_text(deck), encoding="utf-8")
    return filepath


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate heuristic FAB Classic Constructed decks from fablazing.com data"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--hero",
        type=str,
        help="Hero slug to generate a deck for (e.g. kayo-underhanded-cheat)",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Generate decks for all heroes in the database",
    )
    parser.add_argument(
        "--mutate",
        type=int,
        default=0,
        metavar="N",
        help="Generate N mutated variants per hero (in addition to the base deck)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DB_PATH,
        help=f"Path to fablazing_meta.db (default: {DB_PATH})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help=f"Output directory for deck files (default: {OUTPUT_DIR})",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible mutation",
    )
    args = parser.parse_args()

    rng = random.Random(args.seed) if args.seed is not None else random.Random()

    conn = sqlite3.connect(str(args.db))
    if args.all:
        hero_slugs = _list_heroes(conn, fmt="cc")
    else:
        hero_slugs = [args.hero]
    conn.close()

    if not hero_slugs:
        print("No heroes found in database. Run scrape_fablazing.py first.")
        return

    total_decks = 0
    failed: list[tuple[str, str]] = []

    for slug in hero_slugs:
        try:
            # Base deck
            deck = generate_deck(slug, db_path=args.db, mutate=False)
            path = write_deck_file(deck, output_dir=args.output_dir)
            total_deck_cards = deck["total_deck_cards"]
            n_arena = deck["total_arena_cards"]
            # Encode-safe for Windows console
            name = (deck["hero_name"] or slug).encode("ascii", "replace").decode("ascii")
            print(
                f"  {name:<45} {n_arena} arena + {total_deck_cards} deck cards -> {path}"
            )
            total_decks += 1

            # Mutated variants
            for i in range(args.mutate):
                variant = generate_deck(slug, db_path=args.db, mutate=True, rng=rng)
                variant_path = write_deck_file(
                    variant, output_dir=args.output_dir, suffix=f"mut{i+1}"
                )
                v_total = variant["total_deck_cards"]
                print(f"    variant {i+1}: {v_total} deck cards -> {variant_path}")
                total_decks += 1

        except Exception as e:
            print(f"  FAILED {slug}: {e}")
            failed.append((slug, str(e)))

    print(f"\nGenerated {total_decks} deck(s) for {len(hero_slugs)} hero(es).")
    if failed:
        print(f"Failed ({len(failed)}):")
        for slug, err in failed:
            print(f"  - {slug}: {err}")


if __name__ == "__main__":
    main()
