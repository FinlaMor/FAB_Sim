"""No condition/effect type may be registered twice.

`compile_condition` is a long if-chain that RETURNS on the first match, so a type
handled in two places silently keeps the earlier handler and the later one is
dead code. That is invisible: the card still loads, the condition still
evaluates, it just runs a handler expecting different params and quietly gates on
a default.

This happened for real: `LAST_CHAIN_ATTACK` was added with an alias `COMBO`, but
`COMBO` was already handled ~270 lines earlier reading a `names` list. The alias
never ran, and a card authored `{"type":"COMBO","name":"Surging Strike"}` would
have reached the older handler, found no `names`, and gated on an empty list —
while the DSL reference advertised the alias as valid.

A scan is the right shape here rather than a fix at one call site: the same trap
applies to every future type added to either chain.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

DSL = Path(__file__).resolve().parents[1] / "engine" / "card_effects" / "dsl"

# Only a DISPATCH line registers a type: `if ctype == "X":` / `if ctype in (...)`.
# A bare `ctype == "X"` elsewhere is the legitimate pattern of registering a pair
# in one tuple and then branching inside the handler
# (`lte = ctype == "ATTACK_BASE_POWER_LTE"`), which is not a second registration
# — counting those reported 5 false positives on the first pass.
_DISPATCH_EQ = re.compile(r'^\s*if\s+(?:ctype|etype)\s*==\s*"([A-Z_0-9]+)"')
_DISPATCH_IN = re.compile(r'^\s*if\s+(?:ctype|etype)\s+in\s+\(([^)]*)\)')
_STR = re.compile(r'"([A-Z_0-9]+)"')


def _registered_types(path: Path) -> list[str]:
    names: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("#"):
            continue  # guidance ABOUT a name is not a registration of it
        m = _DISPATCH_EQ.match(line)
        if m:
            names.append(m.group(1))
            continue
        m = _DISPATCH_IN.match(line)
        if m:
            names += _STR.findall(m.group(1))
    return names


@pytest.mark.parametrize("filename", ["condition_types.py", "effect_types.py"])
def test_no_type_is_registered_twice(filename):
    names = _registered_types(DSL / filename)
    assert names, f"scan found no type registrations in {filename} — the regex is stale"
    dupes = {n: c for n, c in Counter(names).items() if c > 1}
    assert not dupes, (
        f"{filename}: these types are handled more than once, so every handler "
        f"after the first is dead code and cards using them silently reach the "
        f"earlier one: {sorted(dupes)}"
    )


def test_combo_and_last_chain_attack_stay_distinct():
    # The specific regression: COMBO must NOT resolve to the LAST_CHAIN_ATTACK
    # handler, and LAST_CHAIN_ATTACK must not resolve to the combo_check one.
    from engine.card_effects.dsl.condition_types import compile_condition
    assert compile_condition("COMBO", {}).__name__ == "_combo"
    assert compile_condition("LAST_CHAIN_ATTACK", {}).__name__ == "_last_chain"
