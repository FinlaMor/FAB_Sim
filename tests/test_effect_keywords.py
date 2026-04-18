"""Tests for centralized effect keyword functions (engine/effect_keywords.py).

Each test targets a specific CR 8.5 rule to verify the function
routes correctly through replacement effects and triggers.
"""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from tests.conftest import _make_state, _make_card
from engine.effect_keywords import EventType, banish, BanishEvent, create_token, CreateTokenEvent, deal_damage, DamageEvent, DamageType, discard, DiscardEvent, destroy, DestroyEvent, draw, DrawEvent, gain, GainEvent, AssetType, gets, GetsEvent, GetsKind, gets_property, GetsPropertyEvent, intimidate, IntimidateEvent, look, LookEvent, lose, LoseEvent
from engine.state import Event, Step
from engine.card import CardDB
from copy import deepcopy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _add_to_hand(state, player_id: int, card):
    card.owner = player_id
    card.controller = player_id
    state.players[player_id].hand.add(card)
    return card


# ---------------------------------------------------------------------------
# CR 8.5.1 — banish
# ---------------------------------------------------------------------------

def test_banish_moves_card_to_banished_zone():
    """Basic case: card in hand is moved to banished zone."""
    state = _make_state()
    card = _add_to_hand(state, 1, _make_card("test_card"))

    event = banish(state, card, source_player_id=1, origin_zone="hand")

    assert not event.cancelled
    assert card not in state.players[1].hand.cards
    assert card in state.players[1].banished.cards


def test_banish_emits_trigger():
    """After banish, event_manager emits the banish event to listeners."""
    state = _make_state()
    card = _add_to_hand(state, 1, _make_card("test_card"))

    fired = []
    state.event_manager.register(EventType.BANISH, lambda e, s: fired.append(e))

    banish(state, card, source_player_id=1, origin_zone="hand")

    assert len(fired) == 1
    assert fired[0].card is card


def test_banish_replacement_effect_redirects_destination():
    """CR 8.5.1b — replacement effect can redirect destination; card still considered banished."""
    from engine.effects import ReplacementEffect, ReplacementType
    state = _make_state()
    card = _add_to_hand(state, 1, _make_card("test_card"))

    source = _make_card("effect_source")
    state.effect_manager.replacement_effects.append(
        ReplacementEffect(
            source_card=source,
            replacement_type=ReplacementType.STANDARD,
            condition_fn=lambda e, s: e.get("type") == EventType.BANISH,
            replace_fn=lambda e, s: {**e, "destination": "graveyard"},
        )
    )

    event = banish(state, card, source_player_id=1, origin_zone="hand")

    assert not event.cancelled
    assert event.destination == "graveyard"
    assert card not in state.players[1].hand.cards
    assert card not in state.players[1].banished.cards
    assert card in state.players[1].graveyard.cards


def test_banish_cancellation():
    """A replacement effect can cancel a banish entirely."""
    from engine.effects import ReplacementEffect, ReplacementType
    from tests.conftest import _make_card as _mc
    state = _make_state()
    card = _add_to_hand(state, 1, _make_card("test_card"))

    source = _mc("effect_source")
    state.effect_manager.replacement_effects.append(
        ReplacementEffect(
            source_card=source,
            replacement_type=ReplacementType.STANDARD,
            condition_fn=lambda e, s: e.get("type") == EventType.BANISH,
            replace_fn=lambda e, s: {**e, "cancelled": True},
        )
    )

    event = banish(state, card, source_player_id=1, origin_zone="hand")

    assert event.cancelled
    assert card in state.players[1].hand.cards       # still in hand
    assert card not in state.players[1].banished.cards


def test_banish_until_end_of_turn_registers_return():
    """CR 8.5.1c — temporary banish registers a return handler on end_of_turn."""
    state = _make_state()
    card = _add_to_hand(state, 1, _make_card("test_card"))

    banish(state, card, source_player_id=1, origin_zone="hand",
           until_condition=EventType.EOT)

    assert card in state.players[1].banished.cards
    # Handler registered — fire end_of_turn to trigger return
    state.event_manager.emit(Event(type=EventType.EOT), state)

    assert card not in state.players[1].banished.cards
    assert card in state.players[1].hand.cards


def test_banish_return_fails_if_card_ceased_to_exist():
    """CR 8.5.1c — return fails if card moved to a non-arena/non-stack zone."""
    state = _make_state()
    card = _add_to_hand(state, 1, _make_card("test_card"))

    orig_card = deepcopy(card)

    assert card in state.players[1].hand.cards # precondition check

    banish(state, card, source_player_id=1, origin_zone="hand",
           until_condition=EventType.EOT)
    
    # Card moves to graveyard while banished (ceased to exist per CR 3.0.9)
    state.players[1].banished.remove(card)
    state.players[1].graveyard.add(card)

    state.event_manager.emit(Event(type=EventType.EOT), state)

    # Card should stay in graveyard — return failed
    assert card not in state.players[1].hand.cards
    assert card not in state.players[1].banished.cards
    assert card in state.players[1].graveyard.cards

    # Orig_card would not share same zones as card. precondition for next checks
    orig_card.zone = card.zone
    orig_card.prev_zone = card.prev_zone
    orig_card.is_public = True # copy was made when card was in hand and private

    assert orig_card is not card # check if card in graveyard is a new instance of the card (3.0.9)
    assert orig_card == card


def test_banish_return_succeeds_if_card_in_arena():
    """CR 3.0.9b — return succeeds if card moved to arena (remained public)."""
    from engine.card_effects.card_keywords import ARENA_ZONE_NAMES
    state = _make_state()
    # Card needs a permanent subtype to legally enter the permanents zone (CR 3.13.2)
    card = _add_to_hand(state, 1, _make_card("test_card", types=["Action"]))
    card.raw_subtypes = ["Aura"]

    banish(state, card, source_player_id=1, origin_zone="hand",
           until_condition=EventType.EOT)

    # Card moves to permanents zone (arena) while banished
    state.players[1].banished.remove(card)
    state.players[1].permanents.add(card)

    state.event_manager.emit(Event(type=EventType.EOT), state)

    # Card should be returned to hand
    assert card in state.players[1].hand.cards
    assert card not in state.players[1].permanents.cards


# ---------------------------------------------------------------------------
# Helpers for create_token / deal_damage
# ---------------------------------------------------------------------------

class _MockCardDB:
    """Minimal card_db stub that returns a fresh Card for any slug."""
    def get(self, slug: str):
        c = _make_card(slug)
        c.raw_types = ["Token"]
        return c


def _state_with_db():
    state = _make_state()
    state.card_db = CardDB()
    return state


# ---------------------------------------------------------------------------
# CR 8.5.2 — create_token
# ---------------------------------------------------------------------------

def test_create_token_adds_to_tokens_zone():
    """Basic case: token appears in controlling player's tokens zone."""
    state = _state_with_db()

    assert len(state.players[1].tokens.cards) == 0 # baseline

    event = create_token(state, token="vigor", source_player_id=1, target_player_id=1)

    assert not event.canceled
    assert len(state.players[1].tokens.cards) == 1
    assert state.players[1].tokens.cards[0].slug == "vigor"


def test_create_token_emits_trigger():
    """After creation, event_manager emits create_token event."""
    state = _state_with_db()

    fired = []
    state.event_manager.register("create_token", lambda e, s: fired.append(e))

    create_token(state, token="might", source_player_id=1, target_player_id=1)

    assert len(fired) == 1


def test_create_token_number_creates_multiple():
    """number=3 creates 3 tokens. CR 8.5.2c."""
    state = _state_with_db()

    create_token(state, token="might", source_player_id=1, target_player_id=1, number=3)

    assert len(state.players[1].tokens.cards) == 3
    assert state.players[1].tokens.cards[0].slug == "might"


def test_create_token_canceled_creates_nothing():
    """If replacement reduces number to 0, no token is created."""
    from engine.effects import ReplacementEffect, ReplacementType
    state = _state_with_db()
    source = _make_card("effect_source")

    state.effect_manager.replacement_effects.append(
        ReplacementEffect(
            source_card=source,
            replacement_type=ReplacementType.STANDARD,
            condition_fn=lambda e, s: e.get("type") == "create_token",
            replace_fn=lambda e, s: {**e, "canceled": True},
        )
    )

    event = create_token(state, token="vigor", source_player_id=1, target_player_id=1)

    assert event.canceled
    assert len(state.players[1].tokens.cards) == 0


def test_create_token_target_player_controls_token():
    """CR 8.5.2c — token enters under control of the instructed player."""
    state = _state_with_db()

    create_token(state, token="frailty", source_player_id=1, target_player_id=2)

    assert len(state.players[2].tokens.cards) == 1
    assert len(state.players[1].tokens.cards) == 0

    create_token(state, "ponder", 1, 1)

    assert len(state.players[2].tokens.cards) == 1
    assert len(state.players[1].tokens.cards) == 1
    assert state.players[2].tokens.cards[0].slug == "frailty"
    assert state.players[1].tokens.cards[0].slug == "ponder"

def test_create_token_weapon_in_weapon_zone():
    """Test creating token in zone other than tokens (weapon zone)"""

    state = _state_with_db()
    player = state.players[1]

    assert len(player.tokens.cards) == 0
    assert len(player.weapon1.cards) == 0
    assert len(player.weapon2.cards) == 0

    event = create_token(state, token="graphene_chelicera", source_player_id=1, target_player_id=1, destination="weapon1")

    assert event.canceled == False
    assert event.destination == 'weapon1'
    assert hasattr(player, event.destination)
    assert event.target_player_id == 1

    assert len(player.tokens.cards) == 0
    assert len(player.weapon1.cards) == 1
    assert len(player.weapon2.cards) == 0
    assert player.weapon1.cards[0].slug == "graphene_chelicera"

    create_token(state, token="graphene_chelicera", source_player_id=1, target_player_id=1, destination="weapon2")

    assert len(player.tokens.cards) == 0
    assert len(player.weapon1.cards) == 1
    assert len(player.weapon2.cards) == 1
    assert player.weapon1.cards[0].slug == "graphene_chelicera"
    assert player.weapon2.cards[0].slug == "graphene_chelicera"


# ---------------------------------------------------------------------------
# CR 8.5.3 — deal_damage
# ---------------------------------------------------------------------------

def test_deal_damage_reduces_hero_life():
    """Physical damage reduces the target hero's life."""
    state = _make_state()
    target_hero = state.players[2].hero
    initial_life = state.players[2].life

    deal_damage(state, amount=3, damage_type=DamageType.PHYSICAL,
                source_player_id=1, damage_target=target_hero,
                damage_source="test_attack")

    assert state.players[2].life == initial_life - 3


def test_deal_damage_emits_trigger():
    """After hit, damage event is emitted."""
    state = _make_state()
    target_hero = state.players[2].hero

    fired = []
    state.event_manager.register("damage", lambda e, s: fired.append(e))

    deal_damage(state, amount=2, damage_type=DamageType.PHYSICAL,
                source_player_id=1, damage_target=target_hero,
                damage_source="test_attack")

    assert len(fired) == 1


def test_deal_damage_zero_does_nothing():
    """CR 8.5.3: zero damage — life unchanged, no trigger."""
    state = _make_state()
    target_hero = state.players[2].hero
    initial_life = state.players[2].life

    fired = []
    state.event_manager.register("damage", lambda e, s: fired.append(e))

    deal_damage(state, amount=0, damage_type=DamageType.PHYSICAL,
                source_player_id=1, damage_target=target_hero,
                damage_source="test_attack")

    assert state.players[2].life == initial_life
    assert len(fired) == 0


def test_deal_damage_prevention_reduces_amount():
    """Replacement effect can reduce damage amount (prevention)."""
    from engine.effects import ReplacementEffect, ReplacementType
    state = _make_state()
    target_hero = state.players[2].hero
    initial_life = state.players[2].life
    source = _make_card("effect_source")

    # Prevent 2 damage
    state.effect_manager.replacement_effects.append(
        ReplacementEffect(
            source_card=source,
            replacement_type=ReplacementType.PREVENTION,
            condition_fn=lambda e, s: e.get("type") == "damage",
            replace_fn=lambda e, s: {**e, "amount": max(0, e.get("amount", 0) - 2)},
            prevention_amount=2,
        )
    )

    deal_damage(state, amount=5, damage_type=DamageType.PHYSICAL,
                source_player_id=1, damage_target=target_hero,
                damage_source="test_attack")

    assert state.players[2].life == initial_life - 3


def test_deal_damage_arcane_type_tracked():
    """CR 8.5.3b — arcane damage type is preserved in the event."""
    state = _make_state()
    target_hero = state.players[2].hero

    fired = []
    state.event_manager.register("damage", lambda e, s: fired.append(e))

    deal_damage(state, amount=1, damage_type=DamageType.ARCANE,
                source_player_id=1, damage_target=target_hero,
                damage_source="test_spell")

    assert len(fired) == 1
    assert fired[0].data["damage_type"] == DamageType.ARCANE


def test_deal_damage_non_living_target_fails():
    """CR 8.5.3c — damage to a non-living object fails silently."""
    state = _make_state()
    non_living = _make_card("item_card")  # no Hero/Ally type — not living

    initial_p1_life = state.players[1].life
    initial_p2_life = state.players[2].life

    # Should not raise, just return cancelled event
    event = deal_damage(state, amount=5, damage_type=DamageType.PHYSICAL,
                        source_player_id=1, damage_target=non_living,
                        damage_source="test_attack")

    assert event.canceled
    assert state.players[1].life == initial_p1_life
    assert state.players[2].life == initial_p2_life


def test_deal_damage_reduces_ally_life():
    """Ally damage reduces life by the correct amount."""
    state = _make_state()
    ally = _make_card("test_ally", types=["Ally"])
    ally.life = 5
    ally.owner = 2
    ally.controller = 2

    deal_damage(state, amount=3, damage_type=DamageType.PHYSICAL,
                source_player_id=1, damage_target=ally,
                damage_source="test_attack")

    assert ally.life == 2


def test_deal_damage_ally_emits_damage_event():
    """Ally damage emits a damage event."""
    state = _make_state()
    ally = _make_card("test_ally", types=["Ally"])
    ally.life = 5
    ally.owner = 2
    ally.controller = 2

    fired = []
    state.event_manager.register("damage", lambda e, s: fired.append(e))

    deal_damage(state, amount=2, damage_type=DamageType.PHYSICAL,
                source_player_id=1, damage_target=ally,
                damage_source="test_attack")

    assert len(fired) == 1


def test_deal_damage_kills_ally():
    """An ally reduced to 0 life is removed from allies and placed in graveyard."""
    state = _make_state()
    ally = _make_card("test_ally", types=["Ally"])
    ally.life = 3
    ally.owner = 2
    ally.controller = 2
    state.players[2].allies.add(ally)

    deal_damage(state, amount=3, damage_type=DamageType.PHYSICAL,
                source_player_id=1, damage_target=ally,
                damage_source="test_attack")

    assert ally not in state.players[2].allies.cards
    assert ally in state.players[2].graveyard.cards


def test_deal_damage_ally_death_emits_ally_died_event():
    """When an ally is killed, an ally_died event is emitted."""
    state = _make_state()
    ally = _make_card("test_ally", types=["Ally"])
    ally.life = 3
    ally.owner = 2
    ally.controller = 2
    state.players[2].allies.add(ally)

    fired = []
    state.event_manager.register("ally_died", lambda e, s: fired.append(e))

    deal_damage(state, amount=3, damage_type=DamageType.PHYSICAL,
                source_player_id=1, damage_target=ally,
                damage_source="test_attack")

    assert len(fired) == 1
    assert fired[0].data["ally"] == "test_ally"


def test_deal_damage_hit_event_physical_in_combat_step():
    """Physical damage in the combat_damage step emits a hit event."""
    state = _make_state()
    state.step = Step.COMBAT_DAMAGE
    target_hero = state.players[2].hero

    fired = []
    state.event_manager.register("hit", lambda e, s: fired.append(e))

    deal_damage(state, amount=3, damage_type=DamageType.PHYSICAL,
                source_player_id=1, damage_target=target_hero,
                damage_source="test_attack")

    assert len(fired) == 1


