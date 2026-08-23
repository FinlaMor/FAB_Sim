"""Four cards selected from refs that nothing anywhere sets.

SELECT_FROM_REF chooses a subset of a list a PRECEDING effect stored. All four
cards here named a ref out of thin air - "MYGRAVEYARD", "MYHAND", "arsenal",
"REVEALED" - so there was nothing to select from and every one of them did
nothing at all. What each actually needs is an object target over a zone, which
is a different primitive.

Two of them also reached for an effect whose default points the wrong way:

  SEARCH_DECK  had no way to name WHOSE deck, so mist_hunter_red - "search THEIR
               deck ... and banish them" - raided its own.
  REORDER_REF  defaults its player to OPPONENT, so sutcliffes_research_notes_red
               reordering "your deck" looked at the opponent's, found none of
               the revealed cards there and returned.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.ability_keywords import NO
from engine.card_effects.dsl.effect_types import compile_effect
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

ACTION = "brutal_assault_red"
# A RUNEBLADE attack action: brutal_assault_red is class Generic, so it is
# correctly excluded by Sutcliffe's Runeblade filter and cannot test it.
RUNEBLADE_ATTACK = "aether_slash_red"
# A real Aura CARD with a printed cost. spectral_shield is a TOKEN, and a token
# returned to hand ceases to exist - it cannot show that the return worked.
AURA = "act_of_glory_red"
CHI = "inner_chi_blue"
# Mystic is a TALENT, not a class: kano is a Wizard and would not satisfy it.
MYSTIC_HERO = "nuu"
NON_MYSTIC_HERO = "gravy_bones"


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


# --- beckoning_haunt --------------------------------------------------------

def test_it_returns_an_aura_from_the_graveyard_to_hand():
    st = _state()
    source = _card("beckoning_haunt")
    source.x_paid = DB.get(AURA).cost or 0
    aura = _card(AURA)
    st.players[1].graveyard.add(aura)

    run_ability(get_card("beckoning_haunt").abilities[0], source, None, st)

    assert aura in st.players[1].hand.cards, (
        f"the aura is in {aura.zone!r}, not hand")


def test_it_does_not_return_a_non_aura():
    st = _state()
    source = _card("beckoning_haunt")
    source.x_paid = 0
    other = _card(ACTION)
    st.players[1].graveyard.add(other)

    run_ability(get_card("beckoning_haunt").abilities[0], source, None, st)

    assert other in st.players[1].graveyard.cards, "it returned a non-aura"


def test_the_cost_x_restriction_is_an_equality():
    """"target aura WITH COST X" - not "cost X or less"."""
    st = _state()
    source = _card("beckoning_haunt")
    aura = _card(AURA)
    st.players[1].graveyard.add(aura)
    source.x_paid = (aura.cost or 0) + 1

    run_ability(get_card("beckoning_haunt").abilities[0], source, None, st)

    assert aura in st.players[1].graveyard.cards, (
        f"an aura of cost {aura.cost} was returned for X={source.x_paid}")


# --- burnished_bunkerplate --------------------------------------------------

def _combat(st, attacker=2):
    st.combat = CombatState(attacker_id=attacker, link_id=1, attack_power=3,
                            attack_card=_card(ACTION, attacker), keywords=[])
    return st.combat


def test_it_adds_the_arsenal_card_as_a_defender():
    st = _state()
    combat = _combat(st)
    source = _card("burnished_bunkerplate")
    arsenal_card = _card(ACTION)
    st.players[1].arsenal.add(arsenal_card)

    run_ability(get_card("burnished_bunkerplate").abilities[0], source, None, st)

    assert arsenal_card in combat.defending_cards, (
        "the arsenal card was not added to the chain link")


def test_it_adds_the_arsenal_card_and_not_itself():
    """ADD_DEFEND adds the SOURCE unless handed a target; this card adds a
    DIFFERENT object."""
    st = _state()
    combat = _combat(st)
    source = _card("burnished_bunkerplate")
    arsenal_card = _card(ACTION)
    st.players[1].arsenal.add(arsenal_card)

    run_ability(get_card("burnished_bunkerplate").abilities[0], source, None, st)

    assert source not in combat.defending_cards, (
        "the equipment added itself instead of the arsenal card")


def test_it_will_not_add_a_non_action_from_arsenal():
    st = _state()
    combat = _combat(st)
    source = _card("burnished_bunkerplate")
    instant = _card("shining_courage_red")
    st.players[1].arsenal.add(instant)
    assert "Action" not in (instant.types or [])

    run_ability(get_card("burnished_bunkerplate").abilities[0], source, None, st)

    assert instant not in combat.defending_cards


def test_it_is_optional():
    st = _state(agent=lambda s, o, context="": NO if NO in o else o[0])
    combat = _combat(st)
    source = _card("burnished_bunkerplate")
    arsenal_card = _card(ACTION)
    st.players[1].arsenal.add(arsenal_card)

    run_ability(get_card("burnished_bunkerplate").abilities[0], source, None, st)

    assert arsenal_card not in combat.defending_cards, "\"you MAY\" added it anyway"


# --- sutcliffes_research_notes_red ------------------------------------------

def _tokens(st, pid=1, slug="runechant"):
    return [c for c in st.players[pid].permanents.cards if c.slug == slug]


def test_one_runechant_per_attack_action_revealed():
    st = _state()
    for _ in range(3):
        st.players[1].deck.add(_card(RUNEBLADE_ATTACK))

    run_ability(get_card("sutcliffes_research_notes_red").abilities[0],
                _card("sutcliffes_research_notes_red"), None, st)

    assert len(_tokens(st)) == 3, (
        f"expected one Runechant per revealed attack action, got "
        f"{len(_tokens(st))}")


def test_no_runechants_when_nothing_qualifies():
    """It made ONE token, or none, on a gate that named a zone that is not one."""
    st = _state()
    for _ in range(3):
        st.players[1].deck.add(_card(CHI))

    run_ability(get_card("sutcliffes_research_notes_red").abilities[0],
                _card("sutcliffes_research_notes_red"), None, st)

    assert _tokens(st) == []


def test_the_revealed_cards_stay_in_the_controllers_deck():
    """REORDER_REF defaults to the OPPONENT's deck."""
    st = _state()
    revealed = [_card(RUNEBLADE_ATTACK) for _ in range(3)]
    for c in revealed:
        st.players[1].deck.add(c)
    before = len(st.players[1].deck.cards)

    run_ability(get_card("sutcliffes_research_notes_red").abilities[0],
                _card("sutcliffes_research_notes_red"), None, st)

    assert len(st.players[1].deck.cards) == before
    assert all(c in st.players[1].deck.cards for c in revealed)


