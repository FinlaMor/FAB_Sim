"""Triage the `candidate` tier: unverified cards that are LIVE in the corpus.

`candidate` means the JSON compiles and is not a no-op stub, but no generated
test ever passed. Those cards stay playable, so the corpus currently trusts ~787
implementations that nothing ever checked — and a semantic sample of them found
errors in 6 of 6.

This does the FAST half of the triage: the mechanical defect checks from
audit_run.py cost no LLM time, so every candidate can be classified in seconds
rather than the ~23 hours a full gate run over 787 cards would take.

Policy — quarantine only on POSITIVE EVIDENCE of breakage:

  defective  a mechanically detectable defect (invented flag / fabricated
             keyword / invented amount / bad ability_type). The ability provably
             cannot work, so the card is quarantined out of the live corpus.
  clean      no detectable defect. STAYS live and stays `candidate`: absence of
             a passing test is not evidence of a wrong card, and quarantining
             700+ cards on that basis would break far more than it fixes.

Deck protection: a card used by one of the working decks is NEVER quarantined,
even when defective — a missing implementation makes the game refuse to start,
so silently quarantining one would break a deck that works today. Those are
reported as `defective_in_deck` for hand review instead.

Usage:
  python scripts/triage_candidates.py                 # report only (default)
  python scripts/triage_candidates.py --apply         # move + update queues
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import audit_run  # reuse the exact defect checks the audit reports

JSON_ROOT = ROOT / "engine" / "card_effects" / "json"
# Must start with "." — loader.load_all_cards() rglobs *.json and skips ONLY
# dot-prefixed path parts. A "_quarantine" folder would still be loaded, so the
# cards would stay live and the quarantine would be purely cosmetic.
QUARANTINE = JSON_ROOT / ".quarantine"
DECK_DIR = ROOT / "decks"


def deck_slugs() -> set[str]:
    """Every slug referenced by a deck file, so a working deck is never broken.

    Deck files list card NAMES ("1x Aurum Aegis"), not slugs, so the engine's own
    loader is used to resolve them. A first cut regex-matched bare slugs and
    silently returned an EMPTY set, which made the "0 defective cards in decks"
    safety check vacuously true — the check must fail loudly instead, so callers
    verify it is non-empty before trusting it.
    """
    from engine.card import CardDB
    from engine.deck import load_deck

    slugs: set[str] = set()
    if not DECK_DIR.exists():
        return slugs
    db = CardDB()
    for path in sorted(DECK_DIR.rglob("*.txt")):
        try:
            deck = load_deck(str(path), db)
        except Exception:
            continue  # a malformed/experimental deck must not abort the triage
        for value in deck.values() if isinstance(deck, dict) else []:
            items = value if isinstance(value, list) else [value]
            for item in items:
                slug = getattr(item, "slug", None) or (
                    item if isinstance(item, str) else None)
                if slug:
                    slugs.add(str(slug))
    return slugs


def queue_paths() -> list[Path]:
    return sorted(JSON_ROOT.glob("*/*_work_queue.json"))


def load_queue(path: Path):
    raw = json.loads(path.read_text(encoding="utf-8"))
    cards = raw if isinstance(raw, list) else raw.get("cards", raw.get("queue", []))
    return raw, cards


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="Actually move defective cards and update queues "
                         "(default is a report-only dry run).")
    args = ap.parse_args()

    decks = deck_slugs()
    # Fail loudly rather than quarantine against a silently-empty protection set:
    # an empty `decks` makes every "is this card in a deck?" test false, so the
    # deck guard would pass vacuously and could quarantine a card a working deck
    # needs (a missing implementation makes the game refuse to start).
    if not decks:
        print("ABORT: deck protection resolved 0 slugs — refusing to triage, as "
              "the 'not used by any deck' check would be vacuously true.",
              file=sys.stderr)
        return 2
    print(f"deck protection: {len(decks)} slugs across {DECK_DIR.name}/\n")

    index = json.loads(
        (ROOT / "card_data" / "slug_index.json").read_text(encoding="utf-8"))
    index = index.get("by_slug", index)

    buckets: dict[str, list] = {"defective": [], "clean": [], "defective_in_deck": [],
                                "missing_file": []}
    reasons: Counter = Counter()

    for qpath in queue_paths():
        raw, cards = load_queue(qpath)
        set_code = qpath.parent.name
        for card in cards:
            if card.get("status") != "candidate":
                continue
            slug = card["slug"]
            matches = list(JSON_ROOT.rglob(f"{slug}.json"))
            if not matches:
                buckets["missing_file"].append((set_code, slug, qpath))
                continue
            found = audit_run.audit([matches[0]], index).get(slug, [])
            if found:
                for f in found:
                    reasons[f.split("'")[0].strip()] += 1
                bucket = "defective_in_deck" if slug in decks else "defective"
                buckets[bucket].append((set_code, slug, matches[0], found, qpath))
            else:
                buckets["clean"].append((set_code, slug, qpath))

    total = sum(len(v) for v in buckets.values())
    print(f"candidates triaged: {total}\n")
    print(f"  defective (quarantine)   {len(buckets['defective']):5}")
    print(f"  defective but IN A DECK  {len(buckets['defective_in_deck']):5}  "
          f"(kept live — quarantining would break a working deck)")
    print(f"  clean (stay live)        {len(buckets['clean']):5}")
    print(f"  json missing             {len(buckets['missing_file']):5}")
    if reasons:
        print("\ndefect kinds:")
        for kind, n in reasons.most_common():
            print(f"  {n:5}  {kind}")

    if buckets["defective_in_deck"]:
        print("\nDEFECTIVE CARDS IN WORKING DECKS — review by hand:")
        for set_code, slug, _p, found, _q in buckets["defective_in_deck"]:
            print(f"  {set_code}/{slug}: {found[0]}")

    if not args.apply:
        print("\n(dry run — pass --apply to quarantine defective cards)")
        return 0

    QUARANTINE.mkdir(parents=True, exist_ok=True)
    moved = 0
    by_queue: dict[Path, set[str]] = {}
    for set_code, slug, path, found, qpath in buckets["defective"]:
        dest_dir = QUARANTINE / set_code
        dest_dir.mkdir(parents=True, exist_ok=True)
        path.rename(dest_dir / path.name)
        (dest_dir / f"{slug}.reasons.txt").write_text(
            "\n".join(found) + "\n", encoding="utf-8")
        by_queue.setdefault(qpath, set()).add(slug)
        moved += 1

    for qpath, slugs in by_queue.items():
        raw, cards = load_queue(qpath)
        for card in cards:
            if card["slug"] in slugs:
                card["status"] = "needs_review"
        qpath.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")

    print(f"\nquarantined {moved} card(s) -> {QUARANTINE.relative_to(ROOT)}")
    print(f"updated {len(by_queue)} work queue(s): candidate -> needs_review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