def test_deal_damage_no_hit_event_for_arcane_damage():
    """Arcane damage in the combat_damage step does NOT emit a hit event."""
    state = _make_state()
    state.step = Step.COMBAT_DAMAGE
    target_hero = state.players[2].hero

    fired = []
    state.event_manager.register("hit", lambda e, s: fired.append(e))

    deal_damage(state, amount=3, damage_type=DamageType.ARCANE,
                source_player_id=1, damage_target=target_hero,
                damage_source="test_spell")

    assert len(fired) == 0


def test_deal_damage_no_hit_event_outside_combat_step():
    """Physical damage outside the combat_damage step does NOT emit a hit event."""
    state = _make_state()  # step=Step.ACTION
    target_hero = state.players[2].hero

    fired = []
    state.event_manager.register("hit", lambda e, s: fired.append(e))

    deal_damage(state, amount=3, damage_type=DamageType.PHYSICAL,
                source_player_id=1, damage_target=target_hero,
                damage_source="test_attack")

    assert len(fired) == 0


def test_deal_damage_canceled_by_replacement_effect():
    """A replacement effect setting canceled=True prevents life loss and events."""
    from engine.effects import ReplacementEffect, ReplacementType
    state = _make_state()
    target_hero = state.players[2].hero
    initial_life = state.players[2].life
    source = _make_card("effect_source")

    state.effect_manager.replacement_effects.append(
        ReplacementEffect(
            source_card=source,
            replacement_type=ReplacementType.PREVENTION,
            condition_fn=lambda e, s: e.get("type") == "damage",
            replace_fn=lambda e, s: {**e, "canceled": True},
            prevention_amount=0,
        )
    )

    fired = []
    state.event_manager.register("damage", lambda e, s: fired.append(e))

    event = deal_damage(state, amount=5, damage_type=DamageType.PHYSICAL,
                        source_player_id=1, damage_target=target_hero,
                        damage_source="test_attack")

    assert event.canceled
    assert state.players[2].life == initial_life
    assert len(fired) == 0


# ---------------------------------------------------------------------------
# CR 8.5.5 — discard
# ---------------------------------------------------------------------------

def test_discard_moves_card_to_graveyard():
    """Basic case: card in hand is moved to graveyard."""
    state = _make_state()
    card = _make_card("test_card")
    card.owner = 1
    card.controller = 1
    state.players[1].hand.add(card)

    event = discard(state, card, discard_source=None)

    assert not event.canceled
    assert card not in state.players[1].hand.cards
    assert card in state.players[1].graveyard.cards


def test_discard_emits_trigger():
    """After discard, event_manager emits the discard event."""
    state = _make_state()
    card = _make_card("test_card")
    card.owner = 1
    card.controller = 1
    state.players[1].hand.add(card)

    fired = []
    state.event_manager.register("discard", lambda e, s: fired.append(e))

    discard(state, card, discard_source=None)

    assert len(fired) == 1
    assert fired[0].target == card


def test_discard_empty_hand_returns_cancelled():
    """CR 8.5.5b: discard fails if player has no cards in hand."""
    state = _make_state()
    card = _make_card("test_card")
    card.owner = 1
    card.controller = 1
    # do NOT add card to hand

    event = discard(state, card, discard_source=None)

    assert event.canceled


def test_discard_replacement_effect_redirects_destination():
    """Replacement effect can redirect destination (e.g. to banished instead of graveyard)."""
    from engine.effects import ReplacementEffect, ReplacementType
    state = _make_state()
    card = _make_card("test_card")
    card.owner = 1
    card.controller = 1
    state.players[1].hand.add(card)
    source = _make_card("effect_source")

    state.effect_manager.replacement_effects.append(
        ReplacementEffect(
            source_card=source,
            replacement_type=ReplacementType.STANDARD,
            condition_fn=lambda e, s: e.get("type") == "discard",
            replace_fn=lambda e, s: {**e, "destination": "banished"},
        )
    )

    event = discard(state, card, discard_source=None)

    assert not event.canceled
    assert event.destination == "banished"
    assert card not in state.players[1].hand.cards
    assert card not in state.players[1].graveyard.cards
    assert card in state.players[1].banished.cards


def test_discard_cancellation():
    """A replacement effect can cancel a discard entirely."""
    from engine.effects import ReplacementEffect, ReplacementType
    state = _make_state()
    card = _make_card("test_card")
    card.owner = 1
    card.controller = 1
    state.players[1].hand.add(card)
    source = _make_card("effect_source")

    state.effect_manager.replacement_effects.append(
        ReplacementEffect(
            source_card=source,
            replacement_type=ReplacementType.STANDARD,
            condition_fn=lambda e, s: e.get("type") == "discard",
            replace_fn=lambda e, s: {**e, "canceled": True},
        )
    )

    event = discard(state, card, discard_source=None)

    assert event.canceled
    assert card in state.players[1].hand.cards
    assert card not in state.players[1].graveyard.cards


def test_discard_token_ceases_to_exist():
    """CR 3.0.12a — a discarded token ceases to exist rather than entering the graveyard."""
    state = _make_state()
    token = _make_card("test_token", types=["Token"])
    token.owner = 1
    token.controller = 1
    # Tokens can't enter hand via Zone.add (not deck cards), so place directly
    state.players[1].hand.cards.append(token)
    token.zone = "hand"

    event = discard(state, token, discard_source=None)

    assert not event.canceled
    assert token not in state.players[1].hand.cards
    assert token not in state.players[1].graveyard.cards


# ---------------------------------------------------------------------------
# CR 8.5.4 — destroy
# ---------------------------------------------------------------------------

def _card_in_permanents(state, player_id: int, slug="aura_card"):
    """Helper: put an Aura card in the permanents zone."""
    card = _make_card(slug, types=["Action"])
    card.raw_subtypes = ["Aura"]
    card.owner = player_id
    card.controller = player_id
    state.players[player_id].permanents.add(card)
    return card


def test_destroy_moves_card_to_graveyard():
    """Basic case: card in permanents is moved to owner's graveyard."""
    state = _make_state()
    card = _card_in_permanents(state, 1)
    source = _make_card("destroy_source")
    source.owner = 1
    source.controller = 1

    event = destroy(state, card, destroy_source=source)

    assert not event.canceled
    assert card not in state.players[1].permanents.cards
    assert card in state.players[1].graveyard.cards


def test_destroy_emits_trigger():
    """After destroy, event_manager emits the destroy event."""
    state = _make_state()
    card = _card_in_permanents(state, 1)
    source = _make_card("destroy_source")
    source.owner = 1
    source.controller = 1

    fired = []
    state.event_manager.register("destroy", lambda e, s: fired.append(e))

    destroy(state, card, destroy_source=source)

    assert len(fired) == 1
    assert fired[0].target == card


def test_destroy_returns_event():
    """destroy() must return the event (not None)."""
    state = _make_state()
    card = _card_in_permanents(state, 1)
    source = _make_card("destroy_source")
    source.owner = 1
    source.controller = 1

    event = destroy(state, card, destroy_source=source)

    assert isinstance(event, DestroyEvent)


def test_destroy_cancellation():
    """A replacement effect can cancel a destroy."""
    from engine.effects import ReplacementEffect, ReplacementType
    state = _make_state()
    card = _card_in_permanents(state, 1)
    source = _make_card("destroy_source")
    source.owner = source.controller = 1
    repl_source = _make_card("repl_source")

    state.effect_manager.replacement_effects.append(
        ReplacementEffect(
            source_card=repl_source,
            replacement_type=ReplacementType.STANDARD,
            condition_fn=lambda e, s: e.get("type") == "destroy",
            replace_fn=lambda e, s: {**e, "canceled": True},
        )
    )

    event = destroy(state, card, destroy_source=source)

    assert event.canceled
    assert card in state.players[1].permanents.cards
    assert card not in state.players[1].graveyard.cards


def test_destroy_token_ceases_to_exist():
    """CR 3.0.12a — a destroyed token ceases to exist rather than entering the graveyard."""
    state = _make_state()
    token = _make_card("test_token", types=["Token"])
    token.owner = 1
    token.controller = 1
    state.players[1].tokens.add(token)
    source = _make_card("destroy_source")
    source.owner = source.controller = 1

    event = destroy(state, token, destroy_source=source)

    assert not event.canceled
    assert token not in state.players[1].permanents.cards
    assert token not in state.players[1].graveyard.cards


def test_destroy_sends_card_to_owners_graveyard():
    """CR 8.5.4 — a destroyed card goes to its *owner's* graveyard, not the controller's."""
    state = _make_state()
    # card owned by player 2 but controlled by player 1
    card = _make_card("stolen_card", types=["Action"])
    card.raw_subtypes = ["Aura"]
    card.owner = 2
    card.controller = 1
    state.players[1].permanents.add(card)
    source = _make_card("destroy_source")
    source.owner = source.controller = 1

    destroy(state, card, destroy_source=source)

    assert card not in state.players[1].permanents.cards
    assert card not in state.players[1].graveyard.cards
    assert card in state.players[2].graveyard.cards


def test_destroy_replacement_can_redirect_target():
    """A replacement effect can swap the destroy target for a different card."""
    from engine.effects import ReplacementEffect, ReplacementType
    state = _make_state()
    card_a = _card_in_permanents(state, 1, slug="card_a")
    card_b = _card_in_permanents(state, 1, slug="card_b")
    source = _make_card("destroy_source")
    source.owner = source.controller = 1
    repl_source = _make_card("repl_source")

    # redirect: whenever card_a would be destroyed, destroy card_b instead
    state.effect_manager.replacement_effects.append(
        ReplacementEffect(
            source_card=repl_source,
            replacement_type=ReplacementType.STANDARD,
            condition_fn=lambda e, s: (e.get("type") == "destroy"
                                       and getattr(e.get("target"), "slug", None) == "card_a"),
            replace_fn=lambda e, s: {**e, "target": card_b},
        )
    )

    event = destroy(state, card_a, destroy_source=source)

    assert not event.canceled
    assert card_a in state.players[1].permanents.cards   # untouched
    assert card_b not in state.players[1].permanents.cards  # destroyed instead
    assert card_b in state.players[1].graveyard.cards


# ---------------------------------------------------------------------------
# CR 8.5.6 — draw
# ---------------------------------------------------------------------------

def _fill_deck(state, player_id: int, count: int = 3):
    """Add count Action cards to the top of the player's deck."""
    cards = []
    for i in range(count):
        c = _make_card(f"deck_card_{i}")
        c.owner = player_id
        c.controller = player_id
        state.players[player_id].deck.cards.append(c)
        c.zone = "deck"
        cards.append(c)
    return cards


def test_draw_moves_top_card_to_hand():
    """Basic case: top deck card moves to hand."""
    state = _make_state()
    cards = _fill_deck(state, 1, count=3)
    top = cards[0]  # first appended = index 0 = top (pop_top uses index 0)

    event = draw(state, draw_player=1)

    assert not event.canceled
    assert top in state.players[1].hand.cards
    assert top not in state.players[1].deck.cards


def test_draw_emits_trigger():
    """After draw, event_manager emits the draw event."""
    state = _make_state()
    _fill_deck(state, 1)

    fired = []
    state.event_manager.register("draw", lambda e, s: fired.append(e))

    draw(state, draw_player=1)

    assert len(fired) == 1
    assert fired[0].data["draw_player"] == 1


def test_draw_number_draws_multiple():
    """number=3 draws 3 cards."""
    state = _make_state()
    _fill_deck(state, 1, count=5)

    draw(state, draw_player=1, number=3)

    assert len(state.players[1].hand.cards) == 3
    assert len(state.players[1].deck.cards) == 2


def test_draw_empty_deck_emits_deck_empty():
    """CR 8.5.6b: drawing from empty deck emits deck_empty; total_draw does NOT fire."""
    state = _make_state()
    # deck is empty by default

    deck_empty_fired = []
    total_draw_fired = []
    state.event_manager.register("deck_empty", lambda e, s: deck_empty_fired.append(e))
    state.event_manager.register("total_draw", lambda e, s: total_draw_fired.append(e))

    event = draw(state, draw_player=1)

    assert not event.canceled
    assert len(deck_empty_fired) == 1
    assert deck_empty_fired[0].data["player_id"] == 1
    assert len(total_draw_fired) == 0  # CR 8.5.6b: draw failed — total_draw must not fire


def test_draw_partial_deck_stops_at_empty():
    """CR 8.5.6b: draw 3 with only 1 card in deck — draws 1, emits deck_empty, total_draw fires with number=1."""
    state = _make_state()
    _fill_deck(state, 1, count=1)

    deck_empty_fired = []
    total_draw_fired = []
    draw_fired = []
    state.event_manager.register("deck_empty", lambda e, s: deck_empty_fired.append(e))
    state.event_manager.register("total_draw", lambda e, s: total_draw_fired.append(e))
    state.event_manager.register("draw", lambda e, s: draw_fired.append(e))

    draw(state, draw_player=1, number=3)

    assert len(state.players[1].hand.cards) == 1
    assert len(draw_fired) == 1
    assert len(deck_empty_fired) == 1
    assert len(total_draw_fired) == 1
    assert total_draw_fired[0].data["number"] == 1  # actual drawn, not requested


def test_draw_cancellation():
    """A replacement effect can cancel a draw."""
    from engine.effects import ReplacementEffect, ReplacementType
    state = _make_state()
    _fill_deck(state, 1)
    source = _make_card("effect_source")

    state.effect_manager.replacement_effects.append(
        ReplacementEffect(
            source_card=source,
            replacement_type=ReplacementType.STANDARD,
            condition_fn=lambda e, s: e.get("type") == "draw",
            replace_fn=lambda e, s: {**e, "canceled": True},
        )
    )

    event = draw(state, draw_player=1)

    assert event.canceled
    assert len(state.players[1].hand.cards) == 0


def test_draw_no_source_required():
    """draw() works without a source card (intellect draw at end of turn)."""
    state = _make_state()
    _fill_deck(state, 1)

    event = draw(state, draw_player=1)  # no source kwarg

    assert not event.canceled
    assert event.source is None
    assert len(state.players[1].hand.cards) == 1


# ---------------------------------------------------------------------------
# CR 8.5.7 — gain (asset)
# ---------------------------------------------------------------------------

def test_gain_life_increases_player_life():
    """Basic case: gain {h} increases target player's life total."""
    state = _make_state()
    initial_life = state.players[2].life

    event = gain(state, asset_type=AssetType.LIFE, amount=3,
                 source_player_id=1, target_player_id=2)

    assert not event.canceled
    assert state.players[2].life == initial_life + 3


def test_gain_resources_increases_player_resources():
    """{r} gain increases target player's resource pool."""
    state = _make_state()
    state.players[1].resources = 1

    event = gain(state, asset_type=AssetType.RESOURCES, amount=2,
                 source_player_id=1, target_player_id=1)

    assert not event.canceled
    assert state.players[1].resources == 3


def test_gain_action_points_increases_turn_player():
    """CR 8.5.7b: turn player gains action point."""
    state = _make_state()
    state.active_player = 1
    state.players[1].action_points = 0

    event = gain(state, asset_type=AssetType.ACTION_POINTS, amount=1,
                 source_player_id=1, target_player_id=1)

    assert not event.canceled
    assert state.players[1].action_points == 1


def test_gain_action_points_fails_for_non_turn_player():
    """CR 8.5.7b: non-turn-player cannot gain action points."""
    state = _make_state()
    state.active_player = 1

    event = gain(state, asset_type=AssetType.ACTION_POINTS, amount=1,
                 source_player_id=1, target_player_id=2)

    assert event.canceled
    assert state.players[2].action_points == 0


def test_gain_life_on_ally_increases_ally_life():
    """CR 8.5.7a: {h} gain on a living object (ally) increases its life."""
    state = _make_state()
    ally = _make_card("young_wolf", types=["Ally"])
    ally.owner = 1
    ally.controller = 1
    ally.life = 3

    event = gain(state, asset_type=AssetType.LIFE, amount=2,
                 source_player_id=1, target_card=ally)

    assert not event.canceled
    assert ally.life == 5


