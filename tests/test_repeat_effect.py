"""REPEAT / STOP_REPEAT — "... then repeat this process."

Until this existed the only loop in the DSL was CLASH's own `repeat` count, so a
repeating clause had to be authored as N unrolled copies. That silently truncates
the card in exactly the games where the loop mattered, and reads as deliberate;
dropping the clause instead makes the card weaker than printed. rotten_remains
("banish a card with 1{p} from each hero's graveyard. If you do, this gets +1{p},
then repeat this process") is the case that forced it.

Assertions are on observable GameState — attack power, zone contents — not on
the loop's internals.

The BOUND is the load-bearing test. A game engine that runs self-play cannot
have an effect that might not terminate, so `max` is enforced even when a
`while` condition never goes false.
"""
import copy

import pytest

from engine.card import CardDB
from engine.card_effects.dsl.effect_types import compile_effect
from engine.card_effects.dsl.loader import load_all_cards
from engine.context import push_refs, pop_refs
from engine.state import CombatState, Step
from tests.conftest import _make_state
import engine.engine as E

load_all_cards()
DB = CardDB()


@pytest.fixture
def board():
    st = _make_state()
    st.card_db = DB
    st.step = Step.ACTION
    st.active_player = 1
    E._setup_dsl_listeners(st)
    push_refs()
    yield st
    pop_refs()


def _attacker(st, slug="head_jab_red", power=3):
    card = copy.deepcopy(DB.get(slug))
    card.owner = card.controller = 1
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=power,
                            attack_card=card, keywords=[])
    st.combat.base_attack_power = power
    return card


def _run(spec, card, st):
    compile_effect(spec["type"], spec)(card, None, st)


PUMP = {"type": "MODIFY_ATTACK", "mod": "add", "amount": 1}


def test_times_runs_the_body_exactly_that_many_times(board):
    card = _attacker(board)
    start = board.combat.attack_power
    _run({"type": "REPEAT", "times": 3, "effects": [PUMP]}, card, board)
    assert board.combat.attack_power == start + 3


def test_times_zero_runs_nothing(board):
    card = _attacker(board)
    start = board.combat.attack_power
    _run({"type": "REPEAT", "times": 0, "effects": [PUMP]}, card, board)
    assert board.combat.attack_power == start


def test_while_stops_when_the_condition_goes_false(board):
    """The loop must re-check `while` each pass, not once. Two cards in the
    graveyard means two iterations, because the body consumes one per pass."""
    card = _attacker(board)
    for slug in ("head_jab_red", "surging_strike_red"):
        c = copy.deepcopy(DB.get(slug))
        c.owner = c.controller = 1
        board.players[1].graveyard.add(c)
    start = board.combat.attack_power

    # BANISH from the graveyard drains the zone the `while` reads, so the
    # condition goes false on its own rather than by a counter we maintain.
    _run({"type": "REPEAT",
          "while": [{"type": "CARD_IN_ZONE", "zone": "graveyard",
                     "player": "SELF", "count_gte": 1}],
          "effects": [{"type": "BANISH", "from_zone": "GRAVEYARD",
                       "player": "SELF", "amount": 1},
                      PUMP]},
         card, board)

    assert len(board.players[1].graveyard.cards) == 0
    assert board.combat.attack_power == start + 2


def test_the_bound_is_enforced_when_a_while_never_goes_false(board):
    """The load-bearing one. A mis-authored `while` that cannot go false must
    terminate the game rather than hang it, so `max` is enforced regardless."""
    card = _attacker(board)
    start = board.combat.attack_power
    _run({"type": "REPEAT", "max": 5,
          # Always true: nothing in the body changes it.
          "while": [{"type": "CARD_IN_ZONE", "zone": "graveyard",
                     "player": "SELF", "count_gte": 0}],
          "effects": [PUMP]},
         card, board)
    assert board.combat.attack_power == start + 5


def test_stop_repeat_ends_the_loop(board):
    card = _attacker(board)
    start = board.combat.attack_power
    _run({"type": "REPEAT", "times": 10,
          "effects": [PUMP, {"type": "STOP_REPEAT"}]},
         card, board)
    # The body completes the pass it is in -- "stop repeating", not "undo".
    assert board.combat.attack_power == start + 1


def test_stop_repeat_outside_a_loop_is_a_no_op(board):
    card = _attacker(board)
    start = board.combat.attack_power
    _run({"type": "STOP_REPEAT"}, card, board)
    _run({"type": "REPEAT", "times": 2, "effects": [PUMP]}, card, board)
    # A stray break must not leak into the next loop and end it early.
    assert board.combat.attack_power == start + 2


def test_a_nested_break_ends_only_the_inner_loop(board):
    """A single shared flag passes every test above and fails here: the inner
    loop's break would end the outer one too."""
    card = _attacker(board)
    start = board.combat.attack_power
    _run({"type": "REPEAT", "times": 3,
          "effects": [{"type": "REPEAT", "times": 5,
                       "effects": [PUMP, {"type": "STOP_REPEAT"}]}]},
         card, board)
    # 3 outer passes x 1 inner pass each.
    assert board.combat.attack_power == start + 3


def test_a_break_before_a_nested_loop_still_ends_the_outer_one(board):
    """The other half of the nesting case. With one shared flag the inner loop
    clears the outer loop's break on its way past, and the outer runs on."""
    card = _attacker(board)
    start = board.combat.attack_power
    _run({"type": "REPEAT", "times": 4,
          "effects": [{"type": "STOP_REPEAT"},
                      {"type": "REPEAT", "times": 2, "effects": [PUMP]}]},
         card, board)
    # One outer pass, whose inner loop still ran twice.
    assert board.combat.attack_power == start + 2
