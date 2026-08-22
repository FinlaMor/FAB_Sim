""""When this hits a Pirate hero" was asking about the wrong card.

walk_the_plank_blue reads "When this hits a Pirate hero, {t} them or an ally
they control." Both halves named something other than what the card says.

The gate was ATTACK_CLASS_IN ["pirate"], which asks whether the ATTACK CARD is
a Pirate card. Walk the Plank *is* a Pirate attack, so that gate was true no
matter who it hit — the class of the hero being hit was never checked. The
class of the hero on the receiving end is TARGET_HERO_CLASS_IN.

The effect was TAP_REF over a ref named "ATTACKER" that nothing anywhere
stores, so it tapped nothing at all. "Them or an ally they control" is a choice
between objects, which no fixed target string names, so TAP now accepts the
canonical object-target spec the other targeting effects take.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.condition_types import compile_condition
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

SOURCE = "walk_the_plank_blue"
PIRATE = "gravy_bones"
NOT_PIRATE = "arakni_huntsman"
ALLY = "aether_ashwing"


def _card(slug, pid):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _state(defending_hero=PIRATE):
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    hero = _card(defending_hero, 2)
    st.players[2].hero = hero
    attack = _card(SOURCE, 1)
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=1,
                            attack_card=attack, keywords=[])
    return st, attack


def _run(st, source):
    run_ability(get_card(SOURCE).abilities[0], source, None, st)


def test_it_taps_the_pirate_hero_it_hit():
    st, source = _state()
    assert st.players[2].hero.tapped is False

    _run(st, source)

    assert st.players[2].hero.tapped is True, "the Pirate hero was not tapped"


def test_it_does_nothing_to_a_hero_that_is_not_a_pirate():
    """The old gate read the attack's class, and the attack is always a Pirate
    card — so this case was indistinguishable from the one above."""
    st, source = _state(defending_hero=NOT_PIRATE)

    _run(st, source)

    assert st.players[2].hero.tapped is False, (
        "it tapped a hero that is not a Pirate")


def test_the_gate_reads_the_defending_hero_not_the_attack_card():
    """Directly: the attack card is a Pirate card in both scenarios."""
    fn = compile_condition("TARGET_HERO_CLASS_IN", {"classes": ["Pirate"]})
    pirate_st, _ = _state()
    other_st, _ = _state(defending_hero=NOT_PIRATE)

    assert fn(None, None, pirate_st) is True
    assert fn(None, None, other_st) is False

    old = compile_condition("ATTACK_CLASS_IN", {"classes": ["pirate"]})
    assert old(None, None, pirate_st) == old(None, None, other_st), (
        "the old gate was supposed to be blind to the defending hero")


def test_it_can_tap_an_ally_instead_of_the_hero():
    """"them OR an ally they control" — the ally has to be a legal choice."""
    st, source = _state()
    ally = _card(ALLY, 2)
    st.players[2].permanents.add(ally)
    # The object chooser offers SLUGS, not Card objects — a lambda comparing
    # against the Card would silently never match and fall through to o[0].
    st.player_agents[1] = lambda s, o, context="", _s=ally.slug: (
        _s if _s in o else o[0])

    _run(st, source)

    assert ally.tapped is True, "the ally was not a choosable target"
    assert st.players[2].hero.tapped is False, "it tapped the hero as well"


def test_it_does_not_reach_the_attackers_own_board():
    st, source = _state()
    mine = _card(ALLY, 1)
    st.players[1].permanents.add(mine)

    _run(st, source)

    assert mine.tapped is False, "it tapped the attacking player's own ally"
