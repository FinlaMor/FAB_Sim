#!/usr/bin/env python3
"""Re-audit the 14b-audited tail of the full candidate audit with a STRONGER
model (default qwen3-coder-30b-ctx8k) to surface false-negatives — cards the
weaker model called clean that the stronger model flags.

Reads docs/semantic_audit_all_candidates.jsonl (original run: first ~230 by 30b,
rest by 14b). Re-audits the tail, streams to a SEPARATE resumable jsonl, and a
rolling report that highlights FLIPPED cards (14b clean -> stronger flagged).

Usage:
  python scripts/reaudit_14b_tail.py --model qwen3-coder-30b-ctx8k --start 230
"""
from __future__ import annotations
import argparse, importlib.util, json, sys, glob
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))

ORIG = ROOT / "docs" / "semantic_audit_all_candidates.jsonl"
RESULTS = ROOT / "docs" / "semantic_audit_reaudit.jsonl"
REPORT = ROOT / "docs" / "semantic_audit_reaudit.md"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def _cardpath(slug):
    for p in glob.glob(str(ROOT / "engine/card_effects/json" / "**" / f"{slug}.json"), recursive=True):
        if "needs_review" not in p and Path(p).parent.name != "tokens":
            return Path(p)
    return None


def _rewrite_report(model, orig_clean):
    rows = []
    if RESULTS.exists():
        for line in RESULTS.open(encoding="utf-8"):
            try: rows.append(json.loads(line))
            except json.JSONDecodeError: pass
    flipped = [r for r in rows if r.get("suspect") and r["slug"] in orig_clean]
    still_flagged = [r for r in rows if r.get("suspect") and r["slug"] not in orig_clean]
    lines = [f"# Re-audit of 14b tail — {model} — vs original 14b verdicts\n",
             f"- re-audited: {len(rows)}\n",
             f"- FLIPPED (14b clean -> {model} flagged) — the false-negatives: {len(flipped)}\n",
             f"- flagged by both: {len(still_flagged)}\n",
             "\n## FLIPPED (14b missed these)\n"]
    for r in flipped:
        lines.append(f"\n### {r.get('name')} (`{r['slug']}`)\n> {r.get('text','')}\n")
        for c in r["suspect"]:
            lines.append(f"- **{c.get('status')}** — {c.get('text','')}  \n  {c.get('note','')}\n")
    REPORT.write_text("".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3-coder-30b-ctx8k")
    ap.add_argument("--start", type=int, default=230, help="index in the original jsonl where the 14b tail begins")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    sa = _load("dsl_semantic_audit", ROOT / "scripts" / "dsl_semantic_audit.py")
    claw = sa._auto_impl()
    index = json.loads((ROOT / "card_data" / "slug_index.json").read_text(encoding="utf-8"))["by_slug"]

    orig = [json.loads(l) for l in ORIG.open(encoding="utf-8") if l.strip()]
    tail = orig[args.start:]
    orig_clean = {r["slug"] for r in tail if not r.get("suspect") and not r.get("error")}
    tail_slugs = [r["slug"] for r in tail]

    done = set()
    if RESULTS.exists():
        for line in RESULTS.open(encoding="utf-8"):
            try:
                rec = json.loads(line)
                if rec.get("slug") and not rec.get("error"):
                    done.add(rec["slug"])
            except json.JSONDecodeError:
                pass
    todo = [s for s in tail_slugs if s not in done]
    if args.limit:
        todo = todo[:args.limit]
    print(f"14b tail={len(tail_slugs)} (clean={len(orig_clean)}) already-reaudited={len(done)} to-do={len(todo)} model={args.model}", flush=True)

    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS.open("a", encoding="utf-8") as out:
        for i, slug in enumerate(todo, 1):
            p = _cardpath(slug)
            if p is None:
                continue
            try:
                res = sa.audit_card(p, index, claw, args.model, verbose=False)
            except Exception as exc:
                res = {"slug": slug, "error": f"{type(exc).__name__}: {exc}"}
            if not res:
                res = {"slug": slug, "error": "no entry"}
            suspect = [c for c in (res.get("clauses") or []) if c.get("status") in ("MISSING", "MISMATCH")]
            rec = {"slug": slug, "name": res.get("name"), "text": res.get("text"),
                   "suspect": suspect, "error": res.get("error"),
                   "was_14b_clean": slug in orig_clean}
            out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush()
            flip = " *** FLIP (14b said clean)" if (suspect and slug in orig_clean) else ""
            tag = "ERR" if rec["error"] else (f"{len(suspect)} suspect" if suspect else "clean")
            print(f"[{i}/{len(todo)}] {slug}: {tag}{flip}", flush=True)
            if i % 10 == 0:
                _rewrite_report(args.model, orig_clean)
    _rewrite_report(args.model, orig_clean)
    print("done.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
