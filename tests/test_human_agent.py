"""Tests for the HumanAgent interactive player agent."""

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.actions import Action, ActionType
from engine.state import CombatState, GameState, Step
from rl_agents.human_agent import HumanAgent, _ACTION_LABELS
from tests.conftest import _make_card, _make_combat, _make_state


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def agent():
    return HumanAgent(player_id=1)


@pytest.fixture
def state():
    return _make_state()


def _action(atype=ActionType.PASS, card=None, **kwargs):
    return Action(type=atype, player_id=1, card=card, **kwargs)


# ---------------------------------------------------------------------------
# 1. Action options with mocked stdin
# ---------------------------------------------------------------------------

class TestActionChoices:
    def test_choose_action_from_list(self, agent, state):
        actions = [_action(ActionType.PASS), _action(ActionType.PLAY_CARD, card=_make_card())]
        with patch("builtins.input", return_value="1"):
            result = agent(state, actions)
        assert result is actions[1]

    def test_choose_first_action(self, agent, state):
        actions = [_action(ActionType.PASS), _action(ActionType.PLAY_CARD, card=_make_card())]
        with patch("builtins.input", return_value="0"):
            result = agent(state, actions)
        assert result is actions[0]


# ---------------------------------------------------------------------------
# 2. Non-Action options (strings, ints)
# ---------------------------------------------------------------------------

class TestNonActionChoices:
    def test_choose_string_option(self, agent, state):
        options = ["go first", "go second"]
        with patch("builtins.input", return_value="1"):
            result = agent(state, options)
        assert result == "go second"

    def test_choose_int_option(self, agent, state):
        options = [1, 2]
        with patch("builtins.input", return_value="0"):
            result = agent(state, options)
        assert result == 1


# ---------------------------------------------------------------------------
# 3. Auto-select single option
# ---------------------------------------------------------------------------

class TestAutoSelect:
    def test_auto_select_single_action(self, agent, state):
        actions = [_action(ActionType.PASS)]
        result = agent(state, actions)
        assert result is actions[0]

    def test_auto_select_single_non_action(self, agent, state):
        options = ["only option"]
        result = agent(state, options)
        assert result == "only option"


# ---------------------------------------------------------------------------
# 4. Empty / non-list options returned directly
# ---------------------------------------------------------------------------

class TestEmptyOptions:
    def test_empty_list(self, agent, state):
        result = agent(state, [])
        assert result == []

    def test_none_options(self, agent, state):
        result = agent(state, None)
        assert result is None

    def test_non_list_string(self, agent, state):
        result = agent(state, "something")
        assert result == "something"


# ---------------------------------------------------------------------------
# 5. _display_state produces output without errors
# ---------------------------------------------------------------------------

class TestDisplayState:
    def test_action_phase(self, agent, state, capsys):
        agent._display_state(state)
        out = capsys.readouterr().out
        assert "Turn 1" in out
        assert "Step:" in out

    def test_combat_phase(self, agent, state, capsys):
        attack = _make_card(slug="big_hit", name="Big Hit", types=["Action", "Attack"], base_power=5)
        attack.owner = 2
        attack.controller = 2
        state.combat = _make_combat(attacker_id=2, attack_card=attack)
        agent._display_state(state)
        out = capsys.readouterr().out
        assert "COMBAT" in out
        assert "Big Hit" in out

    def test_empty_hand(self, agent, state, capsys):
        state.players[1].hand.cards.clear()
        agent._display_state(state)
        out = capsys.readouterr().out
        assert "YOU" in out

    def test_with_equipment(self, agent, state, capsys):
        # Head zone entry requires the "Head" subtype (CR 3.x zone rules).
        equip = _make_card(slug="helm", name="Iron Helm", types=["Equipment"],
                           subtypes=["Head"], base_defense=1)
        equip.owner = 1
        equip.controller = 1
        state.players[1].head.add(equip)
        agent._display_state(state)
        out = capsys.readouterr().out
        assert "Iron Helm" in out

    def test_with_weapon(self, agent, state, capsys):
        wpn = _make_card(slug="sword", name="Dawnblade", types=["Weapon"])
        wpn.owner = 1
        wpn.controller = 1
        state.players[1].weapon1.add(wpn)
        agent._display_state(state)
        out = capsys.readouterr().out
        assert "Dawnblade" in out

    def test_with_arsenal(self, agent, state, capsys):
        c = _make_card(slug="stored", name="Stored Card")
        c.owner = 1
        c.controller = 1
        state.players[1].arsenal.add(c)
        agent._display_state(state)
        out = capsys.readouterr().out
        assert "Arsenal" in out


