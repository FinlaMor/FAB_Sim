"""Transform (CR 8.5.36) and Sharpen — two keywords found by the parameter audit.

Both were discovered the same way: a card node whose TYPE was real but whose
parameters the compiler never read.

  * Three cards authored Transform as TRANSFORM_HERO, which is Arakni's "become
    a random Agent of Chaos". That is a real type doing something else entirely
    — no type-name audit can see it — and the ignored `to`/`from` keys were the
    only visible symptom.
  * brimming_blade_red was "+2{p} if a Sword is in your ARSENAL", nothing like
    its printed text, and its generated test passed only because CARD_IN_ZONE
    silently ignored `subtype`, degrading the condition to "is your arsenal
    non-empty".

CR 8.5.36 is specific in two ways worth pinning: transform puts the object UNDER
the permanent (3.0.14) rather than swapping or destroying it, and 8.5.36d makes
a multi-object transform ALL-OR-NOTHING.
"""
import copy

import pytest

from engine.card import Card, CardDB
from engine.card_effects.dsl import dispatch
from engine.card_effects.dsl.loader import load_all_cards
from engine.card_effects.dsl.effect_types import _do_transform
from engine.effect_keywords import TURN_EVENT_MARKER
from engine.state import CombatState
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


def _token(st, slug, pid=1, name=None, subtypes=("Item",)):
    """A token placed through Zone.add, so card.zone is set and the card can be
    found and moved later — appending to zone.cards leaves it half-present."""
    t = Card(slug=slug, name=name or slug, types=["Token"], subtypes=list(subtypes))
    t.owner = t.controller = pid
    st.players[pid].permanents.add(t)
    return t


# --- Transform: the keyword ------------------------------------------------

def test_transform_puts_the_object_under_the_permanent():
    # CR 8.5.36 / 3.0.14 — under, not swapped and not destroyed. The distinction
    # matters because 8.5.36a lets a permanent be asked what it transformed FROM.
    st = _state()
    ash = _token(st, "ash", name="Ash")
    _do_transform(st, [ash], "aether_ashwing", 1)
    wing = next(c for c in st.players[1].permanents.cards
                if c.slug == "aether_ashwing")
    assert ash in wing.cards_underneath
    assert ash.top_card is wing
    assert ash.is_sub_card is True


def test_transformed_object_leaves_its_zone():
    st = _state()
    ash = _token(st, "ash", name="Ash")
    _do_transform(st, [ash], "aether_ashwing", 1)
    assert ash not in st.players[1].permanents.cards, \
        "the ash is still a permanent in its own right as well as a sub-card"


def test_transform_creates_the_target_permanent():
    st = _state()
    ash = _token(st, "ash", name="Ash")
    _do_transform(st, [ash], "aether_ashwing", 1)
    assert [c for c in st.players[1].permanents.cards
            if c.slug == "aether_ashwing"], "the Aether Ashwing was never created"


def test_transform_grants_phantasm_to_what_the_ash_went_under():
    # Ash's printed Material ability. The grant is DERIVED at recalculation
    # rather than written onto card.keywords, so that removing the Ash removes
    # the phantasm — see test_material.py, which owns that behaviour. Asserted
    # here too because it is what makes the transform observable at all.
    import engine.engine as E
    st = _state()
    E._setup_material_statics(st)
    ash = _token(st, "ash", name="Ash")
    _do_transform(st, [ash], "aether_ashwing", 1)
    wing = next(c for c in st.players[1].permanents.cards
                if c.slug == "aether_ashwing")
    keywords = st.continuous_effect_manager.recalculate(
        st, wing, 'keywords', set(wing.keywords or []))
    assert "Phantasm" in keywords


def test_transform_of_nothing_does_nothing():
    st = _state()
    _do_transform(st, [], "aether_ashwing", 1)
    assert not [c for c in st.players[1].permanents.cards
                if c.slug == "aether_ashwing"]


# --- Transform: the cards --------------------------------------------------

def test_billowing_mirage_transforms_an_ash_on_attack():
    st = _state()
    ash = _token(st, "ash", name="Ash")
    card = _card("billowing_mirage_blue")
    atk = Card(slug="a", name="a", types=["Action"], subtypes=["Attack"])
    atk.owner = atk.controller = 1
    atk.power = atk.base_power = 3
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=atk, keywords=[])
    dispatch(st, "ON_ATTACK", card.slug, card=card, event=None)
    ashwings = [c for c in st.players[1].permanents.cards
                if c.slug == "aether_ashwing"]
    assert len(ashwings) == 1
    assert ash in ashwings[0].cards_underneath


def test_billowing_mirage_does_nothing_without_an_ash():
    st = _state()
    card = _card("billowing_mirage_blue")
    atk = Card(slug="a", name="a", types=["Action"], subtypes=["Attack"])
    atk.owner = atk.controller = 1
    atk.power = atk.base_power = 3
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=atk, keywords=[])
    dispatch(st, "ON_ATTACK", card.slug, card=card, event=None)
    assert not [c for c in st.players[1].permanents.cards
                if c.slug == "aether_ashwing"]


def test_dustup_creates_the_ash_before_transforming_it():
    # Order is the whole point: the token is created first, so the transform has
    # something to consume even when the player controlled no ash beforehand.
    st = _state()
    card = _card("dustup_blue")
    dispatch(st, "ON_HIT", card.slug, card=card, event=None)
    assert [c for c in st.players[1].permanents.cards
            if c.slug == "aether_ashwing"], \
        "the ash was created but not transformed — the two effects ran out of order"


def test_nitro_mechanoid_fails_entirely_when_a_part_is_missing():
    # CR 8.5.36d — all named objects must exist, otherwise NOTHING transforms.
    # A partial transform would eat the equipment and produce no Mechanoid.
    st = _state()
    for i in range(3):
        _token(st, "hyper_driver", name="Hyper Driver")
    card = _card("construct_nitro_mechanoid_yellow")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert not [c for c in st.players[1].permanents.cards
                if c.slug == "nitro_mechanoid"]
    assert len([c for c in st.players[1].permanents.cards
                if c.slug == "hyper_driver"]) == 3, \
        "the Hyper Drivers were consumed by a transform that could not complete"


# --- Sharpen ---------------------------------------------------------------

def _sword(st, pid=1):
    sword = Card(slug="a_sword", name="A Sword", types=["Weapon"],
                 subtypes=["Sword"])
    sword.owner = sword.controller = pid
    st.players[pid].weapon1.cards.append(sword)
    return sword


def test_sharpen_puts_power_counters_on_a_sword():
    st = _state()
    sword = _sword(st)
    card = _card("brimming_blade_red")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert sword.counters.get("power", 0) == 2


def test_sharpen_counters_raise_the_attack_power():
    # _recalculate_attack_power already adds card.counters['power'], which is
    # why sharpen needs no separate power plumbing — but if that ever changed,
    # sharpening would silently stop doing anything at all.
    import engine.engine as E
    st = _state()
    sword = _sword(st)
    sword.power = sword.base_power = 4
    card = _card("brimming_blade_red")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=4,
                            attack_card=sword, keywords=[])
    st.combat.base_attack_power = 4
    E._recalculate_attack_power(st)
    assert st.combat.attack_power == 6


def test_sharpen_ignores_a_weapon_that_is_not_a_sword():
    st = _state()
    axe = Card(slug="an_axe", name="An Axe", types=["Weapon"], subtypes=["Axe"])
    axe.owner = axe.controller = 1
    st.players[1].weapon1.cards.append(axe)
    card = _card("brimming_blade_red")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert axe.counters.get("power", 0) == 0
