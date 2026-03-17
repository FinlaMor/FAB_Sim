from __future__ import annotations

import argparse
import sys
import time

sys.path.insert(0, ".")

from rl_agents.game_backends import TalisharBackend


def run_rounds(workers: int, rounds: int, max_turns: int, timeout: float) -> int:
    backend = TalisharBackend(mode="pvp", request_timeout=timeout)
    deck = "decks/kayo_underhanded_cheat_CC_lite.txt"

    for round_idx in range(rounds):
        started = time.time()
        try:
            results = backend.run_games_parallel(
                deck,
                num_games=workers,
                max_turns=max_turns,
                verbose=False,
                mode="pvp",
            )
        except Exception as exc:
            elapsed = time.time() - started
            print(
                {
                    "round": round_idx + 1,
                    "workers": workers,
                    "status": "error",
                    "elapsed_s": round(elapsed, 1),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            return 1

        elapsed = time.time() - started
        wins1 = sum(1 for r in results if r.winner == 1)
        wins2 = sum(1 for r in results if r.winner == 2)
        caps = sum(1 for r in results if r.ended_on_turn_cap)
        avg_turn = sum(r.turn_number for r in results) / len(results)
        avg_actions = sum(r.total_actions for r in results) / len(results)
        print(
            {
                "round": round_idx + 1,
                "workers": workers,
                "status": "ok",
                "elapsed_s": round(elapsed, 1),
                "per_game_s": round(elapsed / len(results), 2),
                "games_per_hour": round(len(results) / elapsed * 3600, 1),
                "wins_p1": wins1,
                "wins_p2": wins2,
                "caps": caps,
                "avg_turn": round(avg_turn, 1),
                "avg_actions": round(avg_actions, 1),
            }
        )

    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--max-turns", type=int, default=40)
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()
    return run_rounds(args.workers, args.rounds, args.max_turns, args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
