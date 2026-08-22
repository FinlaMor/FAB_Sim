""""From anywhere other than your graveyard" tested where the card IS.

graven_gloves has two clauses and both were wrong in a way the other cards in
this sweep have made familiar.

The graveyard clause was a plain STATIC, which nothing dispatches — even though
the effect it needed (MAY_DESTROY_SILVERS_TO_EQUIP) and the trigger it needed
(START_OF_TURN_IN_GRAVEYARD, dispatched to the ACTIVE player's graveyard) both
already existed. Nothing had to be built; the ability was simply the wrong type.

The equip clause tested NOT(IN_GRAVEYARD). By the time ON_EQUIP fires the card
has already left the graveyard, so that is TRUE even when it was equipped FROM
there — the one case the card excludes. "From anywhere other than your
graveyard" is about where it CAME FROM, which is PLAYED_FROM_ZONE; that now
falls back to prev_zone, because equipping is not playing and never stamps
played_from_zone.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import load_all_cards, get_card
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()


def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    return st


def _card(slug, owner=1, zone=None, prev=None):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = owner
    if zone is not None:
        c.zone = zone
    if prev is not None:
        c.prev_zone = prev
    return c


def _counters(card, kind):
    return (getattr(card, "counters", None) or {}).get(kind, 0)


def test_equipped_from_the_graveyard_takes_no_counter():
    """The case the card excludes, and the case NOT(IN_GRAVEYARD) got wrong."""
    st = _state()
    gloves = _card("graven_gloves", zone="arms", prev="graveyard")

    run_ability(get_card("graven_gloves").abilities[1], gloves, None, st)

    assert _counters(gloves, "-1d") == 0, (
        "it took a -1{d} counter when equipped FROM the graveyard")


def test_equipped_from_anywhere_else_takes_a_counter():
    st = _state()
    gloves = _card("graven_gloves", zone="arms", prev="inventory")

    run_ability(get_card("graven_gloves").abilities[1], gloves, None, st)

    assert _counters(gloves, "-1d") == 1, (
        "equipping from inventory did not put a -1{d} counter on it")


def test_the_counter_goes_on_the_gloves():
    """PUT_COUNTER acts on the source unless told otherwise; this one means the
    source, and says so rather than relying on the default."""
    st = _state()
    gloves = _card("graven_gloves", zone="arms", prev="inventory")
    other = _card("nullrune_robe")
    st.players[1].chest.cards = [other]

    run_ability(get_card("graven_gloves").abilities[1], gloves, None, st)

    assert _counters(other, "-1d") == 0


def test_the_graveyard_clause_uses_a_trigger_that_is_dispatched():
    """It was a plain STATIC while the right trigger already existed."""
    import json
    from pathlib import Path
    from engine.card_effects.dsl.trigger_types import TRIGGER_TO_EVENT

    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    raw = json.loads(next(root.rglob("graven_gloves.json")).read_text(encoding="utf-8"))
    types = [(a.get("ability_type") or "").upper() for a in raw["abilities"]]
    assert "STATIC" not in types, types

    trig = raw["abilities"][0].get("trigger")
    assert trig == "START_OF_TURN_IN_GRAVEYARD"
    assert trig in TRIGGER_TO_EVENT, f"{trig} is not a dispatched trigger name"


def test_played_from_zone_falls_back_to_prev_zone():
    """Equipping is not playing, so played_from_zone is never stamped for it."""
    from engine.card_effects.dsl.condition_types import compile_condition

    st = _state()
    fn = compile_condition("PLAYED_FROM_ZONE", {"zone": "graveyard"})

    from_gy = _card("graven_gloves", zone="arms", prev="graveyard")
    from_inv = _card("graven_gloves", zone="arms", prev="inventory")

    assert fn(from_gy, None, st) is True
    assert fn(from_inv, None, st) is False


def test_the_play_time_stamp_still_wins_when_present():
    """The fallback must not displace the explicit stamp play.py sets."""
    from engine.card_effects.dsl.condition_types import compile_condition

    st = _state()
    fn = compile_condition("PLAYED_FROM_ZONE", {"zone": "banished"})
    card = _card("graven_gloves", zone="arena", prev="hand")
    card.played_from_zone = "banished"

    assert fn(card, None, st) is True
