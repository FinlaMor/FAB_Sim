#!/usr/bin/env python3
"""Measure the AUDITOR pass against cards whose defects are known.

NOT bench_triage.py. That measures the triage pass -- which primitive TYPES a
card needs, predicted from printed text alone -- and never sees an
implementation, so it cannot say anything about the auditor. The two were
conflated once in conversation; they are different passes with different inputs.

THE LABELLED SET IS THE POINT. The 2026-08/09 sweeps fixed 38 cards whose JSON
changed, and git holds both sides:

    BEFORE  the implementation that shipped, with a defect whose class is known
    AFTER   the accepted implementation

So the auditor can be scored in both directions on real production drafts,
rather than on defects invented for a benchmark:

    recall     of the BEFORE versions, how many did it flag?
               Misses are the defects that ship.
    false-pos  of the AFTER versions, how many did it flag anyway?
               This is the arm that matters most. A sweep run in the
               "there IS a problem, find it" spirit produced 22 findings of
               which 7 were real -- a 68% false-positive rate -- and every
               false positive costs a real investigation. An auditor that
               flags everything has perfect recall and is worthless.

Both prompts are run over the same cards in the same session, because a recall
number with no baseline says nothing about whether the rewrite helped.

RESULTS, qwen2.5-coder:14b, 27 labelled pairs, idle machine, 2026-09-01:

                        recall    false-pos   discrimination
    old (checklist)     77.8%       70.4%          0.07
    new (clause map)    29.6%        3.7%          0.26

THE OLD PROMPT WAS NOT AUDITING, IT WAS FLAGGING. It objected to 70% of the
ACCEPTED implementations -- and production applied whatever JSON it returned, so
the verification pass was rewriting correct cards most of the time it ran. Its
77.8% recall is nearly worthless next to that: discrimination 0.07 is close to a
coin weighted toward "flag it".

The rewrite is ~4x better at telling the two apart and is safe to leave switched
on. It is still NOT good enough to be the quality gate. Two things make the
headline worse than it looks, and both are recorded here rather than in a
summary somewhere:

  1. THE WORKED EXAMPLES CONTAMINATE THE MEASUREMENT, and worse, production.
     The prompt cites torque_tuned_red, hydraulic_press_blue, spectral_rider_red
     and burly_bones_red by name as WRONG examples. Four of the eight catches
     are those cards (or burly_bones_blue, which shares burly_bones_red's exact
     text). Excluding them, recall is 4/22 = 18.2%.
     The live hazard is the same mechanism: auditing hydraulic_press_blue's
     ACCEPTED version produced the arm's ONLY false positive, because the model
     read its own defect out of the instructions and reported it as present in
     JSON that no longer contains it. Examples should name cards that cannot
     appear in the corpus being audited, or be described without slugs.

  2. THE VARIANCE IS WIDE. torque_tuned_red and torque_tuned_blue are
     byte-identical in abilities and printed text, before and after the fix.
     The auditor caught blue and missed red. At n=27 a proportion near 0.3
     carries roughly +/-9 points, so 29.6% and 18.2% are the same measurement
     within error.

WHAT WORKS AND WHAT DOES NOT. Part A -- the forced clause map -- was produced in
54/54 replies, and all three B checks were answered in 54/54. The mechanism the
rewrite bets on does run. But B1 still MISSES the defect class it was written
for: on soul_cleaver_blue, which prints GoAgain and gates it in its own text, the
model answered "NO. The card does not print a keyword that is gated by its own
text" -- and then rationalised B3 by describing a GO_AGAIN node as "correctly
using the GAIN primitive".

The lesson is the one Part A already demonstrates: ENUMERATION WORKS, JUDGEMENT
DOES NOT. B1 is still a yes/no over a conjunction ("prints X" AND "text gates
X"), which a 14B model answers as a gestalt. It should be mechanical, the way
Part A is: copy the printed keyword list, quote the sentence mentioning each
keyword or write "not mentioned", then mark gated any keyword whose sentence
opens with if/whenever/while. That is the next thing to try, and it is untested.

COST. The new prompt's median reply is 1609 chars against the old prompt's 508 --
roughly 3x the output tokens for the map and the three answered checks. On the
per-card figures in the cost model that is still noise against the ~13.4k-token
prompt, but it is not free.

v2, mechanical B1 + examples that name no real card, same 27 pairs, same model:

                        recall    false-pos   discrimination
    v1 (judgement B1)   29.6%        3.7%          0.26
    v2 (mechanical B1)  37.0%        3.7%          0.33

    like-for-like, on the 22 cards v1's prompt never cited:
    v1 18.2%  ->  v2 31.8%

The headline understates it because v1's examples named five cards in the
benchmark and v2's name none; the like-for-like figure is the honest one. What
makes the result credible is not the delta but WHICH cards moved: the gains are
photon_rush_red, runerager_swarm_blue, soup_up_red and glaring_impact_blue --
all gated-printed-keyword defects, the class judgement-phrased B1 was missing
wholesale. Mechanism, not luck.

CAVEAT, and it is a real one: 6 cards were newly caught and 4 were lost, for +2
net. torque_tuned_red and torque_tuned_blue are byte-identical in abilities and
printed text and have scored differently across runs, so a good part of that
churn is sampling noise at n=27.

THE v2 TALISHAR ARM DID NOT EXIST. It was reported as present and was not: this
script put only ROOT on sys.path, so `import talishar_reference` failed
silently, _talishar_reference returned "", and the block was omitted from all 54
prompts. The tell was that ZERO replies mentioned Talishar. Fixed by adding
ROOT/"scripts" to sys.path; v3 is the first run where the block is actually
there. Anything that reaches a model through a silently-swallowed import is a
variable you are not measuring.

B1 fill rate: the keyword table was completed in 40/54 replies, against Part A's
54/54. Enumeration beats judgement but is not free -- some remaining misses are
probably skipped rows rather than wrong answers.

CORRECTION TO THE FIRST READING OF THESE NUMBERS. The commit that recorded them
concluded "keep the static guards as the gate; they caught every defect class in
this set deterministically". That is wrong, and measuring it says so plainly:

    audit_params / dead-flag / no-abilities checks
    on the same 27 defective versions ........... 0 caught

ALL 27 ARE INVISIBLE TO PER-CARD STATIC ANALYSIS. The guards that do catch these
classes -- the conditional-keyword ratchet and the sweeps -- are corpus-level
counts written AFTER the defects were found, by reading cards against their text.
A static guard can only be written for a class somebody has already named, which
is precisely the step the auditor is supposed to help with.

So the auditor's niche is real even though it is currently bad at it: its 8/27
(4/22 decontaminated) is scored entirely on material no static check can reach.
The honest read is not "the LLM adds nothing" but "the LLM adds a fifth of the
one thing static analysis cannot do at all, and should be made better rather than
switched off".

RUN IT ON A QUIET MACHINE OR NOT AT ALL. bench_triage's two contended runs sat
ten points low with sd 0.7 *among themselves*, so they looked stable and were
reported as fact. Stability within a batch says nothing about whether the batch
is biased.

    python scripts/bench_auditor.py --list
    python scripts/bench_auditor.py --model qwen2.5-coder:14b --limit 4
    python scripts/bench_auditor.py --model qwen2.5-coder:14b --arm new
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# scripts/ too, or _talishar_reference cannot `import talishar_reference` and
# silently returns "" -- which measured the Talishar arm as absent while
# reporting it as present. The v2 run was invalidated by exactly this.
sys.path.insert(0, str(ROOT / "scripts"))

OLLAMA = "http://localhost:11434/api/generate"
#: commits whose card-JSON changes are the labelled fixes
FIX_COMMITS = ["f17a4d3", "89328ca", "7528645", "fac1533"]
#: the commit that introduced the new auditor prompt; its parent has the old one
PROMPT_COMMIT = "6eba621"


def labelled_pairs():
    """[(slug, path, before_json, after_json)] for every card the sweeps fixed."""
    files = set()
    for commit in FIX_COMMITS:
        out = subprocess.run(
            ["git", "show", "--name-only", "--format=", commit, "--",
             "engine/card_effects/json"],
            cwd=ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace").stdout
        for line in out.splitlines():
            line = line.strip()
            if line.endswith(".json") and "work_queue" not in line:
                files.add(line)

    pairs = []
    for path in sorted(files):
        slug = Path(path).stem
        before = subprocess.run(["git", "show", "%s~1:%s" % (FIX_COMMITS[0], path)],
                                cwd=ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace")
        if before.returncode != 0:
            # changed by a later commit in the run; take the parent of whichever
            # commit first touched it
            for commit in FIX_COMMITS[1:]:
                before = subprocess.run(["git", "show", "%s~1:%s" % (commit, path)],
                                        cwd=ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace")
                if before.returncode == 0:
                    break
        if before.returncode != 0:
            continue
        current = ROOT / path
        if not current.exists():
            continue
        after = current.read_text(encoding="utf-8")
        if _abilities(before.stdout) == _abilities(after):
            continue          # only the comment changed: not a labelled defect
        pairs.append((slug, path, before.stdout, after))
    return pairs


def _abilities(text):
    try:
        return json.loads(text).get("abilities")
    except Exception:
        return None


def _prompt_builder(arm):
    """Load build_verification_prompt from this tree (new) or from the commit
    before the rewrite (old)."""
    import importlib.util
    if arm == "new":
        src = (ROOT / "scripts" / "auto_implement_wtr.py").read_text(encoding="utf-8")
    else:
        src = subprocess.run(
            ["git", "show", "%s~1:scripts/auto_implement_wtr.py" % PROMPT_COMMIT],
            cwd=ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace").stdout
    path = ROOT / ("_bench_auditor_%s.py" % arm)
    path.write_text(src, encoding="utf-8")
    try:
        spec = importlib.util.spec_from_file_location("aiw_" + arm, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.build_verification_prompt
    finally:
        path.unlink(missing_ok=True)


def ask(model, prompt, ctx, timeout=1200):
    payload = {"model": model, "prompt": prompt, "stream": False, "think": False,
               "options": {"temperature": 0.1, "num_ctx": ctx, "num_predict": 1200}}
    req = urllib.request.Request(OLLAMA, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read()).get("response", "")


def flagged(arm, reply):
    """Did the auditor object? Parsed the way production parses it."""
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", reply, flags=re.I)
    if arm == "new":
        verdicts = re.findall(r"VERDICT:\s*(LOOKS_GOOD|CORRECTED)", cleaned, re.I)
        if not verdicts:
            return None                      # no verdict: production keeps the card
        return verdicts[-1].upper() == "CORRECTED"
    # old contract: LOOKS_GOOD in the head, else a corrected JSON body
    body = re.sub(r"```(?:json)?\s*", "", cleaned).strip()
    if "LOOKS_GOOD" in body.upper()[:40]:
        return False
    return bool(re.search(r"\{[\s\S]+\}", body))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen2.5-coder:14b")
    ap.add_argument("--arm", choices=["new", "old", "both"], default="both")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ctx", type=int, default=24576)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    idx = json.loads((ROOT / "card_data" / "slug_index.json")
                     .read_text(encoding="utf-8"))["by_slug"]
    pairs = labelled_pairs()
    if args.limit:
        pairs = pairs[:args.limit]

    if args.list:
        print("%d labelled before/after pairs" % len(pairs))
        for slug, path, _b, _a in pairs:
            print("  %-32s %s" % (slug, path))
        return 0

    dsl_ref = (ROOT / "engine" / "card_effects" / "json"
               / "DSL_REFERENCE.md").read_text(encoding="utf-8")
    arms = ["new", "old"] if args.arm == "both" else [args.arm]
    builders = {a: _prompt_builder(a) for a in arms}

    rows = []
    for i, (slug, _path, before, after) in enumerate(pairs, 1):
        entry = idx.get(slug) or {}
        card = {"slug": slug,
                "functional_text": entry.get("functionalText"),
                "keywords": entry.get("keywords") or []}
        for label, body in (("defective", before), ("clean", after)):
            for arm in arms:
                prompt = builders[arm](card, body, dsl_ref)
                try:
                    reply = ask(args.model, prompt, args.ctx)
                except Exception as exc:
                    print("  !! %s %s %s: %s" % (slug, label, arm, exc))
                    continue
                verdict = flagged(arm, reply)
                rows.append({"slug": slug, "label": label, "arm": arm,
                             "flagged": verdict, "reply": reply})
                print("[%2d/%d] %-30s %-9s %-3s -> %s"
                      % (i, len(pairs), slug, label, arm,
                         {True: "FLAGGED", False: "looks_good",
                          None: "(no verdict)"}[verdict]))

    print("\n%-4s %-24s %s" % ("arm", "metric", "value"))
    for arm in arms:
        d = [r for r in rows if r["arm"] == arm and r["label"] == "defective"]
        c = [r for r in rows if r["arm"] == arm and r["label"] == "clean"]
        rec = sum(1 for r in d if r["flagged"] is True) / len(d) if d else 0
        fp = sum(1 for r in c if r["flagged"] is True) / len(c) if c else 0
        noverd = sum(1 for r in rows if r["arm"] == arm and r["flagged"] is None)
        print("%-4s %-24s %.1f%%  (%d/%d)" % (arm, "recall on defective",
                                              rec * 100,
                                              sum(1 for r in d if r["flagged"] is True),
                                              len(d)))
        print("%-4s %-24s %.1f%%  (%d/%d)" % (arm, "FALSE POSITIVES on clean",
                                              fp * 100,
                                              sum(1 for r in c if r["flagged"] is True),
                                              len(c)))
        if rec + (1 - fp):
            print("%-4s %-24s %.2f" % (arm, "  discrimination", rec - fp))
        print("%-4s %-24s %d" % (arm, "unparseable verdicts", noverd))

    if args.out:
        Path(args.out).write_text(json.dumps(rows, indent=1), encoding="utf-8")
        print("\nwrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
