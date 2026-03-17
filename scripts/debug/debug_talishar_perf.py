"""Profile Talishar request times to identify bottlenecks."""
import sys, random, time
sys.path.insert(0, '.')
from rl_agents.game_backends import TalisharClient, _deck_file_to_talishar_slugs

client = TalisharClient('http://localhost:8080/game')
deck = _deck_file_to_talishar_slugs('decks/kayo_underhanded_cheat_CC_lite.txt')

gn, auth = client.create_game(deck)
client.start_game(gn, auth)

times = {'get_state': [], 'get_actions': [], 'submit': []}

for i in range(20):
    # Time get_state
    t0 = time.time()
    state = client.get_state(gn, auth)
    t1 = time.time()
    times['get_state'].append(t1 - t0)

    # Time get_available_actions (local)
    t0 = time.time()
    actions = client.get_available_actions(state)
    t1 = time.time()
    times['get_actions'].append(t1 - t0)

    if not actions:
        break

    # Time submit_action (ProcessInput + implicit get_state)
    action = random.choice(actions)
    t0 = time.time()
    client.submit_action(gn, auth, action)
    t1 = time.time()
    times['submit'].append(t1 - t0)

print("=== TIMING (20 actions) ===")
print(f"get_state:     {sum(times['get_state'])/len(times['get_state']):.3f}s avg ({min(times['get_state']):.3f}s min, {max(times['get_state']):.3f}s max)")
print(f"get_actions:   {sum(times['get_actions'])/len(times['get_actions']):.3f}s avg ({min(times['get_actions']):.3f}s min, {max(times['get_actions']):.3f}s max)")
print(f"submit:        {sum(times['submit'])/len(times['submit']):.3f}s avg ({min(times['submit']):.3f}s min, {max(times['submit']):.3f}s max)")
print(f"Total avg per action: {(sum(times['get_state']) + sum(times['submit'])) / len(times['submit']):.3f}s")
