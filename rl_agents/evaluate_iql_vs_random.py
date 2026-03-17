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
from dataclasses import replace
import json
import os
from pathlib import Path
import random
import time
from typing import Optional

import torch

from config import DECKS_DIR, SLUG_INDEX_PATH
from engine.actions import Action
from engine.card import CardDB
from encoder.action_embedder import ActionEmbedder
from encoder.card_embedder import SlugVocab
from encoder.gamestate_embedder import GameStateEmbedder
from rl_agents.embedder_bundle import load_embedder_bundle
from rl_agents.game_backends import GameRunRequest, add_game_backend_args, build_game_backend
from rl_agents.iql import IQLTrainer
from rl_agents.random_agent import RandomAgent


DECK_BY_HERO = {
    "kayo_underhanded_cheat": "kayo_underhanded_cheat_CC_lite.txt",
    "oscillio_constella_intelligence": "oscillio_constella_intelligence_CC_lite.txt",
}


MATCHUP_SPECS = [
    {
        "name": "kayo_vs_kayo",
        "p1_hero": "kayo_underhanded_cheat",
        "p2_hero": "kayo_underhanded_cheat",
    },
]


def _resolve_base_seed(seed: int | None) -> int:
    if seed is not None:
        return int(seed)
    return random.SystemRandom().randrange(1, 2_147_483_647)


def _resolve_device(device_str: str):
    """Resolve device string to a torch.device, with DirectML support."""
    if device_str in ("dml", "directml"):
        try:
            import torch_directml
            return torch_directml.device()
        except ImportError:
            return torch.device("cpu")
    return torch.device(device_str)


def _default_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    try:
        import torch_directml
        return "dml"
    except ImportError:
        return "cpu"


def _card_slug(card) -> Optional[str]:
    if card is None:
        return None
    if hasattr(card, "slug"):
        return card.slug
    return str(card)


def _normalise_action_for_embedder(action: Action, player_id: int) -> Action:
    pitch_cards = [(_card_slug(card) or "") for card in (action.pitch_cards or [])]
    pitch_cards = [slug for slug in pitch_cards if slug]

    targets = [(_card_slug(target) or "") for target in (action.targets or [])]
    targets = [slug for slug in targets if slug]

    return replace(action, player_id=player_id, pitch_cards=pitch_cards, targets=targets)


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
        self.trainer = IQLTrainer.from_checkpoint(checkpoint_path, device=device)
        self.trainer.actor.eval()
        self.device = _resolve_device(device)

        self.card_db = CardDB(SLUG_INDEX_PATH)
        slug_vocab = SlugVocab.from_card_db(self.card_db)
        d_model = int(embedder_bundle.get("d_model", 128))
        self.action_embedder = ActionEmbedder(
            d_model=d_model,
            slug_vocab_size=slug_vocab.size,
            slug_vocab=slug_vocab,
        )
        self.state_embedder = GameStateEmbedder(
            d_model=d_model,
            slug_vocab_size=slug_vocab.size,
            slug_vocab=slug_vocab,
        )
        card_sd = embedder_bundle.get("card_embedder_state_dict", {})
        card_prefixed = {f"card_embedder.{k}": v for k, v in card_sd.items()}
        self.action_embedder.load_state_dict(
            {**card_prefixed, **embedder_bundle["action_embedder_state_dict"]}, strict=False
        )
        self.state_embedder.load_state_dict(
            {**card_prefixed, **embedder_bundle["state_embedder_state_dict"]}, strict=False
        )
        self.action_embedder.eval()
        self.state_embedder.eval()

        expected_state_dim = self.state_embedder.get_output_dim()
        expected_action_dim = self.action_embedder.get_output_dim()
        if self.trainer.config.state_dim != expected_state_dim:
            raise ValueError(
                f"Checkpoint state_dim={self.trainer.config.state_dim} does not match current embedder state_dim={expected_state_dim}"
            )
        if self.trainer.config.action_dim != expected_action_dim:
            raise ValueError(
                f"Checkpoint action_dim={self.trainer.config.action_dim} does not match current embedder action_dim={expected_action_dim}"
            )

    def _fallback_choice(self, options):
        if len(options) == 1:
            return options[0]
        return self.rng.choice(list(options))

    def __call__(self, state, options, context=None):
        if not isinstance(options, (list, tuple)) or not options:
            return options

        if not isinstance(options[0], Action):
            return self._fallback_choice(options)

        if len(options) == 1:
            return options[0]

        with torch.no_grad():
            state_emb = self.state_embedder(state, perspective_player=self.player_id)
            state_latent = self.trainer.encode_states(state_emb.unsqueeze(0).to(self.device).float())
            predicted_action = self.trainer.actor(state_latent).squeeze(0).cpu()

            player_counters = state.players[self.player_id].counters
            best_score = None
            best_actions: list[Action] = []

            for action in options:
                action_for_embedder = _normalise_action_for_embedder(action, self.player_id)
                action_emb = self.action_embedder(
                    action_for_embedder,
                    player_counters=player_counters,
                ).float()
                action_latent = self.trainer.encode_actions(action_emb.unsqueeze(0).to(self.device).float()).squeeze(0).cpu()
                score = -torch.sum((predicted_action - action_latent) ** 2).item()

                if best_score is None or score > best_score + 1e-9:
                    best_score = score
                    best_actions = [action]
                elif abs(score - best_score) <= 1e-9:
                    best_actions.append(action)

        return self.rng.choice(best_actions)


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