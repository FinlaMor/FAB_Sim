#!/usr/bin/env python3
"""Rank the DSL primitives the corpus is waiting on, by cards unlocked.

`scripts/group_work_queue.py` orders the cards a HUMAN can write today. This is
its counterpart for the ones nobody can: the drafting pipeline's triage pass
reads every unimplemented card and answers one question -- is its printed text
expressible in the DSL as it stands? -- and names the primitive when the answer
is no. 919 cards came back "needs-primitive", and they are deliberately never
drafted, because a drafter handed one has two ways to fail and no way to
succeed: invent a type the compiler does not have, or author something adjacent
that compiles and does the wrong thing.

So this is the engine-side backlog, ordered the same way the authoring one is:
by how many cards a single fix would release.

    python scripts/primitive_backlog.py
    python scripts/primitive_backlog.py --limit 40 --cards

TREAT IT AS A SHORTLIST, NOT A VERDICT, for two reasons that pull opposite ways:

  * the triage ran at a point in time and the DSL has moved since. Several
    named primitives already exist -- REF_HAS_KEYWORD is real, "was fused" is a
    FLAG_SET the fuse keyword writes, the soul zone is reachable. Those entries
    are cards ready to draft, not engine work, and the check below flags the
    ones whose name matches a compiled type so they can be re-triaged instead
    of built twice.
  * a card can be blocked by something the triage named vaguely, or by a second
    clause it did not mention. The count is a lower bound on the win and never
    a promise.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

#: The triage results live in the drafting worktree, which is where that pass
#: runs. Read-only from here.
DEFAULT_TRIAGE = Path(r"C:\Users\Joseph\Desktop\FAB_Sim_oxalpha"
                      r"\engine\card_effects\json\.triage")

KEYS = ("missing", "missing_primitives", "primitives", "needs", "reason")


def _compiled_type_names() -> set[str]:
    """Every effect/condition/cost/trigger type the compiler dispatches on."""
    import re
    names: set[str] = set()
    dsl = ROOT / "engine" / "card_effects" / "dsl"
    for module in ("effect_types.py", "condition_types.py", "cost_types.py",
                   "trigger_types.py"):
        try:
            src = (dsl / module).read_text(encoding="utf-8")
        except OSError:
            continue
        names |= set(re.findall(r'"([A-Z][A-Z0-9_]{2,})"', src))
    return names


def _looks_available(label: str, compiled: set[str]) -> bool:
    """Does a compiled type already carry this primitive's name?

    Deliberately crude -- "ref-has-keyword" -> REF_HAS_KEYWORD. It is a prompt
    to re-triage, not a claim that the card is expressible.
    """
    return label.replace("-", "_").upper() in compiled


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--triage", type=Path, default=DEFAULT_TRIAGE)
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--cards", action="store_true",
                    help="list the blocked cards under each primitive")
    args = ap.parse_args()

    if not args.triage.is_dir():
        print(f"no triage results at {args.triage}")
        return 2

    blocked = collections.defaultdict(list)
    total = 0
    for path in sorted(args.triage.glob("*.json")):
        if path.stem.startswith("_"):
            continue
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if row.get("verdict") != "needs-primitive":
            continue
        total += 1
        for key in KEYS:
            value = row.get(key)
            if not value:
                continue
            for item in (value if isinstance(value, list) else [value]):
                blocked[str(item).strip()[:70]].append(path.stem)
            break

    compiled = _compiled_type_names()
    rows = sorted(blocked.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    maybe = [(k, v) for k, v in rows if _looks_available(k, compiled)]

    print(f"{total} cards blocked on a missing primitive, "
          f"{len(rows)} distinct primitives named\n")
    for label, slugs in rows[:args.limit]:
        flag = "  <-- a compiled type already has this name; re-triage" \
            if _looks_available(label, compiled) else ""
        print(f"{len(slugs):4d}  {label}{flag}")
        if args.cards:
            print("        " + ", ".join(sorted(slugs)[:8])
                  + (" ..." if len(slugs) > 8 else ""))

    if maybe:
        print(f"\n{sum(len(v) for _, v in maybe)} of those cards name a "
              f"primitive the DSL already compiles ({len(maybe)} names). Those "
              f"are re-triage, not engine work.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
