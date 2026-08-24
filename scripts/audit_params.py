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
#
# This is TWO lists, not one, because the loader consumes different keys at the
# two levels and a single flat list gives effect nodes the ability level's
# exemptions. That is not hypothetical: "target" sat in the flat list, so this
# audit — whose whole job is unread parameters — skipped the most consequential
# parameter there is. It hid 33 cards whose BANISH named a zone and a player and
# got neither, 17 of which banished from their OWN deck while the card said the
# opponent's.
# Only nodes carrying a "type" key are audited, and abilities key on
# "ability_type" instead — so every node that reaches audit_node is an effect,
# condition or cost node, and ability-level exemptions never applied to
# anything. Carrying them in the same set only ever leaked to effect nodes.
#
# At effect/condition/cost level the loader pops exactly one key, "conditions"
# (loader._compile_effect), and hands everything else to the compiler as params.
# So everything else must be read by the handler or it is dead. In particular
# "target" and "filter" are ordinary params here: each effect that wants them
# has to read them itself, and most do not.
STRUCTURAL_KEYS = {"type", "conditions"}

#: Sentinel in a type's read-set meaning "this handler consumes params wholesale,
#: so every key on it is read". Not a real parameter name.
WHOLESALE = "*"

# Nested-effect keys: their VALUES are effect/condition specs compiled
# separately, so the inner nodes get audited on their own.
NESTED_KEYS = {"then", "else", "else_effects", "when", "if", "on_success",
               "on_consume", "conditions", "effects", "modes"}