# ---------------------------------------------------------------------------
# 6. _format_action returns readable strings
# ---------------------------------------------------------------------------

class TestFormatAction:
    def test_pass(self, agent):
        assert agent._format_action(_action(ActionType.PASS)) == "Pass"

    def test_reaction_pass(self, agent):
        assert agent._format_action(_action(ActionType.REACTION_PASS)) == "Pass (no reaction)"

    def test_play_card(self, agent):
        card = _make_card(name="Scar for a Scar", base_cost=1, base_power=4, base_defense=3)
        result = agent._format_action(_action(ActionType.PLAY_CARD, card=card))
        assert "Play card" in result
        assert "Scar for a Scar" in result

    def test_attack_weapon(self, agent):
        # Weapon attacks route through ACTIVATE_CARD with is_attack_proxy=True.
        wpn = _make_card(name="Dawnblade", types=["Weapon"])
        action = _action(ActionType.ACTIVATE_CARD, card=wpn)
        action.is_attack_proxy = True
        result = agent._format_action(action)
        assert "Activate card" in result
        assert "Dawnblade" in result

    def test_defend_cards(self, agent):
        c = _make_card(name="Sink Below")
        result = agent._format_action(_action(ActionType.DEFEND_CARDS, card=c))
        assert "Defend with cards" in result

    def test_defend_equipment(self, agent):
        # Equipment defends go through DEFEND_CARDS with the equipment in card_list.
        helm = _make_card(name="Helm", types=["Equipment"])
        action = _action(ActionType.DEFEND_CARDS)
        action.card_list = [helm]
        result = agent._format_action(action)
        assert "Defend with cards" in result
        assert "Helm" in result

    def test_store_arsenal(self, agent):
        result = agent._format_action(_action(ActionType.STORE_ARSENAL, card=_make_card(name="Stored")))
        assert "Store in arsenal" in result

    def test_all_action_types_have_labels(self):
        for at in ActionType:
            assert at in _ACTION_LABELS


# ---------------------------------------------------------------------------
# 7. Input validation: re-prompt on bad input
# ---------------------------------------------------------------------------

class TestInputValidation:
    def test_non_numeric_then_valid(self, agent, state):
        actions = [_action(ActionType.PASS), _action(ActionType.PLAY_CARD, card=_make_card())]
        with patch("builtins.input", side_effect=["abc", "0"]):
            result = agent(state, actions)
        assert result is actions[0]

    def test_out_of_range_then_valid(self, agent, state):
        actions = [_action(ActionType.PASS), _action(ActionType.PLAY_CARD, card=_make_card())]
        with patch("builtins.input", side_effect=["5", "1"]):
            result = agent(state, actions)
        assert result is actions[1]

    def test_empty_input_then_valid(self, agent, state):
        actions = [_action(ActionType.PASS), _action(ActionType.PLAY_CARD, card=_make_card())]
        with patch("builtins.input", side_effect=["", "0"]):
            result = agent(state, actions)
        assert result is actions[0]

    def test_negative_index_then_valid(self, agent, state):
        actions = [_action(ActionType.PASS), _action(ActionType.PLAY_CARD, card=_make_card())]
        with patch("builtins.input", side_effect=["-1", "0"]):
            result = agent(state, actions)
        assert result is actions[0]
