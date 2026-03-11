"""Implicit Q-Learning (IQL) on pre-embedded FAB transitions.

This module trains directly on tensors of:
  (state_emb, action_emb, reward, next_state_emb, done)
where action_emb is the chosen action embedding from the behavior policy.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional
import time

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset

from rl_agents.dataset_adapter import ReplayDataset, build_iql_tensors_from_replay_db


def _build_mlp(input_dim: int, output_dim: int, hidden_dim: int, hidden_layers: int) -> nn.Module:
    if hidden_layers <= 0:
        return nn.Linear(input_dim, output_dim)

    layers: list[nn.Module] = []
    last = input_dim
    for _ in range(hidden_layers):
        layers.append(nn.Linear(last, hidden_dim))
        layers.append(nn.ReLU())
        last = hidden_dim
    layers.append(nn.Linear(last, output_dim))
    return nn.Sequential(*layers)


def expectile_loss(diff: torch.Tensor, expectile: float) -> torch.Tensor:
    """Expectile regression loss used by IQL value training.

    diff is typically (Q(s, a) - V(s)).
    """
    weight_high = torch.full_like(diff, expectile)
    weight_low = torch.full_like(diff, 1.0 - expectile)
    weight = torch.where(diff > 0, weight_high, weight_low)
    return weight * diff.pow(2)


@dataclass
class IQLConfig:
    state_dim: int
    action_dim: int
    hidden_dim: int = 512
    hidden_layers: int = 2
    gamma: float = 0.99
    expectile: float = 0.7
    temperature: float = 3.0
    max_weight: float = 100.0
    batch_size: int = 256
    lr_q: float = 3e-4
    lr_v: float = 3e-4
    lr_actor: float = 3e-4
    weight_decay: float = 0.0
    grad_clip: float = 10.0
    reward_scale: float = 1.0
    device: str = "cpu"


class ValueNetwork(nn.Module):
    def __init__(self, state_dim: int, hidden_dim: int, hidden_layers: int):
        super().__init__()
        self.net = _build_mlp(state_dim, 1, hidden_dim, hidden_layers)

    def forward(self, states: torch.Tensor) -> torch.Tensor:
        return self.net(states).squeeze(-1)


class QNetwork(nn.Module):
    def __init__(self, state_dim: int, action_dim: int, hidden_dim: int, hidden_layers: int):
        super().__init__()
        self.net = _build_mlp(state_dim + action_dim, 1, hidden_dim, hidden_layers)

    def forward(self, states: torch.Tensor, actions: torch.Tensor) -> torch.Tensor:
        x = torch.cat([states, actions], dim=-1)
        return self.net(x).squeeze(-1)


class ActorNetwork(nn.Module):
    def __init__(self, state_dim: int, action_dim: int, hidden_dim: int, hidden_layers: int):
        super().__init__()
        self.net = _build_mlp(state_dim, action_dim, hidden_dim, hidden_layers)

    def forward(self, states: torch.Tensor) -> torch.Tensor:
        return self.net(states)


class IQLTrainer:
    def __init__(self, config: IQLConfig):
        if not (0.0 < config.expectile < 1.0):
            raise ValueError("expectile must be in (0, 1)")
        if config.batch_size <= 0:
            raise ValueError("batch_size must be > 0")

        self.config = config
        self.device = torch.device(config.device)

        self.q1 = QNetwork(config.state_dim, config.action_dim, config.hidden_dim, config.hidden_layers).to(self.device)
        self.q2 = QNetwork(config.state_dim, config.action_dim, config.hidden_dim, config.hidden_layers).to(self.device)
        self.value = ValueNetwork(config.state_dim, config.hidden_dim, config.hidden_layers).to(self.device)
        self.actor = ActorNetwork(config.state_dim, config.action_dim, config.hidden_dim, config.hidden_layers).to(self.device)

        self.opt_q = torch.optim.Adam(
            list(self.q1.parameters()) + list(self.q2.parameters()),
            lr=config.lr_q,
            weight_decay=config.weight_decay,
        )
        self.opt_v = torch.optim.Adam(self.value.parameters(), lr=config.lr_v, weight_decay=config.weight_decay)
        self.opt_actor = torch.optim.Adam(self.actor.parameters(), lr=config.lr_actor, weight_decay=config.weight_decay)

    def train_batch(self, batch: tuple[torch.Tensor, ...]) -> dict[str, float]:
        states, actions, rewards, next_states, dones = batch
        states = states.to(self.device).float()
        actions = actions.to(self.device).float()
        rewards = rewards.to(self.device).float() * self.config.reward_scale
        next_states = next_states.to(self.device).float()
        dones = dones.to(self.device).float()

        with torch.no_grad():
            v_next = self.value(next_states)
            q_target = rewards + self.config.gamma * (1.0 - dones) * v_next

        q1_pred = self.q1(states, actions)
        q2_pred = self.q2(states, actions)
        q1_loss = F.mse_loss(q1_pred, q_target)
        q2_loss = F.mse_loss(q2_pred, q_target)
        q_loss = q1_loss + q2_loss

        self.opt_q.zero_grad(set_to_none=True)
        q_loss.backward()
        nn.utils.clip_grad_norm_(list(self.q1.parameters()) + list(self.q2.parameters()), self.config.grad_clip)
        self.opt_q.step()

        with torch.no_grad():
            q_min_for_value = torch.minimum(self.q1(states, actions), self.q2(states, actions))
        v_pred = self.value(states)
        v_loss = expectile_loss(q_min_for_value - v_pred, self.config.expectile).mean()

        self.opt_v.zero_grad(set_to_none=True)
        v_loss.backward()
        nn.utils.clip_grad_norm_(self.value.parameters(), self.config.grad_clip)
        self.opt_v.step()

        with torch.no_grad():
            q_min = torch.minimum(self.q1(states, actions), self.q2(states, actions))
            v_now = self.value(states)
            advantage = q_min - v_now
            weights = torch.exp(self.config.temperature * advantage).clamp(max=self.config.max_weight)

        pred_actions = self.actor(states)
        bc_per_row = (pred_actions - actions).pow(2).mean(dim=-1)
        actor_loss = (weights * bc_per_row).mean()

        self.opt_actor.zero_grad(set_to_none=True)
        actor_loss.backward()
        nn.utils.clip_grad_norm_(self.actor.parameters(), self.config.grad_clip)
        self.opt_actor.step()

        return {
            "q_loss": float(q_loss.item()),
            "q1_loss": float(q1_loss.item()),
            "q2_loss": float(q2_loss.item()),
            "v_loss": float(v_loss.item()),
            "actor_loss": float(actor_loss.item()),
            "adv_mean": float(advantage.mean().item()),
            "adv_std": float(advantage.std().item()),
            "weight_mean": float(weights.mean().item()),
            "weight_max": float(weights.max().item()),
        }

    def fit(self, dataset: ReplayDataset, num_steps: int, log_every: int = 100) -> list[dict[str, float]]:
        tensor_ds = TensorDataset(
            dataset.states,
            dataset.actions,
            dataset.rewards,
            dataset.next_states,
            dataset.dones,
        )
        drop_last = len(tensor_ds) >= self.config.batch_size
        loader = DataLoader(
            tensor_ds,
            batch_size=self.config.batch_size,
            shuffle=True,
            drop_last=drop_last,
        )

        if len(loader) == 0:
            raise ValueError("Dataset is empty after DataLoader construction")

        it = iter(loader)
        history: list[dict[str, float]] = []
        t0 = time.time()

        for step in range(1, num_steps + 1):
            try:
                batch = next(it)
            except StopIteration:
                it = iter(loader)
                batch = next(it)

            metrics = self.train_batch(batch)
            metrics["step"] = float(step)
            metrics["elapsed_seconds"] = float(time.time() - t0)
            history.append(metrics)

            if log_every > 0 and (step == 1 or step % log_every == 0 or step == num_steps):
                print(
                    f"[iql] step={step:6d} "
                    f"q={metrics['q_loss']:.4f} "
                    f"v={metrics['v_loss']:.4f} "
                    f"actor={metrics['actor_loss']:.4f} "
                    f"adv={metrics['adv_mean']:.4f} "
                    f"w_max={metrics['weight_max']:.2f}"
                )

        return history

    def checkpoint_payload(self, extra: Optional[dict] = None) -> dict:
        return {
            "config": asdict(self.config),
            "q1_state_dict": self.q1.state_dict(),
            "q2_state_dict": self.q2.state_dict(),
            "value_state_dict": self.value.state_dict(),
            "actor_state_dict": self.actor.state_dict(),
            "opt_q_state_dict": self.opt_q.state_dict(),
            "opt_v_state_dict": self.opt_v.state_dict(),
            "opt_actor_state_dict": self.opt_actor.state_dict(),
            "extra": extra or {},
        }

    def save_checkpoint(self, path: str, extra: Optional[dict] = None) -> None:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        torch.save(self.checkpoint_payload(extra=extra), str(out))

    @classmethod
    def from_checkpoint(cls, path: str, device: Optional[str] = None) -> "IQLTrainer":
        payload = torch.load(path, map_location="cpu", weights_only=False)
        cfg = IQLConfig(**payload["config"])
        if device is not None:
            cfg.device = device

        trainer = cls(cfg)
        trainer.q1.load_state_dict(payload["q1_state_dict"])
        trainer.q2.load_state_dict(payload["q2_state_dict"])
        trainer.value.load_state_dict(payload["value_state_dict"])
        trainer.actor.load_state_dict(payload["actor_state_dict"])
        trainer.opt_q.load_state_dict(payload["opt_q_state_dict"])
        trainer.opt_v.load_state_dict(payload["opt_v_state_dict"])
        trainer.opt_actor.load_state_dict(payload["opt_actor_state_dict"])
        return trainer


def dataset_from_replay_db(
    db_path: str,
    game_ids: Optional[list[int]] = None,
    next_state_same_player: bool = True,
) -> tuple[ReplayDataset, dict]:
    payload = build_iql_tensors_from_replay_db(
        db_path=db_path,
        game_ids=game_ids,
        next_state_same_player=next_state_same_player,
    )
    dataset = ReplayDataset.from_tensor_dict(payload)
    return dataset, payload
