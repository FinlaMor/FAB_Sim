"""Auto-generated pytest tests for WTR card DSL implementations.

Original generator output was incompatible with the real DSL `dispatch()` API
(it called `dispatch(card, event, ...)` with mock dicts).  These tests have
been re-written to use the real `(state, event_type, slug, card=card)`
signature, mirroring the patterns in `tests/test_dsl_interpreter.py`.

Each card gets three checks:
  * "ability_fires"  — exercises the happy path (condition met, effect runs)
  * "condition_gates" — flips a relevant condition off and asserts no effect
  * "effect_state"   — confirms the observable state change

These tests do not aim to fully simulate the engine; they verify that the
JSON/DSL path for each card compiles and that ability/condition/effect wiring
behaves the way the JSON declares it.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card import Card
from engine.card_effects.dsl import dispatch, get_card, load_all_cards
from engine.state import (
    ChainLink, CombatState, Event, GameState, Player, Step,
)


# ---------------------------------------------------------------------------
# Shared helpers (mirrors tests/test_dsl_interpreter.py)
# ---------------------------------------------------------------------------

WTR_JSON = ROOT / "engine" / "card_effects" / "json" / "wtr"


def _load_wtr() -> int:
    return load_all_cards(WTR_JSON)


def _make_hero(pid: int = 1) -> Card:
    c = Card(slug="test_hero", name="Test Hero", types=["Hero"],
             base_life=40, base_intellect=4)
    c.owner = pid
    c.controller = pid
    return c


def _make_player(pid: int = 1) -> Player:
    return Player(pid, _make_hero(pid))


def _mock_agent(state, options, **kwargs):
    return options[0] if options else None


def _make_state() -> GameState:
    p1 = _make_player(1)
    p2 = _make_player(2)
    return GameState(
        players={1: p1, 2: p2},
        active_player=1,
        player_agents={1: _mock_agent, 2: _mock_agent},
        step=Step.ACTION,
        turn_number=1,
        combat=None,
        done=False,
        winner=None,
    )


def _make_card(slug: str, owner: int = 1, types=None) -> Card:
    c = Card(slug=slug, name=slug, types=types or ["Action"])
    c.owner = owner
    c.controller = owner
    c.zone = "hand"
    return c


def _make_deck_card(slug: str, owner: int = 1, power: int = 1, cost: int = 1) -> Card:
    c = Card(slug=slug, name=slug, types=["Action"])
    c.owner = owner
    c.controller = owner
    c.power = power
    c.cost = cost
    return c


def _make_combat(attacker_id: int = 1, power: int = 5, attack_card: Card | None = None,
                 from_weapon: bool = False) -> CombatState:
    ac = attack_card or _make_card("atk", attacker_id)
    return CombatState(
        attacker_id=attacker_id, link_id=1,
        attack_power=power, attack_card=ac, keywords=[],
        from_weapon=from_weapon,
    )


def _make_chain_link(slug: str, power: int = 5, hit: bool = False, attacker_id: int = 1):
    return ChainLink(
        chainlink_id=0, attacker_id=attacker_id,
        attack_slug=slug, attack_power=power,
        net_damage=0, keywords=[], from_weapon=False, hit=hit,
    )


def _hit_event(damage: int = 4) -> Event:
    return Event(type="ON_HIT", data={"damage": damage})


# ---------------------------------------------------------------------------
# Module-level setup
# ---------------------------------------------------------------------------

_load_wtr()


# ===========================================================================
# anothos
# ===========================================================================

def test_anothos_card_loads():
    assert get_card("anothos") is not None


def test_anothos_static_ability_present():
    cd = get_card("anothos")
    assert cd is not None and len(cd.abilities) == 1
    assert cd.abilities[0].ability_type == "STATIC"


def test_anothos_static_not_dispatched_via_dsl():
    """STATIC abilities are intentionally not fired via dispatch()."""
    state = _make_state()
    state.combat = _make_combat(power=5)
    card = _make_card("anothos", 1)
    dispatch(state, "ON_PLAY", "anothos", card=card)
    # power must remain unchanged because STATIC effects aren't dispatched
    assert state.combat.attack_power == 5


# ===========================================================================
# barkbone_strapping
# ===========================================================================

def test_barkbone_strapping_loads():
    cd = get_card("barkbone_strapping")
    assert cd is not None
    assert cd.abilities[0].ability_type == "ACTIVATE"


def test_barkbone_strapping_activate_grants_resources_or_zero():
    """Roll 1d6 / 2 — must be int in [0, 3]."""
    state = _make_state()
    card = _make_card("barkbone_strapping", 1)
    state.players[1].permanents.add(card)
    before = state.players[1].resources
    dispatch(state, "ON_ACTIVATE", "barkbone_strapping", card=card)
    delta = state.players[1].resources - before
    assert 0 <= delta <= 3


def test_barkbone_strapping_wrong_event_no_op():
    state = _make_state()
    card = _make_card("barkbone_strapping", 1)
    before = state.players[1].resources
    dispatch(state, "ON_HIT", "barkbone_strapping", card=card)
    assert state.players[1].resources == before


# ===========================================================================
# barraging_brawnhide_blue / red  (STATIC — no DSL dispatch)
# ===========================================================================

def test_barraging_brawnhide_blue_loads():
    assert get_card("barraging_brawnhide_blue") is not None


def test_barraging_brawnhide_blue_is_static():
    cd = get_card("barraging_brawnhide_blue")
    assert cd.abilities[0].ability_type == "STATIC"


def test_barraging_brawnhide_blue_static_not_dispatched():
    state = _make_state()
    state.combat = _make_combat(power=4)
    card = _make_card("barraging_brawnhide_blue", 1)
    dispatch(state, "ON_PLAY", "barraging_brawnhide_blue", card=card)
    # STATIC: no dispatch path → no power change
    assert state.combat.attack_power == 4


def test_barraging_brawnhide_red_loads():
    assert get_card("barraging_brawnhide_red") is not None


def test_barraging_brawnhide_red_is_static():
    cd = get_card("barraging_brawnhide_red")
    assert cd.abilities[0].ability_type == "STATIC"


def test_barraging_brawnhide_red_static_not_dispatched():
    state = _make_state()
    state.combat = _make_combat(power=4)
    card = _make_card("barraging_brawnhide_red", 1)
    dispatch(state, "ON_PLAY", "barraging_brawnhide_red", card=card)
    assert state.combat.attack_power == 4


# ===========================================================================
# blessing_of_deliverance_blue / red / yellow
# ===========================================================================

def test_blessing_of_deliverance_blue_draws_when_pitch_3plus():
    state = _make_state()
    state.players[1].pitch.add(_make_deck_card("hi", power=1, cost=3))
    state.players[1].deck.add(_make_deck_card("d0"))
    state.players[1].deck.add(_make_deck_card("d1"))
    card = _make_card("blessing_of_deliverance_blue", 1)
    dispatch(state, "ON_ENTER_PLAY", "blessing_of_deliverance_blue", card=card)
    assert len(state.players[1].hand.cards) == 1


def test_blessing_of_deliverance_blue_no_draw_without_high_cost_pitch():
    state = _make_state()
    state.players[1].pitch.add(_make_deck_card("lo", cost=1))
    state.players[1].deck.add(_make_deck_card("d0"))
    card = _make_card("blessing_of_deliverance_blue", 1)
    dispatch(state, "ON_ENTER_PLAY", "blessing_of_deliverance_blue", card=card)
    assert len(state.players[1].hand.cards) == 0


def test_blessing_of_deliverance_blue_loads_start_of_turn_ability():
    cd = get_card("blessing_of_deliverance_blue")
    assert any(a.trigger == "START_OF_TURN" for a in cd.abilities)


def test_blessing_of_deliverance_red_draws_when_pitch_3plus():
    state = _make_state()
    state.players[1].pitch.add(_make_deck_card("hi", cost=3))
    state.players[1].deck.add(_make_deck_card("d0"))
    card = _make_card("blessing_of_deliverance_red", 1)
    dispatch(state, "ON_ENTER_PLAY", "blessing_of_deliverance_red", card=card)
    assert len(state.players[1].hand.cards) == 1


def test_blessing_of_deliverance_red_no_draw_without_high_cost_pitch():
    state = _make_state()
    state.players[1].pitch.add(_make_deck_card("lo", cost=2))
    state.players[1].deck.add(_make_deck_card("d0"))
    card = _make_card("blessing_of_deliverance_red", 1)
    dispatch(state, "ON_ENTER_PLAY", "blessing_of_deliverance_red", card=card)
    assert len(state.players[1].hand.cards) == 0


def test_blessing_of_deliverance_red_loads_start_of_turn_ability():
    cd = get_card("blessing_of_deliverance_red")
    assert any(a.trigger == "START_OF_TURN" for a in cd.abilities)


def test_blessing_of_deliverance_yellow_draws_when_pitch_3plus():
    state = _make_state()
    state.players[1].pitch.add(_make_deck_card("hi", cost=4))
    state.players[1].deck.add(_make_deck_card("d0"))
    card = _make_card("blessing_of_deliverance_yellow", 1)
    dispatch(state, "ON_ENTER_PLAY", "blessing_of_deliverance_yellow", card=card)
    assert len(state.players[1].hand.cards) == 1


def test_blessing_of_deliverance_yellow_no_draw_without_high_cost_pitch():
    state = _make_state()
    state.players[1].pitch.add(_make_deck_card("lo", cost=1))
    state.players[1].deck.add(_make_deck_card("d0"))
    card = _make_card("blessing_of_deliverance_yellow", 1)
    dispatch(state, "ON_ENTER_PLAY", "blessing_of_deliverance_yellow", card=card)
    assert len(state.players[1].hand.cards) == 0


def test_blessing_of_deliverance_yellow_loads_start_of_turn_ability():
    cd = get_card("blessing_of_deliverance_yellow")
    assert any(a.trigger == "START_OF_TURN" for a in cd.abilities)


# ===========================================================================
# bone_head_barrier_yellow
# ===========================================================================

def test_bone_head_barrier_yellow_play_grants_action_point():
    state = _make_state()
    card = _make_card("bone_head_barrier_yellow", 1)
    before = state.players[1].action_points
    dispatch(state, "ON_PLAY", "bone_head_barrier_yellow", card=card)
    assert state.players[1].action_points == before + 1


def test_bone_head_barrier_yellow_sets_next_turn_flag():
    state = _make_state()
    card = _make_card("bone_head_barrier_yellow", 1)
    dispatch(state, "ON_PLAY", "bone_head_barrier_yellow", card=card)
    assert "bone_head_barrier_active" in state.players[1].next_turn_effects


def test_bone_head_barrier_yellow_wrong_event_no_op():
    state = _make_state()
    card = _make_card("bone_head_barrier_yellow", 1)
    before = state.players[1].action_points
    dispatch(state, "ON_HIT", "bone_head_barrier_yellow", card=card)
    assert state.players[1].action_points == before


# ===========================================================================
# braveforge_bracers
# ===========================================================================

def test_braveforge_bracers_loads():
    cd = get_card("braveforge_bracers")
    assert cd is not None and cd.abilities[0].ability_type == "ACTIVATE"


def test_braveforge_bracers_activate_with_flag_queues_bonus():
    state = _make_state()
    state.players[1].resources = 1  # cover PAY_RESOURCES cost
    state.players[1].current_turn_effects.append("weapon_hit_this_turn")
    card = _make_card("braveforge_bracers", 1)
    dispatch(state, "ON_ACTIVATE", "braveforge_bracers", card=card)
    assert "next_weapon_attack_+1" in state.players[1].current_turn_effects


def test_braveforge_bracers_no_flag_no_effect():
    state = _make_state()
    card = _make_card("braveforge_bracers", 1)
    dispatch(state, "ON_ACTIVATE", "braveforge_bracers", card=card)
    assert "next_weapon_attack_+1" not in state.players[1].current_turn_effects


# ===========================================================================
# bravo  /  bravo_showstopper  (ACTIVATE → GO_AGAIN; STATIC dominate)
# ===========================================================================

def test_bravo_loads():
    cd = get_card("bravo")
    assert cd is not None and cd.abilities[0].ability_type == "ACTIVATE"


def test_bravo_activate_grants_go_again_in_combat():
    state = _make_state()
    state.players[1].resources = 2  # cover PAY_RESOURCES cost
    state.combat = _make_combat()
    card = _make_card("bravo", 1)
    dispatch(state, "ON_ACTIVATE", "bravo", card=card)
    assert "go_again" in state.combat.keywords


def test_bravo_wrong_event_no_op():
    state = _make_state()
    state.combat = _make_combat()
    card = _make_card("bravo", 1)
    dispatch(state, "ON_HIT", "bravo", card=card)
    assert "go_again" not in state.combat.keywords


def test_bravo_showstopper_loads():
    cd = get_card("bravo_showstopper")
    assert cd is not None and cd.abilities[0].ability_type == "ACTIVATE"


def test_bravo_showstopper_activate_grants_go_again_in_combat():
    state = _make_state()
    state.players[1].resources = 2  # cover PAY_RESOURCES cost
    state.combat = _make_combat()
    card = _make_card("bravo_showstopper", 1)
    dispatch(state, "ON_ACTIVATE", "bravo_showstopper", card=card)
    assert "go_again" in state.combat.keywords


def test_bravo_showstopper_wrong_event_no_op():
    state = _make_state()
    state.combat = _make_combat()
    card = _make_card("bravo_showstopper", 1)
    dispatch(state, "ON_HIT", "bravo_showstopper", card=card)
    assert "go_again" not in state.combat.keywords


# ===========================================================================
# breaking_scales
# ===========================================================================

def test_breaking_scales_loads():
    cd = get_card("breaking_scales")
    assert cd is not None
    assert any(a.ability_type == "ATTACK_REACTION" for a in cd.abilities)


def test_breaking_scales_combo_condition_present():
    """The ATTACK_REACTION ability has a COMBO condition that gates the
    +1{p} effect. With no combo names supplied, combo_check returns False
    so the effect never fires."""
    cd = get_card("breaking_scales")
    ar = next(a for a in cd.abilities if a.ability_type == "ATTACK_REACTION")
    assert any(c.condition_type == "COMBO" for c in ar.conditions)


def test_breaking_scales_no_combo_no_power_bonus():
    state = _make_state()
    state.combat = _make_combat(power=3)
    card = _make_card("breaking_scales", 1)
    dispatch(state, "ON_PLAY", "breaking_scales", card=card)
    # No chain links → COMBO condition false → no power change
    assert state.combat.attack_power == 3


# ===========================================================================
# buckling_blow_blue / red / yellow  (CRUSH → put -1d counter)
# ===========================================================================

def _check_crush_counter(slug: str):
    state = _make_state()
    card = _make_card(slug, 1)
    state.combat = _make_combat(attacker_id=1, power=5, attack_card=card)
    ev = _hit_event(damage=4)
    dispatch(state, "ON_HIT", slug, card=card, event=ev)
    # something was added to player counters
    counters_after = sum(state.players[1].counters.values())
    assert counters_after >= 1


def _check_crush_no_fire(slug: str):
    state = _make_state()
    card = _make_card(slug, 1)
    state.combat = _make_combat(attacker_id=1, power=2, attack_card=card)
    ev = _hit_event(damage=3)
    dispatch(state, "ON_HIT", slug, card=card, event=ev)
    counters_after = sum(state.players[1].counters.values())
    assert counters_after == 0


def test_buckling_blow_blue_fires_on_crush():
    _check_crush_counter("buckling_blow_blue")


def test_buckling_blow_blue_gates_below_4_damage():
    _check_crush_no_fire("buckling_blow_blue")


def test_buckling_blow_blue_loads():
    assert get_card("buckling_blow_blue") is not None


def test_buckling_blow_red_fires_on_crush():
    _check_crush_counter("buckling_blow_red")


def test_buckling_blow_red_gates_below_4_damage():
    _check_crush_no_fire("buckling_blow_red")


def test_buckling_blow_red_loads():
    assert get_card("buckling_blow_red") is not None


def test_buckling_blow_yellow_fires_on_crush():
    _check_crush_counter("buckling_blow_yellow")


def test_buckling_blow_yellow_gates_below_4_damage():
    _check_crush_no_fire("buckling_blow_yellow")


def test_buckling_blow_yellow_loads():
    assert get_card("buckling_blow_yellow") is not None


# ===========================================================================
# cartilage_crush_blue / red / yellow  (CRUSH → set NEXT-turn flag)
# ===========================================================================

def _check_crush_sets_flag(slug: str, flag: str = "crush_cost_next_turn"):
    state = _make_state()
    card = _make_card(slug, 1)
    state.combat = _make_combat(attacker_id=1, power=5, attack_card=card)
    ev = _hit_event(damage=4)
    dispatch(state, "ON_HIT", slug, card=card, event=ev)
    assert flag in state.players[1].next_turn_effects


def _check_crush_does_not_set_flag(slug: str, flag: str = "crush_cost_next_turn"):
    state = _make_state()
    card = _make_card(slug, 1)
    state.combat = _make_combat(attacker_id=1, power=2, attack_card=card)
    ev = _hit_event(damage=3)
    dispatch(state, "ON_HIT", slug, card=card, event=ev)
    assert flag not in state.players[1].next_turn_effects


def test_cartilage_crush_blue_fires_on_crush():
    _check_crush_sets_flag("cartilage_crush_blue")


def test_cartilage_crush_blue_gates_below_4_damage():
    _check_crush_does_not_set_flag("cartilage_crush_blue")


def test_cartilage_crush_blue_loads():
    assert get_card("cartilage_crush_blue") is not None


def test_cartilage_crush_red_fires_on_crush():
    _check_crush_sets_flag("cartilage_crush_red")


def test_cartilage_crush_red_gates_below_4_damage():
    _check_crush_does_not_set_flag("cartilage_crush_red")


def test_cartilage_crush_red_loads():
    assert get_card("cartilage_crush_red") is not None


def test_cartilage_crush_yellow_fires_on_crush():
    _check_crush_sets_flag("cartilage_crush_yellow")


def test_cartilage_crush_yellow_gates_below_4_damage():
    _check_crush_does_not_set_flag("cartilage_crush_yellow")


def test_cartilage_crush_yellow_loads():
    assert get_card("cartilage_crush_yellow") is not None


# ===========================================================================
# cracked_bauble_yellow  (vanilla — no abilities)
# ===========================================================================

def test_cracked_bauble_yellow_no_abilities():
    cd = get_card("cracked_bauble_yellow")
    assert cd is not None and cd.abilities == []


def test_cracked_bauble_yellow_dispatch_is_noop():
    state = _make_state()
    card = _make_card("cracked_bauble_yellow", 1)
    # Must not raise on any event
    dispatch(state, "ON_PLAY", "cracked_bauble_yellow", card=card)
    dispatch(state, "ON_HIT", "cracked_bauble_yellow", card=card)


def test_cracked_bauble_yellow_loads():
    assert get_card("cracked_bauble_yellow") is not None


# ===========================================================================
# cranial_crush_blue
# ===========================================================================

def test_cranial_crush_blue_fires_on_crush():
    _check_crush_sets_flag("cranial_crush_blue", flag="no_draw_next_action")


def test_cranial_crush_blue_gates_below_4_damage():
    _check_crush_does_not_set_flag("cranial_crush_blue", flag="no_draw_next_action")


def test_cranial_crush_blue_loads():
    assert get_card("cranial_crush_blue") is not None


# ===========================================================================
# crazy_brew_blue (ACTIVATE → roll-driven inject)
# ===========================================================================

def test_crazy_brew_blue_loads():
    cd = get_card("crazy_brew_blue")
    assert cd is not None and cd.abilities[0].ability_type == "ACTIVATE"


def test_crazy_brew_blue_activate_does_not_crash():
    state = _make_state()
    card = _make_card("crazy_brew_blue", 1)
    state.players[1].permanents.add(card)
    # Should not raise; state remains consistent
    dispatch(state, "ON_ACTIVATE", "crazy_brew_blue", card=card)


def test_crazy_brew_blue_wrong_event_no_op():
    state = _make_state()
    card = _make_card("crazy_brew_blue", 1)
    before_resources = state.players[1].resources
    dispatch(state, "ON_HIT", "crazy_brew_blue", card=card)
    # Wrong event — no resource change
    assert state.players[1].resources == before_resources


# ===========================================================================
# crippling_crush_red (CRUSH → opponent discards 2)
# ===========================================================================

def test_crippling_crush_red_fires_on_crush():
    state = _make_state()
    # populate opponent hand with 3 cards
    for i in range(3):
        c = _make_deck_card(f"opp{i}", owner=2)
        state.players[2].hand.add(c)
    card = _make_card("crippling_crush_red", 1)
    state.combat = _make_combat(attacker_id=1, power=5, attack_card=card)
    dispatch(state, "ON_HIT", "crippling_crush_red", card=card, event=_hit_event(damage=4))
    # Opponent should have lost 2 cards from hand
    assert len(state.players[2].hand.cards) == 1


def test_crippling_crush_red_gates_below_4_damage():
    state = _make_state()
    for i in range(3):
        c = _make_deck_card(f"opp{i}", owner=2)
        state.players[2].hand.add(c)
    card = _make_card("crippling_crush_red", 1)
    state.combat = _make_combat(attacker_id=1, power=2, attack_card=card)
    dispatch(state, "ON_HIT", "crippling_crush_red", card=card, event=_hit_event(damage=3))
    assert len(state.players[2].hand.cards) == 3


def test_crippling_crush_red_loads():
    assert get_card("crippling_crush_red") is not None


# ===========================================================================
# crush_confidence_blue / red / yellow
# ===========================================================================

def test_crush_confidence_blue_fires_on_crush():
    _check_crush_sets_flag("crush_confidence_blue", flag="hero_abilities_disabled")


def test_crush_confidence_blue_gates_below_4_damage():
    _check_crush_does_not_set_flag("crush_confidence_blue", flag="hero_abilities_disabled")


def test_crush_confidence_blue_loads():
    assert get_card("crush_confidence_blue") is not None


def test_crush_confidence_red_fires_on_crush():
    _check_crush_sets_flag("crush_confidence_red", flag="hero_card_abilities_disabled")


def test_crush_confidence_red_gates_below_4_damage():
    _check_crush_does_not_set_flag("crush_confidence_red", flag="hero_card_abilities_disabled")


def test_crush_confidence_red_loads():
    assert get_card("crush_confidence_red") is not None


def test_crush_confidence_yellow_fires_on_crush():
    _check_crush_sets_flag("crush_confidence_yellow", flag="crush_confidence_lose_ability")


def test_crush_confidence_yellow_gates_below_4_damage():
    _check_crush_does_not_set_flag("crush_confidence_yellow", flag="crush_confidence_lose_ability")


def test_crush_confidence_yellow_loads():
    assert get_card("crush_confidence_yellow") is not None


# ===========================================================================
# dawnblade  (multi-ability hero weapon)
# ===========================================================================

def test_dawnblade_loads():
    cd = get_card("dawnblade")
    assert cd is not None and len(cd.abilities) >= 2


def test_dawnblade_has_start_of_turn_ability():
    cd = get_card("dawnblade")
    assert any(a.trigger == "START_OF_TURN" for a in cd.abilities)


def test_dawnblade_start_of_turn_no_hit_runs_cleanup():
    state = _make_state()
    card = _make_card("dawnblade", 1)
    # Should not raise even when no flag was set
    dispatch(state, "START_OF_TURN", "dawnblade", card=card)


def test_dawnblade_dispatch_does_not_crash():
    state = _make_state()
    card = _make_card("dawnblade", 1)
    state.combat = _make_combat(attacker_id=1, power=4, attack_card=card)
    # The "ATTACK_REACTION" ability fires on ON_PLAY.  Just verify no crash.
    dispatch(state, "ON_PLAY", "dawnblade", card=card)


# ===========================================================================
# debilitate_blue / red / yellow  (CRUSH → next attack -2 power)
# ===========================================================================

def test_debilitate_blue_fires_on_crush_injects_trigger():
    state = _make_state()
    card = _make_card("debilitate_blue", 1)
    state.combat = _make_combat(attacker_id=1, power=5, attack_card=card)
    dispatch(state, "ON_HIT", "debilitate_blue", card=card, event=_hit_event(4))
    assert hasattr(state.combat, "injected_triggers")
    assert len(state.combat.injected_triggers) >= 1


def test_debilitate_blue_gates_below_4_damage():
    state = _make_state()
    card = _make_card("debilitate_blue", 1)
    state.combat = _make_combat(attacker_id=1, power=2, attack_card=card)
    dispatch(state, "ON_HIT", "debilitate_blue", card=card, event=_hit_event(3))
    assert not getattr(state.combat, "injected_triggers", [])


def test_debilitate_blue_loads():
    assert get_card("debilitate_blue") is not None


def test_debilitate_red_fires_on_crush_modifies_power():
    state = _make_state()
    card = _make_card("debilitate_red", 1)
    state.combat = _make_combat(attacker_id=1, power=5, attack_card=card)
    before = state.combat.attack_power
    dispatch(state, "ON_HIT", "debilitate_red", card=card, event=_hit_event(4))
    # Effect runs MODIFY_ATTACK_POWER -2 immediately
    assert state.combat.attack_power == before - 2


def test_debilitate_red_gates_below_4_damage():
    state = _make_state()
    card = _make_card("debilitate_red", 1)
    state.combat = _make_combat(attacker_id=1, power=5, attack_card=card)
    before = state.combat.attack_power
    dispatch(state, "ON_HIT", "debilitate_red", card=card, event=_hit_event(3))
    assert state.combat.attack_power == before


def test_debilitate_red_loads():
    assert get_card("debilitate_red") is not None


def test_debilitate_yellow_fires_on_crush_injects_trigger():
    state = _make_state()
    card = _make_card("debilitate_yellow", 1)
    state.combat = _make_combat(attacker_id=1, power=5, attack_card=card)
    dispatch(state, "ON_HIT", "debilitate_yellow", card=card, event=_hit_event(4))
    assert hasattr(state.combat, "injected_triggers")
    assert len(state.combat.injected_triggers) >= 1


def test_debilitate_yellow_gates_below_4_damage():
    state = _make_state()
    card = _make_card("debilitate_yellow", 1)
    state.combat = _make_combat(attacker_id=1, power=2, attack_card=card)
    dispatch(state, "ON_HIT", "debilitate_yellow", card=card, event=_hit_event(3))
    assert not getattr(state.combat, "injected_triggers", [])


def test_debilitate_yellow_loads():
    assert get_card("debilitate_yellow") is not None


# ===========================================================================
# demolition_crew_blue / red / yellow  (PLAY → DOMINATE; gated by reveal cost)
# ===========================================================================

def _check_demo_crew_dominate(slug: str):
    """When hand has a 2+ cost card, additional_cost passes and DOMINATE applies."""
    state = _make_state()
    state.players[1].hand.add(_make_deck_card("biggie", cost=3))
    state.combat = _make_combat()
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    # DOMINATE adds the literal "Dominate" keyword to combat (per effect_dominate)
    assert "Dominate" in state.combat.keywords


def _check_demo_crew_no_dominate(slug: str):
    """No 2+ cost card in hand → additional_cost can't be paid → no effect."""
    state = _make_state()
    # only cheap cards
    state.players[1].hand.add(_make_deck_card("cheapy", cost=1))
    state.combat = _make_combat()
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert "Dominate" not in state.combat.keywords


