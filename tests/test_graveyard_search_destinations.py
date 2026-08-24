"""A graveyard search that could only ever reach hand, and a cost anyone paid.

Four cards, four different ways of being wrong:

  bone_puppetry            "Return an ALLY from your graveyard TO THE ARENA"
                           was RETURN_DR_FROM_GRAVEYARD, which returns a
                           DEFENSE REACTION card to HAND. Wrong card type,
                           wrong destination; `target_zone: "ALLY"` was the only
                           hint that anything was amiss.
  ominous_excavation_blue  "You may SHUFFLE an INSTANT card from your graveyard
                           INTO YOUR DECK" was BANISH_TRAP_FROM_GRAVEYARD_
                           PLAYABLE -- a different effect, on traps, that
                           banishes rather than shuffles AND makes the card
                           playable from banish.
  looking_for_a_scrap_blue "You MAY banish a card WITH 1{p} from your
                           graveyard. WHEN YOU DO, this gains +1{p} and go
                           again." pitch_power was unread, so ANY graveyard
                           card paid a cost only a 1-power card can pay -- on
                           the COST side that legalises a play whose cost
                           cannot actually be met. The "may" was compulsory and
                           the payoff ungated, so the bonus applied either way.
  arknight_shard_blue      "When THIS is pitched, create a Runechant." The gate
                           was REF_PITCH_IS, which asks about a card a PREVIOUS
                           effect stored under a ref -- and reads `ref`, not
                           `name`. Nothing set the default ref, so it was false
                           in every state and no token was ever created.

The type filter also carried TWO copies of a types-only reading, one per search
effect. "Ally" and "Attack" are SUBTYPES while "Instant" is a type, so a
types-only match found no ally anywhere in the game.
"""
import copy

import pytest

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.effect_types import compile_effect
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

PLAIN = "brutal_assault_red"
# A real INSTANT card (a type), to prove the type half of the filter.
INSTANT = "shining_courage_red"
# A real Ally CARD, not a token: a TOKEN returned to the arena from the
# graveyard ceases to exist, so it can never show that the return worked.
ALLY = "aegis_archangel_of_protection"


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


# --- the shared type/subtype filter -----------------------------------------

def test_a_subtype_matches_the_type_filter():
    """"Ally" is a SUBTYPE. Two search effects each had their own types-only
    copy of this filter, so neither could ever find one."""
    from engine.card_effects.dsl.effect_types import _matches_type_or_subtype

    ally = _card(ALLY)
    assert "Ally" in (ally.subtypes or [])
    assert "Ally" not in (ally.types or []), (
        "the fixture no longer proves the SUBTYPE half")
    assert _matches_type_or_subtype(ally, ["Ally"]) is True
    assert _matches_type_or_subtype(_card(PLAIN), ["Ally"]) is False


def test_a_type_still_matches():
    from engine.card_effects.dsl.effect_types import _matches_type_or_subtype

    instant = _card(INSTANT)
    assert "Instant" in (instant.types or [])
    assert _matches_type_or_subtype(instant, ["Instant"]) is True


# --- SEARCH_GRAVEYARD destinations ------------------------------------------

def test_the_default_destination_is_still_hand():
    st = _state()
    c = _card(PLAIN)
    st.players[1].graveyard.add(c)

    compile_effect("SEARCH_GRAVEYARD", {})(_card(PLAIN), None, st)

    assert c in st.players[1].hand.cards


def test_it_can_put_the_card_into_the_arena():
    st = _state()
    ally = _card(ALLY)
    st.players[1].graveyard.add(ally)

    compile_effect("SEARCH_GRAVEYARD", {"filter_types": ["Ally"],
                                        "destination": "arena"})(
        _card(PLAIN), None, st)

    assert ally in st.players[1].permanents.cards, f"it is in {ally.zone!r}"
    assert ally not in st.players[1].hand.cards


def test_it_can_shuffle_the_card_into_the_deck():
    st = _state()
    instant = _card(INSTANT)
    st.players[1].graveyard.add(instant)

    compile_effect("SEARCH_GRAVEYARD", {"filter_types": ["Instant"],
                                        "destination": "deck"})(
        _card(PLAIN), None, st)

    assert instant in st.players[1].deck.cards, f"it is in {instant.zone!r}"


# --- bone_puppetry ----------------------------------------------------------

def _defending(st, card):
    st.combat = CombatState(attacker_id=2, link_id=1, attack_power=3,
                            attack_card=_card(PLAIN, 2), keywords=[])
    st.combat.defending_cards = [card]
    return st.combat


def test_bone_puppetry_returns_an_ally_to_the_arena():
    st = _state()
    source = _card("bone_puppetry")
    _defending(st, source)
    ally = _card(ALLY)
    st.players[1].graveyard.add(ally)

    run_ability(get_card("bone_puppetry").abilities[0], source, None, st)

    assert ally in st.players[1].permanents.cards, f"the ally is in {ally.zone!r}"


def test_bone_puppetry_does_not_return_a_non_ally():
    st = _state()
    source = _card("bone_puppetry")
    _defending(st, source)
    other = _card(PLAIN)
    st.players[1].graveyard.add(other)

    run_ability(get_card("bone_puppetry").abilities[0], source, None, st)

    assert other in st.players[1].graveyard.cards, (
        "it returned a card that is not an ally")


