""""At the start of each OTHER hero's turn" never received the event.

`_dsl_start_of_turn_listener` dispatches START_OF_TURN to the TURN PLAYER's
permanents only. Three cards are keyed to the opponent's turn and all wrote it
as START_OF_TURN plus a negated IS_ACTIVE_PLAYER condition — so the event never
arrived and the condition was never even evaluated. One of them, `toughness`, is
a generic Aura token that many cards create, so it was dead wherever it appeared.

The fix is a NEW trigger, START_OF_ANY_TURN, dispatched to both players'
permanents — deliberately not a broadening of START_OF_TURN, because 23
abilities use that one with no active-player condition at all, meaning "your
turn", and they would begin firing twice a round.

good_deeds_dont_go_unnoticed_yellow needed more than the trigger. It had NINE
abilities: four payoff clauses duplicated as four more, each gated on FLAG_SET
of a flag its own effects SET, and no implementation of the half that gives the
opponent something — which is what should have set those flags. Flags could not
have carried it in any case: current_turn_effects is emptied every turn, and
this card records what happened on the OPPONENT'S turn to pay out on YOURS. The
record has to survive the turn boundary, so it lives on the card as counters.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.loader import load_all_cards, get_card
from tests.conftest import _make_state
from tests.conftest import _card_json, card_json_files

load_all_cards()
DB = CardDB()


def _state(active=1):
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    st.active_player = active
    for pid in (1, 2):
        st.players[pid].deck.cards = [_card("wounded_bull_red", owner=pid)
                                      for _ in range(5)]
    return st


def _card(slug, owner=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = owner
    return c


def _dispatch_start_of_turn(st):
    """Fire the real listener, not the DSL trigger directly."""
    st.event_manager.emit('start_of_turn', st)


def test_start_of_any_turn_reaches_the_non_active_players_permanents():
    """The gap itself: START_OF_TURN only reaches the turn player's."""
    from engine.card_effects.dsl.trigger_types import TRIGGER_TO_EVENT

    assert TRIGGER_TO_EVENT.get("START_OF_ANY_TURN") == "START_OF_ANY_TURN"

    st = _state(active=2)          # it is the OPPONENT's turn
    tok = _card("toughness", owner=1)
    st.players[1].permanents.cards.append(tok)

    _dispatch_start_of_turn(st)

    assert tok not in st.players[1].permanents.cards, (
        "toughness did not fire on the opponent's turn, so it never fires at all")


def test_it_does_not_fire_on_its_controllers_own_turn():
    """The condition still has to narrow it — the trigger only delivers."""
    st = _state(active=1)          # the CONTROLLER's turn
    tok = _card("toughness", owner=1)
    st.players[1].permanents.cards.append(tok)

    _dispatch_start_of_turn(st)

    assert tok in st.players[1].permanents.cards, (
        "it fired on its controller's own turn")


def test_start_of_turn_still_only_reaches_the_turn_player():
    """The 23 abilities meaning "your turn" must not start firing twice a round."""
    st = _state(active=2)
    fired = []
    import engine.card_effects.dsl as dsl
    real = dsl.dispatch

    def _spy(state, event_type, slug, **kw):
        if event_type == "START_OF_TURN":
            fired.append(slug)
        return real(state, event_type, slug, **kw)

    dsl.dispatch = _spy
    E._setup_dsl_listeners(st)
    try:
        mine = _card("teklo_core_blue", owner=1)
        st.players[1].permanents.cards.append(mine)
        _dispatch_start_of_turn(st)
    finally:
        dsl.dispatch = real

    assert mine.slug not in fired, (
        "START_OF_TURN reached a NON-turn-player's permanent")


def test_good_deeds_records_the_gift_on_the_card_not_in_turn_state():
    """The record must survive the turn boundary to pay out on your turn."""
    st = _state(active=2)          # opponent's turn: the giving half
    aura = _card("good_deeds_dont_go_unnoticed_yellow", owner=1)
    st.players[1].permanents.cards.append(aura)

    _dispatch_start_of_turn(st)

    counters = {k: v for k, v in (aura.counters or {}).items() if v}
    assert counters, "the gift was not recorded on the card"
    assert set(counters) <= {"draw", "resource", "life", "power"}, counters


def test_good_deeds_pays_out_only_what_it_gave():
    st = _state(active=1)
    aura = _card("good_deeds_dont_go_unnoticed_yellow", owner=1)
    aura.counters["life"] = 1      # it gave life, and nothing else
    st.players[1].permanents.cards.append(aura)
    life_before = st.players[1].life
    hand_before = len(st.players[1].hand.cards)

    _dispatch_start_of_turn(st)

    assert st.players[1].life > life_before, "it did not pay back the life"
    assert len(st.players[1].hand.cards) == hand_before, (
        "it drew a card it never gave")
    assert aura not in st.players[1].permanents.cards, "it did not destroy itself"


def test_good_deeds_has_no_duplicated_abilities():
    """It carried four payoff clauses twice, so the payout would have doubled."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    raw = json.loads(_card_json(root, "good_deeds_dont_go_unnoticed_yellow.json")
                     .read_text(encoding="utf-8"))
    seen = [json.dumps(a, sort_keys=True) for a in raw.get("abilities") or []]
    assert len(seen) == len(set(seen)), "duplicate abilities are back"


def test_no_ability_is_gated_on_a_flag_it_sets():
    """The shape found on perch_grapplers and on all eight of good_deeds'
    payoff clauses: an ability that can only run after it has already run."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    offenders = []
    for path in card_json_files(root):
        if path.stem.endswith("_work_queue") or any(
                p.startswith(".") for p in path.parts):
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        for i, ability in enumerate(raw.get("abilities") or []):
            sets = {e.get("flag") for e in ability.get("effects") or []
                    if isinstance(e, dict) and e.get("type") == "SET_FLAG" and e.get("flag")}
            reads = {c.get("flag") for c in ability.get("conditions") or []
                     if isinstance(c, dict) and c.get("type") == "FLAG_SET" and c.get("flag")}
            if sets & reads:
                offenders.append(f"{path.stem}[{i}] {sorted(sets & reads)}")
    assert not offenders, (
        f"ability gated on a flag it sets, so it can never run: {offenders}")
