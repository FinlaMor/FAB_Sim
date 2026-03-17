"""End-to-end IQL with transformer state/action encoding for Talishar data.

Architecture:
    State  → FABTransformerEncoder → state_emb (d_model)
    Action → ActionEncoder         → action_emb (d_model)
    Q(s,a) = MLP(state_emb ‖ action_emb)  → scalar
    V(s)   = MLP(state_emb)                → scalar
    Actor(s) = MLP(state_emb)              → action_emb (d_model)

The transformer and all IQL heads train end-to-end.

Usage:
    config = TransformerIQLConfig()
    trainer = TransformerIQLTrainer(config, attr_table)
    trainer.fit(dataset, num_steps=50_000)
    trainer.save_checkpoint("checkpoints/iql_v1.pt")
"""
from __future__ import annotations

import signal
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import h5py
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset

from rl_agents.fab_transformer import (
    CARD_ATTR_DIM,
    MAX_TOTAL_CARDS,
    META_DIM,
    ActionEncoder,
    FABTransformerConfig,
    FABTransformerEncoder,
)


# ── Device resolution ─────────────────────────────────────────────────


def _resolve_device(device_str: str):
    normalized = (device_str or "cpu").strip().lower()
    if normalized in ("dml", "directml"):
        try:
            import torch_directml
            return torch_directml.device()
        except ImportError as exc:
            raise RuntimeError(
                "torch-directml not installed"
            ) from exc
    if normalized == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda")
        try:
            import torch_directml
            return torch_directml.device()
        except ImportError:
            pass
        return torch.device("cpu")
    return torch.device(device_str)


# ── IQL Networks ──────────────────────────────────────────────────────


def _build_mlp(in_dim: int, out_dim: int, hidden_dim: int, layers: int) -> nn.Module:
    if layers <= 0:
        return nn.Linear(in_dim, out_dim)
    parts: list[nn.Module] = []
    prev = in_dim
    for _ in range(layers):
        parts.extend([nn.Linear(prev, hidden_dim), nn.ReLU()])
        prev = hidden_dim
    parts.append(nn.Linear(prev, out_dim))
    return nn.Sequential(*parts)


def expectile_loss(diff: torch.Tensor, expectile: float) -> torch.Tensor:
    weight = torch.where(diff > 0, expectile, 1.0 - expectile)
    return weight * diff.pow(2)


# ── Config ────────────────────────────────────────────────────────────


@dataclass
class TransformerIQLConfig:
    # Transformer
    d_model: int = 128
    num_heads: int = 4
    num_layers: int = 3
    ff_dim: int = 256
    transformer_dropout: float = 0.1
    slug_vocab_size: int = 4563
    # IQL heads
    hidden_dim: int = 256
    hidden_layers: int = 2
    gamma: float = 0.99
    expectile: float = 0.7
    temperature: float = 3.0
    max_weight: float = 100.0
    normalize_advantages: bool = True
    # Training
    batch_size: int = 256
    lr_encoder: float = 1e-4
    lr_q: float = 3e-4
    lr_v: float = 3e-4
    lr_actor: float = 3e-4
    weight_decay: float = 0.0
    grad_clip: float = 10.0
    reward_scale: float = 1.0
    tau: float = 0.005
    device: str = "auto"


# ── Dataset ───────────────────────────────────────────────────────────


