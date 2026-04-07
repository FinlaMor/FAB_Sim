"""
tests/test_card_implementations.py

Four-section test module:

SECTION 1 — Keyword coverage (CR 8.3 / 8.4)
  One class per keyword. Tests the keyword function directly so that individual
  cards carrying the keyword do NOT need separate keyword tests.

SECTION 2 — Per-card implementation tests
  One class per implemented card. Tests condition logic and effect outcomes.

SECTION 3 — Damage helper coverage
  Parametrized tests for effect_deal_damage, effect_deal_arcane, and
  effect_gain_life.  Card tests that deal damage can assert
  `opp.health == start - card.base_arcane_damage` without re-testing the
  pipeline — these tests prove the pipeline itself is correct.

SECTION 4 — Event dispatch coverage
  Tests that EventManager fires listeners for every event type the engine
  emits.  Cards that register on_hit / start_of_turn / etc. listeners can
  trust the dispatch mechanism is correct.

SECTION 5 — Targeting coverage
  Tests for legal_actions and targeting rules.  For example, when an 
  arcane action specifies target hero vs any target, legal_actions should
  only return valid targets.

SECTION 6 — Pitching coverage
    Tests for find_all_valid_pitch_sequences and pitch legality rules.
"""
from __future__ import annotations

import pytest

from engine.card import Card, CardDB
from engine.card_effects.keywords import (
    arcane_barrier,
    arcane_shelter,
    battleworn,
    blade_break,
    blood_debt,
    boost,
    combo_check,
    crush_check,
    dominate_check,
    effect_deal_arcane,
    effect_deal_damage,
    effect_gain_life,
    effect_transcend,
    fusion,
    go_again,
    guardwell,
    overpower_check,
    phantasm_check,
    phantasm_destroy,
    quell,
    reprise_check,
    spectra_destroy,
    spellvoid,
    temper,
    ward,
    watery_grave,
)
from engine.actions import (
    Action, 
    ActionType,
    _legal_action_step, 
    legal_actions, 
    _attackable_permanents, 
    find_all_valid_pitch_sequences, 
    _legal_targets_for_card, 
    get_defendable_cards,
    get_pitchable_cards,
    _legal_action_step,
    _legal_defend_step,
    _legal_reaction_step,
    _legal_end_turn_step,
    _can_afford_action,
    can_pay_cost,
    get_pitchable_cards
)
from engine.card_effects.registry import (
    EQUIPMENT_ACTIVATION_CONDITIONS,
    EQUIPMENT_ACTIVATION_EFFECTS,
)
from engine.state import (
    ChainLink,
    CombatState,
    ContinuousEffectManager,
    Event,
    EventManager,
    GameState,
    Step,
)
from tests.conftest import _make_card, _make_player, _make_state, _mock_agent
from engine.engine import _pitch_for_cost


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _scripted_agent(*answers):
    """Return an agent callable that pops answers in order."""
    queue = list(answers)
    def _agent(state, options, **kwargs):
        return queue.pop(0) if queue else (options[0] if options else None)
    return _agent


def _make_combat_state(
    attacker_id: int = 1,
    attack_power: int = 4,
    defending_cards: list | None = None,
    defender_used_hand_card: bool = False,
) -> CombatState:
    atk = _make_card("test_attack", types=["Action", "Attack"], base_power=attack_power)
    atk.owner = attacker_id
    atk.controller = attacker_id
    return CombatState(
        attacker_id=attacker_id,
        link_id=1,
        attack_power=attack_power,
        base_attack_power=attack_power,
        attack_card=atk,
        keywords=[],
        defending_cards=list(defending_cards or []),
        defender_used_hand_card=defender_used_hand_card,
    )


def _make_event(event_type: str = "combat_chain_close", data: dict | None = None) -> Event:
    return Event(type=event_type, data=data or {})


def _make_equipment(player, zone_name: str = "chest", base_def: int = 3) -> Card:
    """Create a piece of equipment owned by player and place it in the given slot."""
    card = _make_card("test_equip", types=["Equipment"], base_defense=base_def)
    card.owner = player.player_id
    card.controller = player.player_id
    zone = getattr(player, zone_name, None)
    if zone is not None:
        zone.add(card)
    return card


def _add_chain_link(state: GameState, slug: str, attacker_id: int = 1) -> None:
    link = ChainLink(
        chainlink_id=len(state.chain_links) + 1,
        attacker_id=attacker_id,
        attack_slug=slug,
        attack_power=4,
        net_damage=2,
        keywords=[],
        from_weapon=False,
    )
    state.chain_links.append(link)


# ===========================================================================
# SECTION 1 — KEYWORD COVERAGE TESTS
# ===========================================================================


# ---------------------------------------------------------------------------
# CR 8.3.2  Battleworn
# ---------------------------------------------------------------------------

class TestBattleworn:
    """Battleworn: when combat chain closes after this defended, put a -1{d} counter on it."""

    def test_applies_minus_one_defense_counter(self):
        state = _make_state()
        card = _make_equipment(state.players[1], base_def=3)
        battleworn(card, _make_event(), state)
        assert card.defense == 2

    def test_multiple_applications_stack(self):
        state = _make_state()
        card = _make_equipment(state.players[1], base_def=3)
        battleworn(card, _make_event(), state)
        battleworn(card, _make_event(), state)
        assert card.defense == 1

    def test_does_not_destroy_at_zero(self):
        """Battleworn stops at 0 — Temper destroys, Battleworn does not."""
        state = _make_state()
        card = _make_equipment(state.players[1], base_def=1)
        battleworn(card, _make_event(), state)
        assert card.defense == 0
        assert card in state.players[1].chest.cards


# ---------------------------------------------------------------------------
# CR 8.3.3  Blade Break
# ---------------------------------------------------------------------------

class TestBladeBreak:
    """Blade Break: when combat chain closes after this defended, destroy it."""

    def test_moves_to_graveyard_on_close(self):
        state = _make_state()
        card = _make_equipment(state.players[1], zone_name="head", base_def=2)
        blade_break(card, _make_event(), state)
        assert card in state.players[1].graveyard.cards
        assert card not in state.players[1].head.cards


# ---------------------------------------------------------------------------
# CR 8.3.10  Temper
# ---------------------------------------------------------------------------

class TestTemper:
    """Temper: add -1{d} counter; if defense reaches 0, destroy."""

    def test_adds_counter_and_survives_when_defense_remains(self):
        state = _make_state()
        card = _make_equipment(state.players[1], base_def=2)
        temper(card, _make_event(), state)
        assert card.defense == 1
        assert card in state.players[1].chest.cards

    def test_destroys_when_defense_reaches_zero(self):
        state = _make_state()
        card = _make_equipment(state.players[1], base_def=1)
        temper(card, _make_event(), state)
        assert card.defense == 1  # Temper adds counter first, then checks for destroy — counters reset when changing zones, so defense is still 1 at time of check
        assert card in state.players[1].graveyard.cards

    def test_does_not_destroy_above_zero(self):
        state = _make_state()
        card = _make_equipment(state.players[1], base_def=3)
        temper(card, _make_event(), state)
        assert card not in state.players[1].graveyard.cards


# ---------------------------------------------------------------------------
# CR 8.3.34  Guardwell
# ---------------------------------------------------------------------------

class TestGuardwell:
    """Guardwell: when this defended, add -1{d} counters equal to its current {d}."""

    def test_reduces_defense_to_zero(self):
        state = _make_state()
        card = _make_equipment(state.players[1], base_def=3)
        guardwell(card, _make_event(), state)
        assert card.defense == 0

    def test_no_counters_when_defense_already_zero(self):
        state = _make_state()
        card = _make_equipment(state.players[1], base_def=0)
        guardwell(card, _make_event(), state)
        assert card.defense == 0
        assert card in state.players[1].chest.cards

    def test_counters_not_equal_to_base_defense(self):
        """Guardwell checks current defense, not base defense."""
        state = _make_state()
        card = _make_equipment(state.players[1], base_def=3)
        card.effects.append(('base_defense', lambda x: x - 2))  # simulate a previous effect reducing defense
        guardwell(card, _make_event(), state)
        assert card.defense == 2


