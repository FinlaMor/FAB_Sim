"""The ability_type sweep: a reaction type on a card that is not a reaction.

A wrong ability_type is exactly as fatal as a dead flag — the ability never
fires — but it was the one defect class with NO audit coverage, so it was only
ever found by reading cards one at a time. It turned up by hand in five separate
groups (biting_blade, glint_the_quicksilver, rushing_river, grow_claws/grow_wings,
push_the_point) before this check existed.

The recurring confusion is between "an ability that TRIGGERS when this attacks"
(TRIGGERED + ON_ATTACK) and "an Attack Reaction CARD" (ability_type
ATTACK_REACTION). The former is common on Action - Attack cards; the latter only
belongs on a card that is printed as a reaction.

Two exemptions matter, and both are real cards:
  * an Arakni demi-hero reads "Once per Turn Attack Reaction - ..." in its TEXT,
    so ATTACK_REACTION is correct even though its type is "Demi-Hero";
  * ability_type INSTANT is legitimate when the text has an "Instant - <cost>:"
    ACTIVATED ability, and wrong when the card is merely an Instant that
    resolves on play.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import audit_run


def _audit_one(tmp_path, slug, abilities, type_text, functional_text):
    import json
    p = tmp_path / f"{slug}.json"
    p.write_text(json.dumps({"slug": slug, "abilities": abilities}), encoding="utf-8")
    index = {slug: {"typeText": type_text, "functionalText": functional_text}}
    return audit_run.audit([p], index).get(slug, [])


def test_attack_reaction_on_an_action_attack_is_flagged(tmp_path):
    found = _audit_one(
        tmp_path, "probe",
        [{"ability_type": "ATTACK_REACTION", "effects": [{"type": "GO_AGAIN"}]}],
        "Ninja Action - Attack",
        "When you attack with Probe, draw a card.")
    assert any("ATTACK_REACTION on a card that is not one" in f for f in found), found


def test_attack_reaction_on_a_real_attack_reaction_is_clean(tmp_path):
    found = _audit_one(
        tmp_path, "probe",
        [{"ability_type": "ATTACK_REACTION", "effects": [{"type": "GO_AGAIN"}]}],
        "Warrior Attack Reaction",
        "Target weapon attack gets go again.")
    assert not any("not one" in f for f in found), found


def test_attack_reaction_granted_by_card_text_is_clean(tmp_path):
    # The Arakni demi-heroes: type is "Demi-Hero", but the TEXT grants the
    # reaction. Checking the printed type alone would flag these wrongly.
    found = _audit_one(
        tmp_path, "probe",
        [{"ability_type": "ATTACK_REACTION", "effects": [{"type": "GO_AGAIN"}]}],
        "Chaos Assassin Demi-Hero",
        "**Once per Turn Attack Reaction** - Discard an Assassin card: "
        "Target Assassin attack gets +3{p}.")
    assert not any("not one" in f for f in found), found


def test_defense_reaction_on_a_trap_action_is_flagged(tmp_path):
    found = _audit_one(
        tmp_path, "probe",
        [{"ability_type": "DEFENSE_REACTION", "effects": [{"type": "DRAW", "amount": 1}]}],
        "Ranger Action - Trap",
        "When this defends an attack, its controller discards a card.")
    assert any("DEFENSE_REACTION on a card that is not one" in f for f in found), found


def test_defense_reaction_on_a_real_defense_reaction_is_clean(tmp_path):
    found = _audit_one(
        tmp_path, "probe",
        [{"ability_type": "DEFENSE_REACTION", "effects": [{"type": "DRAW", "amount": 1}]}],
        "Assassin Defense Reaction - Trap",
        "When this defends, they lose 1{h}.")
    assert not any("not one" in f for f in found), found


def test_instant_ability_type_on_a_plain_instant_card_is_flagged(tmp_path):
    found = _audit_one(
        tmp_path, "probe",
        [{"ability_type": "INSTANT", "effects": [{"type": "DRAW", "amount": 1}]}],
        "Light Instant",
        "The next time a Shadow source would deal damage this turn, prevent 4.")
    assert any("INSTANT but the text has no" in f for f in found), found


def test_instant_ability_type_with_an_activated_instant_is_clean(tmp_path):
    found = _audit_one(
        tmp_path, "probe",
        [{"ability_type": "INSTANT", "effects": [{"type": "DRAW", "amount": 1}]}],
        "Runeblade Equipment - Chest",
        "**Instant** - Destroy this: Draw a card.")
    assert not any("INSTANT but the text" in f for f in found), found


def test_sweep_finds_real_defects_in_the_corpus():
    # Guards the guard: if the rule were accidentally disabled the checks above
    # would still pass on synthetic input while the corpus went unswept.
    index = audit_run.load_index() if hasattr(audit_run, "load_index") else None
    if index is None:
        import json
        index = json.loads((ROOT / "card_data" / "slug_index.json").read_text(encoding="utf-8"))
        index = index.get("by_slug", index)
    findings = audit_run.audit(audit_run.card_files(), index)
    hits = [f for fs in findings.values() for f in fs
            if "not one" in f or "INSTANT but the text" in f]
    assert hits, "the ability_type sweep reported nothing across the whole corpus"
