""""Damage can't be prevented" was authored as WARD, which prevents damage.

step_between_red: "{p} damage CAN'T BE PREVENTED this combat chain." Ward is a
replacement that DESTROYS its source and PREVENTS damage (CR 8.5, and the
worked example at CR line 853). Authoring this clause as WARD therefore did the
exact opposite of what the card says -- it helped the DEFENDER against the very
attack it was meant to push through.

The mechanic already existed on both sides: DamageEvent.unpreventable is a real
field and effects.py already refuses to let Ward prevent unpreventable damage.
What was missing is that MAKE_NEXT_DAMAGE_UNPREVENTABLE was:

  one-shot   it burns itself on the first damage event ("the NEXT damage"),
             while this card says "THIS COMBAT CHAIN" -- every hit on it.
  untyped    "{p} damage" is PHYSICAL only; arcane damage is still preventable.

A chain-scoped clause also must not outlive its chain, so the combat object is
captured by identity at registration.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.effect_types import compile_effect
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.effect_keywords import DamageType, deal_damage
from engine.state import CombatState
from tests.conftest import _make_state
from tests.conftest import _card_json

load_all_cards()
DB = CardDB()

PLAIN = "brutal_assault_red"
HERO = "kayo_strong_arm"
OTHER_HERO = "gravy_bones"
# A real card that PRINTS Ward and legally sits in the aura zone.
WARD_AURA = "10000_year_reunion_red"


def _card(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _state():
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="": o[0]
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    st.individual_turns = 1
    st.players[1].hero = _card(HERO, 1)
    st.players[2].hero = _card(OTHER_HERO, 2)
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=_card(PLAIN, 1), keywords=[])
    return st


def _hit(st, amount=3, dtype=DamageType.PHYSICAL):
    """Deal damage from player 1 to player 2's hero, returning the event."""
    return deal_damage(st, amount, dtype, 1, st.players[2].hero, 'effect',
                       damage_source_card=st.combat.attack_card)


# --- the flag reaches the damage event --------------------------------------

def test_physical_damage_becomes_unpreventable():
    st = _state()
    compile_effect("MAKE_NEXT_DAMAGE_UNPREVENTABLE",
                   {"scope": "combat_chain", "damage_type": "physical"})(
        _card(PLAIN, 1), None, st)

    assert _hit(st).unpreventable is True


def test_arcane_damage_is_untouched_by_a_physical_clause():
    """"{p} damage" is PHYSICAL. An untyped reading would also push arcane
    through, which the card does not say."""
    st = _state()
    compile_effect("MAKE_NEXT_DAMAGE_UNPREVENTABLE",
                   {"scope": "combat_chain", "damage_type": "physical"})(
        _card(PLAIN, 1), None, st)

    assert _hit(st, dtype=DamageType.ARCANE).unpreventable is False


def test_the_chain_scope_covers_every_hit_not_just_the_first():
    """The one-shot form burns itself on the first damage event."""
    st = _state()
    compile_effect("MAKE_NEXT_DAMAGE_UNPREVENTABLE",
                   {"scope": "combat_chain", "damage_type": "physical"})(
        _card(PLAIN, 1), None, st)

    assert _hit(st).unpreventable is True
    assert _hit(st).unpreventable is True, (
        "the second hit on the same chain was preventable again")


def test_the_next_form_still_burns_itself():
    """The default is still "the NEXT damage" — 20-odd cards rely on it."""
    st = _state()
    compile_effect("MAKE_NEXT_DAMAGE_UNPREVENTABLE", {})(_card(PLAIN, 1), None, st)

    assert _hit(st).unpreventable is True
    assert _hit(st).unpreventable is False, "a one-shot clause fired twice"


def test_the_clause_does_not_outlive_its_combat_chain():
    st = _state()
    compile_effect("MAKE_NEXT_DAMAGE_UNPREVENTABLE",
                   {"scope": "combat_chain", "damage_type": "physical"})(
        _card(PLAIN, 1), None, st)
    assert _hit(st).unpreventable is True

    # A new chain is a new CombatState object.
    st.combat = CombatState(attacker_id=1, link_id=2, attack_power=3,
                            attack_card=_card(PLAIN, 1), keywords=[])

    assert _hit(st).unpreventable is False, (
        "the clause carried into the next combat chain")


# --- it actually defeats prevention -----------------------------------------

