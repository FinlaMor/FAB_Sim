""""Effects don't trigger when an attack hits" - the damage still happens.

Two cards say it and neither could:

  dense_blue_mist_blue  "If a Chi was pitched to play this, effects don't
                        trigger if an attack hits you THIS TURN." It had an
                        ON_PITCH trigger setting a private flag plus an
                        ON_DEFEND ability granting WARD - damage PREVENTION,
                        not trigger suppression, so the card was given a shield
                        it does not have while its actual clause went missing.
  tripwire_trap_red     "effects don't trigger when an attack hits THIS CHAIN
                        LINK unless the attacking hero pays {r}". CR sec.926
                        describes this card in exactly those terms. It had been
                        a PAY_OR_DAMAGE dealing 1 damage.

The two scopes differ - a turn-scoped marker on the player being hit, and a
chain-link flag on the combat - so SUPPRESS_HIT_TRIGGERS takes a `scope`.
Suppression is read at the single ON_HIT dispatch point, so what is suppressed
is the triggered LAYERS; the damage is dealt as normal.

"If a CHI was pitched to play this" also needed answering: a PLAY ability
resolves after the cost is paid and never sees the Action, and only the ACTIVATE
path carried pitched cards onto the stack entry.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.condition_types import compile_condition
from engine.card_effects.dsl.effect_types import compile_effect
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.engine import HIT_TRIGGERS_SUPPRESSED
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

# An attack whose ON_HIT does something observable to the defender.
HITTER = "the_weakest_link_red"
CHI = "inner_chi_blue"
PLAIN = "brutal_assault_red"


def _card(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    st.individual_turns = 1
    return st


def _attack(st, attacker_id=1):
    card = _card(HITTER, attacker_id)
    st.combat = CombatState(attacker_id=attacker_id, link_id=1, attack_power=3,
                            attack_card=card, keywords=[])
    st.combat.hit = True
    return card


def _hit(st):
    """Emit the real 'hit' event, so the registered ON_HIT listener runs.

    Suppression lives at that listener, so dispatching a card's abilities
    directly would bypass the very thing under test. The bus is
    state.event_manager (there is no event_bus).
    """
    from engine.state import Event
    st.event_manager.emit(Event(type="hit", data={}), st)


# --- the primitive ----------------------------------------------------------

def test_the_turn_marker_is_set_on_the_named_player():
    st = _state()
    source = _card(PLAIN, 1)

    compile_effect("SUPPRESS_HIT_TRIGGERS", {"scope": "TURN", "player": "SELF"})(
        source, None, st)

    assert HIT_TRIGGERS_SUPPRESSED in st.players[1].current_turn_effects
    assert HIT_TRIGGERS_SUPPRESSED not in st.players[2].current_turn_effects


def test_the_chain_flag_lands_on_the_combat_not_the_player():
    st = _state()
    _attack(st, attacker_id=2)
    source = _card(PLAIN, 1)

    compile_effect("SUPPRESS_HIT_TRIGGERS", {"scope": "CHAIN"})(source, None, st)

    assert st.combat.suppress_hit_triggers is True
    assert HIT_TRIGGERS_SUPPRESSED not in st.players[1].current_turn_effects, (
        "a chain-scoped suppression leaked into the whole turn")


# --- "a Chi was pitched to play this" ---------------------------------------

def test_pitched_for_this_reads_what_paid_for_this_card():
    st = _state()
    played = _card(PLAIN, 1)
    fn = compile_condition("PITCHED_FOR_THIS", {"subtype": "Chi"})

    assert fn(played, None, st) is False

    played.pitched_for_this = [_card(CHI, 1)]
    assert fn(played, None, st) is True


def test_pitched_for_this_is_not_the_pitch_zone():
    """The pitch zone holds everything pitched this turn; this asks what paid
    for THIS card."""
    st = _state()
    st.players[1].pitch.add(_card(CHI, 1))
    played = _card(PLAIN, 1)

    fn = compile_condition("PITCHED_FOR_THIS", {"subtype": "Chi"})
    assert fn(played, None, st) is False, (
        "it answered from the pitch zone rather than from this card's cost")


def test_a_non_chi_pitch_does_not_satisfy_it():
    st = _state()
    played = _card(PLAIN, 1)
    played.pitched_for_this = [_card(PLAIN, 1)]

    fn = compile_condition("PITCHED_FOR_THIS", {"subtype": "Chi"})
    assert fn(played, None, st) is False


# --- dense_blue_mist_blue ---------------------------------------------------

def test_dense_blue_mist_suppresses_only_when_a_chi_paid_for_it():
    st = _state()
    played = _card("dense_blue_mist_blue", 1)

    run_ability(get_card("dense_blue_mist_blue").abilities[0], played, None, st)
    assert HIT_TRIGGERS_SUPPRESSED not in st.players[1].current_turn_effects, (
        "it suppressed with no Chi pitched")

    st2 = _state()
    played2 = _card("dense_blue_mist_blue", 1)
    played2.pitched_for_this = [_card(CHI, 1)]
    run_ability(get_card("dense_blue_mist_blue").abilities[0], played2, None, st2)
    assert HIT_TRIGGERS_SUPPRESSED in st2.players[1].current_turn_effects


def test_dense_blue_mist_weakens_incoming_attacks_either_way():
    """Clause 1 is unconditional; only clause 2 needs the Chi."""
    st = _state()
    played = _card("dense_blue_mist_blue", 1)

    run_ability(get_card("dense_blue_mist_blue").abilities[0], played, None, st)

    hooks = list(getattr(st.players[2], "turn_attack_hooks", None) or [])
    assert hooks, "no per-attack hook was queued on the opponent"
    assert any(h.get("amount") == -1 for h in hooks), hooks
    assert not (getattr(st.players[1], "turn_attack_hooks", None) or []), (
        "the -1{p} landed on the caster's own attacks")


# --- the suppression actually stops a trigger -------------------------------

def test_a_suppressed_hit_deals_damage_but_fires_no_trigger():
    st = _state()
    attack = _attack(st, attacker_id=1)
    st.players[2].hand.add(_card("phoenix_flame_red", 2))
    st.players[1].deck.add(_card(PLAIN, 1))
    st.players[2].current_turn_effects.append(HIT_TRIGGERS_SUPPRESSED)
    theirs_before = len(st.players[2].hand.cards)

    _hit(st)

    assert len(st.players[2].hand.cards) == theirs_before, (
        "the attack's ON_HIT fired despite suppression")


def test_an_unsuppressed_hit_still_fires_its_trigger():
    """The other half of the pair: suppression must not be the default."""
    st = _state()
    _attack(st, attacker_id=1)
    st.players[2].hand.add(_card("phoenix_flame_red", 2))
    st.players[1].deck.add(_card(PLAIN, 1))
    theirs_before = len(st.players[2].hand.cards)

    _hit(st)

    assert len(st.players[2].hand.cards) == theirs_before - 1, (
        "the attack's ON_HIT did not fire, so the suppression test above "
        "proves nothing")
