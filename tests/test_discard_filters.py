"""Every non-random discard in the corpus discarded hand position 0.

`effect_discard(..., random_discard=False)` took `player.hand.cards[0]`. Two
things followed, and both reach far past the seven cards fixed here:

  1. NOBODY EVER CHOSE. "They discard a card" is the discarding player's
     decision in FAB. The engine picked for them, so the decision never reached
     the agent and never reached the recorder - which matters directly for
     self-play data, where a missing decision point is a missing action.

  2. FILTERS WERE DECORATION. "Discard a YELLOW card", "an INSTANT card", "a
     Phoenix Flame", "a card with WATERY GRAVE" all discarded index 0 whether it
     matched or not. On the COST side that is worse than weaker: can_pay
     returned true whenever the hand was non-empty, so cards were playable when
     their cost could not actually be paid.

The filter vocabulary is now shared between the DISCARD effect and the
DISCARD_CARD cost (effect_types._hand_card_filter), because the cards use the
same words for both and each had its own partial reading.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.ability_keywords import effect_discard
from engine.card_effects.dsl.cost_types import compile_cost
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

RED = "brutal_assault_red"            # Action - Attack, red
YELLOW = "amplifying_arrow_yellow"    # Action - Arrow Attack, yellow
FILLER = "autumns_touch_red"
NO_DEFENCE = "phoenix_flame_red"   # Action - Attack with NO printed {d}
WATERY = "barnacle_yellow"         # carries the WateryGrave keyword


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


def _stock(st, pid=1, n=4):
    for _ in range(n):
        st.players[pid].deck.add(_card(FILLER, pid))


def _hand(st, pid=1):
    return [c.slug for c in st.players[pid].hand.cards]


def _cost_of(slug, index):
    """The card's OWN DISCARD_CARD cost params, so these tests pin the card and
    not a restatement of it - a hand-written dict here would pass unchanged if
    the requirement were dropped from the JSON."""
    ability = get_card(slug).abilities[index]
    costs = list(getattr(ability, "costs", None) or [])
    costs += list(getattr(ability, "additional_costs", None) or [])
    spec = [c for c in costs if c.cost_type == "DISCARD_CARD"]
    assert spec, f"{slug} ability[{index}] has no DISCARD_CARD cost any more"
    return spec[0].params


def _run(slug, st, source=None, index=0):
    source = source or _card(slug)
    run_ability(get_card(slug).abilities[index], source, None, st)
    return source


# --- the primitive ----------------------------------------------------------

def test_the_discarding_player_chooses():
    """It took hand.cards[0]; the choice never reached the agent."""
    st = _state(agent=lambda s, o, context="": o[-1])   # deliberately NOT o[0]
    first, last = _card(RED), _card(YELLOW)
    st.players[1].hand.add(first)
    st.players[1].hand.add(last)

    effect_discard(st, 1, 1)

    assert last not in st.players[1].hand.cards, "the player's choice was ignored"
    assert first in st.players[1].hand.cards, "it took hand position 0 regardless"


def test_a_filtered_discard_only_offers_matching_cards():
    st = _state(agent=lambda s, o, context="": o[-1])
    red, yellow = _card(RED), _card(YELLOW)
    st.players[1].hand.add(red)
    st.players[1].hand.add(yellow)

    def _is_yellow(c):
        return (c.base_color or "").lower() == "yellow"

    effect_discard(st, 1, 1, matches=_is_yellow)

    assert yellow not in st.players[1].hand.cards
    assert red in st.players[1].hand.cards, (
        "a card the filter excludes was offered and taken")


def test_a_filtered_discard_with_no_match_discards_nothing():
    """It must not fall back to an illegal card."""
    st = _state()
    red = _card(RED)
    st.players[1].hand.add(red)

    got = effect_discard(st, 1, 1, matches=lambda c: False)

    assert got == []
    assert red in st.players[1].hand.cards


# --- golden_tipple_blue -----------------------------------------------------

def test_golden_tipple_discards_the_yellow_card():
    st = _state()
    red, yellow = _card(RED), _card(YELLOW)
    st.players[1].hand.add(red)          # position 0 - what it used to take
    st.players[1].hand.add(yellow)
    _stock(st)

    _run("golden_tipple_blue", st)

    assert yellow not in st.players[1].hand.cards, "the yellow card was not discarded"
    assert red in st.players[1].hand.cards, "it discarded the red card at position 0"


def test_golden_tipple_pays_off_only_when_it_discarded():
    st = _state()
    red, yellow = _card(RED), _card(YELLOW)
    st.players[1].hand.add(red)
    st.players[1].hand.add(yellow)
    _stock(st)

    _run("golden_tipple_blue", st)

    tokens = [c.slug for c in st.players[1].permanents.cards]
    assert "gold" in tokens, f"no Gold token created (permanents={tokens})"


def test_golden_tipple_does_nothing_with_no_yellow_card():
    """The gate was DISCARDED_CARD_POWER_GTE - a question about the discarded
    card's POWER, which this card never asks."""
    st = _state()
    red = _card(RED)
    st.players[1].hand.add(red)
    _stock(st)
    before = len(st.players[1].hand.cards)

    _run("golden_tipple_blue", st)

    assert red in st.players[1].hand.cards, "it discarded a non-yellow card"
    assert len(st.players[1].hand.cards) == before, "it drew anyway"
    assert "gold" not in [c.slug for c in st.players[1].permanents.cards], (
        "it created a Gold token without paying for it")


# --- astravolt_elemental_red ------------------------------------------------

def test_astravolt_needs_an_instant_to_get_paid():
    st = _state()
    st.players[1].hand.add(_card(RED))     # not an Instant
    _stock(st)
    before = len(st.players[1].hand.cards)

    _run("astravolt_elemental_red", st)

    assert len(st.players[1].hand.cards) == before, (
        "accepting the MAY drew a card with no instant discarded")
    assert "embodiment_of_lightning" not in [
        c.slug for c in st.players[1].permanents.cards]


# --- tricorn_of_saltwater_death ---------------------------------------------

def test_tricorn_needs_a_watery_grave_card():
    """The keyword was an effect-level GATE asking whether such a card is
    SOMEWHERE in hand, then discarding position 0 - which need not be it. The
    same gate sat on the DRAW, so the draw fired whenever such a card was merely
    HELD, whatever was actually discarded."""
    st = _state()
    st.players[1].hand.add(_card(RED))
    _stock(st)
    before = len(st.players[1].hand.cards)

    _run("tricorn_of_saltwater_death", st)

    assert len(st.players[1].hand.cards) == before, (
        "it discarded and drew with no watery-grave card in hand")


def test_tricorn_discards_the_watery_grave_card_not_position_zero():
    """The discriminating case. With the old effect-level gate the ability
    fired because such a card was SOMEWHERE in hand, then discarded position 0
    - which is the card the text excludes."""
    st = _state()
    plain = _card(RED)
    watery = _card(WATERY)
    st.players[1].hand.add(plain)      # position 0
    st.players[1].hand.add(watery)
    assert "WateryGrave" in (watery.keywords or []), watery.keywords
    _stock(st)

    _run("tricorn_of_saltwater_death", st)

    assert watery not in st.players[1].hand.cards, (
        "the watery-grave card was not the one discarded")
    assert plain in st.players[1].hand.cards, (
        "it discarded hand position 0, which has no watery grave")


# --- carrion_crown (a COST, so it must block legality) ----------------------

def test_carrion_crown_cannot_be_activated_without_an_ally():
    """can_pay returned true whenever the hand was non-empty."""
    st = _state()
    st.players[1].hand.add(_card(RED))
    source = _card("carrion_crown")

    # Read the cost off the compiled card rather than restating it, so this
    # goes red if the ally requirement is ever dropped from the JSON.
    spec = [c for c in get_card("carrion_crown").abilities[0].costs
            if c.cost_type == "DISCARD_CARD"]
    assert spec, "the ally cost is gone"
    can_pay, _pay = compile_cost("DISCARD_CARD", spec[0].params)

    assert can_pay(source, None, st) is False, (
        "the ability is payable with no ally in hand")


def test_carrion_crown_can_be_activated_with_an_ally():
    st = _state()
    ally = _card("aether_ashwing")
    st.players[1].hand.cards.append(ally)   # tokens are not deck cards
    source = _card("carrion_crown")
    can_pay, pay = compile_cost("DISCARD_CARD", _cost_of("carrion_crown", 0))

    assert can_pay(source, None, st) is True
    pay(source, None, st)
    assert ally not in st.players[1].hand.cards


# --- great_library_of_solana ------------------------------------------------

