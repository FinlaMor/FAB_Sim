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


def test_action_speed_activated_ability_costs_one_ap():
    # CR 5.1.6b: Scabskin Leathers' "Once per turn Action" activated ability is
    # action-speed, so activating it costs 1 action point — even though its
    # printed functional_text is absent from the card DB (the DSL ability_type
    # ACTIVATE is authoritative). Regression: previously charged 0 AP.
    from engine.play import _pay_costs
    st = _make_state(); st.card_db = DB
    st.step = Step.ACTION; st.active_player = 1; st.priority_player = 1
    scab = _card("scabskin_leathers", 1)
    st.players[1].legs.add(scab)
    st.players[1].action_points = 1
    acts = [a for a in available_actions(st, 1)
            if a.type == ActionType.ACTIVATE_CARD and a.card is scab]
    assert acts, "Scabskin's activated ability must be offered"
    act = acts[0]; act.player_id = 1
    # Isolate the action-point *cost* from the ability's AP *gain*.
    _pay_costs(st, 1, act)
    assert st.players[1].action_points == 0, \
        "an action-speed activated ability costs 1 AP (CR 5.1.6b)"


def test_instant_speed_activated_ability_costs_zero_ap():
    # Fyendal's Spring Tunic is an INSTANT-speed activated ability: 0 AP.
    import copy
    from engine.play import _pay_costs
    st = _make_state(); st.card_db = DB
    st.step = Step.ACTION; st.active_player = 1; st.priority_player = 1
    tunic = copy.deepcopy(DB.get("fyendals_spring_tunic"))
    tunic.owner = 1; tunic.controller = 1
    st.players[1].items.add(tunic)
    st.players[1].counters[(tunic.slug, tunic.zone, "energy")] = 3
    st.players[1].action_points = 1
    acts = [a for a in available_actions(st, 1)
            if a.type == ActionType.ACTIVATE_CARD
            and getattr(a.card, "slug", None) == "fyendals_spring_tunic"]
    assert acts, "Fyendal's Spring Tunic instant must be offered"
    act = acts[0]; act.player_id = 1
    _pay_costs(st, 1, act)
    assert st.players[1].action_points == 1, \
        "an instant-speed activated ability costs 0 AP (CR 5.1.6b)"


def test_activation_cost_and_per_turn_are_dsl_authoritative():
    # CR 1.7.3a / 4.4.3d: for implemented cards, the resource cost to activate
    # and the per-turn activation limit come from the DSL ('activation_cost' /
    # 'per_turn'), not from parsing printed text.
    cases = {
        "hunters_klaive": (2, True, 1),
        "millers_grindstone": (3, True, 1),
        "kayo_underhanded_cheat": (4, False, None),
        "scabskin_leathers": (0, True, 1),
        "savage_claw": (2, False, None),
    }
    for slug, (ac, pt, acts) in cases.items():
        c = _card(slug, 1)
        assert c.activation_cost == ac, f"{slug} activation_cost"
        assert c.has_per_turn_limit == pt, f"{slug} has_per_turn_limit"
        assert c.activations == acts, f"{slug} activations"


def test_gold_activation_does_not_double_charge_resources():
    # gold: "Action - {r}{r}, destroy this: Draw a card." The {r}{r} is the
    # DSL activation_cost; it must NOT also appear as a PAY_RESOURCES cost, or
    # the ability charges 4 (paid once by _pay_costs, once by _apply_activate).
    st = _make_state(); st.card_db = DB
    st.step = Step.ACTION; st.active_player = 1; st.priority_player = 1
    g = _card("gold", 1); st.players[1].permanents.add(g)
    st.players[1].resources = 5; st.players[1].action_points = 1
    acts = [a for a in available_actions(st, 1)
            if a.type == ActionType.ACTIVATE_CARD
            and getattr(a.card, "slug", None) == "gold"]
    assert acts, "gold activation must be offered"
    act = acts[0]; act.player_id = 1
    apply_action(st, act)
    assert st.players[1].resources == 3, \
        "gold costs exactly {r}{r} = 2 (regression: was double-charged to 4)"


def _rby_defend_state():
    """Combat in the defend step: player 1 attacking player 2."""
    from engine.card_effects.dsl.loader import load_all_cards
    load_all_cards()
    st = _make_state(); st.card_db = DB
    E._setup_dsl_listeners(st)
    atk = _attack_stub(1)
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=4,
                            attack_card=atk, keywords=[], from_weapon=False)
    st.step = Step.COMBAT_DEFEND; st.active_player = 1
    return st


