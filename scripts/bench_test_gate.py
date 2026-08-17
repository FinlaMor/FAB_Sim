"""Benchmark the test gate on cards that ALREADY failed it.

The `candidate` tier means: the card's JSON loads and is not a no-op stub, but no
generated test passed. That makes the candidate list a clean A/B population — the
baseline pass rate is 0 by definition — so any card that now gets a passing test
is attributable to the gate changes (syntax salvage, tolerant helpers,
error-feedback repair loop) rather than to cherry-picking.

Usage:
  python scripts/bench_test_gate.py --set pen --limit 12 [--samples 3] [--no-repair]

`--no-repair` re-rolls blind with a fresh seed instead of feeding the pytest
error back, which isolates the repair loop's contribution from the harness fixes.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import auto_implement_wtr as A


def load_candidates(set_code: str) -> list[dict]:
    qpath = ROOT / "engine" / "card_effects" / "json" / set_code / f"{set_code}_work_queue.json"
    raw = json.loads(qpath.read_text(encoding="utf-8"))
    cards = raw if isinstance(raw, list) else raw.get("cards", raw.get("queue", []))
    return [c for c in cards if c.get("status") == "candidate"]


def run_one(card: dict, model: str, samples: int, repair: bool, verbose: bool) -> dict:
    slug = card["slug"]
    json_path = A._card_out_dir(slug) / f"{slug}.json"
    if not json_path.exists():
        return {"slug": slug, "result": "no_json"}
    json_content = json_path.read_text(encoding="utf-8")
    prompt = A.build_test_prompt(card, json_content)

    repair_ctx = ""
    t0 = time.time()
    for i in range(samples):
        temp = round(min(0.1 + 0.35 * i, 1.0), 2)
        out = A.run_llm(prompt + repair_ctx, verbose=verbose, model=model,
                        temperature=temp, seed=1000 + i)
        if out == "CLAW_TIMEOUT" or out.startswith("CLAW_ERROR"):
            continue
        if "NEEDS_NEW_DSL:" in out:
            return {"slug": slug, "result": "needs_dsl", "attempts": i + 1,
                    "secs": round(time.time() - t0)}
        code = A.extract_test_code(out)
        if not code:
            continue
        passed, run_out = A.run_generated_test(slug, code, verbose=verbose)
        if passed and A._is_vacuous_test(code):
            passed, run_out = False, "Test passed but asserts nothing observable."
        if passed:
            return {"slug": slug, "result": "PASS", "attempts": i + 1,
                    "secs": round(time.time() - t0)}
        if repair and i + 1 < samples:
            repair_ctx = (
                f"\n\n=== YOUR PREVIOUS ATTEMPT FAILED — FIX IT ===\n\n"
                f"You wrote this test:\n\n{code}\n\nRunning it produced:\n\n"
                f"{run_out[-1500:]}\n\n"
                "Fix the cause. If the traceback says an attribute does not exist, "
                "you INVENTED it — use only the real names listed above (there is no "
                "`state.flags`, no `player.flags`, no `.max_health`; use "
                '`set_turn_flag(st, pid, "marker")` to stage turn state). If a helper '
                "rejected a keyword argument, check its real signature.\n\n"
                "Do NOT weaken the test to make it pass: keep asserting a real, "
                "observable state change. Deleting the assertion or asserting "
                "something trivially true is a FAILURE, not a fix. Output ONLY the "
                "corrected Python.\n"
            )
    # Record the last failure's exception class. Whether the residual failures are
    # AttributeError (harness friction still worth fixing) or AssertionError (the
    # card or the expectation is genuinely wrong) decides whether more gate work
    # would pay off at all, and that is invisible from a pass rate alone.
    err = ""
    for line in reversed((run_out or "").splitlines()):
        m = re.search(r"\b(\w*(?:Error|Exception))\b", line)
        if m:
            err = m.group(1)
            break
    return {"slug": slug, "result": "fail", "attempts": samples,
            "secs": round(time.time() - t0), "error": err,
            "detail": (run_out or "")[-400:]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="pen", dest="set_code")
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--model", default="qwen3-coder-30b-ctx8k:latest")
    ap.add_argument("--no-repair", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    A.BACKEND = "openai"
    A.BASE_URL = "http://localhost:11434/v1"
    A.SET_CODE = args.set_code

    cands = load_candidates(args.set_code)[: args.limit]
    repair = not args.no_repair
    print(f"[bench] set={args.set_code} cards={len(cands)} samples={args.samples} "
          f"repair={repair} model={args.model}")
    print(f"[bench] baseline for these cards is 0/{len(cands)} by definition "
          f"(they are candidates because no test passed)\n")

    results = []
    t0 = time.time()
    for n, card in enumerate(cands, 1):
        r = run_one(card, args.model, args.samples, repair, args.verbose)
        results.append(r)
        print(f"  [{n}/{len(cands)}] {r['slug']:38} {r['result']:9} "
              f"attempts={r.get('attempts','-')} {r.get('secs','-')}s", flush=True)

    passed = [r for r in results if r["result"] == "PASS"]
    print(f"\n[bench] PASS {len(passed)}/{len(results)} "
          f"({100*len(passed)//max(1,len(results))}%) in {round(time.time()-t0)}s")
    if passed:
        from collections import Counter
        print(f"[bench] attempts to pass: {dict(Counter(r['attempts'] for r in passed))}")
        print(f"[bench] newly passing: {', '.join(r['slug'] for r in passed)}")
    out = ROOT / "scratchpad" / f"bench_{args.set_code}_{'repair' if repair else 'blind'}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"[bench] wrote {out}")


if __name__ == "__main__":
    main()
