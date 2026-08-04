#!/usr/bin/env python3
"""Repair candidate cards whose CREATE_TOKEN effect has an unusable token slug
(empty, or a display-cased/spaced name like "Silver" / "Seismic Surge"). These
crash a live game the moment the effect fires (require_card('')). Two safe,
high-confidence repairs, applied to the JSON:

  * non-empty but wrong-case -> slugify it, if that resolves to an implemented token.
  * empty -> read the printed text for "create ... <Token> token"; fill it IN ONLY
    when the text names exactly ONE distinct token that is implemented.

Anything ambiguous (empty with no/￫multiple token hints) is LEFT ALONE and listed
for manual review — this never guesses. Run from the repo root.
"""
from __future__ import annotations
import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine.card_effects.dsl.loader import load_all_cards, get_card

SLUG_INDEX = ROOT / "card_data/slug_index.json"
QUEUE = ROOT / "engine/card_effects/json/batch/batch_work_queue.json"


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (s or "").strip().lower()).strip("_")


def text_tokens(text: str) -> set[str]:
    """Distinct implemented token slugs named as 'create ... <Name> token(s)'."""
    out = set()
    for m in re.finditer(r"[Cc]reates?\s+(?:an?\s+|\d+\s+)?([A-Z][A-Za-z' ]+?)\s+tokens?", text):
        slug = slugify(m.group(1))
        if slug and get_card(slug) is not None:
            out.add(slug)
    return out


def _bad(tok: str) -> bool:
    return (not tok) or get_card(tok) is None


def fix_card(path: Path, text: str) -> tuple[str, str]:
    """Return (status, detail). status in {fixed, review, skip}."""
    data = json.loads(path.read_text(encoding="utf-8"))
    nodes: list[dict] = []

    def walk(o):
        if isinstance(o, dict):
            if (o.get("type") or "").upper() == "CREATE_TOKEN" and _bad(o.get("token", "")):
                nodes.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(data)
    if not nodes:
        return "skip", "no bad CREATE_TOKEN"

    hints = text_tokens(text)
    changed = False
    for node in nodes:
        tok = node.get("token", "")
        if tok:  # wrong-case
            alt = slugify(tok)
            if get_card(alt) is not None:
                node["token"] = alt
                changed = True
            else:
                return "review", f"unresolvable token {tok!r}"
        else:  # empty -> need exactly one text hint
            if len(hints) == 1:
                node["token"] = next(iter(hints))
                changed = True
            else:
                return "review", f"empty token, {len(hints)} text hints {sorted(hints)}"

    if changed and all(not _bad(n.get("token", "")) for n in nodes):
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return "fixed", ", ".join(sorted({n["token"] for n in nodes}))
    return "review", "no confident fix"


def main() -> None:
    load_all_cards()
    db = json.loads(SLUG_INDEX.read_text(encoding="utf-8"))["by_slug"]
    q = json.loads(QUEUE.read_text(encoding="utf-8"))
    cands = [c["slug"] for c in q if c["status"] == "candidate"]

    fixed, review = [], []
    for slug in cands:
        matches = glob.glob(str(ROOT / "engine/card_effects/json" / "**" / f"{slug}.json"),
                            recursive=True)
        if not matches:
            continue
        path = Path(matches[0])
        text = (db.get(slug, {}) or {}).get("functionalText", "") or ""
        status, detail = fix_card(path, text)
        if status == "fixed":
            fixed.append((slug, detail))
        elif status == "review":
            review.append((slug, detail))

    print(f"FIXED {len(fixed)} cards:")
    for s, d in fixed:
        print(f"  {s} -> {d}")
    print(f"\nLEFT FOR REVIEW {len(review)} cards:")
    for s, d in review[:40]:
        print(f"  {s}: {d}")


if __name__ == "__main__":
    main()
