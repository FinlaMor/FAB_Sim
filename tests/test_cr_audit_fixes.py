"""Behavioral tests for the CR audit fixes (docs/cr_audit_2026-07.md).

Covers:
- H1: a card's resolution abilities fire when its layer RESOLVES on the stack
  (CR 5.3.4), not at announce — and the resolved layer is cleared to its
  owner's graveyard (CR 5.3.7 / 3.0.12).
- AR/DR playability during the Reaction Step (Step-enum comparison bug).
- 7.4.2d / 8.1.3b: a resolved defense reaction becomes a defending card.
- 8.3.4b: Dominate blocks DRs from hand once a hand card has defended.
- M1 / CR 7.2.2: the chain closes when the declared attack target is gone.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import engine.engine as E
from engine.actions import Action, ActionType
from engine.card import Card, CardDB
from engine.play import apply_action, available_actions
from engine.state import CombatState, StackEntry, Step
from tests.conftest import _make_state

DB = CardDB()


def _card(slug: str, owner: int) -> Card:
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, f"missing card {slug}"
    c.owner = owner
    c.controller = owner
    return c


def _attack_stub(owner: int = 1) -> Card:
    atk = Card(slug="test_attack", raw_name="Test Attack",
               raw_types=["Action"])
    atk.types = ["Action"]
    atk.subtypes = ["Attack"]
    atk.owner = owner
    atk.controller = owner
    return atk


def _reaction_state(dr_holder: int = 2):
    """Combat in the Reaction Step: player 1 attacking player 2's hero."""
    st = _make_state()
    st.card_db = DB
    atk = _attack_stub(1)
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=4,
                            attack_card=atk, keywords=[], from_weapon=False)
    st.step = Step.COMBAT_REACTION
    st.active_player = 1
    st.priority_player = dr_holder
    return st


# ---------------------------------------------------------------------------
# H1 — resolution at stack resolution, then cleared to graveyard
# ---------------------------------------------------------------------------

def test_play_effects_resolve_at_stack_resolution_not_announce():
    st = _make_state()
    st.card_db = DB
    p1 = st.players[1]
    st.step = Step.ACTION
    st.active_player = 1
    st.priority_player = 1
    card = _card("visit_goldmane_estate_blue", 1)
    p1.hand.add(card)
    p1.action_points = 1
    p1.resources = 5

    act = Action(type=ActionType.PLAY_CARD, card=card)
    act.player_id = 1
    apply_action(st, act)

    # Announce: the layer is on the stack; effects have NOT been generated yet.
    assert len(st.stack_entries) == 1
    assert p1.items.find("gold") is None
    ap_after_paying = p1.action_points

    E.resolve_stack(st)

    # Resolution: Gold created; +1 AP from the card's effect and +1 from its
    # printed Go Again (CR 5.3.5 — granted at layer resolution).
    assert p1.items.find("gold") is not None
    assert p1.action_points == ap_after_paying + 2
    # CR 5.3.7 / 3.0.12: the resolved card-layer is cleared to the graveyard.
    assert card in p1.graveyard.cards
    assert card not in st.stack.cards


# ---------------------------------------------------------------------------
# Reaction Step playability (Step-enum bug) + DR resolution behavior
# ---------------------------------------------------------------------------

def test_defense_reaction_offered_and_becomes_defending_on_resolution():
    st = _reaction_state(dr_holder=2)
    dr = _card("inertia_trap_red", 2)
    st.players[2].hand.add(dr)
    st.players[2].resources = 3

    acts = available_actions(st, 2)
    dr_plays = [a for a in acts
                if a.type == ActionType.PLAY_CARD and a.card is dr]
    assert dr_plays, "defense reaction must be offered during the Reaction Step"

    act = dr_plays[0]
    act.player_id = 2
    apply_action(st, act)

    # The DR resolves as a layer (CR 7.4.2d) — not a defender at announce.
    assert dr not in st.combat.defending_cards

    E.resolve_stack(st)

    assert dr in st.combat.defending_cards
    assert st.combat.defender_used_hand_card is True
    assert st.combat.total_defense >= (dr.defense or 0)
    # It moved to the chain, so it must NOT have been cleared to the graveyard.
    assert dr not in st.players[2].graveyard.cards


