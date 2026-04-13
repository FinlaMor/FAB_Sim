"""Tests for zone entry rules (CR 3.0.11/3.0.12/3.0.12a) and effect_context().

Each test targets a specific CR rule. Zone entry results:
  ALLOW           — card entered normally
  FAIL            — effect-source move rejected
  CLEAR           — rule-source violation → redirected to graveyard
  CEASE_TO_EXIST  — token cannot enter zone → removed from game
"""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from tests.conftest import _make_state, _make_card, _make_player
from engine.card import Card
from engine.state import Zone, ZoneEntryResult
from engine.context import effect_context, is_effect_context


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _deck_card(slug="card", subtypes=None):
    c = _make_card(slug, types=["Action"])
    if subtypes:
        c.raw_subtypes = subtypes
    return c


def _token_card(slug="token"):
    c = Card(slug=slug, raw_name=slug)
    c.raw_types = ["Token"]
    return c


def _hero_card_obj(slug="hero"):
    c = Card(slug=slug, raw_name=slug)
    c.raw_types = ["Hero"]
    c.raw_life = 20
    c.raw_intellect = 4
    return c


def _equip_card(slug="equip", subtypes=None):
    c = Card(slug=slug, raw_name=slug)
    c.raw_types = ["Equipment"]
    c.raw_subtypes = subtypes or []
    return c


# ---------------------------------------------------------------------------
# Context manager tests
# ---------------------------------------------------------------------------

class TestEffectContext:
    def test_outside_context_is_rule(self):
        assert not is_effect_context()

    def test_inside_context_is_effect(self):
        with effect_context():
            assert is_effect_context()

    def test_exits_cleanly(self):
        with effect_context():
            pass
        assert not is_effect_context()

    def test_reentrant(self):
        with effect_context():
            with effect_context():
                assert is_effect_context()
            assert is_effect_context()
        assert not is_effect_context()

    def test_exception_still_exits(self):
        try:
            with effect_context():
                raise ValueError("test")
        except ValueError:
            pass
        assert not is_effect_context()


# ---------------------------------------------------------------------------
# CR 3.9.2 — hand zone: owner's deck-cards only
# ---------------------------------------------------------------------------

class TestHandZone:
    def test_deck_card_enters_hand(self):
        state = _make_state()
        card = _deck_card()
        card.owner = 1
        result = state.players[1].hand.add(card)
        assert result == ZoneEntryResult.ALLOW
        assert card in state.players[1].hand.cards

    def test_token_in_hand_rule_clears_to_graveyard(self):
        """CR 3.0.12: rule-source — token redirected to graveyard."""
        state = _make_state()
        token = _token_card()
        token.owner = 1
        result = state.players[1].hand.add(token)
        assert result == ZoneEntryResult.CEASE_TO_EXIST
        assert token not in state.players[1].hand.cards

    def test_non_deck_card_in_hand_rule_clears(self):
        """CR 3.0.12: hero can't enter hand — rule path redirects to graveyard."""
        state = _make_state()
        hero = _hero_card_obj()
        hero.owner = 1
        result = state.players[1].hand.add(hero)
        assert result == ZoneEntryResult.CLEAR
        assert hero not in state.players[1].hand.cards
        assert hero in state.players[1].graveyard.cards

    def test_non_deck_card_in_hand_effect_fails(self):
        """CR 3.0.11: effect path — move fails, card stays put."""
        state = _make_state()
        hero = _hero_card_obj()
        hero.owner = 1
        state.players[1].graveyard.cards.append(hero)
        with effect_context():
            result = state.players[1].hand.add(hero)
        assert result == ZoneEntryResult.FAIL
        assert hero not in state.players[1].hand.cards


# ---------------------------------------------------------------------------
# CR 3.7.2 — deck zone: owner's deck-cards only
# ---------------------------------------------------------------------------

class TestDeckZone:
    def test_deck_card_enters_deck(self):
        state = _make_state()
        card = _deck_card()
        card.owner = 1
        result = state.players[1].deck.add(card)
        assert result == ZoneEntryResult.ALLOW

    def test_non_deck_card_clears_to_graveyard(self):
        state = _make_state()
        hero = _hero_card_obj()
        hero.owner = 1
        result = state.players[1].deck.add(hero)
        assert result == ZoneEntryResult.CLEAR
        assert hero in state.players[1].graveyard.cards


