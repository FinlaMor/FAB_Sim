""""self" is not a ref, so three cards resolved to nothing and did nothing.

The ref family (FLIP_REF, MOVE_REF, BANISH_REF, ...) resolves its object from a
NAMED REF that an earlier effect stored. Three cards instead wrote
`"target": "self"` for wordings whose object is the source card itself. A bare
string is not a canonical target dict, so the object lookup was skipped and the
ref fell back to its default -- "chosen" / "looked" -- which nothing had set:

  beneath_the_surface_yellow  "While this is DEFENDING, when it's put into your
                              graveyard from the arena, turn IT face-down." The
                              gate was IN_COMBAT + CONTROLS_ATTACK_ACTION, which
                              is a different question, plus a REF_EXISTS on the
                              same non-ref -- false in every state, so the
                              ability could never fire at all.
  invigorating_light_blue     "put IT into your hero's soul."
  patch_the_hole              "Destroy this: return a card from your ARSENAL to
                              your hand." RETURN_TO_HAND had no ref and no
                              target, so it fell through to "return THIS card":
                              it bounced the equipment it had just destroyed as
                              a cost and left the arsenal untouched. Strictly
                              better for the player than printed, and the
                              arsenal card -- the whole point -- never moved.

"self" is the natural word and appears throughout the corpus in other effects,
so it is recognised in the compiler rather than rewritten away in three cards.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.effect_types import compile_effect
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

PLAIN = "brutal_assault_red"
OTHER = "amplifying_arrow_yellow"


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


# --- the compiler-level spelling --------------------------------------------

@pytest.mark.parametrize("word", ["self", "this", "SELF", "source"])
def test_flip_ref_understands_self(word):
    st = _state()
    source = _card(PLAIN)
    source.is_public = True

    compile_effect("FLIP_REF", {"target": word, "face_up": False})(
        source, None, st)

    assert source.is_public is False


def test_flip_ref_still_needs_a_real_ref_for_anything_else():
    """Only "self" is reinterpreted; an unset ref must stay a no-op rather than
    guessing at the source card."""
    st = _state()
    source = _card(PLAIN)
    source.is_public = True

    compile_effect("FLIP_REF", {"ref": "nothing_set_this", "face_up": False})(
        source, None, st)

    assert source.is_public is True


def test_move_ref_understands_self():
    st = _state()
    source = _card(PLAIN)
    st.players[1].hand.add(source)

    compile_effect("MOVE_REF", {"target": "self", "to_zone": "soul"})(
        source, None, st)

    assert source in st.players[1].soul.cards, f"it is in {source.zone!r}"


# --- beneath_the_surface_yellow ---------------------------------------------

def _defending(st, card):
    st.combat = CombatState(attacker_id=2, link_id=1, attack_power=3,
                            attack_card=_card(PLAIN, 2), keywords=[])
    st.combat.defending_cards = [card]
    return st.combat


def test_it_turns_itself_face_down_while_defending():
    st = _state()
    source = _card("beneath_the_surface_yellow")
    source.is_public = True
    _defending(st, source)

    run_ability(get_card("beneath_the_surface_yellow").abilities[0],
                source, None, st)

    assert source.is_public is False, "it did not turn face down"


def test_it_does_nothing_when_it_is_not_defending():
    """"WHILE THIS IS DEFENDING" — the old gate asked whether the controller
    held an attack action, which is a different question."""
    st = _state()
    source = _card("beneath_the_surface_yellow")
    source.is_public = True
    _defending(st, _card(OTHER))          # something ELSE is defending

    run_ability(get_card("beneath_the_surface_yellow").abilities[0],
                source, None, st)

    assert source.is_public is True


def test_it_does_nothing_outside_combat():
    st = _state()
    source = _card("beneath_the_surface_yellow")
    source.is_public = True

    run_ability(get_card("beneath_the_surface_yellow").abilities[0],
                source, None, st)

    assert source.is_public is True


# --- invigorating_light_blue ------------------------------------------------

def test_it_puts_itself_into_the_soul():
    st = _state()
    source = _card("invigorating_light_blue")
    st.players[1].hand.add(source)

    run_ability(get_card("invigorating_light_blue").abilities[0],
                source, None, st)

    assert source in st.players[1].soul.cards, f"it is in {source.zone!r}"


def test_it_does_nothing_with_a_non_empty_soul():
    """"if there are NO cards in your hero's soul"."""
    st = _state()
    st.players[1].soul.add(_card(OTHER))
    source = _card("invigorating_light_blue")
    st.players[1].hand.add(source)

    run_ability(get_card("invigorating_light_blue").abilities[0],
                source, None, st)

    assert source not in st.players[1].soul.cards


# --- patch_the_hole ---------------------------------------------------------

def test_it_returns_the_arsenal_card():
    st = _state()
    source = _card("patch_the_hole")
    st.players[1].permanents.add(source)
    held = _card(OTHER)
    st.players[1].arsenal.add(held)

    run_ability(get_card("patch_the_hole").abilities[0], source, None, st)

    assert held in st.players[1].hand.cards, f"the arsenal card is in {held.zone!r}"
    assert held not in st.players[1].arsenal.cards


def test_it_does_not_bounce_itself():
    """With no ref and no target it returned THIS card — the equipment it had
    just destroyed as a cost."""
    st = _state()
    source = _card("patch_the_hole")
    st.players[1].permanents.add(source)
    st.players[1].arsenal.add(_card(OTHER))

    run_ability(get_card("patch_the_hole").abilities[0], source, None, st)

    assert source not in st.players[1].hand.cards, (
        "it returned itself to hand")


def test_an_empty_arsenal_returns_nothing():
    st = _state()
    source = _card("patch_the_hole")
    st.players[1].permanents.add(source)
    before = len(st.players[1].hand.cards)

    run_ability(get_card("patch_the_hole").abilities[0], source, None, st)

    assert len(st.players[1].hand.cards) == before


def test_inflame_still_returns_the_card_its_target_names():
    """inflame_red authors BOTH a zone and a target dict. The target names one
    specific card and must keep precedence over the zone fallback."""
    st = _state()
    # "if you've played 2 or more red cards this turn" — inflame's own gate,
    # which this test is not about but must satisfy to reach the effect.
    from engine.effect_keywords import _record_turn_event
    for _ in range(2):
        _record_turn_event(st, 1, "play", "red")
    phoenix = _card("phoenix_flame_red")
    st.players[1].graveyard.add(phoenix)
    other = _card(OTHER)
    st.players[1].graveyard.add(other)

    run_ability(get_card("inflame_red").abilities[0], _card("inflame_red"),
                None, st)

    assert phoenix in st.players[1].hand.cards, (
        f"phoenix flame is in {phoenix.zone!r}")
    assert other in st.players[1].graveyard.cards, "it returned the wrong card"
