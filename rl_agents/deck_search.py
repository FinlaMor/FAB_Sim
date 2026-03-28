"""rl_agents/deck_search.py

Evolutionary deck search and tournament simulation for FAB.

Two-stage deck construction:
    Stage 1 — Pool Builder: Select 80 cards for a hero (tournament registration)
    Stage 2 — Matchup Selector: Given pool + opponent hero, pick 60 deck + equipment

Archetype discovery via flex_depth:
    Each pool has a flex_depth parameter (0-20) that controls how many of the
    60 deck slots are matchup-flexible vs locked core cards.
      - flex_depth=0:  pure aggro, locked 60-card core, no sideboarding
      - flex_depth=10: midrange, 50 core + 10 flex slots
      - flex_depth=20: control, 40 core + 20 flex, maximum matchup adaptation

    flex_depth is evolved as part of the genome. The search discovers whether
    tight or wide pools win for each hero automatically.

Tournament simulation:
    - 200-300 players, hero distribution matches fablazing meta percentages
    - Each player builds an 80-card pool via evolutionary search
    - Swiss pairings, matchup-specific deck selection before each round

Usage:
    python -m rl_agents.deck_search search --hero kayo-underhanded-cheat --checkpoint ckpt.pt
    python -m rl_agents.deck_search tournament --checkpoint ckpt.pt --players 256
"""
from __future__ import annotations

import copy
import enum
import json
import random
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import torch
import torch.nn as nn

from rl_agents.deck_evaluator import (
    CardVocab,
    build_evaluator,
    load_checkpoint,
    load_meta_weights,
)

SLUG_INDEX_PATH = Path(__file__).resolve().parent.parent / "card_data" / "slug_index.json"

from .fab_constants import DESCRIPTOR, validate_deck_legality

_valid_slugs: set[str] | None = None


def _get_valid_slugs() -> set[str]:
    """Load the set of all real card slugs from slug_index.json."""
    global _valid_slugs
    if _valid_slugs is None:
        if SLUG_INDEX_PATH.exists():
            with open(SLUG_INDEX_PATH, encoding="utf-8") as f:
                data = json.load(f)
            _valid_slugs = set(data.get("by_slug", {}).keys())
        else:
            _valid_slugs = set()
    return _valid_slugs


MAX_COPIES = 3
POOL_SIZE = 80       # total cards in registered pool
MIN_DECK = 60        # minimum deck cards to play
MAX_EQUIPMENT = 4    # head, chest, arms, legs
MAX_WEAPONS = 2      # maximum number of weapons (usually 1-2)
MAX_FLEX_DEPTH = 20  # maximum flex slots (60 - 40 core minimum)


class PoolStrategy(enum.Enum):
    """When the player selects which pool to register.

    PER_ROUND:  pick the best pool before each round based on the specific
                opponent (maximum adaptation, like a best-of-3 sideboard).
    LOCKED:     pick one pool at registration and use it for every round
                (standard tournament rules — submit decklist before round 1).
    """
    PER_ROUND = "per_round"
    LOCKED = "locked"


def _jaccard_distance(pool_a: "CardPool", pool_b: "CardPool") -> float:
    """Card-level Jaccard distance between two pools (0 = identical, 1 = disjoint)."""
    set_a = set(pool_a.deck_slugs)
    set_b = set(pool_b.deck_slugs)
    if not set_a and not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return 1.0 - (intersection / union) if union > 0 else 0.0


def _archetype_label(pool: "CardPool") -> str:
    """Derive a human-readable archetype label from card color distribution.

    Uses the color suffix on card slugs (red/yellow/blue) to compute
    the pitch curve, then labels accordingly.
    """
    red = sum(1 for s in pool.deck_slugs if s.endswith("_red"))
    yellow = sum(1 for s in pool.deck_slugs if s.endswith("_yellow"))
    blue = sum(1 for s in pool.deck_slugs if s.endswith("_blue"))
    total = red + yellow + blue

    if total == 0:
        return "unknown"

    red_ratio = red / total
    blue_ratio = blue / total

    if red_ratio > 0.55:
        return "aggro"
    elif blue_ratio > 0.45:
        return "fatigue"
    elif pool.flex_depth < 6:
        return "aggro"
    elif pool.flex_depth > 14:
        return "control"
    else:
        return "midrange"


# ---------------------------------------------------------------------------
# Card pool data
# ---------------------------------------------------------------------------

@dataclass
class CardPool:
    """A player's registered 80-card pool for a tournament.

    flex_depth controls how the pool is split into core vs flex for
    matchup-specific deck selection:
        core_size = max(40, MIN_DECK - flex_depth)
        flex_slots = MIN_DECK - core_size
    """
    hero_slug: str
    equipment_slugs: list[str]        # up to MAX_EQUIPMENT
    weapon_slugs: list[str]           # 1-2 weapons
    deck_slugs: list[str]             # flat list with repeats for copies
    flex_depth: int = 10              # 0 = locked aggro, 20 = max adaptation
    fitness: float = 0.0

    @property
    def total_cards(self) -> int:
        return len(self.equipment_slugs) + len(self.weapon_slugs) + len(self.deck_slugs)

    @property
    def core_size(self) -> int:
        return max(40, MIN_DECK - self.flex_depth)

    @property
    def flex_slots(self) -> int:
        return MIN_DECK - self.core_size

    def all_slugs(self) -> list[str]:
        return self.equipment_slugs + self.weapon_slugs + self.deck_slugs


@dataclass
class MatchDeck:
    """The specific cards a player brings to a match (subset of pool)."""
    hero_slug: str
    equipment_slugs: list[str]
    weapon_slugs: list[str]
    deck_slugs: list[str]             # exactly MIN_DECK cards


# ---------------------------------------------------------------------------
# Hero card database (from fablazing)
# ---------------------------------------------------------------------------