def _defense_filler(slug, oid, owner=2):
    c = Card(slug=slug, raw_name=slug, raw_types=["Action"])
    c.subtypes = ["Attack"]; c.defense = 2; c.base_defense = 2
    c.owner = owner; c.controller = owner; c.object_id = oid
    return c


def test_right_behind_you_triggers_only_with_another_hand_card():
    # "When this defends together with ANOTHER card from hand, this gets +1{d}
    # ..." — must NOT trigger on a lone block, nor when the co-defender is not
    # from hand. (Regression: used to trigger on every defend, and used OPT.)
    from engine.play import _apply_defend

    def defend(card_list, setup):
        st = _rby_defend_state()
        for i in range(3):
            st.players[2].deck.add(_defense_filler(f"deckcard{i}", 900 + i))
        setup(st)
        act = Action(type=ActionType.DEFEND_CARDS, card_list=card_list)
        act.player_id = 2
        _apply_defend(st, act)
        return st

    # Positive: RBY + another hand card → RBY(2) + other(2) + trigger(+1) = 5.
    rby = _card("right_behind_you_blue", 2); rby.object_id = 10
    other = _defense_filler("filler_hand", 11)
    st = defend([rby, other], lambda s: (s.players[2].hand.add(rby),
                                         s.players[2].hand.add(other)))
    assert st.combat.total_defense == 5, "should get +1{d} with another hand co-defender"
    assert len(st.players[2].deck.cards) == 3, "look/bottom keeps deck size"

    # Negative: RBY alone (from hand) → no trigger, total = 2.
    rby2 = _card("right_behind_you_blue", 2); rby2.object_id = 20
    st = defend([rby2], lambda s: s.players[2].hand.add(rby2))
    assert st.combat.total_defense == 2, "lone block must not trigger"

    # Negative: RBY (hand) + a co-defender NOT from hand (arsenal) → no trigger.
    rby3 = _card("right_behind_you_blue", 2); rby3.object_id = 30
    ars = _defense_filler("arsenal_card", 31)
    st = defend([rby3, ars], lambda s: (s.players[2].hand.add(rby3),
                                        s.players[2].arsenal.add(ars)))
    assert st.combat.total_defense == 4, "arsenal co-defender is not 'from hand'"


def test_snarky_prick_reveals_red_top_destroys_and_pumps():
    # "When this attacks a hero, look at the top card of their deck. If it's red,
    # destroy it and this gets +4{p}." (Regression: was a PLAY-time banish.)
    from engine.card_effects.dsl import dispatch
    from engine.card_effects.dsl.loader import load_all_cards
    load_all_cards()

    def attack(top_slug, attack_target=None):
        st = _make_state(); st.card_db = DB
        snarky = _card("snarky_prick_red", 1)
        st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                                attack_card=snarky, keywords=[])
        st.combat.attack_target = attack_target
        top = _card(top_slug, 2)
        st.players[2].deck.add(top)
        st.players[2].deck.add(_card("sink_below_yellow", 2))  # non-red beneath
        dispatch(st, "ON_ATTACK", "snarky_prick_red", card=snarky, event=None)
        return st, top

    # Red top (pitch 1) → destroyed and attack pumped +4.
    st, red_top = attack("command_and_conquer_red")
    assert st.combat.attack_power == 7, "red top gives +4{p}"
    assert red_top not in st.players[2].deck.cards, "red top destroyed"
    assert red_top in st.players[2].graveyard.cards

    # Non-red top (pitch 3) → nothing happens.
    st, blue_top = attack("mocking_blow_blue")
    assert st.combat.attack_power == 3, "non-red top: no pump"
    assert blue_top in st.players[2].deck.cards, "non-red top not destroyed"

    # Attacking a non-hero target (e.g. an ally/aura) → does not trigger.
    dummy = _card("command_and_conquer_red", 2)
    st, red_top = attack("command_and_conquer_red", attack_target=dummy)
    assert st.combat.attack_power == 3, "only triggers when attacking a hero"
    assert red_top in st.players[2].deck.cards


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


# ---------------------------------------------------------------------------
# Savage Claw: "If a card with 6+ {p} was pitched to attack WITH THIS, the
# attack gets +1{p}." Must buff only Savage Claw's own attack, not any attack.
# ---------------------------------------------------------------------------