def test_gain_life_on_non_living_fails():
    """CR 8.5.7a: {h} gain on object without life property fails."""
    state = _make_state()
    item = _make_card("item_card")  # Action type, not Hero/Ally — no life property

    event = gain(state, asset_type=AssetType.LIFE, amount=3,
                 source_player_id=1, target_card=item)

    assert event.canceled


def test_gain_emits_trigger():
    """After gain, event_manager emits the gain event."""
    state = _make_state()

    fired = []
    state.event_manager.register("gain", lambda e, s: fired.append(e))

    gain(state, asset_type=AssetType.LIFE, amount=1,
         source_player_id=1, target_player_id=1)

    assert len(fired) == 1
    assert fired[0].data["asset_type"] == AssetType.LIFE
    assert fired[0].data["amount"] == 1


def test_gain_cancellation():
    """A replacement effect can cancel a gain."""
    from engine.effects import ReplacementEffect, ReplacementType
    state = _make_state()
    initial_life = state.players[1].life
    source = _make_card("effect_source")

    state.effect_manager.replacement_effects.append(
        ReplacementEffect(
            source_card=source,
            replacement_type=ReplacementType.STANDARD,
            condition_fn=lambda e, s: e.get("type") == "gain",
            replace_fn=lambda e, s: {**e, "canceled": True},
        )
    )

    event = gain(state, asset_type=AssetType.LIFE, amount=5,
                 source_player_id=1, target_player_id=1)

    assert event.canceled
    assert state.players[1].life == initial_life


def test_gain_zero_amount_does_nothing():
    """Gaining 0 of any asset is a no-op and emits no trigger."""
    state = _make_state()
    initial_life = state.players[1].life

    fired = []
    state.event_manager.register("gain", lambda e, s: fired.append(e))

    event = gain(state, asset_type=AssetType.LIFE, amount=0,
                 source_player_id=1, target_player_id=1)

    assert not event.canceled
    assert state.players[1].life == initial_life
    assert len(fired) == 0


# ---------------------------------------------------------------------------
# CR 8.5.8 — gets (numerical property)
# ---------------------------------------------------------------------------

def _attack_card(state, player_id=1, slug="test_attack", power=3):
    card = _make_card(slug, types=["Action", "Attack"])
    card.base_power = power
    card.power = power
    card.owner = player_id
    card.controller = player_id
    return card


def test_gets_add_power_increases_recalculated_value():
    """gets ADD on power: recalculate returns base + amount."""
    state = _make_state()
    card = _attack_card(state, power=3)

    event = gets(state, prop="power", kind=GetsKind.ADD, amount=2,
                 source_card=None, target_card=card)

    assert not event.canceled
    result = state.continuous_effect_manager.recalculate(state, card, "power", card.base_power)
    assert result == 5


def test_gets_subtract_power_reduces_recalculated_value():
    """gets SUB on power: recalculate returns base - amount (min 0)."""
    state = _make_state()
    card = _attack_card(state, power=3)

    gets(state, prop="power", kind=GetsKind.SUBTRACT, amount=2,
         source_card=None, target_card=card)

    result = state.continuous_effect_manager.recalculate(state, card, "power", card.base_power)
    assert result == 1


def test_gets_set_power_overrides_base():
    """gets SET on power: recalculate returns the set value regardless of base."""
    state = _make_state()
    card = _attack_card(state, power=3)

    gets(state, prop="power", kind=GetsKind.SET, amount=7,
         source_card=None, target_card=card)

    result = state.continuous_effect_manager.recalculate(state, card, "power", card.base_power)
    assert result == 7


def test_gets_only_applies_to_target_card():
    """Modification does not affect other cards."""
    state = _make_state()
    card_a = _attack_card(state, slug="card_a", power=3)
    card_b = _attack_card(state, slug="card_b", power=3)

    gets(state, prop="power", kind=GetsKind.ADD, amount=5,
         source_card=None, target_card=card_a)

    result_a = state.continuous_effect_manager.recalculate(state, card_a, "power", card_a.base_power)
    result_b = state.continuous_effect_manager.recalculate(state, card_b, "power", card_b.base_power)
    assert result_a == 8
    assert result_b == 3


def test_gets_invalid_prop_fails():
    """CR 8.5.8a: unknown property → canceled."""
    state = _make_state()
    card = _attack_card(state)

    event = gets(state, prop="flavor_text", kind=GetsKind.ADD, amount=1,
                 source_card=None, target_card=card)

    assert event.canceled


def test_gets_prop_not_on_card_fails():
    """CR 8.5.8a: card without the property — ADD fails."""
    state = _make_state()
    card = _make_card("no_power_card")  # Action card, no base_power set

    event = gets(state, prop="power", kind=GetsKind.ADD, amount=2,
                 source_card=None, target_card=card)

    assert event.canceled


def test_gets_emits_trigger():
    """After gets, event_manager emits the gets event."""
    state = _make_state()
    card = _attack_card(state, power=3)

    fired = []
    state.event_manager.register("gets", lambda e, s: fired.append(e))

    gets(state, prop="power", kind=GetsKind.ADD, amount=1,
         source_card=None, target_card=card)

    assert len(fired) == 1
    assert fired[0].data["prop"] == "power"
    assert fired[0].data["amount"] == 1


def test_gets_until_end_of_turn_removes_on_event():
    """Temporary gets: effect is removed when until_condition event fires."""
    state = _make_state()
    card = _attack_card(state, power=3)

    gets(state, prop="power", kind=GetsKind.ADD, amount=4,
         source_card=None, target_card=card, until_condition="end_of_turn")

    # Before event: effect active
    result = state.continuous_effect_manager.recalculate(state, card, "power", card.base_power)
    assert result == 7

    state.event_manager.emit(Event(type="end_of_turn"), state)

    # After event: effect removed
    result = state.continuous_effect_manager.recalculate(state, card, "power", card.base_power)
    assert result == 3


# ---------------------------------------------------------------------------
# CR 8.5.9 / 8.5.13 — is_property (gets/is and loses non-numerical property)
# ---------------------------------------------------------------------------

def test_is_property_adds_keyword():
    """CR 8.5.9a: card gains keyword in addition to existing ones."""
    state = _make_state()
    card = _attack_card(state, power=3)
    card.keywords = ["Dominate"]

    event = gets_property(state, prop="keywords", value="Go Again",
                        source_card=None, target_card=card)

    assert not event.canceled
    result = state.continuous_effect_manager.recalculate(state, card, "keywords", set(card.keywords))
    assert "Go Again" in result
    assert "Dominate" in result  # existing keyword preserved


def test_is_property_adds_type():
    """CR 8.5.9a: card gains a type."""
    state = _make_state()
    card = _make_card("test_card", types=["Action"])
    card.owner = 1

    event = gets_property(state, prop="types", value="Attack",
                        source_card=None, target_card=card)

    assert not event.canceled
    result = state.continuous_effect_manager.recalculate(state, card, "types", list(card.types or []))
    assert "Attack" in result
    assert "Action" in result


def test_is_property_only_applies_to_target():
    """Modification does not affect other cards."""
    state = _make_state()
    card_a = _attack_card(state, slug="card_a", power=3)
    card_b = _attack_card(state, slug="card_b", power=3)
    card_a.keywords = []
    card_b.keywords = []

    gets_property(state, prop="keywords", value="Go Again",
                source_card=None, target_card=card_a)

    result_a = state.continuous_effect_manager.recalculate(state, card_a, "keywords", set(card_a.keywords or []))
    result_b = state.continuous_effect_manager.recalculate(state, card_b, "keywords", set(card_b.keywords or []))
    assert "Go Again" in result_a
    assert "Go Again" not in result_b


def test_is_property_invalid_prop_fails():
    """Unknown prop → canceled."""
    state = _make_state()
    card = _attack_card(state)

    event = gets_property(state, prop="flavor_text", value="something",
                        source_card=None, target_card=card)

    assert event.canceled


def test_loses_property_removes_keyword():
    """CR 8.5.13: remove=True removes the property from the card."""
    state = _make_state()
    card = _attack_card(state, power=3)
    card.keywords = ["Go Again", "Dominate"]

    gets_property(state, prop="keywords", value="Go Again",
                source_card=None, target_card=card, remove=True)

    result = state.continuous_effect_manager.recalculate(state, card, "keywords", set(card.keywords))
    assert "Go Again" not in result
    assert "Dominate" in result


def test_is_property_emits_trigger():
    """After is_property, event_manager emits the is_property event."""
    state = _make_state()
    card = _attack_card(state, power=3)
    card.keywords = []

    fired = []
    state.event_manager.register("gets_property", lambda e, s: fired.append(e))

    gets_property(state, prop="keywords", value="Dominate",
                source_card=None, target_card=card)

    assert len(fired) == 1
    assert fired[0].data["value"] == "Dominate"


def test_is_property_until_end_of_turn_removes_on_event():
    """Temporary property: effect removed when until_condition fires."""
    state = _make_state()
    card = _attack_card(state, power=3)
    card.keywords = []

    gets_property(state, prop="keywords", value="Go Again",
                source_card=None, target_card=card, until_condition="end_of_turn")

    result = state.continuous_effect_manager.recalculate(state, card, "keywords", set(card.keywords))
    assert "Go Again" in result

    state.event_manager.emit(Event(type="end_of_turn"), state)

    result = state.continuous_effect_manager.recalculate(state, card, "keywords", set(card.keywords))
    assert "Go Again" not in result


# ---------------------------------------------------------------------------
# CR 8.5.10 — intimidate
# ---------------------------------------------------------------------------

def _hand_with_cards(state, player_id: int, count: int = 3):
    """Add count Action cards to player's hand."""
    cards = []
    for i in range(count):
        c = _make_card(f"hand_card_{i}")
        c.owner = player_id
        c.controller = player_id
        state.players[player_id].hand.add(c)
        cards.append(c)
    return cards


def test_intimidate_banishes_card_from_hand():
    """CR 8.5.10: one random card moves from target's hand to banished."""
    state = _make_state()
    _hand_with_cards(state, 2, count=3)

    event = intimidate(state, source_player_id=1, target_player_id=2)

    assert not event.canceled
    assert event.banished_card is not None
    assert event.banished_card not in state.players[2].hand.cards
    assert event.banished_card in state.players[2].banished.cards
    assert len(state.players[2].hand.cards) == 2


def test_intimidate_emits_trigger():
    """CR 8.5.10a: intimidate event fires regardless."""
    state = _make_state()
    _hand_with_cards(state, 2)

    fired = []
    state.event_manager.register("intimidate", lambda e, s: fired.append(e))

    intimidate(state, source_player_id=1, target_player_id=2)

    assert len(fired) == 1
    assert fired[0].data["target_player_id"] == 2


def test_intimidate_empty_hand_still_intimidated():
    """CR 8.5.10a: player is intimidated even with empty hand; no card banished."""
    state = _make_state()

    fired = []
    state.event_manager.register("intimidate", lambda e, s: fired.append(e))

    event = intimidate(state, source_player_id=1, target_player_id=2)

    assert not event.canceled
    assert event.banished_card is None
    assert len(fired) == 1


def test_intimidate_card_returned_at_end_phase():
    """CR 8.5.10: banished card returns to hand at beginning of end phase."""
    state = _make_state()
    _hand_with_cards(state, 2, count=1)

    event = intimidate(state, source_player_id=1, target_player_id=2)
    card = event.banished_card

    assert card in state.players[2].banished.cards

    state.event_manager.emit(Event(type="end_phase_beginning"), state)

    assert card not in state.players[2].banished.cards
    assert card in state.players[2].hand.cards


def test_intimidate_return_fails_if_card_moved():
    """CR 8.5.10c: if card left banished zone, return does not fire."""
    state = _make_state()
    _hand_with_cards(state, 2, count=1)

    event = intimidate(state, source_player_id=1, target_player_id=2)
    card = event.banished_card

    state.players[2].banished.remove(card)
    state.players[2].graveyard.add(card)

    state.event_manager.emit(Event(type="end_phase_beginning"), state)

    assert card not in state.players[2].hand.cards
    assert card in state.players[2].graveyard.cards


def test_intimidate_multiple_instances_independent():
    """CR 8.5.10c: two intimidate instances each return only their own card."""
    state = _make_state()
    _hand_with_cards(state, 2, count=2)

    intimidate(state, source_player_id=1, target_player_id=2)
    intimidate(state, source_player_id=1, target_player_id=2)

    assert len(state.players[2].banished.cards) == 2

    state.event_manager.emit(Event(type="end_phase_beginning"), state)

    assert len(state.players[2].hand.cards) == 2
    assert len(state.players[2].banished.cards) == 0


def test_intimidate_cancellation():
    """Replacement effect can cancel intimidate."""
    from engine.effects import ReplacementEffect, ReplacementType
    state = _make_state()
    _hand_with_cards(state, 2)
    source = _make_card("effect_source")

    state.effect_manager.replacement_effects.append(
        ReplacementEffect(
            source_card=source,
            replacement_type=ReplacementType.STANDARD,
            condition_fn=lambda e, s: e.get("type") == "intimidate",
            replace_fn=lambda e, s: {**e, "canceled": True},
        )
    )

    event = intimidate(state, source_player_id=1, target_player_id=2)

    assert event.canceled
    assert len(state.players[2].hand.cards) == 3


# ---------------------------------------------------------------------------
# CR 8.5.11 — look
# ---------------------------------------------------------------------------

def _private_card(state, player_id: int, slug="private_card"):
    """Put a private card in player's hand."""
    c = _make_card(slug)
    c.owner = player_id
    c.controller = player_id
    state.players[player_id].hand.add(c)
    return c


def test_look_grants_visibility_to_looker():
    """CR 8.5.11: looker gains visibility into private card."""
    state = _make_state()
    card = _private_card(state, 2)

    event = look(state, target_card=card, looker_ids=[1], source_player_id=1)

    assert not event.canceled
    assert 1 in card.known_by


def test_look_does_not_make_card_public():
    """CR 8.5.11b: card stays private (is_public unchanged)."""
    state = _make_state()
    card = _private_card(state, 2)

    look(state, target_card=card, looker_ids=[1], source_player_id=1)

    assert not card.is_public


def test_look_fails_if_card_already_public():
    """CR 8.5.11c: look on a public card is canceled."""
    state = _make_state()
    card = _make_card("public_card")
    card.owner = 1
    card.controller = 1
    card.is_public = True

    event = look(state, target_card=card, looker_ids=[2], source_player_id=1)

    assert event.canceled
    assert 2 not in card.known_by


def test_look_emits_trigger():
    """After look, event_manager emits the look event."""
    state = _make_state()
    card = _private_card(state, 2)

    fired = []
    state.event_manager.register("look", lambda e, s: fired.append(e))

    look(state, target_card=card, looker_ids=[1], source_player_id=1)

    assert len(fired) == 1
    assert 1 in fired[0].data["looker_ids"]


def test_look_multiple_lookers():
    """Multiple player IDs can be granted visibility at once."""
    state = _make_state()
    card = _private_card(state, 2)

    look(state, target_card=card, looker_ids=[1, 2], source_player_id=1)

    assert 1 in card.known_by
    assert 2 in card.known_by


def test_look_continuous_revokes_on_condition():
    """Continuous look: visibility removed when until_condition fires."""
    state = _make_state()
    card = _private_card(state, 2)

    look(state, target_card=card, looker_ids=[1], source_player_id=1,
         until_condition="end_of_turn")

    assert 1 in card.known_by

    state.event_manager.emit(Event(type="end_of_turn"), state)

    assert 1 not in card.known_by


def test_look_cancellation():
    """Replacement effect can cancel a look."""
    from engine.effects import ReplacementEffect, ReplacementType
    state = _make_state()
    card = _private_card(state, 2)
    source = _make_card("effect_source")

    state.effect_manager.replacement_effects.append(
        ReplacementEffect(
            source_card=source,
            replacement_type=ReplacementType.STANDARD,
            condition_fn=lambda e, s: e.get("type") == "look",
            replace_fn=lambda e, s: {**e, "canceled": True},
        )
    )

    event = look(state, target_card=card, looker_ids=[1], source_player_id=1)

    assert event.canceled
    assert 1 not in card.known_by


