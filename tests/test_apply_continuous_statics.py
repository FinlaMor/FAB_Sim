"""Effects buried in APPLY_CONTINUOUS inside a plain STATIC — dead twice over.

Nothing dispatches a plain STATIC, and the effect the card actually needs was
nested one level further inside an APPLY_CONTINUOUS wrapper it did not need.

benji_the_piercing_wind was wrong three ways at once. The restriction was
RESTRICT_DEFENSE_TO_HEAD_EQUIPMENT, and the card says "can't be defended by
CARDS FROM HAND" — close to the opposite. Its power test was
ATTACK_PITCH_POWER_LTE, which reads the attack's PITCH value rather than its
{p}. And a restriction is created when a qualifying attack is declared, so it is
a trigger, not a continuous effect.

blessing_of_serenity_blue needed no wrapper at all: PREVENT_DAMAGE is already a
one-shot replacement consumed by the next matching damage, which is what "the
NEXT TIME your hero would be dealt {p} damage this turn" means.
"""
import copy

import pytest

import engine.actions as A
import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import load_all_cards, get_card
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

SMALL = "a_drop_in_the_ocean_blue"   # a low-power card to attack with


def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    return st


def _card(slug, owner=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = owner
    return c


def _declare_attack(st, attacker, power, pid=1):
    st.combat = CombatState(attacker_id=pid, link_id=1, attack_power=power,
                            attack_card=attacker, keywords=[])
    st.combat.base_attack_power = power
    st.combat.from_weapon = False
    st.combat.defender_restrictions = []


def _benji_attacks(st, power):
    atk = _card("wounded_bull_red")
    atk.base_power = power
    _declare_attack(st, atk, power)
    run_ability(get_card("benji_the_piercing_wind").abilities[0],
                _card("benji_the_piercing_wind"), None, st)
    return atk


def test_a_small_attack_cannot_be_defended_from_hand():
    st = _state()
    _benji_attacks(st, 2)

    hand_card = _card("wounded_bull_red", owner=2)
    assert A._restriction_blocks(st, hand_card, None) is True, (
        "a card defending from hand was still allowed")


def test_equipment_may_still_defend_it():
    """"cards from hand" is not "everything" — equipment is unaffected."""
    st = _state()
    _benji_attacks(st, 2)

    robe = _card("nullrune_robe", owner=2)
    assert A._restriction_blocks(st, robe, "chest") is False, (
        "the restriction blocked equipment too")


def test_a_bigger_attack_creates_no_restriction():
    """"with 2 or less {p}" — the half a pitch-value test would get wrong."""
    st = _state()
    _benji_attacks(st, 5)

    hand_card = _card("wounded_bull_red", owner=2)
    assert A._restriction_blocks(st, hand_card, None) is False, (
        "a 5-power attack restricted defenders")
    assert not st.combat.defender_restrictions


def test_a_weapon_attack_creates_no_restriction():
    """The card says attack ACTION cards."""
    st = _state()
    atk = _card("beckoning_mistblade")
    _declare_attack(st, atk, 1)
    st.combat.from_weapon = True
    run_ability(get_card("benji_the_piercing_wind").abilities[0],
                _card("benji_the_piercing_wind"), None, st)

    assert not st.combat.defender_restrictions


def test_benji_does_not_restrict_the_opponents_attacks():
    st = _state()
    atk = _card("wounded_bull_red", owner=2)
    atk.base_power = 1
    _declare_attack(st, atk, 1, pid=2)
    run_ability(get_card("benji_the_piercing_wind").abilities[0],
                _card("benji_the_piercing_wind", owner=1), None, st)

    assert not st.combat.defender_restrictions, (
        "Benji restricted defenders against the OPPONENT's attack")


def test_blessing_of_serenity_registers_a_shield():
    """"The next time your hero would be dealt {p} damage this turn, prevent 1."""
    st = _state()
    card = _card("blessing_of_serenity_blue")

    before = len(st.effect_manager.replacement_effects)
    for eff in get_card("blessing_of_serenity_blue").abilities[0].effects:
        eff.fn(card, None, st)
    after = len(st.effect_manager.replacement_effects)

    assert after > before, "playing it registered no prevention shield"


def test_blessing_of_serenity_prevents_one_damage_once():
    from engine.effect_keywords import deal_damage, DamageType

    st = _state()
    card = _card("blessing_of_serenity_blue")
    for eff in get_card("blessing_of_serenity_blue").abilities[0].effects:
        eff.fn(card, None, st)

    hero = st.players[1].hero
    first = st.players[1].life

    def _hit(n):
        deal_damage(st, n, DamageType.PHYSICAL, 2, hero, "card",
                    damage_source_card=card)

    _hit(3)
    after_first = st.players[1].life
    _hit(3)
    after_second = st.players[1].life

    assert first - after_first == 2, "the first hit was not reduced by 1"
    assert after_first - after_second == 3, (
        "the shield was still up for the second hit; it is a ONE-SHOT")


@pytest.mark.parametrize("slug", ["benji_the_piercing_wind",
                                  "blessing_of_serenity_blue"])
def test_neither_still_uses_a_dead_static(slug):
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    raw = json.loads(next(root.rglob(f"{slug}.json")).read_text(encoding="utf-8"))
    types = [(a.get("ability_type") or "").upper() for a in raw.get("abilities") or []]
    assert "STATIC" not in types, types