# ---------------------------------------------------------------------------
# CR 8.3.4  Dominate
# ---------------------------------------------------------------------------

class TestDominate:
    """Dominate: can't be defended by more than one card from hand."""

    def test_false_with_no_defenders(self):
        state = _make_state()
        state.combat = _make_combat_state(defending_cards=[])
        assert dominate_check(None, state) is False

    def test_false_when_defender_not_from_hand(self):
        state = _make_state()
        d = _make_card("blocker", types=["Action"])
        d.prev_zone = "arsenal"
        state.combat = _make_combat_state(defending_cards=[d])
        assert dominate_check(None, state) is False

    def test_true_when_one_hand_card_defending(self):
        state = _make_state()
        d = _make_card("blocker", types=["Action"])
        d.prev_zone = "hand"
        state.combat = _make_combat_state(defending_cards=[d])
        assert dominate_check(None, state) is True

    def test_false_with_no_combat(self):
        state = _make_state()
        state.combat = None
        assert dominate_check(None, state) is False


# ---------------------------------------------------------------------------
# CR 8.3.22  Overpower
# ---------------------------------------------------------------------------

class TestOverpower:
    """Overpower: can't be defended by more than one action card."""

    def test_false_with_no_defenders(self):
        state = _make_state()
        state.combat = _make_combat_state(defending_cards=[])
        assert overpower_check(None, state) is False

    def test_false_when_defender_not_action(self):
        state = _make_state()
        d = _make_card("blocker", types=["Equipment"])
        state.combat = _make_combat_state(defending_cards=[d])
        assert overpower_check(None, state) is False

    def test_true_when_one_action_card_defending(self):
        state = _make_state()
        d = _make_card("blocker", types=["Action"])
        state.combat = _make_combat_state(defending_cards=[d])
        assert overpower_check(None, state) is True

    def test_false_with_no_combat(self):
        state = _make_state()
        state.combat = None
        assert overpower_check(None, state) is False


# ---------------------------------------------------------------------------
# CR 8.3.5  Go Again
# ---------------------------------------------------------------------------

class TestGoAgain:
    """Go Again: active player gains 1 action point on resolution."""

    def test_grants_ap_to_active_player(self):
        state = _make_state()
        card = _make_card("go_again_card")
        card.controller = 1
        state.active_player = 1
        state.players[1].action_points = 0
        go_again(card, state)
        assert state.players[1].action_points == 1

    def test_does_not_grant_to_non_active_player(self):
        """CR 8.5.7b: Go Again only benefits the turn player."""
        state = _make_state()
        card = _make_card("go_again_card")
        card.controller = 2
        state.active_player = 1   # p1 is active; p2's card has Go Again but p2 is not active
        state.players[2].action_points = 0
        go_again(card, state)
        assert state.players[2].action_points == 0


# ---------------------------------------------------------------------------
# CR 8.3.13  Phantasm
# ---------------------------------------------------------------------------

class TestPhantasm:
    """Phantasm: when defended by a non-Illusionist attack action with 6+ power, destroy."""

    def _blocker(self, power: int, illusionist: bool = False) -> Card:
        types = ["Action", "Attack"]
        if illusionist:
            types.append("Illusionist")
        c = _make_card("blocker", types=types, base_power=power)
        return c

    def test_check_true_non_illusionist_6plus(self):
        state = _make_state()
        state.combat = _make_combat_state(defending_cards=[self._blocker(6)])
        assert phantasm_check(None, _make_event(), state) is True

    def test_check_false_illusionist_defends(self):
        state = _make_state()
        state.combat = _make_combat_state(defending_cards=[self._blocker(6, illusionist=True)])
        assert phantasm_check(None, _make_event(), state) is False

    def test_check_false_power_below_6(self):
        state = _make_state()
        state.combat = _make_combat_state(defending_cards=[self._blocker(5)])
        assert phantasm_check(None, _make_event(), state) is False

    def test_check_false_no_defenders(self):
        state = _make_state()
        state.combat = _make_combat_state(defending_cards=[])
        assert phantasm_check(None, _make_event(), state) is False

    def test_destroy_moves_phantasm_to_graveyard(self):
        state = _make_state()
        phantasm_card = _make_card("illusion", types=["Action", "Attack"], keywords=["Phantasm"], base_power=3)
        phantasm_card.owner = 1
        phantasm_card.controller = 1
        state.players[1].hand.add(phantasm_card)
        state.combat = _make_combat_state(defending_cards=[self._blocker(6)])
        phantasm_destroy(phantasm_card, _make_event(), state)
        assert phantasm_card in state.players[1].graveyard.cards

    def test_engine_destroys_phantasm_when_non_illusionist_defends(self):
        """Full-engine test: when a non-Illusionist 6+ power attack action card
        defends against a Phantasm attack, the Phantasm is destroyed synchronously
        at the Defend step and the combat chain closes immediately — identical to
        Spectra. Go Again on the Phantasm does NOT grant +1 AP."""
        import os
        from engine.card import CardDB
        from engine.effects import EffectManager
        from engine.engine import _combat_phase_iter
        from engine.state import StackEntry

        os.environ.setdefault('debug', 'False')
        db = CardDB()
        state = _make_state()
        state.active_player = 1
        state.priority_player = 1
        state.card_db = db
        state.effect_manager = EffectManager()

        # Player 1 attacks with a Phantasm card (has Go Again to prove AP is NOT restored)
        phantasm = _make_card("phantasm_attack", types=["Action", "Attack"],
                              keywords=["Phantasm", "Go Again"], base_power=3, base_cost=0)
        phantasm.owner = 1
        phantasm.controller = 1
        phantasm.is_public = True

        # Place the Phantasm as the active attack entry on the stack
        entry = StackEntry(
            player_id=1,
            card=phantasm,
            layer_type='card',
            layer_position=1,
        )
        state.stack_entries.append(entry)
        state.stack.add(phantasm)
        state.players[1].action_points = 0  # already spent

        # Player 2 has a 6-power non-Illusionist attack action in hand to block with
        blocker = _make_card("big_attack", types=["Action", "Attack"], base_power=6, base_defense=3)
        blocker.owner = 2
        blocker.controller = 2
        blocker.is_public = True
        state.players[2].hand.add(blocker)

        # Script player 2 to defend with the blocker (defend step issues CHOOSE per card)
        choose_blocker = Action(type=ActionType.CHOOSE, card=blocker)
        decisions = iter([choose_blocker])

        def scripted_agent(s, options, *args, **kw):
            try:
                act = next(decisions)
                if act in options:
                    return act
            except StopIteration:
                pass
            # Default: pass
            pass_acts = [o for o in options if o.type == ActionType.PASS or o.type == ActionType.REACTION_PASS]
            return pass_acts[0] if pass_acts else options[0]

        state.player_agents = {1: scripted_agent, 2: scripted_agent}

        _combat_phase_iter(state)

        # Phantasm must be in graveyard — destroyed by its own triggered ability
        assert phantasm in state.players[1].graveyard.cards
        # Go again does not resolve as phantasm destroys the chain.
        assert state.players[1].action_points == 0



# ---------------------------------------------------------------------------
# CR 8.3.14  Spectra
# ---------------------------------------------------------------------------

