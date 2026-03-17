from __future__ import annotations

import json
import sys

sys.path.insert(0, ".")

import requests

from engine.card import CardDB
from rl_agents.game_backends import _deck_file_to_talishar_slugs
from rl_agents.talishar_adapter import (
    extract_talishar_actions,
    talishar_actions_to_engine_actions,
    talishar_state_to_observed_game_state,
)

base = "http://localhost:8080/game"
deck = _deck_file_to_talishar_slugs("decks/kayo_underhanded_cheat_CC_lite.txt")
card_db = CardDB()

cg = requests.post(base + "/APIs/CreateGame.php", json={"deck": deck, "format": "cc", "visibility": "private"}, timeout=10).json()
game_name = cg["gameName"]
p1_auth = cg["authKey"]
join = requests.post(base + "/APIs/JoinGame.php", json={"gameName": game_name, "playerID": 2, "deck": deck}, timeout=10).json()
p2_auth = join["authKey"]
requests.get(base + "/Start.php", params={"gameName": game_name, "playerID": 1, "authKey": p1_auth}, timeout=10)

state_p1 = requests.get(base + "/GetNextTurn.php", params={"gameName": game_name, "playerID": 1, "authKey": p1_auth, "lastUpdate": 0}, timeout=10).json()
state_p2 = requests.get(base + "/GetNextTurn.php", params={"gameName": game_name, "playerID": 2, "authKey": p2_auth, "lastUpdate": 0}, timeout=10).json()

obs = talishar_state_to_observed_game_state(state_p1, player_id=1, card_db=card_db, opponent_view=state_p2)
raw_actions = extract_talishar_actions(state_p1)
engine_actions = talishar_actions_to_engine_actions(state_p1, card_db=card_db, player_id=1)

summary = {
    "talishar_phase": state_p1.get("turnPhase"),
    "talishar_player_hand_0": (state_p1.get("playerHand") or [None])[0],
    "talishar_equipment_count": len(state_p1.get("playerEquipment") or []),
    "talishar_actions": raw_actions,
    "observed_state": {
        "step": obs.step.value,
        "turn_number": obs.turn_number,
        "active_player": obs.active_player,
        "priority_player": obs.priority_player,
        "p1_health": obs.players[1].health,
        "p2_health": obs.players[2].health,
        "p1_hand": [c.slug for c in obs.players[1].hand.cards],
        "p1_weapons": [c.slug for c in obs.players[1].weapon1.cards + obs.players[1].weapon2.cards],
        "p1_equipment": [c.slug for c in obs.players[1].equipment],
        "p2_equipment": [c.slug for c in obs.players[2].equipment],
        "opponent_hand_count": getattr(obs, "observed_opponent_hand_count", None),
    },
    "engine_actions": [
        {
            "type": a.type.value,
            "card": a.card.slug if a.card else None,
            "card_idx": a.card_idx,
            "step": a.step.value if a.step else None,
        }
        for a in engine_actions
    ],
}

print(json.dumps(summary, indent=2)[:16000])
