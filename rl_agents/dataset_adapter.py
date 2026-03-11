"""Dataset adapter utilities for offline RL training from ReplayDB embeddings."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Optional

import torch
from torch.utils.data import Dataset

from data_collection.replay_db import ReplayDB


def _resolve_game_ids(db_path: str, game_ids: Optional[list[int]] = None) -> list[int]:
    if game_ids:
        return sorted(set(int(g) for g in game_ids))

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT t.game_id
            FROM transitions t
            JOIN embeddings e ON e.transition_id = t.id
            ORDER BY t.game_id
            """
        ).fetchall()
        return [int(r[0]) for r in rows]
    finally:
        conn.close()


@dataclass
class IQLTensorBatch:
    states: torch.Tensor
    actions: torch.Tensor
    rewards: torch.Tensor
    next_states: torch.Tensor
    dones: torch.Tensor


def build_iql_tensors_from_replay_db(
    db_path: str,
    game_ids: Optional[list[int]] = None,
    next_state_same_player: bool = True,
) -> dict:
    """Build IQL tensors from ReplayDB embeddings.

    Args:
        db_path: Path to ReplayDB sqlite file.
        game_ids: Optional subset of game IDs. If omitted, uses all embedded games.
        next_state_same_player: If True, s' is next decision by the same player.
            If False, s' is the next global transition.
    """
    db = ReplayDB(db_path)
    try:
        selected_games = _resolve_game_ids(db_path, game_ids)
        if not selected_games:
            raise ValueError("No games with embeddings found in replay DB")

        s_list: list[torch.Tensor] = []
        a_list: list[torch.Tensor] = []
        r_list: list[float] = []
        s_next_list: list[torch.Tensor] = []
        d_list: list[float] = []

        state_dim: Optional[int] = None
        action_dim: Optional[int] = None
        transitions_loaded = 0

        for gid in selected_games:
            rows = db.load_embedding_dataset(gid)
            if not rows:
                continue

            transitions_loaded += len(rows)

            if state_dim is None:
                state_dim = int(rows[0]["state_emb"].shape[0])
                action_dim = int(rows[0]["action_emb"].shape[0])

            if next_state_same_player:
                by_player: dict[int, list[dict]] = {1: [], 2: []}
                for row in rows:
                    by_player[int(row["player_id"])].append(row)

                for player_rows in by_player.values():
                    for i, row in enumerate(player_rows):
                        s_list.append(row["state_emb"].float())
                        a_list.append(row["action_emb"].float())
                        r_list.append(float(row["reward"]))
                        d_list.append(float(row["done"]))
                        if i + 1 < len(player_rows):
                            s_next_list.append(player_rows[i + 1]["state_emb"].float())
                        else:
                            s_next_list.append(torch.zeros(state_dim, dtype=torch.float32))
            else:
                for i, row in enumerate(rows):
                    s_list.append(row["state_emb"].float())
                    a_list.append(row["action_emb"].float())
                    r_list.append(float(row["reward"]))
                    d_list.append(float(row["done"]))
                    if i + 1 < len(rows):
                        s_next_list.append(rows[i + 1]["state_emb"].float())
                    else:
                        s_next_list.append(torch.zeros(state_dim, dtype=torch.float32))

        if not s_list:
            raise ValueError("No embedded transitions found for selected game IDs")

        return {
            "states": torch.stack(s_list),
            "actions": torch.stack(a_list),
            "rewards": torch.tensor(r_list, dtype=torch.float32),
            "next_states": torch.stack(s_next_list),
            "dones": torch.tensor(d_list, dtype=torch.float32),
            "state_dim": int(state_dim),
            "action_dim": int(action_dim),
            "num_transitions": len(s_list),
            "game_ids": selected_games,
            "transitions_loaded": transitions_loaded,
        }
    finally:
        db.close()


class ReplayDataset(Dataset):
    """Torch Dataset over pre-embedded replay transitions for IQL."""

    def __init__(
        self,
        states: torch.Tensor,
        actions: torch.Tensor,
        rewards: torch.Tensor,
        next_states: torch.Tensor,
        dones: torch.Tensor,
    ):
        n = states.shape[0]
        if not (
            actions.shape[0] == n
            and rewards.shape[0] == n
            and next_states.shape[0] == n
            and dones.shape[0] == n
        ):
            raise ValueError("All tensors must have matching first dimension")

        self.states = states.float()
        self.actions = actions.float()
        self.rewards = rewards.float()
        self.next_states = next_states.float()
        self.dones = dones.float()

    @classmethod
    def from_tensor_dict(cls, payload: dict) -> "ReplayDataset":
        return cls(
            states=payload["states"],
            actions=payload["actions"],
            rewards=payload["rewards"],
            next_states=payload["next_states"],
            dones=payload["dones"],
        )

    @classmethod
    def from_replay_db(
        cls,
        db_path: str,
        game_ids: Optional[list[int]] = None,
        next_state_same_player: bool = True,
    ) -> "ReplayDataset":
        payload = build_iql_tensors_from_replay_db(
            db_path=db_path,
            game_ids=game_ids,
            next_state_same_player=next_state_same_player,
        )
        return cls.from_tensor_dict(payload)

    def __len__(self) -> int:
        return int(self.states.shape[0])

    def __getitem__(self, idx: int) -> IQLTensorBatch:
        return IQLTensorBatch(
            states=self.states[idx],
            actions=self.actions[idx],
            rewards=self.rewards[idx],
            next_states=self.next_states[idx],
            dones=self.dones[idx],
        )