def test_bone_puppetry_does_not_put_the_ally_in_hand():
    """RETURN_DR_FROM_GRAVEYARD returns to HAND; the card says the arena."""
    st = _state()
    source = _card("bone_puppetry")
    _defending(st, source)
    ally = _card(ALLY)
    st.players[1].graveyard.add(ally)

    run_ability(get_card("bone_puppetry").abilities[0], source, None, st)

    assert ally not in st.players[1].hand.cards


# --- ominous_excavation_blue ------------------------------------------------

def test_excavation_shuffles_an_instant_into_the_deck():
    st = _state()
    instant = _card(INSTANT)
    st.players[1].graveyard.add(instant)

    run_ability(get_card("ominous_excavation_blue").abilities[0],
                _card("ominous_excavation_blue"), None, st)

    assert instant in st.players[1].deck.cards, f"it is in {instant.zone!r}"


def test_excavation_does_not_banish_it():
    """It was a BANISH that also made the card playable from banish."""
    st = _state()
    instant = _card(INSTANT)
    st.players[1].graveyard.add(instant)

    run_ability(get_card("ominous_excavation_blue").abilities[0],
                _card("ominous_excavation_blue"), None, st)

    assert instant not in st.players[1].banished.cards
    assert st.players[1].playable_from_banished == []


def test_excavation_leaves_a_non_instant_alone():
    st = _state()
    other = _card(PLAIN)
    st.players[1].graveyard.add(other)

    run_ability(get_card("ominous_excavation_blue").abilities[0],
                _card("ominous_excavation_blue"), None, st)

    assert other in st.players[1].graveyard.cards


# --- looking_for_a_scrap_blue ----------------------------------------------

def _cost_fns():
    from engine.card_effects.dsl.cost_types import compile_cost
    return compile_cost("BANISH_FROM_GRAVEYARD",
                        {"pitch_power": 1, "optional": True,
                         "flag": "looking_for_a_scrap_banished"})


def _one_power_card(st, pid=1):
    """A graveyard card whose power is exactly 1."""
    c = _card(PLAIN, pid)
    c.base_power = c.power = 1
    st.players[pid].graveyard.add(c)
    return c


def test_only_a_one_power_card_can_pay():
    st = _state()
    can_pay, pay = _cost_fns()
    wrong = _card(PLAIN)
    assert wrong.power != 1, "the fixture no longer proves the filter"
    st.players[1].graveyard.add(wrong)

    pay(_card("looking_for_a_scrap_blue"), None, st)

    assert wrong in st.players[1].graveyard.cards, (
        f"a {wrong.power}-power card paid a cost only a 1-power card can pay")


def test_a_one_power_card_does_pay():
    st = _state()
    can_pay, pay = _cost_fns()
    right = _one_power_card(st)

    pay(_card("looking_for_a_scrap_blue"), None, st)

    assert right in st.players[1].banished.cards


def test_the_optional_cost_never_blocks_the_play():
    """"You MAY banish" — an empty graveyard must not make the card
    unplayable."""
    st = _state()
    can_pay, _pay = _cost_fns()

    assert can_pay(_card("looking_for_a_scrap_blue"), None, st) is True


def test_declining_pays_nothing_and_sets_no_flag():
    st = _state(agent=lambda s, o, context="": None)
    can_pay, pay = _cost_fns()
    right = _one_power_card(st)

    pay(_card("looking_for_a_scrap_blue"), None, st)

    assert right in st.players[1].graveyard.cards, "it banished it unasked"
    assert "looking_for_a_scrap_banished" not in st.players[1].current_turn_effects


def test_paying_sets_the_flag_the_payoff_reads():
    st = _state()
    can_pay, pay = _cost_fns()
    _one_power_card(st)

    pay(_card("looking_for_a_scrap_blue"), None, st)

    assert "looking_for_a_scrap_banished" in st.players[1].current_turn_effects


def test_the_payoff_is_gated_on_having_paid():
    """"WHEN YOU DO" — the bonus applied whether or not anything was banished."""
    st = _state()
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=_card("looking_for_a_scrap_blue", 1),
                            keywords=[])

    before = st.combat.attack_power

    run_ability(get_card("looking_for_a_scrap_blue").abilities[0],
                _card("looking_for_a_scrap_blue"), None, st)

    assert st.combat.attack_power == before, (
        f"it paid out with nothing banished: {st.combat.attack_power}")


def test_the_payoff_lands_once_the_flag_is_set():
    st = _state()
    # MODIFY_ATTACK acts on the current combat, so the card has to be
    # attacking for its "+1{p}" to have anywhere to land.
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=_card("looking_for_a_scrap_blue", 1),
                            keywords=[])
    st.players[1].current_turn_effects.append("looking_for_a_scrap_banished")

    before = st.combat.attack_power

    run_ability(get_card("looking_for_a_scrap_blue").abilities[0],
                _card("looking_for_a_scrap_blue"), None, st)

    assert st.combat.attack_power == before + 1, (
        "the +1{p} never reached the game state")


# --- arknight_shard_blue ----------------------------------------------------

def test_the_shard_creates_a_runechant_when_pitched():
    st = _state()
    source = _card("arknight_shard_blue")

    run_ability(get_card("arknight_shard_blue").abilities[0], source, None, st)

    assert any(c.slug == "runechant" for c in st.players[1].permanents.cards), (
        "no runechant was created")
