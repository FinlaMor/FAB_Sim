#!/usr/bin/env python3
"""Author the pending cards whose printed text an IMPLEMENTED card already has.

Card text repeats. Colour variants of one card are the same sentence with a
different number, and unrelated cards share whole sentences outright -- "Deal 4
arcane damage to any target" is both Aether Hail and Ice Bolt. Where the text is
IDENTICAL (after substituting each card's own name), the DSL implementation is
identical too: everything that differs between the printings -- cost, pitch,
power, colour -- comes from the card DB, not from the JSON.

COPYING IS NOT AUTOMATICALLY SAFE, which is why this script holds cards back
rather than doing all of them. insult_to_injury shipped three printings of
identical text with THREE DIFFERENT implementations, and the blue one was
missing a gate the other two had; that is the failure this generator is trying
not to industrialise. Seven hazards are excluded and left for a human:

  printed keywords differ   the DB grants keywords, so a source that declares
                            `conditional_keywords` for a keyword the target does
                            not print would carry a meaningless declaration --
                            or worse, strip something the target really has.
  card types differ         a Block behaves differently from an Action even
                            reading the same sentence.
  hero cards                heroes carry `setup` (weapon zones) and activation
                            metadata that is about the printing, not the text.
  source has card-level     activation_cost / per_turn / cost / cost_modifiers
  metadata and the names    are DSL-authoritative and about that specific card.
  differ                    Safe to carry between colour variants of one card,
                            not between two cards that merely read alike.
  source has unread         audit_params findings mean the source has a
  parameters                parameter the compiler never looks at -- a clause
                            that silently does nothing. Copying it turns one
                            defective card into three. Found the hard way: the
                            first run of this script took audit_params from 15
                            findings to 21 by faithfully reproducing
                            shield_bash's and bonds_of_ancestry's.
  source implements         an empty `abilities` list on a card that HAS
  nothing                   functional text is a card whose text was not
                            implemented, not a card with nothing to do. Copying
                            it manufactures cards that look implemented, count
                            as implemented, and do nothing -- worse than a
                            missing card, which at least raises.
  source's whole            cartilage_crush_blue, chokeslam_yellow and
  implementation is a       fatigue_shot_red each stand in for a restriction the
  dead flag                 engine cannot express with a SET_FLAG nothing reads.
                            Copying one turned test_no_dead_flags' count from 6
                            to 12, and its docstring says never raise it.

A card whose text differs only in a NUMBER is not identical and is skipped by
default; `--substitute-numbers` takes those too, carrying the number across
under three further conditions (see `_substitution`). Those copies carry
`_derived_from` + `_substituted` rather than `_copied_from`, and are pinned by
tests/test_number_substituted_copies.py.

Usage:
    python scripts/copy_identical_text_cards.py --dry-run
    python scripts/copy_identical_text_cards.py --write
    python scripts/copy_identical_text_cards.py --held-back
"""
from __future__ import annotations

import argparse
import collections
import functools
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.audit_params import audit_node, build_index, card_files  # noqa: E402
from scripts.remaining_estimate import (implemented_slugs, is_keyword_only,  # noqa: E402
                                        signature, text_of)

JSON_ROOT = ROOT / "engine" / "card_effects" / "json"
_COLOUR = re.compile(r"_(red|yellow|blue)$")
#: Card-level fields that describe THIS printing rather than its text.
_META = ("activation_cost", "per_turn", "setup", "cost", "cost_modifiers")


def _base(slug):
    return _COLOUR.sub("", slug)


def _flagged_by_audit_params():
    """Slugs with a parameter the compiler never reads.

    An unread parameter fails exactly like an invented type -- nothing errors,
    nothing warns, the clause quietly does nothing -- and is invisible to the
    type-name audit. Copying such a card multiplies a silent defect, so those
    sources are held back until they are fixed.
    """
    index = build_index()
    flagged = set()
    for path in card_files():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(raw, dict) or not raw.get("slug"):
            continue
        findings = []
        _walk_all(raw.get("abilities"), index, findings)
        if findings:
            flagged.add(raw["slug"])
    return flagged


