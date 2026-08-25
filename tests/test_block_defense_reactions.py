""""Defense reaction cards can't be played this chain link" blocked nothing.

`combat.no_defense_reactions` is READ in four places -- play.py's reaction-step
offer and `_defense_reaction_legal_check`, and actions.py for both hand and
arsenal -- and was **set by nothing**. All three cards printing this text wrote
a dead `SET_FLAG` instead, under TWO different names
(`DEFENSE_REACTION_BLOCKED` and `command_and_conquer_no_dr`), so each looked
implemented and blocked nothing.

Exactly the shape of `DamageEvent.unpreventable` earlier in this effort: the
reader existed, the writer did not. Worth naming as a class -- when a card's
clause seems to need a new mechanic, grep for the FIELD before building it,
because a fully-wired reader with no writer looks identical to a missing
feature from the card's side.

Two more defects came out with them:

  back_stab_yellow          is an Action - Attack card and its ability_type was
                            DEFENSE_REACTION -- a different card kind, offered
                            in the wrong step entirely.
  corrupt_and_conquer_red   "if this was played from your BANISHED zone" was
                            CARD_IN_ZONE zone:BANISHED, which asks whether any
                            card is SITTING in the banished zone: true whenever
                            anything has been banished, and unrelated to where
                            this card was played from. PLAYED_FROM_ZONE is the
                            real condition.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.effect_types import compile_effect
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

PLAIN = "brutal_assault_red"
CARDS = ["back_stab_yellow", "command_and_conquer_red", "corrupt_and_conquer_red"]


def _card(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _state():
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="": o[0]
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    st.individual_turns = 1
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=_card(PLAIN, 1), keywords=[])
    return st


def test_the_field_starts_false():
    """If it ever defaulted True the tests below would pass vacuously."""
    assert _state().combat.no_defense_reactions is False


def test_the_effect_sets_the_field_the_engine_reads():
    st = _state()

    compile_effect("BLOCK_DEFENSE_REACTIONS", {})(_card(PLAIN, 1), None, st)

    assert st.combat.no_defense_reactions is True


def test_it_is_a_no_op_outside_combat():
    """Asserting the STATE is untouched, not merely that nothing raised — a
    call that silently did the wrong thing satisfies the weaker claim."""
    st = _state()
    st.combat = None

    compile_effect("BLOCK_DEFENSE_REACTIONS", {})(_card(PLAIN, 1), None, st)

    assert st.combat is None, "it invented a combat to write into"


def test_the_legality_check_honours_it():
    """Asserted through play._defense_reaction_legal_check, the function the
    engine actually consults — not by reading the flag back."""
    import engine.play as P

    from engine.state import Step

    st = _state()
    # CR 8.1.3a: a defense reaction is legal only in the REACTION step, and
    # only for the non-attacking player. Without these the baseline is already
    # False and "False after blocking" would prove nothing.
    st.step = Step.COMBAT_REACTION
    dr = _card("sink_below_red", 2)
    assert dr.is_defense_reaction, "fixture is not a defense reaction card"
    st.players[2].hand.add(dr)

    assert P._defense_reaction_legal_check(st, dr, 2) is True, (
        "the fixture is not a legal defense reaction to begin with, so the "
        "assertion below would pass whatever the block does")

    compile_effect("BLOCK_DEFENSE_REACTIONS", {})(_card(PLAIN, 1), None, st)

    assert P._defense_reaction_legal_check(st, dr, 2) is False, (
        "the engine still allowed a defense reaction")


# --- the three cards --------------------------------------------------------

@pytest.mark.parametrize("slug", CARDS)
def test_no_card_still_writes_a_dead_flag(slug):
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    blob = json.dumps(json.loads(
        next(root.rglob(f"{slug}.json")).read_text(encoding="utf-8")))
    for flag in ("DEFENSE_REACTION_BLOCKED", "command_and_conquer_no_dr"):
        assert flag not in blob, f"{slug} still sets the dead flag {flag}"


@pytest.mark.parametrize("slug", ["back_stab_yellow", "command_and_conquer_red"])
def test_the_unconditional_cards_block_on_attack(slug):
    st = _state()

    run_ability(get_card(slug).abilities[0], _card(slug, 1), None, st)

    assert st.combat.no_defense_reactions is True


def test_corrupt_and_conquer_blocks_only_when_played_from_banish():
    st = _state()
    source = _card("corrupt_and_conquer_red", 1)

    run_ability(get_card("corrupt_and_conquer_red").abilities[0], source, None, st)
    assert st.combat.no_defense_reactions is False, (
        "it blocked without having been played from the banished zone")

    source.played_from_zone = "banished"
    run_ability(get_card("corrupt_and_conquer_red").abilities[0], source, None, st)
    assert st.combat.no_defense_reactions is True


def test_back_stab_is_not_a_defense_reaction_ability():
    """It is an Action - Attack card; DEFENSE_REACTION offered it in the wrong
    step."""
    assert "Attack" in (DB.get("back_stab_yellow").subtypes or [])
    types = [a.ability_type.upper()
             for a in get_card("back_stab_yellow").abilities]
    assert "DEFENSE_REACTION" not in types, types
