"""
init_card_db.py — Build card_db.sqlite with a heroes table from slug_index.msgpack or cards.json.

Usage:
    python scripts/init_card_db.py [--json | --msgpack]
    # Default: tries msgpack, falls back to JSON

This script creates data/card_db.sqlite with a 'heroes' table containing all hero cards.
"""
import os
import sys
import sqlite3
import json
from pathlib import Path

try:
    import msgpack
except ImportError:
    print("msgpack not found, will not be able to load slug_index.msgpack. Install with 'pip install msgpack' if you want to use that format.")
    msgpack = None

ROOT = Path(__file__).resolve().parent.parent
CARD_DATA = ROOT / "card_data"
DB_PATH = ROOT / "data" / "card_db.sqlite"
SLUG_INDEX_MSGPACK = CARD_DATA / "slug_index.msgpack"
SLUG_INDEX_JSON = CARD_DATA / "slug_index.json"
CARDS_JSON = CARD_DATA / "cards.json"

# --- Utility: Load slug index ---
def load_slug_index(prefer_msgpack=True):
    if prefer_msgpack and msgpack and SLUG_INDEX_MSGPACK.exists():
        with open(SLUG_INDEX_MSGPACK, "rb") as f:
            raw = msgpack.unpackb(f.read(), raw=False)
        return raw.get("by_slug", raw)
    elif SLUG_INDEX_JSON.exists():
        with open(SLUG_INDEX_JSON, encoding="utf-8") as f:
            raw = json.load(f)
        return raw.get("by_slug", raw)
    elif CARDS_JSON.exists():
        with open(CARDS_JSON, encoding="utf-8") as f:
            cards = json.load(f)
        # Build slug index from cards.json
        return {c["slug"]: c for c in cards if "slug" in c}
    else:
        raise FileNotFoundError("No slug_index.msgpack, slug_index.json, or cards.json found.")

# --- Utility: Extract hero cards ---
def extract_heroes(slug_index):
    heroes = []
    for slug, card in slug_index.items():
        types = card.get("types", [])
        if any(t == "Type.Hero" for t in types):
            heroes.append(card)
    return heroes

# --- Main DB creation ---
def create_heroes_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS heroes (
            slug TEXT PRIMARY KEY,
            name TEXT,
            card_class TEXT,
            talent TEXT,
            life INTEGER,
            intellect INTEGER,
            rarity TEXT,
            set_code TEXT,
            is_adult INTEGER,
            data_json TEXT
        )
    """)
    conn.commit()

def insert_heroes(conn, heroes):
    for h in heroes:
        conn.execute(
            """
            INSERT OR REPLACE INTO heroes (slug, name, card_class, talent, life, intellect, rarity, set_code, is_adult, data_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                h.get("slug"),
                h.get("name"),
                h.get("card_class"),
                h.get("talent"),
                h.get("life"),
                h.get("intellect"),
                h.get("rarity"),
                h.get("set_code"),
                int(h.get("is_adult", False)),
                json.dumps(h, separators=(",", ":"))
            )
        )
    conn.commit()

def main():
    prefer_json = "--json" in sys.argv
    prefer_msgpack = not prefer_json
    slug_index = load_slug_index(prefer_msgpack=prefer_msgpack)
    heroes = extract_heroes(slug_index)
    if not heroes:
        print("No hero cards found in slug index.")
        sys.exit(1)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    create_heroes_table(conn)
    insert_heroes(conn, heroes)
    print(f"Inserted {len(heroes)} heroes into {DB_PATH}")
    conn.close()

if __name__ == "__main__":
    main()
