"""Heuristic bot for the local FAB game engine.

Maximizes damage output on its turn and blocks efficiently with expendable
cards.  Implements the local engine agent interface: __call__(state, actions).

Strategy:
  Action phase → play the highest-damage attack affordable; prefer Go Again
                  chains to stack multiple attacks per turn.  Use weapon when
                  it out-damages hand attacks.
  Defend phase → pick the cheapest defense combo that covers incoming damage,
                  preferring equipment over hand cards and sacrificing low-power
                  cards first.
  Reaction     → play the best attack/defense reaction available, else pass.
  Otherwise    → pass (let the engine advance).
"""
from __future__ import annotations

import random
from typing import Optional

from engine.actions import Action, ActionType
from engine.state import GameState, Step


class HeuristicBot:
    """Greedy damage-first heuristic agent for the local FAB engine."""

    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)

    # ------------------------------------------------------------------
    # Engine agent interface
    # ------------------------------------------------------------------

    def __call__(self, state: GameState, actions, context=None):
        if not isinstance(actions, (list, tuple)) or not actions:
            return actions

        # Non-Action choices (e.g. "who goes first?") — pick randomly
        if not isinstance(actions[0], Action):
            return self._rng.choice(list(actions))

        step = state.step

        if step == Step.ACTION:
            pick = self._pick_action_phase(state, actions)
        elif step == Step.COMBAT_DEFEND:
            pick = self._pick_defend_phase(state, actions)
        elif step == Step.COMBAT_REACTION:
            pick = self._pick_reaction_phase(state, actions)
        else:
            pick = None

        if pick is not None:
            return pick

        # Fallback: pass if available, else random
        for a in actions:
            if a.type in (ActionType.PASS, ActionType.REACTION_PASS):
                return a
        return self._rng.choice(list(actions))

    # ------------------------------------------------------------------
    # Action phase — maximise damage output
    # ------------------------------------------------------------------

    def _pick_action_phase(self, state: GameState, actions: list[Action]) -> Optional[Action]:
        attack_actions: list[Action] = []

        for a in actions:
            if a.type == ActionType.ATTACK_WEAPON:
                attack_actions.append(a)
            elif a.type in (ActionType.PLAY_CARD, ActionType.PLAY_ARSENAL):
                card = a.card
                if card and card.is_attack and (card.power or 0) > 0:
                    attack_actions.append(a)

        if not attack_actions:
            return None  # nothing to attack with — fallback will pass

        # Score each attack action:
        #   primary  = effective power (damage)
        #   secondary = Go Again bonus (chaining = more total damage)
        #   tertiary = fewer pitch cards (preserve hand for future attacks)
        def attack_score(a: Action) -> tuple:
            card = a.card
            power = card.power or 0 if card else 0
            go_again = 1 if (card and card.has_go_again) else 0
            pitch_count = len(a.pitch_cards) if a.pitch_cards else 0
            return (power, go_again, -pitch_count)

        return max(attack_actions, key=attack_score)

    # ------------------------------------------------------------------
    # Defend phase — block with cards we don't need
    # ------------------------------------------------------------------

    def _pick_defend_phase(self, state: GameState, actions: list[Action]) -> Optional[Action]:
        combat = state.combat
        if combat is None:
            return None

        incoming = combat.attack_power or 0

        # Separate defense actions from pass
        defend_actions = [a for a in actions if a.type == ActionType.DEFEND_CARDS]
        pass_action = next((a for a in actions if a.type == ActionType.PASS), None)

        if not defend_actions:
            return pass_action

        # If incoming damage is 0 or less, don't bother blocking
        if incoming <= 0:
            return pass_action

        # Score each defense combo:
        #   We want to block enough damage without wasting good cards.
        #   "Cards we don't need" = low power, high pitch (pitch fodder).
        def defense_score(a: Action) -> tuple:
            cards = a.card_list or []
            total_def = sum((c.defense or 0) for c in cards)
            # Total attack power we're giving up by blocking with these cards
            power_sacrificed = sum((c.power or 0) for c in cards)
            # Count of equipment vs hand cards (equipment = free blocks)
            equip_count = sum(1 for c in cards if c.is_equipment)
            hand_count = len(cards) - equip_count

            # How well this covers the attack (capped at incoming)
            effective_block = min(total_def, incoming)
            # Wasted defense (over-blocking)
            waste = max(0, total_def - incoming)

            return (
                effective_block,      # maximize damage prevented
                -power_sacrificed,    # minimize power given up
                equip_count,          # prefer equipment blocks
                -hand_count,          # fewer hand cards used
                -waste,               # minimize over-blocking
            )

        best = max(defend_actions, key=defense_score)

        # Only block if it's worth it: block at least 1 damage
        best_cards = best.card_list or []
        best_def = sum((c.defense or 0) for c in best_cards)
        if best_def <= 0:
            return pass_action

        return best

    # ------------------------------------------------------------------
    # Reaction phase — play best reaction, else pass
    # ------------------------------------------------------------------

    def _pick_reaction_phase(self, state: GameState, actions: list[Action]) -> Optional[Action]:
        # Attack reactions: pick highest power boost
        attack_reactions = [
            a for a in actions
            if a.type == ActionType.PLAY_ATTACK_REACTION and a.card
        ]
        if attack_reactions:
            return max(attack_reactions, key=lambda a: a.card.power or 0)

        # Defense reactions: pick highest defense
        defense_reactions = [
            a for a in actions
            if a.type == ActionType.PLAY_DEFENSE_REACTION and a.card
        ]
        if defense_reactions:
            return max(defense_reactions, key=lambda a: a.card.defense or 0)

        return None  # fallback will pick REACTION_PASS
