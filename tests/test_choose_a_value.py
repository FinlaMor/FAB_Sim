""""Choose a color" and "name a card" are not the same thing as CHOOSE.

CHOOSE picks between EFFECT OPTIONS. Two cards used it to mean "pick an
abstract VALUE and remember it", and with no `options` list the handler returns
immediately - so neither card did anything at all:

  become_the_cup_yellow     "as you play this, choose a color. This gets the
                            chosen color." Followed by GRANT_SUBTYPE "YELLOW":
                            a colour is not a subtype, and hard-coding yellow is
                            not a choice.
  blessing_of_themis_yellow "name a card. Turn all cards with that name in
                            banished zones face-down." The flip was a second
                            ability whose FLIP_REF and REF_EXISTS both named a
                            ref no effect on the card sets, so it was gated on
                            nothing and acted on nothing.

A reference scope lasts ONE ability execution, and "name a card" is read by a
LATER ability on the same permanent, so the choice is also stamped on the
object.

vow_of_vengeance is the same shape on the other side: "MARK TARGET ARAKNI" put
the hero in a `target` string MARK does not read, so it marked whoever was
opposite, Arakni or not.
"""
import copy

import pytest

import engine.engine as E
from engine.card import Card, CardDB
from engine.card_effects.dsl.effect_types import compile_effect
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
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


def _pick(value):
    return lambda s, o, context="": value if value in o else o[0]


# --- choosing a colour ------------------------------------------------------

def test_the_card_gets_the_colour_that_was_chosen():
    st = _state(agent=_pick("blue"))
    card = _card("become_the_cup_yellow")
    assert card.base_color == "Yellow"

    run_ability(get_card("become_the_cup_yellow").abilities[0], card, None, st)

    assert card.color == "Blue", (
        f"it is {card.color!r}; the choice was not applied")


def test_a_different_choice_gives_a_different_colour():
    """Pinning that this is a CHOICE and not a hard-coded colour."""
    st = _state(agent=_pick("red"))
    card = _card("become_the_cup_yellow")

    run_ability(get_card("become_the_cup_yellow").abilities[0], card, None, st)

    assert card.color == "Red"


def test_colour_conditions_see_the_chosen_colour():
    """Setting .color is only meaningful if the corpus's colour tests read it -
    they read `color` first, then base_color."""
    from engine.card_effects.dsl.condition_types import compile_condition

    st = _state(agent=_pick("blue"))
    card = _card("become_the_cup_yellow")
    run_ability(get_card("become_the_cup_yellow").abilities[0], card, None, st)
    st.players[1].hand.add(card)

    blue = compile_condition("CARD_IN_ZONE", {"zone": "hand", "color": "blue"})
    yellow = compile_condition("CARD_IN_ZONE", {"zone": "hand", "color": "yellow"})

    assert blue(_card(PLAIN), None, st) is True
    assert yellow(_card(PLAIN), None, st) is False, (
        "it still reads as its printed colour")


def test_the_printed_pitch_value_is_left_alone():
    """The card does not mention pitch, so the implementation does not guess."""
    st = _state(agent=_pick("blue"))
    card = _card("become_the_cup_yellow")
    printed_pitch = card.pitch

    run_ability(get_card("become_the_cup_yellow").abilities[0], card, None, st)

    assert card.pitch == printed_pitch


# --- naming a card ----------------------------------------------------------

def _banished(st, pid, slug):
    c = _card(slug, pid)
    st.players[pid].banished.add(c)
    c.is_public = True
    return c


def test_naming_a_card_turns_matching_banished_cards_face_down():
    st = _state()
    target_name = DB.get(PLAIN).name
    st.player_agents = {p: _pick(target_name) for p in (1, 2)}
    match = _banished(st, 1, PLAIN)
    other = _banished(st, 2, OTHER)
    source = _card("blessing_of_themis_yellow")
    st.players[1].permanents.add(source)

    run_ability(get_card("blessing_of_themis_yellow").abilities[1], source, None, st)

    assert match.is_public is False, "the named card was not turned face down"
    assert other.is_public is True, "a card with a different name was flipped"


def test_it_reaches_both_players_banished_zones():
    """"cards with that name in banished ZONES" - plural."""
    st = _state()
    target_name = DB.get(PLAIN).name
    st.player_agents = {p: _pick(target_name) for p in (1, 2)}
    theirs = _banished(st, 2, PLAIN)
    source = _card("blessing_of_themis_yellow")
    st.players[1].permanents.add(source)

    run_ability(get_card("blessing_of_themis_yellow").abilities[1], source, None, st)

    assert theirs.is_public is False


