"""The four engine changes behind the last five "next X" cards.

Each was needed because the card could not be written at all, not because the
existing primitive was applied wrongly:

  granted abilities   the queues carried keywords, power and classes — all
                      VALUES. "The next attack action card you play GAINS
                      '<ability>'" needs the ability itself, attached to one
                      card. An injected turn-scoped trigger would fire for every
                      attack that turn instead.
  play-time amounts   "costs {r} less FOR EACH RUNECHANT YOU CONTROL" must count
                      when the card is PLAYED; the queue resolved its amount when
                      the entry was created, freezing an already-stale number.
  power-gain hook     "the next time an attack would GAIN {p}, instead it gains
                      that much plus 2" needs a point between deciding the amount
                      and applying it. There were two such points and nothing
                      between either.
  unpreventable       the flag existed and was honoured, but nothing set it AND
                      it was read once BEFORE the replacement loop — so a
                      STANDARD replacement setting it mid-loop was ignored by the
                      only stage that consults it.
"""
import copy

import pytest

import engine.engine as E
from engine.actions import Action, ActionType
from engine.card import Card, CardDB
from engine.card_effects.dsl import dispatch
from engine.card_effects.dsl.loader import load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()


def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    return st


def _card(slug, owner=1):
    base = DB.get(slug)
    assert base is not None, f"unknown slug {slug}"
    c = copy.deepcopy(base)
    c.owner = c.controller = owner
    return c


def _play(st, card, pid=1):
    import engine.play as P
    card.owner = card.controller = pid
    st.players[pid].hand.add(card)
    P._pay_costs(st, pid, Action(ActionType.PLAY_CARD, pid, card))
    return card


def _attack_card(pid=1, power=3, slug="atk", is_attack=True):
    c = Card(slug=slug, name=slug, types=["Action"],
             subtypes=["Attack"] if is_attack else [])
    c.owner = c.controller = pid
    c.power = c.base_power = power
    # BOTH: _get_base_resource_cost reads card.cost, while playability reads
    # raw_cost. Setting only one makes the cost path see 0.
    c.raw_cost = c.cost = 3
    return c


def _make_attack(st, card, pid=1):
    st.combat = CombatState(attacker_id=pid, link_id=1,
                            attack_power=card.base_power or 0,
                            attack_card=card, keywords=[])
    st.combat.base_attack_power = card.base_power or 0
    E._apply_turn_attack_effects(st, card)
    E._register_card_continuous_effects(st, card)
    E._recalculate_attack_power(st)
    return st.combat.attack_power


# --- granted abilities -----------------------------------------------------

def test_bramble_spark_grants_an_ability_to_the_next_attack():
    st = _state()
    dispatch(st, "ON_PLAY", "bramble_spark_blue",
             card=_card("bramble_spark_blue"), event=None)
    target = _play(st, _attack_card())
    assert target.granted_abilities, "no ability was attached to the played card"
    before = st.players[2].life
    dispatch(st, "ON_ATTACK", target.slug, card=target, event=None)
    assert before - st.players[2].life == 1, \
        "the granted 'deal 1 arcane damage' did not fire"


def test_the_grant_goes_to_one_card_only():
    st = _state()
    dispatch(st, "ON_PLAY", "bramble_spark_blue",
             card=_card("bramble_spark_blue"), event=None)
    first = _play(st, _attack_card(slug="first"))
    second = _play(st, _attack_card(slug="second"))
    assert first.granted_abilities
    assert not second.granted_abilities, \
        "every attack was granted the ability, not the next one"


def test_a_granted_ability_does_not_affect_other_copies():
    # The grant is on the INSTANCE. A different copy of the same card must be
    # untouched, or the grant has leaked into the definition.
    st = _state()
    dispatch(st, "ON_PLAY", "bramble_spark_blue",
             card=_card("bramble_spark_blue"), event=None)
    granted = _play(st, _attack_card(slug="shared"))
    other = _attack_card(slug="shared")
    assert granted.granted_abilities
    assert not other.granted_abilities


