"""scripts/scrape_fablazing.py

Scrape per-hero card stats from fablazing.com and store in SQLite.

Usage:
    python scripts/scrape_fablazing.py                    # scrape all CC heroes
    python scripts/scrape_fablazing.py --heroes kayo      # single hero
    python scripts/scrape_fablazing.py --format sage      # different format
    python scripts/scrape_fablazing.py --list-heroes      # show available heroes
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import time
from pathlib import Path

import requests

DB_PATH = Path("data/fablazing_meta.db")
SLUG_INDEX_PATH = Path(__file__).resolve().parent.parent / "card_data" / "slug_index.json"

# ---------------------------------------------------------------------------
# Slug index helpers — equipment subtype derivation and slug validation
# ---------------------------------------------------------------------------

_slug_index: dict | None = None


def _get_slug_index() -> dict:
    global _slug_index
    if _slug_index is None:
        if SLUG_INDEX_PATH.exists():
            with open(SLUG_INDEX_PATH, encoding="utf-8") as f:
                _slug_index = json.load(f).get("by_slug", {})
        else:
            _slug_index = {}
    return _slug_index


def _equipment_subtype(slug: str) -> str:
    """Return a canonical equipment subtype string for a slug.

    Derived from the slug's 'types' list in slug_index.json:
        weapon-1h       1-handed weapon
        weapon-2h       2-handed weapon (non-bow)
        weapon-bow      2-handed bow weapon (can pair with Quiver)
        head / chest / arms / legs / off-hand / quiver / base
        equipment-other fallback for unslotted equipment
    """
    index = _get_slug_index()
    entry = index.get(slug)
    if not entry:
        return ""
    types_lower = [t.lower() for t in entry.get("types", [])]
    # Cards with both 'action' and 'equipment' types are Evo-install cards that
    # the simulator cannot handle as standard arena equipment — exclude them.
    if "action" in types_lower and "equipment" in types_lower:
        return ""
    if "weapon" in types_lower:
        if "bow" in types_lower:
            return "weapon-bow"
        if "2h" in types_lower:
            return "weapon-2h"
        if "1h" in types_lower:
            return "weapon-1h"
        return "weapon-other"
    # off-hand may appear on companions/allies without the 'equipment' type
    # slug_index uses both 'Off-Hand' and 'OffHand' — normalise both
    is_offhand = "off-hand" in types_lower or "offhand" in types_lower
    if is_offhand and "equipment" not in types_lower:
        return "off-hand"
    if "equipment" in types_lower:
        for slot in ("head", "chest", "arms", "legs", "quiver", "base"):
            if slot in types_lower:
                return slot
        if is_offhand:
            return "off-hand"
        return "equipment-other"
    return ""


def _resolve_slug(raw_slug: str, card_type: str) -> str:
    """Try to resolve a fablazing card_id to a real slug_index slug.

    Fablazing sometimes emits truncated slugs (e.g. 'gorganian' instead of
    'gorganian_tome'). We attempt prefix matching against the slug index and
    return the best candidate, or the original slug if nothing matches.
    """
    index = _get_slug_index()
    if not index:
        return raw_slug
    if raw_slug in index:
        return raw_slug
    # Prefix match: find all slugs starting with raw_slug + '_'
    prefix = raw_slug + "_"
    candidates = [s for s in index if s.startswith(prefix)]
    if not candidates:
        return raw_slug
    # Prefer candidates whose types match the card_type category
    if card_type == "equipment":
        typed = [
            s for s in candidates
            if any(t in ("Equipment", "Weapon") for t in index[s].get("types", []))
        ]
        if typed:
            return min(typed, key=len)   # shortest = most canonical
    # Fallback: shortest candidate (most likely the base card)
    return min(candidates, key=len)

# Hero slugs for CC format (from fablazing.com/meta/cc as of 2026-03-15).
# Add new heroes here as they appear on the site.
CC_HERO_SLUGS = [
    "vynnset-iron-maiden",
    "oscilio-constella-intelligence",
    "arakni-marionette",
    "jarl-vetreii",
    "arakni-huntsman",
    "dash-io",
    "marlynn-treasure-hunter",
    "ser-boltyn-breaker-of-dawn",
    "rhinar-reckless-rampage",
    "verdance-thorn-of-the-rose",
    "dorinthea-ironsong",
    "victor-goldmane-high-and-mighty",
    "kayo-underhanded-cheat",
    "kayo-armed-and-dangerous",
    "valda-seismic-impact",
    "katsu-the-wanderer",
    "fai-rising-rebellion",
    "cindra-dracai-of-retribution",
    "teklovossen-esteemed-magnate",
    "ira-scarlet-revenger",
    "puffin-hightail",
    "tuffnut-bumbling-hulkster",
    "gravy-bones-shipwrecked-looter",
    "fang-dracai-of-blades",
    "lyath-goldmane-vile-savant",
    "arakni-5lp3d-7hru-7h3-cr4x",
    "pleiades-superstar",
    "riptide-lurker-of-the-deep",
    "kassai-of-the-golden-sand",
    "prism-awakener-of-sol",
    "levia-shadowborn-abomination",
    "maxx-the-hype-nitro",
    "uzuri-switchblade",
    "bravo-showstopper",
    "olympia-prized-fighter",
    "betsy-skin-in-the-game",
]


def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS heroes (
            hero_slug       TEXT NOT NULL,
            format          TEXT NOT NULL,
            hero_name       TEXT,
            win_rate        REAL,
            total_matches   INTEGER,
            scraped_at      TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (hero_slug, format)
        );

        CREATE TABLE IF NOT EXISTS card_stats (
            hero_slug           TEXT NOT NULL,
            format              TEXT NOT NULL,
            card_slug           TEXT NOT NULL,
            card_name           TEXT,
            card_type           TEXT,          -- 'deck' or 'equipment'
            equipment_subtype   TEXT,          -- head/chest/arms/legs/off-hand/quiver/base/weapon-1h/weapon-2h/weapon-bow/weapon-other
            frequency           REAL,          -- play rate (0.0 - 1.0)
            avg_copies          REAL,
            win_rate            REAL,
            match_count         INTEGER,
            scraped_at          TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (hero_slug, format, card_slug)
        );

        CREATE INDEX IF NOT EXISTS idx_card_stats_card
            ON card_stats(card_slug);
        CREATE INDEX IF NOT EXISTS idx_card_stats_hero_freq
            ON card_stats(hero_slug, format, frequency DESC);
    """)
    # Migrate existing DBs that lack the equipment_subtype column
    existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(card_stats)").fetchall()}
    if "equipment_subtype" not in existing_cols:
        conn.execute("ALTER TABLE card_stats ADD COLUMN equipment_subtype TEXT")
    conn.commit()
    return conn


