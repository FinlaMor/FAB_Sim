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
from tests.conftest import _card_json

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


# --- "the next CARD you play": the play-time queue -------------------------
# The attack queue is consumed in _apply_turn_attack_effects, so only ever by an
# attack. "The next BLUE ACTION card" and "the next NON-ATTACK action card" name
# cards that may never attack — queued there, they would never fire at all.

def _play(st, card, pid=1):
    """Run the play-time cost path, which is what consumes the card queue."""
    from engine.actions import Action, ActionType
    import engine.play as P
    card.owner = card.controller = pid
    st.players[pid].hand.add(card)
    action = Action(ActionType.PLAY_CARD, pid, card)
    P._pay_costs(st, pid, action)
    return card


def _action_card(pitch=3, is_attack=False, classes=("Generic",)):
    c = Card(slug="target", name="target", types=["Action"],
             subtypes=["Attack"] if is_attack else [])
    c.pitch = pitch
    c.raw_cost = 1
    c.classes = list(classes)
    c.power = c.base_power = 3 if is_attack else None
    return c


def test_fasting_carcass_grants_go_again_to_the_next_blue_action():
    st = _state()
    card = _card("fasting_carcass_blue")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    target = _play(st, _action_card(pitch=3))
    assert "Go Again" in (target.keywords or [])


def test_fasting_carcass_ignores_a_card_of_the_wrong_colour():
    st = _state()
    card = _card("fasting_carcass_blue")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    target = _play(st, _action_card(pitch=1))       # red
    assert "Go Again" not in (target.keywords or [])


def test_fasting_carcass_grants_to_one_card_only():
    st = _state()
    card = _card("fasting_carcass_blue")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    first = _play(st, _action_card(pitch=3))
    second = _play(st, _action_card(pitch=3))
    assert "Go Again" in (first.keywords or [])
    assert "Go Again" not in (second.keywords or []),         "every blue action was granted go again, not the next one"


def test_mage_master_boots_skips_an_attack_action():
    # "the next NON-ATTACK action card". An attack must not consume it.
    st = _state()
    card = _card("mage_master_boots")
    dispatch(st, "ON_ACTIVATE", card.slug, card=card, event=None)
    attack_card = _play(st, _action_card(is_attack=True))
    assert "Go Again" not in (attack_card.keywords or [])
    non_attack = _play(st, _action_card(is_attack=False))
    assert "Go Again" in (non_attack.keywords or [])


# --- talents, names, and chain scope --------------------------------------

def _talent_attack(st, talents=("Ice",), power=3, pid=1, slug="atk"):
    atk = Card(slug=slug, name=slug, types=["Action"], subtypes=["Attack"])
    atk.owner = atk.controller = pid
    atk.power = atk.base_power = power
    atk.talents = list(talents)
    st.combat = CombatState(attacker_id=pid, link_id=1, attack_power=power,
                            attack_card=atk, keywords=[])
    st.combat.base_attack_power = power
    E._apply_turn_attack_effects(st, atk)
    E._register_card_continuous_effects(st, atk)
    E._recalculate_attack_power(st)
    return st.combat.attack_power


def test_weave_ice_matches_a_talent_not_just_a_class():
    # "Ice or Elemental" are TALENTS. ATTACK_CLASS_IN read only `classes`, so it
    # matched neither and the filter matched nothing at all.
    st = _state()
    card = _card("weave_ice_yellow")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert _talent_attack(st, talents=["Ice"]) == 5


def test_weave_ice_ignores_an_unrelated_talent():
    st = _state()
    card = _card("weave_ice_yellow")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert _talent_attack(st, talents=["Shadow"]) == 3


def test_wind_chakra_matches_the_card_name_across_colours():
    # "The next Crouching Tiger" names the CARD, which spans every colour.
    st = _state()
    card = _card("wind_chakra_red")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert _attack(st, power=3, slug="crouching_tiger_yellow") == 6


def test_wind_chakra_ignores_a_different_card():
    st = _state()
    card = _card("wind_chakra_red")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert _attack(st, power=3, slug="some_other_attack") == 3