def _savage_claw_combat(attack_slug, pitched_power_slug):
    import copy
    from engine.state import CombatState
    st = _make_state(); st.card_db = DB
    E._setup_dsl_listeners(st)
    sc = copy.deepcopy(DB.get("savage_claw")); sc.owner = 1; sc.controller = 1
    st.players[1].weapon1.add(sc)
    atk = copy.deepcopy(DB.get(attack_slug)); atk.owner = 1; atk.controller = 1
    base = atk.power or 0
    pitched = [copy.deepcopy(DB.get(pitched_power_slug))] if pitched_power_slug else []
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=base,
                            base_attack_power=base, attack_card=atk, keywords=[],
                            from_weapon=True, pitched_for_attack=pitched)
    st.active_player = 1
    E._recalculate_attack_power(st)
    return st.combat.attack_power, base


def test_savage_claw_buffs_only_its_own_attack():
    # Savage Claw's own attack, 6-power card pitched -> +1
    power, base = _savage_claw_combat("savage_claw", "command_and_conquer_red")
    assert power == base + 1
    # Savage Claw's own attack, low-power pitch -> no buff
    power, base = _savage_claw_combat("savage_claw", "sink_below_red")
    assert power == base
    # A DIFFERENT weapon's attack (Miller's Grindstone) must NOT be buffed even
    # with a 6-power card pitched — the buff is "to attack WITH THIS".
    power, base = _savage_claw_combat("millers_grindstone", "command_and_conquer_red")
    assert power == base, "Savage Claw must not buff another weapon's attack"


# ---------------------------------------------------------------------------
# CR 7.3.2a: defense reaction cards can't be declared as blockers during the
# Defend Step (they're played in the Reaction Step). The card DB stores the
# type as "DefenseReaction" (no space), which a space-sensitive check missed.
# ---------------------------------------------------------------------------

def test_defense_reaction_not_declarable_as_blocker():
    import copy
    from engine.state import CombatState
    from engine.actions import get_defendable_cards
    st = _make_state(); st.card_db = DB
    opp = _card("mocking_blow_red", 1)
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=4,
                            attack_card=opp, keywords=[])
    st.active_player = 1
    dr = copy.deepcopy(DB.get("sink_below_red")); dr.owner = 2
    st.players[2].hand.add(dr)
    normal = copy.deepcopy(DB.get("command_and_conquer_red")); normal.owner = 2
    st.players[2].hand.add(normal)  # has defense, not a defense reaction
    slugs = [c.slug for c in get_defendable_cards(st)]
    assert "sink_below_red" not in slugs, "a defense reaction can't block in the Defend Step"
    assert "command_and_conquer_red" in slugs


def test_kayo_instant_target_is_the_controlled_card_not_the_active_attack():
    """When Kayo defends with an attack action card vs an opponent's weapon
    attack, the instant must offer the DEFENDING card as the target — not the
    opponent's active attack (a weapon, an illegal target)."""
    import copy
    from engine.state import CombatState
    from engine.play import _apply_defend
    st = _make_state(); st.card_db = DB
    E._setup_dsl_listeners(st)
    kayo = copy.deepcopy(DB.get("kayo_underhanded_cheat")); kayo.owner = 2; kayo.controller = 2
    st.players[2].hero = kayo; st.players[2].resources = 4
    miller = copy.deepcopy(DB.get("millers_grindstone")); miller.owner = 1; miller.controller = 1
    st.players[1].weapon1.add(miller)
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=4,
                            attack_card=miller, keywords=[], from_weapon=True)
    mb = copy.deepcopy(DB.get("mocking_blow_yellow")); mb.owner = 2; mb.zone = "hand"
    st.players[2].hand.add(mb)
    _apply_defend(st, Action(type=ActionType.DEFEND_CARDS, card_list=[mb]))
    st.step = Step.COMBAT_REACTION; st.active_player = 1; st.priority_player = 2

    kayo_acts = [a for a in available_actions(st, 2)
                 if getattr(a.card, "slug", None) == "kayo_underhanded_cheat"]
    targets = [getattr(a.target, "slug", None) for a in kayo_acts]
    assert "mocking_blow_yellow" in targets, "defending attack action card must be a target"
    assert "millers_grindstone" not in targets, "opponent's weapon must not be a target"

    apply_action(st, kayo_acts[0])
    assert mb.base_power == 6            # the declared target was set
    assert miller.base_power != 6        # the opponent's weapon was untouched
