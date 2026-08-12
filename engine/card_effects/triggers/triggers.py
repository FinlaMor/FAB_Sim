"""Trigger registry for FAB engine — maps cards to their triggered effects.

Design:
  1. KEYWORD_TRIGGERS: auto-registered based on ability_keywords from slug_index.
     When a card has e.g. "Battleworn" in its keywords, the corresponding
     trigger function is registered for the appropriate event.

  2. CARD_TRIGGERS: card-specific triggers keyed by slug. These handle unique
     card text that can't be captured by keyword templates.

  3. Template functions: reusable builders for common patterns like
     "on hit draw a card", "on attack get +N power", etc.

Events emitted by the engine (must match EventManager event types):
  start_of_game, start_of_turn, start_of_action_phase, start_of_end_phase,
  attacking, defend, combat_chain_close, damage_dealt, hit, on_play,
  card_destroyed, enters_arena, target_of_attack, card_pitched, card_banished

Rules reference:
  5.4.6 — Triggered-static abilities
  6.6   — Triggered effects
  8.3   — Ability keyword triggers
  8.4   — Label keyword triggers
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from engine.state import GameState, Event, Player
    from engine.card import Card, CardDB

from engine.card import CardEffect
from engine.card_effects.ability_keywords import (
    battleworn, blade_break, temper, guardwell,
    go_again, dominate_check, overpower_check, piercing,
    phantasm_check, phantasm_destroy, spectra_destroy,
    blood_debt, suspense_remove_counter, suspense_enter,
    watery_grave, boost, heave, crank, fusion,
    arcane_barrier, spellvoid, ward, quell, arcane_shelter,
    crush_check, reprise_check, combo_check, surge_check,
    rupture_check, channel_upkeep, galvanize,
    create_token, _controller_id, _get_controller,
    _get_opponent_of,
    roll_die, effect_crowd_boos, has_been_booed, effect_steal_token,
    effect_crowd_cheers as _effect_crowd_cheers,
    create_token_card,
)
from engine.effect_keywords import (
    draw,
    discard as _discard,
    banish,
    deal_damage,
    destroy,
    gain,
    opt,
    intimidate,
    put_counter,
    remove_counter,
    shuffle,
    amp,
    charge,
    mark,
    negate,
    DamageType, AssetType,
)


# Compatibility shim — triggers.py is being deleted in Step 4 of the DSL migration
def _move_to_graveyard(card, state):
    destroy(state, card, None)


def _discard_random(state, player_id: int, count: int = 1):
    """Discard N random cards from player_id's hand (card text: "discard a card")."""
    import random
    player = state.players[player_id]
    for _ in range(count):
        if not player.hand.cards:
            break
        card = random.choice(player.hand.cards)
        _discard(state, discard_target=card, discard_source=None, origin='hand')


def _deal_to_hero(state, target_id: int, amount: int, source_card, dtype=None):
    """Deal damage to the target player's hero (used by trigger templates)."""
    if dtype is None:
        dtype = DamageType.PHYSICAL
    hero = getattr(state.players[target_id], 'hero', None)
    if hero is None:
        return
    deal_damage(state, amount=amount, damage_type=dtype,
                source_player_id=_controller_id(source_card),
                damage_target=hero, damage_source='card', damage_source_card=source_card)


def _opt_with_agent(state, player_id: int, n: int, source_player_id: int = None):
    """Run opt, asking the player's agent for card ordering (used by trigger templates)."""
    from engine.card_effects.ability_keywords import _ask_player
    def _selector(cards):
        top, bottom = [], []
        for card in cards:
            choice = _ask_player(state, player_id, ['top', 'bottom'],
                                 context=f"Opt: put {card.slug} on top or bottom?")
            (top if choice == 'top' else bottom).append(card)
        return top, bottom
    opt(state, n=n, target_player_id=player_id, selector=_selector,
        source_player_id=source_player_id or player_id)


# ---------------------------------------------------------------------------
# Private helpers for CARD_TRIGGERS implementations
# These call effect_keywords directly with correct signatures.
# ---------------------------------------------------------------------------

def _put_counter(state, card, counter_type: str, amount: int = 1):
    for _ in range(amount):
        put_counter(state, counter_type=counter_type, target_card=card)


def _deal_arcane(state, target_id: int, amount: int, source_card=None):
    hero = getattr(state.players[target_id], 'hero', None)
    if hero is None:
        return 0
    source_pid = _controller_id(source_card) if source_card is not None else (3 - target_id)
    evt = deal_damage(state, amount=amount, damage_type=DamageType.ARCANE,
                      source_player_id=source_pid, damage_target=hero,
                      damage_source='card', damage_source_card=source_card)
    return getattr(evt, 'amount', 0) if evt and not getattr(evt, 'canceled', False) else 0