def _walk_all(node, index, out):
    if isinstance(node, dict):
        try:
            out.extend(audit_node(node, index, ()) or [])
        except TypeError:
            out.extend(audit_node(node, index) or [])
        for value in node.values():
            _walk_all(value, index, out)
    elif isinstance(node, list):
        for value in node:
            _walk_all(value, index, out)


def _paths():
    out = {}
    for path in JSON_ROOT.rglob("*.json"):
        rel = path.relative_to(JSON_ROOT)
        if path.stem.endswith("_work_queue") or any(
                p.startswith(".") or p == "needs_review" for p in rel.parts):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(raw, dict) and raw.get("slug"):
            out[raw["slug"]] = path
    return out


def _set_dir(entry, paths, source_slug):
    """Where the new file goes: the source's directory when the target was
    printed in that set, else the target's own first set code."""
    src_dir = paths[source_slug].parent
    codes = {"".join(c for c in i if c.isalpha()).lower()
             for i in (entry.get("setIdentifiers") or [])}
    if src_dir.name in codes:
        return src_dir
    for code in sorted(codes):
        candidate = JSON_ROOT / code
        if candidate.is_dir():
            return candidate
    return src_dir


def _only_sets_dead_flags(raw) -> bool:
    """True when every effect the source has is a SET_FLAG nothing reads.

    Shares the definition of "dead" with tests/test_no_dead_flags.py: a flag no
    engine module mentions and no other card's condition names.
    """
    effects = []

    def walk(node, in_effects):
        """Only nodes reached through an `effects` list are effects.

        A first version collected every dict carrying a "type", which swept up
        `conditions` and `cost` entries too -- so fatigue_shot_red, whose one
        effect is a dead SET_FLAG under an ATTACK_TARGET_IS_HERO condition,
        looked like a card with two different node types and slipped the guard.
        It was copied to blue and yellow twice before this was noticed.
        """
        if isinstance(node, dict):
            if in_effects and node.get("type"):
                effects.append(node)
            for key, value in node.items():
                walk(value, key in ("effects", "then", "else"))
        elif isinstance(node, list):
            for value in node:
                walk(value, in_effects)

    walk(raw.get("abilities"), False)
    if not effects or not all(str(e.get("type", "")).upper() == "SET_FLAG"
                              for e in effects):
        return False
    flags = {e.get("flag") for e in effects if isinstance(e.get("flag"), str)}
    return bool(flags) and all(f in _dead_flag_names() for f in flags)


@functools.lru_cache(maxsize=1)
def _dead_flag_names() -> frozenset:
    import sys as _sys
    _sys.path.insert(0, str(ROOT / "tests"))
    try:
        from test_no_dead_flags import _dead_flags
    except Exception:
        return frozenset()
    return frozenset(_dead_flags())


_NUM = re.compile(r"\d+")


def _numbers_in(node):
    """Every integer the abilities JSON mentions, as strings."""
    return _NUM.findall(json.dumps(node))