# ---------------------------------------------------------------------------
# CR 8.5.12 — lose (asset)
# ---------------------------------------------------------------------------

def test_lose_life_player():
    """Losing life decreases the player's life total."""
    state = _make_state()
    state.players[1].life = 40

    event = lose(state, AssetType.LIFE, 5, source_player_id=0, target_player_id=1)

    assert not event.canceled
    assert state.players[1].life == 35


def test_lose_life_cannot_go_below_zero():
    """Player life cannot go below zero from lose."""
    state = _make_state()
    state.players[1].life = 3

    event = lose(state, AssetType.LIFE, 10, source_player_id=0, target_player_id=1)

    assert state.players[1].life == -7  # life CAN go negative (game-over check is engine's job)


def test_lose_resources():
    """Losing resources decreases the player's resource pool (floor 0)."""
    state = _make_state()
    state.players[1].resources = 4

    lose(state, AssetType.RESOURCES, 2, source_player_id=1, target_player_id=1)

    assert state.players[1].resources == 2


def test_lose_resources_floor_zero():
    """Resources cannot go below 0."""
    state = _make_state()
    state.players[1].resources = 1

    lose(state, AssetType.RESOURCES, 5, source_player_id=1, target_player_id=1)

    assert state.players[1].resources == 0


def test_lose_action_points():
    """Losing action points decreases the player's AP (floor 0)."""
    state = _make_state()
    state.players[1].action_points = 3

    lose(state, AssetType.ACTION_POINTS, 2, source_player_id=1, target_player_id=1)

    assert state.players[1].action_points == 1


def test_lose_life_living_object():
    """Losing life on a card with a life property reduces that card's life."""
    state = _make_state()
    ally = _make_card("test_ally")
    ally.life = 6

    event = lose(state, AssetType.LIFE, 3, source_player_id=0, target_card=ally)

    assert not event.canceled
    assert ally.life == 3


def test_lose_life_non_living_card_fails():
    """CR 8.5.12a: losing {h} on an object without the life property fails."""
    state = _make_state()
    card = _make_card("no_life_card")
    # card.life is None by default

    event = lose(state, AssetType.LIFE, 3, source_player_id=0, target_card=card)

    assert event.canceled


def test_lose_emits_event():
    """lose() emits a 'lose' event."""
    state = _make_state()
    state.players[1].life = 20
    received = []
    state.event_manager.register("lose", lambda ev, s: received.append(ev))

    lose(state, AssetType.LIFE, 5, source_player_id=0, target_player_id=1)

    assert len(received) == 1
    assert received[0].data["asset_type"] == AssetType.LIFE
    assert received[0].data["amount"] == 5


def test_lose_zero_amount_skipped():
    """A lose of 0 is a no-op."""
    state = _make_state()
    state.players[1].life = 20

    event = lose(state, AssetType.LIFE, 0, source_player_id=0, target_player_id=1)

    assert not event.canceled
    assert state.players[1].life == 20


def test_lose_replacement_effect_can_cancel():
    """A replacement effect can cancel a lose event."""
    from engine.effects import ReplacementEffect, ReplacementType
    state = _make_state()
    state.players[1].life = 20
    source = _make_card("shield")

    state.effect_manager.replacement_effects.append(
        ReplacementEffect(
            source_card=source,
            replacement_type=ReplacementType.STANDARD,
            condition_fn=lambda e, s: e.get("type") == "lose",
            replace_fn=lambda e, s: {**e, "canceled": True},
        )
    )

    event = lose(state, AssetType.LIFE, 5, source_player_id=0, target_player_id=1)

    assert event.canceled
    assert state.players[1].life == 20


# ---------------------------------------------------------------------------
# CR 8.5.14 — put_counter
# ---------------------------------------------------------------------------

from engine.effect_keywords import put_counter, PutCounterEvent, remove_counter, RemoveCounterEvent


def test_put_counter_basic():
    """Putting a counter adds it to card.counters."""
    state = _make_state()
    card = _make_card("dawnblade")

    event = put_counter(state, "hit", card, source_player_id=1)

    assert not event.canceled
    assert card.counters["hit"] == 1


def test_put_counter_stacks():
    """Multiple put_counter calls accumulate."""
    state = _make_state()
    card = _make_card("dawnblade")

    put_counter(state, "hit", card)
    put_counter(state, "hit", card)
    put_counter(state, "hit", card)

    assert card.counters["hit"] == 3


def test_put_counter_multiple_amount():
    """Putting amount=3 in one call is one event adding 3 counters."""
    state = _make_state()
    card = _make_card("dawnblade")

    event = put_counter(state, "steam", card, amount=3)

    assert card.counters["steam"] == 3
    assert event.amount == 3


def test_put_counter_different_types_independent():
    """Different counter types are tracked independently."""
    state = _make_state()
    card = _make_card("item_card")

    put_counter(state, "hit", card, amount=2)
    put_counter(state, "steam", card, amount=1)

    assert card.counters["hit"] == 2
    assert card.counters["steam"] == 1


def test_put_counter_emits_event():
    """put_counter emits a 'put_counter' event."""
    state = _make_state()
    card = _make_card("dawnblade")
    received = []
    state.event_manager.register("put_counter", lambda ev, s: received.append(ev))

    put_counter(state, "hit", card, amount=2, source_player_id=1)

    assert len(received) == 1
    assert received[0].data["counter_type"] == "hit"
    assert received[0].data["amount"] == 2


def test_put_counter_replacement_cancels():
    """A replacement effect can cancel a put_counter event."""
    from engine.effects import ReplacementEffect, ReplacementType
    state = _make_state()
    card = _make_card("dawnblade")
    source = _make_card("blocker")

    state.effect_manager.replacement_effects.append(
        ReplacementEffect(
            source_card=source,
            replacement_type=ReplacementType.STANDARD,
            condition_fn=lambda e, s: e.get("type") == "put_counter",
            replace_fn=lambda e, s: {**e, "canceled": True},
        )
    )

    event = put_counter(state, "hit", card)

    assert event.canceled
    assert card.counters.get("hit", 0) == 0


# ---------------------------------------------------------------------------
# CR 8.5.16 — remove_counter
# ---------------------------------------------------------------------------

def test_remove_counter_basic():
    """Removing a counter decrements card.counters."""
    state = _make_state()
    card = _make_card("dawnblade")
    card.counters["hit"] = 3

    event = remove_counter(state, "hit", card)

    assert not event.canceled
    assert card.counters["hit"] == 2
    assert event.actual_removed == 1


def test_remove_counter_clears_key_at_zero():
    """Counter key is removed from dict when count reaches 0."""
    state = _make_state()
    card = _make_card("dawnblade")
    card.counters["hit"] = 1

    remove_counter(state, "hit", card)

    assert "hit" not in card.counters


def test_remove_counter_multiple():
    """CR 8.5.16b: removing multiple counters is one simultaneous event."""
    state = _make_state()
    card = _make_card("dawnblade")
    card.counters["hit"] = 5

    event = remove_counter(state, "hit", card, amount=3)

    assert card.counters["hit"] == 2
    assert event.actual_removed == 3


def test_remove_counter_caps_at_available():
    """Removing more than available removes only what exists."""
    state = _make_state()
    card = _make_card("dawnblade")
    card.counters["hit"] = 2

    event = remove_counter(state, "hit", card, amount=10)

    assert event.actual_removed == 2
    assert "hit" not in card.counters


def test_remove_counter_none_present():
    """Removing a counter type that doesn't exist removes 0."""
    state = _make_state()
    card = _make_card("dawnblade")

    event = remove_counter(state, "steam", card)

    assert event.actual_removed == 0
    assert card.counters.get("steam", 0) == 0


def test_remove_counter_emits_event():
    """remove_counter emits a 'remove_counter' event."""
    state = _make_state()
    card = _make_card("dawnblade")
    card.counters["hit"] = 2
    received = []
    state.event_manager.register("remove_counter", lambda ev, s: received.append(ev))

    remove_counter(state, "hit", card, amount=2, source_player_id=1)

    assert len(received) == 1
    assert received[0].data["actual_removed"] == 2


# ---------------------------------------------------------------------------
# CR 8.5.15 — put_object
# ---------------------------------------------------------------------------

from engine.effect_keywords import put_object, PutObjectEvent


def test_put_object_hand_to_graveyard():
    """Moving a card from hand to graveyard updates zone and card.zone."""
    state = _make_state()
    card = _make_card("test_card")
    card.owner = 1
    state.players[1].hand.add(card)

    assert card in state.players[1].hand.cards

    event = put_object(state, card, "graveyard", destination_player_id=1, source_player_id=1)

    assert not event.canceled
    assert card not in state.players[1].hand.cards
    assert card in state.players[1].graveyard.cards
    assert card.zone == "graveyard"


def test_put_object_graveyard_to_hand():
    """Return a card from graveyard to hand (the 'return' form of CR 8.5.15)."""
    state = _make_state()
    card = _make_card("test_card")
    card.owner = 1
    state.players[1].graveyard.add(card)

    event = put_object(state, card, "hand", destination_player_id=1)

    assert not event.canceled
    assert card in state.players[1].hand.cards
    assert card not in state.players[1].graveyard.cards
    assert card.zone == "hand"


def test_put_object_defaults_owner_as_destination():
    """When destination_player_id omitted, defaults to card.owner."""
    state = _make_state()
    card = _make_card("test_card")
    card.owner = 2
    state.players[2].hand.add(card)

    event = put_object(state, card, "graveyard")

    assert not event.canceled
    assert card in state.players[2].graveyard.cards


def test_put_object_cross_player_owner_zone_rejected():
    """Zone entry rules reject moving a card into another player's owner-restricted zone.

    CR 3.x owner checks: graveyard/hand/deck/arsenal/banished belong to a specific player.
    An effect trying to put a card into the wrong owner's zone fails (FAIL result),
    and the card is returned to its source zone.
    """
    state = _make_state()
    card = _make_card("test_card")
    card.owner = 1
    state.players[1].hand.add(card)

    # try to move into player 2's graveyard — owner mismatch, should be rejected
    event = put_object(state, card, "graveyard", destination_player_id=2)

    assert event.canceled
    # card returned to source (hand)
    assert card in state.players[1].hand.cards
    assert card not in state.players[2].graveyard.cards


def test_put_object_invalid_destination_cancels():
    """Moving to a non-existent zone cancels and returns card to source."""
    state = _make_state()
    card = _make_card("test_card")
    card.owner = 1
    state.players[1].hand.add(card)

    event = put_object(state, card, "nonexistent_zone", destination_player_id=1)

    assert event.canceled
    # card returned to hand
    assert card in state.players[1].hand.cards


def test_put_object_emits_event():
    """put_object emits a 'put_object' event."""
    state = _make_state()
    card = _make_card("test_card")
    card.owner = 1
    state.players[1].hand.add(card)
    received = []
    state.event_manager.register("put_object", lambda ev, s: received.append(ev))

    put_object(state, card, "graveyard", destination_player_id=1)

    assert len(received) == 1
    assert received[0].data["destination_zone"] == "graveyard"


def test_put_object_replacement_redirects_destination():
    """A replacement effect can redirect the destination zone."""
    from engine.effects import ReplacementEffect, ReplacementType
    state = _make_state()
    card = _make_card("test_card")
    card.owner = 1
    state.players[1].hand.add(card)
    source = _make_card("redirect_effect")

    # redirect graveyard → banished
    state.effect_manager.replacement_effects.append(
        ReplacementEffect(
            source_card=source,
            replacement_type=ReplacementType.STANDARD,
            condition_fn=lambda e, s: e.get("type") == "put_object" and e.get("destination_zone") == "graveyard",
            replace_fn=lambda e, s: {**e, "destination_zone": "banished"},
        )
    )

    put_object(state, card, "graveyard", destination_player_id=1)

    assert card in state.players[1].banished.cards
    assert card not in state.players[1].graveyard.cards


# ---------------------------------------------------------------------------
# CR 8.5.17 — reveal
# ---------------------------------------------------------------------------

from engine.effect_keywords import reveal, RevealEvent


def _private_card_in_hand(state, player_id, slug="reveal_target"):
    card = _make_card(slug)
    card.owner = player_id
    card.is_public = False
    state.players[player_id].hand.add(card)
    return card


def test_reveal_discrete_makes_public_then_private():
    """CR 8.5.17b: discrete reveal — card is public during event, private after."""
    state = _make_state()
    card = _private_card_in_hand(state, 1)

    # capture is_public at the moment the 'reveal' event fires
    public_during_event = []
    state.event_manager.register("reveal", lambda ev, s: public_during_event.append(card.is_public))

    event = reveal(state, [card], source_player_id=1)

    assert not event.canceled
    assert public_during_event == [True]   # was public when event fired
    assert card.is_public is False         # made private again after


def test_reveal_fails_if_already_public():
    """CR 8.5.17d: reveal fails if card is already public."""
    state = _make_state()
    card = _make_card("public_card")
    card.owner = 1
    state.players[1].hand.add(card)
    card.is_public = True  # set after add so zone default doesn't overwrite

    event = reveal(state, [card], source_player_id=1)

    assert event.canceled


def test_reveal_continuous_stays_public_until_condition():
    """CR 8.5.17b: continuous reveal — card stays public until until_condition fires."""
    state = _make_state()
    card = _private_card_in_hand(state, 1)

    reveal(state, [card], source_player_id=1, until_condition="end_of_turn")

    assert card.is_public is True

    state.event_manager.emit(Event(type="end_of_turn"), state)

    assert card.is_public is False


def test_reveal_does_not_change_zone():
    """CR 8.5.17c: revealing a card does not move it."""
    state = _make_state()
    card = _private_card_in_hand(state, 1)

    reveal(state, [card], source_player_id=1)

    assert card in state.players[1].hand.cards
    assert card.zone == "hand"


def test_reveal_multiple_cards():
    """CR 8.5.17e: revealing N cards is a single reveal event."""
    state = _make_state()
    cards = [_private_card_in_hand(state, 1, slug=f"card_{i}") for i in range(3)]
    received = []
    state.event_manager.register("reveal", lambda ev, s: received.append(ev))

    event = reveal(state, cards, source_player_id=1)

    assert not event.canceled
    assert len(event.target_cards) == 3
    assert len(received) == 1   # single event for all N cards
    # all made private again
    for c in cards:
        assert c.is_public is False


def test_reveal_mixed_public_private_only_reveals_private():
    """Private cards in a mixed list are revealed; already-public cards are skipped."""
    state = _make_state()
    private_card = _private_card_in_hand(state, 1, slug="private_one")
    public_card = _make_card("public_one")
    public_card.owner = 1
    state.players[1].hand.add(public_card)
    public_card.is_public = True  # set after add so zone default doesn't overwrite

    event = reveal(state, [private_card, public_card], source_player_id=1)

    # not canceled — at least one eligible card
    assert not event.canceled
    assert len(event.target_cards) == 1
    assert event.target_cards[0].slug == "private_one"


def test_reveal_replacement_can_cancel():
    """A replacement effect can cancel a reveal."""
    from engine.effects import ReplacementEffect, ReplacementType
    state = _make_state()
    card = _private_card_in_hand(state, 1)
    source = _make_card("blocker")

    state.effect_manager.replacement_effects.append(
        ReplacementEffect(
            source_card=source,
            replacement_type=ReplacementType.STANDARD,
            condition_fn=lambda e, s: e.get("type") == "reveal",
            replace_fn=lambda e, s: {**e, "canceled": True},
        )
    )

    event = reveal(state, [card], source_player_id=1)

    assert event.canceled
    assert card.is_public is False


# ---------------------------------------------------------------------------
# CR 8.5.18 — roll
# ---------------------------------------------------------------------------

from engine.effect_keywords import roll, RollEvent
import random as _random_module


def test_roll_single_die_in_range():
    """Rolling a d6 produces a result in [1, 6]."""
    state = _make_state()
    event = roll(state, num_dice=1, faces=6)
    assert not event.canceled
    assert len(event.results) == 1
    assert 1 <= event.results[0] <= 6
    assert event.total == event.results[0]


