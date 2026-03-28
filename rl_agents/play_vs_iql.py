"""Play an interactive game against a trained IQL agent.

Launches a single game where a human player (via UserInputAgent) faces off
against an IQL-trained policy, a heuristic bot, or a random agent.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import torch

from config import DECKS_DIR, SLUG_INDEX_PATH
from engine.card import CardDB
from rl_agents.embedder_bundle import load_embedder_bundle
from rl_agents.evaluate_iql_vs_random import IQLPolicyAgent
from rl_agents.game_backends import GameRunRequest, build_game_backend
from rl_agents.heuristic_bot import HeuristicBot
from rl_agents.random_agent import RandomAgent, UserInputAgent
from rl_agents.utils.device import default_device as _default_device
from rl_agents.utils.seed import resolve_base_seed as _resolve_base_seed


def _find_deck_files() -> list[Path]:
    """Return all .txt deck files from DECKS_DIR and DECKS_DIR/generated/."""
    results: list[Path] = []
    decks_path = Path(DECKS_DIR)
    if decks_path.is_dir():
        results.extend(sorted(decks_path.glob("*.txt")))
        generated = decks_path / "generated"
        if generated.is_dir():
            results.extend(sorted(generated.glob("*.txt")))
    return results


def _resolve_deck(name: str) -> str:
    """Resolve a deck name or path to a full deck file path."""
    # If it's already a valid path, use it directly
    if os.path.isfile(name):
        return name

    # Search DECKS_DIR and DECKS_DIR/generated/
    for directory in [DECKS_DIR, os.path.join(DECKS_DIR, "generated")]:
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate):
            return candidate
        # Try appending .txt
        if not name.endswith(".txt"):
            candidate_txt = candidate + ".txt"
            if os.path.isfile(candidate_txt):
                return candidate_txt

    raise FileNotFoundError(
        f"Deck not found: {name!r}. Use --list-decks to see available decks."
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Play an interactive game against an IQL agent (or other opponent)"
    )
    parser.add_argument(
        "--checkpoint", type=str, default="",
        help="Path to IQL checkpoint_final.pt (required when --opponent=iql)",
    )
    parser.add_argument(
        "--deck", type=str, default="",
        help="Deck file name or path (defaults to first available deck)",
    )
    parser.add_argument(
        "--seat", type=int, default=1, choices=[1, 2],
        help="Seat for the human player (1 or 2)",
    )
    parser.add_argument(
        "--opponent", type=str, default="random", choices=["iql", "heuristic", "random"],
        help="Opponent type",
    )
    parser.add_argument(
        "--list-decks", action="store_true",
        help="List available decks and exit",
    )
    parser.add_argument(
        "--max-turns", type=int, default=200,
        help="Turn cap to pass to the engine",
    )
    parser.add_argument(
        "--device", type=str, default=_default_device(),
        help="Torch device for the IQL actor",
    )
    parser.add_argument(
        "--embedder-bundle", type=str, default="",
        help="Optional embedder bundle path (required for IQL checkpoints without one)",
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="Base RNG seed (defaults to a fresh per-run seed)",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    # --list-decks: show available decks and exit
    if args.list_decks:
        deck_files = _find_deck_files()
        if not deck_files:
            print("No deck files found.")
        else:
            print("Available decks:")
            for df in deck_files:
                print(f"  {df.name}")
        return 0

    # Resolve deck
    if args.deck:
        deck_path = _resolve_deck(args.deck)
    else:
        deck_files = _find_deck_files()
        if not deck_files:
            print("ERROR: No deck files found. Provide --deck or add decks to the decks/ directory.")
            return 1
        deck_path = str(deck_files[0])

    base_seed = _resolve_base_seed(args.seed)
    human_seat = args.seat
    opponent_seat = 2 if human_seat == 1 else 1

    # Build opponent agent
    if args.opponent == "iql":
        if not args.checkpoint:
            print("ERROR: --checkpoint is required when --opponent=iql")
            return 1
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
                "Checkpoint does not contain an embedder bundle and --embedder-bundle was not provided."
            )
        opponent_agent = IQLPolicyAgent(
            checkpoint_path=str(checkpoint_path),
            player_id=opponent_seat,
            device=args.device,
            seed=base_seed + 1,
            embedder_bundle=embedder_bundle,
        )
    elif args.opponent == "heuristic":
        opponent_agent = HeuristicBot(seed=base_seed + 1)
    else:
        opponent_agent = RandomAgent(seed=base_seed + 1)

    human_agent = UserInputAgent()
    card_db = CardDB(SLUG_INDEX_PATH)

    if human_seat == 1:
        p1_agent, p2_agent = human_agent, opponent_agent
    else:
        p1_agent, p2_agent = opponent_agent, human_agent

    game_backend = build_game_backend("local")

    print("=" * 60)
    print("PLAY VS OPPONENT")
    print("=" * 60)
    print(f"deck       : {deck_path}")
    print(f"your seat  : Player {human_seat}")
    print(f"opponent   : {args.opponent}")
    print(f"max_turns  : {args.max_turns}")
    print(f"seed       : {base_seed}")
    print("=" * 60)

    req = GameRunRequest(
        p1_deck=deck_path,
        p2_deck=deck_path,
        p1_agent=p1_agent,
        p2_agent=p2_agent,
        card_db=card_db,
        p1_seed=base_seed + 2,
        p2_seed=base_seed + 3,
        max_turns=args.max_turns,
    )

    final_state = game_backend.run_game(req)

    winner = int(final_state.winner or 0)
    turns = int(final_state.turn_number)
    p1_hp = int(final_state.players[1].hp)
    p2_hp = int(final_state.players[2].hp)

    print("=" * 60)
    print("GAME OVER")
    print("=" * 60)
    if winner == 0:
        print("Result     : Draw / Turn cap reached")
    elif winner == human_seat:
        print("Result     : YOU WIN!")
    else:
        print("Result     : You lost.")
    print(f"Winner     : Player {winner}")
    print(f"Turns      : {turns}")
    print(f"P1 final HP: {p1_hp}")
    print(f"P2 final HP: {p2_hp}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nGame aborted.")
        raise SystemExit(130)