def _substitution(entry, src_entry, raw):
    """(old, new) when this pair differs by exactly ONE number that can be
    substituted with confidence, else None.

    Colour variants are usually one sentence with one number changed -- "Deal 1
    arcane damage" / "Deal 3 arcane damage" -- and 221 pending cards match an
    implemented card that way. Copying the source verbatim would give them the
    SOURCE's number, so the copy has to carry the substitution.

    THREE THINGS HAVE TO HOLD, and each rules out a way of getting it wrong:

      exactly one number differs      two differences mean two clauses changed
                                      and nothing says which JSON number is
                                      which.
      the old number appears exactly  more than once and the substitution is
      once in the source's abilities  ambiguous; not at all and the number the
                                      text changed is not modelled, so copying
                                      would silently keep the source's value.
      every number in the abilities   a JSON number the printed text does not
      also appears in the text        contain is something else -- an internal
                                      amount, a zone index, a duration -- and
                                      its presence means the JSON's numbers and
                                      the text's numbers are not in
                                      correspondence, so the one-occurrence
                                      test above proves nothing.
    """
    a = _NUM.findall(signature(src_entry, False))
    b = _NUM.findall(signature(entry, False))
    if len(a) != len(b):
        return None
    diffs = {(x, y) for x, y in zip(a, b) if x != y}
    # A card may print ONE number in several places -- "Deal 2 arcane damage
    # ... Surge - if this deals more than 2 damage" -- and then every printed
    # occurrence changes together in the colour variant. That is still one
    # substitution, so the distinct pairs are what must be unique, not the
    # positions. Requiring a single POSITION held back the whole Surge family.
    if len(diffs) != 1:
        return None
    old, new = diffs.pop()
    abilities = raw.get("abilities") or []
    nums = _numbers_in(abilities)
    if not nums.count(old):
        # The number the text changed is not modelled at all, so copying would
        # silently keep the source's value.
        return None
    if nums.count(old) != a.count(old):
        # The JSON mentions it a different number of times from the printed
        # text, so which occurrences correspond is not established and
        # substituting all of them could change something the text did not.
        return None
    text_nums = set(a)
    if any(n not in text_nums for n in nums):
        return None
    return old, new


def _apply_substitution(abilities, old, new):
    """Replace every whole-number occurrence of `old` in the JSON.

    _substitution has already established that the abilities mention `old`
    exactly as often as the printed text does, so all of them are the same
    printed number and change together -- "Deal 2 arcane damage ... Surge - if
    this deals more than 2 damage" is one number twice, not two numbers.
    """
    blob = json.dumps(abilities)
    pattern = re.compile(r"(?<![\d.])%s(?![\d.])" % re.escape(old))
    swapped, count = pattern.subn(new, blob)
    assert count >= 1, count
    return json.loads(swapped)


def _rank(slug, entry, candidates, idx):
    """Order candidate sources so the most compatible one is tried first.

    Source selection was `sorted(sources)[0]` -- alphabetical -- and the hazard
    checks then ran against whatever that happened to be. flash_bolt_yellow has
    the same card types as flash_bolt_blue and would have copied cleanly, but
    the alphabetical winner was an ACTION reading the same sentence, so the
    whole group was held back for "card types differ" while a perfect source
    sat in the same list. Four cards, and the same shape wherever one sentence
    is printed on both an Instant and an Action.

    Ranked on the things the hazard checks look at, most specific first: the
    same card (a colour variant), then identical types, then identical printed
    keywords. Alphabetical order breaks remaining ties, so the choice stays
    deterministic.
    """
    def key(other_slug):
        other = idx.get(other_slug) or {}
        return (
            0 if _base(other_slug) == _base(slug) else 1,
            0 if (entry.get("types") or []) == (other.get("types") or []) else 1,
            0 if ({str(k).lower() for k in (entry.get("keywords") or [])}
                  == {str(k).lower() for k in (other.get("keywords") or [])}) else 1,
            other_slug,
        )
    return sorted(candidates, key=key)


