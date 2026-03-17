"""Run N rounds of M games through Talishar with random hero deck pairings."""
from __future__ import annotations

import glob
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(__file__))

from rl_agents.game_backends import (
    TalisharClient,
    _deck_file_to_talishar_slugs,
    _run_talishar_pvp_game,
    _NullTalisharAgent,
)

DECK_DIR = os.path.join(os.path.dirname(__file__), "decks")
ALL_DECKS = sorted(glob.glob(os.path.join(DECK_DIR, "*.txt")))


def hero_label(deck_path: str) -> str:
    return os.path.basename(deck_path).replace("_CC_lite.txt", "").replace("_CC.txt", "")


def run_one_game(seed: int, p1_deck_path: str, p2_deck_path: str, max_turns: int, timeout: float):
    client = TalisharClient(request_timeout=timeout)
    p1_sub = _deck_file_to_talishar_slugs(p1_deck_path)
    p2_sub = _deck_file_to_talishar_slugs(p2_deck_path)
    result = _run_talishar_pvp_game(
        client, p1_sub, p2_sub,
        p1_agent=_NullTalisharAgent(),
        p2_agent=_NullTalisharAgent(),
        p1_seed=seed,
        p2_seed=seed + 50_000,
        max_turns=max_turns,
    )
    return result, p1_deck_path, p2_deck_path


def run_round(round_num: int, num_games: int, rng: random.Random,
              max_turns: int = 30, timeout: float = 30.0, workers: int = 2):
    print(f"\n{'='*70}")
    print(f"  ROUND {round_num}  —  {num_games} games, random hero decks, max {max_turns} turns")
    print(f"{'='*70}")

    pairings = []
    for i in range(num_games):
        p1 = rng.choice(ALL_DECKS)
        p2 = rng.choice(ALL_DECKS)
        seed = rng.randint(1, 999_999)
        pairings.append((seed, p1, p2))

    results = []
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {}
        for idx, (seed, p1, p2) in enumerate(pairings):
            f = pool.submit(run_one_game, seed, p1, p2, max_turns, timeout)
            futures[f] = idx

        for f in as_completed(futures):
            idx = futures[f]
            try:
                res, p1_path, p2_path = f.result()
                results.append((idx, res, p1_path, p2_path, None))
            except Exception as exc:
                results.append((idx, None, pairings[idx][1], pairings[idx][2], exc))

    elapsed = time.time() - t0
    results.sort(key=lambda x: x[0])

    # Print per-game results
    print(f"\n{'#':>3}  {'P1 Hero':<35} {'P2 Hero':<35} {'W':>2} {'Turns':>5} {'HP':>9} {'Acts':>5} {'Cap':>4}")
    print("-" * 110)
    wins = {1: 0, 2: 0, "cap": 0, "err": 0}
    hero_wins: dict[str, int] = {}
    hero_games: dict[str, int] = {}

    for idx, res, p1_path, p2_path, err in results:
        p1_label = hero_label(p1_path)
        p2_label = hero_label(p2_path)
        if err:
            print(f"{idx+1:>3}  {p1_label:<35} {p2_label:<35} {'ERR':>2}  — {type(err).__name__}: {err}")
            wins["err"] += 1
            continue

        w = res.winner
        tag = str(w) if w else "-"
        cap = "Y" if res.ended_on_turn_cap else ""
        print(f"{idx+1:>3}  {p1_label:<35} {p2_label:<35} {tag:>2} {res.turn_number:>5} {res.p1_final_hp:>4}/{res.p2_final_hp:<4} {res.total_actions:>5} {cap:>4}")

        for label in (p1_label, p2_label):
            hero_games[label] = hero_games.get(label, 0) + 1
        if w == 1:
            wins[1] += 1
            hero_wins[p1_label] = hero_wins.get(p1_label, 0) + 1
        elif w == 2:
            wins[2] += 1
            hero_wins[p2_label] = hero_wins.get(p2_label, 0) + 1
        else:
            wins["cap"] += 1

    # Summary
    print(f"\n--- Round {round_num} Summary ---")
    print(f"  Elapsed: {elapsed:.1f}s  ({elapsed/num_games:.1f}s per game)")
    print(f"  P1 wins: {wins[1]}   P2 wins: {wins[2]}   Turn-cap draws: {wins['cap']}   Errors: {wins['err']}")
    print(f"\n  Hero win rates:")
    for h in sorted(hero_games):
        w = hero_wins.get(h, 0)
        g = hero_games[h]
        print(f"    {h:<40} {w}/{g}  ({100*w/g:.0f}%)")
    print()
    return results


def main():
    if not ALL_DECKS:
        print(f"ERROR: no deck files found in {DECK_DIR}")
        return 1

    print(f"Found {len(ALL_DECKS)} decks:")
    for d in ALL_DECKS:
        print(f"  {hero_label(d)}")

    master_rng = random.Random(2026_0314)

    round1 = run_round(1, 16, master_rng)
    round2 = run_round(2, 16, master_rng)

    # Cross-round summary
    all_results = round1 + round2
    total_ok = sum(1 for _, r, *_ in all_results if r is not None)
    total_err = sum(1 for _, r, *_ in all_results if r is None)
    total_p1 = sum(1 for _, r, *_ in all_results if r and r.winner == 1)
    total_p2 = sum(1 for _, r, *_ in all_results if r and r.winner == 2)
    total_cap = sum(1 for _, r, *_ in all_results if r and r.winner is None)
    print(f"\n{'='*70}")
    print(f"  OVERALL: {total_ok} completed, {total_err} errors")
    print(f"  P1 wins: {total_p1}   P2 wins: {total_p2}   Cap/draw: {total_cap}")
    print(f"{'='*70}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
