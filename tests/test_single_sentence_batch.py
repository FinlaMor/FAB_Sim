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


# =========================================================== second batch
# Eight more one-liners. Same discipline: each sits on a fork where the wrong
# branch still produces a working card.


def _an_instant():
    import io, json
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    idx = json.load(io.open(root / "card_data" / "slug_index.json",
                            encoding="utf-8"))["by_slug"]
    return next(s for s, e in idx.items()
                if "Instant" in (e.get("types") or []) and DB.get(s))


def test_searing_shot_makes_them_lose_life_rather_than_dealing_damage():
    """Losing life is not being dealt damage: it cannot be prevented and fires
    no on-damage trigger. A shield up and the loss still lands."""
    from engine.card_effects.dsl.effect_types import compile_effect
    st = _state()
    compile_effect("PREVENT_DAMAGE", {"amount": 5})(_card("searing_shot_blue", 2), None, st)
    attacker = attack_with(st, _card("searing_shot_blue"))
    st.combat.hit = True
    before = st.players[2].life
    _fire(st, "searing_shot_blue", attacker)
    assert st.players[2].life == before - 1, (
        "the shield absorbed it, so it was authored as damage")


def test_searing_shot_needs_a_hero():
    st = _state()
    attacker = attack_with(st, _card("searing_shot_blue"))
    st.combat.hit = True
    st.combat.attack_target = _card("searing_shot_blue", 2)   # a permanent
    before = st.players[2].life
    _fire(st, "searing_shot_blue", attacker)
    assert st.players[2].life == before


def test_searing_ray_reads_the_pitch_zone_colour():
    st = _state()
    attacker = attack_with(st, _card("searing_ray_blue"))
    E._register_card_continuous_effects(st, attacker)
    assert recalculate_attack(st) == (attacker.base_power or 0)

    # A REAL yellow card, not one whose pitch was patched after construction:
    # the colour is derived at build time, so assigning raw_pitch afterwards
    # leaves the card blue and the test fails against a correct implementation.
    st.players[1].pitch.add(_card(_a_card_of_pitch(2)))
    assert recalculate_attack(st) == (attacker.base_power or 0) + 2

    st2 = _state()
    other = attack_with(st2, _card("searing_ray_blue"))
    E._register_card_continuous_effects(st2, other)
    st2.players[1].pitch.add(_card(_a_card_of_pitch(3)))     # blue
    assert recalculate_attack(st2) == (other.base_power or 0), (
        "any pitched card satisfied it, so the colour is not being read")


def _a_card_of_pitch(pitch):
    import io, json
    from pathlib import Path as _P
    root = _P(__file__).resolve().parent.parent
    idx = json.load(io.open(root / "card_data" / "slug_index.json",
                            encoding="utf-8"))["by_slug"]
    return next(s for s, e in idx.items()
                if e.get("pitch") == pitch and DB.get(s))


def test_rising_speed_gets_go_again_only_after_a_draw():
    from engine.effect_keywords import _record_turn_event
    st = _state()
    attacker = attack_with(st, _card("rising_speed_blue"))
    E._register_card_continuous_effects(st, attacker)
    recalculate_attack(st)
    assert "goagain" not in {str(k).lower().replace(" ", "").replace("_", "")
                             for k in (st.combat.keywords or [])}

    st2 = _state()
    _record_turn_event(st2, 1, "draw")
    attacker2 = attack_with(st2, _card("rising_speed_blue"))
    E._register_card_continuous_effects(st2, attacker2)
    recalculate_attack(st2)
    assert "goagain" in {str(k).lower().replace(" ", "").replace("_", "")
                         for k in (st2.combat.keywords or [])}


def test_rising_speeds_printed_go_again_is_withdrawn():
    from engine.card_effects.dsl.loader import conditional_keywords
    assert "GoAgain" in (DB.get("rising_speed_blue").keywords or [])
    assert "goagain" in conditional_keywords("rising_speed_blue")


def test_overcharges_printed_go_again_is_left_alone():
    """Its gate is on the +1{p} only. A withdrawal here would take away a
    keyword the card unconditionally has -- the same bug inverted."""
    from engine.card_effects.dsl.loader import conditional_keywords
    assert "GoAgain" in (DB.get("overcharge_blue").keywords or [])
    assert not conditional_keywords("overcharge_blue")


def test_overcharge_pumps_after_an_instant_this_chain_link():
    st = _state()
    attacker = attack_with(st, _card("overcharge_blue"))
    played = _card(_an_instant())
    st.event_manager.emit(
        Event(type="on_play", card=played.slug, data={"card": played}), st)
    E._register_card_continuous_effects(st, attacker)
    assert recalculate_attack(st) == (attacker.base_power or 0) + 1