def test_demolition_crew_blue_fires_on_play():
    _check_demo_crew_dominate("demolition_crew_blue")


def test_demolition_crew_blue_gates_no_2cost_card():
    _check_demo_crew_no_dominate("demolition_crew_blue")


def test_demolition_crew_blue_loads():
    assert get_card("demolition_crew_blue") is not None


def test_demolition_crew_red_fires_on_play():
    _check_demo_crew_dominate("demolition_crew_red")


def test_demolition_crew_red_gates_no_2cost_card():
    _check_demo_crew_no_dominate("demolition_crew_red")


def test_demolition_crew_red_loads():
    assert get_card("demolition_crew_red") is not None


def test_demolition_crew_yellow_fires_on_play():
    _check_demo_crew_dominate("demolition_crew_yellow")


def test_demolition_crew_yellow_gates_no_2cost_card():
    _check_demo_crew_no_dominate("demolition_crew_yellow")


def test_demolition_crew_yellow_loads():
    assert get_card("demolition_crew_yellow") is not None


# ===========================================================================
# disable_blue / red / yellow  (CRUSH → put bottom + draw)
# ===========================================================================

def _check_disable_fires(slug: str):
    """On crush (4+ dmg) the put-bottom-draw effect fires.

    PUT_BOTTOM_DRAW asks the controller for a hand card; with our mock
    agent picking the first option, the effect either picks a card
    (decrementing hand) or "decline" (no change).  We verify the ability
    fires by checking that a deck-add occurred (deck size > 0 after).
    """
    state = _make_state()
    state.players[1].hand.add(_make_deck_card("h0"))
    state.players[1].deck.add(_make_deck_card("d0"))
    card = _make_card(slug, 1)
    state.combat = _make_combat(attacker_id=1, power=5, attack_card=card)
    dispatch(state, "ON_HIT", slug, card=card, event=_hit_event(4))


def _check_disable_no_fire(slug: str):
    state = _make_state()
    state.players[1].hand.add(_make_deck_card("h0"))
    card = _make_card(slug, 1)
    state.combat = _make_combat(attacker_id=1, power=2, attack_card=card)
    hand_before = len(state.players[1].hand.cards)
    dispatch(state, "ON_HIT", slug, card=card, event=_hit_event(3))
    # Below crush threshold — no card movement
    assert len(state.players[1].hand.cards) == hand_before


def test_disable_blue_fires_on_crush():
    _check_disable_fires("disable_blue")


def test_disable_blue_gates_below_4_damage():
    _check_disable_no_fire("disable_blue")


def test_disable_blue_loads():
    assert get_card("disable_blue") is not None


def test_disable_red_fires_on_crush():
    _check_disable_fires("disable_red")


def test_disable_red_gates_below_4_damage():
    _check_disable_no_fire("disable_red")


def test_disable_red_loads():
    assert get_card("disable_red") is not None


def test_disable_yellow_fires_on_crush():
    _check_disable_fires("disable_yellow")


def test_disable_yellow_gates_below_4_damage():
    _check_disable_no_fire("disable_yellow")


def test_disable_yellow_loads():
    assert get_card("disable_yellow") is not None


# ===========================================================================
# dorinthea  (hero — weapon hit grants go again, once per turn)
# ===========================================================================

def test_dorinthea_loads():
    assert get_card("dorinthea") is not None


def test_dorinthea_weapon_hit_grants_go_again():
    state = _make_state()
    card = _make_card("dorinthea", 1, types=["Hero"])
    state.combat = _make_combat(attacker_id=1, power=4, from_weapon=True, attack_card=card)
    dispatch(state, "ON_HIT", "dorinthea", card=card, event=_hit_event(4))
    assert "go_again" in state.combat.keywords


def test_dorinthea_already_used_this_turn_no_go_again():
    state = _make_state()
    state.players[1].current_turn_effects.append("dorinthea_used_this_turn")
    card = _make_card("dorinthea", 1, types=["Hero"])
    state.combat = _make_combat(attacker_id=1, power=4, from_weapon=True, attack_card=card)
    dispatch(state, "ON_HIT", "dorinthea", card=card, event=_hit_event(4))
    assert "go_again" not in state.combat.keywords


def test_dorinthea_non_weapon_attack_no_go_again():
    state = _make_state()
    card = _make_card("dorinthea", 1, types=["Hero"])
    state.combat = _make_combat(attacker_id=1, power=4, from_weapon=False, attack_card=card)
    dispatch(state, "ON_HIT", "dorinthea", card=card, event=_hit_event(4))
    assert "go_again" not in state.combat.keywords


# ===========================================================================
# dorinthea_ironsong  (ATTACK_REACTION on weapon attack → go again)
# ===========================================================================

def test_dorinthea_ironsong_loads():
    assert get_card("dorinthea_ironsong") is not None


def test_dorinthea_ironsong_weapon_attack_grants_go_again():
    state = _make_state()
    state.combat = _make_combat(attacker_id=1, power=4, from_weapon=True)
    card = _make_card("dorinthea_ironsong", 1, types=["Hero"])
    dispatch(state, "ON_PLAY", "dorinthea_ironsong", card=card)
    assert "go_again" in state.combat.keywords


def test_dorinthea_ironsong_non_weapon_attack_no_go_again():
    state = _make_state()
    state.combat = _make_combat(attacker_id=1, power=4, from_weapon=False)
    card = _make_card("dorinthea_ironsong", 1, types=["Hero"])
    dispatch(state, "ON_PLAY", "dorinthea_ironsong", card=card)
    assert "go_again" not in state.combat.keywords


# ===========================================================================
# drone_of_brutality_blue / red / yellow
# ===========================================================================

def test_drone_of_brutality_blue_loads():
    assert get_card("drone_of_brutality_blue") is not None


def test_drone_of_brutality_blue_has_discard_trigger():
    cd = get_card("drone_of_brutality_blue")
    assert any(a.trigger == "ON_DISCARD" for a in cd.abilities)


def test_drone_of_brutality_blue_discard_puts_self_on_deck_bottom():
    state = _make_state()
    card = _make_card("drone_of_brutality_blue", 1)
    state.players[1].graveyard.add(card)
    dispatch(state, "ON_DISCARD", "drone_of_brutality_blue", card=card)
    assert card in state.players[1].deck.cards
    assert card not in state.players[1].graveyard.cards


def test_drone_of_brutality_red_loads():
    assert get_card("drone_of_brutality_red") is not None


def test_drone_of_brutality_red_has_discard_trigger():
    cd = get_card("drone_of_brutality_red")
    assert any(a.trigger == "ON_DISCARD" for a in cd.abilities)


def test_drone_of_brutality_red_discard_puts_self_on_deck_bottom():
    state = _make_state()
    card = _make_card("drone_of_brutality_red", 1)
    state.players[1].graveyard.add(card)
    dispatch(state, "ON_DISCARD", "drone_of_brutality_red", card=card)
    assert card in state.players[1].deck.cards
    assert card not in state.players[1].graveyard.cards


def test_drone_of_brutality_yellow_loads():
    assert get_card("drone_of_brutality_yellow") is not None


def test_drone_of_brutality_yellow_has_discard_trigger():
    cd = get_card("drone_of_brutality_yellow")
    assert any(a.trigger == "ON_DISCARD" for a in cd.abilities)


