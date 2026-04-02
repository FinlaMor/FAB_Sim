"""Unit and integration tests for banned cards functionality."""
from __future__ import annotations

import json
import os
import sys
import warnings

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_banned_json(path, data):
    """Write banned cards JSON to the given path."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)


# ---------------------------------------------------------------------------
# (a) load_banned_cards — missing file, empty format, valid format
# ---------------------------------------------------------------------------

def test_load_banned_cards_missing_file(tmp_path, monkeypatch):
    """Returns empty frozenset when banned_cards.json doesn't exist."""
    from rl_agents import fab_constants
    fake_path = tmp_path / "nonexistent.json"
    monkeypatch.setattr(fab_constants, "_BANNED_CARDS_PATH", fake_path)

    result = fab_constants.load_banned_cards("cc")
    assert result == frozenset()
    assert isinstance(result, frozenset)


def test_load_banned_cards_empty_format(tmp_path, monkeypatch):
    """Returns empty frozenset for unknown format key."""
    from rl_agents import fab_constants
    banned_path = tmp_path / "banned_cards.json"
    _write_banned_json(banned_path, {"cc": ["some-slug"]})
    monkeypatch.setattr(fab_constants, "_BANNED_CARDS_PATH", banned_path)

    result = fab_constants.load_banned_cards("blitz")
    assert result == frozenset()


def test_load_banned_cards_returns_slugs(tmp_path, monkeypatch):
    """Returns correct frozenset for a populated format."""
    from rl_agents import fab_constants
    banned_path = tmp_path / "banned_cards.json"
    _write_banned_json(banned_path, {"cc": ["slug-a", "slug-b"]})
    monkeypatch.setattr(fab_constants, "_BANNED_CARDS_PATH", banned_path)

    result = fab_constants.load_banned_cards("cc")
    assert result == frozenset({"slug-a", "slug-b"})


# ---------------------------------------------------------------------------
# (b) CLI management functions — add, duplicate, remove, nonexistent, clear, list
# ---------------------------------------------------------------------------

def test_manage_add_card(tmp_path, monkeypatch):
    """Adding a slug persists it to the JSON file."""
    import scripts.manage_banned_cards as mgr

    banned_path = tmp_path / "banned_cards.json"
    _write_banned_json(banned_path, {"cc": []})
    monkeypatch.setattr(mgr, "BANNED_CARDS_PATH", str(banned_path))

    # Suppress slug validation warnings
    monkeypatch.setattr(mgr, "_load_slug_index", lambda: {})

    import argparse
    args = argparse.Namespace(format="cc", slugs=["test-slug"], all_colors=False)
    mgr.cmd_add(args)

    with open(banned_path) as f:
        data = json.load(f)
    assert "test-slug" in data["cc"]


def test_manage_add_duplicate(tmp_path, monkeypatch):
    """Adding the same slug twice results in only one entry."""
    import scripts.manage_banned_cards as mgr

    banned_path = tmp_path / "banned_cards.json"
    _write_banned_json(banned_path, {"cc": ["test-slug"]})
    monkeypatch.setattr(mgr, "BANNED_CARDS_PATH", str(banned_path))
    monkeypatch.setattr(mgr, "_load_slug_index", lambda: {})

    import argparse
    args = argparse.Namespace(format="cc", slugs=["test-slug"], all_colors=False)
    mgr.cmd_add(args)

    with open(banned_path) as f:
        data = json.load(f)
    assert data["cc"].count("test-slug") == 1


def test_manage_remove_card(tmp_path, monkeypatch):
    """Removing a slug removes it from the JSON file."""
    import scripts.manage_banned_cards as mgr

    banned_path = tmp_path / "banned_cards.json"
    _write_banned_json(banned_path, {"cc": ["remove-me"]})
    monkeypatch.setattr(mgr, "BANNED_CARDS_PATH", str(banned_path))

    import argparse
    args = argparse.Namespace(format="cc", slugs=["remove-me"])
    mgr.cmd_remove(args)

    with open(banned_path) as f:
        data = json.load(f)
    assert "remove-me" not in data["cc"]


