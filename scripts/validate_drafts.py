"""Compile every draft in `.drafts/` and say which ones are adoptable.

A draft is a proposal. This is the mechanical gate it has to pass before anyone
spends review time on it, and before it goes anywhere a game will load it: the
engine refuses to start if a single card JSON is malformed, so a bad draft
adopted into a set directory breaks every game, not just its own card.

Three checks, in order of how loudly they fail:

  parse      the file is JSON and names the slug it was asked for.
  compile    every ability compiles against the LIVE loader. compile_effect
             raises on a type it does not have, so this covers invented types
             completely -- which is the loud failure, and the good case.

The quiet failure it does NOT cover: a parameter the handler never reads. That
does not error, the effect just does something other than what the card says,
and it is the defect class this whole effort has been chasing.
scripts/audit_params.py finds those, but only once a card is in a set
directory.

What this canNOT check is whether the draft means what the card says. That
needs a reader. This only establishes that a draft is worth reading.

    python scripts/validate_drafts.py            # summary
    python scripts/validate_drafts.py --detail   # per-card problems
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DRAFTS = ROOT / "engine" / "card_effects" / "json" / ".drafts"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--detail", action="store_true")
    args = ap.parse_args()

    if not DRAFTS.exists():
        print("no .drafts/ yet")
        return 0

    ok, bad = [], []
    for path in sorted(DRAFTS.glob("*.json")):
        if path.stem.startswith("_"):
            continue
        problems = []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            bad.append((path.stem, [f"unparseable: {exc}"]))
            continue
        if raw.get("slug") != path.stem:
            problems.append(f'slug is {raw.get("slug")!r}, file is {path.stem!r}')

        # The whole check: does it COMPILE against the live loader?
        # compile_effect RAISES on a type it does not have, so this already
        # covers "unknown type" completely. An earlier version of this script
        # also scanned the compiler source for type names with a regex, and
        # that regex read only the FIRST name out of
        # `if etype in ("CONDITIONAL", "CONDITIONAL_EFFECT", "IF")` -- so it
        # reported two perfectly good drafts as using an invented type. A
        # validator that rejects valid work is worse than no validator: it
        # would have had me rewrite drafts that were already right.
        try:
            from engine.card_effects.dsl.loader import _compile_ability
            for ab in raw.get("abilities") or []:
                _compile_ability(ab)
        except Exception as exc:
            problems.append(f"does not compile: {type(exc).__name__}: {exc}")

        (bad if problems else ok).append((path.stem, problems))

    print(f"drafts: {len(ok) + len(bad)}   compile: {len(ok)}   problems: {len(bad)}")
    if args.detail:
        for slug, problems in bad:
            print(f"\n{slug}")
            for p in problems:
                print(f"    {p}")
    elif bad:
        print("  " + ", ".join(s for s, _ in bad[:12]))
        print("  (--detail for the reasons)")
    return 0


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