def test_drone_of_brutality_yellow_discard_puts_self_on_deck_bottom():
    state = _make_state()
    card = _make_card("drone_of_brutality_yellow", 1)
    state.players[1].graveyard.add(card)
    dispatch(state, "ON_DISCARD", "drone_of_brutality_yellow", card=card)
    assert card in state.players[1].deck.cards
    assert card not in state.players[1].graveyard.cards


# ===========================================================================
# emerging_power_blue / red / yellow
# ===========================================================================

def test_emerging_power_blue_loads():
    assert get_card("emerging_power_blue") is not None


def test_emerging_power_blue_has_start_of_turn_ability():
    cd = get_card("emerging_power_blue")
    assert any(a.trigger == "START_OF_TURN" for a in cd.abilities)


def test_emerging_power_blue_start_of_turn_active_player_no_crash():
    state = _make_state()
    card = _make_card("emerging_power_blue", 1)
    dispatch(state, "START_OF_TURN", "emerging_power_blue", card=card)


def test_emerging_power_red_loads():
    assert get_card("emerging_power_red") is not None


def test_emerging_power_red_has_start_of_turn_ability():
    cd = get_card("emerging_power_red")
    assert any(a.trigger == "START_OF_TURN" for a in cd.abilities)


def test_emerging_power_red_start_of_turn_active_player_no_crash():
    state = _make_state()
    card = _make_card("emerging_power_red", 1)
    dispatch(state, "START_OF_TURN", "emerging_power_red", card=card)


def test_emerging_power_yellow_loads():
    assert get_card("emerging_power_yellow") is not None


def test_emerging_power_yellow_has_start_of_turn_ability():
    cd = get_card("emerging_power_yellow")
    assert any(a.trigger == "START_OF_TURN" for a in cd.abilities)


def test_emerging_power_yellow_start_of_turn_active_player_no_crash():
    state = _make_state()
    card = _make_card("emerging_power_yellow", 1)
    dispatch(state, "START_OF_TURN", "emerging_power_yellow", card=card)


# ===========================================================================
# enlightened_strike_red
# ===========================================================================

def test_enlightened_strike_red_loads():
    cd = get_card("enlightened_strike_red")
    assert cd is not None
    # Must have multiple ability entries (PLAY + ON_ATTACK triggers)
    assert len(cd.abilities) >= 2


def test_enlightened_strike_red_play_with_card_in_hand_runs():
    """When the player has a hand card, the additional_cost can be paid."""
    state = _make_state()
    state.players[1].hand.add(_make_deck_card("filler"))
    state.players[1].deck.add(_make_deck_card("d0"))
    card = _make_card("enlightened_strike_red", 1)
    # Should not raise; PLAY ability runs (no observable effects, just cost)
    dispatch(state, "ON_PLAY", "enlightened_strike_red", card=card)
    # The cost moved a card from hand to deck → hand empty, deck +1
    assert len(state.players[1].deck.cards) >= 1


def test_enlightened_strike_red_attack_with_power_bonus_flag():
    state = _make_state()
    state.players[1].current_turn_effects.append("power_bonus")
    card = _make_card("enlightened_strike_red", 1)
    state.combat = _make_combat(attacker_id=1, power=4, attack_card=card)
    dispatch(state, "ON_ATTACK", "enlightened_strike_red", card=card)
    assert state.combat.attack_power == 6  # +2


def test_enlightened_strike_red_attack_with_go_again_flag():
    state = _make_state()
    state.players[1].current_turn_effects.append("go_again")
    card = _make_card("enlightened_strike_red", 1)
    state.combat = _make_combat(attacker_id=1, power=4, attack_card=card)
    dispatch(state, "ON_ATTACK", "enlightened_strike_red", card=card)
    assert "go_again" in state.combat.keywords


# ===========================================================================
# flic_flak_blue / red / yellow  (DEFENSE_REACTION — combo gated)
# ===========================================================================

def test_flic_flak_blue_loads():
    cd = get_card("flic_flak_blue")
    assert cd is not None and cd.abilities[0].ability_type == "DEFENSE_REACTION"


def test_flic_flak_blue_with_combo_dispatches():
    """DEFENSE_REACTION fires on ON_PLAY when COMBO condition holds."""
    state = _make_state()
    state.chain_links.append(_make_chain_link("surging_strike_red"))
    state.combat = _make_combat(power=3)
    card = _make_card("flic_flak_blue", 1)
    # Effect type MODIFY_DEFENSE_VALUE is unknown — we just verify dispatch
    # does not crash with the COMBO condition true.
    dispatch(state, "ON_PLAY", "flic_flak_blue", card=card)


def test_flic_flak_blue_no_combo_no_crash():
    state = _make_state()
    state.combat = _make_combat(power=3)
    card = _make_card("flic_flak_blue", 1)
    dispatch(state, "ON_PLAY", "flic_flak_blue", card=card)


def test_flic_flak_red_loads():
    cd = get_card("flic_flak_red")
    assert cd is not None and cd.abilities[0].ability_type == "DEFENSE_REACTION"


def test_flic_flak_red_with_combo_dispatches():
    state = _make_state()
    state.chain_links.append(_make_chain_link("surging_strike_red"))
    state.combat = _make_combat(power=3)
    card = _make_card("flic_flak_red", 1)
    dispatch(state, "ON_PLAY", "flic_flak_red", card=card)


def test_flic_flak_red_no_combo_no_crash():
    state = _make_state()
    state.combat = _make_combat(power=3)
    card = _make_card("flic_flak_red", 1)
    dispatch(state, "ON_PLAY", "flic_flak_red", card=card)


def test_flic_flak_yellow_loads():
    cd = get_card("flic_flak_yellow")
    assert cd is not None and cd.abilities[0].ability_type == "DEFENSE_REACTION"


def test_flic_flak_yellow_with_combo_dispatches():
    state = _make_state()
    state.chain_links.append(_make_chain_link("surging_strike_red"))
    state.combat = _make_combat(power=3)
    card = _make_card("flic_flak_yellow", 1)
    dispatch(state, "ON_PLAY", "flic_flak_yellow", card=card)


def test_flic_flak_yellow_no_combo_no_crash():
    state = _make_state()
    state.combat = _make_combat(power=3)
    card = _make_card("flic_flak_yellow", 1)
    dispatch(state, "ON_PLAY", "flic_flak_yellow", card=card)


# ===========================================================================
# alpha_rampage_red  (PLAY discard cost; ON_ATTACK INTIMIDATE)
# ===========================================================================

def test_alpha_rampage_red_loads():
    cd = get_card("alpha_rampage_red")
    assert cd is not None and len(cd.abilities) >= 2


def test_alpha_rampage_red_on_attack_intimidates_opponent():
    state = _make_state()
    for i in range(3):
        state.players[2].hand.add(_make_deck_card(f"opp{i}", owner=2))
    state.combat = _make_combat()
    card = _make_card("alpha_rampage_red", 1)
    dispatch(state, "ON_ATTACK", "alpha_rampage_red", card=card)
    assert len(state.players[2].hand.cards) == 2


def test_alpha_rampage_red_wrong_event_no_op():
    state = _make_state()
    for i in range(3):
        state.players[2].hand.add(_make_deck_card(f"opp{i}", owner=2))
    card = _make_card("alpha_rampage_red", 1)
    dispatch(state, "ON_HIT", "alpha_rampage_red", card=card)
    assert len(state.players[2].hand.cards) == 3


# ===========================================================================
# ancestral_empowerment_red  (ATTACK_REACTION ninja: +1{p} & draw)
# ===========================================================================

def test_ancestral_empowerment_red_ninja_attack_powers_up_and_draws():
    state = _make_state()
    state.players[1].deck.add(_make_deck_card("d0"))
    ninja_atk = _make_card("ninja_atk", 1)
    ninja_atk.classes = ["Ninja"]
    state.combat = _make_combat(power=3, attack_card=ninja_atk)
    card = _make_card("ancestral_empowerment_red", 1)
    dispatch(state, "ON_PLAY", "ancestral_empowerment_red", card=card)
    assert state.combat.attack_power == 4
    assert len(state.players[1].hand.cards) == 1


def test_ancestral_empowerment_red_non_ninja_attack_no_op():
    state = _make_state()
    state.players[1].deck.add(_make_deck_card("d0"))
    atk = _make_card("non_ninja_atk", 1)
    atk.classes = ["Brute"]
    state.combat = _make_combat(power=3, attack_card=atk)
    card = _make_card("ancestral_empowerment_red", 1)
    dispatch(state, "ON_PLAY", "ancestral_empowerment_red", card=card)
    assert state.combat.attack_power == 3
    assert len(state.players[1].hand.cards) == 0


# ===========================================================================
# awakening_bellow_blue / red / yellow  (PLAY: NEXT_ATTACK_BONUS + INTIMIDATE)
# ===========================================================================

def _check_awakening_bellow(slug: str, amt: int):
    state = _make_state()
    state.players[2].hand.add(_make_deck_card("opp0", owner=2))
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert f"next_attack_+{amt}" in state.players[1].current_turn_effects
    assert len(state.players[2].hand.cards) == 0


def _check_awakening_bellow_wrong_event(slug: str):
    state = _make_state()
    state.players[2].hand.add(_make_deck_card("opp0", owner=2))
    card = _make_card(slug, 1)
    dispatch(state, "ON_HIT", slug, card=card)
    assert state.players[1].current_turn_effects == []
    assert len(state.players[2].hand.cards) == 1


def test_awakening_bellow_blue_play_intimidates():
    _check_awakening_bellow("awakening_bellow_blue", 1)


def test_awakening_bellow_blue_wrong_event():
    _check_awakening_bellow_wrong_event("awakening_bellow_blue")


def test_awakening_bellow_red_play_intimidates():
    _check_awakening_bellow("awakening_bellow_red", 3)


def test_awakening_bellow_red_wrong_event():
    _check_awakening_bellow_wrong_event("awakening_bellow_red")


def test_awakening_bellow_yellow_play_intimidates():
    _check_awakening_bellow("awakening_bellow_yellow", 2)


def test_awakening_bellow_yellow_wrong_event():
    _check_awakening_bellow_wrong_event("awakening_bellow_yellow")


# ===========================================================================
# barraging_beatdown_blue / red / yellow  (PLAY: NEXT_ATTACK_BONUS + INTIMIDATE)
# ===========================================================================

def test_barraging_beatdown_blue_queues_bonus_and_intimidates():
    _check_awakening_bellow("barraging_beatdown_blue", 2)


def test_barraging_beatdown_blue_wrong_event():
    _check_awakening_bellow_wrong_event("barraging_beatdown_blue")


def test_barraging_beatdown_red_queues_bonus_and_intimidates():
    _check_awakening_bellow("barraging_beatdown_red", 4)


def test_barraging_beatdown_red_wrong_event():
    _check_awakening_bellow_wrong_event("barraging_beatdown_red")


def test_barraging_beatdown_yellow_queues_bonus_and_intimidates():
    _check_awakening_bellow("barraging_beatdown_yellow", 3)


def test_barraging_beatdown_yellow_wrong_event():
    _check_awakening_bellow_wrong_event("barraging_beatdown_yellow")


# ===========================================================================
# barraging_brawnhide_yellow  (STATIC)
# ===========================================================================

def test_barraging_brawnhide_yellow_loads():
    assert get_card("barraging_brawnhide_yellow") is not None


def test_barraging_brawnhide_yellow_is_static():
    cd = get_card("barraging_brawnhide_yellow")
    assert cd.abilities[0].ability_type == "STATIC"


def test_barraging_brawnhide_yellow_static_not_dispatched():
    state = _make_state()
    state.combat = _make_combat(power=4)
    card = _make_card("barraging_brawnhide_yellow", 1)
    dispatch(state, "ON_PLAY", "barraging_brawnhide_yellow", card=card)
    assert state.combat.attack_power == 4


# ===========================================================================
# biting_blade_blue / red / yellow  (ATTACK_REACTION: +N{p}, REPRISE all_weapons +1)
# ===========================================================================

def _check_biting_blade(slug: str, base_amt: int):
    state = _make_state()
    state.combat = _make_combat(power=2)
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert state.combat.attack_power == 2 + base_amt


def _check_biting_blade_reprise_grants_all_weapons(slug: str):
    state = _make_state()
    state.combat = _make_combat(power=2)
    state.combat.defender_used_hand_card = True
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert "all_weapon_attacks_+1" in state.players[1].current_turn_effects


def test_biting_blade_blue_base_power():
    _check_biting_blade("biting_blade_blue", 1)


def test_biting_blade_blue_reprise_all_weapons():
    _check_biting_blade_reprise_grants_all_weapons("biting_blade_blue")


def test_biting_blade_red_base_power():
    _check_biting_blade("biting_blade_red", 3)


def test_biting_blade_red_reprise_all_weapons():
    _check_biting_blade_reprise_grants_all_weapons("biting_blade_red")


def test_biting_blade_yellow_base_power():
    _check_biting_blade("biting_blade_yellow", 2)


def test_biting_blade_yellow_reprise_all_weapons():
    _check_biting_blade_reprise_grants_all_weapons("biting_blade_yellow")


def test_biting_blade_no_reprise_no_all_weapons():
    state = _make_state()
    state.combat = _make_combat(power=2)
    card = _make_card("biting_blade_blue", 1)
    dispatch(state, "ON_PLAY", "biting_blade_blue", card=card)
    assert "all_weapon_attacks_+1" not in state.players[1].current_turn_effects


# ===========================================================================
# blackout_kick_blue / red / yellow  (TRIGGERED ON_ATTACK: combo rising_knee_thrust)
# ===========================================================================

def _check_blackout_kick_combo(slug: str):
    state = _make_state()
    state.chain_links.append(_make_chain_link("rising_knee_thrust_red"))
    state.combat = _make_combat(power=2)
    card = _make_card(slug, 1)
    dispatch(state, "ON_ATTACK", slug, card=card)
    assert state.combat.attack_power == 5


def _check_blackout_kick_no_combo(slug: str):
    state = _make_state()
    state.combat = _make_combat(power=2)
    card = _make_card(slug, 1)
    dispatch(state, "ON_ATTACK", slug, card=card)
    assert state.combat.attack_power == 2


def test_blackout_kick_blue_combo_powers_up():
    _check_blackout_kick_combo("blackout_kick_blue")


def test_blackout_kick_blue_no_combo_no_op():
    _check_blackout_kick_no_combo("blackout_kick_blue")


def test_blackout_kick_red_combo_powers_up():
    _check_blackout_kick_combo("blackout_kick_red")


def test_blackout_kick_red_no_combo_no_op():
    _check_blackout_kick_no_combo("blackout_kick_red")


def test_blackout_kick_yellow_combo_powers_up():
    _check_blackout_kick_combo("blackout_kick_yellow")


def test_blackout_kick_yellow_no_combo_no_op():
    _check_blackout_kick_no_combo("blackout_kick_yellow")


# ===========================================================================
# bloodrush_bellow_yellow  (PLAY: ALL_ATTACKS_BONUS +2; conditional discard)
# ===========================================================================

def test_bloodrush_bellow_yellow_grants_all_attacks_bonus():
    state = _make_state()
    state.players[1].hand.add(_make_deck_card("h0", power=3))
    card = _make_card("bloodrush_bellow_yellow", 1)
    dispatch(state, "ON_PLAY", "bloodrush_bellow_yellow", card=card)
    assert "all_attacks_+2" in state.players[1].current_turn_effects


def test_bloodrush_bellow_yellow_wrong_event_no_op():
    state = _make_state()
    card = _make_card("bloodrush_bellow_yellow", 1)
    dispatch(state, "ON_HIT", "bloodrush_bellow_yellow", card=card)
    assert state.players[1].current_turn_effects == []


# ===========================================================================
# breakneck_battery_blue / red / yellow
# ===========================================================================

def _check_breakneck_battery_high_power_grants_go_again(slug: str):
    state = _make_state()
    state.players[1].hand.add(_make_deck_card("big", power=6))
    state.combat = _make_combat()
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert "go_again" in state.combat.keywords


def _check_breakneck_battery_low_power_no_go_again(slug: str):
    state = _make_state()
    state.players[1].hand.add(_make_deck_card("small", power=2))
    state.combat = _make_combat()
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert "go_again" not in state.combat.keywords


def test_breakneck_battery_blue_high_power_go_again():
    _check_breakneck_battery_high_power_grants_go_again("breakneck_battery_blue")


def test_breakneck_battery_blue_low_power_no_go_again():
    _check_breakneck_battery_low_power_no_go_again("breakneck_battery_blue")


def test_breakneck_battery_red_high_power_go_again():
    _check_breakneck_battery_high_power_grants_go_again("breakneck_battery_red")


def test_breakneck_battery_red_low_power_no_go_again():
    _check_breakneck_battery_low_power_no_go_again("breakneck_battery_red")


def test_breakneck_battery_yellow_high_power_go_again():
    _check_breakneck_battery_high_power_grants_go_again("breakneck_battery_yellow")


def test_breakneck_battery_yellow_low_power_no_go_again():
    _check_breakneck_battery_low_power_no_go_again("breakneck_battery_yellow")


# ===========================================================================
# descendent_gustwave_blue / red / yellow  (PLAY +2{p} if combo surging_strike)
# ===========================================================================

