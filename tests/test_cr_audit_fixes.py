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
