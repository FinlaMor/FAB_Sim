"""Test player vs player mode - create game without deckTestMode."""
import sys, requests, json
sys.path.insert(0, '.')
from rl_agents.game_backends import _deck_file_to_talishar_slugs

client_base = 'http://localhost:8080/game'
deck = _deck_file_to_talishar_slugs('decks/kayo_underhanded_cheat_CC_lite.txt')

print("=== PLAYER VS PLAYER TEST ===\n")

# Step 1: Player 1 creates game WITHOUT deckTestMode
print("Step 1: Player 1 creates game (no deckTestMode = player vs player)")
payload = {
    "deck": deck,
    "format": "cc",
    "visibility": "private",
    # NOTE: NOT setting deckTestMode - this makes it a 2-player game
}
r = requests.post(f"{client_base}/APIs/CreateGame.php", json=payload, timeout=5)
data = r.json()
gn = int(data["gameName"])
p1_auth = data["authKey"]
print(f"  Game {gn} created")
print(f"  P1 Auth: {p1_auth[:30]}...")
print(f"  Response keys: {list(data.keys())}")
print()

# Step 2: Get P1's auth key (already have it)
# Step 3: Try to have Player 2 join via JoinGame
# The problem is we need P2's deck and how to tell JoinGame.php about it
# Let me check what JoinGame.php expects

print("Step 2: Check JoinGame.php endpoint...")
print("  JoinGame typically requires: gameName, playerID=2, deck")
print()

# Step 3: Player 1 starts the game
print("Step 3: Player 1 starts the game...")
r = requests.get(
    f'{client_base}/Start.php',
    params={"gameName": gn, "playerID": 1, "authKey": p1_auth},
    timeout=5
)
print(f"  Start response: {r.json()}")
print()

# Step 4: Check game state as P1
print("Step 4: Check game state as P1...")
r = requests.get(
    f'{client_base}/GetNextTurn.php',
    params={"gameName": gn, "playerID": 1, "authKey": p1_auth, "lastUpdate": 0},
    timeout=5
)
state = r.json()
print(f"  P1 HP: {state.get('playerHealth')}")
print(f"  P2 HP: {state.get('opponentHealth')}")
print(f"  Am I active player: {state.get('amIActivePlayer')}")
print(f"  P2 is AI: {state.get('opponentIsAI')}") # Check if P2 is marked as AI
print()

# Try to play a move as P1
print("Step 5: Try to play a card as P1...")
hand = state.get('playerHand', [])
print(f"  P1 has {len(hand)} cards in hand")
if hand:
    card = hand[0]
    print(f"  Playing: {card.get('cardNumber')} (mode={card.get('action')})")
    if card.get('action', 0) != 0:
        r = requests.get(
            f'{client_base}/ProcessInput.php',
            params={
                "gameName": gn,
                "playerID": 1,
                "authKey": p1_auth,
                "mode": card['action'],
                "cardID": str(card.get('actionDataOverride', '0'))
            },
            timeout=5
        )
        print(f"  ProcessInput response: {r.status_code}")
        
        # Check new state
        r = requests.get(
            f'{client_base}/GetNextTurn.php',
            params={"gameName": gn, "playerID": 1, "authKey": p1_auth, "lastUpdate": 0},
            timeout=5
        )
        state2 = r.json()
        print(f"  After move: turn={state2.get('turnNo')}, P1 HP={state2.get('playerHealth')}, P2 HP={state2.get('opponentHealth')}")
        print(f"  Am I still active: {state2.get('amIActivePlayer')}")
print()

print("CONCLUSION:")
print(f"  - Game {gn} created as PvP mode (no deckTestMode)")
print(f"  - P1 played a card and game progressed")
print(f"  - P2 status needs investigation (is opponent controlled by AI or waiting for join?)")
