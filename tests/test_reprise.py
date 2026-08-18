"""Reprise (CR 8.4.3) — an existing condition no card was using.

"Reprise - If the defending hero has defended with a card from their hand this
chain link, [EFFECTS]". The engine already tracked
`combat.defender_used_hand_card` (set in three places in play.py /
effect_keywords.py) AND already had a working REPRISE condition — yet ZERO cards
referenced it, and the two cards with reprise text each invented their own flag
(DEFENDED_WITH_HAND_CARD, REPRISE_FLAG).

Both were also on the wrong ability_type (STATIC and DEFENSE_REACTION on Warrior
ATTACK Reaction cards), so neither reprise clause could have fired even if
something had set the flags.
"""
import copy

import pytest

from engine.card import Card, CardDB
from engine.card_effects.dsl import dispatch
from engine.card_effects.dsl.condition_types import compile_condition
from engine.card_effects.dsl.loader import load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()


def _state():
    st = _make_state()
    st.card_db = DB
    # The base state starts with EMPTY decks, so a "draw a card" effect silently
    # no-ops and a CORRECT card fails its assertion. Stock both decks.
    for pid in (1, 2):
        for _ in range(20):
            c = Card(slug="dummy_card", name="dummy", types=["Action"])
            c.owner = c.controller = pid
            st.players[pid].deck.cards.append(c)
    return st


def _card(slug, owner=1):
    base = DB.get(slug)
    assert base is not None, f"unknown slug {slug}"
    c = copy.deepcopy(base)
    c.owner = c.controller = owner
    return c


def _combat(st, defended_from_hand: bool):
    atk = Card(slug="wpn", name="wpn", types=["Weapon"], subtypes=["Sword"])
    atk.owner = atk.controller = 1
    atk.power = 3
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=atk, keywords=[], from_weapon=True)
    st.combat.base_attack_power = 3
    st.combat.defender_used_hand_card = defended_from_hand
    return atk


# --- the condition ---------------------------------------------------------

def test_reprise_false_when_the_defender_used_no_hand_card():
    st = _state()
    card = _card("glint_the_quicksilver_blue")
    _combat(st, defended_from_hand=False)
    assert compile_condition("REPRISE", {})(card, None, st) is False


def test_reprise_true_when_the_defender_defended_from_hand():
    st = _state()
    card = _card("glint_the_quicksilver_blue")
    _combat(st, defended_from_hand=True)
    assert compile_condition("REPRISE", {})(card, None, st) is True


def test_reprise_false_outside_combat():
    st = _state()
    card = _card("glint_the_quicksilver_blue")
    assert st.combat is None
    assert compile_condition("REPRISE", {})(card, None, st) is False


# --- glint: draw a card on reprise -----------------------------------------

def test_glint_draws_on_reprise():
    st = _state()
    card = _card("glint_the_quicksilver_blue")
    _combat(st, defended_from_hand=True)
    before = len(st.players[1].hand.cards)
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert len(st.players[1].hand.cards) == before + 1


def test_glint_does_not_draw_without_reprise():
    # The negative is the point: an always-true condition would pass the
    # positive test just as well.
    st = _state()
    card = _card("glint_the_quicksilver_blue")
    _combat(st, defended_from_hand=False)
    before = len(st.players[1].hand.cards)
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert len(st.players[1].hand.cards) == before


# --- biting blade: turn-long weapon buff on reprise ------------------------

def test_biting_blade_queues_a_weapon_buff_on_reprise():
    st = _state()
    card = _card("biting_blade_red")
    _combat(st, defended_from_hand=True)
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    hooks = getattr(st.players[1], "turn_attack_hooks", [])
    assert hooks, "reprise clause queued no turn-scoped weapon buff"


def test_biting_blade_queues_nothing_without_reprise():
    st = _state()
    card = _card("biting_blade_red")
    _combat(st, defended_from_hand=False)
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert not getattr(st.players[1], "turn_attack_hooks", [])


# --- migration guard -------------------------------------------------------

@pytest.mark.parametrize("slug", ["biting_blade_red", "glint_the_quicksilver_blue"])
def test_reprise_cards_use_the_real_condition(slug):
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "engine" / "card_effects" / "json"
    path = [p for p in root.rglob(f"{slug}.json") if ".quarantine" not in p.parts][0]
    abilities = json.dumps(json.loads(path.read_text(encoding="utf-8"))["abilities"])
    assert "FLAG_SET" not in abilities, f"{slug} still reads an invented flag"
    assert '"REPRISE"' in abilities
    # Both cards are Warrior ATTACK Reactions; the reprise halves were on the
    # wrong ability types and so were unreachable.
    assert "DEFENSE_REACTION" not in abilities
    assert '"STATIC"' not in abilities


# --- SOUL_COUNT_GTE (added for Soul Cleaver) -------------------------------

def test_soul_count_gte_reads_the_defending_heros_soul():
    from engine.card import Card
    from engine.card_effects.dsl.condition_types import compile_condition
    st = _state()
    card = _card("soul_cleaver_blue", owner=1)
    cond = compile_condition("SOUL_COUNT_GTE", {"amount": 1, "player": "DEFENDING"})
    assert cond(card, None, st) is False
    soul_card = Card(slug="souled", name="souled", types=["Action"])
    soul_card.owner = soul_card.controller = 2
    st.players[2].soul.add(soul_card)
    assert cond(card, None, st) is True


def test_soul_count_gte_does_not_read_your_own_soul():
    from engine.card import Card
    from engine.card_effects.dsl.condition_types import compile_condition
    st = _state()
    card = _card("soul_cleaver_blue", owner=1)
    mine = Card(slug="mine", name="mine", types=["Action"])
    mine.owner = mine.controller = 1
    st.players[1].soul.add(mine)
    cond = compile_condition("SOUL_COUNT_GTE", {"amount": 1, "player": "DEFENDING"})
    assert cond(card, None, st) is False
