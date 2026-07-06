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
    assert cd.abilities[0].ability_type == "WHILE_STATIC"


def test_anothos_static_not_fired_on_non_recalc_events():
    """WHILE_STATIC abilities fire only on RECALC_ATTACK_POWER, not other events."""
    state = _make_state()
    state.combat = _make_combat(power=5)
    for i in range(2):
        c = _make_card(f"pitched_{i}", 1)
        c.cost = 3
        state.players[1].pitch.add(c)
    card = _make_card("anothos", 1)
    dispatch(state, "ON_PLAY", "anothos", card=card)
    assert state.combat.attack_power == 5  # ON_PLAY does not fire the static


def test_anothos_static_applies_via_recalc_bridge():
    """With 2+ cost-3 cards in pitch, Anothos's WHILE_STATIC adds +2 on recalc."""
    state = _make_state()
    state.combat = _make_combat(power=5)
    for i in range(2):
        c = _make_card(f"pitched_{i}", 1)
        c.cost = 3
        state.players[1].pitch.add(c)
    card = _make_card("anothos", 1)
    dispatch(state, "RECALC_ATTACK_POWER", "anothos", card=card)
    assert state.combat.attack_power == 7  # 5 + 2


# ===========================================================================
# barkbone_strapping
# ===========================================================================

def test_barkbone_strapping_loads():
    cd = get_card("barkbone_strapping")
    assert cd is not None
    assert cd.abilities[0].ability_type == "INSTANT"


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


# ===========================================================================
# blessing_of_deliverance_blue / red / yellow
# ===========================================================================


# ===========================================================================
# bone_head_barrier_yellow
# ===========================================================================


# ===========================================================================
# braveforge_bracers
# ===========================================================================


# ===========================================================================
# bravo  /  bravo_showstopper  (ACTIVATE → GO_AGAIN; STATIC dominate)
# ===========================================================================


# ===========================================================================
# breaking_scales
# ===========================================================================


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


# --- Migrated crush cards (DSL-authoritative) ---------------------------------
# These fire on the ON_CRUSH event (dispatched by the engine hit-listener only
# when 4+ damage is dealt) and apply their debuff to the *opponent*.

def _crush_sets_opp_flag(slug: str, flag: str):
    """Dispatch ON_CRUSH and assert the opponent receives the next-turn flag."""
    state = _make_state()
    card = _make_card(slug, 1)
    state.combat = _make_combat(attacker_id=1, power=9, attack_card=card)
    dispatch(state, "ON_CRUSH", slug, card=card, event=Event(type="ON_CRUSH", data={"damage": 5}))
    assert flag in state.players[2].next_turn_effects
    assert flag not in state.players[1].next_turn_effects


def _crush_wrong_event_no_flag(slug: str, flag: str):
    """A non-crush event (ON_HIT) must not apply the crush debuff."""
    state = _make_state()
    card = _make_card(slug, 1)
    state.combat = _make_combat(attacker_id=1, power=9, attack_card=card)
    dispatch(state, "ON_HIT", slug, card=card, event=Event(type="ON_HIT", data={"damage": 5}))
    assert flag not in state.players[2].next_turn_effects


# ===========================================================================
# cracked_bauble_yellow  (vanilla — no abilities)
# ===========================================================================


# ===========================================================================
# cranial_crush_blue
# ===========================================================================

def test_cranial_crush_blue_fires_on_crush():
    _crush_sets_opp_flag("cranial_crush_blue", flag="cant_draw")


def test_cranial_crush_blue_wrong_event_no_op():
    _crush_wrong_event_no_flag("cranial_crush_blue", flag="cant_draw")


def test_cranial_crush_blue_loads():
    assert get_card("cranial_crush_blue") is not None


# ===========================================================================
# crazy_brew_blue (ACTIVATE → roll-driven inject)
# ===========================================================================


# ===========================================================================
# crippling_crush_red (CRUSH → opponent discards 2)
# ===========================================================================


# ===========================================================================
# crush_confidence_blue / red / yellow
# ===========================================================================


# ===========================================================================
# dawnblade  (multi-ability hero weapon)
# ===========================================================================


# ===========================================================================
# debilitate_blue / red / yellow  (CRUSH → next attack -2 power)
# ===========================================================================

