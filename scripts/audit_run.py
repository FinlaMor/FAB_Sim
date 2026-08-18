#!/usr/bin/env python3
"""Audit pipeline output for the defect classes that slip past the gates.

    python scripts/audit_run.py --set pen                 # whole set
    python scripts/audit_run.py --set pen --slugs f.json  # just these slugs
    python scripts/audit_run.py --set pen --since-head    # only files git says changed

Every check here found a real, large defect class in a previous run, and every
one is invisible to the existing gates: the cards LOAD, are not stubs, and can
pass a generated test while still being wrong.

  invented flag      FLAG_SET on a flag nothing ever sets. The condition is
                     permanently false, so the ability CAN NEVER FIRE. 167 flags
                     across 195 cards corpus-wide when first swept.
  fabricated keyword an effect granting a keyword the printed text never
                     mentions. 27 cards granted an INTIMIDATE they never had.
  invented amount    an "amount" string the resolver does not know; it resolves
                     to 0, so the effect silently does nothing.
  bad ability_type   an EFFECT type used as an ability_type; the ability is
                     malformed and never runs.
  duplicate slug     one slug defined by two files — the loader rejects BOTH,
                     so the card becomes unimplemented.

Exit code is 1 if any defect is found, so this can gate a run.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSON_ROOT = ROOT / "engine" / "card_effects" / "json"

VALID_ABILITY_TYPES = {
    "PLAY", "ACTION", "MODAL", "ATTACK_REACTION", "DEFENSE_REACTION", "ACTIVATE",
    "INSTANT", "TRIGGERED", "STATIC", "STATIC_TRIGGERED", "DELAYED_TRIGGERED",
    "WHILE_STATIC", "REPLACEMENT", "COST_MODIFIER", "DEFEND_RESTRICTION",
}
# Turn-effect markers engine code actually writes. Anything else must be set by
# the same card, or the ability can never fire.
ENGINE_FLAGS = {
    "die_rolled_six", "activated_cannon", "boosted_this_turn", "cranked_this_turn",
    "crowd_booed", "crowd_cheered", "first_attack_-2p", "played_lightning",
    "next_weapon_attack_go_again", "next_weapon_attack_hit_go_again",
    "ripple_away_active",
}
ENGINE_FLAG_PREFIXES = ("fused_", "destroyed_this_turn:")
KEYWORD_EFFECTS = {
    "INTIMIDATE": "intimidate", "DOMINATE": "dominate", "OVERPOWER": "overpower",
    "STEALTH": "stealth", "PIERCING": "piercing", "BATTLEWORN": "battleworn",
    "TEMPER": "temper", "BLOOD_DEBT": "blood debt",
}
KNOWN_AMOUNT_TOKENS = {"X", "ROLL_NUMBER", "ROLL_RESULT", "ROLL_NUMBER_HALF_ROUND_DOWN"}

# Amount EXPRESSIONS, i.e. {"amount": {"type": ...}}. Read from the resolver's own
# dispatch chain rather than hard-coded, so the audit cannot drift out of date the
# way the string-token list would.
def _known_amount_expressions() -> set[str]:
    src = ROOT / "engine" / "card_effects" / "dsl" / "effect_types.py"
    try:
        text = src.read_text(encoding="utf-8")
    except OSError:
        return set()
    names = set(re.findall(r'atype == "([A-Z_]+)"', text))
    for grp in re.findall(r'atype in \(([^)]*)\)', text):
        names |= set(re.findall(r'"([A-Z_]+)"', grp))
    return names


KNOWN_AMOUNT_EXPRESSIONS = _known_amount_expressions()


def _walk(node, fn):
    if isinstance(node, dict):
        fn(node)
        for v in node.values():
            _walk(v, fn)
    elif isinstance(node, list):
        for v in node:
            _walk(v, fn)


def card_files() -> list[Path]:
    return [p for p in JSON_ROOT.rglob("*.json")
            if not p.stem.endswith("_work_queue")
            and "needs_review" not in p.parts
            and not any(part.startswith(".") for part in p.parts)]


def flags_set_anywhere() -> set[str]:
    """Flags set by ANY card node — a cost can set a flag, not just SET_FLAG."""
    out: set[str] = set()
    for path in card_files():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue

        def visit(node):
            flag = node.get("flag")
            if isinstance(flag, str) and flag and (node.get("type") or "").upper() != "FLAG_SET":
                out.add(flag.lower())
        _walk(raw.get("abilities", []), visit)
    return out


def known_flag(flag: str, settable: set[str]) -> bool:
    low = flag.lower()
    return (low in settable or low in ENGINE_FLAGS
            or low.startswith(ENGINE_FLAG_PREFIXES))


def audit(paths: list[Path], index: dict) -> dict[str, list[str]]:
    settable = flags_set_anywhere()
    findings: dict[str, list[str]] = {}
    for path in paths:
        slug = path.stem
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            findings.setdefault(slug, []).append(f"unparseable JSON: {exc}")
            continue
        if not isinstance(raw, dict):
            findings.setdefault(slug, []).append("top level is not a JSON object")
            continue

        text = ((index.get(slug) or {}).get("functionalText") or "").lower()
        kws = " ".join((index.get(slug) or {}).get("keywords") or []).lower()
        haystack = f"{text} {kws}"
        found: list[str] = []

        type_text = ((index.get(slug) or {}).get("typeText") or "")
        tt_low = type_text.lower()

        for i, ability in enumerate(raw.get("abilities") or []):
            at = (ability.get("ability_type") or "").upper()
            if at and at not in VALID_ABILITY_TYPES:
                found.append(f"ability[{i}] bad ability_type {at!r}")

            # A reaction ability_type on a card that is not a reaction never
            # fires — as fatal as a dead flag, and until now the only defect
            # class with NO audit coverage (it was found by hand in five
            # separate card groups: biting_blade, glint, rushing_river,
            # grow_claws/grow_wings, push_the_point).
            #
            # Legitimate when EITHER the printed card type is that reaction, OR
            # the card's own text grants one — an Arakni demi-hero reads
            # "Once per Turn Attack Reaction - ...", which is correct despite
            # its type being "Demi-Hero". Checking type alone would flag those.
            for kind, label in (("ATTACK_REACTION", "attack reaction"),
                                ("DEFENSE_REACTION", "defense reaction")):
                if at != kind:
                    continue
                if label in tt_low or label in text:
                    continue
                found.append(
                    f"ability[{i}] {kind} on a card that is not one "
                    f"({type_text or 'unknown type'}) — never fires")

            # ability_type INSTANT means an ACTIVATED ability with instant
            # timing, signalled in the text as "Instant - <cost>: ...". An
            # Instant CARD that resolves when played is PLAY; INSTANT there maps
            # to ON_ACTIVATE and never fires (angelic_descent_yellow,
            # comet_collision_red).
            if at == "INSTANT" and "instant" not in text:
                found.append(
                    f"ability[{i}] INSTANT but the text has no 'Instant -' "
                    f"activated ability ({type_text or 'unknown type'}) — "
                    "an Instant CARD resolving on play is PLAY")

        def visit(node):
            ntype = (node.get("type") or "").upper()
            if ntype == "FLAG_SET":
                flag = str(node.get("flag") or "")
                if flag and not known_flag(flag, settable):
                    found.append(f"invented flag {flag!r} (can never fire)")
            if ntype in KEYWORD_EFFECTS and KEYWORD_EFFECTS[ntype] not in haystack:
                found.append(f"fabricated {ntype} (not in card text)")
            amount = node.get("amount")
            # DICT amounts ({"type": "HALF", "value": ...}) are a second, newer
            # authoring form resolved by _resolve_amount's own dispatch chain.
            # This check previously inspected STRING amounts only, so an invented
            # dict amount was invisible — and it resolves to 0 exactly like an
            # invented string, silently doing nothing. Real cases found on the
            # first run that used the new syntax: a CONDITION type used as an
            # amount ({"type": "FLAG_SET", ...}) and a bare {"type":
            # "DAMAGE_AMOUNT"}.
            if isinstance(amount, dict):
                atype = (amount.get("type") or "").upper()
                if atype and atype not in KNOWN_AMOUNT_EXPRESSIONS:
                    found.append(
                        f"invented amount expression {atype!r} (resolves to 0)")
            if isinstance(amount, str):
                bare = amount.strip().lstrip("-")
                if not bare.isdigit() and amount not in KNOWN_AMOUNT_TOKENS:
                    found.append(f"invented amount {amount!r} (resolves to 0)")
        _walk(raw.get("abilities", []), visit)

        if found:
            findings[slug] = sorted(set(found))
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", dest="set_code", help="set folder to audit")
    ap.add_argument("--slugs", help="JSON file holding a list of slugs to audit")
    ap.add_argument("--since-head", action="store_true",
                    help="only files git reports as changed/added")
    args = ap.parse_args()

    index = json.loads((ROOT / "card_data" / "slug_index.json").read_text(encoding="utf-8"))
    index = index.get("by_slug", index)

    paths = card_files()
    if args.set_code:
        paths = [p for p in paths if p.parent.name == args.set_code]
    if args.slugs:
        wanted = set(json.loads(Path(args.slugs).read_text(encoding="utf-8")))
        paths = [p for p in paths if p.stem in wanted]
    if args.since_head:
        out = subprocess.run(["git", "status", "--short"], cwd=ROOT,
                             capture_output=True, text=True).stdout
        changed = {Path(l[3:].strip()).stem for l in out.splitlines()
                   if l[3:].strip().endswith(".json") and not l.startswith(" D")}
        paths = [p for p in paths if p.stem in changed]

    print(f"auditing {len(paths)} card file(s)\n")

    # Load health — a duplicate slug makes BOTH copies unimplemented.
    sys.path.insert(0, str(ROOT))
    from engine.card_effects.dsl.loader import (
        DUPLICATE_SLUGS, LOAD_ERRORS, load_all_cards,
    )
    load_all_cards()
    if LOAD_ERRORS:
        print(f"LOAD ERRORS: {len(LOAD_ERRORS)}")
        for slug, err in list(LOAD_ERRORS.items())[:10]:
            print(f"   {slug}: {str(err)[:110]}")
    if DUPLICATE_SLUGS:
        print(f"DUPLICATE SLUGS: {len(DUPLICATE_SLUGS)} (both copies rejected)")
        for slug, files in DUPLICATE_SLUGS.items():
            print(f"   {slug}: {[Path(f).parent.name + '/' for f in files]}")
    if not LOAD_ERRORS and not DUPLICATE_SLUGS:
        print("load health: OK (no errors, no duplicate slugs)")

    findings = audit(paths, index)
    kinds = Counter(re.sub(r"\s.*", "", f).strip()
                    for fs in findings.values() for f in fs)
    print(f"\ncards with >=1 defect: {len(findings)} / {len(paths)}"
          f"  ({100 * len(findings) / max(len(paths), 1):.0f}%)")
    if kinds:
        print("\nby kind:")
        for kind, n in kinds.most_common():
            print(f"   {n:4d}  {kind}")
        print()
        for slug, fs in sorted(findings.items()):
            print(f"   {slug}")
            for f in fs:
                print(f"        - {f}")

    return 1 if (findings or LOAD_ERRORS or DUPLICATE_SLUGS) else 0


if __name__ == "__main__":
    sys.exit(main())
