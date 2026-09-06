"""Become the Bottle — copying a name off the combat chain.

    "When this attacks, choose a card on the combat chain. This gets the chosen
     card's name. Go again"

It was on test_invented_refs.py's KNOWN_UNFIXED with the diagnosis "copying a
name is not expressible": it read refs COMBAT_CHAIN and SELECTED_CARD, names
nothing sets, and stored the result in a SET_FLAG nothing reads.

Two things were missing, and both are general now:

  * SELECT_FROM_ZONE could not reach the COMBAT CHAIN. The chain is a SHARED
    zone on the GameState, not a player zone, so the per-player fan-out could
    not see it -- this is the one selection that is not about anybody's zone.
  * SET_NAME copies the name.

A NAME IS A READABLE PROPERTY, which is the whole point of the card:
LAST_CHAIN_ATTACK's `name` form, "cards named X" and the Combo family all match
on it, so becoming a card's name really does switch on the combo cards looking
for that name. The last test here is the one that proves the copy is worth
anything.
"""
import copy

import pytest

from engine.card import CardDB
from engine.card_effects.dsl import dispatch
from engine.card_effects.dsl.condition_types import compile_condition
from engine.card_effects.dsl.loader import load_all_cards
from engine.state import ChainLink, CombatState
from scripts.talishar_attack_replay import _replay_agent
from tests.conftest import _make_state
import engine.engine as E

load_all_cards()
DB = CardDB()

CARDS = ["become_the_bottle_red", "become_the_bottle_yellow"]


def _attack(slug, chain=()):
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: _replay_agent, 2: _replay_agent}
    E._setup_dsl_listeners(st)
    for other in chain:
        c = copy.deepcopy(DB.get(other))
        c.owner = c.controller = 2
        st.combat_chain.add(c)
    card = copy.deepcopy(DB.get(slug))
    card.owner = card.controller = 1
    st.combat = CombatState(attacker_id=1, link_id=1,
                            attack_power=card.raw_power or 0,
                            attack_card=card, keywords=[])
    dispatch(st, "ON_ATTACK", slug, card=card, event=None)
    return st, card


@pytest.mark.parametrize("slug", CARDS)
def test_it_takes_the_chosen_cards_name(slug):
    _st, card = _attack(slug, chain=["head_jab_red"])
    assert card.name == DB.get("head_jab_red").name


@pytest.mark.parametrize("slug", CARDS)
def test_a_different_card_gives_a_different_name(slug):
    """Pins that the name is COPIED rather than hardcoded."""
    _st, card = _attack(slug, chain=["surging_strike_red"])
    assert card.name == DB.get("surging_strike_red").name


@pytest.mark.parametrize("slug", CARDS)
def test_an_empty_chain_leaves_the_name_alone(slug):
    _st, card = _attack(slug)
    assert card.name == DB.get(slug).name


@pytest.mark.parametrize("slug", CARDS)
def test_the_printed_name_is_preserved(slug):
    """base_name is the PRINTED name and is what Zone.add's reset_to_base_state
    restores when the object changes zone (CR 3.0.9) -- so the copy lasts
    exactly as long as this object does, and no longer."""
    _st, card = _attack(slug, chain=["head_jab_red"])
    assert card.base_name == DB.get(slug).name


def test_the_copied_name_is_what_combo_cards_read():
    """The payoff. LAST_CHAIN_ATTACK matches on the printed NAME, so a card that
    has become "Surging Strike" satisfies Whelming Gustwave's Combo -- which is
    the only reason copying a name is worth doing."""
    st, card = _attack("become_the_bottle_red", chain=["surging_strike_red"])
    st.chain_links.append(ChainLink(
        chainlink_id=1, attacker_id=1, attack_slug=card.slug,
        attack_power=0, net_damage=0, keywords=[], from_weapon=False))
    st.chain_links[-1].attack_name = card.name
    cond = compile_condition("LAST_CHAIN_ATTACK", {"name": card.name})
    assert cond is not None
    assert card.name == "Surging Strike"
