"""Humble: "they lose all hero card abilities until the end of their next turn."

All three printings were inert, in three different ways at once, and each way
would have been enough on its own:

    humble_red     SET_FLAG HUMBLE_ACTIVE
    humble_yellow  SET_FLAG HUMBLE_ACTIVE
    humble_blue    SET_FLAG HERO_ABILITIES_DISABLED, duration END_OF_TURN

Nothing read either flag name, so nothing happened. Both names were set on the
CONTROLLER rather than on the hero that was hit -- so had anything read them,
the card would have disabled its own player's hero. And blue's duration stopped
at the end of the turn it was played, not the end of the victim's next turn.

Two printings of the same sentence disagreeing about the flag's NAME is the tell
for this whole class: a flag with no reader has no correct spelling, so each
author invented one, and nobody could notice.

WHAT THE TESTS HAVE TO DRIVE. "All hero card abilities" is one phrase over FOUR
separate code paths, and a guard on one is invisible on the others:

    offered        play.available_actions -> _add_hero_dsl_activations
                   (and actions.py's ACTIVATE_HERO, the audit-only mirror)
    fired          dsl.dispatch -> interpreter.dispatch_event
    cost deltas    play._hero_activation_cost_delta, which reads the hero's DSL
                   abilities DIRECTLY and never touches dispatch_event
    replacements   state.clash_fail_retry, registered ONCE at game start, so no
                   registration-time check can ever see a later Humble

Only the first two were obvious. The other two were found by asking what else
reads a hero's abilities, and each needed its own check -- the cost one is the
easiest to miss because it changes a NUMBER rather than whether something
happens, so nothing looks broken.

The tests below therefore go through those paths, and NOT through run_ability,
which bypasses dispatch_event entirely and would pass against a guard that does
nothing. That is not a hypothetical: a fix earlier in this project was verified
with recalculate_attack on a card that never takes the attack path, and the card
was still broken afterwards.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card_effects.dsl import dispatch
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.card_effects.dsl.interpreter import run_ability
from engine.effect_keywords import hero_abilities_are_disabled
from engine.card import CardDB
from engine.play import available_actions
from tests.conftest import _make_state, owned_card, tokens_controlled

load_all_cards()
DB = CardDB()

HUMBLES = ["humble_red", "humble_blue", "humble_yellow"]


def _state():
    """A state that can create tokens: CREATE_TOKEN reads state.card_db, and
    _make_state leaves it None."""
    st = _make_state()
    st.card_db = DB
    return st


def _hero(state, pid, slug):
    """Give a player a real hero card with real DSL abilities."""
    from engine.card import Card
    hero = Card(slug=slug, name=slug, raw_types=["Hero"], raw_life=40,
                raw_intellect=4)
    hero.owner = hero.controller = pid
    hero.life = 40
    state.players[pid].hero = hero
    return hero


def _land_humble(state, slug, controller=1):
    """Fire the card's own ON_HIT ability, the way a hit does."""
    card = owned_card(controller, slug)
    ability = get_card(slug).abilities[0]
    # The ability is gated on ATTACK_TARGET_IS_HERO; drive it through the same
    # entry point the engine uses so the condition sees a real combat.
    from tests.conftest import _make_combat
    state.combat = _make_combat(attacker_id=controller, attack_card=card)
    # ATTACK_TARGET_IS_HERO is true when attack_target is None: the field names
    # a permanent or ally that was attacked INSTEAD of the hero. _make_combat
    # helpfully fills in the defending hero, which reads as "attacked a
    # permanent" and makes every Humble look like it does nothing.
    state.combat.attack_target = None
    run_ability(ability, card, None, state)


# --- the effect exists at all ------------------------------------------------

@pytest.mark.parametrize("slug", HUMBLES)
def test_hero_activated_ability_is_no_longer_offered(slug):
    """maxx_nitro's ability is an ACTIVATE with a cost, so it shows up in
    available_actions until the hero stops having abilities."""
    st = _state()
    _hero(st, 2, "maxx_nitro")
    st.players[2].current_turn_effects.append("boosted_this_turn")
    st.players[2].resources = 5
    st.players[2].action_points = 1
    st.active_player = 2

    before = [a for a in available_actions(st, 2)
              if getattr(a.card, "slug", None) == "maxx_nitro"]
    assert before, "fixture is wrong: the hero ability was never offered"

    st.active_player = 1
    _land_humble(st, slug)
    st.active_player = 2

    after = [a for a in available_actions(st, 2)
             if getattr(a.card, "slug", None) == "maxx_nitro"]
    assert not after, (
        "%s left the hero's activated ability on offer; a hero that has lost "
        "its abilities has none to activate" % slug)


@pytest.mark.parametrize("slug", HUMBLES)
def test_hero_triggered_ability_no_longer_fires(slug):
    """briar's ON_CARD_PLAYED trigger creates a token -- an observable outcome,
    not a flag. Driven through dsl.dispatch, which is the engine's real path."""
    st = _state()
    _hero(st, 2, "briar")
    from engine.effect_keywords import _record_turn_event
    for _ in range(2):
        _record_turn_event(st, 2, "play", "non_attack_action")

    dispatch(st, "ON_CARD_PLAYED", "briar", card=st.players[2].hero, event=None)
    assert tokens_controlled(st, 2, "lightning"), (
        "fixture is wrong: the hero trigger never fired to begin with")

    st2 = _state()
    _hero(st2, 2, "briar")
    for _ in range(2):
        _record_turn_event(st2, 2, "play", "non_attack_action")
    _land_humble(st2, slug)

    dispatch(st2, "ON_CARD_PLAYED", "briar", card=st2.players[2].hero, event=None)
    assert not tokens_controlled(st2, 2, "lightning"), (
        "%s let the hero's triggered ability fire; the ability no longer "
        "exists and cannot trigger" % slug)


