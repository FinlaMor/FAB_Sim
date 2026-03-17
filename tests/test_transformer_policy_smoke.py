"""Smoke test for the ask_agent transformer policy model.

This test validates end-to-end wiring on a live game state:
- engine builds legal actions,
- transformer encodes state + options,
- policy head returns finite logits/value.
"""

from __future__ import annotations

import os
import random

import torch

from config import DECKS_DIR, SLUG_INDEX_PATH
from encoder.card_embedder import SlugVocab
from engine.actions import Action
from engine.card import CardDB
from engine.engine import new_game
from rl_agents.transformer_policy import AskAgentTransformer, TransformerPolicyConfig


class _CaptureFirstDecisionAgent:
    def __init__(self, model: AskAgentTransformer, seed: int):
        self.model = model
        self.rng = random.Random(seed)
        self.checked = False
        self.last_output = None

    def __call__(self, state, options, context=None):
        if isinstance(options, (list, tuple)) and options and isinstance(options[0], Action):
            if not self.checked:
                output = self.model(
                    state=state,
                    legal_actions=list(options),
                    perspective_player=state.priority_player,
                )

                expected_actions = min(len(options), self.model.config.max_actions)
                assert output.action_count == expected_actions
                assert output.logits.shape == (expected_actions,)
                assert output.token_count > 0
                assert output.token_count <= self.model.config.max_sequence_tokens
                assert torch.isfinite(output.logits).all()
                assert torch.isfinite(output.value)

                self.last_output = output
                self.checked = True

                # End early once we validate a real decision context.
                state.done = True

            return self.rng.choice(options)

        if isinstance(options, (list, tuple)) and options:
            return self.rng.choice(options)

        return options


def test_transformer_policy_smoke() -> None:
    card_db = CardDB(SLUG_INDEX_PATH)
    slug_vocab = SlugVocab.from_card_db(card_db)

    model = AskAgentTransformer(
        slug_vocab=slug_vocab,
        config=TransformerPolicyConfig(
            num_layers=2,
            ff_dim=256,
            max_public_cards_per_player=48,
            max_deck_tokens=48,
            max_actions=64,
        ),
    )
    model.eval()

    p1_agent = _CaptureFirstDecisionAgent(model, seed=101)
    p2_agent = _CaptureFirstDecisionAgent(model, seed=202)

    p1_deck = os.path.join(DECKS_DIR, "oscillio_constella_intelligence_CC_lite.txt")
    p2_deck = os.path.join(DECKS_DIR, "kayo_underhanded_cheat_CC_lite.txt")

    new_game(
        p1_deck_path=p1_deck,
        p2_deck_path=p2_deck,
        p1_agent=p1_agent,
        p2_agent=p2_agent,
        card_db=card_db,
        p1_seed=42,
        p2_seed=43,
    )

    assert p1_agent.checked or p2_agent.checked
    captured = p1_agent.last_output or p2_agent.last_output
    assert captured is not None
    assert captured.action_count >= 1
