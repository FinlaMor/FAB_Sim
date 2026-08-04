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


# Capitalised words that are prose, not token names (avoid false "unresolved" flags).
_STOP = {"You", "Go", "When", "If", "Each", "Target", "Deck", "Hero", "Gain",
         "Draw", "Turn", "Put", "Create", "Make", "Forge", "The", "This", "An", "A"}


def _cap_phrases(clause: str) -> list[str]:
    """Capitalised multi-word phrases in a clause, with standalone count vars (a lone
    'X') and single digits stripped so 'X Runechant' reads as 'Runechant'."""
    clause = re.sub(r"\b[A-Z0-9]\b", " ", clause)
    return re.findall(r"[A-Z][A-Za-z']+(?:\s+[A-Z][A-Za-z']+)*", clause)


def confident_token(text: str) -> str | None:
    """The single token a card confidently creates, or None (=leave for review).

    Only fires when the CREATE clause(s) name exactly one token and it is
    implemented, with NO other capitalised token candidate present. This rejects:
    multi-token / choice lists ('a Frailty, Inertia, or Bloodrot Pox token'),
    tokens created alongside an UNIMPLEMENTED one ('a Confidence and 3 Might'), and
    a token merely destroyed/tested elsewhere ('Destroy up to 3 Might tokens.
    Create a Toughness token' -> the created one, Toughness, is unimplemented -> skip).
    """
    impl: set[str] = set()
    unresolved = False
    # (a) 'create/put/forge/make ... token(s)' — everything up to 'token' is the clause.
    for m in re.finditer(r"(?:create|put|forge|make)s?\s+(.*?)\s+tokens?\b", text, re.I):
        for cap in _cap_phrases(m.group(1)):
            if cap in _STOP:
                continue
            slug = slugify(cap)
            if get_card(slug) is not None:
                impl.add(slug)
            else:
                unresolved = True  # an unimplemented token name in the create clause
    # (b) tokens named WITHOUT the word 'token' ('create a Crouching Tiger'): bound to
    # the immediately-following proper-noun phrase (prose after it stays out of scope).
    for m in re.finditer(r"(?:create|forge)s?\s+an?\s+([A-Z][A-Za-z']+(?:\s+[A-Z][A-Za-z']+)*)", text):
        if re.match(r".{0,40}?\btokens?\b", text[m.start():]):
            continue  # this occurrence is a 'token'-suffixed one -> handled by (a)
        words = m.group(1).split()
        for k in range(len(words), 0, -1):
            cand = slugify(" ".join(words[:k]))
            if get_card(cand) is not None:
                impl.add(cand)
                break
    return next(iter(impl)) if (len(impl) == 1 and not unresolved) else None


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

    hint = confident_token(text)
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
        else:  # empty -> only fill from a confident single token
            if hint:
                node["token"] = hint
                changed = True
            else:
                return "review", "empty token, no confident single token in text"

    if changed and all(not _bad(n.get("token", "")) for n in nodes):
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return "fixed", ", ".join(sorted({n["token"] for n in nodes}))
    return "review", "no confident fix"


def main() -> None:
    load_all_cards()
    db = json.loads(SLUG_INDEX.read_text(encoding="utf-8"))["by_slug"]
    q = json.loads(QUEUE.read_text(encoding="utf-8"))
    # Process candidates AND cards previously parked in needs_review for a
    # CREATE_TOKEN defect — re-running with a smarter parser can now fix some.
    by_slug = {c["slug"]: c for c in q}
    todo = [c["slug"] for c in q
            if c["status"] == "candidate"
            or (c["status"] == "needs_review" and "CREATE_TOKEN" in (c.get("note", "") or ""))]

    fixed, review, promoted = [], [], 0
    for slug in todo:
        matches = glob.glob(str(ROOT / "engine/card_effects/json" / "**" / f"{slug}.json"),
                            recursive=True)
        if not matches:
            continue
        path = Path(matches[0])
        text = (db.get(slug, {}) or {}).get("functionalText", "") or ""
        status, detail = fix_card(path, text)
        if status == "fixed":
            fixed.append((slug, detail))
            # A card fixed out of the CREATE_TOKEN needs_review bucket rejoins candidate.
            c = by_slug[slug]
            if c["status"] == "needs_review" and "CREATE_TOKEN" in (c.get("note", "") or ""):
                c["status"] = "candidate"
                c.pop("note", None)
                promoted += 1
        elif status == "review":
            review.append((slug, detail))

    QUEUE.write_text(json.dumps(q, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"FIXED {len(fixed)} cards ({promoted} promoted needs_review -> candidate):")
    for s, d in fixed:
        print(f"  {s} -> {d}")
    print(f"\nLEFT FOR REVIEW {len(review)} cards:")
    for s, d in review[:50]:
        print(f"  {s}: {d}")


if __name__ == "__main__":
    main()
