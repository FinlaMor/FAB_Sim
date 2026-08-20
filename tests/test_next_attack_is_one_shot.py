"""'Your NEXT attack this turn' must buff exactly ONE attack.

This is the single most consequential recurring defect in the corpus, because
both wrong shapes look plausible in JSON and neither errors:

  * a turn-long flag plus a flag-gated static  -> buffs EVERY attack this turn
  * APPLY_CONTINUOUS with span THIS_TURN        -> buffs EVERY attack this turn
  * MODIFY_ATTACK at resolution                 -> buffs the CURRENT attack,
                                                   and there often is none yet,
                                                   so it does nothing at all

MODIFY_NEXT_ATTACK is the only correct shape: queued as a one-shot, consumed by
the first attack matching its filter, and expiring with the turn if unused.

These tests attack TWICE and require the second attack to be unbuffed. A card
that buffs everything passes any single-attack test, which is why the defect
survived so long.
"""
import copy

import pytest

import engine.engine as E
from engine.card import Card, CardDB
from engine.card_effects.dsl import dispatch
from engine.card_effects.dsl.loader import load_all_cards
from engine.state import CombatState
from tests.conftest import _make_state

load_all_cards()
DB = CardDB()


def _state():
    st = _make_state()
    st.card_db = DB
    st.player_agents = {1: lambda s, o, context="": o[0],
                        2: lambda s, o, context="": o[0]}
    return st


def _card(slug, owner=1):
    base = DB.get(slug)
    assert base is not None, f"unknown slug {slug}"
    c = copy.deepcopy(base)
    c.owner = c.controller = owner
    return c


def _attack(st, power=3, cost=2, pid=1, slug="atk"):
    """Make an attack and run the turn-attack hooks, as a real attack does."""
    atk = Card(slug=slug, name=slug, types=["Action"], subtypes=["Attack"])
    atk.owner = atk.controller = pid
    atk.power = atk.base_power = power
    atk.raw_cost = cost
    atk.classes = ["Guardian"]
    st.combat = CombatState(attacker_id=pid, link_id=1, attack_power=power,
                            attack_card=atk, keywords=[])
    st.combat.base_attack_power = power
    # The real attack path is these three in order. _apply_turn_attack_effects
    # only APPENDS to attack_card.effects; _register_card_continuous_effects is
    # what stages those into the manager that _recalculate_attack_power reads.
    # Omitting the middle call makes a perfectly good buff look like it does
    # nothing, which is how the first version of this test "proved" a bug that
    # was in the test.
    E._apply_turn_attack_effects(st, atk)
    E._register_card_continuous_effects(st, atk)
    E._recalculate_attack_power(st)
    return st.combat.attack_power


# --- strong_yield: "your next attack this turn gets +1{p}" -----------------

def test_strong_yield_buffs_the_first_attack():
    st = _state()
    card = _card("strong_yield_blue")
    st.players[1].permanents.add(card)
    dispatch(st, "START_OF_ACTION_PHASE", card.slug, card=card, event=None)
    assert _attack(st, power=3) == 4


def test_strong_yield_does_not_buff_the_second_attack():
    # The whole point. A turn-long effect passes the test above and fails here.
    st = _state()
    card = _card("strong_yield_blue")
    st.players[1].permanents.add(card)
    dispatch(st, "START_OF_ACTION_PHASE", card.slug, card=card, event=None)
    assert _attack(st, power=3, slug="first") == 4
    assert _attack(st, power=3, slug="second") == 3, \
        "the second attack was buffed too — 'next attack' became 'every attack'"


# --- sloggism: "the next attack action card with cost 2 or greater" --------

def test_sloggism_buffs_a_qualifying_attack():
    st = _state()
    card = _card("sloggism_blue")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert _attack(st, power=3, cost=2) == 7


def test_sloggism_does_not_buff_the_second_qualifying_attack():
    st = _state()
    card = _card("sloggism_blue")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert _attack(st, power=3, cost=2, slug="first") == 7
    assert _attack(st, power=3, cost=2, slug="second") == 3, \
        "the second attack was buffed too — 'next attack' became 'every attack'"