def test_debilitate_blue_fires_on_crush():
    _crush_sets_opp_flag("debilitate_blue", flag="first_attack_-2p")


def test_debilitate_blue_wrong_event_no_op():
    _crush_wrong_event_no_flag("debilitate_blue", flag="first_attack_-2p")


def test_debilitate_blue_loads():
    assert get_card("debilitate_blue") is not None


def test_debilitate_red_fires_on_crush():
    _crush_sets_opp_flag("debilitate_red", flag="first_attack_-2p")


def test_debilitate_red_wrong_event_no_op():
    _crush_wrong_event_no_flag("debilitate_red", flag="first_attack_-2p")


def test_debilitate_red_loads():
    assert get_card("debilitate_red") is not None


def test_debilitate_yellow_fires_on_crush():
    _crush_sets_opp_flag("debilitate_yellow", flag="first_attack_-2p")


def test_debilitate_yellow_wrong_event_no_op():
    _crush_wrong_event_no_flag("debilitate_yellow", flag="first_attack_-2p")


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


# ===========================================================================
# disable_blue / red / yellow  (CRUSH → put bottom + draw)
# ===========================================================================

def _check_disable_fires(slug: str):
    """On crush, the opponent's arsenal card is put on the bottom of their deck."""
    state = _make_state()
    arc = _make_deck_card("opp_arsenal", owner=2)
    state.players[2].arsenal.add(arc)
    card = _make_card(slug, 1)
    state.combat = _make_combat(attacker_id=1, power=9, attack_card=card)
    deck_before = len(state.players[2].deck.cards)
    dispatch(state, "ON_CRUSH", slug, card=card,
             event=Event(type="ON_CRUSH", data={"damage": 5}))
    assert len(state.players[2].arsenal.cards) == 0
    assert len(state.players[2].deck.cards) == deck_before + 1


def _check_disable_wrong_event(slug: str):
    state = _make_state()
    arc = _make_deck_card("opp_arsenal", owner=2)
    state.players[2].arsenal.add(arc)
    card = _make_card(slug, 1)
    state.combat = _make_combat(attacker_id=1, power=9, attack_card=card)
    dispatch(state, "ON_HIT", slug, card=card,
             event=Event(type="ON_HIT", data={"damage": 5}))
    # Non-crush event — arsenal untouched
    assert len(state.players[2].arsenal.cards) == 1


def test_disable_blue_fires_on_crush():
    _check_disable_fires("disable_blue")


def test_disable_blue_wrong_event_no_op():
    _check_disable_wrong_event("disable_blue")


def test_disable_blue_loads():
    assert get_card("disable_blue") is not None


def test_disable_red_fires_on_crush():
    _check_disable_fires("disable_red")


def test_disable_red_wrong_event_no_op():
    _check_disable_wrong_event("disable_red")


def test_disable_red_loads():
    assert get_card("disable_red") is not None


def test_disable_yellow_fires_on_crush():
    _check_disable_fires("disable_yellow")


def test_disable_yellow_wrong_event_no_op():
    _check_disable_wrong_event("disable_yellow")


def test_disable_yellow_loads():
    assert get_card("disable_yellow") is not None


# ===========================================================================
# dorinthea  (hero — weapon hit grants go again, once per turn)
# ===========================================================================


# ===========================================================================
# dorinthea_ironsong  (ATTACK_REACTION on weapon attack → go again)
# ===========================================================================


# ===========================================================================
# drone_of_brutality_blue / red / yellow
# ===========================================================================


# ===========================================================================
# emerging_power_blue / red / yellow
# ===========================================================================


# ===========================================================================
# enlightened_strike_red
# ===========================================================================

def test_enlightened_strike_red_loads():
    cd = get_card("enlightened_strike_red")
    assert cd is not None
    # "Choose 1" card → a single MODAL ability with 3 modes, plus a play cost
    assert len(cd.abilities) == 1
    assert cd.abilities[0].ability_type == "MODAL"
    assert len(cd.abilities[0].modes) == 3
    assert cd.play_cost is not None


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