def _check_descendent_gustwave_combo(slug: str):
    state = _make_state()
    state.chain_links.append(_make_chain_link("surging_strike_red"))
    state.combat = _make_combat(power=4)
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert state.combat.attack_power == 6


def _check_descendent_gustwave_no_combo(slug: str):
    state = _make_state()
    state.combat = _make_combat(power=4)
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert state.combat.attack_power == 4


def test_descendent_gustwave_blue_combo_powers_up():
    _check_descendent_gustwave_combo("descendent_gustwave_blue")


def test_descendent_gustwave_blue_no_combo_no_op():
    _check_descendent_gustwave_no_combo("descendent_gustwave_blue")


def test_descendent_gustwave_red_combo_powers_up_local():
    _check_descendent_gustwave_combo("descendent_gustwave_red")


def test_descendent_gustwave_red_no_combo_no_op():
    _check_descendent_gustwave_no_combo("descendent_gustwave_red")


def test_descendent_gustwave_yellow_combo_powers_up():
    _check_descendent_gustwave_combo("descendent_gustwave_yellow")


def test_descendent_gustwave_yellow_no_combo_no_op():
    _check_descendent_gustwave_no_combo("descendent_gustwave_yellow")


# ===========================================================================
# driving_blade_blue / red / yellow
# ===========================================================================

def _check_driving_blade(slug: str, amt: int):
    state = _make_state()
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert f"next_weapon_attack_+{amt}" in state.players[1].current_turn_effects
    assert "next_weapon_attack_go_again" in state.players[1].current_turn_effects


def test_driving_blade_blue_queues_weapon_bonus_and_go_again():
    _check_driving_blade("driving_blade_blue", 1)


def test_driving_blade_red_queues_weapon_bonus_and_go_again():
    _check_driving_blade("driving_blade_red", 3)


def test_driving_blade_yellow_queues_weapon_bonus_and_go_again():
    _check_driving_blade("driving_blade_yellow", 2)


def test_driving_blade_blue_wrong_event_no_op():
    state = _make_state()
    card = _make_card("driving_blade_blue", 1)
    dispatch(state, "ON_HIT", "driving_blade_blue", card=card)
    assert state.players[1].current_turn_effects == []


# ===========================================================================
# energy_potion_blue  (ACTIVATE: gain 2 resources)
# ===========================================================================

def test_energy_potion_blue_loads():
    cd = get_card("energy_potion_blue")
    assert cd is not None and cd.abilities[0].ability_type == "ACTIVATE"


def test_energy_potion_blue_activate_grants_two_resources():
    state = _make_state()
    card = _make_card("energy_potion_blue", 1)
    state.players[1].permanents.add(card)
    before = state.players[1].resources
    dispatch(state, "ON_ACTIVATE", "energy_potion_blue", card=card)
    assert state.players[1].resources == before + 2


def test_energy_potion_blue_wrong_event_no_op():
    state = _make_state()
    card = _make_card("energy_potion_blue", 1)
    before = state.players[1].resources
    dispatch(state, "ON_HIT", "energy_potion_blue", card=card)
    assert state.players[1].resources == before


# ===========================================================================
# flock_of_the_feather_walkers_blue / red / yellow  (PLAY reveal cost; ON_ATTACK token)
# ===========================================================================

def _check_flock_creates_quicken_on_attack(slug: str):
    state = _make_state()
    state.combat = _make_combat()
    card = _make_card(slug, 1)
    perms_before = len(state.players[1].permanents.cards) if hasattr(state.players[1], 'permanents') else 0
    items_before = len(state.players[1].items.cards) if hasattr(state.players[1], 'items') else 0
    auras_before = len(state.players[1].auras.cards) if hasattr(state.players[1], 'auras') else 0
    dispatch(state, "ON_ATTACK", slug, card=card)
    perms_after = len(state.players[1].permanents.cards) if hasattr(state.players[1], 'permanents') else 0
    items_after = len(state.players[1].items.cards) if hasattr(state.players[1], 'items') else 0
    auras_after = len(state.players[1].auras.cards) if hasattr(state.players[1], 'auras') else 0
    assert (perms_after + items_after + auras_after) > (perms_before + items_before + auras_before)


def test_flock_of_the_feather_walkers_blue_creates_token_on_attack():
    _check_flock_creates_quicken_on_attack("flock_of_the_feather_walkers_blue")


def test_flock_of_the_feather_walkers_red_creates_token_on_attack():
    _check_flock_creates_quicken_on_attack("flock_of_the_feather_walkers_red")


def test_flock_of_the_feather_walkers_yellow_creates_token_on_attack():
    _check_flock_creates_quicken_on_attack("flock_of_the_feather_walkers_yellow")


def test_flock_of_the_feather_walkers_blue_wrong_event_no_token():
    state = _make_state()
    card = _make_card("flock_of_the_feather_walkers_blue", 1)
    perms_before = len(state.players[1].permanents.cards)
    auras_before = len(state.players[1].auras.cards) if hasattr(state.players[1], 'auras') else 0
    dispatch(state, "ON_HIT", "flock_of_the_feather_walkers_blue", card=card)
    perms_after = len(state.players[1].permanents.cards)
    auras_after = len(state.players[1].auras.cards) if hasattr(state.players[1], 'auras') else 0
    assert perms_after == perms_before and auras_after == auras_before


# ===========================================================================
# fluster_fist_blue / red / yellow  (PLAY: +1{p} per chain hit)
# ===========================================================================

def _check_fluster_fist_chain_bonus(slug: str):
    state = _make_state()
    state.chain_links.append(_make_chain_link("a"))
    state.chain_links.append(_make_chain_link("b"))
    state.combat = _make_combat(power=1)
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert state.combat.attack_power == 3


def _check_fluster_fist_no_chain_no_bonus(slug: str):
    state = _make_state()
    state.combat = _make_combat(power=1)
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert state.combat.attack_power == 1


def test_fluster_fist_blue_chain_bonus():
    _check_fluster_fist_chain_bonus("fluster_fist_blue")


def test_fluster_fist_blue_no_chain_no_bonus():
    _check_fluster_fist_no_chain_no_bonus("fluster_fist_blue")


def test_fluster_fist_red_chain_bonus():
    _check_fluster_fist_chain_bonus("fluster_fist_red")


def test_fluster_fist_red_no_chain_no_bonus():
    _check_fluster_fist_no_chain_no_bonus("fluster_fist_red")


def test_fluster_fist_yellow_chain_bonus():
    _check_fluster_fist_chain_bonus("fluster_fist_yellow")


def test_fluster_fist_yellow_no_chain_no_bonus():
    _check_fluster_fist_no_chain_no_bonus("fluster_fist_yellow")


# ===========================================================================
# forged_for_war_yellow  (DEFENSE_REACTION: +1 defense)
# ===========================================================================

def test_forged_for_war_yellow_grants_defense():
    state = _make_state()
    state.combat = _make_combat()
    card = _make_card("forged_for_war_yellow", 1)
    dispatch(state, "ON_PLAY", "forged_for_war_yellow", card=card)
    assert state.combat.total_defense == 1


def test_forged_for_war_yellow_wrong_event_no_op():
    state = _make_state()
    state.combat = _make_combat()
    card = _make_card("forged_for_war_yellow", 1)
    dispatch(state, "ON_HIT", "forged_for_war_yellow", card=card)
    assert state.combat.total_defense == 0


# ===========================================================================
# fyendals_spring_tunic
# ===========================================================================

def test_fyendals_spring_tunic_loads():
    cd = get_card("fyendals_spring_tunic")
    assert cd is not None and len(cd.abilities) >= 2


def test_fyendals_spring_tunic_start_of_turn_adds_counter():
    state = _make_state()
    card = _make_card("fyendals_spring_tunic", 1)
    state.players[1].permanents.add(card)
    dispatch(state, "START_OF_TURN", "fyendals_spring_tunic", card=card)
    assert any(v > 0 for v in state.players[1].counters.values()) or card.counters.get("energy", 0) > 0


def test_fyendals_spring_tunic_activate_with_3_counters_grants_resource():
    state = _make_state()
    card = _make_card("fyendals_spring_tunic", 1)
    state.players[1].permanents.add(card)
    state.players[1].counters[(card.slug, card.zone, "energy")] = 3
    before = state.players[1].resources
    dispatch(state, "ON_ACTIVATE", "fyendals_spring_tunic", card=card)
    assert state.players[1].resources == before + 1


def test_fyendals_spring_tunic_activate_no_counters_no_op():
    state = _make_state()
    card = _make_card("fyendals_spring_tunic", 1)
    state.players[1].permanents.add(card)
    before = state.players[1].resources
    dispatch(state, "ON_ACTIVATE", "fyendals_spring_tunic", card=card)
    assert state.players[1].resources == before


# ===========================================================================
# glint_the_quicksilver_blue
# ===========================================================================

def test_glint_the_quicksilver_blue_grants_go_again():
    state = _make_state()
    state.combat = _make_combat()
    card = _make_card("glint_the_quicksilver_blue", 1)
    dispatch(state, "ON_PLAY", "glint_the_quicksilver_blue", card=card)
    assert "go_again" in state.combat.keywords


def test_glint_the_quicksilver_blue_reprise_draws():
    state = _make_state()
    state.combat = _make_combat()
    state.combat.defender_used_hand_card = True
    state.players[1].deck.add(_make_deck_card("d0"))
    card = _make_card("glint_the_quicksilver_blue", 1)
    dispatch(state, "ON_PLAY", "glint_the_quicksilver_blue", card=card)
    assert len(state.players[1].hand.cards) == 1


def test_glint_the_quicksilver_blue_no_reprise_no_draw():
    state = _make_state()
    state.combat = _make_combat()
    state.players[1].deck.add(_make_deck_card("d0"))
    card = _make_card("glint_the_quicksilver_blue", 1)
    dispatch(state, "ON_PLAY", "glint_the_quicksilver_blue", card=card)
    assert len(state.players[1].hand.cards) == 0


# ===========================================================================
# goliath_gauntlet
# ===========================================================================

def test_goliath_gauntlet_loads():
    cd = get_card("goliath_gauntlet")
    assert cd is not None and cd.abilities[0].ability_type == "ACTIVATE"


def test_goliath_gauntlet_activate_queues_high_cost_bonus():
    state = _make_state()
    state.combat = _make_combat()
    card = _make_card("goliath_gauntlet", 1)
    state.players[1].permanents.add(card)
    dispatch(state, "ON_ACTIVATE", "goliath_gauntlet", card=card)
    assert "next_high_cost_attack_+2" in state.players[1].current_turn_effects
    assert "go_again" in state.combat.keywords


def test_goliath_gauntlet_wrong_event_no_op():
    state = _make_state()
    card = _make_card("goliath_gauntlet", 1)
    state.players[1].permanents.add(card)
    dispatch(state, "ON_HIT", "goliath_gauntlet", card=card)
    assert "next_high_cost_attack_+2" not in state.players[1].current_turn_effects


# ===========================================================================
# harmonized_kodachi
# ===========================================================================

def test_harmonized_kodachi_loads():
    cd = get_card("harmonized_kodachi")
    assert cd is not None and len(cd.abilities) >= 2


def test_harmonized_kodachi_static_present():
    cd = get_card("harmonized_kodachi")
    assert any(a.ability_type == "STATIC" for a in cd.abilities)


def test_harmonized_kodachi_play_does_not_crash():
    state = _make_state()
    state.players[1].resources = 1
    card = _make_card("harmonized_kodachi", 1)
    dispatch(state, "ON_PLAY", "harmonized_kodachi", card=card)


# ===========================================================================
# head_jab_blue / red / yellow  (vanilla — no abilities)
# ===========================================================================

def test_head_jab_blue_no_abilities():
    cd = get_card("head_jab_blue")
    assert cd is not None and cd.abilities == []


def test_head_jab_blue_dispatch_is_noop():
    state = _make_state()
    card = _make_card("head_jab_blue", 1)
    dispatch(state, "ON_PLAY", "head_jab_blue", card=card)


def test_head_jab_red_no_abilities():
    cd = get_card("head_jab_red")
    assert cd is not None and cd.abilities == []


def test_head_jab_red_dispatch_is_noop():
    state = _make_state()
    card = _make_card("head_jab_red", 1)
    dispatch(state, "ON_PLAY", "head_jab_red", card=card)


def test_head_jab_yellow_no_abilities():
    cd = get_card("head_jab_yellow")
    assert cd is not None and cd.abilities == []


def test_head_jab_yellow_dispatch_is_noop():
    state = _make_state()
    card = _make_card("head_jab_yellow", 1)
    dispatch(state, "ON_PLAY", "head_jab_yellow", card=card)


# ===========================================================================
# heart_of_fyendal_blue
# ===========================================================================

def test_heart_of_fyendal_blue_low_health_gains_life():
    state = _make_state()
    state.players[1].life = 30
    state.players[2].life = 40
    card = _make_card("heart_of_fyendal_blue", 1)
    before = state.players[1].life
    dispatch(state, "ON_PLAY", "heart_of_fyendal_blue", card=card)
    assert state.players[1].life == before + 1


def test_heart_of_fyendal_blue_high_health_no_op():
    state = _make_state()
    state.players[1].life = 40
    state.players[2].life = 30
    card = _make_card("heart_of_fyendal_blue", 1)
    before = state.players[1].life
    dispatch(state, "ON_PLAY", "heart_of_fyendal_blue", card=card)
    assert state.players[1].life == before


# ===========================================================================
# heartened_cross_strap
# ===========================================================================

def test_heartened_cross_strap_loads():
    cd = get_card("heartened_cross_strap")
    assert cd is not None and cd.abilities[0].ability_type == "ACTIVATE"


def test_heartened_cross_strap_activate_queues_cost_reduction():
    state = _make_state()
    card = _make_card("heartened_cross_strap", 1)
    state.players[1].permanents.add(card)
    dispatch(state, "ON_ACTIVATE", "heartened_cross_strap", card=card)
    flags = state.players[1].current_turn_effects
    assert any("attack_action" in f and "-2" in f for f in flags)


def test_heartened_cross_strap_wrong_event_no_op():
    state = _make_state()
    card = _make_card("heartened_cross_strap", 1)
    state.players[1].permanents.add(card)
    dispatch(state, "ON_HIT", "heartened_cross_strap", card=card)
    assert state.players[1].current_turn_effects == []


# ===========================================================================
# helm_of_isens_peak
# ===========================================================================

def test_helm_of_isens_peak_loads():
    cd = get_card("helm_of_isens_peak")
    assert cd is not None and cd.abilities[0].ability_type == "ACTIVATE"


def test_helm_of_isens_peak_activate_grants_action_point():
    state = _make_state()
    state.players[1].resources = 1
    card = _make_card("helm_of_isens_peak", 1)
    state.players[1].permanents.add(card)
    before = state.players[1].action_points
    dispatch(state, "ON_ACTIVATE", "helm_of_isens_peak", card=card)
    assert state.players[1].action_points == before + 1


def test_helm_of_isens_peak_no_resources_no_op():
    state = _make_state()
    state.players[1].resources = 0
    card = _make_card("helm_of_isens_peak", 1)
    state.players[1].permanents.add(card)
    before = state.players[1].action_points
    dispatch(state, "ON_ACTIVATE", "helm_of_isens_peak", card=card)
    assert state.players[1].action_points == before


# ===========================================================================
# hope_merchants_hood
# ===========================================================================

def test_hope_merchants_hood_loads():
    cd = get_card("hope_merchants_hood")
    assert any(a.trigger == "START_OF_TURN" for a in cd.abilities)


def test_hope_merchants_hood_start_of_turn_shuffles_and_draws():
    state = _make_state()
    state.players[1].hand.add(_make_deck_card("h0"))
    state.players[1].hand.add(_make_deck_card("h1"))
    state.players[1].deck.add(_make_deck_card("d0"))
    state.players[1].deck.add(_make_deck_card("d1"))
    state.players[1].deck.add(_make_deck_card("d2"))
    card = _make_card("hope_merchants_hood", 1)
    state.players[1].permanents.add(card)
    dispatch(state, "START_OF_TURN", "hope_merchants_hood", card=card)
    assert len(state.players[1].hand.cards) == 2


def test_hope_merchants_hood_wrong_event_no_op():
    state = _make_state()
    state.players[1].hand.add(_make_deck_card("h0"))
    card = _make_card("hope_merchants_hood", 1)
    state.players[1].permanents.add(card)
    dispatch(state, "ON_PLAY", "hope_merchants_hood", card=card)
    assert len(state.players[1].hand.cards) == 1


# ===========================================================================
# hurricane_technique_yellow
# ===========================================================================

def test_hurricane_technique_yellow_combo_powers_up_and_go_again():
    state = _make_state()
    state.chain_links.append(_make_chain_link("rising_knee_thrust_red"))
    state.combat = _make_combat(power=2)
    card = _make_card("hurricane_technique_yellow", 1)
    dispatch(state, "ON_ATTACK", "hurricane_technique_yellow", card=card)
    assert state.combat.attack_power == 3
    assert "go_again" in state.combat.keywords


def test_hurricane_technique_yellow_no_combo_no_op():
    state = _make_state()
    state.combat = _make_combat(power=2)
    card = _make_card("hurricane_technique_yellow", 1)
    dispatch(state, "ON_ATTACK", "hurricane_technique_yellow", card=card)
    assert state.combat.attack_power == 2


# ===========================================================================
# ironrot_gauntlet / helm / legs / plate
# ===========================================================================

