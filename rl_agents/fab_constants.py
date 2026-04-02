"""fab_constants.py — Shared constants for FAB card classification.

Primary legality is now determined by the ``legal_heroes`` field from the
upstream card data (``@flesh-and-blood/types``).  Each card lists which hero
enum values are allowed to use it.  The hero entry's ``hero`` field is the
join key.

DESCRIPTOR is kept for backward-compat with ``deck_search.py`` but the
``validate_deck_legality()`` codepath no longer relies on it.
"""

# fmt: off
DESCRIPTOR: frozenset[str] = frozenset({
    # ── format / category markers ──────────────────────────────────────────
    "hero", "equipment", "weapon", "generic", "base",

    # ── weapon handedness ──────────────────────────────────────────────────
    "1h", "2h",

    # ── physical weapon sub-types ─────────────────────────────────────────
    "axe", "book", "bow", "brush", "cannon", "claw", "club", "dagger",
    "fiddle", "flail", "gun", "hammer", "item", "lute", "orb", "pistol",
    "polearm", "rock", "scepter", "scroll", "scythe", "staff", "sword",
    "wrench",

    # ── armor slot names ──────────────────────────────────────────────────
    "head", "chest", "arms", "legs",

    # ── secondary weapon slot names ───────────────────────────────────────
    "off-hand", "offhand", "quiver",

    # ── card traits / keywords ────────────────────────────────────────────
    # NOTE: revered and reviled are talent identifiers (NOT descriptors).
    # Removed so Revered/Reviled cards only appear in matching hero pools.

    # ── special card-type tags ────────────────────────────────────────────
    "demi-hero", "evo", "event", "trap",

    # ── color/pitch keywords (appear in type text, not class restrictions) ─
    "red", "yellow", "blue",

    # ── rarity / print descriptors ────────────────────────────────────────
    "token", "young", "seasoned", "veteran",

    # ── card type categories (not class/talent restrictions) ──────────────
    "action", "attack", "non-attack",
    "instant", "reaction",
    "attack reaction", "defense reaction",
    "defense",
    "block", "generic block",

    # ── card sub-types / play zones (not class restrictions) ──────────────
    "aura", "arrow",
    "ally", "dragon", "angel", "demon", "figment",
    "construct", "ash",                  # Dromai ash tokens / mech constructs
    "cog", "macro",                      # Mechanologist sub-types
    "song",                              # Bard sub-type
    "gem",                               # Jewelry/crafting sub-type
    "invocation",                        # Bravo/Oldhim/shaman sub-type
    "landmark",                          # Permanent landmark sub-type
    "resource",                          # Resource cards
    "mentor",                            # Mentor permanent sub-type
    "companion",                         # Companion permanent sub-type
    "affliction",                        # Affliction card sub-type
    "high seas",                         # Pirate location sub-type (not class)
    "placeholder card",                  # Dev/test placeholder
    "mercenary",                         # Contract mercenary tag
    "chi",                               # Monk chi sub-type
    "shuriken",                          # Ninja equipment sub-type (not class)
    "rosetta",                           # Rosetta sub-type
    "scurv",                             # Pirate crew sub-type
    "puffin",                            # Puffin creature sub-type
    "arakni",                            # Arakni spider sub-type
})
# fmt: on


_ESSENCE_ELEMENTS: frozenset[str] = frozenset(
    {"earth", "ice", "fire", "lightning", "water", "wind", "rock"}
)


def _parse_hybrid_supertypes(
    type_text: str,
) -> tuple[frozenset[str], frozenset[str]] | None:
    """Detect hybrid cards via ' / ' delimiter in type_text.

    Returns a tuple of two frozensets of non-descriptor class types
    (one per side), or None if the card is not a hybrid.
    """
    if " / " not in type_text:
        return None
    left, right = type_text.split(" / ", 1)
    left_classes = frozenset(
        w.lower() for w in left.strip().split()
        if w.lower() not in DESCRIPTOR and w != "-"
    )
    right_classes = frozenset(
        w.lower() for w in right.strip().split()
        if w.lower() not in DESCRIPTOR and w != "-"
    )
    return (left_classes, right_classes)


def _expand_hero_classes(
    hero_types: list[str],
    hero_keywords: list[str],
) -> frozenset[str]:
    """Return hero class/talent types expanded via Essence keywords.

    E.g. hero with Essence of Earth and Ice gets 'earth' and 'ice' added.
    """
    import re as _re
    classes: set[str] = {t.lower() for t in hero_types if t.lower() not in DESCRIPTOR}
    # Join all keywords so split entries like
    # ['Essence of Earth', 'Ice', 'and Lightning'] are handled correctly.
    combined = ", ".join(hero_keywords).lower()
    for match in _re.finditer(r"essence of\s+(.+?)(?=essence of|$)", combined):
        for word in _re.split(r"[\s,]+", match.group(1)):
            word = word.strip()
            if word and word not in ("and", "or", "the") and word in _ESSENCE_ELEMENTS:
                classes.add(word)
    return frozenset(classes)


import json as _json
from pathlib import Path as _Path

# Map short format codes to the canonical format names stored in
# slug_index legal_formats (sourced from the official FAB card data).
FORMAT_MAP: dict[str, str] = {
    "cc": "ClassicConstructed",
    "blitz": "Blitz",
    "draft": "Draft",
    "sealed": "Sealed",
    "clash": "Clash",
    "open": "Open",
    "ll": "LivingLegend",
    "upf": "UltimatePitFight",
    "silverage": "SilverAge",
}