class TalisharHDF5Dataset(Dataset):
    """Memory-mapped HDF5 dataset for preprocessed Talishar transitions.

    Expected HDF5 datasets:
        state_card_ids:      (N, MAX_TOTAL_CARDS) int16
        state_card_zones:    (N, MAX_TOTAL_CARDS) int8
        state_card_mask:     (N, MAX_TOTAL_CARDS) bool
        state_meta:          (N, META_DIM) float32
        state_turn_phase:    (N,) int8
        state_decision_type: (N,) int8
        next_state_card_ids, next_state_card_zones, etc.  (same shapes)
        action_card_id:      (N,) int16
        action_mode_id:      (N,) int8
        reward:              (N,) float32
        done:                (N,) bool
    """

    def __init__(self, path: str, expected_vocab_size: int | None = None):
        self.path = path
        self._file = h5py.File(path, "r")
        self._n = self._file["reward"].shape[0]

        # Validate vocab size matches what was used during preprocessing
        if expected_vocab_size is not None and "vocab_size" in self._file.attrs:
            stored = int(self._file.attrs["vocab_size"])
            if stored != expected_vocab_size:
                raise ValueError(
                    f"HDF5 was built with vocab_size={stored} but model expects "
                    f"{expected_vocab_size}. Regenerate the HDF5 cache."
                )

    def __len__(self) -> int:
        return self._n

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        f = self._file
        return {
            # State
            "s_card_ids": torch.tensor(f["state_card_ids"][idx], dtype=torch.long),
            "s_card_zones": torch.tensor(f["state_card_zones"][idx], dtype=torch.long),
            "s_card_mask": torch.tensor(f["state_card_mask"][idx], dtype=torch.bool),
            "s_meta": torch.tensor(f["state_meta"][idx], dtype=torch.float32),
            "s_phase": torch.tensor(f["state_turn_phase"][idx], dtype=torch.long),
            "s_decision": torch.tensor(f["state_decision_type"][idx], dtype=torch.long),
            # Next state
            "ns_card_ids": torch.tensor(f["next_state_card_ids"][idx], dtype=torch.long),
            "ns_card_zones": torch.tensor(f["next_state_card_zones"][idx], dtype=torch.long),
            "ns_card_mask": torch.tensor(f["next_state_card_mask"][idx], dtype=torch.bool),
            "ns_meta": torch.tensor(f["next_state_meta"][idx], dtype=torch.float32),
            "ns_phase": torch.tensor(f["next_state_turn_phase"][idx], dtype=torch.long),
            "ns_decision": torch.tensor(f["next_state_decision_type"][idx], dtype=torch.long),
            # Action
            "a_card_id": torch.tensor(f["action_card_id"][idx], dtype=torch.long),
            "a_mode_id": torch.tensor(f["action_mode_id"][idx], dtype=torch.long),
            # Reward / done
            "reward": torch.tensor(f["reward"][idx], dtype=torch.float32),
            "done": torch.tensor(f["done"][idx], dtype=torch.float32),
        }

    def close(self):
        self._file.close()


# ── Model ─────────────────────────────────────────────────────────────


