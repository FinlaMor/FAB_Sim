"""
build_slug_index.py — Parse card_data/index.ts and upsert into slug_index.json + slug_index.msgpack.

New cards are added; existing cards are updated with fresh data from index.ts.
Cards in the slug_index that are NOT in index.ts are left untouched.

Field names match index.ts exactly (e.g. 'life', 'intellect', not 'health'/'intelligence').

The card definitions come from the fabrary/cards repo, which publishes two
TypeScript sources in the same format:

    packages/cards/latest-set/index.ts   ~80 KB   the newest set only
    packages/cards/src/index.ts          ~12 MB   every card ever printed

The full catalogue is fetched by default. This script UPSERTS, so parsing
everything refreshes existing cards as well as adding new ones — a stale field
anywhere gets corrected. --latest-set is the cheap alternative when only the
newest set matters; it leaves every other card exactly as it was.

A fetch never overwrites card_data/index.ts. The download is cached beside it
under its own name so the local full copy stays intact and the fetched text can
be inspected after a surprising diff.

Usage:
    python scripts/build_slug_index.py                  # fetch + parse everything
    python scripts/build_slug_index.py --dry-run
    python scripts/build_slug_index.py --latest-set     # newest set only
    python scripts/build_slug_index.py --local          # no download
    python scripts/build_slug_index.py --source path/to/index.ts
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
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


# Upstream card definitions. Same format for both paths, so one parser serves
# each; they differ only in how much of the catalogue they carry.
FABRARY_REPO = "fabrary/cards"
FABRARY_REF = "main"
FABRARY_SOURCES = {
    "latest-set": "packages/cards/latest-set/index.ts",
    "full": "packages/cards/src/index.ts",
}
RAW_URL = "https://raw.githubusercontent.com/{repo}/{ref}/{path}"

# A fetched file lands here rather than on card_data/index.ts, which holds the
# full local catalogue and must survive a latest-set pull.
FETCH_CACHE = {
    "latest-set": ROOT / "card_data" / "latest_set_index.ts",
    "full": ROOT / "card_data" / "full_index.ts",
}

DRY_RUN = "--dry-run" in sys.argv

# Where card implementations live. A refresh that changes one of these cards'
# rules text or stats can silently invalidate its JSON implementation.
CARD_JSON_ROOT = ROOT / "engine" / "card_effects" / "json"

# Fields the engine and card implementations actually read. Everything else
# upstream churns constantly — legalFormats, meta and image ids changed on
# ~4,500 cards in a single refresh — and reporting those would bury the
# handful of changes that matter.
ENGINE_RELEVANT_FIELDS = (
    "functionalText", "typeText", "power", "defense", "life", "intellect",
    "arcane", "cost", "pitch", "types", "subtypes", "classes", "keywords",
)


def implemented_slugs() -> set[str]:
    """Slugs with a DSL implementation under engine/card_effects/json/."""
    if not CARD_JSON_ROOT.exists():
        return set()
    return {
        p.stem for p in CARD_JSON_ROOT.rglob("*.json")
        if not p.stem.endswith("_work_queue")
        and not any(part.startswith(".") for part in p.relative_to(CARD_JSON_ROOT).parts)
    }


def engine_relevant_diff(old_rec: dict, new_rec: dict) -> dict:
    """Changed fields that a card implementation could depend on."""
    return {
        field: (old_rec.get(field), new_rec.get(field))
        for field in ENGINE_RELEVANT_FIELDS
        if old_rec.get(field) != new_rec.get(field)
    }


def report_implementation_impact(impacted: dict[str, dict]) -> None:
    """Print cards whose implementation may have been invalidated by a refresh.

    This is the point of running the refresh at all. card_data/ is gitignored,
    so `git diff` shows nothing after an update, and a rules-text errata will
    otherwise sit undetected behind a passing test suite — the tests assert the
    behaviour the card used to have. Snarky Prick went from "destroy it and
    this gets +4{p}" to "you may destroy it", which turned a correct mandatory
    implementation into a wrong one with no test failure anywhere.
    """
    if not impacted:
        print("\nNo implemented card changed in an engine-relevant field.")
        return

    print(f"\n{'=' * 70}")
    print(f"!! {len(impacted)} IMPLEMENTED CARD(S) CHANGED — review these implementations")
    print(f"{'=' * 70}")
    for slug, diff in sorted(impacted.items()):
        print(f"\n  {slug}   ({', '.join(sorted(diff))})")
        for field, (before, after) in sorted(diff.items()):
            print(f"    {field}:")
            print(f"      was: {str(before)[:200]}")
            print(f"      now: {str(after)[:200]}")
    print(f"\n  Re-read each card's JSON against its new text before trusting the")
    print(f"  test suite: existing tests assert the OLD behaviour and will still pass.")


def fetch_index_ts(which: str, ref: str = FABRARY_REF) -> Path:
    """Download a fabrary/cards index.ts and return the local cache path.

    Verifies the payload actually looks like the expected TypeScript module
    before writing. A 404 or an HTML error page written straight to disk would
    otherwise parse to zero cards and silently report "0 new, 0 updated".
    """
    path = FABRARY_SOURCES[which]
    url = RAW_URL.format(repo=FABRARY_REPO, ref=ref, path=path)
    dest = FETCH_CACHE[which]

    print(f"Fetching {which} from {FABRARY_REPO}@{ref}")
    print(f"  {url}")
    try:
        with urllib.request.urlopen(url, timeout=120) as resp:
            payload = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise SystemExit(
            f"fetch failed: HTTP {exc.code} for {url}\n"
            f"The upstream layout may have changed — check "
            f"https://github.com/{FABRARY_REPO}/tree/{ref}/{Path(path).parent.as_posix()}"
        ) from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"fetch failed: {exc.reason} for {url}") from exc

    if "Card[]" not in payload or "@flesh-and-blood/types" not in payload:
        raise SystemExit(
            f"fetch returned {len(payload)} bytes that do not look like a cards "
            f"index.ts (no 'Card[]' / '@flesh-and-blood/types'). Refusing to "
            f"write {dest.name}; the URL or upstream format likely changed."
        )

    dest.write_text(payload, encoding="utf-8")
    print(f"  wrote {dest.relative_to(ROOT)} ({len(payload):,} bytes)")
    return dest


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

def _parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--latest-set", action="store_true",
                   help="download only the newest set (~80 KB) instead of everything")
    g.add_argument("--local", action="store_true",
                   help="skip the download and parse the local card_data/index.ts")
    g.add_argument("--source", type=Path,
                   help="parse a specific local index.ts")
    ap.add_argument("--ref", default=FABRARY_REF,
                    help=f"branch or tag to fetch from (default: {FABRARY_REF})")
    ap.add_argument("--dry-run", action="store_true",
                    help="parse and report, writing no index files")
    return ap.parse_args(argv)


def resolve_source(args) -> Path:
    """Pick the index.ts to parse. Defaults to fetching the full catalogue.

    Fetching everything is the default because this script upserts: parsing the
    whole catalogue refreshes existing cards as well as adding new ones, so a
    stale field anywhere gets corrected. --latest-set only ever touches the
    newest set's cards and leaves the rest as they were.
    """
    if args.source:
        if not args.source.exists():
            raise SystemExit(f"source not found: {args.source}")
        return args.source
    if args.local:
        if not INDEX_TS.exists():
            raise SystemExit(
                f"{INDEX_TS.relative_to(ROOT)} not found — drop --local to fetch it.")
        return INDEX_TS
    return fetch_index_ts("latest-set" if args.latest_set else "full", args.ref)


def main():
    args = _parse_args()
    global DRY_RUN
    DRY_RUN = args.dry_run

    src_path = resolve_source(args)
    print(f"Parsing {src_path.relative_to(ROOT) if src_path.is_relative_to(ROOT) else src_path}")
    source = src_path.read_text(encoding="utf-8")
    blocks = _extract_card_blocks(source)
    print(f"Parsed {len(blocks)} cards from index.ts")

    # Load existing slug_index
    if SLUG_JSON.exists():
        raw = json.loads(SLUG_JSON.read_text(encoding="utf-8"))
        existing = raw.get("by_slug", raw)
    else:
        existing = {}

    implemented = implemented_slugs()
    impacted: dict[str, dict] = {}

    added = updated = 0
    for card_id, block in blocks:
        slug = _slug(card_id)
        record = parse_card(card_id, block)
        if slug not in existing:
            added += 1
        else:
            updated += 1
            # Capture the diff before the old record is overwritten — only for
            # cards that actually have an implementation to invalidate.
            if slug in implemented:
                diff = engine_relevant_diff(existing[slug], record)
                if diff:
                    impacted[slug] = diff
        existing[slug] = record

    print(f"  {added} new, {updated} updated  (total {len(existing)})")
    print(f"  {len(implemented)} implemented cards checked for engine-relevant changes")

    report_implementation_impact(impacted)

    if DRY_RUN:
        print("\nDry run — no files written.")
        return

    out = {"by_slug": existing}

    SLUG_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {SLUG_JSON}")

    if msgpack:
        SLUG_MSGPACK.write_bytes(msgpack.packb(out, use_bin_type=True))
        print(f"Wrote {SLUG_MSGPACK}")


if __name__ == "__main__":
    main()
