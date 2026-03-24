"""Collect replay embeddings for a Kayo mirror IQL dataset.

Default matchup by game count:
- Kayo vs Kayo only
"""

from __future__ import annotations

import argparse
import json
import os
import random
from pathlib import Path

import torch

from config import DECKS_DIR, SLUG_INDEX_PATH
from data_collection.replay_db import ReplayDB
from engine.actions import Action, ActionType
from engine.card import CardDB
from engine.state import GameState
from encoder.action_embedder import ActionEmbedder
from encoder.card_embedder import SlugVocab
from encoder.gamestate_embedder import GameStateEmbedder, gamestate_to_features
from rl_agents.dataset_adapter import build_iql_tensors_from_replay_db
from rl_agents.embedder_bundle import BUNDLE_FILENAME, save_embedder_bundle
from rl_agents.game_backends import GameRunRequest, add_game_backend_args, build_game_backend
from rl_agents.utils.card_helpers import card_slug as _card_slug, normalise_action_for_embedder as _normalise_action_for_embedder, safe_int as _safe_int
from rl_agents.utils.matchups import DECK_BY_HERO, MATCHUP_SPECS
from rl_agents.utils.seed import resolve_base_seed as _resolve_base_seed

AGENT_MODE_CHOICES = ["random-vs-random", "heuristic-vs-random", "heuristic-vs-heuristic"]


def _serialise_action(action: Action) -> dict:
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


