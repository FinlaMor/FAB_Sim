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
from tests.conftest import _card_json, _make_state

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
    path = _card_json(root, f"{slug}.json")
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


def test_count_boosts_counts_one_turn_marker_per_boost():
    # boost() appends one "boosted_this_turn" marker per boost, so the TURN
    # scope is a count rather than a boolean. Scope is explicit here because the
    # DEFAULT is CHAIN — this test seeds only the turn marker, so relying on the
    # default would read 0 and prove nothing about the marker.
    st = _state()
    card = _card("bloodsheath_skeleta")
    for _ in range(2):
        st.players[1].current_turn_effects.append("boosted_this_turn")
    assert _resolve_amount({"type": "COUNT_BOOSTS", "scope": "TURN"}, st, card) == 2


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
    path = _card_json(root, f"{slug}.json")
    abilities = json.dumps(json.loads(path.read_text(encoding="utf-8"))["abilities"])
    for invented in ("COUNT_CONTROLLERS", "CHAIN_HIT_COUNT_GTE", "BOOST_FLAG",
                     "EVO_COUNT", "BOOST_COUNT\"", "FLAG_SET"):
        assert invented not in abilities, f"{slug} still carries {invented}"
    assert "COUNT_" in abilities


# --- chain-scoped boost counter --------------------------------------------

def _boost(st, pid=1):
    """One boost, recorded the way ability_keywords.boost records it."""
    st.players[pid].current_turn_effects.append("boosted_this_turn")
    st.players[pid].boosts_this_chain = getattr(
        st.players[pid], "boosts_this_chain", 0) + 1


def test_chain_scope_is_the_default_for_count_boosts():
    st = _state()
    card = _card("pulsewave_harpoon_red")
    _boost(st); _boost(st)
    assert _resolve_amount({"type": "COUNT_BOOSTS"}, st, card) == 2


def test_turn_scope_still_available_explicitly():
    st = _state()
    card = _card("pulsewave_harpoon_red")
    _boost(st)
    assert _resolve_amount({"type": "COUNT_BOOSTS", "scope": "TURN"}, st, card) == 1


def test_chain_count_does_not_inherit_an_earlier_attacks_boosts():
    # The whole point: two attacks in one turn. After the first chain closes,
    # the second must start from zero, while the TURN count keeps both.
    import engine.engine as E
    st = _state()
    card = _card("pulsewave_harpoon_red")
    _boost(st); _boost(st)
    assert _resolve_amount({"type": "COUNT_BOOSTS"}, st, card) == 2

    for p in st.players.values():          # chain closes
        p.chain_attack_hooks = []
        p.boosts_this_chain = 0

    _boost(st)                             # one boost on the SECOND attack
    assert _resolve_amount({"type": "COUNT_BOOSTS"}, st, card) == 1
    assert _resolve_amount({"type": "COUNT_BOOSTS", "scope": "TURN"}, st, card) == 3


def test_chain_count_starts_at_zero():
    st = _state()
    card = _card("pulsewave_harpoon_red")
    assert _resolve_amount({"type": "COUNT_BOOSTS"}, st, card) == 0


def test_real_boost_increments_both_scopes_and_chain_close_resets_one():
    # Drives the REAL boost keyword, not a hand-written marker: the earlier
    # tests seed state directly, which would still pass if boost() stopped
    # tallying the chain entirely.
    from engine.card import Card
    from engine.card_effects.ability_keywords import boost as real_boost

    st = _state()
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    for _ in range(4):
        c = Card(slug="d", name="d", types=["Action"])
        c.owner = c.controller = 1
        st.players[1].deck.cards.append(c)
    card = Card(slug="booster", name="booster", types=["Action"])
    card.owner = card.controller = 1

    real_boost(card, st)
    real_boost(card, st)
    assert _resolve_amount({"type": "COUNT_BOOSTS"}, st, card) == 2
    assert _resolve_amount({"type": "COUNT_BOOSTS", "scope": "TURN"}, st, card) == 2

    for p in st.players.values():          # chain closes (engine._close_step)
        p.boosts_this_chain = 0

    real_boost(card, st)
    assert _resolve_amount({"type": "COUNT_BOOSTS"}, st, card) == 1, "chain count leaked"
    assert _resolve_amount({"type": "COUNT_BOOSTS", "scope": "TURN"}, st, card) == 3


# --- life gained this turn (a magnitude, not an occurrence count) -----------

def test_life_gained_this_turn_tallies_amounts_not_events():
    from engine.card_effects.ability_keywords import effect_gain_life
    st = _state()
    card = _card("thistle_bloom__life_yellow")
    assert _resolve_amount({"type": "LIFE_GAINED_THIS_TURN"}, st, card) == 0
    effect_gain_life(st, 1, 2)
    effect_gain_life(st, 1, 3)
    # Two gains totalling 5 — an occurrence marker would say 2, which is why
    # this needed a tally rather than a turn-event marker.
    assert _resolve_amount({"type": "LIFE_GAINED_THIS_TURN"}, st, card) == 5


def test_life_gained_is_per_player():
    from engine.card_effects.ability_keywords import effect_gain_life
    st = _state()
    card = _card("thistle_bloom__life_yellow", owner=1)
    effect_gain_life(st, 2, 4)
    assert _resolve_amount({"type": "LIFE_GAINED_THIS_TURN"}, st, card) == 0


def test_thistle_bloom_creates_one_runechant_per_life_gained():
    from engine.card_effects.ability_keywords import effect_gain_life
    from engine.card_effects.dsl import dispatch
    st = _state()
    card = _card("thistle_bloom__life_yellow")
    effect_gain_life(st, 1, 2)
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    runechants = [c for c in st.players[1].permanents.cards if c.slug == "runechant"]
    assert len(runechants) == 2


# --- damage dealt by this attack -------------------------------------------

def test_damage_dealt_reads_damage_after_defence():
    # eradicate_yellow: "banish the top X cards of their deck, where X is the
    # damage dealt". attack_power ignores blockers, so it is the WRONG source —
    # a 6-power attack blocked for 4 deals 2.
    st = _state()
    card = _card("eradicate_yellow")
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=6,
                            attack_card=card, keywords=[])
    st.combat.total_defense = 4
    st.combat.net_damage_dealt = 2
    assert _resolve_amount({"type": "DAMAGE_DEALT"}, st, card) == 2


def test_damage_dealt_is_zero_outside_combat():
    st = _state()
    card = _card("eradicate_yellow")
    st.combat = None
    assert _resolve_amount({"type": "DAMAGE_DEALT"}, st, card) == 0