def _gain_life(state, player_id: int, amount: int):
    gain(state, AssetType.LIFE, amount, player_id, target_player_id=player_id)


def _intimidate(state, target_player_id: int):
    intimidate(state, source_player_id=3 - target_player_id, target_player_id=target_player_id)


def _mark(state, target_player_id: int):
    mark(state, target_player_id=target_player_id)


def _is_marked(state, player_id: int) -> bool:
    return state.players[player_id].class_counters.get("marked", 0) > 0


def effect_retrieve_dagger(state, player_id: int):
    """Retrieve a dagger from graveyard — pay {r} to equip to empty weapon zone."""
    from engine.card_effects.ability_keywords import _ask_player, _pitch_for_cost
    player = state.players[player_id]
    daggers = [c for c in player.graveyard.cards
                if "Dagger" in (c.types or []) and "Weapon" in (c.types or [])]
    if not daggers:
        return False
    all_weapon_cards = player.weapon1.cards + player.weapon2.cards
    has_2h = any("2H" in (c.types or []) for c in all_weapon_cards)
    if has_2h or len(all_weapon_cards) >= 2:
        return False
    choice = _ask_player(state, player_id, [True, False],
                         context="Retrieve a dagger from graveyard? (costs {r})")
    if not choice:
        return False
    if not _pitch_for_cost(player, 1, state):
        return False
    dagger_slugs = [d.slug for d in daggers]
    pick = _ask_player(state, player_id, dagger_slugs,
                       context="Choose dagger to retrieve")
    dagger = next((d for d in daggers if d.slug == pick), daggers[0])
    player.graveyard.remove(dagger)
    dagger.controller = player_id
    if not player.weapon1.cards:
        player.weapon1.add(dagger)
    elif not player.weapon2.cards:
        player.weapon2.add(dagger)
    return True


# ---------------------------------------------------------------------------
# Trigger definition
# ---------------------------------------------------------------------------

@dataclass
class TriggerDef:
    """A trigger definition that can be registered with the EventManager."""
    event_type: str                     # event name to listen for
    condition_fn: Optional[Callable] = None  # (card, event, state) -> bool
    effect_fn: Optional[Callable] = None     # (card, event, state) -> None
    is_optional: bool = False           # requires agent decision

    source_slug: str = ""               # slug of the card that has this trigger
    priority: int = 0                   # ordering hint (lower = earlier)


# ---------------------------------------------------------------------------
# Keyword → trigger mapping
# Keywords are matched from ability_keywords in slug_index and auto-registered.
# ---------------------------------------------------------------------------

def _defended_this_chain(card, event, state):
    """Check if this card defended during the current combat chain."""
    if not state.combat:
        return False
    return card in state.combat.defending_cards


def _is_attacking(card, event, state):
    """Check if this card is the current attack or was 'flicked' to hit."""
    # Check flick hit: event.data.card matches this card (Flick Knives retroactive hit)
    event_data = event.data if isinstance(event.data, dict) else {}
    flick_card = event_data.get("card")
    if flick_card is not None and getattr(flick_card, 'slug', '') == card.slug:
        return True
    if not state.combat:
        return False
    return state.combat.attack_card == card or state.combat.attack_card.slug == card.slug


