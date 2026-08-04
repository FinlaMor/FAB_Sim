#!/usr/bin/env python3
"""Build "audit decks" that pack playable CANDIDATE cards into the three
functional heroes, so scripts/game_transcript_audit.py can actually REACH the
candidate corpus. Coverage/audit tooling only plays real decks; a candidate that
sits in no deck is never exercised. This stuffs each hero's deck full of distinct
candidate cards of its class (+ Generic), 1x each to maximise variety.

Not tournament-legal — the goal is execution coverage + a rules-invariant audit,
not competitive play. Only ~a third of candidates match the three implemented
heroes' classes (Warrior / Brute / Assassin); the rest need their hero built.

Usage:
  python scripts/build_audit_decks.py                # writes decks/generated/audit_*.txt
  python scripts/build_audit_decks.py --limit 60     # cap deck-card slots
"""
from __future__ import annotations
import argparse
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine.card import CardDB
from engine.deck import _parse_fabrary_card_line, _resolve_fabrary_slug
from engine.card_effects.dsl.loader import load_all_cards, get_card
DECKS_DIR = ROOT / "decks"
OUT_DIR = DECKS_DIR / "audit"
QUEUE = ROOT / "engine/card_effects/json/batch/batch_work_queue.json"
SLUG_INDEX = ROOT / "card_data/slug_index.json"

# hero handle -> (base deck, [classes the hero can play])
HEROES = {
    "victor": ("victor_goldmane_high_and_mighty_CC_lite.txt", ["Warrior"]),
    "kayo": ("kayo_underhanded_cheat_CC_lite.txt", ["Brute"]),
    "arakni": ("arakni_marionette_CC_lite.txt", ["Assassin"]),
    "marlynn": ("audit_base/marlynn_treasure_hunter_base.txt", ["Ranger", "Pirate"]),
    "vynnset": ("audit_base/vynnset_iron_maiden_base.txt", ["Runeblade"]),
}
PITCH_COLOR = {1: "red", 2: "yellow", 3: "blue"}
# Card types that belong in the DECK (not the arena/equipment) section.
DECK_TYPES = {"Action", "AttackReaction", "DefenseReaction", "Instant", "NonAttack"}


def _base_prefix(deck_path: Path) -> str:
    """Everything up to and including the 'Deck cards' header (Hero + Arena)."""
    lines = deck_path.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines:
        out.append(line)
        if line.strip().lower().startswith("deck cards"):
            return "\n".join(out) + "\n"
    # No 'Deck cards' header — keep the whole thing and add one.
    return "\n".join(lines) + "\n\nDeck cards\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=60, help="max deck-card slots")
    args = ap.parse_args()

    db = json.loads(SLUG_INDEX.read_text(encoding="utf-8"))["by_slug"]
    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    cands = [c["slug"] for c in queue if c["status"] == "candidate"]

    load_all_cards()
    card_db = CardDB()

    def _card_json(slug: str):
        for p in glob.glob(str(ROOT / "engine/card_effects/json" / "**" / f"{slug}.json"),
                           recursive=True):
            return json.loads(Path(p).read_text(encoding="utf-8"))
        return None

    def _token_safe(slug: str) -> bool:
        """A candidate is unsafe if it CREATE_TOKENs a slug with no JSON impl (an
        empty "token", or a wrong-case name like "Silver" for "silver"): the token
        must be implemented to enter play, so the effect crashes the game the moment
        it fires (require_card('')). ~21% of candidates have this. Drop them here so
        one bad card doesn't abort every audit game."""
        j = _card_json(slug)
        if j is None:
            return True
        bad = []

        def walk(o):
            if isinstance(o, dict):
                if (o.get("type") or "").upper() == "CREATE_TOKEN":
                    tok = o.get("token", "")
                    if not tok or get_card(tok) is None:
                        bad.append(tok)
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)

        walk(j)
        return not bad

    def _emittable(name: str, color: str) -> bool:
        """A deck line only loads if it resolves — via the engine's own fabrary
        resolver — to a slug that HAS a JSON impl. The resolver falls back to a
        different-color printing when the exact color is missing, and that printing
        may lack JSON -> the game refuses to start (MissingCardImplementation). So
        validate the round-trip here and drop anything that would crash a game."""
        parsed = _parse_fabrary_card_line(f"1x {name} ({color})")
        if parsed is None:
            return False
        rslug = _resolve_fabrary_slug(parsed[1], card_db)
        return rslug is not None and get_card(rslug) is not None

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for handle, (base, hero_classes) in HEROES.items():
        playable = set(hero_classes) | {"Generic"}
        prefix = _base_prefix(DECKS_DIR / base)
        lines, used, dropped = [], 0, 0
        for slug in cands:
            if used >= args.limit:
                break
            d = db.get(slug, {})
            classes = d.get("classes", []) or []
            if not (playable & set(classes)):
                continue
            if not (set(d.get("types", []) or []) & DECK_TYPES):
                continue
            color = PITCH_COLOR.get(d.get("pitch"))
            name = d.get("name")
            if not color or not name:
                continue  # non-pitchable / unnamed -> can't emit a deck line
            if not _emittable(name, color) or not _token_safe(slug):
                dropped += 1
                continue  # would resolve to a JSON-less printing/token and crash the game
            lines.append(f"1x {name} ({color})")
            used += 1
        out_path = OUT_DIR / f"audit_{handle}.txt"
        out_path.write_text(prefix + "\n".join(lines) + "\n", encoding="utf-8")
        print(f"{out_path.name}: {'/'.join(hero_classes)} hero + {used} candidate deck cards "
              f"({dropped} dropped as unresolvable)")


if __name__ == "__main__":
    main()
