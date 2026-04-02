"""rl_agents/utils/device.py — Shared device resolution for all training scripts.

Consolidates _resolve_device() from iql.py, talishar_iql.py, train_iql.py,
evaluate_iql_vs_random.py and _default_device() from train_iql.py,
train_transformer_iql.py, evaluate_iql_vs_random.py.
"""
from __future__ import annotations

import torch
import warnings


def resolve_device(device_str: str) -> torch.device:
    """Resolve device string including 'dml'/'directml'/'auto' for AMD GPU on Windows.

    Supports:
        "cpu"       → torch.device("cpu")
        "cuda"      → torch.device("cuda")
        "dml"/"directml" → torch_directml.device()
        "auto"      → best available (CUDA → DML → CPU)
    """
    normalized = (device_str or "cpu").strip().lower()
    if normalized in ("dml", "directml"):
        try:
            import torch_directml
            return torch_directml.device()
        except ImportError:
            warnings.warn(
                "Requested device 'dml', but torch-directml is not installed; falling back to CPU.",
                RuntimeWarning,
                stacklevel=2,
            )
            return torch.device("cpu")
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


def default_device() -> str:
    """Return best available device string (CUDA first, then DML, then CPU)."""
    if torch.cuda.is_available():
        return "cuda"
    try:
        import torch_directml  # noqa: F401
        return "dml"
    except ImportError:
        return "cpu"
