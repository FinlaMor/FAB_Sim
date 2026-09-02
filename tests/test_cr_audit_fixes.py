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
    # you may destroy it. If you do, this gets +4{p}."
    # (Regression: was a PLAY-time banish. Default agents take the first option,
    # so this covers the accept branch; the decline branch is tested below.)
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


def test_ironfist_revelation_reveals_crush_card_and_powers_it():
    # "When this defends, you may turn a face-down card with crush in your arsenal
    # face-up. If you do, put a +1{p} counter on it." (Was unimplemented.)
    from engine.card_effects.dsl import dispatch
    from engine.card_effects.dsl.loader import load_all_cards
    load_all_cards()

    st = _make_state(); st.card_db = DB
    iron = _card("ironfist_revelation", 1)
    st.players[1].arms.add(iron)
    crush = _card("batter_to_a_pulp_red", 1)   # has the Crush keyword
    st.players[1].arsenal.add(crush)           # arsenal cards are hidden (face-down)
    assert not crush.is_public

    dispatch(st, "ON_DEFEND", "ironfist_revelation", card=iron, event=None)
    assert crush.is_public, "crush card turned face-up"
    assert crush.counters.get("power", 0) == 1, "+1{p} counter placed on it"

    # The +1{p} counter adds to power when that card later attacks.
    base = crush.base_power or 0
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=0,
                            attack_card=crush, keywords=[])
    E._recalculate_attack_power(st)
    assert st.combat.attack_power == base + 1

    # No eligible crush card in arsenal → nothing happens.
    st2 = _make_state(); st2.card_db = DB
    iron2 = _card("ironfist_revelation", 1); st2.players[1].arms.add(iron2)
    plain = _card("sink_below_yellow", 1)      # no Crush
    st2.players[1].arsenal.add(plain)
    dispatch(st2, "ON_DEFEND", "ironfist_revelation", card=iron2, event=None)
    assert plain.counters.get("power", 0) == 0


def test_ironfist_revelation_may_is_declinable():
    """The "you may" is a real choice: declining leaves the eligible crush card
    face-down and uncountered. Covers the MAY-block decline branch created by
    the migration to composable primitives."""
    from engine.card_effects.dsl import dispatch
    from engine.card_effects.dsl.loader import load_all_cards
    load_all_cards()

    st = _make_state(); st.card_db = DB
    iron = _card("ironfist_revelation", 1)
    st.players[1].arms.add(iron)
    crush = _card("batter_to_a_pulp_red", 1)
    st.players[1].arsenal.add(crush)

    def _decline(state, options, context="", **kw):
        for negative in ("no", "decline", "fail_to_find"):
            if negative in options:
                return negative
        return options[-1]
    st.player_agents[1] = _decline

    dispatch(st, "ON_DEFEND", "ironfist_revelation", card=iron, event=None)

    assert not crush.is_public, "declined — crush card stays face-down"
    assert crush.counters.get("power", 0) == 0, "declined — no counter placed"


def test_big_bully_doubles_base_when_booed():
    # "If you've been booed this turn, this card's base {p} is doubled." Must
    # double the CURRENT base (so Kayo setting base 6 → 12), not add a flat 4.
    from engine.card_effects.dsl.loader import load_all_cards
    load_all_cards()

    def attack_power(base_power, booed):
        st = _make_state(); st.card_db = DB
        E._setup_dsl_listeners(st)
        bully = _card("big_bully_red", 1)
        bully.base_power = base_power           # e.g. 6 after Kayo's SET_BASE_POWER
        st.combat = CombatState(attacker_id=1, link_id=1, attack_power=base_power,
                                attack_card=bully, keywords=[])
        st.combat.base_attack_power = base_power
        if booed:
            st.players[1].current_turn_effects.append("crowd_booed")
        E._recalculate_attack_power(st)
        return st.combat.attack_power

    assert attack_power(4, booed=True) == 8, "printed base 4, booed → doubled to 8"
    assert attack_power(6, booed=True) == 12, "Kayo-set base 6, booed → doubled to 12"
    assert attack_power(4, booed=False) == 4, "not booed → no doubling"


def _pow_card(power, oid, owner=2):
    c = Card(slug=f"pow{power}_{oid}", raw_name="x", raw_types=["Action"])
    c.subtypes = ["Attack"]; c.power = power; c.base_power = power
    c.defense = 2; c.base_defense = 2
    c.owner = owner; c.controller = owner; c.object_id = oid
    return c


def _has_perm(player, slug):
    return any(getattr(t, "slug", None) == slug for t in player.permanents.cards)


def test_show_of_strength_minus_power_per_high_defender():
    # "This gets -1{p} for each card with 6 or more {p} defending it."
    from engine.card_effects.dsl.loader import load_all_cards
    load_all_cards()
    st = _make_state(); st.card_db = DB
    E._setup_dsl_listeners(st)
    sos = _card("show_of_strength_red", 1)
    base = sos.base_power or 0
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=base,
                            attack_card=sos, keywords=[])
    st.combat.base_attack_power = base
    st.combat.defending_cards = [_pow_card(6, 1), _pow_card(7, 2), _pow_card(3, 3)]
    E._recalculate_attack_power(st)
    assert st.combat.attack_power == base - 2, "two 6+{p} defenders → -2{p}"


def test_millers_grindstone_clash_on_hit():
    # "When this hits a hero, clash. If you win, destroy the top card of their
    # deck. If they win, put a -1{p} counter on this." (Clash = highest top power.)
    from engine.card_effects.dsl import dispatch
    from engine.card_effects.dsl.loader import load_all_cards
    load_all_cards()

    # You win → their top deck card destroyed.
    st = _make_state(); st.card_db = DB
    m = _card("millers_grindstone", 1)
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=0,
                            attack_card=m, keywords=[])
    st.players[1].deck.add(_pow_card(9, 1, owner=1))
    their_top = _pow_card(1, 2, owner=2); st.players[2].deck.add(their_top)
    dispatch(st, "ON_HIT", "millers_grindstone", card=m, event=None)
    assert their_top not in st.players[2].deck.cards

    # They win → -1{p} counter on Miller's.
    st2 = _make_state(); st2.card_db = DB
    m2 = _card("millers_grindstone", 1)
    st2.combat = CombatState(attacker_id=1, link_id=1, attack_power=0,
                             attack_card=m2, keywords=[])
    st2.players[1].deck.add(_pow_card(1, 3, owner=1))
    st2.players[2].deck.add(_pow_card(9, 4, owner=2))
    dispatch(st2, "ON_HIT", "millers_grindstone", card=m2, event=None)
    assert m2.counters.get("power", 0) == -1


def test_schism_of_chaos_shuffles_and_arsenals_top_facedown():
    # "When this is pitched, each hero shuffles, then puts the top card of their
    # deck facedown into their arsenal."
    from engine.card_effects.dsl import dispatch
    from engine.card_effects.dsl.loader import load_all_cards
    load_all_cards()
    st = _make_state(); st.card_db = DB
    schism = _card("schism_of_chaos_blue", 1)
    for pid in (1, 2):
        for i in range(3):
            st.players[pid].deck.add(_pow_card(1, 100 * pid + i, owner=pid))
    dispatch(st, "ON_PITCH", "schism_of_chaos_blue", card=schism, event=None)
    for pid in (1, 2):
        assert len(st.players[pid].arsenal.cards) == 1, f"P{pid} arsenal gets a card"
        assert not st.players[pid].arsenal.cards[0].is_public, "facedown in arsenal"
        assert len(st.players[pid].deck.cards) == 2, f"P{pid} deck down by 1"


def test_swing_big_quicken_when_it_missed():
    # "When the combat chain closes, if this didn't hit, the defending hero
    # creates a Quicken token."
    from engine.card_effects.dsl import dispatch
    from engine.card_effects.dsl.loader import load_all_cards
    load_all_cards()

    st = _make_state(); st.card_db = DB
    swing = _card("swing_big_red", 1)
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=0,
                            attack_card=swing, keywords=[])
    st.combat.hit = False
    dispatch(st, "ON_COMBAT_CLOSE", "swing_big_red", card=swing, event=None)
    assert _has_perm(st.players[2], "quicken"), "defender gets Quicken on a miss"

    # If it hit, no token.
    st2 = _make_state(); st2.card_db = DB
    sw2 = _card("swing_big_red", 1)
    st2.combat = CombatState(attacker_id=1, link_id=1, attack_power=0,
                             attack_card=sw2, keywords=[])
    st2.combat.hit = True
    dispatch(st2, "ON_COMBAT_CLOSE", "swing_big_red", card=sw2, event=None)
    assert not _has_perm(st2.players[2], "quicken")


