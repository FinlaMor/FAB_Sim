"""Ten cards whose whole text is one sentence, tested together.

622 pending cards are one sentence long. They are individually easy and
collectively most of what is left, so they are authored in batches and checked
in one file — the value is in the batch, not in any one of them.

WHAT THIS FILE IS ACTUALLY GUARDING. Each card here sits on a fork where the
wrong branch still produces a working card:

    strike_gold           "when this HITS" is unqualified — adding a
                          hits-a-hero gate would silently narrow it
    spellblade_assault    "when you ATTACK with this" — the tokens arrive on
    singeing_steelblade   declaration, so they land even when it is blocked;
                          ON_HIT would lose them exactly when it matters
    wartune_herald        "put IT into your SOUL" — the same handler defaults
                          to the DECK, which puts the card back to be drawn
    spring_load           "when this attacks, IF" is checked once, at
                          declaration; a static would take the bonus back the
                          moment a card reached the hand
    valiant_thrust        "if you've charged, this GAINS" is continuous, and
                          SOURCE_IS_ATTACK is what stops it pumping every
                          attack its controller makes
    sneak_attack          the window is a CHAIN LINK, not a turn
    tip_off               the discard is a COST, so the card leaves the hand
    trip_the_light_       whether or not the effect lands
    fantastic
    wrecker_romp          a cost that is not an effect, and a card with no
                          abilities at all
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.effect_keywords import DamageType, deal_damage
from engine.state import Event
from tests.conftest import _make_state, attack_with, recalculate_attack

load_all_cards()
DB = CardDB()


def _card(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _state():
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="", **kw: o[0]      # noqa: E731
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    return st


def _fire(st, slug, source=None):
    run_ability(get_card(slug).abilities[0], source or _card(slug), None, st)


def _tokens(st, pid):
    return [c.slug for c in st.players[pid].permanents.cards]


# ------------------------------------------------------------ on hit / attack

def test_strike_gold_makes_a_gold_token():
    st = _state()
    attacker = attack_with(st, _card("strike_gold_blue"))
    st.combat.hit = True
    _fire(st, "strike_gold_blue", attacker)
    assert "gold" in _tokens(st, 1)


def test_strike_gold_is_not_narrowed_to_heroes():
    """The text says "hits", not "hits a hero". A gate that is not printed is
    as wrong as one that is missing, and much harder to see."""
    st = _state()
    attacker = attack_with(st, _card("strike_gold_blue"))
    st.combat.hit = True
    st.combat.attack_target = _card("strike_gold_blue", 2)   # a permanent
    _fire(st, "strike_gold_blue", attacker)
    assert "gold" in _tokens(st, 1)


def test_spellblade_assault_makes_its_runechants_on_declaration():
    """ON_ATTACK, not ON_HIT: a blocked attack still creates them, which is
    exactly the case the card is bought for."""
    st = _state()
    attacker = attack_with(st, _card("spellblade_assault_blue"))
    st.combat.hit = False
    _fire(st, "spellblade_assault_blue", attacker)
    assert _tokens(st, 1).count("runechant") == 2


def test_singeing_steelblade_burns_on_declaration():
    st = _state()
    attacker = attack_with(st, _card("singeing_steelblade_blue"))
    before = st.players[2].life
    _fire(st, "singeing_steelblade_blue", attacker)
    assert st.players[2].life == before - 1


def test_wartune_herald_goes_to_the_soul_not_the_deck():
    st = _state()
    attacker = attack_with(st, _card("wartune_herald_blue"))
    st.combat.hit = True
    _fire(st, "wartune_herald_blue", attacker)
    assert attacker in st.players[1].soul.cards, (
        "it is in %r" % getattr(attacker, "zone", None))
    assert attacker not in st.players[1].deck.cards


# ---------------------------------------------------------------- the gates

def test_spring_load_pumps_on_an_empty_hand():
    st = _state()
    attacker = attack_with(st, _card("spring_load_blue"))
    _fire(st, "spring_load_blue", attacker)
    assert recalculate_attack(st) == (attacker.base_power or 0) + 1


def test_spring_load_does_not_pump_with_a_card_in_hand():
    st = _state()
    st.players[1].hand.add(_card("strike_gold_blue"))
    attacker = attack_with(st, _card("spring_load_blue"))
    _fire(st, "spring_load_blue", attacker)
    assert recalculate_attack(st) == (attacker.base_power or 0)


def test_valiant_thrust_pumps_after_a_charge():
    from engine.effect_keywords import _record_turn_event
    st = _state()
    _record_turn_event(st, 1, "charge", "some_card", [], [], [])
    attacker = attack_with(st, _card("valiant_thrust_blue"))
    E._register_card_continuous_effects(st, attacker)
    assert recalculate_attack(st) == (attacker.base_power or 0) + 3


def test_valiant_thrust_does_not_pump_without_one():
    st = _state()
    attacker = attack_with(st, _card("valiant_thrust_blue"))
    E._register_card_continuous_effects(st, attacker)
    assert recalculate_attack(st) == (attacker.base_power or 0)


def _an_attack_reaction():
    import io, json
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    idx = json.load(io.open(root / "card_data" / "slug_index.json",
                            encoding="utf-8"))["by_slug"]
    return next(s for s, e in idx.items()
                if "AttackReaction" in (e.get("types") or []) and DB.get(s))


def test_sneak_attack_pumps_after_an_attack_reaction():
    st = _state()
    attacker = attack_with(st, _card("sneak_attack_blue"))
    played = _card(_an_attack_reaction())
    st.event_manager.emit(
        Event(type="on_play", card=played.slug, data={"card": played}), st)
    E._register_card_continuous_effects(st, attacker)
    assert recalculate_attack(st) == (attacker.base_power or 0) + 4


def test_sneak_attack_does_not_pump_on_a_quiet_link():
    st = _state()
    attacker = attack_with(st, _card("sneak_attack_blue"))
    E._register_card_continuous_effects(st, attacker)
    assert recalculate_attack(st) == (attacker.base_power or 0)


# ------------------------------------------------------------- the instants

def test_tip_off_marks_the_opposing_hero():
    st = _state()
    _fire(st, "tip_off_blue")
    assert st.players[2].class_counters.get("marked") == 1
    assert st.players[1].class_counters.get("marked") != 1


def test_trip_the_light_fantastic_shields_two():
    st = _state()
    _fire(st, "trip_the_light_fantastic_blue")
    before = st.players[1].life
    deal_damage(st, 5, DamageType.PHYSICAL, 2, st.players[1].hero, "effect")
    assert before - st.players[1].life == 3


# ----------------------------------------------------------- the bare cost

def test_wrecker_romp_has_a_cost_and_no_abilities():
    """Its entire text is an additional cost. A cost must block the play, so it
    is card-level; an empty PLAY ability to hold it would be a no-op, and an
    ON_PLAY discard would let an empty hand play the card for free."""
    card = get_card("wrecker_romp_blue")
    assert not card.abilities
    assert getattr(card, "play_cost", None), "the cost is not compiled"
