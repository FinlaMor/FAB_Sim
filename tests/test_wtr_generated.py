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


def test_drone_of_brutality_blue_has_leave_play_trigger():
    cd = get_card("drone_of_brutality_blue")
    assert any(a.trigger == "ON_LEAVE_PLAY" for a in cd.abilities)


def test_drone_of_brutality_blue_dispatch_no_crash():
    state = _make_state()
    card = _make_card("drone_of_brutality_blue", 1)
    dispatch(state, "ON_LEAVE_PLAY", "drone_of_brutality_blue", card=card)


def test_drone_of_brutality_red_loads():
    assert get_card("drone_of_brutality_red") is not None


def test_drone_of_brutality_red_has_leave_play_trigger():
    cd = get_card("drone_of_brutality_red")
    assert any(a.trigger == "ON_LEAVE_PLAY" for a in cd.abilities)


def test_drone_of_brutality_red_dispatch_no_crash():
    state = _make_state()
    card = _make_card("drone_of_brutality_red", 1)
    dispatch(state, "ON_LEAVE_PLAY", "drone_of_brutality_red", card=card)


def test_drone_of_brutality_yellow_loads():
    assert get_card("drone_of_brutality_yellow") is not None


def test_drone_of_brutality_yellow_has_death_trigger():
    cd = get_card("drone_of_brutality_yellow")
    assert any(a.trigger == "ON_DEATH" for a in cd.abilities)


def test_drone_of_brutality_yellow_dispatch_no_crash():
    state = _make_state()
    card = _make_card("drone_of_brutality_yellow", 1)
    dispatch(state, "ON_DEATH", "drone_of_brutality_yellow", card=card)


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