class HeroCardDB:
    """Provides the legal card pool for each hero from fablazing data."""

    MIN_EQUIPMENT = 4
    MIN_WEAPONS = 1

    def __init__(self, db_path: str | Path, fmt: str = "cc"):
        conn = sqlite3.connect(str(db_path))

        self.hero_cards: dict[str, list[dict]] = {}
        self.hero_equipment: dict[str, list[dict]] = {}
        self.hero_weapons: dict[str, list[dict]] = {}
        self._slug_idx: dict = {}  # populated below, kept for validation

        heroes = [r[0] for r in conn.execute(
            "SELECT DISTINCT hero_slug FROM card_stats WHERE format = ?", (fmt,)
        ).fetchall()]

        # Fetch generic equipment (used by 3+ heroes) for padding
        generic_rows = conn.execute(
            """
            SELECT card_slug, card_name,
                   CASE
                     WHEN COALESCE(equipment_subtype,'') != '' THEN equipment_subtype
                     WHEN card_type = 'weapon_1h' THEN 'weapon-1h'
                     WHEN card_type = 'weapon_2h' THEN 'weapon-2h'
                     ELSE ''
                   END as equipment_subtype,
                   COUNT(DISTINCT hero_slug) as hero_count,
                   AVG(frequency) as avg_freq, AVG(win_rate) as avg_wr
            FROM card_stats
            WHERE card_type IN ('equipment','weapon_1h','weapon_2h') AND format = ?
            GROUP BY card_slug, equipment_subtype
            HAVING hero_count >= 3
            ORDER BY hero_count DESC, avg_freq DESC
            """,
            (fmt,),
        ).fetchall()
        generic_equip = [
            {"slug": slug, "name": name or slug, "type": "equipment",
             "equipment_subtype": equip_subtype or "",
             "frequency": avg_f or 0.0, "avg_copies": 1.0, "win_rate": avg_wr or 0.5}
            for slug, name, equip_subtype, _, avg_f, avg_wr in generic_rows
        ]

        # Fetch generic deck cards (used by 5+ heroes) for padding
        generic_deck_rows = conn.execute(
            """
            SELECT card_slug, card_name, COUNT(DISTINCT hero_slug) as hero_count,
                   AVG(frequency) as avg_freq, AVG(avg_copies) as avg_copies,
                   AVG(win_rate) as avg_wr
            FROM card_stats
            WHERE card_type = 'deck' AND format = ?
            GROUP BY card_slug
            HAVING hero_count >= 5
            ORDER BY hero_count DESC, avg_freq DESC
            """,
            (fmt,),
        ).fetchall()
        generic_deck = [
            {"slug": slug, "name": name or slug, "type": "deck",
             "frequency": avg_f or 0.0, "avg_copies": avg_c or 1.0,
             "win_rate": avg_wr or 0.5}
            for slug, name, _, avg_f, avg_c, avg_wr in generic_deck_rows
        ]

        # Map DB card_type → equipment_subtype for weapon rows
        _WEAPON_TYPE_MAP = {"weapon_1h": "weapon-1h", "weapon_2h": "weapon-2h"}
        _ARMOR_SLOTS = ("head", "chest", "arms", "legs")

        # Pre-load slug index for class-weapon matching
        _slug_idx: dict = {}
        if SLUG_INDEX_PATH.exists():
            with open(SLUG_INDEX_PATH, encoding="utf-8") as _f:
                _slug_idx = json.load(_f).get("by_slug", {})
        self._slug_idx = _slug_idx

        # Build weapon candidate list with slug_index class types pre-computed.
        # DESCRIPTOR imported from fab_constants — shared with generate_heuristic_decks.py
        _all_weapon_rows = conn.execute(
            """
            SELECT card_slug, card_name,
                   COALESCE(equipment_subtype,
                            CASE card_type WHEN 'weapon_1h' THEN 'weapon-1h'
                                           WHEN 'weapon_2h' THEN 'weapon-2h'
                                           ELSE '' END) as equip_sub,
                   AVG(frequency) as avg_freq
            FROM card_stats
            WHERE card_type IN ('weapon_1h','weapon_2h') AND format = ?
            GROUP BY card_slug
            ORDER BY avg_freq DESC
            """,
            (fmt,),
        ).fetchall()
        # Pre-index: weapon_slug → (card_dict, frozenset_of_class_types)
        _weapon_index: list[tuple[dict, frozenset]] = []
        for slug, name, sub, freq in _all_weapon_rows:
            if not sub or not sub.startswith("weapon"):
                continue
            w = {"slug": slug, "name": name or slug, "type": "equipment",
                 "equipment_subtype": sub, "frequency": freq or 0.0,
                 "avg_copies": 1.0, "win_rate": 0.5}
            w_entry = _slug_idx.get(slug) or _slug_idx.get(slug.replace("-", "_"))
            w_classes: frozenset = frozenset()
            if w_entry:
                w_classes = frozenset(
                    t.lower() for t in w_entry.get("types", [])
                    if t.lower() not in DESCRIPTOR
                )
            _weapon_index.append((w, w_classes))

        for hero in heroes:
            rows = conn.execute(
                "SELECT card_slug, card_name, card_type, frequency, avg_copies, win_rate, "
                "       COALESCE(equipment_subtype, '') "
                "FROM card_stats WHERE hero_slug = ? AND format = ? "
                "ORDER BY frequency DESC",
                (hero, fmt),
            ).fetchall()

            equip = []
            deck = []
            weap = []
            for slug, name, ctype, freq, avg_c, wr, equip_subtype in rows:
                ct = ctype or "deck"
                if ct in ("token", "hero"):
                    continue
                if not equip_subtype and ct in _WEAPON_TYPE_MAP:
                    equip_subtype = _WEAPON_TYPE_MAP[ct]
                entry = {
                    "slug": slug, "name": name or slug, "type": ct,
                    "equipment_subtype": equip_subtype or "",
                    "frequency": freq or 0.0, "avg_copies": avg_c or 1.0,
                    "win_rate": wr or 0.5,
                }
                if ct == "equipment":
                    equip.append(entry)
                elif ct in ("weapon_1h", "weapon_2h"):
                    weap.append(entry)
                else:
                    deck.append(entry)

            # Compute hero class types once (used for both armor and weapon checks)
            hero_entry = _slug_idx.get(hero) or _slug_idx.get(hero.replace("-", "_"))
            hero_classes: frozenset = frozenset(
                t.lower() for t in (hero_entry or {}).get("types", [])
                if t.lower() not in DESCRIPTOR
            )

            def _equip_legal(card_slug: str) -> bool:
                """True if card's class types are a subset of this hero's class+talents."""
                entry = _slug_idx.get(card_slug) or _slug_idx.get(card_slug.replace("-", "_"))
                if not entry:
                    return True  # not in slug_index → treat as generic
                card_classes = frozenset(
                    t.lower() for t in entry.get("types", [])
                    if t.lower() not in DESCRIPTOR
                )
                return not card_classes or card_classes <= hero_classes

            # Pad armor slots with generic equipment where hero is missing a slot.
            # Apply class legality check — e.g. Brute-typed helms must not go on Warriors.
            hero_slugs_set = {e["slug"] for e in equip}
            filled_slots = {e["equipment_subtype"] for e in equip}
            for slot in _ARMOR_SLOTS:
                if slot in filled_slots:
                    continue
                for ge in generic_equip:
                    if ge["equipment_subtype"] == slot and ge["slug"] not in hero_slugs_set:
                        if _equip_legal(ge["slug"]):
                            equip.append(ge)
                            hero_slugs_set.add(ge["slug"])
                            filled_slots.add(slot)
                            break

            # Ensure hero has at least one weapon via class-matched fallback.
            # FAB rule: weapon's class types must be a subset of hero's class+talents.
            if not weap:
                if hero_entry:
                    existing_slugs = {e["slug"] for e in weap} | {e["slug"] for e in equip}
                    for w, w_classes in _weapon_index:
                        if w["slug"] in existing_slugs:
                            continue
                        # Legal if weapon has no class types (generic) or all its
                        # class types are present in the hero's class+talents
                        if not w_classes or w_classes <= hero_classes:
                            weap.append(w)
                            existing_slugs.add(w["slug"])
                            break  # one weapon is enough for the fallback

            # Pad deck with missing color variants of existing cards,
            # but ONLY if the variant exists in the card database.
            valid = _get_valid_slugs()
            deck_slugs = {e["slug"] for e in deck}
            color_variants: list[dict] = []
            for entry in deck:
                parts = entry["slug"].rsplit("_", 1)
                if len(parts) != 2 or parts[1] not in ("red", "yellow", "blue"):
                    continue
                base, color = parts
                for alt in ("red", "yellow", "blue"):
                    if alt == color:
                        continue
                    alt_slug = f"{base}_{alt}"
                    if alt_slug in deck_slugs:
                        continue
                    if valid and alt_slug not in valid:
                        continue
                    color_variants.append({
                        "slug": alt_slug,
                        "name": entry["name"],
                        "type": "deck",
                        "frequency": entry["frequency"] * 0.3,
                        "avg_copies": entry["avg_copies"],
                        "win_rate": entry.get("win_rate", 0.5),
                    })
                    deck_slugs.add(alt_slug)
            deck.extend(color_variants)

            # Pad with generic deck cards (staples used by 5+ heroes)
            # if the hero still doesn't have enough unique cards
            total_possible = sum(
                min(MAX_COPIES, round(e.get("avg_copies", 1)))
                for e in deck
            )
            if total_possible < MIN_DECK:
                for gd in generic_deck:
                    if gd["slug"] not in deck_slugs:
                        deck.append(gd)
                        deck_slugs.add(gd["slug"])
                        total_possible += min(MAX_COPIES, round(gd.get("avg_copies", 1)))
                        if total_possible >= MIN_DECK:
                            break

            self.hero_cards[hero] = deck
            self.hero_equipment[hero] = equip
            self.hero_weapons[hero] = weap

        conn.close()

    @classmethod
    def from_slug_index(cls, path: str | Path | None = None) -> "HeroCardDB":
        """Build a HeroCardDB from slug_index.json instead of fablazing DB.

        Uses card type information to classify cards into equipment, weapons,
        and deck cards. Hero-card legality is determined by class/talent subset
        check (non-DESCRIPTOR types). All cards get default frequency/win_rate
        since no meta data is available.
        """
        obj = cls.__new__(cls)
        obj.hero_cards = {}
        obj.hero_equipment = {}
        obj.hero_weapons = {}

        idx_path = Path(path) if path else SLUG_INDEX_PATH
        if not idx_path.exists():
            obj._slug_idx = {}
            return obj

        with open(idx_path, encoding="utf-8") as f:
            raw = json.load(f)
        slug_idx = raw.get("by_slug", {})
        obj._slug_idx = slug_idx

        _ARMOR_SLOTS = {"head", "chest", "arms", "legs"}
        _WEAPON_KEYWORDS = {"weapon", "1h", "2h", "sword", "axe", "bow", "dagger",
                            "hammer", "staff", "scepter", "scythe", "claw", "club",
                            "flail", "gun", "pistol", "cannon", "polearm", "book",
                            "orb", "fiddle", "lute", "brush", "wrench", "rock",
                            "scroll", "item"}
        _EQUIP_KEYWORD = "equipment"

        def _default_entry(slug: str, card_type: str, equip_subtype: str = "") -> dict:
            return {
                "slug": slug,
                "name": slug,
                "type": card_type,
                "equipment_subtype": equip_subtype,
                "frequency": 0.5,
                "avg_copies": 2.0,
                "win_rate": 0.5,
            }

        def _non_descriptor_types(types: list[str]) -> frozenset:
            return frozenset(t.lower() for t in types if t.lower() not in DESCRIPTOR)

        # Identify heroes and build per-card classification
        heroes: dict[str, dict] = {}  # hero_slug -> slug_idx entry
        all_cards: list[tuple[str, dict]] = []  # (slug, entry) for non-hero cards

        for slug, entry in slug_idx.items():
            types_lower = [t.lower() for t in entry.get("types", [])]
            if "hero" in types_lower:
                heroes[slug] = entry
            else:
                all_cards.append((slug, entry))

        # Classify each non-hero card
        for hero_slug, hero_entry in heroes.items():
            hero_classes = _non_descriptor_types(hero_entry.get("types", []))

            equip: list[dict] = []
            weap: list[dict] = []
            deck: list[dict] = []

            for card_slug, card_entry in all_cards:
                card_types_lower = [t.lower() for t in card_entry.get("types", [])]
                card_classes = _non_descriptor_types(card_entry.get("types", []))

                # Legality: card's class/talent types must be subset of hero's
                if card_classes and not card_classes <= hero_classes:
                    continue

                # Classify by type keywords
                is_equipment = _EQUIP_KEYWORD in card_types_lower
                armor_slot = ""
                for s in _ARMOR_SLOTS:
                    if s in card_types_lower:
                        armor_slot = s
                        break
                is_weapon = any(t in _WEAPON_KEYWORDS for t in card_types_lower) and not armor_slot

                if is_weapon:
                    # Determine handedness
                    if "2h" in card_types_lower:
                        sub = "weapon-2h"
                    else:
                        sub = "weapon-1h"
                    weap.append(_default_entry(card_slug, "equipment", sub))
                elif is_equipment or armor_slot:
                    equip.append(_default_entry(card_slug, "equipment", armor_slot))
                else:
                    deck.append(_default_entry(card_slug, "deck"))

            obj.hero_cards[hero_slug] = deck
            obj.hero_equipment[hero_slug] = equip
            obj.hero_weapons[hero_slug] = weap

        return obj

    def get_candidate_slugs(self, hero_slug: str) -> tuple[list[str], list[str], list[str]]:
        """Return (equipment_slugs, weapon_slugs, deck_card_slugs) available for this hero."""
        equip = [c["slug"] for c in self.hero_equipment.get(hero_slug, [])]
        weapons = [c["slug"] for c in self.hero_weapons.get(hero_slug, [])]
        deck = [c["slug"] for c in self.hero_cards.get(hero_slug, [])]
        return equip, weapons, deck

    def get_card_frequencies(self, hero_slug: str) -> dict[str, float]:
        """Return slug -> frequency for all cards of this hero."""
        freqs = {}
        for c in self.hero_equipment.get(hero_slug, []):
            freqs[c["slug"]] = c["frequency"]
        for c in self.hero_weapons.get(hero_slug, []):
            freqs[c["slug"]] = c["frequency"]
        for c in self.hero_cards.get(hero_slug, []):
            freqs[c["slug"]] = c["frequency"]
        return freqs

    def validate_pool(self, pool: "CardPool") -> list[str]:
        """Check every card in a pool for FAB class/talent legality.

        Returns a list of violation strings (empty = legal).
        Uses the slug_index loaded at construction time.
        """
        hero_entry = self._slug_idx.get(pool.hero_slug) or self._slug_idx.get(
            pool.hero_slug.replace("-", "_")
        )
        hero_types: list[str] = (hero_entry or {}).get("types", [])

        # Convert pool slugs to card dicts expected by validate_deck_legality
        deck_cards = [{"card_slug": s} for s in pool.deck_slugs]
        equipment = [{"card_slug": s} for s in pool.equipment_slugs + pool.weapon_slugs]
        return validate_deck_legality(deck_cards, equipment, hero_types, self._slug_idx)