def plan(substitute_numbers=False):
    idx = json.loads((ROOT / "card_data" / "slug_index.json")
                     .read_text(encoding="utf-8"))["by_slug"]
    have = implemented_slugs()
    paths = _paths()

    playable = {s: e for s, e in idx.items()
                if not e.get("isCardBack") and not e.get("isExpansionSlot")}
    pending = {s: e for s, e in playable.items() if s not in have}
    substantive = {s: e for s, e in pending.items()
                   if text_of(e) and not is_keyword_only(e)}

    by_text = collections.defaultdict(list)
    by_blur = collections.defaultdict(list)
    for slug in have:
        entry = idx.get(slug)
        if entry and text_of(entry):
            by_text[signature(entry, False)].append(slug)
            by_blur[signature(entry, True)].append(slug)

    flagged = _flagged_by_audit_params()

    todo, held = [], []
    for slug, entry in sorted(substantive.items()):
        # EVERY usable source is a candidate, not just the first one found.
        # The old shape picked one source and let the hazard checks pass
        # judgement on it, so a card with a perfect source and an imperfect one
        # was held back whenever the imperfect one sorted first: flash_bolt_
        # yellow shares its EXACT text with an Action and its types with
        # flash_bolt_blue, and was rejected for "card types differ" while blue
        # sat in the same list one substitution away. Exact matches rank ahead
        # of substituted ones (no number to get wrong), and the checks now
        # FILTER candidates rather than deciding on one.
        exact = [(c, None) for c in
                 _rank(slug, entry, by_text.get(signature(entry, False)) or [], idx)]
        blurred = []
        if substitute_numbers:
            for candidate in _rank(slug, entry,
                                   by_blur.get(signature(entry, True), []), idx):
                found = _substitution(entry, idx[candidate],
                                      json.loads(paths[candidate].read_text(
                                          encoding="utf-8")))
                if found:
                    blurred.append((candidate, found))
        best = None
        for source, substitution in exact + blurred:
            src_entry = idx[source]
            raw = json.loads(paths[source].read_text(encoding="utf-8"))
            reasons = _hazards(slug, entry, source, src_entry, raw, flagged)
            if not reasons:
                best = (slug, source, [], raw, entry, substitution)
                break
            if best is None:
                best = (slug, source, reasons, raw, entry, substitution)
        if best is None:
            continue
        (held if best[2] else todo).append(best)
    return todo, held, paths


def _hazards(slug, entry, source, src_entry, raw, flagged):
    """Why this source must NOT be copied to this card, if anything."""
    reasons = []
    if ({str(k).lower() for k in (entry.get("keywords") or [])}
            != {str(k).lower() for k in (src_entry.get("keywords") or [])}):
        reasons.append("printed keywords differ")
    if (entry.get("types") or []) != (src_entry.get("types") or []):
        reasons.append("card types differ")
    if "Hero" in (entry.get("types") or []) or "Hero" in (src_entry.get("types") or []):
        reasons.append("hero card")
    if _base(slug) != _base(source) and any(k in raw for k in _META):
        reasons.append("source carries card-level metadata and the names differ")
    if source in flagged:
        reasons.append("source has unread parameters (audit_params)")
    if _only_sets_dead_flags(raw):
        # cartilage_crush_blue, chokeslam_yellow and fatigue_shot_red each
        # implement a restriction the engine cannot express by writing a
        # SET_FLAG nothing reads, and each says so in its _comment. Copying
        # one turns a single visible gap into three, and tripped
        # test_no_dead_flags' ratchet -- whose docstring says never raise it.
        reasons.append("source's whole implementation is a flag nothing reads")
    if not (raw.get("abilities") or []) and not any(
            raw.get(k) for k in _META):
        # ...UNLESS the implementation is card-level cost machinery.
        # jump_start_red's whole text is "if you control a Hyper Driver,
        # this costs {r} less to play", which is `cost_modifiers` and
        # correctly has no abilities -- a cost must block play legality,
        # never be modelled as an effect. Without the _META exemption this
        # guard held back every such card as unimplemented.
        #
        # `substantive` already excluded keyword-only targets, so an empty
        # source here is a card whose text was NOT implemented -- either a
        # deliberate stub (hamstring_shot_red carries a _comment saying the
        # engine has no cost-increase path) or an oversight. Copying it
        # manufactures cards that LOOK implemented, count as implemented,
        # and do nothing -- the worst outcome available, because a missing
        # card at least raises MissingCardImplementation.
        reasons.append("source implements nothing (empty abilities)")

    return reasons


