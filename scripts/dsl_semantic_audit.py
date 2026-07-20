#!/usr/bin/env python3
"""Semantic audit: does a card's JSON implement every clause of its printed text?

The other two layers cannot answer this question.
  - tests/test_card_json_hygiene.py proves the JSON is well-formed.
  - scripts/dsl_coverage.py proves the effects actually execute.
Neither notices that Big Bully wrote "+4 power" where the card doubles its
base, or that Headbutt implemented its attack clause and silently dropped its
Crush clause. Both are well-formed, both execute, both are wrong.

The technique is clause enumeration, not "does this look right?". A model asked
to judge correctness answers "yes" almost unconditionally; a model asked to
enumerate every clause and name the effect implementing each one has to do the
work, and the clauses it cannot map are the finding.

Two hard rules:

1. THIS SCRIPT NEVER EDITS CARD JSON. It writes a report of suspicions for a
   human to triage. scripts/auto_implement_wtr.py already has a pass that
   auto-applies model corrections; that is an author grading its own homework,
   and it is how wrong-but-plausible implementations become permanent.

2. Run it against cards written in a *different* session from the one auditing.
   A model re-reading its own work in the same context re-derives its original
   misreading and confirms it.

Usage:
  python scripts/dsl_semantic_audit.py --set hnt
  python scripts/dsl_semantic_audit.py --slug big_bully_red --verbose
  python scripts/dsl_semantic_audit.py --all --limit 25 -o docs/semantic_audit.md
"""
from __future__ import annotations

import argparse
import datetime as _dt
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

JSON_ROOT = ROOT / "engine" / "card_effects" / "json"
SLUG_INDEX = ROOT / "card_data" / "slug_index.json"