def test_attack_reaction_offered_to_attacker_in_reaction_step():
    st = _reaction_state(dr_holder=2)
    st.priority_player = 1
    ar = _card("scar_tissue_red", 1)
    st.players[1].hand.add(ar)
    st.players[1].resources = 5

    acts = available_actions(st, 1)
    assert any(a.type == ActionType.PLAY_CARD and a.card is ar for a in acts), \
        "attack reaction must be offered to the attacker during the Reaction Step"


def test_defense_reaction_not_offered_to_attacker():
    st = _reaction_state(dr_holder=2)
    st.priority_player = 1
    dr = _card("inertia_trap_red", 1)
    st.players[1].hand.add(dr)
    st.players[1].resources = 3

    acts = available_actions(st, 1)
    assert not any(a.type == ActionType.PLAY_CARD and a.card is dr for a in acts)


def test_dominate_blocks_dr_from_hand():
    st = _reaction_state(dr_holder=2)
    st.combat.keywords = ["Dominate"]
    st.combat.defender_used_hand_card = True
    dr = _card("inertia_trap_red", 2)
    st.players[2].hand.add(dr)
    st.players[2].resources = 3

    acts = available_actions(st, 2)
    assert not any(a.type == ActionType.PLAY_CARD and a.card is dr for a in acts), \
        "CR 8.3.4b: Dominate blocks defense reactions from hand"


# ---------------------------------------------------------------------------
# M1 — CR 7.2.2: declared attack target gone → chain closes
# ---------------------------------------------------------------------------

def test_attack_step_closes_chain_when_declared_target_gone():
    st = _make_state()
    st.card_db = DB
    st.active_player = 1
    st.priority_player = 1
    atk = _attack_stub(1)
    st.stack.add(atk)
    entry = StackEntry(player_id=1, card=atk, layer_type="card",
                       declared_targets=["spectral_shield"])

    E._attack_step(st, atk, entry=entry)

    assert st.step == Step.COMBAT_CLOSE
    assert st.combat is None
    # CR 7.7.3: the attack on the stack is put into its owner's graveyard.
    assert atk in st.players[1].graveyard.cards
    assert atk not in st.stack.cards


# ---------------------------------------------------------------------------
# CR 1.8.5 — "Target attack with stealth": no legal target => illegal to play
# ---------------------------------------------------------------------------

def test_targeted_attack_reaction_requires_legal_target():
    st = _reaction_state(dr_holder=2)
    st.priority_player = 1  # attacker's reaction window
    ar = _card("stains_of_the_redback_red", 1)
    st.players[1].hand.add(ar)
    st.players[1].resources = 5

    # Hunter's Klaive-style attack WITHOUT stealth: Stains may not be played.
    acts = available_actions(st, 1)
    assert not any(a.type == ActionType.PLAY_CARD and a.card is ar for a in acts), \
        "'Target attack with stealth' must be unplayable vs a non-stealth attack"

    # The same attack WITH stealth: Stains becomes playable.
    st.combat.keywords = ["Stealth"]
    st.combat.attack_card.keywords = ["Stealth"]
    acts = available_actions(st, 1)
    assert any(a.type == ActionType.PLAY_CARD and a.card is ar for a in acts), \
        "'Target attack with stealth' must be playable vs a stealth attack"


# ---------------------------------------------------------------------------
# CR 1.3.1b — controller is set on arena entry (incl. defending); activated
# abilities of equipment/permanents and "attack action card you control"
# targeting (attacking AND defending).
# ---------------------------------------------------------------------------

def test_controller_set_on_permanent_arena_entry():
    st = _make_state()
    st.card_db = DB
    tok = _card("gold", 1)
    tok.controller = None
    st.players[1].items.add(tok)
    assert tok.controller == 1  # CR 1.3.1b: owner as it enters the arena


def test_controller_set_when_played():
    st = _make_state(); st.card_db = DB
    st.step = Step.ACTION; st.active_player = 1; st.priority_player = 1
    card = _card("visit_goldmane_estate_blue", 1)
    card.controller = None
    st.players[1].hand.add(card)
    st.players[1].action_points = 1; st.players[1].resources = 5
    act = Action(type=ActionType.PLAY_CARD, card=card); act.player_id = 1
    apply_action(st, act)
    assert card.controller == 1


