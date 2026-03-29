"""Tests for the card test gamestates pipeline — factory, DB, serialization, batch."""

from __future__ import annotations

import copy
import json
import os
import sqlite3
import tempfile

import pytest

from engine.card import Card, CardDB
from engine.state import GameState, Player, Step, Zone

from data.card_test_gamestates.gamestate_factory import (
    GameStateFactory,
    serialize_gamestate,
)
from data.card_test_gamestates import db as gs_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def factory():
    """Return a GameStateFactory backed by the real CardDB."""
    return GameStateFactory()


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Provide a fresh temp DB for each test, resetting the module singleton."""
    db_file = tmp_path / "test.db"
    schema_path = gs_db.SCHEMA_SQL

    monkeypatch.setattr(gs_db, "DB_PATH", db_file)
    monkeypatch.setattr(gs_db, "_connection", None)

    gs_db.init_db(force=True)
    yield gs_db.get_db()

    # Reset singleton so other tests aren't affected
    monkeypatch.setattr(gs_db, "_connection", None)


# =========================================================================
# 1. GameStateFactory — unit tests per card type
# =========================================================================

class TestFactoryCardTypes:
    """Verify the factory creates valid states for each card type category."""

    def test_factory_action_card(self, factory):
        # aether_arc_blue is a pure Action (no Attack/Aura/Item subtypes)
        state = factory.create_gamestate("aether_arc_blue")
        assert len(state.players) == 2
        assert state.step == Step.ACTION
        p1 = state.players[1]
        hand_slugs = [c.slug for c in p1.hand]
        assert "aether_arc_blue" in hand_slugs

    def test_factory_attack_card(self, factory):
        state = factory.create_gamestate("a_good_clean_fight_red")
        assert len(state.players) == 2
        assert state.step == Step.COMBAT_ATTACK
        assert state.combat is not None

    def test_factory_equipment_card(self, factory):
        # achilles_accelerator is Equipment + Legs — factory resolves slot from types.
        state = factory.create_gamestate("achilles_accelerator")
        assert len(state.players) == 2
        p1 = state.players[1]
        legs_slugs = [c.slug for c in p1.legs]
        assert "achilles_accelerator" in legs_slugs

    def test_factory_weapon_card(self, factory):
        state = factory.create_gamestate("aether_conduit")
        assert len(state.players) == 2
        p1 = state.players[1]
        weapon_slugs = [c.slug for c in p1.weapon1]
        assert "aether_conduit" in weapon_slugs

    def test_factory_permanent_card(self, factory):
        # aether_ashwing is a Token + Ally — should land in permanents
        state = factory.create_gamestate("aether_ashwing")
        assert len(state.players) == 2
        p1 = state.players[1]
        perm_slugs = [c.slug for c in p1.permanents]
        assert "aether_ashwing" in perm_slugs

    def test_factory_hero_card(self, factory):
        state = factory.create_gamestate("arakni")
        assert len(state.players) == 2
        p1 = state.players[1]
        hero_zone = p1.zone_by_name("hero")
        hero_slugs = [c.slug for c in hero_zone]
        assert "arakni" in hero_slugs

    def test_factory_instant_card(self, factory):
        state = factory.create_gamestate("a_drop_in_the_ocean_blue")
        assert len(state.players) == 2
        p1 = state.players[1]
        hand_slugs = [c.slug for c in p1.hand]
        assert "a_drop_in_the_ocean_blue" in hand_slugs

    def test_factory_defense_reaction(self, factory):
        state = factory.create_gamestate("absorb_in_aether_red")
        assert len(state.players) == 2
        assert state.step == Step.COMBAT_REACTION
        assert state.combat is not None

    def test_factory_attack_reaction(self, factory):
        state = factory.create_gamestate("affirm_loyalty_red")
        assert len(state.players) == 2
        assert state.step == Step.COMBAT_REACTION
        assert state.combat is not None


# =========================================================================
# 2. DB module — unit tests
# =========================================================================

class TestDB:
    def test_db_init_idempotent(self, tmp_db, tmp_path, monkeypatch):
        """Calling init_db twice does not raise or duplicate the schema."""
        gs_db.init_db(force=True)
        gs_db.init_db(force=False)
        # Table should still exist with no errors
        row = tmp_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='card_test_gamestates'"
        ).fetchone()
        assert row is not None

    def test_db_insert_and_query(self, tmp_db):
        gs_db.insert_gamestate(
            card_slug="test_slug",
            card_name="Test Card",
            card_types='["Action"]',
            card_category="deck",
            original_gamestate='{"step":"action"}',
            post_gamestate='{"step":"action"}',
            status="generated",
        )
        row = gs_db.get_gamestate("test_slug")
        assert row is not None
        assert row["card_slug"] == "test_slug"
        assert row["card_name"] == "Test Card"
        parsed = json.loads(row["original_gamestate"])
        assert parsed["step"] == "action"

    def test_db_upsert_idempotent(self, tmp_db):
        for val in ("first", "second"):
            gs_db.insert_gamestate(
                card_slug="upsert_slug",
                card_name=val,
                card_types="[]",
                card_category="deck",
                original_gamestate="{}",
                post_gamestate="{}",
                status="generated",
            )
        rows = tmp_db.execute(
            "SELECT COUNT(*) as cnt FROM card_test_gamestates WHERE card_slug='upsert_slug'"
        ).fetchone()
        assert rows["cnt"] == 1
        row = gs_db.get_gamestate("upsert_slug")
        assert row["card_name"] == "second"


# =========================================================================
# 3. Batch error isolation
# =========================================================================

class TestBatchErrorIsolation:
    def test_batch_error_isolation(self, tmp_db, monkeypatch):
        """One card failure must not stop the batch from processing others."""
        from data.card_test_gamestates.batch_runner import run_batch

        factory = GameStateFactory()

        # Craft entries: one real, one bogus slug that will fail, one real
        entries = [
            {"slug": "a_drop_in_the_ocean_blue", "name": "Drop", "types": ["Instant"]},
            {"slug": "NONEXISTENT_CARD_SLUG_XYZ", "name": "Bad", "types": ["Action"]},
            {"slug": "arakni", "name": "Arakni", "types": ["Hero"]},
        ]

        counts = run_batch(entries, factory)
        # The bogus slug should error, but the other two should succeed
        assert counts["error"] >= 1
        total = sum(counts.values())
        assert total == 3


# =========================================================================
# 4. Serialization
# =========================================================================

class TestSerialization:
    def test_serialization_includes_players(self, factory):
        state = factory.create_gamestate("a_drop_in_the_ocean_blue")
        d = serialize_gamestate(state)
        assert "players" in d
        assert len(d["players"]) == 2
        assert "done" in d
        assert "winner" in d

    def test_serialization_roundtrip(self, factory):
        state = factory.create_gamestate("arakni")
        d = serialize_gamestate(state)
        text = json.dumps(d, default=str)
        loaded = json.loads(text)
        assert "players" in loaded
        assert loaded["done"] is False


# =========================================================================
# 5. Dynamic parametrized test using card_slug fixture
# =========================================================================

# Known slugs whose card types aren't handled yet
_XFAIL_SLUGS: set[str] = set()


def test_factory_creates_valid_state(card_slug):
    """Parametrized over every slug via conftest.pytest_generate_tests."""
    if card_slug in _XFAIL_SLUGS:
        pytest.xfail(f"Known unsupported slug: {card_slug}")

    factory = GameStateFactory()
    state = factory.create_gamestate(card_slug)

    # Basic structural checks
    assert len(state.players) == 2, "State must have 2 players"
    assert state.step is not None, "Step must be set"

    # Card should be in some zone of either player.
    # Defense Reactions and Block cards are placed in P2 (the defender), so check both.
    _ZONE_NAMES = (
        "hand", "deck", "graveyard", "banish", "pitch", "arsenal",
        "permanents", "hero", "weapon1", "weapon2",
        "head", "chest", "arms", "legs",
    )
    all_cards = []
    for pid in (1, 2):
        p = state.players[pid]
        for zone_name in _ZONE_NAMES:
            zone = p.zone_by_name(zone_name)
            if zone is not None:
                all_cards.extend(c.slug for c in zone)
    assert card_slug in all_cards, f"{card_slug} not found in any zone of either player"


# =========================================================================
# 6. Integration — batch runner subset
# =========================================================================

class TestBatchRunnerSubset:
    def test_batch_runner_subset(self, tmp_db):
        """Run batch for 50 cards and verify DB has 50 rows."""
        import json
        import config
        from data.card_test_gamestates.batch_runner import run_batch, _load_slugs

        factory = GameStateFactory()
        slugs = _load_slugs()[:50]

        counts = run_batch(slugs, factory, limit=50)
        total = sum(counts.values())
        assert total == 50

        row_count = tmp_db.execute(
            "SELECT COUNT(*) as cnt FROM card_test_gamestates"
        ).fetchone()["cnt"]
        assert row_count == 50
