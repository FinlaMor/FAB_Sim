""""If you've intimidated an opponent this turn, this gets go again."

The drafting pass produced two different structures for this one sentence --
a PLAY ability wrapping CONDITIONAL_EFFECT, and a TRIGGERED ON_ATTACK -- on two
printings of the SAME card. Both compiled. Neither is right, and the reason is
worth writing down, because the trap is not in either structure.

THE PRINTED KEYWORD. The card database lists GoAgain on all three printings; it
has no way to say a keyword is conditional. The engine treats every printed
keyword as unconditional, so unless the card's own JSON says otherwise the card
ALWAYS has go again -- strictly stronger than printed, and worse than a dead
ability, which at least does nothing. loader.conditional_keywords() is what
takes the printed keyword away, and it only recognises an ability that is gated
on SOURCE_IS_ATTACK and grants the keyword. That is what distinguishes "THIS
gains go again" from "your Illusionist attacks get go again" (Luminaris), where
the printed listing belongs to a different card entirely.

Both drafts omitted SOURCE_IS_ATTACK, so both would have left the card with a
free permanent go again while looking like they implemented the condition.

STATIC, NOT TRIGGERED. CR 6.2.3d: a static-continuous effect conditional on
being generated has its condition "evaluated at all times", generated when the
condition is met and ceasing to exist when it is not -- and the rule's own
worked example is a conditional go again. Go again is paid at the Resolution
Step (CR 8.3.5b), so what matters is whether the card HAS it then. An ON_ATTACK
trigger answers the question once, at declaration, and would miss an intimidate
that happens after the attack is on the chain.

THE CONDITION WAS DEAD. `intimidate()` emitted its event and recorded no turn
marker, so EVENT_THIS_TURN event=intimidate was False in every state -- the one
keyword effect that emitted and never recorded. The drafting agent found this
by grepping every _record_turn_event call site and said so rather than shipping
a card that looked finished. Fixed in effect_keywords.intimidate().
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import engine.engine as E
from engine.card import Card, CardDB
from engine.card_effects.dsl.loader import (conditional_keywords, get_card,
                                            load_all_cards)
from engine.effect_keywords import intimidate
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()

PRINTINGS = ["aggressive_pounce_red", "aggressive_pounce_blue",
             "aggressive_pounce_yellow"]


def _state():
    st = _make_state()
    st.card_db = DB
    pick = lambda s, o, context="": o[0]
    st.player_agents = {1: pick, 2: pick}
    E._setup_dsl_listeners(st)
    st.active_player = 1
    st.individual_turns = 1
    return st


def _attack(st, slug):
    card = copy.deepcopy(DB.get(slug))
    assert card is not None, slug
    card.owner = card.controller = 1
    card.zone = "combat_chain"
    st.combat = CombatState(attacker_id=1, link_id=1,
                            attack_power=card.base_power or 4,
                            attack_card=card, keywords=[], from_weapon=False)
    E._apply_turn_attack_effects(st, card)
    E._register_card_continuous_effects(st, card)
    E._recalculate_attack_power(st)
    return card


def _has_go_again(st):
    import re
    return any(re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(k)).lower() == "go again"
               for k in (st.combat.keywords or []))


def _intimidate_someone(st):
    st.players[2].hand.add(Card(slug="a_card", name="a_card", types=["Action"],
                                owner=2, controller=2))
    intimidate(st, 1, 2)


# --- the condition ----------------------------------------------------------

@pytest.mark.parametrize("slug", PRINTINGS)
def test_no_go_again_before_you_have_intimidated(slug):
    st = _state()
    _attack(st, slug)

    assert not _has_go_again(st), (
        "the printed GoAgain was applied unconditionally; the card says 'if'")


@pytest.mark.parametrize("slug", PRINTINGS)
def test_go_again_once_you_have_intimidated_this_turn(slug):
    st = _state()
    _intimidate_someone(st)
    _attack(st, slug)

    assert _has_go_again(st), "intimidate happened and the card did not gain it"


def test_the_condition_is_evaluated_at_all_times_not_at_declaration():
    """CR 6.2.3d. An ON_ATTACK trigger would answer once, when the attack was
    declared; the go again is not paid until the Resolution Step (8.3.5b), and
    an intimidate in between still counts."""
    st = _state()
    card = _attack(st, "aggressive_pounce_red")
    assert not _has_go_again(st)

    _intimidate_someone(st)          # after the attack is already on the chain
    E._recalculate_attack_power(st)

    assert _has_go_again(st), (
        "an intimidate after declaration did not reach the card -- the "
        "condition is being snapshotted, not evaluated at all times")


def test_intimidating_before_the_resolution_step_still_pays():
    """Release note, verbatim: "If you haven't intimidated an opponent yet this
    turn when you attack with this and then you do BEFORE the attack's
    resolution step (i.e. after damage is dealt, but before moving into the
    resolution step), you will gain an action point from go again during the
    resolution step."

    This is the positive control for the test below: without it, "no action
    point was paid" would pass just as well on a fixture where the resolution
    step never pays anyone.
    """
    st = _state()
    _attack(st, "aggressive_pounce_red")
    assert not _has_go_again(st)
    before = st.players[1].action_points

    _intimidate_someone(st)                     # after declaration, before resolution
    E._recalculate_attack_power(st)
    E._resolution_step(st)

    assert st.players[1].action_points == before + 1, (
        "intimidating before the resolution step did not pay the action point")


def test_no_retroactive_action_point_after_the_resolution_step():
    """The release notes bound the "always checking" clause: "You don't
    retroactively get an action point from go again if you've passed the
    resolution step and you haven't intimidated an opponent, and then you do
    later in the turn."

    So "evaluated at all times" is about whether the card HAS go again, not
    about paying for it twice or late. The action point is paid once, at the
    resolution step (CR 8.3.5b), from whatever the combat carried then.
    """
    st = _state()
    _attack(st, "aggressive_pounce_red")
    assert not _has_go_again(st)

    before = st.players[1].action_points
    E._resolution_step(st)                      # passes without go again
    after_resolution = st.players[1].action_points

    _intimidate_someone(st)                     # too late
    E._recalculate_attack_power(st) if st.combat else None

    assert st.players[1].action_points == after_resolution, (
        "an intimidate after the resolution step retroactively paid an action "
        "point")
    assert after_resolution == before, (
        "the resolution step paid for a go again the card did not have")


# --- the printed keyword ----------------------------------------------------

@pytest.mark.parametrize("slug", PRINTINGS)
def test_the_printed_keyword_is_recognised_as_conditional(slug):
    """Without this the DB's unconditional GoAgain wins and the gate is
    decoration. It is what SOURCE_IS_ATTACK in the JSON buys."""
    assert "goagain" in conditional_keywords(slug), (
        f"{slug} still counts as having an unconditional printed go again")


@pytest.mark.parametrize("slug", PRINTINGS)
def test_the_card_really_prints_go_again(slug):
    """The premise: if the DB stopped listing it, the conditional-stripping
    machinery would be pointless here and this test should say so."""
    idx = json.load(open(ROOT / "card_data" / "slug_index.json",
                         encoding="utf-8"))["by_slug"]
    kws = [str(k).lower() for k in (idx[slug].get("keywords") or [])]
    assert "goagain" in kws, kws


# --- the turn marker --------------------------------------------------------

def test_intimidate_records_a_turn_marker():
    """It emitted an event and recorded nothing, so every card asking "have you
    intimidated this turn" got False forever."""
    from engine.effect_keywords import TURN_EVENT_MARKER
    st = _state()

    _intimidate_someone(st)

    assert (TURN_EVENT_MARKER + "intimidate") in st.players[1].current_turn_effects
    assert (TURN_EVENT_MARKER + "intimidate") not in st.players[2].current_turn_effects, (
        "recorded against the intimidated player instead of the intimidator")