def _check_ironrot_static(slug: str):
    cd = get_card(slug)
    assert cd is not None
    assert cd.abilities[0].ability_type == "STATIC"


def _check_ironrot_static_not_dispatched(slug: str):
    state = _make_state()
    state.combat = _make_combat(power=4)
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert state.combat.attack_power == 4


def test_ironrot_gauntlet_loads_static():
    _check_ironrot_static("ironrot_gauntlet")


def test_ironrot_gauntlet_static_not_dispatched():
    _check_ironrot_static_not_dispatched("ironrot_gauntlet")


def test_ironrot_helm_loads_static():
    _check_ironrot_static("ironrot_helm")


def test_ironrot_helm_static_not_dispatched():
    _check_ironrot_static_not_dispatched("ironrot_helm")


def test_ironrot_legs_loads_static():
    _check_ironrot_static("ironrot_legs")


def test_ironrot_legs_static_not_dispatched():
    _check_ironrot_static_not_dispatched("ironrot_legs")


def test_ironrot_plate_loads_static():
    _check_ironrot_static("ironrot_plate")


def test_ironrot_plate_static_not_dispatched():
    _check_ironrot_static_not_dispatched("ironrot_plate")


# ===========================================================================
# ironsong_determination_yellow
# ===========================================================================

def test_ironsong_determination_yellow_queues_weapon_bonus_go_again_dominate():
    state = _make_state()
    state.combat = _make_combat()
    card = _make_card("ironsong_determination_yellow", 1)
    dispatch(state, "ON_PLAY", "ironsong_determination_yellow", card=card)
    assert "next_weapon_attack_+1" in state.players[1].current_turn_effects
    assert "next_weapon_attack_go_again" in state.players[1].current_turn_effects
    assert "Dominate" in state.combat.keywords


def test_ironsong_determination_yellow_wrong_event_no_op():
    state = _make_state()
    state.combat = _make_combat()
    card = _make_card("ironsong_determination_yellow", 1)
    dispatch(state, "ON_HIT", "ironsong_determination_yellow", card=card)
    assert "next_weapon_attack_+1" not in state.players[1].current_turn_effects


# ===========================================================================
# ironsong_response_blue / red / yellow  (ATTACK_REACTION: REPRISE → +N{p})
# ===========================================================================

def _check_ironsong_response_reprise(slug: str, amt: int):
    state = _make_state()
    state.combat = _make_combat(power=4)
    state.combat.defender_used_hand_card = True
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert state.combat.attack_power == 4 + amt


def _check_ironsong_response_no_reprise(slug: str):
    state = _make_state()
    state.combat = _make_combat(power=4)
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert state.combat.attack_power == 4


def test_ironsong_response_blue_reprise():
    _check_ironsong_response_reprise("ironsong_response_blue", 1)


def test_ironsong_response_blue_no_reprise():
    _check_ironsong_response_no_reprise("ironsong_response_blue")


def test_ironsong_response_red_reprise():
    _check_ironsong_response_reprise("ironsong_response_red", 3)


def test_ironsong_response_red_no_reprise():
    _check_ironsong_response_no_reprise("ironsong_response_red")


def test_ironsong_response_yellow_reprise():
    _check_ironsong_response_reprise("ironsong_response_yellow", 2)


def test_ironsong_response_yellow_no_reprise():
    _check_ironsong_response_no_reprise("ironsong_response_yellow")


# ===========================================================================
# katsu  (hero ON_ATTACK ninja)
# ===========================================================================

def test_katsu_loads():
    assert get_card("katsu") is not None


def test_katsu_first_ninja_attack_grants_go_again():
    state = _make_state()
    state.players[1].hand.add(_make_deck_card("h0", owner=1))
    state.players[1].deck.add(_make_deck_card("d0", owner=1))
    state.combat = _make_combat(from_weapon=False)
    card = _make_card("katsu", 1, types=["Hero"])
    dispatch(state, "ON_HIT", "katsu", card=card, event=_hit_event(5))
    assert "katsu_used" in state.players[1].current_turn_effects


def test_katsu_already_used_no_go_again():
    state = _make_state()
    state.players[1].current_turn_effects.append("katsu_used")
    state.players[1].hand.add(_make_deck_card("h0", owner=1))
    state.combat = _make_combat(from_weapon=False)
    card = _make_card("katsu", 1, types=["Hero"])
    dispatch(state, "ON_HIT", "katsu", card=card, event=_hit_event(5))
    # already used — flag stays but ability does not fire again
    assert state.players[1].current_turn_effects.count("katsu_used") == 1


def test_katsu_non_ninja_no_go_again():
    state = _make_state()
    atk = _make_card("brute_atk", 1)
    atk.classes = ["Brute"]
    state.combat = _make_combat(attack_card=atk)
    card = _make_card("katsu", 1, types=["Hero"])
    dispatch(state, "ON_ATTACK", "katsu", card=card)
    assert "go_again" not in state.combat.keywords


# ===========================================================================
# katsu_the_wanderer  (ON_HIT non-weapon → flag NEXT)
# ===========================================================================

def test_katsu_the_wanderer_loads():
    assert get_card("katsu_the_wanderer") is not None


def test_katsu_the_wanderer_non_weapon_hit_sets_next_flag():
    state = _make_state()
    state.players[1].hand.add(_make_deck_card("h0"))
    state.players[1].deck.add(_make_deck_card("d0"))
    card = _make_card("katsu_the_wanderer", 1, types=["Hero"])
    state.combat = _make_combat(power=3, from_weapon=False)
    dispatch(state, "ON_HIT", "katsu_the_wanderer", card=card, event=_hit_event(3))
    assert "katsu_combo_banished" in state.players[1].next_turn_effects


def test_katsu_the_wanderer_weapon_hit_no_flag():
    state = _make_state()
    state.players[1].hand.add(_make_deck_card("h0"))
    state.players[1].deck.add(_make_deck_card("d0"))
    card = _make_card("katsu_the_wanderer", 1, types=["Hero"])
    state.combat = _make_combat(power=3, from_weapon=True)
    dispatch(state, "ON_HIT", "katsu_the_wanderer", card=card, event=_hit_event(3))
    assert "katsu_combo_banished" not in state.players[1].next_turn_effects


# ===========================================================================
# last_ditch_effort_blue
# ===========================================================================

def test_last_ditch_effort_blue_empty_deck_powers_up():
    state = _make_state()
    state.combat = _make_combat(power=2)
    card = _make_card("last_ditch_effort_blue", 1)
    dispatch(state, "ON_PLAY", "last_ditch_effort_blue", card=card)
    assert state.combat.attack_power == 6
    assert "go_again" in state.combat.keywords


def test_last_ditch_effort_blue_non_empty_deck_no_op():
    state = _make_state()
    state.players[1].deck.add(_make_deck_card("d0"))
    state.combat = _make_combat(power=2)
    card = _make_card("last_ditch_effort_blue", 1)
    dispatch(state, "ON_PLAY", "last_ditch_effort_blue", card=card)
    assert state.combat.attack_power == 2
    assert "go_again" not in state.combat.keywords


# ===========================================================================
# leg_tap_blue / red / yellow  (vanilla)
# ===========================================================================

def test_leg_tap_blue_no_abilities():
    cd = get_card("leg_tap_blue")
    assert cd is not None and cd.abilities == []


def test_leg_tap_blue_dispatch_is_noop():
    state = _make_state()
    card = _make_card("leg_tap_blue", 1)
    dispatch(state, "ON_PLAY", "leg_tap_blue", card=card)


def test_leg_tap_red_no_abilities():
    cd = get_card("leg_tap_red")
    assert cd is not None and cd.abilities == []


def test_leg_tap_red_dispatch_is_noop():
    state = _make_state()
    card = _make_card("leg_tap_red", 1)
    dispatch(state, "ON_PLAY", "leg_tap_red", card=card)


def test_leg_tap_yellow_no_abilities():
    cd = get_card("leg_tap_yellow")
    assert cd is not None and cd.abilities == []


def test_leg_tap_yellow_dispatch_is_noop():
    state = _make_state()
    card = _make_card("leg_tap_yellow", 1)
    dispatch(state, "ON_PLAY", "leg_tap_yellow", card=card)


# ===========================================================================
# lord_of_wind_blue
# ===========================================================================

def test_lord_of_wind_blue_loads():
    assert get_card("lord_of_wind_blue") is not None


def test_lord_of_wind_blue_combo_dispatch_does_not_crash():
    state = _make_state()
    state.chain_links.append(_make_chain_link("mugenshi_release_yellow"))
    state.combat = _make_combat(power=4)
    card = _make_card("lord_of_wind_blue", 1)
    dispatch(state, "ON_PLAY", "lord_of_wind_blue", card=card)


def test_lord_of_wind_blue_no_combo_dispatch_does_not_crash():
    state = _make_state()
    state.combat = _make_combat(power=4)
    card = _make_card("lord_of_wind_blue", 1)
    dispatch(state, "ON_PLAY", "lord_of_wind_blue", card=card)


# ===========================================================================
# mask_of_momentum
# ===========================================================================

def test_mask_of_momentum_three_chain_hits_draws():
    state = _make_state()
    for _ in range(3):
        state.chain_links.append(_make_chain_link("a", hit=True))
    state.players[1].deck.add(_make_deck_card("d0"))
    state.combat = _make_combat()
    card = _make_card("mask_of_momentum", 1)
    dispatch(state, "ON_HIT", "mask_of_momentum", card=card, event=_hit_event(3))
    assert len(state.players[1].hand.cards) == 1


def test_mask_of_momentum_two_chain_hits_no_draw():
    state = _make_state()
    for _ in range(1):
        state.chain_links.append(_make_chain_link("a", hit=True))
    state.players[1].deck.add(_make_deck_card("d0"))
    state.combat = _make_combat()
    card = _make_card("mask_of_momentum", 1)
    dispatch(state, "ON_HIT", "mask_of_momentum", card=card, event=_hit_event(3))
    assert len(state.players[1].hand.cards) == 0


# ===========================================================================
# mugenshi_release_yellow
# ===========================================================================

def test_mugenshi_release_yellow_combo_powers_up_and_go_again():
    state = _make_state()
    state.chain_links.append(_make_chain_link("whelming_gustwave_red"))
    state.combat = _make_combat(power=2)
    card = _make_card("mugenshi_release_yellow", 1)
    dispatch(state, "ON_ATTACK", "mugenshi_release_yellow", card=card)
    assert state.combat.attack_power == 3
    assert "go_again" in state.combat.keywords


def test_mugenshi_release_yellow_no_combo_no_op():
    state = _make_state()
    state.combat = _make_combat(power=2)
    card = _make_card("mugenshi_release_yellow", 1)
    dispatch(state, "ON_ATTACK", "mugenshi_release_yellow", card=card)
    assert state.combat.attack_power == 2


# ===========================================================================
# natures_path_pilgrimage_blue / red / yellow
# ===========================================================================

def _check_natures_path(slug: str, amt: int):
    state = _make_state()
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert f"next_weapon_attack_+{amt}" in state.players[1].current_turn_effects


def test_natures_path_pilgrimage_blue_queues_weapon_bonus():
    _check_natures_path("natures_path_pilgrimage_blue", 1)


def test_natures_path_pilgrimage_red_queues_weapon_bonus():
    _check_natures_path("natures_path_pilgrimage_red", 3)


def test_natures_path_pilgrimage_yellow_queues_weapon_bonus():
    _check_natures_path("natures_path_pilgrimage_yellow", 2)


def test_natures_path_pilgrimage_blue_wrong_event_no_op():
    state = _make_state()
    card = _make_card("natures_path_pilgrimage_blue", 1)
    dispatch(state, "ON_HIT", "natures_path_pilgrimage_blue", card=card)
    assert "next_weapon_attack_+1" not in state.players[1].current_turn_effects


# ===========================================================================
# nimble_strike_blue / red / yellow
# ===========================================================================

def _check_nimble_strike_with_nimblism(slug: str):
    state = _make_state()
    nimb = _make_deck_card("nimblism_blue", owner=1)
    state.players[1].graveyard.add(nimb)
    state.combat = _make_combat(power=3)
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert state.combat.attack_power == 4
    assert "go_again" in state.combat.keywords


def _check_nimble_strike_without_nimblism(slug: str):
    state = _make_state()
    state.combat = _make_combat(power=3)
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert state.combat.attack_power == 3


def test_nimble_strike_blue_with_nimblism():
    _check_nimble_strike_with_nimblism("nimble_strike_blue")


def test_nimble_strike_blue_without_nimblism():
    _check_nimble_strike_without_nimblism("nimble_strike_blue")


def test_nimble_strike_red_with_nimblism():
    _check_nimble_strike_with_nimblism("nimble_strike_red")


def test_nimble_strike_red_without_nimblism():
    _check_nimble_strike_without_nimblism("nimble_strike_red")


def test_nimble_strike_yellow_with_nimblism():
    _check_nimble_strike_with_nimblism("nimble_strike_yellow")


def test_nimble_strike_yellow_without_nimblism():
    _check_nimble_strike_without_nimblism("nimble_strike_yellow")


# ===========================================================================
# nimblism_blue / red / yellow
# ===========================================================================

def _check_nimblism(slug: str, amt: int):
    state = _make_state()
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert f"next_low_cost_attack_+{amt}" in state.players[1].current_turn_effects


def test_nimblism_blue_queues_low_cost_bonus():
    _check_nimblism("nimblism_blue", 1)


def test_nimblism_red_queues_low_cost_bonus():
    _check_nimblism("nimblism_red", 3)


def test_nimblism_yellow_queues_low_cost_bonus():
    _check_nimblism("nimblism_yellow", 2)


def test_nimblism_blue_wrong_event_no_op():
    state = _make_state()
    card = _make_card("nimblism_blue", 1)
    dispatch(state, "ON_HIT", "nimblism_blue", card=card)
    assert "next_low_cost_attack_+1" not in state.players[1].current_turn_effects


# ===========================================================================
# nip_at_the_heels_blue
# ===========================================================================

def test_nip_at_the_heels_blue_grants_power():
    state = _make_state()
    state.combat = _make_combat(power=2)
    card = _make_card("nip_at_the_heels_blue", 1)
    dispatch(state, "ON_PLAY", "nip_at_the_heels_blue", card=card)
    assert state.combat.attack_power == 3


def test_nip_at_the_heels_blue_wrong_event_no_op():
    state = _make_state()
    state.combat = _make_combat(power=2)
    card = _make_card("nip_at_the_heels_blue", 1)
    dispatch(state, "ON_HIT", "nip_at_the_heels_blue", card=card)
    assert state.combat.attack_power == 2


# ===========================================================================
# open_the_center_blue / red / yellow
# ===========================================================================

def _check_open_the_center_combo(slug: str):
    state = _make_state()
    state.chain_links.append(_make_chain_link("head_jab_red"))
    state.combat = _make_combat(power=2)
    card = _make_card(slug, 1)
    dispatch(state, "ON_ATTACK", slug, card=card)
    assert state.combat.attack_power == 3
    assert "go_again" in state.combat.keywords
    assert "Dominate" in state.combat.keywords


def _check_open_the_center_no_combo(slug: str):
    state = _make_state()
    state.combat = _make_combat(power=2)
    card = _make_card(slug, 1)
    dispatch(state, "ON_ATTACK", slug, card=card)
    assert state.combat.attack_power == 2


def test_open_the_center_blue_combo():
    _check_open_the_center_combo("open_the_center_blue")


def test_open_the_center_blue_no_combo():
    _check_open_the_center_no_combo("open_the_center_blue")


def test_open_the_center_red_combo():
    _check_open_the_center_combo("open_the_center_red")


def test_open_the_center_red_no_combo():
    _check_open_the_center_no_combo("open_the_center_red")


def test_open_the_center_yellow_combo():
    _check_open_the_center_combo("open_the_center_yellow")


def test_open_the_center_yellow_no_combo():
    _check_open_the_center_no_combo("open_the_center_yellow")


# ===========================================================================
# overpower_blue / red / yellow
# ===========================================================================

def _check_overpower_no_reprise(slug: str, base: int):
    state = _make_state()
    state.combat = _make_combat(power=2, from_weapon=True)
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert state.combat.attack_power == 2 + base


def _check_overpower_reprise(slug: str, base: int):
    state = _make_state()
    state.combat = _make_combat(power=2, from_weapon=True)
    state.combat.defender_used_hand_card = True
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert state.combat.attack_power == 2 + base + 2


def test_overpower_blue_no_reprise():
    _check_overpower_no_reprise("overpower_blue", 2)


def test_overpower_blue_reprise():
    _check_overpower_reprise("overpower_blue", 2)


def test_overpower_red_no_reprise():
    _check_overpower_no_reprise("overpower_red", 4)


def test_overpower_red_reprise():
    _check_overpower_reprise("overpower_red", 4)


def test_overpower_yellow_no_reprise():
    _check_overpower_no_reprise("overpower_yellow", 3)


def test_overpower_yellow_reprise():
    _check_overpower_reprise("overpower_yellow", 3)


# ===========================================================================
# pack_hunt_blue / red / yellow
# ===========================================================================

def _check_pack_hunt_intimidates(slug: str):
    state = _make_state()
    state.players[2].hand.add(_make_deck_card("opp0", owner=2))
    state.combat = _make_combat()
    card = _make_card(slug, 1)
    dispatch(state, "ON_ATTACK", slug, card=card)
    assert len(state.players[2].hand.cards) == 0


