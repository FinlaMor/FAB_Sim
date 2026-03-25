"""GameState factory for creating card-specific test game states."""

from __future__ import annotations

from typing import Optional
from engine.card import Card, CardDB, _derive_category
from engine.state import (
    GameState, Player, Step, Zone, CombatState,
)


def _mock_agent(state, player_id):
    """Mock agent placeholder for test game states."""
    return None


# Maps card type to (zone_name, step) with priority ordering.
# First matching type wins.
CARD_TYPE_TO_ZONE: dict[str, tuple[str, Step]] = {
    "Hero": ("hero", Step.ACTION),
    "Weapon": ("weapon1", Step.ACTION),
    "Equipment": ("equipment", Step.ACTION),  # resolved to head/chest/arms/legs
    "Attack": ("hand", Step.COMBAT_ATTACK),
    "Attack Reaction": ("hand", Step.COMBAT_REACTION),
    "Defense Reaction": ("hand", Step.COMBAT_DEFEND),
    "Instant": ("hand", Step.ACTION),
    "Action": ("hand", Step.ACTION),
    "Aura": ("permanents", Step.ACTION),
    "Item": ("permanents", Step.ACTION),
    "Ally": ("permanents", Step.ACTION),
    "Token": ("permanents", Step.ACTION),
    "Landmark": ("permanents", Step.ACTION),
}

# Equipment subtype to zone mapping
_EQUIPMENT_SLOT_MAP = {
    "Head": "head",
    "Chest": "chest",
    "Arms": "arms",
    "Legs": "legs",
}


def serialize_gamestate(state: GameState) -> dict:
    """Serialize a GameState, including players, done, and winner fields.

    Workaround for commented-out fields in GameState.to_dict().
    """
    d = state.to_dict()
    d["players"] = {pid: player.to_dict() for pid, player in state.players.items()}
    d["done"] = state.done
    d["winner"] = state.winner
    return d


class GameStateFactory:
    """Creates minimal GameStates configured for testing a specific card."""

    def __init__(self, card_db: Optional[CardDB] = None):
        self._card_db = card_db or CardDB()

    def _make_hero(self, player_id: int) -> Card:
        """Create a generic hero card for test states."""
        hero = Card(
            slug=f"test_hero_p{player_id}",
            name=f"Test Hero P{player_id}",
            types=["Hero"],
            category="hero",
            base_life=40,
            base_intellect=4,
        )
        hero.owner = player_id
        hero.controller = player_id
        return hero

    def _resolve_zone_and_step(self, card: Card) -> tuple[str, Step]:
        """Determine target zone and step from card types using priority ordering."""
        types = card.types or []
        subtypes = card.subtypes or []

        # Check types in priority order
        for type_key, (zone, step) in CARD_TYPE_TO_ZONE.items():
            if type_key in types:
                if type_key == "Equipment":
                    # Resolve to specific equipment slot
                    for subtype, slot in _EQUIPMENT_SLOT_MAP.items():
                        if subtype in subtypes:
                            return slot, step
                    # Default to head if no subtype match
                    return "head", step
                return zone, step

        # Check subtypes for Token
        if "Token" in subtypes:
            return "permanents", Step.ACTION

        # Default: hand + ACTION
        return "hand", Step.ACTION

    def create_gamestate(self, card_slug: str, card_data: Optional[dict] = None) -> GameState:
        """Create a 2-player GameState with the specified card placed appropriately.

        Args:
            card_slug: The slug of the card to set up.
            card_data: Optional override data (unused currently, reserved for future).

        Returns:
            A GameState ready for testing the specified card.
        """
        card = self._card_db.get(card_slug)
        if card is None:
            raise ValueError(f"Card not found: {card_slug}")

        # Create players with generic heroes
        hero1 = self._make_hero(1)
        hero2 = self._make_hero(2)
        p1 = Player(player_id=1, hero_card=hero1)
        p2 = Player(player_id=2, hero_card=hero2)

        # Determine placement
        zone_name, step = self._resolve_zone_and_step(card)

        # Configure card ownership
        card.owner = 1
        card.controller = 1

        # Set player resources to card cost
        if card.base_cost is not None:
            p1.resources = card.base_cost

        # Place card in the correct zone
        target_zone = p1.zone_by_name(zone_name)
        if target_zone is not None:
            target_zone.add(card)
        else:
            # Fallback to hand
            p1.hand.add(card)

        # Set up CombatState for attack/reaction cards
        combat = None
        if step in (Step.COMBAT_ATTACK, Step.COMBAT_REACTION, Step.COMBAT_DEFEND):
            attack_card = card if step == Step.COMBAT_ATTACK else Card(
                slug="test_attack",
                name="Test Attack",
                types=["Attack", "Action"],
                base_power=3,
            )
            combat = CombatState(
                attacker_id=1,
                link_id=1,
                attack_power=attack_card.base_power or 0,
                attack_card=attack_card,
                keywords=list(attack_card.keywords),
                base_attack_power=attack_card.base_power or 0,
            )

        state = GameState(
            players={1: p1, 2: p2},
            active_player=1,
            player_agents={1: _mock_agent, 2: _mock_agent},
            step=step,
            turn_number=1,
            combat=combat,
            done=False,
            winner=None,
            card_db=self._card_db,
        )

        return state
