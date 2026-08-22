"""The Evo tier cards: three tiers live, one removed as a fabricated penalty.

Annihilator Engine and War Machine each have four tiers keyed to how many Evos
you have equipped. The "costs {r}{r}{r} less to play" tier was a plain STATIC
holding MODIFY_ATTACK subtract 3 — a POWER penalty, not a cost reduction. Had
anything dispatched it the card would have LOST 3{p} instead of costing less,
which is the recurring shape of this whole sweep: the dead dispatch was the only
thing preventing a wrong effect.

The other three tiers are live. Their gate is CONTROLS_TOKEN_TYPE, which despite
the name searches all permanents PLUS equipment and weapon slots and matches the
Evo SUBTYPE — so "Evos you have equipped" really is what it counts. These tests
pin that, because a gate that is never true would make all three look correct
while doing nothing.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.loader import load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

EVO = "evo_atom_breaker_red"      # Equipment, subtype Chest + Evo
TIERED = ["annihilator_engine_red", "war_machine_red"]


def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    return st


def _card(slug, owner=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = owner
    return c


def _equip_evos(st, n):
    """Put n Evos in equipment slots — where "equipped" actually means."""
    slots = [st.players[1].head, st.players[1].chest,
             st.players[1].arms, st.players[1].legs]
    for i in range(n):
        slots[i % len(slots)].cards.append(_card(EVO))


def _attack(st, slug):
    card = _card(slug)
    power = card.base_power or 0
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=power,
                            attack_card=card, keywords=[])
    st.combat.base_attack_power = power
    E._apply_turn_attack_effects(st, card)
    E._register_card_continuous_effects(st, card)
    E._recalculate_attack_power(st)
    return card, power


@pytest.mark.parametrize("slug", TIERED)
def test_the_evo_gate_counts_equipment_not_only_tokens(slug):
    """CONTROLS_TOKEN_TYPE is named for tokens but reaches equipment slots.

    If it did not, all three surviving tiers would be gated on something never
    true and would look implemented while doing nothing.
    """
    from engine.card_effects.dsl.condition_types import compile_condition

    st = _state()
    fn = compile_condition("CONTROLS_TOKEN_TYPE",
                           {"token_type": "Evo", "amount": 3})
    probe = _card(slug)

    _equip_evos(st, 2)
    assert fn(probe, None, st) is False, "2 Evos satisfied a 3-Evo gate"
    _equip_evos(st, 1)
    assert fn(probe, None, st) is True, "3 equipped Evos did not satisfy it"


@pytest.mark.parametrize("slug", TIERED)
def test_four_evos_add_three_power(slug):
    st = _state()
    _equip_evos(st, 4)
    _, base = _attack(st, slug)
    assert st.combat.attack_power == base + 3, (
        f"4 Evos gave {st.combat.attack_power - base}{{p}}, expected 3")


@pytest.mark.parametrize("slug", TIERED)
def test_three_evos_do_not_add_power(slug):
    """The +3{p} tier is 4 or more; overpower is the 3-Evo tier."""
    st = _state()
    _equip_evos(st, 3)
    _, base = _attack(st, slug)
    assert st.combat.attack_power == base, (
        "the 4-Evo power tier fired at 3 Evos")


@pytest.mark.parametrize("slug", TIERED)
def test_three_evos_grant_overpower(slug):
    st = _state()
    _equip_evos(st, 3)
    _attack(st, slug)
    assert any(str(k).lower() == "overpower" for k in st.combat.keywords), (
        f"3 Evos granted no overpower: {st.combat.keywords}")


@pytest.mark.parametrize("slug", TIERED)
def test_two_evos_grant_no_overpower(slug):
    """The printed-keyword suppression matters here: the card DB lists
    Overpower, and without suppression the card would always have it."""
    st = _state()
    _equip_evos(st, 2)
    _attack(st, slug)
    assert not any(str(k).lower() == "overpower" for k in st.combat.keywords), (
        f"2 Evos granted overpower anyway: {st.combat.keywords}")


@pytest.mark.parametrize("slug", TIERED)
def test_no_fabricated_power_penalty_remains(slug):
    """The removed tier: MODIFY_ATTACK subtract 3 for "costs {r}{r}{r} less"."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    raw = json.loads(next(root.rglob(f"{slug}.json")).read_text(encoding="utf-8"))

    found = []

    def walk(node):
        if isinstance(node, dict):
            if (node.get("type") == "MODIFY_ATTACK"
                    and str(node.get("mod")) == "subtract"):
                found.append(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(raw.get("abilities", []))
    assert not found, f"the fabricated -3{{p}} is back: {found}"
