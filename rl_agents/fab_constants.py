"""fab_constants.py — Shared constants for FAB card classification.

DESCRIPTOR is the set of type-array words that are equipment/format
descriptors, NOT class or talent identifiers.  Used in the legality
subset check: a card is legal for a hero if its non-descriptor types
are a subset of the hero's non-descriptor types.

Additions vs removals:
  - Physical weapon types (sword, axe, flail, etc.)  → DESCRIPTOR
  - Armor slot names (head, chest, arms, legs, …)    → DESCRIPTOR
  - Card traits / keywords (revered, reviled, …)     → DESCRIPTOR
  - Class identifiers (warrior, ninja, brute, …)     → NOT in DESCRIPTOR
  - Talent identifiers (draconic, shadow, earth, …)  → NOT in DESCRIPTOR
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
) -> list[str]:
    """Check every card in a deck for FAB class/talent legality.

    Returns a list of violation strings (empty list = deck is legal).

    FAB rule: a card is legal if it is Generic (no non-descriptor types)
    OR all of its non-descriptor types are a subset of the hero's
    non-descriptor types.  Specialization cards additionally require the
    hero's name to match the specialization constraint.

    Args:
        deck_cards:  list of card dicts with at least a ``card_slug`` key.
        equipment:   list of equipment/weapon dicts with at least a ``card_slug`` key.
        hero_types:  raw type list from slug_index for the hero card
                     (e.g. ``['Warrior', 'Hero', 'Young']``).
        slug_index:  the ``by_slug`` dict from slug_index.json.
        hero_name:   display name of the hero (e.g. ``"Olympia, Prized Fighter"``).
                     Required for specialization checks; ignored if empty.

    Returns:
        A list of human-readable violation strings.
    """
    hero_classes: frozenset[str] = _expand_hero_classes(
        hero_types, hero_keywords or []
    )
    hero_is_young = "young" in {t.lower() for t in hero_types}

    violations: list[str] = []
    all_cards = list(deck_cards) + list(equipment)
    for card in all_cards:
        slug = card.get("card_slug") or card.get("slug", "")
        entry = slug_index.get(slug) or slug_index.get(slug.replace("-", "_"))
        if not entry:
            continue  # not in slug_index → cannot verify, skip

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

        # ── class/talent check ────────────────────────────────────────────
        # Check for hybrid cards via ' / ' delimiter in type_text
        type_text = entry.get("type_text", "")
        hybrid = _parse_hybrid_supertypes(type_text)
        if hybrid is not None:
            left_classes, right_classes = hybrid
            # Hybrid card is legal if EITHER side satisfies hero classes
            left_ok = not left_classes or left_classes <= hero_classes
            right_ok = not right_classes or right_classes <= hero_classes
            if not left_ok and not right_ok:
                name = entry.get("name", slug)
                violations.append(
                    f"{name!r} ({slug}): hybrid card types "
                    f"{set(left_classes)!r} | {set(right_classes)!r} "
                    f"— neither side subset of hero types {set(hero_classes)!r}"
                )
        else:
            card_classes: frozenset[str] = frozenset(
                t.lower() for t in entry.get("types", []) if t.lower() not in DESCRIPTOR
            )
            if card_classes and not card_classes <= hero_classes:
                name = entry.get("name", slug)
                violations.append(
                    f"{name!r} ({slug}): card types {set(card_classes)!r} "
                    f"not subset of hero types {set(hero_classes)!r}"
                )
    return violations