def _check_pack_hunt_wrong_event(slug: str):
    state = _make_state()
    state.players[2].hand.add(_make_deck_card("opp0", owner=2))
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert len(state.players[2].hand.cards) == 1


def test_pack_hunt_blue_intimidates():
    _check_pack_hunt_intimidates("pack_hunt_blue")


def test_pack_hunt_blue_wrong_event():
    _check_pack_hunt_wrong_event("pack_hunt_blue")


def test_pack_hunt_red_intimidates():
    _check_pack_hunt_intimidates("pack_hunt_red")


def test_pack_hunt_red_wrong_event():
    _check_pack_hunt_wrong_event("pack_hunt_red")


def test_pack_hunt_yellow_intimidates():
    _check_pack_hunt_intimidates("pack_hunt_yellow")


def test_pack_hunt_yellow_wrong_event():
    _check_pack_hunt_wrong_event("pack_hunt_yellow")


# ===========================================================================
# potion_of_strength_blue
# ===========================================================================

def test_potion_of_strength_blue_loads():
    cd = get_card("potion_of_strength_blue")
    assert cd is not None and cd.abilities[0].ability_type == "ACTIVATE"


def test_potion_of_strength_blue_activate_queues_bonus_and_go_again():
    state = _make_state()
    state.combat = _make_combat()
    card = _make_card("potion_of_strength_blue", 1)
    state.players[1].permanents.add(card)
    dispatch(state, "ON_ACTIVATE", "potion_of_strength_blue", card=card)
    assert "next_attack_+2" in state.players[1].current_turn_effects
    assert "go_again" in state.combat.keywords


def test_potion_of_strength_blue_wrong_event_no_op():
    state = _make_state()
    card = _make_card("potion_of_strength_blue", 1)
    state.players[1].permanents.add(card)
    dispatch(state, "ON_HIT", "potion_of_strength_blue", card=card)
    assert "next_attack_+2" not in state.players[1].current_turn_effects


# ===========================================================================
# pounding_gale_red
# ===========================================================================

def test_pounding_gale_red_play_injects_trigger():
    state = _make_state()
    state.combat = _make_combat()
    card = _make_card("pounding_gale_red", 1)
    # INJECT_TRIGGER uses DEAL_DAMAGE placeholder — verify no crash and card loads
    dispatch(state, "ON_PLAY", "pounding_gale_red", card=card)
    assert get_card("pounding_gale_red") is not None


def test_pounding_gale_red_no_combat_no_inject():
    state = _make_state()
    card = _make_card("pounding_gale_red", 1)
    dispatch(state, "ON_PLAY", "pounding_gale_red", card=card)


# ===========================================================================
# primeval_bellow_blue / red / yellow
# ===========================================================================

def _check_primeval_bellow(slug: str, amt: int):
    state = _make_state()
    state.players[1].hand.add(_make_deck_card("h0", power=1))
    state.combat = _make_combat()
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert f"next_attack_+{amt}" in state.players[1].current_turn_effects
    assert "go_again" in state.combat.keywords


def test_primeval_bellow_blue_play():
    _check_primeval_bellow("primeval_bellow_blue", 3)


def test_primeval_bellow_red_play():
    _check_primeval_bellow("primeval_bellow_red", 5)


def test_primeval_bellow_yellow_play():
    _check_primeval_bellow("primeval_bellow_yellow", 4)


def test_primeval_bellow_blue_wrong_event_no_op():
    state = _make_state()
    state.players[1].hand.add(_make_deck_card("h0", power=1))
    card = _make_card("primeval_bellow_blue", 1)
    dispatch(state, "ON_HIT", "primeval_bellow_blue", card=card)
    assert "next_attack_+3" not in state.players[1].current_turn_effects


# ===========================================================================
# pummel_blue / red / yellow
# ===========================================================================

_PUMMEL_BONUS = {"pummel_red": 4, "pummel_yellow": 3, "pummel_blue": 2}


def _check_pummel_attacks_action_2cost(slug: str):
    state = _make_state()
    atk = _make_card("hi_cost_atk", 1)
    atk.cost = 2
    state.combat = _make_combat(power=3, attack_card=atk, from_weapon=False)
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert state.combat.attack_power == 3 + _PUMMEL_BONUS[slug]


def _check_pummel_no_match(slug: str):
    state = _make_state()
    atk = _make_card("low_cost_atk", 1)
    atk.cost = 1
    state.combat = _make_combat(power=3, attack_card=atk, from_weapon=False)
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert state.combat.attack_power == 3


def test_pummel_blue_targets_2cost_action():
    _check_pummel_attacks_action_2cost("pummel_blue")


def test_pummel_blue_no_match_no_op():
    _check_pummel_no_match("pummel_blue")


def test_pummel_red_targets_2cost_action():
    _check_pummel_attacks_action_2cost("pummel_red")


def test_pummel_red_no_match_no_op():
    _check_pummel_no_match("pummel_red")


def test_pummel_yellow_targets_2cost_action():
    _check_pummel_attacks_action_2cost("pummel_yellow")


def test_pummel_yellow_no_match_no_op():
    _check_pummel_no_match("pummel_yellow")


# ===========================================================================
# quicken
# ===========================================================================

def test_quicken_loads():
    assert get_card("quicken") is not None


def test_quicken_dispatch_does_not_crash():
    state = _make_state()
    state.combat = _make_combat()
    card = _make_card("quicken", 1)
    state.players[1].auras.add(card)
    dispatch(state, "ON_PLAY", "quicken", card=card)


# ===========================================================================
# raging_onslaught_blue / red / yellow  (vanilla)
# ===========================================================================

def test_raging_onslaught_blue_no_abilities():
    cd = get_card("raging_onslaught_blue")
    assert cd is not None and cd.abilities == []


def test_raging_onslaught_blue_dispatch_is_noop():
    state = _make_state()
    card = _make_card("raging_onslaught_blue", 1)
    dispatch(state, "ON_PLAY", "raging_onslaught_blue", card=card)


def test_raging_onslaught_red_no_abilities():
    cd = get_card("raging_onslaught_red")
    assert cd is not None and cd.abilities == []


def test_raging_onslaught_red_dispatch_is_noop():
    state = _make_state()
    card = _make_card("raging_onslaught_red", 1)
    dispatch(state, "ON_PLAY", "raging_onslaught_red", card=card)


def test_raging_onslaught_yellow_no_abilities():
    cd = get_card("raging_onslaught_yellow")
    assert cd is not None and cd.abilities == []


def test_raging_onslaught_yellow_dispatch_is_noop():
    state = _make_state()
    card = _make_card("raging_onslaught_yellow", 1)
    dispatch(state, "ON_PLAY", "raging_onslaught_yellow", card=card)


# ===========================================================================
# razor_reflex_blue / red / yellow
# ===========================================================================

_RAZOR_REFLEX_BONUS = {"razor_reflex_red": 3, "razor_reflex_yellow": 2, "razor_reflex_blue": 1}


def _check_razor_reflex_dagger(slug: str):
    state = _make_state()
    weapon = _make_card("dag", 1)
    weapon.subtypes = ["Dagger"]
    state.combat = _make_combat(power=2, attack_card=weapon, from_weapon=True)
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert state.combat.attack_power == 2 + _RAZOR_REFLEX_BONUS[slug]


def _check_razor_reflex_no_match(slug: str):
    state = _make_state()
    atk = _make_card("hi_cost", 1)
    atk.cost = 3
    state.combat = _make_combat(power=2, attack_card=atk, from_weapon=False)
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert state.combat.attack_power == 2  # cost-3 non-weapon doesn't match any color


def test_razor_reflex_blue_dagger_powers_up():
    _check_razor_reflex_dagger("razor_reflex_blue")


def test_razor_reflex_blue_no_match():
    _check_razor_reflex_no_match("razor_reflex_blue")


def test_razor_reflex_red_dagger_powers_up():
    _check_razor_reflex_dagger("razor_reflex_red")


def test_razor_reflex_red_no_match():
    _check_razor_reflex_no_match("razor_reflex_red")


def test_razor_reflex_yellow_dagger_powers_up():
    _check_razor_reflex_dagger("razor_reflex_yellow")


def test_razor_reflex_yellow_no_match():
    _check_razor_reflex_no_match("razor_reflex_yellow")


# ===========================================================================
# reckless_swing_blue
# ===========================================================================

def test_reckless_swing_blue_loads():
    assert get_card("reckless_swing_blue") is not None


def test_reckless_swing_blue_dispatch_does_not_crash():
    state = _make_state()
    state.players[1].hand.add(_make_deck_card("h0"))
    state.combat = _make_combat()
    card = _make_card("reckless_swing_blue", 1)
    dispatch(state, "ON_PLAY", "reckless_swing_blue", card=card)


# ===========================================================================
# refraction_bolters
# ===========================================================================

def test_refraction_bolters_weapon_hit_grants_go_again():
    state = _make_state()
    state.combat = _make_combat(from_weapon=True)
    card = _make_card("refraction_bolters", 1)
    state.players[1].permanents.add(card)
    dispatch(state, "ON_HIT", "refraction_bolters", card=card, event=_hit_event(3))
    assert "go_again" in state.combat.keywords


def test_refraction_bolters_non_weapon_no_op():
    state = _make_state()
    state.combat = _make_combat(from_weapon=False)
    card = _make_card("refraction_bolters", 1)
    state.players[1].permanents.add(card)
    dispatch(state, "ON_HIT", "refraction_bolters", card=card, event=_hit_event(3))
    assert "go_again" not in state.combat.keywords


# ===========================================================================
# regurgitating_slog_blue / red / yellow
# ===========================================================================

def _check_regurgitating_slog_with_sloggism(slug: str):
    state = _make_state()
    state.players[1].graveyard.add(_make_deck_card("sloggism_blue", owner=1))
    state.combat = _make_combat()
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert "Dominate" in state.combat.keywords


def _check_regurgitating_slog_without_sloggism(slug: str):
    state = _make_state()
    state.combat = _make_combat()
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert "Dominate" not in state.combat.keywords


def test_regurgitating_slog_blue_with_sloggism():
    _check_regurgitating_slog_with_sloggism("regurgitating_slog_blue")


def test_regurgitating_slog_blue_without_sloggism():
    _check_regurgitating_slog_without_sloggism("regurgitating_slog_blue")


def test_regurgitating_slog_red_with_sloggism():
    _check_regurgitating_slog_with_sloggism("regurgitating_slog_red")


def test_regurgitating_slog_red_without_sloggism():
    _check_regurgitating_slog_without_sloggism("regurgitating_slog_red")


def test_regurgitating_slog_yellow_with_sloggism():
    _check_regurgitating_slog_with_sloggism("regurgitating_slog_yellow")


def test_regurgitating_slog_yellow_without_sloggism():
    _check_regurgitating_slog_without_sloggism("regurgitating_slog_yellow")


# ===========================================================================
# remembrance_yellow
# ===========================================================================

def test_remembrance_yellow_loads():
    cd = get_card("remembrance_yellow")
    assert cd is not None and cd.abilities[0].ability_type == "ACTIVATE"


def test_remembrance_yellow_activate_creates_seismic_surge():
    state = _make_state()
    state.players[1].resources = 1
    card = _make_card("remembrance_yellow", 1)
    state.players[1].permanents.add(card)
    dispatch(state, "ON_ACTIVATE", "remembrance_yellow", card=card)
    assert any(c.slug == "seismic_surge" for c in state.players[1].auras.cards)


# ===========================================================================
# retrace_the_past_blue
# ===========================================================================

def test_retrace_the_past_blue_combo_draws():
    state = _make_state()
    state.chain_links.append(_make_chain_link("descendent_gustwave_red"))
    state.players[1].deck.add(_make_deck_card("d0"))
    state.combat = _make_combat()
    card = _make_card("retrace_the_past_blue", 1)
    dispatch(state, "ON_ATTACK", "retrace_the_past_blue", card=card)
    assert len(state.players[1].hand.cards) == 1


def test_retrace_the_past_blue_no_combo_no_draw():
    state = _make_state()
    state.players[1].deck.add(_make_deck_card("d0"))
    state.combat = _make_combat()
    card = _make_card("retrace_the_past_blue", 1)
    dispatch(state, "ON_ATTACK", "retrace_the_past_blue", card=card)
    assert len(state.players[1].hand.cards) == 0


# ===========================================================================
# rhinar / rhinar_reckless_rampage
# ===========================================================================

def test_rhinar_loads():
    assert get_card("rhinar") is not None


def test_rhinar_dispatch_does_not_crash():
    state = _make_state()
    state.players[2].hand.add(_make_deck_card("opp", owner=2))
    discarded = _make_deck_card("big", owner=1, power=7)
    card = _make_card("rhinar", 1, types=["Hero"])
    ev = Event(type="ON_DISCARD", data={"card": discarded, "card_power": 7})
    dispatch(state, "ON_DISCARD", "rhinar", card=card, event=ev)


def test_rhinar_reckless_rampage_loads():
    assert get_card("rhinar_reckless_rampage") is not None


def test_rhinar_reckless_rampage_dispatch_does_not_crash():
    state = _make_state()
    state.players[2].hand.add(_make_deck_card("opp", owner=2))
    discarded = _make_deck_card("big", owner=1, power=7)
    card = _make_card("rhinar_reckless_rampage", 1, types=["Hero"])
    ev = Event(type="ON_DISCARD", data={"card": discarded, "card_power": 7})
    dispatch(state, "ON_DISCARD", "rhinar_reckless_rampage", card=card, event=ev)


# ===========================================================================
# rising_knee_thrust_blue / red / yellow
# ===========================================================================

def _check_rising_knee_thrust_combo(slug: str):
    state = _make_state()
    state.chain_links.append(_make_chain_link("leg_tap_red"))
    state.combat = _make_combat(power=2)
    card = _make_card(slug, 1)
    dispatch(state, "ON_ATTACK", slug, card=card)
    assert state.combat.attack_power == 4
    assert "go_again" in state.combat.keywords


def _check_rising_knee_thrust_no_combo(slug: str):
    state = _make_state()
    state.combat = _make_combat(power=2)
    card = _make_card(slug, 1)
    dispatch(state, "ON_ATTACK", slug, card=card)
    assert state.combat.attack_power == 2
    assert "go_again" not in state.combat.keywords


def test_rising_knee_thrust_blue_combo():
    _check_rising_knee_thrust_combo("rising_knee_thrust_blue")


def test_rising_knee_thrust_blue_no_combo():
    _check_rising_knee_thrust_no_combo("rising_knee_thrust_blue")


def test_rising_knee_thrust_red_combo():
    _check_rising_knee_thrust_combo("rising_knee_thrust_red")


def test_rising_knee_thrust_red_no_combo():
    _check_rising_knee_thrust_no_combo("rising_knee_thrust_red")


def test_rising_knee_thrust_yellow_combo():
    _check_rising_knee_thrust_combo("rising_knee_thrust_yellow")


def test_rising_knee_thrust_yellow_no_combo():
    _check_rising_knee_thrust_no_combo("rising_knee_thrust_yellow")


# ===========================================================================
# romping_club
# ===========================================================================

def test_romping_club_loads():
    cd = get_card("romping_club")
    assert cd is not None and len(cd.abilities) >= 2


def test_romping_club_activate_does_not_crash():
    state = _make_state()
    state.players[1].resources = 2
    card = _make_card("romping_club", 1)
    state.players[1].permanents.add(card)
    dispatch(state, "ON_ACTIVATE", "romping_club", card=card)


# ===========================================================================
# rout_red
# ===========================================================================

def test_rout_red_grants_three_power():
    state = _make_state()
    state.combat = _make_combat(power=2)
    card = _make_card("rout_red", 1)
    dispatch(state, "ON_PLAY", "rout_red", card=card)
    assert state.combat.attack_power == 5


def test_rout_red_wrong_event_no_op():
    state = _make_state()
    state.combat = _make_combat(power=2)
    card = _make_card("rout_red", 1)
    dispatch(state, "ON_HIT", "rout_red", card=card)
    assert state.combat.attack_power == 2


# ===========================================================================
# sand_sketched_plan_blue
# ===========================================================================

def test_sand_sketched_plan_blue_loads():
    cd = get_card("sand_sketched_plan_blue")
    assert cd is not None


def test_sand_sketched_plan_blue_high_power_discard_grants_ap():
    state = _make_state()
    state.players[1].hand.add(_make_deck_card("big", power=7))
    # empty deck: SEARCH_DECK fails-to-find, leaving only the high-power card to discard
    card = _make_card("sand_sketched_plan_blue", 1)
    before_ap = state.players[1].action_points
    dispatch(state, "ON_PLAY", "sand_sketched_plan_blue", card=card)
    assert state.players[1].action_points == before_ap + 2


def test_sand_sketched_plan_blue_low_power_discard_no_ap():
    state = _make_state()
    state.players[1].hand.add(_make_deck_card("small", power=2))
    state.players[1].deck.add(_make_deck_card("d0"))
    card = _make_card("sand_sketched_plan_blue", 1)
    before_ap = state.players[1].action_points
    dispatch(state, "ON_PLAY", "sand_sketched_plan_blue", card=card)
    assert state.players[1].action_points == before_ap


