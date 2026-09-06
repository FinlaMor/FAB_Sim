"""The attack on the chain right now counts as a chain link you control.

CR 7.0.3a: an attack added to the combat chain becomes the active-attack of
chain link N+1. CR 7.0.3c: that link's properties, control and ownership are
those of its active-attack. So while Phoenix Flame — itself Draconic — is on the
chain, it IS a Draconic chain link you control, and "2 or more Draconic chain
links" needs only ONE prior Draconic link plus itself.

`state.chain_links` receives a link only AFTER damage resolves, so counting that
list alone misses the live attack and every threshold reads one low. Against the
spectator corpus phoenix_flame_red agreed on 104 of 480 attacks and every single
disagreement was ours=0 theirs=1 — one short, every time. With this it is
480/480.

The DOUBLE-COUNT case is the one that makes this delicate: after damage the
active attack is in `chain_links` while `state.combat` is still set, so a naive
"always add the live attack" counts it twice.
"""
import copy

import pytest

from engine.card import CardDB
from engine.card_effects.dsl.condition_types import compile_condition
from engine.card_effects.dsl.loader import load_all_cards
from engine.state import ChainLink, CombatState, Step
from tests.conftest import _make_state
import engine.engine as E

load_all_cards()
DB = CardDB()

DRACONIC_ATTACK = "phoenix_flame_red"     # Draconic
PLAIN_ATTACK = "head_jab_red"             # not Draconic


def _state():
    st = _make_state()
    st.card_db = DB
    st.step = Step.ACTION
    st.active_player = 1
    st.combat = None
    E._setup_dsl_listeners(st)
    return st


def _card(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    c.owner = c.controller = pid
    return c


def _link(st, talents=("Draconic",), attacker=1, slug="prior_attack"):
    st.chain_links.append(ChainLink(
        chainlink_id=len(st.chain_links) + 1, attacker_id=attacker,
        attack_slug=slug, attack_power=0, net_damage=0, keywords=[],
        from_weapon=False, talents=list(talents)))


def _attack(st, slug, attacker=1):
    card = _card(slug, attacker)
    st.combat = CombatState(attacker_id=attacker,
                            link_id=len(st.chain_links) + 1,
                            attack_power=card.base_power or 0,
                            attack_card=card, keywords=[])
    return card


def _controls(st, card, amount, attribute="Draconic"):
    fn = compile_condition("CONTROLS_CHAIN_LINKS",
                           {"attribute": attribute, "amount": amount})
    return fn(card, None, st)


def test_the_live_attack_counts_toward_the_threshold():
    st = _state()
    _link(st)                      # one PRIOR Draconic link
    card = _attack(st, DRACONIC_ATTACK)
    assert _controls(st, card, 2), "1 prior + the live Draconic attack is 2"


def test_the_live_attack_alone_is_one_not_two():
    st = _state()
    card = _attack(st, DRACONIC_ATTACK)
    assert _controls(st, card, 1)
    assert not _controls(st, card, 2)


def test_a_non_draconic_live_attack_does_not_count_toward_draconic():
    st = _state()
    _link(st)
    card = _attack(st, PLAIN_ATTACK)
    assert _controls(st, card, 1)
    assert not _controls(st, card, 2), "the live attack is not Draconic"


def test_links_the_opponent_controls_are_not_yours():
    st = _state()
    _link(st, attacker=2)
    _link(st, attacker=2)
    card = _attack(st, DRACONIC_ATTACK)
    assert not _controls(st, card, 2)


def test_the_live_attack_is_not_counted_twice_after_it_resolves():
    """After damage the attack IS in chain_links, under the same chainlink_id,
    while state.combat is still set until the chain closes. Adding it again
    there would let one attack satisfy a threshold of 2 by itself."""
    st = _state()
    card = _attack(st, DRACONIC_ATTACK)
    # Mirror what the damage step does: append the link for the live attack.
    st.chain_links.append(ChainLink(
        chainlink_id=st.combat.link_id, attacker_id=1,
        attack_slug=card.slug, attack_power=0, net_damage=0, keywords=[],
        from_weapon=False, talents=list(card.talents or [])))
    assert _controls(st, card, 1)
    assert not _controls(st, card, 2), "counted twice"


def test_no_attribute_counts_every_link_you_control():
    st = _state()
    _link(st, talents=())
    _link(st, talents=("Ice",))
    card = _attack(st, PLAIN_ATTACK)
    assert _controls(st, card, 3, attribute="")
    assert not _controls(st, card, 4, attribute="")
