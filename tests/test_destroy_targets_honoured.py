"""DESTROY_TOKEN stood in for six different destroy effects.

It destroys ONE token of a named slug that the CONTROLLER controls. Eight cards
used it for things that are none of those: "all cards defending this", "all
cards in their arsenal", "all aura tokens THEY control", "all equipment they
control with -1{d} counters".

Five of the eight named no token slug at all, so `if not _slug: return` — they
destroyed nothing. The three that did named the controller's own side.

Three of them really are "destroy a <subtype> permanent", which DESTROY_PERMANENT
already does properly. The rest name a zone other than the arena or a filter
richer than a subtype, and go through DESTROY_MATCHING on the shared object
resolver — the same one the counter effects use, because "which objects does
this card mean" is one question, not six.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.loader import load_all_cards, get_card
from engine.card_effects.dsl.interpreter import run_ability
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

FILLER = "wounded_bull_red"


def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    return st


def _card(slug, owner=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = owner
    return c


def _stock(st, pid, zone, n=3, slug=FILLER):
    cards = []
    for _ in range(n):
        c = _card(slug, owner=pid)
        cards.append(c)
    getattr(st.players[pid], zone).cards = cards
    return cards


def _effects_of_type(slug, etype):
    out = []

    def walk(effs):
        for eff in effs:
            if eff.effect_type == etype:
                out.append(eff)

    for ab in get_card(slug).abilities:
        walk(ab.effects)
    return out


def _run_nested(slug, etype, card, st):
    """Compile and run the card's node of `etype`, wherever it is nested.

    Several of these sit inside an INJECT_TRIGGER's granted ability; the point
    under test is which objects the destroy reaches, not the injection.
    """
    import json
    from pathlib import Path
    from engine.card_effects.dsl.effect_types import compile_effect
    from engine.context import push_refs, pop_refs

    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    path = next(p for p in root.rglob(f"{slug}.json"))
    raw = json.loads(path.read_text(encoding="utf-8"))

    found = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == etype:
                found.append(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(raw.get("abilities", []))
    assert found, f"{slug} has no {etype} node"
    push_refs()
    try:
        for spec in found:
            compile_effect(etype, {k: v for k, v in spec.items()
                                   if k not in ("type", "conditions")})(card, None, st)
    finally:
        pop_refs()


def test_war_machine_destroys_their_arsenal_not_nothing():
    """"destroy all cards in THEIR arsenal" — a zone, not a permanent."""
    st = _state()
    _stock(st, 1, "arsenal", 2)
    _stock(st, 2, "arsenal", 3)

    _run_nested("war_machine_red", "DESTROY_MATCHING", _card("war_machine_red"), st)

    assert st.players[2].arsenal.cards == [], "the opponent's arsenal survived"
    assert len(st.players[1].arsenal.cards) == 2, "it destroyed the caster's own arsenal"


def test_smelting_only_destroys_equipment_carrying_the_counter():
    """"destroy all equipment they control WITH -1{d} counters"."""
    st = _state()
    marked = _card("nullrune_robe", owner=2)
    marked.counters["DEFENSE"] = 1
    clean = _card("nullrune_robe", owner=2)
    st.players[2].chest.cards = [marked, clean]
    mine = _card("nullrune_robe", owner=1)
    mine.counters["DEFENSE"] = 1
    st.players[1].chest.cards = [mine]

    _run_nested("smelting_of_the_old_ones_red", "DESTROY_MATCHING",
                _card("smelting_of_the_old_ones_red"), st)

    remaining = st.players[2].chest.cards
    assert clean in remaining, "equipment without the counter was destroyed"
    assert marked not in remaining, "the counter-marked equipment survived"
    assert mine in st.players[1].chest.cards, "it destroyed the caster's own equipment"


def test_annihilator_destroys_the_declared_defenders():
    """"destroy all cards defending this" — combat state, not a zone."""
    st = _state()
    defender = _card("nullrune_robe", owner=2)
    bystander = _card("nullrune_robe", owner=2)
    st.players[2].chest.cards = [defender, bystander]
    atk = _card("annihilator_engine_red")
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=1,
                            attack_card=atk, keywords=[])
    st.combat.defending_cards = [defender]

    _run_nested("annihilator_engine_red", "DESTROY_DEFENDING", atk, st)

    assert defender not in st.players[2].chest.cards, "the defender survived"
    assert bystander in st.players[2].chest.cards, "a non-defender was destroyed"


def test_destroy_defending_never_destroys_the_hero():
    """The defending hero is in defending_cards and is not destructible."""
    from engine.card_effects.dsl.effect_types import compile_effect
    st = _state()
    hero = st.players[2].hero
    assert hero is not None
    atk = _card("annihilator_engine_red")
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=1,
                            attack_card=atk, keywords=[])
    st.combat.defending_cards = [hero]

    compile_effect("DESTROY_DEFENDING", {})(atk, None, st)

    assert st.players[2].hero is hero


@pytest.mark.parametrize("slug,player_key", [
    ("small_problem_yellow", "OPPONENT"),
    ("deadwood_dirge_blue", "SELF"),
])
def test_aura_destroys_name_the_right_player(slug, player_key):
    """These three are exactly "destroy a <subtype> permanent" — the effect that
    already existed and reads `player`."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    raw = json.loads(next(root.rglob(f"{slug}.json")).read_text(encoding="utf-8"))
    found = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "DESTROY_PERMANENT":
                found.append(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(raw.get("abilities", []))
    assert found, f"{slug} no longer uses DESTROY_PERMANENT"
    assert all(n.get("player") == player_key for n in found), found
    assert all(n.get("subtype") == "Aura" for n in found), found


def test_no_card_still_uses_destroy_token_for_a_zone():
    """DESTROY_TOKEN is for a named token the controller controls. A node with
    no token slug destroys nothing, which is how five of these hid."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    offenders = []
    for path in root.rglob("*.json"):
        if path.stem.endswith("_work_queue") or any(
                p.startswith(".") for p in path.parts):
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))

        def walk(node):
            if isinstance(node, dict):
                if node.get("type") == "DESTROY_TOKEN" and not any(
                        node.get(k) for k in ("token", "token_type",
                                              "token_slug", "token_name")):
                    offenders.append(path.stem)
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        walk(raw.get("abilities", []))
    assert not offenders, (
        f"DESTROY_TOKEN with no token named, so it destroys nothing: {sorted(set(offenders))}")


def test_has_counter_reads_presence_not_a_threshold():
    from engine.card_effects.dsl.condition_types import compile_condition
    st = _state()
    fn = compile_condition("HAS_COUNTER", {"counter": "DEFENSE"})

    marked = _card("nullrune_robe")
    marked.counters["DEFENSE"] = 1
    clean = _card("nullrune_robe")

    assert fn(marked, None, st) is True
    assert fn(clean, None, st) is False