# --- the two things every printing got wrong ---------------------------------

@pytest.mark.parametrize("slug", HUMBLES)
def test_it_disables_the_hero_that_was_hit_not_the_controller(slug):
    """Every printing named no player and fell back to the controller, so the
    card that hits YOUR opponent would have switched off YOUR hero."""
    st = _state()
    _hero(st, 1, "maxx_nitro")
    _hero(st, 2, "maxx_nitro")
    _land_humble(st, slug, controller=1)

    assert hero_abilities_are_disabled(st, 2), (
        "%s did not disable the hero it hit" % slug)
    assert not hero_abilities_are_disabled(st, 1), (
        "%s disabled its OWN controller's hero" % slug)


@pytest.mark.parametrize("slug", HUMBLES)
def test_it_lasts_through_the_victims_next_turn(slug):
    """"until the end of THEIR next turn" -- the card is played on the
    controller's turn, so the restriction has to survive the turn rotation that
    follows. humble_blue asked for END_OF_TURN, which expires before the victim
    has had a turn at all, making it a strictly weaker card than printed."""
    st = _state()
    _hero(st, 2, "maxx_nitro")
    _land_humble(st, slug, controller=1)
    assert hero_abilities_are_disabled(st, 2), "not disabled immediately"

    # The victim's turn begins: next_turn_effects rotate into current.
    p2 = st.players[2]
    p2.current_turn_effects = p2.next_turn_effects[:]
    p2.next_turn_effects = []
    assert hero_abilities_are_disabled(st, 2), (
        "%s expired before the victim's next turn began" % slug)

    # ...and ends.
    p2.current_turn_effects = []
    assert not hero_abilities_are_disabled(st, 2), (
        "%s outlived the end of the victim's next turn" % slug)


def test_a_hero_cost_modifier_stops_applying():
    """COST_MODIFIER abilities are read straight off the hero's DSL def by
    play._hero_activation_cost_delta -- not through dispatch_event -- so the
    guard there does not reach them. Three paths read a hero's abilities and
    each needed finding separately; this is the one that is easiest to miss
    because it changes a NUMBER rather than whether something happens."""
    st = _state()
    _hero(st, 2, "arakni_orb_weaver")
    from engine.play import _hero_activation_cost_delta
    from engine.card_effects.dsl.loader import get_card as _gc
    cd = _gc("arakni_orb_weaver")
    assert cd is not None and any(a.ability_type.upper() == "COST_MODIFIER"
                                  for a in cd.abilities), (
        "fixture: arakni_orb_weaver is the corpus's only COST_MODIFIER hero; "
        "if it lost that ability this test needs a new subject, not a skip")
    target = owned_card(2, "graphene_chelicera")
    before = _hero_activation_cost_delta(st, 2, target)
    assert before != 0, "fixture: the hero was not modifying the cost anyway"

    _land_humble(st, "humble_red")
    assert _hero_activation_cost_delta(st, 2, target) == 0, (
        "the hero kept modifying activation costs after losing its abilities")


def test_a_hero_clash_replacement_stops_applying():
    """Hero REPLACEMENT abilities are registered ONCE at game start into
    state.clash_fail_retry, so the registration cannot know about a hero that
    loses its abilities later in the game. The check has to live at the point of
    use."""
    st = _state()
    _hero(st, 2, "victor_goldmane_high_and_mighty")
    st.clash_fail_retry = {2: "fail_clash_retry"}

    from engine.effect_keywords import hero_abilities_are_disabled
    assert not hero_abilities_are_disabled(st, 2)
    _land_humble(st, "humble_red")
    assert hero_abilities_are_disabled(st, 2), (
        "the clash replacement would still be consulted")


def test_a_hero_with_abilities_intact_is_unaffected():
    """The guard must key on the marker, not on being a hero."""
    st = _state()
    _hero(st, 2, "briar")
    from engine.effect_keywords import _record_turn_event
    for _ in range(2):
        _record_turn_event(st, 2, "play", "non_attack_action")
    dispatch(st, "ON_CARD_PLAYED", "briar", card=st.players[2].hero, event=None)
    assert tokens_controlled(st, 2, "lightning")


def test_only_the_hero_card_loses_abilities():
    """"hero card abilities" is the hero card's own abilities. A permanent the
    player controls keeps working -- the marker is on the player, so a guard
    that read it without checking WHICH card would silence the whole board."""
    st = _state()
    _hero(st, 2, "briar")
    _land_humble(st, "humble_red", controller=1)

    other = owned_card(2, "briar")          # same def, NOT the hero object
    st.players[2].permanents.add(other)
    from engine.effect_keywords import _record_turn_event
    for _ in range(2):
        _record_turn_event(st, 2, "play", "non_attack_action")
    dispatch(st, "ON_CARD_PLAYED", "briar", card=other, event=None)
    assert tokens_controlled(st, 2, "lightning"), (
        "a non-hero permanent lost its abilities too")