def test_roll_multiple_dice_simultaneous():
    """CR 8.5.18a: rolling 3d6 is a single event with 3 results."""
    state = _make_state()
    received = []
    state.event_manager.register("roll", lambda ev, s: received.append(ev))

    event = roll(state, num_dice=3, faces=6)

    assert len(event.results) == 3
    assert len(received) == 1  # one event for all dice
    assert event.total == sum(event.results)


def test_roll_deterministic_with_rng():
    """Seeded RNG gives reproducible results."""
    state = _make_state()
    rng = _random_module.Random(42)

    event = roll(state, num_dice=2, faces=6, rng=rng)

    # with seed 42: randint(1,6) twice
    rng2 = _random_module.Random(42)
    expected = tuple(rng2.randint(1, 6) for _ in range(2))
    assert event.results == expected


def test_roll_custom_faces():
    """Rolling a d12 keeps results within [1, 12]."""
    state = _make_state()
    for _ in range(20):
        event = roll(state, num_dice=1, faces=12)
        assert 1 <= event.results[0] <= 12


def test_roll_emits_event():
    """roll() emits a 'roll' event with results data."""
    state = _make_state()
    received = []
    state.event_manager.register("roll", lambda ev, s: received.append(ev))

    roll(state, num_dice=2, faces=6, source_player_id=1)

    assert len(received) == 1
    assert received[0].data["num_dice"] == 2
    assert len(received[0].data["results"]) == 2


def test_roll_replacement_can_cancel():
    """A replacement effect can cancel a roll."""
    from engine.effects import ReplacementEffect, ReplacementType
    state = _make_state()
    source = _make_card("loaded_die")

    state.effect_manager.replacement_effects.append(
        ReplacementEffect(
            source_card=source,
            replacement_type=ReplacementType.STANDARD,
            condition_fn=lambda e, s: e.get("type") == "roll",
            replace_fn=lambda e, s: {**e, "canceled": True},
        )
    )

    event = roll(state, num_dice=1, faces=6)

    assert event.canceled
    assert event.results == ()


# ---------------------------------------------------------------------------
# CR 8.5.19 — search
# ---------------------------------------------------------------------------

from engine.effect_keywords import search, SearchEvent


def _fill_deck_slugs(state, player_id, slugs):
    """Helper: put named cards into a player's deck."""
    for slug in slugs:
        card = _make_card(slug)
        card.owner = player_id
        state.players[player_id].deck.add(card)
    return [state.players[player_id].deck.find(s) for s in slugs]


def test_search_finds_and_returns_chosen_card():
    """Basic search: selector picks a card and it is returned."""
    state = _make_state()
    cards = _fill_deck_slugs(state, 1, ["card_a", "card_b", "card_c"])

    event = search(state, search_player_id=1, zone_names=["deck"],
                   selector=lambda eligible, can_fail: eligible[0])

    assert not event.failed
    assert not event.canceled
    assert event.chosen_card is not None
    assert event.chosen_card.slug == "card_a"


def test_search_empty_zone_fails():
    """CR 8.5.19d: searching an empty zone fails."""
    state = _make_state()
    # deck is empty by default

    event = search(state, search_player_id=1, zone_names=["deck"],
                   selector=lambda eligible, can_fail: eligible[0])

    assert event.failed


def test_search_filter_restricts_eligible():
    """filter_fn limits which cards can be chosen."""
    state = _make_state()
    _fill_deck_slugs(state, 1, ["attack_red", "attack_blue", "defense_card"])
    for c in state.players[1].deck.cards:
        c.raw_types = ["Attack Action"] if "attack" in c.slug else ["Defense Reaction"]

    event = search(state, search_player_id=1, zone_names=["deck"],
                   filter_fn=lambda c: "Attack Action" in (c.raw_types or []),
                   selector=lambda eligible, can_fail: eligible[0])

    assert not event.failed
    assert event.chosen_card is not None
    assert "attack" in event.chosen_card.slug
    assert len(event.eligible_cards) == 2


def test_search_no_filter_cannot_fail():
    """CR 8.5.19c: no filter + non-empty zone → can_fail=False passed to selector."""
    state = _make_state()
    _fill_deck_slugs(state, 1, ["card_a"])

    can_fail_seen = []
    def selector(eligible, can_fail):
        can_fail_seen.append(can_fail)
        return eligible[0]

    search(state, search_player_id=1, zone_names=["deck"], selector=selector)

    assert can_fail_seen == [False]


def test_search_filter_no_public_match_can_fail():
    """CR 8.5.19a: filter given, no public matching cards → can_fail=True."""
    state = _make_state()
    card = _make_card("private_match")
    card.owner = 1
    card.is_public = False
    state.players[1].deck.add(card)

    can_fail_seen = []
    def selector(eligible, can_fail):
        can_fail_seen.append(can_fail)
        return None  # player declines

    event = search(state, search_player_id=1, zone_names=["deck"],
                   filter_fn=lambda c: True,
                   selector=selector)

    assert can_fail_seen == [True]
    assert event.failed


def test_search_filter_public_match_cannot_fail():
    """CR 8.5.19b: filter given + public matching card → can_fail=False."""
    state = _make_state()
    card = _make_card("public_match")
    card.owner = 1
    state.players[1].deck.add(card)
    card.is_public = True  # set after add

    can_fail_seen = []
    def selector(eligible, can_fail):
        can_fail_seen.append(can_fail)
        return eligible[0]

    search(state, search_player_id=1, zone_names=["deck"],
           filter_fn=lambda c: True,
           selector=selector)

    assert can_fail_seen == [False]


def test_search_emits_event():
    """search() emits a 'search' event."""
    state = _make_state()
    _fill_deck_slugs(state, 1, ["card_a"])
    received = []
    state.event_manager.register("search", lambda ev, s: received.append(ev))

    search(state, search_player_id=1, zone_names=["deck"],
           selector=lambda eligible, can_fail: eligible[0])

    assert len(received) == 1
    assert received[0].data["chosen_card"].slug == "card_a"


def test_search_no_eligible_after_filter_fails():
    """If filter matches nothing, search fails."""
    state = _make_state()
    _fill_deck_slugs(state, 1, ["attack_card"])

    event = search(state, search_player_id=1, zone_names=["deck"],
                   filter_fn=lambda c: False,  # nothing matches
                   selector=lambda eligible, can_fail: eligible[0])

    assert event.failed
    assert event.chosen_card is None


# ---------------------------------------------------------------------------
# CR 8.5.20 — shuffle
# ---------------------------------------------------------------------------

from engine.effect_keywords import shuffle, ShuffleEvent
import random as _random_module


def test_shuffle_randomizes_order():
    """Shuffling a deck changes card order (statistically)."""
    state = _make_state()
    _fill_deck_slugs(state, 1, [f"card_{i}" for i in range(20)])
    original_order = [c.slug for c in state.players[1].deck.cards]

    rng = _random_module.Random(99)
    shuffle(state, target_player_id=1, rng=rng)

    new_order = [c.slug for c in state.players[1].deck.cards]
    assert new_order != original_order  # seed 99 should reorder 20 cards


def test_shuffle_empty_zone_succeeds():
    """CR 8.5.20a: shuffling an empty zone is still valid."""
    state = _make_state()
    # deck is empty
    event = shuffle(state, target_player_id=1)
    assert not event.canceled


def test_shuffle_cards_to_add():
    """CR 8.5.20b: cards_to_add are placed into the zone before shuffling."""
    state = _make_state()
    _fill_deck_slugs(state, 1, ["existing"])
    new_card = _make_card("newly_added")
    new_card.owner = 1

    shuffle(state, target_player_id=1, cards_to_add=[new_card])

    deck_slugs = [c.slug for c in state.players[1].deck.cards]
    assert "newly_added" in deck_slugs
    assert new_card.zone == "deck"


def test_shuffle_defaults_to_deck():
    """CR 8.5.20c: default zone is the player's deck."""
    state = _make_state()
    _fill_deck_slugs(state, 1, ["card_a", "card_b"])

    event = shuffle(state, target_player_id=1)

    assert event.zone_name == "deck"
    assert not event.canceled


def test_shuffle_emits_event():
    """shuffle() emits a 'shuffle' event."""
    state = _make_state()
    received = []
    state.event_manager.register("shuffle", lambda ev, s: received.append(ev))

    shuffle(state, target_player_id=1)

    assert len(received) == 1
    assert received[0].data["target_player_id"] == 1


def test_shuffle_replacement_can_cancel():
    """A replacement effect can cancel a shuffle."""
    from engine.effects import ReplacementEffect, ReplacementType
    state = _make_state()
    source = _make_card("stacked_deck")

    state.effect_manager.replacement_effects.append(
        ReplacementEffect(
            source_card=source,
            replacement_type=ReplacementType.STANDARD,
            condition_fn=lambda e, s: e.get("type") == "shuffle",
            replace_fn=lambda e, s: {**e, "canceled": True},
        )
    )

    event = shuffle(state, target_player_id=1)

    assert event.canceled


def test_shuffle_invalidates_pitch_history():
    """CR 8.5.20: shuffling makes previous pitch-order information unknown."""
    state = _make_state()
    _fill_deck_slugs(state, 1, ["card_a", "card_b"])
    state.record_pitch(1, ["blue_pitch"])
    assert state.pitch_history[1]

    shuffle(state, target_player_id=1)

    assert state.pitch_history[1] == {}


# ---------------------------------------------------------------------------
# CR 8.5.21 — name
# ---------------------------------------------------------------------------

from engine.effect_keywords import name, NameEvent


def test_name_records_value():
    """Basic name: records the named string."""
    state = _make_state()
    event = name(state, named_value="Enlightened Strike", source_player_id=1)
    assert not event.canceled
    assert event.named_value == "Enlightened Strike"


def test_name_emits_event():
    """name() emits a 'name' event."""
    state = _make_state()
    received = []
    state.event_manager.register("name", lambda ev, s: received.append(ev))
    name(state, named_value="Snatch", source_player_id=1)
    assert len(received) == 1
    assert received[0].data["named_value"] == "Snatch"


def test_name_replacement_can_cancel():
    """A replacement effect can cancel a name event."""
    from engine.effects import ReplacementEffect, ReplacementType
    state = _make_state()
    source = _make_card("blocker")
    state.effect_manager.replacement_effects.append(
        ReplacementEffect(
            source_card=source,
            replacement_type=ReplacementType.STANDARD,
            condition_fn=lambda e, s: e.get("type") == "name",
            replace_fn=lambda e, s: {**e, "canceled": True},
        )
    )
    event = name(state, named_value="Test", source_player_id=1)
    assert event.canceled


# ---------------------------------------------------------------------------
# CR 8.5.22 — opt
# ---------------------------------------------------------------------------

from engine.effect_keywords import opt, OptEvent


def test_opt_puts_cards_top_and_bottom():
    """Opt N: selector splits cards to top and bottom, deck order preserved."""
    state = _make_state()
    _fill_deck_slugs(state, 1, ["a", "b", "c"])
    # deck[0]=top: a is top, b middle, c is bottom

    # Look at top 2 (a, b); put a on top, b on bottom
    def selector(cards):
        return ([cards[0]], cards[1:])

    event = opt(state, n=2, target_player_id=1, selector=selector)
    assert not event.canceled
    assert len(event.top_cards) == 1
    assert len(event.bottom_cards) == 1
    deck = [c.slug for c in state.players[1].deck.cards]
    assert deck[0] == "a"   # top_cards[0] → deck[0]
    assert deck[-1] == "b"  # bottom_cards[0] → deck[-1]


def test_opt_empty_deck_cancels():
    """CR 8.5.22b: opt on empty deck fails."""
    state = _make_state()
    event = opt(state, n=3, target_player_id=1,
                selector=lambda cards: (cards, []))
    assert event.canceled


def test_opt_fewer_cards_than_n():
    """CR 8.5.22a: if deck < N, use all available."""
    state = _make_state()
    _fill_deck_slugs(state, 1, ["only_one"])

    event = opt(state, n=5, target_player_id=1,
                selector=lambda cards: (cards, []))
    assert not event.canceled
    assert len(event.top_cards) == 1


def test_opt_emits_event():
    """opt() emits an 'opt' event."""
    state = _make_state()
    _fill_deck_slugs(state, 1, ["x", "y"])
    received = []
    state.event_manager.register("opt", lambda ev, s: received.append(ev))
    opt(state, n=2, target_player_id=1,
        selector=lambda cards: (cards, []))
    assert len(received) == 1


# ---------------------------------------------------------------------------
# CR 8.5.23 — reload
# ---------------------------------------------------------------------------

from engine.effect_keywords import reload, ReloadEvent


def test_reload_moves_card_to_arsenal():
    """Reload moves card from hand to arsenal face-down."""
    state = _make_state()
    card = _add_to_hand(state, 1, _make_card("reload_me"))

    event = reload(state, card=card, player_id=1, chose_to_reload=True)

    assert not event.canceled
    assert card not in state.players[1].hand.cards
    assert card in state.players[1].arsenal.cards


def test_reload_declined_no_move():
    """If chose_to_reload=False, no move happens and event is not canceled."""
    state = _make_state()
    card = _add_to_hand(state, 1, _make_card("keep_me"))

    event = reload(state, card=card, player_id=1, chose_to_reload=False)

    assert not event.canceled
    assert card in state.players[1].hand.cards


def test_reload_full_arsenal_cancels():
    """CR 8.5.23a: reload fails if arsenal is not empty."""
    state = _make_state()
    blocker = _make_card("existing")
    blocker.owner = 1
    state.players[1].arsenal.add(blocker)
    card = _add_to_hand(state, 1, _make_card("reload_me"))

    event = reload(state, card=card, player_id=1, chose_to_reload=True)

    assert event.canceled
    assert card in state.players[1].hand.cards


# ---------------------------------------------------------------------------
# CR 8.5.24 — turn
# ---------------------------------------------------------------------------

from engine.effect_keywords import turn, TurnEvent


def test_turn_face_up():
    """Turn face-up makes card public."""
    state = _make_state()
    card = _make_card("hidden")
    card.is_public = False

    event = turn(state, card=card, face_up=True)

    assert not event.canceled
    assert card.is_public is True


def test_turn_face_down():
    """Turn face-down makes card private."""
    state = _make_state()
    card = _make_card("visible")
    card.is_public = True

    event = turn(state, card=card, face_up=False)

    assert not event.canceled
    assert card.is_public is False


def test_turn_already_face_up_cancels():
    """CR 8.5.24a: fails if already at target visibility."""
    state = _make_state()
    card = _make_card("already_up")
    card.is_public = True

    event = turn(state, card=card, face_up=True)
    assert event.canceled


def test_turn_already_face_down_cancels():
    """CR 8.5.24a: fails if already face-down."""
    state = _make_state()
    card = _make_card("already_down")
    card.is_public = False

    event = turn(state, card=card, face_up=False)
    assert event.canceled


# ---------------------------------------------------------------------------
# CR 8.5.26 — negate
# ---------------------------------------------------------------------------

from engine.effect_keywords import negate, NegateEvent


def test_negate_removes_layer_from_stack():
    """Negate removes a layer from state.stack and marks it as negated."""
    state = _make_state()
    card = _make_card("on_stack")
    state.stack.add(card)

    event = negate(state, layer=card)

    assert not event.canceled
    assert card not in state.stack.cards
    # CR 8.5.26: layer is marked as not-resolving
    assert getattr(card, 'negated', False) is True


def test_negate_not_on_stack_cancels():
    """Negate fails if layer is not on the stack."""
    state = _make_state()
    card = _make_card("not_on_stack")

    event = negate(state, layer=card)
    assert event.canceled


# ---------------------------------------------------------------------------
# CR 8.5.27 — repeat
# ---------------------------------------------------------------------------

from engine.effect_keywords import repeat, RepeatEvent


def test_repeat_calls_process():
    """Repeat executes the callable."""
    state = _make_state()
    called = []
    def _once():
        called.append(True)
        return False  # stop after one iteration
    event = repeat(state, process=_once)
    assert not event.canceled
    assert len(called) == 1