def test_sloggism_skips_a_cheap_attack_and_keeps_the_buff():
    # "cost 2 or greater" — a cheaper attack must not consume the one-shot, or
    # the card is spent on an attack it was never meant to buff.
    st = _state()
    card = _card("sloggism_blue")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert _attack(st, power=3, cost=1, slug="cheap") == 3
    assert _attack(st, power=3, cost=2, slug="dear") == 7, \
        "the cheap attack consumed a buff it did not qualify for"


# --- emerging_dominance: "the next GUARDIAN attack action card" -----------

def test_emerging_dominance_buffs_one_guardian_attack_only():
    st = _state()
    card = _card("emerging_dominance_red")
    st.players[1].permanents.add(card)
    dispatch(st, "START_OF_ACTION_PHASE", card.slug, card=card, event=None)
    assert _attack(st, power=3, slug="first") == 6
    assert _attack(st, power=3, slug="second") == 3,         "every Guardian attack was buffed, not the next one"


def test_emerging_dominance_grants_dominate_to_that_attack():
    st = _state()
    card = _card("emerging_dominance_red")
    st.players[1].permanents.add(card)
    dispatch(st, "START_OF_ACTION_PHASE", card.slug, card=card, event=None)
    _attack(st, power=3)
    assert "Dominate" in (st.combat.keywords or [])


def test_emerging_dominance_skips_a_non_guardian_attack():
    st = _state()
    card = _card("emerging_dominance_red")
    st.players[1].permanents.add(card)
    dispatch(st, "START_OF_ACTION_PHASE", card.slug, card=card, event=None)
    atk = Card(slug="ninja", name="ninja", types=["Action"], subtypes=["Attack"])
    atk.owner = atk.controller = 1
    atk.power = atk.base_power = 3
    atk.classes = ["Ninja"]
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=atk, keywords=[])
    st.combat.base_attack_power = 3
    E._apply_turn_attack_effects(st, atk)
    E._register_card_continuous_effects(st, atk)
    E._recalculate_attack_power(st)
    assert st.combat.attack_power == 3
    # ...and the buff is still waiting for a Guardian attack.
    assert _attack(st, power=3, slug="guardian") == 6


# --- force_sight: the +3 is unconditional, only the opt is not -------------

def test_force_sight_buffs_the_next_attack_even_from_hand():
    # The +3{p} does not depend on the arsenal; only the opt 2 does. The old
    # version gated the buff on NOT being played from arsenal, which is a
    # restriction the card never states.
    st = _state()
    card = _card("force_sight_red")
    card.prev_zone = "hand"
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert _attack(st, power=3) == 6


def test_force_sight_buffs_the_next_attack_from_arsenal_too():
    st = _state()
    card = _card("force_sight_red")
    card.prev_zone = "arsenal"
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert _attack(st, power=3) == 6


def test_played_from_arsenal_value_false_is_the_negative():
    # It was unread, so value:false returned the POSITIVE answer and any card
    # using it got the opposite branch.
    from engine.card_effects.dsl.condition_types import compile_condition
    st = _state()
    card = _card("force_sight_red")
    card.prev_zone = "arsenal"
    assert compile_condition("PLAYED_FROM_ARSENAL", {"value": True})(card, None, st) is True
    assert compile_condition("PLAYED_FROM_ARSENAL", {"value": False})(card, None, st) is False
    card.prev_zone = "hand"
    assert compile_condition("PLAYED_FROM_ARSENAL", {"value": True})(card, None, st) is False
    assert compile_condition("PLAYED_FROM_ARSENAL", {"value": False})(card, None, st) is True


# --- "the next TIME ... would" is a replacement, not a state ---------------

def _hit(st, amount=3, pid=1, dtype=None):
    from engine.effect_keywords import DamageType, deal_damage
    before = st.players[pid].life
    deal_damage(st, amount=amount, damage_type=dtype or DamageType.PHYSICAL,
                source_player_id=3 - pid, damage_target=st.players[pid].hero,
                damage_source="effect")
    return before - st.players[pid].life


def test_cloud_cover_prevents_the_next_damage():
    # The card was a lone SET_FLAG nothing read: it did nothing whatsoever.
    st = _state()
    card = _card("cloud_cover_blue")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert _hit(st, 3) == 2


def test_cloud_cover_prevents_only_once():
    st = _state()
    card = _card("cloud_cover_blue")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert _hit(st, 3) == 2
    assert _hit(st, 3) == 3, "the shield prevented a second time"