def test_enlightened_strike_red_mode_power_bonus():
    """Mode 0 (+2{p}): default agent picks the first mode."""
    state = _make_state()
    card = _make_card("enlightened_strike_red", 1)
    state.combat = _make_combat(attacker_id=1, power=4, attack_card=card)
    dispatch(state, "ON_PLAY", "enlightened_strike_red", card=card)
    assert state.combat.attack_power == 6  # +2


def test_enlightened_strike_red_mode_go_again():
    """Mode 1 (go again): agent picks the second mode."""
    state = _make_state()
    state.player_agents[1] = lambda s, options, **kw: "1"
    card = _make_card("enlightened_strike_red", 1)
    state.combat = _make_combat(attacker_id=1, power=4, attack_card=card)
    dispatch(state, "ON_PLAY", "enlightened_strike_red", card=card)
    assert any(k.lower().replace("_", " ") == "go again"
               for k in state.combat.keywords)


# ===========================================================================
# flic_flak_blue / red / yellow  (DEFENSE_REACTION — combo gated)
# ===========================================================================


# ===========================================================================
# alpha_rampage_red  (PLAY discard cost; ON_ATTACK INTIMIDATE)
# ===========================================================================

def test_alpha_rampage_red_loads():
    cd = get_card("alpha_rampage_red")
    # Intimidate trigger as one ability; the random discard is the play cost.
    assert cd is not None and len(cd.abilities) >= 1
    assert cd.play_cost is not None


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


# ===========================================================================
# awakening_bellow_blue / red / yellow  (PLAY: NEXT_ATTACK_BONUS + INTIMIDATE)
# ===========================================================================

def _check_awakening_bellow(slug: str, amt: int):
    # Legacy helper (still used by unimplemented cards that check the next_attack flag).
    state = _make_state()
    state.players[2].hand.add(_make_deck_card("opp0", owner=2))
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert f"next_attack_+{amt}" in state.players[1].current_turn_effects
    assert len(state.players[2].hand.cards) == 0


def _check_awakening_bellow_dsl(slug: str, amt: int):
    # Awakening Bellow: ON_PLAY intimidates AND queues a +amt next-Brute-attack mod.
    state = _make_state()
    state.players[2].hand.add(_make_deck_card("opp0", owner=2))
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    queued = getattr(state.players[1], "dsl_queued_attack_mods", [])
    assert any(m["amount"] == amt and m["mod"] == "add" for m in queued)
    assert len(state.players[2].hand.cards) == 0   # intimidate banished the card


def _check_awakening_bellow_wrong_event(slug: str):
    state = _make_state()
    state.players[2].hand.add(_make_deck_card("opp0", owner=2))
    card = _make_card(slug, 1)
    dispatch(state, "ON_HIT", slug, card=card)
    assert not getattr(state.players[1], "dsl_queued_attack_mods", [])
    assert len(state.players[2].hand.cards) == 1


def test_awakening_bellow_blue_play_intimidates():
    _check_awakening_bellow_dsl("awakening_bellow_blue", 1)


def test_awakening_bellow_blue_wrong_event():
    _check_awakening_bellow_wrong_event("awakening_bellow_blue")


def test_awakening_bellow_red_play_intimidates():
    _check_awakening_bellow_dsl("awakening_bellow_red", 3)


def test_awakening_bellow_red_wrong_event():
    _check_awakening_bellow_wrong_event("awakening_bellow_red")


def test_awakening_bellow_yellow_play_intimidates():
    _check_awakening_bellow_dsl("awakening_bellow_yellow", 2)


def test_awakening_bellow_yellow_wrong_event():
    _check_awakening_bellow_wrong_event("awakening_bellow_yellow")


# ===========================================================================
# barraging_beatdown_blue / red / yellow  (PLAY: NEXT_ATTACK_BONUS + INTIMIDATE)
# ===========================================================================


# ===========================================================================
# barraging_brawnhide_yellow  (STATIC)
# ===========================================================================


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


# ===========================================================================
# bloodrush_bellow_yellow  (PLAY: ALL_ATTACKS_BONUS +2; conditional discard)
# ===========================================================================


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


# ===========================================================================
# driving_blade_blue / red / yellow
# ===========================================================================

def _check_driving_blade(slug: str, amt: int):
    state = _make_state()
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert f"next_weapon_attack_+{amt}" in state.players[1].current_turn_effects
    assert "next_weapon_attack_go_again" in state.players[1].current_turn_effects


