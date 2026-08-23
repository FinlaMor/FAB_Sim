""""Destroy a GOLD you control" destroyed whatever you controlled.

DESTROY_PERMANENT exists twice - as an effect and as a cost - and the two read
DIFFERENT subsets of the same vocabulary. The effect knew `subtype`, the cost
knew `slug`/`permanent_type`, and NEITHER knew `asset`, which is the word both
cards that need it actually use.

With no filter the cost is not merely weaker:

  raise_an_army_yellow  "as an additional cost, destroy X Gold you control" was
                        payable with no Gold at all (can_pay only asked whether
                        the player controlled ANY permanent) and paying it ate
                        an arbitrary permanent instead. It also ignored
                        `amount`, so "destroy X" destroyed one.
  scurv_stowaway        the same, plus its {t} was missing from the cost.

And two "up to" cards counted wrong in the card's favour:

  argh_smash_yellow     "destroy UP TO X ITEMS" wrote the item restriction as
                        target:"ITEM" (read as a target keyword, not a subtype)
                        and "up to" as max:true (a third spelling of up_to), so
                        it destroyed exactly X ARBITRARY permanents, opponent
                        only.
  renounce_violence     "destroy UP TO 3 Might tokens, create a Toughness token
                        FOR EACH DESTROYED THIS WAY" destroyed exactly ONE and
                        created THREE. Three tokens for one.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.cost_types import compile_cost
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()


def _card(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _state(agent=None):
    st = _make_state()
    st.card_db = DB
    pick = agent or (lambda s, o, context="": o[0])
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    st.individual_turns = 1
    return st


def _token(st, slug, pid=1, n=1):
    from engine.effect_keywords import create_token
    for _ in range(n):
        create_token(st, target_player_id=pid, token_slug=slug, number=1)
    return [c for c in st.players[pid].permanents.cards if c.slug == slug]


def _perms(st, pid=1):
    return [c.slug for c in st.players[pid].permanents.cards]


def _force_roll(monkeypatch, value):
    """Pin the die. engine.effect_keywords.roll uses the GLOBAL random module,
    so there is no state hook to seed - an `st.rng_queue` attribute is simply
    ignored, and a test that sets one is FLAKY rather than deterministic: X is
    half the roll, so it is 0 whenever the die shows 1."""
    import random as _random
    import engine.effect_keywords as _ek
    monkeypatch.setattr(_ek.random, "randint", lambda a, b, _v=value: _v)


def _cost_of(slug, index, kind="DESTROY_PERMANENT"):
    """The card's OWN cost params, so this pins the card rather than a
    restatement of it."""
    ability = get_card(slug).abilities[index]
    costs = list(getattr(ability, "costs", None) or [])
    costs += list(getattr(ability, "additional_costs", None) or [])
    spec = [c for c in costs if c.cost_type == kind]
    assert spec, f"{slug} ability[{index}] has no {kind} cost any more"
    return spec[0].params


# --- the cost ---------------------------------------------------------------

def test_scurv_cannot_pay_without_a_gold():
    st = _state()
    source = _card("scurv_stowaway")
    _token(st, "seismic_surge") if DB.get("seismic_surge") else None
    # A permanent that is NOT a Gold.
    other = _card("scurv_stowaway")
    st.players[1].permanents.add(other)

    can_pay, _pay = compile_cost("DESTROY_PERMANENT", _cost_of("scurv_stowaway", 0))

    assert can_pay(source, None, st) is False, (
        "the ability is payable with no Gold, on any permanent at all")


def test_scurv_pays_by_destroying_the_gold_not_something_else():
    st = _state()
    source = _card("scurv_stowaway")
    keeper = _card("scurv_stowaway")
    st.players[1].permanents.add(keeper)
    golds = _token(st, "gold", n=1)
    assert golds, "no Gold token was created"

    can_pay, pay = compile_cost("DESTROY_PERMANENT", _cost_of("scurv_stowaway", 0))
    assert can_pay(source, None, st) is True
    pay(source, None, st)

    assert "gold" not in _perms(st), "the Gold was not destroyed"
    assert keeper in st.players[1].permanents.cards, (
        "it destroyed an arbitrary permanent instead of the Gold")


def test_raise_an_army_needs_x_golds_not_x_permanents():
    st = _state()
    source = _card("raise_an_army_yellow")
    # X comes off the CARD (x_paid, set when the X cost is paid), not the state.
    source.x_paid = 2
    for _ in range(3):
        st.players[1].permanents.add(_card("scurv_stowaway"))
    _token(st, "gold", n=1)

    can_pay, _pay = compile_cost("DESTROY_PERMANENT",
                                 _cost_of("raise_an_army_yellow", 0))

    # One Gold, three other permanents: X=2 must not be payable.
    assert can_pay(source, None, st) is False, (
        "three non-Gold permanents paid a cost of two Gold")


def test_raise_an_army_destroys_the_number_it_asks_for():
    st = _state()
    source = _card("raise_an_army_yellow")
    source.x_paid = 2
    _token(st, "gold", n=3)
    assert _perms(st).count("gold") == 3

    _can, pay = compile_cost("DESTROY_PERMANENT",
                             _cost_of("raise_an_army_yellow", 0))
    pay(source, None, st)

    left = _perms(st).count("gold")
    assert left == 1, f"expected 2 Gold destroyed, {3 - left} were"


# --- argh_smash_yellow ------------------------------------------------------

def test_argh_smash_destroys_only_items(monkeypatch):
    st = _state()
    _force_roll(monkeypatch, 6)          # X = 6 // 2 = 3, enough to reach both
    item = _card("absorption_dome_yellow", 2)
    other = _card("scurv_stowaway", 2)
    st.players[2].permanents.add(item)
    st.players[2].permanents.add(other)

    run_ability(get_card("argh_smash_yellow").abilities[0],
                _card("argh_smash_yellow"), None, st)

    assert item not in st.players[2].permanents.cards, (
        "the Item survived, so this test would pass without any filter at all")
    assert other in st.players[2].permanents.cards, (
        "it destroyed a permanent that is not an Item")


def test_argh_smash_reaches_both_sides(monkeypatch):
    """"Destroy up to X items", unqualified - it was scoped to the OPPONENT."""
    st = _state()
    _force_roll(monkeypatch, 6)
    mine = _card("absorption_dome_yellow", 1)
    st.players[1].permanents.add(mine)

    run_ability(get_card("argh_smash_yellow").abilities[0],
                _card("argh_smash_yellow"), None, st)

    assert mine not in st.players[1].permanents.cards, (
        "an Item on the caster's own side was not a legal target")


def test_argh_smash_destroys_nothing_on_a_roll_of_one(monkeypatch):
    """X is HALF the roll rounded down, so a 1 destroys nothing. Both tests
    above were seeded with an attribute the engine does not read and passed in
    isolation by luck; this pins the other end of the range."""
    st = _state()
    _force_roll(monkeypatch, 1)
    item = _card("absorption_dome_yellow", 2)
    st.players[2].permanents.add(item)

    run_ability(get_card("argh_smash_yellow").abilities[0],
                _card("argh_smash_yellow"), None, st)

    assert item in st.players[2].permanents.cards, (
        "a roll of 1 destroyed an item; X should be 0")


# --- renounce_violence_blue -------------------------------------------------

def test_renounce_creates_one_toughness_per_might_destroyed():
    st = _state()
    _token(st, "might", n=2)
    assert _perms(st).count("might") == 2

    run_ability(get_card("renounce_violence_blue").abilities[0],
                _card("renounce_violence_blue"), None, st)

    perms = _perms(st)
    assert perms.count("might") == 0, "not every Might was destroyed"
    assert perms.count("toughness") == 2, (
        f"expected 2 Toughness for 2 Might destroyed, got "
        f"{perms.count('toughness')}")


def test_renounce_destroys_at_most_three():
    st = _state()
    _token(st, "might", n=5)

    run_ability(get_card("renounce_violence_blue").abilities[0],
                _card("renounce_violence_blue"), None, st)

    perms = _perms(st)
    assert perms.count("might") == 2, (
        f"\"up to 3\" destroyed {5 - perms.count('might')}")
    assert perms.count("toughness") == 3


def test_renounce_creates_nothing_with_no_might():
    """It created three Toughness unconditionally - three tokens for none."""
    st = _state()

    run_ability(get_card("renounce_violence_blue").abilities[0],
                _card("renounce_violence_blue"), None, st)

    assert "toughness" not in _perms(st), (
        "it created Toughness tokens with no Might to destroy")


def test_a_dynamic_cost_amount_is_not_flattened_to_zero():
    """compile_cost coerces any non-integer string `amount` to 0 so the simple
    branches cannot blow up on arithmetic. Its stated reason was that no cost
    branch interprets a marker - no longer true, and flattening made "destroy X
    Gold" destroy ZERO: a mandatory additional cost that is free."""
    from engine.card_effects.dsl.cost_types import compile_cost as _cc

    st = _state()
    source = _card("raise_an_army_yellow")
    source.x_paid = 3
    _token(st, "gold", n=2)

    can_pay, _pay = _cc("DESTROY_PERMANENT", {"asset": "gold", "amount": "X"})

    assert can_pay(source, None, st) is False, (
        "X was flattened to 0, so the cost was payable with too few Gold")

    _token(st, "gold", n=1)
    assert can_pay(source, None, st) is True
