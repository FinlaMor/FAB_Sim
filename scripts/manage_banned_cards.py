"""scripts/manage_banned_cards.py

.. deprecated::
    This script managed banned_cards.json which is no longer used.
    Card format legality is now determined by the ``legal_formats`` field
    in slug_index.msgpack (sourced from the official @flesh-and-blood/types
    package).  This script is kept for reference only.

Manage the banned cards registry for Flesh and Blood formats.

Usage:
    python scripts/manage_banned_cards.py list
    python scripts/manage_banned_cards.py list cc
    python scripts/manage_banned_cards.py add cc wounding_blow_red
    python scripts/manage_banned_cards.py add cc wounding_blow --all-colors
    python scripts/manage_banned_cards.py remove cc wounding_blow_red
    python scripts/manage_banned_cards.py clear cc
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from pathlib import Path

# Allow importing from project root.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config import CARD_DATA_DIR  # noqa: E402
BANNED_CARDS_PATH = os.path.join(CARD_DATA_DIR, "banned_cards.json")

COLORS = ("red", "yellow", "blue")

# Lazily loaded slug index
_slug_index: dict | None = None
SLUG_INDEX_PATH = _PROJECT_ROOT / "card_data" / "slug_index.json"


def _load_slug_index() -> dict:
    global _slug_index
    if _slug_index is not None:
        return _slug_index
    if SLUG_INDEX_PATH.exists():
        with open(SLUG_INDEX_PATH, encoding="utf-8") as f:
            data = json.load(f)
        _slug_index = data.get("by_slug", {})
    else:
        _slug_index = {}
    return _slug_index


def _load_banned() -> dict[str, list[str]]:
    """Load the banned cards JSON file."""
    path = Path(BANNED_CARDS_PATH)
    if not path.exists():
        return {"cc": []}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_banned(data: dict[str, list[str]]) -> None:
    """Save the banned cards JSON file with sorted slugs."""
    for fmt in data:
        data[fmt] = sorted(set(data[fmt]))
    with open(BANNED_CARDS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def _validate_slug(slug: str) -> None:
    """Warn if slug is not found in slug_index."""
    index = _load_slug_index()
    if slug not in index:
        warnings.warn(f"Slug '{slug}' not found in slug_index.json", stacklevel=3)


def _expand_all_colors(slug: str) -> list[str]:
    """Expand a base slug into all color variants."""
    return [f"{slug}_{color}" for color in COLORS]


def cmd_list(args: argparse.Namespace) -> None:
    """List banned cards, optionally filtered by format."""
    data = _load_banned()
    if args.format:
        fmt = args.format
        slugs = data.get(fmt, [])
        if not slugs:
            print(f"No banned cards for format '{fmt}'.")
        else:
            print(f"Banned cards for '{fmt}' ({len(slugs)}):")
            for s in sorted(slugs):
                print(f"  {s}")
    else:
        for fmt in sorted(data.keys()):
            slugs = data[fmt]
            print(f"{fmt}: {len(slugs)} banned card(s)")
            for s in sorted(slugs):
                print(f"  {s}")


def cmd_add(args: argparse.Namespace) -> None:
    """Add slug(s) to a format's banned list."""
    data = _load_banned()
    fmt = args.format
    if fmt not in data:
        data[fmt] = []

    slugs_to_add: list[str] = []
    for slug in args.slugs:
        if args.all_colors:
            slugs_to_add.extend(_expand_all_colors(slug))
        else:
            slugs_to_add.append(slug)

    added = []
    for slug in slugs_to_add:
        _validate_slug(slug)
        if slug not in data[fmt]:
            data[fmt].append(slug)
            added.append(slug)

    _save_banned(data)
    if added:
        print(f"Added to '{fmt}': {', '.join(sorted(added))}")
    else:
        print("No new slugs added (already banned).")


def cmd_remove(args: argparse.Namespace) -> None:
    """Remove slug(s) from a format's banned list."""
    data = _load_banned()
    fmt = args.format
    if fmt not in data:
        data[fmt] = []

    removed = []
    for slug in args.slugs:
        if slug in data[fmt]:
            data[fmt].remove(slug)
            removed.append(slug)
        else:
            warnings.warn(f"Slug '{slug}' not in '{fmt}' banned list.")

    _save_banned(data)
    if removed:
        print(f"Removed from '{fmt}': {', '.join(sorted(removed))}")


def cmd_clear(args: argparse.Namespace) -> None:
    """Clear all banned cards for a format."""
    data = _load_banned()
    fmt = args.format
    count = len(data.get(fmt, []))
    data[fmt] = []
    _save_banned(data)
    print(f"Cleared {count} banned card(s) from '{fmt}'.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage the FAB banned cards registry.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    p_list = subparsers.add_parser("list", help="List banned cards")
    p_list.add_argument("format", nargs="?", default=None, help="Format key (e.g. cc)")
    p_list.set_defaults(func=cmd_list)

    # add
    p_add = subparsers.add_parser("add", help="Add card(s) to banned list")
    p_add.add_argument("format", help="Format key (e.g. cc)")
    p_add.add_argument("slugs", nargs="+", help="Card slug(s) to ban")
    p_add.add_argument("--all-colors", action="store_true",
                       help="Expand each slug into red/yellow/blue variants")
    p_add.set_defaults(func=cmd_add)

    # remove
    p_remove = subparsers.add_parser("remove", help="Remove card(s) from banned list")
    p_remove.add_argument("format", help="Format key (e.g. cc)")
    p_remove.add_argument("slugs", nargs="+", help="Card slug(s) to unban")
    p_remove.set_defaults(func=cmd_remove)

    # clear
    p_clear = subparsers.add_parser("clear", help="Clear all banned cards for a format")
    p_clear.add_argument("format", help="Format key (e.g. cc)")
    p_clear.set_defaults(func=cmd_clear)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
