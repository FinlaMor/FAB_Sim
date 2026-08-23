"""GAIN resolved every asset to the controller, and never expired.

Three unread parameters, three different consequences:

  good_deeds_dont_go_unnoticed  "THEY draw a card, THEY gain {r}, THEY gain
                                1{h}" - `player` was authored and unread, so a
                                card handing resources to the OPPONENT handed
                                them to itself. An inversion, not a no-op.
  great_library_of_solana       "they gain +1{i} UNTIL END OF TURN" was GAIN
                                keyword:"INTELLECT" - the KEYWORD branch, which
                                grants to the current combat's keyword list, so
                                no intellect was gained anywhere. Intellect is a
                                Player stat with no gain() asset type. Its
                                duration was unread too, so the gain would have
                                been PERMANENT: for intellect that means a
                                permanently larger draw-up every turn after.
  painful_passage_red           "IF YOU DO, it gets +3{p} OR go again" lived
                                under `additional_effects` on the BANISH node -
                                a key BANISH does not read - so both halves were
                                unreachable and the card only banished. The
                                previous authoring also applied BOTH options
                                where the card says "or".
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.effect_types import compile_effect
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

ATTACK = "brutal_assault_red"
YELLOW = "amplifying_arrow_yellow"


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


# --- GAIN player ------------------------------------------------------------

def test_the_named_player_gains_the_resource():
    st = _state()
    mine, theirs = st.players[1].resources, st.players[2].resources

    compile_effect("GAIN", {"asset": "RESOURCE_POINTS", "amount": 1,
                            "player": "OPPONENT"})(_card(ATTACK), None, st)

    assert st.players[2].resources == theirs + 1, "the opponent gained nothing"
    assert st.players[1].resources == mine, "the controller gained it instead"


def test_gain_still_defaults_to_the_controller():
    st = _state()
    mine = st.players[1].resources

    compile_effect("GAIN", {"asset": "RESOURCE_POINTS", "amount": 1})(
        _card(ATTACK), None, st)

    assert st.players[1].resources == mine + 1


def test_good_deeds_gives_the_resource_to_the_other_hero():
    st = _state()
    st.active_player = 2          # "at the start of each OTHER hero's turn"
    source = _card("good_deeds_dont_go_unnoticed_yellow", 1)
    st.players[1].permanents.add(source)
    # Pick the "they gain {r}" mode.
    st.player_agents = {p: (lambda s, o, context="": next(
        (x for x in o if "{r}" in str(x)), o[0])) for p in (1, 2)}
    mine, theirs = st.players[1].resources, st.players[2].resources

    run_ability(get_card("good_deeds_dont_go_unnoticed_yellow").abilities[0],
                source, None, st)

    assert st.players[2].resources == theirs + 1, (
        "the other hero gained nothing")
    assert st.players[1].resources == mine, (
        "the card's controller took the resource meant for them")


# --- GAIN intellect + duration ----------------------------------------------

def test_intellect_is_gained_at_all():
    st = _state()
    before = st.players[1].intellect

    compile_effect("GAIN", {"asset": "INTELLECT", "amount": 1})(
        _card(ATTACK), None, st)

    assert st.players[1].intellect == before + 1


def test_the_keyword_form_never_touched_intellect():
    """The card had GAIN keyword:"INTELLECT", which grants to the COMBAT's
    keyword list - so no intellect was gained anywhere."""
    st = _state()
    before = st.players[1].intellect

    compile_effect("GAIN", {"keyword": "INTELLECT", "amount": 1})(
        _card(ATTACK), None, st)

    assert st.players[1].intellect == before


def test_an_end_of_turn_intellect_gain_is_taken_back():
    st = _state()
    before = st.players[1].intellect

    compile_effect("GAIN", {"asset": "INTELLECT", "amount": 1,
                            "duration": "END_OF_TURN"})(_card(ATTACK), None, st)
    assert st.players[1].intellect == before + 1

    # The ENGINE's end phase, not a reimplementation of the restore: pasting a
    # copy of the cleanup here would pass whatever the engine does.
    E._end_phase_iter(st)

    assert st.players[1].intellect == before, (
        "the intellect gain outlived the turn; for intellect that means a "
        "permanently larger draw-up every turn after")


def test_a_gain_with_no_duration_is_not_queued_for_restore():
    st = _state()
    compile_effect("GAIN", {"asset": "INTELLECT", "amount": 1})(
        _card(ATTACK), None, st)

    assert not (getattr(st.players[1], "dsl_pending_stat_restores", None) or []), (
        "a permanent gain was queued to be taken back")


def test_great_library_grants_intellect_on_two_yellow_pitched():
    st = _state()
    source = _card("great_library_of_solana", 1)
    st.players[1].permanents.add(source)
    before = st.players[1].intellect

    run_ability(get_card("great_library_of_solana").abilities[0], source, None, st)
    assert st.players[1].intellect == before, "it fired with no yellow cards pitched"

    for _ in range(2):
        st.players[1].pitch.add(_card(YELLOW, 1))
    run_ability(get_card("great_library_of_solana").abilities[0], source, None, st)

    assert st.players[1].intellect == before + 1


# --- painful_passage_red ----------------------------------------------------

def test_painful_passage_banishes_only_an_attack_action():
    st = _state()
    attack = _card(ATTACK)
    instant = _card("shining_courage_red")
    st.players[1].hand.add(attack)
    st.players[1].hand.add(instant)

    run_ability(get_card("painful_passage_red").abilities[0],
                _card("painful_passage_red"), None, st)

    assert attack not in st.players[1].hand.cards, "the attack was not banished"
    assert instant in st.players[1].hand.cards, "it banished a non-attack card"


def test_painful_passage_pays_off_after_banishing():
    st = _state()
    st.players[1].hand.add(_card(ATTACK))

    run_ability(get_card("painful_passage_red").abilities[0],
                _card("painful_passage_red"), None, st)

    queued = list(getattr(st.players[1], "dsl_queued_attack_mods", None) or [])
    grants = list(getattr(st.players[1], "dsl_play_keyword_grants", None) or [])
    assert queued or grants, (
        "neither half of \"it gets +3{p} or go again\" reached the game state")


def test_painful_passage_pays_off_with_nothing_to_banish():
    """"IF YOU DO" - an empty hand must not pay out."""
    st = _state()
    st.players[1].hand.cards = []

    run_ability(get_card("painful_passage_red").abilities[0],
                _card("painful_passage_red"), None, st)

    queued = list(getattr(st.players[1], "dsl_queued_attack_mods", None) or [])
    grants = list(getattr(st.players[1], "dsl_play_keyword_grants", None) or [])
    assert not queued and not grants, (
        "it paid out without banishing anything")


def test_painful_passage_grants_one_option_not_both():
    """"+3{p} OR go again" - the previous authoring applied both."""
    st = _state()
    st.players[1].hand.add(_card(ATTACK))

    run_ability(get_card("painful_passage_red").abilities[0],
                _card("painful_passage_red"), None, st)

    queued = list(getattr(st.players[1], "dsl_queued_attack_mods", None) or [])
    grants = list(getattr(st.players[1], "dsl_play_keyword_grants", None) or [])
    assert not (queued and grants), (
        f"both options applied: {queued} and {grants}")