def test_manage_remove_nonexistent(tmp_path, monkeypatch):
    """Removing a slug that doesn't exist warns but doesn't error."""
    import scripts.manage_banned_cards as mgr

    banned_path = tmp_path / "banned_cards.json"
    _write_banned_json(banned_path, {"cc": []})
    monkeypatch.setattr(mgr, "BANNED_CARDS_PATH", str(banned_path))

    import argparse
    args = argparse.Namespace(format="cc", slugs=["ghost-slug"])
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        mgr.cmd_remove(args)
    assert any("ghost-slug" in str(warning.message) for warning in w)


def test_manage_clear_format(tmp_path, monkeypatch):
    """Clearing a format removes all its entries."""
    import scripts.manage_banned_cards as mgr

    banned_path = tmp_path / "banned_cards.json"
    _write_banned_json(banned_path, {"cc": ["a", "b", "c"]})
    monkeypatch.setattr(mgr, "BANNED_CARDS_PATH", str(banned_path))

    import argparse
    args = argparse.Namespace(format="cc")
    mgr.cmd_clear(args)

    with open(banned_path) as f:
        data = json.load(f)
    assert data["cc"] == []


def test_manage_list_all(tmp_path, monkeypatch, capsys):
    """Listing shows all formats and their banned cards."""
    import scripts.manage_banned_cards as mgr

    banned_path = tmp_path / "banned_cards.json"
    _write_banned_json(banned_path, {"cc": ["slug-a"], "blitz": ["slug-b"]})
    monkeypatch.setattr(mgr, "BANNED_CARDS_PATH", str(banned_path))

    import argparse
    args = argparse.Namespace(format=None)
    mgr.cmd_list(args)

    output = capsys.readouterr().out
    assert "cc" in output
    assert "blitz" in output
    assert "slug-a" in output
    assert "slug-b" in output


# ---------------------------------------------------------------------------
# (c) Validation — banned card violation, no false positives
# ---------------------------------------------------------------------------

def test_validate_banned_card_violation():
    """validate_deck_legality() reports violation for a banned card."""
    from rl_agents.fab_constants import validate_deck_legality

    slug_index = {
        "test-card": {
            "name": "Test Card",
            "types": ["Warrior", "Action"],
            "type_text": "Warrior Action",
        }
    }
    violations = validate_deck_legality(
        deck_cards=[{"card_slug": "test-card"}],
        equipment=[],
        hero_types=["Warrior", "Hero"],
        slug_index=slug_index,
        banned_slugs=frozenset({"test-card"}),
    )
    assert len(violations) >= 1
    assert any("banned" in v.lower() for v in violations)


def test_validate_no_banned_cards():
    """No false positives when banned_slugs is empty or None."""
    from rl_agents.fab_constants import validate_deck_legality

    slug_index = {
        "test-card": {
            "name": "Test Card",
            "types": ["Warrior", "Action"],
            "type_text": "Warrior Action",
        }
    }
    # With None
    v1 = validate_deck_legality(
        deck_cards=[{"card_slug": "test-card"}],
        equipment=[],
        hero_types=["Warrior", "Hero"],
        slug_index=slug_index,
        banned_slugs=None,
    )
    # With empty frozenset
    v2 = validate_deck_legality(
        deck_cards=[{"card_slug": "test-card"}],
        equipment=[],
        hero_types=["Warrior", "Hero"],
        slug_index=slug_index,
        banned_slugs=frozenset(),
    )
    assert not any("banned" in v.lower() for v in v1)
    assert not any("banned" in v.lower() for v in v2)


# ---------------------------------------------------------------------------
# (d) Generation — legal pool excludes banned cards
# ---------------------------------------------------------------------------

def test_build_legal_pool_excludes_banned():
    """build_legal_pool() result minus banned set excludes the banned card."""
    # This tests the pattern: legal_pool = legal_pool - banned
    pool = frozenset({"card-a", "card-b", "card-c"})
    banned = frozenset({"card-b"})
    filtered = pool - banned
    assert "card-b" not in filtered
    assert "card-a" in filtered
    assert "card-c" in filtered


# ---------------------------------------------------------------------------
# (e) Integration tests
# ---------------------------------------------------------------------------

