# Paths configuration
import os

CARD_DATA_DIR = r'C:\Users\Joseph\Desktop\FAB_Sim\card_data'
SLUG_INDEX_PATH = os.path.join(CARD_DATA_DIR, "slug_index.json")
BANNED_CARDS_PATH = os.path.join(CARD_DATA_DIR, "banned_cards.json")
DECKS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "decks")
