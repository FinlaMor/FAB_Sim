"""Material (CR 3.0.14 sub-cards) — a grant that must END when its source leaves.

"While this is under a permanent, that permanent has <property>." Eight corpus
cards: seven grant **phantasm**, one grants +1{p}, and six of the seven exclude
one specific dragon.

The design question is where the grant lives. Registering it when the sub-card
goes underneath is the obvious answer and is wrong: every path by which a
sub-card stops being under — banished to pay Nitro Mechanoid's cost, the top
card leaving the arena, the sub-card ceasing to exist — would have to unregister
it, and missing one leaves a permanent with phantasm forever. That is the same
"hook every call site" trap that the invented-flag class came from.

So it is DERIVED: two continuous effects registered once per game ask each card
what is under it at the moment of recalculation. "While" then holds by
construction rather than by remembering, which is what the last three tests here
actually check.
"""
import copy

import pytest

import engine.engine as E
from engine.card import Card, CardDB
from engine.card_effects.ability_keywords import material_grants
from engine.card_effects.dsl.effect_types import _do_transform
from engine.card_effects.dsl.loader import load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()


def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    # The bare test state never calls these (only new_game does), and Material
    # lives entirely in _setup_material_statics — without it every assertion
    # below would be testing nothing.
    E._setup_dsl_listeners(st)
    E._setup_material_statics(st)
    return st


def _token(st, slug, pid=1, name=None, subtypes=("Item",)):
    t = Card(slug=slug, name=name or slug, types=["Token"], subtypes=list(subtypes))
    t.owner = t.controller = pid
    st.players[pid].permanents.add(t)
    return t


def _under(st, sub_slug, top_slug="aether_ashwing", pid=1):
    """Put a sub-card under a freshly transformed permanent, the real path."""
    sub = _token(st, sub_slug, pid=pid)
    _do_transform(st, [sub], top_slug, pid)
    top = next(c for c in st.players[pid].permanents.cards if c.slug == top_slug)
    return sub, top


def _keywords_of(st, card):
    return st.continuous_effect_manager.recalculate(
        st, card, 'keywords', set(card.keywords or []))


def _power_of(st, card, base=None):
    base = card.base_power if base is None else base
    return st.continuous_effect_manager.recalculate(st, card, 'power', base or 0)


# --- the grant applies -----------------------------------------------------

def test_ash_grants_phantasm_to_what_it_is_under():
    st = _state()
    _sub, top = _under(st, "ash")
    assert "Phantasm" in _keywords_of(st, top)


def test_a_permanent_with_nothing_under_it_gets_nothing():
    st = _state()
    plain = _token(st, "aether_ashwing")
    assert "Phantasm" not in _keywords_of(st, plain)


def test_galvanic_bender_grants_power_not_a_keyword():
    # The one Material card that grants a NUMBER. It is the reason the derived
    # static is registered for prop='power' as well as prop='keywords'; with
    # only the keyword hook this card would silently do nothing.
    st = _state()
    _sub, top = _under(st, "galvanic_bender")
    top.base_power = 1
    assert _power_of(st, top) == 2


def test_material_grants_stack_from_several_sub_cards():
    st = _state()
    subs = [_token(st, "galvanic_bender") for _ in range(2)]
    _do_transform(st, subs, "aether_ashwing", 1)
    top = next(c for c in st.players[1].permanents.cards
               if c.slug == "aether_ashwing")
    top.base_power = 1
    assert _power_of(st, top) == 3


# --- the exception clause --------------------------------------------------

def test_dust_does_not_grant_phantasm_to_its_own_dragon():
    # "under a permanent OTHER THAN Vynserakai". The exception is the point of
    # the card — these exist to give a NON-dragon permanent phantasm — so
    # dropping it would hand phantasm to the one permanent it must not.
    st = _state()
    dragon = _token(st, "vynserakai")
    dust = _token(st, "dust_from_the_red_desert_red")
    st.players[1].permanents.remove(dust)
    dust.is_sub_card = True
    dust.top_card = dragon
    dragon.cards_underneath.append(dust)
    assert "Phantasm" not in _keywords_of(st, dragon)


def test_dust_grants_phantasm_to_any_other_permanent():
    st = _state()
    _sub, top = _under(st, "dust_from_the_red_desert_red")
    assert "Phantasm" in _keywords_of(st, top)