# ---------------------------------------------------------------------------
# CR 3.3.2 / 3.3.2a — arsenal: deck-cards only, max 1
# ---------------------------------------------------------------------------

class TestArsenalZone:
    def test_deck_card_enters_empty_arsenal(self):
        state = _make_state()
        card = _deck_card()
        card.owner = 1
        result = state.players[1].arsenal.add(card)
        assert result == ZoneEntryResult.ALLOW

    def test_second_card_to_full_arsenal_rule_clears(self):
        """CR 3.3.2: rule path — cleared to graveyard."""
        state = _make_state()
        card1 = _deck_card("c1")
        card2 = _deck_card("c2")
        card1.owner = card2.owner = 1
        state.players[1].arsenal.add(card1)
        result = state.players[1].arsenal.add(card2)
        assert result == ZoneEntryResult.CLEAR
        assert card2 in state.players[1].graveyard.cards

    def test_second_card_to_full_arsenal_effect_fails(self):
        """CR 3.3.2a: effect path — move fails entirely."""
        state = _make_state()
        card1 = _deck_card("c1")
        card2 = _deck_card("c2")
        card1.owner = card2.owner = 1
        state.players[1].arsenal.add(card1)
        with effect_context():
            result = state.players[1].arsenal.add(card2)
        assert result == ZoneEntryResult.FAIL
        assert card2 not in state.players[1].arsenal.cards


# ---------------------------------------------------------------------------
# CR 3.8.2 / 3.0.12a — graveyard: owner's cards; tokens cease-to-exist
# ---------------------------------------------------------------------------

class TestGraveyardZone:
    def test_deck_card_enters_graveyard(self):
        state = _make_state()
        card = _deck_card()
        card.owner = 1
        result = state.players[1].graveyard.add(card)
        assert result == ZoneEntryResult.ALLOW

    def test_token_ceases_to_exist_in_graveyard(self):
        """CR 3.0.12a: token entering graveyard ceases to exist."""
        state = _make_state()
        token = _token_card()
        token.owner = 1
        result = state.players[1].graveyard.add(token)
        assert result == ZoneEntryResult.CEASE_TO_EXIST
        assert token not in state.players[1].graveyard.cards
        assert token.zone == "ceased_to_exist"

    def test_wrong_owner_card_rule_clears(self):
        """Rule path: p2's card can't enter p1's graveyard — cleared to p2's graveyard."""
        state = _make_state()
        card = _deck_card()
        card.owner = 2
        result = state.players[1].graveyard.add(card)
        assert result == ZoneEntryResult.CLEAR
        assert card in state.players[2].graveyard.cards

    def test_wrong_owner_card_effect_fails(self):
        state = _make_state()
        card = _deck_card()
        card.owner = 2
        with effect_context():
            result = state.players[1].graveyard.add(card)
        assert result == ZoneEntryResult.FAIL


# ---------------------------------------------------------------------------
# CR 3.4.2 / 3.0.12a — banished: owner's cards; tokens cease-to-exist
# ---------------------------------------------------------------------------

class TestBanishedZone:
    def test_deck_card_enters_banished(self):
        state = _make_state()
        card = _deck_card()
        card.owner = 1
        result = state.players[1].banished.add(card)
        assert result == ZoneEntryResult.ALLOW

    def test_token_ceases_to_exist_in_banished(self):
        """CR 3.0.12a: token entering banished ceases to exist."""
        state = _make_state()
        token = _token_card()
        token.owner = 1
        result = state.players[1].banished.add(token)
        assert result == ZoneEntryResult.CEASE_TO_EXIST
        assert token.zone == "ceased_to_exist"


# ---------------------------------------------------------------------------
# CR 3.11.2 — hero zone: only Hero-type cards
# ---------------------------------------------------------------------------

