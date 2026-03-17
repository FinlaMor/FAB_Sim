"""Benchmark parallel Talishar game execution."""
import sys, time
sys.path.insert(0, '.')
from rl_agents.game_backends import TalisharBackend

backend = TalisharBackend()

# Sequential (1 game)
print("=== SEQUENTIAL (1 game) ===")
t0 = time.time()
results_seq = backend.run_games_parallel('decks/kayo_underhanded_cheat_CC_lite.txt', num_games=1, max_turns=150, verbose=True)
t_seq = time.time() - t0
print(f"Time: {t_seq:.1f}s")
print()

# Parallel (4 games)
print("=== PARALLEL (4 games) ===")
t0 = time.time()
results_par = backend.run_games_parallel('decks/kayo_underhanded_cheat_CC_lite.txt', num_games=4, max_turns=150, verbose=True)
t_par = time.time() - t0
print(f"Time: {t_par:.1f}s")
print()

# Stats
print("=== RESULTS ===")
print(f"Sequential:  {t_seq:.1f}s for 1 game = {t_seq:.2f}s/game")
print(f"Parallel 4:  {t_par:.1f}s for 4 games = {t_par/4:.2f}s/game")
print(f"Speedup: {t_seq / (t_par/4):.1f}x faster per-game")
print()
print("Sequential games (sample):")
for r in results_seq:
    print(f"  Game {r.game_name}: Turn {r.turn_number} Winner={r.winner} HP={r.p1_final_hp}/{r.p2_final_hp} Actions={r.total_actions}")
print("Parallel games (sample):")
for r in results_par:
    print(f"  Game {r.game_name}: Turn {r.turn_number} Winner={r.winner} HP={r.p1_final_hp}/{r.p2_final_hp} Actions={r.total_actions}")
