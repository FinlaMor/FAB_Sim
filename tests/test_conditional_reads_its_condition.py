"""CONDITIONAL/IF read `when` and `if`, but six cards spell the test `condition`.

`compile_effect("CONDITIONAL", ...)` built its test from `params.get("when",
params.get("if", []))`. A card supplying `condition` therefore got an EMPTY
test list, `ok` stayed True, and the `then` branch ran every single time.

This is the worst shape an unread parameter takes. An effect that does nothing
looks broken the first time someone plays the card; a branch that always fires
looks like the card working.

Three of the six also had tests that could never be True — a zone spelling
CARD_IN_ZONE does not know, a colour passed where an int was compared, a ref
that was never stored. Honouring those would have swapped "always" for "never",
which is not a fix, so they are corrected here too. Each test below drives the
compiled effect and asserts the branch runs in one case and not the other.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.loader import load_all_cards, get_card
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

BLUE = "art_of_desire_mind_blue"    # pitch 3
YELLOW = "bonds_of_memory_yellow"   # pitch 2
RED = "wounded_bull_red"            # pitch 1


def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    return st


def _stack(st, pid, zone, slug, n=4):
    cards = []
    for _ in range(n):
        c = copy.deepcopy(DB.get(slug))
        c.owner = c.controller = pid
        cards.append(c)
    getattr(st.players[pid], zone).cards = cards


def _attacking_a_hero(st, slug, owner=1):
    """Excessive Bloodloss reads "When this HITS A HERO", and the gate for that
    (ATTACK_TARGET_IS_HERO) is false when there is no combat at all. The
    original fixture ran the ability with combat None, which passed only while
    the gate was missing -- so the combat is part of the premise, not scenery.
    """
    from engine.state import CombatState
    card = _card(slug, owner)
    card.zone = "combat_chain"
    st.combat = CombatState(attacker_id=owner, link_id=1, attack_power=4,
                            attack_card=card, keywords=[], from_weapon=False)
    st.combat.attack_target = None      # None means the attack is at the hero
    return card


def _card(slug, owner=1):
    c = copy.deepcopy(DB.get(slug))
    c.owner = c.controller = owner
    return c


def _run(slug, st, card=None):
    """Drive the real ability path.

    Calling `eff.fn` directly skips the reference scope run_ability pushes, so
    every set_ref inside would be dropped and every ref test answer None —
    which is exactly the "always False" failure these cards already had.
    """
    from engine.card_effects.dsl.interpreter import run_ability
    card = card or _card(slug)
    run_ability(get_card(slug).abilities[0], card, None, st)


@pytest.mark.parametrize("top,expected_loss", [(BLUE, 1), (RED, 0)])
def test_vile_inquisition_only_drains_on_a_blue_banish(top, expected_loss):
    """"banishes the top card of their deck. If it's blue, THEY lose 1{h}."""
    st = _state()
    _stack(st, 2, "deck", top)
    before = st.players[2].life
    mine = st.players[1].life

    _run("vile_inquisition_blue", st)

    assert before - st.players[2].life == expected_loss
    # The caster's own 2 life is the card's PAY_LIFE additional cost, so it is
    # the same either way. Pinning it constant is what proves the conditional
    # 1{h} landed on the opponent rather than on the player who cast it.
    assert mine - st.players[1].life == 2


@pytest.mark.parametrize("top,expected_banished", [(RED, 2), (BLUE, 1)])
def test_excessive_bloodloss_repeats_only_on_red(top, expected_banished):
    """"banish the top card of their deck. If it's red, repeat this process."""
    st = _state()
    _stack(st, 2, "deck", top, n=5)
    card = _attacking_a_hero(st, "excessive_bloodloss_blue")

    _run("excessive_bloodloss_blue", st, card)

    assert len(st.players[2].banished.cards) == expected_banished


@pytest.mark.parametrize("top,expected_soul", [(YELLOW, 1), (RED, 0)])
def test_soul_bond_belief_souls_only_a_yellow_reveal(top, expected_soul):
    """"reveal the top card of your deck. If it's yellow, put it into your soul."""
    st = _state()
    _stack(st, 1, "deck", top)
    st.players[1].soul.cards = []

    _run("soul_bond_belief_red", st)

    assert len(st.players[1].soul.cards) == expected_soul


def test_a_bare_condition_dict_is_accepted():
    """Cards give the test as one dict, not a list of one."""
    from engine.card_effects.dsl.effect_types import compile_effect
    st = _state()
    _stack(st, 1, "deck", RED)
    card = _card(RED)

    from engine.context import push_refs, pop_refs
    push_refs()
    ran = compile_effect("CONDITIONAL", {
        "condition": {"type": "REF_PITCH_IS", "ref": "nothing_here",
                      "color": "blue"},
        "then": [{"type": "LOSE_LIFE", "amount": 3}]})
    before = st.players[1].life
    try:
        ran(card, None, st)
    finally:
        pop_refs()
    assert st.players[1].life == before, "branch ran with an unmet condition"


def test_banish_records_what_it_banished():
    """The ref the "if it's <colour>" tests ask about."""
    from engine.context import get_ref, push_refs, pop_refs
    st = _state()
    _stack(st, 2, "deck", BLUE)

    push_refs()
    try:
        get_card("vile_inquisition_blue").abilities[0].effects[0].fn(
            _card("vile_inquisition_blue"), None, st)
        banished = get_ref("banished")
    finally:
        pop_refs()
    assert banished is not None and getattr(banished, "slug", None) == BLUE
