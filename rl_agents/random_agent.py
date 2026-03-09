"""Random agent for FAB self-play: picks uniformly at random from legal actions."""

import random
from typing import Optional


class RandomAgent:
    def __init__(self, seed=None):
        self.rng = random.Random(seed)

    def __call__(self, state, actions, context=None):
        return self.rng.choice(actions)

class UserInputAgent:
    def __call__(self, state, actions, context=None):
        if context:
            print(f"\nDecision: {context}")
        print("Options:")
        for i, action in enumerate(actions):
            print(f"  {i}: {action}")
        choice = int(input("Choose (enter number): "))
        return actions[choice]
