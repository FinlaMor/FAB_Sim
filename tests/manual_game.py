import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import SLUG_INDEX_PATH, DECKS_DIR
from engine.card import CardDB, Card
from engine.engine import new_game
from engine.deck import load_deck, create_player
from engine.actions import legal_actions, Action
from rl_agents.random_agent import RandomAgent, UserInputAgent

user_agent = UserInputAgent()

if __name__ == "__main__":
    # Example usage
    card_db = CardDB(SLUG_INDEX_PATH)
    p1_deck_path = os.path.join(DECKS_DIR, "kayo_underhanded_cheat_CC_lite.txt")
    p2_deck_path = os.path.join(DECKS_DIR, "kayo_underhanded_cheat_CC_lite.txt")

    game_state = new_game(p1_deck_path,
                          p2_deck_path,
                          user_agent,
                          user_agent,
                          card_db=card_db
                          )
            