def test_the_name_survives_onto_the_object():
    """A reference scope lasts ONE ability execution; the later clause that
    reads the name runs in a different one."""
    st = _state()
    target_name = DB.get(PLAIN).name
    st.player_agents = {p: _pick(target_name) for p in (1, 2)}
    _banished(st, 1, PLAIN)
    source = _card("blessing_of_themis_yellow")
    st.players[1].permanents.add(source)

    run_ability(get_card("blessing_of_themis_yellow").abilities[1], source, None, st)

    assert (getattr(source, "dsl_chosen", None) or {}).get("named_card") == target_name


def test_naming_nothing_flips_nothing():
    """An unset name must not fall through to "every card in the zone"."""
    st = _state()
    banished = _banished(st, 1, PLAIN)
    source = _card("blessing_of_themis_yellow")

    compile_effect("FLIP_MATCHING", {
        "face_up": False,
        "target": {"controller": "ANY", "zone": "BANISHED", "amount": "ALL",
                   "name_ref": "named_card"}})(source, None, st)

    assert banished.is_public is True, (
        "with nothing named it flipped the whole banished zone")


def test_themis_goes_to_the_soul_not_the_deck():
    """"put this into your SOUL" - it was PUT_SELF_BOTTOM_DECK, a different zone
    with different consequences (soul count feeds other cards; a deck card is
    drawn again)."""
    st = _state()
    source = _card("blessing_of_themis_yellow")
    st.players[1].permanents.add(source)

    run_ability(get_card("blessing_of_themis_yellow").abilities[2], source, None, st)

    assert source in st.players[1].soul.cards, (
        f"it went to {source.zone!r}")
    assert source not in st.players[1].deck.cards


# --- MARK naming a hero -----------------------------------------------------

def _is_marked(st, pid):
    """effect_keywords.mark() writes class_counters["marked"]. Player also has a
    plain `marked` bool that nothing sets — reading it is how the clear-on-hit
    listener came to be a no-op."""
    return st.players[pid].class_counters.get("marked", 0) > 0


def _hero(st, pid, slug):
    h = _card(slug, pid)
    st.players[pid].hero = h
    return h


def test_vow_marks_an_arakni():
    st = _state()
    _hero(st, 2, "arakni_huntsman")
    source = _card("vow_of_vengeance")

    run_ability(get_card("vow_of_vengeance").abilities[0], source, None, st)

    assert _is_marked(st, 2) is True


def test_vow_does_not_mark_a_hero_that_is_not_an_arakni():
    st = _state()
    _hero(st, 2, "gravy_bones")
    source = _card("vow_of_vengeance")

    run_ability(get_card("vow_of_vengeance").abilities[0], source, None, st)

    assert _is_marked(st, 2) is False, (
        "it marked a hero the card does not name")


def test_an_untargeted_mark_still_hits_the_opponent():
    """The nine cards saying "mark target opposing hero" must be unaffected."""
    st = _state()
    _hero(st, 2, "gravy_bones")

    compile_effect("MARK", {"target": "opponent"})(_card(PLAIN), None, st)

    assert _is_marked(st, 2) is True


# --- CR 9.3.3: marked is cleared on hit -------------------------------------

def test_marked_is_cleared_when_the_marked_hero_is_hit():
    """CR 9.3.3: "when a marked hero is HIT by a source controlled by an
    opponent, the marked condition of that hero is REMOVED as part of the hit
    event."

    The listener that does this read Player.marked - a plain bool that NOTHING
    ever sets. effect_keywords.mark() writes class_counters["marked"], which is
    what every condition reads. So the bool was always False, the condition was
    never cleared, and a marked hero stayed marked for the rest of the game
    with every "if they are marked" payoff still paying out.

    Uses the ENGINE's listener, not a copy: registering a local reimplementation
    here would pass whatever the engine does.
    """
    from engine.state import CombatState, Event

    st = _state()
    st.event_manager.register("hit", E.clear_marked_on_hit)

    compile_effect("MARK", {})(_card(PLAIN), None, st)
    assert _is_marked(st, 2) is True

    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=_card(PLAIN), keywords=[])
    st.combat.hit = True
    st.event_manager.emit(Event(type="hit", data={}), st)

    assert _is_marked(st, 2) is False, (
        "the marked condition survived the hit that should have removed it")


def test_the_clear_listener_is_the_one_start_game_registers():
    """The extracted listener has to be the one actually wired up, or this file
    tests a function nothing calls."""
    import io as _io
    src = _io.open(E.__file__, encoding="utf-8").read()
    assert "event_mngr.register('hit', clear_marked_on_hit)" in src
