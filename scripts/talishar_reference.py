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
import os, re, sys, json, functools
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Talishar backend to read card logic from — first that exists:
#   1. $TALISHAR_DIR  2. the latest read-only extraction (git archive of origin/main)
#   3. the user's live working copy (has local mods; may be months stale).
# Empirically ~coverage-equivalent (357 vs 361 of 467 candidates), but 2 is a
# clean, reproducible snapshot that doesn't depend on uncommitted working state.
_TAL_CANDIDATES = [
    os.environ.get("TALISHAR_DIR"),
    r"C:\tools\talishar-latest",
    r"C:\Users\Joseph\Desktop\FAB_Sim_Headless\talishar",
]
TALISHAR = Path(next((p for p in _TAL_CANDIDATES if p and Path(p).exists()),
                     _TAL_CANDIDATES[-1]))

_CASE_NEXT = re.compile(r'\s*(case\s+["\']|default\s*:)')
_FUNC = re.compile(r'\s*(?:public\s+|private\s+|static\s+)*function\s+(\w+)')


def _php_files() -> list[Path]:
    return [p for p in TALISHAR.rglob("*.php")
            if "GeneratedCardDictionaries" not in p.name]  # data, not logic


@functools.lru_cache(maxsize=1)
def build_slug_index() -> dict:
    """One-pass scan of the Talishar tree -> {slug: [{func, file, code}, ...]}.

    Cached, so per-card lookups in the pipeline are O(1) instead of re-scanning
    hundreds of PHP files each time. Handles fall-through case groups
    (`case "a": case "b": <body>`) by attaching the shared body to every label.
    """
    idx: dict[str, list[dict]] = {}
    if not TALISHAR.exists():
        return idx
    label_re = re.compile(r'case\s+"([^"]+)"\s*:')
    for php in _php_files():
        try:
            lines = php.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        rel = str(php.relative_to(TALISHAR)).replace("\\", "/")
        cur_func = "?"
        i = 0
        while i < len(lines):
            fm = _FUNC.match(lines[i])
            if fm:
                cur_func = fm.group(1)
            if not label_re.search(lines[i]):
                i += 1
                continue
            # A case GROUP: contiguous case-label lines sharing one body. Stop as
            # soon as a label line carries an inline body after its final colon.
            group, k, inline = [], i, None
            while k < len(lines) and label_re.search(lines[k]):
                group += label_re.findall(lines[k])
                tail = lines[k].rsplit(":", 1)[1].strip()
                k += 1
                if tail:
                    inline = lines[k - 1]
                    break
            if inline is not None:
                body = [inline]
            else:
                body = []
                while k < len(lines) and len(body) < 40:
                    if _CASE_NEXT.match(lines[k]) or re.match(r'\s{0,4}\}\s*$', lines[k]):
                        break
                    body.append(lines[k])
                    k += 1
            code = "\n".join(body).strip()
            for slug in group:
                idx.setdefault(slug, []).append(
                    {"func": cur_func, "file": rel, "code": code})
            i = k if k > i else i + 1
    return idx


def reference_text(slug: str, max_chars: int = 1600) -> str:
    """Talishar reference for a slug formatted for prompt injection (empty if
    none). Deduplicates identical blocks and caps length."""
    blocks = build_slug_index().get(slug, [])
    seen, parts = set(), []
    for b in blocks:
        key = (b["func"], b["code"])
        if key in seen or not b["code"]:
            continue
        seen.add(key)
        parts.append(f"# {b['func']}()\n{b['code']}")
    out = "\n".join(parts)
    return out[:max_chars]


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
    cands = [c["slug"] for c in q if c["status"] == "candidate"]
    return cands[:n] if n else cands


_BOLD = re.compile(r'\*\*[^*]+\*\*')


def _is_keyword_only(text: str) -> bool:
    """True if the card's whole text is just bolded keyword tokens (e.g.
    "**Stealth**\\n\\n**Dominate**", "**Heave 2**", "**Go again**"). Such cards
    correctly carry empty `abilities` — the keywords are handled generically by
    the engine from the card's keyword metadata, not by per-card JSON."""
    stripped = _BOLD.sub("", text or "")
    return re.sub(r"[\s\W_]+", "", stripped) == ""