def _parse_remix_stream(html: str) -> list | None:
    """Parse the Remix turbo-stream embedded in the page HTML.

    Remix serializes route data as a flat JSON array inside a script tag:
        window.__remixContext.streamController.enqueue("[...]")

    The array uses positional references: objects have _N keys where N
    is the index of the key name, and integer values reference other
    positions in the array.
    """
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    for script in scripts:
        m = re.search(r'\.enqueue\("(.*)"\)', script, re.DOTALL)
        if not m:
            continue
        raw = m.group(1)
        if 'card_id' not in raw and 'frequency' not in raw:
            continue
        # Unescape the JSON string (it's double-escaped inside a JS string)
        unescaped = raw.encode().decode('unicode_escape')
        # The stream may be truncated — find the last valid ] to parse
        for end in range(len(unescaped), max(0, len(unescaped) - 50000), -500):
            bracket = unescaped.rfind(']', 0, end)
            if bracket > 0:
                try:
                    return json.loads(unescaped[:bracket + 1])
                except json.JSONDecodeError:
                    continue
    return None


def _resolve_remix_object(stream: list, idx: int) -> dict | None:
    """Resolve a Remix stream object at the given index.

    Objects have _N keys: N is the stream index of the key name,
    and the value is the stream index of the value (or -5 for None).
    """
    if idx < 0 or idx >= len(stream):
        return None
    obj = stream[idx]
    if not isinstance(obj, dict):
        return None
    result = {}
    for k, v in obj.items():
        key_idx = int(k.lstrip('_')) if k.startswith('_') else None
        key_name = stream[key_idx] if key_idx is not None and key_idx < len(stream) else k
        if isinstance(v, int) and v == -5:
            result[key_name] = None
        elif isinstance(v, int) and 0 <= v < len(stream):
            result[key_name] = stream[v]
        else:
            result[key_name] = v
    return result


