"""Verify that keyword-only cards are fully handled by build_keyword_triggers()
without needing CARD_TRIGGERS entries.

Cards whose only game effect comes from their keywords (Go Again, Battleworn,
Blade Break, Temper, Boost, Blood Debt, Stealth, Dominate, Overpower, Phantasm,
Opt, Fusion, Suspense, Galvanize, Heave, etc.) should produce the correct
TriggerDef list from build_keyword_triggers() alone.
"""

from __future__ import annotations

import pytest

from engine.card import Card
from engine.card_effects.triggers import TriggerDef, build_keyword_triggers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _card_with_keywords(*keywords: str) -> Card:
    """Create a minimal Card with the given keywords."""
    return Card(
        slug="test_keyword_card",
        name="Test Keyword Card",
        types=["Action"],
        keywords=list(keywords),
    )


# ---------------------------------------------------------------------------
# Tests — keywords that produce triggers
# ---------------------------------------------------------------------------

class TestKeywordsThatProduceTriggers:
    """Keywords that should generate one or more TriggerDef entries."""

    def test_battleworn(self):
        triggers = build_keyword_triggers(_card_with_keywords("Battleworn"))
        assert len(triggers) == 1
        assert triggers[0].event_type == "combat_chain_close"

    def test_blade_break(self):
        triggers = build_keyword_triggers(_card_with_keywords("Blade Break"))
        assert len(triggers) == 1
        assert triggers[0].event_type == "combat_chain_close"

    def test_temper(self):
        triggers = build_keyword_triggers(_card_with_keywords("Temper"))
        assert len(triggers) == 1
        assert triggers[0].event_type == "combat_chain_close"

    def test_guardwell(self):
        triggers = build_keyword_triggers(_card_with_keywords("Guardwell"))
        assert len(triggers) == 1
        assert triggers[0].event_type == "combat_chain_close"

    def test_phantasm(self):
        triggers = build_keyword_triggers(_card_with_keywords("Phantasm"))
        assert len(triggers) == 1
        assert triggers[0].event_type == "defend"

    def test_spectra(self):
        triggers = build_keyword_triggers(_card_with_keywords("Spectra"))
        assert len(triggers) == 1
        assert triggers[0].event_type == "target_of_attack"

    def test_blood_debt(self):
        triggers = build_keyword_triggers(_card_with_keywords("Blood Debt"))
        assert len(triggers) == 1
        assert triggers[0].event_type == "start_of_end_phase"

    def test_watery_grave(self):
        triggers = build_keyword_triggers(_card_with_keywords("Watery Grave"))
        assert len(triggers) == 1
        assert triggers[0].event_type == "card_destroyed"

    def test_suspense(self):
        triggers = build_keyword_triggers(_card_with_keywords("Suspense"))
        assert len(triggers) == 2
        events = {t.event_type for t in triggers}
        assert events == {"enters_arena", "start_of_turn"}

    def test_boost(self):
        triggers = build_keyword_triggers(_card_with_keywords("Boost"))
        assert len(triggers) == 1
        assert triggers[0].event_type == "on_play"
        assert triggers[0].is_optional is True

    def test_fusion_ice(self):
        triggers = build_keyword_triggers(_card_with_keywords("Ice Fusion"))
        assert len(triggers) == 1
        assert triggers[0].event_type == "on_play"
        assert triggers[0].is_optional is True

    def test_fusion_lightning(self):
        triggers = build_keyword_triggers(_card_with_keywords("Lightning Fusion"))
        assert len(triggers) == 1
        assert triggers[0].event_type == "on_play"

    def test_fusion_earth(self):
        triggers = build_keyword_triggers(_card_with_keywords("Earth Fusion"))
        assert len(triggers) == 1
        assert triggers[0].event_type == "on_play"

    def test_opt(self):
        triggers = build_keyword_triggers(_card_with_keywords("Opt 2"))
        assert len(triggers) == 1
        assert triggers[0].event_type == "on_play"

    def test_opt_default(self):
        """Opt without a number defaults to Opt 1."""
        triggers = build_keyword_triggers(_card_with_keywords("Opt"))
        assert len(triggers) == 1
        assert triggers[0].event_type == "on_play"

    def test_piercing(self):
        triggers = build_keyword_triggers(_card_with_keywords("Piercing 1"))
        assert len(triggers) == 1
        assert triggers[0].event_type == "defend"

    def test_heave(self):
        triggers = build_keyword_triggers(_card_with_keywords("Heave 3"))
        assert len(triggers) == 1
        assert triggers[0].event_type == "start_of_end_phase"
        assert triggers[0].is_optional is True

    def test_crank(self):
        triggers = build_keyword_triggers(_card_with_keywords("Crank"))
        assert len(triggers) == 1
        assert triggers[0].event_type == "enters_arena"
        assert triggers[0].is_optional is True

    def test_the_crowd_cheers(self):
        triggers = build_keyword_triggers(_card_with_keywords("The Crowd Cheers"))
        assert len(triggers) == 1
        assert triggers[0].event_type == "on_play"

    def test_scrap(self):
        # Scrap is now handled as an effect-cost in _pay_effect_costs (pre-stack),
        # not as an on_play trigger — no triggers expected.
        triggers = build_keyword_triggers(_card_with_keywords("Scrap"))
        assert triggers == []

    def test_beat_chest(self):
        # Beat Chest is now handled as an effect-cost in _pay_effect_costs (pre-stack),
        # not as an on_play trigger — no triggers expected.
        triggers = build_keyword_triggers(_card_with_keywords("Beat Chest"))
        assert triggers == []


