"""Three cards granted an ability from inside a STATIC, so it never existed.

Each held an INJECT_TRIGGER under a plain STATIC. Nothing dispatches a plain
STATIC, so the trigger was never injected and the granted ability was never
real.

sting_of_sorcery_blue's was doubly unreachable: its INJECT_TRIGGER named
ON_ATTACK, which is dispatched only to the ATTACKING CARD's slug. An aura that
grants an ability to OTHER cards can never receive that event no matter how it
is dispatched. ON_PLAY_ACTIVATE_ATTACK reaches every permanent the attacker
controls, which is the hook a granting permanent actually needs.

shimmering_specter_yellow turned out not to be a granted ability at all — "when
THIS leaves the arena" is its own trigger, with "while this is attacking or
defending" as a condition on it.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.loader import load_all_cards, get_card
from engine.card_effects.dsl.interpreter import run_ability
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()


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


def _attack_with(st, attacker, pid=1, from_weapon=False):
    power = attacker.base_power or 0
    st.combat = CombatState(attacker_id=pid, link_id=1, attack_power=power,
                            attack_card=attacker, keywords=[])
    st.combat.base_attack_power = power
    st.combat.attack_target = None
    # ATTACK_IS_WEAPON reads combat.from_weapon, NOT the card's type -- a weapon
    # card in attack_card is not enough, and leaving it unset makes every attack
    # look like an action.
    st.combat.from_weapon = from_weapon


def test_sting_of_sorcery_pings_when_you_attack_with_an_action():
    """"Attack action cards you control gain 'when you attack with this, deal 1
    arcane damage to target hero.'"""
    st = _state()
    aura = _card("sting_of_sorcery_blue")
    st.players[1].permanents.cards.append(aura)

    atk = _card("wounded_bull_red")          # an attack ACTION card
    _attack_with(st, atk)
    before = st.players[2].life

    st.event_manager.emit('attacking', st)

    assert st.players[2].life == before - 1, (
        "attacking with an action card dealt no arcane damage")


def test_sting_of_sorcery_does_not_ping_on_a_weapon_attack():
    """The card says attack ACTION cards; the trigger fires for weapons too."""
    st = _state()
    aura = _card("sting_of_sorcery_blue")
    st.players[1].permanents.cards.append(aura)

    weapon = _card("beckoning_mistblade")
    _attack_with(st, weapon, from_weapon=True)
    before = st.players[2].life

    st.event_manager.emit('attacking', st)

    assert st.players[2].life == before, "a weapon attack pinged"


def test_sting_of_sorcery_does_nothing_without_the_aura():
    """Pairs the positive case: an unconditional ping would pass that alone."""
    st = _state()
    atk = _card("wounded_bull_red")
    _attack_with(st, atk)
    before = st.players[2].life

    st.event_manager.emit('attacking', st)

    assert st.players[2].life == before


def test_frost_hex_damages_you_for_each_frostbite():
    st = _state()
    hex_card = _card("frost_hex_blue")
    st.players[1].permanents.cards.append(hex_card)
    for _ in range(2):
        fb = _card("frostbite", owner=1)
        st.players[1].permanents.cards.append(fb)

    before = st.players[1].life
    opp_before = st.players[2].life
    st.event_manager.emit('start_of_end_phase', st)

    assert st.players[1].life == before - 2, (
        f"expected 2 arcane to its own controller, life went {before} -> "
        f"{st.players[1].life}")
    assert st.players[2].life == opp_before, "it damaged the opponent"


def test_frost_hex_does_nothing_with_no_frostbites():
    st = _state()
    st.players[1].permanents.cards.append(_card("frost_hex_blue"))
    before = st.players[1].life

    st.event_manager.emit('start_of_end_phase', st)

    assert st.players[1].life == before


def test_shimmering_specter_only_pays_off_while_in_combat():
    """"WHILE THIS IS ATTACKING OR DEFENDING, when this leaves the arena ..."."""
    st = _state()
    spectre = _card("shimmering_specter_yellow")
    ability = get_card("shimmering_specter_yellow").abilities[0]

    before = len(st.players[1].permanents.cards)
    run_ability(ability, spectre, None, st)          # no combat
    assert len(st.players[1].permanents.cards) == before, (
        "it made a Spectral Shield while not in combat")

    _attack_with(st, spectre)
    run_ability(ability, spectre, None, st)
    made = [c.slug for c in st.players[1].permanents.cards]
    assert any("spectral" in s for s in made), (
        f"no Spectral Shield while attacking: {made}")


@pytest.mark.parametrize("slug", ["frost_hex_blue", "sting_of_sorcery_blue",
                                  "shimmering_specter_yellow"])
def test_none_of_them_still_use_a_dead_static(slug):
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    raw = json.loads(next(root.rglob(f"{slug}.json")).read_text(encoding="utf-8"))
    types = [(a.get("ability_type") or "").upper() for a in raw.get("abilities") or []]
    assert "STATIC" not in types, types
