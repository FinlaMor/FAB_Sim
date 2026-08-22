""""You may pay {r}. If you do, this gets +1{p}." — the paying was free.

MAY compiled its sub-effects and its `else` block but never read `cost`, so the
prompt cost nothing and the bonus was unconditional. Both cards using it were
strictly stronger than printed, which is the quietest kind of wrong: nothing
fails, nothing looks odd, the card is just better than the text.

A cost inside a MAY is not an ability-level cost. It gates the OPTION, not the
ability — the ability still resolves when you decline, and declining runs the
`else` block ("unless you ..."). So it is compiled and paid here rather than in
AbilityDef.costs.

Both cards also named the wrong cost:
  * spark_spray_yellow's "pay {r}" is one RESOURCE, authored as PAY_LIFE 1.
  * hoist_em_up_red's "{t} an ALLY you control" was TAP_SELF, which taps the
    source card, with its "target": "ALLY" unread — so it tapped itself and took
    the bonus whether or not the player had an ally.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.effect_types import compile_effect
from engine.card_effects.dsl.loader import load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

ALLY = "zap_clappers"


def _state(accept=True):
    st = _make_state()
    st.card_db = DB
    # The base state starts with EMPTY decks, so a DRAW used as the observable
    # effect is a silent no-op and "the block did not run" passes whether the
    # block ran or not.
    for pid in (1, 2):
        st.players[pid].deck.cards = [_card("wounded_bull_red", owner=pid)
                                      for _ in range(5)]
    # ask_yes_no takes the first option; make the answer explicit per test.
    choice = (lambda s, o, context="": o[0] if accept else o[-1])
    st.player_agents = {1: choice, 2: choice}
    E._setup_dsl_listeners(st)
    return st


def _card(slug, owner=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = owner
    return c


def test_a_may_cost_is_actually_paid():
    st = _state(accept=True)
    st.players[1].resources = 3
    card = _card("wounded_bull_red")

    compile_effect("MAY", {"cost": [{"type": "PAY_RESOURCES", "amount": 1}],
                           "effects": [{"type": "DRAW", "amount": 1}]})(card, None, st)

    assert st.players[1].resources == 2, "the cost was not paid"


def test_an_unpayable_may_does_not_run_its_block():
    """Not payable means the option is not on the table."""
    st = _state(accept=True)
    st.players[1].resources = 0
    before = len(st.players[1].hand.cards)
    card = _card("wounded_bull_red")

    compile_effect("MAY", {"cost": [{"type": "PAY_RESOURCES", "amount": 2}],
                           "effects": [{"type": "DRAW", "amount": 1}]})(card, None, st)

    assert len(st.players[1].hand.cards) == before, (
        "the block ran without the cost being payable")


def test_an_unpayable_may_runs_the_else_block():
    """"lose 2{h} UNLESS you discard a card" — the penalty still applies when
    you cannot pay, not only when you decline."""
    st = _state(accept=True)
    st.players[1].resources = 0
    before = st.players[1].life
    card = _card("wounded_bull_red")

    compile_effect("MAY", {"cost": [{"type": "PAY_RESOURCES", "amount": 5}],
                           "effects": [{"type": "DRAW", "amount": 1}],
                           "else": [{"type": "LOSE_LIFE", "amount": 2}]})(card, None, st)

    assert st.players[1].life == before - 2


def test_spark_spray_pays_resources_not_life():
    """"you may pay {r}" is one resource point."""
    from engine.card_effects.dsl.loader import get_card

    st = _state(accept=True)
    st.players[1].resources = 3
    life_before = st.players[1].life
    card = _card("spark_spray_yellow")
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=card, keywords=[])
    st.combat.base_attack_power = 3

    for eff in get_card("spark_spray_yellow").abilities[0].effects:
        eff.fn(card, None, st)

    assert st.players[1].resources == 2, "the resource was not paid"
    assert st.players[1].life == life_before, "it paid LIFE instead of a resource"


def test_hoist_em_up_taps_an_ally_not_itself():
    """"you may {t} an ALLY you control"."""
    from engine.card_effects.dsl.loader import get_card

    st = _state(accept=True)
    ally = _card(ALLY)
    ally.subtypes = list(getattr(ally, "subtypes", None) or []) + ["Ally"]
    ally.tapped = False
    st.players[1].permanents.cards.append(ally)

    card = _card("hoist_em_up_red")
    card.tapped = False
    st.combat = CombatState(attacker_id=2, link_id=1, attack_power=3,
                            attack_card=_card("wounded_bull_red", owner=2),
                            keywords=[])

    for eff in get_card("hoist_em_up_red").abilities[0].effects:
        eff.fn(card, None, st)

    assert ally.tapped is True, "the ally was not tapped"
    assert card.tapped is False, "it tapped itself instead of the ally"


def test_hoist_em_up_gets_nothing_without_an_ally():
    """With no ally the cost is unpayable, so the +1{d} must not happen."""
    from engine.card_effects.dsl.loader import get_card

    st = _state(accept=True)
    card = _card("hoist_em_up_red")
    attacker = _card("wounded_bull_red", owner=2)
    st.combat = CombatState(attacker_id=2, link_id=1, attack_power=3,
                            attack_card=attacker, keywords=[])
    st.combat.defense_mods = []

    for eff in get_card("hoist_em_up_red").abilities[0].effects:
        eff.fn(card, None, st)

    assert not st.combat.defense_mods, (
        "it took +1{d} with no ally to tap")
