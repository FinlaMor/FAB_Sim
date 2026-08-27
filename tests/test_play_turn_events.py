"""Cards gated on "if you've played a <X> card this turn".

Every card here was DEAD before playing a card recorded a turn event: each read a
private FLAG_SET (`BLUE_CARD_PLAYED_THIS_TURN`, `NON_ATTACK_ACTION_PLAYED_THIS_TURN`,
...) that nothing in the engine ever wrote, so the ability could never fire. These
tests assert the observable outcome, and the negative cases matter as much as the
positive ones — a condition that is always true would pass the positive test just
as well as a correct one.
"""
import copy

import pytest

from engine.actions import Action, ActionType
from engine.card import CardDB
from engine.card_effects.dsl.loader import load_all_cards
from engine.engine import resolve_stack
from engine.play import apply_action
from tests.conftest import _card_json, _make_state

load_all_cards()
DB = CardDB()


def _state():
    st = _make_state()
    st.card_db = DB
    return st


def _play(st, slug, pid=1):
    """Play `slug` from hand through the real action path.

    The stack is resolved afterwards: a card left unresolved on the stack makes
    the NEXT play fail its legality check, which silently records nothing and
    would make an accumulation test pass for the wrong reason.
    """
    card = copy.deepcopy(DB.get(slug))
    assert card is not None, f"unknown slug {slug}"
    card.owner = card.controller = pid
    st.players[pid].hand.add(card)
    st.players[pid].resources = 20
    st.players[pid].action_points = max(1, st.players[pid].action_points)
    apply_action(st, Action(type=ActionType.PLAY_CARD, player_id=pid, card=card))
    resolve_stack(st)
    return card


def _play_markers(st, pid=1):
    return [m for m in st.players[pid].current_turn_effects
            if m.startswith("did_this_turn:play")]


# --- the recording itself -------------------------------------------------

def test_attack_action_records_attack_action_not_non_attack():
    # "Attack" is a SUBTYPE, not a type: an attack action is types=['Action'],
    # subtypes=['Attack']. Deriving the split from `types` alone (as a first cut
    # did) labels every attack action a NON-attack action, inverting every card
    # gated on either.
    st = _state()
    _play(st, "wounding_blow_red")
    markers = _play_markers(st)
    assert "did_this_turn:play:attackaction" in markers
    assert "did_this_turn:play:nonattackaction" not in markers


def test_play_records_colour_type_and_class():
    st = _state()
    _play(st, "wounding_blow_red")
    markers = _play_markers(st)
    assert "did_this_turn:play" in markers          # the bare event
    assert "did_this_turn:play:red" in markers      # colour, from pitch value
    assert "did_this_turn:play:action" in markers   # type
    assert "did_this_turn:play:woundingblowred" in markers  # slug


def test_each_play_appends_so_counts_are_observable():
    # "another blue card" is a COUNT check (>=2), which only works if markers
    # accumulate rather than dedupe across plays. Two NON-attack actions are used
    # deliberately: playing an attack action opens a combat chain and the second
    # play is then illegal, which would make this pass for the wrong reason.
    st = _state()
    before = _play_markers(st).count("did_this_turn:play")
    _play(st, "aether_dart_blue")
    _play(st, "aether_arc_blue")
    markers = _play_markers(st)
    assert markers.count("did_this_turn:play") == before + 2
    assert markers.count("did_this_turn:play:blue") == 2


# --- cards that were dead and now fire ------------------------------------

def test_vigor_rush_blue_go_again_only_after_a_non_attack_action():
    # "If you have played a 'non-attack' action card this turn, Vigor Rush gains
    # go again." Vigor Rush is itself an ATTACK action, so its own play must not
    # satisfy its own condition.
    from engine.card_effects.dsl import get_card
    card = get_card("vigor_rush_blue")
    assert card is not None and card.abilities, "vigor_rush_blue has no abilities"
    cond = card.abilities[0].conditions
    assert cond, "condition was dropped in migration"

    st = _state()
    played = _play(st, "vigor_rush_blue")
    markers = _play_markers(st)
    # Its own play records an ATTACK action; the gate wants a NON-attack action.
    assert "did_this_turn:play:attackaction" in markers
    assert "did_this_turn:play:nonattackaction" not in markers


def test_non_attack_action_play_is_recorded_for_the_gate():
    # The other half of the same gate: a non-attack action must actually record
    # the marker those cards read, or they stay as dead as they were with the
    # invented flag.
    st = _state()
    card = DB.get("aether_dart_blue")
    assert card.is_action and not card.is_attack, "fixture is no longer a non-attack action"
    _play(st, "aether_dart_blue")
    markers = _play_markers(st)
    assert "did_this_turn:play:nonattackaction" in markers
    assert "did_this_turn:play:attackaction" not in markers


@pytest.mark.parametrize("slug", [
    "aether_ironweave",
    "vigor_rush_blue",
    "a_drop_in_the_ocean_blue",
    "droplet_blue",
    "inflame_red",
    "quick_clicks",
    "dread_triptych_blue",
])
def test_migrated_cards_keep_a_real_condition(slug):
    # Guard against a migration that "fixes" a card by deleting its gate: each
    # of these must still be conditional, and must no longer reference a flag.
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "engine" / "card_effects" / "json"
    path = _card_json(root, f"{slug}.json")
    raw = path.read_text(encoding="utf-8")
    assert "PLAYED_THIS_TURN" not in raw, f"{slug} still reads an invented flag"
    assert "EVENT_THIS_TURN" in raw, f"{slug} lost its condition entirely"
    json.loads(raw)  # still valid JSON
