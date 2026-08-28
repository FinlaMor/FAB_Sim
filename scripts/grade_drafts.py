#!/usr/bin/env python3
"""Run the corpus's known defect sweeps against DRAFTS, before adoption.

WHY. Every defect class found in the implemented corpus was a card that
compiles, uses real types, reads every parameter, and still does the wrong
thing. `validate_drafts.py` proves a draft loads; `audit_params.py --path`
proves it reads what it writes. Neither can see a card that is wrong in the way
that has actually been costing us cards, and "a reviewer said ok" was the other
signal that missed all five clusters.

So the sweeps that found those clusters run here too, against drafts, while
rejecting one is still free. A hit is not proof of a bug -- Luminaris is a
standing example of a legitimate hit in sweep A -- it is a card that must be
read before it is adopted.

    python scripts/grade_drafts.py             # summary
    python scripts/grade_drafts.py --detail    # per-card, per-sweep
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DRAFTS = ROOT / "engine" / "card_effects" / "json" / ".drafts"
INDEX = ROOT / "card_data" / "slug_index.json"

_GATED_GO_AGAIN = re.compile(r"\b(if|whenever|while)\b[^.]{0,120}?\bgo again\b", re.I)


def _nodes(raw: dict, wanted: str) -> list[dict]:
    found: list[dict] = []

    def walk(n):
        if isinstance(n, dict):
            if n.get("type") == wanted:
                found.append(n)
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(raw.get("abilities"))
    return found


def _grants_go_again_on_attack(raw: dict) -> bool:
    """The shape loader.conditional_keywords() recognises: an ability gated on
    SOURCE_IS_ATTACK that grants go again. Checked on raw JSON because a draft
    is not in the registry get_card() reads."""
    for ability in raw.get("abilities") or []:
        conds = [str(c.get("type", "")).upper()
                 for c in (ability.get("conditions") or [])]
        if "SOURCE_IS_ATTACK" not in conds:
            continue
        for eff in ability.get("effects") or []:
            etype = str(eff.get("type", "")).upper()
            name = eff.get("keyword") if etype == "GAIN" else etype
            if str(name or "").replace("_", "").lower() == "goagain":
                return True
    return False


# --- the sweeps -------------------------------------------------------------

def _prints_go_again_outright(text: str) -> bool:
    """True when a line IS the keyword, e.g. a card whose box reads

        **Go again**

    on its own. That is an unconditional printed keyword; a gated sentence
    elsewhere on the card is about something else. Channel the Thunder Steppe
    prints go again AND grants it to action cards you play -- reading only the
    second sentence calls a correct card broken.
    """
    for line in text.splitlines():
        if line.replace("*", "").replace("-", "").strip().lower() == "go again":
            return True
    return False


def _go_again_is_about_itself(text: str, name: str) -> bool:
    """Luminaris's distinction, applied to the printed text.

    "the attack gets go again" and "attack action cards with combo gain go
    again" hand the keyword to ANOTHER card; the DB lists it on this one only
    because it flattens the sentence. Only a card that gives ITSELF go again
    can have its printed keyword stripped.
    """
    low = text.lower()
    subjects = ["this get", "this gain", "it get", "it gain"]
    if name:
        subjects += [f"{name.lower()} get", f"{name.lower()} gain"]
    return any(sub in low for sub in subjects)


def sweep_gated_go_again(raw, entry):
    """Cluster 5: card prints GoAgain, text gates it, JSON never strips it."""
    kws = [str(k).lower() for k in (entry.get("keywords") or [])]
    text = entry.get("functionalText") or ""
    if "goagain" not in kws or not _GATED_GO_AGAIN.search(text):
        return []
    if _prints_go_again_outright(text):
        return []
    if not _go_again_is_about_itself(text, entry.get("name") or ""):
        return []
    if _grants_go_again_on_attack(raw):
        return []
    return ["prints GoAgain and the text gates it, but no SOURCE_IS_ATTACK "
            "ability grants it -- the printed keyword stays unconditional"]


def sweep_inject_trigger_string_form(raw, entry):
    """Cluster 4's trap: conditions on a string-form INJECT_TRIGGER are eaten by
    the loader and never reach the trigger."""
    out = []
    for n in _nodes(raw, "INJECT_TRIGGER"):
        if not isinstance(n.get("trigger"), dict) and n.get("conditions"):
            out.append(
                "INJECT_TRIGGER uses the string form with conditions "
                f"{[c.get('type') for c in n['conditions']]} -- if those are "
                "meant to gate FIRING they never arrive; use the dict form")
    return out


def _mentions(node, wanted: str) -> bool:
    """Whether a condition type appears ANYWHERE beneath this node.

    The gate does not have to sit in the trigger's own `conditions`: a card may
    put it in a nested CONDITIONAL_EFFECT `when`, which fires at the same
    moment and additionally lets the rest of the trigger still run. Demanding
    one spelling reported a correctly-gated card as broken.
    """
    if isinstance(node, dict):
        if str(node.get("type", "")).upper() == wanted:
            return True
        return any(_mentions(v, wanted) for v in node.values())
    if isinstance(node, list):
        return any(_mentions(v, wanted) for v in node)
    return False


def sweep_hits_a_hero(raw, entry):
    """Cluster 4: a granted trigger whose text names a hero, ungated."""
    text = (entry.get("functionalText") or "").lower()
    if "hits a hero" not in text:
        return []
    out = []
    for n in _nodes(raw, "INJECT_TRIGGER"):
        spec = n.get("trigger")
        if not isinstance(spec, dict):
            continue
        # Only an ON_HIT trigger is the one the sentence is about. Flashfreeze
        # grants an ON_ATTACK rider as well, and requiring the hero gate on
        # THAT accused a correct card.
        if str(spec.get("trigger_type", "")).upper() != "ON_HIT":
            continue
        if not _mentions(spec, "ATTACK_TARGET_IS_HERO"):
            out.append("text says 'hits a hero' but the injected ON_HIT "
                       "trigger is not gated on ATTACK_TARGET_IS_HERO")
    return out


_SELF_DEFENSE = re.compile("(?:^|[^a-z])(?:this|it) +gets", re.I)


def sweep_untargeted_defense(raw, entry):
    """Cluster 1: MODIFY_DEFENSE_VALUE that moves the TOTAL where the card
    means one card.

    Untargeted is NOT automatically wrong. With no target the handler moves the
    defending total, and for "when this defends, it gets +2{d}" that is the same
    number -- the two part company only where the card is restrictive ("target
    defending action card"), which is the shape that produced the corpus bug.
    Flagging every untargeted node cried wolf on nine self-modifying cards, so
    the sweep asks what the TEXT says rather than only what the JSON omits.

    A duration on an untargeted node is reported separately: the total is
    rebuilt per combat, so "until end of turn" written on it does not survive
    the way the card says it should.
    """
    text = entry.get("functionalText") or ""
    out = []
    for n in _nodes(raw, "MODIFY_DEFENSE_VALUE"):
        if n.get("target"):
            continue
        if not _SELF_DEFENSE.search(text):
            out.append("MODIFY_DEFENSE_VALUE with no 'target' and text that "
                       "does not say 'this/it gets' -- moves the whole "
                       "defending total")
        elif n.get("duration"):
            out.append(f"MODIFY_DEFENSE_VALUE has duration {n['duration']!r} "
                       "on the defending TOTAL, which is rebuilt per combat; "
                       "a lasting buff belongs on the card")
    return out


def sweep_create_token_nested_effects(raw, entry):
    """Cluster 3: clauses nested under CREATE_TOKEN that the handler drops."""
    return ["CREATE_TOKEN carries nested 'effects', which the handler does not "
            "resolve -- use record_as and a following effect"
            for n in _nodes(raw, "CREATE_TOKEN") if n.get("effects")]


# Text that hands the token to someone OTHER than this card's controller.
# Deliberately conservative: "under their control" and "under an opposing
# hero's control" are the phrasings the corpus review actually cited.
_OTHER_CONTROLLER = re.compile(
    "under (an|another|the (opposing|defending)|their|his or her|your "
    "opponent's)[^.]{0,40}control", re.I)


def sweep_token_controller(raw, entry):
    """CREATE_TOKEN that omits `player` on a card whose text gives the token
    to someone else.

    create_token() defaults to the ability's own controller, so a card reading
    "create a Vigor token under another hero's control" hands the benefit to
    the wrong player -- and, like every defect in this effort, it fails quietly:
    a token IS created, just for the wrong person.
    """
    text = entry.get("functionalText") or ""
    if not _OTHER_CONTROLLER.search(text):
        return []
    return ["text creates the token under ANOTHER hero's control but "
            "CREATE_TOKEN has no 'player' -- it defaults to this card's "
            "controller"
            for n in _nodes(raw, "CREATE_TOKEN")
            if not n.get("player") and not n.get("controller")]


SWEEPS = {
    "gated go again": sweep_gated_go_again,
    "INJECT_TRIGGER string form": sweep_inject_trigger_string_form,
    "hits a hero ungated": sweep_hits_a_hero,
    "untargeted defense": sweep_untargeted_defense,
    "CREATE_TOKEN nested effects": sweep_create_token_nested_effects,
    "token wrong controller": sweep_token_controller,
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--detail", action="store_true")
    ap.add_argument("--sweep", help="run only this sweep")
    args = ap.parse_args()

    # PREMISE. A regex that matches nothing makes its sweep pass silently, and
    # that is not hypothetical here: a bash heredoc turned "\b" into a literal
    # backspace byte, which grep renders invisibly and re.compile accepts
    # without complaint. The sweep reported nine cards as defective because its
    # self-reference test could never fire. Checked against known text so the
    # tool fails loudly instead of lying quietly.
    for name, rx, positive in (
            ("_SELF_DEFENSE", _SELF_DEFENSE, "If you do, it gets +2{d}"),
            ("_GATED_GO_AGAIN", _GATED_GO_AGAIN,
             "If you have attacked, this gets go again"),
            ("_OTHER_CONTROLLER", _OTHER_CONTROLLER,
             "create a Vigor token under another hero's control")):
        if not rx.search(positive):
            print(f"ERROR: {name} does not match its own example "
                  f"({rx.pattern!r}) -- every sweep using it is vacuous.")
            return 2

    index = json.loads(INDEX.read_text(encoding="utf-8"))["by_slug"]
    per_sweep: dict[str, list[str]] = defaultdict(list)
    detail: dict[str, list[str]] = defaultdict(list)
    total = 0

    for path in sorted(DRAFTS.glob("*.json")):
        if path.stem.startswith("_"):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        slug = raw.get("slug") or path.stem
        entry = index.get(slug) or {}
        total += 1
        for name, fn in SWEEPS.items():
            if args.sweep and name != args.sweep:
                continue
            for problem in fn(raw, entry):
                per_sweep[name].append(slug)
                detail[slug].append(f"[{name}] {problem}")

    print(f"graded {total} draft(s)\n")
    flagged = sorted(detail)
    for name in SWEEPS:
        if args.sweep and name != args.sweep:
            continue
        print(f"  {len(set(per_sweep[name])):4d}  {name}")
    print(f"\ncards flagged by >=1 sweep: {len(flagged)} / {total}")

    if args.detail:
        print()
        for slug in flagged:
            print(f"  {slug}")
            for line in detail[slug]:
                print(f"       - {line}")
    return 1 if flagged else 0


if __name__ == "__main__":
    raise SystemExit(main())
