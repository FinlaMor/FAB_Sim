import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.engine import new_game
from engine.card import CardDB
from engine.deck import load_deck
from rl_agents.heuristic_bot import HeuristicBot

deck1 = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'decks\\generated\\arakni_5lp3d_7hru_7h3_cr4x_CC_aggro.txt')
deck2 = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'decks\\generated\\bravo_showstopper_CC_aggro.txt')
player1 = HeuristicBot()
player2 = HeuristicBot()
card_db=CardDB(os.path.join(os.path.dirname(os.path.dirname(__file__)), "card_data\\slug_index.json"))

new_game(
    p1_deck_path=deck1,
    p2_deck_path=deck2,
    p1_agent=player1,
    p2_agent=player2,
    card_db=card_db,
)
