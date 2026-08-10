#!/usr/bin/env python3
"""Run the CR-grounded semantic audit (scripts/dsl_semantic_audit.py) over EVERY
candidate card with a strong auditor model, writing results INCREMENTALLY and
RESUMABLY so a multi-hour run survives interruption.

- Results stream to docs/semantic_audit_all_candidates.jsonl (one line per card).
- A rolling human report is rewritten to docs/semantic_audit_all_candidates.md.
- Re-running skips cards already present in the .jsonl (resume).

Usage:
  python scripts/audit_all_candidates.py                    # all candidates
  python scripts/audit_all_candidates.py --limit 50         # first N unaudited
  python scripts/audit_all_candidates.py --model qwen3-coder:30b
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import sys
import glob
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

RESULTS = ROOT / "docs" / "semantic_audit_all_candidates.jsonl"
REPORT = ROOT / "docs" / "semantic_audit_all_candidates.md"


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _card_path(slug: str):
    for p in glob.glob(str(ROOT / "engine/card_effects/json" / "**" / f"{slug}.json"),
                       recursive=True):
        if "needs_review" not in p and f"{Path(p).parent.name}" != "tokens":
            return Path(p)
    return None


def _rewrite_report(model: str):
    rows = []
    if RESULTS.exists():
        for line in RESULTS.open(encoding="utf-8"):
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    suspect = [r for r in rows if r.get("suspect")]
    errs = [r for r in rows if r.get("error")]
    lines = [
        f"# Semantic audit — ALL candidate cards — {model}\n",
        "Auditor model via Ollama. Suspicions, not verified defects; confirm "
        "against card text + CR before changing anything.\n",
        f"- audited so far: {len(rows)}\n",
        f"- with suspect clauses: {len(suspect)}\n",
        f"- model/parse errors: {len(errs)}\n",
    ]
    for r in suspect:
        lines.append(f"\n### {r.get('name')} (`{r['slug']}`)\n")
        lines.append(f"> {r.get('text','')}\n")
        for c in r["suspect"]:
            lines.append(f"- **{c.get('status')}** — {c.get('text','')}  \n  {c.get('note','')}\n")
    REPORT.write_text("".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3-coder:30b")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    sa = _load_module("dsl_semantic_audit", ROOT / "scripts" / "dsl_semantic_audit.py")
    claw = sa._auto_impl()
    index = json.loads((ROOT / "card_data" / "slug_index.json").read_text(encoding="utf-8"))["by_slug"]
    queue = json.loads((ROOT / "engine/card_effects/json/batch/batch_work_queue.json").read_text(encoding="utf-8"))
    cands = [c["slug"] for c in queue if c["status"] == "candidate"]

    done = set()
    if RESULTS.exists():
        for line in RESULTS.open(encoding="utf-8"):
            try:
                done.add(json.loads(line)["slug"])
            except (json.JSONDecodeError, KeyError):
                continue
    todo = [s for s in cands if s not in done]
    if args.limit:
        todo = todo[:args.limit]
    print(f"candidates={len(cands)} already-audited={len(done)} to-audit={len(todo)} model={args.model}",
          flush=True)

    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS.open("a", encoding="utf-8") as out:
        for i, slug in enumerate(todo, 1):
            p = _card_path(slug)
            if p is None:
                continue
            try:
                res = sa.audit_card(p, index, claw, args.model, verbose=False)
            except Exception as exc:  # keep the run alive
                res = {"slug": slug, "error": f"{type(exc).__name__}: {exc}"}
            if not res:
                res = {"slug": slug, "error": "no card entry / vanilla"}
            suspect = [c for c in (res.get("clauses") or [])
                       if c.get("status") in ("MISSING", "MISMATCH")]
            rec = {"slug": slug, "name": res.get("name"), "text": res.get("text"),
                   "suspect": suspect, "error": res.get("error")}
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            tag = "ERR" if rec["error"] else (f"{len(suspect)} suspect" if suspect else "clean")
            print(f"[{i}/{len(todo)}] {slug}: {tag}", flush=True)
            if i % 10 == 0:
                _rewrite_report(args.model)
    _rewrite_report(args.model)
    print("done.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
