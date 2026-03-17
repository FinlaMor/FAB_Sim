from __future__ import annotations

import random
from typing import Any

from rl_agents.game_backends import (
    _auto_pass_when_only_option,
    _pick_talishar_action,
    _run_talishar_pvp_game,
    _run_talishar_random_game,
)


class _SelectorMustNotRunAgent:
    def choose_talishar_action(self, state: dict, actions: list[dict], player_id: int) -> dict:
        raise AssertionError("selector should not run when only action is forced pass")


class _RandomGameStubClient:
    def __init__(self) -> None:
        self.submitted_actions: list[dict] = []
        self.processed_modes: list[int] = []
        self._states = [
            {
                "turnNo": 1,
                "playerHealth": 40,
                "opponentHealth": 40,
                "havePriority": True,
                "canPassPhase": True,
                "actions": [{"type": "pass_phase", "mode": 99, "cardID": ""}],
            },
            {
                "turnNo": 1,
                "playerHealth": 40,
                "opponentHealth": 0,
                "havePriority": False,
                "canPassPhase": False,
                "actions": [],
            },
        ]

    def create_game(self, deck: dict, format: str = "cc", *, deck_test_mode: bool = True) -> tuple[int, str]:
        return 1001, "p1_auth"

    def start_game(self, game_name: int, auth_key: str) -> bool:
        return True

    def get_state(self, game_name: int, auth_key: str, player_id: int = 1) -> dict:
        return self._states.pop(0)

    def is_game_over(self, state: dict) -> tuple[bool, int | None]:
        p1_hp = int(state.get("playerHealth", 1))
        p2_hp = int(state.get("opponentHealth", 1))
        if p2_hp <= 0:
            return True, 1
        if p1_hp <= 0:
            return True, 2
        return False, None

    def get_available_actions(self, state: dict) -> list[dict]:
        return list(state.get("actions", []))

    def submit_action(self, game_name: int, auth_key: str, action: dict, player_id: int = 1) -> None:
        self.submitted_actions.append(dict(action))

    def process_input(
        self,
        game_name: int,
        auth_key: str,
        mode: str | int,
        player_id: int = 1,
        card_id: str = "",
        button_input: str = "",
        input_text: str = "",
    ) -> None:
        self.processed_modes.append(int(mode))


class _PvpGameStubClient:
    def __init__(self) -> None:
        self.submitted_actions: list[tuple[int, dict]] = []
        self.processed_modes: list[tuple[int, int]] = []
        self._states_by_player = {
            1: [
                {
                    "turnNo": 1,
                    "playerHealth": 40,
                    "opponentHealth": 40,
                    "havePriority": True,
                    "canPassPhase": True,
                    "actions": [{"type": "pass_phase", "mode": 99, "cardID": ""}],
                },
                {
                    "turnNo": 1,
                    "playerHealth": 40,
                    "opponentHealth": 0,
                    "havePriority": False,
                    "canPassPhase": False,
                    "actions": [],
                },
            ],
            2: [
                {
                    "turnNo": 1,
                    "playerHealth": 40,
                    "opponentHealth": 40,
                    "havePriority": False,
                    "canPassPhase": False,
                    "actions": [],
                },
                {
                    "turnNo": 1,
                    "playerHealth": 0,
                    "opponentHealth": 40,
                    "havePriority": False,
                    "canPassPhase": False,
                    "actions": [],
                },
            ],
        }

    def create_game(self, deck: dict, format: str = "cc", *, deck_test_mode: bool = False) -> tuple[int, str]:
        return 2002, "p1_auth"

    def join_game(self, game_name: int, deck: dict, player_id: int = 2) -> str:
        return "p2_auth"

    def start_game(self, game_name: int, auth_key: str) -> bool:
        return True

    def get_state(self, game_name: int, auth_key: str, player_id: int = 1) -> dict:
        return self._states_by_player[player_id].pop(0)

    def is_game_over(self, state: dict) -> tuple[bool, int | None]:
        p1_hp = int(state.get("playerHealth", 1))
        p2_hp = int(state.get("opponentHealth", 1))
        if p2_hp <= 0:
            return True, 1
        if p1_hp <= 0:
            return True, 2
        return False, None

    def get_available_actions(self, state: dict) -> list[dict]:
        return list(state.get("actions", []))

    def submit_action(self, game_name: int, auth_key: str, action: dict, player_id: int = 1) -> None:
        self.submitted_actions.append((player_id, dict(action)))

    def process_input(
        self,
        game_name: int,
        auth_key: str,
        mode: str | int,
        player_id: int = 1,
        card_id: str = "",
        button_input: str = "",
        input_text: str = "",
    ) -> None:
        self.processed_modes.append((player_id, int(mode)))


def test_auto_pass_when_only_option_detects_single_pass_action() -> None:
    forced = _auto_pass_when_only_option([{"type": "pass_phase", "mode": 99, "cardID": ""}])
    assert forced is not None
    assert forced["type"] == "pass_phase"

    assert _auto_pass_when_only_option([{"type": "hand", "mode": 1, "cardID": "abc"}]) is None
    assert _auto_pass_when_only_option(
        [
            {"type": "pass_phase", "mode": 99, "cardID": ""},
            {"type": "hand", "mode": 1, "cardID": "abc"},
        ]
    ) is None


def test_pick_talishar_action_skips_agent_selector_on_forced_pass() -> None:
    forced_action = {"type": "pass_phase", "mode": 99, "cardID": ""}
    chosen = _pick_talishar_action(
        _SelectorMustNotRunAgent(),
        state={},
        actions=[forced_action],
        rng=random.Random(0),
        player_id=1,
    )
    assert chosen == forced_action


def test_random_talishar_game_submits_single_forced_pass() -> None:
    client = _RandomGameStubClient()

    result = _run_talishar_random_game(
        client,
        p1_deck_submission={},
        max_turns=5,
        rng=random.Random(1),
    )

    assert result.winner == 1
    assert result.total_actions == 1
    assert client.submitted_actions == [{"type": "pass_phase", "mode": 99, "cardID": ""}]
    assert client.processed_modes == []


def test_pvp_talishar_game_submits_single_forced_pass() -> None:
    client = _PvpGameStubClient()

    result = _run_talishar_pvp_game(
        client,
        p1_deck_submission={},
        p2_deck_submission={},
        p1_agent=None,
        p2_agent=None,
        p1_seed=7,
        p2_seed=8,
        max_turns=5,
    )

    assert result.winner == 1
    assert result.total_actions == 1
    assert client.submitted_actions == [(1, {"type": "pass_phase", "mode": 99, "cardID": ""})]
    assert client.processed_modes == []
