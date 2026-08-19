#!/usr/bin/env python3
"""Find card JSON keys the compiler never reads.

    python scripts/audit_params.py            # whole corpus
    python scripts/audit_params.py --set pen

WHY THIS EXISTS
---------------
audit_run.py checks that a node's *type* is real. It cannot see a node whose
type is real but whose PARAMETERS are named something the compiler never looks
at — and that fails identically:

    {"type": "WEAPON_SUBTYPE_IN", "subtypes": ["sword"]}

WEAPON_SUBTYPE_IN reads `values`. Three of the five cards using it authored
`subtypes` (the natural name, given what the condition is called), so they
filtered on an empty list, matched nothing, and could never fire. From a
type-name audit's point of view those three cards are perfect.

The defect is invisible for the same reason the invented-flag class was: nothing
errors, nothing warns, the card just quietly does nothing.

HOW IT WORKS
------------
The compilers are one big dispatch chain of `if ctype == "X":` / `if etype in
(...)` blocks, and each block reads its parameters with `params.get("name")`.
So the set of keys a type actually reads can be extracted from the source rather
than maintained by hand — the same reason audit_run.py generates its
amount-expression list instead of typing one.

A key is reported when it appears on a node in card JSON and the block for that
node's type never reads it. Structural keys consumed by the loader (`type`,
`conditions`, `effects`, ...) are excluded, as are `_comment`-style annotations.

Exit code is 1 if anything is found, so this can gate a run.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DSL_DIR = ROOT / "engine" / "card_effects" / "dsl"
JSON_ROOT = ROOT / "engine" / "card_effects" / "json"

# Keys the LOADER consumes before params is ever built (see loader._compile_*),
# plus annotation keys that are documentation, not data.
STRUCTURAL_KEYS = {
    "type", "conditions", "condition", "effects", "effect", "modes",
    "cost", "additional_cost", "alternative_cost", "target", "filter",
    "choose", "choose_max", "optional", "trigger", "ability_type",
    "slug", "abilities", "setup", "activation_cost", "per_turn",
    "cost_modifiers", "once_per_turn",
}

# Nested-effect keys: their VALUES are effect/condition specs compiled
# separately, so the inner nodes get audited on their own.
NESTED_KEYS = {"then", "else", "else_effects", "when", "if", "on_success",
               "on_consume", "conditions", "effects", "modes", "filter"}


def _dispatch_params(path: Path, var: str) -> dict[str, set[str]]:
    """Map each registered type name -> the params.get() keys its block reads.

    Read from the compiler's own source, so it cannot drift out of date the way
    a hand-maintained table would.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: dict[str, set[str]] = defaultdict(set)

    def names_tested(test) -> list[str]:
        """Type names an `if` test matches, for == and `in (...)` forms."""
        found: list[str] = []
        for node in ast.walk(test):
            if not isinstance(node, ast.Compare):
                continue
            left = node.left
            if not (isinstance(left, ast.Name) and left.id == var):
                continue
            for op, comp in zip(node.ops, node.comparators):
                if isinstance(op, ast.Eq) and isinstance(comp, ast.Constant):
                    if isinstance(comp.value, str):
                        found.append(comp.value)
                elif isinstance(op, ast.In) and isinstance(comp, (ast.Tuple, ast.List, ast.Set)):
                    for elt in comp.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            found.append(elt.value)
        return found

    def keys_read(body) -> set[str]:
        """Every params.get("k") / params["k"] literal inside this block.

        Some blocks read params INDIRECTLY through a local helper:

            def _first_num(*keys):
                for k in keys: v = params.get(k)   # <- key is a variable
            resources = _first_num("resources", "resource_cost", "amount")

        A literal-only scan sees none of those names and reports every card
        using them — PAY_OR_DAMAGE produced 8 such false reports on the first
        run. When a block accesses params with a NON-literal key, every string
        literal in the block is treated as possibly-read. That is deliberately
        over-broad: widening the read set can only ever suppress a report, never
        manufacture one, and a silent false positive here would send someone to
        "fix" a card that is already correct.
        """
        keys: set[str] = set()
        indirect = False
        for stmt in body:
            for node in ast.walk(stmt):
                if (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "get"
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "params"
                        and node.args
                        and not isinstance(node.args[0], ast.Constant)):
                    indirect = True
                elif (isinstance(node, ast.Subscript)
                      and isinstance(node.value, ast.Name)
                      and node.value.id == "params"
                      and not isinstance(node.slice, ast.Constant)):
                    indirect = True
        if indirect:
            for stmt in body:
                for node in ast.walk(stmt):
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        keys.add(node.value)
        for stmt in body:
            for node in ast.walk(stmt):
                if (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "get"
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "params"
                        and node.args
                        and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)):
                    keys.add(node.args[0].value)
                elif (isinstance(node, ast.Subscript)
                      and isinstance(node.value, ast.Name)
                      and node.value.id == "params"
                      and isinstance(node.slice, ast.Constant)
                      and isinstance(node.slice.value, str)):
                    keys.add(node.slice.value)
                # helper(params, "a", "b", ...) — the shared spelling-tolerant
                # readers (_as_list and friends) take the params dict followed by
                # the key names. Refactoring ATTACK_CLASS_IN to use one made the
                # literal-only scan stop seeing "classes" and report 42 MORE
                # cards, all of them correct: a detector that goes blind when the
                # code it inspects is tidied is worse than no detector.
                elif (isinstance(node, ast.Call) and node.args
                      and isinstance(node.args[0], ast.Name)
                      and node.args[0].id == "params"):
                    for arg in node.args[1:]:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            keys.add(arg.value)
        return keys

    for func in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        for stmt in func.body:
            if not isinstance(stmt, ast.If):
                continue
            names = names_tested(stmt.test)
            if not names:
                continue
            read = keys_read(stmt.body)
            for name in names:
                out[name] |= read

    # Keys read OUTSIDE any dispatch block (compile_effect coerces
    # params["amount"] up front, for instance) apply to every type.
    global_keys: set[str] = set()
    for func in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        if func.name not in ("compile_effect", "compile_condition", "compile_cost"):
            continue
        for stmt in func.body:
            if isinstance(stmt, ast.If) and names_tested(stmt.test):
                continue
            global_keys |= keys_read([stmt])
    for name in out:
        out[name] |= global_keys
    return out