class RandomEmbedderRecorderAgent:
    """Random policy agent that records transitions + embeddings."""

    def __init__(
        self,
        player_id: int,
        seed: int,
        game_id: int,
        replay_db: ReplayDB,
        step_counter: list[int],
        action_embedder: ActionEmbedder,
        state_embedder: GameStateEmbedder,
        max_decisions_per_game: int,
        max_sink_below_per_window: int,
    ):
        self.player_id = player_id
        self.rng = random.Random(seed)
        self.game_id = game_id
        self.replay_db = replay_db
        self.step_counter = step_counter
        self.action_embedder = action_embedder
        self.state_embedder = state_embedder
        self.max_decisions_per_game = max_decisions_per_game
        self.max_sink_below_per_window = max_sink_below_per_window
        self._sink_counts_by_window: dict[tuple[int, int, int], int] = {}

    @staticmethod
    def _pick_fallback_action(options: list[Action]) -> Action:
        pass_action = next((a for a in options if a.type == ActionType.PASS), None)
        if pass_action is not None:
            return pass_action
        return options[0]

    @staticmethod
    def _is_sink_below_defense_reaction(action: Action) -> bool:
        if action.type != ActionType.PLAY_DEFENSE_REACTION:
            return False
        slug = _card_slug(action.card) or ""
        return slug.startswith("sink_below")

    def _reaction_window_key(self, state: GameState) -> tuple[int, int, int]:
        # (player_id, turn_number, chain_link_id)
        link_id = int(state.combat.link_id) if state.combat is not None else -1
        return (self.player_id, int(state.turn_number), link_id)

    def _choose_action(self, state: GameState, options: list[Action]) -> Action:
        # Include PASS/REACTION_PASS in normal random choice pool.
        sink_options = [a for a in options if self._is_sink_below_defense_reaction(a)]
        if not sink_options:
            return self.rng.choice(list(options))

        key = self._reaction_window_key(state)
        sink_count = self._sink_counts_by_window.get(key, 0)

        # Anti-loop guard: after N Sink Below plays in one reaction window,
        # force selection from non-Sink options to break stalls.
        if sink_count >= self.max_sink_below_per_window:
            non_sink = [a for a in options if not self._is_sink_below_defense_reaction(a)]
            if non_sink:
                return self.rng.choice(non_sink)

        return self.rng.choice(list(options))

    def __call__(self, state: GameState, options, context=None):
        if not isinstance(options, (list, tuple)) or not options:
            return options

        if self.step_counter[0] >= self.max_decisions_per_game:
            # Guardrail against pathological loops that can create huge DB files.
            p1_hp = state.players[1].health
            p2_hp = state.players[2].health
            state.winner = 1 if p1_hp >= p2_hp else 2
            state.done = True
            if isinstance(options[0], Action):
                return self._pick_fallback_action(list(options))
            return options[0]

        is_action_choice = isinstance(options[0], Action)
        if is_action_choice:
            choice = self._choose_action(state, list(options))
        else:
            choice = self.rng.choice(list(options))

        if is_action_choice and isinstance(choice, Action):
            if self._is_sink_below_defense_reaction(choice):
                key = self._reaction_window_key(state)
                self._sink_counts_by_window[key] = self._sink_counts_by_window.get(key, 0) + 1

            with torch.no_grad():
                state_emb = self.state_embedder(state, perspective_player=self.player_id)
                action_for_embedder = _normalise_action_for_embedder(choice)
                action_emb = self.action_embedder(
                    action_for_embedder,
                    player_counters=state.players[self.player_id].counters,
                )

            phase = state.step.value if hasattr(state.step, "value") else str(state.step)
            obs = {
                "turn": state.turn_number,
                "step": phase,
                "active_player": state.active_player,
                "priority_player": state.priority_player,
                "state_debug": gamestate_to_features(state),
                "state_embedding_norm": float(torch.norm(state_emb).item()),
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

            # Amortize write overhead.
            if self.step_counter[0] % 50 == 0:
                self.replay_db.flush()

        return choice


class HeuristicEmbedderRecorderAgent(RandomEmbedderRecorderAgent):
    """Heuristic policy agent that records transitions + embeddings.

    Uses greedy attack-first heuristic logic (same strategy as HeuristicBot)
    while recording state/action embeddings via the parent class machinery.
    """

    def __init__(self, slug_index_path: str = "card_data/slug_index.json", **kwargs):
        super().__init__(**kwargs)
        self._card_stats_cache: dict[str, dict] = {}
        path = Path(slug_index_path)
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            by_slug = raw.get("by_slug", {})
            for slug, card in by_slug.items():
                self._card_stats_cache[slug] = {
                    "power": _safe_int(card.get("power"), 0),
                    "defense": _safe_int(card.get("defense"), 0),
                    "cost": _safe_int(card.get("cost"), 0),
                    "pitch": _safe_int(card.get("pitch"), 0),
                    "types": card.get("types", []),
                }

    def _get_stats(self, action: Action) -> dict:
        slug = _card_slug(action.card) or ""
        return self._card_stats_cache.get(slug, {"power": 0, "defense": 0, "cost": 0, "pitch": 0, "types": []})

    def _choose_action(self, state: GameState, options: list[Action]) -> Action:
        from engine.state import Step

        step = state.step

        # --- Action phase: play highest-power attack ---
        if step == Step.ACTION:
            attacks = [
                a for a in options
                if a.type in (ActionType.PLAY_CARD, ActionType.ATTACK_WEAPON)
                and self._get_stats(a)["power"] > 0
            ]
            if attacks:
                return max(attacks, key=lambda a: self._get_stats(a)["power"])

        # --- Defend phase: block with equipment first, then weakest hand cards ---
        if step == Step.COMBAT_DEFEND:
            eq_blocks = [a for a in options if a.type == ActionType.DEFEND_EQUIPMENT]
            card_blocks = [a for a in options if a.type == ActionType.DEFEND_CARDS]
            if eq_blocks:
                return max(eq_blocks, key=lambda a: self._get_stats(a)["defense"])
            if card_blocks:
                return max(card_blocks, key=lambda a: (
                    self._get_stats(a)["defense"],
                    -self._get_stats(a)["power"],
                ))

        # --- Reaction phase: apply sink-below guard then fall back to heuristic ---
        if step == Step.COMBAT_REACTION:
            return super()._choose_action(state, options)

        # Fall back to random for all other phases
        return self.rng.choice(list(options))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect Kayo-mirror IQL replay data")
    parser.add_argument(
        "--out-dir",
        type=str,
        default="data_collection/iql_initial_mix",
        help="Output folder for DB, summary, and optional dataset pt",
    )
    parser.add_argument(
        "--games-per-matchup",
        type=int,
        default=1,
        help="Number of games to collect per matchup bucket",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Base RNG seed for game and agent randomness (defaults to a fresh per-run seed)",
    )
    parser.add_argument(
        "--torch-seed",
        type=int,
        default=None,
        help="Torch seed used for deterministic embedder initialization (defaults to --seed)",
    )
    parser.add_argument(
        "--save-dataset-pt",
        action="store_true",
        help="Also write merged (s, a, r, s', done) tensors to iql_dataset.pt",
    )
    parser.add_argument(
        "--max-decisions-per-game",
        type=int,
        default=5000,
        help="Hard cap on recorded Action decisions per game to prevent runaway DB growth",
    )
    parser.add_argument(
        "--max-sink-below-per-window",
        type=int,
        default=3,
        help="Max Sink Below defense-reaction plays per player per chain link before forcing non-Sink actions",
    )
    parser.add_argument(
        "--agent-mode",
        type=str,
        choices=AGENT_MODE_CHOICES,
        default="random-vs-random",
        help="Agent pairing: random-vs-random, heuristic-vs-random, heuristic-vs-heuristic",
    )
    add_game_backend_args(parser)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.games_per_matchup <= 0:
        raise ValueError("--games-per-matchup must be > 0")
    if args.max_decisions_per_game <= 0:
        raise ValueError("--max-decisions-per-game must be > 0")
    if args.max_sink_below_per_window <= 0:
        raise ValueError("--max-sink-below-per-window must be > 0")

    base_seed = _resolve_base_seed(args.seed)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = out_dir / "mixed_seeded_replay.db"
    summary_path = out_dir / "collection_summary.json"
    dataset_path = out_dir / "iql_dataset.pt"
    bundle_path = out_dir / BUNDLE_FILENAME

    if db_path.exists():
        db_path.unlink()

    torch_seed = base_seed if args.torch_seed is None else args.torch_seed
    torch.manual_seed(torch_seed)

    card_db = CardDB(SLUG_INDEX_PATH)
    game_backend = build_game_backend(
        args.game_backend,
        talishar_base_url=args.talishar_base_url,
        talishar_api_key=args.talishar_api_key,
        talishar_mode=args.talishar_mode,
        talishar_request_timeout=args.talishar_request_timeout,
    )
    slug_vocab = SlugVocab.from_card_db(card_db)
    action_embedder = ActionEmbedder(d_model=128, slug_vocab_size=slug_vocab.size, slug_vocab=slug_vocab)
    state_embedder = GameStateEmbedder(d_model=128, slug_vocab_size=slug_vocab.size, slug_vocab=slug_vocab)
    action_embedder.eval()
    state_embedder.eval()
    save_embedder_bundle(bundle_path, action_embedder, state_embedder)

    replay_db = ReplayDB(str(db_path))

    game_records: list[dict] = []
    global_game_idx = 0

    print("=" * 72)
    print("KAYO MIRROR IQL DATA COLLECTION")
    print("=" * 72)
    print(f"games_per_matchup : {args.games_per_matchup}")
    print(f"total_games       : {args.games_per_matchup * len(MATCHUP_SPECS)}")
    print(f"decision_cap/game : {args.max_decisions_per_game}")
    print(f"sink_cap/window   : {args.max_sink_below_per_window}")
    print(f"base_seed         : {base_seed}")
    print(f"torch_seed        : {torch_seed}")
    print(f"agent_mode        : {args.agent_mode}")
    print(f"game_backend      : {game_backend.name}")
    print(f"output_db         : {db_path}")

    for spec in MATCHUP_SPECS:
        for i in range(args.games_per_matchup):
            p1_hero = spec["p1_hero"]
            p2_hero = spec["p2_hero"]
            p1_deck = os.path.join(DECKS_DIR, DECK_BY_HERO[p1_hero])
            p2_deck = os.path.join(DECKS_DIR, DECK_BY_HERO[p2_hero])

            game_id = replay_db.start_game(p1_hero, p2_hero)
            step_counter = [0]

            seed_offset = base_seed + global_game_idx * 10
            common_kwargs = dict(
                game_id=game_id,
                replay_db=replay_db,
                step_counter=step_counter,
                action_embedder=action_embedder,
                state_embedder=state_embedder,
                max_decisions_per_game=args.max_decisions_per_game,
                max_sink_below_per_window=args.max_sink_below_per_window,
            )

            p1_use_heuristic = args.agent_mode in ("heuristic-vs-random", "heuristic-vs-heuristic")
            p2_use_heuristic = args.agent_mode == "heuristic-vs-heuristic"

            if p1_use_heuristic:
                p1_agent = HeuristicEmbedderRecorderAgent(
                    slug_index_path=str(SLUG_INDEX_PATH),
                    player_id=1,
                    seed=seed_offset + 1,
                    **common_kwargs,
                )
            else:
                p1_agent = RandomEmbedderRecorderAgent(
                    player_id=1,
                    seed=seed_offset + 1,
                    **common_kwargs,
                )

            if p2_use_heuristic:
                p2_agent = HeuristicEmbedderRecorderAgent(
                    slug_index_path=str(SLUG_INDEX_PATH),
                    player_id=2,
                    seed=seed_offset + 2,
                    **common_kwargs,
                )
            else:
                p2_agent = RandomEmbedderRecorderAgent(
                    player_id=2,
                    seed=seed_offset + 2,
                    **common_kwargs,
                )

            final_state = game_backend.run_game(
                GameRunRequest(
                    p1_deck=p1_deck,
                    p2_deck=p2_deck,
                    p1_agent=p1_agent,
                    p2_agent=p2_agent,
                    card_db=card_db,
                    p1_seed=seed_offset + 3,
                    p2_seed=seed_offset + 4,
                )
            )

            winner = int(final_state.winner) if final_state.winner is not None else None
            turns = int(final_state.turn_number)
            ended_on_turn_cap = bool(getattr(final_state, "ended_on_turn_cap", False))
            replay_db.finalize_game(
                game_id,
                winner,
                turns,
                ended_on_turn_cap=ended_on_turn_cap,
            )
            replay_db.flush()

            game_records.append(
                {
                    "game_id": game_id,
                    "matchup": spec["name"],
                    "p1_hero": p1_hero,
                    "p2_hero": p2_hero,
                    "winner": winner,
                    "turns": turns,
                    "transitions": step_counter[0],
                    "ended_on_turn_cap": ended_on_turn_cap,
                    "hit_decision_cap": bool(step_counter[0] >= args.max_decisions_per_game),
                }
            )

            global_game_idx += 1
            print(
                f"[collect] game={game_id:4d} matchup={spec['name']:<22} "
                f"winner=P{winner} turns={turns:3d} transitions={step_counter[0]:4d}"
            )

    by_matchup: dict[str, dict] = {}
    for spec in MATCHUP_SPECS:
        key = spec["name"]
        rows = [r for r in game_records if r["matchup"] == key]
        by_matchup[key] = {
            "games": len(rows),
            "transitions": int(sum(r["transitions"] for r in rows)),
            "avg_turns": float(sum(r["turns"] for r in rows) / max(len(rows), 1)),
        }

    total_transitions = int(sum(r["transitions"] for r in game_records))
    summary = {
        "seed": base_seed,
        "torch_seed": torch_seed,
        "torch_seed": torch_seed,
        "games_per_matchup": args.games_per_matchup,
        "total_games": len(game_records),
        "total_transitions": total_transitions,
        "matchups": by_matchup,
        "state_dim": state_embedder.get_output_dim(),
        "action_dim": action_embedder.get_output_dim(),
        "db_path": str(db_path),
        "embedder_bundle": str(bundle_path),
        "games": game_records,
    }

    if args.save_dataset_pt:
        payload = build_iql_tensors_from_replay_db(str(db_path))
        torch.save(payload, str(dataset_path))
        summary["dataset_pt"] = {
            "path": str(dataset_path),
            "num_transitions": int(payload["num_transitions"]),
            "state_dim": int(payload["state_dim"]),
            "action_dim": int(payload["action_dim"]),
        }

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    replay_db.close()

    print("=" * 72)
    print("COLLECTION COMPLETE")
    print("=" * 72)
    for key, stats in by_matchup.items():
        print(
            f"{key:<22} games={stats['games']:3d} "
            f"transitions={stats['transitions']:5d} avg_turns={stats['avg_turns']:.1f}"
        )
    print(f"total_transitions     : {total_transitions}")
    print(f"embedder_bundle       : {bundle_path}")
    print(f"summary               : {summary_path}")
    print(f"replay_db             : {db_path}")
    if args.save_dataset_pt:
        print(f"dataset_pt            : {dataset_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