def test_crown_of_dominion_creates_gold_on_equip():
    # "When you equip Crown of Dominion, create a Gold token."
    from engine.card_effects.dsl import dispatch
    from engine.card_effects.dsl.loader import load_all_cards
    load_all_cards()
    st = _make_state(); st.card_db = DB
    crown = _card("crown_of_dominion", 1)
    st.players[1].head.add(crown)
    dispatch(st, "ON_EQUIP", "crown_of_dominion", card=crown, event=None)
    assert _has_perm(st.players[1], "gold")


def test_destroying_weapon2_card_with_generic_zone_does_not_duplicate():
    # Regression: destroying a card that sits in weapon2 but whose .zone is the
    # generic "weapon" (which maps to the weapon1 slot) must still remove it from
    # weapon2 — not leave it equipped AND add a copy to the graveyard. Surfaced
    # by Flick Knives destroying one of two equipped Hunter's Klaive (daggers)
    # while the other was the active attacking weapon. CR 8.5.4.
    from engine.effect_keywords import destroy
    st = _make_state(); st.card_db = DB
    p = st.players[1]
    k1 = _card("hunters_klaive", 1); k2 = _card("hunters_klaive", 1)
    p.weapon1.add(k1); p.weapon2.add(k2)
    k2.zone = "weapon"  # stale/generic zone name from the weapon-attack path
    before = len(p.weapon1.cards) + len(p.weapon2.cards) + len(p.graveyard.cards)
    destroy(st, k2, None)
    after = len(p.weapon1.cards) + len(p.weapon2.cards) + len(p.graveyard.cards)
    assert after == before, "destroy must not create a phantom graveyard copy"
    assert k2 not in p.weapon2.cards, "destroyed weapon must leave its slot"
    assert p.graveyard.find("hunters_klaive") is not None, "it goes to the graveyard"
    assert len(p.weapon1.cards) == 1, "the other equipped weapon is untouched"


def test_priority_loop_ends_game_when_a_player_is_already_dead():
    # CR 1.10.2a: a player brought to <=0 life in a no-priority window (e.g. a
    # start-of-turn Bloodrot Pox DoT) loses when the game transitions to a
    # priority state — before being granted priority to act.
    from engine.engine import priority_loop
    st = _make_state()
    st.players[2].health = -5
    st.priority_player = 1
    priority_loop(st)
    assert st.done is True
    assert st.winner == 1


def test_lethal_combat_hit_ends_game_before_on_hit_triggers():
    # CR 1.10.2a: the 0-life loss is applied before on-hit triggered-layers
    # resolve. A lethal hit must end the game without firing the 'hit' event
    # (which is what drives on-hit effects and was prompting the defeated player).
    from engine.engine import _resolve_damage
    from engine.state import CombatState
    st = _make_state()
    st.players[2].health = 10
    atk = _attack_stub(1); atk.base_power = 50; atk.power = 50
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=50,
                            attack_card=atk, keywords=[])
    fired = []
    st.event_manager.register("hit", lambda ev, s: fired.append(True))
    _resolve_damage(st)
    assert st.done is True and st.winner == 1
    assert fired == [], "on-hit ('hit') must not fire on a lethal hit (game already over)"


def test_nonlethal_combat_hit_still_fires_on_hit():
    # Guard against over-suppression: a non-lethal hit fires 'hit' as normal.
    from engine.engine import _resolve_damage
    from engine.state import CombatState
    st = _make_state()
    st.players[2].health = 40
    atk = _attack_stub(1); atk.base_power = 4; atk.power = 4
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=4,
                            attack_card=atk, keywords=[])
    fired = []
    st.event_manager.register("hit", lambda ev, s: fired.append(True))
    _resolve_damage(st)
    assert st.done is False
    assert fired == [True], "a non-lethal hit still fires on-hit triggers"


def test_take_up_the_mantle_copy_reverts_when_chain_closes():
    # CR 3.0.9: when the copied attack leaves the combat chain (an arena zone)
    # into the graveyard it resets to a new object — its original card, not the
    # copied one. Take Up the Mantle overwrote the target's identity permanently,
    # leaving a mislabelled duplicate of the copied card in the graveyard.
    from engine.card_effects.dsl.effect_types import compile_effect
    from engine.card_effects.dsl.loader import load_all_cards
    from engine.state import CombatState, Event
    load_all_cards()
    st = _make_state(); st.card_db = DB

    target = Card(slug="orig_attack", raw_name="Orig", raw_types=["Action"])
    target.subtypes = ["Attack"]; target.keywords = ["stealth"]
    target.base_power = 2; target.power = 2; target.types = ["Action"]
    target.owner = target.controller = 1

    src = Card(slug="copied_stealth_attack", raw_name="Src", raw_types=["Action"])
    src.subtypes = ["Attack"]; src.keywords = ["stealth"]
    src.base_power = 6; src.power = 6; src.types = ["Action"]
    src.owner = src.controller = 1
    st.players[1].graveyard.add(src)

    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=2,
                            attack_card=target, keywords=["stealth"])

    hero = _card("arakni_marionette", 1)
    fn = compile_effect("COPY_BANISHED_STEALTH_ATTACK", {})
    fn(hero, None, st)

    # The target became a copy, and the original was banished from the graveyard.
    assert target.slug == "copied_stealth_attack", "target becomes a copy"
    assert st.players[1].banished.find("copied_stealth_attack") is not None
    assert st.players[1].graveyard.find("copied_stealth_attack") is None

    # When the chain closes and the attack leaves the arena, it reverts (CR 3.0.9)
    st.event_manager.emit(Event(type="combat_chain_close"), st)
    assert target.slug == "orig_attack", "copy reverts on leaving the chain"
    assert target.base_power == 2


def _victor_gold_state():
    """Victor as p1 with a stocked deck so his gold-draw is observable."""
    from engine.card_effects.dsl.loader import load_all_cards
    load_all_cards()
    st = _make_state(); st.card_db = DB
    hero = _card("victor_goldmane_high_and_mighty", 1)
    st.players[1].hero = hero
    for i in range(3):
        filler = Card(slug=f"filler_{i}", raw_name="Filler", raw_types=["Action"])
        filler.owner = filler.controller = 1
        st.players[1].deck.add(filler)  # non-token, so it stays in the deck
    return st, hero


def test_victor_gold_draw_not_during_start_of_game():
    # CR 4.1.8b + its Victor example: "The first time each turn you create a Gold
    # token from an effect you control, draw a card." A Gold created during the
    # start-of-game procedure must NOT draw, because it is not during a turn.
    from engine.card_effects.dsl import dispatch
    st, hero = _victor_gold_state()
    st.individual_turns = 0  # start-of-game procedure
    before = len(st.players[1].hand.cards)
    dispatch(st, "ON_TOKEN_CREATED", "victor_goldmane_high_and_mighty",
             card=hero, event={"slug": "gold"})
    assert len(st.players[1].hand.cards) == before, \
        "Victor must not draw from a Gold created during start-of-game (CR 4.1.8b)"


def test_victor_gold_draw_fires_once_per_turn_during_a_turn():
    # During an actual turn the trigger fires — and only the first time each turn.
    from engine.card_effects.dsl import dispatch
    st, hero = _victor_gold_state()
    st.individual_turns = 1  # a real turn is underway
    before = len(st.players[1].hand.cards)
    dispatch(st, "ON_TOKEN_CREATED", "victor_goldmane_high_and_mighty",
             card=hero, event={"slug": "gold"})
    assert len(st.players[1].hand.cards) == before + 1, "first Gold this turn draws"
    # Second Gold same turn: 'first time each turn' — no further draw.
    dispatch(st, "ON_TOKEN_CREATED", "victor_goldmane_high_and_mighty",
             card=hero, event={"slug": "gold"})
    assert len(st.players[1].hand.cards) == before + 1, "only the first Gold each turn draws"


def _equip(slot, defense, oid, owner=2):
    c = Card(slug=f"eq_{slot}_{oid}", raw_name="eq", raw_types=["Equipment"])
    c.subtypes = [slot.title()]; c.defense = defense; c.base_defense = defense
    c.owner = owner; c.controller = owner; c.object_id = oid
    return c


