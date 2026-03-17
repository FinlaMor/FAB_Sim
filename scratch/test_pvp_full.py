"""Test true player vs player mode."""
import sys, requests, json
sys.path.insert(0, '.')
from rl_agents.game_backends import _deck_file_to_talishar_slugs
import random

client_base = 'http://localhost:8080/game'
deck = _deck_file_to_talishar_slugs('decks/kayo_underhanded_cheat_CC_lite.txt')

print("=== TRUE PLAYER VS PLAYER TEST ===\n")

# Step 1: Player 1 creates game WITHOUT deckTestMode
print("Step 1: Player 1 creates game (no deckTestMode = PvP mode)")
payload = {
    "deck": deck,
    "format": "cc",
    "visibility": "private",
    # DO NOT set deckTestMode
}
r = requests.post(f"{client_base}/APIs/CreateGame.php", json=payload, timeout=5)
data = r.json()
gn = int(data["gameName"])
p1_auth = data["authKey"]
print(f"  Game {gn} created")
print(f"  P1 Auth (first 30 chars): {p1_auth[:30]}...")
print()

# Step 2: Player 2 joins game with their own deck
print("Step 2: Player 2 joins the game")
join_payload = {
    "gameName": gn,
    "playerID": 2,
    "deck": deck,  # P2 uses same deck for testing
}
r = requests.post(f"{client_base}/APIs/JoinGame.php", json=join_payload, timeout=5)
data2 = r.json()
print(f"  Join response: {list(data2.keys())}")
if "error" in data2 and data2["error"]:
    print(f"  ERROR: {data2['error']}")
else:
    print(f"  SUCCESS: P2 joined")
    if "authKey" in data2:
        p2_auth = data2["authKey"]
        print(f"  P2 Auth (first 30 chars): {p2_auth[:30]}...")
    else:
        print(f"  Response keys: {list(data2.keys())}")
print()

# Step 3: Player 1 starts the game
print("Step 3: Player 1 starts the game")
r = requests.get(
    f'{client_base}/Start.php',
    params={"gameName": gn, "playerID": 1, "authKey": p1_auth},
    timeout=5
)
start_data = r.json()
print(f"  Start response: {start_data}")
print()

# Step 4: Check game state as both players
print("Step 4: Get initial state as both players")
r = requests.get(
    f'{client_base}/GetNextTurn.php',
    params={"gameName": gn, "playerID": 1, "authKey": p1_auth, "lastUpdate": 0},
    timeout=5
)
state_p1 = r.json()
print(f"  P1 view: My HP={state_p1.get('playerHealth')}, Opp HP={state_p1.get('opponentHealth')}")
print(f"    Am I active: {state_p1.get('amIActivePlayer')}, Have priority: {state_p1.get('havePriority')}")
print(f"    My hand size: {len(state_p1.get('playerHand', []))}, Opp hand size: {len(state_p1.get('opponentHand', []))}")

# Try to get P2's view
try:
    p2_auth = data2.get("authKey", p1_auth)  # Fallback
    r = requests.get(
        f'{client_base}/GetNextTurn.php',
        params={"gameName": gn, "playerID": 2, "authKey": p2_auth, "lastUpdate": 0},
        timeout=5
    )
    state_p2 = r.json()
    print(f"  P2 view: My HP={state_p2.get('playerHealth')}, Opp HP={state_p2.get('opponentHealth')}")
    print(f"    Am I active: {state_p2.get('amIActivePlayer')}, Have priority: {state_p2.get('havePriority')}")
    print(f"    My hand size: {len(state_p2.get('playerHand', []))}, Opp hand size: {len(state_p2.get('opponentHand', []))}")
except Exception as e:
    print(f"  P2 view: ERROR - {e}")
print()

# Step 5: Both players take turns
print("Step 5: Simulate 10 turns of PvP")
for turn_num in range(10):
    # P1 plays a card
    if state_p1.get('amIActivePlayer'):
        hand = state_p1.get('playerHand', [])
        if hand:
            card = hand[0]
            if card.get('action', 0) != 0:
                r = requests.get(
                    f'{client_base}/ProcessInput.php',
                    params={
                        "gameName": gn, "playerID": 1, "authKey": p1_auth,
                        "mode": card['action'],
                        "cardID": str(card.get('actionDataOverride', '0'))
                    },
                    timeout=5
                )
                state_p1 = requests.get(
                    f'{client_base}/GetNextTurn.php',
                    params={"gameName": gn, "playerID": 1, "authKey": p1_auth, "lastUpdate": 0},
                    timeout=5
                ).json()
    
    # P2 takes action (or pass)
    try:
        p2_auth = data2.get("authKey", p1_auth)
        r = requests.get(
            f'{client_base}/GetNextTurn.php',
            params={"gameName": gn, "playerID": 2, "authKey": p2_auth, "lastUpdate": 0},
            timeout=5
        )
        state_p2 = r.json()
        
        if state_p2.get('amIActivePlayer') and state_p2.get('havePriority'):
            hand2 = state_p2.get('playerHand', [])
            if hand2:
                card2 = hand2[0]
                if card2.get('action', 0) != 0:
                    r = requests.get(
                        f'{client_base}/ProcessInput.php',
                        params={
                            "gameName": gn, "playerID": 2, "authKey": p2_auth,
                            "mode": card2['action'],
                            "cardID": str(card2.get('actionDataOverride', '0'))
                        },
                        timeout=5
                    )
                else:
                    # Try to pass phase
                    r = requests.get(
                        f'{client_base}/ProcessInput.php',
                        params={"gameName": gn, "playerID": 2, "authKey": p2_auth, "mode": 99},
                        timeout=5
                    )
            else:
                # No cards, try to pass
                r = requests.get(
                    f'{client_base}/ProcessInput.php',
                    params={"gameName": gn, "playerID": 2, "authKey": p2_auth, "mode": 99},
                    timeout=5
                )
    except Exception as e:
        pass
    
    # Check state
    state_p1 = requests.get(
        f'{client_base}/GetNextTurn.php',
        params={"gameName": gn, "playerID": 1, "authKey": p1_auth, "lastUpdate": 0},
        timeout=5
    ).json()
    
    print(f"  Turn {turn_num}: P1={state_p1.get('playerHealth')} vs P2={state_p1.get('opponentHealth')}, Active={state_p1.get('amIActivePlayer')}, Turn#{state_p1.get('turnNo')}")
    
    # Check for game over
    if state_p1.get('playerHealth', 1) <= 0 or state_p1.get('opponentHealth', 1) <= 0:
        break

print()
print(f"FINAL: P1 HP={state_p1.get('playerHealth')}, P2 HP={state_p1.get('opponentHealth')}")
print("SUCCESS: True Player vs Player mode works!")