# ---------------------------------------------------------------------------
# Evolutionary pool search (Stage 1)
# ---------------------------------------------------------------------------
def select_weapons(
    weapon_cards: list[dict],
    offhand_candidates: list[dict],
    quiver_candidates: list[dict],
    rng: random.Random,
) -> tuple[list[str], list[str]]:
    """Select weapons and optional secondary (off-hand / quiver).

    Args:
        weapon_cards: list of card dicts with 'slug' and 'equipment_subtype'
        offhand_candidates: list of card dicts with equipment_subtype=='off-hand'
        quiver_candidates: list of card dicts with equipment_subtype=='quiver'
        rng: Random instance

    Returns:
        (weapon_slugs, secondary_slugs) where secondary is [] or [one slug]
    """
    if not weapon_cards:
        return [], []

    weapons_1h = [w for w in weapon_cards if w["equipment_subtype"] in ("weapon-1h",)]
    weapons_2h = [w for w in weapon_cards if w["equipment_subtype"] in ("weapon-2h",)]
    weapons_bow = [w for w in weapon_cards if w["equipment_subtype"] == "weapon-bow"]
    weapons_other = [w for w in weapon_cards if w["equipment_subtype"] not in
                     ("weapon-1h", "weapon-2h", "weapon-bow")]

    # Choose a weapon type randomly, weighted by pool size
    options: list[tuple[str, list[dict]]] = []
    if weapons_1h:
        options.append(("1h", weapons_1h))
    if weapons_2h:
        options.append(("2h", weapons_2h))
    if weapons_bow:
        options.append(("bow", weapons_bow))
    if weapons_other:
        options.append(("other", weapons_other))

    if not options:
        return [], []

    wtype, pool = rng.choice(options)
    chosen = rng.choice(pool)
    weapon_slugs = [chosen["slug"]]

    secondary: list[str] = []
    if wtype == "1h" and offhand_candidates:
        oh = rng.choice(offhand_candidates)
        secondary = [oh["slug"]]
    elif wtype == "bow" and quiver_candidates:
        q = rng.choice(quiver_candidates)
        secondary = [q["slug"]]

    return weapon_slugs, secondary

def _random_pool(
    hero_slug: str,
    card_db: HeroCardDB,
    rng: random.Random,
) -> CardPool:
    """Generate a random legal 80-card pool with random flex_depth."""
    equip_cards = card_db.hero_equipment.get(hero_slug, [])
    weapon_cards = card_db.hero_weapons.get(hero_slug, [])
    deck_candidates = [c["slug"] for c in card_db.hero_cards.get(hero_slug, [])]

    # Pick one armor piece per slot randomly
    by_slot: dict[str, list[dict]] = {}
    for c in equip_cards:
        by_slot.setdefault(c["equipment_subtype"], []).append(c)

    equipment: list[str] = []
    for slot in ("head", "chest", "arms", "legs"):
        pool = by_slot.get(slot, [])
        if pool:
            equipment.append(rng.choice(pool)["slug"])

    # Weapon + secondary (off-hand or quiver)
    offhand = by_slot.get("off-hand", [])
    quivers = by_slot.get("quiver", [])
    weapon_slugs, secondary = select_weapons(weapon_cards, offhand, quivers, rng)

    target_deck = POOL_SIZE - len(equipment) - len(weapon_slugs) - len(secondary)
    deck_slugs: list[str] = []

    if deck_candidates:
        shuffled = list(deck_candidates)
        rng.shuffle(shuffled)
        for slug in shuffled:
            if len(deck_slugs) >= target_deck:
                break
            copies = rng.randint(1, MAX_COPIES)
            copies = min(copies, target_deck - len(deck_slugs))
            deck_slugs.extend([slug] * copies)

    flex_depth = rng.randint(0, MAX_FLEX_DEPTH)
    # secondary (off-hand/quiver) goes into equipment_slugs
    return CardPool(hero_slug, equipment + secondary, weapon_slugs, deck_slugs[:target_deck], flex_depth=flex_depth)