def test_a_granted_ability_does_not_survive_a_reset():
    # CR 3.0.9 — a card leaving the arena becomes a NEW object, so the grant
    # must not follow it back.
    st = _state()
    dispatch(st, "ON_PLAY", "bramble_spark_blue",
             card=_card("bramble_spark_blue"), event=None)
    target = _play(st, _attack_card())
    assert target.granted_abilities
    target.reset_to_base_state()
    assert not target.granted_abilities


# --- play-time cost resolution --------------------------------------------

def _runechants(st, n, pid=1):
    for _ in range(n):
        t = Card(slug="runechant", name="Runechant", types=["Token"],
                 subtypes=["Aura"])
        t.owner = t.controller = pid
        st.players[pid].permanents.add(t)


def test_bloodsheath_counts_runechants_when_the_card_is_played():
    # The reduction is "for each Runechant you control" AT PLAY TIME. Resolving
    # it when the entry was queued freezes a number that is already stale.
    import engine.play as P
    st = _state()
    skeleta = _card("bloodsheath_skeleta")
    st.players[1].permanents.add(skeleta)
    dispatch(st, "ON_ACTIVATE", skeleta.slug, card=skeleta, event=None)
    _runechants(st, 2)          # created AFTER the entry was queued
    target = _attack_card()
    target.raw_cost = target.cost = 5
    st.players[1].hand.add(target)
    action = Action(ActionType.PLAY_CARD, 1, target)
    cost = P._calculate_resource_cost(st, action)
    assert cost == 3, f"expected 5 - 2 Runechants = 3, got {cost}"


def test_bloodsheath_reduction_is_zero_with_no_runechants():
    import engine.play as P
    st = _state()
    skeleta = _card("bloodsheath_skeleta")
    st.players[1].permanents.add(skeleta)
    dispatch(st, "ON_ACTIVATE", skeleta.slug, card=skeleta, event=None)
    target = _attack_card()
    target.raw_cost = target.cost = 5
    st.players[1].hand.add(target)
    assert P._calculate_resource_cost(st, Action(ActionType.PLAY_CARD, 1, target)) == 5


# --- the power-gain choke point -------------------------------------------

def test_flourish_amplifies_a_gain_from_modify_attack():
    st = _state()
    dispatch(st, "ON_PLAY", "flourish_blue", card=_card("flourish_blue"), event=None)
    atk = _attack_card(power=3)
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=atk, keywords=[])
    st.combat.base_attack_power = 3
    from engine.card_effects.dsl.effect_types import compile_effect
    compile_effect("MODIFY_ATTACK", {"mod": "add", "amount": 1})(atk, None, st)
    E._recalculate_attack_power(st)
    assert st.combat.attack_power == 6, "gain of 1 should have become 3 (1 + 2)"


def test_flourish_amplifies_a_gain_from_the_queue():
    # The OTHER power-gain path. Two call sites is the "hook every call site"
    # shape, so both must go through the choke point — a gain that arrives via
    # the queue must not dodge the replacement.
    st = _state()
    dispatch(st, "ON_PLAY", "flourish_blue", card=_card("flourish_blue"), event=None)
    from engine.card_effects.dsl.effect_types import compile_effect
    compile_effect("MODIFY_NEXT_ATTACK", {"mod": "add", "amount": 1})(
        _card("flourish_blue"), None, st)
    assert _make_attack(st, _attack_card(power=3)) == 6


def test_flourish_applies_once():
    st = _state()
    dispatch(st, "ON_PLAY", "flourish_blue", card=_card("flourish_blue"), event=None)
    # One gain per attack, so the two are separated: SEVERAL queued mods all
    # apply to a single attack, which would confuse "once" with "once per
    # attack" and pass for the wrong reason.
    from engine.card_effects.dsl.effect_types import compile_effect
    compile_effect("MODIFY_NEXT_ATTACK", {"mod": "add", "amount": 1})(
        _card("flourish_blue"), None, st)
    assert _make_attack(st, _attack_card(power=3, slug="one")) == 6
    compile_effect("MODIFY_NEXT_ATTACK", {"mod": "add", "amount": 1})(
        _card("flourish_blue"), None, st)
    assert _make_attack(st, _attack_card(power=3, slug="two")) == 4, \
        "the replacement fired a second time"


