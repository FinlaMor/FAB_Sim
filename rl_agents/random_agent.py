"""Random agent for FAB self-play: picks uniformly at random from legal actions."""

import random
from typing import Optional

from engine.actions import Action


class RandomAgent:
    def __init__(self, seed=None):
        self.rng = random.Random(seed)

    def __call__(self, state, actions, context=None):
        if not isinstance(actions, (list, tuple)) or not actions:
            return actions

        if isinstance(actions[0], Action):
            return self.rng.choice(list(actions))

        return self.rng.choice(list(actions))

class UserInputAgent:
    def __call__(self, state, actions, context=None):
        if context:
            print(f"\nDecision: {context}")
        print("Options:")
        for i, action in enumerate(actions):
            print(f"  {i}: {action}")
        choice = int(input("Choose (enter number): "))
        return actions[choice]
