"""Dataset adapter utilities for offline RL training from ReplayDB embeddings."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Optional

import torch
from torch.utils.data import Dataset

from data_collection.replay_db import ReplayDB


def _resolve_game_ids(
    db_path: str,
    game_ids: Optional[list[int]] = None,
    filter_timeout: bool = False,
) -> list[int]:
    """Resolve which game IDs to include in the dataset.

    Args:
        db_path: Path to the ReplayDB sqlite file.
        game_ids: Optional explicit subset. If provided, timeout filtering is
            still applied when *filter_timeout* is True.
        filter_timeout: If True, exclude games where ``ended_on_turn_cap=1``.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if game_ids:
            candidates = sorted(set(int(g) for g in game_ids))
            if not filter_timeout:
                return candidates
            # Filter explicit game IDs against timeout flag
            placeholders = ",".join("?" for _ in candidates)
            rows = conn.execute(
                f"""
                SELECT game_id FROM games
                WHERE game_id IN ({placeholders})
                  AND (ended_on_turn_cap IS NULL OR ended_on_turn_cap = 0)
                """,
                candidates,
            ).fetchall()
            filtered = [int(r[0]) for r in rows]
            excluded = len(candidates) - len(filtered)
            if excluded:
                print(
                    f"[dataset] filter_timeout: excluded {excluded}/{len(candidates)} "
                    f"timed-out games from explicit game_ids",
                    flush=True,
                )
            return sorted(filtered)

        timeout_clause = "AND (g.ended_on_turn_cap IS NULL OR g.ended_on_turn_cap = 0)" if filter_timeout else ""
        rows = conn.execute(
            f"""
            SELECT DISTINCT t.game_id
            FROM transitions t
            JOIN embeddings e ON e.transition_id = t.id
            JOIN games g ON g.game_id = t.game_id
            WHERE g.winner IS NOT NULL
            {timeout_clause}
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


def _apply_rtg(r_list: list[float], d_list: list[float], gamma: float) -> list[float]:
    """Replace terminal-only rewards with discounted reward-to-go.

    For sparse terminal rewards (+1/-1 at episode end, 0 elsewhere), this
    propagates the outcome backwards: r_t = gamma^(steps_remaining) * outcome.
    Transitions where done=1 keep their terminal reward.
    Non-terminal transitions with reward=0 get the discounted future return.
    """
    result = list(r_list)
    n = len(result)
    # find episode boundaries (done=1) and back-fill
    run = 0.0
    for i in range(n - 1, -1, -1):
        if d_list[i]:
            run = r_list[i]  # reset to terminal reward at episode end
            result[i] = run
        else:
            run = gamma * run
            result[i] = run
    return result


def build_iql_tensors_from_replay_db(
    db_path: str,
    game_ids: Optional[list[int]] = None,
    next_state_same_player: bool = True,
    reward_mode: str = "terminal",
    gamma: float = 0.99,
    filter_timeout: bool = False,
    normalize_rewards: bool = False,
) -> dict:
    """Build IQL tensors from ReplayDB embeddings.

    Args:
        db_path: Path to ReplayDB sqlite file.
        game_ids: Optional subset of game IDs. If omitted, uses all embedded games.
        next_state_same_player: If True, s' is next decision by the same player.
            If False, s' is the next global transition.
        reward_mode: ``'terminal'`` keeps only the final ±1 reward (sparse).
            ``'rtg'`` replaces each reward with discounted reward-to-go
            ``gamma^(steps_remaining) * outcome``, giving every transition a
            non-zero training signal.
        gamma: Discount factor used when ``reward_mode='rtg'``.
        filter_timeout: If True, exclude games that ended on turn cap
            (``ended_on_turn_cap=1``). These games are often low-quality draws.
        normalize_rewards: If True, normalize rewards to zero mean and unit
            variance after all other reward processing (RTG, etc.).
    """
    db = ReplayDB(db_path)
    try:
        # (P3-9) Fail-fast: validate reward_mode before loading any data
        if reward_mode == "rtg" and not next_state_same_player:
            raise ValueError(
                "reward_mode='rtg' requires next_state_same_player=True. "
                "Global trajectory mode mixes player perspectives, corrupting RTG signals."
            )
        if reward_mode not in ("terminal", "rtg"):
            raise ValueError(f"Unknown reward_mode: {reward_mode!r}. Choose 'terminal' or 'rtg'.")

        selected_games = _resolve_game_ids(db_path, game_ids, filter_timeout=filter_timeout)
        if not selected_games:
            raise ValueError("No games with embeddings found in replay DB")

        # P2-5: Warn about peak RAM cost before loading.  For large datasets
        # consider building once with save_mmap() + loading via from_mmap().
        print(
            f"[dataset] assembling tensors from {len(selected_games)} games into RAM "
            f"(~18 KB per transition). For large datasets use ReplayDataset.save_mmap() / from_mmap().",
            flush=True,
        )

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
                        if i + 1 < len(player_rows):
                            # Keep original terminal marker when same-player next state exists.
                            d_list.append(float(row["done"]))
                            s_next_list.append(player_rows[i + 1]["state_emb"].float())
                        else:
                            # In same-player mode, this is an absorbing terminal transition
                            # for the player's trajectory (no next same-player decision).
                            d_list.append(1.0)
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

        if reward_mode == "rtg":
            r_list = _apply_rtg(r_list, d_list, gamma)

        if normalize_rewards:
            r_tensor = torch.tensor(r_list, dtype=torch.float32)
            r_mean = r_tensor.mean().item()
            r_std = r_tensor.std().item()
            if r_std > 1e-8:
                r_list = ((r_tensor - r_mean) / r_std).tolist()
                print(
                    f"[dataset] reward_normalization: mean={r_mean:.4f} std={r_std:.4f}",
                    flush=True,
                )
            else:
                print(
                    f"[dataset] reward_normalization: skipped (std={r_std:.2e} too small)",
                    flush=True,
                )

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
            "reward_mode": reward_mode,
            "filter_timeout": filter_timeout,
            "normalize_rewards": normalize_rewards,
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
        reward_mode: str = "terminal",
        gamma: float = 0.99,
    ) -> "ReplayDataset":
        payload = build_iql_tensors_from_replay_db(
            db_path=db_path,
            game_ids=game_ids,
            next_state_same_player=next_state_same_player,
            reward_mode=reward_mode,
            gamma=gamma,
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

    def save_mmap(self, directory: str) -> None:
        """Save dataset to memory-mappable files for large-scale training (P2-18)."""
        import numpy as np
        from pathlib import Path
        d = Path(directory)
        d.mkdir(parents=True, exist_ok=True)
        for name in ("states", "actions", "rewards", "next_states", "dones"):
            arr = getattr(self, name).numpy()
            mmap = np.memmap(str(d / f"{name}.npy"), dtype=arr.dtype, mode="w+", shape=arr.shape)
            mmap[:] = arr
            mmap.flush()
        # Save metadata
        import json
        meta = {
            "n": int(self.states.shape[0]),
            "state_dim": int(self.states.shape[1]),
            "action_dim": int(self.actions.shape[1]),
        }
        (d / "meta.json").write_text(json.dumps(meta))

    @classmethod
    def from_mmap(cls, directory: str) -> "ReplayDataset":
        """Load dataset from memory-mapped files (low RAM usage)."""
        import numpy as np
        import json
        from pathlib import Path
        d = Path(directory)
        meta = json.loads((d / "meta.json").read_text())
        n, sd, ad = meta["n"], meta["state_dim"], meta["action_dim"]

        states = torch.from_numpy(np.memmap(str(d / "states.npy"), dtype="float32", mode="r", shape=(n, sd)))
        actions = torch.from_numpy(np.memmap(str(d / "actions.npy"), dtype="float32", mode="r", shape=(n, ad)))
        rewards = torch.from_numpy(np.memmap(str(d / "rewards.npy"), dtype="float32", mode="r", shape=(n,)))
        next_states = torch.from_numpy(np.memmap(str(d / "next_states.npy"), dtype="float32", mode="r", shape=(n, sd)))
        dones = torch.from_numpy(np.memmap(str(d / "dones.npy"), dtype="float32", mode="r", shape=(n,)))
        return cls(states=states, actions=actions, rewards=rewards, next_states=next_states, dones=dones)
