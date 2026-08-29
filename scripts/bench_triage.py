#!/usr/bin/env python3
"""Measure the TRIAGE pass, which is where card quality actually comes from.

NOTE: the commit that added this file says triage "finds a quarter of the types
a card needs". That number was measured while the machine was in use. It is
34%, not 24.8% -- see RESULTS below.

scripts/bench_local_models.py established that the drafter is not the lever:

    baseline                 type recall 40.2%
    + triage type shortlist  type recall 78.8%     (+38.6)
    2x bigger model                      +0.0
    coder-tuned MoE                      -17.5
    release notes + CR                    +0.0

That shortlist is `primitives_the_triage_pass_identified`, produced by the
triage pass and carried in every draft prompt. So the question that matters is
no longer "which model drafts best" but "how good is the shortlist?" -- and
that had never been measured, because the oracle arm handed over the accepted
answer rather than predicting it.

This measures the real thing. Triage sees what it sees in production: the
printed text, the type line, the printed keywords, and the catalogue of type
NAMES the compiler knows (the production pass reads the same list as
.triage/_types.json). It does not see the implementation. Its predicted
primitives are then scored against the types the accepted implementation
actually uses.

Both directions are reported, because they fail differently:

    recall     types the card needs that triage FOUND. Misses here are the
               drafter's missing gates -- the defect class that has cost real
               cards.
    precision  types triage named that the card does NOT need. Noise here
               sends the drafter looking for mechanics that are not there,
               and inflates the missing-mechanic backlog with phantom gaps.

RESULTS, measured on an IDLE machine, 20 cards, repeated:

    baseline                 n=5   34.1%   sd 0.4
    --described (params)     n=7   32.6%   sd 1.3     -1.5
    --cr (rules sections)    n=3   34.1%   sd 0.5     +0.0
    baseline, machine BUSY   n=2   24.1%   sd 0.7

RUN THIS ON A QUIET MACHINE OR NOT AT ALL. The two contended runs sit ten
points low and had sd 0.7 *among themselves*, so they looked perfectly stable
and were reported as fact -- "real triage recall is 24.8%" and "the CR makes it
slightly worse". Both were artefacts of load. Stability within a batch says
nothing about whether the batch is biased.

Idle, this benchmark has sd 0.4 and resolves differences of about a point,
which makes --described's -1.5 likely a small REAL negative rather than noise.

--described was the arm that should have worked. Triage's errors are near
misses -- MODIFY_ATTACK for MODIFY_NEXT_ATTACK, and an invented
GRANT_NEXT_ATTACK -- which is exactly what put CARD_TYPE_IN into a set
directory and stopped a card loading. Giving each type the parameters its
handler reads did not help. A first single run showed +10.4 and was reported
before being repeated; that was noise.

So every "give it more reference material" intervention has now failed: bigger
model, release notes, comprehensive rules, parameter signatures. Only the
oracle shortlist moves the number (+38.6), and it is two orders of magnitude
outside the noise. Try few-shot examples next.

    python scripts/bench_triage.py --n 20 qwen2.5-coder:14b
    python scripts/bench_triage.py --n 20 --cr qwen2.5-coder:14b
"""
from __future__ import annotations

import json
import random
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSON_ROOT = ROOT / "engine" / "card_effects" / "json"
OLLAMA = "http://localhost:11434/api/generate"

WITH_CR = "--cr" in sys.argv
FEWSHOT = "--fewshot" in sys.argv
DESCRIBED = "--described" in sys.argv

_CR = (ROOT / "docs" / "ref" / "en-fab-cr-comprehensive-rules.txt").read_text(
    encoding="utf-8", errors="replace")


def _cr_sections():
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
    return re.sub(r"[^a-z]", "",
                  re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(s or "")).lower())


def cr_excerpts(keywords, budget=4000):
    """The rules sections for this card's printed keywords, and nothing else."""
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