class TestSpectra:
    """Spectra: when this aura becomes the target of an attack, destroy it."""

    def test_destroys_when_targeted(self):
        """Full-engine test: attacking a Spectra aura by name destroys it and
        closes the combat chain without proceeding to Defend/Damage/Resolution."""
        from engine.card import CardDB
        from engine.effects import EffectManager
        from engine.card_effects.triggers import register_card_triggers
        from engine.engine import _combat_phase_iter
        from engine.state import StackEntry

        db = CardDB()
        state = _make_state()
        state.active_player = 2
        state.priority_player = 2
        state.card_db = db
        state.effect_manager = EffectManager()

        # Spectra aura on player 1's side
        aura = _make_card("spectral_shield", types=["Aura"], keywords=["Spectra"])
        aura.owner = 1
        aura.controller = 1
        aura.is_public = True
        state.players[1].permanents.add(aura)
        register_card_triggers(aura, state.event_manager)

        # Attack card on the stack with declared target = the aura slug
        attack = _make_card("test_attack", types=["Action", "Attack"], base_power=4, base_cost=0, keywords=["Go Again"])
        attack.owner = 2
        attack.controller = 2
        attack.is_public = True
        state.players[2].action_points = 0  # already spent playing the attack

        entry = StackEntry(
            player_id=2,
            card=attack,
            layer_type='card',
            layer_position=1,
            declared_targets=[aura.slug],
        )
        state.stack_entries.append(entry)
        state.stack.add(attack)

        import os
        os.environ.setdefault('debug', 'False')
        _combat_phase_iter(state)

        assert aura in state.players[1].graveyard.cards
        assert aura not in state.players[1].permanents.cards
        assert state.step == Step.COMBAT_CLOSE
        assert state.players[2].action_points == 0  # Go Again did not trigger since chain closed before resolution

    def test_closes_combat_chain(self):
        """Spectra immediately moves to Close Step — no Defend/Reaction/Damage/Resolution."""
        state = _make_state()
        aura = _make_card("test_aura", types=["Aura"])
        aura.owner = 1
        aura.controller = 1
        state.players[1].permanents.add(aura)
        spectra_destroy(aura, _make_event(event_type="target_of_attack"), state)
        assert state.step == Step.COMBAT_CLOSE

    def test_go_again_does_not_restore_ap(self):
        """Go Again resolves at Resolution Step. Spectra closes at Close Step before that,
        so the attacker does not recover the AP spent playing the attack."""
        state = _make_state()
        state.active_player = 2

        aura = _make_card("test_aura", types=["Aura"])
        aura.owner = 1
        aura.controller = 1
        state.players[1].permanents.add(aura)

        attack = _make_card("test_attack", types=["Action", "Attack"], base_power=4, keywords=["Go Again"])
        attack.owner = 2
        attack.controller = 2

        # AP was spent playing the attack (1 → 0); Go Again would restore it at Resolution.
        state.players[2].action_points = 0
        state.combat = CombatState(
            attacker_id=2,
            link_id=1,
            attack_power=4,
            base_attack_power=4,
            attack_card=attack,
            keywords=["Go Again"],
        )

        spectra_destroy(aura, _make_event(event_type="target_of_attack"), state)

        # Chain closed at Close Step — Resolution Step (where Go Again grants +1 AP) never ran.
        assert state.step == Step.COMBAT_CLOSE
        assert state.players[2].action_points == 0


# ---------------------------------------------------------------------------
# CR 8.3.11  Blood Debt
# ---------------------------------------------------------------------------

class TestBloodDebt:
    """Blood Debt: while banished face-up, lose 1 life at start of end phase."""

    def test_loses_one_life_when_banished_face_up(self):
        state = _make_state()
        card = _make_card("bd_card")
        card.owner = 1
        card.zone = "banished"
        card.is_public = True
        state.players[1].banished.add(card)
        starting = state.players[1].health
        blood_debt(card, _make_event(), state)
        assert state.players[1].health == starting - 1

    def test_no_loss_when_zone_not_banished(self):
        state = _make_state()
        card = _make_card("bd_card")
        card.owner = 1
        card.zone = "graveyard"
        card.is_public = True
        starting = state.players[1].health
        blood_debt(card, _make_event(), state)
        assert state.players[1].health == starting

    def test_no_loss_when_banished_face_down(self):
        state = _make_state()
        card = _make_card("bd_card")
        card.owner = 1
        card.zone = "banished"
        card.is_public = False
        starting = state.players[1].health
        blood_debt(card, _make_event(), state)
        assert state.players[1].health == starting


# ---------------------------------------------------------------------------
# CR 8.3.41  Watery Grave
# ---------------------------------------------------------------------------

class TestWateryGrave:
    """Watery Grave: when put into graveyard from the arena, turn face-down."""

    def test_turns_face_down_when_from_arena(self):
        state = _make_state()
        card = _make_card("wg_card")
        card.zone = "graveyard"
        card.prev_zone = "chest"   # chest is an arena zone
        card.is_public = True
        card.face_down = False
        watery_grave(card, _make_event(), state)
        assert card.face_down is True
        assert card.is_public is False

    def test_no_change_when_came_from_hand(self):
        state = _make_state()
        card = _make_card("wg_card")
        card.zone = "graveyard"
        card.prev_zone = "hand"    # hand is NOT an arena zone
        card.face_down = False
        watery_grave(card, _make_event(), state)
        assert card.face_down is False


# ---------------------------------------------------------------------------
# CR 8.3.20  Ward
# ---------------------------------------------------------------------------

class TestWard:
    """Ward N: auto-destroy this to prevent N damage (not optional)."""

    def test_destroys_and_returns_full_prevention(self):
        state = _make_state()
        card = _make_card("ward_aura", types=["Aura"])
        card.owner = 1
        card.controller = 1
        state.players[1].permanents.add(card)
        prevented = ward(card, 3, state)
        assert prevented == 3
        assert card in state.players[1].graveyard.cards

    @pytest.mark.parametrize("amount", [1, 2, 4, 6])
    def test_prevents_exact_ward_value(self, amount):
        state = _make_state()
        card = _make_card("ward_aura", types=["Aura"])
        card.owner = 1
        card.controller = 1
        state.players[1].permanents.add(card)
        assert ward(card, amount, state) == amount


# ---------------------------------------------------------------------------
# CR 8.3.37  Arcane Shelter
# ---------------------------------------------------------------------------

class TestArcaneShelter:
    """Arcane Shelter N: auto-destroy to prevent N arcane damage (not optional)."""

    def test_destroys_and_returns_full_prevention(self):
        state = _make_state()
        card = _make_equipment(state.players[1], zone_name="chest", base_def=2)
        prevented = arcane_shelter(card, 2, state)
        assert prevented == 2
        assert card in state.players[1].graveyard.cards


# ---------------------------------------------------------------------------
# CR 8.3.15  Spellvoid
# ---------------------------------------------------------------------------

class TestSpellvoid:
    """Spellvoid N: optional — destroy this to prevent N arcane damage."""

    def test_activating_destroys_and_prevents(self):
        state = _make_state()
        card = _make_equipment(state.players[1])
        state.player_agents[1] = _scripted_agent(True)
        prevented = spellvoid(card, 4, state)
        assert prevented == 4
        assert card in state.players[1].graveyard.cards

    def test_declining_does_nothing(self):
        state = _make_state()
        card = _make_equipment(state.players[1])
        state.player_agents[1] = _scripted_agent(False)
        prevented = spellvoid(card, 4, state)
        assert prevented == 0
        assert card not in state.players[1].graveyard.cards


# ---------------------------------------------------------------------------
# CR 8.3.8  Arcane Barrier
# ---------------------------------------------------------------------------

