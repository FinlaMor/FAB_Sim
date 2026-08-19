"""Counting turn events, damage magnitude, and looked-at cards.

The EVENT_THIS_TURN *condition* could already TEST a turn-event marker; nothing
could COUNT one. Every card phrased "X is the number of <thing> you've done this
turn" therefore invented a private counter that nothing incremented, so X was 0
and the card did nothing — Rift Bind is the case that surfaced it.

Damage needed a separate mechanism: markers record that something HAPPENED, so
four 1-point arcane hits and one 1-point hit look identical to them. Vaporize's
"X is the total arcane damage you've dealt this turn" is a MAGNITUDE and reads a
tally instead.
"""
import copy

from engine.card import Card, CardDB
from engine.card_effects.dsl.effect_types import _resolve_amount
from engine.card_effects.dsl.loader import load_all_cards
from engine.effect_keywords import DamageType, deal_damage
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


def _hero(st, pid):
    return st.players[pid].hero


# --- COUNT_TURN_EVENT ------------------------------------------------------

def test_count_turn_event_counts_every_occurrence():
    st = _state()
    card = _card("rift_bind_blue")
    from engine.effect_keywords import _record_turn_event
    for _ in range(3):
        _record_turn_event(st, 1, "play", "non_attack_action")
    n = _resolve_amount({"type": "COUNT_TURN_EVENT", "event": "play",
                         "qualifier": "non_attack_action"}, st, card)
    assert n == 3


def test_count_turn_event_is_zero_before_anything_happens():
    st = _state()
    card = _card("rift_bind_blue")
    assert _resolve_amount({"type": "COUNT_TURN_EVENT", "event": "play",
                            "qualifier": "non_attack_action"}, st, card) == 0


def test_count_turn_event_respects_the_qualifier():
    # An attack action must not count toward "non-attack action cards played".
    st = _state()
    card = _card("rift_bind_blue")
    from engine.effect_keywords import _record_turn_event
    _record_turn_event(st, 1, "play", "attack_action")
    assert _resolve_amount({"type": "COUNT_TURN_EVENT", "event": "play",
                            "qualifier": "non_attack_action"}, st, card) == 0


def test_count_turn_event_counts_only_the_controllers_events():
    st = _state()
    card = _card("rift_bind_blue")
    from engine.effect_keywords import _record_turn_event
    _record_turn_event(st, 2, "play", "non_attack_action")
    assert _resolve_amount({"type": "COUNT_TURN_EVENT", "event": "play",
                            "qualifier": "non_attack_action"}, st, card) == 0


# --- DAMAGE_DEALT_THIS_TURN ------------------------------------------------

def test_damage_tally_sums_magnitude_not_occurrences():
    # Three 1-point hits are 3, not 3 markers' worth of "something happened".
    st = _state()
    card = _card("vaporize__shock_yellow")
    for _ in range(3):
        deal_damage(st, amount=1, damage_type=DamageType.ARCANE,
                    source_player_id=1, damage_target=_hero(st, 2),
                    damage_source="effect", damage_source_card=card)
    n = _resolve_amount({"type": "DAMAGE_DEALT_THIS_TURN",
                         "damage_type": "arcane", "target": "hero"}, st, card)
    assert n == 3


def test_damage_tally_separates_damage_types():
    st = _state()
    card = _card("vaporize__shock_yellow")
    deal_damage(st, amount=4, damage_type=DamageType.PHYSICAL,
                source_player_id=1, damage_target=_hero(st, 2),
                damage_source="effect", damage_source_card=card)
    n = _resolve_amount({"type": "DAMAGE_DEALT_THIS_TURN",
                         "damage_type": "arcane", "target": "hero"}, st, card)
    assert n == 0, "physical damage must not count toward arcane"


def test_damage_tally_counts_only_what_you_dealt():
    st = _state()
    card = _card("vaporize__shock_yellow")
    opp_card = _card("vaporize__shock_yellow", owner=2)
    deal_damage(st, amount=3, damage_type=DamageType.ARCANE,
                source_player_id=2, damage_target=_hero(st, 1),
                damage_source="effect", damage_source_card=opp_card)
    n = _resolve_amount({"type": "DAMAGE_DEALT_THIS_TURN",
                         "damage_type": "arcane", "target": "hero"}, st, card)
    assert n == 0


def test_damage_tally_clears_at_end_of_turn():
    st = _state()
    card = _card("vaporize__shock_yellow")
    deal_damage(st, amount=2, damage_type=DamageType.ARCANE,
                source_player_id=1, damage_target=_hero(st, 2),
                damage_source="effect", damage_source_card=card)
    import engine.engine as E
    E._end_phase_iter(st)
    assert _resolve_amount({"type": "DAMAGE_DEALT_THIS_TURN",
                            "damage_type": "arcane", "target": "hero"}, st, card) == 0


# --- COUNT_REF -------------------------------------------------------------

def test_count_ref_counts_revealed_cards_matching_the_filter():
    st = _state()
    card = _card("song_of_sinew_yellow")
    for power in (7, 6, 2, 9):
        c = Card(slug=f"c{power}", name=f"c{power}", types=["Action"],
                 subtypes=["Attack"])
        c.owner = c.controller = 1
        c.power = c.base_power = power
        st.players[1].deck.add(c)
    from engine.card_effects.dsl import dispatch
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    # 7, 6 and 9 qualify; 2 does not.
    assert st.players[1].dsl_queued_attack_mods[0]["amount"] == 3


def test_revealing_does_not_move_the_cards_off_the_deck():
    # "Put them back in any order" needs no effect BECAUSE revealing never
    # removed them — if reveal started popping cards this would silently
    # mill four cards every time the card is played.
    st = _state()
    card = _card("song_of_sinew_yellow")
    for i in range(4):
        c = Card(slug=f"d{i}", name=f"d{i}", types=["Action"])
        c.owner = c.controller = 1
        c.power = c.base_power = 1
        st.players[1].deck.add(c)
    before = len(st.players[1].deck.cards)
    from engine.card_effects.dsl import dispatch
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert len(st.players[1].deck.cards) == before