def test_mask_of_deceit_transforms_on_defend():
    # "When this defends, become a random Agent of Chaos. If the attacking hero
    # is marked, instead choose the Agent of Chaos."
    from engine.card_effects.dsl import dispatch
    from engine.card_effects.dsl.loader import load_all_cards
    from engine.card_effects.ability_keywords import AGENT_OF_CHAOS_SLUGS
    load_all_cards()

    # Not marked → a (random) Agent of Chaos.
    st = _make_state(); st.card_db = DB
    st.players[1].hero = _card("arakni_marionette", 1)
    mask = _card("mask_of_deceit", 1); st.players[1].arms.add(mask)
    dispatch(st, "ON_DEFEND", "mask_of_deceit", card=mask, event=None)
    assert st.players[1].hero.slug in AGENT_OF_CHAOS_SLUGS

    # Attacking hero marked → choose (the mock agent takes the first option).
    st2 = _make_state(); st2.card_db = DB
    st2.players[1].hero = _card("arakni_marionette", 1)
    st2.players[2].class_counters["marked"] = 1
    mask2 = _card("mask_of_deceit", 1); st2.players[1].arms.add(mask2)
    dispatch(st2, "ON_DEFEND", "mask_of_deceit", card=mask2, event=None)
    assert st2.players[1].hero.slug == AGENT_OF_CHAOS_SLUGS[0]


def test_headbutt_restriction_bonus_and_crush():
    from engine.card_effects.dsl import dispatch
    from engine.card_effects.dsl.loader import load_all_cards
    from engine.actions import get_defendable_cards
    load_all_cards()

    # Part 1: can't be defended by non-head equipment (hand cards unaffected).
    st = _make_state(); st.card_db = DB; st.active_player = 1
    hb = _card("headbutt_blue", 1)
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=hb.power or 0,
                            attack_card=hb, keywords=[])
    head_eq = _equip("head", 2, 1); chest_eq = _equip("chest", 2, 2)
    st.players[2].head.add(head_eq); st.players[2].chest.add(chest_eq)
    dispatch(st, "ON_ATTACK", "headbutt_blue", card=hb, event=None)
    defendable = get_defendable_cards(st)
    assert head_eq in defendable and chest_eq not in defendable

    # Part 2: +1{p} when you have a head equipped and the defender doesn't.
    st2 = _make_state(); st2.card_db = DB
    E._setup_dsl_listeners(st2)
    hb2 = _card("headbutt_blue", 1); base = hb2.base_power or 0
    st2.combat = CombatState(attacker_id=1, link_id=1, attack_power=base,
                             attack_card=hb2, keywords=[])
    st2.combat.base_attack_power = base
    st2.players[1].head.add(_equip("head", 1, 3, owner=1))   # you have a head
    E._recalculate_attack_power(st2)
    assert st2.combat.attack_power == base + 1

    # Part 3: Crush destroys the defender's head equipment once its {d} hits 0.
    st3 = _make_state(); st3.card_db = DB
    hb3 = _card("headbutt_blue", 1)
    st3.combat = CombatState(attacker_id=1, link_id=1, attack_power=0,
                             attack_card=hb3, keywords=[])
    survive = _equip("head", 2, 4, owner=2)  # 2{d} → 1{d}, survives
    st3.players[2].head.add(survive)
    dispatch(st3, "ON_CRUSH", "headbutt_blue", card=hb3, event=None)
    assert survive in st3.players[2].head.cards and survive.defense == 1
    dispatch(st3, "ON_CRUSH", "headbutt_blue", card=hb3, event=None)  # 1 → 0 → destroyed
    assert survive not in st3.players[2].head.cards


def test_aurum_aegis_counts_as_a_gold():
    # "This counts as a Gold." — grants the Gold subtype on equip so gold-count
    # checks (CONTROLS_TOKEN_TYPE) see it.
    from engine.card_effects.dsl import dispatch
    from engine.card_effects.dsl.condition_types import compile_condition
    from engine.card_effects.dsl.loader import load_all_cards
    load_all_cards()
    st = _make_state(); st.card_db = DB
    aurum = _card("aurum_aegis", 1)
    st.players[1].permanents.add(aurum)
    assert "Gold" not in (aurum.subtypes or [])
    dispatch(st, "ON_EQUIP", "aurum_aegis", card=aurum, event=None)
    assert "Gold" in aurum.subtypes, "counts as a Gold (subtype granted)"
    # A gold-count check now recognises it.
    ctt = compile_condition("CONTROLS_TOKEN_TYPE", {"token": "gold"})
    assert ctt(aurum, None, st) is True


def test_visit_goldmane_counts_aurum_as_gold_for_might():
    # "Create a Gold. Then if you control 3+ Gold, create that many Might."
    # Aurum Aegis counts as a Gold, so aurum + 1 real gold + the created gold = 3.
    from engine.card_effects.dsl import dispatch
    from engine.card_effects.dsl.loader import load_all_cards
    from engine.effect_keywords import create_token
    load_all_cards()
    st = _make_state(); st.card_db = DB
    aurum = _card("aurum_aegis", 1)
    st.players[1].permanents.add(aurum)
    dispatch(st, "ON_EQUIP", "aurum_aegis", card=aurum, event=None)  # grant Gold subtype
    create_token(st, target_player_id=1, token_slug="gold", number=1)

    visit = _card("visit_goldmane_estate_blue", 1)
    dispatch(st, "ON_PLAY", "visit_goldmane_estate_blue", card=visit, event=None)
    mights = sum(1 for t in st.players[1].permanents.cards
                 if getattr(t, "slug", None) == "might")
    assert mights == 3, "aurum + 1 gold + created gold = 3 Golds → 3 Might"


def test_under_the_trap_door_banishes_trap_and_makes_it_playable():
    # "Instant - Discard this: Banish target trap from your graveyard. If you do,
    # you may play it this turn." Exercises the from-hand instant-discard subsystem.
    from engine.card_effects.dsl.loader import load_all_cards
    load_all_cards()
    st = _make_state(); st.card_db = DB
    st.step = Step.ACTION; st.active_player = 1; st.priority_player = 1
    utd = _card("under_the_trap_door_blue", 1); utd.zone = "hand"
    st.players[1].hand.add(utd)
    trap = Card(slug="fake_trap", raw_name="Trap", raw_types=["Action"])
    trap.subtypes = ["Trap"]; trap.owner = 1; trap.controller = 1; trap.object_id = 555
    st.players[1].graveyard.add(trap)

    acts = [a for a in available_actions(st, 1)
            if a.type == ActionType.DISCARD_ACTIVATE and a.card is utd]
    assert acts, "Under the Trap-Door offered as a from-hand instant"
    act = acts[0]; act.player_id = 1
    apply_action(st, act)
    assert utd in st.players[1].graveyard.cards, "the card is discarded as the cost"
    assert trap not in st.players[1].graveyard.cards
    assert trap in st.players[1].banished.cards
    assert any(c is trap for c in st.players[1].playable_from_banished)

    # Rider: "if it would be put into the graveyard this turn, instead banish it."
    from engine.engine import _to_graveyard
    st.players[1].banished.remove(trap)          # simulate the trap being played
    _to_graveyard(st.players[1], trap)           # ... then heading to the graveyard
    assert trap in st.players[1].banished.cards, "graveyard placement redirected to banish"
    assert trap not in st.players[1].graveyard.cards
    # A card without the rider goes to the graveyard normally.
    plain = Card(slug="plain", raw_name="P", raw_types=["Action"]); plain.object_id = 556
    _to_graveyard(st.players[1], plain)
    assert plain in st.players[1].graveyard.cards


def test_ripple_away_reduces_token_creation():
    # "Instant - Discard this: If an action card effect would create 1+ tokens
    # this turn, instead it creates that many minus 1 of each of those tokens."
    from engine.card_effects.dsl.loader import load_all_cards
    from engine.effect_keywords import create_token
    load_all_cards()
    st = _make_state(); st.card_db = DB
    st.step = Step.ACTION; st.active_player = 1; st.priority_player = 1
    ripple = _card("ripple_away_blue", 1); ripple.zone = "hand"
    st.players[1].hand.add(ripple)
    acts = [a for a in available_actions(st, 1)
            if a.type == ActionType.DISCARD_ACTIVATE and a.card is ripple]
    assert acts, "Ripple Away offered as a from-hand instant"
    act = acts[0]; act.player_id = 1
    apply_action(st, act)

    from engine.context import push_effect_source, pop_effect_source
    action_src = Card(slug="act_src", raw_name="A", raw_types=["Action"])
    action_src.types = ["Action"]
    equip_src = Card(slug="eq_src", raw_name="E", raw_types=["Equipment"])
    equip_src.types = ["Equipment"]

    # An action card effect creating 3 tokens → 2; creating 1 → 0.
    push_effect_source(action_src)
    create_token(st, target_player_id=1, token_slug="gold", number=3)
    create_token(st, target_player_id=1, token_slug="might", number=1)
    pop_effect_source()
    golds = sum(1 for t in st.players[1].permanents.cards if getattr(t, "slug", None) == "gold")
    mights = sum(1 for t in st.players[1].permanents.cards if getattr(t, "slug", None) == "might")
    assert golds == 2, "action-card effect: 3 tokens → 2"
    assert mights == 0, "action-card effect: 1 token → 0"

    # A non-action-card effect is unaffected.
    push_effect_source(equip_src)
    create_token(st, target_player_id=1, token_slug="vigor", number=3)
    pop_effect_source()
    vigor = sum(1 for t in st.players[1].permanents.cards if getattr(t, "slug", None) == "vigor")
    assert vigor == 3, "non-action source: not reduced"


def test_outside_interference_reveals_reviled_from_inventory():
    # "Instant - Discard this: You may reveal a Reviled attack action card from
    # your inventory and put it into your hand." Needs the populated inventory.
    from engine.card_effects.dsl.loader import load_all_cards
    from engine.engine import _populate_reviled_inventory
    load_all_cards()
    st = _make_state(); st.card_db = DB
    st.step = Step.ACTION; st.active_player = 1; st.priority_player = 1
    _populate_reviled_inventory(st)
    assert len(st.players[1].inventory.cards) == 3, "3 Reviled attacks in inventory"
    assert all(c.power == 0 and c.defense == 3 for c in st.players[1].inventory.cards)

    oi = _card("outside_interference_blue", 1); oi.zone = "hand"
    st.players[1].hand.add(oi)
    acts = [a for a in available_actions(st, 1)
            if a.type == ActionType.DISCARD_ACTIVATE and a.card is oi]
    assert acts, "Outside Interference offered as a from-hand instant"
    act = acts[0]; act.player_id = 1
    apply_action(st, act)
    assert oi in st.players[1].graveyard.cards
    assert len(st.players[1].inventory.cards) == 2, "one Reviled left the inventory"
    assert any(c.slug == "reviled" for c in st.players[1].hand.cards)


def _attack_action(power, oid, owner=1, classes=None, keywords=None):
    c = Card(slug=f"aa{oid}", raw_name="AA", raw_types=["Action"])
    c.subtypes = ["Attack"]; c.power = power; c.base_power = power
    c.owner = owner; c.controller = owner; c.object_id = oid
    c.classes = classes or []; c.keywords = keywords or []
    return c


def test_codex_of_frailty_arsenal_discard_and_tokens():
    from engine.card_effects.dsl import dispatch
    from engine.card_effects.dsl.loader import load_all_cards
    load_all_cards()
    st = _make_state(); st.card_db = DB
    for pid in (1, 2):
        st.players[pid].graveyard.add(_attack_action(4, 700 + pid, owner=pid))
        st.players[pid].hand.add(_pow_card(1, 800 + pid, owner=pid))
    dispatch(st, "ON_PLAY", "codex_of_frailty_yellow", card=_card("codex_of_frailty_yellow", 1), event=None)
    for pid in (1, 2):
        assert len(st.players[pid].arsenal.cards) == 1, f"P{pid} attack → arsenal"
        assert len(st.players[pid].hand.cards) == 0, f"P{pid} discarded"
    assert _has_perm(st.players[1], "ponder") and _has_perm(st.players[2], "frailty")


def test_codex_of_inertia_deck_to_arsenal_and_tokens():
    from engine.card_effects.dsl import dispatch
    from engine.card_effects.dsl.loader import load_all_cards
    load_all_cards()
    st = _make_state(); st.card_db = DB
    for pid in (1, 2):
        st.players[pid].deck.add(_pow_card(1, 900 + pid, owner=pid))
        st.players[pid].hand.add(_pow_card(1, 950 + pid, owner=pid))
    dispatch(st, "ON_PLAY", "codex_of_inertia_yellow", card=_card("codex_of_inertia_yellow", 1), event=None)
    for pid in (1, 2):
        assert len(st.players[pid].arsenal.cards) == 1 and len(st.players[pid].hand.cards) == 0
    assert _has_perm(st.players[1], "ponder") and _has_perm(st.players[2], "inertia")


def test_savor_bloodshed_queues_marked_dagger_draw():
    from engine.card_effects.dsl import dispatch
    from engine.card_effects.dsl.loader import load_all_cards
    load_all_cards()
    st = _make_state(); st.card_db = DB
    dispatch(st, "ON_PLAY", "savor_bloodshed_red", card=_card("savor_bloodshed_red", 1), event=None)
    assert any(k.startswith("next_marked_dagger_hit_draw_")
               for k in st.players[1].current_turn_effects), "delayed draw queued"


def test_flick_knives_dagger_deals_damage_and_destroys():
    from engine.card_effects.dsl.loader import load_all_cards, get_card
    from engine.card_effects.dsl.interpreter import run_ability
    from engine.state import Event
    load_all_cards()
    st = _make_state(); st.card_db = DB
    flick = _card("flick_knives", 1)  # the reaction source
    dagger = Card(slug="mydagger", raw_name="D", raw_types=["Weapon"])
    dagger.subtypes = ["Dagger"]; dagger.owner = 1; dagger.controller = 1; dagger.object_id = 321
    st.players[1].weapon2.add(dagger)
    life0 = st.players[2].life
    run_ability(get_card("flick_knives").abilities[0], flick, Event(type="ON_ACTIVATE"), st)
    assert st.players[2].life == life0 - 1, "dagger dealt 1 damage to opposing hero"
    assert dagger not in st.players[1].weapon2.cards, "dagger destroyed"


def test_blacktek_reaction_destroys_self():
    from engine.card_effects.dsl.loader import load_all_cards, get_card
    from engine.card_effects.dsl.interpreter import run_ability
    from engine.state import Event, CombatState
    load_all_cards()
    st = _make_state(); st.card_db = DB
    blacktek = _card("blacktek_whisperers", 1); st.players[1].arms.add(blacktek)
    atk = _attack_action(6, 42, owner=1, classes=["Assassin"])
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=6, attack_card=atk, keywords=[])
    ab = get_card("blacktek_whisperers").abilities[0]
    ev = Event(type="ON_ACTIVATE")
    for c in ab.costs:      # pay DESTROY_SELF (the reaction's cost)
        c.pay_fn(blacktek, ev, st)
    run_ability(ab, blacktek, ev, st)
    assert blacktek not in st.players[1].arms.cards, "Blacktek destroyed as the reaction cost"


def test_take_up_the_mantle_marked_copies_banished_stealth():
    from engine.card_effects.dsl.loader import load_all_cards, get_card
    from engine.card_effects.dsl.interpreter import run_ability
    from engine.state import Event, CombatState
    load_all_cards()
    st = _make_state(); st.card_db = DB
    E._setup_dsl_listeners(st)
    target = _attack_action(2, 50, owner=1, keywords=["Stealth"])
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=2, attack_card=target,
                            keywords=["Stealth"])
    st.combat.base_attack_power = 2
    st.players[2].class_counters["marked"] = 1  # attacking a marked hero
    banished_src = _attack_action(6, 51, owner=1, keywords=["Stealth"])
    banished_src.slug = "big_stealth_attack"
    st.players[1].graveyard.add(banished_src)
    run_ability(get_card("take_up_the_mantle_yellow").abilities[0], _card("take_up_the_mantle_yellow", 1),
                Event(type="ON_ACTIVATE", target=target), st)
    assert st.combat.attack_card.slug == "big_stealth_attack", "target became a copy"
    assert banished_src in st.players[1].banished.cards, "source banished"
    # +3 (marked) on top of the copied base 6 = 9
    assert st.combat.attack_power == 9


def test_blacktek_graveyard_buyback_destroys_silvers_and_equips():
    # "While this is in your graveyard, at the start of your turn, you may destroy
    # 2 Silvers you control. If you do, equip this."
    from engine.card_effects.dsl import dispatch
    from engine.card_effects.dsl.loader import load_all_cards
    from engine.effect_keywords import create_token
    load_all_cards()

    st = _make_state(); st.card_db = DB
    blacktek = _card("blacktek_whisperers", 1); st.players[1].graveyard.add(blacktek)
    create_token(st, target_player_id=1, token_slug="silver", number=2)
    dispatch(st, "START_OF_TURN_IN_GRAVEYARD", "blacktek_whisperers", card=blacktek, event=None)
    assert not any(t.slug == "silver" for t in st.players[1].permanents.cards), "2 Silvers destroyed"
    assert blacktek not in st.players[1].graveyard.cards
    assert blacktek in st.players[1].legs.cards, "Blacktek re-equipped"

    # Fewer than 2 Silvers → stays in the graveyard.
    st2 = _make_state(); st2.card_db = DB
    b2 = _card("blacktek_whisperers", 1); st2.players[1].graveyard.add(b2)
    create_token(st2, target_player_id=1, token_slug="silver", number=1)
    dispatch(st2, "START_OF_TURN_IN_GRAVEYARD", "blacktek_whisperers", card=b2, event=None)
    assert b2 in st2.players[1].graveyard.cards


def test_silver_token_is_implemented():
    from engine.card_effects.dsl.loader import load_all_cards, get_card
    load_all_cards()
    assert get_card("silver") is not None, "Silver token has a DSL definition"


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


# ---------------------------------------------------------------------------
# L1 / L3 — CR behaviors that were implemented but never covered by a test.
# The 2026-07 audit listed both as "open"; the code had moved ahead of the doc.
# ---------------------------------------------------------------------------

def test_defend_declarations_are_one_compound_event():
    """CR 7.3.2d: all declared cards join the chain link as a single compound
    event, so a 'defends together with …' trigger sees every co-defender.

    If _apply_defend interleaved add/emit per card, the first card's defend
    event would fire while later co-defenders were still absent.
    """
    from engine.play import _apply_defend

    st = _reaction_state(dr_holder=2)  # p1 attacking p2
    seen: list[int] = []

    def _watch(event, state):
        # Record how many cards were already defending when each event fired.
        seen.append(len(state.combat.defending_cards))

    st.event_manager.register("defend", _watch)

    a = _card("big_bully_red", 2)
    b = _card("show_of_strength_red", 2)
    st.players[2].hand.add(a)
    st.players[2].hand.add(b)

    _apply_defend(st, Action(type=ActionType.DEFEND_CARDS, card_list=[a, b]))

    assert st.combat.defending_cards == [a, b]
    assert seen == [2, 2], (
        f"expected both defenders present for every defend event, saw {seen} — "
        f"declarations are being emitted sequentially, not as one compound event"
    )


def test_end_of_turn_resets_every_players_ally_life():
    """CR 4.4.3a: the end-of-turn procedure resets *all* allies' life, not just
    the turn player's."""
    st = _make_state()
    st.card_db = DB
    st.active_player = 1

    allies = {}
    for pid in (1, 2):
        ally = Card(slug=f"test_ally_{pid}", raw_name="Test Ally", raw_types=["Ally"])
        ally.types = ["Ally"]
        ally.owner = ally.controller = pid
        ally.base_life = 3
        ally.current_life = 1  # damaged this turn
        st.players[pid].allies.add(ally)
        allies[pid] = ally

    E._end_phase_iter(st)

    assert allies[1].current_life == 3, "turn player's ally was not reset"
    assert allies[2].current_life == 3, "non-turn player's ally was not reset"


def test_boulder_drop_puts_card_on_top_of_deck_not_bottom():
    """Boulder Drop's Crush clause reads 'on top of their deck'.

    Found by scripts/dsl_semantic_audit.py: the JSON used
    PUT_HAND_CARD_BOTTOM, which is the opposite end of the deck and a
    meaningfully different effect (the opponent redraws it next turn).
    Also mandatory — 'they put a card' allows no decline.
    """
    from engine.card_effects.dsl.effect_types import compile_effect

    st = _make_state()
    st.card_db = DB
    src = _card("boulder_drop_red", 1)

    known = _card("big_bully_red", 2)
    st.players[2].hand.add(known)
    marker = _card("show_of_strength_red", 2)
    st.players[2].deck.add(marker)

    fn = compile_effect("PUT_HAND_CARD_TOP", {"player": "OPPONENT", "optional": False})
    fn(src, None, st)

    assert known not in st.players[2].hand.cards, "card was not moved out of hand"
    assert st.players[2].deck.cards[0] is known, (
        f"expected the card on top of the deck, found {st.players[2].deck.cards[0].slug}"
    )


# ---------------------------------------------------------------------------
# M2 — the attack layer stays on the stack during the Layer Step
# ---------------------------------------------------------------------------

def test_attack_layer_is_on_the_stack_during_layer_step(monkeypatch):
    """CR 7.1.3 / 3.15.4-5: the attack sits on the stack as the bottom layer
    during the Layer Step, so effects that inspect the stack can see it and new
    layers order above it.

    Previously _combat_phase_iter removed the attack entry before the priority
    window, making it invisible to stack-inspecting effects.
    """
    seen: list[bool] = []
    real_priority_loop = E.priority_loop

    def _spy(state, *a, **kw):
        if state.step == Step.COMBAT_LAYER:
            seen.append(any(e.is_attack for e in state.stack_entries))
        return real_priority_loop(state, *a, **kw)

    monkeypatch.setattr(E, "priority_loop", _spy)

    st = _make_state()
    st.card_db = DB
    st.active_player = 1
    st.priority_player = 1

    atk = _attack_stub(1)
    atk.keywords = []
    atk.base_power = atk.power = 4
    st.stack.add(atk)
    entry = StackEntry(card=atk, player_id=1, layer_type='card')
    assert entry.is_attack, "stub must register as an attack layer"
    st.stack_entries.append(entry)

    E._combat_phase_iter(st)

    assert seen, "the Layer Step priority window never ran"
    assert all(seen), (
        "the attack layer was not on the stack during the Layer Step — "
        "stack-inspecting effects cannot see it"
    )
    # And it must not leak: combat must not re-enter from a leftover entry.
    assert not any(e.is_attack for e in st.stack_entries), (
        "attack entry leaked past the Attack Step"
    )


def test_snarky_prick_destruction_is_optional_after_errata():
    """Errata: "If it's red, **you may** destroy it. If you do, this gets +4{p}."

    The card previously read "destroy it and this gets +4{p}" — mandatory — and
    the implementation destroyed unconditionally. Declining must leave the card
    on top of the deck AND give no power bonus, since the bonus is gated on
    having destroyed it.
    """
    from engine.card_effects.dsl import dispatch
    from engine.card_effects.dsl.loader import load_all_cards
    load_all_cards()

    st = _make_state(); st.card_db = DB
    snarky = _card("snarky_prick_red", 1)
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=snarky, keywords=[])
    st.combat.attack_target = None
    top = _card("command_and_conquer_red", 2)   # red (pitch 1)
    st.players[2].deck.add(top)
    st.players[2].deck.add(_card("sink_below_yellow", 2))

    # Controller declines the optional destruction.
    def _decline(state, options, context="", **kw):
        # Decline whatever the negative option is called — effects use "no"
        # (MAY blocks), "decline", or "fail_to_find" depending on the prompt.
        for negative in ("no", "decline", "fail_to_find"):
            if negative in options:
                return negative
        return options[-1]
    st.player_agents[1] = _decline

    dispatch(st, "ON_ATTACK", "snarky_prick_red", card=snarky, event=None)

    assert top in st.players[2].deck.cards, "declined — top card must survive"
    assert top not in st.players[2].graveyard.cards
    assert st.combat.attack_power == 3, (
        "declining must give no +4{p}; the bonus is gated on destroying"
    )


def test_leave_no_witnesses_banishes_up_to_one_arsenal_not_all():
    """CR text: hit → banish the top card of their deck AND *up to 1* card in
    their arsenal. Was DESTROY_ARSENAL, which destroyed every arsenal card.
    Three deviations fixed: destroy→banish, all→up-to-1, mandatory→optional.
    Found by the semantic audit (docs/semantic_audit_triage.md)."""
    from engine.card_effects.dsl import dispatch
    from engine.card_effects.dsl.loader import load_all_cards
    load_all_cards()

    def run(decline):
        st = _make_state(); st.card_db = DB
        atk = _card("leave_no_witnesses_red", 1)
        st.combat = CombatState(attacker_id=1, link_id=1, attack_power=4,
                                attack_card=atk, keywords=[])
        ars = _card("big_bully_red", 2)
        st.players[2].arsenal.add(ars)
        st.players[2].deck.add(_card("sink_below_red", 2))
        if decline:
            def _dec(state, options, context="", **kw):
                for n in ("no", "decline"):
                    if n in options:
                        return n
                return options[-1]
            st.player_agents[1] = _dec
        dispatch(st, "ON_HIT", "leave_no_witnesses_red", card=atk, event=None)
        return st, ars

    st, ars = run(decline=False)
    assert ars in st.players[2].banished.cards, "arsenal card banished, not destroyed"
    assert ars not in st.players[2].graveyard.cards, "banish must not go to graveyard"

    st, ars = run(decline=True)
    assert ars in st.players[2].arsenal.cards, "'up to 1' declined → arsenal card survives"


