"""Dynamic amount expressions (COUNT_CHAIN_LINKS / COUNT_COUNTERS).

An unresolved amount returns 0, so "create X Runechants" creates none and the
effect looks implemented while doing nothing. Worse, a threshold CONDITION
authored as a bare string compared `int <= "DRACONIC_CHAIN_LINKS_CONTROLLED"`,
which raises TypeError and aborts resolution mid-game rather than merely
no-opping.

These cover both: the expressions resolve to real counts, and an unresolvable
threshold fails the condition instead of crashing.
"""
import copy

import pytest

from engine.card import CardDB
from engine.card_effects.dsl.condition_types import compile_condition
from engine.card_effects.dsl.effect_types import _resolve_amount
from engine.card_effects.dsl.loader import load_all_cards
from engine.state import ChainLink, CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()


def _state():
    st = _make_state()
    st.card_db = DB
    return st


def _card(slug, owner=1):
    c = copy.deepcopy(DB.get(slug))
    c.owner = c.controller = owner
    return c


def _link(st, pid=1, talents=(), hit=True, slug="a"):
    st.chain_links.append(ChainLink(
        chainlink_id=len(st.chain_links) + 1, attacker_id=pid, attack_slug=slug,
        attack_power=1, net_damage=1 if hit else 0, keywords=[], from_weapon=False,
        hit=hit, talents=list(talents), classes=[], subtypes=[]))


# --- COUNT_CHAIN_LINKS -----------------------------------------------------

def test_count_chain_links_counts_only_the_matching_talent():
    st = _state()
    _link(st, talents=["Draconic"])
    _link(st, talents=["Draconic"])
    _link(st, talents=["Elemental"])
    card = _card("mounting_anger_red")
    n = _resolve_amount({"type": "COUNT_CHAIN_LINKS", "talent": "Draconic"}, st, card)
    assert n == 2


def test_count_chain_links_counts_only_your_own_links():
    # "chain links YOU control" — the opponent's attacks must not count.
    st = _state()
    _link(st, pid=1, talents=["Draconic"])
    _link(st, pid=2, talents=["Draconic"])
    card = _card("mounting_anger_red", owner=1)
    n = _resolve_amount({"type": "COUNT_CHAIN_LINKS", "talent": "Draconic"}, st, card)
    assert n == 1


def test_count_chain_links_is_zero_with_no_links():
    st = _state()
    card = _card("mounting_anger_red")
    assert _resolve_amount({"type": "COUNT_CHAIN_LINKS", "talent": "Draconic"}, st, card) == 0


# --- COUNT_COUNTERS --------------------------------------------------------

def test_count_counters_reads_counters_on_this_card():
    st = _state()
    card = _card("doomsaying_red")
    st.players[1].counters[("doomsaying_red", "permanents", "doom")] = 3
    n = _resolve_amount({"type": "COUNT_COUNTERS", "counter": "doom"}, st, card)
    assert n == 3


def test_count_counters_ignores_a_different_counter_kind():
    st = _state()
    card = _card("doomsaying_red")
    st.players[1].counters[("doomsaying_red", "permanents", "steam")] = 5
    n = _resolve_amount({"type": "COUNT_COUNTERS", "counter": "doom"}, st, card)
    assert n == 0


# --- the crash this replaces ----------------------------------------------

def test_unresolvable_threshold_fails_closed_instead_of_raising():
    # The regression: ATTACK_COST_LTE compared an int against a raw string.
    st = _state()
    attacker = _card("mounting_anger_red")
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=1,
                            attack_card=attacker, keywords=[])
    cond = compile_condition("ATTACK_COST_LTE", {"amount": "DRACONIC_CHAIN_LINKS_CONTROLLED"})
    # Must not raise TypeError; an unresolvable threshold means "not met".
    assert cond(attacker, None, st) is False


def test_threshold_accepts_a_dynamic_expression():
    st = _state()
    _link(st, talents=["Draconic"])
    _link(st, talents=["Draconic"])
    attacker = _card("mounting_anger_red")
    st.combat = CombatState(attacker_id=1, link_id=3, attack_power=1,
                            attack_card=attacker, keywords=[])
    cost = None
    from engine.card_effects.dsl.condition_types import _attack_card_cost
    cost = _attack_card_cost(attacker)
    cond = compile_condition(
        "ATTACK_COST_LTE",
        {"amount": {"type": "COUNT_CHAIN_LINKS", "talent": "Draconic"}})
    # 2 Draconic links: true exactly when the attack's cost is <= 2.
    assert cond(attacker, None, st) is (cost <= 2)


def test_integer_string_threshold_still_works():
    st = _state()
    attacker = _card("mounting_anger_red")
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=1,
                            attack_card=attacker, keywords=[])
    assert compile_condition("ATTACK_COST_LTE", {"amount": "99"})(attacker, None, st) is True
    assert compile_condition("ATTACK_COST_LTE", {"amount": "0"})(attacker, None, st) is (
        _card_cost_zero(attacker))


def _card_cost_zero(card):
    from engine.card_effects.dsl.condition_types import _attack_card_cost
    return _attack_card_cost(card) <= 0


# --- migration guard -------------------------------------------------------