def test_controller_set_on_defend():
    from engine.play import _apply_defend
    st = _reaction_state(dr_holder=2)  # p1 attacking p2
    blk = _card("big_bully_red", 2)
    blk.controller = None
    st.players[2].hand.add(blk)
    _apply_defend(st, Action(type=ActionType.DEFEND_CARDS, card_list=[blk]))
    assert blk.controller == 2
    assert blk in st.combat.defending_cards


def test_equipment_activated_ability_offered():
    st = _make_state(); st.card_db = DB
    st.step = Step.ACTION; st.active_player = 1; st.priority_player = 1
    scab = _card("scabskin_leathers", 1)
    st.players[1].legs.add(scab)
    st.players[1].action_points = 1
    acts = available_actions(st, 1)
    assert any(a.type == ActionType.ACTIVATE_CARD and a.card is scab for a in acts), \
        "equipment activated ability (Scabskin Leathers) must be offered"


def test_kayo_instant_offered_when_attacking_own_action_attack():
    import copy
    st = _make_state(); st.card_db = DB
    kayo = copy.deepcopy(DB.get("kayo_underhanded_cheat")); kayo.owner = 1; kayo.controller = 1
    st.players[1].hero = kayo
    st.players[1].resources = 4
    atk = _card("command_and_conquer_red", 1)  # an attack action card
    atk.controller = 1
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=6,
                            attack_card=atk, keywords=[])
    st.step = Step.COMBAT_REACTION; st.active_player = 1; st.priority_player = 1
    acts = available_actions(st, 1)
    assert any(a.card is kayo for a in acts if a.type == ActionType.ACTIVATE_CARD)


def test_kayo_instant_offered_and_targets_defending_action_attack():
    import copy
    from engine.play import _apply_defend
    from engine.card_effects.dsl import dispatch
    st = _make_state(); st.card_db = DB
    kayo = copy.deepcopy(DB.get("kayo_underhanded_cheat")); kayo.owner = 2; kayo.controller = 2
    st.players[2].hero = kayo
    st.players[2].resources = 4
    opp_atk = _card("mocking_blow_red", 1); opp_atk.controller = 1  # base power != 6
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=opp_atk.base_power or 0,
                            attack_card=opp_atk, keywords=[])
    opp_base_before = opp_atk.base_power
    blk = _card("big_bully_red", 2)  # Kayo defends with an attack action card
    st.players[2].hand.add(blk)
    _apply_defend(st, Action(type=ActionType.DEFEND_CARDS, card_list=[blk]))
    st.step = Step.COMBAT_REACTION; st.active_player = 1; st.priority_player = 2
    acts = available_actions(st, 2)
    assert any(a.card is kayo for a in acts if a.type == ActionType.ACTIVATE_CARD), \
        "Kayo's instant must be offered when defending with an attack action card"
    # Resolving sets the defending card's base power to 6 (not the opponent's attack).
    dispatch(st, "ON_ACTIVATE", "kayo_underhanded_cheat", card=kayo)
    assert blk.base_power == 6
    assert opp_atk.base_power == opp_base_before  # opponent's attack untouched


# ---------------------------------------------------------------------------
# On-attack power buff (MODIFY_ATTACK) persists through later combat steps.
# Reckless Arithmetic: "When this attacks, roll a d6. This gets +X{p}." The
# buff was lost at the defend step because it was a transient bump that
# _recalculate_attack_power overwrote (now recorded on combat.power_mods).
# ---------------------------------------------------------------------------

def test_modify_attack_buff_persists_through_recalculation():
    import copy
    from engine.state import CombatState
    from engine.card_effects.dsl import dispatch
    st = _make_state(); st.card_db = DB
    atk = _card("reckless_arithmetic_blue", 1)
    base = atk.base_power or 0
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=base,
                            base_attack_power=base, attack_card=atk, keywords=[])
    st.active_player = 1
    dispatch(st, "ON_PLAY", "reckless_arithmetic_blue", card=atk,
             event=type("E", (), {"type": "on_play", "data": {}})())
    after_attack = st.combat.attack_power
    assert after_attack > base, "roll buff must raise the attack's power"
    assert st.combat.power_mods, "the buff must be recorded on combat.power_mods"

    # Later combat steps recalculate power — the buff must survive.
    E._recalculate_attack_power(st)   # defend step
    assert st.combat.attack_power == after_attack
    E._recalculate_attack_power(st)   # damage step
    assert st.combat.attack_power == after_attack