def _extract_cards_and_hero(html: str) -> tuple[list[dict], dict]:
    """Extract card data and hero info from the Remix stream.

    Returns (cards_list, hero_info_dict).
    """
    stream = _parse_remix_stream(html)
    if not stream:
        return [], {}

    # --- Hero info ---
    # The queried hero's data is in the "currentHero" object.
    hero_info: dict = {}
    title_match = re.search(r'<title>([^<|]+)', html)
    if title_match:
        name = re.sub(r'\s*Core Cards.*', '', title_match.group(1).strip()).strip()
        if name:
            hero_info["name"] = name

    # Resolve the currentHero object for win_rate and total_matches
    for i, item in enumerate(stream):
        if item == "currentHero" and i + 1 < len(stream):
            hero_data = _resolve_remix_object(stream, i + 1)
            if hero_data:
                if "overall_win_rate" in hero_data:
                    hero_info["win_rate"] = hero_data["overall_win_rate"]
                if "total_matches" in hero_data:
                    hero_info["total_matches"] = hero_data["total_matches"]
                if "name" in hero_data and not hero_info.get("name"):
                    hero_info["name"] = hero_data["name"]
            break

    # --- Cards ---
    cards: list[dict] = []

    for section_name, card_type in [("core_cards", "deck"), ("core_equipment", "equipment")]:
        for i, item in enumerate(stream):
            if item == section_name and i + 1 < len(stream):
                indices = stream[i + 1]
                if isinstance(indices, list):
                    for idx in indices:
                        card = _resolve_remix_object(stream, idx)
                        if card and "card_id" in card:
                            card["_card_type"] = card_type
                            cards.append(card)
                break

    return cards, hero_info


def scrape_hero(hero_slug: str, fmt: str = "cc", session: requests.Session | None = None) -> dict:
    """Scrape card stats for a single hero from fablazing.com.

    Returns dict with 'hero', 'cards' keys.
    """
    session = session or requests.Session()
    url = f"https://fablazing.com/core/{hero_slug}?format={fmt}"

    resp = session.get(url, timeout=30, headers={
        "User-Agent": "FAB_Sim/1.0 (deck-builder research)",
        "Accept": "text/html,application/xhtml+xml",
    })
    resp.raise_for_status()

    html = resp.text
    cards, hero_info = _extract_cards_and_hero(html)

    return {
        "hero_slug": hero_slug,
        "format": fmt,
        "hero_info": hero_info,
        "cards": cards,
        "raw_html_len": len(html),
    }