def test_art_of_desire_draws_and_gains_only_on_red_banish():
    """Text: banish the top card of their deck; whenever this banishes a RED
    card, draw a card and gain 1{h}. Both were unconditional and the life gain
    was missing. Found by the semantic audit."""
    from engine.card_effects.dsl import dispatch
    from engine.card_effects.dsl.loader import load_all_cards
    load_all_cards()

    def run(top_slug):
        st = _make_state(); st.card_db = DB
        atk = _card("art_of_desire_body_red", 1)
        st.combat = CombatState(attacker_id=1, link_id=1, attack_power=4,
                                attack_card=atk, keywords=[])
        st.players[1].deck.add(_card("swing_big_red", 1))
        top = _card(top_slug, 2)
        st.players[2].deck.add(top)
        st.players[2].deck.add(_card("mocking_blow_blue", 2))
        h0, l0 = len(st.players[1].hand.cards), st.players[1].life
        dispatch(st, "ON_HIT", "art_of_desire_body_red", card=atk, event=None)
        return st, top, len(st.players[1].hand.cards) - h0, st.players[1].life - l0

    st, top, drew, gained = run("command_and_conquer_red")   # red (pitch 1)
    assert top in st.players[2].banished.cards
    assert drew == 1 and gained == 1, "red banish → draw a card and gain 1 life"

    st, top, drew, gained = run("mocking_blow_blue")          # blue (pitch 3)
    assert top in st.players[2].banished.cards, "top card banished regardless of colour"
    assert drew == 0 and gained == 0, "non-red banish → no draw, no life"


def test_death_touch_token_type_is_a_choice():
    """Text: create a Frailty, Inertia, OR Bloodrot Pox token — the controller
    chooses. Was hardcoded to frailty. Found by the semantic audit."""
    from engine.card_effects.dsl import dispatch
    from engine.card_effects.dsl.loader import load_all_cards
    load_all_cards()

    def run(agent=None):
        st = _make_state(); st.card_db = DB
        atk = _card("death_touch_red", 1)
        st.combat = CombatState(attacker_id=1, link_id=1, attack_power=4,
                                attack_card=atk, keywords=[])
        if agent:
            st.player_agents[1] = agent
        dispatch(st, "ON_HIT", "death_touch_red", card=atk, event=None)
        return {t.slug for t in st.players[2].permanents.cards}

    assert "frailty" in run(), "default (option 0) creates Frailty"

    def _pick_third(state, options, context="", **kw):
        return "2" if "2" in options else options[0]
    assert "bloodrot_pox" in run(_pick_third), "choosing option 2 creates Bloodrot Pox"


def test_inertia_trap_fires_only_on_pumped_attack():
    """Text: "When this defends an attack with {p} greater than its base,
    create an Inertia token under the attacking hero's control." Previously
    fired on every defend. Found by the semantic audit."""
    from engine.card_effects.dsl import dispatch
    from engine.card_effects.dsl.loader import load_all_cards
    load_all_cards()

    def run(power, base):
        st = _make_state(); st.card_db = DB
        trap = _card("inertia_trap_red", 2)
        atk = _card("big_bully_red", 1)
        st.combat = CombatState(attacker_id=1, link_id=1, attack_power=power,
                                base_attack_power=base, attack_card=atk, keywords=[])
        dispatch(st, "ON_PLAY", "inertia_trap_red", card=trap, event=None)
        return {t.slug for t in st.players[1].permanents.cards}

    assert "inertia" in run(8, 4), "pumped attack (8 > base 4) → Inertia token"
    assert "inertia" not in run(4, 4), "unpumped attack (4 == base 4) → no token"


def test_spreading_plague_creates_x_tokens_per_defending_card():
    """Text: "Create X Bloodrot Pox tokens under the defending hero's control,
    where X is the number of defending cards this chain link." Count was
    hardcoded to 1. Found by the semantic audit."""
    from engine.card_effects.dsl import dispatch
    from engine.card_effects.dsl.loader import load_all_cards
    load_all_cards()

    def run(n_defenders):
        st = _make_state(); st.card_db = DB
        atk = _card("spreading_plague_yellow", 1)
        st.combat = CombatState(attacker_id=1, link_id=1, attack_power=4,
                                attack_card=atk, keywords=[])
        st.combat.defending_cards = [_card("big_bully_red", 2) for _ in range(n_defenders)]
        dispatch(st, "ON_PLAY", "spreading_plague_yellow", card=atk, event=None)
        return sum(1 for t in st.players[2].permanents.cards if t.slug == "bloodrot_pox")

    assert run(0) == 0, "no defenders → no tokens"
    assert run(1) == 1
    assert run(3) == 3, "X scales with the number of defending cards"


def test_orb_weaver_equips_token_and_restricts_pump_to_stealth():
    """Text: "Equip a Graphene Chelicera token. Your next attack with stealth
    this turn gets +3{p}." The equip was missing and the +3 buffed any attack.
    Found by the semantic audit."""
    from engine.card_effects.dsl import dispatch
    from engine.card_effects.dsl.loader import load_all_cards
    load_all_cards()

    st = _make_state(); st.card_db = DB
    orb = _card("orb_weaver_spinneret_red", 1)
    dispatch(st, "ON_PLAY", "orb_weaver_spinneret_red", card=orb, event=None)

    weapons = {c.slug for c in st.players[1].weapon1.cards}
    assert "graphene_chelicera" in weapons, "Graphene Chelicera token equipped"

    queued = getattr(st.players[1], "dsl_queued_attack_mods", [])
    assert queued, "the +3 next-attack bonus was queued"
    filt = queued[0].get("filter") or []
    assert any(f.get("keyword", "").lower() == "stealth" for f in filt), (
        "the +3 must be restricted to attacks with stealth, not any attack"
    )


def test_cut_from_the_same_cloth_reveals_marks_and_dagger_filters():
    """Text: "Target opposing hero reveals their hand. If an attack reaction
    card is revealed this way, mark them. Your next dagger attack this turn
    gets +4{p}." The reveal/mark clause was missing and the +4 buffed any
    attack. Found by the semantic audit."""
    from engine.card_effects.dsl import dispatch
    from engine.card_effects.dsl.loader import load_all_cards
    load_all_cards()

    def run(hand):
        st = _make_state(); st.card_db = DB
        cut = _card("cut_from_the_same_cloth_red", 1)
        for s in hand:
            st.players[2].hand.add(_card(s, 2))
        dispatch(st, "ON_PLAY", "cut_from_the_same_cloth_red", card=cut, event=None)
        queued = getattr(st.players[1], "dsl_queued_attack_mods", [])
        return st.players[2].class_counters.get("marked", 0), queued

    marked, queued = run(["affirm_loyalty_red"])   # an Attack Reaction card
    assert marked > 0, "attack reaction revealed → hero is marked"
    assert queued and any("Dagger" in (f.get("subtypes") or [])
                          for f in queued[0].get("filter", [])), \
        "the +4 is restricted to dagger attacks"

    marked, _ = run(["big_bully_red"])             # not an Attack Reaction
    assert marked == 0, "no attack reaction revealed → no mark"


def test_overcrowded_counts_arena_auras_and_boosts_attack_or_defend():
    """Text: "When this attacks or defends, it gets +1{p} +1{d} for each
    different name among aura tokens in the arena." Previously counted only the
    controller's auras, added only power, and never fired on defend. Found by
    the semantic audit."""
    from engine.card_effects.dsl import dispatch
    from engine.card_effects.dsl.loader import load_all_cards
    load_all_cards()

    def with_three_distinct_auras():
        # 3 distinct names split across BOTH players (a dup counts once).
        st = _make_state(); st.card_db = DB
        st.players[1].auras.add(_card("frailty", 1))
        st.players[1].auras.add(_card("frailty", 1))
        st.players[2].auras.add(_card("inertia", 2))
        st.players[2].auras.add(_card("bloodrot_pox", 2))
        return st

    st = with_three_distinct_auras()
    oc = _card("overcrowded_blue", 1)
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=2,
                            attack_card=oc, keywords=[])
    dispatch(st, "ON_PLAY", "overcrowded_blue", card=oc, event=None)
    assert st.combat.attack_power == 5, "attacking: +1 power per arena aura name (2+3)"

    st = with_three_distinct_auras()
    oc = _card("overcrowded_blue", 2)
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=6,
                            attack_card=_card("big_bully_red", 1), keywords=[])
    st.combat.total_defense = 1
    dispatch(st, "ON_DEFEND", "overcrowded_blue", card=oc, event=None)
    assert st.combat.total_defense == 4, "defending: +1 defense per arena aura name (1+3)"


