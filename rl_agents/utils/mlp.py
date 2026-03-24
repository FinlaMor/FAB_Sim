"""rl_agents/utils/mlp.py — Shared neural network building blocks.

Consolidates _build_mlp() and expectile_loss() from iql.py and talishar_iql.py.
"""
from __future__ import annotations

import torch
import torch.nn as nn


def build_mlp(input_dim: int, output_dim: int, hidden_dim: int, hidden_layers: int) -> nn.Module:
    """Build a simple MLP with ReLU activations.

    Args:
        input_dim: Input feature dimension.
        output_dim: Output feature dimension.
        hidden_dim: Width of each hidden layer.
        hidden_layers: Number of hidden layers. If 0, returns a single Linear.
    """
    if hidden_layers <= 0:
        return nn.Linear(input_dim, output_dim)
    layers: list[nn.Module] = []
    prev = input_dim
    for _ in range(hidden_layers):
        layers.extend([nn.Linear(prev, hidden_dim), nn.ReLU()])
        prev = hidden_dim
    layers.append(nn.Linear(prev, output_dim))
    return nn.Sequential(*layers)


def expectile_loss(diff: torch.Tensor, expectile: float) -> torch.Tensor:
    """Expectile regression loss used by IQL value training.

    Args:
        diff: Typically (Q(s, a) - V(s)).
        expectile: Asymmetric weight parameter in (0, 1).
    """
    weight = torch.where(diff > 0, expectile, 1.0 - expectile)
    return weight * diff.pow(2)
