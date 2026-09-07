"""Reprise: "the defending hero has defended with a card FROM THEIR HAND".

Equipment defends for free every turn, so "defended with a card from hand" is
the whole point of the keyword -- a condition that counted any defender would
be true in almost every combat and the Reprise clause would stop being a
clause.

    overpower blue/yellow/red   +2/+3/+4, INSTEAD +4/+5/+6 on a reprise
    out_for_blood_blue          +1, and on a reprise your NEXT attack gains +1

THE TWO CARDS DIFFER IN A WAY THAT IS EASY TO FLATTEN. Overpower says
"instead", so exactly one pump happens: written as an unconditional +2 plus a
conditional +4, a reprised attack would gain +6 rather than +4. Out for Blood
has no "instead", so its base pump is unconditional and only the extra is
gated, and it lands on the NEXT attack rather than this one. Both mistakes
produce a card that works in the common case and is wrong in the case the
keyword exists for.

THE THREE OVERPOWER PRINTINGS ARE AUTHORED SEPARATELY, not derived. They differ
in BOTH numbers, and the copier allows one substitution: two distinct
differences mean two clauses changed with nothing to say which JSON value is
which.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from tests.conftest import _make_state, attack_with, recalculate_attack

load_all_cards()
DB = CardDB()

OVERPOWER = {"overpower_blue": (2, 4),
             "overpower_yellow": (3, 5),
             "overpower_red": (4, 6)}


def _card(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _weapon_attack(reprise):
    """A weapon attack on the chain, optionally reprised."""
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="", **kw: o[0]      # noqa: E731
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    weapon = _card(_a_weapon())
    attack_with(st, weapon)
    st.combat.from_weapon = True
    st.combat.defender_used_hand_card = reprise
    return st, weapon


def _a_weapon():
    import io, json
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    idx = json.load(io.open(root / "card_data" / "slug_index.json",
                            encoding="utf-8"))["by_slug"]
    return next(s for s, e in idx.items()
                if "Weapon" in (e.get("types") or []) and (e.get("power") or 0) > 0
                and DB.get(s))


def _play(st, slug):
    run_ability(get_card(slug).abilities[0], _card(slug), None, st)


def test_the_probe_really_is_a_weapon():
    """Guards every test here: the reaction targets a WEAPON attack, so a probe
    that was not one would make every pump silently do nothing."""
    assert "Weapon" in (DB.get(_a_weapon()).types or [])


# --------------------------------------------------------------- overpower

@pytest.mark.parametrize("slug", sorted(OVERPOWER))
def test_overpower_gives_its_base_pump_without_a_reprise(slug):
    base, _reprised = OVERPOWER[slug]
    st, weapon = _weapon_attack(reprise=False)
    _play(st, slug)
    assert recalculate_attack(st) == (weapon.base_power or 0) + base


@pytest.mark.parametrize("slug", sorted(OVERPOWER))
def test_overpower_replaces_the_pump_on_a_reprise(slug):
    """"INSTEAD" -- one pump, not both. A card that added them would give
    base+reprised here, which is the commonest way this text is got wrong."""
    base, reprised = OVERPOWER[slug]
    st, weapon = _weapon_attack(reprise=True)
    _play(st, slug)
    got = recalculate_attack(st)
    assert got == (weapon.base_power or 0) + reprised, (
        "expected the reprised pump alone; base+reprised would be %d"
        % ((weapon.base_power or 0) + base + reprised))


def test_the_three_printings_really_do_differ():
    """The premise for authoring them separately. If two ever printed the same
    numbers, one of them should be derived instead of hand-kept in sync."""
    assert len({v for v in OVERPOWER.values()}) == 3


# ------------------------------------------------------------ out for blood

def test_out_for_blood_pumps_unconditionally():
    """No "instead" here: the base pump happens whether or not it reprised."""
    st, weapon = _weapon_attack(reprise=False)
    _play(st, "out_for_blood_blue")
    assert recalculate_attack(st) == (weapon.base_power or 0) + 1


def test_out_for_blood_adds_nothing_to_this_attack_on_a_reprise():
    """Its reprise pays the NEXT attack. A card that used MODIFY_ATTACK for it
    would double this one instead, which no assertion about the next attack
    would notice."""
    st, weapon = _weapon_attack(reprise=True)
    _play(st, "out_for_blood_blue")
    assert recalculate_attack(st) == (weapon.base_power or 0) + 1


def test_out_for_blood_pays_the_next_attack_on_a_reprise():
    st, _weapon = _weapon_attack(reprise=True)
    _play(st, "out_for_blood_blue")
    st.combat = None
    nxt = attack_with(st, _card(_a_weapon()))
    assert recalculate_attack(st) == (nxt.base_power or 0) + 1


def test_out_for_blood_pays_nothing_forward_without_a_reprise():
    st, _weapon = _weapon_attack(reprise=False)
    _play(st, "out_for_blood_blue")
    st.combat = None
    nxt = attack_with(st, _card(_a_weapon()))
    assert recalculate_attack(st) == (nxt.base_power or 0)
