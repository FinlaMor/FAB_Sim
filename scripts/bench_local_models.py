#!/usr/bin/env python3
"""Rank local models by how close their draft is to the ACCEPTED implementation.

Two earlier benchmarks here failed, both the tool's fault rather than the
models':

  - the easy one TOLD the model the rule it was being tested on, so all three
    scored 100% and the ranking collapsed to speed;
  - the hard one graded a FAB_Sim-internal convention (SOURCE_IS_ATTACK, which
    only loader.conditional_keywords defines) that was never in the prompt, so
    all three failed the same item and it still did not discriminate.

This one grades against ground truth that exists independently of the prompt:
cards already implemented, reviewed, and covered by behavioural tests in the
repo. The model gets the same DSL_REFERENCE.md the real pipeline gives it and
is scored on whether it reaches for the same effect and condition TYPES the
accepted answer uses.

Scoring is type-level, not byte-level, on purpose. Two authors can spell the
same card differently and both be right; what actually goes wrong in practice
is a MISSING condition (a gate that never fires) or a wrong effect type, and
both show up as a type-set difference.

WHAT THE PROMPT CONTAINS is itself a variable, and probably a bigger one than
the model:

  (default)  DSL_REFERENCE.md + printed text + type + printed keywords
  --notes    + the card's official release notes. The real draft queue DOES
             inline these, for the 3612 slugs that have them.
  --cr       + keyword-retrieved extracts from the comprehensive rules. The
             real pipeline inlines NONE of this: the agent prompt only points
             at docs/ref/ and relies on the agent having file tools, so a
             tool-less local pipeline would get none of it at all.

    python bench_real.py --n 6 --ctx 24576 --notes --cr qwen3-coder:30b
"""
from __future__ import annotations

import json
import random
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(r"C:/Users/Joseph/Desktop/FAB_Sim")
JSON_ROOT = REPO / "engine" / "card_effects" / "json"
OLLAMA = "http://localhost:11434/api/generate"

WITH_NOTES = "--notes" in sys.argv
WITH_CR = "--cr" in sys.argv
# ORACLE, not a fair arm: feeds the accepted answer's type list as if a
# perfect triage pass had produced it. The real draft prompt DOES carry
# primitives_the_triage_pass_identified, so this measures the ceiling that
# better triage buys the drafter -- and how much of the pipeline's quality
# is triage rather than drafting.
ORACLE = "--oracle-primitives" in sys.argv
THINK = "--think" in sys.argv
# Few-shot is the ONLY intervention that improved TRIAGE (+11 recall,
# F1 39 -> 49) where a bigger model, the release notes, the comprehensive
# rules and parameter signatures were each worth zero. The drafter never
# got the same arm, and the drafter is where the JSON is actually written.
FEWSHOT = "--fewshot" in sys.argv
SHOTS = (int(sys.argv[sys.argv.index("--shots") + 1])
         if "--shots" in sys.argv else 2)
# Vary WHICH examples, not just how many. A non-overlapping range once
# looked like proof that example COUNT mattered for triage and turned out
# to be one unhelpful example. Ranges prove two conditions differ, never
# why, so the example set has to be varied before any effect is
# attributed to few-shot as a category.
SHOT_OFFSET = (int(sys.argv[sys.argv.index("--shot-offset") + 1])
               if "--shot-offset" in sys.argv else 0)

_RNRAW = json.loads(
    (REPO / "card_data" / "release_notes.json").read_text(encoding="utf-8"))
_RN = _RNRAW.get("by_slug") or _RNRAW
_CR = (REPO / "docs" / "ref" / "en-fab-cr-comprehensive-rules.txt").read_text(
    encoding="utf-8", errors="replace")


def notes_for(slug):
    return (_RN.get(slug, {}) or {}).get("notes", []) or []


def _cr_sections():
    """Index the CR by numbered section, e.g. ('8.3.5', 'Go again').

    The document is uniformly structured -- a numbered heading, then the rule
    and its lettered clauses -- so a keyword's rule can be retrieved exactly
    instead of approximately. 160 sections, and every keyword tried resolves.
    """
    import re
    head = re.compile(r"^(\d+\.\d+\.\d+)\s+([A-Z][A-Za-z' ]{2,40})$")
    nxt = re.compile(r"^\d+\.\d+\.\d+\s")
    out, cur = {}, None
    for line in _CR.splitlines():
        s = line.strip()
        m = head.match(s)
        if m:
            cur = (m.group(1), m.group(2).strip())
            out[cur] = []
        elif cur and s:
            if nxt.match(s) and not s.startswith(cur[0]):
                cur = None
                continue
            out[cur].append(line.rstrip())
    return out


_CR_SECTIONS = _cr_sections()


def _norm(s):
    """'GoAgain' and 'Go again' are the same keyword; the card DB spells them
    differently from the rules document."""
    import re
    return re.sub(r"[^a-z]", "", re.sub(r"(?<=[a-z])(?=[A-Z])", " ",
                                        str(s or "")).lower())