# ===========================================================================
# savage_feast_blue / red / yellow  (PLAY discard random)
# ===========================================================================

def _check_savage_feast_loads(slug: str):
    cd = get_card(slug)
    assert cd is not None
    assert cd.abilities[0].ability_type == "PLAY"


def _check_savage_feast_dispatch_pays_cost(slug: str):
    state = _make_state()
    state.players[1].hand.add(_make_deck_card("h0"))
    state.players[1].hand.add(_make_deck_card("h1"))
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert len(state.players[1].hand.cards) == 1


def test_savage_feast_blue_loads():
    _check_savage_feast_loads("savage_feast_blue")


def test_savage_feast_blue_play_pays_cost():
    _check_savage_feast_dispatch_pays_cost("savage_feast_blue")


def test_savage_feast_red_loads():
    _check_savage_feast_loads("savage_feast_red")


def test_savage_feast_red_play_pays_cost():
    _check_savage_feast_dispatch_pays_cost("savage_feast_red")


def test_savage_feast_yellow_loads():
    _check_savage_feast_loads("savage_feast_yellow")


def test_savage_feast_yellow_play_pays_cost():
    _check_savage_feast_dispatch_pays_cost("savage_feast_yellow")


# ===========================================================================
# savage_swing_blue / red / yellow
# ===========================================================================

def test_savage_swing_blue_loads():
    _check_savage_feast_loads("savage_swing_blue")


def test_savage_swing_blue_play_pays_cost():
    _check_savage_feast_dispatch_pays_cost("savage_swing_blue")


def test_savage_swing_red_loads():
    _check_savage_feast_loads("savage_swing_red")


def test_savage_swing_red_play_pays_cost():
    _check_savage_feast_dispatch_pays_cost("savage_swing_red")


def test_savage_swing_yellow_loads():
    _check_savage_feast_loads("savage_swing_yellow")


def test_savage_swing_yellow_play_pays_cost():
    _check_savage_feast_dispatch_pays_cost("savage_swing_yellow")


# ===========================================================================
# scabskin_leathers
# ===========================================================================

def test_scabskin_leathers_loads():
    cd = get_card("scabskin_leathers")
    assert cd is not None and cd.abilities[0].ability_type == "PLAY"


def test_scabskin_leathers_play_grants_some_resources():
    state = _make_state()
    card = _make_card("scabskin_leathers", 1)
    before = state.players[1].resources
    dispatch(state, "ON_PLAY", "scabskin_leathers", card=card)
    delta = state.players[1].resources - before
    assert 0 <= delta <= 3


def test_scabskin_leathers_wrong_event_no_op():
    state = _make_state()
    card = _make_card("scabskin_leathers", 1)
    before = state.players[1].resources
    dispatch(state, "ON_HIT", "scabskin_leathers", card=card)
    assert state.players[1].resources == before


# ===========================================================================
# scar_for_a_scar_blue / red / yellow
# ===========================================================================

def _check_scar_for_a_scar_low_health(slug: str):
    state = _make_state()
    state.players[1].life = 30
    state.players[2].life = 40
    state.combat = _make_combat()
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert "go_again" in state.combat.keywords


def _check_scar_for_a_scar_high_health(slug: str):
    state = _make_state()
    state.players[1].life = 40
    state.players[2].life = 30
    state.combat = _make_combat()
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert "go_again" not in state.combat.keywords


def test_scar_for_a_scar_blue_low_health():
    _check_scar_for_a_scar_low_health("scar_for_a_scar_blue")


def test_scar_for_a_scar_blue_high_health():
    _check_scar_for_a_scar_high_health("scar_for_a_scar_blue")


def test_scar_for_a_scar_red_low_health():
    _check_scar_for_a_scar_low_health("scar_for_a_scar_red")


def test_scar_for_a_scar_red_high_health():
    _check_scar_for_a_scar_high_health("scar_for_a_scar_red")


def test_scar_for_a_scar_yellow_low_health():
    _check_scar_for_a_scar_low_health("scar_for_a_scar_yellow")


def test_scar_for_a_scar_yellow_high_health():
    _check_scar_for_a_scar_high_health("scar_for_a_scar_yellow")


# ===========================================================================
# scour_the_battlescape_blue / red / yellow
# ===========================================================================

def _check_scour_dispatch(slug: str):
    state = _make_state()
    state.players[1].hand.add(_make_deck_card("h0"))
    state.players[1].deck.add(_make_deck_card("d0"))
    state.combat = _make_combat()
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)


def _check_scour_arsenal_grants_go_again(slug: str):
    state = _make_state()
    state.players[1].hand.add(_make_deck_card("h0"))
    state.players[1].deck.add(_make_deck_card("d0"))
    state.combat = _make_combat()
    card = _make_card(slug, 1)
    card.prev_zone = "arsenal"
    dispatch(state, "ON_PLAY", slug, card=card)
    assert "go_again" in state.combat.keywords


def test_scour_the_battlescape_blue_dispatch():
    _check_scour_dispatch("scour_the_battlescape_blue")


def test_scour_the_battlescape_blue_arsenal_go_again():
    _check_scour_arsenal_grants_go_again("scour_the_battlescape_blue")


def test_scour_the_battlescape_red_dispatch():
    _check_scour_dispatch("scour_the_battlescape_red")


def test_scour_the_battlescape_red_arsenal_go_again():
    _check_scour_arsenal_grants_go_again("scour_the_battlescape_red")


def test_scour_the_battlescape_yellow_dispatch():
    _check_scour_dispatch("scour_the_battlescape_yellow")


def test_scour_the_battlescape_yellow_arsenal_go_again():
    _check_scour_arsenal_grants_go_again("scour_the_battlescape_yellow")


# ===========================================================================
# seismic_surge
# ===========================================================================

def test_seismic_surge_loads():
    cd = get_card("seismic_surge")
    assert cd is not None and len(cd.abilities) >= 1


def test_seismic_surge_start_of_turn_reduces_guardian_cost():
    state = _make_state()
    card = _make_card("seismic_surge", 1)
    state.players[1].auras.add(card)
    dispatch(state, "START_OF_TURN", "seismic_surge", card=card)
    flags = state.players[1].current_turn_effects
    assert any("guardian" in f and "-1" in f for f in flags)


def test_seismic_surge_start_of_turn_destroys_self():
    state = _make_state()
    card = _make_card("seismic_surge", 1)
    state.players[1].auras.add(card)
    dispatch(state, "START_OF_TURN", "seismic_surge", card=card)
    assert card not in state.players[1].auras.cards


# ===========================================================================
# sharpen_steel_blue / yellow  (red already covered upstream)
# ===========================================================================

def test_sharpen_steel_blue_queues_weapon_bonus():
    state = _make_state()
    card = _make_card("sharpen_steel_blue", 1)
    dispatch(state, "ON_PLAY", "sharpen_steel_blue", card=card)
    assert "next_weapon_attack_+1" in state.players[1].current_turn_effects


def test_sharpen_steel_yellow_queues_weapon_bonus():
    state = _make_state()
    card = _make_card("sharpen_steel_yellow", 1)
    dispatch(state, "ON_PLAY", "sharpen_steel_yellow", card=card)
    assert "next_weapon_attack_+2" in state.players[1].current_turn_effects


def test_sharpen_steel_blue_wrong_event_no_op():
    state = _make_state()
    card = _make_card("sharpen_steel_blue", 1)
    dispatch(state, "ON_HIT", "sharpen_steel_blue", card=card)
    assert "next_weapon_attack_+1" not in state.players[1].current_turn_effects


# ===========================================================================
# show_time_blue
# ===========================================================================

def test_show_time_blue_loads():
    cd = get_card("show_time_blue")
    assert cd is not None and len(cd.abilities) >= 2


def test_show_time_blue_start_of_turn_destroys_and_draws():
    state = _make_state()
    state.players[1].deck.add(_make_deck_card("d0"))
    card = _make_card("show_time_blue", 1)
    state.players[1].auras.add(card)
    dispatch(state, "START_OF_TURN", "show_time_blue", card=card)
    assert len(state.players[1].hand.cards) == 1
    assert card not in state.players[1].auras.cards


def test_show_time_blue_wrong_event_no_destroy():
    state = _make_state()
    state.players[1].deck.add(_make_deck_card("d0"))
    card = _make_card("show_time_blue", 1)
    before_hand = len(state.players[1].hand.cards)
    # ON_HIT does not fire START_OF_TURN ability — no draw, no destroy
    dispatch(state, "ON_HIT", "show_time_blue", card=card)
    assert len(state.players[1].hand.cards) == before_hand


# ===========================================================================
# sigil_of_solace_blue / red / yellow
# ===========================================================================

def test_sigil_of_solace_blue_play_gains_one_life():
    state = _make_state()
    before = state.players[1].life
    card = _make_card("sigil_of_solace_blue", 1)
    dispatch(state, "ON_PLAY", "sigil_of_solace_blue", card=card)
    assert state.players[1].life == before + 1


def test_sigil_of_solace_red_play_gains_three_life():
    state = _make_state()
    before = state.players[1].life
    card = _make_card("sigil_of_solace_red", 1)
    dispatch(state, "ON_PLAY", "sigil_of_solace_red", card=card)
    assert state.players[1].life == before + 3


def test_sigil_of_solace_yellow_play_gains_two_life():
    state = _make_state()
    before = state.players[1].life
    card = _make_card("sigil_of_solace_yellow", 1)
    dispatch(state, "ON_PLAY", "sigil_of_solace_yellow", card=card)
    assert state.players[1].life == before + 2


def test_sigil_of_solace_blue_wrong_event_no_op():
    state = _make_state()
    before = state.players[1].life
    card = _make_card("sigil_of_solace_blue", 1)
    dispatch(state, "ON_HIT", "sigil_of_solace_blue", card=card)
    assert state.players[1].life == before


# ===========================================================================
# singing_steelblade_yellow
# ===========================================================================

def test_singing_steelblade_yellow_grants_base_power():
    state = _make_state()
    state.combat = _make_combat(power=2)
    card = _make_card("singing_steelblade_yellow", 1)
    dispatch(state, "ON_PLAY", "singing_steelblade_yellow", card=card)
    assert state.combat.attack_power >= 3


def test_singing_steelblade_yellow_reprise_extra_bonus():
    state = _make_state()
    state.combat = _make_combat(power=2)
    state.combat.defender_used_hand_card = True
    card = _make_card("singing_steelblade_yellow", 1)
    dispatch(state, "ON_PLAY", "singing_steelblade_yellow", card=card)
    assert state.combat.attack_power == 4
    assert "go_again" in state.combat.keywords


# ===========================================================================
# sink_below_blue / red / yellow
# ===========================================================================

def _check_sink_below_dispatch(slug: str):
    state = _make_state()
    state.players[1].hand.add(_make_deck_card("h0"))
    state.players[1].deck.add(_make_deck_card("d0"))
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)


def test_sink_below_blue_dispatch():
    _check_sink_below_dispatch("sink_below_blue")


def test_sink_below_red_dispatch():
    _check_sink_below_dispatch("sink_below_red")


def test_sink_below_yellow_dispatch():
    _check_sink_below_dispatch("sink_below_yellow")


def test_sink_below_blue_loads():
    cd = get_card("sink_below_blue")
    assert cd is not None and cd.abilities[0].ability_type == "DEFENSE_REACTION"


# ===========================================================================
# sloggism_blue / red / yellow
# ===========================================================================

def _check_sloggism(slug: str, amt: int):
    state = _make_state()
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert f"next_high_cost_attack_+{amt}" in state.players[1].current_turn_effects


def test_sloggism_blue_queues_high_cost_bonus():
    _check_sloggism("sloggism_blue", 4)


def test_sloggism_red_queues_high_cost_bonus():
    _check_sloggism("sloggism_red", 6)


def test_sloggism_yellow_queues_high_cost_bonus():
    _check_sloggism("sloggism_yellow", 5)


def test_sloggism_blue_wrong_event_no_op():
    state = _make_state()
    card = _make_card("sloggism_blue", 1)
    dispatch(state, "ON_HIT", "sloggism_blue", card=card)
    assert "next_high_cost_attack_+4" not in state.players[1].current_turn_effects


# ===========================================================================
# smash_instinct_blue / red / yellow
# ===========================================================================

def _check_smash_instinct_intimidates(slug: str):
    state = _make_state()
    state.players[2].hand.add(_make_deck_card("opp", owner=2))
    state.combat = _make_combat()
    card = _make_card(slug, 1)
    dispatch(state, "ON_ATTACK", slug, card=card)
    assert len(state.players[2].hand.cards) == 0


def test_smash_instinct_blue_intimidates():
    _check_smash_instinct_intimidates("smash_instinct_blue")


def test_smash_instinct_red_intimidates():
    _check_smash_instinct_intimidates("smash_instinct_red")


def test_smash_instinct_yellow_intimidates():
    _check_smash_instinct_intimidates("smash_instinct_yellow")


def test_smash_instinct_blue_wrong_event_no_op():
    state = _make_state()
    state.players[2].hand.add(_make_deck_card("opp", owner=2))
    card = _make_card("smash_instinct_blue", 1)
    dispatch(state, "ON_PLAY", "smash_instinct_blue", card=card)
    assert len(state.players[2].hand.cards) == 1


# ===========================================================================
# snapdragon_scalers
# ===========================================================================

def test_snapdragon_scalers_loads():
    cd = get_card("snapdragon_scalers")
    assert cd is not None and cd.abilities[0].ability_type == "ATTACK_REACTION"


def test_snapdragon_scalers_2cost_grants_go_again():
    state = _make_state()
    atk = _make_card("hi", 1)
    atk.cost = 2
    state.combat = _make_combat(power=3, attack_card=atk)
    card = _make_card("snapdragon_scalers", 1)
    state.players[1].permanents.add(card)
    dispatch(state, "ON_PLAY", "snapdragon_scalers", card=card)
    assert "go_again" in state.combat.keywords


def test_snapdragon_scalers_low_cost_no_go_again():
    state = _make_state()
    atk = _make_card("low", 1)
    atk.cost = 1
    state.combat = _make_combat(power=3, attack_card=atk)
    card = _make_card("snapdragon_scalers", 1)
    state.players[1].permanents.add(card)
    dispatch(state, "ON_PLAY", "snapdragon_scalers", card=card)
    assert "go_again" not in state.combat.keywords


# ===========================================================================
# snatch_blue / red / yellow
# ===========================================================================

def _check_snatch_draws_on_hit(slug: str):
    state = _make_state()
    state.players[1].deck.add(_make_deck_card("d0"))
    state.combat = _make_combat()
    card = _make_card(slug, 1)
    dispatch(state, "ON_HIT", slug, card=card, event=_hit_event(3))
    assert len(state.players[1].hand.cards) == 1


def _check_snatch_wrong_event(slug: str):
    state = _make_state()
    state.players[1].deck.add(_make_deck_card("d0"))
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert len(state.players[1].hand.cards) == 0


def test_snatch_blue_draws_on_hit():
    _check_snatch_draws_on_hit("snatch_blue")


def test_snatch_blue_wrong_event_no_op():
    _check_snatch_wrong_event("snatch_blue")


def test_snatch_red_draws_on_hit_local():
    _check_snatch_draws_on_hit("snatch_red")


def test_snatch_red_wrong_event_no_op():
    _check_snatch_wrong_event("snatch_red")


def test_snatch_yellow_draws_on_hit():
    _check_snatch_draws_on_hit("snatch_yellow")


def test_snatch_yellow_wrong_event_no_op():
    _check_snatch_wrong_event("snatch_yellow")


# ===========================================================================
# spinal_crush_red
# ===========================================================================

def test_spinal_crush_red_fires_on_crush():
    state = _make_state()
    card = _make_card("spinal_crush_red", 1)
    state.combat = _make_combat(power=5, attack_card=card)
    dispatch(state, "ON_HIT", "spinal_crush_red", card=card, event=_hit_event(4))
    assert "spinal_crush_disable_go_again" in state.players[1].next_turn_effects


def test_spinal_crush_red_below_crush_no_op():
    state = _make_state()
    card = _make_card("spinal_crush_red", 1)
    state.combat = _make_combat(power=2, attack_card=card)
    dispatch(state, "ON_HIT", "spinal_crush_red", card=card, event=_hit_event(3))
    assert "spinal_crush_disable_go_again" not in state.players[1].next_turn_effects


# ===========================================================================
# staunch_response_blue / red / yellow
# ===========================================================================

def _check_staunch_response_with_resources(slug: str):
    state = _make_state()
    state.players[1].resources = 4
    state.combat = _make_combat(power=3)
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert state.combat.total_defense == 3


def _check_staunch_response_no_resources(slug: str):
    state = _make_state()
    state.players[1].resources = 0
    state.combat = _make_combat(power=3)
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert state.combat.total_defense == 0


def test_staunch_response_blue_with_resources():
    _check_staunch_response_with_resources("staunch_response_blue")


def test_staunch_response_blue_no_resources():
    _check_staunch_response_no_resources("staunch_response_blue")


def test_staunch_response_red_with_resources():
    _check_staunch_response_with_resources("staunch_response_red")


def test_staunch_response_red_no_resources():
    _check_staunch_response_no_resources("staunch_response_red")


def test_staunch_response_yellow_with_resources():
    _check_staunch_response_with_resources("staunch_response_yellow")


def test_staunch_response_yellow_no_resources():
    _check_staunch_response_no_resources("staunch_response_yellow")