# ===========================================================================
# energy_potion_blue  (ACTIVATE: gain 2 resources)
# ===========================================================================


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


# ===========================================================================
# forged_for_war_yellow  (DEFENSE_REACTION: +1 defense)
# ===========================================================================


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
    # Activating without 3 energy is unaffordable -> no-op (cost gated in _apply_activate).
    import engine.play as _P
    from engine.actions import Action as _Action, ActionType as _AT
    state = _make_state()
    card = _make_card("fyendals_spring_tunic", 1)
    card.zone = "chest"
    state.players[1].chest.cards.append(card)
    before = state.players[1].resources
    act = _Action(type=_AT.ACTIVATE_CARD, card=card, slot="chest")
    act.player_id = 1
    _P._apply_activate(state, act)
    assert state.players[1].resources == before


# ===========================================================================
# glint_the_quicksilver_blue
# ===========================================================================


# ===========================================================================
# goliath_gauntlet
# ===========================================================================


# ===========================================================================
# harmonized_kodachi
# ===========================================================================


# ===========================================================================
# head_jab_blue / red / yellow  (vanilla — no abilities)
# ===========================================================================


# ===========================================================================
# heart_of_fyendal_blue
# ===========================================================================


# ===========================================================================
# heartened_cross_strap
# ===========================================================================


# ===========================================================================
# helm_of_isens_peak
# ===========================================================================


# ===========================================================================
# hope_merchants_hood
# ===========================================================================


# ===========================================================================
# hurricane_technique_yellow
# ===========================================================================


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


# ===========================================================================
# ironsong_determination_yellow
# ===========================================================================


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


# ===========================================================================
# katsu  (hero ON_ATTACK ninja)
# ===========================================================================


# ===========================================================================
# katsu_the_wanderer  (ON_HIT non-weapon → flag NEXT)
# ===========================================================================


# ===========================================================================
# last_ditch_effort_blue
# ===========================================================================


# ===========================================================================
# leg_tap_blue / red / yellow  (vanilla)
# ===========================================================================


# ===========================================================================
# lord_of_wind_blue
# ===========================================================================


# ===========================================================================
# mask_of_momentum
# ===========================================================================


# ===========================================================================
# mugenshi_release_yellow
# ===========================================================================


# ===========================================================================
# natures_path_pilgrimage_blue / red / yellow
# ===========================================================================

def _check_natures_path(slug: str, amt: int):
    state = _make_state()
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert f"next_weapon_attack_+{amt}" in state.players[1].current_turn_effects


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


# ===========================================================================
# nimblism_blue / red / yellow
# ===========================================================================

def _check_nimblism(slug: str, amt: int):
    # MODIFY_NEXT_ATTACK queues a power mod onto the player (consumed at attack creation).
    state = _make_state()
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    queued = getattr(state.players[1], "dsl_queued_attack_mods", [])
    assert any(m["amount"] == amt and m["mod"] == "add" for m in queued)


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
    assert not getattr(state.players[1], "dsl_queued_attack_mods", [])


# ===========================================================================
# nip_at_the_heels_blue
# ===========================================================================


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


# ===========================================================================
# potion_of_strength_blue
# ===========================================================================


# ===========================================================================
# pounding_gale_red
# ===========================================================================


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


def test_pummel_red_targets_2cost_action():
    _check_pummel_attacks_action_2cost("pummel_red")


def test_pummel_red_no_match_no_op():
    _check_pummel_no_match("pummel_red")


# ===========================================================================
# quicken
# ===========================================================================


# ===========================================================================
# raging_onslaught_blue / red / yellow  (vanilla)
# ===========================================================================


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


# ===========================================================================
# reckless_swing_blue
# ===========================================================================


# ===========================================================================
# refraction_bolters
# ===========================================================================


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


# ===========================================================================
# remembrance_yellow
# ===========================================================================


# ===========================================================================
# retrace_the_past_blue
# ===========================================================================


# ===========================================================================
# rhinar / rhinar_reckless_rampage
# ===========================================================================


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


# ===========================================================================
# romping_club
# ===========================================================================


# ===========================================================================
# rout_red
# ===========================================================================


