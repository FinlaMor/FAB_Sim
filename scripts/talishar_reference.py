#!/usr/bin/env python3
"""Tier-1 Talishar cross-check: extract a card's effect logic from a local
Talishar backend as a REFERENCE ORACLE, to cross-check our DSL card JSON during
candidate verification.

Talishar keys its per-card logic by the SAME slug we use (`case "sink_below_red":`
in switch($cardID) blocks), spread across per-set/class files under
CardDictionaries/ plus shared ability files. So the join is a direct slug match —
no card-id mapping needed. For a slug we collect every `case "<slug>":` block and
the function it lives in (cost / is-instant / play-ability / hit-effect / combat).

NOTE: Talishar is a SECOND OPINION, not ground truth — its own README says it "may
have bugs ... should not be used as an indication of how the game works." A
divergence flags a card for review; it does not prove our impl is wrong.

Usage:
  python scripts/talishar_reference.py <slug> [<slug> ...]
  python scripts/talishar_reference.py --candidates N   # first N batch candidates
  TALISHAR_DIR=/path/to/talishar  (default: the local backend on the desktop)
"""
from __future__ import annotations
import os, re, sys, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TALISHAR = Path(os.environ.get(
    "TALISHAR_DIR", r"C:\Users\Joseph\Desktop\FAB_Sim_Headless\talishar"))

_CASE_NEXT = re.compile(r'\s*(case\s+["\']|default\s*:)')
_FUNC = re.compile(r'\s*(?:public\s+|private\s+|static\s+)*function\s+(\w+)')


def _php_files() -> list[Path]:
    return [p for p in TALISHAR.rglob("*.php")
            if "GeneratedCardDictionaries" not in p.name]  # data, not logic


def extract_for_slug(slug: str) -> list[dict]:
    """Every `case "<slug>":` block in the Talishar PHP tree, with its function."""
    out = []
    needle = f'"{slug}"'
    case_re = re.compile(rf'case\s+"{re.escape(slug)}"\s*:')
    for php in _php_files():
        try:
            lines = php.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        if needle not in "\n".join(lines):
            continue
        for i, line in enumerate(lines):
            if not case_re.search(line):
                continue
            func = "?"
            for j in range(i, -1, -1):
                m = _FUNC.match(lines[j])
                if m:
                    func = m.group(1)
                    break
            # Body: this line, then following lines until the next case/default
            # or the switch closes. Inline `case "x": return ...;` stays one line.
            block = [lines[i]]
            after_colon = line.split(":", 1)[1].strip() if ":" in line else ""
            if not after_colon:  # multi-line body
                k = i + 1
                while k < len(lines) and len(block) < 40:
                    if _CASE_NEXT.match(lines[k]) or re.match(r'\s{0,4}\}\s*$', lines[k]):
                        break
                    block.append(lines[k])
                    k += 1
            out.append({"file": str(php.relative_to(TALISHAR)).replace("\\", "/"),
                        "func": func, "code": "\n".join(block).strip()})
    return out


def our_json(slug: str) -> str | None:
    import glob
    for p in glob.glob(str(ROOT / "engine" / "card_effects" / "json" / "**" / f"{slug}.json"),
                       recursive=True):
        return Path(p).read_text(encoding="utf-8")
    # maybe quarantined
    for p in glob.glob(str(ROOT / "engine" / "card_effects" / "json" / "**" / f"{slug}.json.quarantine"),
                       recursive=True):
        return Path(p).read_text(encoding="utf-8")
    return None


def card_text(slug: str) -> str:
    try:
        db = json.load(open(ROOT / "card_data" / "slug_index.json", encoding="utf-8"))["by_slug"]
        return db.get(slug, {}).get("functionalText", "") or ""
    except Exception:
        return ""


def report(slug: str) -> None:
    print("=" * 78)
    print(f"CARD: {slug}")
    print(f"TEXT: {card_text(slug)!r}")
    oj = our_json(slug)
    print("\n--- OUR DSL JSON ---")
    print(oj.strip() if oj else "(not found)")
    refs = extract_for_slug(slug)
    print(f"\n--- TALISHAR REFERENCE ({len(refs)} logic block(s)) ---")
    if not refs:
        print("(no per-card logic found — vanilla card, or not in this Talishar build)")
    for r in refs:
        print(f"\n# {r['func']}()  [{r['file']}]")
        print(r["code"])


def _candidates(n: int) -> list[str]:
    q = json.load(open(ROOT / "engine/card_effects/json/batch/batch_work_queue.json",
                       encoding="utf-8"))
    return [c["slug"] for c in q if c["status"] == "candidate"][:n]


def main() -> None:
    if not TALISHAR.exists():
        print(f"Talishar backend not found at {TALISHAR} (set TALISHAR_DIR)")
        sys.exit(2)
    args = sys.argv[1:]
    if args and args[0] == "--candidates":
        slugs = _candidates(int(args[1]) if len(args) > 1 else 5)
    else:
        slugs = args
    if not slugs:
        print(__doc__)
        sys.exit(1)
    for s in slugs:
        report(s)


if __name__ == "__main__":
    main()