def test_repeat_emits_event():
    """repeat() emits a 'repeat' event."""
    state = _make_state()
    received = []
    state.event_manager.register("repeat", lambda ev, s: received.append(ev))
    repeat(state, process=lambda: False)
    assert len(received) == 1


def test_repeat_stops_when_process_returns_false():
    """CR 8.5.27b: repeat stops when instructions fail to advance game state."""
    state = _make_state()
    call_count = [0]
    def _three_times():
        call_count[0] += 1
        return call_count[0] < 3  # True twice, then False
    repeat(state, process=_three_times)
    assert call_count[0] == 3


def test_repeat_respects_max_iterations():
    """Hard cap prevents infinite loops."""
    state = _make_state()
    call_count = [0]
    def _always_true():
        call_count[0] += 1
        return True
    repeat(state, process=_always_true, max_iterations=5)
    assert call_count[0] == 5


# ---------------------------------------------------------------------------
# CR 8.5.28 — reroll
# ---------------------------------------------------------------------------

from engine.effect_keywords import reroll, RerollEvent
import random as _random


def test_reroll_produces_new_results():
    """Reroll returns new dice results."""
    state = _make_state()
    rng = _random.Random(42)
    event = reroll(state, dice_results=[1, 2, 3], faces=6, rng=rng)
    assert not event.canceled
    assert len(event.new_results) == 3
    assert all(1 <= r <= 6 for r in event.new_results)
    assert event.original_results == (1, 2, 3)


def test_reroll_emits_event():
    """reroll() emits a 'reroll' event."""
    state = _make_state()
    received = []
    state.event_manager.register("reroll", lambda ev, s: received.append(ev))
    rng = _random.Random(99)
    reroll(state, dice_results=[4], faces=6, rng=rng)
    assert len(received) == 1


# ---------------------------------------------------------------------------
# CR 8.5.29 — charge
# ---------------------------------------------------------------------------

from engine.effect_keywords import charge, ChargeEvent


def test_charge_moves_card_to_empty_soul():
    """Charge moves card from hand to soul zone."""
    state = _make_state()
    card = _add_to_hand(state, 1, _make_card("soul_card"))

    event = charge(state, card=card, player_id=1)
    player = state.players[1]
    print(card.zone)
    print(card.prev_zone)
    assert not event.canceled
    assert card not in player.hand.cards
    assert card.is_sub_card
    assert card.top_card is player.hero
    assert card is player.hero.cards_underneath[0]
    assert len(player.soul.cards) == 1
    assert card in state.players[1].soul.cards

def test_charge_moves_card_to_non_empty_soul():
    state = _make_state()
    card = _add_to_hand(state, 1, _make_card("soul_card"))
    card2 = _add_to_hand(state, 1, _make_card("soul_card_2"))
    event = charge(state, card=card, player_id=1)
    event2 = charge(state, card=card2, player_id=1)

    player = state.players[1]
    assert not event.canceled
    assert not event2.canceled
    assert card not in player.hand.cards
    assert card2 not in player.hand.cards
    assert card.is_sub_card
    assert card2.is_sub_card
    assert card.top_card is player.hero
    assert card2.top_card is player.hero
    assert card is player.hero.cards_underneath[0]
    assert card2 is player.hero.cards_underneath[1]
    assert len(player.soul.cards) == 2
    assert card in player.soul.cards
    assert card2 in player.soul.cards


def test_charge_emits_event():
    """charge() emits a 'charge' event."""
    state = _make_state()
    card = _add_to_hand(state, 1, _make_card("soul_card"))

    received = []
    state.event_manager.register("charge", lambda ev, s: received.append(ev))
    charge(state, card=card, player_id=1)
    assert len(received) == 1
    assert received[0].card == "soul_card"


# ---------------------------------------------------------------------------
# CR 8.5.30 — distribute
# ---------------------------------------------------------------------------

from engine.effect_keywords import distribute, DistributeEvent


def test_distribute_puts_counters_on_targets():
    """Distribute places counters across multiple cards."""
    state = _make_state()
    c1 = _make_card("target_a")
    c2 = _make_card("target_b")

    event = distribute(state, counter_type="damage", distribution=[(c1, 2), (c2, 3)])

    assert not event.canceled
    assert c1.counters.get("damage", 0) == 2
    assert c2.counters.get("damage", 0) == 3


def test_distribute_emits_event():
    """distribute() emits a 'distribute' event."""
    state = _make_state()
    c1 = _make_card("t1")
    received = []
    state.event_manager.register("distribute", lambda ev, s: received.append(ev))
    distribute(state, counter_type="damage", distribution=[(c1, 1)])
    assert len(received) == 1
    assert sum(amt for _, amt in received[0].data["distribution"]) == 1


# ---------------------------------------------------------------------------
# CR 8.5.31 — pay
# ---------------------------------------------------------------------------

from engine.effect_keywords import pay, PayEvent


def test_pay_deducts_resources():
    """Pay deducts from player resources."""
    state = _make_state()
    state.players[1].resources = 5
    event = pay(state, asset_type=AssetType.RESOURCES, amount=3, player_id=1)
    assert not event.canceled
    assert state.players[1].resources == 2


def test_pay_deducts_life():
    """Pay deducts life."""
    state = _make_state()
    state.players[1].life = 20
    event = pay(state, asset_type=AssetType.LIFE, amount=2, player_id=1)
    assert not event.canceled
    assert state.players[1].life == 18


def test_pay_declined():
    """CR 8.5.31a: player can refuse to pay."""
    state = _make_state()
    state.players[1].resources = 5
    event = pay(state, asset_type=AssetType.RESOURCES, amount=3, player_id=1, chose_to_pay=False)
    assert not event.canceled
    assert state.players[1].resources == 5


def test_pay_emits_event():
    """pay() emits a 'pay' event."""
    state = _make_state()
    state.players[1].resources = 10
    received = []
    state.event_manager.register("pay", lambda ev, s: received.append(ev))
    pay(state, asset_type=AssetType.RESOURCES, amount=2, player_id=1)
    assert len(received) == 1


# ---------------------------------------------------------------------------
# CR 8.5.34 — freeze
# ---------------------------------------------------------------------------

from engine.effect_keywords import freeze, FreezeEvent


def test_freeze_sets_frozen_counter():
    """Freeze sets __frozen__ counter on card."""
    state = _make_state()
    card = _make_card("ice_target")

    event = freeze(state, target_card=card)

    assert not event.canceled
    assert card.counters.get("__frozen__", 0) == 1


def test_freeze_stacks():
    """Multiple freezes increment the counter."""
    state = _make_state()
    card = _make_card("ice_target")
    freeze(state, target_card=card)
    freeze(state, target_card=card)
    assert card.counters["__frozen__"] == 2


def test_freeze_emits_event():
    """freeze() emits a 'freeze' event."""
    state = _make_state()
    card = _make_card("ice_target")
    received = []
    state.event_manager.register("freeze", lambda ev, s: received.append(ev))
    freeze(state, target_card=card)
    assert len(received) == 1


# ---------------------------------------------------------------------------
# CR 8.5.37 — unfreeze
# ---------------------------------------------------------------------------

from engine.effect_keywords import unfreeze, UnfreezeEvent


def test_unfreeze_removes_frozen():
    """Unfreeze removes all __frozen__ counters."""
    state = _make_state()
    card = _make_card("thaw_me")
    card.counters["__frozen__"] = 2

    event = unfreeze(state, target_card=card)

    assert not event.canceled
    assert "__frozen__" not in card.counters


def test_unfreeze_not_frozen_cancels():
    """CR 8.5.37b: unfreeze fails if not frozen."""
    state = _make_state()
    card = _make_card("not_frozen")
    event = unfreeze(state, target_card=card)
    assert event.canceled


def test_unfreeze_emits_event():
    """unfreeze() emits an 'unfreeze' event."""
    state = _make_state()
    card = _make_card("thaw_me")
    card.counters["__frozen__"] = 1
    received = []
    state.event_manager.register("unfreeze", lambda ev, s: received.append(ev))
    unfreeze(state, target_card=card)
    assert len(received) == 1


# ---------------------------------------------------------------------------
# CR 8.5.41 — equip
# ---------------------------------------------------------------------------

from engine.effect_keywords import equip, EquipEvent


def test_equip_moves_card_to_zone():
    """Equip puts a card into the specified zone via put_object."""
    state = _make_state()
    card = _make_card("my_helmet")
    card.owner = 1
    card.raw_types = ["Equipment"]
    card.types = ["Equipment"]
    card.subtypes = ["Head"]
    state.players[1].hand.add(card)

    event = equip(state, card=card, zone_name="head", player_id=1)

    assert not event.canceled
    assert card in state.players[1].head.cards


def test_equip_emits_event():
    """equip() emits an 'equip' event after successful equip."""
    state = _make_state()
    card = _make_card("my_helmet")
    card.owner = 1
    card.raw_types = ["Equipment"]
    card.types = ["Equipment"]
    card.subtypes = ["Head"]
    state.players[1].hand.add(card)
    received = []
    state.event_manager.register("equip", lambda ev, s: received.append(ev))
    equip(state, card=card, zone_name="head", player_id=1)
    assert len(received) == 1


# ---------------------------------------------------------------------------
# CR 8.5.42 — move counter
# ---------------------------------------------------------------------------

from engine.effect_keywords import move_counter, MoveCounterEvent


def test_move_counter_transfers():
    """Move counter removes from source and adds to target."""
    state = _make_state()
    c1 = _make_card("source")
    c2 = _make_card("dest")
    c1.counters["steam"] = 3

    event = move_counter(state, counter_type="steam", from_card=c1, to_card=c2)

    assert not event.canceled
    assert c1.counters.get("steam", 0) == 2
    assert c2.counters.get("steam", 0) == 1


def test_move_counter_no_counter_cancels():
    """CR 8.5.42a: if no counter exists, nothing happens."""
    state = _make_state()
    c1 = _make_card("empty")
    c2 = _make_card("dest")

    event = move_counter(state, counter_type="steam", from_card=c1, to_card=c2)
    assert event.canceled


def test_move_counter_emits_event():
    """move_counter() emits a 'move_counter' event."""
    state = _make_state()
    c1 = _make_card("source")
    c2 = _make_card("dest")
    c1.counters["steam"] = 1
    received = []
    state.event_manager.register("move_counter", lambda ev, s: received.append(ev))
    move_counter(state, counter_type="steam", from_card=c1, to_card=c2)
    assert len(received) == 1


# ---------------------------------------------------------------------------
# CR 8.5.44 — pitch
# ---------------------------------------------------------------------------

from engine.effect_keywords import pitch, PitchEvent


def test_pitch_moves_to_pitch_zone_and_gains_resources():
    """Pitch moves card to pitch zone and gains resources."""
    state = _make_state()
    card = _make_card("pitch_card")
    card.owner = 1
    card.pitch = 3
    state.players[1].hand.add(card)
    state.players[1].resources = 0

    event = pitch(state, card=card, player_id=1, source_player_id=1)

    assert not event.canceled
    assert event.pitch_value == 3
    assert card in state.players[1].pitch.cards
    assert state.players[1].resources == 3


def test_pitch_zero_value_no_gain():
    """Pitch with 0 pitch value moves card but grants no resources."""
    state = _make_state()
    card = _make_card("no_pitch")
    card.owner = 1
    card.pitch = 0
    state.players[1].hand.add(card)
    state.players[1].resources = 0

    event = pitch(state, card=card, player_id=1, source_player_id=1)

    assert not event.canceled
    assert state.players[1].resources == 0


def test_pitch_emits_event():
    """pitch() emits a 'pitch' event."""
    state = _make_state()
    card = _make_card("pitch_card")
    card.owner = 1
    card.pitch = 1
    state.players[1].hand.add(card)
    received = []
    state.event_manager.register("pitch", lambda ev, s: received.append(ev))
    pitch(state, card=card, player_id=1, source_player_id=1)
    assert len(received) == 1
    assert received[0].data["pitch_value"] == 1


# ---------------------------------------------------------------------------
# CR 8.5.45 — clash
# ---------------------------------------------------------------------------

from engine.effect_keywords import clash, ClashEvent


def test_clash_highest_power_wins():
    """Clash: player with higher power top card wins."""
    state = _make_state()
    c1 = _make_card("strong")
    c1.owner = 1
    c1.power = 5
    state.players[1].deck.add(c1)

    c2 = _make_card("weak")
    c2.owner = 2
    c2.power = 2
    state.players[2].deck.add(c2)

    event = clash(state, player1_id=1, player2_id=2)

    assert not event.canceled
    assert event.winner_id == 1


def test_clash_tie_no_winner():
    """CR 8.5.45c: tied power — no winner."""
    state = _make_state()
    c1 = _make_card("even_a")
    c1.owner = 1
    c1.power = 3
    state.players[1].deck.add(c1)

    c2 = _make_card("even_b")
    c2.owner = 2
    c2.power = 3
    state.players[2].deck.add(c2)

    event = clash(state, player1_id=1, player2_id=2)
    assert event.winner_id is None


def test_clash_empty_deck_loses():
    """CR 8.5.45b: no top card = lose the clash."""
    state = _make_state()
    c2 = _make_card("has_card")
    c2.owner = 2
    c2.power = 1
    state.players[2].deck.add(c2)

    event = clash(state, player1_id=1, player2_id=2)
    assert event.winner_id == 2


# ---------------------------------------------------------------------------
# CR 8.5.47 — amp
# ---------------------------------------------------------------------------

from engine.effect_keywords import amp, AmpEvent


def test_amp_adds_to_class_counters():
    """Amp increments class_counters['amp']."""
    state = _make_state()

    event = amp(state, amount=2, player_id=1)

    assert not event.canceled
    assert state.players[1].class_counters.get("amp", 0) == 2


def test_amp_stacks():
    """Multiple amp calls stack."""
    state = _make_state()
    amp(state, amount=1, player_id=1)
    amp(state, amount=3, player_id=1)
    assert state.players[1].class_counters["amp"] == 4


def test_amp_emits_event():
    """amp() emits an 'amp' event."""
    state = _make_state()
    received = []
    state.event_manager.register("amp", lambda ev, s: received.append(ev))
    amp(state, amount=2, player_id=1)
    assert len(received) == 1


# ---------------------------------------------------------------------------
# CR 8.5.49 — exchange
# ---------------------------------------------------------------------------

from engine.effect_keywords import exchange, ExchangeEvent


def test_exchange_swaps_zones():
    """Exchange swaps two cards' zones."""
    state = _make_state()
    card_a = _make_card("card_a")
    card_a.owner = 1
    card_a.controller = 1
    state.players[1].hand.add(card_a)

    card_b = _make_card("card_b")
    card_b.owner = 1
    card_b.controller = 1
    state.players[1].graveyard.add(card_b)

    event = exchange(state, card_a=card_a, card_b=card_b)

    assert not event.canceled
    assert card_a in state.players[1].graveyard.cards
    assert card_b in state.players[1].hand.cards


def test_exchange_swaps_control():
    """CR 8.5.49: exchange swaps zone, visibility, AND control."""
    state = _make_state()
    card_a = _make_card("card_a")
    card_a.owner = 1
    card_a.controller = 1
    state.players[1].hand.add(card_a)

    card_b = _make_card("card_b")
    card_b.owner = 2
    card_b.controller = 2
    state.players[2].hand.add(card_b)

    exchange(state, card_a=card_a, card_b=card_b)

    # Control should be swapped
    assert card_a.controller == 2
    assert card_b.controller == 1


def test_exchange_emits_event():
    """exchange() emits an 'exchange' event."""
    state = _make_state()
    card_a = _make_card("card_a")
    card_a.owner = 1
    state.players[1].hand.add(card_a)
    card_b = _make_card("card_b")
    card_b.owner = 1
    state.players[1].graveyard.add(card_b)

    received = []
    state.event_manager.register("exchange", lambda ev, s: received.append(ev))
    exchange(state, card_a=card_a, card_b=card_b)
    assert len(received) == 1


# ---------------------------------------------------------------------------
# CR 8.5.50 — mark
# ---------------------------------------------------------------------------

from engine.effect_keywords import mark, MarkEvent


