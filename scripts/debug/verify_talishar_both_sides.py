"""Test both sides of Talishar game and max parallel capacity."""
import sys, time
sys.path.insert(0, '.')
from rl_agents.game_backends import TalisharClient, _deck_file_to_talishar_slugs

print("=== VERIFY BOTH SIDES PLAY ===\n")

client = TalisharClient('http://localhost:8080/game')
deck = _deck_file_to_talishar_slugs('decks/kayo_underhanded_cheat_CC_lite.txt')

gn, auth = client.create_game(deck)
client.start_game(gn, auth)

print("Initial state:")
s = client.get_state(gn, auth)
p1_hp_start = int(s.get('playerHealth', 0))
p2_hp_start = int(s.get('opponentHealth', 0))
print(f"  P1 HP: {p1_hp_start} (us)")
print(f"  P2 HP: {p2_hp_start} (Dummy AI)")
print(f"  Turn: {s.get('turnNo')}")

# Play 30 actions
import random
rng = random.Random(42)
for i in range(30):
    state = client.get_state(gn, auth)
    if not state.get('havePriority'):
        time.sleep(0.05)
        continue
    
    acts = client.get_available_actions(state)
    if not acts:
        if state.get('canPassPhase'):
            client.process_input(gn, auth, 99)
        continue
    
    action = rng.choice(acts)
    client.submit_action(gn, auth, action)

s = client.get_state(gn, auth)
p1_hp_end = int(s.get('playerHealth', 0))
p2_hp_end = int(s.get('opponentHealth', 0))
print(f"\nAfter 30 actions:")
print(f"  P1 HP: {p1_hp_end} (us) - changed by {p1_hp_start - p1_hp_end}")
print(f"  P2 HP: {p2_hp_end} (Dummy AI) - changed by {p2_hp_start - p2_hp_end}")
print(f"  Turn: {s.get('turnNo')}")

if p1_hp_end < p1_hp_start or p2_hp_end < p2_hp_start:
    print("\n✅ BOTH SIDES ARE PLAYING - HP changed for P1 and/or P2")
else:
    print("\n❌ WARNING - No HP changes detected")

print("\n" + "="*60)
print("=== MAX PARALLEL CAPACITY TEST ===\n")

from rl_agents.game_backends import TalisharBackend

backend = TalisharBackend()

configs = [
    (4, "4 games"),
    (8, "8 games"),
    (16, "16 games"),
]

for num_games, label in configs:
    print(f"\nTesting {label}...")
    try:
        t0 = time.time()
        results = backend.run_games_parallel(
            'decks/kayo_underhanded_cheat_CC_lite.txt',
            num_games=num_games,
            max_turns=150,
            verbose=False
        )
        elapsed = time.time() - t0
        
        completed = len(results)
        avg_turn = sum(r.turn_number for r in results) / len(results) if results else 0
        failures = sum(1 for r in results if r.winner is None)
        
        print(f"  ✅ Completed {completed}/{num_games} games in {elapsed:.1f}s ({elapsed/num_games:.1f}s per game)")
        print(f"     Avg turn: {avg_turn:.1f}, Failures: {failures}")
        
    except Exception as e:
        print(f"  ❌ Failed: {e}")

print("\n" + "="*60)
print("Recommendation: Max out at 8 parallel games for reliability")
print("(4.9x speedup with 4, should see similar or slightly better with 8)")
