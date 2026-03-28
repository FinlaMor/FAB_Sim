"""Core game simulation module for the training/evolution pipeline.

Provides:
- OpponentPool: manages a mix of agent types for self-play
- MatchupScheduler: ensures deck coverage across game batches
- EmbeddingRecorderAgent: wraps any agent to record embeddings to ReplayDB
- run_games(): orchestrates batch game execution
"""

from __future__ import annotations

import random
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import torch

from config import SLUG_INDEX_PATH
from data_collection.replay_db import ReplayDB
from engine.actions import Action, ActionType
from engine.card import CardDB
from engine.state import GameState
from encoder.action_embedder import ActionEmbedder
from encoder.card_embedder import SlugVocab
from encoder.gamestate_embedder import GameStateEmbedder, gamestate_to_features
from rl_agents.game_backends import GameRunRequest, LocalEngineBackend
from rl_agents.random_agent import RandomAgent
from rl_agents.utils.card_helpers import (
    card_slug as _card_slug,
    normalise_action_for_embedder as _normalise_action_for_embedder,
)


def _serialise_action(action: Action) -> dict:
    """Serialise an Action for replay DB storage."""
    defend_cards = [(_card_slug(c) or "") for c in (action.card_list or [])]
    defend_cards = [slug for slug in defend_cards if slug]

    return {
        "selected_action": {
            "type": action.type.value,
            "player_id": action.player_id,
            "card": {"slug": _card_slug(action.card)} if action.card is not None else None,
            "pitch_cards": [(_card_slug(c) or "") for c in (action.pitch_cards or [])],
            "defend_cards": defend_cards,
            "from_arsenal": bool(action.from_arsenal),
            "slot": action.slot,
            "target": _card_slug(action.target),
            "targets": list(action.targets) if action.targets else [],
            "modes_selected": list(action.modes_selected) if action.modes_selected else [],
            "meld_side": getattr(action, "meld_side", None),
            "resource_cost": action.resource_cost,
            "action_cost": action.action_cost,
            "has_go_again": action.has_go_again,
        }
    }


# ---------------------------------------------------------------------------
# GameResults
# ---------------------------------------------------------------------------

@dataclass
class GameResult:
    """Result of a single game."""
    winner: int | None  # 1 or 2, or None if draw/cap
    turn_number: int
    ended_on_turn_cap: bool
    p1_final_hp: int
    p2_final_hp: int
    p1_deck: str
    p2_deck: str
    error: str | None = None


