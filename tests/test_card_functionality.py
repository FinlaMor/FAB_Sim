"""Card database functionality test.

For a representative sample of card slugs, this test:
  1. Validates that CardDB loads correct stats (power, defense, pitch, cost).
  2. Uses GameStateFactory to place the card in the appropriate zone.
  3. Calls legal_actions() to confirm the engine recognises the card.
  4. Applies the first available action — verifying no exceptions are raised.
  5. Checks keyword flags and type properties match the slug_index source.

Sample strategy
---------------
- Fixed random seed for reproducibility.
- ~5% of the catalogue sampled per type group (Action, Attack, Equipment, Weapon,
  Defense Reaction, Attack Reaction, Instant, Item, Aura, Hero, Token, Landmark).
- All slugs that appear in effect registries are always included.
"""
from __future__ import annotations

import json
import os
import random
import sys
import traceback
from collections import defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import SLUG_INDEX_PATH
from data.card_test_gamestates.gamestate_factory import GameStateFactory, CARD_TYPE_TO_ZONE, _EQUIPMENT_SLOT_MAP
from engine.card import CardDB
from engine.engine import legal_actions, apply_action
from engine.state import Step


# ---------------------------------------------------------------------------
# Load card data
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def slug_index() -> dict:
    with open(SLUG_INDEX_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def card_db() -> CardDB:
    return CardDB(SLUG_INDEX_PATH)


@pytest.fixture(scope="module")
def factory(card_db) -> GameStateFactory:
    return GameStateFactory(card_db=card_db)


# ---------------------------------------------------------------------------
# Registry slugs — always tested
# ---------------------------------------------------------------------------

def _get_registry_slugs() -> set[str]:
    """Return all slugs present in any card-effect registry."""
    slugs: set[str] = set()
    try:
        from engine.card_effects import registry as _reg
        for attr in dir(_reg):
            val = getattr(_reg, attr)
            if isinstance(val, dict):
                slugs.update(val.keys())
    except Exception:
        pass
    return slugs


# ---------------------------------------------------------------------------
# Sampling helpers
# ---------------------------------------------------------------------------

_SAMPLE_FRACTION = 0.05   # 5% per type group
_SAMPLE_SEED = 42


def _build_sample(slug_index: dict) -> list[str]:
    """Return a deterministic sample covering all type groups plus registry slugs."""
    rng = random.Random(_SAMPLE_SEED)
    by_slug = slug_index["by_slug"]

    # Group slugs by their primary type
    groups: defaultdict[str, list[str]] = defaultdict(list)
    for slug, data in by_slug.items():
        types = data.get("types") or []
        # Primary type = first listed
        primary = types[0] if types else "Unknown"
        groups[primary].append(slug)

    sampled: set[str] = set()
    for group, members in groups.items():
        k = max(1, int(len(members) * _SAMPLE_FRACTION))
        sampled.update(rng.sample(members, min(k, len(members))))

    # Always include all registered effect slugs that exist in the index
    registry_slugs = _get_registry_slugs()
    for s in registry_slugs:
        if s in by_slug:
            sampled.add(s)

    return sorted(sampled)


# ---------------------------------------------------------------------------
# Per-card test helpers
# ---------------------------------------------------------------------------

def _expected_zone(data: dict) -> str:
    """Return the expected zone name given slug_index data.

    Uses the same priority as GameStateFactory._resolve_zone_and_step so the
    two are always consistent.
    """
    types = data.get("types") or []
    subtypes = data.get("subtypes") or []

    for type_key, (zone, _step) in CARD_TYPE_TO_ZONE.items():
        if type_key in types:
            if type_key == "Equipment":
                for subtype, slot in _EQUIPMENT_SLOT_MAP.items():
                    if subtype in subtypes:
                        return slot
                return "chest"
            return zone

    # Attack subtype (type="Action", subtype="Attack")
    if "Attack" in subtypes:
        return "hand"

    # supertypes Token → permanents
    supertypes = data.get("supertypes") or []
    if "Token" in supertypes:
        return "permanents"

    # Ally subtype → permanents
    if "Ally" in subtypes:
        return "permanents"

    return "hand"


def _card_in_zone(state, slug: str, zone_name: str) -> bool:
    """Return True if slug is found in zone_name for either player."""
    for player in state.players.values():
        zone = player.zone_by_name(zone_name)
        if zone is not None and any(c.slug == slug for c in zone):
            return True
    return False


# ---------------------------------------------------------------------------
# Parametrised tests
# ---------------------------------------------------------------------------

# Build sample at collection time so pytest can show the count.
with open(SLUG_INDEX_PATH, encoding="utf-8") as _f:
    _slug_index_data = json.load(_f)
SAMPLE_SLUGS = _build_sample(_slug_index_data)


@pytest.fixture(scope="module")
def sample_slugs() -> list[str]:
    return SAMPLE_SLUGS


def test_sample_size(sample_slugs, slug_index):
    """Sanity check: we always test at least 100 cards."""
    total = len(slug_index["by_slug"])
    assert len(sample_slugs) >= 100, (
        f"Sample too small: {len(sample_slugs)} of {total}"
    )
    print(f"\n  Sampled {len(sample_slugs)} / {total} cards")


@pytest.mark.parametrize("slug", SAMPLE_SLUGS)
class TestCardFunctionality:
    """Run per-card checks: stats, zone, playability, application."""

    # ── 1. Stats match slug_index ─────────────────────────────────────

    def test_stats_load_correctly(self, slug: str, slug_index, card_db):
        """Card attributes from CardDB match the slug_index source of truth."""
        data = slug_index["by_slug"][slug]
        card = card_db.get(slug)

        assert card is not None, f"CardDB.get('{slug}') returned None"
        assert card.slug == slug

        def _stat(val):
            """Normalise slug_index stat: '' or None → None."""
            return None if val is None or val == "" else int(val)

        # Numeric stats — skip check when slug_index has None or "" (optional fields)
        if _stat(data.get("power")) is not None:
            assert card.base_power == _stat(data["power"]), (
                f"{slug}: base_power={card.base_power!r}, expected {_stat(data['power'])!r}"
            )
        if _stat(data.get("defense")) is not None:
            assert card.base_defense == _stat(data["defense"]), (
                f"{slug}: base_defense={card.base_defense!r}, expected {_stat(data['defense'])!r}"
            )
        if _stat(data.get("pitch")) is not None:
            assert card.base_pitch == _stat(data["pitch"]), (
                f"{slug}: base_pitch={card.base_pitch!r}, expected {_stat(data['pitch'])!r}"
            )
        if _stat(data.get("cost")) is not None:
            assert card.base_cost == _stat(data["cost"]), (
                f"{slug}: base_cost={card.base_cost!r}, expected {_stat(data['cost'])!r}"
            )
        if _stat(data.get("health")) is not None:
            assert card.base_life == _stat(data["health"]), (
                f"{slug}: base_life={card.base_life!r}, expected {_stat(data['health'])!r}"
            )
        if _stat(data.get("intelligence")) is not None:
            assert card.base_intellect == _stat(data["intelligence"]), (
                f"{slug}: base_intellect={card.base_intellect!r}, expected {_stat(data['intelligence'])!r}"
            )

    # ── 2. Keyword flags ──────────────────────────────────────────────

    def test_keyword_flags(self, slug: str, slug_index, card_db):
        """has_go_again, has_dominate, has_on_hit match ability_keywords in slug_index."""
        data = slug_index["by_slug"][slug]
        card = card_db.get(slug)

        kws = [k.lower() for k in (data.get("ability_keywords") or [])]

        if "go again" in kws:
            assert card.has_go_again, f"{slug}: expected has_go_again=True"

        if "dominate" in kws:
            assert card.has_dominate, f"{slug}: expected has_dominate=True"

        # Cards registered in HIT_EFFECTS must have has_on_hit = True.
        # (Reverse is NOT checked — text may mention hits without a registered effect.)
        try:
            from engine.card_effects.registry import HIT_EFFECTS
            if slug in HIT_EFFECTS:
                assert card.has_on_hit or card.has_on_hit_trigger, (
                    f"{slug}: registered in HIT_EFFECTS but has_on_hit=False"
                )
        except ImportError:
            pass

    # ── 3. Type properties ────────────────────────────────────────────

    def test_type_properties(self, slug: str, slug_index, card_db):
        """Computed type booleans match the types list from slug_index."""
        data = slug_index["by_slug"][slug]
        card = card_db.get(slug)
        types = data.get("types") or []

        if "Attack" in types:
            assert card.is_attack, f"{slug}: expected is_attack=True"
        if "Action" in types:
            assert card.is_action, f"{slug}: expected is_action=True"
        if "Instant" in types:
            assert card.is_instant, f"{slug}: expected is_instant=True"
        if "Equipment" in types:
            assert card.is_equipment, f"{slug}: expected is_equipment=True"
        if "Weapon" in types:
            assert card.is_weapon, f"{slug}: expected is_weapon=True"
        if "Hero" in types:
            assert card.is_hero, f"{slug}: expected is_hero=True"
        if "Defense Reaction" in types:
            assert card.is_defense_reaction, f"{slug}: expected is_defense_reaction=True"

    # ── 4. GameStateFactory zone placement ───────────────────────────

    def test_gamestate_zone_placement(self, slug: str, slug_index, factory):
        """GameStateFactory places the card in the expected zone."""
        data = slug_index["by_slug"][slug]
        types = data.get("types") or []
        subtypes = data.get("subtypes") or []

        # Heroes require a dedicated hero slot — the factory replaces test_hero
        # with the actual hero card, so just verify the state is constructed.
        try:
            state = factory.create_gamestate(slug)
        except Exception as exc:
            pytest.fail(f"{slug}: GameStateFactory raised {type(exc).__name__}: {exc}")

        assert len(state.players) == 2, f"{slug}: expected 2 players"

        # For hero cards, the factory sets up a hero zone entry;
        # skip zone check (hero replaces the generic test hero).
        if "Hero" in types or "Demi-Hero" in types or "DemiHero" in types or "Macro" in types:
            return
        # Equipment with no recognized slot subtype — factory falls back to chest but
        # the card may not pass chest zone entry; skip placement check.
        if "Equipment" in types and not any(s in subtypes for s in ("Head", "Chest", "Arms", "Legs", "OffHand", "Off-Hand", "Quiver", "Base")):
            return

        expected = _expected_zone(data)
        assert _card_in_zone(state, slug, expected), (
            f"{slug}: card not found in zone '{expected}' "
            f"(types={types})"
        )

    # ── 5. Engine offers ≥ 1 legal action ─────────────────────────────

    def test_legal_actions_not_empty(self, slug: str, slug_index, factory, card_db):
        """legal_actions() returns at least one action for the constructed state."""
        data = slug_index["by_slug"][slug]
        types = data.get("types") or []

        # Tokens have no independent legal action (they're game objects, not playable
        # cards), so skip playability check for pure tokens.
        supertypes = data.get("supertypes") or []
        if "Token" in supertypes and "Action" not in types and "Attack" not in types:
            pytest.skip("Token-only card — no standalone playable action expected")

        # Landmark cards are placed by other effects; skip.
        if "Landmark" in types and "Action" not in types:
            pytest.skip("Landmark — placed by effects, no standalone action")

        try:
            state = factory.create_gamestate(slug)
            actions = legal_actions(state, card_db)
        except Exception as exc:
            pytest.fail(
                f"{slug}: exception during legal_actions — "
                f"{type(exc).__name__}: {exc}"
            )

        assert len(actions) > 0, (
            f"{slug}: legal_actions returned empty list "
            f"(types={types}, step={state.step})"
        )

    # ── 6. Apply first legal action — no exception ────────────────────

    def test_apply_action_no_exception(self, slug: str, slug_index, factory, card_db):
        """Applying the first legal action raises no exception."""
        data = slug_index["by_slug"][slug]
        types = data.get("types") or []
        supertypes = data.get("supertypes") or []

        if "Token" in supertypes and "Action" not in types and "Attack" not in types:
            pytest.skip("Token-only card — no standalone playable action")
        if "Landmark" in types and "Action" not in types:
            pytest.skip("Landmark — placed by effects")

        try:
            state = factory.create_gamestate(slug)
            actions = legal_actions(state, card_db)
        except Exception as exc:
            pytest.fail(
                f"{slug}: setup failed — {type(exc).__name__}: {exc}"
            )

        if not actions:
            pytest.skip(f"{slug}: no legal actions to apply")

        try:
            apply_action(state, actions[0])
        except Exception as exc:
            pytest.fail(
                f"{slug}: apply_action raised {type(exc).__name__}: {exc}\n"
                f"  action={actions[0]}\n"
                + traceback.format_exc()
            )

    # ── 7. Attack power matches slug_index for attack cards ───────────

    def test_attack_power_in_combat(self, slug: str, slug_index, factory, card_db):
        """Attack cards: CombatState.attack_power matches card's base_power."""
        data = slug_index["by_slug"][slug]
        types = data.get("types") or []

        if "Attack" not in types:
            pytest.skip("Not an attack card")
        if not data.get("power") and data.get("power") != 0:
            pytest.skip(f"{slug}: no base_power in slug_index")

        state = factory.create_gamestate(slug)

        # The factory places attack cards at COMBAT_ATTACK step with a CombatState.
        assert state.step == Step.COMBAT_ATTACK, (
            f"{slug}: expected COMBAT_ATTACK step, got {state.step}"
        )
        assert state.combat is not None, f"{slug}: expected combat state"
        expected_power = int(data["power"])
        assert state.combat.attack_power == expected_power, (
            f"{slug}: combat.attack_power={state.combat.attack_power}, "
            f"expected {expected_power}"
        )
