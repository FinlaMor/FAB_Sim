#!/usr/bin/env python3
"""Author the pending cards whose printed text an IMPLEMENTED card already has.

Card text repeats. Colour variants of one card are the same sentence with a
different number, and unrelated cards share whole sentences outright -- "Deal 4
arcane damage to any target" is both Aether Hail and Ice Bolt. Where the text is
IDENTICAL (after substituting each card's own name), the DSL implementation is
identical too: everything that differs between the printings -- cost, pitch,
power, colour -- comes from the card DB, not from the JSON.

COPYING IS NOT AUTOMATICALLY SAFE, which is why this script holds cards back
rather than doing all of them. insult_to_injury shipped three printings of
identical text with THREE DIFFERENT implementations, and the blue one was
missing a gate the other two had; that is the failure this generator is trying
not to industrialise. Four hazards are excluded and left for a human:

  printed keywords differ   the DB grants keywords, so a source that declares
                            `conditional_keywords` for a keyword the target does
                            not print would carry a meaningless declaration --
                            or worse, strip something the target really has.
  card types differ         a Block behaves differently from an Action even
                            reading the same sentence.
  hero cards                heroes carry `setup` (weapon zones) and activation
                            metadata that is about the printing, not the text.
  source has card-level     activation_cost / per_turn / cost / cost_modifiers
  metadata and the names    are DSL-authoritative and about that specific card.
  differ                    Safe to carry between colour variants of one card,
                            not between two cards that merely read alike.
  source has unread         audit_params findings mean the source has a
  parameters                parameter the compiler never looks at -- a clause
                            that silently does nothing. Copying it turns one
                            defective card into three. Found the hard way: the
                            first run of this script took audit_params from 15
                            findings to 21 by faithfully reproducing
                            shield_bash's and bonds_of_ancestry's.

Usage:
    python scripts/copy_identical_text_cards.py --dry-run
    python scripts/copy_identical_text_cards.py --write
    python scripts/copy_identical_text_cards.py --held-back
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.audit_params import audit_node, build_index, card_files  # noqa: E402
from scripts.remaining_estimate import (implemented_slugs, is_keyword_only,  # noqa: E402
                                        signature, text_of)

JSON_ROOT = ROOT / "engine" / "card_effects" / "json"
_COLOUR = re.compile(r"_(red|yellow|blue)$")
#: Card-level fields that describe THIS printing rather than its text.
_META = ("activation_cost", "per_turn", "setup", "cost", "cost_modifiers")


def _base(slug):
    return _COLOUR.sub("", slug)


def _flagged_by_audit_params():
    """Slugs with a parameter the compiler never reads.

    An unread parameter fails exactly like an invented type -- nothing errors,
    nothing warns, the clause quietly does nothing -- and is invisible to the
    type-name audit. Copying such a card multiplies a silent defect, so those
    sources are held back until they are fixed.
    """
    index = build_index()
    flagged = set()
    for path in card_files():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(raw, dict) or not raw.get("slug"):
            continue
        findings = []
        _walk_all(raw.get("abilities"), index, findings)
        if findings:
            flagged.add(raw["slug"])
    return flagged


def _walk_all(node, index, out):
    if isinstance(node, dict):
        try:
            out.extend(audit_node(node, index, ()) or [])
        except TypeError:
            out.extend(audit_node(node, index) or [])
        for value in node.values():
            _walk_all(value, index, out)
    elif isinstance(node, list):
        for value in node:
            _walk_all(value, index, out)


def _paths():
    out = {}
    for path in JSON_ROOT.rglob("*.json"):
        rel = path.relative_to(JSON_ROOT)
        if path.stem.endswith("_work_queue") or any(
                p.startswith(".") or p == "needs_review" for p in rel.parts):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(raw, dict) and raw.get("slug"):
            out[raw["slug"]] = path
    return out


def _set_dir(entry, paths, source_slug):
    """Where the new file goes: the source's directory when the target was
    printed in that set, else the target's own first set code."""
    src_dir = paths[source_slug].parent
    codes = {"".join(c for c in i if c.isalpha()).lower()
             for i in (entry.get("setIdentifiers") or [])}
    if src_dir.name in codes:
        return src_dir
    for code in sorted(codes):
        candidate = JSON_ROOT / code
        if candidate.is_dir():
            return candidate
    return src_dir