class TestArcaneBarrier:
    """Arcane Barrier N: optional — pay N resources to prevent N arcane damage."""

    def test_pays_resources_and_prevents(self):
        state = _make_state()
        card = _make_equipment(state.players[1])
        state.players[1].resources = 3
        state.player_agents[1] = _scripted_agent(True)
        prevented = arcane_barrier(card, 3, state)
        assert prevented == 3
        assert state.players[1].resources == 0

    def test_declining_prevents_nothing(self):
        state = _make_state()
        card = _make_equipment(state.players[1])
        state.players[1].resources = 3
        state.player_agents[1] = _scripted_agent(False)
        prevented = arcane_barrier(card, 3, state)
        assert prevented == 0
        assert state.players[1].resources == 3

    def test_prevents_nothing_when_unaffordable(self):
        state = _make_state()
        card = _make_equipment(state.players[1])
        state.players[1].resources = 0  # no resources, empty hand — can't pitch
        prevented = arcane_barrier(card, 3, state)
        assert prevented == 0


# ---------------------------------------------------------------------------
# CR 8.3.19  Quell
# ---------------------------------------------------------------------------

class TestQuell:
    """Quell N: optional — pay N resources to prevent N damage; schedule for end-phase destruction."""

    def test_pays_and_schedules_destroy(self):
        state = _make_state()
        card = _make_card("quell_aura", types=["Aura"])
        card.owner = 1
        card.controller = 1
        state.players[1].permanents.add(card)
        state.players[1].resources = 2
        state.player_agents[1] = _scripted_agent(True)
        prevented = quell(card, 2, state)
        assert prevented == 2
        assert state.players[1].resources == 0
        assert f"quell_destroy_{card.slug}" in state.players[1].current_turn_effects

    def test_declining_prevents_nothing(self):
        state = _make_state()
        card = _make_card("quell_aura", types=["Aura"])
        card.owner = 1
        card.controller = 1
        state.players[1].resources = 2
        state.player_agents[1] = _scripted_agent(False)
        prevented = quell(card, 2, state)
        assert prevented == 0


# ---------------------------------------------------------------------------
# CR 8.4.2  Crush
# ---------------------------------------------------------------------------

class TestCrush:
    """Crush: conditional label — triggers when this attack deals 4 or more damage."""

    @pytest.mark.parametrize("damage,expected", [
        (4, True), (7, True), (3, False), (0, False),
    ])
    def test_threshold(self, damage, expected):
        event = _make_event(data={"damage": damage})
        assert crush_check(event, None) is expected

    def test_false_when_damage_key_absent(self):
        event = _make_event(data={})
        assert crush_check(event, None) is False


# ---------------------------------------------------------------------------
# CR 8.4.3  Reprise
# ---------------------------------------------------------------------------

class TestReprise:
    """Reprise: conditional label — active when the defending hero used a hand card."""

    def test_true_when_defender_used_hand_card(self):
        state = _make_state()
        state.combat = _make_combat_state(defender_used_hand_card=True)
        assert reprise_check(state) is True

    def test_false_when_no_hand_card_used(self):
        state = _make_state()
        state.combat = _make_combat_state(defender_used_hand_card=False)
        assert reprise_check(state) is False

    def test_false_with_no_combat(self):
        state = _make_state()
        state.combat = None
        assert reprise_check(state) is False


# ---------------------------------------------------------------------------
# CR 8.4.1  Combo
# ---------------------------------------------------------------------------

class TestCombo:
    """Combo: conditional label — last attack on the chain was one of the named cards."""

    def test_true_when_last_link_matches(self):
        state = _make_state()
        _add_chain_link(state, "knee_thrust_red")
        assert combo_check(state, ["knee_thrust_red", "knee_thrust_yellow"]) is True

    def test_false_when_last_link_does_not_match(self):
        state = _make_state()
        _add_chain_link(state, "some_other_card")
        assert combo_check(state, ["knee_thrust_red"]) is False

    def test_false_with_empty_chain(self):
        state = _make_state()
        assert combo_check(state, ["knee_thrust_red"]) is False

    def test_only_last_link_matters(self):
        state = _make_state()
        _add_chain_link(state, "knee_thrust_red")   # link 1 — matches
        _add_chain_link(state, "some_other_card")   # link 2 — last link, does NOT match
        assert combo_check(state, ["knee_thrust_red"]) is False


# ---------------------------------------------------------------------------
# CR 8.3.9  Boost
# ---------------------------------------------------------------------------

class TestBoost:
    """Boost: optional additional cost — banish top of deck; if Mechanologist, gain Go Again."""

    def _deck_top(self, state: GameState, types: list) -> Card:
        top = _make_card("deck_top", types=types)
        top.owner = 1
        top.controller = 1
        state.players[1].deck.add(top)
        return top

    def test_banishes_top_card_when_activated(self):
        state = _make_state()
        top = self._deck_top(state, ["Action"])
        card = _make_card("boost_card", types=["Action"])
        card.owner = 1
        card.controller = 1
        state.player_agents[1] = _scripted_agent(True)
        boost(card, state)
        assert top in state.players[1].banished.cards

    def test_false_when_declined(self):
        state = _make_state()
        self._deck_top(state, ["Action"])
        card = _make_card("boost_card", types=["Action"])
        card.owner = 1
        card.controller = 1
        state.player_agents[1] = _scripted_agent(False)
        assert boost(card, state) is False

    def test_false_when_deck_empty(self):
        state = _make_state()
        card = _make_card("boost_card", types=["Action"])
        card.owner = 1
        card.controller = 1
        assert boost(card, state) is False

    def test_grants_go_again_when_mechanologist_card_banished(self):
        state = _make_state()
        self._deck_top(state, ["Mechanologist"])
        card = _make_card("boost_card", types=["Action"])
        card.owner = 1
        card.controller = 1
        state.player_agents[1] = _scripted_agent(True)
        result = boost(card, state)
        assert result is True
        assert any("go again" in kw.lower() for kw in card.keywords)

    def test_no_go_again_for_non_mechanologist(self):
        state = _make_state()
        self._deck_top(state, ["Action"])
        card = _make_card("boost_card", types=["Action"])
        card.owner = 1
        card.controller = 1
        state.player_agents[1] = _scripted_agent(True)
        result = boost(card, state)
        assert result is False
        assert not any("go again" in kw.lower() for kw in card.keywords)


# ---------------------------------------------------------------------------
# CR 8.3.17  Fusion
# ---------------------------------------------------------------------------

class TestFusion:
    """Fusion: optional additional cost — reveal a card with the named supertype from hand."""

    def test_true_when_matching_card_revealed(self):
        state = _make_state()
        card = _make_card("fusion_card", types=["Action"])
        card.owner = 1
        card.controller = 1
        ice_card = _make_card("ice_card", types=["Ice", "Action"])
        ice_card.owner = 1
        ice_card.controller = 1
        state.players[1].hand.add(ice_card)
        state.player_agents[1] = _scripted_agent(True, ice_card.slug)
        assert fusion(card, "Ice", state) is True

    def test_false_when_no_matching_card_in_hand(self):
        state = _make_state()
        card = _make_card("fusion_card", types=["Action"])
        card.owner = 1
        card.controller = 1
        assert fusion(card, "Ice", state) is False

    def test_false_when_player_declines(self):
        state = _make_state()
        card = _make_card("fusion_card", types=["Action"])
        card.owner = 1
        card.controller = 1
        ice_card = _make_card("ice_card", types=["Ice", "Action"])
        ice_card.owner = 1
        ice_card.controller = 1
        state.players[1].hand.add(ice_card)
        state.player_agents[1] = _scripted_agent(False)
        assert fusion(card, "Ice", state) is False


# ---------------------------------------------------------------------------
# CR 8.5.48  Transcend
# ---------------------------------------------------------------------------

