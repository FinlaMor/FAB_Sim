"""Repair cards whose ability_type means the ability can never fire.

The audit's ability_type sweep found 80 such cards. The dominant confusion is
between "an ability that TRIGGERS when this attacks" (TRIGGERED + ON_ATTACK) and
"an Attack Reaction CARD" (ability_type ATTACK_REACTION).

Repairs are split by how much inference each needs, and only the tiers that need
none are applied automatically:

  A  the ability ALREADY carries a `trigger` key. Nothing is inferred: the
     ability_type becomes TRIGGERED and the existing trigger stands.
  B  no trigger key, but the card text contains EXACTLY ONE trigger phrase, so
     the mapping is forced. Ambiguous cards (two or more phrases, or none) are
     never guessed at — they are reported for a human.
  C  ability_type INSTANT on a card with no "Instant - <cost>:" activated
     ability. An Instant CARD resolves when played, so it becomes PLAY.

Usage:
  python scripts/fix_ability_types.py            # dry run (default)
  python scripts/fix_ability_types.py --apply
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import audit_run

JSON_ROOT = ROOT / "engine" / "card_effects" / "json"

# Printed wording -> the trigger it denotes. Ordered longest/most specific first
# so "when this hits a hero" is not swallowed by a broader pattern.
TRIGGER_PHRASES: list[tuple[str, str]] = [
    (r"when (?:you )?attacks? with|when this attacks|when \w[\w' ]* attacks", "ON_ATTACK"),
    (r"when this hits|if this hits|when \w[\w' ]* hits", "ON_HIT"),
    (r"when this defends|when \w[\w' ]* defends", "ON_DEFEND"),
    (r"at the (?:start|beginning) of your turn", "START_OF_TURN"),
    (r"at the (?:start|beginning) of your (?:end phase|end step)", "BEGINNING_OF_END_PHASE"),
    (r"when this enters the arena|when \w[\w' ]* enters the arena", "ON_ENTER_PLAY"),
]


def load_index() -> dict:
    raw = json.loads((ROOT / "card_data" / "slug_index.json").read_text(encoding="utf-8"))
    return raw.get("by_slug", raw)


def infer_trigger(text: str) -> list[str]:
    """Every distinct trigger the printed text names."""
    low = text.lower()
    found = []
    for pattern, trigger in TRIGGER_PHRASES:
        if re.search(pattern, low) and trigger not in found:
            found.append(trigger)
    return found


def card_path(slug: str) -> Path | None:
    hits = [p for p in JSON_ROOT.rglob(f"{slug}.json") if ".quarantine" not in p.parts]
    return hits[0] if hits else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="Write the repairs (default is a dry run).")
    args = ap.parse_args()

    index = load_index()
    findings = audit_run.audit(audit_run.card_files(), index)

    tiers: Counter = Counter()
    manual: list[tuple[str, str, list[str]]] = []
    changes: list[tuple[Path, dict, str]] = []

    for slug, msgs in sorted(findings.items()):
        hits = [m for m in msgs if "not one" in m or "INSTANT but the text" in m]
        if not hits:
            continue
        path = card_path(slug)
        if path is None:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        text = (index.get(slug) or {}).get("functionalText") or ""
        abilities = data.get("abilities") or []
        touched = False

        for msg in hits:
            m = re.search(r"ability\[(\d+)\]", msg)
            if not m:
                continue
            i = int(m.group(1))
            if i >= len(abilities):
                continue
            ability = abilities[i]

            if "INSTANT but the text" in msg:
                ability["ability_type"] = "PLAY"          # tier C
                tiers["C: INSTANT -> PLAY"] += 1
                touched = True
                continue

            existing = ability.get("trigger")
            if existing:                                   # tier A
                ability["ability_type"] = "TRIGGERED"
                tiers["A: kept existing trigger"] += 1
                touched = True
                continue

            inferred = infer_trigger(text)                 # tier B
            if len(inferred) == 1:
                ability["ability_type"] = "TRIGGERED"
                ability["trigger"] = inferred[0]
                tiers[f"B: inferred {inferred[0]}"] += 1
                touched = True
            else:
                manual.append((slug, msg, inferred))

        if touched:
            changes.append((path, data, slug))

    print(f"cards with an ability_type defect : {len([s for s, m in findings.items() if any('not one' in x or 'INSTANT but the text' in x for x in m)])}")
    print(f"cards repaired automatically      : {len(changes)}")
    print(f"abilities left for manual review  : {len(manual)}\n")
    for tier, n in sorted(tiers.items()):
        print(f"  {n:4}  {tier}")

    if manual:
        print("\nAMBIGUOUS — not guessed at:")
        for slug, msg, inferred in manual:
            why = ", ".join(inferred) if inferred else "no trigger phrase in text"
            print(f"  {slug:36} [{why}]")

    if not args.apply:
        print("\n(dry run — pass --apply to write)")
        return 0

    for path, data, slug in changes:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(f"\nwrote {len(changes)} card file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
