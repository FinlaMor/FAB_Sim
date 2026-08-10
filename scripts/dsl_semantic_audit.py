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

With --tests it audits the other direction: does each card's TEST cover its
printed text? This catches a test that passes while asserting the wrong
behaviour — exactly what a card errata produces (the Snarky Prick test kept
passing while describing a card that no longer existed). Same two rules apply,
and doubly so for tests: compare the test to the CARD TEXT, never just to the
implementation, or a matched pair of bugs (impl does X, test asserts X, both
contradict the card) rubber-stamps itself. Run it in a session separate from
whoever wrote the tests.

Usage:
  python scripts/dsl_semantic_audit.py --set hnt
  python scripts/dsl_semantic_audit.py --slug big_bully_red --verbose
  python scripts/dsl_semantic_audit.py --all --limit 25 -o docs/semantic_audit.md
  python scripts/dsl_semantic_audit.py --tests --slug snarky_prick_red   # audit tests
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

# One model for every run, by default. qwen3-coder:30b is a 30B-A3B MoE (~18 GB,
# only ~3B params active per token, so it is fast despite its size) and reasons
# markedly better than the smaller coders: on the calibration card
# put_em_in_their_place_red it flags the discard/draw mismatch that both
# qwen2.5-coder:14b and a 4B distill call "clean". It fits a 31 GB machine ALONE
# — do not also keep a second large model resident (ollama holds a model for 30
# min after use; 30b + 14b together exhausted 31 GB and got the audit OOM-killed).
DEFAULT_MODEL = "qwen3-coder:30b"

JSON_ROOT = ROOT / "engine" / "card_effects" / "json"
SLUG_INDEX = ROOT / "card_data" / "slug_index.json"
TESTS_DIR = ROOT / "tests"


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

4. Check the TRIGGER, not just the effect. If a clause names more than one \
trigger condition ("when this attacks OR DEFENDS", "whenever you gain or lose \
life"), the JSON must cover every one of them; report MISMATCH if it covers \
only some. Note that for an Action - Attack card, ability_type "PLAY" fires at \
the Attack Step and correctly implements "when this attacks" — but it does NOT \
implement "when this defends".

These keywords are implemented by the game engine itself, never by card JSON. \
Treat a bare keyword clause naming one of them as COVERED_BY_ENGINE, not MISSING:
{engine_keywords}

Activated abilities are declared by TOP-LEVEL fields, not by an effect. \
`"activation_cost": 2` and `"per_turn": 1` together implement a clause like \
"Once per Turn Action - {{r}}{{r}}: Attack." Treat such a clause as IMPLEMENTED \
when those fields are present; do not report it MISSING for lack of an effect.

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
        src = trig.read_text(encoding="utf-8")
        found |= set(re.findall(r'kw_base == "([a-z ]+)"', src))
        # Static keywords are matched by a tuple membership test rather than
        # equality — `kw_base in ("dominate", "ambush", …)`. Missing that form
        # left Ambush out of the prompt, so the auditor had no way to know the
        # engine handles it.
        for block in re.findall(r"kw_base in \(([^)]*)\)", src, re.S):
            found |= set(re.findall(r'"([a-z ]+)"', block))
    try:
        from engine.card_effects.registry import KEYWORD_STATIC_ABILITIES
        found |= set(KEYWORD_STATIC_ABILITIES)
    except Exception:
        pass
    # Always-on keywords handled in combat//play rather than the kw_base chain.
    found |= {"go again", "dominate", "intimidate", "stealth", "ward", "overpower"}
    return sorted(k.title() for k in found if k.strip())


import ast


def find_tests_for_slug(slug: str) -> str:
    """Return the source of every test function that mentions *slug*.

    Card tests are scattered across tests/*.py by behaviour, not named per
    slug, so the only reliable link is the slug string appearing in the test
    body (e.g. _card("snarky_prick_red", ...)). Imperfect — a helper that wraps
    the slug indirectly would be missed — but good enough to start, and a card
    with zero matching tests is itself a finding.
    """
    chunks: list[str] = []
    for tf in sorted(TESTS_DIR.glob("test_*.py")):
        src = tf.read_text(encoding="utf-8")
        if slug not in src:
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        lines = src.splitlines()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test"):
                seg = "\n".join(lines[node.lineno - 1: node.end_lineno])
                if slug in seg:
                    chunks.append(f"# --- {tf.name}::{node.name} ---\n{seg}")
    return "\n\n".join(chunks)


