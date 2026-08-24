"""A cost comparison that ran backwards, and a payoff that reached nowhere.

CARD_COST_LTE and friends chose their operator with
`cost <= n if kind == "CARD_COST_LTE" else cost >= n`. The COST_LTE ALIAS is
not that one string, so it took the >= branch: urgent_delivery_yellow's "put a
Mechanologist item from your hand into the arena WITH COST LESS THAN OR EQUAL
TO the number of times you've boosted" matched exactly the expensive items the
text excludes. An alias that compiles but compares backwards is worse than no
alias -- the card works, visibly, on the wrong cards. The operator is now
derived from the suffix, which also gives the strict LT/GT forms nothing could
previously express.

mounting_anger_red: "you may banish an attack action card from your hand with
cost LESS THAN the number of Draconic chain links you control. If you do, it
gains +1{p} and YOU MAY PLAY IT THIS TURN."

  - both payoff halves re-filtered the WHOLE banished zone rather than acting
    on the card just banished, so with two eligible cards there it could pump
    one and unlock a different one;
  - neither reached the game state at all. MODIFY_ATTACK reads no target, and
    SET_FLAG appends a STRING to current_turn_effects while play.py consults
    `player.playable_from_banished`;
  - the bound was LTE where the card says "less than";
  - "you may" was compulsory, and the payoff was not gated on "if you do".
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.condition_types import compile_condition
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.state import ChainLink, CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

# A Draconic ATTACK ACTION, so it is both a legal banish target and a legal
# chain-link contributor.
DRACONIC_ATTACK = "mounting_anger_red"
CHEAP_ATTACK = "brutal_assault_red"      # cost 2
INSTANT = "shining_courage_red"


def _card(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _state(agent=None):
    st = _make_state()
    st.card_db = DB
    pick = agent or (lambda s, o, context="": o[0])
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    st.individual_turns = 1
    return st


# --- the cost comparison ----------------------------------------------------

@pytest.mark.parametrize("ctype,limit,expected", [
    ("COST_LTE", 2, True),      # cost 2 <= 2
    ("COST_LTE", 1, False),
    ("CARD_COST_LTE", 2, True),
    ("COST_GTE", 3, False),
    ("COST_GTE", 2, True),
    ("COST_LT", 2, False),      # strict: 2 is not < 2
    ("COST_LT", 3, True),
    ("COST_GT", 2, False),
    ("COST_GT", 1, True),
])
def test_the_operator_comes_from_the_name(ctype, limit, expected):
    """COST_LTE took the >= branch because it is not the literal string
    "CARD_COST_LTE"."""
    probe = _card(CHEAP_ATTACK)
    assert probe.cost == 2, "the fixture no longer has the cost these cases assume"

    fn = compile_condition(ctype, {"amount": limit})
    assert fn(probe, None, None) is expected


def test_the_alias_and_the_full_name_agree():
    """They are the same condition; disagreeing is the whole defect."""
    probe = _card(CHEAP_ATTACK)
    for n in range(0, 5):
        assert (compile_condition("COST_LTE", {"amount": n})(probe, None, None)
                == compile_condition("CARD_COST_LTE", {"amount": n})(probe, None, None))


# --- mounting_anger_red -----------------------------------------------------

def _hit(st, draconic_links=3):
    attack = _card(DRACONIC_ATTACK, 1)
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=attack, keywords=[])
    st.combat.hit = True
    st.chain_links = [
        ChainLink(chainlink_id=i + 1, attacker_id=1, attack_slug=DRACONIC_ATTACK,
                  attack_power=3, net_damage=3, keywords=[], from_weapon=False,
                  hit=True, talents=["Draconic"])
        for i in range(draconic_links)]
    return attack


def _run(st):
    run_ability(get_card("mounting_anger_red").abilities[0],
                _card("mounting_anger_red", 1), None, st)


def test_it_banishes_an_attack_action_from_hand():
    st = _state()
    _hit(st, draconic_links=3)
    held = _card(CHEAP_ATTACK)
    st.players[1].hand.add(held)

    _run(st)

    assert held in st.players[1].banished.cards, (
        f"the card is in {held.zone!r}")


def test_the_banished_card_becomes_playable_from_banish():
    """SET_FLAG appended a string nothing reads; play.py consults
    playable_from_banished."""
    st = _state()
    _hit(st, draconic_links=3)
    held = _card(CHEAP_ATTACK)
    st.players[1].hand.add(held)

    _run(st)

    assert any(c is held for c in st.players[1].playable_from_banished), (
        "the card was banished but never became playable")


def test_the_banished_card_gets_the_power():
    st = _state()
    _hit(st, draconic_links=3)
    held = _card(CHEAP_ATTACK)
    before = held.power
    st.players[1].hand.add(held)

    _run(st)

    assert held.power == before + 1, f"power is {held.power}, was {before}"


def test_the_pump_and_the_grant_land_on_the_SAME_card():
    """Each half re-filtered the banished zone, so with another eligible card
    already sitting there they could pick different ones."""
    st = _state()
    _hit(st, draconic_links=3)
    decoy = _card(CHEAP_ATTACK)
    st.players[1].banished.add(decoy)
    decoy_power = decoy.power
    held = _card(CHEAP_ATTACK)
    st.players[1].hand.add(held)

    _run(st)

    assert held.power == decoy_power + 1, "the pump missed the banished card"
    assert decoy.power == decoy_power, "it pumped a card already in banish"
    assert all(c is not decoy for c in st.players[1].playable_from_banished), (
        "it unlocked a card it did not banish")


def test_the_cost_bound_is_strictly_less_than():
    """"cost LESS THAN the number of Draconic chain links" — with 2 links a
    cost-2 card does not qualify."""
    st = _state()
    _hit(st, draconic_links=2)
    held = _card(CHEAP_ATTACK)
    assert held.cost == 2
    st.players[1].hand.add(held)

    _run(st)

    assert held in st.players[1].hand.cards, (
        "a cost-2 card was banished for 2 Draconic chain links")


def test_a_non_attack_card_is_not_eligible():
    st = _state()
    _hit(st, draconic_links=3)
    instant = _card(INSTANT)
    st.players[1].hand.add(instant)

    _run(st)

    assert instant in st.players[1].hand.cards, "it banished a non-attack card"


def test_it_is_optional():
    from engine.card_effects.ability_keywords import NO  # noqa: F401

    st = _state(agent=lambda s, o, context="": "none" if "none" in o else o[0])
    _hit(st, draconic_links=3)
    held = _card(CHEAP_ATTACK)
    st.players[1].hand.add(held)

    _run(st)

    assert held in st.players[1].hand.cards, "\"you may\" banished it anyway"


def test_nothing_is_granted_when_nothing_was_banished():
    """"IF YOU DO" — declining must not pay out."""
    st = _state(agent=lambda s, o, context="": "none" if "none" in o else o[0])
    _hit(st, draconic_links=3)
    st.players[1].hand.add(_card(CHEAP_ATTACK))

    _run(st)

    assert st.players[1].playable_from_banished == [], (
        "it granted a play with nothing banished")


def test_an_empty_hand_pays_out_nothing():
    st = _state()
    _hit(st, draconic_links=3)
    st.players[1].hand.cards = []

    _run(st)

    assert st.players[1].playable_from_banished == []