_BANNED_CARDS_PATH = _Path(__file__).resolve().parent.parent / "card_data" / "banned_cards.json"


def load_banned_cards(fmt: str) -> frozenset[str]:
    """Return a frozenset of banned card slugs for the given format.

    .. deprecated::
        Use the ``legal_formats`` field from slug_index instead.
        This function reads from banned_cards.json which is no longer maintained.
    """
    if not _BANNED_CARDS_PATH.exists():
        return frozenset()
    try:
        with open(_BANNED_CARDS_PATH, encoding="utf-8") as f:
            data = _json.load(f)
    except (ValueError, OSError):
        return frozenset()
    slugs = data.get(fmt, [])
    return frozenset(slugs)


import re as _re

_SPEC_RE = _re.compile(r'\*\*(.+?)\s+Specialization\*\*', _re.IGNORECASE)


def _check_specialization(spec_req: str, hero_name: str, hero_is_young: bool) -> bool:
    """Return True if *hero_name* satisfies *spec_req*.

    Rules:
    - ``"Legendary X"``  → hero name must contain all words of X (case-insensitive)
                           AND the hero must not be Young.
    - ``"X or Y"``       → hero name must satisfy either X or Y (recursive).
    - ``"X"``            → all words of X must appear in hero name.
    """
    hero_lower = hero_name.lower()
    # Handle "X or Y" alternatives
    if _re.search(r'\bor\b', spec_req, _re.IGNORECASE):
        parts = _re.split(r'\bor\b', spec_req, flags=_re.IGNORECASE)
        return any(_check_specialization(p.strip(), hero_name, hero_is_young) for p in parts)
    # Handle "Legendary X" prefix
    legendary = False
    req = spec_req.strip()
    if req.lower().startswith("legendary "):
        legendary = True
        req = req[len("legendary "):].strip()
    if legendary and hero_is_young:
        return False
    words = [w.lower() for w in req.split() if w]
    return all(w in hero_lower for w in words)


def validate_deck_legality(
    deck_cards: list[dict],
    equipment: list[dict],
    hero_types: list[str],
    slug_index: dict,
    hero_keywords: list[str] | None = None,
    hero_name: str = "",
    banned_slugs: frozenset[str] | None = None,
    fmt: str | None = None,
    hero_enum: str = "",
) -> list[str]:
    """Check every card in a deck for FAB class/talent legality.

    Returns a list of violation strings (empty list = deck is legal).

    Primary check: uses the upstream ``legal_heroes`` field on each card.
    A card is legal if the hero's enum value (``hero_enum``) appears in
    the card's ``legal_heroes`` list.  Cards with an empty/missing
    ``legal_heroes`` list are assumed legal (they may be tokens or cards
    without upstream hero restrictions).

    Args:
        deck_cards:   list of card dicts with at least a ``card_slug`` key.
        equipment:    list of equipment/weapon dicts with at least a ``card_slug`` key.
        hero_types:   raw type list from slug_index for the hero card.
        slug_index:   the ``by_slug`` dict from slug_index.
        hero_name:    display name of the hero (for specialization checks).
        hero_enum:    the hero's ``hero`` field value from slug_index
                      (e.g. ``"RKO"``, ``"Oscilio"``).  This is the join key
                      into each card's ``legal_heroes`` list.
        fmt:          format key for legal_formats checks (default ``None``).

    Returns:
        A list of human-readable violation strings.
    """
    hero_is_young = "young" in {t.lower() for t in hero_types}

    # Resolve canonical format name for legal_formats checks
    _canonical_fmt = FORMAT_MAP.get(fmt, fmt) if fmt else None

    violations: list[str] = []
    all_cards = list(deck_cards) + list(equipment)
    for card in all_cards:
        slug = card.get("card_slug") or card.get("slug", "")

        entry = slug_index.get(slug) or slug_index.get(slug.replace("-", "_"))
        if not entry:
            continue  # not in slug_index → cannot verify, skip

        # ── format legality check (preferred) ────────────────────────────
        if _canonical_fmt:
            legal_fmts = entry.get("legal_formats", [])
            if legal_fmts and _canonical_fmt not in legal_fmts:
                name = entry.get("name", slug)
                violations.append(
                    f"{name!r} ({slug}): not legal in {_canonical_fmt}"
                )
                continue
        # ── deprecated banned card check (fallback) ──────────────────────
        elif banned_slugs and slug in banned_slugs:
            name = entry.get("name", slug)
            violations.append(f"{name!r} ({slug}): banned in this format")

        # ── specialization check ──────────────────────────────────────────
        if hero_name:
            ft = entry.get("functional_text") or ""
            m = _SPEC_RE.search(ft)
            if m:
                spec_req = m.group(1)
                if not _check_specialization(spec_req, hero_name, hero_is_young):
                    name = entry.get("name", slug)
                    violations.append(
                        f"{name!r} ({slug}): requires {spec_req!r} Specialization"
                        f" — hero is {hero_name!r}"
                    )
                continue  # specialization cards don't need further class checks

        # ── hero legality check (primary: legal_heroes) ──────────────────
        legal_heroes = entry.get("legal_heroes") or []
        if hero_enum and legal_heroes:
            if hero_enum not in legal_heroes:
                name = entry.get("name", slug)
                violations.append(
                    f"{name!r} ({slug}): not legal for hero {hero_enum!r}"
                )
    return violations