def test_flourish_does_not_amplify_a_set():
    # "Would GAIN {p}". Setting power is not gaining it.
    st = _state()
    dispatch(st, "ON_PLAY", "flourish_blue", card=_card("flourish_blue"), event=None)
    atk = _attack_card(power=3)
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=atk, keywords=[])
    st.combat.base_attack_power = 3
    from engine.card_effects.dsl.effect_types import compile_effect
    compile_effect("MODIFY_ATTACK", {"mod": "set", "amount": 7})(atk, None, st)
    assert st.combat.attack_power == 7


# --- unpreventable ---------------------------------------------------------

def _runechant_damage(st, amount=1, pid=1):
    from engine.effect_keywords import DamageType, deal_damage
    src = Card(slug="runechant", name="Runechant", types=["Token"])
    src.owner = src.controller = pid
    before = st.players[3 - pid].life
    deal_damage(st, amount=amount, damage_type=DamageType.ARCANE,
                source_player_id=pid, damage_target=st.players[3 - pid].hero,
                damage_source="effect", damage_source_card=src)
    return before - st.players[3 - pid].life


def test_a_shield_normally_stops_runechant_damage():
    # The control: without the mark, prevention works.
    st = _state()
    from engine.card_effects.dsl.effect_types import compile_effect
    compile_effect("PREVENT_DAMAGE", {"amount": 5})(
        _card("flourish_blue", owner=2), None, st)
    assert _runechant_damage(st, 3) == 0


def test_marked_runechant_damage_cannot_be_prevented():
    # The flag existed and effects.py honoured it, but it was read ONCE before
    # the replacement loop — so a STANDARD replacement setting it mid-loop was
    # ignored by the only stage that reads it.
    st = _state()
    from engine.card_effects.dsl.effect_types import compile_effect
    compile_effect("MAKE_NEXT_DAMAGE_UNPREVENTABLE",
                   {"source_slug": "runechant"})(_card("flourish_blue"), None, st)
    compile_effect("PREVENT_DAMAGE", {"amount": 5})(
        _card("flourish_blue", owner=2), None, st)
    assert _runechant_damage(st, 3) == 3, \
        "the shield prevented damage that was marked unpreventable"


def test_the_mark_applies_to_one_damage_event_only():
    st = _state()
    from engine.card_effects.dsl.effect_types import compile_effect
    compile_effect("MAKE_NEXT_DAMAGE_UNPREVENTABLE",
                   {"source_slug": "runechant"})(_card("flourish_blue"), None, st)
    assert _runechant_damage(st, 3) == 3
    compile_effect("PREVENT_DAMAGE", {"amount": 5})(
        _card("flourish_blue", owner=2), None, st)
    assert _runechant_damage(st, 3) == 0, "the mark applied a second time"


def test_the_mark_only_covers_the_named_source():
    st = _state()
    from engine.card_effects.dsl.effect_types import compile_effect
    from engine.effect_keywords import DamageType, deal_damage
    compile_effect("MAKE_NEXT_DAMAGE_UNPREVENTABLE",
                   {"source_slug": "runechant"})(_card("flourish_blue"), None, st)
    compile_effect("PREVENT_DAMAGE", {"amount": 5})(
        _card("flourish_blue", owner=2), None, st)
    other = Card(slug="something_else", name="x", types=["Action"])
    other.owner = other.controller = 1
    before = st.players[2].life
    deal_damage(st, amount=3, damage_type=DamageType.ARCANE, source_player_id=1,
                damage_target=st.players[2].hero, damage_source="effect",
                damage_source_card=other)
    assert before - st.players[2].life == 0, \
        "damage from an unnamed source was made unpreventable"
