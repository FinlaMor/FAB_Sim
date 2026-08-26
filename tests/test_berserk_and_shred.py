"""Two cards whose every clause pointed at the wrong thing.

Berserk: "whenever you discard a random card with 6 or more {p}, BANISH IT. If
you do, reveal the top card of your deck. If it has 6 or more {p}, draw a card."

  banish it     a bare BANISH banishes from the TOP OF THE DECK by default, so
                the card milled its controller instead of banishing what was
                discarded.
  if it has 6+  authored as REF_PITCH_IS pitch: 6 -- a PITCH VALUE test on a
                scale that only runs 1 to 3. False for every card in the game.
  if you do     the payoff lived in a SECOND ability, so even a correct ref
                could not have reached it: a reference scope lasts exactly one
                ability execution.

Shred: "TARGET CARD DEFENDING an Assassin attack gets -3{d}." The target sat at
ABILITY level, which MODIFY_DEFENSE_VALUE does not read -- it reads a target in
its own params -- so the effect took the untargeted branch and moved the whole
defending TOTAL. With a single defender the two agree, which is why it looked
right; they part company exactly where the card is restrictive.

Not fixed, and said plainly in the card's _comment: Berserk's "until end of
turn" is a turn-scoped injected trigger, the DSL gap already on record. Worse,
_fire_on_discard dispatches ON_DISCARD only to a player's PERSISTENT cards
(weapons, items, auras, allies, permanents, hero); Berserk is an action in the
graveyard by then, so nothing delivers the trigger to it in a real game at all.
These tests therefore drive the ability directly. Fixing what the ability DOES
is still worth doing -- the delivery gap is one change away, and three wrong
clauses behind it would have survived it.
"""
from __future__ import annotations

import copy
import sys

import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import engine.engine as E
from engine.card import Card, CardDB
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.context import pop_refs, push_refs, set_ref
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()


def _state():
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="": o[0]
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    st.individual_turns = 1
    return st


def _action(slug, pid=1, power=None):
    c = Card(slug=slug, name=slug, types=["Action"], subtypes=["Attack"])
    c.owner = c.controller = pid
    if power is not None:
        c.raw_power = power
        c.power = power
    return c


# --- berserk_yellow ---------------------------------------------------------

def _berserk(st, discarded, deck_top):
    """Run the ability with `discarded` already in the register the engine's
    discard path writes -- which is how the trigger actually reaches it."""
    for c in deck_top:
        st.players[1].deck.add(c)
    src = copy.deepcopy(DB.get("berserk_yellow"))
    src.owner = src.controller = 1
    # run_ability, not eff.fn: effect-level `conditions` are a gate the
    # INTERPRETER evaluates, so calling the compiled functions directly runs
    # every effect unconditionally and would pass whatever the gate does.
    push_refs()
    try:
        set_ref("discarded", discarded)
        # ON_DISCARD passes the DISCARDED CARD as the event
        # (ability_keywords._fire_on_discard), which is what the ability-level
        # DISCARDED_CARD_POWER_GTE gate reads.
        run_ability(get_card("berserk_yellow").abilities[0], src, discarded, st)
    finally:
        pop_refs()
    return src


def test_berserk_banishes_the_discarded_card_not_the_deck():
    st = _state()
    discarded = _action("big_discard", power=7)
    st.players[1].graveyard.add(discarded)
    top = _action("deck_top", power=1)

    _berserk(st, discarded, [top])

    assert discarded in st.players[1].banished.cards, (
        "the discarded card was not banished")
    assert top in st.players[1].deck.cards, (
        "it banished off the top of the deck instead")


def test_berserk_draws_when_the_revealed_card_has_six_power():
    st = _state()
    discarded = _action("big_discard", power=7)
    st.players[1].graveyard.add(discarded)
    top = _action("fat_top", power=6)
    before = len(st.players[1].hand.cards)

    _berserk(st, discarded, [top])

    assert len(st.players[1].hand.cards) == before + 1, (
        "the reveal payoff never fired")


