"""Regression: an ON_HIT effect that relocates the attack card (e.g. Herald of
Protection putting itself on the bottom of the deck) must NOT also see the card
sent to the graveyard by combat close. That double-move duplicated the card and
broke card conservation (real-card total rose by 1). See engine._close_combat_chain.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import engine.engine as E
from engine.state import CombatState
from engine.effect_keywords import put_object
from tests.conftest import _make_state, _make_card


def _put_attack_on_chain(st, pid):
    atk = _make_card(slug="herald", name="Herald", types=["Action", "Attack"])
    atk.owner = atk.controller = pid
    st.combat_chain.add(atk)  # where an attack lives during the combat chain
    st.combat = CombatState(attacker_id=pid, link_id=1, attack_power=4,
                            attack_card=atk, keywords=[])
    return atk


def test_relocated_attack_not_duplicated_into_graveyard():
    """When an ON_HIT effect already moved the attack to the deck, combat close
    leaves it there — it is not also copied into the graveyard."""
    st = _make_state()
    pid = 1
    atk = _put_attack_on_chain(st, pid)

    # Simulate Herald's PUT_SELF_BOTTOM_DECK firing during hit resolution.
    put_object(st, atk, "deck", destination_player_id=pid,
               source_player_id=pid, position=None)
    assert atk in st.players[pid].deck.cards

    E._close_combat_chain(st)

    assert st.players[pid].deck.cards.count(atk) == 1, "card left the deck / duplicated"
    assert atk not in st.players[pid].graveyard.cards, "relocated attack duplicated into graveyard"


def test_normal_attack_still_goes_to_graveyard():
    """A plain non-weapon attack still lands in the graveyard at combat close."""
    st = _make_state()
    pid = 1
    atk = _put_attack_on_chain(st, pid)

    E._close_combat_chain(st)

    assert atk in st.players[pid].graveyard.cards
    assert atk not in st.combat_chain.cards