def _ward_aura(st, pid=2):
    """A real card PRINTING Ward, in a zone it can legally occupy.

    An attack action card put into `permanents` is routed straight to the
    graveyard, so an earlier version of this fixture registered a Ward that
    could never fire -- and the test passed while proving nothing.
    """
    aura = _card(WARD_AURA, pid)
    st.players[pid].auras.add(aura)
    st.effect_manager.register_prevention_effects(aura, st)
    return aura


def test_the_ward_fixture_really_prevents_damage():
    """The control for the test below. Without this, "ward did not reduce the
    damage" is satisfied by a ward that was never going to reduce anything."""
    st = _state()
    _ward_aura(st)
    before = st.players[2].life

    _hit(st, amount=3)

    assert st.players[2].life == before, (
        f"the fixture ward prevented nothing (lost "
        f"{before - st.players[2].life}), so the unpreventable test below "
        f"would pass vacuously")


def test_ward_cannot_prevent_it():
    """The point of the flag: effects.py must refuse to let Ward reduce it.
    Asserted through a real printed Ward, not by reading the flag back."""
    st = _state()
    _ward_aura(st)
    before = st.players[2].life

    compile_effect("MAKE_NEXT_DAMAGE_UNPREVENTABLE",
                   {"scope": "combat_chain", "damage_type": "physical"})(
        _card(PLAIN, 1), None, st)
    _hit(st, amount=3)

    assert st.players[2].life == before - 3, (
        f"ward reduced unpreventable damage: lost "
        f"{before - st.players[2].life} of 3")


# --- step_between_red -------------------------------------------------------

def test_step_between_makes_its_damage_unpreventable():
    st = _state()
    source = _card("step_between_red", 1)
    st.players[1].permanents.add(source)

    run_ability(get_card("step_between_red").abilities[0], source, None, st)

    assert _hit(st).unpreventable is True, (
        "the card that says damage CAN'T be prevented did not push it through")


def test_step_between_does_not_prevent_damage():
    """WARD would have made the card protect the DEFENDER from the attack it is
    supposed to push through."""
    st = _state()
    source = _card("step_between_red", 1)
    st.players[1].permanents.add(source)
    before = st.players[2].life

    run_ability(get_card("step_between_red").abilities[0], source, None, st)
    _hit(st, amount=3)

    assert st.players[2].life == before - 3, (
        "damage was reduced by the card that forbids reducing it")


def test_step_between_still_adds_its_power():
    st = _state()
    source = _card("step_between_red", 1)
    st.players[1].permanents.add(source)
    before = st.combat.attack_power

    run_ability(get_card("step_between_red").abilities[0], source, None, st)

    assert st.combat.attack_power == before + 1


def test_step_between_no_longer_grants_ward():
    """A ward left on the source would keep silently preventing damage."""
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    raw = json.loads(_card_json(root, "step_between_red.json")
                     .read_text(encoding="utf-8"))
    assert "WARD" not in json.dumps(raw.get("abilities", []))


# --- DESTROY_ARSENAL whose-arsenal spelling ---------------------------------

def _arsenal(st, pid):
    c = _card(PLAIN, pid)
    st.players[pid].arsenal.add(c)
    return c


def test_destroy_arsenal_reads_target_as_the_player():
    st = _state()
    theirs = _arsenal(st, 2)

    compile_effect("DESTROY_ARSENAL", {"target": "opponent"})(
        _card(PLAIN, 1), None, st)

    assert theirs not in st.players[2].arsenal.cards


def test_destroy_arsenal_target_self_hits_your_own():
    """`target` was unread. It named the default on the only card using it, so
    it was harmless there — and a card writing "self" would have hit the
    OPPONENT instead, which is the inversion this closes."""
    st = _state()
    mine = _arsenal(st, 1)
    theirs = _arsenal(st, 2)

    compile_effect("DESTROY_ARSENAL", {"target": "self"})(
        _card(PLAIN, 1), None, st)

    assert mine not in st.players[1].arsenal.cards
    assert theirs in st.players[2].arsenal.cards, "it destroyed the wrong arsenal"


def test_smashing_ground_destroys_the_opposing_arsenal():
    st = _state()
    st.combat.hit = True
    st.combat.attack_power = 6
    theirs = _arsenal(st, 2)
    mine = _arsenal(st, 1)

    run_ability(get_card("smashing_ground_blue").abilities[0],
                _card("smashing_ground_blue", 1), None, st)

    assert theirs not in st.players[2].arsenal.cards
    assert mine in st.players[1].arsenal.cards, "it destroyed its own arsenal"
