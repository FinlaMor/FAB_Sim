""""Target defending card gets +N{d}" is not "the defending total gets +N".

MODIFY_DEFENSE_VALUE only ever moved combat.total_defense. With a single
defender the two readings agree, which is why this survived — they part company
exactly where the card is restrictive:

  shining_courage_red   "up to one target defending ACTION CARD gets +3{d}"
                        applied +3 to a block made entirely of equipment, where
                        the card has no legal target at all.
  sunkwater_exoshell    "THIS gets +1{d}", and the +1 went to the total, so it
                        was there whether or not the equipment was defending
                        alongside anything else. Its "IF YOU DO" was also
                        ignored: with an empty arsenal it drew and buffed
                        anyway — the payoff without the cost.
  platinum_amulet_blue  "target defending card gets +1{d}".
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

ACTION = "brutal_assault_red"        # plain action card, 3{d}
EQUIP = "arcanite_skullcap"          # 1{d} head equipment


def _card(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _state(defenders):
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    st.combat = CombatState(attacker_id=2, link_id=1, attack_power=0,
                            attack_card=None, keywords=[])
    st.combat.defending_cards = list(defenders)
    st.combat.total_defense = sum((c.defense or 0) for c in defenders)
    return st


def _stock_deck(st, pid=1, n=3):
    """Zone.add() stamps card.zone; assigning deck.cards leaves the cards
    claiming to be in 'inventory' and effect_keywords.draw refuses to move
    them. A test that stocks the deck the wrong way reads a silent no-draw as
    "the gate held"."""
    for _ in range(n):
        st.players[pid].deck.add(_card(ACTION, pid))


def _run(slug, st, source=None, index=0):
    source = source or _card(slug)
    run_ability(get_card(slug).abilities[index], source, None, st)
    return source


# --- shining_courage_red ----------------------------------------------------

def test_it_buffs_the_defending_action_card():
    action = _card(ACTION)
    st = _state([action])
    printed = action.defense

    _run("shining_courage_red", st)

    assert action.defense == printed + 3, (
        f"the action card is at {action.defense}{{d}}, expected {printed + 3}")


def test_it_does_nothing_when_only_equipment_is_defending():
    """"UP TO ONE target defending ACTION CARD" — there is no legal target."""
    gear = _card(EQUIP)
    st = _state([gear])
    printed = gear.defense

    _run("shining_courage_red", st)

    assert gear.defense == printed, "the equipment got +3{d} it is not eligible for"
    assert st.combat.total_defense == printed, (
        f"the defending total rose to {st.combat.total_defense} with no legal target")


def test_it_picks_the_action_card_out_of_a_mixed_block():
    action, gear = _card(ACTION), _card(EQUIP)
    st = _state([gear, action])
    action_printed, gear_printed = action.defense, gear.defense

    _run("shining_courage_red", st)

    assert action.defense == action_printed + 3
    assert gear.defense == gear_printed, "the equipment was buffed instead"


# --- sunkwater_exoshell -----------------------------------------------------

def test_exoshell_does_nothing_with_an_empty_arsenal():
    """"IF YOU DO" — no card to bottom, no draw and no +1{d}."""
    shell = _card("sunkwater_exoshell")
    st = _state([shell])
    st.players[1].arsenal.cards = []
    _stock_deck(st)
    hand_before = len(st.players[1].hand.cards)
    printed = shell.defense

    _run("sunkwater_exoshell", st, source=shell)

    assert len(st.players[1].hand.cards) == hand_before, (
        "it drew a card without putting one from arsenal on the bottom")
    assert shell.defense == printed, "it got +1{d} without paying for it"


def test_exoshell_pays_and_is_paid():
    shell = _card("sunkwater_exoshell")
    st = _state([shell])
    arsenal_card = _card(ACTION)
    st.players[1].arsenal.add(arsenal_card)
    arsenal_card.is_public = True
    _stock_deck(st)
    hand_before = len(st.players[1].hand.cards)
    printed = shell.defense

    _run("sunkwater_exoshell", st, source=shell)

    assert arsenal_card in st.players[1].deck.cards, (
        "the arsenal card did not go to the bottom of the deck")
    assert len(st.players[1].hand.cards) == hand_before + 1, "it did not draw"
    assert shell.defense == printed + 1, (
        f"the shell is at {shell.defense}{{d}}, expected {printed + 1}")


# --- platinum_amulet_blue ---------------------------------------------------

def test_amulet_buffs_a_defending_card():
    action = _card(ACTION)
    st = _state([action])
    printed = action.defense

    _run("platinum_amulet_blue", st)

    assert action.defense == printed + 1


def test_amulet_is_an_instant():
    """The printing says Instant; it was authored as ACTIVATE, which is an
    action and cannot be used in the defend step this card exists for."""
    assert get_card("platinum_amulet_blue").abilities[0].ability_type == "INSTANT"


def test_exoshell_bottoms_its_own_arsenal_card_not_the_opponents():
    """PUT_ARSENAL_BOTTOM defaults to OPPONENT — the three Disable printings
    ("put a card from THEIR arsenal on the bottom of THEIR deck") were its
    first users, so silence means the opponent. A card that says "YOUR
    arsenal" and omits the key hits the wrong player, which is why this card's
    own "if you do" could never be satisfied."""
    shell = _card("sunkwater_exoshell")
    st = _state([shell])
    mine, theirs = _card(ACTION, 1), _card(ACTION, 2)
    st.players[1].arsenal.add(mine)
    st.players[2].arsenal.add(theirs)
    mine.is_public = True
    theirs.is_public = True
    _stock_deck(st)

    _run("sunkwater_exoshell", st, source=shell)

    assert mine not in st.players[1].arsenal.cards, "it did not bottom its own card"
    assert theirs in st.players[2].arsenal.cards, (
        "it bottomed the OPPONENT's arsenal card")


def test_exoshell_will_not_bottom_a_face_down_arsenal_card():
    """"put a FACE-UP card from your arsenal" — arsenal cards are face down by
    default, so this excludes the ordinary case rather than decorating it."""
    shell = _card("sunkwater_exoshell")
    st = _state([shell])
    hidden = _card(ACTION, 1)
    st.players[1].arsenal.add(hidden)     # add() puts it in face down
    assert hidden.is_public is False
    _stock_deck(st)
    hand_before = len(st.players[1].hand.cards)

    _run("sunkwater_exoshell", st, source=shell)

    assert hidden in st.players[1].arsenal.cards, (
        "it bottomed a face-down card the text excludes")
    assert len(st.players[1].hand.cards) == hand_before, "it drew anyway"
