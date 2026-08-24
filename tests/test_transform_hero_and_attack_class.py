"""A hero transform that was really a permanent transform, and a gate that
asked about the wrong player.

TRANSFORM_HERO is Arakni's "you become a random Agent of Chaos". It reads
`mode` and nothing else. Two cards put the form in `target`:

  arakni_web_of_deceit  named the default, so it was right BY ACCIDENT.
  invoke_azvolai_red    "Transform target ash you control into Azvolai" - a
                        PERMANENT transform. Unread, the ash was left alone and
                        the CONTROLLER'S HERO became an Agent of Chaos instead.
                        Not a no-op: a strictly different, game-losing board.

That is the fourth card to author the hero effect when it meant TRANSFORM, so
an unrecognised mode now RAISES at load rather than defaulting - a load failure
names the card, a silent default does not.

CONTROLS_ATTACK_ACTION had two unread parameters that failed in opposite
directions:

  opponent      leap_frog_vocal_sac asks about the OPPONENT's attack; looking
                at your own inverted the gate.
  attack_class  scorpio_comet_tail activates "only if you control a LIGHTNING
                attack"; unfiltered, ANY attack let it activate. Lightning is a
                TALENT, not a class - the same trap as Mystic - which is why the
                filter matches classes, talents and colour alike.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.condition_types import compile_condition
from engine.card_effects.dsl.effect_types import compile_effect
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

# Lightning is a TALENT: astral_strike_red is classes=['NotClassed'],
# talents=['Lightning']. A class-only reading would never match it.
LIGHTNING_ATTACK = "astral_strike_red"
PLAIN_ATTACK = "brutal_assault_red"


def _card(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _state(agent=None):
    st = _make_state()
    st.card_db = DB
    pick = agent or (lambda s, o, context="": o[0])
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    st.individual_turns = 1
    return st


# --- invoke_azvolai_red -----------------------------------------------------

def _ash(st, pid=1):
    from engine.effect_keywords import create_token
    create_token(st, target_player_id=pid, token_slug="ash", number=1,
                 source_player_id=pid)
    return next(c for c in st.players[pid].permanents.cards if c.slug == "ash")


def test_the_ash_becomes_an_azvolai():
    st = _state()
    _ash(st)

    run_ability(get_card("invoke_azvolai_red").abilities[0],
                _card("invoke_azvolai_red"), None, st)

    slugs = [c.slug for c in st.players[1].permanents.cards]
    assert "azvolai" in slugs, f"permanents are {slugs}"


def test_it_leaves_the_hero_alone():
    """It transformed the HERO into an Agent of Chaos and left the ash sitting
    there."""
    st = _state()
    hero = _card("kayo_strong_arm", 1)
    st.players[1].hero = hero
    was = hero.slug
    _ash(st)

    run_ability(get_card("invoke_azvolai_red").abilities[0],
                _card("invoke_azvolai_red"), None, st)

    assert st.players[1].hero.slug == was, (
        f"the hero became {st.players[1].hero.slug}")


def test_with_no_ash_nothing_is_transformed():
    """'TARGET ash' is not 'up to any number of ash'."""
    st = _state()
    hero = _card("kayo_strong_arm", 1)
    st.players[1].hero = hero
    st.players[1].permanents.add(_card(PLAIN_ATTACK))

    run_ability(get_card("invoke_azvolai_red").abilities[0],
                _card("invoke_azvolai_red"), None, st)

    slugs = [c.slug for c in st.players[1].permanents.cards]
    assert "azvolai" not in slugs, f"it invented one out of {slugs}"
    assert st.players[1].hero.slug == hero.slug


# --- the load gate ----------------------------------------------------------

def test_a_mode_that_is_not_a_hero_form_is_refused():
    with pytest.raises(ValueError) as excinfo:
        compile_effect("TRANSFORM_HERO", {"target": "Ash"})
    assert "TRANSFORM" in str(excinfo.value), str(excinfo.value)


@pytest.mark.parametrize("key", ["mode", "target", "form"])
def test_the_form_is_read_from_any_of_its_spellings(key):
    st = _state()
    st.players[1].hero = _card("arakni_marionette", 1)

    compile_effect("TRANSFORM_HERO", {key: "random_agent_of_chaos"})(
        _card(PLAIN_ATTACK), None, st)

    assert st.players[1].hero.slug != "arakni_marionette", (
        "the hero did not transform")


def test_web_of_deceit_becomes_an_agent_of_chaos_at_end_of_turn():
    st = _state()
    st.players[1].hero = _card("arakni_marionette", 1)
    source = st.players[1].hero
    compile_effect("MARK", {})(_card(PLAIN_ATTACK), None, st)

    run_ability(get_card("arakni_web_of_deceit").abilities[2], source, None, st)

    assert st.players[1].hero.slug != "arakni_marionette"


def test_web_of_deceit_does_not_transform_with_nobody_marked():
    st = _state()
    st.players[1].hero = _card("arakni_marionette", 1)
    source = st.players[1].hero

    run_ability(get_card("arakni_web_of_deceit").abilities[2], source, None, st)

    assert st.players[1].hero.slug == "arakni_marionette"


# --- CONTROLS_ATTACK_ACTION -------------------------------------------------

def _attacking(st, slug, attacker):
    ac = _card(slug, attacker)
    st.combat = CombatState(attacker_id=attacker, link_id=1, attack_power=3,
                            attack_card=ac, keywords=[])
    return ac


def test_the_opponent_form_asks_about_the_opponents_attack():
    st = _state()
    _attacking(st, PLAIN_ATTACK, attacker=2)
    fn = compile_condition("CONTROLS_ATTACK_ACTION", {"opponent": True})

    assert fn(_card(PLAIN_ATTACK, 1), None, st) is True


def test_the_opponent_form_is_false_when_YOU_are_the_attacker():
    st = _state()
    _attacking(st, PLAIN_ATTACK, attacker=1)
    fn = compile_condition("CONTROLS_ATTACK_ACTION", {"opponent": True})

    assert fn(_card(PLAIN_ATTACK, 1), None, st) is False, (
        "it answered about the controller's own attack")


def test_the_plain_form_still_asks_about_the_controller():
    st = _state()
    _attacking(st, PLAIN_ATTACK, attacker=1)
    fn = compile_condition("CONTROLS_ATTACK_ACTION", {})

    assert fn(_card(PLAIN_ATTACK, 1), None, st) is True


def test_a_class_filter_rejects_an_attack_of_another_class():
    st = _state()
    _attacking(st, PLAIN_ATTACK, attacker=1)
    fn = compile_condition("CONTROLS_ATTACK_ACTION", {"attack_class": "Lightning"})

    assert fn(_card("scorpio_comet_tail", 1), None, st) is False, (
        "any attack at all satisfied 'a Lightning attack'")


def test_a_class_filter_accepts_the_named_talent():
    st = _state()
    _attacking(st, LIGHTNING_ATTACK, attacker=1)
    assert "Lightning" in (DB.get(LIGHTNING_ATTACK).talents or [])
    assert "Lightning" not in (DB.get(LIGHTNING_ATTACK).classes or []), (
        "the fixture no longer proves the talent path")
    fn = compile_condition("CONTROLS_ATTACK_ACTION", {"attack_class": "Lightning"})

    assert fn(_card("scorpio_comet_tail", 1), None, st) is True