def test_wind_chakra_gives_five_after_transcending():
    # "instead" — the two amounts are branches of one conditional, so they must
    # never both land.
    from engine.effect_keywords import _record_turn_event
    st = _state()
    _record_turn_event(st, 1, "transcend")
    card = _card("wind_chakra_red")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert _attack(st, power=3, slug="crouching_tiger_red") == 8


def test_chain_scoped_grant_does_not_survive_the_chain():
    # "this COMBAT CHAIN" is narrower than "this turn": the grant must be gone
    # when the chain closes, not waiting to buff an attack in a later chain.
    st = _state()
    card = _card("ride_the_tailwind_blue")
    dispatch(st, "ON_HIT", card.slug, card=card, event=None)
    assert st.players[1].dsl_queued_attack_mods, "nothing was queued"
    E._close_step(st)
    assert not [m for m in st.players[1].dsl_queued_attack_mods
                if str(m.get("scope", "")).upper() == "CHAIN"],         "a chain-scoped grant outlived its combat chain"


def test_turn_scoped_grant_survives_a_chain_close():
    # The other half of the same rule: a TURN-scoped one-shot must NOT be
    # dropped just because a chain closed.
    st = _state()
    card = _card("quick_succession_red")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    E._close_step(st)
    assert st.players[1].dsl_queued_attack_mods,         "a turn-scoped grant was dropped at chain close"


# --- dynamic amounts and source filters on prevention ---------------------

def test_dampen_prevents_what_it_actually_dealt():
    # "X is the damage dealt by Dampen." PREVENT_DAMAGE coerced its amount to an
    # int at COMPILE time, so any expression became 0 — a shield preventing
    # nothing at all.
    from engine.effect_keywords import DamageType
    st = _state()
    card = _card("dampen_yellow")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert _hit(st, 5, dtype=DamageType.ARCANE) == 2,         "the shield did not absorb the 3 arcane damage Dampen dealt"


def test_dampen_shield_is_arcane_only():
    from engine.effect_keywords import DamageType
    st = _state()
    card = _card("dampen_yellow")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert _hit(st, 5, dtype=DamageType.PHYSICAL) == 5


def _shadow_hit(st, amount, shadow=True, pid=1):
    from engine.effect_keywords import DamageType, deal_damage
    src = Card(slug="src", name="src", types=["Action"])
    src.owner = src.controller = 3 - pid
    src.talents = ["Shadow"] if shadow else ["Light"]
    before = st.players[pid].life
    deal_damage(st, amount=amount, damage_type=DamageType.PHYSICAL,
                source_player_id=3 - pid, damage_target=st.players[pid].hero,
                damage_source="effect", damage_source_card=src)
    return before - st.players[pid].life


def test_break_of_dawn_prevents_shadow_damage():
    st = _state()
    card = _card("break_of_dawn_red")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert _shadow_hit(st, 6, shadow=True) == 2


def test_break_of_dawn_ignores_a_non_shadow_source():
    # Unfiltered this is a flat 4-damage shield against anything, strictly
    # stronger than the card. The source restriction IS the card.
    st = _state()
    card = _card("break_of_dawn_red")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    assert _shadow_hit(st, 6, shadow=False) == 6


# --- the DEFENCE queue ----------------------------------------------------
# A card used to BLOCK passes through neither the attack queue (consumed by
# attacks) nor the play-time queue (consumed by cards being played), so "the
# next action card you defend with" had no queue at all.

def _defend(st, defender_id=2, defense=3, slug="blocker", types=("Action",)):
    """Declare a block through the real defend path, which is what reads {d}."""
    from engine.actions import Action, ActionType
    import engine.play as P
    blocker = Card(slug=slug, name=slug, types=list(types))
    blocker.owner = blocker.controller = defender_id
    blocker.defense = blocker.base_defense = defense
    st.players[defender_id].hand.add(blocker)
    atk = Card(slug="atk", name="atk", types=["Action"], subtypes=["Attack"])
    atk.owner = atk.controller = 3 - defender_id
    atk.power = atk.base_power = 5
    st.combat = CombatState(attacker_id=3 - defender_id, link_id=1,
                            attack_power=5, attack_card=atk, keywords=[])
    action = Action(ActionType.DEFEND_CARDS, defender_id, None)
    action.card_list = [blocker]
    P._apply_defend(st, action)
    return st.combat.total_defense


