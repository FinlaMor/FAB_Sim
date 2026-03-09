"""Run a test game with random agents, printing all options and choices."""
import os
import sys
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import SLUG_INDEX_PATH, DECKS_DIR
from engine.card import CardDB
from engine.engine import new_game

d_file = 'C:\\Users\\Joseph\\Desktop\\FAB_Sim_v2\\random_game_output.txt'

def fmt_action(a):
    """Short format for an action."""
    if not hasattr(a, 'type'):
        return str(a)
    parts = [a.type.value]
    if a.card:
        parts.append(a.card.name)
    if a.pitch_cards:
        parts.append(f"pitch={a.pitch_cards}")
    if a.target:
        parts.append(f"target={a.target.name}")
    if a.slot:
        parts.append(f"slot={a.slot}")
    if a.card_list:
        parts.append(f"cards=[{', '.join(c.name for c in a.card_list)}]")
    return ' | '.join(parts)

class VerboseRandomAgent:
    """Random agent that prints all options and its choice."""
    def __init__(self, name, seed=None):
        self.name = name
        self.rng = random.Random(seed)

    def __call__(self, state, options, context=None):
        with open(d_file,'a') as f:
            print(f"\n--- {self.name} | {state.step.value} | Turn {state.turn_number} ---", file=f)
            if isinstance(options, (list, tuple)) and len(options) > 0:
                print(f'{context}')
                for i, opt in enumerate(options):
                    print(f"  [{i}] {fmt_action(opt)}", file=f)
            else:
                print(f"  Options: {options}", file=f)
            choice = self.rng.choice(options) if isinstance(options, (list, tuple)) else options
            print(f"  => {fmt_action(choice)}", file=f)
        return choice


if __name__ == "__main__":
    with open(d_file,'a') as f:
        card_db = CardDB(SLUG_INDEX_PATH)
        p1_deck_path = os.path.join(DECKS_DIR, "kayo_underhanded_cheat_CC_lite.txt")
        p2_deck_path = os.path.join(DECKS_DIR, "kayo_underhanded_cheat_CC_lite.txt")

        agent1 = VerboseRandomAgent("Player 1", seed=42)
        agent2 = VerboseRandomAgent("Player 2", seed=123)

        print("Starting test game...", file=f)
        try:
            game_state = new_game(
                p1_deck_path,
                p2_deck_path,
                agent1,
                agent2,
                card_db=card_db,
                debug_file=d_file
            )
            print(f"\n=== Game Over ===", file=f)
            print(f"Winner: Player {game_state.winner}", file=f)
            print(f"P1 health: {game_state.players[1].health}", file=f)
            print(f"P2 health: {game_state.players[2].health}", file=f)
            print(f"Turns: {game_state.turn_number}", file=f)
        except Exception as e:
            import traceback
            print(f"\n=== ERROR ===", file=f)
            traceback.print_exc()