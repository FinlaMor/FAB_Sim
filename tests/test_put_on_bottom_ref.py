""""Put IT on the bottom" cannot be spelled as a zone.

Three cards say "look at a card, then put THAT CARD on the bottom of a deck".
PUT_CARDS_BOTTOM only knew how to name a zone and move everything in it, so
each one landed somewhere different and none of them moved the looked-at card:

  seerstone            named no zone at all, so it fell through to the
                       hand+arsenal DEFAULT: activating it put a card from your
                       HAND and a card from your ARSENAL on the bottom of your
                       deck. A wrong default is more damaging than none.
  right_behind_you_red named the zone "top_deck", which is not a Player
                       attribute, so getattr found nothing and it bottomed
                       NOTHING.
  phantasmaclasm_red   wrapped it in a SELECT_FROM_REF carrying an `effects`
                       list that it does not read, so the whole body was
                       unreachable and the card only looked at the hand.

All three were also mandatory where two of them say "you MAY", and
phantasmaclasm's draw had no player, so the CASTER would have drawn the card
that is meant to compensate the victim.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.ability_keywords import NO, YES
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

TOP = "brutal_assault_red"
FILLER = "rusty_harpoon_blue"
HANDCARD = "amplifying_arrow_yellow"


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


def _decliner(st):
    """An agent that says no to every "you may" but still picks real options."""
    st.player_agents = {p: (lambda s, o, context="": NO if NO in o else o[0])
                        for p in (1, 2)}


def _stock(st, pid=1, top=TOP, n=4):
    first = _card(top, pid)
    st.players[pid].deck.add(first)
    for _ in range(n):
        st.players[pid].deck.add(_card(FILLER, pid))
    return first


def _run(slug, st, source=None, index=0):
    source = source or _card(slug)
    run_ability(get_card(slug).abilities[index], source, None, st)
    return source


# --- seerstone --------------------------------------------------------------

def test_seerstone_bottoms_the_looked_at_card():
    st = _state()
    top = _stock(st)

    _run("seerstone", st)

    assert st.players[1].deck.cards[-1] is top, (
        "the card looked at is not on the bottom")
    assert st.players[1].deck.cards[0] is not top


def test_seerstone_leaves_hand_and_arsenal_alone():
    """It fell through to the hand+arsenal default and bottomed one from each."""
    st = _state()
    _stock(st)
    in_hand = _card(HANDCARD)
    in_arsenal = _card(FILLER)
    st.players[1].hand.add(in_hand)
    st.players[1].arsenal.add(in_arsenal)

    _run("seerstone", st)

    assert in_hand in st.players[1].hand.cards, "it bottomed a card from HAND"
    assert in_arsenal in st.players[1].arsenal.cards, (
        "it bottomed a card from ARSENAL")


def test_seerstone_you_may_decline():
    st = _state()
    _decliner(st)
    top = _stock(st)

    _run("seerstone", st)

    assert st.players[1].deck.cards[0] is top, (
        "\"you MAY put it on the bottom\" moved it anyway")


def test_seerstone_still_creates_the_token():
    st = _state()
    _stock(st)

    _run("seerstone", st)

    assert "ponder" in [c.slug for c in st.players[1].permanents.cards]


# --- right_behind_you_red ---------------------------------------------------

def _defend_state(source):
    st = _state()
    st.combat = CombatState(attacker_id=2, link_id=1, attack_power=0,
                            attack_card=None, keywords=[])
    st.combat.defending_cards = [source]
    return st


def _defend_from_hand(st):
    """DEFENDS_WITH_OTHER_HAND_CARD reads combat.hand_defender_ids, NOT
    prev_zone — stamping prev_zone leaves the gate false and the whole ability
    silently does nothing, which reads as an engine bug."""
    other = _card(FILLER)
    st.combat.defending_cards.append(other)
    ids = getattr(st.combat, "hand_defender_ids", None)
    if ids is None:
        ids = set()
        st.combat.hand_defender_ids = ids
    ids.add(other.object_id)
    return other


def test_right_behind_you_bottoms_the_looked_at_card():
    source = _card("right_behind_you_red")
    st = _defend_state(source)
    top = _stock(st)
    other = _defend_from_hand(st)

    _run("right_behind_you_red", st, source=source)

    assert st.players[1].deck.cards[-1] is top, (
        "the looked-at card was not bottomed (it named a zone Player has not)")


def test_right_behind_you_buffs_itself():
    source = _card("right_behind_you_red")
    st = _defend_state(source)
    _stock(st)
    other = _defend_from_hand(st)
    printed, other_printed = source.defense, other.defense

    _run("right_behind_you_red", st, source=source)

    assert source.defense == printed + 1, "it did not get +1{d}"
    assert other.defense == other_printed, "the other defender got the +1{d}"


# --- phantasmaclasm_red -----------------------------------------------------

def test_phantasmaclasm_bottoms_a_card_from_their_hand():
    st = _state()
    theirs = _card(HANDCARD, 2)
    st.players[2].hand.add(theirs)
    _stock(st, pid=2)

    _run("phantasmaclasm_red", st)

    assert theirs not in st.players[2].hand.cards, "their card stayed in hand"
    assert theirs in st.players[2].deck.cards, (
        "their card did not reach their deck")


def test_phantasmaclasm_leaves_the_casters_hand_alone():
    st = _state()
    mine = _card(HANDCARD, 1)
    st.players[1].hand.add(mine)
    st.players[2].hand.add(_card(HANDCARD, 2))
    _stock(st, pid=1)
    _stock(st, pid=2)

    _run("phantasmaclasm_red", st)

    assert mine in st.players[1].hand.cards, "it bottomed the CASTER's card"


def test_phantasmaclasm_makes_them_draw_not_the_caster():
    """"THEY draw a card" is the compensation that makes the effect fair; the
    DRAW had no player, so it would have gone to the caster."""
    st = _state()
    st.players[2].hand.add(_card(HANDCARD, 2))
    _stock(st, pid=1)
    _stock(st, pid=2)
    mine_before = len(st.players[1].hand.cards)
    theirs_before = len(st.players[2].hand.cards)

    _run("phantasmaclasm_red", st)

    assert len(st.players[1].hand.cards) == mine_before, "the caster drew"
    # one card left their hand for the deck, one was drawn back
    assert len(st.players[2].hand.cards) == theirs_before, (
        "they did not draw their replacement")