def test_chain_of_brutality_six_power_gates_go_again_and_set_base():
    """Text: "If this has 6 or more {p}, it gets go again and 'When this hits a
    hero, the next attack action card you play this turn has 6 base {p}.'" Was a
    flat +4 with no power gate and no go again — three bugs. Found by the
    semantic audit (its worst finding)."""
    from engine.card_effects.dsl import dispatch
    from engine.card_effects.dsl.loader import load_all_cards
    from engine.engine import _apply_turn_attack_effects
    load_all_cards()

    def on_hit(power):
        st = _make_state(); st.card_db = DB
        cob = _card("chain_of_brutality_red", 1)
        st.combat = CombatState(attacker_id=1, link_id=1, attack_power=power,
                                base_attack_power=power, attack_card=cob, keywords=[])
        dispatch(st, "ON_HIT", "chain_of_brutality_red", card=cob, event=None)
        return getattr(st.players[1], "dsl_queued_attack_mods", [])

    q6 = on_hit(6)
    assert q6 and q6[0]["mod"] == "set_base" and q6[0]["amount"] == 6, \
        "≥6 power → queue 'next attack action has 6 base power'"
    assert not on_hit(4), "<6 power → no effect"

    # go again is granted when it attacks with 6 or more power.
    #
    # This is now a WHILE_STATIC dispatched on RECALC_ATTACK_POWER rather than
    # an ON_ATTACK trigger, and the change is the point rather than an
    # incidental refactor. The card PRINTS GoAgain, so while the grant was a
    # trigger the printed keyword applied unconditionally and a 4-power Chain
    # of Brutality had go again anyway -- the gate this test was written to
    # protect was decoration. loader.conditional_keywords strips a printed
    # keyword only for a SOURCE_IS_ATTACK-gated static, and reading the power
    # continuously is also the correct timing: a pump applied after declaration
    # has to count, because go again is paid at the Resolution Step (CR 8.3.5b).
    def go_again_at(power):
        st = _make_state(); st.card_db = DB
        cob = _card("chain_of_brutality_red", 1)
        st.combat = CombatState(attacker_id=1, link_id=1, attack_power=power,
                                base_attack_power=power, attack_card=cob,
                                keywords=[])
        dispatch(st, "RECALC_ATTACK_POWER", "chain_of_brutality_red",
                 card=cob, event=None)
        return any(k.lower().replace("_", " ") == "go again"
                   for k in (st.combat.keywords or []))

    assert go_again_at(6), "6 or more power grants go again"
    assert not go_again_at(4), (
        "below 6 power it still grants go again -- the gate is decoration")

    # the queued set_base sets a future attack ACTION's base to 6 (not a weapon)
    st = _make_state(); st.card_db = DB
    st.players[1].dsl_queued_attack_mods = list(q6)
    nxt = _card("swing_big_red", 1); nxt.base_power = 3
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            base_attack_power=3, attack_card=nxt, keywords=[])
    _apply_turn_attack_effects(st, nxt)
    assert nxt.base_power == 6, "next attack action card set to 6 base power"


def test_pain_in_the_backside_dagger_deals_the_damage():
    """Text: "When this hits a hero, target dagger you control deals 1 damage
    to them. If damage is dealt this way, the dagger has hit." Previously dealt
    generic damage not attributed to a dagger and never registered the dagger
    hit. Found by the semantic audit."""
    from engine.card_effects.dsl import dispatch
    from engine.card_effects.dsl.loader import load_all_cards
    load_all_cards()

    # controls a Dagger weapon → 1 damage dealt
    st = _make_state(); st.card_db = DB
    pain = _card("pain_in_the_backside_red", 1)
    st.players[1].weapon1.add(_card("graphene_chelicera", 1))   # a Weapon-Dagger
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=4,
                            attack_card=pain, keywords=[])
    l0 = st.players[2].life
    dispatch(st, "ON_HIT", "pain_in_the_backside_red", card=pain, event=None)
    assert st.players[2].life - l0 == -1, "the dagger deals 1 damage"

    # controls no dagger → nothing happens
    st = _make_state(); st.card_db = DB
    pain = _card("pain_in_the_backside_red", 1)
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=4,
                            attack_card=pain, keywords=[])
    l0 = st.players[2].life
    dispatch(st, "ON_HIT", "pain_in_the_backside_red", card=pain, event=None)
    assert st.players[2].life - l0 == 0, "no dagger controlled → no damage"


def test_stains_of_the_redback_costs_less_when_defender_marked():
    """Text: "If the defending hero is marked, this costs {r} less to play."
    A cost, so it must affect the resource cost (play legality), not be an
    effect. Found by the semantic audit. Covers both colours via the shared
    cost_modifiers subsystem."""
    from engine.card_effects.dsl.loader import load_all_cards
    from engine.play import _calculate_resource_cost
    from engine.actions import Action, ActionType
    load_all_cards()

    def cost(slug, marked):
        st = _make_state(); st.card_db = DB
        stains = _card(slug, 1)
        st.players[1].hand.add(stains)
        if marked:
            st.players[2].class_counters["marked"] = 1
        st.combat = CombatState(attacker_id=1, link_id=1, attack_power=4,
                                attack_card=_card("kiss_of_death_red", 1),
                                keywords=["Stealth"])
        a = Action(type=ActionType.PLAY_CARD, card=stains); a.player_id = 1
        return _calculate_resource_cost(st, a)

    for slug in ("stains_of_the_redback_red", "stains_of_the_redback_blue"):
        base = cost(slug, marked=False)
        assert cost(slug, marked=True) == max(0, base - 1), \
            f"{slug}: marked defender → 1 less resource cost"


def test_arakni_trap_door_grants_trap_play_from_banish():
    """Regression lock: the test-audit flagged "if it's a trap, you may play it"
    as unimplemented, but SEARCH_BANISH_FACE_DOWN already banishes the trap and
    marks it playable-from-banish — a false positive from effect-name blindness.
    This asserts the working behavior so it stays working."""
    from engine.card_effects.dsl import dispatch
    from engine.card_effects.dsl.loader import load_all_cards
    load_all_cards()

    st = _make_state(); st.card_db = DB
    arak = _card("arakni_trap_door", 1)
    trap = _card("frailty_trap_red", 1)   # subtype Trap
    st.players[1].deck.add(trap)
    dispatch(st, "ON_BECOME", "arakni_trap_door", card=arak, event=None)

    assert trap in st.players[1].banished.cards, "trap banished face-down"
    assert any(trap is g for g in st.players[1].playable_from_banished), \
        "a banished trap is playable from banish"


def test_10000_year_reunion_alternative_cost_removes_three_counters():
    """Text: "You may remove three +1{p} counters from among auras you control
    rather than pay its {r} cost." An alternative cost — pay by removing
    counters instead of resources. Was absent. Found by the semantic audit."""
    from engine.card_effects.dsl.loader import load_all_cards, get_card
    load_all_cards()

    alt = get_card("10000_year_reunion_red").abilities[0].alternative_costs[0]

    def payable(n):
        st = _make_state(); st.card_db = DB
        reunion = _card("10000_year_reunion_red", 1)
        aura = _card("frailty", 1)
        st.players[1].auras.add(aura)
        st.players[1].counters[(aura.slug, getattr(aura, "zone", "auras"), "+1{p}")] = n
        return alt.check_fn(reunion, None, st)

    assert payable(3), "3 +1{p} counters → alternative cost is available"
    assert not payable(2), "fewer than 3 → not available"

    # paying removes exactly three
    st = _make_state(); st.card_db = DB
    reunion = _card("10000_year_reunion_red", 1)
    aura = _card("frailty", 1); st.players[1].auras.add(aura)
    key = (aura.slug, getattr(aura, "zone", "auras"), "+1{p}")
    st.players[1].counters[key] = 5
    alt.pay_fn(reunion, None, st)
    assert st.players[1].counters.get(key) == 2, "exactly three counters removed"


