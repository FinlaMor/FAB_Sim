#!/usr/bin/env python3
"""Restore quarantined card JSONs that now load — e.g. cards rejected earlier for
using a DSL type that has since been implemented (CONDITIONAL, PUT_REF_BOTTOM, …).

For each `needs_review/<slug>.json.quarantine` that (a) compiles through the real
loader, (b) is not a no-op stub, and (c) would pass the empty-abilities hygiene
check, move it to its printed set folder as `<slug>.json` and flip the batch
work-queue entry back to `candidate`. Dry-run by default; pass --apply to write.

Usage:  python scripts/unquarantine_loadable.py [--apply]
"""
from __future__ import annotations
import argparse
import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
QUEUE = ROOT / "engine/card_effects/json/batch/batch_work_queue.json"
SLUG_INDEX = ROOT / "card_data/slug_index.json"
_BOLD = re.compile(r"\*\*.*?\*\*")


def _set_folder(slug: str, db: dict, default: str = "batch") -> str:
    entry = db.get(slug) or {}
    codes = sorted({
        "".join(ch for ch in ident if ch.isalpha()).lower()
        for ident in (entry.get("setIdentifiers") or [])
    })
    return codes[0] if codes else default


def _is_noop_stub(j: dict) -> bool:
    abils = j.get("abilities") or []
    return any(not (a.get("effects") or a.get("modes") or a.get("options"))
               for a in abils)


def _unsupported_multi_activate(j: dict) -> bool:
    """The engine can't yet route to one of several activated abilities on a card;
    such a card compiles but raises NotImplementedError mid-game."""
    activ = sum(1 for a in (j.get("abilities") or [])
                if (a.get("ability_type") or "").upper() in ("ACTIVATE", "INSTANT", "ACTION"))
    return activ > 1


def _fails_hygiene(slug: str, j: dict, db: dict) -> bool:
    """Empty abilities + non-keyword printed text -> the hygiene suite rejects it."""
    if j.get("abilities") or j.get("setup"):
        return False
    text = (db.get(slug, {}) or {}).get("functionalText", "") or ""
    return bool(_BOLD.sub("", text).strip(" \n\t-—,."))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    from engine.card_effects.dsl.loader import compile_card
    db = json.loads(SLUG_INDEX.read_text(encoding="utf-8"))["by_slug"]
    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    by_slug = {c["slug"]: c for c in queue}

    restored, skipped = [], []
    for f in glob.glob(str(ROOT / "engine/card_effects/json/**/*.json.quarantine"),
                       recursive=True):
        path = Path(f)
        slug = path.name.replace(".json.quarantine", "")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            skipped.append((slug, "bad json"))
            continue
        try:
            compile_card(raw)
        except Exception:
            skipped.append((slug, "still won't load"))
            continue
        if _is_noop_stub(raw):
            skipped.append((slug, "no-op stub"))
            continue
        if _unsupported_multi_activate(raw):
            skipped.append((slug, "multi activated-ability (engine gap)"))
            continue
        if _fails_hygiene(slug, raw, db):
            skipped.append((slug, "empty abilities + prose (hygiene)"))
            continue
        dest_dir = ROOT / "engine/card_effects/json" / _set_folder(slug, db)
        dest = dest_dir / f"{slug}.json"
        restored.append((slug, str(dest.relative_to(ROOT))))
        if args.apply:
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
            path.unlink()
            entry = by_slug.get(slug)
            if entry is not None:
                entry["status"] = "candidate"
                entry.pop("note", None)

    if args.apply:
        QUEUE.write_text(json.dumps(queue, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")

    print(f"{'RESTORED' if args.apply else 'WOULD RESTORE'}: {len(restored)}")
    for s, d in restored[:60]:
        print(f"  {s} -> {d}")
    print(f"\nskipped: {len(skipped)}")
    from collections import Counter
    for reason, n in Counter(r for _, r in skipped).most_common():
        print(f"  {n:4d}  {reason}")


if __name__ == "__main__":
    main()
