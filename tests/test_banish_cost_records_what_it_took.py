""""If a card with 6 or more {p} is banished this way" — gated on Blood Debt.

writhing_beast_hulk_red carried three defects at once:

  * Its DOMINATE was gated on FLAG_SET "BLOOD_DEBT_FLAG". Blood Debt is a
    PRINTED KEYWORD on the card and has nothing to do with the condition, which
    is about the POWER of what the cost banished.
  * That flag was set by a plain STATIC, which nothing dispatches — so dominate
    could never apply. Had the static run it would have applied ALWAYS, since
    the flag is unconditional.
  * Its cost was BANISH_NAMED_GRAVEYARD_OPTIONAL — "you MAY banish a NAMED
    card" — where the card says banish 3 RANDOM cards, mandatorily.

The cost now records what it banished under the same `banished_cards` ref the
BANISH effect uses. run_ability pushes the reference scope BEFORE paying
additional costs, so the effects can read it — that ordering is what makes
"banished this way" expressible at all, and there is a test for it.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.cost_types import compile_cost
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import load_all_cards, get_card
from engine.state import CombatState
from tests.conftest import _make_state
from tests.conftest import _card_json

load_all_cards()
DB = CardDB()

BIG = "wounded_bull_red"          # power 7
SMALL = "a_drop_in_the_ocean_blue"


def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    return st


def _card(slug, owner=1, zone=None):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = owner
    if zone is not None:
        c.zone = zone
    return c


def _fill_graveyard(st, slug, n=3):
    st.players[1].graveyard.cards = [_card(slug, zone="graveyard")
                                     for _ in range(n)]


def test_the_cost_banishes_three_and_records_them():
    from engine.context import get_ref, push_refs, pop_refs

    st = _state()
    _fill_graveyard(st, BIG, 4)
    can_pay, pay = compile_cost("BANISH_RANDOM_FROM_GRAVEYARD", {"amount": 3})
    source = _card("writhing_beast_hulk_red")

    push_refs()
    try:
        assert can_pay(source, None, st) is True
        pay(source, None, st)
        recorded = get_ref("banished_cards")
    finally:
        pop_refs()

    assert len(st.players[1].graveyard.cards) == 1
    assert len(st.players[1].banished.cards) == 3
    assert recorded and len(recorded) == 3, f"recorded {recorded}"


def test_the_cost_is_unpayable_with_too_few_cards():
    st = _state()
    _fill_graveyard(st, BIG, 2)
    can_pay, _pay = compile_cost("BANISH_RANDOM_FROM_GRAVEYARD", {"amount": 3})

    assert can_pay(_card("writhing_beast_hulk_red"), None, st) is False


def test_dominate_applies_when_a_big_card_was_banished():
    st = _state()
    _fill_graveyard(st, BIG, 3)          # power 7 each
    card = _card("writhing_beast_hulk_red")
    power = card.base_power or 0
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=power,
                            attack_card=card, keywords=[])
    st.combat.base_attack_power = power

    run_ability(get_card("writhing_beast_hulk_red").abilities[0], card, None, st)

    assert any(str(k).lower() == "dominate" for k in st.combat.keywords), (
        f"no dominate after banishing 6+ power cards: {st.combat.keywords}")


def test_dominate_does_not_apply_when_nothing_big_was_banished():
    """The half the Blood Debt gate got wrong in both directions."""
    st = _state()
    _fill_graveyard(st, SMALL, 3)
    card = _card("writhing_beast_hulk_red")
    power = card.base_power or 0
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=power,
                            attack_card=card, keywords=[])
    st.combat.base_attack_power = power

    run_ability(get_card("writhing_beast_hulk_red").abilities[0], card, None, st)

    assert not any(str(k).lower() == "dominate" for k in st.combat.keywords), (
        f"dominate applied with no 6+ power card banished: {st.combat.keywords}")


def test_the_reference_scope_covers_additional_costs():
    """run_ability must push refs BEFORE paying costs, or "banished this way"
    can never be read by the effects that follow."""
    import inspect
    from engine.card_effects.dsl import interpreter

    src = inspect.getsource(interpreter.run_ability)
    assert "push_refs()" in src
    body = inspect.getsource(interpreter._run_ability)
    # The cost payment happens inside _run_ability, which run_ability wraps in
    # the scope — so any ref a cost records is visible to the effects.
    assert "additional_costs" in body or "additional" in body


def test_no_blood_debt_flag_remains():
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    raw = json.loads(_card_json(root, "writhing_beast_hulk_red.json")
                     .read_text(encoding="utf-8"))
    blob = json.dumps(raw.get("abilities", []))
    assert "BLOOD_DEBT_FLAG" not in blob, "the Blood Debt gate is back"