def save_to_db(conn: sqlite3.Connection, data: dict) -> int:
    """Save scraped hero data to SQLite. Returns number of cards saved."""
    hero_slug = data["hero_slug"]
    fmt = data["format"]
    hero_info = data["hero_info"]

    # Fix common Unicode issues from fablazing HTML
    # e.g. U+0111 (d with stroke) -> U+00F0 (eth ð) for Icelandic names
    hero_name = hero_info.get("name")
    if hero_name:
        hero_name = hero_name.replace("\u0111", "\u00f0")

    conn.execute("""
        INSERT OR REPLACE INTO heroes (hero_slug, format, hero_name, win_rate, total_matches)
        VALUES (?, ?, ?, ?, ?)
    """, (
        hero_slug, fmt,
        hero_name,
        hero_info.get("win_rate"),
        hero_info.get("total_matches"),
    ))

    cards = data["cards"]
    saved = 0
    for card in cards:
        raw_slug = card.get("card_id", "")
        if not raw_slug:
            continue

        card_type = card.get("_card_type", "deck")

        # Resolve potentially truncated fablazing slug to real card slug
        card_slug = _resolve_slug(raw_slug, card_type)

        # Derive equipment subtype from slug_index
        subtype = _equipment_subtype(card_slug) if card_type == "equipment" else None

        conn.execute("""
            INSERT OR REPLACE INTO card_stats
                (hero_slug, format, card_slug, card_name, card_type, equipment_subtype,
                 frequency, avg_copies, win_rate, match_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            hero_slug, fmt, card_slug,
            card.get("card_name", card_slug),
            card_type,
            subtype,
            card.get("frequency"),
            card.get("avg_copies") or card.get("average_copies"),
            card.get("win_rate"),
            card.get("match_count"),
        ))
        saved += 1

    conn.commit()
    return saved


def backfill_equipment_subtypes(conn: sqlite3.Connection) -> int:
    """Populate equipment_subtype for all existing equipment rows that lack it.

    Safe to re-run — only updates rows where equipment_subtype IS NULL.
    Returns the number of rows updated.
    """
    # Re-process all equipment rows (NULL or empty) to pick up classification fixes
    rows = conn.execute(
        "SELECT rowid, card_slug FROM card_stats "
        "WHERE card_type IN ('equipment','weapon_1h','weapon_2h') "
        "AND (equipment_subtype IS NULL OR equipment_subtype = '')"
    ).fetchall()
    updated = 0
    for rowid, slug in rows:
        subtype = _equipment_subtype(slug)
        conn.execute(
            "UPDATE card_stats SET equipment_subtype = ? WHERE rowid = ?",
            (subtype, rowid),
        )
        updated += 1
    conn.commit()
    return updated


def scrape_all(
    heroes: list[str] | None = None,
    fmt: str = "cc",
    db_path: Path = DB_PATH,
    delay: float = 1.5,
) -> None:
    """Scrape all heroes and save to database."""
    heroes = heroes or CC_HERO_SLUGS
    conn = init_db(db_path)
    session = requests.Session()

    total_cards = 0
    success = 0
    failed = []

    print(f"Scraping {len(heroes)} heroes from fablazing.com ({fmt} format)")
    print(f"Database: {db_path.resolve()}")
    print()

    for i, slug in enumerate(heroes, 1):
        try:
            print(f"  [{i:>2}/{len(heroes)}] {slug:<45}", end="", flush=True)
            data = scrape_hero(slug, fmt, session)
            n_cards = save_to_db(conn, data)
            total_cards += n_cards

            hero_wr = data["hero_info"].get("win_rate")
            wr_str = f"  WR={hero_wr:.1%}" if hero_wr else ""
            print(f"  {n_cards:>3} cards{wr_str}")
            success += 1

        except requests.HTTPError as e:
            print(f"  FAILED ({e.response.status_code})")
            failed.append((slug, str(e)))
        except Exception as e:
            print(f"  ERROR: {e}")
            failed.append((slug, str(e)))

        if i < len(heroes):
            time.sleep(delay)

    # Backfill equipment subtypes for any rows that may have been inserted
    # by older scraper versions (or rows just saved above without subtype).
    n_backfilled = backfill_equipment_subtypes(conn)
    if n_backfilled:
        print(f"  Backfilled equipment_subtype for {n_backfilled} rows")

    conn.close()

    print()
    print(f"Done: {success}/{len(heroes)} heroes, {total_cards} total card entries")
    if failed:
        print(f"Failed ({len(failed)}):")
        for slug, err in failed:
            print(f"  - {slug}: {err}")


def print_summary(db_path: Path = DB_PATH) -> None:
    """Print a summary of what's in the database."""
    if not db_path.exists():
        print("No database found. Run scraper first.")
        return

    conn = sqlite3.connect(str(db_path))

    heroes = conn.execute(
        "SELECT hero_slug, hero_name, win_rate, total_matches FROM heroes ORDER BY total_matches DESC"
    ).fetchall()

    print(f"\n{'Hero':<45} {'WR':>6} {'Matches':>8} {'Cards':>6}")
    print("-" * 70)
    for slug, name, wr, matches in heroes:
        n_cards = conn.execute(
            "SELECT COUNT(*) FROM card_stats WHERE hero_slug = ?", (slug,)
        ).fetchone()[0]
        wr_str = f"{wr:.1%}" if wr else "N/A"
        # Encode-safe: replace non-ASCII chars for Windows console
        display_name = (name or slug).encode('ascii', 'replace').decode('ascii')
        print(f"{display_name:<45} {wr_str:>6} {matches or 0:>8} {n_cards:>6}")

    total = conn.execute("SELECT COUNT(DISTINCT card_slug) FROM card_stats").fetchone()[0]
    print(f"\nTotal unique cards: {total}")
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Scrape fablazing.com card stats")
    parser.add_argument("--heroes", nargs="*", help="Hero slugs to scrape (default: all CC heroes)")
    parser.add_argument("--format", default="cc", help="Game format (default: cc)")
    parser.add_argument("--db", type=Path, default=DB_PATH, help=f"SQLite database path (default: {DB_PATH})")
    parser.add_argument("--delay", type=float, default=1.5, help="Delay between requests in seconds (default: 1.5)")
    parser.add_argument("--list-heroes", action="store_true", help="List available hero slugs and exit")
    parser.add_argument("--summary", action="store_true", help="Print database summary and exit")
    args = parser.parse_args()

    if args.list_heroes:
        print("Available CC hero slugs:")
        for slug in CC_HERO_SLUGS:
            print(f"  {slug}")
        return

    if args.summary:
        print_summary(args.db)
        return

    scrape_all(heroes=args.heroes, fmt=args.format, db_path=args.db, delay=args.delay)
    print_summary(args.db)


if __name__ == "__main__":
    main()