class TransformerIQL(nn.Module):
    """End-to-end IQL with transformer state encoder and action encoder."""

    def __init__(self, config: TransformerIQLConfig, attr_table: torch.Tensor):
        super().__init__()
        self.config = config

        tx_config = FABTransformerConfig(
            d_model=config.d_model,
            num_heads=config.num_heads,
            num_layers=config.num_layers,
            ff_dim=config.ff_dim,
            dropout=config.transformer_dropout,
            slug_vocab_size=config.slug_vocab_size,
        )

        self.state_encoder = FABTransformerEncoder(tx_config, attr_table=attr_table)
        self.action_encoder = ActionEncoder(
            tx_config, slug_embed=self.state_encoder.slug_embed,
        )

        d = config.d_model

        # IQL heads
        self.q1 = _build_mlp(d * 2, 1, config.hidden_dim, config.hidden_layers)
        self.q2 = _build_mlp(d * 2, 1, config.hidden_dim, config.hidden_layers)
        self.value = _build_mlp(d, 1, config.hidden_dim, config.hidden_layers)
        self.value_target = _build_mlp(d, 1, config.hidden_dim, config.hidden_layers)
        self.actor = _build_mlp(d, d, config.hidden_dim, config.hidden_layers)

        # Copy value → target, freeze target
        self.value_target.load_state_dict(self.value.state_dict())
        self.value_target.requires_grad_(False)

    def encode_state(
        self,
        card_ids: torch.Tensor,
        card_zones: torch.Tensor,
        card_mask: torch.Tensor,
        meta: torch.Tensor,
        turn_phase: torch.Tensor,
        decision_type: torch.Tensor,
    ) -> torch.Tensor:
        return self.state_encoder(card_ids, card_zones, card_mask, meta, turn_phase, decision_type)

    def encode_action(self, card_id: torch.Tensor, mode_id: torch.Tensor) -> torch.Tensor:
        return self.action_encoder(card_id, mode_id)

    def q_values(self, state_emb: torch.Tensor, action_emb: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        sa = torch.cat([state_emb, action_emb], dim=-1)
        return self.q1(sa).squeeze(-1), self.q2(sa).squeeze(-1)

    def state_value(self, state_emb: torch.Tensor) -> torch.Tensor:
        return self.value(state_emb).squeeze(-1)

    def target_value(self, state_emb: torch.Tensor) -> torch.Tensor:
        return self.value_target(state_emb).squeeze(-1)

    def predict_action(self, state_emb: torch.Tensor) -> torch.Tensor:
        return self.actor(state_emb)


# ── Trainer ───────────────────────────────────────────────────────────


class TransformerIQLTrainer:
    """Trains TransformerIQL end-to-end on HDF5 data."""

    def __init__(self, config: TransformerIQLConfig, attr_table: torch.Tensor):
        self.config = config
        self.device = _resolve_device(config.device)

        self.model = TransformerIQL(config, attr_table).to(self.device)

        # Optimizer groups: encoder gets lower LR than IQL heads
        encoder_params = (
            list(self.model.state_encoder.parameters())
            + list(self.model.action_encoder.parameters())
        )
        q_params = list(self.model.q1.parameters()) + list(self.model.q2.parameters())
        v_params = list(self.model.value.parameters())
        actor_params = list(self.model.actor.parameters())

        self.opt_encoder = torch.optim.AdamW(
            encoder_params, lr=config.lr_encoder, weight_decay=config.weight_decay,
        )
        self.opt_q = torch.optim.Adam(q_params, lr=config.lr_q, weight_decay=config.weight_decay)
        self.opt_v = torch.optim.Adam(v_params, lr=config.lr_v, weight_decay=config.weight_decay)
        self.opt_actor = torch.optim.Adam(actor_params, lr=config.lr_actor, weight_decay=config.weight_decay)

    def _encode_state_batch(self, batch: dict, prefix: str) -> torch.Tensor:
        return self.model.encode_state(
            batch[f"{prefix}_card_ids"].to(self.device),
            batch[f"{prefix}_card_zones"].to(self.device),
            batch[f"{prefix}_card_mask"].to(self.device),
            batch[f"{prefix}_meta"].to(self.device),
            batch[f"{prefix}_phase"].to(self.device),
            batch[f"{prefix}_decision"].to(self.device),
        )

    @torch.no_grad()
    def _update_target(self):
        tau = self.config.tau
        for p, pt in zip(self.model.value.parameters(), self.model.value_target.parameters()):
            pt.data.mul_(1 - tau).add_(p.data, alpha=tau)

    def train_batch(self, batch: dict[str, torch.Tensor]) -> dict[str, float]:
        cfg = self.config
        rewards = batch["reward"].to(self.device) * cfg.reward_scale
        dones = batch["done"].to(self.device)
        a_card = batch["a_card_id"].to(self.device)
        a_mode = batch["a_mode_id"].to(self.device)

        # ── Single forward pass through encoder (used by Q-loss + actor) ──
        state_emb = self._encode_state_batch(batch, "s")
        action_emb = self.model.encode_action(a_card, a_mode)
        with torch.no_grad():
            next_state_emb = self._encode_state_batch(batch, "ns")

        # ── Q-loss ──
        with torch.no_grad():
            v_next = self.model.target_value(next_state_emb)
            q_target = rewards + cfg.gamma * (1 - dones) * v_next

        q1, q2 = self.model.q_values(state_emb, action_emb)
        q_loss = F.mse_loss(q1, q_target) + F.mse_loss(q2, q_target)

        # ── Actor loss (advantage-weighted BC) ──
        # Compute advantage from detached Q/V (no gradient through heads)
        with torch.no_grad():
            state_emb_d = state_emb.detach()
            action_emb_d = action_emb.detach()
            q_min = torch.minimum(*self.model.q_values(state_emb_d, action_emb_d))
            v_now = self.model.state_value(state_emb_d)
            advantage = q_min - v_now
            if cfg.normalize_advantages:
                advantage = (advantage - advantage.mean()) / advantage.std().clamp_min(1e-6)
            weights = torch.exp(cfg.temperature * advantage).clamp(max=cfg.max_weight)

        # Actor predicts action embedding; gradients flow through encoder
        pred_action = self.model.predict_action(state_emb)
        bc_per_row = (pred_action - action_emb_d).pow(2).mean(dim=-1)
        actor_loss = (weights * bc_per_row).mean()

        # ── Combined backward: Q + actor both update encoder in one step ──
        total_loss = q_loss + actor_loss

        self.opt_encoder.zero_grad(set_to_none=True)
        self.opt_q.zero_grad(set_to_none=True)
        self.opt_actor.zero_grad(set_to_none=True)
        total_loss.backward()
        nn.utils.clip_grad_norm_(self.model.parameters(), cfg.grad_clip)
        self.opt_q.step()
        self.opt_actor.step()
        self.opt_encoder.step()

        # ── V-loss (expectile regression, detached encoder) ──
        with torch.no_grad():
            state_emb_v = state_emb.detach()
            action_emb_v = action_emb.detach()
            q_min_v = torch.minimum(*self.model.q_values(state_emb_v, action_emb_v))
        v_pred = self.model.state_value(state_emb_v)
        v_loss = expectile_loss(q_min_v - v_pred, cfg.expectile).mean()

        self.opt_v.zero_grad(set_to_none=True)
        v_loss.backward()
        nn.utils.clip_grad_norm_(self.model.value.parameters(), cfg.grad_clip)
        self.opt_v.step()

        self._update_target()

        return {
            "q_loss": q_loss.item(),
            "v_loss": v_loss.item(),
            "actor_loss": actor_loss.item(),
            "adv_mean": advantage.mean().item(),
            "adv_std": advantage.std().item(),
            "w_max": weights.max().item(),
        }

    def fit(
        self,
        dataset: TalisharHDF5Dataset,
        num_steps: int,
        log_every: int = 100,
    ) -> list[dict[str, float]]:
        loader = DataLoader(
            dataset,
            batch_size=self.config.batch_size,
            shuffle=True,
            drop_last=len(dataset) >= self.config.batch_size,
            num_workers=0,
            pin_memory=False,
        )

        print(
            f"[iql] fit_start steps={num_steps} batch={self.config.batch_size} "
            f"data={len(dataset)} device={self.device}",
            flush=True,
        )

        it = iter(loader)
        history: list[dict[str, float]] = []
        t0 = time.time()

        # Signal-flag approach: Ctrl+C sets flag even during C-extension calls
        _stop_flag = False
        _prev_handler = signal.getsignal(signal.SIGINT)

        def _on_sigint(signum, frame):
            nonlocal _stop_flag
            _stop_flag = True
            print("\n[iql] Ctrl+C received — stopping after current step...", flush=True)

        signal.signal(signal.SIGINT, _on_sigint)

        step = 0
        try:
            for step in range(1, num_steps + 1):
                if _stop_flag:
                    break

                try:
                    batch = next(it)
                except StopIteration:
                    it = iter(loader)
                    batch = next(it)

                metrics = self.train_batch(batch)

                if log_every > 0 and (step == 1 or step % log_every == 0 or step == num_steps):
                    metrics["step"] = step
                    metrics["elapsed"] = time.time() - t0
                    history.append(metrics)
                    print(
                        f"[iql] step={step:6d} "
                        f"q={metrics['q_loss']:.4f} v={metrics['v_loss']:.4f} "
                        f"actor={metrics['actor_loss']:.4f} "
                        f"adv={metrics['adv_mean']:.4f} w_max={metrics['w_max']:.1f}",
                        flush=True,
                    )
        except KeyboardInterrupt:
            pass
        finally:
            signal.signal(signal.SIGINT, _prev_handler)

        if _stop_flag or step < num_steps:
            print(f"[iql] Stopped at step {step}. Returning partial history.", flush=True)

        return history

    def save_checkpoint(self, path: str, extra: dict | None = None) -> None:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        torch.save({
            "config": asdict(self.config),
            "model_state_dict": self.model.state_dict(),
            "opt_encoder": self.opt_encoder.state_dict(),
            "opt_q": self.opt_q.state_dict(),
            "opt_v": self.opt_v.state_dict(),
            "opt_actor": self.opt_actor.state_dict(),
            "extra": extra or {},
        }, str(out))
        print(f"[iql] checkpoint saved → {out}")

    @classmethod
    def from_checkpoint(
        cls,
        path: str,
        attr_table: torch.Tensor,
        device: str | None = None,
    ) -> "TransformerIQLTrainer":
        payload = torch.load(path, map_location="cpu", weights_only=False)
        cfg = TransformerIQLConfig(**payload["config"])
        if device is not None:
            cfg.device = device
        trainer = cls(cfg, attr_table)
        trainer.model.load_state_dict(payload["model_state_dict"])
        trainer.opt_encoder.load_state_dict(payload["opt_encoder"])
        trainer.opt_q.load_state_dict(payload["opt_q"])
        trainer.opt_v.load_state_dict(payload["opt_v"])
        trainer.opt_actor.load_state_dict(payload["opt_actor"])
        return trainer