# --- mist_hunter_red --------------------------------------------------------

def _hit_mystic(st, mystic=True):
    hero_slug = MYSTIC_HERO if mystic else NON_MYSTIC_HERO
    st.players[2].hero = _card(hero_slug, 2)
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=_card("mist_hunter_red"), keywords=[])
    st.combat.hit = True
    return st


def test_it_banishes_inner_chi_from_THEIR_deck():
    st = _state()
    _hit_mystic(st)
    theirs = [_card(CHI, 2) for _ in range(2)]
    for c in theirs:
        st.players[2].deck.add(c)
    mine = _card(CHI, 1)
    st.players[1].deck.add(mine)

    run_ability(get_card("mist_hunter_red").abilities[0],
                _card("mist_hunter_red"), None, st)

    assert all(c not in st.players[2].deck.cards for c in theirs), (
        "their Inner Chi were not banished")
    assert mine in st.players[1].deck.cards, (
        "it raided the attacker's OWN deck")


def test_it_does_nothing_against_a_non_mystic_hero():
    """The gate asked whether the ATTACK CARD is Mystic, not the hero hit."""
    st = _state()
    _hit_mystic(st, mystic=False)
    theirs = _card(CHI, 2)
    st.players[2].deck.add(theirs)

    run_ability(get_card("mist_hunter_red").abilities[0],
                _card("mist_hunter_red"), None, st)

    assert theirs in st.players[2].deck.cards


def test_it_leaves_other_cards_in_their_deck_alone():
    st = _state()
    _hit_mystic(st)
    keeper = _card(ACTION, 2)
    st.players[2].deck.add(keeper)
    st.players[2].deck.add(_card(CHI, 2))

    run_ability(get_card("mist_hunter_red").abilities[0],
                _card("mist_hunter_red"), None, st)

    assert keeper in st.players[2].deck.cards, (
        "it banished a card that is not an Inner Chi")