# ---------------------------------------------------------------------------
# Tests — keywords handled as static abilities (no triggers needed)
# ---------------------------------------------------------------------------

class TestStaticKeywords:
    """Keywords that are static abilities — build_keyword_triggers should
    return an empty list (they are handled elsewhere in the engine)."""

    @pytest.mark.parametrize("keyword", [
        "Go Again",
        "Dominate",
        "Overpower",
        "Stealth",
        "Legendary",
        "Universal",
        "Cloaked",
        "Ephemeral",
        "Pairs",
        "Perched",
        "Unlimited",
        "Modular",
        "Protect",
        "Ambush",
        "Meld",
    ])
    def test_static_keyword_no_trigger(self, keyword):
        triggers = build_keyword_triggers(_card_with_keywords(keyword))
        assert triggers == [], f"{keyword} should not produce triggers"


# ---------------------------------------------------------------------------
# Tests — card-specific keywords (pass-through, no generic trigger)
# ---------------------------------------------------------------------------

class TestCardSpecificKeywords:
    """Keywords that are card-specific and handled via CARD_TRIGGERS entries,
    not build_keyword_triggers. They should produce no triggers."""

    @pytest.mark.parametrize("keyword", [
        "Transform",
        "Charge",
        "Mark",
        "Contract",
        "Clash",
        "Combo",
        "Crush",
        "Reprise",
        "Surge",
        "Rune Gate",
    ])
    def test_card_specific_keyword_no_trigger(self, keyword):
        triggers = build_keyword_triggers(_card_with_keywords(keyword))
        assert triggers == [], f"{keyword} should not produce generic triggers"


# ---------------------------------------------------------------------------
# Tests — multiple keywords combined
# ---------------------------------------------------------------------------

class TestMultipleKeywords:
    """Cards with multiple keywords should get triggers from all of them."""

    def test_battleworn_and_blade_break(self):
        triggers = build_keyword_triggers(
            _card_with_keywords("Battleworn", "Blade Break")
        )
        assert len(triggers) == 2
        events = [t.event_type for t in triggers]
        assert events == ["combat_chain_close", "combat_chain_close"]

    def test_go_again_and_opt(self):
        """Go Again (static) + Opt (trigger) = 1 trigger."""
        triggers = build_keyword_triggers(
            _card_with_keywords("Go Again", "Opt 1")
        )
        assert len(triggers) == 1
        assert triggers[0].event_type == "on_play"

    def test_phantasm_and_dominate(self):
        """Phantasm (trigger) + Dominate (static) = 1 trigger."""
        triggers = build_keyword_triggers(
            _card_with_keywords("Phantasm", "Dominate")
        )
        assert len(triggers) == 1
        assert triggers[0].event_type == "defend"

    def test_all_static_keywords(self):
        """A card with only static keywords produces no triggers."""
        triggers = build_keyword_triggers(
            _card_with_keywords("Go Again", "Dominate", "Overpower", "Stealth")
        )
        assert triggers == []

    def test_boost_and_go_again(self):
        """Boost (trigger) + Go Again (static) = 1 trigger."""
        triggers = build_keyword_triggers(
            _card_with_keywords("Boost", "Go Again")
        )
        assert len(triggers) == 1
        assert triggers[0].event_type == "on_play"
        assert triggers[0].is_optional is True


# ---------------------------------------------------------------------------
# Tests — trigger properties
# ---------------------------------------------------------------------------

class TestTriggerProperties:
    """Verify that trigger definitions have correct properties."""

    def test_all_triggers_are_triggerdef(self):
        triggers = build_keyword_triggers(
            _card_with_keywords("Battleworn", "Boost", "Phantasm")
        )
        for t in triggers:
            assert isinstance(t, TriggerDef)

    def test_all_triggers_have_effect_fn(self):
        triggers = build_keyword_triggers(
            _card_with_keywords("Battleworn", "Boost", "Phantasm")
        )
        for t in triggers:
            assert t.effect_fn is not None, f"Trigger {t.event_type} missing effect_fn"

    def test_combat_close_triggers_have_condition(self):
        """Battleworn/Blade Break/Temper should have condition_fn."""
        for kw in ("Battleworn", "Blade Break", "Temper", "Guardwell"):
            triggers = build_keyword_triggers(_card_with_keywords(kw))
            assert triggers[0].condition_fn is not None, f"{kw} missing condition_fn"

    def test_empty_keywords(self):
        card = Card(slug="no_kw", name="No Keywords", types=["Action"])
        triggers = build_keyword_triggers(card)
        assert triggers == []

    def test_none_keywords(self):
        card = Card(slug="none_kw", name="None Keywords", types=["Action"], keywords=None)
        triggers = build_keyword_triggers(card)
        assert triggers == []
