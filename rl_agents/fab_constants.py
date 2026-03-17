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


def _expand_hero_classes(
    hero_types: list[str],
    hero_keywords: list[str],
) -> frozenset[str]:
    """Return hero class/talent types expanded via Essence keywords.

    E.g. hero with Essence of Earth and Ice gets 'earth' and 'ice' added.
    """
    import re as _re
    classes: set[str] = {t.lower() for t in hero_types if t.lower() not in DESCRIPTOR}
    for kw in hero_keywords:
        kw_lower = kw.lower()
        if "essence of" in kw_lower:
            after = kw_lower.split("essence of", 1)[1]
            for word in _re.split(r"[\s,]+", after):
                word = word.strip()
                if word and word not in ("and", "or", "the") and word in _ESSENCE_ELEMENTS:
                    classes.add(word)
    return frozenset(classes)


def validate_deck_legality(
    deck_cards: list[dict],
    equipment: list[dict],
    hero_types: list[str],
    slug_index: dict,
    hero_keywords: list[str] | None = None,
) -> list[str]:
    """Check every card in a deck for FAB class/talent legality.

    Returns a list of violation strings (empty list = deck is legal).

    FAB rule: a card is legal if it is Generic (no non-descriptor types)
    OR all of its non-descriptor types are a subset of the hero's
    non-descriptor types.

    Args:
        deck_cards: list of card dicts with at least a ``card_slug`` key.
        equipment:  list of equipment/weapon dicts with at least a ``card_slug`` key.
        hero_types: raw type list from slug_index for the hero card
                    (e.g. ``['Warrior', 'Hero', 'Young']``).
        slug_index: the ``by_slug`` dict from slug_index.json.

    Returns:
        A list of human-readable violation strings.
    """
    hero_classes: frozenset[str] = _expand_hero_classes(
        hero_types, hero_keywords or []
    )

    violations: list[str] = []
    all_cards = list(deck_cards) + list(equipment)
    for card in all_cards:
        slug = card.get("card_slug") or card.get("slug", "")
        entry = slug_index.get(slug) or slug_index.get(slug.replace("-", "_"))
        if not entry:
            continue  # not in slug_index → cannot verify, skip
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