TEST_PROMPT = """\
You are auditing whether the automated TESTS for a trading-card-game card \
actually verify that the card behaves as its printed text says. You are NOT \
checking the card's implementation, and NOT checking test style.

Card: {name} ({slug})
Printed text:
\"\"\"
{text}
\"\"\"

The card's JSON implementation (context only — do not audit it):
```json
{json_content}
```

Its tests:
```python
{tests}
```

Do this exactly:

1. Split the printed text into atomic clauses (a full instruction or one \
keyword; ignore reminder text in parentheses). Some keywords are implemented by \
the game engine and need no card-specific test: {engine_keywords}.
2. For EACH clause, find a test ASSERTION that would fail if that clause were \
implemented wrongly. Status IMPLEMENTED if such an assertion exists, MISSING if \
no test asserts an observable outcome for the clause.
3. Flag status MISMATCH for any assertion whose expected value CONTRADICTS the \
printed text (e.g. text says the attack gets +4 but the test asserts +1, or the \
text says "you may" but no test covers declining).

Judge only by observable game-state outcomes (life, zones, power, counters, \
tokens). An assertion on an internal flag or queue does NOT count as covering a \
clause.

Reply with ONLY a JSON object, no prose, no fences:
{{
  "clauses": [
    {{"text": "<clause>", "implemented_by": "<test name or null>",
      "status": "IMPLEMENTED" | "MISSING" | "COVERED_BY_ENGINE" | "MISMATCH",
      "note": "<why, only for MISSING or MISMATCH>"}}
  ],
  "verdict": "COMPLETE" | "INCOMPLETE"
}}
"""


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
    output = claw.run_llm(prompt, verbose=verbose, model=model)
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


def audit_card_tests(path: Path, index: dict, claw, model: str | None,
                     verbose: bool) -> dict | None:
    """Audit whether a card's tests cover its printed text (vs its JSON)."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    slug = raw.get("slug") or path.stem
    entry = index.get(slug)
    if entry is None:
        return None
    text = (entry.get("functionalText") or "").strip()
    if not text:
        return None

    tests = find_tests_for_slug(slug)
    if not tests.strip():
        # No test mentions this card at all — a finding on its own, and no
        # point spending a model call to confirm emptiness.
        # Phrase as a full sentence so the fragment filter (which demotes short
        # or dangling clauses) keeps this as a high-confidence finding.
        return {"slug": slug, "name": entry.get("name"), "text": text,
                "clauses": [{"text": "This card has no automated test referencing its slug.",
                             "status": "MISSING",
                             "note": "no test references this card's slug"}],
                "verdict": "INCOMPLETE"}

    prompt = TEST_PROMPT.format(
        name=entry.get("name") or slug, slug=slug, text=text,
        engine_keywords=", ".join(engine_keywords()),
        json_content=json.dumps(raw, indent=2, ensure_ascii=False), tests=tests)
    output = claw.run_llm(prompt, verbose=verbose, model=model)
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

# A note that affirms the implementation is correct contradicts its own
# MISSING/MISMATCH label. Both local models do this: they reason correctly
# ("+1 on top of +3 makes 4, this matches the printed text") and then attach
# the wrong status. The prose is the reliable part, so a self-contradicting
# finding is demoted rather than believed.
_SELF_CONTRADICTING = re.compile(
    r"\b(this )?(matches|is correct|correctly implement\w*|is implemented|"
    r"which is correct|as (?:the )?(?:printed )?text)\b", re.I)


def _note_contradicts_status(clause: dict) -> bool:
    return bool(_SELF_CONTRADICTING.search(clause.get("note") or ""))


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
        def _weak(c):
            return _is_fragment(c.get("text", "")) or _note_contradicts_status(c)

        bad = [c for c in flagged if not _weak(c)]
        frags = [c for c in flagged if _weak(c)]
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
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    help=f"ollama model passed to claw-code (default: {DEFAULT_MODEL}). "
                         "Keep every run on ONE model: ollama holds each loaded "
                         "model for 30 minutes, so mixing models across runs pins "
                         "both in RAM at once.")
    ap.add_argument("-o", "--out", help="write the markdown report here")
    ap.add_argument("--json", dest="json_out", help="also write raw results as JSON")
    ap.add_argument("--no-resume", action="store_true",
                    help="ignore an existing --json cache and re-audit everything")
    ap.add_argument("--tests", action="store_true",
                    help="audit whether each card's TESTS cover its text, "
                         "instead of whether its JSON does")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    audit_fn = audit_card_tests if args.tests else audit_card

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
            # Re-apply the current post-processing rules to everything already
            # cached. A long corpus is audited over several runs, and the rules
            # improve between them — the engine-keyword list grew from 31 to 42
            # mid-corpus — so cards audited early would otherwise keep findings
            # that the current rules would have downgraded.
            for r in results:
                _downgrade_engine_keyword_findings(r)
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
        result = audit_fn(path, index, claw, args.model, args.verbose)
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