def catalogue(described=False):
    """Every type name the compiler knows, which is what triage gets to see.

    With `described`, each name carries the PARAMETERS its handler reads, e.g.

        MODIFY_NEXT_ATTACK(amount, filter, mod)

    Bare names are what the production pass gets, and the failure they produce
    is specific: the model reaches for MODIFY_ATTACK when the card needs
    MODIFY_NEXT_ATTACK, and invents GRANT_NEXT_ATTACK outright. A list of 321
    undifferentiated names gives it nothing to tell near-misses apart with.

    The parameter list is a free disambiguator -- audit_params already extracts
    it from the compilers, so it is complete for all 321 types rather than the
    7% that DSL_REFERENCE.md happens to describe in prose.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "ap", ROOT / "scripts" / "audit_params.py")
    ap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ap)
    index = ap.build_index()
    if not described:
        return sorted(n for n in index if n)
    out = []
    for name in sorted(n for n in index if n):
        params = sorted(p for p in index[name] if isinstance(p, str)
                        and not p.startswith("*"))
        out.append(f"{name}({', '.join(params[:6])})" if params else name)
    return out


def examples(n_test, k=3, seed=11):
    """Worked examples drawn from BEYOND the scored slice.

    Every "give it more reference material" arm has failed -- bigger model,
    release notes, comprehensive rules, parameter signatures -- so this shows
    the shape of a right answer instead of describing the vocabulary.

    The examples are taken from indices n_test.. of the SAME shuffled pool, so
    they are real implemented cards and provably disjoint from the ones being
    scored. An example drawn from the test set would leak the answer and the
    arm would measure nothing, which is the failure mode this effort keeps
    reproducing.
    """
    pool = _pool(seed)
    return pool[n_test:n_test + k]


def _pool(seed=11):
    idx = json.loads(
        (ROOT / "card_data" / "slug_index.json").read_text(encoding="utf-8"))["by_slug"]
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
        if not text or len(want) < 2:
            continue
        pool.append((raw["slug"], e.get("typeText") or "", text, want,
                     e.get("keywords") or []))
    random.Random(seed).shuffle(pool)
    return pool


def load_cards(n, seed=11):
    return _pool(seed)[:n]


def ask(model, prompt, ctx=16384, timeout=3600):
    payload = {"model": model, "prompt": prompt, "stream": False,
               "think": False,
               "options": {"temperature": 0.1, "num_ctx": ctx,
                           "num_predict": 400}}
    req = urllib.request.Request(OLLAMA, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def parse_types(text, known):
    """Type names the reply proposes. Tolerant of prose, lists and JSON, because
    scoring a formatting slip as a triage failure would measure the wrong
    thing."""
    if not text:
        return set()
    found = {t for t in re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", text)}
    return {t for t in found if t in known}


def build_prompt(cat, slug, ttext, text, kws, shots=()):
    parts = [
        "You triage Flesh and Blood cards for a rules engine. You do NOT "
        "implement them.",
        "",
        "Name every DSL type this card's behaviour would need. Choose ONLY "
        "from this catalogue:",
        ", ".join(cat),
        "",
        "Keywords printed on the card (Go Again, Dominate, Ward, Intimidate, "
        "Blade Break ...) fire automatically from the card database and need "
        "NO types at all. Do not name types for them.",
        "",
        *( [""] if not FEWSHOT else [] ),
        f"Card: {slug}",
        f"Type: {ttext}",
        f"Printed keywords: {kws}",
        f"Text:\n{text}",
    ]
    if FEWSHOT and shots:
        block = ["", "Worked examples of the answer expected:"]
        for e_slug, e_tt, e_text, e_want, e_kw in shots:
            one = ' '.join(e_text.split())
            block.append(f"  Card: {e_slug} ({e_tt})")
            block.append(f"  Text: {one[:150]}")
            block.append(f"  Types: {', '.join(sorted(e_want))}")
        parts[4:4] = block
    if WITH_CR:
        ex = cr_excerpts(kws)
        if ex:
            parts.append("\nThe comprehensive rules for this card's keywords:")
            parts.append(ex)
    parts.append("\nReply with ONLY a comma-separated list of type names.")
    return "\n".join(parts)


def main():
    argv = sys.argv[1:]
    n, skip = 20, set()
    if "--n" in argv:
        i = argv.index("--n")
        n = int(argv[i + 1])
        skip.add(argv[i + 1])
    models = [a for a in argv if not a.startswith("--") and a not in skip]

    cat = catalogue(DESCRIBED)
    # names only, for scoring -- the described catalogue carries params too
    known = {c.split('(')[0] for c in cat}
    cards = load_cards(n)
    shots = examples(n) if FEWSHOT else ()
    print(f"{len(cards)} real cards | catalogue {len(cat)} types | cr={WITH_CR}\n")

    for m in models:
        recs, precs, secs = [], [], 0.0
        print(f"--- {m} ---")
        for slug, ttext, text, want, kws in cards:
            prompt = build_prompt(cat, slug, ttext, text, kws, shots)
            t0 = time.time()
            try:
                out = ask(m, prompt)
            except Exception as e:
                print(f"  {slug:<32} ERR {str(e)[:40]}")
                recs.append(0.0)
                precs.append(0.0)
                continue
            secs += time.time() - t0
            got = parse_types(out.get("response", ""), known)
            hit = want & got
            rec = len(hit) / len(want) if want else 1.0
            pre = len(hit) / len(got) if got else 0.0
            recs.append(rec)
            precs.append(pre)
            miss = sorted(want - got)
            print(f"  {slug:<32} recall {rec:4.0%}  precision {pre:4.0%}"
                  + (f"   missed {miss[:4]}" if miss else "   found all"))
        if recs:
            print(f"\n  MEAN  recall {sum(recs)/len(recs):5.1%}   "
                  f"precision {sum(precs)/len(precs):5.1%}   "
                  f"{secs/len(cards):4.0f}s/card\n")


if __name__ == "__main__":
    main()
