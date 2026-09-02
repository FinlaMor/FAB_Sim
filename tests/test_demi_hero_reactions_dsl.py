"""Arakni demi-hero Once-per-Turn Attack Reactions.

Each demi-hero's reaction differs:
  * black_widow — discard an Assassin: target Assassin attack +3; stealth →
    "on hit, they banish a card from their hand"
  * funnel_web  — same, stealth → "on hit, banish a card in their arsenal"
  * redback     — same, stealth → go again
  * tarantula   — discard an Assassin: target DAGGER attack +3 (no rider)
These fire at the combat reaction step via hero activation (ACTIVATE_CARD).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import engine.engine as E
from engine.actions import Action, ActionType
from engine.card import Card
from engine.card_effects.dsl import load_all_cards
from engine.play import apply_action, available_actions
from engine.state import CombatState, GameState, Player, Step

load_all_cards()


def _hero(pid, slug):
    c = Card(slug=slug, name=slug, types=["Chaos", "Assassin", "Demi-Hero"],
             base_life=40, base_intellect=4)
    c.owner = pid
    c.controller = pid
    return c


def _assassin_card(slug, owner, classes=("Assassin",), subtypes=("Attack",)):
    c = Card(slug=slug, name=slug, types=["Action"], subtypes=list(subtypes),
             classes=list(classes))
    c.owner = owner
    c.controller = owner
    return c


def _pick_first(state, options, context=None):
    return options[0] if options else None


def _state(demi_slug, stealth=True, attack_classes=("Assassin",),
           attack_subtypes=("Attack",)):
    st = GameState(
        players={1: Player(1, _hero(1, demi_slug)), 2: Player(2, _hero(2, "test_hero"))},
        active_player=1,
        player_agents={1: _pick_first, 2: _pick_first},
        step=Step.COMBAT_REACTION, turn_number=1, combat=None, done=False, winner=None,
    )
    ac = _assassin_card("some_dagger", 1, classes=list(attack_classes),
                        subtypes=list(attack_subtypes))
    ac.base_power = 4
    st.combat = CombatState(attacker_id=1, link_id=1, attack_power=4,
                            base_attack_power=4, attack_card=ac,
                            keywords=(["Stealth"] if stealth else []), from_weapon=False)
    # Player 1 holds an Assassin card to pay the discard cost.
    st.players[1].hand.add(_assassin_card("fodder", 1))
    return st


def _activate_hero(st):
    action = Action(type=ActionType.ACTIVATE_CARD, player_id=1,
                    card=st.players[1].hero, target=st.combat.attack_card)
    apply_action(st, action)


# ── the reaction is offered as a legal action at reaction timing ─────────────

def test_black_widow_reaction_is_offered():
    st = _state("arakni_black_widow")
    acts = available_actions(st, 1)
    assert any(a.type == ActionType.ACTIVATE_CARD and a.card is st.players[1].hero
               for a in acts)


def test_reaction_not_offered_without_assassin_to_discard():
    st = _state("arakni_black_widow")
    st.players[1].hand.cards.clear()  # no Assassin card to discard
    acts = available_actions(st, 1)
    assert not any(a.type == ActionType.ACTIVATE_CARD and a.card is st.players[1].hero
                   for a in acts)


def test_reaction_not_offered_against_non_assassin_attack():
    st = _state("arakni_black_widow", attack_classes=("Warrior",))
    acts = available_actions(st, 1)
    assert not any(a.type == ActionType.ACTIVATE_CARD and a.card is st.players[1].hero
                   for a in acts)


# ── +3 power and the discard cost ────────────────────────────────────────────

def test_black_widow_reaction_buffs_and_discards():
    st = _state("arakni_black_widow")
    hand_before = len(st.players[1].hand.cards)
    _activate_hero(st)
    assert st.combat.attack_power == 7          # 4 + 3
    assert len(st.players[1].hand.cards) == hand_before - 1  # discarded the Assassin


def test_once_per_turn_flag_blocks_second_use():
    st = _state("arakni_black_widow")
    st.players[1].hand.add(_assassin_card("fodder2", 1))  # a second Assassin
    _activate_hero(st)
    assert "black_widow_ar_used" in st.players[1].current_turn_effects
    acts = available_actions(st, 1)
    assert not any(a.type == ActionType.ACTIVATE_CARD and a.card is st.players[1].hero
                   for a in acts)


# ── stealth riders differ per demi-hero ──────────────────────────────────────

def test_black_widow_stealth_injects_on_hit_banish():
    st = _state("arakni_black_widow", stealth=True)
    _activate_hero(st)
    assert len(_attached_on_hit_triggers(st)) == 1


def test_black_widow_no_rider_without_stealth():
    st = _state("arakni_black_widow", stealth=False)
    _activate_hero(st)
    assert len(st.combat.injected_triggers) == 0


def test_redback_stealth_grants_go_again():
    st = _state("arakni_redback", stealth=True)
    _activate_hero(st)
    assert any(k.lower() == "go again" for k in st.combat.keywords)


def test_redback_no_go_again_without_stealth():
    st = _state("arakni_redback", stealth=False)
    _activate_hero(st)
    assert not any(k.lower() == "go again" for k in st.combat.keywords)


def test_black_widow_on_hit_banishes_from_defender_hand():
    st = _state("arakni_black_widow", stealth=True)
    E._setup_dsl_listeners(st)  # so the hit listener fires injected triggers
    victim = _assassin_card("victim", 2)
    st.players[2].hand.add(victim)
    _activate_hero(st)
    # Fire the attack's hit; the injected on-hit trigger banishes from P2's hand.
    from engine.state import Event
    st.event_manager.emit(Event(type="hit", card=st.combat.attack_card.slug,
                                data={"damage": 7}), st)
    assert victim in st.players[2].banished.cards


# ── tarantula: dagger attack, NO stealth rider ───────────────────────────────

def test_tarantula_reaction_buffs_dagger_attack():
    st = _state("arakni_tarantula", stealth=True,
                attack_classes=("Assassin",), attack_subtypes=("Attack", "Dagger"))
    _activate_hero(st)
    assert st.combat.attack_power == 7          # +3
    assert len(st.combat.injected_triggers) == 0  # tarantula has no rider


def test_tarantula_not_offered_against_non_dagger():
    st = _state("arakni_tarantula", attack_subtypes=("Attack",))  # no Dagger subtype
    acts = available_actions(st, 1)
    assert not any(a.type == ActionType.ACTIVATE_CARD and a.card is st.players[1].hero
                   for a in acts)


# ── orb_weaver: Instant (not a reaction), equip Graphene + next stealth +3 ────

def _orb_state():
    from engine.card import CardDB
    st = GameState(
        players={1: Player(1, _hero(1, "arakni_orb_weaver")), 2: Player(2, _hero(2, "t"))},
        active_player=1,
        player_agents={1: _pick_first, 2: _pick_first},
        step=Step.ACTION, turn_number=1, combat=None, done=False, winner=None,
    )
    st.card_db = CardDB()
    st.players[1].hand.add(_assassin_card("fodder", 1))
    return st


def test_orb_weaver_instant_equips_graphene_and_queues_stealth_buff():
    st = _orb_state()
    action = Action(type=ActionType.ACTIVATE_CARD, player_id=1, card=st.players[1].hero)
    apply_action(st, action)
    # Graphene token equipped into a weapon zone.
    assert st.players[1].weapon1.find("graphene_chelicera") is not None
    # Next stealth attack +3 queued.
    mods = getattr(st.players[1], "dsl_queued_attack_mods", [])
    assert any(m.get("amount") == 3 for m in mods)
    assert "orb_weaver_instant_used" in st.players[1].current_turn_effects


def test_orb_weaver_graphene_token_has_stealth():
    st = _orb_state()
    action = Action(type=ActionType.ACTIVATE_CARD, player_id=1, card=st.players[1].hero)
    apply_action(st, action)
    token = st.players[1].weapon1.find("graphene_chelicera")
    assert token is not None
    assert any(k.lower() == "stealth" for k in (token.keywords or []))


# ── trap_door: on-become search + face-down banish ───────────────────────────

def _deck_state(hero_slug="arakni_marionette"):
    from engine.card import CardDB
    st = GameState(
        players={1: Player(1, _hero(1, hero_slug)), 2: Player(2, _hero(2, "t"))},
        active_player=1,
        player_agents={1: _pick_first, 2: _pick_first},
        step=Step.END_PHASE_BEGINNING, turn_number=1, combat=None, done=False, winner=None,
    )
    st.card_db = CardDB()
    return st


def _trap(slug, owner=1, cost=0):
    c = Card(slug=slug, name=slug, types=["Action"], subtypes=["Trap"])
    c.owner = owner
    c.controller = owner
    c.raw_cost = cost
    return c


def test_trap_door_on_become_banishes_a_card_face_down():
    from engine.card_effects.dsl import dispatch
    st = _deck_state("arakni_trap_door")
    trap = _trap("snare_trap")
    st.players[1].deck.add(trap)
    st.players[1].deck.add(_trap("other", 1))
    dispatch(st, "ON_BECOME", "arakni_trap_door", card=st.players[1].hero)
    banished = st.players[1].banished.cards
    assert len(banished) == 1
    assert banished[0].is_public is False           # face-down
    assert trap in st.players[1].playable_from_banished  # was a Trap


def test_trap_door_banished_trap_is_playable_then_expires():
    from engine.card_effects.dsl import dispatch
    from engine.play import recalculate_playable
    from engine.engine import start_of_turn_refresh_player
    st = _deck_state("arakni_trap_door")
    trap = _trap("snare_trap")
    st.players[1].deck.add(trap)
    dispatch(st, "ON_BECOME", "arakni_trap_door", card=st.players[1].hero)
    recalculate_playable(st, 1)
    assert trap.playable is True            # playable from banished
    # At the start of this player's next turn the grant expires.
    start_of_turn_refresh_player(st, 1)
    recalculate_playable(st, 1)
    assert trap.playable is False
    assert trap in st.players[1].banished.cards  # still banished, just not playable


def test_trap_door_non_trap_not_playable_from_banished():
    from engine.card_effects.dsl import dispatch
    st = _deck_state("arakni_trap_door")
    non_trap = Card(slug="just_a_card", name="X", types=["Action"], subtypes=["Attack"])
    non_trap.owner = 1
    non_trap.controller = 1
    non_trap.raw_cost = 1
    st.players[1].deck.add(non_trap)
    dispatch(st, "ON_BECOME", "arakni_trap_door", card=st.players[1].hero)
    assert non_trap not in st.players[1].playable_from_banished


def test_become_trap_door_fires_on_become_search():
    from engine.card_effects.ability_keywords import become_agent_of_chaos
    st = _deck_state("arakni_marionette")
    st.players[1].deck.add(_trap("snare_trap"))
    # Agent picks trap_door to become, then the trap to banish.
    def _agent(state, options, context=None):
        if options and "arakni_trap_door" in options:
            return "arakni_trap_door"
        return options[0] if options else None
    st.player_agents[1] = _agent
    become_agent_of_chaos(st, 1, choose=True)
    assert st.players[1].hero.slug == "arakni_trap_door"
    assert len(st.players[1].banished.cards) == 1   # on-become search fired


def _attached_on_hit_triggers(state):
    """Every ON_HIT ability granted to the current attack, wherever it lives.

    A grant to an attack ACTION CARD attaches to the card (the attack IS the
    card); a grant to a WEAPON's attack stays on the combat, because the attack
    is a proxy object that dies with the chain link (CR 1.4.3c/e). Tests that
    only knew about combat.injected_triggers were asserting the storage rather
    than the behaviour.
    """
    out = [td for td in (getattr(state.combat, "injected_triggers", None) or [])
           if td.event_type == "ON_HIT"]
    attack = getattr(state.combat, "attack_card", None)
    out += [g for g in (getattr(attack, "granted_abilities", None) or [])
            if str(g.get("trigger", "")).upper() == "ON_HIT"]
    return out