def _heuristic_pool(
    hero_slug: str,
    card_db: HeroCardDB,
    rng: random.Random,
    noise: float = 0.1,
    flex_depth: int | None = None,
) -> CardPool:
    """Generate a pool biased toward high-frequency cards (with noise)."""
    equip_cards = card_db.hero_equipment.get(hero_slug, [])
    weapon_cards = card_db.hero_weapons.get(hero_slug, [])
    deck_cards = card_db.hero_cards.get(hero_slug, [])

    # Pick best armor piece per slot (with noise)
    by_slot: dict[str, list[dict]] = {}
    for c in equip_cards:
        by_slot.setdefault(c["equipment_subtype"], []).append(c)

    equipment: list[str] = []
    for slot in ("head", "chest", "arms", "legs"):
        pool = sorted(
            by_slot.get(slot, []),
            key=lambda c: c["frequency"] + rng.gauss(0, noise),
            reverse=True,
        )
        if pool:
            equipment.append(pool[0]["slug"])

    # Weapon + secondary
    offhand = sorted(by_slot.get("off-hand", []), key=lambda c: c["frequency"], reverse=True)
    quivers = sorted(by_slot.get("quiver", []), key=lambda c: c["frequency"], reverse=True)
    weapon_sorted = sorted(weapon_cards, key=lambda c: c["frequency"] + rng.gauss(0, noise), reverse=True)
    weapon_slugs, secondary = select_weapons(weapon_sorted, offhand, quivers, rng)

    target_deck = POOL_SIZE - len(equipment) - len(weapon_slugs) - len(secondary)
    deck_slugs: list[str] = []

    noisy_deck = [(c, c["frequency"] + rng.gauss(0, noise)) for c in deck_cards]
    noisy_deck.sort(key=lambda x: x[1], reverse=True)

    for card, _ in noisy_deck:
        if len(deck_slugs) >= target_deck:
            break
        copies = max(1, min(MAX_COPIES, round(card["avg_copies"])))
        copies = min(copies, target_deck - len(deck_slugs))
        deck_slugs.extend([card["slug"]] * copies)

    if flex_depth is None:
        flex_depth = rng.randint(0, MAX_FLEX_DEPTH)
    # secondary (off-hand/quiver) goes into equipment_slugs
    return CardPool(hero_slug, equipment + secondary, weapon_slugs, deck_slugs[:target_deck], flex_depth=flex_depth)


def _crossover(p1: CardPool, p2: CardPool, rng: random.Random) -> CardPool:
    """Crossover two pools of the same hero, including flex_depth."""
    # Equipment (armor + secondary): inherit from one parent whole to preserve
    # slot integrity — no risk of duplicate slots or lost off-hand/quiver items.
    # Deck card crossover already provides sufficient genetic diversity.
    equipment = list(rng.choice([p1.equipment_slugs, p2.equipment_slugs]))

    # Weapons: inherit from one parent unchanged
    weapons = list(rng.choice([p1.weapon_slugs, p2.weapon_slugs]))

    target_deck = POOL_SIZE - len(equipment) - len(weapons)

    # Count copies in each parent
    p1_counts: dict[str, int] = {}
    for s in p1.deck_slugs:
        p1_counts[s] = p1_counts.get(s, 0) + 1
    p2_counts: dict[str, int] = {}
    for s in p2.deck_slugs:
        p2_counts[s] = p2_counts.get(s, 0) + 1

    # For each unique card, pick copy count from one parent randomly
    all_slugs = list(set(list(p1_counts.keys()) + list(p2_counts.keys())))
    rng.shuffle(all_slugs)

    deck_slugs: list[str] = []
    for slug in all_slugs:
        if len(deck_slugs) >= target_deck:
            break
        c1 = p1_counts.get(slug, 0)
        c2 = p2_counts.get(slug, 0)
        copies = rng.choice([c1, c2]) if c1 and c2 else max(c1, c2)
        copies = min(copies, MAX_COPIES, target_deck - len(deck_slugs))
        if copies > 0:
            deck_slugs.extend([slug] * copies)

    # Pad if the union of parent cards is smaller than target (rare edge case)
    if len(deck_slugs) < target_deck and all_slugs:
        child_counts: dict[str, int] = {}
        for s in deck_slugs:
            child_counts[s] = child_counts.get(s, 0) + 1
        for slug in all_slugs:
            if len(deck_slugs) >= target_deck:
                break
            if child_counts.get(slug, 0) < MAX_COPIES:
                deck_slugs.append(slug)
                child_counts[slug] = child_counts.get(slug, 0) + 1

    # Inherit flex_depth from one parent (with small perturbation)
    flex_depth = rng.choice([p1.flex_depth, p2.flex_depth])
    flex_depth += rng.randint(-2, 2)
    flex_depth = max(0, min(MAX_FLEX_DEPTH, flex_depth))

    return CardPool(p1.hero_slug, equipment, weapons, deck_slugs[:target_deck], flex_depth=flex_depth)


def _mutate(
    pool: CardPool,
    card_db: HeroCardDB,
    rng: random.Random,
    n_swaps: int = 5,
) -> CardPool:
    """Mutate a pool by swapping cards and optionally adjusting flex_depth."""
    pool = CardPool(
        pool.hero_slug,
        list(pool.equipment_slugs),
        list(pool.weapon_slugs),
        list(pool.deck_slugs),
        flex_depth=pool.flex_depth,
    )

    _, _, all_deck_candidates = card_db.get_candidate_slugs(pool.hero_slug)
    used = set(pool.deck_slugs)
    unused = [s for s in all_deck_candidates if s not in used]

    for _ in range(n_swaps):
        if not pool.deck_slugs or not unused:
            break

        # 70% swap a card, 30% change copy count of existing card
        if rng.random() < 0.7:
            idx = rng.randint(0, len(pool.deck_slugs) - 1)
            removed_slug = pool.deck_slugs.pop(idx)
            new_card = rng.choice(unused)
            pool.deck_slugs.append(new_card)
            unused = [s for s in unused if s != new_card]
            # Re-add the removed slug to unused if it has no remaining copies
            if removed_slug not in pool.deck_slugs and removed_slug not in unused:
                unused.append(removed_slug)
        else:
            # Adjust copy count: pick a card, add or remove a copy
            slug_counts: dict[str, int] = {}
            for s in pool.deck_slugs:
                slug_counts[s] = slug_counts.get(s, 0) + 1

            target_slug = rng.choice(list(slug_counts.keys()))
            current = slug_counts[target_slug]

            if rng.random() < 0.5 and current < MAX_COPIES:
                # Add a copy
                pool.deck_slugs.append(target_slug)
                # Remove a different card to keep pool size constant
                other_slugs = [i for i, s in enumerate(pool.deck_slugs)
                               if s != target_slug]
                if other_slugs:
                    removed_idx = rng.choice(other_slugs)
                    removed_slug = pool.deck_slugs[removed_idx]
                    pool.deck_slugs.pop(removed_idx)
                    if removed_slug not in pool.deck_slugs and removed_slug not in unused:
                        unused.append(removed_slug)
            elif current > 1:
                # Remove a copy
                idx = pool.deck_slugs.index(target_slug)
                pool.deck_slugs.pop(idx)
                # If no copies remain, return to unused pool
                if target_slug not in pool.deck_slugs and target_slug not in unused:
                    unused.append(target_slug)
                # Add a random unused card to keep pool size constant
                if unused:
                    new_card = rng.choice(unused)
                    pool.deck_slugs.append(new_card)
                    unused = [s for s in unused if s != new_card]

    # Mutate flex_depth occasionally (30% chance)
    if rng.random() < 0.3:
        pool.flex_depth += rng.randint(-3, 3)
        pool.flex_depth = max(0, min(MAX_FLEX_DEPTH, pool.flex_depth))

    return pool


# ---------------------------------------------------------------------------
# Matchup deck selection (Stage 2) — archetype-aware
# ---------------------------------------------------------------------------