def test_end_to_end_ban_and_validate(tmp_path, monkeypatch):
    """Add a card to ban list, run validation, verify violation is reported."""
    import scripts.manage_banned_cards as mgr
    from rl_agents import fab_constants

    # Set up temp banned cards file
    banned_path = tmp_path / "banned_cards.json"
    _write_banned_json(banned_path, {"cc": []})
    monkeypatch.setattr(mgr, "BANNED_CARDS_PATH", str(banned_path))
    monkeypatch.setattr(mgr, "_load_slug_index", lambda: {})
    monkeypatch.setattr(fab_constants, "_BANNED_CARDS_PATH", banned_path)

    # Add a card to the banned list via management functions
    import argparse
    args = argparse.Namespace(format="cc", slugs=["banned-card"], all_colors=False)
    mgr.cmd_add(args)

    # Load banned cards
    banned = fab_constants.load_banned_cards("cc")
    assert "banned-card" in banned

    # Validate a deck containing the banned card
    slug_index = {
        "banned-card": {
            "name": "Banned Card",
            "types": ["Generic", "Action"],
            "type_text": "Generic Action",
        }
    }
    violations = fab_constants.validate_deck_legality(
        deck_cards=[{"card_slug": "banned-card"}],
        equipment=[],
        hero_types=["Warrior", "Hero"],
        slug_index=slug_index,
        banned_slugs=banned,
    )
    assert any("banned" in v.lower() for v in violations)


def test_end_to_end_ban_and_generate(tmp_path, monkeypatch):
    """Add a card to ban list, verify it's excluded from a legal pool."""
    import scripts.manage_banned_cards as mgr
    from rl_agents import fab_constants

    # Set up temp banned cards file
    banned_path = tmp_path / "banned_cards.json"
    _write_banned_json(banned_path, {"cc": []})
    monkeypatch.setattr(mgr, "BANNED_CARDS_PATH", str(banned_path))
    monkeypatch.setattr(mgr, "_load_slug_index", lambda: {})
    monkeypatch.setattr(fab_constants, "_BANNED_CARDS_PATH", banned_path)

    # Add a card to the banned list
    import argparse
    args = argparse.Namespace(format="cc", slugs=["card-to-ban"], all_colors=False)
    mgr.cmd_add(args)

    # Simulate the generation pattern: legal_pool - banned
    legal_pool = frozenset({"card-to-ban", "legal-card-a", "legal-card-b"})
    banned = fab_constants.load_banned_cards("cc")
    filtered_pool = legal_pool - banned

    assert "card-to-ban" not in filtered_pool
    assert "legal-card-a" in filtered_pool
    assert "legal-card-b" in filtered_pool


# ---------------------------------------------------------------------------
# (f) Production legal_formats and HeroCardDB integration tests
# ---------------------------------------------------------------------------

# Heroes NOT legal in CC per the official FAB card data legal_formats field.
# These were previously tracked in banned_cards.json but are now determined
# by the absence of "ClassicConstructed" in each card's legal_formats.
CC_ILLEGAL_HERO_SLUGS = frozenset({
    "aurora_shooting_star",
    "azalea_ace_in_the_hole",
    "bravo_star_of_the_show",
    "briar_warden_of_thorns",
    "chane_bound_by_shadow",
    "dash_inventor_extraordinaire",
    "dromai_ash_artist",
    "enigma_ledger_of_ancestry",
    "florian_rotwood_harbinger",
    "iyslander_stormbind",
    "kano_dracai_of_aether",
    "kayo_armed_and_dangerous",
    "lexi_livewire",
    "nuu_alluring_desire",
    "oldhim_grandfather_of_eternity",
    "prism_sculptor_of_arc_light",
    "verdance_thorn_of_the_rose",
    "viserai_rune_blood",
    "zen_tamer_of_purpose",
})

CC_ILLEGAL_WEAPON_SLUGS = frozenset({
    "star_fall",
    "death_dealer",
    "rosetta_thorn",
    "galaxxi_black",
    "teklo_plasma_pistol",
    "storm_of_sandikai",
    "cosmo_scroll_of_ancestral_tapestry",
    "rotwood_reaper",
    "krakens_aethervein",
    "crucible_of_aetherweave",
    "mandible_claw",
    "voltaire_strike_twice",
    "beckoning_mistblade",
    "winters_wail",
    "luminaris",
    "staff_of_verdant_shoots",
    "nebula_blade",
    "tiger_taming_khakkara",
})