# Declarative statics: types whose params are deliberately NOT read by the
# compile block (it returns a no-op) but by a named engine reader instead,
# because the property is continuous, or is consulted outside effect resolution.
#
# The reader FUNCTIONS are parsed for the keys they actually read, so this
# cannot become a lie the way a hand-written allowlist can: audit_run.py's
# ENGINE_FLAGS asserted "die_rolled_six" was engine-written when nothing wrote
# it, and so certified a dead flag for an entire corpus sweep. Scoping to named
# functions rather than whole files matters just as much in the other
# direction — a file-wide scan picks up every .get() in the module and would
# suppress genuine findings on unrelated types.
DECLARATIVE_READERS: dict[str, tuple[tuple[str, str], ...]] = {
    "MATERIAL": (("engine/card_effects/ability_keywords.py", "material_grants"),
                 ("engine/engine.py", "_setup_material_statics")),
    "PLAYABLE_FROM_BANISHED": (("engine/play.py", "_self_playable_from_banished"),),
    "RUNE_GATE": (("engine/play.py", "rune_gate_available"),),
    "DEFENSE_EQUALS": (("engine/play.py", "_apply_dynamic_defense"),),
}


def _keys_read_by(path: Path, func_name: str) -> set[str]:
    """String-literal .get("k") keys inside one named function (nested defs included)."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except OSError:
        return set()
    target = next((n for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef) and n.name == func_name), None)
    if target is None:
        return set()
    keys: set[str] = set()
    for node in ast.walk(target):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            keys.add(node.args[0].value)
    return keys


def _declarative_keys() -> dict[str, set[str]]:
    """Keys each declarative type's reader is actually SEEN to read."""
    out: dict[str, set[str]] = {}
    for type_name, readers in DECLARATIVE_READERS.items():
        keys: set[str] = set()
        for rel, func_name in readers:
            keys |= _keys_read_by(ROOT / rel, func_name)
        out[type_name] = keys
    return out


def build_index() -> dict[str, set[str]]:
    """type name -> keys read, across conditions, effects and costs.

    One flat map: a name can legitimately exist in more than one namespace
    (DESTROY_PERMANENT is both an effect and a cost), and merging is the
    conservative choice — it can only ever suppress a report, never invent one.
    """
    index: dict[str, set[str]] = defaultdict(set)
    for filename, var in (("condition_types.py", "ctype"),
                          ("effect_types.py", "etype"),
                          ("cost_types.py", "ctype")):
        for name, keys in _dispatch_params(DSL_DIR / filename, var).items():
            index[name] |= keys
    for name, keys in _declarative_keys().items():
        if name in index:
            index[name] |= keys
    return index


def card_files(set_code: str | None = None) -> list[Path]:
    return [p for p in JSON_ROOT.rglob("*.json")
            if not p.stem.endswith("_work_queue")
            and "needs_review" not in p.parts
            and not any(part.startswith(".") for part in p.parts)
            and (set_code is None or p.parent.name == set_code)]


def audit_node(node: dict, index: dict[str, set[str]]) -> list[str]:
    ntype = node.get("type")
    if not isinstance(ntype, str) or not ntype:
        return []
    known = index.get(ntype.upper())
    if known is None:
        return []          # unknown type — that is audit_run.py's job, not this
    bad = []
    for key in node:
        if key in STRUCTURAL_KEYS or key in NESTED_KEYS or key.startswith("_"):
            continue
        if key not in known:
            bad.append(f"{ntype} has no parameter {key!r} "
                       f"(reads: {', '.join(sorted(known)) or 'nothing'})")
    return bad


def walk(node, fn):
    if isinstance(node, dict):
        fn(node)
        for v in node.values():
            walk(v, fn)
    elif isinstance(node, list):
        for v in node:
            walk(v, fn)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", dest="set_code", help="set folder to audit")
    ap.add_argument("--quiet", action="store_true", help="summary only")
    args = ap.parse_args()

    index = build_index()
    if len(index) < 100:
        print(f"ERROR: only {len(index)} types extracted from the compilers — "
              "the AST walk is stale, and every check below would pass vacuously.")
        return 2

    paths = card_files(args.set_code)
    print(f"auditing {len(paths)} card file(s) against {len(index)} compiled types\n")

    findings: dict[str, list[str]] = {}
    for path in paths:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        found: list[str] = []
        walk(raw.get("abilities", []), lambda n: found.extend(audit_node(n, index)))
        if found:
            findings[path.stem] = sorted(set(found))

    kinds = Counter(re.sub(r" has no parameter.*", "", f)
                    for fs in findings.values() for f in fs)
    print(f"cards with >=1 unread parameter: {len(findings)} / {len(paths)}"
          f"  ({100 * len(findings) / max(len(paths), 1):.0f}%)")
    if kinds:
        print("\nby type:")
        for kind, n in kinds.most_common(30):
            print(f"   {n:4d}  {kind}")
        if not args.quiet:
            print()
            for slug, fs in sorted(findings.items()):
                print(f"   {slug}")
                for f in fs:
                    print(f"        - {f}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