def _flags(slug: str, blocks: list[dict]) -> list[str]:
    """Cheap structural divergence signals between Talishar's logic and our JSON,
    for triage. Not proof — just where to look first."""
    fl = []
    oj = our_json(slug) or ""
    try:
        abils = json.loads(oj).get("abilities", []) if oj else []
    except Exception:
        abils = []
    funcs = " ".join(b["func"] for b in blocks)
    code = " ".join(b["code"] for b in blocks)
    if not blocks:
        return ["no-talishar-logic"]  # can't cross-check (vanilla or newer set)
    # Keyword-only card (all text is engine-handled keywords) -> empty abilities is
    # correct and there is nothing card-specific to cross-check. Checked first so it
    # short-circuits the empty-abilities / hit-effect flags below.
    if _is_keyword_only(card_text(slug)):
        return ["keyword-only"]
    # ON_HIT presence must be checked against the WHOLE json: the canonical pattern
    # for "this attack gains: if it hits ..." nests the ON_HIT trigger inside an
    # INJECT_TRIGGER effect, not as a top-level ability.trigger. (Checking only
    # ability.trigger produced ~10 false positives.)
    has_on_hit = "ON_HIT" in oj or "ON_ATTACK" in oj
    # High-precision structural flags only. A `PlayAbility` heuristic was tried and
    # dropped as noise: Talishar routes many on-play / current-turn effects through
    # PlayAbility that we correctly model as STATIC or TRIGGERED ON_PLAY, so its
    # presence does not discriminate real divergences.
    if "HitEffect" in funcs and not has_on_hit:
        fl.append("talishar-has-hit-effect/our-json-no-ON_HIT")
    # Persistent turn-scoped combat effect ("whenever an attack ... this turn",
    # "until start of your next turn"). Genuine divergence only if our impl does NOT
    # register a turn/next-turn-scoped effect and instead models it as a one-shot
    # self-trigger. If the json already uses a current/next-turn construct, aligned.
    turn_scoped = any(m in oj for m in
                      ("CURRENT_TURN", "NEXT_TURN", "current_turn", "TURN_EFFECT", "LASTING"))
    if "IsCombatEffectPersistent" in funcs and "return true" in code.lower() \
            and not turn_scoped \
            and not any((a.get("ability_type") or "").upper() in ("STATIC", "WHILE_STATIC")
                        or (a.get("trigger") or "").upper() in ("ON_ATTACK",) for a in abils):
        fl.append("persistent-combat-effect/verify-scope")
    if not abils:
        fl.append("our-json-empty-abilities")
    return fl or ["looks-aligned"]


def build_report(outfile: Path) -> dict:
    idx = build_slug_index()
    slugs = _candidates(0)
    rows = []
    for s in slugs:
        blocks = idx.get(s, [])
        rows.append((s, _flags(s, blocks), blocks))
    # order: divergence flags first, then aligned, then no-logic
    def rank(r):
        f = r[1]
        if f == ["no-talishar-logic"]:
            return 2
        if f == ["looks-aligned"]:
            return 1
        return 0
    rows.sort(key=rank)
    from collections import Counter
    summ = Counter(f for _, fl, _ in rows for f in fl)
    lines = [f"# Talishar candidate cross-check ({len(slugs)} candidates)\n",
             "Second opinion from the local Talishar backend; not authoritative.\n",
             "## Flag summary", ""]
    for f, n in summ.most_common():
        lines.append(f"- **{f}**: {n}")
    lines.append("\n## Candidates (divergences first)\n")
    for s, fl, blocks in rows:
        lines.append(f"### {s}  — {', '.join(fl)}")
        lines.append(f"text: {card_text(s)!r}")
        oj = our_json(s)
        lines.append("```json\n" + (oj.strip() if oj else "(none)") + "\n```")
        if blocks:
            lines.append("Talishar:")
            lines.append("```php")
            for b in blocks:
                if b["code"]:
                    lines.append(f"// {b['func']}()\n{b['code']}")
            lines.append("```")
        lines.append("")
    outfile.write_text("\n".join(lines), encoding="utf-8")
    return dict(summ)


def main() -> None:
    if not TALISHAR.exists():
        print(f"Talishar backend not found at {TALISHAR} (set TALISHAR_DIR)")
        sys.exit(2)
    args = sys.argv[1:]
    if args and args[0] == "--report":
        out = Path(args[1]) if len(args) > 1 else (ROOT / "docs" / "talishar_candidate_review.md")
        out.parent.mkdir(parents=True, exist_ok=True)
        summ = build_report(out)
        print(f"wrote {out}")
        for f, n in sorted(summ.items(), key=lambda x: -x[1]):
            print(f"  {n:4d}  {f}")
        return
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
