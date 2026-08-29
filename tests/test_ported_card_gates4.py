"""Three more ported cards, written with the shared harness helpers.

    gang_robbery_yellow   "if you control 3 or more auras, this gets +3{p}"
    bark_obscenities_red  "your next attack that targets a GUARDIAN hero"
    hungry_for_more_red   "when this leaves the arena, gain 3{h}"

gang_robbery is the reason conftest.give_permanent exists. `player.auras` is a
SubZoneView matching `card.permanent_subtype`, and that attribute is set by
`auras.add()` -- not by the card having subtype "Aura". A first attempt used
`permanents.add()`, the aura count stayed zero, the buff never applied, and a
correct card looked broken. Again.

It also earns a leak test. Its WHILE_STATIC carries no SOURCE_IS_ATTACK, and
"THIS gets +3" that pumps whatever happens to be attacking is exactly the
defect class found in MODIFY_DEFENSE_VALUE. It does not leak -- statics are
registered against the attacking card -- and that is now pinned rather than
assumed.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from tests.conftest import (_make_state, attack_with, give_permanent,
                            owned_card, recalculate_attack)

load_all_cards()
DB = CardDB()


def _state():
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="": o[0]
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    return st


def _auras(st, pid, n):
    for i in range(n):
        give_permanent(st, pid, owned_card(pid, f"aura{i}", types=["Token"]),
                       subtype="Aura")


def _attacking(st, slug):
    card = copy.deepcopy(DB.get(slug))
    card.owner = card.controller = 1
    return attack_with(st, card)


# --- "if you control 3 or more auras" ---------------------------------------

def test_gang_robbery_pumps_at_three_auras():
    st = _state()
    _auras(st, 1, 3)
    card = _attacking(st, "gang_robbery_yellow")
    base = card.base_power or 0

    assert recalculate_attack(st) == base + 3, (
        f"expected +3 with 3 auras, got {recalculate_attack(st) - base}")


def test_gang_robbery_does_not_pump_at_two_auras():
    st = _state()
    _auras(st, 1, 2)
    card = _attacking(st, "gang_robbery_yellow")
    base = card.base_power or 0

    assert recalculate_attack(st) == base, (
        "pumped with only 2 auras -- the 3-aura threshold is not gating")


def test_gang_robbery_does_not_pump_someone_elses_attack():
    """Its WHILE_STATIC has no SOURCE_IS_ATTACK, and "THIS gets +3" that pumps
    whatever is attacking is the MODIFY_DEFENSE_VALUE defect in another
    costume. It does not, and that should stay true."""
    st = _state()
    _auras(st, 1, 3)
    robbery = copy.deepcopy(DB.get("gang_robbery_yellow"))
    robbery.owner = robbery.controller = 1
    st.players[1].permanents.add(robbery)

    other = owned_card(1, "other_attack", types=["Action"], base_power=4)
    other.subtypes = ["Attack"]
    attack_with(st, other)

    assert recalculate_attack(st) == 4, (
        "Gang Robbery pumped a DIFFERENT card's attack -- its static is "
        "leaking onto the combat rather than applying to itself")


# --- "your next attack that targets a GUARDIAN hero" ------------------------

def test_bark_obscenities_only_buffs_against_a_guardian():
    st = _state()
    st.players[2].hero.classes = ["Guardian"]
    src = copy.deepcopy(DB.get("bark_obscenities_red"))
    src.owner = src.controller = 1

    run_ability(get_card("bark_obscenities_red").abilities[0], src, None, st)

    attacker = owned_card(1, "some_attack", types=["Action"], base_power=3)
    attacker.subtypes = ["Attack"]
    attack_with(st, attacker)

    assert recalculate_attack(st) == 3 + 4, (
        "the queued +4 did not land on an attack against a Guardian hero")


def test_bark_obscenities_does_nothing_against_another_class():
    st = _state()
    st.players[2].hero.classes = ["Wizard"]
    src = copy.deepcopy(DB.get("bark_obscenities_red"))
    src.owner = src.controller = 1

    run_ability(get_card("bark_obscenities_red").abilities[0], src, None, st)

    attacker = owned_card(1, "some_attack", types=["Action"], base_power=3)
    attacker.subtypes = ["Attack"]
    attack_with(st, attacker)

    assert recalculate_attack(st) == 3, (
        "buffed an attack against a WIZARD hero -- the Guardian filter is not "
        "filtering")


# --- "when this leaves the arena, gain 3{h}" --------------------------------

def test_hungry_for_more_heals_when_it_leaves():
    st = _state()
    st.players[1].life = 10
    src = copy.deepcopy(DB.get("hungry_for_more_red"))
    src.owner = src.controller = 1

    run_ability(get_card("hungry_for_more_red").abilities[0], src, None, st)

    assert st.players[1].life == 13, (
        f"expected 3 life, went from 10 to {st.players[1].life}")


def test_hungry_for_more_heals_its_controller_not_the_opponent():
    """"gain 3{h}" is the controller. Civic Duty gave its token to the wrong
    hero exactly this way and no audit noticed."""
    st = _state()
    st.players[1].life = 10
    st.players[2].life = 10
    src = copy.deepcopy(DB.get("hungry_for_more_red"))
    src.owner = src.controller = 1

    run_ability(get_card("hungry_for_more_red").abilities[0], src, None, st)

    assert st.players[2].life == 10, "the OPPONENT gained the life"


# --- premise ----------------------------------------------------------------

def test_the_printed_text_still_says_what_these_assert():
    idx = json.loads((ROOT / "card_data" / "slug_index.json")
                     .read_text(encoding="utf-8"))["by_slug"]
    assert "3 or more auras" in (
        idx["gang_robbery_yellow"].get("functionalText") or "")
    assert "guardian hero" in (
        idx["bark_obscenities_red"].get("functionalText") or "").lower()
    assert "leaves the arena" in (
        idx["hungry_for_more_red"].get("functionalText") or "").lower()
