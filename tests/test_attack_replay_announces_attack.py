"""The attack-power replay harness must announce the attack.

The harness in scripts/talishar_attack_replay.py reconstructs a board and asks
the engine what an attack's power is, and its answers are compared against
Talishar's. It applied continuous statics but never fired the ON_ATTACK
triggers, so a pump written as a TRIGGERED / ON_ATTACK ability read as absent.

That is not a small class -- it is every "Combo — ... gains +N{p}" card -- and
it fails in the direction that manufactures findings: ours low, theirs right,
looking exactly like an engine defect in a card the engine has right.
whelming_gustwave_red is the case that surfaced it, on states BUILT to put
Surging Strike on the previous chain link. tests/test_last_chain_attack.py and
tests/test_go_again_backlog_combo.py already covered the card; nothing covered
the harness, so the harness was where the error lived.

These assert through our_power(), the same entry point the comparison uses, so
the test fails if the announcement is removed from it.
"""

import copy

import pytest

from engine.card import CardDB
from engine.card_effects.dsl.loader import load_all_cards
from engine.state import ChainLink, Step
from scripts.talishar_attack_replay import _replay_agent, our_power
from tests.conftest import _make_state
import engine.engine as E

load_all_cards()
DB = CardDB()

COMBO_CARD = "whelming_gustwave_red"
COMBO_PARTNER = "surging_strike_red"


def _board():
    """The minimum the harness needs: listeners registered, a live attacker."""
    st = _make_state()
    st.card_db = DB
    st.step = Step.COMBAT if hasattr(Step, "COMBAT") else Step.ACTION
    st.active_player = 1
    st.combat = None
    # The harness's own agent, not a local stand-in: conftest's default answers
    # every prompt with options[0], and ask_yes_no offers YES first, so a local
    # stub would quietly test a configuration the comparison never runs.
    st.player_agents = {1: _replay_agent, 2: _replay_agent}
    # Without this every WHILE_STATIC and every dispatched trigger is silently
    # absent -- the harness's own docstring calls this out as the whole hazard
    # of a replay harness.
    E._setup_dsl_listeners(st)
    return st


def _push_link(st, slug):
    st.chain_links.append(ChainLink(
        chainlink_id=len(st.chain_links) + 1, attacker_id=1, attack_slug=slug,
        attack_power=0, net_damage=0, keywords=[], from_weapon=False))


def _base_power(slug):
    card = DB.get(slug)
    assert card is not None, "unknown slug %s" % slug
    return card.base_power or 0


def test_combo_pump_applies_when_the_named_card_was_the_last_link():
    st = _board()
    _push_link(st, COMBO_PARTNER)
    assert our_power(st, COMBO_CARD, attacker_id=1) == _base_power(COMBO_CARD) + 1


def test_combo_pump_absent_on_an_empty_chain():
    # The negative case carries the weight: a harness that pumped everything
    # unconditionally would satisfy the assertion above just as well.
    st = _board()
    assert our_power(st, COMBO_CARD, attacker_id=1) == _base_power(COMBO_CARD)


def test_combo_pump_absent_when_a_different_card_was_the_last_link():
    st = _board()
    _push_link(st, "head_jab_red")
    assert our_power(st, COMBO_CARD, attacker_id=1) == _base_power(COMBO_CARD)


def test_the_replay_agent_declines_optional_effects():
    """Announcing the attack fires optional pumps too, and the old stub answered
    every prompt with options[0] -- which ask_yes_no offers as YES.

    The spectator feed does not record whether the player paid an optional cost,
    so auto-accepting is invention: it turned 102 agreeing cadaverous_tilling
    attacks into ours+2, and 67 more on felling_of_the_crown.
    """
    from engine.card_effects.ability_keywords import YES, NO, DECLINE
    from scripts.talishar_attack_replay import _replay_agent

    assert _replay_agent(None, [YES, NO]) == NO
    assert _replay_agent(None, ["banish a card", DECLINE]) == DECLINE
    # Anything that is not an opt-out still takes the first option, so a forced
    # choice does not deadlock the replay.
    assert _replay_agent(None, ["a", "b"]) == "a"


#: Cadaverous Tilling: "Decompose - when this attacks, you may banish 2 Earth
#: cards and an action card from your graveyard. If you do, this gets +2{p}."
OPTIONAL_PUMP_CARD = "cadaverous_tilling_red"
#: Enough Earth action cards to satisfy Decompose's gate AND its cost.
DECOMPOSE_FUEL = ["autumns_touch_red", "autumns_touch_yellow", "anthem_of_spring_blue"]


def _stock_graveyard(st, slugs, owner=1):
    for slug in slugs:
        card = copy.deepcopy(DB.get(slug))
        card.owner = card.controller = owner
        st.players[owner].graveyard.add(card)


def test_an_optional_pump_is_declined_even_when_it_could_be_paid():
    """The graveyard is stocked so Decompose's gate PASSES and the cost is
    payable. Declining must still be what happens -- otherwise the harness is
    inventing a player choice the spectator feed never recorded."""
    st = _board()
    _stock_graveyard(st, DECOMPOSE_FUEL)
    assert our_power(st, OPTIONAL_PUMP_CARD, attacker_id=1) == \
        _base_power(OPTIONAL_PUMP_CARD)


def test_accepting_the_same_optional_does_pump_it():
    """The counterfactual explains_as_choice() computes. Without this, the test
    above would pass just as well against a card whose optional is unreachable,
    and would be proving nothing about the agent."""
    from scripts.talishar_attack_replay import _accepting_agent

    st = _board()
    _stock_graveyard(st, DECOMPOSE_FUEL)
    st.player_agents = {1: _accepting_agent, 2: _accepting_agent}
    assert our_power(st, OPTIONAL_PUMP_CARD, attacker_id=1) == \
        _base_power(OPTIONAL_PUMP_CARD) + 2


def test_a_trigger_that_raises_does_not_take_down_the_power_read():
    """A trigger needing more game than a reconstructed state carries must not
    take the whole comparison down -- the power read is still the engine's
    answer for everything else on the board.

    Asserted through our_power, not through _announce_attack alone: "it did not
    raise" is not the guarantee. The guarantee is that a usable number still
    comes back.
    """
    st = _board()

    class _BoomOnAnnounce:
        """Raises for the announcement only, and delegates everything else.

        A stub that broke every emit would also break the RECALC_ATTACK_POWER
        dispatch that WHILE_STATIC abilities hang on, so it would be testing
        that a dead event manager is survivable rather than that a bad TRIGGER
        is.
        """

        def __init__(self, real):
            self._real = real

        def emit(self, event, *a, **k):
            if getattr(event, "type", None) == "attacking":
                raise RuntimeError("trigger needs a real game")
            return self._real.emit(event, *a, **k)

        def __getattr__(self, name):
            return getattr(self._real, name)

    st.event_manager = _BoomOnAnnounce(st.event_manager)
    _push_link(st, COMBO_PARTNER)
    # The combo pump is lost with the announcement -- that is the cost of the
    # failure -- but a usable number still comes back for everything else.
    assert our_power(st, COMBO_CARD, attacker_id=1) == _base_power(COMBO_CARD)
