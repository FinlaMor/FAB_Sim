"""Shield Bash read every clause off the wrong object, and then did nothing.

Printed: "If a Guardian off-hand with 1 or more {d} is DEFENDING this chain
link, deal 1 damage to the attacking hero unless THEY discard a card."

THE CONDITIONS WERE ALL ABOUT THE ATTACK. ATTACK_CLASS_IN, ATTACK_SUBTYPE_IN and
ATTACK_PITCH_POWER_GTE, on a card whose sentence is about the DEFENDER -- and
the third asked about pitch power rather than {d} as well. Three conditions,
three wrong objects, and the card still compiled and validated.

THE EFFECT DID NOTHING. PAY_OR_DAMAGE reads `amount` as RESOURCES and defaults
`damage` to 0, and it is entirely self-targeted. So `{"amount": 1, "cost":
[{"type": "DISCARD_CARD"}]}` asked the card's OWN controller to pay a resource
the card never mentions, in order to avoid zero damage, and dropped the discard
entirely. There is no state in which it did anything.

WHY NOT A MAY. loan_shark_yellow expresses the same "unless you discard a card"
wording by composing MAY + else, so composition looked like the precedent to
follow. It is not available here: MAY always prompts the CONTROLLER, and this
choice belongs to the ATTACKING hero. PAY_OR_ELSE already names a player and
already models "X unless they pay Y"; discarding is a third currency beside
resources and counters.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.card import Card, CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from tests.conftest import _make_combat, _make_state, owned_card

load_all_cards()
DB = CardDB()
SLUG = "shield_bash_blue"


def _state():
    st = _make_state()
    st.card_db = DB
    # Player 1 attacks; player 2 defends and controls Shield Bash.
    st.combat = _make_combat(attacker_id=1)
    st.combat.attack_target = None
    st.players[1].life = 20
    return st


def _defender(card_class="Guardian", subtypes=("OffHand",), defense=1):
    c = Card(slug="shield", name="Shield", raw_types=["Equipment"])
    c.types, c.subtypes = ["Equipment"], list(subtypes)
    c.classes = [card_class]
    c.defense = defense
    c.owner = c.controller = 2
    return c


def _hand(st, pid, n):
    for i in range(n):
        c = Card(slug="h_%d" % i, name="H%d" % i, raw_types=["Action"])
        c.types = ["Action"]
        c.owner = c.controller = pid
        st.players[pid].hand.add(c)


def _ability():
    return get_card(SLUG).abilities[0]


def _gate(st):
    card = owned_card(2, SLUG)
    return all(c.fn is None or c.fn(card, None, st) for c in _ability().conditions)


def _resolve(st, choice):
    st.player_agents[1] = lambda s, options, context="", **kw: (
        choice if choice in options else options[0])
    run_ability(_ability(), owned_card(2, SLUG), None, st)


# --- the condition is about the DEFENDER -------------------------------------

def test_it_fires_for_a_guardian_off_hand_with_defence():
    st = _state()
    st.combat.defending_cards = [_defender()]
    assert _gate(st)


def test_it_does_not_fire_for_the_wrong_class():
    st = _state()
    st.combat.defending_cards = [_defender(card_class="Ninja")]
    assert not _gate(st)


def test_it_does_not_fire_for_a_non_off_hand():
    st = _state()
    st.combat.defending_cards = [_defender(subtypes=("OneHanded",))]
    assert not _gate(st)


def test_it_does_not_fire_for_zero_defence():
    st = _state()
    st.combat.defending_cards = [_defender(defense=0)]
    assert not _gate(st), "'with 1 or more {d}' excludes a 0-defence off-hand"


def test_it_does_not_read_the_attack():
    """The old conditions asked about the attacking card. A Guardian off-hand
    defender with a non-Guardian attack must still qualify -- and did not."""
    st = _state()
    attacker = Card(slug="atk", name="Atk", raw_types=["Action"])
    attacker.types, attacker.subtypes = ["Action"], ["Attack"]
    attacker.classes = ["Ninja"]
    attacker.owner = attacker.controller = 1
    st.combat.attack_card = attacker
    st.combat.defending_cards = [_defender()]
    assert _gate(st)


# --- the choice belongs to the attacking hero --------------------------------

def test_the_attacking_hero_may_discard_to_avoid_the_damage():
    st = _state()
    st.combat.defending_cards = [_defender()]
    _hand(st, 1, 3)

    _resolve(st, "pay")

    assert len(st.players[1].hand.cards) == 2, "the attacker did not discard"
    assert st.players[1].life == 20, "they discarded AND took the damage"


def test_declining_takes_the_damage():
    st = _state()
    st.combat.defending_cards = [_defender()]
    _hand(st, 1, 3)

    _resolve(st, "decline")

    assert len(st.players[1].hand.cards) == 3
    assert st.players[1].life == 19, "declining did not deal the damage"


def test_an_empty_hand_simply_takes_the_damage():
    st = _state()
    st.combat.defending_cards = [_defender()]

    _resolve(st, "pay")

    assert st.players[1].life == 19, (
        "a player with no cards cannot pay, so the penalty happens")


def test_the_defender_is_not_the_one_paying():
    """PAY_OR_DAMAGE charged the card's own controller. Shield Bash's controller
    is the DEFENDING player and should neither discard nor take damage."""
    st = _state()
    st.combat.defending_cards = [_defender()]
    _hand(st, 1, 2)
    _hand(st, 2, 2)
    st.players[2].life = 20

    _resolve(st, "decline")

    assert len(st.players[2].hand.cards) == 2, "the defender discarded"
    assert st.players[2].life == 20, "the defender took its own damage"