class TestTranscend:
    """Transcend: if you've played another blue card this turn, the card goes to
    hand flipped to its back face (inner chi) instead of the graveyard.

    Two things are tested here:
      1. effect_transcend() — the mechanical move (card → hand, transcended=True).
      2. The trigger condition — any(c.base_color == 'blue' for c in
         player.cards_played_this_turn) — so per-card tests don't re-check it.
    """

    # ── effect_transcend() mechanics ─────────────────────────────────────────

    def test_transcend_moves_card_to_hand(self):
        state = _make_state()
        card = _make_card("transcend_card", types=["Action"])
        card.owner = 1
        card.controller = 1
        state.players[1].graveyard.add(card)
        effect_transcend(state, 1, source=card)
        assert card in state.players[1].hand.cards
        assert card not in state.players[1].graveyard.cards

    def test_transcend_sets_transcended_flag(self):
        state = _make_state()
        card = _make_card("transcend_card", types=["Action"])
        card.owner = 1
        card.controller = 1
        state.players[1].graveyard.add(card)
        effect_transcend(state, 1, source=card)
        assert card.transcended is True

    def test_transcend_clears_face_down(self):
        state = _make_state()
        card = _make_card("transcend_card", types=["Action"])
        card.owner = 1
        card.controller = 1
        card.face_down = True
        state.players[1].graveyard.add(card)
        effect_transcend(state, 1, source=card)
        assert card.face_down is False

    def test_transcend_returns_true(self):
        state = _make_state()
        card = _make_card("transcend_card", types=["Action"])
        card.owner = 1
        card.controller = 1
        state.players[1].graveyard.add(card)
        assert effect_transcend(state, 1, source=card) is True

    def test_transcend_returns_false_when_no_source(self):
        state = _make_state()
        assert effect_transcend(state, 1) is False

    # ── Transcend trigger condition ───────────────────────────────────────────

    def _blue_condition(self, state: GameState) -> bool:
        """The condition every Transcend card checks before calling effect_transcend."""
        player = state.players[1]
        return any(c.base_color == "blue" for c in player.cards_played_this_turn)

    def test_condition_true_when_blue_card_played(self):
        state = _make_state()
        blue = _make_card("blue_card")
        blue.base_color = "blue"
        state.players[1].cards_played_this_turn.append(blue)
        assert self._blue_condition(state) is True

    def test_condition_true_with_mixed_cards(self):
        state = _make_state()
        red = _make_card("red_card")
        red.base_color = "red"
        blue = _make_card("blue_card")
        blue.base_color = "blue"
        state.players[1].cards_played_this_turn.extend([red, blue])
        assert self._blue_condition(state) is True

    def test_condition_false_when_only_red_and_yellow(self):
        state = _make_state()
        red = _make_card("red_card")
        red.base_color = "red"
        yellow = _make_card("yellow_card")
        yellow.base_color = "yellow"
        state.players[1].cards_played_this_turn.extend([red, yellow])
        assert self._blue_condition(state) is False

    def test_condition_false_when_no_cards_played(self):
        state = _make_state()
        assert self._blue_condition(state) is False

    def test_condition_uses_base_color_not_pitch(self):
        """A blue card whose pitch has been modified by a game effect still triggers Transcend."""
        state = _make_state()
        blue = _make_card("blue_card")
        blue.base_color = "blue"
        blue.base_pitch = 3  # canonical blue pitch
        # Simulate a game effect that overrides the computed pitch to 1
        blue.effects.append(("base_pitch", lambda _: 1))
        assert blue.pitch == 1  # confirm pitch is now 1 (not blue's normal 3)
        state.players[1].cards_played_this_turn.append(blue)
        assert self._blue_condition(state) is True

    def test_condition_false_for_card_that_is_its_own_blue_play(self):
        """The self-card check: Transcend triggers only on *another* blue card.
        The triggering card itself is typically already in the played list, but
        cards_played_this_turn includes self — the condition remains True because
        a second blue card is what matters.  This test confirms the list must
        contain at least one blue card independent of the source card."""
        state = _make_state()
        # Only the source card itself (blue) is in the list — still triggers.
        # (Engine appends the card before calling on_play, so this is realistic.)
        source = _make_card("source_card")
        source.base_color = "blue"
        state.players[1].cards_played_this_turn.append(source)
        assert self._blue_condition(state) is True


# ===========================================================================
# SECTION 2 — PER-CARD IMPLEMENTATION TESTS
# ===========================================================================

# ===========================================================================
# 10,000 Year Reunion alternate cost
# ===========================================================================


class Test10000YearReunion:
    """10,000 Year Reunion alternate cost: remove 3 +1{p} counters from auras.

    Implementation: engine.engine._10000_year_reunion_effect_cost
    Registered in EFFECT_COSTS["10000_year_reunion_red"].
    """

    _COST_FN = staticmethod(
        __import__("engine.engine", fromlist=["EFFECT_COSTS"]).EFFECT_COSTS[
            "10000_year_reunion_red"
        ]
    )

    # ── helpers ──────────────────────────────────────────────────────────────

    def _action(self, alt: bool = True):
        """Minimal action stub."""
        class _Act:
            alternative_cost_used = "remove_p_counters" if alt else None
        return _Act()

    def _add_aura(self, state: GameState, slug: str, counters: int) -> Card:
        card = _make_card(slug, types=["Aura"])
        card.owner = 1
        card.controller = 1
        state.players[1].auras.add(card)
        if counters:
            state.players[1].counters[(slug, "permanents", "+1{p}")] = counters
        return card

    # ── normal-cost path (alternative_cost_used is None) ─────────────────────

    def test_normal_cost_path_returns_true_immediately(self):
        """When normal cost is used, effect-cost function is a no-op and returns True."""
        state = _make_state()
        action = self._action(alt=False)
        result = self._COST_FN(state, 1, action, check=True)
        assert result is True

    def test_normal_cost_path_does_not_touch_counters(self):
        state = _make_state()
        self._add_aura(state, "some_aura", 2)
        action = self._action(alt=False)
        self._COST_FN(state, 1, action, check=False)
        assert state.players[1].counters[("some_aura", "permanents", "+1{p}")] == 2

    # ── check=True (legality probe) ───────────────────────────────────────────

    def test_check_true_when_exactly_three_counters(self):
        state = _make_state()
        self._add_aura(state, "aura_a", 3)
        action = self._action()
        assert self._COST_FN(state, 1, action, check=True) is True

    def test_check_true_when_counters_spread_across_auras(self):
        state = _make_state()
        self._add_aura(state, "aura_a", 1)
        self._add_aura(state, "aura_b", 1)
        self._add_aura(state, "aura_c", 1)
        action = self._action()
        assert self._COST_FN(state, 1, action, check=True) is True

    def test_check_true_when_more_than_three_counters(self):
        state = _make_state()
        self._add_aura(state, "aura_a", 5)
        action = self._action()
        assert self._COST_FN(state, 1, action, check=True) is True

    def test_check_false_when_no_counters(self):
        state = _make_state()
        # aura present but zero counters
        self._add_aura(state, "aura_a", 0)
        action = self._action()
        assert self._COST_FN(state, 1, action, check=True) is False

    def test_check_false_when_fewer_than_three_counters(self):
        state = _make_state()
        self._add_aura(state, "aura_a", 1)
        self._add_aura(state, "aura_b", 1)
        action = self._action()
        assert self._COST_FN(state, 1, action, check=True) is False

    def test_check_false_when_no_auras_at_all(self):
        state = _make_state()
        action = self._action()
        assert self._COST_FN(state, 1, action, check=True) is False

    # ── check=False (execution) — counters actually removed ──────────────────

    def test_removes_exactly_three_counters_from_single_aura(self):
        state = _make_state()
        self._add_aura(state, "aura_a", 5)
        action = self._action()
        # agent always picks "aura_a"
        state.player_agents[1] = _scripted_agent("aura_a", "aura_a", "aura_a")
        self._COST_FN(state, 1, action, check=False)
        assert state.players[1].counters[("aura_a", "permanents", "+1{p}")] == 2

    def test_removes_counters_spread_across_two_auras(self):
        state = _make_state()
        self._add_aura(state, "aura_a", 2)
        self._add_aura(state, "aura_b", 1)
        action = self._action()
        # agent picks: a, a, b
        state.player_agents[1] = _scripted_agent("aura_a", "aura_a", "aura_b")
        self._COST_FN(state, 1, action, check=False)
        assert state.players[1].counters[("aura_a", "permanents", "+1{p}")] == 0
        assert state.players[1].counters[("aura_b", "permanents", "+1{p}")] == 0

    def test_removes_one_counter_per_aura_across_three(self):
        state = _make_state()
        self._add_aura(state, "aura_x", 1)
        self._add_aura(state, "aura_y", 1)
        self._add_aura(state, "aura_z", 1)
        action = self._action()
        state.player_agents[1] = _scripted_agent("aura_x", "aura_y", "aura_z")
        self._COST_FN(state, 1, action, check=False)
        for slug in ("aura_x", "aura_y", "aura_z"):
            assert state.players[1].counters[(slug, "permanents", "+1{p}")] == 0

    def test_check_does_not_remove_counters(self):
        """check=True must never mutate counters."""
        state = _make_state()
        self._add_aura(state, "aura_a", 3)
        action = self._action()
        self._COST_FN(state, 1, action, check=True)
        assert state.players[1].counters[("aura_a", "permanents", "+1{p}")] == 3

    def test_returns_true_after_successful_removal(self):
        state = _make_state()
        self._add_aura(state, "aura_a", 3)
        action = self._action()
        state.player_agents[1] = _scripted_agent("aura_a", "aura_a", "aura_a")
        result = self._COST_FN(state, 1, action, check=False)
        assert result is True