def test_set_base_power_stacks_with_roll_buff():
    """Kayo sets BASE power to 6; Reckless Arithmetic's rolled +X{p} (a stage-8
    modifier) must apply on top, not be overwritten. Base 6 + rolled X."""
    import copy
    from engine.state import CombatState
    from engine.card_effects.dsl import dispatch
    st = _make_state(); st.card_db = DB
    kayo = copy.deepcopy(DB.get("kayo_underhanded_cheat")); kayo.owner = 1; kayo.controller = 1
    st.players[1].hero = kayo
    atk = _card("reckless_arithmetic_blue", 1)
    base = atk.base_power or 0
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=base,
                            base_attack_power=base, attack_card=atk, keywords=[])
    st.active_player = 1
    dispatch(st, "ON_PLAY", "reckless_arithmetic_blue", card=atk,
             event=type("E", (), {"type": "on_play", "data": {}})())
    roll = st.combat.power_mods[0][1]
    dispatch(st, "ON_ACTIVATE", "kayo_underhanded_cheat", card=kayo)
    assert atk.base_power == 6
    assert st.combat.attack_power == 6 + roll, "base set to 6, roll buff on top"
    E._recalculate_attack_power(st)  # defend step: still base 6 + roll
    assert st.combat.attack_power == 6 + roll


def test_activation_cost_ignores_resource_symbols_in_effect_text():
    """The resource cost of an activated ability is the {r} in its COST portion
    only (between the dash and the colon), not {r} in the EFFECT. Fyendal's
    Spring Tunic ("Remove 3 energy counters: Gain {r}") costs 0 resources, not 1."""
    assert DB.get("fyendals_spring_tunic").activation_cost in (None, 0)
    assert DB.get("scabskin_leathers").activation_cost in (None, 0)  # cost is "0"
    assert DB.get("kayo_underhanded_cheat").activation_cost == 4     # {r}{r}{r}{r}
    assert DB.get("hunters_klaive").activation_cost == 2             # weapon attack {r}{r}


def test_fyendals_spring_tunic_activates_for_zero_resources():
    import copy
    st = _make_state(); st.card_db = DB
    st.step = Step.ACTION; st.active_player = 1; st.priority_player = 1
    c = copy.deepcopy(DB.get("fyendals_spring_tunic")); c.owner = 1; c.controller = 1
    st.players[1].chest.add(c)
    st.players[1].counters[(c.slug, "chest", "energy")] = 3
    st.players[1].resources = 0
    acts = available_actions(st, 1)
    tunic = [a for a in acts
             if getattr(a.card, "slug", None) == "fyendals_spring_tunic"
             and a.type == ActionType.ACTIVATE_CARD]
    assert tunic, "Fyendal's Spring Tunic instant must be offered at 0 resources"
    act = tunic[0]; act.player_id = 1
    apply_action(st, act)
    assert st.players[1].resources == 1                       # gained {r}
    assert st.players[1].counters[(c.slug, "chest", "energy")] == 0  # paid 3 energy


# ---------------------------------------------------------------------------
# Apex Bonebreaker: "When this defends together with a card with 6+ {p}, create
# a Might." Fires only with a 6+ power co-defender; exactly one Might.
# ---------------------------------------------------------------------------

def _n_might(p):
    seen = set()
    for z in (p.auras, p.items, p.permanents, p.tokens):
        for c in z.cards:
            if c.slug == "might":
                seen.add(id(c))
    return len(seen)


