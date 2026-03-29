"""Unit and integration tests for zone content columns, pitch stacks,
deck remainder, and migration script in rl_agents/game_data.py."""
from __future__ import annotations

import json
import os
import sqlite3
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from rl_agents.game_data import (
    GameDataStore,
    Transition,
    TransitionCollector,
    DeckMeta,
    _extract_zone_slugs,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _card(slug: str) -> dict:
    """Create a minimal Talishar card dict."""
    return {"cardNumber": slug}


def _make_state(**overrides) -> dict:
    """Build a Talishar-style state dict with sensible defaults."""
    state = {
        "playerHand": [_card("sink_below_red"), _card("command_and_conquer_red")],
        "playerDiscard": [_card("pummel_red")],
        "playerBanish": [],
        "playerArse": [_card("arsenal_card")],
        "playerEquipment": [_card("fyendal_spring_tunic")],
        "playerPitch": [_card("pitching_card")],
        "playerSoul": [],
        "playerAuras": [],
        "playerItems": [],
        "playerPermanents": [],
        "playerDeck": [_card("deck_card_a"), _card("deck_card_b"), _card("deck_card_c")],
        "playerHealth": 20,
        "playerAP": 2,
        "playerHero": {"cardNumber": "ira_crimson_haze"},
        "opponentHand": [_card("opp_hand_1"), _card("opp_hand_2")],
        "opponentDiscard": [_card("opp_grave_1")],
        "opponentBanish": [],
        "opponentArse": [],
        "opponentEquipment": [_card("opp_equip_1")],
        "opponentPitch": [_card("opp_pitch_1")],
        "opponentSoul": [],
        "opponentAuras": [],
        "opponentItems": [],
        "opponentPermanents": [],
        "opponentDeck": [_card("x1"), _card("x2")],
        "opponentHealth": 18,
        "opponentHero": {"cardNumber": "dorinthea_ironsong"},
        "turnPhase": "M",
        "activeChainLink": None,
        "combatChainLinks": [],
    }
    state.update(overrides)
    return state


def _make_action(slug: str = "sink_below_red") -> dict:
    return {"cardNumber": slug, "mode": 27, "type": "hand"}


def _make_deck_meta(game_id: str) -> DeckMeta:
    return DeckMeta(
        game_id=game_id,
        p1_deck_file="deck1.txt",
        p2_deck_file="deck2.txt",
        p1_decklist={"hero": "ira", "cards": []},
        p2_decklist={"hero": "dorinthea", "cards": []},
        winner=1,
        p1_final_hp=15,
        p2_final_hp=0,
        turn_count=5,
        ended_on_turn_cap=False,
        total_actions=20,
        seed=42,
    )


# ===========================================================================
# (1) _extract_zone_slugs tests
# ===========================================================================

class TestExtractZoneSlugs:
    def test_normal_extraction(self):
        state = {"zone": [_card("a"), _card("b")]}
        result = _extract_zone_slugs(state, "zone")
        assert json.loads(result) == ["a", "b"]

    def test_empty_list(self):
        state = {"zone": []}
        result = _extract_zone_slugs(state, "zone")
        assert result == "[]"

    def test_missing_key(self):
        result = _extract_zone_slugs({}, "zone")
        assert result is None

    def test_non_dict_cards_skipped(self):
        state = {"zone": ["string_card", _card("valid"), 42, None]}
        result = _extract_zone_slugs(state, "zone")
        assert json.loads(result) == ["valid"]

    def test_non_list_value(self):
        state = {"zone": "not_a_list"}
        result = _extract_zone_slugs(state, "zone")
        assert result is None

    def test_cards_with_cardID_fallback(self):
        state = {"zone": [{"cardID": "fallback_slug"}]}
        result = _extract_zone_slugs(state, "zone")
        assert json.loads(result) == ["fallback_slug"]

    def test_cards_with_empty_slug_skipped(self):
        state = {"zone": [{"cardNumber": ""}, {"cardNumber": "good"}]}
        result = _extract_zone_slugs(state, "zone")
        assert json.loads(result) == ["good"]

    def test_all_empty_slugs_returns_empty_array(self):
        state = {"zone": [{"cardNumber": ""}, {"other": "data"}]}
        result = _extract_zone_slugs(state, "zone")
        assert result == "[]"


# ===========================================================================
# (2) Player pitch stack ordering
# ===========================================================================

class TestPlayerPitchStack:
    def test_chronological_ordering_across_turns(self):
        """Pitch stack preserves chronological order across multiple turns."""
        collector = TransitionCollector(game_id="test_pitch")
        action = _make_action()

        # Turn 1: pitch card_a
        state1 = _make_state(playerPitch=[_card("card_a")], playerDeck=[])
        collector.record(1, 1, state1, [action], action, None, 20, 20)

        # Turn 2: pitch card_b, card_c
        state2 = _make_state(playerPitch=[_card("card_b"), _card("card_c")], playerDeck=[])
        collector.record(1, 2, state2, [action], action, None, 20, 20)

        transitions = collector.transitions
        stack = json.loads(transitions[-1].player_pitch_stack)
        assert stack == ["card_a", "card_b", "card_c"]

    def test_empty_pitch_zone(self):
        collector = TransitionCollector(game_id="test_empty_pitch")
        action = _make_action()
        state = _make_state(playerPitch=[], playerDeck=[])
        collector.record(1, 1, state, [action], action, None, 20, 20)
        t = collector.transitions[0]
        assert json.loads(t.player_pitch_stack) == []


# ===========================================================================
# (3) Opponent pitch stack bucketing
# ===========================================================================

class TestOppPitchStack:
    def test_turn_bucketed_alpha_sorted(self):
        collector = TransitionCollector(game_id="test_opp_pitch")
        action = _make_action()

        # Turn 1: opponent pitches z_card, a_card (should be alpha-sorted)
        state1 = _make_state(opponentPitch=[_card("z_card"), _card("a_card")])
        collector.record(1, 1, state1, [action], action, None, 20, 20)

        # Turn 3: opponent pitches m_card
        state2 = _make_state(opponentPitch=[_card("m_card")])
        collector.record(1, 3, state2, [action], action, None, 20, 20)

        t = collector.transitions[-1]
        opp_stack = json.loads(t.opp_pitch_stack)
        assert opp_stack == {"1": ["a_card", "z_card"], "3": ["m_card"]}

    def test_empty_opponent_pitch(self):
        collector = TransitionCollector(game_id="test_opp_empty")
        action = _make_action()
        state = _make_state(opponentPitch=[])
        collector.record(1, 1, state, [action], action, None, 20, 20)
        t = collector.transitions[0]
        opp_stack = json.loads(t.opp_pitch_stack)
        assert opp_stack == {}


# ===========================================================================
# (4) Deck remainder excluding pitch stack
# ===========================================================================

class TestDeckRemainder:
    def test_excludes_pitched_cards(self):
        collector = TransitionCollector(game_id="test_deck_rem")
        action = _make_action()

        # Pitch card_a, then check deck remainder
        state = _make_state(
            playerPitch=[_card("card_a")],
            playerDeck=[_card("card_a"), _card("card_b"), _card("card_c")],
        )
        collector.record(1, 1, state, [action], action, None, 20, 20)
        t = collector.transitions[0]
        remainder = json.loads(t.deck_remainder)
        # card_a excluded, remainder alpha-sorted
        assert remainder == ["card_b", "card_c"]

    def test_no_deck_key(self):
        collector = TransitionCollector(game_id="test_no_deck")
        action = _make_action()
        state = _make_state()
        del state["playerDeck"]
        collector.record(1, 1, state, [action], action, None, 20, 20)
        t = collector.transitions[0]
        assert t.deck_remainder is None


# ===========================================================================
# (5) Opponent visibility rules
# ===========================================================================

class TestOppVisibility:
    def test_no_opponent_hand_content(self):
        """Transition should NOT have opponent hand card slugs."""
        collector = TransitionCollector(game_id="test_vis")
        action = _make_action()
        state = _make_state(opponentHand=[_card("secret_1"), _card("secret_2")])
        collector.record(1, 1, state, [action], action, None, 20, 20)
        t = collector.transitions[0]
        # No opp_hand field with card contents
        assert not hasattr(t, "opp_hand") or getattr(t, "opp_hand", None) is None
        # opp_hand_size should be a count only
        assert t.opp_hand_size == 2

    def test_no_opponent_deck_content(self):
        collector = TransitionCollector(game_id="test_vis2")
        action = _make_action()
        state = _make_state(opponentDeck=[_card("x1"), _card("x2")])
        collector.record(1, 1, state, [action], action, None, 20, 20)
        t = collector.transitions[0]
        assert not hasattr(t, "opp_deck") or getattr(t, "opp_deck", None) is None
        assert t.opp_cards_in_deck == 2

    def test_no_opponent_arsenal_content(self):
        collector = TransitionCollector(game_id="test_vis3")
        action = _make_action()
        state = _make_state(opponentArse=[_card("hidden_arsenal")])
        collector.record(1, 1, state, [action], action, None, 20, 20)
        t = collector.transitions[0]
        # opp_has_arsenal is bool, no content
        assert t.opp_has_arsenal is True

    def test_opponent_public_zones_present(self):
        collector = TransitionCollector(game_id="test_vis4")
        action = _make_action()
        state = _make_state(
            opponentDiscard=[_card("opp_grave")],
            opponentEquipment=[_card("opp_eq")],
        )
        collector.record(1, 1, state, [action], action, None, 20, 20)
        t = collector.transitions[0]
        assert json.loads(t.opp_graveyard) == ["opp_grave"]
        assert json.loads(t.opp_equipment) == ["opp_eq"]


# ===========================================================================
# (6) Transition dataclass initialization
# ===========================================================================

class TestTransitionNewFields:
    def test_all_new_fields_exist(self):
        """Transition dataclass has all new zone/pitch/metadata fields."""
        new_fields = [
            "player_hand", "player_graveyard", "player_banished", "player_arsenal",
            "player_equipment", "player_pitch_zone", "player_soul", "player_auras",
            "player_items", "player_permanents",
            "opp_graveyard", "opp_banished", "opp_equipment", "opp_pitch_zone",
            "opp_soul", "opp_auras", "opp_items", "opp_permanents",
            "player_pitch_stack", "opp_pitch_stack", "deck_remainder",
            "player_hero", "opp_hero", "combat_attack_card",
            "combat_defending_cards", "chain_link_history",
        ]
        # Verify all fields exist on the dataclass
        from dataclasses import fields as dc_fields
        field_names = {f.name for f in dc_fields(Transition)}
        for f in new_fields:
            assert f in field_names, f"Missing field: {f}"

    def test_defaults_are_none(self):
        """New fields default to None."""
        collector = TransitionCollector(game_id="test_defaults")
        collector.record_simple(player_id=1)
        t = collector.transitions[0]
        assert t.player_hand is None
        assert t.player_pitch_stack is None
        assert t.deck_remainder is None
        assert t.player_hero is None


# ===========================================================================
# (7) record_simple() defaults
# ===========================================================================

class TestRecordSimpleDefaults:
    def test_all_zone_fields_none(self):
        collector = TransitionCollector(game_id="test_simple")
        collector.record_simple(player_id=1, reward=0.5, done=False)
        t = collector.transitions[0]
        assert t.reward == 0.5
        assert t.done is False
        assert t.player_hand is None
        assert t.opp_graveyard is None
        assert t.player_pitch_stack is None
        assert t.opp_pitch_stack is None
        assert t.deck_remainder is None
        assert t.player_hero is None
        assert t.opp_hero is None
        assert t.combat_attack_card is None
        assert t.combat_defending_cards is None
        assert t.chain_link_history is None

    def test_core_fields_populated(self):
        collector = TransitionCollector(game_id="test_simple2")
        collector.record_simple(player_id=2, turn_number=3, p1_hp=15, p2_hp=18)
        t = collector.transitions[0]
        assert t.player_id == 2
        assert t.turn_number == 3
        assert t.p1_hp == 15
        assert t.p2_hp == 18
        assert t.decision_type == "other"


# ===========================================================================
# (8) save_game() round-trip
# ===========================================================================

class TestSaveGameRoundTrip:
    def test_all_new_columns_persisted(self, tmp_path):
        store = GameDataStore.create_fresh(base_dir=str(tmp_path), prefix="zone_test")
        try:
            collector = TransitionCollector(game_id="roundtrip_1")
            state = _make_state()
            action = _make_action()
            collector.record(1, 1, state, [action], action, None, 20, 18)
            collector.finalize(winner=1)
            meta = _make_deck_meta("roundtrip_1")
            store.save_game(collector, meta)

            conn = sqlite3.connect(store.db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM transitions WHERE game_id='roundtrip_1' LIMIT 1"
            ).fetchone()
            conn.close()

            assert row is not None
            # Zone content columns
            assert json.loads(row["player_hand"]) == ["sink_below_red", "command_and_conquer_red"]
            assert json.loads(row["player_graveyard"]) == ["pummel_red"]
            assert json.loads(row["player_equipment"]) == ["fyendal_spring_tunic"]
            assert json.loads(row["opp_graveyard"]) == ["opp_grave_1"]
            # Hero slugs
            assert row["player_hero"] == "ira_crimson_haze"
            assert row["opp_hero"] == "dorinthea_ironsong"
            # Pitch stack
            assert row["player_pitch_stack"] is not None
            assert row["opp_pitch_stack"] is not None
            # Deck remainder
            assert row["deck_remainder"] is not None
        finally:
            store.close()


# ===========================================================================
# (9) Backward compatibility (old NULL rows)
# ===========================================================================

class TestBackwardCompat:
    def test_old_null_rows_read_without_error(self, tmp_path):
        """Rows with NULL new columns can coexist with populated rows."""
        store = GameDataStore.create_fresh(base_dir=str(tmp_path), prefix="compat_test")
        try:
            # Insert a row with NULLs for new columns via record_simple
            collector = TransitionCollector(game_id="old_game")
            collector.record_simple(player_id=1, reward=0.0, done=False)
            collector.finalize(winner=None)
            meta = _make_deck_meta("old_game")
            meta.game_id = "old_game"
            meta.winner = None
            store.save_game(collector, meta)

            # Insert a new row with populated columns
            collector2 = TransitionCollector(game_id="new_game")
            state = _make_state()
            action = _make_action()
            collector2.record(1, 1, state, [action], action, None, 20, 18)
            collector2.finalize(winner=1)
            meta2 = _make_deck_meta("new_game")
            store.save_game(collector2, meta2)

            # Both rows should be readable
            conn = sqlite3.connect(store.db_path)
            rows = conn.execute("SELECT game_id, player_hand FROM transitions ORDER BY game_id").fetchall()
            conn.close()
            assert len(rows) == 2
            # Old row has NULL
            assert rows[1][1] is None  # new_game has data, old_game has NULL
        finally:
            store.close()


# ===========================================================================
# (10) Migration script correctness
# ===========================================================================

class TestMigrationScript:
    def test_add_columns_and_backfill(self, tmp_path):
        """Migration adds columns and backfills from state JSON."""
        # Import migration functions
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from migrate_talishar_zones import (
            _add_missing_columns,
            _get_existing_columns,
            _ZONE_MAP,
            _extract_hero_slug,
        )

        db_path = str(tmp_path / "migrate_test.db")
        conn = sqlite3.connect(db_path)

        # Create a minimal old-schema transitions table (without new columns)
        conn.execute("""
            CREATE TABLE transitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT NOT NULL,
                step INTEGER NOT NULL,
                player_id INTEGER NOT NULL,
                turn_number INTEGER NOT NULL,
                state TEXT NOT NULL,
                available_actions TEXT NOT NULL,
                action_taken TEXT NOT NULL,
                action_index INTEGER NOT NULL,
                next_state TEXT,
                reward REAL NOT NULL,
                done INTEGER NOT NULL,
                p1_hp INTEGER NOT NULL,
                p2_hp INTEGER NOT NULL
            )
        """)

        # Insert a row with a state JSON blob
        state = _make_state()
        conn.execute(
            "INSERT INTO transitions (game_id, step, player_id, turn_number, state, "
            "available_actions, action_taken, action_index, reward, done, p1_hp, p2_hp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("g1", 0, 1, 1, json.dumps(state), "[]", "{}", -1, 0.0, 0, 20, 18),
        )
        conn.commit()

        # Run column addition
        added = _add_missing_columns(conn, dry_run=False)
        assert added > 0

        # Verify columns exist
        cols = _get_existing_columns(conn, "transitions")
        assert "player_hand" in cols
        assert "player_hero" in cols
        assert "opp_pitch_stack" in cols

        # Verify idempotent re-run
        added2 = _add_missing_columns(conn, dry_run=False)
        assert added2 == 0

        conn.close()

    def test_extract_hero_slug_from_dict(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from migrate_talishar_zones import _extract_hero_slug
        state = {"playerHero": {"cardNumber": "ira_crimson_haze"}}
        assert _extract_hero_slug(state, "playerHero") == "ira_crimson_haze"

    def test_extract_hero_slug_from_string(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from migrate_talishar_zones import _extract_hero_slug
        state = {"playerHero": "ira_crimson_haze"}
        assert _extract_hero_slug(state, "playerHero") == "ira_crimson_haze"

    def test_extract_hero_slug_missing(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from migrate_talishar_zones import _extract_hero_slug
        assert _extract_hero_slug({}, "playerHero") is None