def select_match_deck(
    pool: CardPool,
    opp_hero_slug: str,
    model: nn.Module,
    vocab: CardVocab,
    device: torch.device,
    card_db: HeroCardDB | None = None,
    n_candidates: int = 50,
    seed: int = random.randint(0, 1_000_000),
) -> MatchDeck:
    """Select the best ~60 deck cards from the pool for a specific matchup.

    Uses pool.flex_depth to split cards into core (always included) and
    flex (matchup-dependent). Core cards are the highest-frequency cards
    in the pool; flex slots are filled by sampling from remaining pool cards.

    Args:
        pool: The 80-card registered pool.
        opp_hero_slug: The opponent's hero.
        model: Deck evaluator model.
        vocab: Card vocabulary.
        device: Torch device.
        card_db: HeroCardDB for frequency-based core ordering (optional).
        n_candidates: Number of candidate decks to score.
        seed: Random seed.
    """
    rng = random.Random(seed)
    equipment = list(pool.equipment_slugs)

    if len(pool.deck_slugs) <= MIN_DECK:
        # Pool has <= 60 deck cards, no selection needed
        return MatchDeck(pool.hero_slug, equipment, list(pool.weapon_slugs), list(pool.deck_slugs))

    # Count copies of each card in the pool
    slug_counts: dict[str, int] = {}
    for s in pool.deck_slugs:
        slug_counts[s] = slug_counts.get(s, 0) + 1

    # Order cards by quality: use fablazing frequency if available, else copy count
    if card_db is not None:
        freqs = card_db.get_card_frequencies(pool.hero_slug)
        ordered = sorted(slug_counts.keys(),
                         key=lambda s: freqs.get(s, 0.0), reverse=True)
    else:
        ordered = sorted(slug_counts.keys(),
                         key=lambda s: slug_counts[s], reverse=True)

    # Split into core and flex based on flex_depth
    core_size = pool.core_size
    flex_slots = pool.flex_slots

    # Build core: the top cards that are always included
    core_slugs: list[str] = []
    core_card_set: set[str] = set()
    for slug in ordered:
        if len(core_slugs) >= core_size:
            break
        copies = min(slug_counts[slug], core_size - len(core_slugs))
        core_slugs.extend([slug] * copies)
        if copies == slug_counts[slug]:
            core_card_set.add(slug)

    # Flex candidates: all pool deck cards not fully consumed by core
    flex_candidates: list[str] = []
    for slug in ordered:
        if slug in core_card_set:
            continue
        remaining = slug_counts[slug]
        # If partially consumed by core, count remaining
        core_count = core_slugs.count(slug)
        remaining -= core_count
        for _ in range(remaining):
            flex_candidates.append(slug)

    # Deduplicate flex_candidates list (keep all copies)
    # flex_candidates already has the right copies from above

    # Generate candidate decks by sampling different flex combinations
    candidates: list[list[str]] = []

    # Candidate 0: greedy — take top flex cards by frequency order
    greedy_flex = flex_candidates[:flex_slots]
    candidates.append(core_slugs + greedy_flex)

    # Remaining candidates: random samples from flex pool
    for _ in range(n_candidates - 1):
        if len(flex_candidates) <= flex_slots:
            # Not enough flex cards to vary — all candidates are the same
            flex_pick = list(flex_candidates)
        else:
            flex_pick = rng.sample(flex_candidates, flex_slots)
        candidates.append(core_slugs + flex_pick)

    # Ensure all candidates are exactly MIN_DECK
    for i in range(len(candidates)):
        candidates[i] = candidates[i][:MIN_DECK]
        # Pad if short (shouldn't happen with proper pool, but safety)
        while len(candidates[i]) < MIN_DECK and flex_candidates:
            candidates[i].append(rng.choice(flex_candidates))

    # Score all candidates in one batched forward pass
    model.eval()
    max_cards = 80
    opp_id = vocab.hero_id(opp_hero_slug)
    hero_id = vocab.hero_id(pool.hero_slug)

    B = len(candidates)
    all_card_ids = []
    all_counts = []
    all_pad_masks = []

    weapons = list(pool.weapon_slugs)
    for cand in candidates:
        all_slugs = equipment + weapons + cand
        card_ids_c, counts_c = vocab.encode_deck(all_slugs)
        n = min(len(card_ids_c), max_cards)
        card_ids_c = card_ids_c[:n]
        counts_c = counts_c[:n]
        pad_len = max_cards - n
        all_card_ids.append(card_ids_c + [0] * pad_len)
        all_counts.append(counts_c + [0] * pad_len)
        all_pad_masks.append([False] * n + [True] * pad_len)

    with torch.no_grad():
        logits = model(
            torch.tensor([hero_id] * B, dtype=torch.long).to(device),
            torch.tensor(all_card_ids, dtype=torch.long).to(device),
            torch.tensor(all_counts, dtype=torch.float).to(device),
            torch.tensor([opp_id] * B, dtype=torch.long).to(device),
            torch.tensor(all_pad_masks, dtype=torch.bool).to(device),
        )
        scores = torch.sigmoid(logits).squeeze(-1)

    best_idx = scores.argmax().item()
    return MatchDeck(pool.hero_slug, equipment, list(pool.weapon_slugs), candidates[best_idx])


# ---------------------------------------------------------------------------
# Pool scoring — scores THROUGH Stage 2 matchup selection
# ---------------------------------------------------------------------------

def _score_pool(
    pool: CardPool,
    model: nn.Module,
    vocab: CardVocab,
    opp_hero_slugs: list[str],
    device: torch.device,
    card_db: HeroCardDB | None = None,
    n_select_candidates: int = 20,
) -> float:
    """Score a pool by selecting matchup-specific decks per opponent.

    Instead of scoring the raw 80-card pool, this selects the best 60-card
    deck for each opponent via select_match_deck, then averages the scores.
    This gives evolution the gradient to distinguish tight vs wide pools.
    """
    model.eval()
    scores: list[float] = []

    for i, opp in enumerate(opp_hero_slugs):
        match_deck = select_match_deck(
            pool, opp, model, vocab, device,
            card_db=card_db,
            n_candidates=n_select_candidates,
            seed=hash((pool.hero_slug, opp, i)) & 0x7FFFFFFF,
        )
        score = _score_matchup(match_deck, opp, model, vocab, device)
        scores.append(score)

    return sum(scores) / len(scores) if scores else 0.0


# ---------------------------------------------------------------------------
# Evolution
# ---------------------------------------------------------------------------