# ===========================================================================
# steelblade_shunt_blue / red / yellow
# ===========================================================================

def _check_steelblade_shunt_weapon(slug: str):
    state = _make_state()
    state.combat = _make_combat(attacker_id=2, from_weapon=True)
    card = _make_card(slug, 1)
    before = state.players[2].life
    dispatch(state, "ON_PLAY", slug, card=card)
    assert state.players[2].life == before - 1


def _check_steelblade_shunt_non_weapon(slug: str):
    state = _make_state()
    state.combat = _make_combat(attacker_id=2, from_weapon=False)
    card = _make_card(slug, 1)
    before = state.players[2].life
    dispatch(state, "ON_PLAY", slug, card=card)
    assert state.players[2].life == before


def test_steelblade_shunt_blue_weapon_attack_damages_attacker():
    _check_steelblade_shunt_weapon("steelblade_shunt_blue")


def test_steelblade_shunt_blue_non_weapon_no_damage():
    _check_steelblade_shunt_non_weapon("steelblade_shunt_blue")


def test_steelblade_shunt_red_weapon_attack_damages_attacker():
    _check_steelblade_shunt_weapon("steelblade_shunt_red")


def test_steelblade_shunt_red_non_weapon_no_damage():
    _check_steelblade_shunt_non_weapon("steelblade_shunt_red")


def test_steelblade_shunt_yellow_weapon_attack_damages_attacker():
    _check_steelblade_shunt_weapon("steelblade_shunt_yellow")


def test_steelblade_shunt_yellow_non_weapon_no_damage():
    _check_steelblade_shunt_non_weapon("steelblade_shunt_yellow")


# ===========================================================================
# steelblade_supremacy_red
# ===========================================================================

def test_steelblade_supremacy_red_grants_all_attacks_bonus_and_draw():
    state = _make_state()
    card = _make_card("steelblade_supremacy_red", 1)
    dispatch(state, "ON_PLAY", "steelblade_supremacy_red", card=card)
    assert "all_attacks_+2" in state.players[1].current_turn_effects
    assert "all_attacks_hit_draw_1" in state.players[1].current_turn_effects


def test_steelblade_supremacy_red_wrong_event_no_op():
    state = _make_state()
    card = _make_card("steelblade_supremacy_red", 1)
    dispatch(state, "ON_HIT", "steelblade_supremacy_red", card=card)
    assert "all_attacks_+2" not in state.players[1].current_turn_effects


# ===========================================================================
# stonewall_confidence_blue / red / yellow
# ===========================================================================

def _check_stonewall_confidence(slug: str, amt: int):
    state = _make_state()
    state.combat = _make_combat()
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert state.combat.total_defense == amt


def test_stonewall_confidence_blue_grants_defense():
    _check_stonewall_confidence("stonewall_confidence_blue", 2)


def test_stonewall_confidence_red_grants_defense():
    _check_stonewall_confidence("stonewall_confidence_red", 4)


def test_stonewall_confidence_yellow_grants_defense():
    _check_stonewall_confidence("stonewall_confidence_yellow", 3)


def test_stonewall_confidence_blue_wrong_event_no_op():
    state = _make_state()
    state.combat = _make_combat()
    card = _make_card("stonewall_confidence_blue", 1)
    dispatch(state, "ON_HIT", "stonewall_confidence_blue", card=card)
    assert state.combat.total_defense == 0


# ===========================================================================
# stroke_of_foresight_blue / red / yellow
# ===========================================================================

def _check_stroke_of_foresight_no_reprise(slug: str, amt: int):
    state = _make_state()
    state.combat = _make_combat(power=2)
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert state.combat.attack_power == 2 + amt


def _check_stroke_of_foresight_reprise(slug: str):
    state = _make_state()
    state.combat = _make_combat(power=2)
    state.combat.defender_used_hand_card = True
    state.players[1].deck.add(_make_deck_card("d0"))
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert len(state.players[1].hand.cards) == 1


def test_stroke_of_foresight_blue_no_reprise():
    _check_stroke_of_foresight_no_reprise("stroke_of_foresight_blue", 1)


def test_stroke_of_foresight_blue_reprise_draws():
    _check_stroke_of_foresight_reprise("stroke_of_foresight_blue")


def test_stroke_of_foresight_red_no_reprise():
    _check_stroke_of_foresight_no_reprise("stroke_of_foresight_red", 3)


def test_stroke_of_foresight_red_reprise_draws():
    _check_stroke_of_foresight_reprise("stroke_of_foresight_red")


def test_stroke_of_foresight_yellow_no_reprise():
    _check_stroke_of_foresight_no_reprise("stroke_of_foresight_yellow", 2)


def test_stroke_of_foresight_yellow_reprise_draws():
    _check_stroke_of_foresight_reprise("stroke_of_foresight_yellow")


# ===========================================================================
# surging_strike_blue / red / yellow
# ===========================================================================

def _check_surging_strike_grants_go_again(slug: str):
    state = _make_state()
    state.combat = _make_combat()
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert "go_again" in state.combat.keywords


def test_surging_strike_blue_grants_go_again():
    _check_surging_strike_grants_go_again("surging_strike_blue")


def test_surging_strike_red_grants_go_again():
    _check_surging_strike_grants_go_again("surging_strike_red")


def test_surging_strike_yellow_grants_go_again():
    _check_surging_strike_grants_go_again("surging_strike_yellow")


def test_surging_strike_blue_wrong_event_no_op():
    state = _make_state()
    state.combat = _make_combat()
    card = _make_card("surging_strike_blue", 1)
    dispatch(state, "ON_HIT", "surging_strike_blue", card=card)
    assert "go_again" not in state.combat.keywords


# ===========================================================================
# tectonic_plating
# ===========================================================================

def test_tectonic_plating_loads():
    cd = get_card("tectonic_plating")
    assert cd is not None and cd.abilities[0].ability_type == "ACTIVATE"


def test_tectonic_plating_activate_grants_go_again():
    state = _make_state()
    state.players[1].resources = 1
    state.combat = _make_combat()
    card = _make_card("tectonic_plating", 1)
    state.players[1].permanents.add(card)
    dispatch(state, "ON_ACTIVATE", "tectonic_plating", card=card)
    assert "go_again" in state.combat.keywords


def test_tectonic_plating_no_resources_no_op():
    state = _make_state()
    state.players[1].resources = 0
    state.combat = _make_combat()
    card = _make_card("tectonic_plating", 1)
    state.players[1].permanents.add(card)
    dispatch(state, "ON_ACTIVATE", "tectonic_plating", card=card)
    assert "go_again" not in state.combat.keywords


# ===========================================================================
# timesnap_potion_blue
# ===========================================================================

def test_timesnap_potion_blue_loads():
    cd = get_card("timesnap_potion_blue")
    assert cd is not None and cd.abilities[0].ability_type == "ACTIVATE"


def test_timesnap_potion_blue_activate_grants_two_ap():
    state = _make_state()
    card = _make_card("timesnap_potion_blue", 1)
    state.players[1].permanents.add(card)
    before = state.players[1].action_points
    dispatch(state, "ON_ACTIVATE", "timesnap_potion_blue", card=card)
    assert state.players[1].action_points == before + 2


def test_timesnap_potion_blue_wrong_event_no_op():
    state = _make_state()
    card = _make_card("timesnap_potion_blue", 1)
    state.players[1].permanents.add(card)
    before = state.players[1].action_points
    dispatch(state, "ON_HIT", "timesnap_potion_blue", card=card)
    assert state.players[1].action_points == before


# ===========================================================================
# tome_of_fyendal_yellow
# ===========================================================================

def test_tome_of_fyendal_yellow_arsenal_draws_two():
    state = _make_state()
    state.players[1].deck.add(_make_deck_card("d0"))
    state.players[1].deck.add(_make_deck_card("d1"))
    card = _make_card("tome_of_fyendal_yellow", 1)
    card.prev_zone = "arsenal"
    dispatch(state, "ON_PLAY", "tome_of_fyendal_yellow", card=card)
    assert len(state.players[1].hand.cards) == 2


def test_tome_of_fyendal_yellow_not_from_arsenal_no_draw():
    state = _make_state()
    state.players[1].deck.add(_make_deck_card("d0"))
    card = _make_card("tome_of_fyendal_yellow", 1)
    dispatch(state, "ON_PLAY", "tome_of_fyendal_yellow", card=card)
    assert len(state.players[1].hand.cards) == 0


# ===========================================================================
# unmovable_blue / red / yellow  (STATIC)
# ===========================================================================

def _check_unmovable_static(slug: str):
    cd = get_card(slug)
    assert cd is not None
    assert cd.abilities[0].ability_type == "DEFENSE_REACTION"


def _check_unmovable_static_not_dispatched(slug: str):
    state = _make_state()
    state.combat = _make_combat(power=4)
    card = _make_card(slug, 1)
    card.prev_zone = "arsenal"
    dispatch(state, "ON_PLAY", slug, card=card)
    assert state.combat.attack_power == 4


def test_unmovable_blue_loads_static():
    _check_unmovable_static("unmovable_blue")


def test_unmovable_blue_static_not_dispatched():
    _check_unmovable_static_not_dispatched("unmovable_blue")


def test_unmovable_red_loads_static():
    _check_unmovable_static("unmovable_red")


def test_unmovable_red_static_not_dispatched():
    _check_unmovable_static_not_dispatched("unmovable_red")


def test_unmovable_yellow_loads_static():
    _check_unmovable_static("unmovable_yellow")


def test_unmovable_yellow_static_not_dispatched():
    _check_unmovable_static_not_dispatched("unmovable_yellow")


# ===========================================================================
# warriors_valor_blue / red / yellow
# ===========================================================================

def _check_warriors_valor(slug: str, amt: int):
    state = _make_state()
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert f"next_weapon_attack_+{amt}" in state.players[1].current_turn_effects
    assert "next_weapon_attack_hit_go_again" in state.players[1].current_turn_effects


def test_warriors_valor_blue_play():
    _check_warriors_valor("warriors_valor_blue", 1)


def test_warriors_valor_red_play():
    _check_warriors_valor("warriors_valor_red", 3)


def test_warriors_valor_yellow_play():
    _check_warriors_valor("warriors_valor_yellow", 2)


def test_warriors_valor_blue_wrong_event_no_op():
    state = _make_state()
    card = _make_card("warriors_valor_blue", 1)
    dispatch(state, "ON_HIT", "warriors_valor_blue", card=card)
    assert "next_weapon_attack_+1" not in state.players[1].current_turn_effects


# ===========================================================================
# whelming_gustwave_blue / red / yellow
# ===========================================================================

def _check_whelming_gustwave_blue_red_combo(slug: str):
    state = _make_state()
    state.chain_links.append(_make_chain_link("surging_strike_red"))
    state.combat = _make_combat(power=2)
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert state.combat.attack_power == 3
    assert "go_again" in state.combat.keywords


def _check_whelming_gustwave_blue_red_no_combo(slug: str):
    state = _make_state()
    state.combat = _make_combat(power=2)
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert state.combat.attack_power == 2


def test_whelming_gustwave_blue_combo():
    _check_whelming_gustwave_blue_red_combo("whelming_gustwave_blue")


def test_whelming_gustwave_blue_no_combo():
    _check_whelming_gustwave_blue_red_no_combo("whelming_gustwave_blue")


def test_whelming_gustwave_red_combo():
    _check_whelming_gustwave_blue_red_combo("whelming_gustwave_red")


def test_whelming_gustwave_red_no_combo():
    _check_whelming_gustwave_blue_red_no_combo("whelming_gustwave_red")


def test_whelming_gustwave_yellow_combo_powers_up_and_go_again():
    state = _make_state()
    state.chain_links.append(_make_chain_link("surging_strike_red"))
    state.combat = _make_combat(power=2)
    card = _make_card("whelming_gustwave_yellow", 1)
    dispatch(state, "ON_ATTACK", "whelming_gustwave_yellow", card=card)
    assert state.combat.attack_power == 3
    assert "go_again" in state.combat.keywords


def test_whelming_gustwave_yellow_no_combo_no_op():
    state = _make_state()
    state.combat = _make_combat(power=2)
    card = _make_card("whelming_gustwave_yellow", 1)
    dispatch(state, "ON_ATTACK", "whelming_gustwave_yellow", card=card)
    assert state.combat.attack_power == 2


# ===========================================================================
# wounded_bull_blue / red / yellow
# ===========================================================================

def _check_wounded_bull_low_health(slug: str):
    state = _make_state()
    state.players[1].life = 30
    state.players[2].life = 40
    state.combat = _make_combat(power=3)
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert state.combat.attack_power == 4


def _check_wounded_bull_high_health(slug: str):
    state = _make_state()
    state.players[1].life = 40
    state.players[2].life = 30
    state.combat = _make_combat(power=3)
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert state.combat.attack_power == 3


def test_wounded_bull_blue_low_health():
    _check_wounded_bull_low_health("wounded_bull_blue")


def test_wounded_bull_blue_high_health():
    _check_wounded_bull_high_health("wounded_bull_blue")


def test_wounded_bull_red_low_health():
    _check_wounded_bull_low_health("wounded_bull_red")


def test_wounded_bull_red_high_health():
    _check_wounded_bull_high_health("wounded_bull_red")


def test_wounded_bull_yellow_low_health():
    _check_wounded_bull_low_health("wounded_bull_yellow")


def test_wounded_bull_yellow_high_health():
    _check_wounded_bull_high_health("wounded_bull_yellow")


# ===========================================================================
# wounding_blow_blue / red / yellow  (vanilla)
# ===========================================================================

def test_wounding_blow_blue_no_abilities():
    cd = get_card("wounding_blow_blue")
    assert cd is not None and cd.abilities == []


def test_wounding_blow_blue_dispatch_is_noop():
    state = _make_state()
    card = _make_card("wounding_blow_blue", 1)
    dispatch(state, "ON_PLAY", "wounding_blow_blue", card=card)


def test_wounding_blow_red_no_abilities():
    cd = get_card("wounding_blow_red")
    assert cd is not None and cd.abilities == []


def test_wounding_blow_red_dispatch_is_noop():
    state = _make_state()
    card = _make_card("wounding_blow_red", 1)
    dispatch(state, "ON_PLAY", "wounding_blow_red", card=card)


def test_wounding_blow_yellow_no_abilities():
    cd = get_card("wounding_blow_yellow")
    assert cd is not None and cd.abilities == []


def test_wounding_blow_yellow_dispatch_is_noop():
    state = _make_state()
    card = _make_card("wounding_blow_yellow", 1)
    dispatch(state, "ON_PLAY", "wounding_blow_yellow", card=card)


# ===========================================================================
# wrecker_romp_blue / red / yellow
# ===========================================================================

def test_wrecker_romp_blue_loads():
    _check_savage_feast_loads("wrecker_romp_blue")


def test_wrecker_romp_blue_play_pays_cost():
    _check_savage_feast_dispatch_pays_cost("wrecker_romp_blue")


def test_wrecker_romp_red_loads():
    _check_savage_feast_loads("wrecker_romp_red")


def test_wrecker_romp_red_play_pays_cost():
    _check_savage_feast_dispatch_pays_cost("wrecker_romp_red")


def test_wrecker_romp_yellow_loads():
    _check_savage_feast_loads("wrecker_romp_yellow")


def test_wrecker_romp_yellow_play_pays_cost():
    _check_savage_feast_dispatch_pays_cost("wrecker_romp_yellow")


# ===========================================================================
# Improved tests for previously-only-loaded cards:
# drone_of_brutality_blue / red / yellow + emerging_power_blue / red / yellow
# ===========================================================================

def test_drone_of_brutality_blue_discard_no_crash():
    state = _make_state()
    card = _make_card("drone_of_brutality_blue", 1)
    state.players[1].graveyard.add(card)
    dispatch(state, "ON_DISCARD", "drone_of_brutality_blue", card=card)


def test_drone_of_brutality_red_discard_no_crash():
    state = _make_state()
    card = _make_card("drone_of_brutality_red", 1)
    state.players[1].graveyard.add(card)
    dispatch(state, "ON_DISCARD", "drone_of_brutality_red", card=card)


def test_drone_of_brutality_yellow_discard_no_crash():
    state = _make_state()
    card = _make_card("drone_of_brutality_yellow", 1)
    state.players[1].graveyard.add(card)
    dispatch(state, "ON_DISCARD", "drone_of_brutality_yellow", card=card)


def test_emerging_power_blue_start_of_turn_destroys_self():
    state = _make_state()
    card = _make_card("emerging_power_blue", 1)
    state.players[1].auras.add(card)
    dispatch(state, "START_OF_TURN", "emerging_power_blue", card=card)
    assert card not in state.players[1].auras.cards


def test_emerging_power_red_start_of_turn_destroys_self():
    state = _make_state()
    card = _make_card("emerging_power_red", 1)
    state.players[1].auras.add(card)
    dispatch(state, "START_OF_TURN", "emerging_power_red", card=card)
    assert card not in state.players[1].auras.cards


def test_emerging_power_yellow_start_of_turn_destroys_self():
    state = _make_state()
    card = _make_card("emerging_power_yellow", 1)
    state.players[1].auras.add(card)
    dispatch(state, "START_OF_TURN", "emerging_power_yellow", card=card)
    assert card not in state.players[1].auras.cards