def test_mark_sets_class_counter():
    """Mark sets class_counters['marked'] on target player."""
    state = _make_state()

    event = mark(state, target_player_id=2, source_player_id=1)

    assert not event.canceled
    assert state.players[2].class_counters.get("marked") == 1


def test_mark_emits_event():
    """mark() emits a 'mark' event."""
    state = _make_state()
    received = []
    state.event_manager.register("mark", lambda ev, s: received.append(ev))
    mark(state, target_player_id=2, source_player_id=1)
    assert len(received) == 1
    assert received[0].data["target_player_id"] == 2


# ---------------------------------------------------------------------------
# CR 8.5.55 — tap
# ---------------------------------------------------------------------------

from engine.effect_keywords import tap, TapEvent


def test_tap_card():
    """Tap changes untapped card to tapped."""
    state = _make_state()
    card = _make_card("my_equip")
    card.tapped = False

    event = tap(state, card=card)

    assert not event.canceled
    assert card.tapped is True


def test_tap_already_tapped_cancels():
    """CR 8.5.55a: fails if already tapped."""
    state = _make_state()
    card = _make_card("already_tapped")
    card.tapped = True

    event = tap(state, card=card)
    assert event.canceled


def test_tap_emits_event():
    """tap() emits a 'tap' event."""
    state = _make_state()
    card = _make_card("equip")
    received = []
    state.event_manager.register("tap", lambda ev, s: received.append(ev))
    tap(state, card=card)
    assert len(received) == 1


# ---------------------------------------------------------------------------
# CR 8.5.56 — untap
# ---------------------------------------------------------------------------

from engine.effect_keywords import untap, UntapEvent


def test_untap_card():
    """Untap changes tapped card to untapped."""
    state = _make_state()
    card = _make_card("my_equip")
    card.tapped = True

    event = untap(state, card=card)

    assert not event.canceled
    assert card.tapped is False


def test_untap_already_untapped_cancels():
    """CR 8.5.56a: fails if already untapped."""
    state = _make_state()
    card = _make_card("already_untapped")
    card.tapped = False

    event = untap(state, card=card)
    assert event.canceled


def test_untap_emits_event():
    """untap() emits an 'untap' event."""
    state = _make_state()
    card = _make_card("equip")
    card.tapped = True
    received = []
    state.event_manager.register("untap", lambda ev, s: received.append(ev))
    untap(state, card=card)
    assert len(received) == 1


# ---------------------------------------------------------------------------
# CR 8.5.57 — cheer / boo
# ---------------------------------------------------------------------------

from engine.effect_keywords import cheer, CheerEvent, boo, BooEvent


def test_cheer_sets_counter():
    """Cheer sets cheered_this_turn on target player."""
    state = _make_state()
    event = cheer(state, target_player_id=1)
    assert not event.canceled
    assert state.players[1].class_counters.get("cheered_this_turn") == 1


def test_cheer_emits_event():
    """cheer() emits a 'cheer' event."""
    state = _make_state()
    received = []
    state.event_manager.register("cheer", lambda ev, s: received.append(ev))
    cheer(state, target_player_id=1)
    assert len(received) == 1


def test_boo_sets_counter():
    """Boo sets booed_this_turn on target player."""
    state = _make_state()
    event = boo(state, target_player_id=2)
    assert not event.canceled
    assert state.players[2].class_counters.get("booed_this_turn") == 1


def test_boo_emits_event():
    """boo() emits a 'boo' event."""
    state = _make_state()
    received = []
    state.event_manager.register("boo", lambda ev, s: received.append(ev))
    boo(state, target_player_id=2)
    assert len(received) == 1


def test_boo_replacement_can_cancel():
    """A replacement effect can cancel a boo."""
    from engine.effects import ReplacementEffect, ReplacementType
    state = _make_state()
    source = _make_card("shield")
    state.effect_manager.replacement_effects.append(
        ReplacementEffect(
            source_card=source,
            replacement_type=ReplacementType.STANDARD,
            condition_fn=lambda e, s: e.get("type") == "boo",
            replace_fn=lambda e, s: {**e, "canceled": True},
        )
    )
    event = boo(state, target_player_id=2)
    assert event.canceled
    assert state.players[2].class_counters.get("booed_this_turn", 0) == 0


# ---------------------------------------------------------------------------
# CR 8.5.25 — become_copy
# ---------------------------------------------------------------------------

from engine.effect_keywords import become_copy, BecomeCopyEvent


def test_become_copy_transfers_base_properties():
    """Subject card's base stats are overwritten with reference's base stats."""
    state = _make_state()
    subject = _make_card("subject_card")
    subject.base_power = 1

    reference = _make_card("reference_card")
    reference.base_power = 5
    reference.base_defense = 3
    reference.base_types = ["Attack Action"]

    event = become_copy(state, subject, reference, source_player_id=1)

    assert not event.canceled
    assert subject.base_power == 5
    assert subject.base_defense == 3
    assert subject.base_types == ["Attack Action"]


def test_become_copy_does_not_change_raw_fields():
    """raw_* fields (original print) are never touched by become_copy."""
    state = _make_state()
    subject = _make_card("subject_card")
    subject.raw_power = 2
    subject.raw_name = "Subject Card"

    reference = _make_card("reference_card")
    reference.raw_power = 9
    reference.base_power = 9

    become_copy(state, subject, reference)

    # raw stays unchanged
    assert subject.raw_power == 2
    assert subject.raw_name == "Subject Card"
    # base is updated
    assert subject.base_power == 9


def test_become_copy_preserves_zone_and_owner():
    """Non-copyable properties (zone, owner, controller, counters) are preserved."""
    state = _make_state()
    subject = _make_card("subject_card")
    subject.owner = 1
    subject.zone = "hand"
    subject.counters["hit"] = 2
    state.players[1].hand.add(subject)

    reference = _make_card("reference_card")
    reference.base_power = 7

    become_copy(state, subject, reference)

    assert subject.zone == "hand"
    assert subject.owner == 1
    assert subject.counters["hit"] == 2


def test_become_copy_snapshot_not_live():
    """CR 8.5.25c: future changes to reference do not affect subject."""
    state = _make_state()
    subject = _make_card("subject_card")
    reference = _make_card("reference_card")
    reference.base_power = 4

    become_copy(state, subject, reference)
    assert subject.base_power == 4

    reference.base_power = 99

    assert subject.base_power == 4  # subject unchanged


def test_become_copy_same_card_fails():
    """CR 8.5.25d: becoming a copy of itself fails."""
    state = _make_state()
    card = _make_card("same_card")

    event = become_copy(state, card, card)

    assert event.canceled


def test_become_copy_emits_event():
    """become_copy emits a 'become_copy' event."""
    state = _make_state()
    subject = _make_card("subject_card")
    reference = _make_card("reference_card")
    received = []
    state.event_manager.register("become_copy", lambda ev, s: received.append(ev))

    become_copy(state, subject, reference, source_player_id=1)

    assert len(received) == 1
    assert received[0].data["subject_card"].slug == "subject_card"
    assert received[0].data["reference_card"].slug == "reference_card"


# ---------------------------------------------------------------------------
# CR 8.5.35 — gain_control
# ---------------------------------------------------------------------------

from engine.effect_keywords import gain_control, GainControlEvent


def _make_item_card(slug):
    """Make a card with Item subtype so it can enter the permanents zone."""
    card = _make_card(slug)
    card.raw_types = ["Action"]
    card.types = ["Action"]
    card.raw_subtypes = ["Item"]
    card.subtypes = ["Item"]
    return card


def test_gain_control_moves_card_to_new_controller_zone():
    """Gaining control moves card to the same zone type on new controller's side."""
    state = _make_state()
    card = _make_item_card("item_card")
    card.owner = 1
    card.controller = 1
    state.players[1].permanents.add(card)

    event = gain_control(state, card, new_controller_id=2, source_player_id=2)

    assert not event.canceled
    assert card.controller == 2
    assert card in state.players[2].permanents.cards
    assert card not in state.players[1].permanents.cards


def test_gain_control_updates_controller_not_owner():
    """card.owner is unchanged; only card.controller changes."""
    state = _make_state()
    card = _make_item_card("item_card")
    card.owner = 1
    card.controller = 1
    state.players[1].permanents.add(card)

    gain_control(state, card, new_controller_id=2)

    assert card.owner == 1   # owner unchanged
    assert card.controller == 2


def test_gain_control_same_controller_cancels():
    """Gaining control when already controlling is a no-op."""
    state = _make_state()
    card = _make_item_card("item_card")
    card.owner = 1
    card.controller = 2
    state.players[2].permanents.add(card)

    event = gain_control(state, card, new_controller_id=2)

    assert event.canceled
    assert card in state.players[2].permanents.cards


def test_gain_control_emits_event():
    """gain_control emits a 'gain_control' event."""
    state = _make_state()
    card = _make_item_card("item_card")
    card.owner = 1
    card.controller = 1
    state.players[1].permanents.add(card)
    received = []
    state.event_manager.register("gain_control", lambda ev, s: received.append(ev))

    gain_control(state, card, new_controller_id=2)

    assert len(received) == 1
    assert received[0].data["new_controller_id"] == 2
    assert received[0].data["previous_controller_id"] == 1


def test_gain_control_equipment_zone_fails_wrong_owner():
    """CR 8.5.35a: gaining control of equipment in an owner-restricted zone fails."""
    state = _make_state()
    card = _make_card("equipment_card")
    card.owner = 1
    card.controller = 1
    # put in player 1's hand (owner-restricted zone)
    state.players[1].hand.add(card)

    event = gain_control(state, card, new_controller_id=2)

    # hand is owner-restricted, so zone entry for player 2 should fail
    assert event.canceled
    # card returned to player 1's hand
    assert card in state.players[1].hand.cards
    assert card.controller == 1


# ---------------------------------------------------------------------------
# CR 8.5.36 — transform
# ---------------------------------------------------------------------------

from engine.effect_keywords import transform, TransformEvent


def test_transform_puts_objects_under_permanent():
    """CR 8.5.36 — source card is placed under the permanent."""
    state = _make_state()
    obj = _make_card("obj_card")
    obj.owner = 1
    state.players[1].hand.add(obj)

    perm = _make_item_card("perm_card")
    perm.owner = 1
    state.players[1].permanents.add(perm)

    event = transform(state, [obj], perm, source_player_id=1)

    assert not event.canceled
    assert obj in perm.cards_underneath
    assert obj.is_sub_card


def test_transform_canceled_when_no_objects():
    """CR 8.5.36d — empty objects list fails."""
    state = _make_state()
    perm = _make_item_card("perm_card")
    perm.owner = 1
    state.players[1].permanents.add(perm)

    event = transform(state, [], perm, source_player_id=1)
    assert event.canceled


def test_transform_emits_event():
    """transform emits a 'transform' event."""
    state = _make_state()
    obj = _make_card("obj_card")
    obj.owner = 1
    state.players[1].hand.add(obj)
    perm = _make_item_card("perm_card")
    perm.owner = 1
    state.players[1].permanents.add(perm)

    received = []
    state.event_manager.register("transform", lambda ev, s: received.append(ev))
    transform(state, [obj], perm, source_player_id=1)

    assert len(received) == 1
    assert any(o.slug == "obj_card" for o in received[0].data["objects"])


# ---------------------------------------------------------------------------
# CR 8.5.38 — attack
# ---------------------------------------------------------------------------

from engine.effect_keywords import attack, AttackEvent


def test_attack_emits_event():
    """CR 8.5.38 — attack emits 'attack' event."""
    state = _make_state()
    card = _make_card("swing_card")
    card.owner = 1

    received = []
    state.event_manager.register("attack", lambda ev, s: received.append(ev))
    event = attack(state, card, target_id=2, source_player_id=1)

    assert not event.canceled
    assert len(received) == 1
    assert received[0].data["target_id"] == 2


def test_attack_replacement_can_cancel():
    """Replacement effect can cancel the attack event."""
    from engine.effects import ReplacementEffect, ReplacementType
    from tests.conftest import _make_card as _mc
    state = _make_state()
    card = _make_card("swing_card")
    card.owner = 1

    source = _mc("effect_source")
    state.effect_manager.replacement_effects.append(ReplacementEffect(
        source_card=source,
        replacement_type=ReplacementType.STANDARD,
        condition_fn=lambda e, s: e.get("type") == "attack",
        replace_fn=lambda e, s: {**e, "canceled": True},
    ))

    event = attack(state, card, target_id=2)
    assert event.canceled


# ---------------------------------------------------------------------------
# CR 8.5.39 — contract
# ---------------------------------------------------------------------------

from engine.effect_keywords import contract, ContractEvent


def test_contract_records_on_player():
    """CR 8.5.39 — contract sets a flag on the player."""
    state = _make_state()

    event = contract(state, player_id=1, condition="attack three times",
                     reward="+3 life", source_card_slug="quest_card")

    assert not event.canceled
    assert state.players[1].class_counters.get("contract_quest_card") == 1


def test_contract_fails_for_missing_player():
    """contract fails if player_id doesn't exist."""
    state = _make_state()
    event = contract(state, player_id=99, condition="do something", reward="prize")
    assert event.canceled


# ---------------------------------------------------------------------------
# CR 8.5.40 — create (card)
# ---------------------------------------------------------------------------

from engine.effect_keywords import create_card, CreateCardEvent


def test_create_card_adds_to_zone():
    """CR 8.5.40 — created card appears in the specified zone."""
    state = _make_state()

    event = create_card(state, slug="new_card", dest_player_id=1, dest_zone="hand")

    assert not event.canceled
    assert event.created_card is not None
    slugs = [c.slug for c in state.players[1].hand.cards]
    assert "new_card" in slugs


def test_create_card_emits_event():
    """create_card emits 'create_card' event."""
    state = _make_state()
    received = []
    state.event_manager.register("create_card", lambda ev, s: received.append(ev))

    create_card(state, slug="test_card", dest_player_id=2, dest_zone="hand")

    assert len(received) == 1
    assert received[0].data["dest_player_id"] == 2


# ---------------------------------------------------------------------------
# CR 8.5.43 — awaken
# ---------------------------------------------------------------------------

from engine.effect_keywords import awaken, AwakenEvent


def test_awaken_flips_double_faced_card():
    """CR 8.5.43 — awaken sets back_face_active on a double-faced card."""
    state = _make_state()
    card = _make_card("double_faced_card")
    card.owner = 1
    # Simulate double-faced card by injecting the back_face_slug attribute
    object.__setattr__(card, 'back_face_slug', 'double_faced_card_back') if hasattr(type(card), '__slots__') else setattr(card, 'back_face_slug', 'double_faced_card_back')
    state.players[1].hand.add(card)

    event = awaken(state, card, source_player_id=1)

    assert not event.canceled
    assert card.counters.get("__back_face_active__")


def test_awaken_fails_if_no_back_face():
    """CR 8.5.43a — awaken fails if card is not double-faced."""
    state = _make_state()
    card = _make_card("single_card")
    card.owner = 1
    state.players[1].hand.add(card)

    event = awaken(state, card)
    assert event.canceled


def test_awaken_fails_if_already_awakened():
    """CR 8.5.43a — awaken fails if back face is already active."""
    state = _make_state()
    card = _make_card("double_faced_card")
    card.owner = 1
    setattr(card, 'back_face_slug', 'double_faced_card_back')
    card.counters["__back_face_active__"] = 1
    state.players[1].hand.add(card)

    event = awaken(state, card)
    assert event.canceled


# ---------------------------------------------------------------------------
# CR 8.5.46 — wager
# ---------------------------------------------------------------------------

from engine.effect_keywords import wager, WagerEvent


def test_wager_stores_prize_on_card():
    """CR 8.5.46 — wager records prize data on the attack card."""
    state = _make_state()
    atk = _make_card("attack_card")
    atk.owner = 1

    event = wager(state, atk, prize="Might", controller_id=1, opponent_id=2)

    assert not event.canceled
    assert atk.wager_data['prize'] == "Might"
    assert atk.wager_data['controller_id'] == 1
    assert atk.wager_data['opponent_id'] == 2


