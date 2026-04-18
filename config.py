# Paths configuration
import os

_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CARD_DATA_DIR = os.path.join(_ROOT_DIR, "card_data")
SLUG_INDEX_PATH = os.path.join(CARD_DATA_DIR, "slug_index.msgpack")
DECKS_DIR = os.path.join(_ROOT_DIR, "decks")
