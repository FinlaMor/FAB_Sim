"""Test max parallel games and verify both sides play (player vs player)."""
import sys, time
sys.path.insert(0, '.')
from rl_agents.game_backends import TalisharClient, _deck_file_to_talishar_slugs

client = TalisharClient('http://localhost:8080/game')
deck = _deck_file_to_talishar_slugs('decks/kayo_underhanded_cheat_CC_lite.txt')

print("=== SCALING TEST ===")
for num_games in [4, 8, 16]:
    print(f"\n{num_games} games in parallel...")
    t0 = time.time()
    from concurrent.futures import ThreadPoolExecutor
    from rl_agents.game_backends import _run_talishar_random_game
    import random
    
    with ThreadPoolExecutor(max_workers=num_games) as executor:
        futures = [
            executor.submit(_run_talishar_random_game, client, deck, max_turns=150, rng=random.Random(i), verbose=False)
            for i in range(num_games)
        ]
        results = [f.result() for f in futures]
    
    elapsed = time.time() - t0
    avg_per_game = elapsed / num_games
    print(f"  Total: {elapsed:.1f}s | Per-game: {avg_per_game:.2f}s | Throughput: {num_games/elapsed:.1f} games/min")

print("\n\n=== PLAYER VS PLAYER TEST ===")
print("Creating 2-player game with Kayo on both sides...")
print()

# Create a game with 2 players (not vs dummy)
# The key is playerID=1 creates, playerID=2 joins
payload = {
    "deck": deck,
    "deckTestMode": "1",
    "format": "cc",
    "visibility": "private",
}
r = client._session.post(f"{client.base_url}/APIs/CreateGame.php", json=payload, timeout=5)
data = r.json()
gn = int(data["gameName"])
p1_auth = data["authKey"]  # Player 1
print(f"Game {gn} created. Player 1 auth: {p1_auth[:20]}...")

# Try to get player 2 auth key - need to check if we can join as player 2
# In Talishar, there's a JoinGame endpoint that would let player 2 join
# Let's check if playerID=1 started the game
print("\nStarting game...")
r = client._session.get(
    f"{client.base_url}/Start.php",
    params={"gameName": gn, "playerID": 1, "authKey": p1_auth},
    timeout=5,
)
print(f"Start response: {r.json()}")

# Get state as player 1
print("\nGetting initial state as Player 1...")
r = client._session.get(
    f"{client.base_url}/GetNextTurn.php",
    params={"gameName": gn, "playerID": 1, "authKey": p1_auth, "lastUpdate": 0},
    timeout=5,
)
state1 = r.json()
print(f"Player 1 view: HP={state1.get('playerHealth')}/{state1.get('opponentHealth')}")
print(f"  amIActivePlayer: {state1.get('amIActivePlayer')}")
print(f"  havePriority: {state1.get('havePriority')}")
print(f"  opponentHand count: {len(state1.get('opponentHand', []))}")

# Try to get state as player 2 (likely we don't know the auth key yet)
# The game probably needs player 2 to join via a join endpoint
print("\nNote: To play player vs player, we need:")
print("  1. Player 1 creates and starts the game")
print("  2. Player 2 joins via JoinGame.php with same gameID")
print("  3. Get Player 2's auth key")
print("  4. Both players take turns")
print("\nLooking for JoinGame.php...")

import os
talishar_path = "third_party/Talishar_official/"
apis_path = os.path.join(talishar_path, "APIs")
if os.path.exists(apis_path):
    files = os.listdir(apis_path)
    print(f"Found {len(files)} files in APIs/:")
    for f in sorted(files)[:20]:
        print(f"  {f}")
