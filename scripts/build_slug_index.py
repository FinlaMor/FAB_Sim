"""
build_slug_index.py — Parse card_data/index.ts and upsert into slug_index.json + slug_index.msgpack.

New cards are added; existing cards are updated with fresh data from index.ts.
Cards in the slug_index that are NOT in index.ts are left untouched.

Field names match index.ts exactly (e.g. 'life', 'intellect', not 'health'/'intelligence').

Usage:
    python scripts/build_slug_index.py [--dry-run]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    import msgpack
except ImportError:
    msgpack = None
    print("Warning: msgpack not installed — slug_index.msgpack will not be updated.")

ROOT = Path(__file__).resolve().parent.parent
INDEX_TS = ROOT / "card_data" / "index.ts"
SLUG_JSON = ROOT / "card_data" / "slug_index.json"
SLUG_MSGPACK = ROOT / "card_data" / "slug_index.msgpack"

DRY_RUN = "--dry-run" in sys.argv


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slug(card_identifier: str) -> str:
    """'10000-year-reunion-red' → '10000_year_reunion_red'"""
    return card_identifier.replace("-", "_")


def _pitch_to_color(pitch) -> str:
    return {1: "Red", 2: "Yellow", 3: "Blue"}.get(pitch, "")


def _strip_enum(value: str) -> str:
    """'Keyword.Ward' → 'Ward', 'Type.Action' → 'Action'"""
    return value.split(".")[-1]


def _parse_array(raw: str) -> list[str]:
    """Parse '[Keyword.Ward, Keyword.GoAgain]' → ['Ward', 'GoAgain']"""
    inner = raw.strip().lstrip("[").rstrip("]")
    if not inner.strip():
        return []
    return [_strip_enum(x.strip()) for x in inner.split(",") if x.strip()]


def _parse_optional_int(s: str | None):
    if s is None:
        return None
    s = s.strip()
    if s in ("null", "undefined", ""):
        return None
    try:
        return int(s)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Card block extraction
# ---------------------------------------------------------------------------

_CARD_ID_RE = re.compile(r'cardIdentifier:\s*"([^"]+)"')


def _extract_card_blocks(source: str) -> list[tuple[str, str]]:
    """Return list of (card_identifier, block_text) pairs."""
    matches = list(_CARD_ID_RE.finditer(source))
    results = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(source)
        results.append((m.group(1), source[start:end]))
    return results


# ---------------------------------------------------------------------------
# Field parsers  (all use negative lookbehind to avoid e.g. 'subtypes' → 'types')
# ---------------------------------------------------------------------------

def _str(block: str, field: str) -> str | None:
    m = re.search(rf'(?<!\w){field}:\s*"([^"]*)"', block)
    return m.group(1) if m else None


def _int_or_null(block: str, field: str):
    m = re.search(rf'(?<!\w){field}:\s*(-?\d+)', block)
    return int(m.group(1)) if m else None


def _array(block: str, field: str) -> list[str]:
    m = re.search(rf'(?<!\w){field}:\s*(\[[^\]]*\])', block)
    return _parse_array(m.group(1)) if m else []


def _str_array(block: str, field: str) -> list[str]:
    """Parse a quoted-string array e.g. setIdentifiers: ["ARK001","DYN114"]"""
    m = re.search(rf'(?<!\w){field}:\s*(\[[^\]]*\])', block)
    if not m:
        return []
    inner = m.group(1).strip().lstrip("[").rstrip("]")
    return [x.strip().strip('"').strip("'") for x in inner.split(",") if x.strip().strip('"').strip("'")]


def _template_literal(block: str, field: str) -> str | None:
    m = re.search(rf'(?<!\w){field}:\s*`(.*?)`', block, re.DOTALL)
    return m.group(1).strip() if m else None


def _str_or_template(block: str, field: str) -> str | None:
    return _template_literal(block, field) or _str(block, field)


def _bool(block: str, field: str) -> bool | None:
    m = re.search(rf'(?<!\w){field}:\s*(true|false)', block)
    if not m:
        return None
    return m.group(1) == "true"


def _special_str(block: str, field: str) -> str | None:
    """For fields like specialCost: "XX", specialPower: "*" """
    return _str(block, field)


def _enum_value(block: str, field: str) -> str | None:
    """Single enum value e.g. hero: Hero.Arakni → 'Arakni'"""
    m = re.search(rf'(?<!\w){field}:\s*\w+\.(\w+)', block)
    return m.group(1) if m else None


def _opposite_side_ids(block: str) -> list[str]:
    """oppositeSideCardIdentifiers: ["a", "b"] — quoted array."""
    m = re.search(r'oppositeSideCardIdentifiers:\s*(\[[^\]]*\])', block)
    if not m:
        # single backtick form
        m2 = re.search(r'oppositeSideCardIdentifier:\s*`([^`]+)`', block)
        return [m2.group(1)] if m2 else []
    inner = m.group(1).strip().lstrip("[").rstrip("]")
    return [x.strip().strip('"') for x in inner.split(",") if x.strip().strip('"')]


# ---------------------------------------------------------------------------
# Parse a single card block into slug_index record
# ---------------------------------------------------------------------------

def _strip_printings(block: str) -> str:
    """Remove the printings array so nested fields don't bleed into card-level parsing."""
    m = re.search(r'(?<!\w)printings:\s*\[', block)
    if not m:
        return block
    # Walk forward to find the matching closing bracket
    depth = 0
    i = m.end() - 1  # position of '['
    while i < len(block):
        if block[i] == '[':
            depth += 1
        elif block[i] == ']':
            depth -= 1
            if depth == 0:
                return block[:m.start()] + block[i + 1:]
        i += 1
    return block


