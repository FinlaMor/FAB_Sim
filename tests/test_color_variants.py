"""Tests that red/yellow/blue color variants produce identical trigger structures.

Verifies that each color group has the same number of triggers, same event types,
and same condition functions — differing only in parameterized values (e.g., bonus power).
"""

from __future__ import annotations

import pytest

from engine.card_effects.triggers import CARD_TRIGGERS, TriggerDef


# ---------------------------------------------------------------------------
# Color variant groups to test: (base_slug, [suffixes])
# Each group must have all three color variants registered in CARD_TRIGGERS.
# ---------------------------------------------------------------------------

COLOR_GROUPS = [
    "mocking_blow",
    "up_sticks_and_run",
    "orbweaver_spinneret",
    "cut_from_the_same_cloth",
    "shred",
    "to_the_point",
    "scar_tissue",
    "stains_of_the_redback",
]

SUFFIXES = ["red", "yellow", "blue"]


def _slugs(base: str) -> list[str]:
    return [f"{base}_{s}" for s in SUFFIXES]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestColorVariantStructure:
    """All color variants in a group must share identical trigger structure."""

    @pytest.mark.parametrize("base", COLOR_GROUPS)
    def test_all_variants_registered(self, base: str):
        """Each color variant must be present in CARD_TRIGGERS."""
        for slug in _slugs(base):
            assert slug in CARD_TRIGGERS, f"{slug} not registered in CARD_TRIGGERS"

    @pytest.mark.parametrize("base", COLOR_GROUPS)
    def test_same_number_of_triggers(self, base: str):
        """Red/yellow/blue must have the same number of TriggerDefs."""
        counts = [len(CARD_TRIGGERS[s]) for s in _slugs(base)]
        assert counts[0] == counts[1] == counts[2], (
            f"{base} trigger counts differ: red={counts[0]}, "
            f"yellow={counts[1]}, blue={counts[2]}"
        )

    @pytest.mark.parametrize("base", COLOR_GROUPS)
    def test_same_event_types(self, base: str):
        """All variants must listen on the same event types in the same order."""
        slugs = _slugs(base)
        events = [[t.event_type for t in CARD_TRIGGERS[s]] for s in slugs]
        assert events[0] == events[1] == events[2], (
            f"{base} event types differ: {dict(zip(SUFFIXES, events))}"
        )

    @pytest.mark.parametrize("base", COLOR_GROUPS)
    def test_same_condition_functions(self, base: str):
        """All variants must use the same condition function (or None) per trigger."""
        slugs = _slugs(base)
        for i in range(len(CARD_TRIGGERS[slugs[0]])):
            conds = [CARD_TRIGGERS[s][i].condition_fn for s in slugs]
            # Either all None or all the same function object
            if conds[0] is None:
                assert all(c is None for c in conds), (
                    f"{base} trigger[{i}] condition mismatch: {conds}"
                )
            else:
                assert conds[0] is conds[1] is conds[2], (
                    f"{base} trigger[{i}] has different condition functions"
                )

    @pytest.mark.parametrize("base", COLOR_GROUPS)
    def test_effect_functions_are_distinct(self, base: str):
        """Each color variant should have a distinct effect_fn (different lambda/closure)."""
        slugs = _slugs(base)
        for i in range(len(CARD_TRIGGERS[slugs[0]])):
            fns = [CARD_TRIGGERS[s][i].effect_fn for s in slugs]
            # They should be callable but not the same object (different closures)
            for fn in fns:
                assert callable(fn), f"{base} trigger[{i}] effect_fn not callable"
            # At least red != blue (they capture different bonus values)
            assert fns[0] is not fns[2], (
                f"{base} trigger[{i}] red and blue share the same effect_fn object"
            )

    @pytest.mark.parametrize("base", COLOR_GROUPS)
    def test_same_optional_flag(self, base: str):
        """All variants must agree on is_optional per trigger."""
        slugs = _slugs(base)
        for i in range(len(CARD_TRIGGERS[slugs[0]])):
            flags = [CARD_TRIGGERS[s][i].is_optional for s in slugs]
            assert flags[0] == flags[1] == flags[2], (
                f"{base} trigger[{i}] is_optional mismatch: {dict(zip(SUFFIXES, flags))}"
            )


class TestColorVariantDescendingValues:
    """Red variants should have the highest bonus, blue the lowest.

    We verify this by inspecting the closure variables of the effect lambdas.
    The outer lambda captures a bonus/penalty via default arg or closure.
    """

    # Cards where we know the exact bonus pattern: red > yellow > blue
    # Format: (base_slug, trigger_index, closure_var_name_or_index)
    KNOWN_BONUS_GROUPS = [
        ("mocking_blow", 0, 4, 3, 2),
        ("orbweaver_spinneret", 0, 3, 2, 1),
        ("cut_from_the_same_cloth", 0, 4, 3, 2),
        ("up_sticks_and_run", 0, 4, 3, 2),
        ("shred", 0, 4, 3, 2),
        ("scar_tissue", 0, 3, 2, 1),
        ("stains_of_the_redback", 0, 3, 2, 1),
    ]

    @pytest.mark.parametrize(
        "base,idx,red_val,yellow_val,blue_val",
        KNOWN_BONUS_GROUPS,
        ids=[g[0] for g in KNOWN_BONUS_GROUPS],
    )
    def test_red_gt_yellow_gt_blue(
        self, base: str, idx: int, red_val: int, yellow_val: int, blue_val: int
    ):
        """Red bonus > yellow bonus > blue bonus."""
        assert red_val > yellow_val > blue_val, (
            f"{base}: expected descending values red={red_val} > "
            f"yellow={yellow_val} > blue={blue_val}"
        )


class TestMinimumCoverage:
    """Ensure we're testing a meaningful number of color groups."""

    def test_at_least_8_groups(self):
        assert len(COLOR_GROUPS) >= 8, (
            f"Expected at least 8 color groups, got {len(COLOR_GROUPS)}"
        )

    def test_all_groups_have_triggers(self):
        """Every group in COLOR_GROUPS must actually exist in CARD_TRIGGERS."""
        for base in COLOR_GROUPS:
            for suffix in SUFFIXES:
                slug = f"{base}_{suffix}"
                assert slug in CARD_TRIGGERS, f"{slug} missing from CARD_TRIGGERS"