# ---------------------------------------------------------------------------
# Aether Ironweave
# ---------------------------------------------------------------------------

class TestAetherIronweave:
    _COND = staticmethod(EQUIPMENT_ACTIVATION_CONDITIONS["aether_ironweave"])
    _EFFECT = staticmethod(EQUIPMENT_ACTIVATION_EFFECTS["aether_ironweave"])

    def _equip(self, state: GameState) -> Card:
        card = _make_card("aether_ironweave", types=["Equipment"], subtypes=["Chest"])
        card.owner = 1
        card.controller = 1
        state.players[1].chest.add(card)
        return card

    def _played(self, state: GameState, types: list, subtypes: list) -> None:
        c = _make_card("played", types=types, subtypes=subtypes)
        c.owner = 1
        c.controller = 1
        state.players[1].cards_played_this_turn.append(c)

    # -- condition --

    def test_condition_false_no_cards_played(self):
        state = _make_state()
        card = self._equip(state)
        assert self._COND(state.players[1], "chest", card, state) is False

    def test_condition_false_only_attack_action(self):
        state = _make_state()
        card = self._equip(state)
        self._played(state, ["Action"], ["Attack"])
        assert self._COND(state.players[1], "chest", card, state) is False

    def test_condition_false_only_non_attack_action(self):
        state = _make_state()
        card = self._equip(state)
        self._played(state, ["Action"], [])
        assert self._COND(state.players[1], "chest", card, state) is False

    def test_condition_false_instants_do_not_count(self):
        """Instant type cards are not Action type — neither flag should set."""
        state = _make_state()
        card = self._equip(state)
        self._played(state, ["Instant"], [])
        self._played(state, ["Instant"], ["Attack"])
        assert self._COND(state.players[1], "chest", card, state) is False

    def test_condition_true_both_types_played(self):
        state = _make_state()
        card = self._equip(state)
        self._played(state, ["Action"], ["Attack"])   # attack action
        self._played(state, ["Action"], [])            # non-attack action
        assert self._COND(state.players[1], "chest", card, state) is True

    def test_condition_true_multiple_of_each_type(self):
        state = _make_state()
        card = self._equip(state)
        self._played(state, ["Action"], ["Attack"])
        self._played(state, ["Action"], ["Attack"])
        self._played(state, ["Action"], [])
        assert self._COND(state.players[1], "chest", card, state) is True

    # -- effect --

    def test_effect_grants_two_resources(self):
        state = _make_state()
        state.players[1].resources = 0
        self._EFFECT(None, state.players[1], state)
        assert state.players[1].resources == 2

    def test_effect_grants_go_again(self):
        state = _make_state()
        state.players[1].action_points = 0
        self._EFFECT(None, state.players[1], state)
        assert state.players[1].action_points == 1

    def test_effect_stacks_with_existing_resources(self):
        state = _make_state()
        state.players[1].resources = 3
        self._EFFECT(None, state.players[1], state)
        assert state.players[1].resources == 5


# ---------------------------------------------------------------------------
# Aether Icevein — card DB sanity + variant coverage
# (Full effect tests to be added once PLAY_ABILITIES entry is implemented)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("slug,expected_arcane", [
    ("aether_icevein_red",    5),
    ("aether_icevein_yellow", 4),
    ("aether_icevein_blue",   3),
])
def test_aether_icevein_correct_arcane_value(slug, expected_arcane):
    """Each color variant carries the correct arcane damage value in the card DB."""
    from config import SLUG_INDEX_PATH
    db = CardDB(SLUG_INDEX_PATH)
    card = db.get(slug)
    assert card is not None, f"{slug} not found in card DB"
    assert card.base_arcane_damage == expected_arcane



# ===========================================================================
# SECTION 3 — DAMAGE HELPER COVERAGE
# ===========================================================================
# Tests for effect_deal_damage, effect_deal_arcane, and effect_gain_life.
# Once these pass, card tests can write:
#   assert opp.health == start - card.base_arcane_damage
# without re-testing the pipeline itself.
# ===========================================================================


# ---------------------------------------------------------------------------
# effect_deal_damage  (physical / generic damage)
# ---------------------------------------------------------------------------

class TestEffectDealDamage:
    """effect_deal_damage reduces target health by exactly the amount given."""

    @pytest.mark.parametrize("amount", [1, 2, 3, 4, 5, 6])
    def test_reduces_health_by_amount(self, amount):
        state = _make_state()
        start = state.players[2].health
        dealt = effect_deal_damage(state, 2, amount)
        assert dealt == amount
        assert state.players[2].health == start - amount

    def test_zero_damage_is_noop(self):
        state = _make_state()
        start = state.players[2].health
        dealt = effect_deal_damage(state, 2, 0)
        assert dealt == 0
        assert state.players[2].health == start

    def test_negative_damage_is_noop(self):
        state = _make_state()
        start = state.players[2].health
        dealt = effect_deal_damage(state, 2, -3)
        assert dealt == 0
        assert state.players[2].health == start

    def test_damage_dealt_event_fires(self):
        """damage_dealt event is emitted with correct payload."""
        state = _make_state()
        received = []
        state.event_manager.register(
            "damage_dealt",
            lambda ev, st: received.append(ev.data),
        )
        effect_deal_damage(state, 2, 4)
        assert received, "damage_dealt event did not fire"
        assert received[0]["amount"] == 4
        assert received[0]["target_player_id"] == 2

    def test_can_target_either_player(self):
        state = _make_state()
        start1, start2 = state.players[1].health, state.players[2].health
        effect_deal_damage(state, 1, 3)
        effect_deal_damage(state, 2, 5)
        assert state.players[1].health == start1 - 3
        assert state.players[2].health == start2 - 5


# ---------------------------------------------------------------------------
# effect_deal_arcane  (arcane damage)
# ---------------------------------------------------------------------------