def _rename_self_references(abilities, source, slug):
    """Repoint strings that name the SOURCE card at the copy instead.

    A card that refers to ITSELF by slug -- `{"flag": "fused_buzz_bolt_blue"}`,
    `{"source_slug": "malign_blue"}` -- must not carry that name into a copy.
    ability_keywords.fuse writes the marker as f"fused_{card.slug}", so a red
    printing gating on the BLUE printing's marker asks whether a different card
    was fused: false in every state, and silent, because a flag nothing sets
    reads exactly like a condition that happens not to hold. Thirty already
    written copies carried this before it was noticed, each one with its whole
    conditional clause quietly switched off.

    The rewrite is unambiguous -- the slug is a card identity, and in a copy it
    can only mean this card -- so this substitutes rather than holding the copy
    back.
    """
    if source not in json.dumps(abilities or []):
        return abilities

    def walk(node):
        if isinstance(node, dict):
            return {k: (v.replace(source, slug) if isinstance(v, str) else walk(v))
                    for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(abilities)


def build(slug, source, raw, entry, substitution=None):
    out = {"slug": slug}
    # Card-level metadata travels only between printings of the SAME card.
    if _base(slug) == _base(source):
        for key in _META:
            if key in raw:
                out[key] = raw[key]
    if raw.get("conditional_keywords"):
        out["conditional_keywords"] = raw["conditional_keywords"]
    if substitution:
        old, new = substitution
        out["abilities"] = _rename_self_references(
            _apply_substitution(raw["abilities"], old, new), source, slug)
        out["_substituted"] = {"from": old, "to": new}
        out["_derived_from"] = source
        out["_comment"] = (
            "Derived from %s, whose printed functional text is identical to "
            "this card's apart from ONE number (%s here, %s there) -- the usual "
            "shape of a colour variant. That number appears exactly once in "
            "%s's abilities, and every number in those abilities also appears "
            "in its printed text, so which JSON value the text changed is not "
            "in doubt; it is substituted here and recorded in _substituted.\n\n"
            "THE DERIVATION IS PINNED, not trusted: "
            "tests/test_number_substituted_copies.py re-applies the same "
            "substitution to %s's current abilities and asserts it still "
            "yields these, and that the two printed texts still differ in "
            "exactly that one number. An edit to either card that breaks the "
            "correspondence fails there rather than leaving the pair silently "
            "out of step -- the insult_to_injury failure, where three "
            "printings of one sentence got three implementations and the blue "
            "one was missing a gate."
            % (source, new, old, source, source))
        out["_copied_from"] = None
        del out["_copied_from"]
        return out
    out["abilities"] = _rename_self_references(raw["abilities"], source, slug)
    out["_comment"] = (
        "Implementation copied verbatim from %s, whose printed functional text "
        "is identical to this card's once each card's own name is substituted "
        "out. Everything that differs between them -- cost, pitch, power, "
        "colour -- comes from the card DB, not from this file, so the DSL is "
        "the same card twice.\n\nTHE COPY IS PINNED, not trusted: "
        "tests/test_copied_card_implementations.py asserts that these abilities "
        "still match %s's and that the two printed texts still agree, so a "
        "later edit to one cannot silently leave the other behind. That is the "
        "insult_to_injury failure -- three printings of one sentence with three "
        "different implementations, the blue one missing a gate the others had."
        % (source, source))
    out["_copied_from"] = source
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--held-back", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--substitute-numbers", action="store_true",
                    help="also take cards whose text matches a source apart "
                         "from ONE number, substituting it (see _substitution)")
    args = ap.parse_args()

    todo, held, paths = plan(substitute_numbers=args.substitute_numbers)

    if args.held_back:
        print("HELD BACK FOR A HUMAN (%d)\n" % len(held))
        for slug, source, reasons, _raw, _entry in held:
            print("  %-34s <- %-30s %s" % (slug, source, "; ".join(reasons)))
        return 0

    print("copyable now: %d    held back: %d" % (len(todo), len(held)))
    if not args.write:
        for slug, source, _r, _raw, _e, sub in todo[:15]:
            print("  %-34s <- %-30s %s"
                  % (slug, source, ("%s->%s" % sub) if sub else ""))
        print("  ...")
        return 0

    written = 0
    for slug, source, _reasons, raw, entry, substitution in todo:
        target_dir = _set_dir(entry, paths, source)
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / (slug + ".json")
        if path.exists():
            continue
        path.write_text(json.dumps(build(slug, source, raw, entry, substitution),
                                   indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
        written += 1
    print("wrote %d card files" % written)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