def plan():
    idx = json.loads((ROOT / "card_data" / "slug_index.json")
                     .read_text(encoding="utf-8"))["by_slug"]
    have = implemented_slugs()
    paths = _paths()

    playable = {s: e for s, e in idx.items()
                if not e.get("isCardBack") and not e.get("isExpansionSlot")}
    pending = {s: e for s, e in playable.items() if s not in have}
    substantive = {s: e for s, e in pending.items()
                   if text_of(e) and not is_keyword_only(e)}

    by_text = collections.defaultdict(list)
    for slug in have:
        entry = idx.get(slug)
        if entry and text_of(entry):
            by_text[signature(entry, False)].append(slug)

    flagged = _flagged_by_audit_params()

    todo, held = [], []
    for slug, entry in sorted(substantive.items()):
        sources = by_text.get(signature(entry, False))
        if not sources:
            continue
        source = sorted(sources)[0]
        src_entry = idx[source]
        raw = json.loads(paths[source].read_text(encoding="utf-8"))

        reasons = []
        if ({str(k).lower() for k in (entry.get("keywords") or [])}
                != {str(k).lower() for k in (src_entry.get("keywords") or [])}):
            reasons.append("printed keywords differ")
        if (entry.get("types") or []) != (src_entry.get("types") or []):
            reasons.append("card types differ")
        if "Hero" in (entry.get("types") or []) or "Hero" in (src_entry.get("types") or []):
            reasons.append("hero card")
        if _base(slug) != _base(source) and any(k in raw for k in _META):
            reasons.append("source carries card-level metadata and the names differ")
        if source in flagged:
            reasons.append("source has unread parameters (audit_params)")

        (held if reasons else todo).append((slug, source, reasons, raw, entry))
    return todo, held, paths


def build(slug, source, raw, entry):
    out = {"slug": slug}
    # Card-level metadata travels only between printings of the SAME card.
    if _base(slug) == _base(source):
        for key in _META:
            if key in raw:
                out[key] = raw[key]
    if raw.get("conditional_keywords"):
        out["conditional_keywords"] = raw["conditional_keywords"]
    out["abilities"] = raw["abilities"]
    out["_comment"] = (
        "Implementation copied verbatim from %s, whose printed functional text "
        "is identical to this card's once each card's own name is substituted "
        "out. Everything that differs between them -- cost, pitch, power, "
        "colour -- comes from the card DB, not from this file, so the DSL is "
        "the same card twice.\n\nTHE COPY IS PINNED, not trusted: "
        "tests/test_copied_card_implementations.py asserts that these abilities "
        "still match %s's and that the two printed texts still agree, so a "
        "later edit to one cannot silently leave the other behind. That is the "
        "insult_to_injury failure -- three printings of one sentence with three "
        "different implementations, the blue one missing a gate the others had."
        % (source, source))
    out["_copied_from"] = source
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--held-back", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    todo, held, paths = plan()

    if args.held_back:
        print("HELD BACK FOR A HUMAN (%d)\n" % len(held))
        for slug, source, reasons, _raw, _entry in held:
            print("  %-34s <- %-30s %s" % (slug, source, "; ".join(reasons)))
        return 0

    print("copyable now: %d    held back: %d" % (len(todo), len(held)))
    if not args.write:
        for slug, source, _r, _raw, _e in todo[:15]:
            print("  %-34s <- %s" % (slug, source))
        print("  ...")
        return 0

    written = 0
    for slug, source, _reasons, raw, entry in todo:
        target_dir = _set_dir(entry, paths, source)
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / (slug + ".json")
        if path.exists():
            continue
        path.write_text(json.dumps(build(slug, source, raw, entry),
                                   indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
        written += 1
    print("wrote %d card files" % written)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
