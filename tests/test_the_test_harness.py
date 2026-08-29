"""The harness itself, tested, because three times it accused a correct card.

Every card test in this suite builds a little world by hand -- a state, an
attack, some tokens -- and three separate false alarms came from getting that
world subtly wrong rather than from any defect in the card:

    the identity trap   SOURCE_IS_ATTACK is `combat.attack_card is c`. A test
                        that builds combat from one deepcopy and passes the
                        ability a second, equal-but-not-identical copy makes
                        the condition false, and a working static silently does
                        nothing. Indistinguishable from a missing buff.
    the overlapping     `auras` is a VIEW over the same objects `permanents`
    zones               holds. Summing them counted three tokens as six and
                        reported two correct cards as broken.
    the ownerless card  discard() reads the DISCARDED CARD's owner to decide
                        whose hand it left, so a filler card with no owner
                        resolves to player 0 and raises KeyError inside the
                        engine.

conftest now provides attack_with / tokens_controlled / owned_card so nobody
reimplements them, and assert_source_is_the_attack turns the first trap from a
silent false negative into a loud explanation.

These tests pin the helpers. A helper that quietly stopped working would take
every test that relies on it down with it -- and would do so by making cards
look fine, which is the worse direction.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card_effects.dsl.condition_types import compile_condition
from tests.conftest import (_make_state, assert_source_is_the_attack,
                            attack_with, owned_card, tokens_controlled)


class _FakeAbility:
    def __init__(self, types):
        self.conditions = [type("C", (), {"condition_type": t})() for t in types]


# --- the identity trap -------------------------------------------------------

def test_source_is_attack_really_compares_identity():
    """The premise for the guard. If this ever became an equality test the
    guard would be unnecessary -- and, more importantly, the bug it prevents
    would no longer exist."""
    st = _make_state()
    a = owned_card(1, "spike", types=["Action"], base_power=4)
    b = owned_card(1, "spike", types=["Action"], base_power=4)
    attack_with(st, a)

    fn = compile_condition("SOURCE_IS_ATTACK", {})
    assert fn(a, None, st) is True, "the attack card should satisfy it"
    assert fn(b, None, st) is False, (
        "an equal COPY satisfied SOURCE_IS_ATTACK -- it is no longer an "
        "identity test and this whole class of false alarm has changed")


def test_the_guard_fires_on_a_detached_copy():
    st = _make_state()
    a = owned_card(1, "spike", base_power=4)
    b = owned_card(1, "spike", base_power=4)
    attack_with(st, a)
    ability = _FakeAbility(["SOURCE_IS_ATTACK"])

    with pytest.raises(AssertionError, match="IDENTITY"):
        assert_source_is_the_attack(ability, b, st)


def test_the_guard_is_silent_on_the_real_attack_card():
    st = _make_state()
    a = owned_card(1, "spike", base_power=4)
    attack_with(st, a)
    # Returns None rather than raising. Asserted explicitly: a test whose only
    # check lives inside a helper reads as vacuous to static analysis, and
    # test_tests_actually_assert is right to say so.
    assert assert_source_is_the_attack(
        _FakeAbility(["SOURCE_IS_ATTACK"]), a, st) is None


def test_the_guard_ignores_abilities_that_are_not_gated_on_it():
    """It must not become a blanket requirement that every ability's source be
    the attack -- most are not."""
    st = _make_state()
    attack_with(st, owned_card(1, "spike", base_power=4))
    assert assert_source_is_the_attack(
        _FakeAbility(["HEALTH_LT_OPP"]), owned_card(1, "other"), st) is None


# --- the overlapping zones ---------------------------------------------------

def test_tokens_are_counted_once_across_overlapping_zones():
    st = _make_state()
    tok = owned_card(2, "toughness", types=["Token"], subtypes=["Aura"])
    st.players[2].permanents.add(tok)
    seen = [c for c in tokens_controlled(st, 2) if c is tok]
    assert len(seen) == 1, (
        f"the same token object was counted {len(seen)} times -- auras and "
        "permanents overlap and the dedupe has stopped working")


def test_tokens_can_be_filtered_by_name():
    st = _make_state()
    st.players[1].permanents.add(owned_card(1, "toughness", types=["Token"]))
    st.players[1].permanents.add(owned_card(1, "vigor", types=["Token"]))
    assert len(tokens_controlled(st, 1, "toughness")) == 1
    assert len(tokens_controlled(st, 1, "vigor")) == 1


# --- the ownerless card ------------------------------------------------------

def test_owned_card_actually_sets_an_owner():
    """An ownerless card resolves to player 0 in the engine paths that read the
    owner off the card, which raises KeyError rather than failing usefully."""
    c = owned_card(2, "filler")
    assert c.owner == 2 and c.controller == 2


# --- attack_with --------------------------------------------------------------

def test_attack_with_returns_the_object_it_installed():
    """The whole point: tests must pass THIS object as the ability source."""
    st = _make_state()
    c = owned_card(1, "spike", base_power=7)
    returned = attack_with(st, c)
    assert returned is c
    assert st.combat.attack_card is c


def test_attack_with_defaults_power_to_the_card_base():
    st = _make_state()
    c = owned_card(1, "spike", base_power=7)
    attack_with(st, c)
    assert st.combat.attack_power == 7
    assert st.combat.base_attack_power == 7
