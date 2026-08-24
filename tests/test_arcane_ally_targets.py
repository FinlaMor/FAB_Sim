"""Arcane damage could only ever reach a hero.

effect_deal_arcane resolves its player_id to that player's HERO and nothing
else. Two cards need it to reach an ALLY:

  singe_yellow  "Deal 1 arcane damage to target hero AND UP TO 2 TARGET ALLIES
                THEY CONTROL." target:"ally" is not "OPPONENT", so it fell
                through to the other branch and dealt the second point to the
                CONTROLLER'S OWN hero - an inversion, and free damage to
                yourself. max_targets was unread on top, so it was one point.
  azvolai       "up to any 2 targets" - any mix of heroes and allies on either
                side. The token had NO JSON FILE AT ALL, so transforming an ash
                into it raised MissingCardImplementation and aborted the game.

Routing through the deal_damage keyword with the ally as the target object is
what makes the CR 1.10.2b ally death check see the damage; a hero-only helper
never could.

TWO STORES FOR ONE FACT, AGAIN — and it makes every ally in the game immune to
every non-combat damage source. create_token and engine.py write an ally's
health to `current_life`; effect_keywords.deal_damage reads and writes `life`,
which is left None. Its CR 8.5.3c "non-living targets cannot be damaged" check
therefore CANCELS, so arcane and direct-damage effects bounce off allies while
COMBAT damage (engine.py, which uses current_life) lands normally.

Fixing that is an engine change, so the tests that need it are xfail(strict)
until it is agreed: they turn green the moment the fields are reconciled, and
strict makes the marker itself fail then, so nobody has to remember to remove
it.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.effect_types import compile_effect
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

HERO = "kayo_strong_arm"
OTHER_HERO = "gravy_bones"
PLAIN = "brutal_assault_red"
# A real Ally TOKEN with printed stats in token_meta.ALLY_TOKEN_STATS. A card
# with subtypes=['Ally'] but no life cannot show that damage landed.
ALLY = "aether_ashwing"


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
    st.players[1].hero = _card(HERO, 1)
    st.players[2].hero = _card(OTHER_HERO, 2)
    return st


def _ally(st, pid):
    from engine.effect_keywords import create_token
    before = {id(c) for c in st.players[pid].permanents.cards}
    create_token(st, target_player_id=pid, token_slug=ALLY, number=1,
                 source_player_id=pid)
    return next(c for c in st.players[pid].permanents.cards
                if c.slug == ALLY and id(c) not in before)


def _life(card):
    return getattr(card, "life", None)


# --- the ally target --------------------------------------------------------

@pytest.mark.xfail(strict=True, reason=(
    "engine: allies store health in current_life, deal_damage reads life, so "
    "CR 8.5.3c cancels all non-combat damage to allies"))
def test_an_ally_takes_the_arcane_damage():
    st = _state()
    ally = _ally(st, 2)
    before = _life(ally)
    assert before, "the fixture ally has no life to lose"

    compile_effect("DEAL_ARCANE", {"amount": 1, "target": "ally"})(
        _card(PLAIN, 1), None, st)

    assert _life(ally) == before - 1, f"ally life is {_life(ally)}"


def test_it_does_not_hit_the_controllers_own_hero():
    """target:"ally" fell through to the not-the-opponent branch."""
    st = _state()
    _ally(st, 2)
    mine = st.players[1].life

    compile_effect("DEAL_ARCANE", {"amount": 1, "target": "ally"})(
        _card(PLAIN, 1), None, st)

    assert st.players[1].life == mine, (
        "it dealt the damage to its own controller")


@pytest.mark.xfail(strict=True, reason=(
    "engine: allies store health in current_life, deal_damage reads life, so "
    "CR 8.5.3c cancels all non-combat damage to allies"))
def test_max_targets_lets_it_reach_two_allies():
    st = _state()
    a, b = _ally(st, 2), _ally(st, 2)

    compile_effect("DEAL_ARCANE", {"amount": 1, "target": "ally",
                                   "max_targets": 2})(_card(PLAIN, 1), None, st)

    assert (_life(a), _life(b)) == (0, 0), (
        f"only one ally was damaged: {_life(a)}, {_life(b)}")


@pytest.mark.xfail(strict=True, reason=(
    "engine: allies store health in current_life, deal_damage reads life, so "
    "CR 8.5.3c cancels all non-combat damage to allies"))
def test_without_max_targets_only_one_ally_is_hit():
    st = _state()
    a, b = _ally(st, 2), _ally(st, 2)

    compile_effect("DEAL_ARCANE", {"amount": 1, "target": "ally"})(
        _card(PLAIN, 1), None, st)

    assert [_life(a), _life(b)].count(0) == 1


def test_up_to_means_the_controller_may_take_fewer():
    from engine.card_effects.ability_keywords import NO  # noqa: F401
    st = _state(agent=lambda s, o, context="": "none" if "none" in o else o[0])
    ally = _ally(st, 2)
    before = _life(ally)

    compile_effect("DEAL_ARCANE", {"amount": 1, "target": "ally",
                                   "max_targets": 2})(_card(PLAIN, 1), None, st)

    assert _life(ally) == before, "declining still dealt the damage"


@pytest.mark.xfail(strict=True, reason=(
    "engine: allies store health in current_life, deal_damage reads life, so "
    "CR 8.5.3c cancels all non-combat damage to allies"))
def test_an_ally_at_zero_life_is_destroyed():
    """Routing through the damage keyword is what makes CR 1.10.2b see it."""
    st = _state()
    ally = _ally(st, 2)
    n = _life(ally)

    compile_effect("DEAL_ARCANE", {"amount": n, "target": "ally"})(
        _card(PLAIN, 1), None, st)
    E._check_ally_deaths(st) if hasattr(E, "_check_ally_deaths") else None

    assert _life(ally) <= 0


# --- singe_yellow -----------------------------------------------------------

def test_singe_hits_the_opposing_hero():
    st = _state()
    theirs = st.players[2].life

    run_ability(get_card("singe_yellow").abilities[0], _card("singe_yellow", 1),
                None, st)

    assert st.players[2].life == theirs - 1


@pytest.mark.xfail(strict=True, reason=(
    "engine: allies store health in current_life, deal_damage reads life, so "
    "CR 8.5.3c cancels all non-combat damage to allies"))
def test_singe_hits_their_allies_and_not_the_caster():
    st = _state()
    a, b = _ally(st, 2), _ally(st, 2)
    mine_hero = st.players[1].life
    mine_ally = _ally(st, 1)
    mine_ally_life = _life(mine_ally)

    run_ability(get_card("singe_yellow").abilities[0], _card("singe_yellow", 1),
                None, st)

    assert (_life(a), _life(b)) == (0, 0), (
        f"their allies took {_life(a)}, {_life(b)}")
    assert st.players[1].life == mine_hero, "it burned its own controller"
    assert _life(mine_ally) == mine_ally_life, "it burned its own ally"


# --- azvolai ----------------------------------------------------------------

def test_azvolai_has_an_implementation_at_all():
    assert get_card("azvolai") is not None


def test_azvolai_can_hit_a_hero_on_attack():
    st = _state()
    source = _card("azvolai", 1)
    st.players[1].permanents.add(source)
    st.player_agents = {p: (lambda s, o, context="": next(
        (x for x in o if x == "hero:2"), o[0])) for p in (1, 2)}
    theirs = st.players[2].life

    run_ability(get_card("azvolai").abilities[0], source, None, st)

    assert st.players[2].life == theirs - 1


@pytest.mark.xfail(strict=True, reason=(
    "engine: allies store health in current_life, deal_damage reads life, so "
    "CR 8.5.3c cancels all non-combat damage to allies"))
def test_azvolai_can_hit_an_ally():
    """"any 2 targets" is not "any 2 heroes"."""
    st = _state()
    source = _card("azvolai", 1)
    st.players[1].permanents.add(source)
    ally = _ally(st, 2)
    st.player_agents = {p: (lambda s, o, context="": next(
        (x for x in o if x == ALLY), o[0])) for p in (1, 2)}

    run_ability(get_card("azvolai").abilities[0], source, None, st)

    assert _life(ally) == 0
