"""Behavioral tests for semantic-audit batch-1 card fixes (dual-branch / optional
clauses). Each asserts the OBSERVABLE GameState outcome for both branches.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import engine.card_effects.dsl as dsl
from engine.card_effects.dsl.loader import load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state, _make_card


def _play(state, slug, pid=1, types=("Action",)):
    card = _make_card(slug=slug, name=slug, types=list(types))
    card.owner = card.controller = pid
    dsl.dispatch(state, "ON_PLAY", slug, card=card, event=None)
    return card


# ---------------------------------------------------------------- comet_collision
def test_comet_collision_deals_3_without_starfall():
    load_all_cards()
    st = _make_state()
    before = st.players[2].life
    _play(st, "comet_collision_red", types=["Action", "Instant"])
    assert before - st.players[2].life == 3


def test_comet_collision_deals_4_with_starfall():
    load_all_cards()
    st = _make_state()
    st.players[1].current_turn_effects.append("STARFALL_FLAG")
    before = st.players[2].life
    _play(st, "comet_collision_red", types=["Action", "Instant"])
    assert before - st.players[2].life == 4


# --------------------------------------------------------------------- tide_chakra
def _attack_combat(st, classes):
    atk = _make_card(slug="atk", name="atk", types=["Action", "Attack"])
    atk.owner = atk.controller = 1
    atk.classes = classes
    atk.base_power = 3
    atk.power = 3
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=atk, keywords=[])
    st.combat.base_attack_power = 3
    return atk


def test_tide_chakra_plus2_without_transcend():
    load_all_cards()
    st = _make_state()
    _attack_combat(st, ["Assassin"])
    _play(st, "tide_chakra_yellow", types=["AttackReaction"])
    assert st.combat.attack_power == 5  # 3 + 2


def test_tide_chakra_plus4_with_transcend():
    load_all_cards()
    st = _make_state()
    st.players[1].current_turn_effects.append("TRANSCENDED")
    _attack_combat(st, ["Mystic"])
    _play(st, "tide_chakra_yellow", types=["AttackReaction"])
    assert st.combat.attack_power == 7  # 3 + 4