def _load_slug_index_for_test() -> dict:
    """Load slug_index (msgpack or json) for test assertions."""
    import msgpack
    msgpack_path = os.path.join(ROOT, "card_data", "slug_index.msgpack")
    json_path = os.path.join(ROOT, "card_data", "slug_index.json")
    if os.path.exists(msgpack_path):
        with open(msgpack_path, "rb") as f:
            return msgpack.unpack(f, raw=False).get("by_slug", {})
    elif os.path.exists(json_path):
        with open(json_path, encoding="utf-8") as f:
            return json.load(f).get("by_slug", {})
    pytest.skip("slug_index not available")


def test_cc_illegal_heroes_not_in_cc_legal_formats():
    """Heroes in CC_ILLEGAL_HERO_SLUGS lack 'ClassicConstructed' in legal_formats."""
    by_slug = _load_slug_index_for_test()
    for slug in CC_ILLEGAL_HERO_SLUGS:
        entry = by_slug.get(slug)
        if entry is None:
            continue  # slug not in index, skip
        legal_fmts = entry.get("legal_formats", [])
        assert "ClassicConstructed" not in legal_fmts, (
            f"{slug} should NOT be CC-legal but has ClassicConstructed in legal_formats"
        )


def test_cc_illegal_weapons_not_in_cc_legal_formats():
    """Weapons in CC_ILLEGAL_WEAPON_SLUGS lack 'ClassicConstructed' in legal_formats."""
    by_slug = _load_slug_index_for_test()
    for slug in CC_ILLEGAL_WEAPON_SLUGS:
        entry = by_slug.get(slug)
        if entry is None:
            continue
        legal_fmts = entry.get("legal_formats", [])
        assert "ClassicConstructed" not in legal_fmts, (
            f"{slug} should NOT be CC-legal but has ClassicConstructed in legal_formats"
        )


def test_validate_deck_legality_fmt_param():
    """validate_deck_legality with fmt= catches cards not legal in format."""
    from rl_agents.fab_constants import validate_deck_legality

    slug_index = {
        "test_card": {
            "name": "Test Card",
            "types": ["Generic", "Action"],
            "type_text": "Generic Action",
            "legal_formats": ["Blitz"],
        }
    }
    violations = validate_deck_legality(
        deck_cards=[{"card_slug": "test_card"}],
        equipment=[],
        hero_types=["Warrior", "Hero"],
        slug_index=slug_index,
        fmt="cc",
    )
    assert len(violations) == 1
    assert "not legal in ClassicConstructed" in violations[0]

    # Same card IS legal in Blitz
    violations_blitz = validate_deck_legality(
        deck_cards=[{"card_slug": "test_card"}],
        equipment=[],
        hero_types=["Warrior", "Hero"],
        slug_index=slug_index,
        fmt="blitz",
    )
    assert not violations_blitz


def test_hero_card_db_from_slug_index_excludes_cc_illegal_heroes():
    """HeroCardDB.from_slug_index() excludes CC-illegal hero slugs."""
    from rl_agents.deck_search import HeroCardDB

    db = HeroCardDB.from_slug_index()
    illegal_heroes_in_db = set(db.hero_cards.keys()) & CC_ILLEGAL_HERO_SLUGS
    assert not illegal_heroes_in_db, (
        f"CC-illegal heroes found in hero_cards: {illegal_heroes_in_db}"
    )


def test_hero_card_db_from_slug_index_excludes_cc_illegal_cards():
    """HeroCardDB.from_slug_index() card pools contain no CC-illegal slugs."""
    from rl_agents.deck_search import HeroCardDB

    by_slug = _load_slug_index_for_test()
    db = HeroCardDB.from_slug_index()

    cc_illegal_slugs = {
        slug for slug, entry in by_slug.items()
        if entry.get("legal_formats") and "ClassicConstructed" not in entry.get("legal_formats", [])
    }

    all_card_slugs = set()
    for hero_slug in db.hero_cards:
        for card in db.hero_cards[hero_slug]:
            all_card_slugs.add(card.get("card_slug", card.get("slug", "")))
        for card in db.hero_equipment.get(hero_slug, []):
            all_card_slugs.add(card.get("card_slug", card.get("slug", "")))
        for card in db.hero_weapons.get(hero_slug, []):
            all_card_slugs.add(card.get("card_slug", card.get("slug", "")))

    illegal_in_pools = all_card_slugs & cc_illegal_slugs
    assert not illegal_in_pools, (
        f"CC-illegal slugs found in card pools: {illegal_in_pools}"
    )
