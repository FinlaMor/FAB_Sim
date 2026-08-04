"""Turn-scoped attack hooks — the engine mechanism behind DSL `INJECT_TRIGGER`
with `scope: TURN|NEXT_TURN` and `MODIFY_ATTACKS_THIS_TURN`.

These exercise the REAL engine paths the feature runs through:
  - engine._apply_turn_attack_effects re-applies every hook to each attack, and
  - engine._dsl_hit_listener consumes the ON_HIT triggers the hooks re-inject.

The synthetic attack()/hit() helpers in test_batch_generated.py bypass both, so
turn-scoped behaviour (persist across MULTIPLE attacks) can only be verified here.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import engine.engine as E
from engine.card import Card, CardDB
from engine.state import CombatState, Event
from engine.effect_keywords import EventType
from engine.card_effects.dsl.loader import load_all_cards
from tests.conftest import _make_state


def _setup():
    load_all_cards()
    st = _make_state()
    st.card_db = CardDB()
    E._setup_dsl_listeners(st)  # registers _dsl_hit_listener on the 'hit' event
    # Base state has EMPTY decks, so any DRAW silently no-ops. Pre-stock both.
    for pid in (1, 2):
        for _ in range(20):
            c = Card(slug="dummy_card", name="dummy", types=["Action"])
            c.owner = c.controller = pid
            st.players[pid].deck.cards.append(c)
    return st


def _new_attack(st, pid, power=4):
    atk = Card(slug="swing", name="swing", types=["Attack"])
    atk.owner = atk.controller = pid
    atk.base_power = power
    atk.power = power
    st.combat = CombatState(attacker_id=pid, link_id=1, attack_power=power,
                            attack_card=atk, keywords=[])
    st.combat.base_attack_power = power
    return atk


def _resolve_attack(st, atk):
    # Mirror the real attack-resolution order (engine._attack_step): apply turn
    # effects, then register the card's continuous effects, then recompute power.
    E._apply_turn_attack_effects(st, atk)
    E._register_card_continuous_effects(st, atk)
    E._recalculate_attack_power(st)


def _emit_hit(st, defender_pid):
    st.combat.hit = True
    st.event_manager.emit(
        event=Event(type=EventType.HIT,
                    data={"target": st.players[defender_pid].hero.slug,
                          "target_type": "hero", "amount": st.combat.attack_power}),
        game_state=st)


def _emit_damage_dealt(st, defender_pid):
    # Mirror engine._attack_step's combat-damage emission (engine.py ~1612).
    st.combat.hit = True
    st.event_manager.emit(
        event=Event(type="damage_dealt",
                    data={"damage": st.combat.attack_power, "target": defender_pid}),
        game_state=st)


def test_power_mod_hook_applies_to_every_attack_this_turn():
    """A turn-scoped -1 power mod reduces EACH attack this turn, not just one."""
    st = _setup()
    pid = st.active_player
    st.players[pid].turn_attack_hooks.append(
        {"kind": "power_mod", "amount": -1,
         "conditions": [{"type": "ATTACK_TARGET_IS_HERO"}]})
    for _ in range(2):
        atk = _new_attack(st, pid, power=4)
        _resolve_attack(st, atk)
        assert st.combat.attack_power == 3  # 4 - 1, applied fresh each attack


def test_inject_trigger_hook_fires_on_every_hit_this_turn():
    """A turn-scoped ON_HIT hook fires on each attack's hit for the whole turn."""
    st = _setup()
    pid = st.active_player
    opp = 3 - pid
    st.players[pid].turn_attack_hooks.append(
        {"kind": "inject_trigger", "event": "ON_HIT",
         "conditions": [{"type": "ATTACK_TARGET_IS_HERO"}],
         "effects": [{"type": "LOSE_LIFE", "amount": 1, "player": "OPPONENT"}]})
    start = st.players[opp].health
    for _ in range(2):
        atk = _new_attack(st, pid)
        _resolve_attack(st, atk)
        _emit_hit(st, opp)
    assert st.players[opp].health == start - 2  # 1 per hit, both attacks


def test_turn_hook_expires_at_end_of_turn():
    """turn_attack_hooks created this turn are cleared when the turn's end phase
    runs (engine end-phase clear), so they do not bleed into later turns."""
    st = _setup()
    pid = st.active_player
    st.players[pid].turn_attack_hooks.append(
        {"kind": "power_mod", "amount": -1, "conditions": []})
    # Simulate the end-of-turn clear (engine.py end phase, line ~869).
    st.players[pid].turn_attack_hooks = []
    atk = _new_attack(st, pid, power=4)
    _resolve_attack(st, atk)
    assert st.combat.attack_power == 4  # no lingering modifier


def test_next_turn_hook_is_not_active_until_promoted():
    """A NEXT_TURN hook sits on next_turn_attack_hooks and does nothing until the
    turn-start rotation promotes it into turn_attack_hooks."""
    st = _setup()
    pid = st.active_player
    st.players[pid].next_turn_attack_hooks.append(
        {"kind": "power_mod", "amount": -1, "conditions": []})
    atk = _new_attack(st, pid, power=4)
    _resolve_attack(st, atk)
    assert st.combat.attack_power == 4  # not active yet
    # Promote (engine.py begin_turn rotation, line ~334).
    p = st.players[pid]
    p.turn_attack_hooks = p.next_turn_attack_hooks[:]
    p.next_turn_attack_hooks = []
    atk2 = _new_attack(st, pid, power=4)
    _resolve_attack(st, atk2)
    assert st.combat.attack_power == 3  # now active


# --- real cards fixed by the feature ---------------------------------------

def test_buzz_bolt_blue_fused_deals_1_on_every_hit_this_turn():
    """buzz_bolt_blue (fused): "whenever an attack hits a hero this turn, it deals
    1 damage to them" — every attack, not just buzz_bolt's own."""
    from engine.card_effects.dsl import dispatch
    st = _setup()
    pid = st.active_player
    opp = 3 - pid
    buzz = st.card_db.get("buzz_bolt_blue")
    buzz.owner = buzz.controller = pid
    # Simulate a successful Lightning Fusion (fusion() sets this marker).
    st.players[pid].current_turn_effects.append("fused_buzz_bolt_blue")
    dispatch(st, "ON_PLAY", "buzz_bolt_blue", card=buzz)
    assert any(h.get("kind") == "inject_trigger"
               for h in st.players[pid].turn_attack_hooks)
    start = st.players[opp].life
    for _ in range(2):
        atk = _new_attack(st, pid)
        _resolve_attack(st, atk)
        _emit_hit(st, opp)
    assert st.players[opp].life == start - 2  # 1 per hit, both attacks


def test_buzz_bolt_blue_not_fused_does_nothing():
    """Without a fuse, buzz_bolt registers no hook (the "if fused" gate)."""
    from engine.card_effects.dsl import dispatch
    st = _setup()
    pid = st.active_player
    opp = 3 - pid
    buzz = st.card_db.get("buzz_bolt_blue")
    buzz.owner = buzz.controller = pid
    dispatch(st, "ON_PLAY", "buzz_bolt_blue", card=buzz)
    assert st.players[pid].turn_attack_hooks == []
    start = st.players[opp].life
    atk = _new_attack(st, pid)
    _resolve_attack(st, atk)
    _emit_hit(st, opp)
    assert st.players[opp].life == start  # no extra damage


def test_this_rounds_on_me_blue_reduces_opponent_hero_attacks_next_turn():
    """this_rounds_on_me_blue: each hero draws; and until the caster's next turn,
    the opponent's attacks that target the caster get -1{p}."""
    from engine.card_effects.dsl import dispatch
    st = _setup()
    caster = st.active_player
    opp = 3 - caster
    card = st.card_db.get("this_rounds_on_me_blue")
    card.owner = card.controller = caster
    h_caster = len(st.players[caster].hand.cards)
    h_opp = len(st.players[opp].hand.cards)
    dispatch(st, "ON_PLAY", "this_rounds_on_me_blue", card=card)
    # each hero draws a card
    assert len(st.players[caster].hand.cards) == h_caster + 1
    assert len(st.players[opp].hand.cards) == h_opp + 1
    # the -1 is queued for the opponent's next turn, not active now
    assert any(h.get("kind") == "power_mod"
               for h in st.players[opp].next_turn_attack_hooks)
    assert st.players[opp].turn_attack_hooks == []
    # Opponent's turn start: rotate hooks + they become active.
    op = st.players[opp]
    op.turn_attack_hooks = op.next_turn_attack_hooks[:]
    op.next_turn_attack_hooks = []
    st.active_player = opp
    atk = _new_attack(st, opp, power=4)
    _resolve_attack(st, atk)
    assert st.combat.attack_power == 3  # 4 - 1 vs the caster's hero


def test_turn_scoped_on_deal_damage_hook_fires_each_attack():
    """A turn-scoped ON_DEAL_DAMAGE hook fires when each attack deals combat
    damage (the 'damage_dealt' path), for the whole turn."""
    st = _setup()
    pid = st.active_player
    opp = 3 - pid
    st.players[pid].turn_attack_hooks.append(
        {"kind": "inject_trigger", "event": "ON_DEAL_DAMAGE",
         "conditions": [{"type": "ATTACK_TARGET_IS_HERO"}],
         "effects": [{"type": "LOSE_LIFE", "amount": 1, "player": "OPPONENT"}]})
    start = st.players[opp].health
    for _ in range(2):
        atk = _new_attack(st, pid)
        _resolve_attack(st, atk)
        _emit_damage_dealt(st, opp)
    assert st.players[opp].health == start - 2


def test_chilling_icevein_yellow_fused_discards_on_attack_damage():
    """chilling_icevein_yellow (fused): whenever an attack deals damage to a hero
    this turn, they discard a card unless they pay {r}. Opponent with 0 resources
    and a card in hand discards it."""
    from engine.card_effects.dsl import dispatch
    st = _setup()
    pid = st.active_player
    opp = 3 - pid
    chill = st.card_db.get("chilling_icevein_yellow")
    chill.owner = chill.controller = pid
    st.players[pid].current_turn_effects.append("fused_chilling_icevein_yellow")
    dispatch(st, "ON_PLAY", "chilling_icevein_yellow", card=chill)
    assert any(h.get("kind") == "inject_trigger"
               and h.get("event") == "ON_DEAL_DAMAGE"
               for h in st.players[pid].turn_attack_hooks)
    # Defender: 0 resources, one card in hand -> cannot pay, must discard it.
    st.players[opp].resources = 0
    victim = Card(slug="dummy_card", name="dummy", types=["Action"])
    victim.owner = victim.controller = opp
    st.players[opp].hand.cards.append(victim)
    before = len(st.players[opp].hand.cards)
    atk = _new_attack(st, pid)
    _resolve_attack(st, atk)
    _emit_damage_dealt(st, opp)
    assert len(st.players[opp].hand.cards) == before - 1
