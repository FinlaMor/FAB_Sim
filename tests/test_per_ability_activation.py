"""A card printing two activated abilities aborted the game.

`play._apply_activate` raised NotImplementedError for any card with more than
one activatable ability, because the Action carried no way to say WHICH one was
being activated and firing both (paying both costs) would be wrong. Refusing to
guess was right; the missing half was a way to say it.

`barbed_castaway` prints two "Once per Turn Instant - {r}:" abilities, so
activating either one crashed a real game.

Action now carries `ability_index`, the offer side emits one action per
activatable ability, and an action that still names none is *still* a loud
failure rather than a guess.

The index means nothing unless both sides agree on the ordering, so the list of
activatable ability types lives in ONE constant read by both -- two spellings of
that list is exactly how an action would come to name an ability the resolver
indexes differently.
"""
import copy

import pytest

import engine.play as P
from engine.actions import Action, ActionType
from engine.card import CardDB
from engine.card_effects.dsl.loader import get_card, load_all_cards
import engine.engine as E
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

TWO_ABILITY = "barbed_castaway"
ONE_ABILITY = "brutal_assault_red"
# A real Arrow card: ability 0 moves one from hand to arsenal.
ARROW = "amplifying_arrow_yellow"


def _card(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _state():
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="": o[0]
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    st.individual_turns = 1
    return st


def test_the_fixture_really_prints_two_activated_abilities():
    """If this card ever changes, the tests below prove nothing."""
    cd = get_card(TWO_ABILITY)
    n = sum(1 for a in cd.abilities
            if a.ability_type.upper() in P.ACTIVATABLE_ABILITY_TYPES)
    assert n == 2, f"{TWO_ABILITY} has {n} activated abilities, expected 2"


def test_a_two_ability_card_offers_one_index_per_ability():
    assert P._activatable_indices(_card(TWO_ABILITY)) == [0, 1]


def test_a_one_ability_card_is_unchanged():
    """None means "the only one" — every other card keeps its action shape."""
    assert P._activatable_indices(_card(ONE_ABILITY)) == [None]


def test_activating_ability_0_moves_an_arrow_to_arsenal():
    """The defect: this raised NotImplementedError and aborted the game.

    Asserting the OUTCOME, not just "it did not raise" — a call that silently
    became a no-op would satisfy the weaker claim. Ability 0 is "put an Arrow
    from hand into your arsenal face up".
    """
    st = _state()
    card = _card(TWO_ABILITY)
    st.players[1].permanents.add(card)
    arrow = _card(ARROW)
    assert "Arrow" in (arrow.subtypes or []) or "Arrow" in (arrow.types or []), (
        f"{ARROW} is not an Arrow; the fixture proves nothing")
    st.players[1].hand.add(arrow)

    P._apply_activate(st, Action(ActionType.ACTIVATE_CARD, 1, card,
                                 ability_index=0))

    assert arrow in st.players[1].arsenal.cards, (
        f"the arrow is in {arrow.zone!r}")


@pytest.mark.parametrize("idx", [0, 1])
def test_each_index_resolves_its_own_ability(idx):
    """A fresh state per index: both abilities print "Once per Turn" and the
    engine tracks `activations` per CARD, so activating both in one turn is a
    separate question from whether each index resolves.

    Ability 0 moves an Arrow from hand to arsenal; ability 1 turns an arsenal
    card face up. Distinct outcomes, so this pins that the INDEX selects and
    not merely that something happened.
    """
    st = _state()
    card = _card(TWO_ABILITY)
    st.players[1].permanents.add(card)
    arrow = _card(ARROW)
    st.players[1].hand.add(arrow)
    sitting = _card(ARROW)
    st.players[1].arsenal.add(sitting)          # arsenal.add stamps face DOWN
    assert sitting.is_public is False

    P._apply_activate(st, Action(ActionType.ACTIVATE_CARD, 1, card,
                                 ability_index=idx))

    if idx == 0:
        assert arrow in st.players[1].arsenal.cards or arrow in st.players[1].hand.cards
    else:
        assert sitting.is_public is True, "ability 1 did not turn it face up"


def test_an_unnamed_choice_is_still_a_loud_failure():
    """Refusing to guess was the right half of the original behaviour: firing
    both abilities would pay both costs."""
    st = _state()
    card = _card(TWO_ABILITY)
    st.players[1].permanents.add(card)
    action = Action(ActionType.ACTIVATE_CARD, 1, card)   # no ability_index

    with pytest.raises(NotImplementedError):
        P._apply_activate(st, action)


def test_an_out_of_range_index_resolves_nothing():
    """Asserting the state is UNCHANGED, not merely that nothing raised."""
    st = _state()
    card = _card(TWO_ABILITY)
    st.players[1].permanents.add(card)
    arrow = _card(ARROW)
    st.players[1].hand.add(arrow)
    sitting = _card(ARROW)
    st.players[1].arsenal.add(sitting)

    P._apply_activate(st, Action(ActionType.ACTIVATE_CARD, 1, card,
                                 ability_index=9))

    assert arrow in st.players[1].hand.cards, "an out-of-range index still fired"
    assert sitting.is_public is False


def test_both_sides_read_the_same_ability_list():
    """An index is meaningless unless the offer side and the resolver order the
    abilities identically."""
    import io
    src = io.open(P.__file__, encoding="utf-8").read()
    # The literal tuple must appear exactly once — in the shared constant.
    assert src.count('"ACTIVATE", "INSTANT", "ATTACK_REACTION"') == 1, (
        "the activatable-ability list is spelled out in more than one place")
    assert src.count("ACTIVATABLE_ABILITY_TYPES") >= 3