def test_peace_of_mind_prevents_physical_only():
    # "{p} damage" is PHYSICAL specifically. PREVENT_DAMAGE ignored damage_type,
    # so this would also have blocked arcane damage the card never mentions.
    from engine.effect_keywords import DamageType
    st = _state()
    card = _card("peace_of_mind_blue")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert _hit(st, 3, dtype=DamageType.ARCANE) == 3,         "arcane damage was prevented by a shield that only covers {p}"
    assert _hit(st, 3, dtype=DamageType.PHYSICAL) == 1


def test_peace_of_mind_still_makes_its_token():
    st = _state()
    card = _card("peace_of_mind_blue")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert [c for c in st.players[1].permanents.cards if c.slug == "ponder"]


def test_earthlore_surge_buffs_one_attack_only():
    st = _state()
    card = _card("earthlore_surge_yellow")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert _attack(st, power=3, slug="first") == 7
    assert _attack(st, power=3, slug="second") == 3


# --- "prevent the next N damage" ------------------------------------------
# Every card in this family was doing something else: WARD (a pay-{r} keyword the
# defender may decline, not a flat shield), a SET_FLAG nothing reads, a counter
# nothing consumes, or the prevention simply absent.

@pytest.mark.parametrize("slug,trigger,amount", [
    ("steadfast_red", "ON_PLAY", 6),
    ("haven_veil_red", "ON_ENTER_PLAY", 3),
    ("gloves_of_astral_sanctuary", "ON_ACTIVATE", 1),
    ("haunting_rendition_red", "ON_ACTIVATE", 2),
    ("glide_through_starlight_red", "ON_ACTIVATE", 1),
])
def test_prevention_card_registers_a_shield(slug, trigger, amount):
    from engine.effect_keywords import DamageType
    st = _state()
    card = _card(slug)
    dispatch(st, trigger, card.slug, card=card, event=None)
    dtype = (DamageType.ARCANE if slug == "haven_veil_red"
             else DamageType.PHYSICAL)
    taken = _hit(st, amount + 2, dtype=dtype)
    assert taken == 2, f"{slug} prevented {amount + 2 - taken}, expected {amount}"


def test_haven_veil_does_not_prevent_physical_damage():
    # The text says ARCANE. Untyped, the shield would also soak physical damage
    # the card never mentions.
    from engine.effect_keywords import DamageType
    st = _state()
    card = _card("haven_veil_red")
    dispatch(st, "ON_ENTER_PLAY", card.slug, card=card, event=None)
    assert _hit(st, 3, dtype=DamageType.PHYSICAL) == 3


def test_prevention_is_one_shot():
    st = _state()
    card = _card("steadfast_red")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert _hit(st, 6) == 0
    assert _hit(st, 6) == 6, "the shield absorbed a second hit"


# --- the queue expires with the turn ---------------------------------------

def test_an_unused_next_attack_buff_does_not_survive_the_turn():
    st = _state()
    card = _card("sloggism_blue")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert st.players[1].dsl_queued_attack_mods, "nothing was queued"
    E._end_phase_iter(st)
    assert not getattr(st.players[1], "dsl_queued_attack_mods", []), \
        "an unused 'this turn' buff outlived the turn"


# --- the shape itself ------------------------------------------------------

@pytest.mark.parametrize("slug", ["strong_yield_blue", "sloggism_blue",
                                 "emerging_dominance_red", "force_sight_red"])
def test_next_attack_cards_use_the_one_shot_primitive(slug):
    # Guards against a future edit reintroducing either wrong shape. Both are
    # plausible-looking JSON that buffs every attack instead of one.
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "engine" / "card_effects" / "json"
    path = [p for p in root.rglob(f"{slug}.json")
            if not any(part.startswith(".") for part in p.parts)][0]
    abilities = json.dumps(json.loads(path.read_text(encoding="utf-8"))["abilities"])
    assert "MODIFY_NEXT_ATTACK" in abilities
    assert "APPLY_CONTINUOUS" not in abilities, \
        "a turn-long continuous buffs every attack, not the next one"
    assert "FLAG_SET" not in abilities, \
        "a turn flag plus a flag-gated static buffs every attack, not the next one"