def test_overcharge_does_not_pump_on_a_quiet_link():
    st = _state()
    attacker = attack_with(st, _card("overcharge_blue"))
    E._register_card_continuous_effects(st, attacker)
    assert recalculate_attack(st) == (attacker.base_power or 0)


def test_plunge_pays_only_a_dagger():
    """The filter IS the clause. An unfiltered queue would pay the next attack
    of any kind, which no dagger-only test would notice."""
    st = _state()
    attacker = attack_with(st, _card("plunge_blue"))
    st.combat.hit = True
    _fire(st, "plunge_blue", attacker)
    st.combat = None
    plain = attack_with(st, _card("strike_gold_blue"))    # not a dagger
    assert recalculate_attack(st) == (plain.base_power or 0)


def test_rising_energy_is_a_cost_reduction_not_an_effect():
    """A reduction applied as an effect happens after the price is paid. It is
    card-level so play.py can charge less in the first place."""
    card = get_card("rising_energy_blue")
    assert not card.abilities
    assert getattr(card, "cost_modifiers", None), "no cost modifier compiled"


def test_savage_swing_has_a_cost_and_no_abilities():
    card = get_card("savage_swing_blue")
    assert not card.abilities
    assert getattr(card, "play_cost", None)


# =========================================================== third batch


def test_wounded_bull_pumps_only_while_behind_on_life():
    st = _state()
    st.players[1].life = 10
    st.players[2].life = 20
    attacker = attack_with(st, _card("wounded_bull_blue"))
    _fire(st, "wounded_bull_blue", attacker)
    assert recalculate_attack(st) == (attacker.base_power or 0) + 1

    st = _state()
    st.players[1].life = 20
    st.players[2].life = 10
    attacker = attack_with(st, _card("wounded_bull_blue"))
    _fire(st, "wounded_bull_blue", attacker)
    assert recalculate_attack(st) == (attacker.base_power or 0)


def test_punch_above_your_weight_charges_for_the_pump():
    st = _state()
    st.players[1].resources = 3
    attacker = attack_with(st, _card("punch_above_your_weight_blue"))
    _fire(st, "punch_above_your_weight_blue", attacker)
    assert recalculate_attack(st) == (attacker.base_power or 0) + 3
    assert st.players[1].resources == 0, "the {r}{r}{r} was not paid"


def test_punch_above_your_weight_pays_nothing_when_it_cannot():
    """The payment is the MAY's COST. A controller who cannot pay must not be
    charged, and must not get the pump either."""
    st = _state()
    st.players[1].resources = 1
    attacker = attack_with(st, _card("punch_above_your_weight_blue"))
    _fire(st, "punch_above_your_weight_blue", attacker)
    assert recalculate_attack(st) == (attacker.base_power or 0)
    assert st.players[1].resources == 1


def test_puncture_takes_a_sword_or_a_dagger_and_grants_piercing():
    """"sword OR dagger" is one subtype filter with two entries; two separate
    conditions would be an AND and the reaction could never be played."""
    import io, json
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    idx = json.load(io.open(root / "card_data" / "slug_index.json",
                            encoding="utf-8"))["by_slug"]
    # A SWORD is a weapon and a DAGGER can be either a weapon or an attack
    # action card, so "sword or dagger attack" spans both shapes. A first
    # version looked for subtypes Sword+Attack together, which no card has --
    # it raised StopIteration instead of testing the card.
    for want in ("Sword", "Dagger"):
        slug = next(s for s, e in idx.items()
                    if want in (e.get("subtypes") or [])
                    and (e.get("power") or 0) > 0 and DB.get(s))
        st = _state()
        attacker = attack_with(st, _card(slug))
        _fire(st, "puncture_blue", attacker)
        assert recalculate_attack(st) == (attacker.base_power or 0) + 1, want
        kws = {str(k).lower().replace(" ", "") for k in (st.combat.keywords or [])}
        assert "piercing" in kws, want


def test_take_aim_pays_a_ranger_attack_action_and_nothing_else():
    """MODIFY_NEXT_CARD has no power grant at all -- `power_mod` there is a
    parameter nothing reads, so the clause would compile and do nothing.
    audit_params caught that; this pins the working shape."""
    import io, json
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    idx = json.load(io.open(root / "card_data" / "slug_index.json",
                            encoding="utf-8"))["by_slug"]
    ranger = next(s for s, e in idx.items()
                  if "Ranger" in (e.get("classes") or [])
                  and "Attack" in (e.get("subtypes") or [])
                  and "Action" in (e.get("types") or []) and DB.get(s))
    other = next(s for s, e in idx.items()
                 if "Ranger" not in (e.get("classes") or [])
                 and "Attack" in (e.get("subtypes") or [])
                 and "Action" in (e.get("types") or []) and DB.get(s))

    st = _state()
    _fire(st, "take_aim_blue")
    a = attack_with(st, _card(ranger))
    assert recalculate_attack(st) == (a.base_power or 0) + 1

    st = _state()
    _fire(st, "take_aim_blue")
    b = attack_with(st, _card(other))
    assert recalculate_attack(st) == (b.base_power or 0), (
        "it paid a non-Ranger attack")