def test_under_the_trap_door_grants_play_and_graveyard_to_banish_rider():
    """Regression lock: another test-audit false positive. The card banishes a
    trap, marks it playable-from-banish, AND sets the "if it would be put into
    the graveyard this turn, instead banish it" rider — all already implemented
    (a stale code comment claimed the rider was missing)."""
    from engine.card_effects.dsl.loader import load_all_cards, get_card
    from engine.card_effects.dsl.interpreter import run_ability
    from engine.engine import _to_graveyard
    load_all_cards()

    st = _make_state(); st.card_db = DB
    utd = _card("under_the_trap_door_blue", 1)
    trap = _card("frailty_trap_red", 1)   # subtype Trap
    st.players[1].graveyard.add(trap)

    run_ability(get_card("under_the_trap_door_blue").abilities[0], utd, None, st)
    assert trap in st.players[1].banished.cards, "trap banished from graveyard"
    assert any(trap is g for g in st.players[1].playable_from_banished), \
        "banished trap is playable this turn"

    # the rider: if it would go to the graveyard this turn, it banishes instead
    st.players[1].banished.remove(trap)
    _to_graveyard(st.players[1], trap, is_public=True)
    assert trap in st.players[1].banished.cards, "graveyard→banish rider redirects it"
    assert trap not in st.players[1].graveyard.cards


def test_infiltrate_banishes_opponent_top_and_lets_you_play_it():
    """Text: "When this hits a hero, banish the top card of their deck. You may
    play it until the end of your next turn." Previously only banished; the
    cross-player play-grant was absent. Found by the semantic audit."""
    from engine.card_effects.dsl import dispatch
    from engine.card_effects.dsl.loader import load_all_cards
    from engine.play import recalculate_playable
    load_all_cards()

    st = _make_state(); st.card_db = DB
    inf = _card("infiltrate_red", 1)
    top = _card("mocking_blow_red", 2)   # the opponent's top card
    st.players[2].deck.add(top)
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=4,
                            attack_card=inf, keywords=[])
    dispatch(st, "ON_HIT", "infiltrate_red", card=inf, event=None)

    assert top in st.players[2].banished.cards, "opponent's top card is banished"
    assert any(top is g for g in st.players[1].playable_from_banished), \
        "attacker is granted play of it"

    # and it is actually offered as playable to the attacker (cross-zone)
    st.combat = None
    recalculate_playable(st, 1)
    assert top.playable is True, "the opponent's banished card is playable by you"


def test_tarantula_toxin_choose_one_or_both_modes():
    """Text: "Choose 1 or both; * Target dagger attack gets +3{p}. * Target
    card defending an attack with stealth gets -3{d} this turn." Was a single
    unconditional +3. Found by the semantic audit. Exercises the MODAL
    choose/choose_max range and per-mode conditions."""
    from engine.card_effects.dsl import dispatch
    from engine.card_effects.dsl.loader import load_all_cards
    load_all_cards()

    def run(picks, attack_slug, keywords):
        st = _make_state(); st.card_db = DB
        tar = _card("tarantula_toxin_red", 1)
        atk = _card(attack_slug, 1)
        st.combat = CombatState(attacker_id=1, link_id=1, attack_power=5,
                                base_attack_power=5, attack_card=atk, keywords=keywords)
        # A REAL DEFENDING CARD, because the card says "target card DEFENDING".
        # This fixture used to set combat.total_defense = 6 and populate no
        # defenders at all, which is unreachable in a game -- and it only
        # passed because the effect was untargeted and shifted the aggregate.
        # The card targets ONE defending card, so there has to be one.
        defender = _card("kiss_of_death_red", 2)
        defender.raw_defense = defender.defense = 6
        st.combat.defending_cards = [defender]
        st.combat.total_defense = 6
        seq = iter(picks)
        def agent(state, options, context="", **kw):
            try:
                return next(seq)
            except StopIteration:
                return options[0]
        st.player_agents[1] = agent
        dispatch(st, "ON_PLAY", "tarantula_toxin_red", card=tar, event=None)
        return st.combat.attack_power, defender.defense

    # mode 0 only (dagger +3), decline the second
    assert run(["0", "done"], "kiss_of_death_red", ["Stealth"]) == (8, 6)
    # both modes: +3 power, and the -3 lands on the defending card
    assert run(["0", "1"], "kiss_of_death_red", ["Stealth"]) == (8, 3)
    # mode 0 on a non-dagger attack → the +3 is gated off
    assert run(["0", "done"], "big_bully_red", ["Stealth"]) == (5, 6)


# ---------------------------------------------------------------------------
# Coverage-driven fixes: cards whose effects never executed in audit games.
# Two were genuine dead bugs; two worked and only lacked a test.
# ---------------------------------------------------------------------------

def test_lair_of_the_spider_marks_attacker_with_go_again():
    """BUG: the condition used the token "go_again" but combat stores "Go
    Again", so this never fired in a real game. Now normalised."""
    from engine.card_effects.dsl import dispatch
    from engine.card_effects.dsl.loader import load_all_cards
    load_all_cards()

    def marked_when(keywords):
        st = _make_state(); st.card_db = DB
        lair = _card("lair_of_the_spider_red", 2)
        st.combat = CombatState(attacker_id=1, link_id=1, attack_power=4,
                                attack_card=_card("big_bully_red", 1), keywords=keywords)
        dispatch(st, "ON_PLAY", "lair_of_the_spider_red", card=lair, event=None)
        return st.players[1].class_counters.get("marked", 0)

    assert marked_when(["Go Again"]) == 1, "defending a go-again attack marks the attacker"
    assert marked_when([]) == 0, "no go again → no mark"


def test_nights_embrace_continuous_buffs_only_stealth_attacks():
    """BUG: APPLY_CONTINUOUS registered the effect but nothing read
    dsl_continuous_effects, so it never applied. Now applied during recalc."""
    from engine.card_effects.dsl import dispatch
    from engine.card_effects.dsl.loader import load_all_cards
    from engine.engine import _recalculate_attack_power
    load_all_cards()

    st = _make_state(); st.card_db = DB; st.active_player = 1
    dispatch(st, "ON_PLAY", "nights_embrace_blue", card=_card("nights_embrace_blue", 1), event=None)

    def power(attack_slug, kw):
        atk = _card(attack_slug, 1); atk.keywords = kw
        st.combat = CombatState(attacker_id=1, link_id=1, attack_power=0,
                                base_attack_power=atk.base_power or 0,
                                attack_card=atk, keywords=list(kw))
        _recalculate_attack_power(st)
        return atk.base_power, st.combat.attack_power

    b, p = power("kiss_of_death_red", ["Stealth"])
    assert p == b + 1, "attacks with stealth get +1{p}"
    b, p = power("big_bully_red", [])
    assert p == b, "attacks without stealth are unaffected"


def test_booze_destroys_itself_at_start_of_turn():
    """Verified-working card that only lacked coverage: "At the start of your
    turn, destroy this." """
    from engine.card_effects.dsl import dispatch
    from engine.card_effects.dsl.loader import load_all_cards
    load_all_cards()

    st = _make_state(); st.card_db = DB
    booze = _card("booze_blue", 1)
    st.players[1].permanents.add(booze)
    dispatch(st, "START_OF_TURN", "booze_blue", card=booze, event=None)
    assert booze not in st.players[1].permanents.cards, "booze destroys itself at start of turn"


def test_arakni_funnel_web_stealth_attack_banishes_arsenal_on_hit():
    """Verified-working card that only lacked coverage: the +3 to an Assassin
    attack, and if it has stealth, an injected 'when this hits, banish a card
    in their arsenal'."""
    from engine.card_effects.dsl.loader import load_all_cards, get_card
    from engine.card_effects.dsl.interpreter import run_ability
    from engine.state import Event
    load_all_cards()

    st = _make_state(); st.card_db = DB
    fw = _card("arakni_funnel_web", 1)
    atk = _card("kiss_of_death_red", 1); atk.keywords = ["Stealth"]
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=4,
                            base_attack_power=4, attack_card=atk, keywords=["Stealth"])
    opp_ars = _card("big_bully_red", 2)
    st.players[2].arsenal.add(opp_ars)

    run_ability(get_card("arakni_funnel_web").abilities[0], fw, None, st)
    assert st.combat.attack_power == 7, "target Assassin attack gets +3{p}"

    # Fire the granted trigger the way the engine does. The grant is on the
    # ATTACK, and for an attack ACTION CARD (Kiss of Death) that is the card
    # itself -- a weapon's grant would sit on the combat instead, because its
    # attack is a proxy object (CR 1.4.3). Driving only combat.injected_triggers
    # tested one of the two storage locations.
    ev = Event(type="ON_HIT", data={"damage": 7})
    from engine.card_effects.dsl import dispatch as _dsl_dispatch
    for td in list(getattr(st.combat, "injected_triggers", [])):
        if td.event_type == "ON_HIT" and (td.condition_fn is None or td.condition_fn(atk, ev, st)):
            td.effect_fn(atk, ev, st)
    _dsl_dispatch(st, "ON_HIT", atk.slug, card=atk, event=ev)
    assert opp_ars in st.players[2].banished.cards, \
        "a stealth-buffed attack banishes a card from their arsenal on hit"
