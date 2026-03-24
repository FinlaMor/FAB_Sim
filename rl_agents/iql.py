"""Implicit Q-Learning (IQL) on pre-embedded FAB transitions.

This module trains directly on tensors of:
  (state_emb, action_emb, reward, next_state_emb, done)
where action_emb is the chosen action embedding from the behavior policy.
"""

from __future__ import annotations

import signal
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional
import time

import math

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.optim.lr_scheduler import LambdaLR
from torch.utils.data import DataLoader, TensorDataset

from rl_agents.dataset_adapter import ReplayDataset, build_iql_tensors_from_replay_db
from rl_agents.utils.device import resolve_device as _resolve_device
from rl_agents.utils.mlp import build_mlp as _build_mlp, expectile_loss


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
    tau: float = 0.005
    normalize_advantages: bool = True
    rwbc_mode: bool = False
    trainable_embedder: bool = False
    embedder_hidden_dim: int = 512
    embedder_layers: int = 2
    lr_embedder: float = 1e-4
    lr_schedule: str = "constant"
    lr_warmup_steps: int = 0


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


class ResidualAdapter(nn.Module):
    """Residual MLP adapter over pre-computed embeddings.

    When disabled, this is a strict identity map with no parameters.
    """

    def __init__(
        self,
        input_dim: int,
        hidden_dim: int,
        hidden_layers: int,
        enabled: bool,
    ):
        super().__init__()
        self.enabled = bool(enabled)

        if not self.enabled:
            self.net = nn.Identity()
            return

        if hidden_layers <= 0 or hidden_dim <= 0:
            out = nn.Linear(input_dim, input_dim)
            nn.init.zeros_(out.weight)
            nn.init.zeros_(out.bias)
            self.net = out
            return

        layers: list[nn.Module] = []
        last = input_dim
        for _ in range(hidden_layers):
            layers.append(nn.Linear(last, hidden_dim))
            layers.append(nn.ReLU())
            last = hidden_dim

        out = nn.Linear(last, input_dim)
        # Start near identity so enabling this mode does not shock training.
        nn.init.zeros_(out.weight)
        nn.init.zeros_(out.bias)
        layers.append(out)
        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if not self.enabled:
            return x
        return x + self.net(x)


