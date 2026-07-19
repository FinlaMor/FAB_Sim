"""Interactive human agent for FAB self-play: prompts the player for decisions."""

from __future__ import annotations

import sys
from typing import Optional

from engine.actions import Action, ActionType
from engine.state import GameState, Step


# Human-readable labels for each ActionType
_ACTION_LABELS = {
    ActionType.PASS: "Pass",
    ActionType.PLAY_CARD: "Play card",
    ActionType.DEFEND_CARDS: "Defend with cards",
    ActionType.STORE_ARSENAL: "Store in arsenal",
    ActionType.REACTION_PASS: "Pass (no reaction)",
    ActionType.ACTIVATE_CARD: "Activate card",
    ActionType.DISCARD_ACTIVATE: "Discard for instant ability",
    ActionType.CHOOSE: "Choose",
    ActionType.PITCH_CARD: "Pitch card",
    ActionType.PITCH_TO_DECK: "Pitch to deck",
}


class HumanAgent:
    """Interactive agent that prompts a human player for decisions via stdin."""

    def __init__(self, player_id: int = 1):
        self.player_id = player_id

    def __call__(self, state: GameState, actions, context=None):
        if not isinstance(actions, (list, tuple)) or not actions:
            return actions

        # Non-Action options (e.g. start-player choice, trigger ordering)
        if not isinstance(actions[0], Action):
            return self._choose_non_action(state, actions, context)

        # Auto-select when only one legal action
        if len(actions) == 1:
            desc = self._format_action(actions[0])
            print(f"\n  (Auto-selecting: {desc})")
            return actions[0]

        self._display_state(state)

        if context:
            print(f"\n  Context: {context}")

        self._format_action_list(actions)
        return self._get_choice(actions)

    # ------------------------------------------------------------------
    # State display
    # ------------------------------------------------------------------

    def _display_state(self, state: GameState) -> None:
        opp_id = 3 - self.player_id
        me = state.players.get(self.player_id)
        opp = state.players.get(opp_id)
        if not me or not opp:
            return

        print("\n" + "=" * 60)
        print(f"  Turn {state.turn_number}  |  Step: {state.step.value}  |  Active: P{state.active_player}")
        print("=" * 60)

        # Opponent (public info only)
        print(f"\n  OPPONENT (P{opp_id}): {opp.hero.name}")
        print(f"    Health: {opp.health}  |  Hand: {len(opp.hand)} cards  |  Deck: {len(opp.deck)}")
        equip_strs = [f"{c.name}(def:{c.defense or 0})" for c in opp.equipment]
        if equip_strs:
            print(f"    Equipment: {', '.join(equip_strs)}")
        for wz in (opp.weapon1, opp.weapon2):
            if wz.cards:
                print(f"    Weapon: {wz.cards[0].name}")
        if opp.arsenal:
            face = "face-up" if opp.arsenal_face_up else "face-down"
            print(f"    Arsenal: {len(opp.arsenal)} card ({face})")
        if opp.graveyard:
            print(f"    Graveyard: {len(opp.graveyard)} cards")

        print(f"\n  YOU (P{self.player_id}): {me.hero.name}")
        print(f"    Health: {me.health}  |  Resources: {me.resources}  |  AP: {me.action_points}")

        # Hand with card details
        if me.hand:
            print("    Hand:")
            for i, c in enumerate(me.hand):
                parts = [c.name]
                if c.cost is not None:
                    parts.append(f"cost:{c.cost}")
                if c.power is not None:
                    parts.append(f"pow:{c.power}")
                if c.defense is not None:
                    parts.append(f"def:{c.defense}")
                if c.pitch is not None:
                    parts.append(f"pitch:{c.pitch}")
                print(f"      [{i}] {' | '.join(parts)}")

        equip_strs = [f"{c.name}(def:{c.defense or 0})" for c in me.equipment]
        if equip_strs:
            print(f"    Equipment: {', '.join(equip_strs)}")
        for wz in (me.weapon1, me.weapon2):
            if wz.cards:
                w = wz.cards[0]
                exh = " [exhausted]" if me.weapon_exhausted else ""
                print(f"    Weapon: {w.name}{exh}")
        if me.arsenal:
            ac = me.arsenal.top
            if ac:
                print(f"    Arsenal: {ac.name} ({'face-up' if me.arsenal_face_up else 'face-down'})")

        # Combat state
        combat = state.combat
        if combat:
            print(f"\n  COMBAT: {combat.attack_card.name} (power: {combat.attack_power})")
            if combat.defending_cards:
                def_names = [c.name for c in combat.defending_cards]
                print(f"    Defending: {', '.join(def_names)} (total def: {combat.total_defense})")

        print("-" * 60)

    # ------------------------------------------------------------------
    # Action formatting
    # ------------------------------------------------------------------

    def _format_action(self, action: Action) -> str:
        label = _ACTION_LABELS.get(action.type, action.type.value)

        if action.type in (ActionType.PASS, ActionType.REACTION_PASS):
            return label

        parts = [label]

        if action.card:
            card_info = action.card.name
            extras = []
            if action.card.cost is not None:
                extras.append(f"cost:{action.card.cost}")
            if action.card.power is not None:
                extras.append(f"pow:{action.card.power}")
            if action.card.defense is not None:
                extras.append(f"def:{action.card.defense}")
            if extras:
                card_info += f" [{', '.join(extras)}]"
            parts.append(card_info)

        if action.card_list:
            names = [c.name for c in action.card_list]
            parts.append(f"with [{', '.join(names)}]")

        if action.pitch_cards:
            pitch_names = []
            for p in action.pitch_cards:
                if hasattr(p, 'name'):
                    pitch_names.append(p.name)
                else:
                    pitch_names.append(str(p))
            if pitch_names:
                parts.append(f"pitch: {', '.join(pitch_names)}")

        if action.slot:
            parts.append(f"slot:{action.slot}")

        if action.target:
            tgt = action.target.name if hasattr(action.target, 'name') else str(action.target)
            parts.append(f"target:{tgt}")

        if action.from_arsenal:
            parts.append("(from arsenal)")

        return " — ".join(parts)

    def _format_action_list(self, actions: list[Action]) -> None:
        # Group by type for long lists
        if len(actions) > 10:
            grouped: dict[ActionType, list[tuple[int, Action]]] = {}
            for i, a in enumerate(actions):
                grouped.setdefault(a.type, []).append((i, a))

            print("\n  Available actions:")
            for atype, items in grouped.items():
                label = _ACTION_LABELS.get(atype, atype.value)
                print(f"\n    [{label}]")
                for idx, a in items:
                    print(f"      {idx}: {self._format_action(a)}")
        else:
            print("\n  Available actions:")
            for i, a in enumerate(actions):
                print(f"    {i}: {self._format_action(a)}")

    # ------------------------------------------------------------------
    # Non-Action choices (start-player, trigger ordering, etc.)
    # ------------------------------------------------------------------

    def _choose_non_action(self, state: GameState, options, context=None) -> object:
        if len(options) == 1:
            print(f"\n  (Auto-selecting: {options[0]})")
            return options[0]

        if context:
            print(f"\n  Decision: {context}")
        print("  Options:")
        for i, opt in enumerate(options):
            print(f"    {i}: {opt}")

        return self._get_choice(options)

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------

    def _get_choice(self, options) -> object:
        while True:
            try:
                raw = input(f"  Choose [0-{len(options)-1}]: ").strip()
                if not raw:
                    print("  Please enter a number.")
                    continue
                try:
                    idx = int(raw)
                except ValueError:
                    print(f"  Invalid input. Enter a number 0-{len(options)-1}.")
                    continue
                if idx < 0 or idx >= len(options):
                    print(f"  Out of range. Enter a number 0-{len(options)-1}.")
                    continue
                return options[idx]
            except KeyboardInterrupt:
                print("\n  Game aborted.")
                sys.exit(0)
            except EOFError:
                print("\n  Game aborted.")
                sys.exit(0)