def _strip_docstrings(body):
    """Drop docstring statements from a body, at every nesting level.

    Only the leading string-expression of a function counts as a docstring, so
    this walks nested FunctionDefs rather than filtering every bare string.
    """
    for stmt in body:
        for node in ast.walk(stmt):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef, ast.Module)):
                inner = getattr(node, "body", None)
                if (inner and isinstance(inner[0], ast.Expr)
                        and isinstance(inner[0].value, ast.Constant)
                        and isinstance(inner[0].value.value, str)):
                    node.body = inner[1:] or [ast.Pass()]
    return [st for st in body
            if not (isinstance(st, ast.Expr)
                    and isinstance(st.value, ast.Constant)
                    and isinstance(st.value.value, str))]


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

    # Module-level helpers, so a block that hands `params` to one can be
    # credited with the keys the HELPER reads. _hand_card_filter(params) is
    # shared by the DISCARD effect and the DISCARD_CARD cost precisely so the
    # two agree on what "discard a yellow card" means; without this the scan
    # sees no literals at the call site and reports every card using the shared
    # vocabulary. The same trap the helper(params, "a", "b") rule below was
    # added for — a detector that goes blind when the code it inspects is
    # factored into a shared function is worse than no detector.
    module_funcs = {n.name: n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef)}
    # A helper can also be IMPORTED — cost_types.DISCARD_CARD shares
    # effect_types._hand_card_filter so the cost and the effect agree on what
    # "discard a yellow card" means. Resolve those too, or the audit is blind
    # exactly where the compiler is most correct.
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        src = ROOT / (node.module.replace(".", "/") + ".py")
        if not src.is_file():
            continue
        try:
            other = ast.parse(src.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        wanted = {a.name for a in node.names}
        for fn in ast.walk(other):
            if isinstance(fn, ast.FunctionDef) and fn.name in wanted:
                module_funcs.setdefault(fn.name, fn)

    def keys_read(body, _seen=None) -> set[str]:
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
        seen = _seen or frozenset()
        # A DOCSTRING is a string constant like any other, and the indirect-read
        # path below adds every string literal it can see. Descending into a
        # helper therefore swept that helper's prose into the read set --
        # which does not just make the report unreadable, it WIDENS the set with
        # arbitrary text and so suppresses real findings. Strip them first.
        body = [st for st in _strip_docstrings(body)]
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
                # Wholesale consumption: `{k: v for k, v in params.items()}`,
                # `dict(params)`, `**params`. The block reads EVERY key, so no
                # parameter on it can be unread. RESTRICT_DEFENDERS builds its
                # filter this way and the literal-only scan reported its
                # "equipment" key as dead on two cards that work — a false
                # positive in a report this long is not a small cost, it is how
                # someone learns to stop believing the report.
                elif (isinstance(node, ast.Attribute)
                      and node.attr in ("items", "keys", "values")
                      and isinstance(node.value, ast.Name)
                      and node.value.id == "params"):
                    keys.add(WHOLESALE)
                elif (isinstance(node, ast.keyword) and node.arg is None
                      and isinstance(node.value, ast.Name)
                      and node.value.id == "params"):
                    keys.add(WHOLESALE)
                elif (isinstance(node, ast.Call)
                      and isinstance(node.func, ast.Name)
                      and node.func.id == "dict"
                      and any(isinstance(a, ast.Name) and a.id == "params"
                              for a in node.args)):
                    keys.add(WHOLESALE)
                # compile_condition(inner_t, params) — the block hands the WHOLE
                # params dict to another dispatcher whose type is chosen at
                # runtime, so the keys it reads are the INNER type's, not this
                # one's. NOT's flattened form does exactly this, and reporting
                # fyendals_spring_tunic's counter_type/min as unread was a false
                # positive on a card that demonstrably works.
                elif (isinstance(node, ast.Call)
                      and isinstance(node.func, ast.Name)
                      and node.func.id in ("compile_condition", "compile_effect",
                                           "compile_cost")
                      and any(isinstance(a, ast.Name) and a.id == "params"
                              for a in node.args)):
                    keys.add(WHOLESALE)
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
                    # helper(params) with no key literals: the names it reads
                    # are inside the helper, so descend into it. Guarded against
                    # recursion by the visited set.
                    fn = (module_funcs.get(node.func.id)
                          if isinstance(node.func, ast.Name) else None)
                    if fn is not None and fn.name not in seen:
                        keys |= keys_read(fn.body, seen | {fn.name})
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


# An unread key is not automatically a defect. When the value it carries is the
# same as what the code does anyway, honouring it would change nothing — the key
# is redundant, not broken. Reporting those alongside real defects invites
# someone to churn dozens of correct cards, so they are separated.
#
# Every entry here is a CLAIM about the code and can therefore be wrong, which is
# how audit_run.py's ENGINE_FLAGS certified a dead flag for a whole sweep. So the
# list is kept small and each entry names the behaviour that makes it inert; when
# in doubt a finding stays ACTIVE, because a false "active" costs someone a
# second look while a false "inert" hides a broken card forever.
INERT: dict[tuple[str, str], tuple[frozenset[str], str]] = {
    # Every effect that takes a player defaults to the controller, so "SELF" is
    # what already happens. "OPPONENT" on the same key is a real defect.
    ("CHOOSE", "player"):            (frozenset({"self"}), "defaults to controller"),
    ("ATTACK_IS_WEAPON", "player"):  (frozenset({"self"}), "defaults to controller"),
    ("ROLL", "player"):              (frozenset({"self"}), "defaults to controller"),
    ("DISCARD_RANDOM", "player"):    (frozenset({"self"}), "defaults to controller"),
    ("SELECT_FROM_REF", "player"):   (frozenset({"self"}), "defaults to controller"),
    ("PUT_CARDS_BOTTOM", "player"):  (frozenset({"self"}), "defaults to controller"),
    ("CONTROLS_ATTACK_ACTION", "player"): (frozenset({"self"}), "defaults to controller"),
    ("IN_COMBAT", "player"):         (frozenset({"self"}), "defaults to controller"),
    ("SOURCE_IS_ATTACK", "source"):  (frozenset({"self"}), "the source IS this card"),
    ("CARD_IN_ZONE", "source"):      (frozenset({"self"}), "defaults to controller"),
    # SEARCH_DECK always shuffles (effect_shuffle at the end) and always reveals
    # what it moves (is_public=True), so saying so changes nothing.
    ("SEARCH_DECK", "shuffle"):      (frozenset({"true"}), "always shuffles"),
    ("SEARCH_DECK", "reveal"):       (frozenset({"true"}), "moves with is_public=True"),
    ("SEARCH_DECK", "face_up"):      (frozenset({"true"}), "moves with is_public=True"),
    # "put them back in any order" needs no effect: revealing never moved them.
    ("PUT_CARDS_BOTTOM", "order"):   (frozenset({"any"}), "reveal does not move cards"),
    # ADD_DEFEND adds the SOURCE card unless handed an object target, so
    # "self" is what already happens. A dict target is a real one.
    ("ADD_DEFEND", "target"):        (frozenset({"self"}), "adds the source card"),
    # REORDER_REF only ever reorders a DECK — that is the whole effect — so
    # naming the deck as the zone says nothing the handler does not already do.
    ("REORDER_REF", "zone"):         (frozenset({"deck"}), "only reorders decks"),
    # These name the card's CURRENT zone, which put_object resolves from the
    # card itself. Naming it changes nothing. They are recorded here rather than
    # "read" with a bare params.get() in the compiler — touching a key to quiet
    # the audit marks it consumed without honouring it, which is the same lie as
    # an allowlist entry that is not true, and hides the next real defect on
    # that key.
    # INTIMIDATE always intimidates the opposing hero (3 - controller), which is
    # what "intimidate target hero" means on all three Bad Breath printings.
    ("INTIMIDATE", "target"):        (frozenset({"hero", "opponent"}), "always the opposing hero"),
    # PREVENT_DAMAGE shields the CONTROLLER — "the next time YOUR HERO would be
    # dealt damage". Naming the player changes nothing.
    ("PREVENT_DAMAGE", "target"):    (frozenset({"player", "self", "hero"}), "shields the controller"),
    # The counter effects act on the source card, so a target naming the source
    # is what already happens. Any OTHER target on them is a real defect — those
    # 13 nodes name an aura, an ally, an equipment or a named permanent and get
    # the source card instead.
    ("PUT_COUNTER", "target"):       (frozenset({"self", "this"}), "acts on the source card"),
    ("REMOVE_COUNTER", "target"):    (frozenset({"self", "this"}), "acts on the source card"),
    ("REMOVE_COUNTERS", "target"):   (frozenset({"self", "this"}), "acts on the source card"),
    ("MOVE_REF", "from"):            (frozenset({"revealed_cards", "graveyard",
                                                 "deck", "hand", "arsenal"}),
                                      "origin comes from the card"),
    ("MOVE_REF", "zone"):            (frozenset({"deck", "hand", "graveyard",
                                                 "arsenal", "banished"}),
                                      "origin comes from the card"),
    ("RETURN_TO_HAND", "zone"):      (frozenset({"graveyard", "arena", "deck",
                                                 "banished", "permanents"}),
                                      "origin comes from the card"),
}


def severity(type_name: str, key: str, value) -> str:
    """"active" if honouring this key would change behaviour, else "inert"."""
    rule = INERT.get((type_name.upper(), key))
    if rule is None:
        return "active"
    allowed, _why = rule
    return "inert" if str(value).strip().lower() in allowed else "active"


def card_files(set_code: str | None = None) -> list[Path]:
    return [p for p in JSON_ROOT.rglob("*.json")
            if not p.stem.endswith("_work_queue")
            and "needs_review" not in p.parts
            and not any(part.startswith(".") for part in p.parts)
            and (set_code is None or p.parent.name == set_code)]


def audit_node(node: dict, index: dict[str, set[str]],
               include_inert: bool = False) -> list[str]:
    ntype = node.get("type")
    if not isinstance(ntype, str) or not ntype:
        return []
    known = index.get(ntype.upper())
    if known is None:
        return []          # unknown type — that is audit_run.py's job, not this
    if WHOLESALE in known:
        return []          # handler consumes params wholesale; nothing is unread
    bad = []
    for key, value in node.items():
        if key in STRUCTURAL_KEYS or key in NESTED_KEYS or key.startswith("_"):
            continue
        if key in known:
            continue
        kind = severity(ntype, key, value)
        if kind == "inert" and not include_inert:
            continue
        label = "" if kind == "active" else " [inert: carries the default]"
        bad.append(f"{ntype} has no parameter {key!r}{label} "
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
    ap.add_argument("--all", action="store_true",
                    help="include INERT findings (keys whose value is the default anyway)")
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
        walk(raw.get("abilities", []),
             lambda n: found.extend(audit_node(n, index, include_inert=args.all)))
        if found:
            findings[path.stem] = sorted(set(found))

    kinds = Counter(re.sub(r" has no parameter.*", "", f)
                    for fs in findings.values() for f in fs)
    kind = "unread parameter" if args.all else "ACTIVE unread parameter"
    print(f"cards with >=1 {kind}: {len(findings)} / {len(paths)}"
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