@dataclass
class GameResults:
    """Aggregate results from a batch of games."""
    results: list[GameResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def completed(self) -> int:
        return sum(1 for r in self.results if r.error is None)

    @property
    def failed(self) -> int:
        return len(self.errors)


# ---------------------------------------------------------------------------
class LocalHeuristicAgent:
    """Simple heuristic agent for the local engine.

    Prefers attack actions over non-attacks, and non-pass actions over pass.
    Falls back to random choice among equally ranked options.
    """

    def __init__(self, seed: int = 0):
        self._rng = random.Random(seed)

    def __call__(self, state: GameState, options, context=None):
        if not options:
            return None
        if len(options) == 1:
            return options[0]

        # For Action choices, rank: attacks > non-pass > pass
        if isinstance(options[0], Action):
            attacks = [a for a in options if a.type in (
                ActionType.ATTACK_WEAPON, ActionType.PLAY_CARD,
            )]
            non_pass = [a for a in options if a.type != ActionType.PASS]
            if attacks:
                return self._rng.choice(attacks)
            if non_pass:
                return self._rng.choice(non_pass)
        return self._rng.choice(options)


# ---------------------------------------------------------------------------
# OpponentPool
# ---------------------------------------------------------------------------

class OpponentPool:
    """Manages a pool of agents for self-play matchups.

    Falls back to heuristic + random agents if no checkpoints are provided.
    """

    def __init__(
        self,
        heuristic_seed: int = 0,
        checkpoint_paths: list[str] | None = None,
        device: str = "cpu",
        embedder_bundle: dict | None = None,
    ):
        self._agents: list[dict[str, Any]] = []
        self._device = device
        self._embedder_bundle = embedder_bundle

        # Always include heuristic and random agents
        self._agents.append({
            "type": "heuristic",
            "seed": heuristic_seed,
        })
        self._agents.append({
            "type": "random",
            "seed": heuristic_seed + 1,
        })

        # Add IQL policy agents from checkpoints
        for cp_path in (checkpoint_paths or []):
            if Path(cp_path).exists():
                self._agents.append({
                    "type": "iql_policy",
                    "checkpoint_path": cp_path,
                })

    def sample_agent(self, rng: random.Random, player_id: int = 1, seed: int = 0) -> Any:
        """Return a random agent instance from the pool."""
        entry = rng.choice(self._agents)
        return self._build_agent(entry, player_id=player_id, seed=seed)

    def _build_agent(self, entry: dict, player_id: int, seed: int) -> Any:
        agent_type = entry["type"]
        if agent_type == "heuristic":
            return LocalHeuristicAgent(seed=seed)
        elif agent_type == "random":
            return RandomAgent(seed=seed)
        elif agent_type == "iql_policy":
            from rl_agents.evaluate_iql_vs_random import IQLPolicyAgent
            if self._embedder_bundle is None:
                raise ValueError("embedder_bundle required for IQL policy agents")
            return IQLPolicyAgent(
                checkpoint_path=entry["checkpoint_path"],
                player_id=player_id,
                device=self._device,
                seed=seed,
                embedder_bundle=self._embedder_bundle,
            )
        else:
            raise ValueError(f"Unknown agent type: {agent_type}")


# ---------------------------------------------------------------------------
# MatchupScheduler
# ---------------------------------------------------------------------------

class MatchupScheduler:
    """Ensures all validated decks appear at least once per batch."""

    def schedule_matchups(
        self,
        deck_paths: list[str],
        games_per_loop: int,
    ) -> list[tuple[str, str]]:
        """Return a list of (p1_deck, p2_deck) pairs.

        Algorithm:
        1. Shuffle decks, pair consecutively for round-robin coverage.
        2. Add random pairings to fill remaining games.
        3. Handle odd deck count by repeating the last deck.
        """
        if not deck_paths:
            return []

        shuffled = list(deck_paths)
        random.shuffle(shuffled)

        # Handle odd count: repeat last deck so we can pair evenly
        if len(shuffled) % 2 != 0:
            shuffled.append(shuffled[-1])

        # Round-robin coverage: pair consecutive decks
        pairs: list[tuple[str, str]] = []
        for i in range(0, len(shuffled), 2):
            pairs.append((shuffled[i], shuffled[i + 1]))

        # Fill remaining games with random pairings
        while len(pairs) < games_per_loop:
            d1 = random.choice(deck_paths)
            d2 = random.choice(deck_paths)
            pairs.append((d1, d2))

        # Trim to exact count
        return pairs[:games_per_loop]


# ---------------------------------------------------------------------------
# EmbeddingRecorderAgent
# ---------------------------------------------------------------------------

class EmbeddingRecorderAgent:
    """Wraps any base agent, recording state/action embeddings to ReplayDB.

    Follows the pattern from collect_iql_mixed_data.py's
    RandomEmbedderRecorderAgent.
    """

    def __init__(
        self,
        base_agent: Any,
        player_id: int,
        game_id: int,
        replay_db: ReplayDB,
        action_embedder: ActionEmbedder,
        state_embedder: GameStateEmbedder,
        step_counter: list[int] | None = None,
        max_decisions_per_game: int = 5000,
        combat_log: dict[int, list[dict]] | None = None,
    ):
        self.base_agent = base_agent
        self.player_id = player_id
        self.game_id = game_id
        self.replay_db = replay_db
        self.action_embedder = action_embedder
        self.state_embedder = state_embedder
        self.step_counter = step_counter if step_counter is not None else [0]
        self.max_decisions_per_game = max_decisions_per_game
        self.combat_log = combat_log if combat_log is not None else {}
        self._last_seen_chain_count: int = 0

    def __call__(self, state: GameState, options, context=None):
        if not isinstance(options, (list, tuple)) or not options:
            return options

        # Guardrail against pathological loops
        if self.step_counter[0] >= self.max_decisions_per_game:
            p1_hp = state.players[1].health
            p2_hp = state.players[2].health
            state.winner = 1 if p1_hp >= p2_hp else 2
            state.done = True
            if isinstance(options[0], Action):
                pass_action = next((a for a in options if a.type == ActionType.PASS), None)
                return pass_action if pass_action is not None else options[0]
            return options[0]

        # Delegate to base agent for the actual decision
        choice = self.base_agent(state, options, context)

        # Snapshot new chain_links into combat_log
        chain_links = getattr(state, "chain_links", []) or []
        if len(chain_links) > self._last_seen_chain_count:
            turn = getattr(state, "turn_number", 0)
            new_links = chain_links[self._last_seen_chain_count:]
            entry_list = self.combat_log.setdefault(turn, [])
            for link in new_links:
                entry_list.append({
                    "attacker_id": link.attacker_id,
                    "attack_power": link.attack_power,
                    "net_damage": link.net_damage,
                    "hit": link.hit,
                })
            self._last_seen_chain_count = len(chain_links)

        # Reset chain count tracking when turn advances (chain_links reset at turn start)
        if chain_links == [] and self._last_seen_chain_count > 0:
            self._last_seen_chain_count = 0

        # Record embeddings for Action decisions
        is_action_choice = isinstance(options[0], Action) and isinstance(choice, Action)
        if is_action_choice:
            with torch.no_grad():
                state_emb = self.state_embedder(
                    state, perspective_player=self.player_id,
                )
                action_for_embedder = _normalise_action_for_embedder(choice)
                action_emb = self.action_embedder(
                    action_for_embedder,
                    player_counters=state.players[self.player_id].counters,
                )

            phase = state.step.value if hasattr(state.step, "value") else str(state.step)
            chain_links_snapshot = [
                {
                    "attacker_id": link.attacker_id,
                    "attack_power": link.attack_power,
                    "net_damage": link.net_damage,
                    "hit": link.hit,
                }
                for link in chain_links
            ]
            obs = {
                "turn": state.turn_number,
                "step": phase,
                "active_player": state.active_player,
                "priority_player": state.priority_player,
                "state_debug": gamestate_to_features(state),
                "state_embedding_norm": float(torch.norm(state_emb).item()),
                "chain_links_snapshot": chain_links_snapshot,
                "p1_hp": state.players[1].health,
                "p2_hp": state.players[2].health,
            }
            action_json = _serialise_action(choice)

            row_id = self.replay_db.insert_transition(
                game_id=self.game_id,
                step_idx=self.step_counter[0],
                player_id=self.player_id,
                phase=phase,
                obs=obs,
                action=action_json,
            )
            self.replay_db.store_embeddings(row_id, state_emb, action_emb)
            self.step_counter[0] += 1

            if self.step_counter[0] % 50 == 0:
                self.replay_db.flush()

        return choice


# ---------------------------------------------------------------------------
# run_games
# ---------------------------------------------------------------------------

def _extract_hero_from_deck(deck_path: str) -> str:
    """Extract hero name from a deck file."""
    try:
        with open(deck_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line.startswith("Hero:"):
                    return line[5:].strip()
    except OSError:
        pass
    return "Unknown"


def _build_embedders(embedder_bundle: dict) -> tuple[ActionEmbedder, GameStateEmbedder]:
    """Build ActionEmbedder and GameStateEmbedder from a bundle dict."""
    card_db = CardDB(SLUG_INDEX_PATH)
    slug_vocab = SlugVocab.from_card_db(card_db)
    d_model = int(embedder_bundle.get("d_model", 128))

    action_embedder = ActionEmbedder(
        d_model=d_model,
        slug_vocab_size=slug_vocab.size,
        slug_vocab=slug_vocab,
    )
    state_embedder = GameStateEmbedder(
        d_model=d_model,
        slug_vocab_size=slug_vocab.size,
        slug_vocab=slug_vocab,
    )

    card_sd = embedder_bundle.get("card_embedder_state_dict", {})
    card_prefixed = {f"card_embedder.{k}": v for k, v in card_sd.items()}
    action_embedder.load_state_dict(
        {**card_prefixed, **embedder_bundle["action_embedder_state_dict"]},
        strict=False,
    )
    state_embedder.load_state_dict(
        {**card_prefixed, **embedder_bundle["state_embedder_state_dict"]},
        strict=False,
    )
    action_embedder.eval()
    state_embedder.eval()

    return action_embedder, state_embedder


def run_games(
    deck_pairs: list[tuple[str, str]],
    opponent_pool: OpponentPool,
    card_db: CardDB,
    replay_db: ReplayDB,
    game_data_store: Any | None,
    embedder_bundle: dict,
    max_turns: int = 200,
    seed: int = 0,
) -> GameResults:
    """Run a batch of games and record results.

    For each matchup:
    1. Sample agents from the opponent pool.
    2. Wrap with EmbeddingRecorderAgent for embedding collection.
    3. Run via LocalEngineBackend.run_game().
    4. Record results to ReplayDB (for IQL) and GameDataStore (for deck evaluator).
    5. Catch individual game errors without halting the batch.
    """
    rng = random.Random(seed)
    backend = LocalEngineBackend()
    action_embedder, state_embedder = _build_embedders(embedder_bundle)
    results = GameResults()

    for idx, (p1_deck, p2_deck) in enumerate(deck_pairs):
        game_seed = rng.randint(0, 2**31 - 1)
        try:
            # Extract hero names for replay DB
            p1_hero = _extract_hero_from_deck(p1_deck)
            p2_hero = _extract_hero_from_deck(p2_deck)
            game_id = replay_db.start_game(p1_hero, p2_hero)

            # Sample and wrap agents
            step_counter = [0]
            combat_log: dict[int, list[dict]] = {}
            base_p1 = opponent_pool.sample_agent(rng, player_id=1, seed=game_seed)
            base_p2 = opponent_pool.sample_agent(rng, player_id=2, seed=game_seed + 1)

            p1_agent = EmbeddingRecorderAgent(
                base_agent=base_p1,
                player_id=1,
                game_id=game_id,
                replay_db=replay_db,
                action_embedder=action_embedder,
                state_embedder=state_embedder,
                step_counter=step_counter,
                combat_log=combat_log,
            )
            p2_agent = EmbeddingRecorderAgent(
                base_agent=base_p2,
                player_id=2,
                game_id=game_id,
                replay_db=replay_db,
                action_embedder=action_embedder,
                state_embedder=state_embedder,
                step_counter=step_counter,
                combat_log=combat_log,
            )

            req = GameRunRequest(
                p1_deck=p1_deck,
                p2_deck=p2_deck,
                p1_agent=p1_agent,
                p2_agent=p2_agent,
                card_db=card_db,
                p1_seed=game_seed,
                p2_seed=game_seed + 1,
                max_turns=max_turns,
            )

            game_state = backend.run_game(req)

            winner = getattr(game_state, "winner", None)
            turn_number = getattr(game_state, "turn_number", 0)
            ended_on_cap = turn_number >= max_turns
            p1_hp = game_state.players[1].health if hasattr(game_state, "players") else 0
            p2_hp = game_state.players[2].health if hasattr(game_state, "players") else 0

            # Finalize in ReplayDB
            replay_db.finalize_game(game_id, winner, turn_number, ended_on_cap)
            replay_db.flush()

            # Record to GameDataStore if available
            if game_data_store is not None:
                try:
                    game_data_store.record_local_game(
                        collector=None,
                        game_state=game_state,
                        p1_deck_file=p1_deck,
                        p2_deck_file=p2_deck,
                        seed=game_seed,
                        game_id=game_id,
                    )
                except Exception:
                    pass  # Non-critical; replay DB is the primary store

            result = GameResult(
                winner=winner,
                turn_number=turn_number,
                ended_on_turn_cap=ended_on_cap,
                p1_final_hp=p1_hp,
                p2_final_hp=p2_hp,
                p1_deck=p1_deck,
                p2_deck=p2_deck,
            )
            results.results.append(result)

            print(f"  Game {idx + 1}/{len(deck_pairs)}: "
                  f"winner=P{winner or '?'}, turns={turn_number}, "
                  f"HP={p1_hp}/{p2_hp}")

        except Exception as exc:
            error_msg = f"Game {idx + 1} error ({p1_deck} vs {p2_deck}): {exc}"
            results.errors.append(error_msg)
            results.results.append(GameResult(
                winner=None,
                turn_number=0,
                ended_on_turn_cap=False,
                p1_final_hp=0,
                p2_final_hp=0,
                p1_deck=p1_deck,
                p2_deck=p2_deck,
                error=str(exc),
            ))
            print(f"  Game {idx + 1}/{len(deck_pairs)}: ERROR - {exc}")

    return results
