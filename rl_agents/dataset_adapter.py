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
            # Filter explicit game IDs against timeout flag.
            # Use a temp table to avoid SQLite's 999-variable IN() limit.
            conn.execute("CREATE TEMP TABLE IF NOT EXISTS _filter_game_ids (game_id INTEGER PRIMARY KEY)")
            conn.execute("DELETE FROM _filter_game_ids")
            conn.executemany("INSERT OR IGNORE INTO _filter_game_ids VALUES (?)", [(g,) for g in candidates])
            rows = conn.execute(
                """
                SELECT game_id FROM games
                JOIN _filter_game_ids f USING (game_id)
                WHERE (ended_on_turn_cap IS NULL OR ended_on_turn_cap = 0)
                """
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
    shaping_scale: float = 0.025,
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
            non-zero training signal. ``'shaped'`` keeps the terminal ±1 and adds
            potential-based shaping ``gamma*Phi(s') - Phi(s)`` where
            ``Phi = shaping_scale * (my_life - opp_life)`` (Ng et al. 1999 —
            policy-invariant, so it densifies without changing the optimal policy).
        gamma: Discount factor used when ``reward_mode='rtg'`` or ``'shaped'``.
        filter_timeout: If True, exclude games that ended on turn cap
            (``ended_on_turn_cap=1``). These games are often low-quality draws.
        normalize_rewards: If True, normalize rewards to zero mean and unit
            variance after all other reward processing (RTG, shaping, etc.).
        shaping_scale: Multiplier on the life differential for ``reward_mode='shaped'``.
            Default 1/40 keeps Phi within roughly [-1, 1] (starting life is ~40).
    """
    import numpy as np

    db = ReplayDB(db_path)
    try:
        # (P3-9) Fail-fast: validate reward_mode before loading any data
        if reward_mode in ("rtg", "shaped") and not next_state_same_player:
            raise ValueError(
                f"reward_mode={reward_mode!r} requires next_state_same_player=True. "
                "Global trajectory mode mixes player perspectives, corrupting the signal."
            )
        if reward_mode not in ("terminal", "rtg", "shaped"):
            raise ValueError(
                f"Unknown reward_mode: {reward_mode!r}. Choose 'terminal', 'rtg', or 'shaped'."
            )

        selected_games = _resolve_game_ids(db_path, game_ids, filter_timeout=filter_timeout)
        if not selected_games:
            raise ValueError("No games with embeddings found in replay DB")

        print(
            f"[dataset] bulk-loading {len(selected_games)} games from SQLite...",
            flush=True,
        )

        # Bulk load: single SQL query → pre-allocated numpy arrays → zero-copy torch conversion.
        # ~3-5× faster than per-game list-appending for large datasets.
        bulk = db.load_embeddings_bulk(selected_games)
        if bulk is None:
            raise ValueError("No embedded transitions found for selected game IDs")

        raw_states = bulk["states"]       # (N, state_dim) float32
        raw_actions = bulk["actions"]     # (N, action_dim) float32
        raw_rewards = bulk["rewards"]     # (N,) float32
        raw_dones = bulk["dones"]         # (N,) float32
        raw_player_ids = bulk["player_ids"]   # (N,) int32
        raw_game_ids = bulk["game_id_per_row"]  # (N,) int64
        state_dim = int(bulk["state_dim"])
        action_dim = int(bulk["action_dim"])
        transitions_loaded = len(raw_states)

        # Detect dim mismatches across transitions (data from mixed-schema runs)
        if raw_states.shape[1] != state_dim or raw_actions.shape[1] != action_dim:
            import warnings
            warnings.warn(
                f"[dataset] unexpected dim mismatch in bulk load: "
                f"state={raw_states.shape[1]} expected={state_dim}",
                stacklevel=2,
            )

        # Build (s, a, r, s', done) pairs respecting same-player or global ordering.
        s_indices: list[int] = []
        s_next_indices: list[int] = []  # -1 = use zero vector
        r_list: list[float] = []
        d_list: list[float] = []

        if next_state_same_player:
            # Group by (game_id, player_id) and pair consecutive decisions
            from collections import defaultdict
            group: dict[tuple, list[int]] = defaultdict(list)
            for i in range(transitions_loaded):
                key = (int(raw_game_ids[i]), int(raw_player_ids[i]))
                group[key].append(i)
            for indices in group.values():
                for j, idx in enumerate(indices):
                    s_indices.append(idx)
                    r_list.append(float(raw_rewards[idx]))
                    if j + 1 < len(indices):
                        d_list.append(float(raw_dones[idx]))
                        s_next_indices.append(indices[j + 1])
                    else:
                        d_list.append(1.0)
                        s_next_indices.append(-1)  # absorbing terminal
        else:
            # Global ordering: pair consecutive rows within the same game
            from collections import defaultdict
            game_group: dict[int, list[int]] = defaultdict(list)
            for i in range(transitions_loaded):
                game_group[int(raw_game_ids[i])].append(i)
            for indices in game_group.values():
                for j, idx in enumerate(indices):
                    s_indices.append(idx)
                    r_list.append(float(raw_rewards[idx]))
                    d_list.append(float(raw_dones[idx]))
                    s_next_indices.append(indices[j + 1] if j + 1 < len(indices) else -1)

        n_out = len(s_indices)

        # Allocate output arrays (pre-sized, no growth)
        out_states = np.empty((n_out, state_dim), dtype=np.float32)
        out_actions = np.empty((n_out, action_dim), dtype=np.float32)
        out_next_states = np.zeros((n_out, state_dim), dtype=np.float32)
        out_rewards = np.empty(n_out, dtype=np.float32)
        out_dones = np.empty(n_out, dtype=np.float32)

        for j in range(n_out):
            src = s_indices[j]
            out_states[j] = raw_states[src]
            out_actions[j] = raw_actions[src]
            out_rewards[j] = r_list[j]
            out_dones[j] = d_list[j]
            nxt = s_next_indices[j]
            if nxt >= 0:
                out_next_states[j] = raw_states[nxt]
            # else: stays as zeros (absorbing terminal)

        if reward_mode == "shaped":
            # Potential-based reward shaping (Ng et al. 1999): keep the terminal
            # +/-1 and add gamma*Phi(s') - Phi(s), Phi = scale*(my_life-opp_life)
            # from the acting player's perspective. Terminal s' is absorbing with
            # Phi=0. Policy-invariant regardless of scale, so it densifies the
            # signal without changing which policy is optimal.
            transition_ids = bulk["transition_ids"]
            pot_map = db.load_life_potentials(selected_games)
            row_phi = np.array(
                [shaping_scale * pot_map.get(int(tid), 0.0) for tid in transition_ids],
                dtype=np.float32,
            )
            for j in range(n_out):
                phi_s = row_phi[s_indices[j]]
                nxt = s_next_indices[j]
                phi_next = row_phi[nxt] if nxt >= 0 else 0.0
                out_rewards[j] += gamma * phi_next - phi_s

        if reward_mode == "rtg":
            out_rewards = np.array(
                _apply_rtg(out_rewards.tolist(), out_dones.tolist(), gamma), dtype=np.float32
            )

        if normalize_rewards:
            r_mean = float(out_rewards.mean())
            r_std = float(out_rewards.std())
            if r_std > 1e-8:
                out_rewards = (out_rewards - r_mean) / r_std
                print(
                    f"[dataset] reward_normalization: mean={r_mean:.4f} std={r_std:.4f}",
                    flush=True,
                )
            else:
                print(
                    f"[dataset] reward_normalization: skipped (std={r_std:.2e} too small)",
                    flush=True,
                )

        uses_raw_features = bool(bulk.get("uses_raw_features", False))
        print(
            f"[dataset] loaded {n_out} transitions "
            f"(state_dim={state_dim}, action_dim={action_dim}, "
            f"uses_raw_features={uses_raw_features})",
            flush=True,
        )

        return {
            "states": torch.from_numpy(out_states),
            "actions": torch.from_numpy(out_actions),
            "rewards": torch.from_numpy(out_rewards),
            "next_states": torch.from_numpy(out_next_states),
            "dones": torch.from_numpy(out_dones),
            "state_dim": state_dim,
            "action_dim": action_dim,
            "num_transitions": n_out,
            "game_ids": selected_games,
            "transitions_loaded": transitions_loaded,
            "reward_mode": reward_mode,
            "filter_timeout": filter_timeout,
            "normalize_rewards": normalize_rewards,
            "uses_raw_features": uses_raw_features,
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
