"""The ON_BANISH cycle: a trigger name that does not exist, hiding six bad tests.

Six MST cards read "when this hits a hero, banish the top card of their deck"
plus "whenever this banishes a <kind> card, <payoff>". The payoff was a second
ability triggered on ON_BANISH, which is not in TRIGGER_TO_EVENT — dispatch
falls back to the raw string and matches nothing, so it never ran.

Adding an ON_BANISH event is the obvious fix and the wrong one. The banish and
the payoff are the same ability on the same card: "whenever THIS banishes" can
only mean the banish this card just did. Since BANISH records what it banished
under the `banished` ref, the payoff is a CONDITIONAL in the same ability.

The dead trigger was also hiding six fabricated conditions, every one of which
adding the trigger would have ACTIVATED — pitch compared against the string
"BLUE", an AND wearing an OR's clothes, a test about the current attack standing
in for a test about the banished card, "same name" written as pitch 1.

Each payoff is checked BOTH ways: it fires on a matching card and does not fire
on a non-matching one. A one-sided test passes on a condition that is always
true, which is what several of these would have become.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.state import CombatState
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import load_all_cards, get_card
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()


def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    E._setup_dsl_listeners(st)
    # Only the OPPONENT's deck is emptied — these cards banish from it, so its
    # contents are the input under test. The caster's deck must be stocked or
    # "draw a card" is a silent no-op and the payoff looks like it did not fire.
    st.players[2].deck.cards = []
    st.players[1].deck.cards = [_card("wounded_bull_red", owner=1, zone="deck")
                                for _ in range(5)]
    return st


def _card(slug, owner=1, zone=None):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = owner
    if zone is not None:
        c.zone = zone
    return c


def _stack_their_deck(st, *cards):
    """Top of deck first."""
    for c in cards:
        c.owner = c.controller = 2
        c.zone = "deck"
    st.players[2].deck.cards = list(cards)


def _fire(slug, st):
    """Run the card's ON_HIT ability — banish and payoff together.

    The ability is gated on ATTACK_TARGET_IS_HERO, which reads real combat
    state: attack_target is set only when the attack was declared against a
    permanent, so a hero attack leaves it None. Without a CombatState the gate
    fails and the whole ability is skipped — including the banish — so the
    payoff assertions would pass for the wrong reason.
    """
    card = _card(slug)
    st.combat = CombatState(attacker_id=1, link_id=1,
                            attack_power=card.power or 0,
                            attack_card=card, keywords=[])
    st.combat.attack_target = None
    ability = get_card(slug).abilities[0]
    before = st.players[1].life
    hand_before = len(st.players[1].hand.cards)
    run_ability(ability, card, None, st)
    return (st.players[1].life - before,
            len(st.players[1].hand.cards) - hand_before)


def _blue():
    return _card("art_of_desire_mind_blue", owner=2)      # pitch 3


def _red():
    return _card("wounded_bull_red", owner=2)             # pitch 1


def test_art_of_desire_pays_off_only_on_a_blue_banish():
    """"Whenever this banishes a BLUE card, draw a card and gain 1{h}"."""
    st = _state()
    _stack_their_deck(st, _blue())
    life, drawn = _fire("art_of_desire_mind_blue", st)
    assert (life, drawn) == (1, 1), f"blue banish paid {life} life, {drawn} cards"

    st = _state()
    _stack_their_deck(st, _red())
    life, drawn = _fire("art_of_desire_mind_blue", st)
    assert (life, drawn) == (0, 0), "a RED banish paid off"


@pytest.mark.parametrize("slug", ["impulsive_desire_blue"])
def test_reaction_or_instant_is_an_or_not_an_and(slug):
    """"banishes a REACTION or INSTANT card" — either one, not both.

    Authored as two AND-ed conditions, which demanded a single card be both.
    """
    st = _state()
    reaction = _red()
    reaction.types = ["DefenseReaction"]
    _stack_their_deck(st, reaction)
    life, _ = _fire(slug, st)
    assert life == 1, "a reaction alone did not pay off"

    st = _state()
    instant = _red()
    instant.types = ["Instant"]
    _stack_their_deck(st, instant)
    life, _ = _fire(slug, st)
    assert life == 1, "an instant alone did not pay off"

    st = _state()
    plain = _red()
    plain.types = ["Action"]
    plain.subtypes = ["Attack"]
    _stack_their_deck(st, plain)
    life, _ = _fire(slug, st)
    assert life == 0, "an attack action paid off"


def test_minds_desire_wants_a_non_attack_action():
    """"a NON-ATTACK ACTION card" — is an action AND is not an attack."""
    st = _state()
    non_attack = _red()
    non_attack.types = ["Action"]
    non_attack.subtypes = []
    _stack_their_deck(st, non_attack)
    life, _ = _fire("minds_desire_red", st)
    assert life == 1, "a non-attack action did not pay off"

    st = _state()
    attack_action = _red()
    attack_action.types = ["Action"]
    attack_action.subtypes = ["Attack"]
    _stack_their_deck(st, attack_action)
    life, _ = _fire("minds_desire_red", st)
    assert life == 0, "an ATTACK action paid off"


def test_bonds_of_attraction_needs_another_card_of_the_same_colour():
    """"banishes a card AND this has banished ANOTHER with the same colour".

    Both banishes happen in one resolution: top of deck, then their graveyard.
    """
    st = _state()
    _stack_their_deck(st, _blue())
    gy = _blue()
    gy.zone = "graveyard"
    st.players[2].graveyard.cards = [gy]

    life, _ = _fire("bonds_of_attraction_red", st)
    assert life == 1, "two blue cards did not pay off"

    st = _state()
    _stack_their_deck(st, _blue())
    other = _red()
    other.zone = "graveyard"
    st.players[2].graveyard.cards = [other]
    life, _ = _fire("bonds_of_attraction_red", st)
    assert life == 0, "a blue and a red paid off as 'the same colour'"


def test_bonds_of_memory_needs_another_card_of_the_same_name():
    st = _state()
    _stack_their_deck(st, _blue())
    same = _blue()
    same.zone = "graveyard"
    st.players[2].graveyard.cards = [same]
    life, _ = _fire("bonds_of_memory_yellow", st)
    assert life == 1, "two cards of the same name did not pay off"

    st = _state()
    _stack_their_deck(st, _blue())
    other = _card("wounded_bull_red", owner=2)
    other.zone = "graveyard"
    st.players[2].graveyard.cards = [other]
    life, _ = _fire("bonds_of_memory_yellow", st)
    assert life == 0, "two DIFFERENT names paid off as 'the same name'"


def test_a_single_banish_is_not_another_card():
    """"ANOTHER card with the same X" — one card trivially matches itself, and
    reading the list against itself would make the condition always true."""
    from engine.card_effects.dsl.condition_types import compile_condition
    from engine.context import push_refs, pop_refs, set_ref

    st = _state()
    fn = compile_condition("REF_MATCHES_OTHER",
                           {"ref": "banished_cards", "property": "name"})
    only = _blue()
    push_refs()
    try:
        set_ref("banished_cards", [only])
        assert fn(only, None, st) is False, "one card matched itself"
        set_ref("banished_cards", [only, _blue()])
        assert fn(only, None, st) is True
    finally:
        pop_refs()


def test_no_card_still_triggers_on_the_nonexistent_on_banish():
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "engine/card_effects/json"
    offenders = []
    for path in root.rglob("*.json"):
        if path.stem.endswith("_work_queue") or any(
                p.startswith(".") for p in path.parts):
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        for ability in raw.get("abilities") or []:
            if (ability.get("trigger") or "").upper() == "ON_BANISH":
                offenders.append(path.stem)
    assert not offenders, (
        f"ON_BANISH is not a trigger name; these never fire: {sorted(set(offenders))}")
