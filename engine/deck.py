"""Deck loading and player state construction for FAB self-play engine (OO rewrite)."""

from __future__ import annotations

import re
import random
import unicodedata
from typing import Optional

from engine.card import CardDB, Card
from engine.state import Player, Event, TriggeredAbility



def _kw(card, kw):
    if card is None:
        return False
    kw_lower = kw.lower()
    if any(k.lower() == kw_lower for k in (card.keywords or [])):
        return True
    return card.functional_text is not None and f'**{kw}**' in card.functional_text


# Map equipment type strings to slot names
_EQUIP_TYPE_TO_SLOT = {
    "Head": "head",
    "Chest": "chest",
    "Arms": "arms",
    "Legs": "legs",
    "Quiver": "weapon",  # 8.2.15a: quiver equips to weapon zone (can share with 2H bow)
    'Offhand': "weapon",
}

# Known hero slug aliases seen in scraped/exported deck headers.
_HERO_SLUG_ALIASES = {
    "jarl_vetreii": "jarl_vetreidi",
    "fab_jarl_vetreii_deck_analysis_": "jarl_vetreidi",
}


def _slugify(name: str) -> str:
    """Convert a card display name to slug format."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"['\u2019,!?.]", "", s)
    s = re.sub(r"[\s\-]+", "_", s.strip())
    s = re.sub(r"[^a-z0-9_]", "", s)
    return s


def _parse_fabrary_card_line(line: str):
    m = re.match(r"^(\d+)x\s+(.+)$", line.strip())
    if not m:
        return None
    count = int(m.group(1))
    rest = m.group(2).strip()
    color_m = re.match(r"^(.+?)\s+\((red|yellow|blue)\)$", rest, flags=re.IGNORECASE)
    if color_m:
        base_slug = _slugify(color_m.group(1))
        color = color_m.group(2).lower()
        if base_slug.endswith(f"_{color}"):
            slug = base_slug
        else:
            slug = f"{base_slug}_{color}"
    else:
        slug = _slugify(rest)
    slug = re.sub(r"_(red|yellow|blue)_\1$", r"_\1", slug)
    return count, slug


def _resolve_fabrary_slug(slug: str, card_db: CardDB) -> Optional[str]:
    """Resolve parsed Fabrary slug to a canonical DB slug.

    Handles several real-world cases from generated decks:
    - short color suffixes (_r/_y/_b)
    - duplicated color naming (e.g. backup_protocol_red)
    - unsupported color variants (fallback to available printing by base name)
    """
    if card_db.get(slug) is not None:
        return slug

    if slug.endswith(("_r", "_y", "_b")):
        short_fixed = slug[:-2]
        if card_db.get(short_fixed) is not None:
            return short_fixed
        slug = short_fixed

    # First try CardDB's canonical resolution as-is.
    resolved = card_db.resolve_slug(slug)
    if resolved is not None:
        return resolved

    for color in ("red", "yellow", "blue"):
        suffix = f"_{color}"
        if slug.endswith(suffix):
            base = slug[:-len(suffix)]

            # Some canon slugs include color in both name and suffix.
            resolved = card_db.resolve_slug(f"{slug}_{color}")
            if resolved is not None:
                return resolved

            # If requested color doesn't exist, fall back to an available printing.
            resolved = card_db.resolve_slug(base)
            if resolved is not None:
                return resolved
            break

    return None


def _is_fabrary_format(lines: list[str]) -> bool:
    for line in lines[:15]:
        stripped = line.strip()
        if stripped.startswith("Hero:") or stripped == "Arena cards":
            return True
    return False


def _load_deck_fabrary(lines: list[str], card_db: CardDB) -> dict:
    hero_slug: Optional[str] = None
    weapons: list[str] = []  # all weapon slugs in arena order (count-expanded)
    equipment: dict[str, str] = {}
    cards: list[str] = []

    in_arena = False
    in_deck = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            in_arena = in_deck = False
            continue
        if stripped.startswith("Name:") or stripped.startswith("Format:"):
            continue
        if stripped.startswith("Made with") or stripped.startswith("See the full") or stripped.startswith("http"):
            continue
        if stripped.startswith("Hero:"):
            hero_slug = _slugify(stripped[5:].strip())
            hero_slug = _HERO_SLUG_ALIASES.get(hero_slug, hero_slug)
            continue
        if stripped == "Arena cards":
            in_arena = True
            in_deck = False
            continue
        if stripped == "Deck cards":
            in_deck = True
            in_arena = False
            continue

        parsed = _parse_fabrary_card_line(stripped)
        if parsed is None:
            continue
        count, slug = parsed
        resolved_slug = _resolve_fabrary_slug(slug, card_db)
        if resolved_slug is None:
            continue
        slug = resolved_slug

        if in_arena:
            card = card_db.get(slug)
            if card is None:
                continue
            if "Weapon" in card.types:
                for _ in range(count):
                    weapons.append(slug)
            else:
                # Upstream schema stores armor slots in subtypes (Head/Chest/Arms/Legs).
                card_slot_tokens = set((card.types or []) + (card.subtypes or []))
                for type_name, slot_name in _EQUIP_TYPE_TO_SLOT.items():
                    if type_name in card_slot_tokens and slot_name not in equipment:
                        equipment[slot_name] = slug
                        break
        elif in_deck:
            for _ in range(count):
                cards.append(slug)

    return {
        "hero": hero_slug,
        "weapon": weapons[0] if weapons else None,
        "weapons": weapons,
        "equipment": equipment,
        "cards": cards,
    }


def load_deck(path: str, card_db: CardDB) -> dict:
    """Load a deck from a text file."""
    hero_slug: Optional[str] = None
    weapon_slugs: list[str] = []
    equipment: dict[str, str] = {}
    cards: list[str] = []

    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    if _is_fabrary_format(lines):
        result = _load_deck_fabrary(lines, card_db)
        if result["hero"] is None:
            raise ValueError(f"No hero found in fabrary deck file: {path}")
        return result

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split()
        if parts[0] == "hero":
            hero_slug = parts[1]
        elif parts[0] == "weapon":
            weapon_slugs.append(parts[1])
        elif parts[0] == "equipment":
            equip_slug = parts[1]
            card = card_db.get(equip_slug)
            if card is not None:
                slot_found = False
                for type_name, slot_name in _EQUIP_TYPE_TO_SLOT.items():
                    if type_name in (card.raw_types or []):
                        equipment[slot_name] = equip_slug
                        slot_found = True
                        break
                if not slot_found:
                    raise ValueError(f"Equipment Slot not found: {card.slug}")
                    #equipment[equip_slug] = equip_slug
        else:
            try:
                count = int(parts[0])
                slug = parts[1]
                for _ in range(count):
                    cards.append(slug)
            except (ValueError, IndexError):
                pass

    if hero_slug is None:
        raise ValueError(f"No hero found in deck file: {path}")

    return {
        "hero": hero_slug,
        "weapon": weapon_slugs,
        "equipment": equipment,
        "cards": cards,
    }


def get_card_info(slug: str, card_db: CardDB) -> Card:
    """Get a card from db, or raise error if not found."""
    c = card_db.get(slug)
    if c is None:
        raise ValueError(f'Card slug "{slug}" not found in card database.')
    return c


def create_player(
    deck_data: dict,
    player_id: int,
    card_db: CardDB,
    seed: Optional[int] = None,
) -> Player:
    """Set up initial Player.
    Returns a Player object with deck loaded and shuffled, hero card assigned, and weapon/equipment placed.
    """
    rng = random.Random(seed)

    # Get hero card
    hero_card = get_card_info(deck_data["hero"], card_db)

    # Create player
    player = Player(player_id=player_id, hero_card=hero_card)

    # Override life/intellect from card db if set
    if hero_card.raw_life and hero_card.raw_life > 0:
        player.life = hero_card.raw_life
    if hero_card.raw_intellect and hero_card.raw_intellect > 0:
        player.intellect = hero_card.raw_intellect

    # Shuffle and load deck
    deck_slugs = list(deck_data["cards"])
    rng.shuffle(deck_slugs)

    for slug in deck_slugs:
        card = get_card_info(slug, card_db)
        card.owner = player_id
        card.controller = None
        player.deck.cards.append(card)
        card.zone = "deck"
        card.is_public = False

    # Place weapon
    # CR 3.0.2 / 8.2.10b: 2H weapons occupy both weapon zones simultaneously,
    # which prevents equipping a second weapon.
    weapon_slugs = deck_data.get("weapon")
    if weapon_slugs:
        for weapon_slug in weapon_slugs:
            wc = get_card_info(weapon_slug, card_db)
            wc.owner = player_id
            wc.controller = player_id
            if not player.weapon1.top:
                player.weapon1.add(wc)
                is_two_handed = "2H" in (wc.raw_types or [])
                if is_two_handed:
                    player.weapon2.add(wc)  # same object in both zones — CR 3.0.2
            else:
                if not player.weapon2.top:
                    player.weapon2.add(wc)
                else:
                    continue
            
        

    # Place equipment
    for slot_name, equip_slug in deck_data.get("equipment", {}).items():
        if slot_name != 'weapon':
            equip_zone = player.zone_by_name(slot_name)
            if equip_zone is None:
                continue
            ec = get_card_info(equip_slug, card_db)
            ec.owner = player_id
            ec.controller = player_id
            equip_zone.add(ec)
        else:
            if player.weapon1.top is None and player.weapon2.top is None:
                player.weapon1.add(get_card_info(equip_slug, card_db))
            elif player.weapon1.top is not None and player.weapon2.top is None:
                player.weapon2.add(get_card_info(equip_slug, card_db))
            else:
                continue

    return player