def evolve_pool(
    hero_slug: str,
    model: nn.Module,
    vocab: CardVocab,
    card_db: HeroCardDB,
    meta_weights: dict[str, float],
    device: torch.device,
    pop_size: int = 100,
    n_generations: int = 50,
    elite_frac: float = 0.2,
    seed: int = random.randint(0, 1_000_000),
) -> CardPool:
    """Evolutionary search for the best 80-card pool for a hero.

    Scores each pool through matchup-specific deck selection (Stage 2)
    against a field of opponents sampled from the meta distribution.
    Evolves both card composition and flex_depth.
    """
    rng = random.Random(seed)

    # Sample opponent field
    opp_heroes = list(meta_weights.keys())
    opp_weights = [meta_weights[h] for h in opp_heroes]
    field_size = min(20, len(opp_heroes))
    opp_field = rng.choices(opp_heroes, weights=opp_weights, k=field_size)

    # Initialize population with diverse flex_depths
    # 1/3 heuristic-tight (flex 0-5), 1/3 heuristic-mid (flex 6-14),
    # 1/3 heuristic-wide (flex 15-20), plus random pools
    population: list[CardPool] = []
    third = pop_size // 3

    for i in range(third):
        # Tight / aggressive
        fd = rng.randint(0, 5)
        pool = _heuristic_pool(hero_slug, card_db, rng,
                               noise=0.1 + i * 0.01, flex_depth=fd)
        population.append(pool)

    for i in range(third):
        # Midrange
        fd = rng.randint(6, 14)
        pool = _heuristic_pool(hero_slug, card_db, rng,
                               noise=0.1 + i * 0.01, flex_depth=fd)
        population.append(pool)

    for i in range(pop_size - 2 * third):
        # Wide / control + random
        if i < (pop_size - 2 * third) // 2:
            fd = rng.randint(15, MAX_FLEX_DEPTH)
            pool = _heuristic_pool(hero_slug, card_db, rng,
                                   noise=0.15 + i * 0.01, flex_depth=fd)
        else:
            pool = _random_pool(hero_slug, card_db, rng)
        population.append(pool)

    n_elite = max(2, int(pop_size * elite_frac))

    # Resample opponent field every N generations for robustness
    resample_every = max(1, n_generations // 5)

    for gen in range(n_generations):
        # Resample opponent field periodically
        if gen > 0 and gen % resample_every == 0:
            opp_field = rng.choices(opp_heroes, weights=opp_weights, k=field_size)

        # Score all pools through Stage 2
        for pool in population:
            pool.fitness = _score_pool(
                pool, model, vocab, opp_field, device,
                card_db=card_db,
                n_select_candidates=15,
            )

        # Niche diversity pressure: bonus for underrepresented flex_depth buckets
        # Buckets: [0-4], [5-9], [10-14], [15-20]
        buckets: dict[int, list[CardPool]] = {}
        for pool in population:
            bucket = min(pool.flex_depth // 5, 3)
            buckets.setdefault(bucket, []).append(pool)

        for bucket_id, bucket_pools in buckets.items():
            if len(bucket_pools) < 3:
                # Underrepresented archetype — small fitness bonus
                for p in bucket_pools:
                    p.fitness += 0.005

        # Sort by fitness
        population.sort(key=lambda p: p.fitness, reverse=True)

        best = population[0]
        mean_fit = sum(p.fitness for p in population) / len(population)

        # Flex depth distribution in current population
        fd_counts = {}
        for p in population:
            b = min(p.flex_depth // 5, 3)
            fd_counts[b] = fd_counts.get(b, 0) + 1
        fd_str = " ".join(f"[{b*5}-{b*5+4 if b<3 else 20}]:{c}"
                          for b, c in sorted(fd_counts.items()))

        print(
            f"  Gen {gen+1:>3}/{n_generations}  "
            f"best={best.fitness:.4f}  mean={mean_fit:.4f}  "
            f"flex={best.flex_depth}  niches: {fd_str}"
        )

        if gen == n_generations - 1:
            break

        # Selection: keep elite
        elite = population[:n_elite]
        next_gen = list(elite)

        # Fill rest with crossover + mutation
        while len(next_gen) < pop_size:
            p1 = rng.choice(elite)
            p2 = rng.choice(elite)
            child = _crossover(p1, p2, rng)
            if rng.random() < 0.8:
                child = _mutate(child, card_db, rng, n_swaps=rng.randint(2, 8))
            next_gen.append(child)

        population = next_gen

    population.sort(key=lambda p: p.fitness, reverse=True)
    return population[0]


def evolve_pool_diverse(
    hero_slug: str,
    model: nn.Module,
    vocab: CardVocab,
    card_db: HeroCardDB,
    meta_weights: dict[str, float],
    device: torch.device,
    pop_size: int = 100,
    n_generations: int = 50,
    elite_frac: float = 0.2,
    seed: int = random.randint(0, 1_000_000),
    min_fitness_gap: float = 0.03,
    min_jaccard: float = 0.10,
) -> list[CardPool]:
    """Evolutionary search returning a Pareto front of diverse pools.

    Runs the standard evolution, then extracts the best pool from each
    occupied flex_depth bucket. Pools whose fitness is more than
    min_fitness_gap below the best are dropped. Pools with Jaccard
    distance < min_jaccard from a better pool are collapsed.

    Returns 1-4 pools sorted by fitness (best first).
    """
    rng = random.Random(seed)

    # Run full evolution to get the scored population
    opp_heroes = list(meta_weights.keys())
    opp_weights = [meta_weights[h] for h in opp_heroes]
    field_size = min(20, len(opp_heroes))
    opp_field = rng.choices(opp_heroes, weights=opp_weights, k=field_size)

    # Initialize diverse population (same as evolve_pool)
    population: list[CardPool] = []
    third = pop_size // 3

    for i in range(third):
        fd = rng.randint(0, 5)
        population.append(_heuristic_pool(hero_slug, card_db, rng,
                                          noise=0.1 + i * 0.01, flex_depth=fd))
    for i in range(third):
        fd = rng.randint(6, 14)
        population.append(_heuristic_pool(hero_slug, card_db, rng,
                                          noise=0.1 + i * 0.01, flex_depth=fd))
    for i in range(pop_size - 2 * third):
        if i < (pop_size - 2 * third) // 2:
            fd = rng.randint(15, MAX_FLEX_DEPTH)
            population.append(_heuristic_pool(hero_slug, card_db, rng,
                                              noise=0.15 + i * 0.01, flex_depth=fd))
        else:
            population.append(_random_pool(hero_slug, card_db, rng))

    n_elite = max(2, int(pop_size * elite_frac))
    resample_every = max(1, n_generations // 5)

    for gen in range(n_generations):
        if gen > 0 and gen % resample_every == 0:
            opp_field = rng.choices(opp_heroes, weights=opp_weights, k=field_size)

        for pool in population:
            pool.fitness = _score_pool(
                pool, model, vocab, opp_field, device,
                card_db=card_db, n_select_candidates=15,
            )

        # Niche diversity pressure
        buckets: dict[int, list[CardPool]] = {}
        for pool in population:
            bucket = min(pool.flex_depth // 5, 3)
            buckets.setdefault(bucket, []).append(pool)
        for bucket_pools in buckets.values():
            if len(bucket_pools) < 3:
                for p in bucket_pools:
                    p.fitness += 0.005

        population.sort(key=lambda p: p.fitness, reverse=True)

        best = population[0]
        mean_fit = sum(p.fitness for p in population) / len(population)
        fd_counts: dict[int, int] = {}
        for p in population:
            b = min(p.flex_depth // 5, 3)
            fd_counts[b] = fd_counts.get(b, 0) + 1
        fd_str = " ".join(f"[{b*5}-{b*5+4 if b<3 else 20}]:{c}"
                          for b, c in sorted(fd_counts.items()))
        print(
            f"  Gen {gen+1:>3}/{n_generations}  "
            f"best={best.fitness:.4f}  mean={mean_fit:.4f}  "
            f"flex={best.flex_depth}  niches: {fd_str}"
        )

        if gen == n_generations - 1:
            break

        elite = population[:n_elite]
        next_gen = list(elite)
        while len(next_gen) < pop_size:
            p1 = rng.choice(elite)
            p2 = rng.choice(elite)
            child = _crossover(p1, p2, rng)
            if rng.random() < 0.8:
                child = _mutate(child, card_db, rng, n_swaps=rng.randint(2, 8))
            next_gen.append(child)
        population = next_gen

    population.sort(key=lambda p: p.fitness, reverse=True)
    best_fitness = population[0].fitness

    # Extract best pool from each flex_depth bucket
    bucket_best: dict[int, CardPool] = {}
    for pool in population:
        bucket = min(pool.flex_depth // 5, 3)
        if bucket not in bucket_best:
            bucket_best[bucket] = pool

    # Filter: drop pools too far below the best
    candidates = [p for p in bucket_best.values()
                  if best_fitness - p.fitness <= min_fitness_gap]

    # Sort by fitness
    candidates.sort(key=lambda p: p.fitness, reverse=True)

    # Deduplicate: drop pools too similar (low Jaccard distance) to a better one
    diverse: list[CardPool] = []
    for pool in candidates:
        too_similar = False
        for existing in diverse:
            if _jaccard_distance(pool, existing) < min_jaccard:
                too_similar = True
                break
        if not too_similar:
            diverse.append(pool)

    if not diverse:
        diverse = [population[0]]

    print(f"  Pareto front: {len(diverse)} pool(s) "
          f"[{', '.join(f'flex={p.flex_depth}({_archetype_label(p)})' for p in diverse)}]")

    return diverse


# ---------------------------------------------------------------------------
# Pool selection for tournament matches
# ---------------------------------------------------------------------------

def _select_pool_for_match(
    pools: list[CardPool],
    opp_hero_slug: str,
    model: nn.Module,
    vocab: CardVocab,
    device: torch.device,
    card_db: HeroCardDB | None = None,
    seed: int = random.randint(0, 1_000_000),
) -> tuple[CardPool, MatchDeck]:
    """Pick the best pool + deck for a specific matchup.

    Runs select_match_deck for each pool, returns the (pool, deck) pair
    with the highest matchup score.
    """
    if len(pools) == 1:
        deck = select_match_deck(
            pools[0], opp_hero_slug, model, vocab, device,
            card_db=card_db, seed=seed,
        )
        return pools[0], deck

    best_pool = pools[0]
    best_deck = select_match_deck(
        pools[0], opp_hero_slug, model, vocab, device,
        card_db=card_db, seed=seed,
    )
    best_score = _score_matchup(best_deck, opp_hero_slug, model, vocab, device)

    for pool in pools[1:]:
        deck = select_match_deck(
            pool, opp_hero_slug, model, vocab, device,
            card_db=card_db, seed=seed,
        )
        score = _score_matchup(deck, opp_hero_slug, model, vocab, device)
        if score > best_score:
            best_score = score
            best_pool = pool
            best_deck = deck

    return best_pool, best_deck


def _select_locked_pool(
    pools: list[CardPool],
    model: nn.Module,
    vocab: CardVocab,
    meta_weights: dict[str, float],
    device: torch.device,
    card_db: HeroCardDB | None = None,
    seed: int = random.randint(0, 1_000_000),
) -> CardPool:
    """Pick the single best pool to lock in for an entire tournament.

    Scores each pool against the full meta-weighted opponent field
    and returns the one with the highest average expected win rate.
    """
    if len(pools) == 1:
        return pools[0]

    rng = random.Random(seed)
    opp_heroes = list(meta_weights.keys())
    opp_weights = [meta_weights[h] for h in opp_heroes]
    field = rng.choices(opp_heroes, weights=opp_weights, k=20)

    best_pool = pools[0]
    best_score = _score_pool(pools[0], model, vocab, field, device,
                             card_db=card_db, n_select_candidates=15)

    for pool in pools[1:]:
        score = _score_pool(pool, model, vocab, field, device,
                            card_db=card_db, n_select_candidates=15)
        if score > best_score:
            best_score = score
            best_pool = pool

    return best_pool


# ---------------------------------------------------------------------------
# Tournament simulation
# ---------------------------------------------------------------------------

@dataclass
class TournamentPlayer:
    """A player in the simulated tournament."""
    player_id: int
    hero_slug: str
    pools: list[CardPool]             # Pareto front of diverse pools
    active_pool: CardPool | None = None  # locked pool (if strategy=LOCKED)
    wins: int = 0
    losses: int = 0
    points: float = 0.0
    opponents_faced: list[int] = field(default_factory=list)

    @property
    def pool(self) -> CardPool:
        """Primary pool (best fitness or locked selection)."""
        return self.active_pool or self.pools[0]


def simulate_tournament(
    model: nn.Module,
    vocab: CardVocab,
    card_db: HeroCardDB,
    meta_weights: dict[str, float],
    device: torch.device,
    n_players: int = 256,
    n_rounds: int = 5,
    pool_pop_size: int = 50,
    pool_generations: int = 20,
    seed: int = random.randint(0, 1_000_000),
    pool_strategy: PoolStrategy = PoolStrategy.PER_ROUND,
) -> list[TournamentPlayer]:
    """Simulate a Swiss-style tournament with multi-pool support.

    1. Sample n_players heroes from meta distribution
    2. Each player builds a Pareto front of diverse pools via evolutionary search
    3. If LOCKED strategy: each player picks one pool at registration
    4. Swiss pairings for n_rounds
    5. If PER_ROUND strategy: pick best pool+deck per matchup each round

    Returns players sorted by final standing.
    """
    rng = random.Random(seed)

    hero_slugs = list(meta_weights.keys())
    hero_weights = [meta_weights[h] for h in hero_slugs]

    # Sample hero distribution
    sampled_heroes = rng.choices(hero_slugs, weights=hero_weights, k=n_players)

    print(f"\nTournament: {n_players} players, {n_rounds} rounds, strategy={pool_strategy.value}")
    print(f"Hero distribution:")
    hero_counts: dict[str, int] = {}
    for h in sampled_heroes:
        hero_counts[h] = hero_counts.get(h, 0) + 1
    for h, c in sorted(hero_counts.items(), key=lambda x: -x[1])[:10]:
        pct = c / n_players * 100
        print(f"  {h:<45} {c:>3} ({pct:.1f}%)")
    if len(hero_counts) > 10:
        print(f"  ... and {len(hero_counts) - 10} more heroes")

    # Build pools (Pareto front per player)
    print(f"\nBuilding pools ({pool_pop_size} pop, {pool_generations} gens)...")
    players: list[TournamentPlayer] = []

    for i, hero in enumerate(sampled_heroes):
        print(f"  Player {i+1:>3}/{n_players}: {hero}")
        pools = evolve_pool_diverse(
            hero, model, vocab, card_db, meta_weights, device,
            pop_size=pool_pop_size,
            n_generations=pool_generations,
            seed=seed + i,
        )

        player = TournamentPlayer(
            player_id=i, hero_slug=hero, pools=pools,
        )

        # For LOCKED strategy, select one pool at registration
        if pool_strategy == PoolStrategy.LOCKED:
            player.active_pool = _select_locked_pool(
                pools, model, vocab, meta_weights, device,
                card_db=card_db, seed=seed + i,
            )

        players.append(player)

    # Swiss rounds
    for round_num in range(1, n_rounds + 1):
        print(f"\n=== Round {round_num}/{n_rounds} ===")

        # Sort by points for Swiss pairing
        players.sort(key=lambda p: (-p.points, -p.wins))

        # Pair players (adjacent in standings, skip already-faced)
        paired: set[int] = set()
        matches: list[tuple[int, int]] = []

        for i in range(len(players)):
            if i in paired:
                continue
            for j in range(i + 1, len(players)):
                if j in paired:
                    continue
                pi = players[i]
                pj = players[j]
                if pj.player_id not in pi.opponents_faced:
                    matches.append((i, j))
                    paired.add(i)
                    paired.add(j)
                    break

        print(f"  {len(matches)} matches")

        for idx_a, idx_b in matches:
            pa = players[idx_a]
            pb = players[idx_b]

            match_seed_a = seed + round_num * 1000 + pa.player_id
            match_seed_b = seed + round_num * 1000 + pb.player_id

            if pool_strategy == PoolStrategy.PER_ROUND:
                # Pick best pool + deck for each player's specific matchup
                _, deck_a = _select_pool_for_match(
                    pa.pools, pb.hero_slug, model, vocab, device,
                    card_db=card_db, seed=match_seed_a,
                )
                _, deck_b = _select_pool_for_match(
                    pb.pools, pa.hero_slug, model, vocab, device,
                    card_db=card_db, seed=match_seed_b,
                )
            else:
                # LOCKED: use the pre-selected active_pool
                deck_a = select_match_deck(
                    pa.pool, pb.hero_slug, model, vocab, device,
                    card_db=card_db, seed=match_seed_a,
                )
                deck_b = select_match_deck(
                    pb.pool, pa.hero_slug, model, vocab, device,
                    card_db=card_db, seed=match_seed_b,
                )

            # Score the matchup
            score_a = _score_matchup(deck_a, pb.hero_slug, model, vocab, device)
            score_b = _score_matchup(deck_b, pa.hero_slug, model, vocab, device)

            # Stochastic outcome
            p_a_wins = score_a / (score_a + score_b + 1e-8)
            if rng.random() < p_a_wins:
                pa.wins += 1
                pa.points += 1.0
                pb.losses += 1
            else:
                pb.wins += 1
                pb.points += 1.0
                pa.losses += 1

            pa.opponents_faced.append(pb.player_id)
            pb.opponents_faced.append(pa.player_id)

    # Final standings
    players.sort(key=lambda p: (-p.points, -p.wins))

    print(f"\n{'Rank':<6} {'Hero':<35} {'Archetype':<12} {'Pools':>5} {'Flex':>4} {'W':>3}-{'L':>3} {'Pts':>5}")
    print("-" * 80)
    for rank, p in enumerate(players[:20], 1):
        label = _archetype_label(p.pool)
        n_pools = len(p.pools)
        print(
            f"{rank:<6} {p.hero_slug:<35} "
            f"{label:<12} {n_pools:>5} {p.pool.flex_depth:>4} "
            f"{p.wins:>3}-{p.losses:>3} {p.points:>5.1f}"
        )

    # Archetype summary
    print(f"\nArchetype distribution (top 20):")
    archetype_counts: dict[str, int] = {}
    for p in players[:20]:
        label = _archetype_label(p.pool)
        archetype_counts[label] = archetype_counts.get(label, 0) + 1
    for label, count in sorted(archetype_counts.items(), key=lambda x: -x[1]):
        print(f"  {label:<15} {count:>3}")

    print(f"\nHero archetypes (top 20):")
    hero_archetypes: dict[str, list[str]] = {}
    for p in players[:20]:
        label = _archetype_label(p.pool)
        hero_archetypes.setdefault(p.hero_slug, []).append(label)
    for hero, labels in sorted(hero_archetypes.items()):
        pool_info = ", ".join(labels)
        print(f"  {hero:<35} {pool_info}")

    return players


def _score_matchup(
    deck: MatchDeck,
    opp_hero_slug: str,
    model: nn.Module,
    vocab: CardVocab,
    device: torch.device,
) -> float:
    """Score a specific deck against a specific opponent."""
    all_slugs = deck.equipment_slugs + deck.weapon_slugs + deck.deck_slugs
    card_ids, counts = vocab.encode_deck(all_slugs)

    max_cards = 80
    n = min(len(card_ids), max_cards)
    card_ids = card_ids[:n]
    counts = counts[:n]
    pad_len = max_cards - n

    with torch.no_grad():
        logit = model(
            torch.tensor([vocab.hero_id(deck.hero_slug)], dtype=torch.long).to(device),
            torch.tensor([card_ids + [0] * pad_len], dtype=torch.long).to(device),
            torch.tensor([counts + [0] * pad_len], dtype=torch.float).to(device),
            torch.tensor([vocab.hero_id(opp_hero_slug)], dtype=torch.long).to(device),
            torch.tensor([[False] * n + [True] * pad_len], dtype=torch.bool).to(device),
        )
        return torch.sigmoid(logit).item()


# ---------------------------------------------------------------------------
# Export evolved pools as deck files
# ---------------------------------------------------------------------------

def _pool_to_deck_text(pool: CardPool, hero_name: str, label: str = "") -> str:
    """Convert a CardPool to FaBrary-format deck text."""
    lines: list[str] = []
    deck_name = f"{hero_name} - Evolved"
    if label:
        deck_name += f" ({label})"

    lines.append(f"Name: {deck_name}")
    lines.append(f"Hero: {hero_name}")
    lines.append("Format: Classic Constructed")
    lines.append("")
    lines.append("Arena cards")
    def _slug_to_name(slug: str) -> str:
        return slug.replace("-", " ").replace("_", " ").title()

    if len(pool.weapon_slugs) > 1 and pool.weapon_slugs[0] == pool.weapon_slugs[1]:
        lines.append(f"2x {_slug_to_name(pool.weapon_slugs[0])}")
    elif pool.weapon_slugs:
        for slug in pool.weapon_slugs:
            lines.append(f"1x {_slug_to_name(slug)}")
    # Weaponless heroes (e.g. Gravy Bones) have no weapon line — that is legal
    for slug in pool.equipment_slugs:
        lines.append(f"1x {_slug_to_name(slug)}")
    lines.append("")
    lines.append("Deck cards")

    # Pool may be larger than MIN_DECK (tournament pool) — take core cards first
    if len(pool.deck_slugs) < MIN_DECK:
        import warnings
        warnings.warn(
            f"Pool for {pool.hero_slug} has only {len(pool.deck_slugs)} deck cards "
            f"(expected >= {MIN_DECK}); output deck will be undersized.",
            stacklevel=2,
        )
    deck_to_write = pool.deck_slugs[:MIN_DECK]
    slug_counts: dict[str, int] = {}
    for s in deck_to_write:
        slug_counts[s] = slug_counts.get(s, 0) + 1

    color_order = {"red": 0, "yellow": 1, "blue": 2}

    def sort_key(item: tuple[str, int]) -> tuple[int, str]:
        slug = item[0]
        parts = slug.rsplit("_", 1)
        if len(parts) == 2 and parts[1] in ("red", "yellow", "blue"):
            c = color_order.get(parts[1], 3)
        else:
            c = 3
        return (c, slug)

    for slug, count in sorted(slug_counts.items(), key=sort_key):
        parts = slug.rsplit("_", 1)
        if len(parts) == 2 and parts[1] in ("red", "yellow", "blue"):
            base_name = parts[0].replace("_", " ").title()
            lines.append(f"{count}x {base_name} ({parts[1]})")
        else: # Non-colored card ie "gorganian_tome" or "burn_bare"
            name = slug.replace("_", " ").title()
            lines.append(f"{count}x {name}")

    lines.append("")
    return "\n".join(lines)


def export_evolved_decks(
    model: nn.Module,
    vocab: CardVocab,
    card_db: HeroCardDB,
    meta_weights: dict[str, float],
    device: torch.device,
    output_dir: Path = Path("decks/generated"),
    pop_size: int = 50,
    n_generations: int = 20,
    seed: int = random.randint(0, 1_000_000),
) -> int:
    """Evolve pools for all heroes and write them as deck files.

    Returns the number of deck files written.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    heroes = sorted(card_db.hero_cards.keys())
    total_files = 0

    print(f"Exporting evolved decks for {len(heroes)} heroes")
    print(f"Output: {output_dir}")
    print(f"Evolution: pop={pop_size}, gens={n_generations}")
    print()

    for hi, hero in enumerate(heroes, 1):
        hero_name = hero.replace("-", " ").title()
        file_base = hero.replace("-", "_")

        print(f"  [{hi:>2}/{len(heroes)}] {hero:<45}", end="", flush=True)
        try:
            pools = evolve_pool_diverse(
                hero, model, vocab, card_db, meta_weights, device,
                pop_size=pop_size, n_generations=n_generations,
                seed=seed + hi,
            )
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

        for pi, pool in enumerate(pools):
            label = _archetype_label(pool)
            if len(pools) == 1:
                filename = f"{file_base}_CC.txt"
                suffix = ""
            else:
                filename = f"{file_base}_CC_{label}.txt"
                suffix = label

            violations = card_db.validate_pool(pool) if card_db else []
            if violations:
                import warnings
                warnings.warn(
                    f"Deck legality violations for {hero} ({label or 'default'}):\n"
                    + "\n".join(f"  {v}" for v in violations),
                    stacklevel=2,
                )
            text = _pool_to_deck_text(pool, hero_name, suffix)
            (output_dir / filename).write_text(text, encoding="utf-8")
            total_files += 1

        labels = ", ".join(
            f"{_archetype_label(p)}({p.fitness:.3f})" for p in pools
        )
        print(f"  {len(pools)} pool(s): {labels}")

    print(f"\nExported {total_files} deck files to {output_dir}")
    return total_files


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Evolutionary deck search & tournament")
    sub = parser.add_subparsers(dest="command")

    # Single hero pool search
    search_p = sub.add_parser("search", help="Search for best pool(s) for a single hero")
    search_p.add_argument("--hero", required=True, help="Hero slug")
    search_p.add_argument("--checkpoint", required=True, type=Path)
    search_p.add_argument("--meta-db", type=Path, default=Path("data/fablazing_meta.db"))
    search_p.add_argument("--pop-size", type=int, default=100)
    search_p.add_argument("--generations", type=int, default=50)
    search_p.add_argument("--seed", type=int, default=random.randint(0, 1_000_000))

    # Export evolved pools as deck files
    export_p = sub.add_parser("export", help="Evolve pools for all heroes and export as deck files")
    export_p.add_argument("--checkpoint", required=True, type=Path)
    export_p.add_argument("--meta-db", type=Path, default=Path("data/fablazing_meta.db"))
    export_p.add_argument("--output-dir", type=Path, default=Path("decks/generated"))
    export_p.add_argument("--pop-size", type=int, default=50)
    export_p.add_argument("--generations", type=int, default=20)
    export_p.add_argument("--seed", type=int, default=random.randint(0, 1_000_000))

    # Tournament simulation
    tourney_p = sub.add_parser("tournament", help="Simulate a Swiss tournament")
    tourney_p.add_argument("--checkpoint", required=True, type=Path)
    tourney_p.add_argument("--meta-db", type=Path, default=Path("data/fablazing_meta.db"))
    tourney_p.add_argument("--players", type=int, default=256)
    tourney_p.add_argument("--rounds", type=int, default=5)
    tourney_p.add_argument("--pool-pop", type=int, default=50)
    tourney_p.add_argument("--pool-gens", type=int, default=20)
    tourney_p.add_argument("--seed", type=int, default=random.randint(0, 1_000_000))
    tourney_p.add_argument("--strategy", default="per_round",
                           choices=["per_round", "locked"],
                           help="Pool selection strategy (default: per_round)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Load model
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    ckpt = load_checkpoint(args.checkpoint)
    vocab = CardVocab.from_state_dict(ckpt["vocab"])
    model = build_evaluator(vocab, ckpt.get("model_type", "deepsets"))
    model.load_state_dict(ckpt["model_state_dict"])
    model = model.to(device)
    model.eval()

    card_db = HeroCardDB(args.meta_db)
    meta_weights = load_meta_weights(args.meta_db)

    if args.command == "search":
        print(f"Searching for best pool(s): {args.hero}")
        pools = evolve_pool_diverse(
            args.hero, model, vocab, card_db, meta_weights, device,
            pop_size=args.pop_size,
            n_generations=args.generations,
            seed=args.seed,
        )
        for pi, pool in enumerate(pools):
            label = _archetype_label(pool)
            print(f"\n--- Pool {pi+1}/{len(pools)} "
                  f"(fitness={pool.fitness:.4f}, flex_depth={pool.flex_depth}, "
                  f"archetype={label}) ---")
            print(f"  Core size: {pool.core_size} cards (always played)")
            print(f"  Flex slots: {pool.flex_slots} cards (matchup-dependent)")
            print(f"\n  Equipment ({len(pool.equipment_slugs)}):")
            for s in pool.equipment_slugs:
                print(f"    {s}")
            print(f"\n  Deck cards ({len(pool.deck_slugs)}):")
            slug_counts: dict[str, int] = {}
            for s in pool.deck_slugs:
                slug_counts[s] = slug_counts.get(s, 0) + 1
            for slug, count in sorted(slug_counts.items()):
                print(f"    {count}x {slug}")

    elif args.command == "export":
        export_evolved_decks(
            model, vocab, card_db, meta_weights, device,
            output_dir=args.output_dir,
            pop_size=args.pop_size,
            n_generations=args.generations,
            seed=args.seed,
        )

    elif args.command == "tournament":
        strategy = PoolStrategy(args.strategy)
        simulate_tournament(
            model, vocab, card_db, meta_weights, device,
            n_players=args.players,
            n_rounds=args.rounds,
            pool_pop_size=args.pool_pop,
            pool_generations=args.pool_gens,
            seed=args.seed,
            pool_strategy=strategy,
        )


if __name__ == "__main__":
    main()
