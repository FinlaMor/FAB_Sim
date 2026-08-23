"""Freeze was unwired end to end.

effect_keywords.freeze() wrote card.counters['__frozen__'] and cleared it again
at the right time, but NOTHING read it, there was no DSL FREEZE effect at all,
and no implemented card froze anything. CR 8.5.34: "To freeze an object, that
object CANNOT BE PLAYED and its abilities CANNOT BE ACTIVATED for the duration
of the effect." play._legality_check is the one gate both playing and
activating pass through, so that is where it is enforced.

channel_iceloch_glaze_blue needs a second, different thing: "cards in opponents'
arsenals are frozen WHILE they control a Frostbite or a frozen permanent" is
true or false from moment to moment. A one-shot freeze would lock the arsenal
once and never release it, so FREEZE_WHILE is a declarative static that
_apply_conditional_freezes clears and re-derives on every legality pass - under
a SEPARATE marker from the discrete freeze counter, because that counter is
paired with duration bookkeeping and a continuous effect re-applying it would
accumulate without bound.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.condition_types import compile_condition
from engine.card_effects.dsl.effect_types import compile_effect
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.effect_keywords import freeze as _freeze
from engine.play import CONTINUOUS_FREEZE, _legality_check, recalculate_playable
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

# An INSTANT: in a bare test state an Action is illegal for unrelated reasons
# (no action point), so it cannot serve as the control case for a freeze gate.
PLAYABLE = "shining_courage_red"
SOURCE = "channel_iceloch_glaze_blue"


def _card(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    st.individual_turns = 1
    return st


# --- CR 8.5.34 enforcement --------------------------------------------------

def test_a_frozen_card_cannot_be_played():
    st = _state()
    card = _card(PLAYABLE)
    st.players[1].hand.add(card)
    assert _legality_check(st, card, 1) is True, "the control case is not playable"

    _freeze(st, card, source_player_id=2)

    assert _legality_check(st, card, 1) is False, (
        "a frozen card was still legal to play (CR 8.5.34)")


def test_unfreezing_makes_it_playable_again():
    from engine.effect_keywords import unfreeze as _unfreeze

    st = _state()
    card = _card(PLAYABLE)
    st.players[1].hand.add(card)
    _freeze(st, card, source_player_id=2)

    _unfreeze(st, card)

    assert _legality_check(st, card, 1) is True


def test_the_dsl_can_freeze_at_all():
    """There was no FREEZE effect, so none of the ~30 corpus cards that freeze
    could be written."""
    st = _state()
    theirs = _card(PLAYABLE, 2)
    st.players[2].arsenal.add(theirs)
    source = _card(SOURCE, 1)

    compile_effect("FREEZE", {"target": {"controller": "OPPONENT",
                                         "zone": "ARSENAL", "amount": "ALL"}})(
        source, None, st)

    assert theirs.counters.get("__frozen__", 0) > 0
    assert _legality_check(st, theirs, 2) is False


# --- FREEZE_WHILE -----------------------------------------------------------

def _iceloch(st, pid=1):
    src = _card(SOURCE, pid)
    st.players[pid].permanents.add(src)
    return src


def _frostbite(st, pid):
    """Build the token by hand: `frostbite` has no DSL definition, so
    create_token raises MissingCardImplementation for it."""
    from engine.card import Card
    tok = Card(slug="frostbite", raw_name="Frostbite", raw_types=["Token"],
               raw_subtypes=["Aura"])
    tok.name = "Frostbite"
    tok.types = ["Token"]
    tok.subtypes = ["Aura"]
    tok.is_token = True
    tok.owner = tok.controller = pid
    st.players[pid].permanents.cards.append(tok)
    tok.zone = "permanents"
    return tok


# NOTE ON DIRECTION: the source sits on player 2 and the frozen arsenal is
# player 1's. In a bare test state only player 1's cards pass the unrelated
# legality gates, so putting it the other way round makes the CONTROL case
# false and the freeze untestable.

def test_their_arsenal_freezes_only_while_the_condition_holds():
    st = _state()
    _iceloch(st, 2)
    mine = _card(PLAYABLE, 1)
    st.players[1].arsenal.add(mine)

    recalculate_playable(st, 1)
    assert _legality_check(st, mine, 1) is True, (
        "the arsenal froze with no Frostbite and no frozen permanent")

    _frostbite(st, 1)
    recalculate_playable(st, 1)

    assert _legality_check(st, mine, 1) is False, (
        "the arsenal did not freeze while its controller has a Frostbite")


def test_it_releases_when_the_condition_stops_holding():
    """The whole point of WHILE: a one-shot freeze could never let go."""
    st = _state()
    _iceloch(st, 2)
    mine = _card(PLAYABLE, 1)
    st.players[1].arsenal.add(mine)
    _frostbite(st, 1)
    recalculate_playable(st, 1)
    assert _legality_check(st, mine, 1) is False

    st.players[1].permanents.cards = [
        c for c in st.players[1].permanents.cards if c.slug != "frostbite"]
    recalculate_playable(st, 1)

    assert _legality_check(st, mine, 1) is True, (
        "the freeze outlived the condition that caused it")


def test_it_reads_THEIR_board_not_the_controllers():
    """"while THEY control a Frostbite" - the gate had asked about the source's
    own controller."""
    st = _state()
    _iceloch(st, 2)
    mine = _card(PLAYABLE, 1)
    st.players[1].arsenal.add(mine)
    _frostbite(st, 2)          # the SOURCE's own Frostbite, not the victim's

    recalculate_playable(st, 1)

    assert _legality_check(st, mine, 1) is True, (
        "a Frostbite on the source's own side froze the opponent's arsenal")


def test_the_sources_own_arsenal_is_untouched():
    st = _state()
    _iceloch(st, 2)
    theirs = _card(PLAYABLE, 2)
    st.players[2].arsenal.add(theirs)
    _frostbite(st, 2)

    recalculate_playable(st, 2)

    assert theirs.counters.get(CONTINUOUS_FREEZE, 0) == 0, (
        "it froze the source controller's own arsenal")


def test_the_continuous_marker_does_not_accumulate():
    st = _state()
    _iceloch(st, 2)
    mine = _card(PLAYABLE, 1)
    st.players[1].arsenal.add(mine)
    _frostbite(st, 1)

    for _ in range(5):
        recalculate_playable(st, 1)

    assert mine.counters.get(CONTINUOUS_FREEZE, 0) == 1, (
        f"five passes left {mine.counters.get(CONTINUOUS_FREEZE)} on the card; "
        f"a continuous effect must be re-derived, not stacked")
    assert mine.counters.get("__frozen__", 0) == 0, (
        "the continuous freeze wrote the DISCRETE counter, whose duration "
        "bookkeeping would then never release it")


def test_controls_frozen_permanent_reads_the_object():
    st = _state()
    source = _card(SOURCE, 1)
    perm = _frostbite(st, 2)
    fn = compile_condition("CONTROLS_FROZEN_PERMANENT", {"player": "OPPONENT"})

    assert fn(source, None, st) is False

    _freeze(st, perm, source_player_id=1)
    assert fn(source, None, st) is True