def test_wager_emits_event():
    """wager emits 'wager' event."""
    state = _make_state()
    atk = _make_card("attack_card")
    received = []
    state.event_manager.register("wager", lambda ev, s: received.append(ev))

    wager(state, atk, prize="Agility")

    assert len(received) == 1


# ---------------------------------------------------------------------------
# CR 8.5.48 — transcend
# ---------------------------------------------------------------------------

from engine.effect_keywords import transcend, TranscendEvent


def test_transcend_moves_card_to_hand_with_back_face():
    """CR 8.5.48 — transcend puts card in owner's hand with back-face active."""
    state = _make_state()
    card = _make_card("transcend_card")
    card.owner = 1
    card.controller = 1
    state.players[1].permanents.add(card)

    event = transcend(state, card, player_id=1)

    assert not event.canceled
    assert card in state.players[1].hand.cards
    assert card not in state.players[1].permanents.cards
    assert card.counters.get("__back_face_active__")


def test_transcend_emits_event():
    """transcend emits 'transcend' event."""
    state = _make_state()
    card = _make_card("transcend_card")
    card.owner = 1
    state.players[1].permanents.add(card)
    received = []
    state.event_manager.register("transcend", lambda ev, s: received.append(ev))

    transcend(state, card)

    assert len(received) == 1


# ---------------------------------------------------------------------------
# CR 8.5.51 — retrieve
# ---------------------------------------------------------------------------

from engine.effect_keywords import retrieve, RetrieveEvent


def _make_weapon_card(slug):
    """Make a card that passes weapon zone entry (needs 'Weapon' in raw_types)."""
    card = _make_card(slug)
    card.raw_types = ["Weapon"]
    card.raw_subtypes = ["1H"]
    return card


def test_retrieve_equips_weapon_from_graveyard():
    """CR 8.5.51 — pays 1r and equips card from graveyard to weapon zone."""
    state = _make_state()
    card = _make_weapon_card("sword")
    card.owner = 1
    state.players[1].graveyard.add(card)
    state.players[1].resources = 2

    event = retrieve(state, card, player_id=1)

    assert not event.canceled
    assert event.cost_paid
    assert state.players[1].resources == 1
    assert card in state.players[1].weapon1.cards


def test_retrieve_fails_no_resources():
    """CR 8.5.51a — fails when player has no resources."""
    state = _make_state()
    card = _make_weapon_card("sword")
    card.owner = 1
    state.players[1].graveyard.add(card)
    state.players[1].resources = 0

    event = retrieve(state, card, player_id=1)

    assert event.canceled


def test_retrieve_fails_non_equipment():
    """CR 8.5.51a — fails for a card with no equipment subtype."""
    state = _make_state()
    card = _make_card("action_card")
    card.raw_subtypes = []
    card.owner = 1
    state.players[1].graveyard.add(card)
    state.players[1].resources = 3

    event = retrieve(state, card, player_id=1)

    assert event.canceled


# ---------------------------------------------------------------------------
# CR 8.5.52 — return to the brood
# ---------------------------------------------------------------------------

from engine.effect_keywords import return_to_the_brood, ReturnToTheBroodEvent


def test_return_to_the_brood_removes_become_copy_effects():
    """CR 8.5.52 — removes become/copy continuous effects on player's hero."""
    state = _make_state()

    # Inject a plain object acting as a become_copy effect on player 1
    class FakeBecomeEffect:
        effect_type = "become_copy"
        target_player_id = 1

    state.effect_manager.continuous_effects.append(FakeBecomeEffect())
    assert len(state.effect_manager.continuous_effects) >= 1

    event = return_to_the_brood(state, player_id=1)

    assert not event.canceled
    remaining = [e for e in state.effect_manager.continuous_effects
                 if getattr(e, 'effect_type', None) == 'become_copy'
                 and getattr(e, 'target_player_id', None) == 1]
    assert len(remaining) == 0


def test_return_to_the_brood_emits_event():
    """return_to_the_brood emits 'return_to_the_brood' event."""
    state = _make_state()
    received = []
    state.event_manager.register("return_to_the_brood", lambda ev, s: received.append(ev))

    return_to_the_brood(state, player_id=1)

    assert len(received) == 1


# ---------------------------------------------------------------------------
# CR 8.5.53 — give
# ---------------------------------------------------------------------------

from engine.effect_keywords import give, GiveEvent


def test_give_transfers_control():
    """CR 8.5.53 — give moves card to new controller's permanents zone."""
    state = _make_state()
    card = _make_item_card("item_card")
    card.owner = 1
    card.controller = 1
    state.players[1].permanents.add(card)

    event = give(state, card, new_controller_id=2, source_player_id=1)

    assert not event.canceled
    assert card.controller == 2
    assert card in state.players[2].permanents.cards


def test_give_emits_give_event():
    """give emits its own 'give' event (in addition to gain_control)."""
    state = _make_state()
    card = _make_item_card("item_card")
    card.owner = 1
    card.controller = 1
    state.players[1].permanents.add(card)
    received = []
    state.event_manager.register("give", lambda ev, s: received.append(ev))

    give(state, card, new_controller_id=2)

    assert len(received) == 1


# ---------------------------------------------------------------------------
# CR 8.5.54 — steal
# ---------------------------------------------------------------------------

from engine.effect_keywords import steal, StealEvent


def test_steal_transfers_control():
    """CR 8.5.54 — steal moves card from opponent to stealer's permanents zone."""
    state = _make_state()
    card = _make_item_card("item_card")
    card.owner = 2
    card.controller = 2
    state.players[2].permanents.add(card)

    event = steal(state, card, new_controller_id=1, source_player_id=1)

    assert not event.canceled
    assert card.controller == 1
    assert card in state.players[1].permanents.cards
    assert card.owner == 2   # ownership unchanged


def test_steal_emits_steal_event():
    """steal emits its own 'steal' event."""
    state = _make_state()
    card = _make_item_card("item_card")
    card.owner = 2
    card.controller = 2
    state.players[2].permanents.add(card)
    received = []
    state.event_manager.register("steal", lambda ev, s: received.append(ev))

    steal(state, card, new_controller_id=1)

    assert len(received) == 1
    assert received[0].data["previous_controller_id"] == 2


# ---------------------------------------------------------------------------
# CR 8.5.32 — add (defend)
# ---------------------------------------------------------------------------

from engine.effect_keywords import add_defend, AddDefendEvent
from engine.state import CombatState


def _make_combat(attacker_id: int = 1) -> CombatState:
    attack_card = _make_card("attack_card")
    defender_hero = _make_card("defender_hero")
    return CombatState(
        attacker_id=attacker_id,
        link_id=1,
        attack_power=4,
        attack_card=attack_card,
        keywords=[],
        attack_target=defender_hero,
        base_attack_power=4,
    )


def test_add_defend_adds_card_to_combat_defending_cards():
    """CR 8.5.32 — card is added to combat.defending_cards."""
    state = _make_state()
    state.combat = _make_combat(attacker_id=1)
    card = _make_card("block_card")
    card.raw_defense = 3
    card.defense = 3
    card.owner = 2
    state.players[2].hand.add(card)

    event = add_defend(state, card, source_player_id=2)

    assert not event.canceled
    assert card in state.combat.defending_cards
    assert state.combat.total_defense == 3


def test_add_defend_from_hand_sets_defender_used_hand_card():
    """add_defend from hand sets defender_used_hand_card for Dominate/Reprise."""
    state = _make_state()
    state.combat = _make_combat(attacker_id=1)
    card = _make_card("block_card")
    card.owner = 2
    state.players[2].hand.add(card)

    add_defend(state, card, source_player_id=2)

    assert state.combat.defender_used_hand_card


def test_add_defend_fails_when_no_combat():
    """CR 8.5.32a — fails if combat is not active."""
    state = _make_state()
    state.combat = None
    card = _make_card("block_card")
    card.owner = 2

    event = add_defend(state, card)

    assert event.canceled
    assert card not in (state.combat.defending_cards if state.combat else [])


def test_add_defend_replacement_can_cancel():
    """CR 8.5.32a — replacement effect can prevent the defend."""
    from engine.effects import ReplacementEffect, ReplacementType
    from tests.conftest import _make_card as _mc
    state = _make_state()
    state.combat = _make_combat(attacker_id=1)
    card = _make_card("block_card")
    card.owner = 2
    state.players[2].hand.add(card)

    source = _mc("effect_source")
    state.effect_manager.replacement_effects.append(ReplacementEffect(
        source_card=source,
        replacement_type=ReplacementType.STANDARD,
        condition_fn=lambda e, s: e.get("type") == "add_defend",
        replace_fn=lambda e, s: {**e, "canceled": True},
    ))

    event = add_defend(state, card)

    assert event.canceled
    assert card not in state.combat.defending_cards


def test_add_defend_emits_event():
    """add_defend emits 'add_defend' event."""
    state = _make_state()
    state.combat = _make_combat(attacker_id=1)
    card = _make_card("block_card")
    card.owner = 2
    state.players[2].hand.add(card)

    received = []
    state.event_manager.register("add_defend", lambda ev, s: received.append(ev))
    add_defend(state, card)

    assert len(received) == 1
    assert received[0].card == "block_card"


# ---------------------------------------------------------------------------
# Additional audit fix tests
# ---------------------------------------------------------------------------

def test_freeze_default_duration_unregisters_on_turn_start():
    """CR 8.5.34b: freeze with no duration unfreezes at start of controller's next turn."""
    state = _make_state()
    card = _make_card("ice_target")
    card.owner = 1
    card.controller = 1
    state.active_player = 1

    freeze(state, target_card=card)  # no until_condition
    assert card.counters.get("__frozen__", 0) == 1

    # Simulate start_of_turn for the controller
    state.event_manager.emit(Event(type="start_of_turn", data={}), state)

    assert card.counters.get("__frozen__", 0) == 0


def test_freeze_explicit_duration_does_not_auto_unfreeze():
    """freeze() with explicit until_condition does NOT register auto-unfreeze."""
    state = _make_state()
    card = _make_card("ice_target")
    card.owner = 1
    card.controller = 1
    state.active_player = 1

    freeze(state, target_card=card, until_condition="end_of_turn")
    assert card.counters.get("__frozen__", 0) == 1

    # start_of_turn should NOT unfreeze since explicit condition was given
    state.event_manager.emit(Event(type="start_of_turn", data={}), state)
    assert card.counters.get("__frozen__", 0) == 1


def test_ignore_registers_replacement_effect():
    """CR 8.5.33: ignore registers a one-shot replacement that cancels matching events."""
    from engine.effect_keywords import ignore
    state = _make_state()

    initial_count = len(state.effect_manager.replacement_effects)
    ignore(state, description="ignore next damage", ignored_event_type="deal_damage")

    assert len(state.effect_manager.replacement_effects) == initial_count + 1


def test_ignore_without_event_type_is_record_only():
    """ignore() with no ignored_event_type just emits event, no replacement registered."""
    from engine.effect_keywords import ignore
    state = _make_state()

    initial_count = len(state.effect_manager.replacement_effects)
    ignore(state, description="record only")

    assert len(state.effect_manager.replacement_effects) == initial_count


def test_clash_uses_reveal_emits_reveal_event():
    """clash() routes through reveal() which emits a 'reveal' event."""
    state = _make_state()
    c1 = _make_card("strong")
    c1.owner = 1
    c1.power = 5
    state.players[1].deck.add(c1)

    c2 = _make_card("weak")
    c2.owner = 2
    c2.power = 2
    state.players[2].deck.add(c2)

    reveal_events = []
    state.event_manager.register("reveal", lambda ev, s: reveal_events.append(ev))

    clash(state, player1_id=1, player2_id=2)

    assert len(reveal_events) == 1


def test_put_object_uses_controller_for_source():
    """put_object removes card from controller's zone, not owner's."""
    from engine.effect_keywords import put_object
    state = _make_state()
    card = _make_card("controlled_card")
    card.owner = 1
    card.controller = 2  # controlled by player 2
    state.players[2].hand.add(card)

    # Move to owner's graveyard (owner=1, so graveyard zone entry accepts it)
    event = put_object(state, card, destination_zone="graveyard", destination_player_id=1)

    assert not event.canceled
    # Card was in player 2's hand (controller), should be removed from there
    assert card not in state.players[2].hand.cards
    assert card in state.players[1].graveyard.cards


def test_gain_chi_goes_to_chi_pool():
    """gain() CHI adds to player.chi, not resources."""
    state = _make_state()
    state.players[1].chi = 0

    gain(state, asset_type=AssetType.CHI, amount=3, source_player_id=1, target_player_id=1)

    assert state.players[1].chi == 3
    assert state.players[1].resources == 0


def test_lose_chi_subtracts_from_chi_pool():
    """lose() CHI subtracts from player.chi, not resources."""
    state = _make_state()
    state.players[1].chi = 5

    lose(state, asset_type=AssetType.CHI, amount=2, target_player_id=1)

    assert state.players[1].chi == 3


# ---------------------------------------------------------------------------
# Rules accuracy regression guards (for fixes applied in this audit)
# ---------------------------------------------------------------------------

def test_amp_applied_to_arcane_damage():
    """CR 8.5.47: amp bonus is consumed and added to the next arcane damage event."""
    from engine.effect_keywords import amp
    state = _make_state()
    target_hero = state.players[2].hero
    amp(state, amount=3, player_id=1)
    initial_life = state.players[2].life

    deal_damage(state, amount=2, damage_type=DamageType.ARCANE,
                source_player_id=1, damage_target=target_hero,
                damage_source="test_spell")

    assert state.players[2].life == initial_life - 5  # 2 base + 3 amp


def test_amp_consumed_after_arcane_damage():
    """CR 8.5.47: amp counter is cleared after the first arcane damage (next-time rule)."""
    from engine.effect_keywords import amp
    state = _make_state()
    target_hero = state.players[2].hero
    amp(state, amount=3, player_id=1)

    deal_damage(state, amount=1, damage_type=DamageType.ARCANE,
                source_player_id=1, damage_target=target_hero,
                damage_source="test_spell")

    assert state.players[1].class_counters.get('amp', 0) == 0


def test_amp_not_applied_to_physical_damage():
    """CR 8.5.47: amp only affects arcane damage, not physical."""
    from engine.effect_keywords import amp
    state = _make_state()
    target_hero = state.players[2].hero
    amp(state, amount=3, player_id=1)
    initial_life = state.players[2].life

    deal_damage(state, amount=2, damage_type=DamageType.PHYSICAL,
                source_player_id=1, damage_target=target_hero,
                damage_source="test_attack")

    assert state.players[2].life == initial_life - 2   # no amp bonus
    assert state.players[1].class_counters.get('amp', 0) == 3  # counter unchanged


def test_clash_reads_top_card_index_zero():
    """CR 8.5.45: clash reveals top card (deck.cards[0]), not the bottom (deck.cards[-1])."""
    from engine.effect_keywords import clash
    state = _make_state()

    top = _make_card("top_card"); top.owner = 1; top.power = 10
    bottom = _make_card("bot_card"); bottom.owner = 1; bottom.power = 1
    state.players[1].deck.cards.clear()
    state.players[1].deck.cards.insert(0, top)      # index 0 = top
    state.players[1].deck.cards.append(bottom)       # index 1 = below top

    filler = _make_card("filler"); filler.owner = 2; filler.power = 5
    state.players[2].deck.cards.clear()
    state.players[2].deck.cards.append(filler)

    event = clash(state, player1_id=1, player2_id=2)

    # Top card (power=10) should win, not bottom card (power=1)
    assert event.power1 == 10
    assert event.winner_id == 1


def test_retrieve_decline_does_not_equip():
    """CR 8.5.51a: chose_to_pay=False — no equip, no cost, event not canceled."""
    from engine.effect_keywords import retrieve
    state = _make_state()
    card = _make_card("test_dagger")
    card.raw_subtypes = ["1H"]
    card.owner = 1
    state.players[1].graveyard.add(card)
    state.players[1].resources = 5

    event = retrieve(state, card, player_id=1, chose_to_pay=False)

    assert not event.canceled
    assert not event.cost_paid
    assert card in state.players[1].graveyard.cards   # still in graveyard
    assert state.players[1].resources == 5            # no cost deducted
