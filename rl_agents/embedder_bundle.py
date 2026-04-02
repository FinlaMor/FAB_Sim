from __future__ import annotations

from pathlib import Path
from typing import Optional

import torch


BUNDLE_FILENAME = "embedder_bundle.pt"


def build_embedder_bundle(
    action_embedder,
    state_embedder,
    game_transformer=None,
) -> dict:
    # Schema fingerprint for compatibility validation (P2-14)
    slug_vocab_size = int(getattr(action_embedder, "slug_vocab_size", 0))

    # Extract shared CardEmbedder weights once to avoid duplication (P2-15)
    shared_card_embedder = getattr(action_embedder, "card_embedder", None)
    card_embedder_state_dict = shared_card_embedder.state_dict() if shared_card_embedder else {}

    # Filter out shared card_embedder keys to avoid triplication
    action_sd = {k: v for k, v in action_embedder.state_dict().items()
                 if not k.startswith("card_embedder.")}
    state_sd = {k: v for k, v in state_embedder.state_dict().items()
                if not k.startswith("card_embedder.")}

    # When a game_transformer is provided it becomes the active state embedder.
    # Report its output dim as state_output_dim so IQL dimension validation passes.
    if game_transformer is not None:
        active_state_output_dim = int(game_transformer.get_output_dim())
    else:
        active_state_output_dim = int(state_embedder.get_output_dim())

    bundle = {
        "d_model": int(getattr(action_embedder, "d_model", 128)),
        "action_output_dim": int(action_embedder.get_output_dim()),
        "state_output_dim": active_state_output_dim,
        "slug_vocab_size": slug_vocab_size,
        "card_embedder_state_dict": card_embedder_state_dict,
        "action_embedder_state_dict": action_sd,
        "state_embedder_state_dict": state_sd,
    }

    if game_transformer is not None:
        bundle["game_transformer_state_dict"] = game_transformer.state_dict()
        bundle["game_transformer_d_model"] = int(game_transformer.d_model)
        bundle["game_transformer_n_heads"] = int(game_transformer.n_heads)
        bundle["game_transformer_n_layers"] = int(game_transformer.n_layers)
        bundle["game_transformer_hero_head_dim"] = int(game_transformer.hero_head_dim)
        bundle["game_transformer_output_dim"] = int(game_transformer.get_output_dim())
        # Indicate whether card_feats_lookup was populated before saving.
        # card_feats_lookup is a register_buffer so it is included in state_dict() automatically.
        # This flag tells consumers whether the lookup table is non-zero.
        card_feats = getattr(game_transformer, "card_feats_lookup", None)
        bundle["game_transformer_card_feats_populated"] = (
            card_feats is not None and bool(card_feats.abs().sum().item() > 0)
        )

    return bundle


def save_embedder_bundle(
    path: str | Path,
    action_embedder,
    state_embedder,
    game_transformer=None,
) -> Path:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        build_embedder_bundle(action_embedder, state_embedder, game_transformer),
        str(out_path),
    )
    return out_path


def load_embedder_bundle(path: str | Path) -> dict:
    # Only load embedder bundles from trusted sources (P3-7)
    return torch.load(Path(path), map_location="cpu", weights_only=False)


def resolve_embedder_bundle_path(
    explicit_path: str = "",
    db_path: str = "",
    dataset_pt: str = "",
) -> Optional[Path]:
    candidates: list[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path))
    if db_path:
        candidates.append(Path(db_path).parent / BUNDLE_FILENAME)
    if dataset_pt:
        candidates.append(Path(dataset_pt).parent / BUNDLE_FILENAME)

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None