def build_keyword_triggers(card: Card) -> list[TriggerDef]:
    """Build trigger definitions from a card's keywords.
    Returns a list of TriggerDef for each keyword the card has."""
    triggers = []
    keywords = card.keywords or []

    for kw in keywords:
        # Normalize CamelCase keywords from card DB (e.g. "BladeBreak" -> "blade break")
        kw_spaced = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', kw.strip())
        kw_lower = kw_spaced.lower()
        # Parse numbered keywords like "Ward 3", "Arcane Barrier 2"
        kw_base = re.sub(r'\s+\d+$', '', kw_lower).strip()
        kw_num_match = re.search(r'(\d+)$', kw)
        kw_num = int(kw_num_match.group(1)) if kw_num_match else 0

        # --- Combat chain close triggers (equipment keywords) ---
        if kw_base == "battleworn":
            triggers.append(TriggerDef(
                event_type="combat_chain_close",
                condition_fn=_defended_this_chain,
                effect_fn=lambda c, e, s: battleworn(c, e, s),
            ))

        elif kw_base == "blade break":
            triggers.append(TriggerDef(
                event_type="combat_chain_close",
                condition_fn=_defended_this_chain,
                effect_fn=lambda c, e, s: blade_break(c, e, s),
            ))

        elif kw_base == "temper":
            triggers.append(TriggerDef(
                event_type="combat_chain_close",
                condition_fn=_defended_this_chain,
                effect_fn=lambda c, e, s: temper(c, e, s),
            ))

        elif kw_base == "guardwell":
            triggers.append(TriggerDef(
                event_type="combat_chain_close",
                condition_fn=_defended_this_chain,
                effect_fn=lambda c, e, s: guardwell(c, e, s),
            ))

        # --- Triggered static abilities ---
        elif kw_base == "phantasm":
            triggers.append(TriggerDef(
                event_type="defend",
                condition_fn=lambda c, e, s: phantasm_check(c, e, s),
                effect_fn=lambda c, e, s: phantasm_destroy(c, e, s),
            ))

        elif kw_base == "spectra":
            triggers.append(TriggerDef(
                event_type="target_of_attack",
                effect_fn=lambda c, e, s: spectra_destroy(c, e, s),
            ))

        elif kw_base == "blood debt":
            triggers.append(TriggerDef(
                event_type="start_of_end_phase",
                condition_fn=lambda c, e, s: c.zone == "banished" and c.is_public,
                effect_fn=lambda c, e, s: blood_debt(c, e, s),
            ))

        elif kw_base == "watery grave":
            triggers.append(TriggerDef(
                event_type="card_destroyed",
                effect_fn=lambda c, e, s: watery_grave(c, e, s),
            ))

        elif kw_base == "suspense":
            triggers.append(TriggerDef(
                event_type="enters_arena",
                effect_fn=lambda c, e, s: suspense_enter(c, s),
            ))
            triggers.append(TriggerDef(
                event_type="start_of_turn",
                effect_fn=lambda c, e, s: suspense_remove_counter(c, e, s),
            ))

        # --- Static abilities (not triggers — handled elsewhere) ---
        elif kw_base in ("dominate", "overpower", "go again", "stealth",
                         "legendary", "universal", "cloaked", "ephemeral",
                         "pairs", "perched", "unlimited", "modular",
                         "protect", "ambush", "meld"):
            pass

        # --- Optional play-static abilities ---
        elif kw_base == "boost":
            triggers.append(TriggerDef(
                event_type="on_play",
                effect_fn=lambda c, e, s: boost(c, s),
                is_optional=True,
                
            ))

        elif kw_base.endswith("fusion"):
            supertype = kw_base.replace(" fusion", "").strip().title()
            fusion_map = {
                "Ice": "Elemental", "Lightning": "Elemental",
                "Earth": "Elemental", "Light": "Light",
                "Shadow": "Shadow", "Draconic": "Draconic",
            }
            st = fusion_map.get(supertype, supertype)
            triggers.append(TriggerDef(
                event_type="on_play",
                effect_fn=lambda c, e, s, _st=st: fusion(c, _st, s),
                is_optional=True,
                
            ))

        # --- Numbered abilities ---
        elif kw_base == "piercing":
            n = kw_num
            triggers.append(TriggerDef(
                event_type="defend",
                condition_fn=_is_attacking,
                effect_fn=lambda c, e, s, _n=n: piercing(c, _n, s),
            ))

        elif kw_base == "heave":
            n = kw_num
            triggers.append(TriggerDef(
                event_type="start_of_end_phase",
                condition_fn=lambda c, e, s: c.zone == "hand",
                effect_fn=lambda c, e, s, _n=n: heave(c, _n, s),
                is_optional=True,
                
            ))

        elif kw_base == "opt":
            n = kw_num or 1
            triggers.append(TriggerDef(
                event_type="on_play",
                effect_fn=lambda c, e, s, _n=n: opt(s, n=_n, target_player_id=_controller_id(c)),
            ))

        elif kw_base == "crank":
            triggers.append(TriggerDef(
                event_type="enters_arena",
                effect_fn=lambda c, e, s: crank(c, s),
                is_optional=True,
                
            ))

        elif kw_base == "transform":
            pass  # Card-specific — transform targets vary per card

        elif kw_base == "charge":
            pass  # Card-specific — charge conditions vary per card

        elif kw_base == "mark":
            pass  # Discrete effect, applied by card text

        elif kw_base == "the crowd cheers":
            # Route through the keyword function rather than appending a raw
            # flag: the flag this used to write was read by nothing.
            triggers.append(TriggerDef(
                event_type="on_play",
                effect_fn=lambda c, e, s: _effect_crowd_cheers(
                    s, _controller_id(c)),
            ))

        elif kw_base == "contract":
            pass  # Card-specific — contract conditions vary per card

        elif kw_base == "clash":
            pass  # Card-specific — clash resolution varies per card

        elif kw_base == "combo":
            pass  # Card-specific — combo names vary per card

        elif kw_base == "crush":
            pass  # Card-specific — crush effects vary per card

        elif kw_base == "reprise":
            pass  # Card-specific — reprise effects vary per card

        elif kw_base == "surge":
            pass  # Card-specific — surge amounts/effects vary per card

        elif kw_base == "rune gate":
            # 8.3.27: If you control Runechants >= cost, play from banished without paying cost
            pass  # Handled by legal_actions play-from-banished check

    return triggers


