#!/usr/bin/env python3
"""Candidate-verification pass: re-run ONLY the test gate on existing `candidate`
cards (impl already loads + is non-stub) and promote to `done` any whose behaviour
a test now verifies. Does NOT re-implement — the committed JSON is kept as-is.

Reuses the pipeline's own functions (build_test_prompt — now Talishar-grounded —
best-of-N with the temperature ladder, run_generated_test, append_test), so a
promotion earns `done` by the exact same gate as a first-pass card.

Usage:  python scripts/verify_candidates.py [N]      # verify up to N candidates
        (server on $FAB_LLM_BASE_URL, default :8080). Resumable: saves after each.
"""
from __future__ import annotations
import json, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import auto_implement_wtr as A

A.BACKEND = "openai"
A.BASE_URL = os.environ.get("FAB_LLM_BASE_URL", "http://localhost:8080/v1")
A.SET_CODE = "batch"
A.WTR_DIR = A.ROOT / "engine" / "card_effects" / "json" / "batch"
A.QUEUE_PATH = A.WTR_DIR / "batch_work_queue.json"
A.REVIEW_DIR = A.WTR_DIR / "needs_review"
A.TEST_OUTPUT = A.ROOT / "tests" / "test_batch_generated.py"

MODEL = os.environ.get("FAB_MODEL", "qwen2.5-coder:14b")
SAMPLES = 3


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10**9
    queue = json.loads(A.QUEUE_PATH.read_text(encoding="utf-8"))
    cands = [c for c in queue if c["status"] == "candidate"]
    n = min(limit, len(cands))
    print(f"verifying {n} of {len(cands)} candidates via the test gate "
          f"(best-of-{SAMPLES}, Talishar-grounded)", flush=True)

    promoted = 0
    for i, card in enumerate(cands[:n]):
        slug = card["slug"]
        jpath = A._card_out_dir(slug) / f"{slug}.json"
        if not jpath.exists():
            print(f"[{i+1}/{n}] {slug}: json missing, skip", flush=True)
            continue
        json_content = jpath.read_text(encoding="utf-8")
        prompt = A.build_test_prompt(card, json_content)

        passed_code = None
        for s in range(SAMPLES):
            temp = round(min(0.1 + 0.35 * s, 1.0), 2)
            out = A.run_llm(prompt, verbose=False, model=MODEL,
                            temperature=temp, seed=1000 + s)
            if out == "CLAW_TIMEOUT" or out.startswith("CLAW_ERROR") or "NEEDS_NEW_DSL" in out:
                continue
            code = A.extract_test_code(out)
            if not code:
                continue
            ok, _ = A.run_generated_test(slug, code, verbose=False)
            if ok:
                passed_code = code
                break

        if passed_code is not None:
            A.append_test(slug, passed_code)
            card["status"] = "done"
            promoted += 1
            print(f"[{i+1}/{n}] {slug}: PROMOTED -> done", flush=True)
        else:
            print(f"[{i+1}/{n}] {slug}: still candidate", flush=True)
        A.QUEUE_PATH.write_text(json.dumps(queue, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\npromoted {promoted}/{n} candidates -> done", flush=True)


if __name__ == "__main__":
    main()
