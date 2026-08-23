"""A dropped filter on CARD_IN_ZONE does not disable a gate - it opens it.

CARD_IN_ZONE counts cards in a zone and returns "at least one" by default, so
every filter it fails to read widens the question to "is this zone non-empty".
Five cards asked something much narrower and got that instead:

  buzzard_helm         "if a card with 6 or more {p} is discarded this way"
                       became "is your hand non-empty" - +1{d} on essentially
                       every defend. It also asked about the HAND rather than
                       about what was discarded, which differ exactly when the
                       random discard misses.
  metex_red            "an item with cost 0 or 1" became "any card", on an
                       effect that puts cards on the BOTTOM OF YOUR DECK rather
                       than into the arena.
  break_open_the_...   "a face-up YELLOW card" asked for card_class "YELLOW" -
                       yellow is a COLOUR, no card has it as a class - so the
                       gate matched nothing and the tokens were unreachable.
  swift_shot_red       "card": "swift_shot_red" asked only whether the arsenal
                       was non-empty, which is true whenever this card is there
                       and just as true when it is not.
  rotten_remains_blue  "a card with 1{p}" was power:1, which it did not read.

The exact spellings (cost, power, face_up, card, a nested filter dict, and
player ANY) are now read.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.condition_types import compile_condition
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

BIG = "brutal_assault_red"        # 6{p}
# 1{p}. autumns_touch_red was the first pick here and has SEVEN power, which
# made the "small discard" cases pass the 6{p} gate and read as engine bugs.
SMALL = "rusty_harpoon_blue"
YELLOW = "amplifying_arrow_yellow"
# "Item" is a SUBTYPE, not a type (types are Action/Equipment/Instant/...),
# which is why the card's filter uses CARD_IS_TYPE - it checks both.
ITEM = "absorption_dome_yellow"   # Action - Item, cost 0


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


def _run(slug, st, source=None, index=0):
    source = source or _card(slug)
    run_ability(get_card(slug).abilities[index], source, None, st)
    return source


# --- the condition ----------------------------------------------------------

def test_exact_cost_and_power_are_read():
    st = _state()
    big = _card(BIG)
    st.players[1].hand.add(big)

    exact = compile_condition("CARD_IN_ZONE", {"zone": "hand", "power": big.power})
    wrong = compile_condition("CARD_IN_ZONE", {"zone": "hand", "power": big.power + 1})

    assert exact(_card(BIG), None, st) is True
    assert wrong(_card(BIG), None, st) is False, (
        "an exact power filter matched a card with different {p}")


def test_a_nested_filter_dict_is_read():
    """buzzard_helm authored {"filter": {"power_gte": 6}}; unread, the whole
    condition reduced to "is the zone non-empty"."""
    st = _state()
    st.players[1].hand.add(_card(SMALL))

    fn = compile_condition("CARD_IN_ZONE",
                           {"zone": "hand", "filter": {"power_gte": 6}})

    assert fn(_card(BIG), None, st) is False, (
        "the nested filter was dropped and any card in hand satisfied it")


def test_face_up_is_read():
    st = _state()
    hidden = _card(YELLOW)
    st.players[1].arsenal.add(hidden)      # add() stamps arsenal face down
    assert hidden.is_public is False

    fn = compile_condition("CARD_IN_ZONE", {"zone": "arsenal", "face_up": True})
    assert fn(_card(BIG), None, st) is False

    hidden.is_public = True
    assert fn(_card(BIG), None, st) is True


def test_a_named_card_is_read():
    st = _state()
    st.players[1].arsenal.add(_card(SMALL))

    fn = compile_condition("CARD_IN_ZONE",
                           {"zone": "arsenal", "card": "swift_shot_red"})

    assert fn(_card(BIG), None, st) is False, (
        "an unnamed card satisfied a gate that names one")


def test_player_any_looks_at_both_sides():
    st = _state()
    theirs = _card(YELLOW, 2)
    st.players[2].arsenal.add(theirs)
    theirs.is_public = True

    mine_only = compile_condition("CARD_IN_ZONE", {"zone": "arsenal",
                                                   "color": "yellow"})
    either = compile_condition("CARD_IN_ZONE", {"zone": "arsenal",
                                                "color": "yellow",
                                                "player": "ANY"})

    assert mine_only(_card(BIG), None, st) is False
    assert either(_card(BIG), None, st) is True, "\"any arsenal\" saw only mine"


def test_colour_reads_the_printed_colour():
    """Card.color is None on a real card; the printing is on base_color."""
    st = _state()
    yellow = _card(YELLOW)
    assert yellow.color is None and yellow.base_color == "Yellow"
    st.players[1].hand.add(yellow)

    fn = compile_condition("CARD_IN_ZONE", {"zone": "hand", "color": "yellow"})
    assert fn(_card(BIG), None, st) is True


# --- buzzard_helm -----------------------------------------------------------

def _defend_state(source, fodder=SMALL):
    """The card draws BEFORE it discards at RANDOM, so the deck must be stocked
    with the same kind of card as the hand or the discard is a coin flip and the
    test is flaky rather than wrong."""
    st = _state()
    st.combat = CombatState(attacker_id=2, link_id=1, attack_power=0,
                            attack_card=None, keywords=[])
    st.combat.defending_cards = [source]
    for _ in range(4):
        st.players[1].deck.add(_card(fodder))
    return st


def test_buzzard_helm_buffs_only_on_a_big_discard():
    source = _card("buzzard_helm")
    st = _defend_state(source)                 # deck stocked with SMALL too,
    st.players[1].hand.add(_card(SMALL))       # so the random pick is 1{p}
    printed = source.defense

    _run("buzzard_helm", st, source=source)

    assert source.defense == printed, (
        f"it got +1{{d}} discarding a small card ({source.defense} vs {printed})")


def test_buzzard_helm_buffs_when_a_big_card_is_discarded():
    source = _card("buzzard_helm")
    st = _defend_state(source, fodder=BIG)
    big = _card(BIG)
    assert big.power >= 6, big.power
    st.players[1].hand.add(big)
    printed = source.defense

    _run("buzzard_helm", st, source=source)

    assert source.defense == printed + 1, (
        f"no +1{{d}} after discarding a {big.power}{{p}} card")


def test_buzzard_helm_still_draws_and_discards():
    source = _card("buzzard_helm")
    st = _defend_state(source)
    st.players[1].hand.add(_card(SMALL))
    before = len(st.players[1].hand.cards)

    _run("buzzard_helm", st, source=source)

    assert len(st.players[1].hand.cards) == before, "draw-then-discard is net zero"


# --- metex_red --------------------------------------------------------------

def test_metex_does_not_bottom_cards_from_hand():
    """It was two PUT_CARDS_BOTTOM nodes: hitting put TWO arbitrary cards from
    hand on the bottom of your deck - a punishment, not the printed effect."""
    st = _state()
    keep = [_card(BIG), _card(SMALL)]
    for c in keep:
        st.players[1].hand.add(c)
    for _ in range(4):
        st.players[1].deck.add(_card(SMALL))

    _run("metex_red", st)

    for c in keep:
        assert c in st.players[1].hand.cards, (
            f"{c.slug} was put on the bottom of the deck")


def test_metex_puts_a_cheap_item_into_the_arena():
    st = _state()
    item = _card(ITEM)
    assert "Item" in (item.subtypes or []) and (item.cost or 0) <= 1, (
        f"{ITEM} was picked as a cheap Item; it is now {item.subtypes} cost "
        f"{item.cost} and this test proves nothing")
    st.players[1].hand.add(item)
    expensive = _card(BIG)
    st.players[1].hand.add(expensive)

    _run("metex_red", st)

    assert item in st.players[1].permanents.cards, (
        "the item did not reach the arena")
    assert expensive in st.players[1].hand.cards, (
        "it took a non-item out of hand as well")


# --- break_open_the_chests_yellow -------------------------------------------

def test_break_open_turns_both_arsenals_face_up():
    st = _state()
    mine, theirs = _card(SMALL, 1), _card(SMALL, 2)
    st.players[1].arsenal.add(mine)
    st.players[2].arsenal.add(theirs)
    assert mine.is_public is False and theirs.is_public is False

    _run("break_open_the_chests_yellow", st)

    assert mine.is_public is True, "own arsenal was not turned face up"
    assert theirs.is_public is True, "\"ALL arsenals\" missed the opponent's"


def test_break_open_creates_gold_for_a_yellow_card_in_any_arsenal():
    st = _state()
    theirs = _card(YELLOW, 2)
    st.players[2].arsenal.add(theirs)

    _run("break_open_the_chests_yellow", st)

    tokens = [c.slug for c in st.players[1].permanents.cards]
    assert tokens.count("gold") == 2, (
        f"expected 2 Gold tokens for a yellow card in THEIR arsenal, got {tokens}")


def test_break_open_creates_nothing_without_a_yellow_card():
    st = _state()
    st.players[1].arsenal.add(_card(SMALL, 1))

    _run("break_open_the_chests_yellow", st)

    assert "gold" not in [c.slug for c in st.players[1].permanents.cards]


# --- swift_shot_red ---------------------------------------------------------

def test_swift_shot_fires_when_put_face_up_into_arsenal():
    """The trigger was ON_ENTER_PLAY, and an arsenal is not the arena."""
    from engine.card_effects.dsl.trigger_types import TRIGGER_TO_EVENT

    trig = get_card("swift_shot_red").abilities[0].trigger
    assert trig == "ON_PUT_FACEUP_IN_ARSENAL"
    assert trig in TRIGGER_TO_EVENT, f"{trig} is not a dispatched trigger name"


def test_swift_shot_grants_go_again_through_a_real_arsenal_entry():
    st = _state()
    shot = _card("swift_shot_red")
    st.players[1].arsenal.add(shot)
    shot.is_public = True
    # Re-add through the real path so Zone.add does the dispatch.
    st.players[1].arsenal.cards = []
    from engine.effect_keywords import put_object
    st.players[1].hand.add(shot)
    put_object(st, shot, "arsenal", destination_player_id=1,
               source_player_id=1, is_public=True)

    grants = getattr(st.players[1], "dsl_play_keyword_grants", None) or []
    assert grants, "no go-again grant was queued by the arsenal entry"
    assert any((g.get("keyword") or "").lower() == "go again" for g in grants), grants


def test_swift_shot_gate_is_about_this_card_not_a_full_arsenal():
    """CARD_IN_ZONE card:"swift_shot_red" was unread, so the gate reduced to
    "is the arsenal non-empty" - true with any other card sitting there."""
    st = _state()
    other = _card(SMALL)
    st.players[1].arsenal.add(other)
    other.is_public = True
    shot = _card("swift_shot_red")          # NOT in the arsenal

    fn = compile_condition("SELF_IN_ZONE", {"zone": "arsenal", "face_up": True})
    assert fn(shot, None, st) is False, (
        "the gate passed for a card that is not in the arsenal")