def _begin_opponents_turn(st, defender_id=2):
    """Start the turn of the player who is NOT the token's controller.

    Driven through the real listener rather than dispatching the DSL trigger
    by name: toughness fires "at the start of each OTHER hero's turn", and
    START_OF_TURN is delivered only to the TURN PLAYER's permanents. Naming the
    trigger directly bypasses exactly the dispatch this card depends on, so the
    test would pass while the card never fired in a real game.
    """
    import engine.engine as _E
    _E._setup_dsl_listeners(st)
    st.active_player = 3 - defender_id
    st.event_manager.emit('start_of_turn', st)


def test_toughness_buffs_the_next_block():
    st = _state()
    token = _card("toughness", owner=2)
    st.players[2].permanents.add(token)
    _begin_opponents_turn(st)                  # the opponent's turn has begun
    assert _defend(st, defender_id=2, defense=3) == 4


def test_toughness_buffs_one_block_only():
    st = _state()
    token = _card("toughness", owner=2)
    st.players[2].permanents.add(token)
    _begin_opponents_turn(st)
    assert _defend(st, defender_id=2, defense=3, slug="first") == 4
    assert _defend(st, defender_id=2, defense=3, slug="second") == 3,         "every block was buffed, not the next one"


def test_razor_ring_weakens_the_opponents_next_block():
    st = _state()
    card = _card("razor_ring_blue", owner=1)
    atk = Card(slug="rr", name="rr", types=["Action"], subtypes=["Attack"])
    atk.owner = atk.controller = 1
    atk.power = atk.base_power = 3
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=atk, keywords=[])
    dispatch(st, "ON_HIT", card.slug, card=card, event=None)
    # The mod goes on the OPPONENT, not on the card's controller.
    assert getattr(st.players[2], "dsl_queued_defense_mods", []),         "the -1{d} was queued on the wrong player"
    assert _defend(st, defender_id=2, defense=3) == 2


def test_defence_queue_respects_chain_scope():
    st = _state()
    card = _card("razor_ring_blue", owner=1)
    atk = Card(slug="rr", name="rr", types=["Action"], subtypes=["Attack"])
    atk.owner = atk.controller = 1
    atk.power = atk.base_power = 3
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=atk, keywords=[])
    dispatch(st, "ON_HIT", card.slug, card=card, event=None)
    E._close_step(st)
    assert not [m for m in getattr(st.players[2], "dsl_queued_defense_mods", [])
                if str(m.get("scope", "")).upper() == "CHAIN"],         "a chain-scoped defence mod outlived its combat chain"


# --- arcane amplification and multi-use reductions ------------------------

def test_multi_use_reduction_lasts_exactly_three_cards():
    # "The next 3 Draconic cards you play this turn cost {r} less" — one entry
    # with three uses. As a single-use entry two reductions are lost; as a
    # turn-long effect every Draconic card is cheaper forever.
    st = _state()
    card = _card("blood_of_the_dracai_red")
    dispatch(st, "ON_PITCH", card.slug, card=card, event=None)
    queued = st.players[1].dsl_queued_card_mods
    assert len(queued) == 1
    assert queued[0]["uses"] == 3
    import engine.play as P
    for expected in (2, 1):
        target = Card(slug="drac", name="drac", types=["Action"])
        target.owner = target.controller = 1
        target.classes = ["Draconic"]
        target.raw_cost = 3
        from engine.actions import Action, ActionType
        st.players[1].hand.add(target)
        P._pay_costs(st, 1, Action(ActionType.PLAY_CARD, 1, target))
        assert st.players[1].dsl_queued_card_mods[0]["uses"] == expected
    # third use spends the entry
    target = Card(slug="drac", name="drac", types=["Action"])
    target.owner = target.controller = 1
    target.classes = ["Draconic"]
    target.raw_cost = 3
    from engine.actions import Action, ActionType
    st.players[1].hand.add(target)
    P._pay_costs(st, 1, Action(ActionType.PLAY_CARD, 1, target))
    assert not st.players[1].dsl_queued_card_mods,         "the entry outlived its three uses"


