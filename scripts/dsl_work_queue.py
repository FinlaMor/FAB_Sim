#!/usr/bin/env python3
"""DSL card-implementation work-queue tool.

The engine refuses to start a game if any card in play lacks a JSON DSL
definition under engine/card_effects/json/ (see
engine.card_effects.dsl.loader.MissingCardImplementation). This tool reports
what is implemented and generates per-set work queues for authoring the rest.

Usage:
  python scripts/dsl_work_queue.py --status
      Summary: implemented counts per set dir, load errors.

  python scripts/dsl_work_queue.py --deck decks/kayo_underhanded_cheat_CC_lite.txt
      List every slug the deck needs that has no DSL definition.
      (Default with no args: checks every decks/*.txt.)

  python scripts/dsl_work_queue.py --set hnt
      List unimplemented cards for a set (matched by setIdentifiers prefix).

  python scripts/dsl_work_queue.py --set hnt --write-queue
      Write/refresh engine/card_effects/json/<set>/<set>_work_queue.json.
      Existing statuses are preserved; implemented cards are marked "done".
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card_effects.dsl.loader import get_card, load_all_cards, LOAD_ERRORS  # noqa: E402

JSON_ROOT = ROOT / "engine" / "card_effects" / "json"


def _slug_index() -> dict:
    with open(ROOT / "card_data" / "slug_index.json", encoding="utf-8") as f:
        raw = json.load(f)
    return raw.get("by_slug", raw)


def _set_codes(entry: dict) -> set[str]:
    """Every lowercase set code a card was printed in (HNT012 -> hnt).

    Reprints are the norm, not the exception: over 2000 of the ~4600 cards
    list more than one set. Reading only the first identifier hid 118 of the
    265 Heavy Hitters cards (including Arakni) from `--set hnt`, so a set was
    never actually finishable through this tool.
    """
    codes = set()
    for ident in entry.get("setIdentifiers") or []:
        code = "".join(ch for ch in ident if ch.isalpha()).lower()
        if code:
            codes.add(code)
    return codes


def _queue_entry(slug: str, entry: dict, status: str) -> dict:
    return {
        "slug": slug,
        "name": entry.get("name"),
        "type_text": entry.get("typeText"),
        "cost": entry.get("cost"),
        "pitch": entry.get("pitch"),
        "power": entry.get("power"),
        "defense": entry.get("defense"),
        "life": entry.get("life"),
        "intellect": entry.get("intellect"),
        "subtypes": entry.get("subtypes") or [],
        "classes": entry.get("classes") or [],
        "keywords": entry.get("keywords") or [],
        "specializations": entry.get("specializations") or [],
        "functional_text": entry.get("functionalText"),
        "status": status,
    }


def cmd_status() -> None:
    load_all_cards()
    # Dot-directories under the card tree are PIPELINE RESULTS -- .drafts,
    # .review, .triage, .draft-review -- not implemented cards. They only exist
    # in the pipeline worktree, where counting them reported 5530 implemented
    # against a true 1010: the one number someone reads to judge progress.
    files = [p for p in JSON_ROOT.rglob("*.json")
             if not p.stem.endswith("_work_queue")
             and not any(part.startswith(".") for part in p.parts)]
    per_set: dict[str, int] = {}
    for p in files:
        per_set[p.parent.name] = per_set.get(p.parent.name, 0) + 1
    print(f"Implemented DSL card definitions: {len(files)}")
    for name in sorted(per_set):
        print(f"  {name:8s} {per_set[name]}")
    if LOAD_ERRORS:
        print(f"\nJSON files FAILING to load ({len(LOAD_ERRORS)}) — these count as unimplemented:")
        for stem, err in sorted(LOAD_ERRORS.items()):
            print(f"  {stem}: {err}")
    queues = sorted(JSON_ROOT.rglob("*_work_queue.json"))
    if queues:
        print("\nWork queues:")
        for q in queues:
            items = json.loads(q.read_text(encoding="utf-8"))
            pending = sum(1 for it in items if it.get("status") != "done")
            print(f"  {q.relative_to(ROOT)}: {pending} pending / {len(items)} total")


def _deck_slugs(deck_path: Path) -> set[str]:
    from engine.card import CardDB
    from engine.deck import load_deck
    db = CardDB()
    deck = load_deck(str(deck_path), db)
    slugs: set[str] = set()
    if deck.get("hero"):
        slugs.add(deck["hero"])
    slugs.update(deck.get("weapons") or [])
    slugs.update((deck.get("equipment") or {}).values())
    slugs.update(deck.get("cards") or [])
    return {s for s in slugs if s}


def cmd_deck(paths: list[Path]) -> int:
    load_all_cards()
    missing_total = 0
    index = _slug_index()
    for path in paths:
        slugs = _deck_slugs(path)
        missing = sorted(s for s in slugs if get_card(s) is None)
        missing_total += len(missing)
        status = "OK" if not missing else f"{len(missing)} missing"
        print(f"{path.name}: {len(slugs)} unique cards — {status}")
        for s in missing:
            ft = (index.get(s, {}).get("functionalText") or "").replace("\n", " ")
            print(f"  {s}: {ft[:100]}")
    return 1 if missing_total else 0


def cmd_set(set_code: str, write_queue: bool) -> None:
    load_all_cards()
    index = _slug_index()
    in_set = {s: e for s, e in index.items() if set_code in _set_codes(e)}
    if not in_set:
        print(f"No cards found for set code '{set_code}'.")
        return
    missing = {s: e for s, e in in_set.items() if get_card(s) is None}
    print(f"Set '{set_code}': {len(in_set)} cards, "
          f"{len(in_set) - len(missing)} implemented, {len(missing)} missing")

    if not write_queue:
        for s in sorted(missing):
            ft = (missing[s].get("functionalText") or "").replace("\n", " ")
            print(f"  {s}: {ft[:100]}")
        return

    # Merge: keep every existing queue entry (queues may use broader set
    # membership than setIdentifiers), update statuses from actual DSL
    # presence, and append any set cards the queue doesn't know about yet.
    qdir = JSON_ROOT / set_code
    qdir.mkdir(parents=True, exist_ok=True)
    qpath = qdir / f"{set_code}_work_queue.json"
    items: list[dict] = []
    seen: set[str] = set()
    if qpath.exists():
        items = json.loads(qpath.read_text(encoding="utf-8"))
        seen = {it["slug"] for it in items}
    for it in items:
        if get_card(it["slug"]) is not None:
            it["status"] = "done"
        elif it.get("status") == "done":  # queue said done but JSON is gone
            it["status"] = "pending"
    for slug in sorted(in_set):
        if slug in seen:
            continue
        status = "done" if get_card(slug) is not None else "pending"
        items.append(_queue_entry(slug, in_set[slug], status))
    qpath.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    pending = sum(1 for it in items if it["status"] != "done")
    print(f"Wrote {qpath.relative_to(ROOT)} ({pending} pending / {len(items)} total)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", action="store_true", help="implementation summary")
    ap.add_argument("--deck", action="append", type=Path, help="deck txt file to check")
    ap.add_argument("--set", dest="set_code", help="set code, e.g. hnt, wtr, hvy")
    ap.add_argument("--write-queue", action="store_true",
                    help="with --set: write/refresh the set's work-queue JSON")
    args = ap.parse_args()

    if args.status:
        cmd_status()
        return 0
    if args.set_code:
        cmd_set(args.set_code.lower(), args.write_queue)
        return 0
    decks = args.deck or sorted((ROOT / "decks").glob("*.txt"))
    return cmd_deck(decks)


if __name__ == "__main__":
    raise SystemExit(main())
