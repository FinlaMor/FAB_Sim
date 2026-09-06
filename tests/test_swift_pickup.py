"""Swift Pickup — an optional cost paid out of the graveyard.

    "When this attacks, you may put a shuriken item from your graveyard on the
     bottom of your deck. If you do, this gets +1{p}. Go again"

The previous implementation was a `MOVE_REF` reading `shuriken_item`, a name
nothing in the ability ever set. The move silently did nothing while the
`MODIFY_ATTACK` beside it applied anyway, so the card pumped for free: built
states showed 4{p} with an EMPTY graveyard, and with a shuriken present the
shuriken was still sitting there afterwards. Costs-vs-effects again.

It could not be authored correctly before — the *_REF family needs a reference
and nothing could produce one from a graveyard — so `SELECT_FROM_ZONE` exists
for this.

The negatives carry the weight. An implementation that always pumps passes
"accept with a shuriken"; only the empty-graveyard and wrong-subtype cases tell
it apart from one that reads the cost.
"""
import copy

import pytest

from engine.card import CardDB
from engine.card_effects.dsl.loader import load_all_cards
from engine.state import Step
from scripts.talishar_attack_replay import (_accepting_agent, _replay_agent,
                                            our_power)
from tests.conftest import _make_state
import engine.engine as E

load_all_cards()
DB = CardDB()

CARD = "swift_pickup_red"
SHURIKEN = "silverwind_shuriken_blue"
NOT_SHURIKEN = "head_jab_red"


def _board(agent, graveyard=()):
    st = _make_state()
    st.card_db = DB
    st.step = Step.ACTION
    st.active_player = 1
    st.combat = None
    st.player_agents = {1: agent, 2: agent}
    E._setup_dsl_listeners(st)
    for slug in graveyard:
        card = copy.deepcopy(DB.get(slug))
        card.owner = card.controller = 1
        st.players[1].graveyard.add(card)
    return st


def _base():
    return DB.get(CARD).base_power or 0


def test_the_fuel_really_is_a_shuriken():
    """Guard for the rest: if SHURIKEN were not one, "accept with a shuriken"
    would fail for a reason that has nothing to do with the card."""
    assert "Shuriken" in (DB.get(SHURIKEN).subtypes or [])
    assert "Shuriken" not in (DB.get(NOT_SHURIKEN).subtypes or [])


def test_paying_bottoms_the_shuriken_and_pumps():
    st = _board(_accepting_agent, [SHURIKEN])
    assert our_power(st, CARD, attacker_id=1) == _base() + 1
    assert [c.slug for c in st.players[1].graveyard.cards] == []
    assert st.players[1].deck.cards[-1].slug == SHURIKEN


def test_declining_leaves_the_shuriken_and_grants_nothing():
    st = _board(_replay_agent, [SHURIKEN])
    assert our_power(st, CARD, attacker_id=1) == _base()
    assert [c.slug for c in st.players[1].graveyard.cards] == [SHURIKEN]


def test_an_empty_graveyard_grants_nothing_even_when_accepting():
    """The defect, directly. This read base + 1 before: the cost could not be
    paid and the pump applied regardless."""
    st = _board(_accepting_agent)
    assert our_power(st, CARD, attacker_id=1) == _base()


def test_a_card_that_is_not_a_shuriken_is_not_valid_fuel():
    st = _board(_accepting_agent, [NOT_SHURIKEN])
    assert our_power(st, CARD, attacker_id=1) == _base()
    assert [c.slug for c in st.players[1].graveyard.cards] == [NOT_SHURIKEN]


def test_go_again_is_unconditional():
    """Printed on the card, not part of the optional clause -- so it must not
    have been swept into the MAY along with the rest."""
    from engine.card_effects.dsl.loader import get_card
    play = [a for a in get_card(CARD).abilities
            if a.ability_type.upper() == "PLAY"]
    assert play, "go again should still be a plain PLAY ability"
    assert any(str(e.effect_type).upper() == "GO_AGAIN"
               for a in play for e in a.effects)