def _auto_impl():
    """Reuse the existing claw-code driver rather than a second LLM path."""
    spec = importlib.util.spec_from_file_location(
        "auto_implement_wtr", ROOT / "scripts" / "auto_implement_wtr.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PROMPT = """\
You are auditing whether a trading-card-game card's JSON implementation covers \
everything its printed rules text says. You are NOT checking DSL syntax.

Card: {name} ({slug})
Printed text:
\"\"\"
{text}
\"\"\"

Its JSON implementation:
```json
{json_content}
```

Do this exactly:

1. Split the printed text into atomic clauses. A clause is one COMPLETE \
instruction or one keyword — a full sentence or independent sub-sentence.

   A condition and the effect it governs are ONE clause, never two. \
"If this deals 4 or more damage to a hero, they discard a card" is a single \
clause; do not emit "If this deals 4 or more damage to a hero" on its own. \
Likewise never emit a bare fragment such as "If you do", "this combat chain", \
"the attacking hero", "Attack", or "{{p}}" as a clause. If a fragment cannot \
stand alone as an instruction, it belongs to the neighbouring clause.

   Ignore pure reminder text in parentheses.
2. For EACH clause, name the specific JSON effect(s)/ability that implement it, \
or say NOTHING if no part of the JSON implements it.
3. Separately flag any clause where the JSON does something related but \
QUANTITATIVELY OR SEMANTICALLY DIFFERENT (e.g. text says "double its base \
power", JSON adds a flat +4; text says "choose one", JSON picks at random; \
text says "you may", JSON does it unconditionally).

These keywords are implemented by the game engine itself, never by card JSON. \
Treat a bare keyword clause naming one of them as COVERED_BY_ENGINE, not MISSING:
{engine_keywords}

Numeric modifiers in an effects list STACK — they are applied in sequence, not \
chosen between. A card reading "gets +3{{p}}; if the hero is marked, instead it \
gets +4{{p}}" is CORRECTLY implemented as +3 unconditionally followed by a \
further +1 conditional on marked, because 3+1=4. Add the modifiers up before \
calling anything a MISMATCH.

Reply with ONLY a JSON object, no prose, no markdown fences:
{{
  "clauses": [
    {{"text": "<clause>", "implemented_by": "<effect type or null>",
      "status": "IMPLEMENTED" | "MISSING" | "COVERED_BY_ENGINE" | "MISMATCH",
      "note": "<why, only for MISSING or MISMATCH>"}}
  ],
  "verdict": "COMPLETE" | "INCOMPLETE"
}}
"""


def _slug_index() -> dict:
    raw = json.loads(SLUG_INDEX.read_text(encoding="utf-8"))
    return raw.get("by_slug", raw)


def engine_keywords() -> list[str]:
    """Keywords the engine implements, read from the code rather than hardcoded.

    A hardcoded list drifts: the first version of this prompt omitted Piercing,
    so the auditor reported Hunter's Klaive's "Piercing 1" as an unimplemented
    clause when the engine handles it. Deriving the list keeps the prompt
    honest as keywords are added.
    """
    found: set[str] = set()
    trig = ROOT / "engine" / "card_effects" / "triggers" / "triggers.py"
    if trig.exists():
        found |= set(re.findall(r'kw_base == "([a-z ]+)"', trig.read_text(encoding="utf-8")))
    try:
        from engine.card_effects.registry import KEYWORD_STATIC_ABILITIES
        found |= set(KEYWORD_STATIC_ABILITIES)
    except Exception:
        pass
    # Always-on keywords handled in combat//play rather than the kw_base chain.
    found |= {"go again", "dominate", "intimidate", "stealth", "ward", "overpower"}
    return sorted(k.title() for k in found if k.strip())


def card_files(set_code: str | None, slug: str | None) -> list[Path]:
    paths = []
    for path in sorted(JSON_ROOT.rglob("*.json")):
        rel = path.relative_to(JSON_ROOT)
        if path.stem.endswith("_work_queue") or any(p.startswith(".") for p in rel.parts):
            continue
        if path.parent.name == "tokens":
            continue
        if set_code and path.parent.name != set_code:
            continue
        if slug and path.stem != slug:
            continue
        paths.append(path)
    return paths


def audit_card(path: Path, index: dict, claw, model: str | None,
               verbose: bool) -> dict | None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    slug = raw.get("slug") or path.stem
    entry = index.get(slug)
    if entry is None:
        return None
    text = (entry.get("functionalText") or "").strip()
    if not text:
        return None  # vanilla card, nothing to audit

    prompt = PROMPT.format(name=entry.get("name") or slug, slug=slug, text=text,
                           engine_keywords=", ".join(engine_keywords()),
                           json_content=json.dumps(raw, indent=2, ensure_ascii=False))
    output = claw.run_claw(prompt, verbose=verbose, model=model)
    if output == "CLAW_TIMEOUT" or output.startswith("CLAW_ERROR"):
        return {"slug": slug, "error": output}

    cleaned = re.sub(r"```(?:json)?\s*", "", output)
    cleaned = re.sub(r"```\s*", "", cleaned).strip()
    match = re.search(r"\{[\s\S]+\}", cleaned)
    if not match:
        return {"slug": slug, "error": "no JSON in model output", "raw": cleaned[:400]}
    try:
        result = json.loads(match.group())
    except json.JSONDecodeError as exc:
        return {"slug": slug, "error": f"unparseable model output: {exc}",
                "raw": cleaned[:400]}
    result["slug"] = slug
    result["name"] = entry.get("name")
    result["text"] = text
    _downgrade_engine_keyword_findings(result)
    return result


def _downgrade_engine_keyword_findings(result: dict) -> None:
    """Relabel bare-keyword clauses the model wrongly marked MISSING.

    Both local models understand these keywords are engine-implemented — one
    said so in the note while still marking the clause MISSING. The status
    label is the unreliable part, and it is over a known finite set, so it is
    computed here rather than trusted from the model.
    """
    keywords = {k.lower() for k in engine_keywords()}
    for clause in result.get("clauses", []):
        if clause.get("status") not in ("MISSING", "MISMATCH"):
            continue
        # Strip markdown, trailing reminder numbers ("Piercing 1"), punctuation.
        bare = re.sub(r"[*_`]", "", clause.get("text") or "").strip()
        bare = re.sub(r"\s*\d+\s*$", "", bare).strip(" .-—'\"").lower()
        if bare in keywords:
            was = clause["status"]
            clause["status"] = "COVERED_BY_ENGINE"
            clause["note"] = f"engine keyword (auto-corrected from {was})"


_SUBORDINATE = re.compile(r"^(if|when|whenever|then|and|or|instead)\b", re.I)


def _is_fragment(text: str) -> bool:
    """True if a clause is too incomplete to be an instruction on its own.

    The auditor over-splits conditionals, emitting halves like "If you do",
    "this combat chain", or "{p}" as clauses and then reporting them as
    unimplemented. These are sorted into a low-confidence bucket rather than
    dropped — a suppressed real finding costs more than a noisy one.
    """
    bare = re.sub(r"[*_`]", "", text or "").strip()
    words = bare.split()
    if len(words) <= 3:
        return True
    # A dangling condition: opens with a subordinating word and never reaches
    # the effect it governs. Every real finding observed so far carries the
    # comma that separates condition from effect ("If the hero is marked, this
    # costs {r} less"), so the missing comma is the tell regardless of length.
    if _SUBORDINATE.match(bare) and "," not in bare:
        return True
    return False


def render(results: list[dict]) -> str:
    today = _dt.date.today().isoformat()
    findings, errors, clean, weak = [], [], [], []
    for r in results:
        if r.get("error"):
            errors.append(r)
            continue
        flagged = [c for c in r.get("clauses", [])
                   if c.get("status") in ("MISSING", "MISMATCH")]
        bad = [c for c in flagged if not _is_fragment(c.get("text", ""))]
        frags = [c for c in flagged if _is_fragment(c.get("text", ""))]
        if frags:
            weak.append((r, frags))
        (findings if bad else clean).append((r, bad))

    lines = [f"# DSL semantic audit — {today}", "",
             "Model-generated *suspicions*, not verified defects. Each finding is a",
             "clause the auditor could not map to an implementing effect. Confirm",
             "against the card text and the CR before changing anything.", "",
             f"- cards audited: {len(results)}",
             f"- cards with at least one suspect clause: {len(findings)}",
             f"- cards clean: {len(clean)}",
             f"- audit errors: {len(errors)}", ""]

    if findings:
        lines += ["## Suspect clauses", ""]
        for r, bad in findings:
            lines.append(f"### {r.get('name') or r['slug']} (`{r['slug']}`)")
            lines.append("")
            lines.append(f"> {r.get('text','').replace(chr(10), ' ')}")
            lines.append("")
            for c in bad:
                lines.append(f"- **{c.get('status')}** — {c.get('text','')!r}")
                if c.get("note"):
                    lines.append(f"  - {c['note']}")
            lines.append("")

    if weak:
        lines += ["## Low confidence — probable clause fragments", "",
                  "The auditor split a conditional and flagged half of it. Kept here",
                  "rather than dropped, but check the high-confidence list first.", ""]
        for r, frags in weak:
            labels = ", ".join(f"{c.get('status')}: {(c.get('text') or '')[:40]!r}"
                               for c in frags)
            lines.append(f"- `{r['slug']}` — {labels}")
        lines.append("")

    if errors:
        lines += ["## Audit errors", ""]
        for r in errors:
            lines.append(f"- `{r['slug']}`: {r['error']}")
        lines.append("")

    if clean:
        lines += ["## Clean", "",
                  ", ".join(f"`{r['slug']}`" for r, _ in clean), ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--set", dest="set_code", help="audit one set folder")
    g.add_argument("--slug", help="audit a single card")
    g.add_argument("--all", action="store_true", help="audit every implemented card")
    ap.add_argument("--limit", type=int, help="stop after N cards")
    ap.add_argument("--model", help="model override passed to claw-code")
    ap.add_argument("-o", "--out", help="write the markdown report here")
    ap.add_argument("--json", dest="json_out", help="also write raw results as JSON")
    ap.add_argument("--no-resume", action="store_true",
                    help="ignore an existing --json cache and re-audit everything")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    paths = card_files(args.set_code, args.slug)
    if not paths:
        print("no matching cards", file=sys.stderr)
        return 1

    # Resume: a long run that dies should not be lost. Results are appended to
    # the JSON sidecar after each card and already-audited slugs are skipped.
    cache_path = Path(args.json_out) if args.json_out else None
    results: list[dict] = []
    done: set[str] = set()
    if cache_path and cache_path.exists() and not args.no_resume:
        try:
            results = json.loads(cache_path.read_text(encoding="utf-8"))
            done = {r.get("slug") for r in results if not r.get("error")}
            print(f"resuming: {len(done)} cards already audited", file=sys.stderr)
        except json.JSONDecodeError:
            print("cache unreadable, starting fresh", file=sys.stderr)

    # --limit caps REMAINING work, not the raw file list. Applying it before
    # the resume-skip made chunked runs useless: with 64 cards cached,
    # `--limit 20` would consider only the first 20 files, find them all
    # cached, and do nothing. Chunking is how a run survives a duration cap.
    todo = [p for p in paths if p.stem not in done]
    if args.limit:
        todo = todo[: args.limit]
    if not todo:
        print(f"nothing to do: all {len(paths)} cards already audited", file=sys.stderr)

    claw = _auto_impl() if todo else None
    index = _slug_index() if todo else {}
    for i, path in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {path.stem}  ({len(done) + i}/{len(paths)} overall)",
              file=sys.stderr)
        result = audit_card(path, index, claw, args.model, args.verbose)
        if result is not None:
            results.append(result)
            if cache_path:
                cache_path.write_text(json.dumps(results, indent=2, ensure_ascii=False),
                                      encoding="utf-8")

    report = render(results)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