def cr_excerpts(text, keywords, budget=6000):
    """The rules sections for THIS card's keywords, and nothing else.

    The CR is 270KB, ~70k tokens: too big to inline, which is why the agent
    prompt only POINTS at it and a tool-less local pipeline gets none of it.

    An earlier version of this matched lines containing common words ("hits",
    "attacks"), which pulled ~5.7KB of loosely-related text per card and made
    recall WORSE than no rules at all -- dilution, not evidence. Retrieving the
    keyword's own section instead gives roughly 500 characters of exactly the
    rule that governs the card.
    """
    want = {_norm(k) for k in (keywords or []) if str(k).strip()}
    if not want:
        return ""
    out, used = [], 0
    for (num, title), body in _CR_SECTIONS.items():
        if _norm(title) not in want:
            continue
        block = f"{num} {title}\n" + "\n".join(body)
        if used + len(block) > budget:
            break
        out.append(block)
        used += len(block)
    return "\n\n".join(out)


def details_in(node, out=None, ctype=None):
    """(type, key, value) triples -- the DETAIL inside each node.

    Type recall cannot see the difference between a token created for yourself
    and one created for the opponent: both are CREATE_TOKEN. But that
    difference is the whole of Civic Duty, whose release note says in as many
    words "You may not choose yourself to create the Vigor token for."

    So type recall is blind to precisely what the release notes and the
    comprehensive rules affect -- which player, which amount, which duration --
    and measuring notes with it was measuring the wrong thing. This is the
    field-level companion: it sees ("CREATE_TOKEN", "player", "OPPONENT").
    """
    out = set() if out is None else out
    if isinstance(node, dict):
        t = node.get("type")
        here = t.upper() if isinstance(t, str) else ctype
        for k, v in node.items():
            if k == "type":
                continue
            if isinstance(v, (str, int, float, bool)) and here:
                out.add((here, k, str(v).upper()))
            else:
                details_in(v, out, here)
    elif isinstance(node, list):
        for v in node:
            details_in(v, out, ctype)
    return out


def types_in(node, out=None):
    out = set() if out is None else out
    if isinstance(node, dict):
        t = node.get("type")
        if isinstance(t, str):
            out.add(t.upper())
        for v in node.values():
            types_in(v, out)
    elif isinstance(node, list):
        for v in node:
            types_in(v, out)
    return out


def _pool(seed=7):
    idx = json.loads(
        (REPO / "card_data" / "slug_index.json").read_text(encoding="utf-8"))["by_slug"]
    pool = []
    for p in JSON_ROOT.rglob("*.json"):
        rel = p.relative_to(JSON_ROOT)
        if p.stem.endswith("_work_queue") or any(x.startswith(".") for x in rel.parts):
            continue
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(raw, dict) or not raw.get("abilities"):
            continue
        e = idx.get(raw.get("slug")) or {}
        text = e.get("functionalText") or ""
        want = types_in(raw.get("abilities"))
        # A card with no gate cannot demonstrate a missing gate, and gates are
        # where the defects live.
        if not text or len(want) < 2:
            continue
        pool.append((raw["slug"], e.get("typeText") or "", text, want,
                     e.get("keywords") or [], details_in(raw.get("abilities"))))
    random.Random(seed).shuffle(pool)
    return pool


def load_cards(n, seed=7):
    return _pool(seed)[:n]


def draft_examples(n_test, k=2, seed=7):
    """Whole worked implementations, drawn from BEYOND the scored slice.

    Triage examples showed card text -> a list of type names. The drafter has
    to produce a JSON OBJECT, so its examples are the accepted implementations
    in full. Taken from indices n_test.. of the same shuffled pool, so they are
    real reviewed cards and provably disjoint from the ones being scored.
    """
    out = []
    start = n_test + SHOT_OFFSET
    for slug, ttext, text, want, kws, want_d in _pool(seed)[start:start + k]:
        path = [q for q in JSON_ROOT.rglob(f"{slug}.json")
                if not any(x.startswith(".") for x in q.parts)]
        if not path:
            continue
        raw = json.loads(path[0].read_text(encoding="utf-8"))
        out.append((slug, ttext, text, kws,
                    json.dumps({"slug": slug, "abilities": raw["abilities"]},
                               indent=1)))
    return out