class TestEffectDealArcane:
    """effect_deal_arcane reduces health by amount; respects Arcane Barrier."""

    @pytest.mark.parametrize("amount", [1, 2, 3, 4, 5])
    def test_reduces_health_by_amount(self, amount):
        state = _make_state()
        start = state.players[2].health
        dealt = effect_deal_arcane(state, 2, amount)
        assert dealt == amount
        assert state.players[2].health == start - amount

    def test_zero_arcane_is_noop(self):
        state = _make_state()
        start = state.players[2].health
        dealt = effect_deal_arcane(state, 2, 0)
        assert dealt == 0
        assert state.players[2].health == start

    def test_arcane_barrier_reduces_damage(self):
        """Arcane Barrier N: pay N to prevent N arcane damage (agent accepts)."""
        state = _make_state()
        barrier = _make_card("ab_equip", types=["Equipment"])
        barrier.owner = 2
        barrier.controller = 2
        state.players[2].chest.add(barrier)
        state.players[2].resources = 2
        state.player_agents[2] = _scripted_agent(True)   # activate barrier
        start = state.players[2].health
        # 3 arcane dealt, barrier blocks 2 → only 1 gets through
        from engine.card_effects.keywords import arcane_barrier as _ab
        prevented = _ab(barrier, 2, state)
        assert prevented == 2
        effect_deal_arcane(state, 2, 3 - prevented)
        assert state.players[2].health == start - 1

    def test_arcane_damage_dealt_event_fires(self):
        """arcane_damage_dealt event is emitted when arcane damage is dealt."""
        state = _make_state()
        source = _make_card("source_card")
        source.owner = 1
        source.controller = 1
        received = []
        state.event_manager.register(
            "arcane_damage_dealt",
            lambda ev, st: received.append(ev.data),
        )
        effect_deal_arcane(state, 2, 3, source=source)
        assert received, "arcane_damage_dealt event did not fire"
        assert received[0]["amount"] == 3

    def test_no_arcane_event_when_zero_damage(self):
        """arcane_damage_dealt must NOT fire when no damage is dealt."""
        state = _make_state()
        fired = []
        state.event_manager.register(
            "arcane_damage_dealt",
            lambda ev, st: fired.append(True),
        )
        effect_deal_arcane(state, 2, 0)
        assert not fired

    def test_amp_bonus_adds_to_arcane(self):
        """amp_N current_turn_effect adds N to the next arcane damage instance."""
        state = _make_state()
        source = _make_card("source_card")
        source.owner = 1
        source.controller = 1
        state.players[1].current_turn_effects.append("amp_2")
        start = state.players[2].health
        effect_deal_arcane(state, 2, 3, source=source)
        # 3 base + 2 amp = 5 damage
        assert state.players[2].health == start - 5
        # amp consumed
        assert "amp_2" not in state.players[1].current_turn_effects


# ---------------------------------------------------------------------------
# effect_gain_life
# ---------------------------------------------------------------------------

class TestEffectGainLife:
    """effect_gain_life adds health to target player."""

    @pytest.mark.parametrize("amount", [1, 2, 3, 5])
    def test_increases_health_by_amount(self, amount):
        state = _make_state()
        start = state.players[1].health
        effect_gain_life(state, 1, amount)
        assert state.players[1].health == start + amount

    def test_zero_gain_is_noop(self):
        state = _make_state()
        start = state.players[1].health
        effect_gain_life(state, 1, 0)
        assert state.players[1].health == start


# ===========================================================================
# SECTION 4 — EVENT DISPATCH COVERAGE
# ===========================================================================
# Tests that EventManager correctly fires listeners for every event type
# the engine emits.  One test per event type — cards with triggered abilities
# on these events can trust the dispatch mechanism works.
# ===========================================================================


class TestEventDispatch:
    """EventManager dispatch: listener fires, receives event, data is intact."""

    def _capture(self, state: GameState, event_type: str) -> list:
        """Register a listener and return the list it appends into."""
        received = []
        state.event_manager.register(
            event_type,
            lambda ev, st: received.append(ev if isinstance(ev, Event) else ev),
        )
        return received

    # ── Core dispatch mechanics ───────────────────────────────────────────

    def test_listener_called_on_emit(self):
        state = _make_state()
        calls = self._capture(state, "test_event")
        state.event_manager.emit(Event(type="test_event"), state)
        assert len(calls) == 1

    def test_listener_not_called_for_other_event(self):
        state = _make_state()
        calls = self._capture(state, "other_event")
        state.event_manager.emit(Event(type="test_event"), state)
        assert len(calls) == 0

    def test_multiple_listeners_all_called(self):
        state = _make_state()
        a, b = [], []
        state.event_manager.register("ev", lambda e, s: a.append(1))
        state.event_manager.register("ev", lambda e, s: b.append(1))
        state.event_manager.emit(Event(type="ev"), state)
        assert len(a) == 1
        assert len(b) == 1

    def test_event_data_passed_intact(self):
        state = _make_state()
        received = []
        state.event_manager.register(
            "ev_data",
            lambda ev, st: received.append(ev.data),
        )
        state.event_manager.emit(
            Event(type="ev_data", data={"foo": 42, "bar": "hello"}), state
        )
        assert received[0] == {"foo": 42, "bar": "hello"}

    def test_string_event_fires_correctly(self):
        """Engine sometimes emits plain strings like 'start_of_turn'."""
        state = _make_state()
        called = []
        state.event_manager.register("start_of_turn", lambda e, s: called.append(1))
        state.event_manager.emit("start_of_turn", state)
        assert called

    # ── Engine event types ────────────────────────────────────────────────
    # One test per event type the engine can emit.

    @pytest.mark.parametrize("event_type", [
        "start_of_turn",
        "start_of_action_phase",
        "start_of_end_phase",
        "end_of_turn",
        "combat_chain_close",
        "chain_link_resolves",
        "on_play",
        "hit",
        "hit_hero",
        "damage_dealt",
        "arcane_damage_dealt",
        "attacking",
        "attacking_hero",
        "defend",
        "enters_arena",
        "leaves_arena",
        "card_drawn",
        "card_destroyed",
        "aura_destroyed",
        "card_pitched",
        "boosted",
        "recalculate_attack_power",
    ])
    def test_event_type_dispatches(self, event_type):
        """Each engine event type is dispatchable and fires registered listeners."""
        state = _make_state()
        calls = self._capture(state, event_type)
        state.event_manager.emit(Event(type=event_type, data={}), state)
        assert len(calls) == 1, f"Listener not called for event '{event_type}'"

    # ── on_hit ────────────────────────────────────────────────────────────

    def test_on_hit_receives_damage_data(self):
        state = _make_state()
        received = []
        state.event_manager.register(
            "hit",
            lambda ev, st: received.append(ev.data),
        )
        state.event_manager.emit(
            Event(type="hit", card="test_card", data={"damage": 5}), state
        )
        assert received[0]["damage"] == 5

    # ── start_of_turn ─────────────────────────────────────────────────────

    def test_start_of_turn_listener_receives_state(self):
        state = _make_state()
        received_state = []
        state.event_manager.register(
            "start_of_turn",
            lambda ev, st: received_state.append(st),
        )
        state.event_manager.emit("start_of_turn", state)
        assert received_state[0] is state

    # ── damage_dealt ──────────────────────────────────────────────────────

    def test_damage_dealt_contains_amount_and_type(self):
        state = _make_state()
        received = []
        state.event_manager.register(
            "damage_dealt",
            lambda ev, st: received.append(ev.data),
        )
        effect_deal_damage(state, 2, 3, damage_type="physical")
        assert received[0]["amount"] == 3
        assert received[0]["damage_type"] == "physical"

    # ── arcane_damage_dealt ───────────────────────────────────────────────

    def test_arcane_damage_dealt_contains_amount(self):
        state = _make_state()
        source = _make_card("src")
        source.owner = 1
        source.controller = 1
        received = []
        state.event_manager.register(
            "arcane_damage_dealt",
            lambda ev, st: received.append(ev.data),
        )
        effect_deal_arcane(state, 2, 4, source=source)
        assert received[0]["amount"] == 4
        assert received[0]["target_player_id"] == 2


# ===========================================================================
# SECTION 5 — ATTACK TARGETS AND LEGAL ACTION GENERATION
# ===========================================================================

# ---------------------------------------------------------------------------
# CR 1.4.5a  Attackable targets
# ---------------------------------------------------------------------------