def test_each_dust_excludes_only_its_own_dragon():
    st = _state()
    other = _token(st, "cromai")
    dust = _token(st, "dust_from_the_red_desert_red")   # excludes Vynserakai
    st.players[1].permanents.remove(dust)
    dust.is_sub_card = True
    dust.top_card = other
    other.cards_underneath.append(dust)
    assert "Phantasm" in _keywords_of(st, other)


# --- the "while": the grant must END ---------------------------------------

def test_removing_the_sub_card_removes_the_grant():
    # The whole reason the grant is derived rather than registered. A registered
    # grant would still be here.
    st = _state()
    sub, top = _under(st, "ash")
    assert "Phantasm" in _keywords_of(st, top)
    top.cards_underneath.remove(sub)
    assert "Phantasm" not in _keywords_of(st, top), \
        "the grant outlived the sub-card it was read from"


def test_banishing_the_sub_card_as_a_cost_removes_the_grant():
    # Nitro Mechanoid's "banish a card from under this" is a real path by which
    # a sub-card leaves, and it goes nowhere near any grant bookkeeping.
    from engine.card_effects.dsl.cost_types import compile_cost
    st = _state()
    sub, top = _under(st, "galvanic_bender")
    top.base_power = 1
    assert _power_of(st, top) == 2
    can_pay, pay = compile_cost("BANISH_FROM_UNDER_SELF", {})
    assert can_pay(top, None, st) is True
    pay(top, None, st)
    assert _power_of(st, top) == 1, \
        "the +1{p} survived the sub-card being banished away"


def test_material_grants_reads_nothing_from_a_bare_card():
    st = _state()
    plain = _token(st, "aether_ashwing")
    assert material_grants(plain) == []


# --- the grant reaches combat ----------------------------------------------

def test_phantasm_reaches_the_attack_power_recalculation():
    # Registering at stage 6 (keywords) is what makes the grant visible to
    # combat.keywords, where every "X in combat.keywords" check reads it.
    st = _state()
    sub, top = _under(st, "ash")
    top.power = top.base_power = 1
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=1,
                            attack_card=top, keywords=[])
    st.combat.base_attack_power = 1
    E._recalculate_attack_power(st)
    assert "Phantasm" in (st.combat.keywords or [])


def test_material_power_reaches_the_attack_power_recalculation():
    st = _state()
    sub, top = _under(st, "galvanic_bender")
    top.power = top.base_power = 1
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=1,
                            attack_card=top, keywords=[])
    st.combat.base_attack_power = 1
    E._recalculate_attack_power(st)
    assert st.combat.attack_power == 2


def test_rake_the_embers_makes_one_ashwing_per_ash():
    # "into Aether AshwingS" — plural. All three under a single Ashwing would be
    # a different, strictly worse board state for the player.
    from engine.card_effects.dsl import dispatch
    st = _state()
    for _ in range(2):
        _token(st, "ash")
    card = copy.deepcopy(DB.get("rake_the_embers_red"))
    card.owner = card.controller = 1
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    wings = [c for c in st.players[1].permanents.cards
             if c.slug == "aether_ashwing"]
    assert len(wings) == 3, f"expected one Ashwing per ash, got {len(wings)}"
    assert all(len(w.cards_underneath) == 1 for w in wings)


def test_invoke_nekria_needs_an_ash():
    from engine.card_effects.dsl import dispatch
    st = _state()
    card = copy.deepcopy(DB.get("invoke_nekria_red"))
    card.owner = card.controller = 1
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert not [c for c in st.players[1].permanents.cards if c.slug == "nekria"]


# --- every Material card is declared the same way --------------------------

@pytest.mark.parametrize("slug", [
    "ash", "galvanic_bender",
    "dust_from_stillwater_shrine_red", "dust_from_the_chrome_caverns_red",
    "dust_from_the_fertile_fields_red", "dust_from_the_golden_plains_red",
    "dust_from_the_red_desert_red", "dust_from_the_shadow_crypts_red",
])
def test_every_material_card_declares_a_material_static(slug):
    from engine.card_effects.dsl.loader import get_card
    card_def = get_card(slug)
    assert card_def is not None, f"{slug} has no DSL definition"
    materials = [eff for ability in card_def.abilities
                 if (ability.ability_type or "").upper() == "STATIC"
                 for eff in ability.effects
                 if (eff.effect_type or "").upper() == "MATERIAL"]
    assert materials, f"{slug} prints Material but declares no MATERIAL static"
    params = materials[0].params or {}
    assert params.get("keyword") or params.get("power"), \
        f"{slug} declares MATERIAL but grants nothing"
