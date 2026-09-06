"""What a search FOUND has to be nameable, or the next sentence has nothing.

Search text usually keeps talking about the card it just fetched:

    katsu               "search your deck for a card with combo, banish it face
                         up, then shuffle your deck. YOU MAY PLAY IT this turn."
    iris_of_the_blossom "...reveal it, then put IT on top of your deck."
    lady_barthimont     "...banish IT."

SEARCH_DECK moved the card and then forgot it. Three drafts named `record_as`
or `into` to get it back and the handler read neither, so the follow-up clause
pointed at a ref nothing ever wrote:

  - GRANT_PLAY_FROM_BANISHED reads a ref and returns immediately when it
    resolves to None, so Katsu banished the combo card and never made it
    playable -- the whole point of the ability, silently absent;
  - audit_params saw an unread parameter on all three and the adoption gate
    correctly held them back, which is how this was found.

The default is "searched" so the common case needs no ceremony, and
`record_as` / `into` / `store_as` override it (the spelling the rest of the DSL
uses -- BANISH and DISCARD already take exactly these three).

WHY THE FAILED SEARCH MATTERS. The ref is written even when nothing was found,
as an empty list. A scope holds one set of names for the whole ability, so a
handler that only writes on success lets a LATER effect read what an EARLIER
one found -- "search for an X, then search for a Y and play it" would replay
the X. test_a_failed_search_writes_an_empty_ref pins that.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.card_effects.dsl.effect_types import compile_effect
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

COMBO_CARD = "back_heel_kick_red"    # has the Combo keyword
PLAIN_CARD = "brutal_assault_red"    # does not
FREE_CARD = "aspect_of_tiger_body_red"   # cost 0, to pay Katsu's discard


def _card(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _state():
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="", **kw: o[0]      # noqa: E731 -- take the offer
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    return st


def _ability(*effects):
    """A bare ability wrapping `effects`, so the ref scope is a real one."""
    from engine.card_effects.dsl.loader import _compile_ability
    return _compile_ability({"ability_type": "ON_PLAY", "effects": list(effects)})


def _run(st, source, *effects):
    run_ability(_ability(*effects), source, None, st)


def test_the_combo_card_is_really_a_combo_card():
    """Guards every search below: if COMBO_CARD stopped having the keyword the
    searches would find nothing and the assertions would pass vacuously."""
    assert any(str(k).lower().replace(" ", "") == "combo"
               for k in (DB.get(COMBO_CARD).keywords or []))
    assert not any(str(k).lower().replace(" ", "") == "combo"
                   for k in (DB.get(PLAIN_CARD).keywords or []))


def test_a_search_records_what_it_found_under_the_default_name():
    st = _state()
    src = _card(PLAIN_CARD)
    wanted = _card(COMBO_CARD)
    st.players[1].deck.add(wanted)

    _run(st, src,
         {"type": "SEARCH_DECK", "keyword": "combo",
          "destination": "banished", "amount": 1},
         {"type": "GRANT_PLAY_FROM_BANISHED", "ref": "searched"})

    assert wanted in st.players[1].banished.cards
    assert any(c is wanted for c in st.players[1].playable_from_banished), (
        "the search found the card but the next clause could not name it")


def test_record_as_names_the_ref():
    st = _state()
    src = _card(PLAIN_CARD)
    wanted = _card(COMBO_CARD)
    st.players[1].deck.add(wanted)

    _run(st, src,
         {"type": "SEARCH_DECK", "keyword": "combo", "destination": "banished",
          "amount": 1, "record_as": "fetched"},
         {"type": "GRANT_PLAY_FROM_BANISHED", "ref": "fetched"})

    assert any(c is wanted for c in st.players[1].playable_from_banished)


def test_the_ref_holds_the_card_the_search_matched_not_just_any():
    """A decoy sits in the deck alongside the answer. Re-filtering the banished
    zone (what several cards used to do instead of a ref) cannot tell them
    apart once both are there; the ref can."""
    st = _state()
    src = _card(PLAIN_CARD)
    decoy = _card(PLAIN_CARD)
    wanted = _card(COMBO_CARD)
    st.players[1].banished.add(decoy)          # already banished, not eligible
    st.players[1].deck.add(wanted)

    _run(st, src,
         {"type": "SEARCH_DECK", "keyword": "combo",
          "destination": "banished", "amount": 1},
         {"type": "GRANT_PLAY_FROM_BANISHED", "ref": "searched"})

    granted = st.players[1].playable_from_banished
    assert any(c is wanted for c in granted)
    assert all(c is not decoy for c in granted), (
        "the grant landed on a card the search never touched")


def test_a_failed_search_writes_an_empty_ref():
    """Two searches in one ability. The second finds nothing, and must not
    leave the first one's card readable -- one ref scope spans the ability."""
    st = _state()
    src = _card(PLAIN_CARD)
    wanted = _card(COMBO_CARD)
    st.players[1].deck.add(wanted)

    _run(st, src,
         {"type": "SEARCH_DECK", "keyword": "combo",
          "destination": "banished", "amount": 1},
         # nothing in the deck has this keyword any more
         {"type": "SEARCH_DECK", "keyword": "combo",
          "destination": "banished", "amount": 1},
         {"type": "GRANT_PLAY_FROM_BANISHED", "ref": "searched"})

    assert st.players[1].playable_from_banished == [], (
        "the failed second search replayed what the first one found")


# ----------------------------------------------------------------- katsu

def test_katsu_makes_the_searched_combo_card_playable():
    """The card this capability was missing for, end to end.

    "The first time an attack action card you control hits each turn, you may
     discard a card with cost 0. If you do, search your deck for a card with
     combo, banish it face up, then shuffle your deck. You may play it this
     turn."
    """
    st = _state()
    # Katsu's trigger is gated on an ATTACK ACTION you control having hit, so
    # the combat has to be real -- without it the ability declines silently and
    # every assertion below would be about a trigger that never ran.
    from engine.state import CombatState
    attack = _card(COMBO_CARD, 1)
    st.combat = CombatState(attacker_id=1, link_id=1,
                            attack_power=attack.raw_power or 0,
                            attack_card=attack, keywords=[])
    st.combat.hit = True

    hero = _card("katsu")
    wanted = _card(COMBO_CARD)
    st.players[1].deck.add(wanted)
    free = _card(FREE_CARD)
    assert (free.cost or 0) == 0, "the discard cost needs a cost-0 card"
    st.players[1].hand.add(free)

    run_ability(get_card("katsu").abilities[0], hero, None, st)

    assert wanted in st.players[1].banished.cards, "the search did not run"
    assert any(c is wanted for c in st.players[1].playable_from_banished), (
        "'you may play it this turn' reached the game state nowhere")
