"""An ability's additional_cost is PAID EVERY TIME THE ABILITY IS DISPATCHED.

interpreter._run_ability checks and pays `additional_costs` on every dispatch,
before conditions are even evaluated. For a PLAY or ACTIVATE ability that is
exactly right -- it is dispatched once, when the card is played or activated.

For an ability that is dispatched REPEATEDLY it is a disaster in two directions
at once, and both are silent:

  * the cost is paid again on every dispatch. A WHILE_STATIC runs on every
    attack-power recalculation, so "discard a random card" would empty the hand
    over the course of one combat;
  * once the cost can no longer be paid, `_run_ability` RETURNS EARLY -- before
    the conditions, before the effects -- so the ability stops working and
    looks like a condition that stopped holding.

This was found by walking into it: Breakneck Battery's discard cost was moved
onto its WHILE_STATIC because the alternative (an effect-less PLAY ability) is
a no-op the hygiene tests reject. The card then failed its own behavioural
test, which is the only reason it did not ship. The right home is the
CARD-LEVEL `cost`, which play.py checks for legality and pays once.

The corpus was clean when this was written -- no card had this shape except the
one being fixed -- so this guard exists to keep it that way rather than to
report a backlog.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.conftest import card_json_files

JSON_ROOT = ROOT / "engine" / "card_effects" / "json"

#: Ability types dispatched ONCE per play/activation, where paying an
#: additional cost on dispatch is the intended behaviour.
PAID_ONCE = {"PLAY", "ACTION", "MODAL", "ACTIVATE", "INSTANT",
             "ATTACK_REACTION", "DEFENSE_REACTION"}


def _cards():
    for path in card_json_files(JSON_ROOT):
        rel = path.relative_to(JSON_ROOT)
        if path.stem.endswith("_work_queue") or any(
                p.startswith(".") for p in rel.parts):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(raw, dict) and raw.get("abilities"):
            yield raw


def test_no_repeatedly_dispatched_ability_carries_an_additional_cost():
    offenders = []
    for raw in _cards():
        for i, ability in enumerate(raw["abilities"]):
            if not ability.get("additional_cost"):
                continue
            atype = (ability.get("ability_type") or "").upper()
            if atype not in PAID_ONCE:
                offenders.append(
                    "%s ability[%d] (%s): %s" % (
                        raw.get("slug"), i, atype,
                        [c.get("type") for c in ability["additional_cost"]]))
    assert not offenders, (
        "these abilities pay their additional cost on EVERY dispatch, and stop "
        "working entirely once it can no longer be paid. Move the cost to the "
        "card-level \"cost\" field, which is paid once when the card is "
        "played:\n  " + "\n  ".join(offenders))


def test_the_interpreter_still_pays_on_dispatch():
    """The premise. If _run_ability stopped paying costs on dispatch, the guard
    above would be protecting against nothing -- and something much worse would
    be true, since PLAY abilities would have stopped paying their costs."""
    source = (ROOT / "engine" / "card_effects" / "dsl" / "interpreter.py"
              ).read_text(encoding="utf-8")
    body = source[source.index("def _run_ability"):]
    body = body[:body.index("\ndef ", 1)]
    assert "additional_costs" in body, (
        "_run_ability no longer touches additional_costs at all -- either "
        "costs moved somewhere else, or PLAY abilities have silently stopped "
        "paying them")
    assert "pay_fn" in body


def test_breakneck_battery_keeps_its_cost_at_card_level():
    """The card the guard came from. Its cost cannot live on its ability, and
    an effect-less PLAY ability to hold it is rejected as a no-op -- so
    card-level is the only correct home, and it is easy to "tidy" back."""
    raw = json.loads((JSON_ROOT / "hp" / "breakneck_battery_red.json")
                     .read_text(encoding="utf-8"))
    assert raw.get("cost", {}).get("type") == "DISCARD_RANDOM", (
        "the discard moved off the card level; if it is on the WHILE_STATIC "
        "again, the card discards once per recalculation")
    assert not any(a.get("additional_cost") for a in raw["abilities"])
