"""IQL Decode Agent — bridges offline IQL training to online legal-action selection.

Addresses P1-9 (training-inference architecture gap) and P1-11 (no IQL inference decode).

The IQL actor produces an action embedding vector given a state embedding.
This module provides the missing inference path:
    1. Embed the current GameState using gamestate_embedder.
    2. Pass the state embedding through the trained IQL actor to get a predicted action embedding.
    3. Embed each legal action using action_embedder.
    4. Select the legal action whose embedding is nearest to the actor's prediction.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Sequence

import torch
import torch.nn.functional as F

logger = logging.getLogger(__name__)

from engine.actions import Action
from engine.card import CardDB
from engine.state import GameState
from encoder.action_embedder import ActionEmbedder
from encoder.card_embedder import SlugVocab
from encoder.gamestate_embedder import GameStateEmbedder
from rl_agents.iql import IQLTrainer, IQLConfig
from rl_agents.embedder_bundle import load_embedder_bundle


class IQLDecodeAgent:
    """Selects legal actions at inference time using a trained IQL actor.

    Usage:
        agent = IQLDecodeAgent.from_checkpoint("checkpoints/iql_best.pt", card_db=card_db)
        chosen_action = agent.select_action(game_state, legal_actions, perspective_player=1)
    """

    def __init__(
        self,
        trainer: IQLTrainer,
        state_embedder: GameStateEmbedder,
        action_embedder: ActionEmbedder,
        card_db: Optional[CardDB] = None,
        similarity: str = "cosine",  # "cosine" or "l2"
    ):
        self.trainer = trainer
        self.state_embedder = state_embedder
        self.action_embedder = action_embedder
        self.card_db = card_db
        self.similarity = similarity
        self.device = trainer.device

    @classmethod
    def from_checkpoint(
        cls,
        checkpoint_path: str | Path,
        bundle_path: str | Path,
        card_db: Optional[CardDB] = None,
        device: str = "cpu",
        similarity: str = "cosine",
    ) -> "IQLDecodeAgent":
        """Load a trained IQL checkpoint and full embedder bundle for inference.

        Args:
            checkpoint_path: Path to IQL checkpoint (.pt) saved by IQLTrainer.save_checkpoint.
            bundle_path: Path to embedder_bundle.pt saved during data collection.
            card_db: Optional CardDB for richer action embeddings.
            device: Torch device string.
            similarity: "cosine" or "l2" for action matching.
        """
        trainer = IQLTrainer.from_checkpoint(str(checkpoint_path), device=device)
        trainer.actor.eval()
        trainer.state_adapter.eval()
        trainer.action_adapter.eval()

        bundle = load_embedder_bundle(bundle_path)
        slug_vocab_size = bundle.get("slug_vocab_size", 2000)
        d_model = bundle.get("d_model", 128)

        # (P2-7) Verify bundle dims match IQL checkpoint expectations
        bundle_state_dim = bundle.get("state_output_dim")
        bundle_action_dim = bundle.get("action_output_dim")
        if bundle_state_dim is not None and bundle_state_dim != trainer.config.state_dim:
            raise ValueError(
                f"Bundle state_output_dim ({bundle_state_dim}) != "
                f"IQL checkpoint state_dim ({trainer.config.state_dim}). "
                f"Rebuild the bundle or retrain IQL with matching dimensions."
            )
        if bundle_action_dim is not None and bundle_action_dim != trainer.config.action_dim:
            raise ValueError(
                f"Bundle action_output_dim ({bundle_action_dim}) != "
                f"IQL checkpoint action_dim ({trainer.config.action_dim}). "
                f"Rebuild the bundle or retrain IQL with matching dimensions."
            )

        slug_vocab = SlugVocab.from_card_db(card_db) if card_db is not None else None

        state_embedder = GameStateEmbedder(
            d_model=d_model,
            slug_vocab_size=slug_vocab_size,
            slug_vocab=slug_vocab,
        )
        action_embedder = ActionEmbedder(
            d_model=d_model,
            slug_vocab_size=slug_vocab_size,
            slug_vocab=slug_vocab,
        )

        state_sd = bundle.get("state_embedder_state_dict", {})
        action_sd = bundle.get("action_embedder_state_dict", {})
        card_sd = bundle.get("card_embedder_state_dict", {})
        # Merge shared card_embedder weights back into each embedder
        card_prefixed = {f"card_embedder.{k}": v for k, v in card_sd.items()}
        if state_sd:
            result = state_embedder.load_state_dict({**card_prefixed, **state_sd}, strict=False)
            if result.missing_keys:
                logger.warning("state_embedder missing keys: %s", result.missing_keys)
            if result.unexpected_keys:
                logger.warning("state_embedder unexpected keys: %s", result.unexpected_keys)
        if action_sd:
            result = action_embedder.load_state_dict({**card_prefixed, **action_sd}, strict=False)
            if result.missing_keys:
                logger.warning("action_embedder missing keys: %s", result.missing_keys)
            if result.unexpected_keys:
                logger.warning("action_embedder unexpected keys: %s", result.unexpected_keys)

        state_embedder.eval()
        action_embedder.eval()

        return cls(
            trainer=trainer,
            state_embedder=state_embedder,
            action_embedder=action_embedder,
            card_db=card_db,
            similarity=similarity,
        )

    @torch.no_grad()
    def _embed_state(self, state: GameState, perspective_player: int) -> torch.Tensor:
        """Embed a GameState into the IQL state space."""
        state_vec = self.state_embedder(state, perspective_player)
        if isinstance(state_vec, torch.Tensor):
            state_vec = state_vec.to(self.device).unsqueeze(0)
        else:
            state_vec = torch.tensor(state_vec, dtype=torch.float32, device=self.device).unsqueeze(0)
        return self.trainer.encode_states(state_vec).squeeze(0)

    @torch.no_grad()
    def _embed_action(self, action: Action, player_counters: Optional[dict] = None) -> torch.Tensor:
        """Embed an Action into the IQL action space."""
        action_vec = self.action_embedder(action, player_counters=player_counters)
        if isinstance(action_vec, torch.Tensor):
            action_vec = action_vec.to(self.device).unsqueeze(0)
        else:
            action_vec = torch.tensor(action_vec, dtype=torch.float32, device=self.device).unsqueeze(0)
        return self.trainer.encode_actions(action_vec).squeeze(0)

    @torch.no_grad()
    def select_action(
        self,
        state: GameState,
        legal_actions: Sequence[Action],
        perspective_player: int,
    ) -> Action:
        """Select the best legal action using the trained IQL actor.

        Returns the legal action whose embedding is nearest to the actor's
        predicted action embedding vector.
        """
        if not legal_actions:
            raise ValueError("No legal actions to select from")
        if len(legal_actions) == 1:
            return legal_actions[0]

        # 1. Embed current state
        state_emb = self._embed_state(state, perspective_player)

        # 2. Actor predicts ideal action embedding
        predicted_action_emb = self.trainer.actor(state_emb.unsqueeze(0)).squeeze(0)

        # 3. Embed all legal actions
        player = state.players.get(perspective_player)
        counters = player.counters if player else None
        action_embs = torch.stack([
            self._embed_action(action, player_counters=counters)
            for action in legal_actions
        ])

        # 4. Find nearest legal action
        if self.similarity == "cosine":
            predicted_norm = F.normalize(predicted_action_emb.unsqueeze(0), dim=-1)
            action_norms = F.normalize(action_embs, dim=-1)
            scores = torch.mm(predicted_norm, action_norms.t()).squeeze(0)
            best_idx = scores.argmax().item()
        else:  # l2
            dists = torch.cdist(predicted_action_emb.unsqueeze(0), action_embs).squeeze(0)
            best_idx = dists.argmin().item()

        return legal_actions[best_idx]

    @torch.no_grad()
    def action_scores(
        self,
        state: GameState,
        legal_actions: Sequence[Action],
        perspective_player: int,
    ) -> list[tuple[Action, float]]:
        """Return all legal actions with their similarity scores, sorted best-first."""
        if not legal_actions:
            return []

        state_emb = self._embed_state(state, perspective_player)
        predicted_action_emb = self.trainer.actor(state_emb.unsqueeze(0)).squeeze(0)

        player = state.players.get(perspective_player)
        counters = player.counters if player else None
        action_embs = torch.stack([
            self._embed_action(action, player_counters=counters)
            for action in legal_actions
        ])

        if self.similarity == "cosine":
            predicted_norm = F.normalize(predicted_action_emb.unsqueeze(0), dim=-1)
            action_norms = F.normalize(action_embs, dim=-1)
            scores = torch.mm(predicted_norm, action_norms.t()).squeeze(0)
        else:
            scores = -torch.cdist(predicted_action_emb.unsqueeze(0), action_embs).squeeze(0)

        scored = [(legal_actions[i], scores[i].item()) for i in range(len(legal_actions))]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored
