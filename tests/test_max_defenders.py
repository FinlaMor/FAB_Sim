"""A defender restriction that limits HOW MANY, not WHICH.

Every entry in `combat.defender_restrictions` named the cards that may NOT
defend: equipment, cards from hand, a type, a cost threshold. The Confidence
token needs something none of them can express -- "the next attack card you
play this turn can't be defended by more than 2 **non-block** cards" -- which
is a COUNT.

`max_defenders` is counted against what is ALREADY on the chain, so the first N
cards are legal and the N+1th is not. `exclude_types` names card types that do
not count toward the limit and are never blocked by it; Block is a card TYPE
(CR 8.1.12, 67 cards in this corpus), not a subtype.

The restriction reaches ONE attack rather than every attack for the turn by
riding the same one-shot queue as the other "next attack" mods -- authored as a
turn-long flag it would restrict every attack for the rest of the turn, which
is the failure this project keeps finding in "the next ..." wordings.
"""
import copy

import pytest

import engine.engine as E
from engine.actions import _restriction_blocks
from engine.card import CardDB
from engine.card_effects.dsl.effect_types import compile_effect
from engine.card_effects.dsl.interpreter import run_ability
from engine.card_effects.dsl.loader import get_card, load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

PLAIN = "brutal_assault_red"


def _card(slug, pid=1):
    c = copy.deepcopy(DB.get(slug))
    assert c is not None, slug
    c.owner = c.controller = pid
    return c


def _block_card():
    """A card whose TYPE is Block (CR 8.1.12)."""
    import json
    from pathlib import Path
    idx = json.load(open(Path(__file__).resolve().parent.parent
                         / "card_data" / "slug_index.json", encoding="utf-8"))["by_slug"]
    slug = next(s for s, v in idx.items() if "Block" in (v.get("types") or []))
    c = _card(slug, 2)
    assert "Block" in (c.types or []), f"{slug} is not a Block card"
    return c


def _state():
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="": o[0]
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    st.individual_turns = 1
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=_card(PLAIN, 1), keywords=[])
    return st


RULE = {"max_defenders": 2, "exclude_types": ["Block"]}


def test_the_first_two_defenders_are_legal():
    st = _state()
    st.combat.defender_restrictions.append(dict(RULE))

    assert _restriction_blocks(st, _card(PLAIN, 2), None) is False
    st.combat.defending_cards.append(_card(PLAIN, 2))
    assert _restriction_blocks(st, _card(PLAIN, 2), None) is False


def test_the_third_defender_is_blocked():
    st = _state()
    st.combat.defender_restrictions.append(dict(RULE))
    for _ in range(2):
        st.combat.defending_cards.append(_card(PLAIN, 2))

    assert _restriction_blocks(st, _card(PLAIN, 2), None) is True


def test_block_cards_do_not_count_toward_the_limit():
    """"more than 2 NON-BLOCK cards" — block cards are excluded from the count
    AND never blocked by it."""
    st = _state()
    st.combat.defender_restrictions.append(dict(RULE))
    for _ in range(3):
        st.combat.defending_cards.append(_block_card())

    assert _restriction_blocks(st, _card(PLAIN, 2), None) is False, (
        "three BLOCK cards counted against a non-block limit")
    assert _restriction_blocks(st, _block_card(), None) is False, (
        "a block card was itself blocked by a non-block limit")


def test_a_card_with_no_limit_rule_is_unaffected():
    st = _state()

    assert _restriction_blocks(st, _card(PLAIN, 2), None) is False


# --- it reaches exactly one attack ------------------------------------------

def test_the_restriction_lands_on_the_attack():
    st = _state()
    compile_effect("RESTRICT_NEXT_ATTACK_DEFENDERS",
                   {"max_defenders": 2, "exclude_types": ["Block"]})(
        _card(PLAIN, 1), None, st)

    player = st.players[1]
    queued = list(getattr(player, "dsl_queued_attack_mods", None) or [])
    assert queued and queued[0]["mod"] == "restrict_defenders", queued

    E._apply_turn_attack_effects(st, st.combat.attack_card)

    assert any(r.get("max_defenders") == 2
               for r in st.combat.defender_restrictions), (
        st.combat.defender_restrictions)


def test_it_is_consumed_by_the_first_attack():
    """"The NEXT attack card" — a turn-long flag would restrict every attack
    for the rest of the turn."""
    st = _state()
    compile_effect("RESTRICT_NEXT_ATTACK_DEFENDERS",
                   {"max_defenders": 2, "exclude_types": ["Block"]})(
        _card(PLAIN, 1), None, st)
    player = st.players[1]

    E._apply_turn_attack_effects(st, st.combat.attack_card)

    assert not [m for m in (getattr(player, "dsl_queued_attack_mods", None) or [])
                if m.get("mod") == "restrict_defenders"], (
        "the restriction stayed queued for later attacks too")


# --- the confidence token ---------------------------------------------------

def test_confidence_destroys_itself_and_queues_the_restriction():
    st = _state()
    token = _card("confidence", 1)
    st.players[1].permanents.add(token)

    run_ability(get_card("confidence").abilities[0], token, None, st)

    assert token not in st.players[1].permanents.cards, "it did not destroy itself"
    queued = [m for m in (getattr(st.players[1], "dsl_queued_attack_mods", None) or [])
              if m.get("mod") == "restrict_defenders"]
    assert queued, "no defender restriction was queued"
    assert queued[0]["restriction"]["max_defenders"] == 2
