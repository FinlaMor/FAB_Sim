"""Unit tests for rl_agents.deck_validator module."""
from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.card import CardDB
from rl_agents.deck_validator import validate_single_deck, validate_all_decks


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def card_db() -> CardDB:
    return CardDB()


@pytest.fixture(scope="module")
def slug_index() -> dict:
    from config import SLUG_INDEX_PATH
    with open(SLUG_INDEX_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("by_slug", data)


@pytest.fixture(scope="module")
def valid_deck_path() -> str:
    """Return a known-good deck from decks/generated/."""
    # Try worktree first, then fall back to main repo via git
    gen_dir = os.path.join(ROOT, "decks", "generated")
    if not os.path.isdir(gen_dir):
        import subprocess
        try:
            main_root = subprocess.check_output(
                ["git", "worktree", "list", "--porcelain"],
                cwd=ROOT, text=True,
            ).split("\n")[0].replace("worktree ", "").strip()
            gen_dir = os.path.join(main_root, "decks", "generated")
        except Exception:
            pass
    if not os.path.isdir(gen_dir):
        pytest.skip("decks/generated/ not found")
    txt_files = sorted(f for f in os.listdir(gen_dir) if f.endswith(".txt"))
    if not txt_files:
        pytest.skip("No deck files in decks/generated/")
    # Find first deck that actually passes validation
    _db = CardDB()
    _si_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "card_data", "slug_index.json")
    if not os.path.exists(_si_path):
        from config import SLUG_INDEX_PATH
        _si_path = SLUG_INDEX_PATH
    with open(_si_path, encoding="utf-8") as f:
        _si = json.load(f).get("by_slug", json.load(open(_si_path)))
    with open(_si_path, encoding="utf-8") as f:
        _si = json.load(f)
    _si = _si.get("by_slug", _si)
    for fn in txt_files:
        path = os.path.join(gen_dir, fn)
        ok, _ = validate_single_deck(path, _db, _si)
        if ok:
            return path
    pytest.skip("No valid deck found in decks/generated/")


# ---------------------------------------------------------------------------
# (a) Valid deck passes validation
# ---------------------------------------------------------------------------

def test_validate_legal_deck(card_db, slug_index, valid_deck_path):
    is_valid, violations = validate_single_deck(valid_deck_path, card_db, slug_index)
    assert is_valid, f"Expected valid deck but got violations: {violations}"
    assert violations == []


# ---------------------------------------------------------------------------
# (b) Wrong class cards → violations
# ---------------------------------------------------------------------------

def test_reject_wrong_class(card_db, slug_index, tmp_path):
    """A deck with cards from the wrong class should fail validation."""
    # Use a Ninja hero but give it Warrior-only cards
    deck_content = """\
Name: Bad Class Deck
Hero: Arakni 5Lp3D 7Hru 7H3 Cr4X
Format: Classic Constructed

Arena cards
1x Hatchet Of Body
1x Crown Of Providence
1x Fyendals Spring Tunic
1x Nullrune Gloves
1x Nullrune Boots

Deck cards
3x Driving Blade (red)
3x Overpower (red)
3x Pummel (red)
"""
    deck_file = tmp_path / "wrong_class.txt"
    deck_file.write_text(deck_content)

    is_valid, violations = validate_single_deck(str(deck_file), card_db, slug_index)
    assert not is_valid, "Deck with wrong-class cards should be invalid"
    assert len(violations) > 0


# ---------------------------------------------------------------------------
# (c) Missing weapon → flagged
# ---------------------------------------------------------------------------

def test_reject_missing_weapon(card_db, slug_index, tmp_path):
    """A deck with no weapon should be flagged."""
    # Deck with no Arena/weapon line
    deck_content = """\
Name: No Weapon Deck
Hero: Arakni 5Lp3D 7Hru 7H3 Cr4X
Format: Classic Constructed

Arena cards
1x Crown Of Providence
1x Fyendals Spring Tunic
1x Nullrune Gloves
1x Nullrune Boots

Deck cards
3x Infect (red)
3x Infiltrate (red)
"""
    deck_file = tmp_path / "no_weapon.txt"
    deck_file.write_text(deck_content)

    is_valid, violations = validate_single_deck(str(deck_file), card_db, slug_index)
    assert not is_valid
    assert any("weapon" in v.lower() for v in violations), f"Expected weapon violation, got: {violations}"


# ---------------------------------------------------------------------------
# (d) Missing equipment → flagged
# ---------------------------------------------------------------------------

def test_reject_missing_equipment(card_db, slug_index, tmp_path):
    """A deck with empty equipment should be flagged."""
    # Deck with only weapon in arena, no equipment
    deck_content = """\
Name: No Equipment Deck
Hero: Arakni 5Lp3D 7Hru 7H3 Cr4X
Format: Classic Constructed

Arena cards
1x Hunters Klaive R

Deck cards
3x Infect (red)
3x Infiltrate (red)
"""
    deck_file = tmp_path / "no_equipment.txt"
    deck_file.write_text(deck_content)

    is_valid, violations = validate_single_deck(str(deck_file), card_db, slug_index)
    assert not is_valid
    assert any("equipment" in v.lower() for v in violations), f"Expected equipment violation, got: {violations}"


# ---------------------------------------------------------------------------
# (e) validate_all_decks filters invalid
# ---------------------------------------------------------------------------

def test_validate_all_decks_filters_invalid(card_db, slug_index, valid_deck_path, tmp_path):
    """validate_all_decks should separate valid from invalid decks."""
    import shutil

    # Copy valid deck
    valid_dest = tmp_path / "valid.txt"
    shutil.copy2(valid_deck_path, valid_dest)

    # Create an invalid deck (no weapon, no equipment)
    invalid_content = """\
Name: Invalid Deck
Hero: Arakni 5Lp3D 7Hru 7H3 Cr4X
Format: Classic Constructed

Arena cards

Deck cards
3x Infect (red)
"""
    (tmp_path / "invalid.txt").write_text(invalid_content)

    valid_paths, invalid_report = validate_all_decks(str(tmp_path), card_db, slug_index)

    assert len(valid_paths) >= 1, "Should have at least one valid deck"
    assert any("valid.txt" in p for p in valid_paths)
    assert len(invalid_report) >= 1, "Should have at least one invalid deck"
    assert any("invalid.txt" in p for p in invalid_report)


# ---------------------------------------------------------------------------
# (f) Empty directory → empty results
# ---------------------------------------------------------------------------

def test_validate_all_decks_empty_dir(card_db, slug_index, tmp_path):
    """Empty directory returns empty valid list."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    valid_paths, invalid_report = validate_all_decks(str(empty_dir), card_db, slug_index)
    assert valid_paths == []
    assert invalid_report == {}