def parse_card(card_identifier: str, block: str) -> dict:
    block = _strip_printings(block)
    pitch = _int_or_null(block, "pitch")

    return {
        # Identity
        "name":                     _str(block, "name") or card_identifier,
        "shortName":                _str(block, "shortName"),
        "typeText":                 _str(block, "typeText"),
        # Stats
        "color":                    _pitch_to_color(pitch),
        "pitch":                    pitch,
        "cost":                     _int_or_null(block, "cost"),
        "specialCost":              _special_str(block, "specialCost"),
        "power":                    _int_or_null(block, "power"),
        "specialPower":             _special_str(block, "specialPower"),
        "defense":                  _int_or_null(block, "defense"),
        "specialDefense":           _special_str(block, "specialDefense"),
        "life":                     _int_or_null(block, "life"),
        "specialLife":              _special_str(block, "specialLife"),
        "intellect":                _int_or_null(block, "intellect"),
        "arcane":                   _int_or_null(block, "arcane"),
        "specialArcane":            _special_str(block, "specialArcane"),
        # Classification
        "types":                    _array(block, "types"),
        "subtypes":                 _array(block, "subtypes"),
        "classes":                  _array(block, "classes"),
        "talents":                  _array(block, "talents"),
        "keywords":                 _array(block, "keywords"),
        "shorthands":               _array(block, "shorthands"),
        "meta":                     _array(block, "meta"),
        "metatypes":                _array(block, "metatypes"),
        "traits":                   _array(block, "traits"),
        # Mechanics
        "fusions":                  _array(block, "fusions"),
        "bonds":                    _array(block, "bonds"),
        "flows":                    _array(block, "flows"),
        # Hero linkage
        "hero":                     _enum_value(block, "hero"),
        "specializations":          _array(block, "specializations"),
        "legalHeroes":              _array(block, "legalHeroes"),
        # Format legality
        "legalFormats":             _array(block, "legalFormats"),
        "bannedFormats":            _array(block, "bannedFormats"),
        "restrictedFormats":        _array(block, "restrictedFormats"),
        # Card text
        "functionalText":           _str_or_template(block, "functionalText"),
        # Flags
        "young":                    _bool(block, "young"),
        "isCardBack":               _bool(block, "isCardBack"),
        "isExpansionSlot":          _bool(block, "isExpansionSlot"),
        "playedHorizontally":       _bool(block, "playedHorizontally"),
        # Double-faced
        "oppositeSideCardIdentifiers": _opposite_side_ids(block),
        # Print metadata
        "defaultImage":             _str(block, "defaultImage"),
        "specialImage":             _str(block, "specialImage"),
        "rarity":                   _enum_value(block, "rarity"),
        "rarities":                 _array(block, "rarities"),
        "setIdentifiers":           _str_array(block, "setIdentifiers"),
        "sets":                     _array(block, "sets"),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    source = INDEX_TS.read_text(encoding="utf-8")
    blocks = _extract_card_blocks(source)
    print(f"Parsed {len(blocks)} cards from index.ts")

    # Load existing slug_index
    if SLUG_JSON.exists():
        raw = json.loads(SLUG_JSON.read_text(encoding="utf-8"))
        existing = raw.get("by_slug", raw)
    else:
        existing = {}

    added = updated = 0
    for card_id, block in blocks:
        slug = _slug(card_id)
        record = parse_card(card_id, block)
        if slug not in existing:
            added += 1
        else:
            updated += 1
        existing[slug] = record

    print(f"  {added} new, {updated} updated  (total {len(existing)})")

    if DRY_RUN:
        print("Dry run — no files written.")
        for card_id, _ in blocks[:3]:
            slug = _slug(card_id)
            print(f"\n  {slug}:", json.dumps(existing[slug], indent=4, ensure_ascii=False)[:600])
        return

    out = {"by_slug": existing}

    SLUG_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {SLUG_JSON}")

    if msgpack:
        SLUG_MSGPACK.write_bytes(msgpack.packb(out, use_bin_type=True))
        print(f"Wrote {SLUG_MSGPACK}")


if __name__ == "__main__":
    main()