class IQLTrainer:
    def __init__(self, config: IQLConfig):
        if not (0.0 < config.expectile < 1.0):
            raise ValueError("expectile must be in (0, 1)")
        if config.batch_size <= 0:
            raise ValueError("batch_size must be > 0")
        if config.trainable_embedder and config.lr_embedder <= 0:
            raise ValueError("lr_embedder must be > 0 when trainable_embedder is enabled")

        self.config = config
        self.device = _resolve_device(config.device)

        self.q1 = QNetwork(config.state_dim, config.action_dim, config.hidden_dim, config.hidden_layers).to(self.device)
        self.q2 = QNetwork(config.state_dim, config.action_dim, config.hidden_dim, config.hidden_layers).to(self.device)
        self.value = ValueNetwork(config.state_dim, config.hidden_dim, config.hidden_layers).to(self.device)
        self.value_target = ValueNetwork(config.state_dim, config.hidden_dim, config.hidden_layers).to(self.device)
        self.value_target.load_state_dict(self.value.state_dict())
        self.value_target.requires_grad_(False)
        self.actor = ActorNetwork(config.state_dim, config.action_dim, config.hidden_dim, config.hidden_layers).to(self.device)

        self.state_adapter = ResidualAdapter(
            input_dim=config.state_dim,
            hidden_dim=config.embedder_hidden_dim,
            hidden_layers=config.embedder_layers,
            enabled=config.trainable_embedder,
        ).to(self.device)
        self.action_adapter = ResidualAdapter(
            input_dim=config.action_dim,
            hidden_dim=config.embedder_hidden_dim,
            hidden_layers=config.embedder_layers,
            enabled=config.trainable_embedder,
        ).to(self.device)
        self._embedder_params = list(self.state_adapter.parameters()) + list(self.action_adapter.parameters())

        self.opt_q = torch.optim.Adam(
            list(self.q1.parameters()) + list(self.q2.parameters()),
            lr=config.lr_q,
            weight_decay=config.weight_decay,
        )
        self.opt_v = torch.optim.Adam(self.value.parameters(), lr=config.lr_v, weight_decay=config.weight_decay)
        self.opt_actor = torch.optim.Adam(self.actor.parameters(), lr=config.lr_actor, weight_decay=config.weight_decay)
        self.opt_embed = (
            torch.optim.Adam(self._embedder_params, lr=config.lr_embedder, weight_decay=config.weight_decay)
            if self._embedder_params
            else None
        )

        self._schedulers: list[LambdaLR] = []

    def encode_states(self, states: torch.Tensor) -> torch.Tensor:
        return self.state_adapter(states)

    def encode_actions(self, actions: torch.Tensor) -> torch.Tensor:
        return self.action_adapter(actions)

    def _zero_embedder_grad(self) -> None:
        if self.opt_embed is not None:
            self.opt_embed.zero_grad(set_to_none=True)

    def _step_embedder(self) -> None:
        if self.opt_embed is not None:
            self.opt_embed.step()

    def _clip_embedder_grad(self) -> None:
        if self._embedder_params:
            nn.utils.clip_grad_norm_(self._embedder_params, self.config.grad_clip)

    def _build_schedulers(self, total_steps: int) -> None:
        """Create LR schedulers for all optimizers based on config."""
        schedule = self.config.lr_schedule
        warmup = self.config.lr_warmup_steps

        if schedule == "constant" and warmup <= 0:
            self._schedulers = []
            return

        def _lr_lambda(step: int) -> float:
            # Warmup phase
            if warmup > 0 and step < warmup:
                return (step + 1) / warmup
            # After warmup
            if schedule == "cosine":
                progress = (step - warmup) / max(1, total_steps - warmup)
                return 0.5 * (1.0 + math.cos(math.pi * progress))
            return 1.0

        opts = [self.opt_q, self.opt_v, self.opt_actor]
        if self.opt_embed is not None:
            opts.append(self.opt_embed)
        self._schedulers = [LambdaLR(opt, _lr_lambda) for opt in opts]

    def _step_schedulers(self) -> None:
        for sched in self._schedulers:
            sched.step()

    @torch.no_grad()
    def _update_targets(self) -> None:
        tau = self.config.tau
        for p, p_targ in zip(self.value.parameters(), self.value_target.parameters()):
            p_targ.data.mul_(1.0 - tau).add_(p.data, alpha=tau)

    def _actor_weights_from_advantage(self, advantage: torch.Tensor) -> torch.Tensor:
        if self.config.normalize_advantages:
            advantage = (advantage - advantage.mean()) / advantage.std().clamp_min(1e-6)
        return torch.exp(self.config.temperature * advantage).clamp(max=self.config.max_weight)

    def train_batch(self, batch: tuple[torch.Tensor, ...]) -> dict[str, float]:
        raw_states, raw_actions, rewards, raw_next_states, dones = batch
        raw_states = raw_states.to(self.device).float()
        raw_actions = raw_actions.to(self.device).float()
        rewards = rewards.to(self.device).float() * self.config.reward_scale
        raw_next_states = raw_next_states.to(self.device).float()
        dones = dones.to(self.device).float()

        if self.config.rwbc_mode:
            q_loss = torch.zeros((), device=self.device)
            q1_loss = torch.zeros((), device=self.device)
            q2_loss = torch.zeros((), device=self.device)
            v_loss = torch.zeros((), device=self.device)
            with torch.no_grad():
                advantage = rewards
                weights = self._actor_weights_from_advantage(advantage)
        else:
            # When trainable_embedder is enabled, let Q-network gradients also flow
            # through adapters to prevent representation collapse from actor-only signal (P2-16).
            if self.config.trainable_embedder:
                states = self.encode_states(raw_states)
                actions = self.encode_actions(raw_actions)
                next_states = self.encode_states(raw_next_states).detach()
            else:
                states = self.encode_states(raw_states).detach()
                actions = self.encode_actions(raw_actions).detach()
                next_states = self.encode_states(raw_next_states).detach()

            with torch.no_grad():
                v_next = self.value_target(next_states)
                q_target = rewards + self.config.gamma * (1.0 - dones) * v_next

            q1_pred = self.q1(states, actions)
            q2_pred = self.q2(states, actions)
            q1_loss = F.mse_loss(q1_pred, q_target)
            q2_loss = F.mse_loss(q2_pred, q_target)
            q_loss = q1_loss + q2_loss

            self.opt_q.zero_grad(set_to_none=True)
            if self.config.trainable_embedder:
                self._zero_embedder_grad()
            q_loss.backward()
            nn.utils.clip_grad_norm_(list(self.q1.parameters()) + list(self.q2.parameters()), self.config.grad_clip)
            if self.config.trainable_embedder:
                self._clip_embedder_grad()
            self.opt_q.step()
            if self.config.trainable_embedder:
                self._step_embedder()

            states = self.encode_states(raw_states).detach()
            actions = self.encode_actions(raw_actions).detach()
            with torch.no_grad():
                q_min_for_value = torch.minimum(self.q1(states, actions), self.q2(states, actions))
            v_pred = self.value(states)
            v_loss = expectile_loss(q_min_for_value - v_pred, self.config.expectile).mean()

            self.opt_v.zero_grad(set_to_none=True)
            v_loss.backward()
            nn.utils.clip_grad_norm_(self.value.parameters(), self.config.grad_clip)
            self.opt_v.step()

            with torch.no_grad():
                states = self.encode_states(raw_states)
                actions = self.encode_actions(raw_actions)
                q_min = torch.minimum(self.q1(states, actions), self.q2(states, actions))
                v_now = self.value(states)
                advantage = q_min - v_now
                weights = self._actor_weights_from_advantage(advantage)

        states = self.encode_states(raw_states)
        actions = self.encode_actions(raw_actions)
        pred_actions = self.actor(states)
        bc_per_row = (pred_actions - actions).pow(2).mean(dim=-1)
        actor_loss = (weights * bc_per_row).mean()

        self.opt_actor.zero_grad(set_to_none=True)
        self._zero_embedder_grad()
        actor_loss.backward()
        nn.utils.clip_grad_norm_(self.actor.parameters(), self.config.grad_clip)
        self._clip_embedder_grad()
        self.opt_actor.step()
        self._step_embedder()

        if not self.config.rwbc_mode:
            self._update_targets()

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

    @torch.no_grad()
    def _compute_eval_metrics(
        self,
        eval_s: torch.Tensor,
        eval_a: torch.Tensor,
        eval_r: torch.Tensor,
        eval_s2: torch.Tensor,
        eval_d: torch.Tensor,
    ) -> dict[str, float]:
        """Compute held-out eval losses for Q-overestimation detection (P2-7).

        In rwbc_mode Q/V networks are intentionally untrained, so Q/V metrics
        are omitted to avoid misleading diagnostic output.
        eval_bc_loss is unweighted MSE (not advantage-weighted like actor_loss).
        """
        # Put all sub-modules in eval mode for correctness with future BatchNorm/Dropout
        nets = [self.q1, self.q2, self.value, self.value_target, self.actor,
                self.state_adapter, self.action_adapter]
        for m in nets:
            m.eval()
        try:
            s = eval_s.to(self.device)
            a = eval_a.to(self.device)
            r = eval_r.to(self.device) * self.config.reward_scale
            s2 = eval_s2.to(self.device)
            d = eval_d.to(self.device)

            states = self.encode_states(s)
            actions = self.encode_actions(a)

            pred = self.actor(states)
            bc_loss = (pred - actions).pow(2).mean()
            result: dict[str, float] = {
                "eval_bc_loss": float(bc_loss.item()),
            }

            if not self.config.rwbc_mode:
                next_states = self.encode_states(s2)
                q1 = self.q1(states, actions)
                q2 = self.q2(states, actions)
                q_min = torch.minimum(q1, q2)
                v = self.value(states)
                v_next = self.value_target(next_states)

                target = r + self.config.gamma * (1.0 - d) * v_next
                q_loss = 0.5 * (F.mse_loss(q1, target) + F.mse_loss(q2, target))
                diff = q_min - v
                v_loss = expectile_loss(diff, self.config.expectile).mean()

                result["eval_q_loss"] = float(q_loss.item())
                result["eval_v_loss"] = float(v_loss.item())
                result["eval_q_mean"] = float(q_min.mean().item())
                result["eval_v_mean"] = float(v.mean().item())

        finally:
            for m in nets:
                m.train()

        return result

    def fit(
        self,
        dataset: ReplayDataset,
        num_steps: int,
        log_every: int = 100,
        eval_ratio: float = 0.1,
    ) -> list[dict[str, float]]:
        if eval_ratio < 0.0 or eval_ratio >= 1.0:
            raise ValueError(f"eval_ratio must be in [0.0, 1.0); got {eval_ratio}")

        n = len(dataset)

        # P2-7: hold out eval split for offline Q-overestimation detection.
        # Cap n_eval at 2048 here so no extra transitions are withheld from training.
        n_eval = min(max(1, int(n * eval_ratio)), 2048) if eval_ratio > 0 else 0
        eval_s = eval_a = eval_r = eval_s2 = eval_d = None
        if n_eval > 0 and n_eval < n:
            perm = torch.randperm(n, generator=torch.Generator().manual_seed(43))
            eval_idx = perm[:n_eval]
            train_idx = perm[n_eval:]
            eval_s = dataset.states[eval_idx]
            eval_a = dataset.actions[eval_idx]
            eval_r = dataset.rewards[eval_idx]
            eval_s2 = dataset.next_states[eval_idx]
            eval_d = dataset.dones[eval_idx]
            train_ds = TensorDataset(
                dataset.states[train_idx],
                dataset.actions[train_idx],
                dataset.rewards[train_idx],
                dataset.next_states[train_idx],
                dataset.dones[train_idx],
            )
            print(f"[iql] eval_split train={len(train_idx)} eval={n_eval}", flush=True)
        else:
            train_ds = TensorDataset(
                dataset.states,
                dataset.actions,
                dataset.rewards,
                dataset.next_states,
                dataset.dones,
            )

        drop_last = len(train_ds) >= self.config.batch_size
        use_pin_memory = self.device.type == "cuda"
        loader = DataLoader(
            train_ds,
            batch_size=self.config.batch_size,
            shuffle=True,
            drop_last=drop_last,
            pin_memory=use_pin_memory,
            generator=torch.Generator().manual_seed(42),
        )

        if len(loader) == 0:
            raise ValueError("Dataset is empty after DataLoader construction")

        print(
            f"[iql] fit_start steps={num_steps} batch_size={self.config.batch_size} "
            f"batches_per_epoch={len(loader)} device={self.device}",
            flush=True,
        )

        self._build_schedulers(num_steps)

        it = iter(loader)
        history: list[dict[str, float]] = []
        t0 = time.time()
        step = 0

        # Signal-flag approach: Ctrl+C sets flag even during C-extension calls
        _stop_flag = False
        _prev_handler = signal.getsignal(signal.SIGINT)

        def _on_sigint(signum, frame):
            nonlocal _stop_flag
            _stop_flag = True
            print("\n[iql] Ctrl+C received — stopping after current step...", flush=True)

        signal.signal(signal.SIGINT, _on_sigint)

        try:
            for step in range(1, num_steps + 1):
                if _stop_flag:
                    break

                try:
                    batch = next(it)
                except StopIteration:
                    it = iter(loader)
                    batch = next(it)

                should_log = log_every > 0 and (step == 1 or step % log_every == 0 or step == num_steps)

                if should_log:
                    metrics = self.train_batch(batch)
                    self._step_schedulers()
                    metrics["step"] = float(step)
                    metrics["elapsed_seconds"] = float(time.time() - t0)

                    if eval_s is not None:
                        eval_m = self._compute_eval_metrics(eval_s, eval_a, eval_r, eval_s2, eval_d)
                        metrics.update(eval_m)

                    history.append(metrics)

                    line = (
                        f"[iql] step={step:6d} "
                        f"q={metrics['q_loss']:.4f} "
                        f"v={metrics['v_loss']:.4f} "
                        f"actor={metrics['actor_loss']:.4f} "
                        f"adv={metrics['adv_mean']:.4f} "
                        f"w_max={metrics['weight_max']:.2f}"
                    )
                    if eval_s is not None:
                        bc = metrics.get('eval_bc_loss', float('nan'))
                        q_m = metrics.get('eval_q_mean', float('nan'))
                        q_l = metrics.get('eval_q_loss', float('nan'))
                        v_l = metrics.get('eval_v_loss', float('nan'))
                        line += f" | eval bc={bc:.4f} q={q_l:.4f} v={v_l:.4f} q_mean={q_m:.4f}"
                    print(line, flush=True)
                else:
                    self.train_batch(batch)
                    self._step_schedulers()
        except KeyboardInterrupt:
            pass
        finally:
            signal.signal(signal.SIGINT, _prev_handler)

        if _stop_flag or step < num_steps:
            print(f"[iql] Stopped at step {step}. Returning partial history.", flush=True)

        return history

    def checkpoint_payload(self, extra: Optional[dict] = None) -> dict:
        return {
            "config": asdict(self.config),
            "q1_state_dict": self.q1.state_dict(),
            "q2_state_dict": self.q2.state_dict(),
            "value_state_dict": self.value.state_dict(),
            "value_target_state_dict": self.value_target.state_dict(),
            "actor_state_dict": self.actor.state_dict(),
            "state_adapter_state_dict": self.state_adapter.state_dict(),
            "action_adapter_state_dict": self.action_adapter.state_dict(),
            "opt_q_state_dict": self.opt_q.state_dict(),
            "opt_v_state_dict": self.opt_v.state_dict(),
            "opt_actor_state_dict": self.opt_actor.state_dict(),
            "opt_embed_state_dict": self.opt_embed.state_dict() if self.opt_embed is not None else None,
            "extra": extra or {},
        }

    def save_checkpoint(self, path: str, extra: Optional[dict] = None) -> None:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        torch.save(self.checkpoint_payload(extra=extra), str(out))

    @classmethod
    def from_checkpoint(cls, path: str, device: Optional[str] = None) -> "IQLTrainer":
        # Only load checkpoints from trusted sources.
        payload = torch.load(path, map_location="cpu", weights_only=True)
        cfg = IQLConfig(**payload["config"])
        if device is not None:
            cfg.device = device

        trainer = cls(cfg)
        trainer.q1.load_state_dict(payload["q1_state_dict"])
        trainer.q2.load_state_dict(payload["q2_state_dict"])
        trainer.value.load_state_dict(payload["value_state_dict"])
        value_target_sd = payload.get("value_target_state_dict")
        if value_target_sd is not None:
            trainer.value_target.load_state_dict(value_target_sd)
        else:
            trainer.value_target.load_state_dict(payload["value_state_dict"])
        trainer.actor.load_state_dict(payload["actor_state_dict"])

        state_adapter_sd = payload.get("state_adapter_state_dict")
        action_adapter_sd = payload.get("action_adapter_state_dict")
        if state_adapter_sd is not None:
            trainer.state_adapter.load_state_dict(state_adapter_sd)
        if action_adapter_sd is not None:
            trainer.action_adapter.load_state_dict(action_adapter_sd)

        trainer.opt_q.load_state_dict(payload["opt_q_state_dict"])
        trainer.opt_v.load_state_dict(payload["opt_v_state_dict"])
        trainer.opt_actor.load_state_dict(payload["opt_actor_state_dict"])

        opt_embed_sd = payload.get("opt_embed_state_dict")
        if trainer.opt_embed is not None and opt_embed_sd is not None:
            trainer.opt_embed.load_state_dict(opt_embed_sd)
        return trainer


def dataset_from_replay_db(
    db_path: str,
    game_ids: Optional[list[int]] = None,
    next_state_same_player: bool = True,
    reward_mode: str = "terminal",
    gamma: float = 0.99,
) -> tuple[ReplayDataset, dict]:
    payload = build_iql_tensors_from_replay_db(
        db_path=db_path,
        game_ids=game_ids,
        next_state_same_player=next_state_same_player,
        reward_mode=reward_mode,
        gamma=gamma,
    )
    dataset = ReplayDataset.from_tensor_dict(payload)
    return dataset, payload
