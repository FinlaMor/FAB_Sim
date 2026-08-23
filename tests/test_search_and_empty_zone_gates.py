"""Two families: a search that names nothing, and a gate that is always true.

"amount": 0 on CARD_IN_ZONE meant count >= 0 - TRUE IN EVERY STATE. All three
cards in the corpus that author it say "if you have NO cards in <zone>", so the
gate was the exact opposite of the restriction each states. Zero is meaningless
as a lower bound, which is why "exactly none" is the only non-vacuous reading.

SEARCH_DECK read neither a nested `filter` dict nor the plain "card_type"
spelling, so a search that names what it is looking for matched ANY card and
fetched whatever came first. A search that names a card and returns a different
one is worse than a search that fails.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.condition_types import compile_condition
from engine.card_effects.dsl.effect_types import compile_effect
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

ARROW = "amplifying_arrow_yellow"
NOT_ARROW = "brutal_assault_red"


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


# --- the empty-zone gate ----------------------------------------------------

@pytest.mark.parametrize("zone", ["hand", "arsenal", "soul"])
def test_amount_zero_means_none_not_at_least_none(zone):
    st = _state()
    source = _card(NOT_ARROW)
    fn = compile_condition("CARD_IN_ZONE", {"zone": zone, "amount": 0})

    assert fn(source, None, st) is True, f"an empty {zone} did not satisfy it"

    getattr(st.players[1], zone).add(_card(ARROW))
    assert fn(source, None, st) is False, (
        f"a non-empty {zone} still satisfied \"no cards in {zone}\"")


def test_an_explicit_count_gte_zero_is_left_alone():
    """Only a BARE amount: 0 is reinterpreted; someone writing count_gte: 0 has
    said what they mean."""
    st = _state()
    st.players[1].hand.add(_card(ARROW))
    fn = compile_condition("CARD_IN_ZONE", {"zone": "hand", "count_gte": 0})

    assert fn(_card(NOT_ARROW), None, st) is True


def test_a_positive_amount_is_still_a_lower_bound():
    st = _state()
    st.players[1].hand.add(_card(ARROW))
    fn = compile_condition("CARD_IN_ZONE", {"zone": "hand", "amount": 1})

    assert fn(_card(NOT_ARROW), None, st) is True
    st.players[1].hand.add(_card(ARROW))
    assert fn(_card(NOT_ARROW), None, st) is True


# --- SEARCH_DECK filters ----------------------------------------------------

def _stock_deck(st, pid=1):
    """A non-arrow FIRST, so an unfiltered search takes the wrong card."""
    first = _card(NOT_ARROW, pid)
    st.players[pid].deck.add(first)
    arrow = _card(ARROW, pid)
    st.players[pid].deck.add(arrow)
    return first, arrow


def test_a_nested_filter_dict_narrows_the_search():
    st = _state()
    wrong, arrow = _stock_deck(st)

    compile_effect("SEARCH_DECK", {
        "filter": {"type": "CARD_IN_ZONE", "zones": ["deck"],
                   "subtypes": ["arrow"]},
        "amount": 1, "put_on_top": True})(_card(NOT_ARROW), None, st)

    assert st.players[1].deck.cards[0] is arrow, (
        f"it fetched {st.players[1].deck.cards[0].slug}, not the arrow")


def test_the_plain_card_type_spelling_narrows_the_search():
    st = _state()
    wrong, arrow = _stock_deck(st)

    compile_effect("SEARCH_DECK", {"card_type": "Arrow", "amount": 1,
                                   "put_on_top": True})(_card(NOT_ARROW), None, st)

    assert st.players[1].deck.cards[0] is arrow


# --- nock_the_deathwhistle_blue ---------------------------------------------

def test_nock_puts_an_arrow_on_top():
    st = _state()
    wrong, arrow = _stock_deck(st)

    run_ability(get_card("nock_the_deathwhistle_blue").abilities[0],
                _card("nock_the_deathwhistle_blue"), None, st)

    assert st.players[1].deck.cards[0] is arrow, (
        f"top of deck is {st.players[1].deck.cards[0].slug}")


def test_nock_is_not_gated_on_controlling_an_azalea_token():
    """"Azalea Specialization" is a DECKBUILDING restriction (slug_index records
    it under legalHeroes), not a game state - and Azalea is a hero, not a token.
    The gate was false in every game, so the card did nothing at all."""
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    raw = json.loads(next(root.rglob("nock_the_deathwhistle_blue.json"))
                     .read_text(encoding="utf-8"))
    blob = json.dumps(raw.get("abilities", []))
    assert "CONTROLS_TOKEN_TYPE" not in blob, blob


# --- pathing_helix_yellow ---------------------------------------------------

def _hit_state():
    st = _state()
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=_card("pathing_helix_yellow"), keywords=[])
    st.combat.hit = True
    return st


def test_pathing_helix_moves_a_card_from_hand_face_down():
    st = _hit_state()
    held = _card(NOT_ARROW)
    st.players[1].hand.add(held)
    top = _card(ARROW)
    st.players[1].deck.add(top)

    run_ability(get_card("pathing_helix_yellow").abilities[0],
                _card("pathing_helix_yellow"), None, st)

    assert held in st.players[1].arsenal.cards, "the hand card did not move"
    assert held.is_public is False, "it went in face up"
    assert top in st.players[1].deck.cards, "it tutored from the DECK instead"


def test_pathing_helix_does_nothing_with_a_full_arsenal():
    """The gate was amount: 0, i.e. "zero or more" - true in every state."""
    st = _hit_state()
    sitting = _card(ARROW)
    st.players[1].arsenal.add(sitting)
    held = _card(NOT_ARROW)
    st.players[1].hand.add(held)

    run_ability(get_card("pathing_helix_yellow").abilities[0],
                _card("pathing_helix_yellow"), None, st)

    assert held in st.players[1].hand.cards, (
        "it moved a card with a non-empty arsenal")
    assert sitting in st.players[1].arsenal.cards


def test_pathing_helix_is_optional():
    from engine.card_effects.ability_keywords import NO

    st = _hit_state()
    st.player_agents = {p: (lambda s, o, context="": NO if NO in o else o[0])
                        for p in (1, 2)}
    held = _card(NOT_ARROW)
    st.players[1].hand.add(held)

    run_ability(get_card("pathing_helix_yellow").abilities[0],
                _card("pathing_helix_yellow"), None, st)

    assert held in st.players[1].hand.cards, "\"you MAY\" moved it anyway"


# --- unwinding_finality_red -------------------------------------------------

def test_unwinding_finality_no_longer_tutors_from_the_deck():
    """Its fragment clause searched the DECK for ANY card and put it on top -
    a tutor from the wrong zone with no filter, strictly stronger than printed
    and not the same effect. Fragment has no implementation to gate it on."""
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    raw = json.loads(next(root.rglob("unwinding_finality_red.json"))
                     .read_text(encoding="utf-8"))
    blob = json.dumps(raw.get("abilities", []))
    assert "SEARCH_DECK" not in blob, blob


def test_unwinding_finality_still_draws_on_hit():
    st = _state()
    st.players[1].deck.add(_card(ARROW))
    before = len(st.players[1].hand.cards)

    run_ability(get_card("unwinding_finality_red").abilities[0],
                _card("unwinding_finality_red"), None, st)

    assert len(st.players[1].hand.cards) == before + 1


def test_put_on_top_actually_repositions_the_card():
    """"deck_top" is not a ZONE. put_object looks the destination up by name on
    the Player and finds nothing, so every "search your deck ... and put it on
    top" silently left the card where it was - and then shuffled, which is the
    one thing that makes the failure invisible."""
    st = _state()
    wrong, arrow = _stock_deck(st)
    for _ in range(3):
        st.players[1].deck.add(_card(NOT_ARROW))

    compile_effect("SEARCH_DECK", {"subtype": "Arrow", "amount": 1,
                                   "destination": "deck_top"})(
        _card(NOT_ARROW), None, st)

    assert st.players[1].deck.cards[0] is arrow, (
        f"top of deck is {st.players[1].deck.cards[0].slug}")
    assert st.players[1].deck.cards.count(arrow) == 1, "the card was duplicated"
