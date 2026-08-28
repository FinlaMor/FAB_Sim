"""Turn an agent's REPLY into the per-card result files the pipeline consumes.

big-pickle will not reliably call a write tool. Pushed to write files it wrote
them and the analysis collapsed -- a card it had correctly flagged came back
"ok", which is the worst possible result: a file that certifies a live bug as
checked. Pushed to analyse properly it produced six minutes of verified
reasoning, citing handler line numbers, and no files at all. Batch size 1 did
not change this, so it is a preference, not a budget.

So stop fighting it. The model is good at the analysis and bad at the
bookkeeping; the bookkeeping is the part a script can do. The agent answers in
prose and ends with a fenced json block, and this extracts that block into
`<results>/<slug>.json`.

This also removes tool-use from the critical path entirely, which is worth
having independently: the previous model was withdrawn overnight, and the less
a pass depends on a given model's habits, the cheaper the next migration is.

    opencode run ... | python scripts/capture_verdicts.py .draft-review
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSON_ROOT = ROOT / "engine" / "card_effects" / "json"


def _blocks(text: str):
    """Every JSON object in the text, fenced or bare.

    Fenced blocks are tried first because that is what the prompt asks for. A
    bare scan is the fallback: an agent that forgets the fence has still done
    the work, and losing it to a formatting slip would repeat the failure this
    script exists to fix.
    """
    seen = []
    for m in re.finditer(r"```(?:json)?\s*(.*?)```", text, re.S):
        seen.append(m.group(1))
    if not seen:
        seen = [text]
    out = []
    for chunk in seen:
        # Objects can be top-level or inside a list; scan for balanced braces
        # rather than assuming one shape.
        depth = 0
        start = None
        for i, ch in enumerate(chunk):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start is not None:
                    try:
                        out.append(json.loads(chunk[start:i + 1]))
                    except Exception:
                        pass
                    start = None
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: capture_verdicts.py <results-dir-name>", file=sys.stderr)
        return 2
    results = JSON_ROOT / sys.argv[1]
    # .drafts holds CARD JSON (slug + abilities); every other pass holds
    # verdicts (slug + status/findings).
    shape = "draft" if sys.argv[1].strip("./") == "drafts" else "verdict"
    results.mkdir(parents=True, exist_ok=True)

    text = sys.stdin.read()
    written = 0
    for obj in _blocks(text):
        slug = obj.get("slug")
        if not isinstance(slug, str) or not slug:
            continue
        # TWO SHAPES, and writing one where the other belongs is silent
        # corruption: 23 review verdicts landed in .drafts/, where the queue
        # counts a present file as "this card is drafted", so those cards would
        # never have been drafted at all. The shape is checked against the
        # destination rather than assumed.
        if shape == "draft":
            if "abilities" not in obj:
                continue
        else:
            if "status" not in obj and "findings" not in obj:
                continue
            obj.setdefault("status", "finding" if obj.get("findings") else "ok")
            obj.setdefault("findings", [])
        (results / f"{slug}.json").write_text(
            json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")
        written += 1
    print(f"captured {written} ({shape})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