def ask(model, prompt, ctx, timeout=3600):
    payload = {"model": model, "prompt": prompt, "stream": False,
               # A reasoning model spends its budget THINKING first. At 900
               # tokens qwen3.8:27b produced 3969 characters of thinking, an
               # empty response and done_reason "length" -- which this harness
               # scored as "no usable JSON", i.e. as a model that cannot author
               # a card. The budget has to cover the trace AND the answer.
               "options": {"temperature": 0.1, "num_ctx": ctx,
                           "num_predict": 4000}}
    # Reasoning models here think by DEFAULT, and qwen3.8:27b spends the whole
    # token budget on the trace: 3969 characters of thinking, an empty
    # response, done_reason "length". Scored naively that reads as "cannot
    # author a card" for a model that is working fine. Thinking is therefore
    # explicit, and off unless asked for.
    payload["think"] = bool(THINK)
    req = urllib.request.Request(OLLAMA, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def extract(text):
    d, start = 0, None
    for i, ch in enumerate(text or ""):
        if ch == "{":
            if d == 0:
                start = i
            d += 1
        elif ch == "}":
            d -= 1
            if d == 0 and start is not None:
                try:
                    return json.loads(text[start:i + 1])
                except Exception:
                    start = None
    return None


def build_prompt(ref, slug, ttext, text, kws, want=None, shots=()):
    parts = [
        "You author Flesh and Blood cards as JSON for a rules engine.",
        "The complete schema follows. Use ONLY types it defines.",
        "",
        ref,
        "",
        "Author this card. Reply with ONLY the JSON object "
        '{"slug":...,"abilities":[...]}.',
        "Keywords printed on the card fire automatically from the card "
        "database -- do not author them.",
        "",
        f"Card: {slug}",
        f"Type: {ttext}",
        f"Printed keywords: {kws}",
        f"Text:\n{text}",
    ]
    if FEWSHOT and shots:
        block = ["", "Worked examples of accepted implementations:"]
        for e_slug, e_tt, e_text, e_kw, e_json in shots:
            block.append(f"Card: {e_slug} ({e_tt})")
            block.append("Text: " + " ".join(e_text.split())[:160])
            block.append(e_json)
            block.append("")
        parts[4:4] = block
    if ORACLE and want:
        # The real draft prompt carries primitives_the_triage_pass_identified.
        # This stands in for a PERFECT triage pass, so it is an upper bound, not
        # a fair arm -- it measures how much of the pipeline's quality is triage
        # rather than drafting.
        parts.append("\nA triage pass suggests these DSL types are relevant "
                     "(it may be incomplete or wrong):")
        parts.append("  " + ", ".join(sorted(want)))
    if WITH_NOTES and notes_for(slug):
        parts.append("\nOfficial release notes for this card:")
        parts.extend(f"- {n}" for n in notes_for(slug))
    if WITH_CR:
        ex = cr_excerpts(text, kws)
        if ex:
            parts.append("\nRelevant comprehensive-rules extracts:")
            parts.append(ex)
    parts.append("\nJSON:")
    return "\n".join(parts)


def main():
    argv = sys.argv[1:]
    ctx = 24576
    n = 6
    skip = set()
    for flag, default in (("--ctx", None), ("--n", None)):
        if flag in argv:
            i = argv.index(flag)
            val = int(argv[i + 1])
            skip.add(argv[i + 1])
            if flag == "--ctx":
                ctx = val
            else:
                n = val
    models = [a for a in argv if not a.startswith("--") and a not in skip]

    ref = (JSON_ROOT / "DSL_REFERENCE.md").read_text(encoding="utf-8")
    cards = load_cards(n)
    shots = draft_examples(n, SHOTS) if FEWSHOT else ()
    print(f"{len(cards)} real cards | ctx={ctx} | notes={WITH_NOTES} "
          f"cr={WITH_CR} think={THINK}\n")

    results = {}
    for m in models:
        recalls, drecalls, exact, usable, secs = [], [], 0, 0, 0.0
        print(f"--- {m} ---")
        for slug, ttext, text, want, kws, want_d in cards:
            prompt = build_prompt(ref, slug, ttext, text, kws, want, shots)
            t0 = time.time()
            try:
                out = ask(m, prompt, ctx)
            except Exception as e:
                print(f"  {slug:<32} ERR {str(e)[:40]}")
                recalls.append(0.0)
                drecalls.append(0.0)
                continue
            secs += time.time() - t0
            obj = extract(out.get("response") or out.get("thinking") or "")
            if not obj or not obj.get("abilities"):
                print(f"  {slug:<32} no usable JSON")
                recalls.append(0.0)
                drecalls.append(0.0)
                continue
            usable += 1
            got = types_in(obj["abilities"])
            hit = want & got
            recall = len(hit) / len(want)
            recalls.append(recall)
            exact += (got == want)
            got_d = details_in(obj["abilities"])
            drec = (len(want_d & got_d) / len(want_d)) if want_d else 1.0
            drecalls.append(drec)
            missing = sorted(want - got)
            print(f"  {slug:<32} type {recall:4.0%}  detail {drec:4.0%}"
                  + (f"   missing {missing}" if missing else "   exact"))
        if recalls:
            results[m] = (sum(recalls) / len(recalls),
                          sum(drecalls) / max(len(drecalls), 1), exact, usable,
                          len(cards), secs)
        print()

    print("SUMMARY  (mean type recall vs the accepted implementation)")
    for m, (rec, drec, ex, val, n_, secs) in sorted(results.items(),
                                                    key=lambda kv: -kv[1][0]):
        print(f"  {m:<26} type {rec:5.1%}  detail {drec:5.1%}  exact {ex}/{n_}"
              f"  usable {val}/{n_}  {secs / max(n_, 1):5.0f}s/card")


if __name__ == "__main__":
    main()