def test_berserk_does_not_draw_on_a_small_reveal():
    st = _state()
    discarded = _action("big_discard", power=7)
    st.players[1].graveyard.add(discarded)
    top = _action("thin_top", power=2)
    spare = _action("spare", power=1)
    st.players[1].deck.add(spare)
    before = len(st.players[1].hand.cards)

    _berserk(st, discarded, [top])

    assert len(st.players[1].hand.cards) == before, (
        "it drew off a card with less than 6 power")


# --- shred_yellow -----------------------------------------------------------

def _combat_with_defenders(st, defenders, attack_classes=("Assassin",)):
    attack = _action("an_attack", 1)
    attack.classes = list(attack_classes)
    attack.card_class = attack_classes[0] if attack_classes else None
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=5,
                            attack_card=attack, keywords=[], from_weapon=False)
    st.combat.defending_cards = list(defenders)
    return st.combat


def test_shred_takes_three_off_one_defender_not_the_whole_block():
    st = _state()
    a = _action("defender_a", 2)
    a.raw_defense = a.defense = 3
    b = _action("defender_b", 2)
    b.raw_defense = b.defense = 3
    _combat_with_defenders(st, [a, b])
    src = copy.deepcopy(DB.get("shred_yellow"))
    src.owner = src.controller = 1

    run_ability(get_card("shred_yellow").abilities[0], src, None, st)

    hit = [c for c in (a, b) if c.defense < 3]
    assert len(hit) == 1, (
        f"-3{{d}} landed on {len(hit)} defenders; the card targets one")


def test_shred_does_nothing_off_a_non_assassin_attack():
    st = _state()
    a = _action("defender_a", 2)
    a.raw_defense = a.defense = 3
    _combat_with_defenders(st, [a], attack_classes=("Guardian",))
    src = copy.deepcopy(DB.get("shred_yellow"))
    src.owner = src.controller = 1

    run_ability(get_card("shred_yellow").abilities[0], src, None, st)

    assert a.defense == 3, "it fired off a Guardian attack"

# --- the siblings -----------------------------------------------------------

SIBLINGS = [
    # slug, defender types that qualify, the modifier, the printed clause
    ("reinforce_the_line_blue", ["Action", "Attack"], +2),
    ("dramatic_pause_blue", ["Action"], +1),
]


@pytest.mark.parametrize("slug,types,delta", SIBLINGS)
def test_a_targeted_defense_bonus_lands_on_one_card(slug, types, delta):
    """Same defect as Shred, on the cards the first pass did not sweep for.

    "TARGET defending <X> card gets +N{d}" with no target in the effect's own
    params takes the untargeted branch and shifts combat.total_defense -- the
    whole block. One defender hides it; two do not.
    """
    st = _state()
    a = _action("defender_a", 2)
    a.raw_defense = a.defense = 3
    a.types, a.subtypes = list(types), list(types)
    b = _action("defender_b", 2)
    b.raw_defense = b.defense = 3
    b.types, b.subtypes = list(types), list(types)
    _combat_with_defenders(st, [a, b], attack_classes=("Assassin",))
    src = copy.deepcopy(DB.get(slug))
    src.owner = src.controller = 1

    run_ability(get_card(slug).abilities[0], src, None, st)

    moved = [c for c in (a, b) if c.defense != 3]
    assert len(moved) == 1, (
        f"{delta:+}{{d}} reached {len(moved)} defenders; the card targets one")
    assert moved[0].defense == 3 + delta


@pytest.mark.parametrize("slug,types,delta", SIBLINGS)
def test_it_skips_a_defender_of_the_wrong_type(slug, types, delta):
    """The filter is the half that only matters when the block is mixed --
    exactly where the untargeted version was wrong."""
    st = _state()
    equip = _action("an_equipment", 2)
    equip.raw_defense = equip.defense = 3
    equip.types, equip.subtypes = ["Equipment"], ["Chest"]
    _combat_with_defenders(st, [equip], attack_classes=("Assassin",))
    src = copy.deepcopy(DB.get(slug))
    src.owner = src.controller = 1

    run_ability(get_card(slug).abilities[0], src, None, st)

    assert equip.defense == 3, (
        "the bonus landed on equipment; the card names an action card")