@pytest.mark.parametrize("slug", ["mounting_anger_red", "doomsaying_red"])
def test_migrated_cards_no_longer_carry_an_invented_amount(slug):
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "engine" / "card_effects" / "json"
    path = [p for p in root.rglob(f"{slug}.json") if ".quarantine" not in p.parts][0]
    data = json.loads(path.read_text(encoding="utf-8"))
    # Inspect the ABILITIES, not the raw file: `_comment` legitimately names the
    # old invented token to explain what was replaced, and matching raw text
    # would fail on the documentation rather than on the implementation.
    abilities = json.dumps(data["abilities"])
    assert "DRACONIC_CHAIN_LINKS_CONTROLLED" not in abilities
    assert '"amount": "doom"' not in abilities
    assert "COUNT_" in abilities, f"{slug} lost its dynamic amount"


# --- COUNT_PERMANENT / COUNT_BOOSTS ----------------------------------------

def test_count_permanent_counts_matching_subtype():
    from engine.card import Card
    st = _state()
    card = _card("bloodsheath_skeleta")
    for _ in range(3):
        t = Card(slug="runechant", name="Runechant", types=["Token"],
                 subtypes=["Runechant", "Aura"])
        t.owner = t.controller = 1
        st.players[1].permanents.add(t)
    assert _resolve_amount({"type": "COUNT_PERMANENT", "subtype": "Runechant"}, st, card) == 3


def test_count_permanent_ignores_other_subtypes():
    from engine.card import Card
    st = _state()
    card = _card("bloodsheath_skeleta")
    t = Card(slug="gold", name="Gold", types=["Token"], subtypes=["Item"])
    t.owner = t.controller = 1
    st.players[1].permanents.add(t)
    assert _resolve_amount({"type": "COUNT_PERMANENT", "subtype": "Runechant"}, st, card) == 0


def test_count_boosts_counts_one_marker_per_boost():
    st = _state()
    card = _card("bloodsheath_skeleta")
    for _ in range(2):
        st.players[1].current_turn_effects.append("boosted_this_turn")
    assert _resolve_amount({"type": "COUNT_BOOSTS"}, st, card) == 2


def test_count_expressions_do_not_crash_without_a_controller():
    # A card with no owner yields controller id 0, and state.players[0] raises
    # KeyError — aborting resolution mid-game. An unresolvable controller must
    # make the count 0.
    from engine.card import Card
    st = _state()
    orphan = Card(slug="orphan", name="orphan", types=["Action"])
    st.combat = None
    st.active_player = None
    assert _resolve_amount({"type": "COUNT_PERMANENT", "subtype": "Runechant"}, st, orphan) == 0
    assert _resolve_amount({"type": "COUNT_BOOSTS"}, st, orphan) == 0


# --- counts that were invented strings/dicts on real cards -----------------

def test_dagger_hit_count_on_the_chain():
    # stab_wound_blue: "X is the number of times a dagger has hit this combat
    # chain". ChainLink already records subtypes and hit, so this needed no new
    # engine state — only the right expression.
    st = _state()
    st.chain_links.append(ChainLink(
        chainlink_id=1, attacker_id=1, attack_slug="d1", attack_power=1,
        net_damage=1, keywords=[], from_weapon=True, hit=True,
        talents=[], classes=[], subtypes=["Dagger"]))
    st.chain_links.append(ChainLink(
        chainlink_id=2, attacker_id=1, attack_slug="d2", attack_power=1,
        net_damage=0, keywords=[], from_weapon=True, hit=False,
        talents=[], classes=[], subtypes=["Dagger"]))     # missed — must not count
    st.chain_links.append(ChainLink(
        chainlink_id=3, attacker_id=1, attack_slug="s1", attack_power=1,
        net_damage=1, keywords=[], from_weapon=True, hit=True,
        talents=[], classes=[], subtypes=["Sword"]))      # not a dagger
    card = _card("stab_wound_blue")
    n = _resolve_amount({"type": "COUNT_CHAIN_LINKS", "subtype": "Dagger", "hit": True},
                        st, card)
    assert n == 1


def test_count_permanent_counts_equipped_cards():
    # heavy_artillery_red: "the number of Evos you have EQUIPPED". Equipment
    # lives in head/chest/arms/legs/weapon slots, NOT the permanents zone, so
    # scanning permanents alone returned 0 for every equipment count.
    # Use a REAL Evo chest equipment: Zone.add enforces zone-entry rules, so a
    # synthetic card with subtypes ["Evo"] but no slot subtype is REJECTED and
    # the chest stays empty — which reads exactly like a broken count.
    st = _state()
    card = _card("heavy_artillery_red")
    evo = _card("evo_atom_breaker_red")
    st.players[1].chest.add(evo)
    assert evo in st.players[1].chest.cards, "fixture did not actually equip"
    assert _resolve_amount({"type": "COUNT_PERMANENT", "subtype": "Evo",
                            "zone": "EQUIPMENT"}, st, card) == 1
    # and the permanents-only scope still excludes it
    assert _resolve_amount({"type": "COUNT_PERMANENT", "subtype": "Evo",
                            "zone": "PERMANENTS"}, st, card) == 0


@pytest.mark.parametrize("slug", [
    "mounting_anger_blue", "stab_wound_blue", "pulsewave_harpoon_red",
    "urgent_delivery_yellow", "heavy_artillery_red",
])
def test_no_invented_amounts_remain(slug):
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "engine" / "card_effects" / "json"
    path = [p for p in root.rglob(f"{slug}.json") if ".quarantine" not in p.parts][0]
    abilities = json.dumps(json.loads(path.read_text(encoding="utf-8"))["abilities"])
    for invented in ("COUNT_CONTROLLERS", "CHAIN_HIT_COUNT_GTE", "BOOST_FLAG",
                     "EVO_COUNT", "BOOST_COUNT\"", "FLAG_SET"):
        assert invented not in abilities, f"{slug} still carries {invented}"
    assert "COUNT_" in abilities