class TestHeroZone:
    def test_hero_card_enters_hero_zone(self):
        state = _make_state()
        hero = _hero_card_obj("hero2")
        hero.owner = 1
        hero.raw_life = 40
        hero.raw_intellect = 4
        result = state.players[1].hero_zone.add(hero)
        assert result == ZoneEntryResult.ALLOW

    def test_non_hero_clears_to_graveyard(self):
        state = _make_state()
        card = _deck_card()
        card.owner = 1
        result = state.players[1].hero_zone.add(card)
        assert result == ZoneEntryResult.CLEAR
        assert card in state.players[1].graveyard.cards


# ---------------------------------------------------------------------------
# CR 3.13.2 — permanent zone: deck-cards need permanent subtype
# ---------------------------------------------------------------------------

class TestPermanentZone:
    def test_aura_deck_card_enters_permanents(self):
        state = _make_state()
        card = _deck_card("aura", subtypes=["Aura"])
        card.owner = 1
        result = state.players[1].permanents.add(card)
        assert result == ZoneEntryResult.ALLOW

    def test_ally_deck_card_enters_permanents(self):
        state = _make_state()
        card = _deck_card("ally", subtypes=["Ally"])
        card.owner = 1
        result = state.players[1].permanents.add(card)
        assert result == ZoneEntryResult.ALLOW

    def test_plain_action_cannot_enter_permanents(self):
        """Action card with no permanent subtype — rule clears to graveyard."""
        state = _make_state()
        card = _deck_card("plain_action")
        card.owner = 1
        result = state.players[1].permanents.add(card)
        assert result == ZoneEntryResult.CLEAR
        assert card in state.players[1].graveyard.cards

    def test_plain_action_effect_fails(self):
        state = _make_state()
        card = _deck_card("plain_action")
        card.owner = 1
        with effect_context():
            result = state.players[1].permanents.add(card)
        assert result == ZoneEntryResult.FAIL
        assert card not in state.players[1].permanents.cards

    def test_token_enters_permanents(self):
        """Tokens are not deck-cards so the deck-card restriction doesn't apply."""
        state = _make_state()
        token = _token_card("vigor")
        token.owner = 1
        result = state.players[1].permanents.add(token)
        assert result == ZoneEntryResult.ALLOW


# ---------------------------------------------------------------------------
# CR 3.2.2a / 3.5.2a / 3.10.2a / 3.12.2a — equipment slot zones
# ---------------------------------------------------------------------------

class TestEquipmentZones:
    def test_arms_card_enters_arms(self):
        state = _make_state()
        card = _equip_card("gauntlets", subtypes=["Arms"])
        card.owner = 1
        result = state.players[1].arms.add(card)
        assert result == ZoneEntryResult.ALLOW

    def test_wrong_subtype_clears_from_arms(self):
        state = _make_state()
        card = _equip_card("helmet", subtypes=["Head"])
        card.owner = 1
        result = state.players[1].arms.add(card)
        assert result == ZoneEntryResult.CLEAR

    def test_chest_card_enters_chest(self):
        state = _make_state()
        card = _equip_card("breastplate", subtypes=["Chest"])
        card.owner = 1
        result = state.players[1].chest.add(card)
        assert result == ZoneEntryResult.ALLOW

    def test_head_card_enters_head(self):
        state = _make_state()
        card = _equip_card("helmet", subtypes=["Head"])
        card.owner = 1
        result = state.players[1].head.add(card)
        assert result == ZoneEntryResult.ALLOW

    def test_legs_card_enters_legs(self):
        state = _make_state()
        card = _equip_card("boots", subtypes=["Legs"])
        card.owner = 1
        result = state.players[1].legs.add(card)
        assert result == ZoneEntryResult.ALLOW

    def test_weapon_enters_weapon_zone(self):
        state = _make_state()
        card = _equip_card("sword", subtypes=["1H"])
        card.raw_types = ["Weapon"]
        card.owner = 1
        result = state.players[1].weapon1.add(card)
        assert result == ZoneEntryResult.ALLOW

    def test_wrong_slot_equipment_clears(self):
        state = _make_state()
        card = _equip_card("boots", subtypes=["Legs"])
        card.owner = 1
        result = state.players[1].head.add(card)
        assert result == ZoneEntryResult.CLEAR