def test_shaden_swing_banishes_rather_than_discards():
    """A discarded card goes to the graveyard and a banished one does not, so
    the two differ for every graveyard-recursion card. Both spellings resolve,
    and only one puts the card in the right zone."""
    st = _state()
    st.players[1].hand.add(_card("strike_gold_blue"))
    card = get_card("shaden_swing_blue")
    assert getattr(card, "play_cost", None)
    assert not card.abilities
    import json as _json
    blob = _json.dumps(_raw("shaden_swing_blue").get("cost"))
    assert "BANISH_FROM_HAND" in blob and "DISCARD" not in blob


def _raw(slug):
    import json as _json
    from pathlib import Path
    from tests.conftest import _card_json
    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    return _json.loads(_card_json(root, slug + ".json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("slug", ["swing_fist_think_later_blue",
                                  "shaden_swing_blue", "rev_up_blue"])
def test_the_cost_only_cards_have_no_abilities(slug):
    card = get_card(slug)
    assert not card.abilities
    assert getattr(card, "play_cost", None) or getattr(card, "cost_modifiers", None)


# =========================================================== fourth batch


@pytest.mark.parametrize("slug,token,n", [
    ("seismic_stir_red", "seismic_surge", 3),
    ("read_the_runes_red", "runechant", 3),
    ("prismatic_shield_red", "spectral_shield", 3),
])
def test_a_create_n_card_creates_n(slug, token, n):
    """`amount` is read under both `amount` and `count`, and a CREATE_TOKEN
    that names neither creates ONE -- so "create 3" silently becomes "create
    1", which every other assertion about the card would still pass."""
    st = _state()
    _fire(st, slug)
    assert _tokens(st, 1).count(token) == n


def test_deadwood_dirge_pays_out_only_if_it_destroyed_something():
    st = _state()
    aura = _card("runechant")
    st.players[1].permanents.add(aura)
    _fire(st, "deadwood_dirge_red")
    assert _tokens(st, 1).count("runechant") == 3, (
        "destroyed the aura but paid nothing, or paid the wrong number")


def test_deadwood_dirge_pays_nothing_with_no_aura():
    """"If you do" is a real gate. Asking the ARENA afterwards cannot answer
    it: destroying the only aura leaves the same empty board as never having
    had one."""
    st = _state()
    _fire(st, "deadwood_dirge_red")
    assert _tokens(st, 1).count("runechant") == 0


def test_little_big_foot_needs_two_expensive_pitches():
    """Both numbers are gates. With the count omitted it defaults to one and
    the card pumps off a single expensive pitch -- stronger than printed, and
    invisible unless a test pitches exactly one."""
    import io, json
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    idx = json.load(io.open(root / "card_data" / "slug_index.json",
                            encoding="utf-8"))["by_slug"]
    dear = next(s for s, e in idx.items()
                if isinstance(e.get("cost"), int) and e["cost"] >= 3 and DB.get(s))
    cheap = next(s for s, e in idx.items() if e.get("cost") == 0 and DB.get(s))

    st = _state()
    attacker = attack_with(st, _card("little_big_foot_blue"))
    E._register_card_continuous_effects(st, attacker)
    st.players[1].pitch.add(_card(dear))
    assert recalculate_attack(st) == (attacker.base_power or 0), "one was enough"
    st.players[1].pitch.add(_card(dear))
    assert recalculate_attack(st) == (attacker.base_power or 0) + 4

    st2 = _state()
    other = attack_with(st2, _card("little_big_foot_blue"))
    E._register_card_continuous_effects(st2, other)
    st2.players[1].pitch.add(_card(cheap))
    st2.players[1].pitch.add(_card(cheap))
    assert recalculate_attack(st2) == (other.base_power or 0), (
        "two CHEAP pitches satisfied it, so the cost bound is not being read")


def test_golden_company_replaces_its_cost_rather_than_adding_to_it():
    """An ALTERNATIVE cost, not an additional one. As an additional_cost the
    Gold would be charged on top of the {r} -- the opposite of the card."""
    card = get_card("golden_company_blue")
    ability = card.abilities[0]
    assert getattr(ability, "alternative_costs", None), "no alternative cost"
    assert not getattr(ability, "additional_costs", None), (
        "an additional cost would be charged ON TOP of the resource cost")