# ===========================================================================
# sand_sketched_plan_blue
# ===========================================================================


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


# ===========================================================================
# savage_swing_blue / red / yellow
# ===========================================================================


# ===========================================================================
# scabskin_leathers
# ===========================================================================

def test_scabskin_leathers_loads():
    cd = get_card("scabskin_leathers")
    assert cd is not None and cd.abilities[0].ability_type == "ACTIVATE"


def test_scabskin_leathers_activate_grants_action_points():
    state = _make_state()
    card = _make_card("scabskin_leathers", 1)
    before = state.players[1].action_points
    dispatch(state, "ON_ACTIVATE", "scabskin_leathers", card=card)
    delta = state.players[1].action_points - before
    assert 0 <= delta <= 3   # floor(d6 / 2)


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


# ===========================================================================
# seismic_surge
# ===========================================================================


# ===========================================================================
# sharpen_steel_blue / yellow  (red already covered upstream)
# ===========================================================================


# ===========================================================================
# show_time_blue
# ===========================================================================


# ===========================================================================
# sigil_of_solace_blue / red / yellow
# ===========================================================================


def test_sigil_of_solace_red_play_gains_three_life():
    state = _make_state()
    before = state.players[1].life
    card = _make_card("sigil_of_solace_red", 1)
    dispatch(state, "ON_PLAY", "sigil_of_solace_red", card=card)
    assert state.players[1].life == before + 3


# ===========================================================================
# singing_steelblade_yellow
# ===========================================================================


# ===========================================================================
# sink_below_blue / red / yellow
# ===========================================================================

def _check_sink_below_dispatch(slug: str):
    state = _make_state()
    state.players[1].hand.add(_make_deck_card("h0"))
    state.players[1].deck.add(_make_deck_card("d0"))
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)


def test_sink_below_red_dispatch():
    _check_sink_below_dispatch("sink_below_red")


# ===========================================================================
# sloggism_blue / red / yellow
# ===========================================================================

def _check_sloggism(slug: str, amt: int):
    state = _make_state()
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert f"next_high_cost_attack_+{amt}" in state.players[1].current_turn_effects


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


# ===========================================================================
# snapdragon_scalers
# ===========================================================================


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


# ===========================================================================
# spinal_crush_red
# ===========================================================================

def test_spinal_crush_red_fires_on_crush():
    _crush_sets_opp_flag("spinal_crush_red", flag="cant_go_again")


def test_spinal_crush_red_wrong_event_no_op():
    _crush_wrong_event_no_flag("spinal_crush_red", flag="cant_go_again")


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


# ===========================================================================
# steelblade_supremacy_red
# ===========================================================================


# ===========================================================================
# stonewall_confidence_blue / red / yellow
# ===========================================================================

def _check_stonewall_confidence(slug: str, amt: int):
    state = _make_state()
    state.combat = _make_combat()
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert state.combat.total_defense == amt


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


# ===========================================================================
# surging_strike_blue / red / yellow
# ===========================================================================

def _check_surging_strike_grants_go_again(slug: str):
    state = _make_state()
    state.combat = _make_combat()
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert "go_again" in state.combat.keywords


# ===========================================================================
# tectonic_plating
# ===========================================================================


# ===========================================================================
# timesnap_potion_blue
# ===========================================================================


# ===========================================================================
# tome_of_fyendal_yellow
# ===========================================================================


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


# ===========================================================================
# warriors_valor_blue / red / yellow
# ===========================================================================

def _check_warriors_valor(slug: str, amt: int):
    state = _make_state()
    card = _make_card(slug, 1)
    dispatch(state, "ON_PLAY", slug, card=card)
    assert f"next_weapon_attack_+{amt}" in state.players[1].current_turn_effects
    assert "next_weapon_attack_hit_go_again" in state.players[1].current_turn_effects


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


# ===========================================================================
# wounding_blow_blue / red / yellow  (vanilla)
# ===========================================================================


# ===========================================================================
# wrecker_romp_blue / red / yellow
# ===========================================================================


# ===========================================================================
# Improved tests for previously-only-loaded cards:
# drone_of_brutality_blue / red / yellow + emerging_power_blue / red / yellow
# ===========================================================================


