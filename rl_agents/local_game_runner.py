"""Core game simulation module for the training/evolution pipeline.

Provides:
- OpponentPool: manages a mix of agent types for self-play
- MatchupScheduler: ensures deck coverage across game batches
- EmbeddingRecorderAgent: wraps any agent to record embeddings to ReplayDB
- run_games(): orchestrates batch game execution
"""

from __future__ import annotations

import random
import sqlite3
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
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
from encoder.gamestate_embedder import GameStateEmbedder
from encoder.game_transformer import GameTransformerEncoder, prime_dummy_vocab
from rl_agents.game_backends import GameRunRequest, LocalEngineBackend
from rl_agents.game_data import TransitionCollector
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
    """Manages agent assignment for training games.

    P1 (the learner) always uses the current best IQL checkpoint.
    P2 (the opponent) is sampled from a configurable mix of previous
    checkpoints and heuristic (optionally current IQL model), to provide
    diverse training signal.
    Falls back to heuristic for P1 if no checkpoint exists yet.
    """

    def __init__(
        self,
        heuristic_seed: int = 0,
        current_checkpoint: str | None = None,
        previous_checkpoints: list[str] | None = None,
        include_current_in_p2: bool = True,
        device: str = "cpu",
        embedder_bundle: dict | None = None,
    ):
        self._device = device
        self._embedder_bundle = embedder_bundle
        self._heuristic_seed = heuristic_seed

        # P1 agent config: current IQL model (or heuristic if none)
        if current_checkpoint and Path(current_checkpoint).exists():
            self._p1_config = {"type": "iql_policy", "checkpoint_path": current_checkpoint}
        else:
            self._p1_config = {"type": "heuristic", "seed": heuristic_seed}

        # P2 opponent pool: configurable mix of current model, previous checkpoints, heuristic
        self._p2_pool: list[dict[str, Any]] = []

        # Current model as opponent (self-play)
        if include_current_in_p2 and current_checkpoint and Path(current_checkpoint).exists():
            self._p2_pool.append({
                "type": "iql_policy",
                "checkpoint_path": current_checkpoint,
            })

        # Previous checkpoints
        for cp_path in (previous_checkpoints or []):
            if Path(cp_path).exists():
                self._p2_pool.append({
                    "type": "iql_policy",
                    "checkpoint_path": cp_path,
                })

        # Always include heuristic as opponent
        self._p2_pool.append({
            "type": "heuristic",
            "seed": heuristic_seed,
        })

    def get_p1_agent(self, player_id: int = 1, seed: int = 0) -> Any:
        """Return the P1 (learner) agent — always the current best model."""
        return self._build_agent(self._p1_config, player_id=player_id, seed=seed)

    def sample_opponent(self, rng: random.Random, player_id: int = 2, seed: int = 0) -> Any:
        """Return a random P2 opponent from the pool."""
        entry = rng.choice(self._p2_pool)
        return self._build_agent(entry, player_id=player_id, seed=seed)

    # Keep backward compat for any code that calls sample_agent
    def sample_agent(self, rng: random.Random, player_id: int = 1, seed: int = 0) -> Any:
        if player_id == 1:
            return self.get_p1_agent(player_id=player_id, seed=seed)
        return self.sample_opponent(rng, player_id=player_id, seed=seed)

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
    """Ensures all validated decks appear at least once per batch.

    Scheduling pattern: 4 non-mirror cycles followed by 1 mirror cycle,
    repeating until games_per_loop is reached.

    Non-mirror cycle — shuffle decks, pair consecutively (N//2 pairs).
    Mirror cycle     — each deck plays against itself (N pairs).
    """

    MIRROR_EVERY_N_CYCLES: int = 4  # insert 1 mirror cycle after this many non-mirror cycles

    def schedule_matchups(
        self,
        deck_paths: list[str],
        games_per_loop: int,
    ) -> list[tuple[str, str]]:
        """Return a list of (p1_deck, p2_deck) pairs.

        Generates complete super-cycles (4 non-mirror + 1 mirror) until the
        list is at least games_per_loop long, then trims to exact count.
        """
        if not deck_paths:
            return []

        pairs: list[tuple[str, str]] = []
        non_mirror_cycles_done = 0

        while len(pairs) < games_per_loop:
            if non_mirror_cycles_done < self.MIRROR_EVERY_N_CYCLES:
                # Non-mirror cycle: shuffle, pair consecutively without replacement
                shuffled = list(deck_paths)
                random.shuffle(shuffled)
                if len(shuffled) % 2 != 0:
                    # Odd count: repeat last deck to allow clean pairing
                    shuffled.append(shuffled[-1])
                for i in range(0, len(shuffled), 2):
                    pairs.append((shuffled[i], shuffled[i + 1]))
                non_mirror_cycles_done += 1
            else:
                # Mirror cycle: every deck plays itself once
                shuffled = list(deck_paths)
                random.shuffle(shuffled)
                for deck in shuffled:
                    pairs.append((deck, deck))
                non_mirror_cycles_done = 0  # reset counter

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
        transition_collector: Any | None = None,
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
        self.transition_collector = transition_collector
        self._last_seen_chain_count: int = 0
        # Card usage tracking: {slug: count} per usage type
        self._card_usage: dict[str, dict[str, int]] = {
            "played": {},
            "blocked": {},
            "pitched": {},
        }

    def get_card_usage(self) -> dict[str, dict[str, int]]:
        """Return accumulated card usage for this player."""
        return self._card_usage

    def _track_action_cards(self, action: "Action") -> None:
        """Extract card slugs from action and record how they were used.

        Coverage:
          played  — PLAY_CARD, PLAY_ARSENAL, PLAY_ATTACK_REACTION,
                    PLAY_DEFENSE_REACTION, ATTACK_WEAPON, ACTIVATE_WEAPON,
                    ACTIVATE_EQUIPMENT, ACTIVATE_ITEM, ATTACK_ALLY,
                    DISCARD_ACTIVATE, PLAY_BANISH
          blocked — DEFEND_CARDS (hand cards), DEFEND_EQUIPMENT
          pitched — pitch_cards attached to any action
        """
        # ── pitched cards (attached to any action type) ──────────────────
        for pc in (action.pitch_cards or []):
            ps = _card_slug(pc)
            if ps:
                self._card_usage["pitched"][ps] = self._card_usage["pitched"].get(ps, 0) + 1

        # ── primary card usage ────────────────────────────────────────────
        t = action.type

        if t in (
            ActionType.PLAY_CARD,
            ActionType.PLAY_ARSENAL,
            ActionType.PLAY_ATTACK_REACTION,
            ActionType.PLAY_DEFENSE_REACTION,
            ActionType.DISCARD_ACTIVATE,
            ActionType.PLAY_BANISH,
        ):
            # Hand/arsenal card played as the primary action
            slug = _card_slug(action.card) if action.card is not None else None
            if slug:
                self._card_usage["played"][slug] = self._card_usage["played"].get(slug, 0) + 1

        elif t in (
            ActionType.ATTACK_WEAPON,
            ActionType.ACTIVATE_WEAPON,
        ):
            # Weapon being swung or activated
            slug = _card_slug(action.card) if action.card is not None else None
            if slug:
                self._card_usage["played"][slug] = self._card_usage["played"].get(slug, 0) + 1

        elif t in (
            ActionType.ACTIVATE_EQUIPMENT,
            ActionType.ACTIVATE_ITEM,
            ActionType.ATTACK_ALLY,
        ):
            # Equipment/item activated, or ally attacking
            slug = _card_slug(action.card) if action.card is not None else None
            if slug:
                self._card_usage["played"][slug] = self._card_usage["played"].get(slug, 0) + 1

        elif t == ActionType.DEFEND_CARDS:
            # One or more hand cards committed as blockers
            for c in (action.card_list or []):
                slug = _card_slug(c)
                if slug:
                    self._card_usage["blocked"][slug] = self._card_usage["blocked"].get(slug, 0) + 1

        elif t == ActionType.DEFEND_EQUIPMENT:
            # Equipment used to block
            slug = _card_slug(action.card) if action.card is not None else None
            if slug:
                self._card_usage["blocked"][slug] = self._card_usage["blocked"].get(slug, 0) + 1

    def __call__(self, state: GameState, options, context=None):
        if not isinstance(options, (list, tuple)) or not options:
            return options

        # Guardrail against pathological loops
        if self.step_counter[0] >= self.max_decisions_per_game:
            p1_hp = state.players[1].health
            p2_hp = state.players[2].health
            # Declare winner only if a hero died or HP gap > 30
            if p1_hp <= 0 or p2_hp <= 0:
                state.winner = 1 if p1_hp >= p2_hp else 2
            elif abs(p1_hp - p2_hp) > 30:
                state.winner = 1 if p1_hp > p2_hp else 2
            else:
                state.winner = None
            state.done = True
            if isinstance(options[0], Action):
                pass_action = next((a for a in options if a.type == ActionType.PASS), None)
                return pass_action if pass_action is not None else options[0]
            return options[0]

        # Log when option count is dangerously high (combinatorial explosion)
        if isinstance(options, (list, tuple)) and len(options) > 200:
            step_name = getattr(state.step, "value", state.step) if hasattr(state, "step") else "?"
            print(f"  [WARN] game={self.game_id} step={self.step_counter[0]} "
                  f"phase={step_name} options={len(options)} player={self.player_id}")

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
            self._track_action_cards(choice)

            action_for_embedder = _normalise_action_for_embedder(choice)
            player_counters = state.players[self.player_id].counters

            # Decide: end-to-end (raw features) or legacy (pre-computed embeddings)?
            use_raw_features = isinstance(self.state_embedder, GameTransformerEncoder) and hasattr(
                self.action_embedder, "tokenize_to_packed"
            )

            if use_raw_features:
                # Store compact raw tokenized features — transformer runs inside training loop
                state_feat = self.state_embedder.tokenize_to_packed(
                    state, perspective_player=self.player_id,
                )
                action_feat = self.action_embedder.tokenize_to_packed(
                    action_for_embedder,
                    player_counters=player_counters,
                )
            else:
                # Legacy path: run encoders now, store the resulting embedding blobs
                with torch.no_grad():
                    state_emb = self.state_embedder(
                        state, perspective_player=self.player_id,
                    )
                    action_emb = self.action_embedder(
                        action_for_embedder,
                        player_counters=player_counters,
                    )

            phase = state.step.value if hasattr(state.step, "value") else str(state.step)
            obs = {
                "turn": state.turn_number,
                "step": phase,
                "active_player": state.active_player,
                "priority_player": state.priority_player,
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

            if use_raw_features:
                self.replay_db.store_features(row_id, state_feat, action_feat)
            else:
                self.replay_db.store_embeddings(row_id, state_emb, action_emb)

            self.step_counter[0] += 1

            # Also record to TransitionCollector (→ game_data.db rich columns)
            if self.transition_collector is not None:
                self.transition_collector.record_local(
                    player_id=self.player_id,
                    state=state,
                    action=choice,
                    legal_actions=options,
                )

            if self.step_counter[0] % 50 == 0:
                self.replay_db.flush()

        return choice


# ---------------------------------------------------------------------------
# run_games
# ---------------------------------------------------------------------------

def _assign_game_rewards(
    replay_db: ReplayDB,
    game_id: int,
    combat_log: dict[int, list[dict]],
    winner: int | None,
    normalizer: float = 10.0,
    is_guardrail: bool = False,
) -> None:
    """Compute damage-scaled rewards and back-propagate to previous-turn transitions.

    Reward structure:
    - Dealing net_damage: attacker receives +net_damage / normalizer
    - Taking net_damage: defender receives -0.75 * net_damage / normalizer
    - The asymmetry (1.0 vs 0.75) encourages aggression over stalling.
    - Terminal: +1 for winner, -1 for loser on each player's final transition.
    - Guardrail games (turn cap / decision cap hit): all rewards are 0; transitions
      are still marked done so the dataset knows the episode ended.

    Back-propagation target: last transition of the *previous* turn (when cards were
    drawn), falling back to each player's earliest transition for turn-1 combat.
    """
    transitions = replay_db.get_game_transitions(game_id)
    if not transitions:
        return

    import json as _json

    # Build per-player per-turn lookup: {(player_id, turn): last_tid}
    player_turn_last: dict[tuple[int, int], int] = {}
    player_earliest: dict[int, int] = {}
    player_latest: dict[int, int] = {}

    for t in transitions:
        tid = t["id"]
        pid = t["player_id"]
        obs = _json.loads(t["obs"]) if isinstance(t["obs"], str) else t["obs"]
        turn = obs.get("turn", 0)

        player_turn_last[(pid, turn)] = tid  # last one wins (ordered by step_idx)
        if pid not in player_earliest:
            player_earliest[pid] = tid
        player_latest[pid] = tid

    # Accumulate rewards: {tid: float}
    reward_acc: dict[int, float] = {}

    if not is_guardrail:
        for turn, links in combat_log.items():
            if not links:
                continue

            # Aggregate actual net damage per attacker/defender
            damage_dealt: dict[int, float] = {}   # attacker_id -> total net damage dealt
            damage_taken: dict[int, float] = {}   # defender_id -> total net damage received

            for link in links:
                attacker_id = link.get("attacker_id")
                net_damage = link.get("net_damage", 0) or 0

                if attacker_id is not None and net_damage > 0:
                    defender_id = 2 if attacker_id == 1 else 1
                    damage_dealt[attacker_id] = damage_dealt.get(attacker_id, 0) + net_damage
                    damage_taken[defender_id] = damage_taken.get(defender_id, 0) + net_damage

            # Back-propagate to last transition of previous turn
            target_turn = turn - 1
            for pid, total_dealt in damage_dealt.items():
                tid = player_turn_last.get((pid, target_turn)) or player_earliest.get(pid)
                if tid is not None:
                    reward_acc[tid] = reward_acc.get(tid, 0.0) + total_dealt / normalizer

            for pid, total_taken in damage_taken.items():
                tid = player_turn_last.get((pid, target_turn)) or player_earliest.get(pid)
                if tid is not None:
                    reward_acc[tid] = reward_acc.get(tid, 0.0) - 0.75 * total_taken / normalizer

    # Terminal rewards: last transition per player (zero for guardrail games)
    done_updates: list[tuple[int, int]] = []  # (done, tid)
    for pid, tid in player_latest.items():
        terminal = 0.0
        if not is_guardrail and winner is not None:
            terminal = 1.0 if pid == winner else -1.0
        reward_acc[tid] = reward_acc.get(tid, 0.0) + terminal
        done_updates.append((1, tid))

    # Batch update
    if reward_acc:
        replay_db.batch_update_rewards([(r, tid) for tid, r in reward_acc.items()])
    if done_updates:
        replay_db.batch_update_done(done_updates)


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


def _build_embedders(
    embedder_bundle: dict,
    device: "torch.device | None" = None,
) -> tuple[ActionEmbedder, "GameStateEmbedder | GameTransformerEncoder"]:
    """Build ActionEmbedder and state embedder from a bundle dict.

    If the bundle contains a ``game_transformer_state_dict`` key, construct and
    return a ``GameTransformerEncoder`` as the state embedder.  Otherwise fall
    back to the legacy ``GameStateEmbedder``.
    """
    card_db = CardDB(SLUG_INDEX_PATH)
    slug_vocab = SlugVocab.from_card_db(card_db)
    d_model = int(embedder_bundle.get("d_model", 128))

    action_embedder = ActionEmbedder(
        d_model=d_model,
        slug_vocab_size=slug_vocab.size,
        slug_vocab=slug_vocab,
    )

    card_sd = embedder_bundle.get("card_embedder_state_dict", {})
    card_prefixed = {f"card_embedder.{k}": v for k, v in card_sd.items()}

    def _filter_by_shape(model, sd):
        """Skip entries whose shape doesn't match the model (handles stale bundles)."""
        model_sd = model.state_dict()
        return {k: v for k, v in sd.items()
                if k in model_sd and model_sd[k].shape == v.shape}

    action_embedder.load_state_dict(
        _filter_by_shape(action_embedder, {**card_prefixed, **embedder_bundle["action_embedder_state_dict"]}),
        strict=False,
    )
    action_embedder.eval()

    # ── Choose state embedder ───────────────────────────────────────────────
    if "game_transformer_state_dict" in embedder_bundle:
        # Use transformer encoder — populate slug vocab for forward() lookups
        prime_dummy_vocab(card_db)
        gt_d_model        = int(embedder_bundle.get("game_transformer_d_model", 256))
        gt_n_heads        = int(embedder_bundle.get("game_transformer_n_heads", 8))
        gt_n_layers       = int(embedder_bundle.get("game_transformer_n_layers", 4))
        gt_hero_head_dim  = int(embedder_bundle.get("game_transformer_hero_head_dim", 64))
        state_embedder = GameTransformerEncoder(
            slug_vocab_size=slug_vocab.size,
            d_model=gt_d_model,
            n_heads=gt_n_heads,
            n_layers=gt_n_layers,
            hero_head_dim=gt_hero_head_dim,
        )
        state_embedder.load_state_dict(
            _filter_by_shape(state_embedder, embedder_bundle["game_transformer_state_dict"]),
            strict=False,
        )
    else:
        state_embedder = GameStateEmbedder(
            d_model=d_model,
            slug_vocab_size=slug_vocab.size,
            slug_vocab=slug_vocab,
        )
        state_embedder.load_state_dict(
            _filter_by_shape(state_embedder, {**card_prefixed, **embedder_bundle["state_embedder_state_dict"]}),
            strict=False,
        )

    state_embedder.eval()

    if device is not None:
        action_embedder = action_embedder.to(device)
        state_embedder = state_embedder.to(device)

    return action_embedder, state_embedder


def _run_games_chunk(
    deck_pairs: list[tuple[str, str]],
    opponent_pool: OpponentPool,
    card_db: CardDB,
    replay_db: ReplayDB | str,
    game_data_store: Any | None,
    embedder_bundle: dict,
    max_turns: int = 200,
    seed: int = 0,
    device: "torch.device | str | None" = None,
    index_offset: int = 0,
    total_games: int | None = None,
    worker_label: str = "",
) -> GameResults:
    """Run a batch of games and record results.

    For each matchup:
    1. Sample agents from the opponent pool.
    2. Wrap with EmbeddingRecorderAgent for embedding collection.
    3. Run via LocalEngineBackend.run_game().
    4. Record results to ReplayDB (for IQL) and GameDataStore (for deck evaluator).
    5. Catch individual game errors without halting the batch.
    """
    created_replay_db = False
    if isinstance(replay_db, str):
        replay_db = ReplayDB(replay_db)
        created_replay_db = True

    rng = random.Random(seed)
    backend = LocalEngineBackend()
    # Resolve device — accept string ("dml", "cpu", etc.) or torch.device
    if isinstance(device, str):
        from rl_agents.utils.device import resolve_device
        _device = resolve_device(device)
    else:
        _device = device  # None → embedders stay on CPU
    action_embedder, state_embedder = _build_embedders(embedder_bundle, device=_device)
    results = GameResults()

    total = total_games if total_games is not None else len(deck_pairs)

    for idx, (p1_deck, p2_deck) in enumerate(deck_pairs):
        display_idx = index_offset + idx + 1
        game_seed = rng.randint(0, 2**31 - 1)
        try:
            # Extract hero names for replay DB
            p1_hero = _extract_hero_from_deck(p1_deck)
            p2_hero = _extract_hero_from_deck(p2_deck)
            game_id = replay_db.start_game(p1_hero, p2_hero)

            # Sample and wrap agents
            step_counter = [0]
            combat_log: dict[int, list[dict]] = {}
            collector = TransitionCollector(game_id=game_id)
            base_p1 = opponent_pool.get_p1_agent(player_id=1, seed=game_seed)
            base_p2 = opponent_pool.sample_opponent(rng, player_id=2, seed=game_seed + 1)

            p1_agent = EmbeddingRecorderAgent(
                base_agent=base_p1,
                player_id=1,
                game_id=game_id,
                replay_db=replay_db,
                action_embedder=action_embedder,
                state_embedder=state_embedder,
                step_counter=step_counter,
                combat_log=combat_log,
                transition_collector=collector,
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
                transition_collector=collector,
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
            guardrail_terminated = step_counter[0] >= p1_agent.max_decisions_per_game
            ended_on_cap = bool(
                getattr(game_state, "ended_on_turn_cap", False)
                or turn_number >= max_turns
                or guardrail_terminated
            )
            p1_hp = game_state.players[1].health if hasattr(game_state, "players") else 0
            p2_hp = game_state.players[2].health if hasattr(game_state, "players") else 0

            # If both heroes are alive, only award winner/rewards when
            # the HP gap is decisive (>30).  Otherwise treat as
            # inconclusive — no winner, no rewards.
            both_alive = p1_hp > 0 and p2_hp > 0
            inconclusive = False
            if both_alive:
                hp_gap = abs(p1_hp - p2_hp)
                if hp_gap > 30:
                    winner = 1 if p1_hp > p2_hp else 2
                else:
                    winner = None
                    inconclusive = True

            # Finalize in ReplayDB
            replay_db.finalize_game(game_id, winner, turn_number, ended_on_cap)

            # Assign damage-scaled rewards and terminal signals
            _assign_game_rewards(
                replay_db, game_id, combat_log, winner,
                is_guardrail=inconclusive or ended_on_cap or guardrail_terminated,
            )

            replay_db.flush()

            # Record to GameDataStore if available
            if game_data_store is not None:
                try:
                    collector.finalize(winner)
                    game_data_store.record_local_game(
                        collector=collector,
                        game_state=game_state,
                        p1_deck_file=p1_deck,
                        p2_deck_file=p2_deck,
                        seed=game_seed,
                        game_id=game_id,
                        p1_card_usage=p1_agent.get_card_usage(),
                        p2_card_usage=p2_agent.get_card_usage(),
                    )
                except Exception:
                    pass  # Non-critical; replay DB is the primary store

            early_end = turn_number <= 2

            # Free memory: clear collector transitions and game state references
            collector._transitions.clear()
            del game_state, p1_agent, p2_agent, base_p1, base_p2, collector

            # Periodic garbage collection to break circular refs (every 50 games)
            if (idx + 1) % 50 == 0:
                import gc
                gc.collect()

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

            prefix = f"[{worker_label}] " if worker_label else ""
            msg = (f"  {prefix}Game {display_idx}/{total}: "
                   f"winner=P{winner or '?'}, turns={turn_number}, "
                   f"HP={p1_hp}/{p2_hp}")
            if guardrail_terminated:
                msg += f" [GUARDRAIL: {step_counter[0]} decisions, trigger loop on turn {turn_number}]"
            elif early_end:
                msg += f" [EARLY END]"
            print(msg)

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
            prefix = f"[{worker_label}] " if worker_label else ""
            print(f"  {prefix}Game {display_idx}/{total}: ERROR - {exc}")

    if created_replay_db:
        replay_db.flush()
        replay_db.close()

    return results


def _merge_replay_shard(main_db_path: str, shard_db_path: str) -> tuple[int, int]:
    """Merge a worker replay shard into the main replay DB.

    Returns (games_merged, transitions_merged).
    """
    main = sqlite3.connect(main_db_path)
    shard = sqlite3.connect(shard_db_path)
    main.row_factory = sqlite3.Row
    shard.row_factory = sqlite3.Row

    games_merged = 0
    transitions_merged = 0

    try:
        game_rows = shard.execute(
            "SELECT game_id, p1_hero, p2_hero, winner, turns, ended_on_turn_cap, created_at FROM games ORDER BY game_id"
        ).fetchall()

        for g in game_rows:
            cur = main.execute(
                "INSERT INTO games (p1_hero, p2_hero, winner, turns, ended_on_turn_cap, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (g["p1_hero"], g["p2_hero"], g["winner"], g["turns"], g["ended_on_turn_cap"], g["created_at"]),
            )
            new_game_id = int(cur.lastrowid)
            old_game_id = g["game_id"]

            transition_rows = shard.execute(
                "SELECT id, step_idx, player_id, phase, obs, action, reward, done FROM transitions WHERE game_id = ? ORDER BY id",
                (old_game_id,),
            ).fetchall()

            id_map: dict[int, int] = {}
            for t in transition_rows:
                t_cur = main.execute(
                    "INSERT INTO transitions (game_id, step_idx, player_id, phase, obs, action, reward, done) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (new_game_id, t["step_idx"], t["player_id"], t["phase"], t["obs"], t["action"], t["reward"], t["done"]),
                )
                id_map[int(t["id"])] = int(t_cur.lastrowid)
                transitions_merged += 1

            if id_map:
                placeholders = ",".join("?" for _ in id_map)
                emb_rows = shard.execute(
                    f"SELECT transition_id, state_embedding, action_embedding, state_features, action_features FROM embeddings WHERE transition_id IN ({placeholders})",
                    tuple(id_map.keys()),
                ).fetchall()
                for e in emb_rows:
                    mapped_tid = id_map[int(e["transition_id"])]
                    main.execute(
                        "INSERT OR REPLACE INTO embeddings (transition_id, state_embedding, action_embedding, state_features, action_features) VALUES (?, ?, ?, ?, ?)",
                        (mapped_tid, e["state_embedding"], e["action_embedding"], e["state_features"], e["action_features"]),
                    )

            games_merged += 1

        main.commit()
    finally:
        shard.close()
        main.close()

    return games_merged, transitions_merged


def _worker_process_entry(
    deck_pairs: list[tuple[str, str]],
    shard_db_path: str,
    game_data_db_path: str | None,
    embedder_bundle_path: str,
    slug_index_path: str,
    opponent_config: dict,
    max_turns: int,
    seed: int,
    device: str | None,
    index_offset: int,
    total_games: int,
    worker_label: str,
) -> dict:
    """Entry point for worker processes. Reconstructs all objects from paths.

    Returns a dict (not GameResults) so it's easily picklable across processes.
    """
    from rl_agents.embedder_bundle import load_embedder_bundle
    from rl_agents.game_data import GameDataStore

    # Reconstruct objects in this process
    card_db = CardDB(slug_index_path)
    embedder_bundle = load_embedder_bundle(embedder_bundle_path)
    replay_db = ReplayDB(shard_db_path)

    game_data_store = None
    if game_data_db_path:
        game_data_store = GameDataStore(db_path=game_data_db_path)

    opponent_pool = OpponentPool(
        heuristic_seed=opponent_config["heuristic_seed"],
        current_checkpoint=opponent_config.get("current_checkpoint"),
        previous_checkpoints=opponent_config.get("previous_checkpoints"),
        device=opponent_config.get("device", "cpu"),
        embedder_bundle=embedder_bundle,
    )

    results = _run_games_chunk(
        deck_pairs=deck_pairs,
        opponent_pool=opponent_pool,
        card_db=card_db,
        replay_db=replay_db,
        game_data_store=game_data_store,
        embedder_bundle=embedder_bundle,
        max_turns=max_turns,
        seed=seed,
        device=device,
        index_offset=index_offset,
        total_games=total_games,
        worker_label=worker_label,
    )

    replay_db.flush()
    replay_db.close()
    if game_data_store is not None:
        game_data_store.close()

    # Return plain dicts for pickling
    return {
        "results": [
            {
                "winner": r.winner,
                "turn_number": r.turn_number,
                "ended_on_turn_cap": r.ended_on_turn_cap,
                "p1_final_hp": r.p1_final_hp,
                "p2_final_hp": r.p2_final_hp,
                "p1_deck": r.p1_deck,
                "p2_deck": r.p2_deck,
                "error": r.error,
            }
            for r in results.results
        ],
        "errors": results.errors,
    }


def run_games(
    deck_pairs: list[tuple[str, str]],
    opponent_pool: OpponentPool,
    card_db: CardDB,
    replay_db: ReplayDB,
    game_data_store: Any | None,
    embedder_bundle: dict,
    max_turns: int = 200,
    seed: int = 0,
    device: "torch.device | str | None" = None,
    game_workers: int = 1,
) -> GameResults:
    """Run a batch of games and record results.

    When game_workers > 1, games are split across worker *processes*
    (not threads) so each gets its own GIL and torch context.
    Each worker writes to a private shard DB, which is merged back
    into the main replay DB sequentially after all workers finish.
    """
    if game_workers <= 1 or len(deck_pairs) <= 1:
        return _run_games_chunk(
            deck_pairs=deck_pairs,
            opponent_pool=opponent_pool,
            card_db=card_db,
            replay_db=replay_db,
            game_data_store=game_data_store,
            embedder_bundle=embedder_bundle,
            max_turns=max_turns,
            seed=seed,
            device=device,
            index_offset=0,
            total_games=len(deck_pairs),
        )

    workers = max(1, min(int(game_workers), len(deck_pairs)))
    chunks: list[list[tuple[str, str]]] = [list() for _ in range(workers)]
    offsets: list[int] = [0 for _ in range(workers)]

    for idx, pair in enumerate(deck_pairs):
        chunks[idx % workers].append(pair)

    running = 0
    for i in range(workers):
        offsets[i] = running
        running += len(chunks[i])

    # Flush and close the main DB — workers will use independent shards
    replay_db.flush()
    replay_db.close()

    main_db_path = replay_db.db_path

    # Build serializable opponent config from the pool's internal state
    opponent_config = {
        "heuristic_seed": opponent_pool._heuristic_seed,
        "current_checkpoint": opponent_pool._p1_config.get("checkpoint_path"),
        "previous_checkpoints": [
            e["checkpoint_path"]
            for e in opponent_pool._p2_pool
            if e["type"] == "iql_policy" and e.get("checkpoint_path") != opponent_pool._p1_config.get("checkpoint_path")
        ] or None,
        "device": opponent_pool._device,
    }

    # Resolve paths needed by workers
    embedder_bundle_path = str(Path(main_db_path).parent.parent / "checkpoints" / "embedder_bundle.pt")
    slug_index_path = str(SLUG_INDEX_PATH)
    game_data_db_path = game_data_store.db_path if game_data_store is not None else None
    device_str = str(device) if device is not None else None

    shard_paths: list[str] = []
    futures = {}
    merged_results = GameResults()

    with ProcessPoolExecutor(max_workers=workers) as executor:
        for worker_id in range(workers):
            chunk = chunks[worker_id]
            if not chunk:
                continue
            shard_path = f"{main_db_path}.worker{worker_id}.db"
            Path(shard_path).unlink(missing_ok=True)
            shard_paths.append(shard_path)

            fut = executor.submit(
                _worker_process_entry,
                deck_pairs=chunk,
                shard_db_path=shard_path,
                game_data_db_path=game_data_db_path,
                embedder_bundle_path=embedder_bundle_path,
                slug_index_path=slug_index_path,
                opponent_config=opponent_config,
                max_turns=max_turns,
                seed=seed + worker_id * 1_000_003,
                device=device_str,
                index_offset=offsets[worker_id],
                total_games=len(deck_pairs),
                worker_label=f"W{worker_id + 1}",
            )
            futures[fut] = shard_path

        for fut in as_completed(futures):
            result_dict = fut.result()
            for r in result_dict["results"]:
                merged_results.results.append(GameResult(**r))
            merged_results.errors.extend(result_dict["errors"])

    # Merge shards into main DB sequentially
    total_merged_games = 0
    total_merged_transitions = 0
    for shard_path in shard_paths:
        games_merged, transitions_merged = _merge_replay_shard(main_db_path, shard_path)
        total_merged_games += games_merged
        total_merged_transitions += transitions_merged
        Path(shard_path).unlink(missing_ok=True)

    # Re-open main connection for subsequent pipeline steps
    replay_db.conn
    print(
        f"  Merged replay shards: games={total_merged_games}, "
        f"transitions={total_merged_transitions}, workers={workers}"
    )

    return merged_results