# ---------------------------------------------------------------------------
# Card-specific triggers — removed.
# All card-specific behavior is owned by the JSON DSL under
# engine/card_effects/json/. CARD_TRIGGERS remains only as an (empty) hook
# for the registration machinery; do not add Python card effects here.
# ---------------------------------------------------------------------------
CARD_TRIGGERS: dict[str, list[TriggerDef]] = {}

# Meld cards (top/bottom halves) — awaiting DSL implementations.
MELD_EFFECT_REGISTRY: dict = {}


def get_triggers_for_card(card: Card) -> list[TriggerDef]:
    """Keyword-derived triggers for a card.

    Card-specific effects live in the JSON DSL and are dispatched by
    _setup_dsl_listeners; only CR section-8 keyword triggers are built here.
    """
    triggers = build_keyword_triggers(card)
    for t in triggers:
        t.source_slug = card.slug
    return triggers


def register_card_triggers(card: Card, event_manager) -> None:
    """Register all triggers for a card with the EventManager.

    Per CR 6.6.5-6.6.6: when a trigger condition is met, the effect creates a
    triggered-layer that is added to the stack. Players then receive priority
    before it resolves. Triggers are queued as StackEntry objects (is_triggered=True)
    rather than executing synchronously.
    """
    from engine.state import StackEntry

    triggers = get_triggers_for_card(card)
    for trigger in triggers:
        def make_listener(trig, source_card):
            def listener(event, state):
                # CR 5.4.6a / CR 1.7.4: triggered-static abilities are only functional
                # when their source card is public (face-up in a public zone).
                if not source_card.is_public:
                    return
                # Static suppression: e.g. A Good Clean Fight silences opponent cards
                # while attacking.  Set card._triggers_suppressed = True to disable.
                if getattr(source_card, '_triggers_suppressed', False):
                    return
                if trig.condition_fn and not trig.condition_fn(source_card, event, state):
                    return
                if trig.effect_fn:
                    player_id = _controller_id(source_card)
                    captured_event = event
                    # Wrap effect_fn so resolve_stack() can call it as (card, game_state)
                    def resolve_fn(c, gs, _e=captured_event, _fn=trig.effect_fn):
                        _fn(c, _e, gs)
                    # CR 6.6.6: add triggered-layer to stack; resolves when priority passes
                    # CR 1.6.2c: Triggered effect (triggered-layer)
                    # CR 3.15.4: layer position is N+1 where N is existing layers
                    entry = StackEntry(
                        player_id=player_id,
                        card=source_card,
                        layer_type='triggered',
                        layer_position=len(state.stack_entries) + 1,
                        is_triggered=True,
                        trigger_event=trig.event_type,
                        effect_fn=resolve_fn,
                    )
                    state.stack_entries.append(entry)
            return listener

        event_manager.register(trigger.event_type, make_listener(trigger, card))


def register_hero_triggers(hero_card, player, event_manager) -> None:
    """Register passive triggered hero abilities from HERO_TRIGGERS."""
    from engine.card_effects.registry import HERO_TRIGGERS
    slug = hero_card.slug
    triggers_list = HERO_TRIGGERS.get(slug, [])
    for tdef in triggers_list:
        event_type = tdef["event"]
        cond_fn = tdef.get("condition_fn")
        eff_fn = tdef.get("effect_fn")
        if eff_fn is None:
            continue

        def make_hero_listener(p=player, cf=cond_fn, ef=eff_fn):
            def listener(event, state):
                if cf and not cf(p, event, state):
                    return
                ef(p, event, state)
            return listener

        event_manager.register(event_type, make_hero_listener())


def register_all_triggers(state: GameState) -> None:
    """Register triggers for all public cards of all players."""
    for player_id in state.players:
        player = state.players[player_id]
        for card in player.public_cards:
            register_card_triggers(card, state.event_manager)
        register_hero_triggers(player.hero, player, state.event_manager)