def _apex_defense(codefender_slug):
    import copy
    from engine.state import CombatState
    from engine.play import _apply_defend
    st = _make_state(); st.card_db = DB
    E._setup_dsl_listeners(st)
    apex = copy.deepcopy(DB.get("apex_bonebreaker")); apex.owner = 2; apex.controller = 2
    st.players[2].arms.add(apex)
    cards = [apex]
    if codefender_slug:
        co = _card(codefender_slug, 2); co.zone = "hand"
        st.players[2].hand.add(co); cards.append(co)
    opp = _card("mocking_blow_red", 1)
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=8,
                            attack_card=opp, keywords=[])
    st.active_player = 1
    _apply_defend(st, Action(type=ActionType.DEFEND_CARDS, card_list=cards))
    return st


def test_apex_bonebreaker_requires_6power_codefender():
    assert _n_might(_apex_defense(None).players[2]) == 0            # alone
    assert _n_might(_apex_defense("mocking_blow_red").players[2]) == 0  # 4-power co-defender
    st = _apex_defense("command_and_conquer_red")                  # 6-power co-defender
    assert _n_might(st.players[2]) == 1                            # exactly one Might


def test_snapshot_does_not_double_list_typed_permanents():
    from engine.recorder import snapshot_state
    st = _apex_defense("command_and_conquer_red")
    snap = snapshot_state(st)["players"][2]
    assert "might" in snap["auras"]
    assert "might" not in snap["permanents"], "aura token must not appear under permanents too"


def test_instant_card_costs_zero_action_points():
    import copy
    st = _make_state(); st.card_db = DB
    st.step = Step.ACTION; st.active_player = 1; st.priority_player = 1
    sig = copy.deepcopy(DB.get("sigil_of_solace_red")); sig.owner = 1; sig.controller = 1; sig.zone = "hand"
    st.players[1].hand.add(sig)
    st.players[1].action_points = 1; st.players[1].resources = 5
    plays = [a for a in available_actions(st, 1)
             if getattr(a.card, "slug", None) == "sigil_of_solace_red"
             and a.type == ActionType.PLAY_CARD]
    assert plays, "instant must be playable"
    act = plays[0]; act.player_id = 1
    apply_action(st, act)
    assert st.players[1].action_points == 1, "an Instant costs 0 AP (CR 5.1.6b)"


# ---------------------------------------------------------------------------
# Quickdodge Flexors: legs equipment with an activated DEFENSE_REACTION
# ("Defense Reaction - {r}: Add this to the active chain link as a defending
# card. It has 2 base {d} this chain link."). Must be offered to the defender
# during the reaction step and add itself as a defender.
# ---------------------------------------------------------------------------

def _quickdodge_reaction_state():
    import copy
    from engine.state import CombatState
    st = _make_state(); st.card_db = DB
    E._setup_dsl_listeners(st)
    qd = copy.deepcopy(DB.get("quickdodge_flexors")); qd.owner = 2; qd.controller = 2
    st.players[2].legs.add(qd)
    st.players[2].resources = 1
    opp = _card("mocking_blow_red", 1)
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=4,
                            attack_card=opp, keywords=[])
    st.step = Step.COMBAT_REACTION; st.active_player = 1; st.priority_player = 2
    return st, qd


def test_quickdodge_flexors_offered_to_defender_and_defends():
    st, qd = _quickdodge_reaction_state()
    acts = available_actions(st, 2)
    plays = [a for a in acts
             if getattr(a.card, "slug", None) == "quickdodge_flexors"
             and a.type == ActionType.ACTIVATE_CARD]
    assert plays, "Quickdodge's defense reaction must be offered to the defender"
    # Not offered to the attacker.
    assert not any(getattr(a.card, "slug", None) == "quickdodge_flexors"
                   for a in available_actions(st, 1))
    act = plays[0]; act.player_id = 2
    apply_action(st, act)
    assert qd in st.combat.defending_cards
    assert qd.defense == 2
    assert st.combat.total_defense >= 2
    assert st.players[2].resources == 0  # paid {r}


def test_quickdodge_flexors_self_destructs_at_end_phase_if_it_defended():
    st, qd = _quickdodge_reaction_state()
    st.players[2].current_turn_effects.append("quickdodge_defended")
    st.event_manager.emit("start_of_end_phase", st)
    E._resolve_all_triggers(st)
    assert qd not in st.players[2].legs.cards
    assert any(c.slug == "quickdodge_flexors" for c in st.players[2].graveyard.cards)