def test_card_has_effect_reads_the_played_cards_own_json():
    # "with an effect that deals arcane damage" is knowable only from the card's
    # definition; a filter that cannot see it matches everything.
    from engine.card_effects.dsl.condition_types import compile_condition
    st = _state()
    fn = compile_condition("CARD_HAS_EFFECT", {"effect": "DEAL_ARCANE"})
    arcane = _card("aether_flare_blue")          # deals arcane damage
    plain = _card("overswing_blue")              # does not
    assert fn(arcane, None, st) is True
    assert fn(plain, None, st) is False


def test_card_cost_lte_asks_about_this_card():
    from engine.card_effects.dsl.condition_types import compile_condition
    st = _state()
    fn = compile_condition("CARD_COST_LTE", {"amount": 2})
    cheap = Card(slug="c", name="c", types=["Action"])
    cheap.raw_cost = 1
    dear = Card(slug="d", name="d", types=["Action"])
    dear.raw_cost = 5
    assert fn(cheap, None, st) is True
    assert fn(dear, None, st) is False


# --- boosted / charged / class grants -------------------------------------

def test_quickfire_buffs_only_an_attack_that_was_boosted():
    # A turn marker records only that the player boosted at some point, so it
    # would buff an attack that was never boosted. boost() marks the card.
    st = _state()
    card = _card("quickfire_red")
    dispatch(st, "ON_PLAY", card.slug, card=card, event=None)
    unboosted = Card(slug="plain", name="plain", types=["Action"],
                     subtypes=["Attack"])
    unboosted.owner = unboosted.controller = 1
    unboosted.power = unboosted.base_power = 3
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=unboosted, keywords=[])
    st.combat.base_attack_power = 3
    E._apply_turn_attack_effects(st, unboosted)
    E._register_card_continuous_effects(st, unboosted)
    E._recalculate_attack_power(st)
    assert st.combat.attack_power == 3, "an unboosted attack took the buff"

    boosted = Card(slug="boosted", name="boosted", types=["Action"],
                   subtypes=["Attack"])
    boosted.owner = boosted.controller = 1
    boosted.power = boosted.base_power = 3
    boosted.was_boosted = True
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=3,
                            attack_card=boosted, keywords=[])
    st.combat.base_attack_power = 3
    E._apply_turn_attack_effects(st, boosted)
    E._register_card_continuous_effects(st, boosted)
    E._recalculate_attack_power(st)
    assert st.combat.attack_power == 7


def test_boost_marks_the_card_it_boosted():
    from engine.card_effects.ability_keywords import boost
    st = _state()
    target = Card(slug="t", name="t", types=["Action"], subtypes=["Attack"])
    target.owner = target.controller = 1
    for i in range(3):
        c = Card(slug=f"d{i}", name=f"d{i}", types=["Action"])
        c.owner = c.controller = 1
        st.players[1].deck.add(c)
    boost(target, st)
    assert getattr(target, "was_boosted", False) is True


def test_fealty_grants_a_class_to_the_next_card_played():
    # "The next card you play this turn IS DRACONIC" — a class grant, neither a
    # keyword nor a number, ADDED to the card's own classes.
    st = _state()
    token = _card("fealty")
    st.players[1].permanents.add(token)
    dispatch(st, "ON_ACTIVATE", token.slug, card=token, event=None)
    from engine.actions import Action, ActionType
    import engine.play as P
    target = Card(slug="plain", name="plain", types=["Action"])
    target.owner = target.controller = 1
    target.classes = ["Ninja"]
    target.raw_cost = 1
    st.players[1].hand.add(target)
    P._pay_costs(st, 1, Action(ActionType.PLAY_CARD, 1, target))
    assert "Draconic" in target.classes
    assert "Ninja" in target.classes, "the grant replaced the card's own class"


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
    path = _card_json(root, f"{slug}.json")
    abilities = json.dumps(json.loads(path.read_text(encoding="utf-8"))["abilities"])
    assert "MODIFY_NEXT_ATTACK" in abilities
    assert "APPLY_CONTINUOUS" not in abilities, \
        "a turn-long continuous buffs every attack, not the next one"
    assert "FLAG_SET" not in abilities, \
        "a turn flag plus a flag-gated static buffs every attack, not the next one"
