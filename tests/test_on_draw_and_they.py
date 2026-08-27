""""They" had no spelling, so it could only be written as SELF or OPPONENT.

escalate_bloodshed_red says "whenever a hero draws a card during an action
phase, THEY lose 1{h}" and "at the beginning of each hero's action phase, THEY
draw a card". Both refer to a player who is neither the controller nor
necessarily their opponent — whoever drew, and whoever's phase it is.

DRAW and LOSE_LIFE resolved only SELF/OPPONENT relative to the CONTROLLER, so
"they" could only be authored as one of those and would be right half the time
by accident. `_effect_player_id` adds ACTIVE (whose turn it is) and EVENT_PLAYER
(who the event is about, read off the event payload).

ON_DRAW was also not a trigger name at all — dispatch fell back to the raw
string and matched nothing — so the first clause never fired. It is dispatched
to BOTH players' permanents, because the card says "a hero", not "you".
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.effect_types import _effect_player_id, compile_effect
from engine.card_effects.dsl.loader import load_all_cards
from tests.conftest import _make_state
from tests.conftest import _card_json

load_all_cards()
DB = CardDB()


def _state(active=1):
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    st.active_player = active
    # DURING_TURN gates a turn-restricted trigger out of the start-of-game
    # procedure (CR 4.1.8b) by checking individual_turns, which is 0 all through
    # setup. The base test state never leaves setup, so without this the card is
    # correctly silent and the test would read that as "the trigger is broken".
    st.individual_turns = 1
    for pid in (1, 2):
        st.players[pid].deck.cards = [_card("wounded_bull_red", owner=pid)
                                      for _ in range(6)]
    return st


def _card(slug, owner=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = owner
    return c


class _Ev:
    def __init__(self, **data):
        self.data = data


def test_active_resolves_to_whose_turn_it_is():
    st = _state(active=2)
    card = _card("escalate_bloodshed_red", owner=1)
    assert _effect_player_id(st, card, "ACTIVE") == 2
    assert _effect_player_id(st, card, "SELF") == 1
    assert _effect_player_id(st, card, "OPPONENT") == 2


def test_event_player_reads_the_event_not_the_controller():
    st = _state(active=1)
    card = _card("escalate_bloodshed_red", owner=1)
    assert _effect_player_id(st, card, "EVENT_PLAYER", _Ev(draw_player=2)) == 2
    assert _effect_player_id(st, card, "EVENT_PLAYER", _Ev(draw_player=1)) == 1


def test_the_opponent_loses_life_when_the_opponent_draws():
    """"whenever A HERO draws ... THEY lose 1{h}" — not always the controller."""
    st = _state(active=1)
    card = _card("escalate_bloodshed_red", owner=1)
    mine, theirs = st.players[1].life, st.players[2].life

    compile_effect("LOSE_LIFE", {"amount": 1, "player": "EVENT_PLAYER"})(
        card, _Ev(draw_player=2), st)

    assert st.players[2].life == theirs - 1, "the drawing player did not lose life"
    assert st.players[1].life == mine, "the card's controller lost it instead"


def test_the_active_player_draws_at_their_own_action_phase():
    st = _state(active=2)
    card = _card("escalate_bloodshed_red", owner=1)
    mine, theirs = len(st.players[1].hand.cards), len(st.players[2].hand.cards)

    compile_effect("DRAW", {"amount": 1, "player": "ACTIVE"})(card, None, st)

    assert len(st.players[2].hand.cards) == theirs + 1
    assert len(st.players[1].hand.cards) == mine, "the controller drew instead"


def test_on_draw_reaches_both_players_permanents():
    """The card says "a hero", so a permanent on either side can care."""
    from engine.effect_keywords import draw as _draw

    st = _state(active=1)
    card = _card("escalate_bloodshed_red", owner=1)
    st.players[1].permanents.cards.append(card)
    theirs = st.players[2].life

    _draw(st, 2, number=1)          # the OPPONENT draws

    assert st.players[2].life == theirs - 1, (
        "the opponent drew and lost no life; ON_DRAW did not reach the permanent")


def test_on_draw_is_a_real_trigger_name():
    from engine.card_effects.dsl.trigger_types import TRIGGER_TO_EVENT
    assert TRIGGER_TO_EVENT.get("ON_DRAW") == "ON_DRAW"


def test_escalate_no_longer_destroys_itself_unconditionally():
    """Its end-phase clause was START_OF_TURN gated on DURING_TURN(END_PHASE) —
    false at the start of a turn — around an unconditional self-destroy."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    raw = json.loads(_card_json(root, "escalate_bloodshed_red.json")
                     .read_text(encoding="utf-8"))
    blob = json.dumps(raw.get("abilities", []))
    assert "DESTROY_PERMANENT" not in blob, (
        "the unconditional self-destroy is back")