def test_great_library_needs_two_yellow_cards():
    st = _state()
    st.players[1].hand.add(_card(YELLOW))
    st.players[1].hand.add(_card(RED))
    source = _card("great_library_of_solana")
    can_pay, pay = compile_cost("DISCARD_CARD", _cost_of("great_library_of_solana", 1))

    assert can_pay(source, None, st) is False, "one yellow card paid a cost of two"

    st.players[1].hand.add(_card(YELLOW))
    assert can_pay(source, None, st) is True


def test_great_library_discards_only_yellow_cards():
    st = _state()
    keep = _card(RED)
    st.players[1].hand.add(keep)
    for _ in range(2):
        st.players[1].hand.add(_card(YELLOW))
    source = _card("great_library_of_solana")
    _can, pay = compile_cost("DISCARD_CARD", _cost_of("great_library_of_solana", 1))

    pay(source, None, st)

    assert _hand(st) == [RED], f"it discarded the red card too: {_hand(st)}"


# --- art_of_the_phoenix_war_red ---------------------------------------------

def test_phoenix_war_cost_needs_a_phoenix_flame():
    st = _state()
    st.players[1].hand.add(_card(RED))
    source = _card("art_of_the_phoenix_war_red")
    can_pay, _pay = compile_cost("DISCARD_CARD",
                                 _cost_of("art_of_the_phoenix_war_red", 0))

    assert can_pay(source, None, st) is False, (
        "the card is playable without a Phoenix Flame to discard")

    st.players[1].hand.add(_card("phoenix_flame_red"))
    assert can_pay(source, None, st) is True


def test_phoenix_war_cost_discards_the_phoenix_flame_not_a_random_card():
    st = _state()
    keep = _card(RED)
    flame = _card("phoenix_flame_red")
    st.players[1].hand.add(keep)
    st.players[1].hand.add(flame)
    source = _card("art_of_the_phoenix_war_red")
    _can, pay = compile_cost("DISCARD_CARD",
                             _cost_of("art_of_the_phoenix_war_red", 0))

    pay(source, None, st)

    assert flame not in st.players[1].hand.cards
    assert keep in st.players[1].hand.cards, "a random card was discarded"


# --- the_weakest_link_red ---------------------------------------------------

def test_weakest_link_makes_the_OPPONENT_discard():
    """It defaulted to player SELF: had it been reachable at all, the ATTACKER
    would have discarded their own card."""
    st = _state()
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=1,
                            attack_card=_card("the_weakest_link_red"), keywords=[])
    # NO_BASE_DEFENCE on BOTH sides, so the effect has a legal target in either
    # hand and the test distinguishes WHOSE it takes. With a filtered-out card
    # in their hand nothing would be discarded at all and this would pass
    # against a card that does nothing.
    theirs = _card(NO_DEFENCE, 2)
    mine = _card(NO_DEFENCE, 1)
    st.players[2].hand.add(theirs)
    st.players[1].hand.add(mine)
    _stock(st, 1)

    _run("the_weakest_link_red", st)

    assert theirs not in st.players[2].hand.cards, "the opponent kept their card"
    assert mine in st.players[1].hand.cards, "the attacker discarded their own card"


def test_weakest_link_leaves_a_hand_of_cards_with_base_defence_alone():
    st = _state()
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=1,
                            attack_card=_card("the_weakest_link_red"), keywords=[])
    theirs = _card(RED, 2)          # base {d} 3 - excluded by the text
    st.players[2].hand.add(theirs)
    _stock(st, 1)
    before = len(st.players[1].hand.cards)

    _run("the_weakest_link_red", st)

    assert theirs in st.players[2].hand.cards, (
        "it took a card WITH base {d}, which the text excludes")
    assert len(st.players[1].hand.cards) == before, (
        "the attacker drew with nothing discarded")


def test_weakest_link_only_takes_a_card_without_base_defence():
    """"Choose a card WITHOUT BASE {d}" was ATTACK_HAS_KEYWORD "BASE_DEFENSE" -
    there is no such keyword, so the test was false for every card in the game,
    and it gated the whole ability rather than filtering which card."""
    from engine.card_effects.dsl.condition_types import compile_condition

    st = _state()
    fn = compile_condition("NO_BASE_DEFENSE", {})
    with_d = _card(RED)
    assert with_d.base_defense is not None
    assert fn(with_d, None, st) is False

    without_d = _card(NO_DEFENCE)
    assert without_d.base_defense is None, (
        f"{NO_DEFENCE} was picked BECAUSE it has no printed {{d}}; it now has "
        f"{without_d.base_defense} and this test proves nothing")
    assert fn(without_d, None, st) is True