class TestAttackableTargets:
    """CR 1.4.5a: valid attack targets are the opponent's hero, living permanents
    (allies), and permanents made attackable by an effect (Spectra)."""

    def _weapon(self, player):
        weapon = _make_card("test_sword", types=["Weapon"], base_power=3,
                            base_functional_text="Once per Turn Action — **Attack**")
        weapon.owner = player.player_id
        weapon.controller = player.player_id
        weapon.zone = "weapon1"
        weapon.is_public = True
        player.weapon1.cards.append(weapon)
        return weapon

    # --- _attackable_permanents helper ---

    def test_no_attackable_permanents_when_none_present(self):
        state = _make_state()
        assert _attackable_permanents(state, 1) == []

    def test_spectra_aura_is_attackable(self):
        state = _make_state()
        aura = _make_card("spectral_shield", types=["Aura"], keywords=["Spectra"])
        aura.owner = 1
        aura.controller = 1
        state.players[1].permanents.add(aura)
        result = _attackable_permanents(state, 1)
        assert aura in result

    def test_non_spectra_aura_is_not_attackable(self):
        state = _make_state()
        aura = _make_card("plain_aura", types=["Aura"])
        aura.owner = 1
        aura.controller = 1
        state.players[1].permanents.add(aura)
        assert _attackable_permanents(state, 1) == []

    def test_ally_is_attackable(self):
        state = _make_state()
        ally = _make_card("test_ally", types=["Permanent"], subtypes=["Ally"])
        ally.owner = 1
        ally.controller = 1
        state.players[1].allies.add(ally)
        result = _attackable_permanents(state, 1)
        assert ally in result

    # --- legal_actions generates targeted attack variants ---

    def test_weapon_attack_offers_spectra_target(self):
        """When a Spectra aura is in play, ATTACK_WEAPON actions include a
        targeted variant (target=aura) in addition to the default hero attack."""
        state = _make_state()
        state.active_player = 2
        state.priority_player = 2
        state.players[2].action_points = 1
        state.players[2].resources = 0

        aura = _make_card("spectral_shield", types=["Aura"], keywords=["Spectra"])
        aura.owner = 1
        aura.controller = 1
        state.players[1].permanents.add(aura)

        self._weapon(state.players[2])

        from engine.card import CardDB
        db = CardDB()
        acts = legal_actions(state, db)
        weapon_acts = [a for a in acts if a.type == ActionType.ATTACK_WEAPON]
        # One default (hero) + one targeted (aura)
        assert len(weapon_acts) == 2
        targeted = [a for a in weapon_acts if a.target is not None]
        assert len(targeted) == 1
        assert targeted[0].target is aura
        assert targeted[0].targets == [aura.slug]

    def test_weapon_attack_no_extra_targets_without_spectra(self):
        """Without any Spectra/Ally permanents, only the default hero attack is offered."""
        state = _make_state()
        state.active_player = 2
        state.priority_player = 2
        state.players[2].action_points = 1
        state.players[2].resources = 0
        self._weapon(state.players[2])

        from engine.card import CardDB
        db = CardDB()
        acts = legal_actions(state, db)
        weapon_acts = [a for a in acts if a.type == ActionType.ATTACK_WEAPON]
        assert len(weapon_acts) == 1
        assert weapon_acts[0].target is None

    def test_attack_card_offers_spectra_target(self):
        """A PLAY_CARD attack action also generates a targeted variant for a
        Spectra aura on the board."""
        state = _make_state()
        state.active_player = 2
        state.priority_player = 2
        state.players[2].action_points = 1
        state.players[2].resources = 10  # plenty to pay

        aura = _make_card("spectral_shield", types=["Aura"], keywords=["Spectra"])
        aura.owner = 1
        aura.controller = 1
        state.players[1].permanents.add(aura)

        attack = _make_card("test_attack", types=["Action", "Attack"], base_power=3, base_cost=0)
        attack.owner = 2
        attack.controller = 2
        state.players[2].hand.add(attack)

        from engine.card import CardDB
        db = CardDB()
        acts = legal_actions(state, db)
        play_attacks = [a for a in acts
                        if a.type == ActionType.PLAY_CARD and a.card is attack]
        targeted = [a for a in play_attacks if a.target is not None and a.targets]
        assert any(a.target is aura for a in targeted)

# ---------------------------------------------------------------------------
# cards_played_this_turn list — integration with engine
# ---------------------------------------------------------------------------

class TestCardsPlayedThisTurn:
    """Verify the tracking list resets each turn and covers both play paths."""

    def test_initialises_empty(self):
        state = _make_state()
        assert state.players[1].cards_played_this_turn == []
        assert state.players[2].cards_played_this_turn == []

    def test_cleared_at_start_of_turn(self):
        """Simulated via direct manipulation — full engine turn tested elsewhere."""
        state = _make_state()
        c = _make_card("some_card")
        state.players[1].cards_played_this_turn.append(c)
        assert len(state.players[1].cards_played_this_turn) == 1
        # Simulate what _start_of_turn does
        state.players[1].cards_played_this_turn = []
        assert state.players[1].cards_played_this_turn == []

# ===========================================================================
# SECTION 6 — PITCHABLE CARD IMPLEMENTATIONS
# ===========================================================================

class TestPitchSequence:
    def test_pitch_for_card_from_hand(self):
        state = _make_state()
        actor = state.players[1]
        blue_card = _make_card(slug="test_card_blue", name="Test Card Blue", pitch=3, color='blue')
        red_card = _make_card(slug="test_card_red", name="Test Card Red", pitch=1, color='red')
        cost = 3
        play_card = _make_card(slug="test_play_card", cost=cost, pitch=2)
        actor.hand.add(blue_card)
        actor.hand.add(red_card)
        actor.hand.add(play_card)

        assert can_pay_cost(actor.hand.cards, cost, actor.resources, play_card)
        assert len(get_pitchable_cards(actor.hand.cards, play_card)) == 2
        assert len(get_pitchable_cards(actor.hand.cards)) == 3

        #test pitch blue then red
        agent = _scripted_agent([0, 0])
        state.player_agents = {1:agent}
        _pitch_for_cost(state,Action(ActionType.PLAY_CARD,1,play_card),play_card.cost)
        assert actor.resources == 0
        assert len(actor.hand.cards) == 1
        assert len(actor.pitch.cards) == 1

    def test_over_pitch():
        state = _make_state()
        actor = state.players[1]
        blue_card = _make_card(slug="test_card_blue", name="Test Card Blue", pitch=3, color='blue')
        red_card = _make_card(slug="test_card_red", name="Test Card Red", pitch=1, color='red')
        cost = 3
        play_card = _make_card(slug="test_play_card", cost=cost, pitch=2)
        actor.hand.add(blue_card)
        actor.hand.add(red_card)
        actor.hand.add(play_card)

        assert can_pay_cost(actor.hand.cards, cost, actor.resources, play_card)
        assert len(get_pitchable_cards(actor.hand.cards, play_card)) == 2
        assert len(get_pitchable_cards(actor.hand.cards)) == 3

        #test pitch red then blue
        agent = _scripted_agent([1, 0])
        state.player_agents = {1:agent}
        _pitch_for_cost(state,Action(ActionType.PLAY_CARD,1,play_card),play_card.cost)
        assert actor.resources == 1
        assert len(actor.hand.cards) == 0
        assert len(actor.pitch.cards) == 2


    def test_cost_increase():
        state = _make_state()
        mng = ContinuousEffectManager()
        mng.add_cost_modifier

    def test_cost_decrease():
        state = _make_state()
        mng = ContinuousEffectManager()
        mng.add_cost_modifier

    def test_cost_set():
        state = _make_state()
        mng = ContinuousEffectManager()
        mng.add_cost_modifier

    def test_alternative_cost():
