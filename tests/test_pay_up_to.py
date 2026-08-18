"""'You may pay up to {r}{r}{r}. <do something> that many times.'

A variable OPTIONAL payment made during resolution — not a play cost. The player
chooses how much to pay, and the amount paid becomes X for the following effect.

Both cards had an invented amount string that resolved to 0, so the payoff was
always nothing: Bask created no Might, Bully Tactics intimidated zero times.
10 cards in the corpus use this wording.

PAY_UP_TO stores the paid amount and PAID_AMOUNT reads it, mirroring
ROLL / ROLL_RESULT rather than inventing a second mechanism.
"""
import copy

import pytest

from engine.card import Card, CardDB
from engine.card_effects.dsl import dispatch
from engine.card_effects.dsl.effect_types import _resolve_amount, compile_effect
from engine.card_effects.dsl.loader import load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()


def _agent_pays(n):
    """Choose exactly n if offered, else the largest option (options are
    offered high-to-low)."""
    def _a(state, options, context=""):
        return n if n in options else options[0]
    return _a


def _state(agent=None, resources=10):
    st = _make_state()
    st.card_db = DB
    a = agent or _agent_pays(3)
    st.player_agents = {1: a, 2: a}
    st.players[1].resources = resources
    return st


def _card(slug, owner=1):
    c = copy.deepcopy(DB.get(slug))
    c.owner = c.controller = owner
    return c


def _attack(st, card):
    bp = card.power or 0
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=bp,
                            attack_card=card, keywords=[])
    st.combat.base_attack_power = bp
    dispatch(st, "ON_ATTACK", card.slug, card=card, event=None)


# --- the payment -----------------------------------------------------------

def test_pays_what_the_player_chooses():
    st = _state(agent=_agent_pays(2))
    card = _card("bask_in_your_own_greatness_red")
    before = st.players[1].resources
    compile_effect("PAY_UP_TO", {"max": 3})(card, None, st)
    assert st.players[1].resources == before - 2
    assert _resolve_amount({"type": "PAID_AMOUNT"}, st, card) == 2


def test_paying_zero_is_allowed():
    # "you MAY pay" — declining entirely must be possible and must charge nothing.
    st = _state(agent=_agent_pays(0))
    card = _card("bask_in_your_own_greatness_red")
    before = st.players[1].resources
    compile_effect("PAY_UP_TO", {"max": 3})(card, None, st)
    assert st.players[1].resources == before
    assert _resolve_amount({"type": "PAID_AMOUNT"}, st, card) == 0


def test_cannot_pay_more_than_you_have():
    # The cap is min(printed max, resources actually held) — otherwise a player
    # with 1 resource could "pay" 3 and go negative.
    st = _state(agent=_agent_pays(3), resources=1)
    card = _card("bask_in_your_own_greatness_red")
    compile_effect("PAY_UP_TO", {"max": 3})(card, None, st)
    assert st.players[1].resources == 0
    assert _resolve_amount({"type": "PAID_AMOUNT"}, st, card) == 1


def test_cannot_pay_more_than_the_printed_max():
    st = _state(agent=_agent_pays(9), resources=10)
    card = _card("bask_in_your_own_greatness_red")
    compile_effect("PAY_UP_TO", {"max": 3})(card, None, st)
    assert st.players[1].resources == 7


# --- the payoff ------------------------------------------------------------

def test_bask_creates_one_might_per_resource_paid():
    st = _state(agent=_agent_pays(2))
    card = _card("bask_in_your_own_greatness_red")
    _attack(st, card)
    might = [c for c in st.players[1].permanents.cards if c.slug == "might"]
    assert len(might) == 2


def test_bask_creates_nothing_when_paying_zero():
    # The negative that matters: an unresolved amount ALSO produces zero, so the
    # positive test alone cannot tell a working card from a broken one.
    st = _state(agent=_agent_pays(0))
    card = _card("bask_in_your_own_greatness_red")
    _attack(st, card)
    assert [c for c in st.players[1].permanents.cards if c.slug == "might"] == []


def test_intimidate_repeats_by_amount():
    st = _state()
    card = _card("bully_tactics_red")
    st.players[2].hand.add(Card(slug="a", name="a", types=["Action"]))
    st.players[2].hand.add(Card(slug="b", name="b", types=["Action"]))
    before = len(st.players[2].hand.cards)
    compile_effect("INTIMIDATE", {"amount": 2})(card, None, st)
    assert len(st.players[2].hand.cards) == before - 2


def test_intimidate_still_defaults_to_once():
    st = _state()
    card = _card("bully_tactics_red")
    for s in ("a", "b"):
        st.players[2].hand.add(Card(slug=s, name=s, types=["Action"]))
    before = len(st.players[2].hand.cards)
    compile_effect("INTIMIDATE", {})(card, None, st)
    assert len(st.players[2].hand.cards) == before - 1


# --- migration guard -------------------------------------------------------

@pytest.mark.parametrize("slug", ["bask_in_your_own_greatness_red", "bully_tactics_red"])
def test_no_invented_payment_amount_remains(slug):
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "engine" / "card_effects" / "json"
    path = [p for p in root.rglob(f"{slug}.json") if ".quarantine" not in p.parts][0]
    abilities = json.dumps(json.loads(path.read_text(encoding="utf-8"))["abilities"])
    for invented in ("PAY_AMOUNT", "PAYMENT_AMOUNT", "UP_TO_3"):
        assert invented not in abilities, f"{slug} still carries {invented}"
    assert "PAY_UP_TO" in abilities and "PAID_AMOUNT" in abilities
