#!/usr/bin/env python3
"""Withdraw copied cards whose SOURCE was not clean.

`copy_identical_text_cards.py` reproduces a card's implementation verbatim onto
every printing with the same text. When the source has a latent defect, the copy
inherits it exactly, and one silent defect becomes three.

That is not hypothetical. The first bulk run took `audit_params` from 15
findings to 21, and the full suite then failed nine more ways -- dead flags,
invented refs, an injected trigger hiding its conditions in the string form,
unstripped conditional keywords, and cards with text but no abilities. Every
single failure was a copy inheriting something its source already had.

RATHER THAN ENUMERATE THE GUARDS -- which would miss whichever one nobody
thought of -- this reruns them and withdraws any copy that is implicated. The
first version of this script enumerated five of them and missed the sixth
(invented refs), proving its own point: the list is added to by importing each
guard's own logic, never by restating it here. A copy
is byte-identical to its source in `abilities`, so anything a guard says about
the copy it would say about the source; the copies are simply where it becomes
visible, because the ratchets are pinned at a count and the allowlists name
specific slugs.

    python scripts/prune_unsafe_copies.py --dry-run
    python scripts/prune_unsafe_copies.py --delete
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

JSON_ROOT = ROOT / "engine" / "card_effects" / "json"


def _copies():
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
        if isinstance(raw, dict) and raw.get("_copied_from"):
            out[raw["slug"]] = (path, raw)
    return out


def implicated():
    """{slug: [reason, ...]} for every card a corpus guard objects to."""
    from engine.card_effects.dsl.loader import load_all_cards
    load_all_cards()
    bad = {}

    def flag(slug, reason):
        bad.setdefault(slug, []).append(reason)

    # 1. a card with real text but nothing authored
    from tests.test_card_json_hygiene import (INDEX, KNOWN_UNIMPLEMENTED,
                                              _BOLD, CARD_FILES)
    for path in CARD_FILES:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        slug = raw.get("slug")
        entry = INDEX.get(slug)
        if entry is None or raw.get("abilities") or raw.get("setup") or raw.get("cost"):
            continue
        if slug in KNOWN_UNIMPLEMENTED:
            continue
        if _BOLD.sub("", entry.get("functionalText") or "").strip(" \n\t-—,."):
            flag(slug, "text but no abilities")

    # 2. flags nobody reads
    from tests.test_no_dead_flags import _dead_flags
    for name, slugs in _dead_flags().items():
        for slug in slugs:
            flag(slug, "dead flag %s" % name)

    # 3. a printed keyword its own text gates, not made conditional
    from tests.conditional_keyword_sweep import unstripped
    from tests.test_conditional_keyword_ratchet import WORDS
    for word, slugs in unstripped(WORDS).items():
        for slug in slugs:
            flag(slug, "unstripped conditional %s" % word)

    # 4. parameters the compiler never reads
    from scripts.audit_params import audit_node, build_index, card_files
    index = build_index()

    def walk(node, out):
        if isinstance(node, dict):
            out.extend(audit_node(node, index) or [])
            for value in node.values():
                walk(value, out)
        elif isinstance(node, list):
            for value in node:
                walk(value, out)
        return out

    for path in card_files():
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and raw.get("slug") and walk(raw.get("abilities"), []):
            flag(raw["slug"], "unread parameter")

    # 5. a ref name nothing ever writes -- the effect is a silent no-op and any
    #    gate reading it is silently false
    from tests.test_invented_refs import KNOWN_UNFIXED, _offenders
    for slug, refs in _offenders().items():
        if slug not in KNOWN_UNFIXED:
            flag(slug, "reads a ref nothing writes (%s)" % ", ".join(sorted(refs)))

    # 6. an INJECT_TRIGGER whose string form silently drops its conditions
    for path in JSON_ROOT.rglob("*.json"):
        rel = path.relative_to(JSON_ROOT)
        if path.stem.endswith("_work_queue") or any(
                p.startswith(".") or p == "needs_review" for p in rel.parts):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(raw, dict) or not raw.get("slug"):
            continue

        def scan(node):
            if isinstance(node, dict):
                if (node.get("type") == "INJECT_TRIGGER"
                        and isinstance(node.get("trigger"), str)
                        and node.get("conditions")):
                    flag(raw["slug"], "INJECT_TRIGGER string form hides conditions")
                for value in node.values():
                    scan(value)
            elif isinstance(node, list):
                for value in node:
                    scan(value)

        scan(raw.get("abilities"))
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delete", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    copies = _copies()
    bad = implicated()

    doomed = {}
    for slug, (path, raw) in copies.items():
        source = raw["_copied_from"]
        reasons = sorted(set(bad.get(slug, []) + bad.get(source, [])))
        if reasons:
            doomed[slug] = (path, source, reasons)

    print("copies: %d    implicated: %d" % (len(copies), len(doomed)))
    for slug, (_p, source, reasons) in sorted(doomed.items()):
        print("  %-34s <- %-30s %s" % (slug, source, "; ".join(reasons)))

    if args.delete:
        for slug, (path, _s, _r) in doomed.items():
            path.unlink()
        print("\nwithdrew %d copies" % len(doomed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
