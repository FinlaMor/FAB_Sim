""""IF <something>, you may play this from your banished zone" — the IF was free.

play._self_playable_from_banished read the STATIC's declared EFFECT TYPES and
never looked at the ability's conditions, so a card of this shape could be
played out of the banished zone in every state. That is not a smaller version
of the card; it is a free one, and it is silent — the play is simply offered.

13 cards write the permission that way:

    bounding_demigon x3    "if you have played a non-attack action card this turn"
    deep_rooted_evil       "if a card with 6 or more {p} has been put into your
                            banished zone this turn"
    hungering_demigon x2   "if an opposing hero has 1 or more cards in their soul"
    ghost_protocol x2      "if this was banished from boosting this turn"
    ...

None had been implemented yet, so this is preventive rather than a live fix —
but it is exactly the shape that would have shipped unnoticed, since the card
works, the permission appears, and only the gate is missing.

A CONDITION THAT RAISES COUNTS AS NOT HOLDING. The alternative — swallowing the
error into a True — hands out the free play this exists to prevent, which is
the failure it is guarding against.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.play import _self_playable_from_banished, available_actions
from engine.state import Step
from tests.conftest import _make_state, attack_with, recalculate_attack

load_all_cards()
DB = CardDB()

CARD = "bounding_demigon_blue"


def _card(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _state():
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="", **kw: o[0]      # noqa: E731
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    st.step = Step.ACTION
    st.players[1].resources = 9
    st.players[1].action_points = 1
    return st


@pytest.fixture(scope="module")
def non_attack_action():
    """A real non-attack action card, so the turn marker is a real one."""
    import io, json
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    idx = json.load(io.open(root / "card_data" / "slug_index.json",
                            encoding="utf-8"))["by_slug"]
    return next(s for s, e in idx.items()
                if "Action" in (e.get("types") or [])
                and "NonAttack" in (e.get("subtypes") or []) and DB.get(s))


def _played_a_non_attack(st, slug):
    """Record the play the way play.py does, through the canonical marker."""
    from engine.effect_keywords import _record_turn_event
    card = DB.get(slug)
    _record_turn_event(st, 1, "play", card.slug, card.name,
                       card.types or [], card.subtypes or [],
                       card.classes or [], card.talents or [], "blue")


def test_the_probe_is_a_non_attack_action(non_attack_action):
    """Guards the positive test: a probe that was secretly an attack would
    record the wrong marker and the permission would stay closed."""
    card = DB.get(non_attack_action)
    assert "Action" in (card.types or [])
    assert "NonAttack" in (card.subtypes or [])


def test_the_permission_is_closed_on_a_quiet_turn():
    """THE ONE THAT WAS BROKEN. Nothing has been played, so the card must not
    be playable out of the banished zone."""
    st = _state()
    banished = _card(CARD)
    st.players[1].banished.add(banished)
    assert not _self_playable_from_banished(banished, st, st.players[1])


def test_the_permission_opens_after_a_non_attack_action(non_attack_action):
    st = _state()
    _played_a_non_attack(st, non_attack_action)
    banished = _card(CARD)
    st.players[1].banished.add(banished)
    assert _self_playable_from_banished(banished, st, st.players[1])


def test_the_game_actually_offers_the_play(non_attack_action):
    """The observable that matters: `available_actions` is what a player sees.
    A permission that is true in the helper and never reaches the action list
    is still an unplayable card."""
    st = _state()
    _played_a_non_attack(st, non_attack_action)
    st.players[1].banished.add(_card(CARD))
    offered = {getattr(a.card, "slug", None) for a in available_actions(st, 1)}
    assert CARD in offered


def test_the_game_does_not_offer_it_on_a_quiet_turn():
    st = _state()
    st.players[1].banished.add(_card(CARD))
    offered = {getattr(a.card, "slug", None) for a in available_actions(st, 1)}
    assert CARD not in offered


def test_an_unconditional_permission_is_unaffected():
    """Grim Feast declares the same STATIC with no conditions, and must keep
    working -- an over-tight fix here would take the permission away from every
    card that legitimately has it."""
    st = _state()
    card = _card("grim_feast_red")
    st.players[1].banished.add(card)
    assert _self_playable_from_banished(card, st, st.players[1])


# ------------------------------------------------------------- "if you do"

def test_the_bonus_belongs_to_the_copy_played_from_banish():
    st = _state()
    attacker = _card(CARD)
    attacker.played_from_zone = "banished"
    attack_with(st, attacker)
    assert recalculate_attack(st) == (attacker.base_power or 0) + 1


def test_a_copy_played_from_hand_gets_no_bonus():
    """"IF YOU DO" means the banished play, and this card can also be played
    normally. A flag set by the permission rather than by the play would give
    the bonus to both."""
    st = _state()
    attacker = _card(CARD)
    attacker.played_from_zone = "hand"
    attack_with(st, attacker)
    assert recalculate_attack(st) == (attacker.base_power or 0)
