"""Evaluate a trained IQL actor against the random agent.

The actor predicts an action embedding from the current state embedding.
At decision time, the agent embeds each legal action and selects the legal
action whose embedding is nearest to the actor output in L2 distance.

Non-Action prompts used by the engine (for example trigger ordering or
start-player choice) fall back to seeded random selection because the current
IQL dataset only trains on Action decisions.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import random
import time

import torch

from config import DECKS_DIR, SLUG_INDEX_PATH
from engine.actions import Action, ActionType
from engine.card import CardDB
from encoder.action_embedder import ActionEmbedder
from encoder.card_embedder import SlugVocab
from encoder.gamestate_embedder import GameStateEmbedder
from encoder.game_transformer import GameTransformerEncoder, prime_dummy_vocab
from rl_agents.embedder_bundle import load_embedder_bundle
from rl_agents.game_backends import GameRunRequest, add_game_backend_args, build_game_backend
from rl_agents.iql import IQLTrainer
from rl_agents.random_agent import RandomAgent
from rl_agents.utils.card_helpers import card_slug as _card_slug, normalise_action_for_embedder as _normalise_action_for_embedder
from rl_agents.utils.device import default_device as _default_device, resolve_device as _resolve_device
from rl_agents.utils.matchups import DECK_BY_HERO, MATCHUP_SPECS
from rl_agents.utils.seed import resolve_base_seed as _resolve_base_seed


class IQLPolicyAgent:
    def __init__(
        self,
        checkpoint_path: str,
        player_id: int,
        device: str,
        seed: int,
        embedder_bundle: dict,
    ):
        self.player_id = player_id
        self.rng = random.Random(seed)
        self.device = _resolve_device(device)

        # Load checkpoint payload to access trained e2e weights
        checkpoint_payload = torch.load(checkpoint_path, map_location="cpu", weights_only=False)

        self.card_db = CardDB(SLUG_INDEX_PATH)
        slug_vocab = SlugVocab.from_card_db(self.card_db)
        d_model = int(embedder_bundle.get("d_model", 128))
        self.action_embedder = ActionEmbedder(
            d_model=d_model,
            slug_vocab_size=slug_vocab.size,
            slug_vocab=slug_vocab,
        )
        def _filter_by_shape(model, sd):
            model_sd = model.state_dict()
            return {
                k: v for k, v in sd.items()
                if k in model_sd and model_sd[k].shape == v.shape
            }
        # Prefer trained weights from checkpoint over stale bundle weights
        if "action_embedder_state_dict" in checkpoint_payload:
            ae_sd = checkpoint_payload["action_embedder_state_dict"]
            ae_model_sd = self.action_embedder.state_dict()
            ae_filtered = {k: v for k, v in ae_sd.items() if k in ae_model_sd and ae_model_sd[k].shape == v.shape}
            self.action_embedder.load_state_dict(ae_filtered, strict=False)
        else:
            card_sd = embedder_bundle.get("card_embedder_state_dict", {})
            card_prefixed = {f"card_embedder.{k}": v for k, v in card_sd.items()}
            self.action_embedder.load_state_dict(
                _filter_by_shape(self.action_embedder, {**card_prefixed, **embedder_bundle["action_embedder_state_dict"]}),
                strict=False,
            )
        self.action_embedder.eval()

        # Use GameTransformerEncoder as state embedder when the bundle includes one;
        # fall back to legacy GameStateEmbedder for checkpoints trained without it.
        if "game_transformer_state_dict" in embedder_bundle:
            prime_dummy_vocab(self.card_db)
            gt_d_model       = int(embedder_bundle.get("game_transformer_d_model", 256))
            gt_n_heads       = int(embedder_bundle.get("game_transformer_n_heads", 8))
            gt_n_layers      = int(embedder_bundle.get("game_transformer_n_layers", 4))
            gt_hero_head_dim = int(embedder_bundle.get("game_transformer_hero_head_dim", 64))
            self.state_embedder = GameTransformerEncoder(
                slug_vocab_size=slug_vocab.size,
                d_model=gt_d_model,
                n_heads=gt_n_heads,
                n_layers=gt_n_layers,
                hero_head_dim=gt_hero_head_dim,
            )
            # Prefer trained weights from checkpoint over stale bundle weights
            if "transformer_state_dict" in checkpoint_payload:
                gt_sd = checkpoint_payload["transformer_state_dict"]
            else:
                gt_sd = embedder_bundle["game_transformer_state_dict"]
            gt_model_sd = self.state_embedder.state_dict()
            gt_filtered = {k: v for k, v in gt_sd.items() if k in gt_model_sd and gt_model_sd[k].shape == v.shape}
            self.state_embedder.load_state_dict(gt_filtered, strict=False)
            # Ensure card_feats_lookup is populated (may already be in state_dict,
            # but re-populate from card_db as authoritative source)
            self.state_embedder.set_card_feats_lookup(self.card_db)
        else:
            card_sd = embedder_bundle.get("card_embedder_state_dict", {})
            card_prefixed = {f"card_embedder.{k}": v for k, v in card_sd.items()}
            self.state_embedder = GameStateEmbedder(
                d_model=d_model,
                slug_vocab_size=slug_vocab.size,
                slug_vocab=slug_vocab,
            )
            self.state_embedder.load_state_dict(
                _filter_by_shape(self.state_embedder, {**card_prefixed, **embedder_bundle["state_embedder_state_dict"]}),
                strict=False,
            )
        self.state_embedder.eval()

        # Build trainer from checkpoint (passing None for transformer/action_embedder
        # since eval uses the embedders directly, not through trainer's e2e path)
        self.trainer = IQLTrainer.from_checkpoint(checkpoint_path, device=device)
        self.trainer.actor.eval()

        expected_state_dim = self.state_embedder.get_output_dim()
        expected_action_dim = self.action_embedder.get_output_dim()
        if self.trainer.config.state_dim != expected_state_dim:
            raise ValueError(
                f"Checkpoint state_dim={self.trainer.config.state_dim} does not match "
                f"embedder state_dim={expected_state_dim}. "
                f"The checkpoint was trained with a different state encoder — delete stale checkpoints."
            )
        if self.trainer.config.action_dim != expected_action_dim:
            raise ValueError(
                f"Checkpoint action_dim={self.trainer.config.action_dim} does not match current embedder action_dim={expected_action_dim}"
            )

    def _fallback_choice(self, options):
        if len(options) == 1:
            return options[0]
        return self.rng.choice(list(options))

    def _score_actions(self, state, actions: list[Action]) -> int:
        """Score a list of synthetic/real Actions via the actor; return the best index.

        Ties are broken randomly.  Caller is responsible for supplying at least
        one action — returns 0 for an empty list.
        """
        if not actions:
            return 0
        if len(actions) == 1:
            return 0

        with torch.no_grad():
            state_emb = self.state_embedder(state, perspective_player=self.player_id)
            state_latent = self.trainer.encode_states(state_emb.unsqueeze(0).to(self.device).float())
            predicted_action = self.trainer.actor(state_latent).squeeze(0).cpu()

            player_counters = state.players[self.player_id].counters
            best_score = None
            best_indices: list[int] = []

            for i, action in enumerate(actions):
                action_for_embedder = _normalise_action_for_embedder(action, self.player_id)
                action_emb = self.action_embedder(
                    action_for_embedder,
                    player_counters=player_counters,
                ).float()
                action_latent = self.trainer.encode_actions(
                    action_emb.unsqueeze(0).to(self.device).float()
                ).squeeze(0).cpu()
                score = -torch.sum((predicted_action - action_latent) ** 2).item()

                if best_score is None or score > best_score + 1e-9:
                    best_score = score
                    best_indices = [i]
                elif abs(score - best_score) <= 1e-9:
                    best_indices.append(i)

        return self.rng.choice(best_indices)

    @staticmethod
    def _trigger_to_synthetic_action(entry) -> Action:
        """Map a StackEntry to a PASS Action that carries the trigger's card/player identity."""
        return Action(
            type=ActionType.PASS,
            card=entry.card,
            player_id=entry.player_id,
        )

    def __call__(self, state, options, context=None):
        if not isinstance(options, (list, tuple)) or not options:
            return options

        # ── Start-player choice: ('You', 'Opponent') ──────────────────────
        # Map each string to a PASS Action that differs only by player_id so
        # the actor can discriminate based on who goes first.
        if len(options) == 2 and set(options) == {'You', 'Opponent'}:
            opp_id = 3 - self.player_id
            synthetic = [
                Action(type=ActionType.PASS, player_id=self.player_id),  # 'You'
                Action(type=ActionType.PASS, player_id=opp_id),          # 'Opponent'
            ]
            best_idx = self._score_actions(state, synthetic)
            return options[best_idx]

        # ── Trigger ordering: list[int] with context=list[StackEntry] ─────
        # Each integer N means "put remaining[N] on the stack next".  We embed
        # each candidate trigger as a PASS carrying its card, so the actor can
        # eventually learn to prefer certain resolution orders.
        if (
            isinstance(options[0], int)
            and isinstance(context, (list, tuple))
            and len(context) == len(options)
            and context
            and hasattr(context[0], 'card')
        ):
            synthetic = [self._trigger_to_synthetic_action(context[i]) for i in range(len(options))]
            return self._score_actions(state, synthetic)

        if not isinstance(options[0], Action):
            return self._fallback_choice(options)

        if len(options) == 1:
            return options[0]

        best_idx = self._score_actions(state, list(options))
        return options[best_idx]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate an IQL checkpoint against the random agent")
    parser.add_argument("--checkpoint", type=str, required=True, help="Path to IQL checkpoint_final.pt")
    parser.add_argument("--games-per-matchup", type=int, default=10, help="Games to run for each matchup bucket")
    parser.add_argument("--seed", type=int, default=None, help="Base RNG seed (defaults to a fresh per-run seed)")
    parser.add_argument("--device", type=str, default=_default_device(), help="Torch device for the actor")
    parser.add_argument("--max-turns", type=int, default=200, help="Turn cap to pass to the engine")
    parser.add_argument("--out-dir", type=str, default="data_collection/iql_eval_runs", help="Folder for evaluation summaries")
    parser.add_argument("--run-name", type=str, default="", help="Optional evaluation run name")
    parser.add_argument("--model-seat", type=int, default=1, choices=[1, 2], help="Seat (1 or 2) that the IQL model occupies; the other seat is filled by the random agent")
    parser.add_argument("--embedder-bundle", type=str, default="", help="Optional embedder bundle path. Required for checkpoints that do not already contain one.")
    add_game_backend_args(parser)
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.games_per_matchup <= 0:
        raise ValueError("--games-per-matchup must be > 0")
    if args.max_turns <= 0:
        raise ValueError("--max-turns must be > 0")

    base_seed = _resolve_base_seed(args.seed)

    checkpoint_path = Path(args.checkpoint)
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")
    checkpoint_payload = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    embedder_bundle = None
    if args.embedder_bundle:
        embedder_bundle = load_embedder_bundle(args.embedder_bundle)
    else:
        embedder_bundle = (checkpoint_payload.get("extra") or {}).get("embedder_bundle")
    if embedder_bundle is None:
        raise ValueError(
            "Checkpoint does not contain an embedder bundle and --embedder-bundle was not provided. "
            "Using fresh random embedders would produce invalid evaluation results."
        )

    run_name = args.run_name or time.strftime("iql_eval_%Y%m%d_%H%M%S")
    run_dir = Path(args.out_dir) / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    summary_path = run_dir / "summary.json"

    card_db = CardDB(SLUG_INDEX_PATH)
    game_backend = build_game_backend(
        args.game_backend,
        talishar_base_url=args.talishar_base_url,
        talishar_api_key=args.talishar_api_key,
        talishar_mode=args.talishar_mode,
        talishar_request_timeout=args.talishar_request_timeout,
    )
    model_seat = args.model_seat
    model_agent = IQLPolicyAgent(
        checkpoint_path=str(checkpoint_path),
        player_id=model_seat,
        device=args.device,
        seed=base_seed,
        embedder_bundle=embedder_bundle,
    )

    print("=" * 72)
    print("IQL VS RANDOM EVALUATION")
    print("=" * 72)
    print(f"checkpoint         : {checkpoint_path}")
    print(f"model_seat         : {model_seat}")
    print(f"games_per_matchup  : {args.games_per_matchup}")
    print(f"total_games        : {args.games_per_matchup * len(MATCHUP_SPECS)}")
    print(f"base_seed          : {base_seed}")
    print(f"device             : {args.device}")
    print(f"game_backend       : {game_backend.name}")

    game_records: list[dict] = []
    global_game_idx = 0

    for spec in MATCHUP_SPECS:
        p1_deck = os.path.join(DECKS_DIR, DECK_BY_HERO[spec["p1_hero"]])
        p2_deck = os.path.join(DECKS_DIR, DECK_BY_HERO[spec["p2_hero"]])

        for game_idx in range(args.games_per_matchup):
            seed_offset = base_seed + (global_game_idx * 10)
            random_agent = RandomAgent(seed=seed_offset + 2)

            if model_seat == 1:
                p1_agent, p2_agent = model_agent, random_agent
            else:
                p1_agent, p2_agent = random_agent, model_agent
                # swap deck assignment so model always uses the hero it was configured with
                p1_deck, p2_deck = p2_deck, p1_deck

            final_state = game_backend.run_game(
                GameRunRequest(
                    p1_deck=p1_deck,
                    p2_deck=p2_deck,
                    p1_agent=p1_agent,
                    p2_agent=p2_agent,
                    card_db=card_db,
                    p1_seed=seed_offset + 3,
                    p2_seed=seed_offset + 4,
                    max_turns=args.max_turns,
                )
            )

            if model_seat == 2:
                # restore deck order for the next iteration
                p1_deck, p2_deck = p2_deck, p1_deck

            winner = int(final_state.winner or 0)
            turns = int(final_state.turn_number)
            model_won = winner == model_seat
            game_records.append(
                {
                    "matchup": spec["name"],
                    "game_index": game_idx,
                    "winner": winner,
                    "turns": turns,
                    "model_seat": model_seat,
                    "model_won": model_won,
                    "p1_hero": spec["p1_hero"],
                    "p2_hero": spec["p2_hero"],
                }
            )

            global_game_idx += 1
            print(
                f"[eval] matchup={spec['name']:<22} game={game_idx + 1:3d}/{args.games_per_matchup:3d} "
                f"winner=P{winner} turns={turns:3d} model_win={int(model_won)}"
            )

    by_matchup: dict[str, dict] = {}
    for spec in MATCHUP_SPECS:
        key = spec["name"]
        rows = [row for row in game_records if row["matchup"] == key]
        model_wins = sum(1 for row in rows if row["model_won"])
        by_matchup[key] = {
            "games": len(rows),
            "model_wins": int(model_wins),
            "random_wins": int(len(rows) - model_wins),
            "model_win_rate": float(model_wins / max(len(rows), 1)),
            "avg_turns": float(sum(row["turns"] for row in rows) / max(len(rows), 1)),
        }

    total_games = len(game_records)
    total_model_wins = sum(1 for row in game_records if row["model_won"])
    summary = {
        "checkpoint": str(checkpoint_path),
        "seed": base_seed,
        "device": args.device,
        "games_per_matchup": args.games_per_matchup,
        "total_games": total_games,
        "model_wins": int(total_model_wins),
        "random_wins": int(total_games - total_model_wins),
        "model_win_rate": float(total_model_wins / max(total_games, 1)),
        "matchups": by_matchup,
        "games": game_records,
    }

    with open(summary_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)

    print("=" * 72)
    print("EVALUATION COMPLETE")
    print("=" * 72)
    for key, stats in by_matchup.items():
        print(
            f"{key:<22} games={stats['games']:3d} model_wins={stats['model_wins']:3d} "
            f"win_rate={stats['model_win_rate']:.3f} avg_turns={stats['avg_turns']:.1f}"
        )
    print(f"overall_win_rate    : {summary['model_win_rate']:.3f}")
    print(f"summary             : {summary_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())