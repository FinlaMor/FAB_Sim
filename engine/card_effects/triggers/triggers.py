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
            triggers.append(TriggerDef(
                event_type="on_play",
                effect_fn=lambda c, e, s: s.players[_controller_id(c)]
                    .current_turn_effects.append("crowd_cheers"),
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
# Template trigger builders — reusable for common card text patterns
# ---------------------------------------------------------------------------

def on_hit_draw(count: int = 1) -> TriggerDef:
    """Template: "When this hits, draw N card(s)."."""
    return TriggerDef(
        event_type="hit",
        effect_fn=lambda c, e, s: draw(s, draw_player=_controller_id(c), number=count),
    )


def on_hit_damage(amount: int, damage_type: str = "generic") -> TriggerDef:
    """Template: "When this hits, deal N damage."."""
    dtype = DamageType.ARCANE if damage_type == "arcane" else DamageType.PHYSICAL
    def _effect(c, e, s):
        _deal_to_hero(s, 3 - _controller_id(c), amount, c, dtype)
    return TriggerDef(event_type="hit", effect_fn=_effect)


def on_hit_arcane(amount: int) -> TriggerDef:
    """Template: "When this hits, deal N arcane damage."."""
    return on_hit_damage(amount, "arcane")


def on_hit_discard(count: int = 1) -> TriggerDef:
    """Template: "When this hits a hero, they discard N card(s)."."""
    def _effect(c, e, s):
        _discard_random(s, 3 - _controller_id(c), count)
    return TriggerDef(event_type="hit", effect_fn=_effect)


def on_hit_gain_life(amount: int) -> TriggerDef:
    """Template: "When this hits, gain N life."."""
    def _effect(c, e, s):
        cid = _controller_id(c)
        gain(s, AssetType.LIFE, amount, cid, target_player_id=cid)
    return TriggerDef(event_type="hit", effect_fn=_effect)


def on_hit_lose_life(amount: int) -> TriggerDef:
    """Template: "When this hits, defending hero loses N life."."""
    def _effect(c, e, s):
        tid = 3 - _controller_id(c)
        gain(s, AssetType.LIFE, -amount, tid, target_player_id=tid)
    return TriggerDef(event_type="hit", effect_fn=_effect)


def on_hit_create_token(token_slug: str, count: int = 1) -> TriggerDef:
    """Template: "When this hits, create N token(s)."."""
    return TriggerDef(
        event_type="hit",
        effect_fn=lambda c, e, s: create_token(s, _controller_id(c), token_slug, count),
    )


def on_hit_intimidate() -> TriggerDef:
    """Template: "When this hits, intimidate."."""
    def _effect(c, e, s):
        cid = _controller_id(c)
        intimidate(s, source_player_id=cid, target_player_id=3 - cid)
    return TriggerDef(event_type="hit", effect_fn=_effect)


def on_hit_banish_top(count: int = 1) -> TriggerDef:
    """Template: "When this hits, banish the top N cards of defending hero's deck."."""
    def _effect(c, e, s):
        target_id = 3 - _controller_id(c)
        target = s.players[target_id]
        from engine.card_effects.ability_keywords import banish_card
        for _ in range(count):
            if target.deck.cards:
                top = target.deck.pop_top()
                banish_card(s, target, top, face_up=True)
    return TriggerDef(event_type="hit", effect_fn=_effect)


def on_attack_power_bonus(amount: int) -> TriggerDef:
    """Template: "When this attacks, it gets +N{p}."."""
    def _effect(c, e, s):
        if s.combat and s.combat.attack_card:
            s.combat.attack_card.effects.append(
                CardEffect(prop="power", stage=7, substage=5, fn=lambda val, n=amount: val + n))
    return TriggerDef(event_type="attacking", effect_fn=_effect)


def on_attack_draw(count: int = 1) -> TriggerDef:
    """Template: "When this attacks, draw N card(s)."."""
    return TriggerDef(
        event_type="attacking",
        effect_fn=lambda c, e, s: draw(s, draw_player=_controller_id(c), number=count),
    )


def on_attack_create_token(token_slug: str, count: int = 1) -> TriggerDef:
    """Template: "When this attacks, create N token(s)."."""
    return TriggerDef(
        event_type="attacking",
        effect_fn=lambda c, e, s: create_token(s, _controller_id(c), token_slug, count),
    )


def on_attack_discard(count: int = 1) -> TriggerDef:
    """Template: "When this attacks, discard N card(s)."."""
    def _effect(c, e, s):
        _discard_random(s, 3 - _controller_id(c), count)
    return TriggerDef(event_type="attacking", effect_fn=_effect)


def on_play_draw(count: int = 1) -> TriggerDef:
    """Template: "When you play this, draw N card(s)."."""
    return TriggerDef(
        event_type="on_play",
        effect_fn=lambda c, e, s: draw(s, draw_player=_controller_id(c), number=count),
    )


def on_play_deal_arcane(amount: int) -> TriggerDef:
    """Template: "Deal N arcane damage."."""
    def _effect(c, e, s):
        _deal_to_hero(s, 3 - _controller_id(c), amount, c, DamageType.ARCANE)
    return TriggerDef(event_type="on_play", effect_fn=_effect)


def on_play_deal_damage(amount: int) -> TriggerDef:
    """Template: "Deal N damage."."""
    def _effect(c, e, s):
        _deal_to_hero(s, 3 - _controller_id(c), amount, c)
    return TriggerDef(event_type="on_play", effect_fn=_effect)


def on_play_create_token(token_slug: str, count: int = 1) -> TriggerDef:
    """Template: "Create N token(s)."."""
    return TriggerDef(
        event_type="on_play",
        effect_fn=lambda c, e, s: create_token(s, _controller_id(c), token_slug, count),
    )


def on_play_power_bonus(amount: int, condition_fn=None) -> TriggerDef:
    """Template: "This gets +N{p}."."""
    def _effect(c, e, s):
        c.effects.append(CardEffect(prop="power", stage=7, substage=5, fn=lambda val, n=amount: val + n))
    return TriggerDef(
        event_type="on_play",
        condition_fn=condition_fn,
        effect_fn=_effect,
    )


def on_play_defense_bonus(amount: int, condition_fn=None) -> TriggerDef:
    """Template: "This gets +N{d}."."""
    def _effect(c, e, s):
        c.effects.append(CardEffect(prop="defense", stage=7, substage=5, fn=lambda val, n=amount: val + n))
    return TriggerDef(
        event_type="on_play",
        condition_fn=condition_fn,
        effect_fn=_effect,
    )


def on_defend_defense_bonus(amount: int, condition_fn=None) -> TriggerDef:
    """Template: "When this defends, it gets +N{d}."."""
    def _effect(c, e, s):
        c.effects.append(CardEffect(prop="defense", stage=7, substage=5, fn=lambda val, n=amount: val + n))
    return TriggerDef(
        event_type="defend",
        condition_fn=condition_fn,
        effect_fn=_effect,
    )


def on_play_gain_resources(amount: int) -> TriggerDef:
    """Template: "Gain N resources."."""
    def _effect(c, e, s):
        cid = _controller_id(c)
        gain(s, AssetType.RESOURCES, amount, cid, target_player_id=cid)
    return TriggerDef(event_type="on_play", effect_fn=_effect)


def on_play_gain_action_point() -> TriggerDef:
    """Template: "Gain an action point."."""
    def _effect(c, e, s):
        cid = _controller_id(c)
        gain(s, AssetType.ACTION_POINTS, 1, cid, target_player_id=cid)
    return TriggerDef(event_type="on_play", effect_fn=_effect)


def on_play_intimidate() -> TriggerDef:
    """Template: "Intimidate."."""
    def _effect(c, e, s):
        cid = _controller_id(c)
        intimidate(s, source_player_id=cid, target_player_id=3 - cid)
    return TriggerDef(event_type="on_play", effect_fn=_effect)


def on_play_opt(count: int) -> TriggerDef:
    """Template: "Opt N."."""
    def _effect(c, e, s):
        cid = _controller_id(c)
        _opt_with_agent(s, cid, count, source_player_id=cid)
    return TriggerDef(event_type="on_play", effect_fn=_effect)


def on_play_banish_top(count: int = 1) -> TriggerDef:
    """Template: "Banish the top N card(s) of your deck."."""
    def _effect(c, e, s):
        cid = _controller_id(c)
        player = s.players[cid]
        from engine.card_effects.ability_keywords import banish_card
        for _ in range(count):
            if player.deck.cards:
                top = player.deck.pop_top()
                banish_card(s, player, top, face_up=True)
    return TriggerDef(event_type="on_play", effect_fn=_effect)


def on_play_shuffle() -> TriggerDef:
    """Template: "Shuffle your deck."."""
    return TriggerDef(
        event_type="on_play",
        effect_fn=lambda c, e, s: shuffle(s, target_player_id=_controller_id(c)),
    )


def on_play_amp(amount: int) -> TriggerDef:
    """Template: "Amp N."."""
    return TriggerDef(
        event_type="on_play",
        effect_fn=lambda c, e, s: amp(s, amount=amount, player_id=_controller_id(c)),
    )


def on_hit_go_again() -> TriggerDef:
    """Template: "When this hits, it gains go again."."""
    def _effect(c, e, s):
        if s.combat:
            go_again(c, e, s)
    return TriggerDef(event_type="hit", effect_fn=_effect)


def on_attack_go_again_conditional(condition_fn: Callable) -> TriggerDef:
    """Template: "When this attacks, if [CONDITION], it gains go again."."""
    def _effect(c, e, s):
        if s.combat and condition_fn(c, e, s):
            go_again(c, e, s)
    return TriggerDef(event_type="attacking", effect_fn=_effect)


def on_play_discard(count: int = 1) -> TriggerDef:
    """Template: "When you play this, discard N card(s)."."""
    def _effect(c, e, s):
        _discard_random(s, _controller_id(c), count)
    return TriggerDef(event_type="on_play", effect_fn=_effect)


def on_play_gain_life(amount: int) -> TriggerDef:
    """Template: "When you play this, gain N life."."""
    def _effect(c, e, s):
        cid = _controller_id(c)
        gain(s, AssetType.LIFE, amount, cid, target_player_id=cid)
    return TriggerDef(event_type="on_play", effect_fn=_effect)


def on_play_mark() -> TriggerDef:
    """Template: "When you play this, mark the defending hero."."""
    return TriggerDef(
        event_type="on_play",
        effect_fn=lambda c, e, s: mark(s, target_player_id=3 - _controller_id(c)),
    )


def on_defend_draw(count: int = 1) -> TriggerDef:
    """Template: "When this defends, draw N card(s)."."""
    return TriggerDef(
        event_type="defend",
        effect_fn=lambda c, e, s: draw(s, draw_player=_controller_id(c), number=count),
    )


def on_defend_create_token(token_slug: str, count: int = 1) -> TriggerDef:
    """Template: "When this defends, create N token(s)."."""
    return TriggerDef(
        event_type="defend",
        effect_fn=lambda c, e, s: create_token(s, _controller_id(c), token_slug, count),
    )


def on_defend_gain_resources(amount: int = 1) -> TriggerDef:
    """Template: "When this defends, gain N resource(s)."."""
    def _effect(c, e, s):
        cid = _controller_id(c)
        gain(s, AssetType.RESOURCES, amount, cid, target_player_id=cid)
    return TriggerDef(event_type="defend", effect_fn=_effect)


def crush_trigger(effect_fn: Callable) -> TriggerDef:
    """Template: "Crush - When this deals 4+ damage, [EFFECT]."."""
    return TriggerDef(
        event_type="damage_dealt",
        condition_fn=lambda c, e, s: crush_check(e, s),
        effect_fn=effect_fn,
    )


def reprise_trigger(effect_fn: Callable) -> TriggerDef:
    """Template: "Reprise - If defending hero defended from hand, [EFFECT]."."""
    return TriggerDef(
        event_type="on_play",
        condition_fn=lambda c, e, s: reprise_check(s),
        effect_fn=effect_fn,
    )


def surge_trigger(amount: int, effect_fn: Callable) -> TriggerDef:
    """Template: "Surge - If this deals N+ damage, [EFFECT]."."""
    return TriggerDef(
        event_type="damage_dealt",
        condition_fn=lambda c, e, s: surge_check(e, amount),
        effect_fn=effect_fn,
    )


def combo_trigger(combo_names: list, effect_fn: Callable) -> TriggerDef:
    """Template: "Combo - If [NAME] was last attack, [EFFECT]."."""
    return TriggerDef(
        event_type="on_play",
        condition_fn=lambda c, e, s: combo_check(s, combo_names),
        effect_fn=effect_fn,
    )


def rupture_trigger(effect_fn: Callable) -> TriggerDef:
    """Template: "Rupture - If played at chain link 4+, [EFFECT]."."""
    return TriggerDef(
        event_type="on_play",
        condition_fn=lambda c, e, s: rupture_check(s),
        effect_fn=effect_fn,
    )

def enters_with_steam_counters(count: int) -> TriggerDef:
    """Template: "When this enters the arena, put N steam counters on it."."""
    def _effect(c, e, s):
        for _ in range(count):
            put_counter(s, counter_type="steam", target_card=c)
    return TriggerDef(event_type="enters_arena", effect_fn=_effect)


# ---------------------------------------------------------------------------
# Card-specific triggers — keyed by slug
# Covers cards with unique text that can't use templates.
# ---------------------------------------------------------------------------

CARD_TRIGGERS: dict[str, list[TriggerDef]] = {}

# ---------------------------------------------------------------------------
# Kayo deck — card-specific triggers
# ---------------------------------------------------------------------------

def _crowd_boos_on_attack(card, event, state):
    """When this attacks a hero, if controller has more health, the crowd boos."""
    from engine.card_effects.ability_keywords import effect_crowd_boos
    cid = _controller_id(card)
    if state.players[cid].health > state.players[3 - cid].health:
        effect_crowd_boos(state, cid)

def _is_this_attacking(card, event, state):
    return state.combat and state.combat.attack_card.slug == card.slug


# -- kayo_underhanded_cheat --
# Passive: "Whenever the crowd boos you, create a Vigor token."
# Activated: "Instant - {r}{r}{r}{r}, {t}: Target attack action card you control has 6 base power."
# {t} = tap hero permanent (8.5.55). Activated ability handled in legal_actions/apply_action.
CARD_TRIGGERS["kayo_underhanded_cheat"] = [
    TriggerDef(
        event_type="crowd_boos",
        condition_fn=lambda c, e, s: hasattr(e, 'data') and e.data.get('player_id') == _controller_id(c),
        effect_fn=lambda c, e, s: create_token(s, _controller_id(c), "vigor"),
    ),
]



# -- fyendals_spring_tunic --
# "At the start of your turn, if this has fewer than 3 energy counters, you may put an energy counter on it."
# Activated instant: "Remove 3 energy counters: Gain {r}." (handled in actions)
def _fst_start_of_turn(card, event, state):
    cid = _controller_id(card)
    from engine.actions import ActionType, Action
    if cid != state.active_player:
        return
    key = (card.slug, card.zone, "energy")
    current = state.players[cid].counters.get(key, 0)
    if current < 3:
        options = [
            Action(type=ActionType.CHOOSE, choose_index=0),  # 0 = no counter
            Action(type=ActionType.CHOOSE, choose_index=1),  # 1 = place counter
        ]
        choice = state.player_agents[cid](state, options,
                             context="Put an energy counter on Fyendal's Spring Tunic? (max 3)")
        if choice:
            _put_counter(state, card, "energy")

CARD_TRIGGERS["fyendals_spring_tunic"] = [
    TriggerDef(event_type="start_of_turn", effect_fn=_fst_start_of_turn, is_optional=True),
]


# -- scowling_flesh_bag --
# "When this defends, intimidate."
def _scowling_defend(card, event, state):
    if not state.combat or card not in state.combat.defending_cards:
        return
    _intimidate(state,state.combat.attacker_id)

CARD_TRIGGERS["scowling_flesh_bag"] = [
    TriggerDef(
        event_type="defend",
        condition_fn=lambda c, e, s: s.combat and c in s.combat.defending_cards,
        effect_fn=_scowling_defend,
    ),
]


# -- apex_bonebreaker --
# "When this defends together with a card with 6+ power, create a Might token."
def _apex_defend_condition(card, event, state):
    if not state.combat or card not in state.combat.defending_cards:
        return False
    return any(c.power is not None and c.power >= 6
               for c in state.combat.defending_cards if c.slug != card.slug)

CARD_TRIGGERS["apex_bonebreaker"] = [
    TriggerDef(
        event_type="defend",
        condition_fn=_apex_defend_condition,
        effect_fn=lambda c, e, s: create_token(s, _controller_id(c), "might"),
    ),
]


# -- big_bully --
# Trigger: "When this attacks a hero, if you have more health, the crowd boos you."
# Continuous: "If you've been booed this turn, this card's base power is doubled."
def _big_bully_attacking(card, event, state):
    _crowd_boos_on_attack(card, event, state)
    from engine.card_effects.ability_keywords import has_been_booed
    cid = _controller_id(card)
    if has_been_booed(state, cid):
        state.combat.attack_card.effects.append(
            CardEffect(prop="power", stage=7, substage=3, fn=lambda val: val * 2))

CARD_TRIGGERS["big_bully"] = [
    TriggerDef(event_type="attacking", condition_fn=_is_this_attacking,
               effect_fn=_big_bully_attacking),
]


# -- chain_of_brutality --
# "If this has 6 or more power, it gets go again and
#  'When this hits a hero, the next attack action card you play this turn has 6 base power.'"
def _chain_of_brutality_attacking(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    if state.combat.attack_power >= 6:
        if 'go_again' not in state.combat.keywords:
            state.combat.grant_keyword('go_again')

def _chain_of_brutality_hit(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    if state.combat.attack_power >= 6:
        cid = _controller_id(card)
        state.players[cid].current_turn_effects.append('next_attack_6_base_power')

CARD_TRIGGERS["chain_of_brutality"] = [
    TriggerDef(event_type="attacking", effect_fn=_chain_of_brutality_attacking),
    TriggerDef(event_type="hit", effect_fn=_chain_of_brutality_hit),
]


# -- command_and_conquer --
# "Defense reaction cards can't be played this chain link."
# "When this hits a hero, destroy all cards in their arsenal."
def _cnc_attacking(card, event, state):
    if state.combat and state.combat.attack_card.slug == card.slug:
        state.combat.no_defense_reactions = True

def _cnc_on_hit(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    target_id = 3 - _controller_id(card)
    target = state.players[target_id]
    if hasattr(target, 'arsenal'):
        for c in list(target.arsenal.cards):
            target.arsenal.remove(c)
            target.graveyard.add(c)

CARD_TRIGGERS["command_and_conquer"] = [
    TriggerDef(event_type="attacking", effect_fn=_cnc_attacking),
    TriggerDef(event_type="hit", effect_fn=_cnc_on_hit),
]


# -- looking_for_a_scrap --
# "As an additional cost, you may banish a card with 1 power from your graveyard.
#  When you do, this gains +1 power and go again."
def _looking_scrap_on_play(card, event, state):
    from engine.card_effects.ability_keywords import _ask_player
    cid = _controller_id(card)
    controller = state.players[cid]
    eligible = [c for c in controller.graveyard.cards
                if c.power is not None and c.power == 1]
    if not eligible:
        return
    choice = _ask_player(state, cid, [True, False],
                         context="Banish a 1-power card from graveyard to give this +1 power and go again?")
    if not choice:
        return
    pick = _ask_player(state, cid, [c.slug for c in eligible],
                       context="Choose a 1-power graveyard card to banish (Looking for a Scrap)")
    target = next((c for c in eligible if c.slug == pick), None)
    if target:
        controller.graveyard.remove(target)
        banish(state, target, cid, 'graveyard')
        card.effects.append(CardEffect(prop="power", stage=8, substage=5, fn=lambda val: val + 1))
        if state.combat:
            go_again(card, state)

CARD_TRIGGERS["looking_for_a_scrap"] = [
    TriggerDef(event_type="on_play", effect_fn=_looking_scrap_on_play, is_optional=True),
]


# -- mocking_blow --
# Trigger: "When this attacks a hero, if you have more health, the crowd boos you."
# Continuous: "If you've been booed this turn, this gets +N power."
def _mocking_blow_attacking(card, event, state, bonus):
    _crowd_boos_on_attack(card, event, state)
    from engine.card_effects.ability_keywords import has_been_booed
    cid = _controller_id(card)
    if has_been_booed(state, cid):
        state.combat.attack_card.effects.append(
            CardEffect(prop="power", stage=8, substage=5, fn=lambda val, n=bonus: val + n))

CARD_TRIGGERS["mocking_blow_red"] = [
    TriggerDef(event_type="attacking", condition_fn=_is_this_attacking,
               effect_fn=lambda c, e, s: _mocking_blow_attacking(c, e, s, 4)),
]
CARD_TRIGGERS["mocking_blow_yellow"] = [
    TriggerDef(event_type="attacking", condition_fn=_is_this_attacking,
               effect_fn=lambda c, e, s: _mocking_blow_attacking(c, e, s, 3)),
]
CARD_TRIGGERS["mocking_blow_blue"] = [
    TriggerDef(event_type="attacking", condition_fn=_is_this_attacking,
               effect_fn=lambda c, e, s: _mocking_blow_attacking(c, e, s, 2)),
]


# -- pummel -- migrated to card_effects/json/wtr/pummel_{red,yellow,blue}.json


# -- show_of_strength --
# "This gets -1 power for each card with 6 or more power defending it."
def _show_of_strength_defend(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    penalty = sum(1 for d in state.combat.defending_cards
                  if d.power is not None and d.power >= 6)
    if penalty > 0:
        state.combat.attack_power -= penalty

CARD_TRIGGERS["show_of_strength"] = [
    TriggerDef(event_type="defend", condition_fn=_is_this_attacking,
               effect_fn=_show_of_strength_defend),
]


# -- sigil_of_solace -- migrated to card_effects/json/wtr/sigil_of_solace_{red,yellow,blue}.json


# -- sink_below --
# Defense reaction: "You may put a card from your hand on the bottom of your deck.
#  If you do, draw a card."
def _sink_below_effect(card, event, state):
    from engine.card_effects.ability_keywords import _ask_player
    cid = _controller_id(card)
    controller = state.players[cid]
    if not controller.hand.cards:
        return
    options = [c.slug for c in controller.hand.cards] + ["decline"]
    choice = _ask_player(state, cid, options,
                         context="Sink Below: choose a hand card to put on the bottom of your deck, then draw")
    if choice == "decline":
        return
    target = controller.hand.find(choice)
    if target:
        controller.hand.remove(target)
        controller.deck.add_bottom(target)
        effect_draw(state, cid, 1)

CARD_TRIGGERS["sink_below"] = [
    TriggerDef(event_type="on_play", effect_fn=_sink_below_effect),
]


# -- snarky_prick --
# "When this attacks a hero, look at the top card of their deck.
#  If it's red, destroy it and this gets +4 power."
def _snarky_prick_effect(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    target_id = 3 - _controller_id(card)
    target = state.players[target_id]
    if not target.deck.cards:
        return
    top_card = target.deck.cards[0]
    if top_card.pitch == 1:  # Red cards have pitch 1
        target.deck.pop_top()
        target.graveyard.add(top_card)
        state.combat.attack_power += 4

CARD_TRIGGERS["snarky_prick"] = [
    TriggerDef(event_type="attacking", effect_fn=_snarky_prick_effect),
]


# -- swing_big --
# "If Swing Big doesn't hit, the defending hero creates a Quicken token when the combat chain closes."
def _swing_big_close(card, event, state):
    for link in state.chain_links:
        if link.attack_slug == card.slug and not link.hit:
            target_id = 3 - link.attacker_id
            create_token(state, target_id, "quicken")
            return

CARD_TRIGGERS["swing_big"] = [
    TriggerDef(event_type="combat_chain_close", effect_fn=_swing_big_close),
]


# -- booze --
# "Go again" (keyword)
# "When this enters the arena, the crowd boos you." — trigger on enters_arena
# "When this leaves the arena, the crowd boos you." — trigger on leaves_arena (any reason)
# "At the start of your turn, destroy this." — separate trigger
def _booze_enters_arena(card, event, state):
    from engine.card_effects.ability_keywords import effect_crowd_boos
    effect_crowd_boos(state, _controller_id(card))

def _booze_leaves_arena(card, event, state):
    from engine.card_effects.ability_keywords import effect_crowd_boos
    effect_crowd_boos(state, _controller_id(card))

def _booze_start_of_turn(card, event, state):
    cid = _controller_id(card)
    if cid != state.active_player:
        return
    if card in state.players[cid].auras.cards:
        _move_to_graveyard(card, state)
        # _move_to_graveyard should emit leaves_arena, which triggers _booze_leaves_arena

CARD_TRIGGERS["booze"] = [
    TriggerDef(event_type="enters_arena", effect_fn=_booze_enters_arena),
    TriggerDef(event_type="leaves_arena", effect_fn=_booze_leaves_arena),
    TriggerDef(event_type="start_of_turn", effect_fn=_booze_start_of_turn),
]


# -- insult_to_injury --
# "When this attacks a hero, if you have more health than them, this gets go again."
def _insult_to_injury_effect(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    if state.players[cid].health > state.players[3 - cid].health:
        if 'go_again' not in state.combat.keywords:
            state.combat.grant_keyword('go_again')

CARD_TRIGGERS["insult_to_injury"] = [
    TriggerDef(event_type="attacking", effect_fn=_insult_to_injury_effect),
]

def _shock_charmers_on_hit(card, event, state):
    """When an attack action card hits a hero, it deals 1 generic damage to them."""
    cid = _controller_id(card)
    player = state.players[cid]
    if "shock_charmers_hit_damage" not in player.current_turn_effects:
        return
    if not state.combat or not state.combat.attack_card:
        return
    atk = state.combat.attack_card
    if _controller_id(atk) != cid:
        return
    types_lower = [t.lower() for t in atk.types]
    if not any(t in types_lower for t in ("Attack", "Action")):
        return
    player.current_turn_effects.remove("shock_charmers_hit_damage")
    defender_id = 3 - cid
    effect_deal_damage(state, defender_id, 1, atk, "generic")

# -- nimblism_blue --
# "The next attack action card with cost 1 or less you play this turn gains +1 power."
# This effect is specific to the blue version of Nimblism.
CARD_TRIGGERS["nimblism_blue"] = [
    TriggerDef(
        event_type="on_play",
        effect_fn=lambda c, e, s: s.players[_controller_id(c)].current_turn_effects.append(
            "nimblism_next_attack_plus1"),
    ),
]


# -- nimby --
# "When this attacks, you may search your deck for a Nimblism, reveal it, put into hand, then shuffle."
# Player chooses to search first. Shuffle always happens. Player can "fail to find" (choose nothing).
def _nimby_effect(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    from engine.card_effects.ability_keywords import _ask_player
    cid = _controller_id(card)
    controller = state.players[cid]
    # Ask if player wants to search
    choice = _ask_player(state, cid, [True, False],
                         context="Search your deck for a Nimblism and put it into hand? (Nimby)")
    if not choice:
        return
    # Search — player may "fail to find" even if Nimblism exists (8.5.19)
    nimblisms = [c for c in controller.deck.cards if 'nimblism' in c.slug]
    options = [c.slug for c in nimblisms] + ["fail_to_find"]
    pick = _ask_player(state, cid, options,
                       context="Choose a Nimblism to put into hand (or fail to find)")
    if pick != "fail_to_find":
        target = next((c for c in nimblisms if c.slug == pick), None)
        if target:
            controller.deck.cards.remove(target)
            controller.hand.add(target)
            state.set_card_visibility(target, True)
    # Shuffle regardless of whether a card was found
    effect_shuffle(state, cid)

CARD_TRIGGERS["nimby"] = [
    TriggerDef(event_type="attacking", effect_fn=_nimby_effect, is_optional=True),
]


# -- offensive_behavior --
# Continuous: "If you control a Might or Vigor token, this gets +1 power."
# Trigger: "When this hits a hero, create a Might and a Vigor token."
def _offensive_behavior_attack(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    has_token = any('might' in t.slug or 'vigor' in t.slug
                     for t in state.players[cid].auras.cards)
    if has_token:
        state.combat.attack_power += 1

def _offensive_behavior_hit(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    create_token(state, cid, "might")
    create_token(state, cid, "vigor")

CARD_TRIGGERS["offensive_behavior"] = [
    TriggerDef(event_type="attacking", effect_fn=_offensive_behavior_attack),
    TriggerDef(event_type="hit", effect_fn=_offensive_behavior_hit),
]


# -- overcrowded --
# "Ambush" (keyword)
# "When this attacks or defends, +1p +1d per unique aura token name in the arena."
def _overcrowded_count_auras(state):
    names = set()
    for pid in state.players:
        for t in state.players[pid].auras.cards:
            if "Token" in t.types:
                names.add(t.slug)
    return len(names)

def _overcrowded_attack(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    bonus = _overcrowded_count_auras(state)
    if bonus > 0:
        state.combat.attack_power += bonus

def _overcrowded_defend(card, event, state):
    if not state.combat or card not in state.combat.defending_cards:
        return
    bonus = _overcrowded_count_auras(state)
    if bonus > 0:
        card.effects.append(CardEffect(prop="defense", stage=7, substage=5, fn=lambda val, n=bonus: val + n))

CARD_TRIGGERS["overcrowded"] = [
    TriggerDef(event_type="attacking", effect_fn=_overcrowded_attack),
    TriggerDef(event_type="defend",
               condition_fn=lambda c, e, s: s.combat and c in s.combat.defending_cards,
               effect_fn=_overcrowded_defend),
]


# -- reckless_arithmetic --
# "When this attacks, roll a 6 sided die. This gets +X power."
def _reckless_arithmetic_effect(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    from engine.card_effects.ability_keywords import roll_die
    cid = _controller_id(card)
    result = roll_die(state, cid)
    state.combat.attack_power += result

CARD_TRIGGERS["reckless_arithmetic"] = [
    TriggerDef(event_type="attacking", effect_fn=_reckless_arithmetic_effect),
]


# -- steal_victory --
# "When this defends, steal an aura token the attacking hero controls."
def _steal_victory_effect(card, event, state):
    if not state.combat or card not in state.combat.defending_cards:
        return
    from engine.card_effects.ability_keywords import effect_steal_token
    defender_id = _controller_id(card)
    attacker_id = state.combat.attacker_id
    effect_steal_token(state, defender_id, attacker_id)

CARD_TRIGGERS["steal_victory"] = [
    TriggerDef(event_type="defend",
               condition_fn=lambda c, e, s: s.combat and c in s.combat.defending_cards,
               effect_fn=_steal_victory_effect),
]


# ---------------------------------------------------------------------------
# Helper: find all daggers controlled by a player (weapons, chain, arena)
# ---------------------------------------------------------------------------

def _find_controlled_daggers(player, state, exclude_card=None):
    """Find all dagger cards controlled by a player.
    Includes weapon zone daggers AND dagger-type cards on the combat chain."""
    daggers = []
    for c in player.weapon1.cards + player.weapon2.cards:
        if "Dagger" in (c.types or []) and c != exclude_card:
            daggers.append(c)
    if state.combat:
        if (state.combat.attack_card
                and state.combat.attack_card != exclude_card
                and state.combat.attack_card.controller == player.player_id
                and "Dagger" in (state.combat.attack_card.types or [])):
            if state.combat.attack_card not in daggers:
                daggers.append(state.combat.attack_card)
        for link in getattr(state, 'chain_links', []):
            ac = getattr(link, 'attack_card', None)
            if (ac and ac != exclude_card
                    and ac.controller == player.player_id
                    and "Dagger" in (ac.types or [])
                    and ac not in daggers):
                daggers.append(ac)
    return daggers


# ---------------------------------------------------------------------------
# Arakni Marionette deck — card-specific triggers
# ---------------------------------------------------------------------------

# -- hunters_klaive --
# "When this hits a hero, mark them." (Piercing 1 handled by keyword trigger)
def _hunters_klaive_hit(card, event, state):
    if not state.combat or state.combat.attack_card != card:
        return
    target_id = 3 - _controller_id(card)
    _mark(state, target_id)

# hunters_klaive and kiss_of_death full registrations are below (~line 1883/1890)
# — do not add stub registrations here, as they would be silently overwritten.

def _kiss_of_death_hit(card, event, state):
    """When Kiss of Death hits a hero, they lose 1 health."""
    if not _is_attacking(card, event, state):
        return
    target_id = 3 - _controller_id(card)
    effect_lose_life(state, target_id, 1)


# -- infiltrate --
# "When this hits a hero, banish the top card of their deck. You may play it until end of next turn."
def _infiltrate_hit(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    target_id = 3 - _controller_id(card)
    target = state.players[target_id]
    cid = _controller_id(card)
    if target.deck.cards:
        top = target.deck.pop_top()
        effect_banish(state, top, face_up=True, banisher_id=cid)
        # "until end of your NEXT turn": playable this turn AND next turn
        state.players[cid].current_turn_effects.append(f"infiltrate_play_{top.slug}")
        if hasattr(state.players[cid], 'next_turn_effects'):
            state.players[cid].next_turn_effects.append(f"infiltrate_play_{top.slug}")

CARD_TRIGGERS["infiltrate"] = [
    TriggerDef(event_type="hit", effect_fn=_infiltrate_hit),
]


# -- art_of_desire_body --
# "When this hits, banish top of their deck. If red, draw a card and gain 1 health."
def _art_of_desire_body_hit(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    target_id = 3 - cid
    target = state.players[target_id]
    if target.deck.cards:
        top = target.deck.pop_top()
        effect_banish(state, top, face_up=True, banisher_id=cid)
        if top.pitch == 1:  # Red card
            effect_draw(state, cid, 1)
            _gain_life(state, cid, 1)

CARD_TRIGGERS["art_of_desire_body"] = [
    TriggerDef(event_type="hit", effect_fn=_art_of_desire_body_hit),
]


# -- mark_of_the_black_widow --
# "When this hits a marked hero, they banish a card from their hand."
# Mark clearing is registered AFTER card triggers in engine.py, so is_marked
# is still True when this fires on hit.
def _mark_black_widow_hit(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    target_id = 3 - _controller_id(card)
    if not _is_marked(state, target_id):
        return
    cid = _controller_id(card)
    target = state.players[target_id]
    if target.hand.cards:
        from engine.card_effects.ability_keywords import _ask_player
        pick = _ask_player(state, target_id, [c.slug for c in target.hand.cards],
                           context="Mark of the Black Widow: choose a card from your hand to be banished")
        chosen = next((c for c in target.hand.cards if c.slug == pick), target.hand.cards[0])
        target.hand.remove(chosen)
        effect_banish(state, chosen, face_up=True, banisher_id=cid)

CARD_TRIGGERS["mark_of_the_black_widow"] = [
    TriggerDef(event_type="hit", effect_fn=_mark_black_widow_hit),
]


# -- pain_in_the_backside --
# "When this hits a hero, target dagger you control deals 1 damage to them."
# Daggers include weapon daggers AND dagger-type cards on the combat chain.
def _pain_in_backside_hit(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    target_id = 3 - cid
    player = state.players[cid]
    daggers = _find_controlled_daggers(player, state, exclude_card=card)
    if not daggers:
        return
    from engine.card_effects.ability_keywords import _ask_player
    if len(daggers) == 1:
        dagger = daggers[0]
    else:
        pick = _ask_player(state, cid, [d.slug for d in daggers],
                           context="Pain in the Backside: choose a dagger you control to deal 1 damage")
        dagger = next((d for d in daggers if d.slug == pick), daggers[0])
    effect_deal_damage(state, target_id, 1, dagger, "generic")

CARD_TRIGGERS["pain_in_the_backside"] = [
    TriggerDef(event_type="hit", effect_fn=_pain_in_backside_hit),
]


# -- flick_knives --
# "Once per Turn Attack Reaction - 0: Target dagger you control that isn't on
#  the active chain link deals 1 damage to target hero. If damage is dealt,
#  the dagger has hit. Destroy the dagger."
def _flick_knives_on_play(card, event, state):
    if not state.combat:
        return
    cid = _controller_id(card)
    player = state.players[cid]
    target_id = 3 - cid
    current_attack = state.combat.attack_card
    daggers = _find_controlled_daggers(player, state, exclude_card=current_attack)
    if not daggers:
        return
    from engine.card_effects.ability_keywords import _ask_player
    if len(daggers) == 1:
        dagger = daggers[0]
    else:
        pick = _ask_player(state, cid, [d.slug for d in daggers],
                           context="Flick Knives: choose a dagger to deal 1 damage to the defending hero")
        dagger = next((d for d in daggers if d.slug == pick), daggers[0])
    dmg = effect_deal_damage(state, target_id, 1, dagger, "generic")
    if dmg and dmg > 0:
        # Dagger has "hit" — emit hit event for the dagger
        state.event_manager.emit(
            type('Event', (), {'type': 'hit',
                               'data': {'card': dagger, 'damage': dmg}})(),
            state)
    # Destroy the dagger
    for _wz in [player.weapon1, player.weapon2]:
        if dagger in _wz.cards:
            _wz.remove(dagger)
            player.graveyard.add(dagger)
            break

CARD_TRIGGERS["flick_knives"] = [
    TriggerDef(event_type="on_play", effect_fn=_flick_knives_on_play),
]


# -- leave_no_witnesses --
# Contract (8.5.39): continuous effect active while card is on combat chain.
# "You are contracted to banish opponents' red cards. Whenever you complete
#  this contract, create a Silver token."
# On hit: banish top of deck + up to 1 arsenal card.
def _leave_no_witnesses_on_play(card, event, state):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("contract_leave_no_witnesses_active")

def _leave_no_witnesses_contract(card, event, state):
    """Contract trigger: listens for card_banished events.
    If the banished card belongs to an opponent and is red, create Silver."""
    cid = _controller_id(card)
    if "contract_leave_no_witnesses_active" not in state.players[cid].current_turn_effects:
        return
    if not hasattr(event, 'data'):
        return
    banished = event.data.get('card')
    banisher_id = event.data.get('banisher_id')
    if banisher_id != cid:
        return
    if banished and banished.owner != cid and banished.pitch == 1:
        create_token(state, cid, "silver")
        state.players[cid].current_turn_effects.append("fulfilled_contract")

def _leave_no_witnesses_hit(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    target_id = 3 - cid
    target = state.players[target_id]
    # Banish top of deck
    if target.deck.cards:
        top = target.deck.pop_top()
        effect_banish(state, top, face_up=True, banisher_id=cid)
    # Banish up to 1 card in arsenal
    if hasattr(target, 'arsenal') and target.arsenal.cards:
        from engine.card_effects.ability_keywords import _ask_player
        options = [c.slug for c in target.arsenal.cards] + ["decline"]
        pick = _ask_player(state, cid, options,
                           context="Leave No Witnesses: choose an opponent's arsenal card to banish")
        if pick != "decline":
            chosen = next((c for c in target.arsenal.cards if c.slug == pick), None)
            if chosen:
                target.arsenal.remove(chosen)
                effect_banish(state, chosen, face_up=True, banisher_id=cid)

def _leave_no_witnesses_chain_close(card, event, state):
    """Deactivate contract when the combat chain closes."""
    cid = _controller_id(card)
    player = state.players[cid]
    while "contract_leave_no_witnesses_active" in player.current_turn_effects:
        player.current_turn_effects.remove("contract_leave_no_witnesses_active")

CARD_TRIGGERS["leave_no_witnesses"] = [
    TriggerDef(event_type="on_play", effect_fn=_leave_no_witnesses_on_play),
    TriggerDef(event_type="card_banished", effect_fn=_leave_no_witnesses_contract),
    TriggerDef(event_type="hit", effect_fn=_leave_no_witnesses_hit),
    TriggerDef(event_type="combat_chain_close", effect_fn=_leave_no_witnesses_chain_close),
]


# -- pick_up_the_point --
# "When this attacks, you may retrieve a dagger from your graveyard."
def _pick_up_the_point_attack(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    effect_retrieve_dagger(state, cid)

CARD_TRIGGERS["pick_up_the_point"] = [
    TriggerDef(event_type="attacking", effect_fn=_pick_up_the_point_attack, is_optional=True),
]


# -- up_sticks_and_run --
# "You may retrieve a dagger. Your next dagger attack this turn gets +X{p}."
def _up_sticks_on_play(card, event, state, bonus):
    cid = _controller_id(card)
    effect_retrieve_dagger(state, cid)
    state.players[cid].current_turn_effects.append(f"up_sticks_dagger_+{bonus}")

CARD_TRIGGERS["up_sticks_and_run_red"] = [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: _up_sticks_on_play(c, e, s, 4)),
]
CARD_TRIGGERS["up_sticks_and_run_yellow"] = [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: _up_sticks_on_play(c, e, s, 3)),
]
CARD_TRIGGERS["up_sticks_and_run_blue"] = [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: _up_sticks_on_play(c, e, s, 2)),
]


# -- savor_bloodshed --
# "Your next dagger attack this turn gets +4{p}.
#  The next time you hit a marked hero with a dagger this turn, draw a card."
def _savor_bloodshed_on_play(card, event, state):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("savor_dagger_+4")
    state.players[cid].current_turn_effects.append("savor_marked_hit_draw")

CARD_TRIGGERS["savor_bloodshed"] = [
    TriggerDef(event_type="on_play", effect_fn=_savor_bloodshed_on_play),
]


# -- orb_weaver_spinneret --
# "Equip a Graphene Chelicera token. Your next stealth attack gets +X{p}."
def _orb_weaver_on_play(card, event, state, bonus):
    cid = _controller_id(card)
    player = state.players[cid]
    chelicera = create_token_card("graphene_chelicera", cid)
    if not player.weapon1.cards:
        player.weapon1.add(chelicera)
    elif not player.weapon2.cards:
        player.weapon2.add(chelicera)
    state.players[cid].current_turn_effects.append(f"orb_weaver_stealth_+{bonus}")

CARD_TRIGGERS["orbweaver_spinneret_red"] = [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: _orb_weaver_on_play(c, e, s, 3)),
]
CARD_TRIGGERS["orbweaver_spinneret_yellow"] = [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: _orb_weaver_on_play(c, e, s, 2)),
]
CARD_TRIGGERS["orbweaver_spinneret_blue"] = [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: _orb_weaver_on_play(c, e, s, 1)),
]


# -- cut_from_the_same_cloth --
# "Target opposing hero reveals their hand. If an attack reaction card is revealed,
#  mark them. Your next dagger attack this turn gets +X{p}."
def _cut_from_cloth_on_play(card, event, state, bonus):
    cid = _controller_id(card)
    target_id = 3 - cid
    target = state.players[target_id]
    has_ar = any("Attack Reaction" in (c.types or [])
                 for c in target.hand.cards)
    if has_ar:
        _mark(state, target_id)
    state.players[cid].current_turn_effects.append(f"cut_cloth_dagger_+{bonus}")

CARD_TRIGGERS["cut_from_the_same_cloth_red"] = [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: _cut_from_cloth_on_play(c, e, s, 4)),
]
CARD_TRIGGERS["cut_from_the_same_cloth_yellow"] = [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: _cut_from_cloth_on_play(c, e, s, 3)),
]
CARD_TRIGGERS["cut_from_the_same_cloth_blue"] = [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: _cut_from_cloth_on_play(c, e, s, 2)),
]


# -- codex_of_frailty --
# Each hero puts an attack action from graveyard face-down into arsenal.
# Each hero that does, discards a card. Create Ponder + Frailty tokens.
def _codex_of_frailty_on_play(card, event, state):
    from engine.card_effects.ability_keywords import _ask_player
    cid = _controller_id(card)
    for pid in state.players:
        player = state.players[pid]
        eligible = [c for c in player.graveyard.cards
                    if "Attack" in c.types and "Action" in c.types]
        if eligible and hasattr(player, 'arsenal') and player.arsenal.top is None:
            options = [c.slug for c in eligible]
            pick = _ask_player(state, pid, options,
                               context="Codex of Frailty: choose an attack action from graveyard to put face-down into arsenal (then discard a card)")
            chosen = next((c for c in eligible if c.slug == pick), None)
            if chosen:
                player.graveyard.remove(chosen)
                player.arsenal.add(chosen, is_public=False)
                effect_discard(state, pid, 1)
    create_token(state, cid, "ponder")
    for pid in state.players:
        if pid != cid:
            create_token(state, pid, "frailty")

CARD_TRIGGERS["codex_of_frailty"] = [
    TriggerDef(event_type="on_play", effect_fn=_codex_of_frailty_on_play),
]


# -- codex_of_inertia --
# Each hero puts top of deck face-down into arsenal.
# Each hero that does, discards a card. Create Ponder + Inertia tokens.
def _codex_of_inertia_on_play(card, event, state):
    cid = _controller_id(card)
    for pid in state.players:
        player = state.players[pid]
        if player.deck.cards and player.arsenal.top is None:
            top = player.deck.pop_top()
            player.arsenal.add(top, is_public=False)
            effect_discard(state, pid, 1)
    create_token(state, cid, "ponder")
    for pid in state.players:
        if pid != cid:
            create_token(state, pid, "inertia")

CARD_TRIGGERS["codex_of_inertia"] = [
    TriggerDef(event_type="on_play", effect_fn=_codex_of_inertia_on_play),
]


# -- nights_embrace --
# "Your attacks with stealth get +1{p} this turn."
def _nights_embrace_on_play(card, event, state):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("nights_embrace_stealth_+1")

CARD_TRIGGERS["nights_embrace"] = [
    TriggerDef(event_type="on_play", effect_fn=_nights_embrace_on_play),
]


# -- frailty_trap --
# "When this defends an attack with go again, create Frailty under attacking hero."
def _frailty_trap_defend(card, event, state):
    if not state.combat or card not in state.combat.defending_cards:
        return
    attack = state.combat.attack_card
    if attack and "Go again" in (attack.keywords or []):
        create_token(state, state.combat.attacker_id, "frailty")

CARD_TRIGGERS["frailty_trap"] = [
    TriggerDef(event_type="defend",
               condition_fn=lambda c, e, s: s.combat and c in s.combat.defending_cards,
               effect_fn=_frailty_trap_defend),
]


# -- inertia_trap --
# "When this defends an attack with power greater than its base, create Inertia."
def _inertia_trap_defend(card, event, state):
    if not state.combat or card not in state.combat.defending_cards:
        return
    attack = state.combat.attack_card
    if attack and state.combat.attack_power > (attack.base_power or 0):
        create_token(state, state.combat.attacker_id, "inertia")

CARD_TRIGGERS["inertia_trap"] = [
    TriggerDef(event_type="defend",
               condition_fn=lambda c, e, s: s.combat and c in s.combat.defending_cards,
               effect_fn=_inertia_trap_defend),
]


# -- lair_of_the_spider --
# "When this defends an attack with go again, mark the attacking hero."
def _lair_of_spider_defend(card, event, state):
    if not state.combat or card not in state.combat.defending_cards:
        return
    attack = state.combat.attack_card
    if attack and "Go again" in (attack.keywords or []):
        _mark(state, state.combat.attacker_id)

CARD_TRIGGERS["lair_of_the_spider"] = [
    TriggerDef(event_type="defend",
               condition_fn=lambda c, e, s: s.combat and c in s.combat.defending_cards,
               effect_fn=_lair_of_spider_defend),
]


# -- shred --
# "Target card defending an Assassin attack gets -X{d} this combat chain."
def _shred_on_play(card, event, state, penalty):
    if not state.combat:
        return
    attack = state.combat.attack_card
    if not attack or "Assassin" not in (attack.types or []):
        return
    if not state.combat.defending_cards:
        return
    from engine.card_effects.ability_keywords import _ask_player
    cid = _controller_id(card)
    options = [c.slug for c in state.combat.defending_cards]
    pick = _ask_player(state, cid, options,
                       context="Shred: choose a defending card to reduce its defense")
    target = next((c for c in state.combat.defending_cards if c.slug == pick), None)
    if target:
        target.effects.append(CardEffect(prop="defense", stage=7, substage=6, fn=lambda val, p=penalty: val - p))

CARD_TRIGGERS["shred_red"] = [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: _shred_on_play(c, e, s, 4)),
]
CARD_TRIGGERS["shred_yellow"] = [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: _shred_on_play(c, e, s, 3)),
]
CARD_TRIGGERS["shred_blue"] = [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: _shred_on_play(c, e, s, 2)),
]


# -- to_the_point --
# "Target dagger attack gets +X{p}. If defending hero is marked, instead +X+1{p}."
# Dagger attacks include dagger-type action cards (Kiss of Death, etc.)
def _to_the_point_on_play(card, event, state, base_bonus, marked_bonus):
    if not state.combat:
        return
    attack = state.combat.attack_card
    if not attack or "Dagger" not in (attack.types or []):
        return
    cid = _controller_id(card)
    target_id = 3 - cid
    bonus = marked_bonus if _is_marked(state, target_id) else base_bonus
    attack.effects.append(CardEffect(prop="power", stage=7, substage=5, fn=lambda val, b=bonus: val + b))

CARD_TRIGGERS["to_the_point_red"] = [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: _to_the_point_on_play(c, e, s, 3, 4)),
]
CARD_TRIGGERS["to_the_point_yellow"] = [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: _to_the_point_on_play(c, e, s, 2, 3)),
]
CARD_TRIGGERS["to_the_point_blue"] = [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: _to_the_point_on_play(c, e, s, 1, 2)),
]


# -- scar_tissue --
# "Target dagger attack gets +X{p} and 'When this hits a hero, mark them.'"
def _scar_tissue_on_play(card, event, state, bonus):
    if not state.combat:
        return
    attack = state.combat.attack_card
    if not attack or "Dagger" not in (attack.types or []):
        return
    attack.effects.append(CardEffect(prop="power", stage=7, substage=5, fn=lambda val, b=bonus: val + b))
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("scar_tissue_on_hit_mark")

CARD_TRIGGERS["scar_tissue_red"] = [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: _scar_tissue_on_play(c, e, s, 3)),
]
CARD_TRIGGERS["scar_tissue_yellow"] = [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: _scar_tissue_on_play(c, e, s, 2)),
]
CARD_TRIGGERS["scar_tissue_blue"] = [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: _scar_tissue_on_play(c, e, s, 1)),
]


# -- spreading_plague --
# "Create X Bloodrot Pox under defending hero, X = number of defending cards."
def _spreading_plague_on_play(card, event, state):
    if not state.combat:
        return
    cid = _controller_id(card)
    target_id = 3 - cid
    num_defenders = len(state.combat.defending_cards)
    if num_defenders > 0:
        create_token(state, target_id, "bloodrot_pox", num_defenders)

CARD_TRIGGERS["spreading_plague"] = [
    TriggerDef(event_type="on_play", effect_fn=_spreading_plague_on_play),
]


# -- stains_of_the_redback --
# "If defending hero is marked, this costs {r} less.
#  Target attack with stealth gets +X{p} and go again."
def _stains_on_play(card, event, state, bonus):
    if not state.combat:
        return
    attack = state.combat.attack_card
    if attack and "Stealth" in (attack.keywords or []):
        attack.effects.append(CardEffect(prop="power", stage=7, substage=5, fn=lambda val, b=bonus: val + b))
        go_again(attack, state)

CARD_TRIGGERS["stains_of_the_redback_red"] = [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: _stains_on_play(c, e, s, 3)),
]
CARD_TRIGGERS["stains_of_the_redback_yellow"] = [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: _stains_on_play(c, e, s, 2)),
]
CARD_TRIGGERS["stains_of_the_redback_blue"] = [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: _stains_on_play(c, e, s, 1)),
]


# -- tarantula_toxin --
# "Choose 1 or both: (1) Target dagger attack gets +3{p}.
#  (2) Target card defending an attack with stealth gets -3{d}."
def _tarantula_toxin_on_play(card, event, state):
    if not state.combat:
        return
    from engine.card_effects.ability_keywords import _ask_player
    cid = _controller_id(card)
    attack = state.combat.attack_card
    modes = []
    if attack and "Dagger" in (attack.types or []):
        modes.append("dagger_+3")
    if (attack and "Stealth" in (attack.keywords or [])
            and state.combat.defending_cards):
        modes.append("defender_-3")
    if not modes:
        return
    if len(modes) == 2:
        options = ["dagger_+3", "defender_-3", "both"]
        pick = _ask_player(state, cid, options,
                           context="Tarantula Toxin: give dagger +3 power, reduce a defender's defense by 3, or both?")
    else:
        pick = modes[0]
    if pick in ("dagger_+3", "both"):
        attack.effects.append(CardEffect(prop="power", stage=7, substage=5, fn=lambda val: val + 3))
    if pick in ("defender_-3", "both"):
        if state.combat.defending_cards:
            d_opts = [c.slug for c in state.combat.defending_cards]
            d_pick = _ask_player(state, cid, d_opts,
                                 context="Tarantula Toxin: choose a defending card to reduce its defense by 3")
            d_target = next((c for c in state.combat.defending_cards
                             if c.slug == d_pick), None)
            if d_target:
                d_target.effects.append(CardEffect(prop="defense", stage=7, substage=6, fn=lambda val: val - 3))

CARD_TRIGGERS["tarantula_toxin"] = [
    TriggerDef(event_type="on_play", effect_fn=_tarantula_toxin_on_play),
]


# -- take_up_the_mantle --
# "Target attack action card with stealth gets +2{p}.
#  If it's attacking a marked hero, instead it gets +3{p} and you may banish an
#  attack action card with stealth from your graveyard. If you do, the target
#  becomes a copy of the banished card."
def _take_up_mantle_on_play(card, event, state):
    if not state.combat:
        return
    cid = _controller_id(card)
    target_id = 3 - cid
    attack = state.combat.attack_card
    if not attack or "Stealth" not in (attack.keywords or []):
        return
    if _is_marked(state, target_id):
        attack.effects.append(CardEffect(prop="power", stage=7, substage=5, fn=lambda val: val + 3))
        from engine.card_effects.ability_keywords import _ask_player
        player = state.players[cid]
        stealth_attacks = [
            c for c in player.graveyard.cards
            if "Attack" in (c.types or [])
            and "Action" in (c.types or [])
            and "Stealth" in (c.keywords or [])
        ]
        if stealth_attacks:
            choice = _ask_player(state, cid, [True, False],
                                 context="Take Up the Mantle: banish a stealth attack from graveyard to copy it?")
            if choice:
                options = [c.slug for c in stealth_attacks]
                pick = _ask_player(state, cid, options,
                                   context="Choose a stealth attack action from graveyard to copy (Take Up the Mantle)")
                source = next((c for c in stealth_attacks if c.slug == pick), None)
                if source:
                    effect_banish(state, source, face_up=True, banisher_id=cid)
                    # Target becomes a copy: take name, power, keywords, types from source
                    attack.name = source.name
                    attack.base_power = source.base_power
                    attack.keywords = list(source.keywords or [])
                    attack.types = list(source.types or [])
                    attack.functional_text = source.functional_text
    else:
        attack.effects.append(CardEffect(prop="power", stage=7, substage=5, fn=lambda val: val + 2))

CARD_TRIGGERS["take_up_the_mantle"] = [
    TriggerDef(event_type="on_play", effect_fn=_take_up_mantle_on_play),
]


# -- death_touch --
# "Can't be played from hand." (Enforced in legal_actions)
# "When this hits, create Frailty, Inertia, or Bloodrot Pox under their control."
def _death_touch_hit(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    from engine.card_effects.ability_keywords import _ask_player
    cid = _controller_id(card)
    target_id = 3 - cid
    pick = _ask_player(state, cid, ["frailty", "inertia", "bloodrot_pox"],
                       context="Choose a token to create under opponent's control (Death Touch)")
    create_token(state, target_id, pick)

CARD_TRIGGERS["death_touch"] = [
    TriggerDef(event_type="hit", effect_fn=_death_touch_hit),
]


# -- Dagger/stealth turn-attack effects consumed on attack --
# Dagger attacks include weapon daggers AND dagger-type action cards.
def _dagger_buffs_on_attack(card, event, state):
    if not state.combat or state.combat.attack_card != card:
        return
    cid = _controller_id(card)
    player = state.players[cid]
    attack = state.combat.attack_card
    is_dagger = "Dagger" in (attack.types or [])
    is_stealth = "Stealth" in (attack.keywords or [])

    for bonus in (2, 3, 4):
        key = f"up_sticks_dagger_+{bonus}"
        if is_dagger and key in player.current_turn_effects:
            attack.effects.append(CardEffect(prop="power", stage=7, substage=5, fn=lambda val, b=bonus: val + b))
            player.current_turn_effects.remove(key)
            break

    if is_dagger and "savor_dagger_+4" in player.current_turn_effects:
        attack.effects.append(CardEffect(prop="power", stage=7, substage=5, fn=lambda val: val + 4))
        player.current_turn_effects.remove("savor_dagger_+4")

    for bonus in (2, 3, 4):
        key = f"cut_cloth_dagger_+{bonus}"
        if is_dagger and key in player.current_turn_effects:
            attack.effects.append(CardEffect(prop="power", stage=7, substage=5, fn=lambda val, b=bonus: val + b))
            player.current_turn_effects.remove(key)
            break

    for bonus in (1, 2, 3):
        key = f"orb_weaver_stealth_+{bonus}"
        if is_stealth and key in player.current_turn_effects:
            attack.effects.append(CardEffect(prop="power", stage=7, substage=5, fn=lambda val, b=bonus: val + b))
            player.current_turn_effects.remove(key)
            break

    # nights_embrace: all stealth attacks +1 (not consumed)
    if is_stealth and "nights_embrace_stealth_+1" in player.current_turn_effects:
        attack.effects.append(CardEffect(prop="power", stage=7, substage=5, fn=lambda val: val + 1))

    # Graphene Chelicera: stealth dagger attacking marked hero gets go again
    if is_dagger and is_stealth:
        target_id = 3 - cid
        if _is_marked(state, target_id):
            if "Go again" not in (attack.keywords or []):
                attack.keywords = list(attack.keywords or [])
                attack.keywords.append("Go again")


# -- Dagger on-hit effects from turn effects --
def _dagger_turn_hit_effects(card, event, state):
    if not state.combat or state.combat.attack_card != card:
        return
    cid = _controller_id(card)
    player = state.players[cid]
    target_id = 3 - cid

    if "scar_tissue_on_hit_mark" in player.current_turn_effects:
        _mark(state, target_id)
        player.current_turn_effects.remove("scar_tissue_on_hit_mark")

    is_dagger = "Dagger" in (card.types or [])
    if (is_dagger and "savor_marked_hit_draw" in player.current_turn_effects
            and _is_marked(state, target_id)):
        effect_draw(state, cid, 1)
        player.current_turn_effects.remove("savor_marked_hit_draw")

    # Blacktek Whisperers attack reaction: on hit, gain go again
    if "blacktek_hit_go_again" in player.current_turn_effects:
        player.current_turn_effects.remove("blacktek_hit_go_again")
        card.keywords = list(card.keywords or [])
        if "Go again" not in card.keywords:
            card.keywords.append("Go again")


# Register dagger buff listeners on dagger weapons and dagger-type action cards.
CARD_TRIGGERS["graphene_chelicera"] = [
    TriggerDef(event_type="attacking", effect_fn=_dagger_buffs_on_attack),
    TriggerDef(event_type="hit", effect_fn=_dagger_turn_hit_effects),
    TriggerDef(event_type="hit", effect_fn=_hunters_klaive_hit),
]

CARD_TRIGGERS["hunters_klaive"] = [
    TriggerDef(event_type="attacking", effect_fn=_dagger_buffs_on_attack),
    TriggerDef(event_type="hit", effect_fn=_hunters_klaive_hit),
    TriggerDef(event_type="hit", effect_fn=_dagger_turn_hit_effects),
]

# Kiss of Death: dagger-type action — gets dagger buffs + its own on-hit
CARD_TRIGGERS["kiss_of_death"] = [
    TriggerDef(event_type="attacking", effect_fn=_dagger_buffs_on_attack),
    TriggerDef(event_type="hit", effect_fn=_kiss_of_death_hit),
    TriggerDef(event_type="hit", effect_fn=_dagger_turn_hit_effects),
]


# ---------------------------------------------------------------------------
# Marlynn Treasure Hunter deck — card-specific triggers
# ---------------------------------------------------------------------------

# -- crown_of_dominion --
# "When you equip Crown of Dominion, create a Gold token."
def _crown_of_dominion_equip(card, event, state):
    cid = _controller_id(card)
    create_token(state, cid, "gold")

CARD_TRIGGERS["crown_of_dominion"] = [
    TriggerDef(event_type="enters_arena", effect_fn=_crown_of_dominion_equip),
]


# -- goldbaited_hook --
# On hit: steal/create Gold when pirate attack hits with buff active.
# End phase: if activated but no gold obtained, destroy this.
def _goldbaited_hook_on_hit(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    if "goldbaited_hook_on_hit_gold" not in player.current_turn_effects:
        return
    player.current_turn_effects.remove("goldbaited_hook_on_hit_gold")
    opp_id = 3 - cid
    opp = state.players[opp_id]
    opp_golds = [c for c in opp.items.cards if "Gold" in c.types and "Token" in c.types]
    if opp_golds:
        gold = opp_golds[0]
        opp.items.remove(gold)
        gold.controller = cid
        player.items.add(gold)
    else:
        create_token(state, cid, "gold")
    player.current_turn_effects.append("goldbaited_hook_gold_obtained")

def _goldbaited_hook_end_phase(card, event, state):
    cid = _controller_id(card)
    if cid != state.active_player:
        return
    player = state.players[cid]
    if "goldbaited_hook_activated_this_turn" not in player.current_turn_effects:
        return
    if "goldbaited_hook_gold_obtained" in player.current_turn_effects:
        return
    # Destroy Gold-Baited Hook
    if card in player.arms.cards:
        player.arms.remove(card)
        player.graveyard.add(card)

def _goldbaited_hook_gold_created(card, event, state):
    """Track ANY gold created this turn while hook is activated and still equipped."""
    cid = _controller_id(card)
    player = state.players[cid]
    if card not in player.arms.cards:
        return  # Hook has been destroyed — no longer listening
    if "goldbaited_hook_activated_this_turn" not in player.current_turn_effects:
        return
    if "goldbaited_hook_gold_obtained" not in player.current_turn_effects:
        player.current_turn_effects.append("goldbaited_hook_gold_obtained")

CARD_TRIGGERS["goldbaited_hook"] = [
    TriggerDef(event_type="hit", effect_fn=_goldbaited_hook_on_hit),
    TriggerDef(event_type="gold_created", effect_fn=_goldbaited_hook_gold_created),
    TriggerDef(event_type="start_of_end_phase", effect_fn=_goldbaited_hook_end_phase),
]


# -- Go Fish template --
# "When this hits, they choose/reveal a card. If [check], discard it and create Gold.
#  If cannon activated, you look at their hand and choose."
def _go_fish_hit(card, event, state, check_fn):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    target_id = 3 - cid
    target = state.players[target_id]
    if not target.hand.cards:
        return
    from engine.card_effects.ability_keywords import _ask_player
    cannon_activated = "activated_cannon" in state.players[cid].current_turn_effects
    if cannon_activated:
        pick = _ask_player(state, cid, [c.slug for c in target.hand.cards],
                           context="Go Fish (cannon active): choose a card from opponent's hand to reveal")
    else:
        pick = _ask_player(state, target_id, [c.slug for c in target.hand.cards],
                           context="Go Fish: choose a card from your hand to reveal")
    chosen = next((c for c in target.hand.cards if c.slug == pick), target.hand.cards[0])
    state.set_card_visibility(chosen, True)
    if check_fn(chosen):
        target.hand.remove(chosen)
        target.graveyard.add(chosen)
        create_token(state, cid, "gold")
        state.players[cid].current_turn_effects.append("goldbaited_hook_gold_obtained")

CARD_TRIGGERS["red_fin_harpoon"] = [
    TriggerDef(event_type="hit",
               effect_fn=lambda c, e, s: _go_fish_hit(c, e, s,
                   lambda card: card.pitch == 1)),
]
CARD_TRIGGERS["blue_fin_harpoon"] = [
    TriggerDef(event_type="hit",
               effect_fn=lambda c, e, s: _go_fish_hit(c, e, s,
                   lambda card: card.pitch == 3)),
]
CARD_TRIGGERS["yellow_fin_harpoon"] = [
    TriggerDef(event_type="hit",
               effect_fn=lambda c, e, s: _go_fish_hit(c, e, s,
                   lambda card: card.pitch == 2)),
]
CARD_TRIGGERS["king_shark_harpoon"] = [
    TriggerDef(event_type="hit",
               effect_fn=lambda c, e, s: _go_fish_hit(c, e, s,
                   lambda card: "Attack" in (card.types or []) and "Action" in (card.types or []))),
]
CARD_TRIGGERS["king_kraken_harpoon"] = [
    TriggerDef(event_type="hit",
               effect_fn=lambda c, e, s: _go_fish_hit(c, e, s,
                   lambda card: ("Action" in (card.types or [])
                                 and "Attack" not in (card.types or [])))),
]


# -- battering_bolt --
# "If this hits, they reveal hand, discard non-action cards, lose 1 life per discarded."
def _battering_bolt_hit(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    target_id = 3 - _controller_id(card)
    target = state.players[target_id]
    to_discard = [c for c in target.hand.cards if "Action" not in (c.types or [])]
    count = len(to_discard)
    for c in to_discard:
        target.hand.remove(c)
        target.graveyard.add(c)
    if count > 0:
        effect_lose_life(state, target_id, count)

CARD_TRIGGERS["battering_bolt"] = [
    TriggerDef(event_type="hit", effect_fn=_battering_bolt_hit),
]


# -- big_game_trophy_shot --
# "Next arrow +4{p}. If harpoon, 'on hit create Gold.' Draw, discard. Go again."
def _big_game_trophy_on_play(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    player.current_turn_effects.append("big_game_arrow_+4")
    player.current_turn_effects.append("big_game_harpoon_gold")
    effect_draw(state, cid, 1)
    effect_discard(state, cid, 1)

CARD_TRIGGERS["big_game_trophy_shot"] = [
    TriggerDef(event_type="on_play", effect_fn=_big_game_trophy_on_play),
]


# -- catch_of_the_day --
# "Next arrow +2{p}. Go fish triggers twice this turn."
def _catch_of_the_day_on_play(card, event, state):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("catch_arrow_+2")
    state.players[cid].current_turn_effects.append("go_fish_double")

CARD_TRIGGERS["catch_of_the_day"] = [
    TriggerDef(event_type="on_play", effect_fn=_catch_of_the_day_on_play),
]


# -- gold_the_tip --
# "Next arrow +3{p}. If yellow arrow face-up in arsenal, create Gold."
def _gold_the_tip_on_play(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    player.current_turn_effects.append("gold_tip_arrow_+3")
    if hasattr(player, 'arsenal') and player.arsenal.cards:
        for ac in player.arsenal.cards:
            if ac.is_public and "Arrow" in (ac.types or []) and ac.pitch == 2:
                create_token(state, cid, "gold")
                break

CARD_TRIGGERS["gold_the_tip"] = [
    TriggerDef(event_type="on_play", effect_fn=_gold_the_tip_on_play),
]


# -- golden_tipple --
# "When attacks, may discard yellow card. If so, draw + create Gold."
def _golden_tipple_attack(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    player = state.players[cid]
    yellows = [c for c in player.hand.cards if c.pitch == 2]
    if not yellows:
        return
    from engine.card_effects.ability_keywords import _ask_player
    options = [c.slug for c in yellows] + ["decline"]
    pick = _ask_player(state, cid, options,
                       context="Golden Tipple: discard a yellow card to draw a card and create a Gold token?")
    if pick == "decline":
        return
    chosen = next((c for c in yellows if c.slug == pick), None)
    if chosen:
        player.hand.remove(chosen)
        player.graveyard.add(chosen)
        effect_draw(state, cid, 1)
        create_token(state, cid, "gold")

CARD_TRIGGERS["golden_tipple"] = [
    TriggerDef(event_type="attacking", effect_fn=_golden_tipple_attack, is_optional=True),
]


# -- murderous_rabble --
# "When attacks, reveal top of deck. Gets +X{p} where X is pitch value."
def _murderous_rabble_attack(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    player = state.players[cid]
    if player.deck.cards:
        top = player.deck.cards[0]
        state.set_card_visibility(top, True)
        pitch = top.pitch or 0
        state.combat.attack_card.effects.append(
            CardEffect(prop="power", stage=7, substage=5, fn=lambda val, p=pitch: val + p))

CARD_TRIGGERS["murderous_rabble"] = [
    TriggerDef(event_type="attacking", effect_fn=_murderous_rabble_attack),
]


# -- portside_exchange --
# "Discard a card, draw a card. If yellow card discarded, create Gold."
def _portside_exchange_on_play(card, event, state):
    from engine.card_effects.ability_keywords import _ask_player
    cid = _controller_id(card)
    player = state.players[cid]
    if not player.hand.cards:
        return
    options = [c.slug for c in player.hand.cards]
    pick = _ask_player(state, cid, options,
                       context="Portside Exchange: choose a card to discard (yellow creates a Gold token)")
    chosen = next((c for c in player.hand.cards if c.slug == pick), player.hand.cards[0])
    is_yellow = chosen.pitch == 2
    player.hand.remove(chosen)
    player.graveyard.add(chosen)
    effect_draw(state, cid, 1)
    if is_yellow:
        create_token(state, cid, "gold")

CARD_TRIGGERS["portside_exchange"] = [
    TriggerDef(event_type="on_play", effect_fn=_portside_exchange_on_play),
]


# -- sea_floor_salvage --
# "Turn a card in a graveyard face-down. If yellow, create Gold."
def _sea_floor_salvage_on_play(card, event, state):
    from engine.card_effects.ability_keywords import _ask_player
    cid = _controller_id(card)
    targets = []
    for pid in state.players:
        for c in state.players[pid].graveyard.cards:
            if c.is_public:
                targets.append(c)
    if not targets:
        return
    options = [c.slug for c in targets]
    pick = _ask_player(state, cid, options,
                       context="Sea Floor Salvage: choose a face-up graveyard card to turn face-down (yellow creates Gold)")
    chosen = next((c for c in targets if c.slug == pick), None)
    if chosen:
        is_yellow = chosen.pitch == 2
        state.set_card_visibility(chosen, False)
        if is_yellow:
            create_token(state, cid, "gold")

CARD_TRIGGERS["sea_floor_salvage"] = [
    TriggerDef(event_type="on_play", effect_fn=_sea_floor_salvage_on_play),
]


# -- shallow_water_shark_harpoon --
# "If cannon activated, gets 'on hit destroy arsenal card, create Gold.'"
def _shallow_water_attack(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    if "activated_cannon" in state.players[cid].current_turn_effects:
        state.players[cid].current_turn_effects.append("shallow_water_on_hit")

def _shallow_water_hit(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    if "shallow_water_on_hit" not in state.players[cid].current_turn_effects:
        return
    state.players[cid].current_turn_effects.remove("shallow_water_on_hit")
    target_id = 3 - cid
    target = state.players[target_id]
    if hasattr(target, 'arsenal') and target.arsenal.cards:
        from engine.card_effects.ability_keywords import _ask_player
        options = [c.slug for c in target.arsenal.cards]
        pick = _ask_player(state, cid, options,
                           context="Shallow Water Shark Harpoon: choose an opponent's arsenal card to destroy and create Gold")
        chosen = next((c for c in target.arsenal.cards if c.slug == pick), None)
        if chosen:
            target.arsenal.remove(chosen)
            target.graveyard.add(chosen)
            create_token(state, cid, "gold")

CARD_TRIGGERS["shallow_water_shark_harpoon"] = [
    TriggerDef(event_type="attacking", effect_fn=_shallow_water_attack),
    TriggerDef(event_type="hit", effect_fn=_shallow_water_hit),
]


# -- shifting_tides --
# "At start of turn, pitch top card. If blue, put on bottom of deck. Else destroy."
def _shifting_tides_start_turn(card, event, state):
    cid = _controller_id(card)
    if cid != state.active_player:
        return
    player = state.players[cid]
    if card not in player.auras.cards:
        return
    if not player.deck.cards:
        _move_to_graveyard(card, state)
        return
    # Reveal and pitch the top card of the deck (CR 8.6.X: always moves to graveyard)
    top = player.deck.cards[0]
    state.set_card_visibility(top, True)
    player.deck.cards.remove(top)
    _move_to_graveyard(top, state)
    # If it was blue, put this aura on the bottom of the deck; otherwise destroy it
    if top.pitch == 3:  # Blue
        player.auras.remove(card)
        player.deck.add_bottom(card)
    else:
        _move_to_graveyard(card, state)

CARD_TRIGGERS["shifting_tides"] = [
    TriggerDef(event_type="start_of_turn", effect_fn=_shifting_tides_start_turn),
]


# -- sift --
# "Put up to 4 cards from hand on bottom of deck, then draw that many."
def _sift_on_play(card, event, state):
    from engine.card_effects.ability_keywords import _ask_player
    cid = _controller_id(card)
    player = state.players[cid]
    count = 0
    for _ in range(4):
        if not player.hand.cards:
            break
        options = [c.slug for c in player.hand.cards] + ["done"]
        pick = _ask_player(state, cid, options,
                           context="Sift: choose a hand card to put on bottom of deck (then draw that many)")
        if pick == "done":
            break
        chosen = next((c for c in player.hand.cards if c.slug == pick), None)
        if chosen:
            player.hand.remove(chosen)
            player.deck.add_bottom(chosen)
            count += 1
    if count > 0:
        effect_draw(state, cid, count)

CARD_TRIGGERS["sift"] = [
    TriggerDef(event_type="on_play", effect_fn=_sift_on_play),
]


# -- sunken_treasure --
# "When this defends, may turn a card in a graveyard face-down. If yellow, create Gold."
def _sunken_treasure_defend(card, event, state):
    if not state.combat or card not in state.combat.defending_cards:
        return
    from engine.card_effects.ability_keywords import _ask_player
    cid = _controller_id(card)
    targets = []
    for pid in state.players:
        for c in state.players[pid].graveyard.cards:
            if c.is_public:
                targets.append(c)
    if not targets:
        return
    options = [c.slug for c in targets] + ["decline"]
    pick = _ask_player(state, cid, options,
                       context="Sunken Treasure: choose a face-up graveyard card to turn face-down (yellow creates Gold)")
    if pick == "decline":
        return
    chosen = next((c for c in targets if c.slug == pick), None)
    if chosen:
        is_yellow = chosen.pitch == 2
        state.set_card_visibility(chosen, False)
        if is_yellow:
            create_token(state, cid, "gold")

CARD_TRIGGERS["sunken_treasure"] = [
    TriggerDef(event_type="defend",
               condition_fn=lambda c, e, s: s.combat and c in s.combat.defending_cards,
               effect_fn=_sunken_treasure_defend, is_optional=True),
]


# -- three_of_a_kind --
# "Draw 3 cards. Until end of turn, you may only play cards from arsenal."
def _three_of_a_kind_on_play(card, event, state):
    cid = _controller_id(card)
    effect_draw(state, cid, 3)
    state.players[cid].current_turn_effects.append("play_from_arsenal_only")

CARD_TRIGGERS["three_of_a_kind"] = [
    TriggerDef(event_type="on_play", effect_fn=_three_of_a_kind_on_play),
]


# -- Arrow turn-attack buffs --
def _arrow_buffs_on_attack(card, event, state):
    if not state.combat or state.combat.attack_card != card:
        return
    if "Arrow" not in (card.types or []):
        return
    cid = _controller_id(card)
    player = state.players[cid]
    attack = state.combat.attack_card

    if "big_game_arrow_+4" in player.current_turn_effects:
        attack.effects.append(CardEffect(prop="power", stage=7, substage=5, fn=lambda val: val + 4))
        player.current_turn_effects.remove("big_game_arrow_+4")
        if ("big_game_harpoon_gold" in player.current_turn_effects
                and "harpoon" in attack.name.lower()):
            player.current_turn_effects.remove("big_game_harpoon_gold")
            player.current_turn_effects.append("big_game_harpoon_on_hit_gold")

    if "catch_arrow_+2" in player.current_turn_effects:
        attack.effects.append(CardEffect(prop="power", stage=7, substage=5, fn=lambda val: val + 2))
        player.current_turn_effects.remove("catch_arrow_+2")

    if "gold_tip_arrow_+3" in player.current_turn_effects:
        attack.effects.append(CardEffect(prop="power", stage=7, substage=5, fn=lambda val: val + 3))
        player.current_turn_effects.remove("gold_tip_arrow_+3")

def _arrow_on_hit_gold(card, event, state):
    if not state.combat or state.combat.attack_card != card:
        return
    cid = _controller_id(card)
    player = state.players[cid]
    if "big_game_harpoon_on_hit_gold" in player.current_turn_effects:
        player.current_turn_effects.remove("big_game_harpoon_on_hit_gold")
        create_token(state, cid, "gold")

CARD_TRIGGERS["goldfin_harpoon_yellow"] = [
    TriggerDef(event_type="attacking", effect_fn=_arrow_buffs_on_attack),
    TriggerDef(event_type="hit", effect_fn=_arrow_on_hit_gold),
]


# ---------------------------------------------------------------------------
# Oscilio Constella Intelligence deck — card-specific triggers
# ---------------------------------------------------------------------------

# -- sigil_of_aether --
# "Destroy at start of action phase. When this leaves the arena, amp 1."
def _sigil_aether_action_phase(card, event, state):
    cid = _controller_id(card)
    if cid != state.active_player:
        return
    player = state.players[cid]
    if card in player.auras.cards:
        _move_to_graveyard(card, state)

def _sigil_aether_leaves(card, event, state):
    cid = _controller_id(card)
    target_id = 3 - cid
    damage = _deal_arcane(state, target_id, 1, card)
    if damage > 0:
        effect_amp(state, cid, 1)

CARD_TRIGGERS["sigil_of_aether"] = [
    TriggerDef(event_type="start_of_action_phase", effect_fn=_sigil_aether_action_phase),
    TriggerDef(event_type="leaves_arena", effect_fn=_sigil_aether_leaves),
]


# -- sigil_of_brilliance --
# "Destroy at start of action phase. When this leaves the arena, draw a card."
def _sigil_brilliance_action_phase(card, event, state):
    cid = _controller_id(card)
    if cid != state.active_player:
        return
    player = state.players[cid]
    if card in player.auras.cards:
        _move_to_graveyard(card, state)

def _sigil_brilliance_leaves(card, event, state):
    cid = _controller_id(card)
    effect_draw(state, cid, 1)

CARD_TRIGGERS["sigil_of_brilliance"] = [
    TriggerDef(event_type="start_of_action_phase", effect_fn=_sigil_brilliance_action_phase),
    TriggerDef(event_type="leaves_arena", effect_fn=_sigil_brilliance_leaves),
]


# -- sigil_of_lightning --
# "Destroy at start of action phase. When leaves, create Embodiment of Lightning."
def _sigil_lightning_action_phase(card, event, state):
    cid = _controller_id(card)
    if cid != state.active_player:
        return
    player = state.players[cid]
    if card in player.auras.cards:
        _move_to_graveyard(card, state)

def _sigil_lightning_leaves(card, event, state):
    cid = _controller_id(card)
    create_token(state, cid, "embodiment_of_lightning")

CARD_TRIGGERS["sigil_of_lightning"] = [
    TriggerDef(event_type="start_of_action_phase", effect_fn=_sigil_lightning_action_phase),
    TriggerDef(event_type="leaves_arena", effect_fn=_sigil_lightning_leaves),
]


# -- sigil_of_conductivity --
# "When this leaves the arena, create Embodiment of Lightning."
def _sigil_conductivity_leaves(card, event, state):
    cid = _controller_id(card)
    create_token(state, cid, "embodiment_of_lightning")

CARD_TRIGGERS["sigil_of_conductivity"] = [
    TriggerDef(event_type="leaves_arena", effect_fn=_sigil_conductivity_leaves),
]


# -- blink --
# "Gain 1 action point."
CARD_TRIGGERS["blink"] = [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: effect_gain_action_point(s, _controller_id(c))),
]


# -- electrostatic_discharge --
# "Next attack action card with cost 1 or less gets +3{p}."
def _electrostatic_on_play(card, event, state):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("electrostatic_next_attack_+3")

CARD_TRIGGERS["electrostatic_discharge"] = [
    TriggerDef(event_type="on_play", effect_fn=_electrostatic_on_play),
]


# -- current_funnel --
# "If last card played was Lightning, this and next action get go again."
def _current_funnel_on_play(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    if "played_lightning" in player.current_turn_effects:
        card.keywords = list(card.keywords or [])
        if "Go again" not in card.keywords:
            card.keywords.append("Go again")
        player.current_turn_effects.append("current_funnel_next_go_again")

CARD_TRIGGERS["current_funnel"] = [
    TriggerDef(event_type="on_play", effect_fn=_current_funnel_on_play),
]


# -- flittering_charge --
# "If you've played an instant this chain link, this gets go again."
def _flittering_charge_on_play(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    if "played_instant_this_link" in player.current_turn_effects:
        card.keywords = list(card.keywords or [])
        if "Go again" not in card.keywords:
            card.keywords.append("Go again")

CARD_TRIGGERS["flittering_charge"] = [
    TriggerDef(event_type="on_play", effect_fn=_flittering_charge_on_play),
]


# -- blast_to_oblivion --
# "When attacks, next instant this link returns aura with cost ≤1 to hand."
# NOTE: Flag consumption ("blast_oblivion_next_instant_bounce") lives in
# _oscilio_track_lightning (oscilio_constella_intelligence on_play listener).
# These effects only fire when Oscilio is in play as the hero.
# By design: both cards are part of Oscilio's kit and are not intended for other heroes.
def _blast_to_oblivion_attack(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("blast_oblivion_next_instant_bounce")

CARD_TRIGGERS["blast_to_oblivion"] = [
    TriggerDef(event_type="attacking", effect_fn=_blast_to_oblivion_attack),
]


# -- gone_in_a_flash --
# "When attacks, next instant this link may return this to hand."
def _gone_in_a_flash_attack(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("gone_flash_next_instant_bounce")

CARD_TRIGGERS["gone_in_a_flash"] = [
    TriggerDef(event_type="attacking", effect_fn=_gone_in_a_flash_attack),
]


# -- etchings_of_arcana --
# "Deal 3 arcane damage. Surge (>3): return target Sigil aura from graveyard to hand."
def _etchings_on_play(card, event, state):
    cid = _controller_id(card)
    target_id = 3 - cid
    _deal_arcane(state, target_id, 3, card)

def _etchings_surge(card, event, state):
    if not surge_check(event, 4):  # "more than 3 damage" = dealt >= 4
        return
    cid = _controller_id(card)
    player = state.players[cid]
    from engine.card_effects.ability_keywords import _ask_player
    sigils = [c for c in player.graveyard.cards if "sigil" in c.slug.lower()]
    if not sigils:
        return
    options = [c.slug for c in sigils]
    pick = _ask_player(state, cid, options,
                       context="Etchings of Arcana (surge): choose a Sigil from graveyard to return to hand")
    chosen = next((c for c in sigils if c.slug == pick), None)
    if chosen:
        player.graveyard.remove(chosen)
        player.hand.add(chosen)

CARD_TRIGGERS["etchings_of_arcana"] = [
    TriggerDef(event_type="on_play", effect_fn=_etchings_on_play),
    TriggerDef(event_type="damage_dealt",
               condition_fn=lambda c, e, s: surge_check(e, 4),
               effect_fn=_etchings_surge),
]


# -- mind_warp --
# "Deal 2 arcane. Surge (>2): opponent shuffles hand into deck, draws that many minus 1."
def _mind_warp_on_play(card, event, state):
    cid = _controller_id(card)
    target_id = 3 - cid
    _deal_arcane(state, target_id, 2, card)

def _mind_warp_surge(card, event, state):
    if not surge_check(event, 3):  # "more than 2 damage" = dealt >= 3
        return
    cid = _controller_id(card)
    target_id = 3 - cid
    target = state.players[target_id]
    hand_count = len(target.hand.cards)
    cards_to_shuffle = list(target.hand.cards)
    for c in cards_to_shuffle:
        target.hand.remove(c)
        target.deck.add_bottom(c)
    effect_shuffle(state, target_id)
    effect_draw(state, target_id, max(0, hand_count - 1))

CARD_TRIGGERS["mind_warp"] = [
    TriggerDef(event_type="on_play", effect_fn=_mind_warp_on_play),
    TriggerDef(event_type="damage_dealt",
               condition_fn=lambda c, e, s: surge_check(e, 3),
               effect_fn=_mind_warp_surge),
]


# -- flash_of_brilliance (equipment) --
# "When defends, may discard Lightning card to return target aura to hand."
def _flash_brilliance_defend(card, event, state):
    if not state.combat or card not in state.combat.defending_cards:
        return
    from engine.card_effects.ability_keywords import _ask_player
    cid = _controller_id(card)
    player = state.players[cid]
    lightning_cards = [c for c in player.hand.cards if "Lightning" in (c.types or [])]
    if not lightning_cards:
        return
    choice = _ask_player(state, cid, [True, False],
                         context="Flash of Brilliance: discard a Lightning card to return an aura to hand?")
    if not choice:
        return
    options = [c.slug for c in lightning_cards]
    pick = _ask_player(state, cid, options,
                       context="Choose a Lightning card to discard (Flash of Brilliance)")
    chosen = next((c for c in lightning_cards if c.slug == pick), lightning_cards[0])
    player.hand.remove(chosen)
    player.graveyard.add(chosen)
    auras = list(player.auras.cards)
    if auras:
        aura_opts = [c.slug for c in auras]
        aura_pick = _ask_player(state, cid, aura_opts,
                                context="Choose an aura to return to hand (Flash of Brilliance)")
        aura = next((c for c in auras if c.slug == aura_pick), None)
        if aura:
            player.auras.remove(aura)
            player.hand.add(aura)

CARD_TRIGGERS["flash_of_brilliance"] = [
    TriggerDef(event_type="defend",
               condition_fn=lambda c, e, s: s.combat and c in s.combat.defending_cards,
               effect_fn=_flash_brilliance_defend, is_optional=True),
]

def _helios_mitre_end_phase(card, event, state):
    """If Helios Mitre was activated this turn, destroy it at the beginning of the end phase."""
    cid = _controller_id(card)
    player = state.players[cid]
    if "helios_mitre_destroy_eot" in player.current_turn_effects:
        if card in player.head.cards:
            player.current_turn_effects.remove("helios_mitre_destroy_eot")
            player.head.remove(card)
            player.graveyard.add(card)

CARD_TRIGGERS["helios_mitre"] = [
    TriggerDef(event_type="start_of_end_phase", condition_fn=lambda c, e, s: ("helios_mitre_destroy_eot" in s.players[_controller_id(c)].current_turn_effects), effect_fn=_helios_mitre_end_phase),
]
# -- temporal_wobble --
# "Negate target non-attack action if cost < sigils controlled. Opponent gains AP."
def _temporal_wobble_on_play(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    target_id = 3 - cid
    sigil_count = sum(1 for c in player.auras.cards if "sigil" in c.slug.lower())
    eligible = [e for e in (state.stack_entries or [])
                if e.card and "Action" in (e.card.types or [])
                and "Attack" not in (e.card.types or [])
                and (e.card.cost or 0) < sigil_count]
    if eligible:
        from engine.card_effects.ability_keywords import _ask_player
        options = [e.card.slug for e in eligible]
        pick = _ask_player(state, cid, options,
                           context="Temporal Wobble: choose a non-attack action to negate")
        target_entry = next((e for e in eligible if e.card.slug == pick), eligible[0])
        effect_negate(state, target_entry)
    effect_gain_action_point(state, target_id)

CARD_TRIGGERS["temporal_wobble"] = [
    TriggerDef(event_type="on_play", effect_fn=_temporal_wobble_on_play),
]


# -- electromagnetic_somersault --
# "Return up to 2 attack action cards with cost ≥0 on the active chain link to their
#  owner's hand when the chain link resolves."  (delayed trigger — CR 6.0)
def _em_somersault_on_play(card, event, state):
    """Selection window: player chooses which cards to return.
    Actual movement is deferred to chain link close."""
    from engine.card_effects.ability_keywords import _ask_player
    cid = _controller_id(card)
    if not state.combat:
        return
    # "Active chain link" = attacking card + cards used to defend/react
    on_chain = []
    if state.combat.attack_card:
        atk = state.combat.attack_card
        if "Attack" in (atk.types or []) and "Action" in (atk.types or []):
            on_chain.append(atk)
    for c in (state.combat.defending_cards or []):
        if "Attack" in (c.types or []) and "Action" in (c.types or []):
            on_chain.append(c)
    eligible = on_chain[:]
    controller = state.players[cid]
    for _ in range(2):
        if not eligible:
            break
        options = [c.slug for c in eligible] + ["done"]
        pick = _ask_player(state, cid, options,
                           context="Electromagnetic Somersault: choose up to 2 attack action cards"
                                   " to return to their owner's hand when this chain link resolves")
        if pick == "done":
            break
        chosen = next((c for c in eligible if c.slug == pick), None)
        if chosen:
            # Store object_id in current_turn_effects as deferred return token
            controller.current_turn_effects.append(f"em_pending:{chosen.object_id}")
            eligible.remove(chosen)

def _em_somersault_chain_close(card, event, state):
    """Chain close: move deferred cards to their owner's hand."""
    cid = _controller_id(card)
    controller = state.players[cid]
    pending = [e for e in controller.current_turn_effects if e.startswith("em_pending:")]
    for key in pending:
        oid = int(key.split(":")[1])
        # Search graveyard first (chain resolved), then defending_cards (in case still there)
        found = False
        for pid, player in state.players.items():
            for zone in [player.graveyard, player.weapon1, player.weapon2,
                         player.head, player.chest, player.arms, player.legs,
                         player.items, player.auras, player.allies, player.hand]:
                target = next((c for c in zone.cards if c.object_id == oid), None)
                if target:
                    zone.remove(target)
                    state.players[target.owner].hand.add(target)
                    found = True
                    break
            if found:
                break
        if not found and state.combat and state.combat.defending_cards:
            target = next((c for c in state.combat.defending_cards if c.object_id == oid), None)
            if target:
                state.combat.defending_cards.remove(target)
                state.players[target.owner].hand.add(target)
        controller.current_turn_effects.remove(key)

CARD_TRIGGERS["electromagnetic_somersault"] = [
    TriggerDef(event_type="on_play", effect_fn=_em_somersault_on_play),
    TriggerDef(event_type="combat_chain_close", effect_fn=_em_somersault_chain_close),
]


# -- comet_storm__shock (meld) --
# TOP  (Comet Storm): "Deal 5 arcane damage."          — action-speed, costs 2
# BOTTOM (Shock):     "Deal 1 arcane damage."          — instant-speed, costs 0
# MELDED: Shock fires via on_play → priority gap → Comet Storm via triggered continuation
def _comet_storm_on_play(card, event, state):
    cid = _controller_id(card)
    target_id = 3 - cid
    ms = getattr(card, 'meld_side', None)
    if ms == 'both':
        return  # effects handled at layer resolution time (CR 5.3.4d) via MELD_EFFECT_REGISTRY
    if ms == 'bottom':
        _deal_arcane(state, target_id, 1, card)
    else:
        # Top side (meld_side='top', None, or legacy): Comet Storm 5 arcane
        _deal_arcane(state, target_id, 5, card)

CARD_TRIGGERS["comet_storm__shock"] = [
    TriggerDef(event_type="on_play", effect_fn=_comet_storm_on_play),
]


# -- aether_wildfire_red --
# "Deal 4 arcane damage to target opposing hero.
#  If Aether Wildfire is played during an opponents turn, until end of turn,
#  action card effects that deal arcane damage instead deal that much arcane
#  damage plus X, where X is the damage dealt by Aether Wildfire."
def _aether_wildfire_on_play(card, event, state):
    cid = _controller_id(card)
    target_id = 3 - cid
    # Deal 4 arcane damage and track how much actually landed
    damage_dealt = _deal_arcane(state, target_id, 4, card)
    # Check if played during opponent's turn
    if cid != state.active_player and damage_dealt > 0:
        # Register a replacement effect that boosts action card arcane damage
        from engine.effects import ReplacementEffect, ReplacementType
        boost_amount = damage_dealt
        # Set a flag to track this effect (cleared at end of turn via current_turn_effects)
        flag_key = f"aether_wildfire_boost_{boost_amount}"
        state.players[cid].current_turn_effects.append(flag_key)
        
        def _condition(evt, gs):
            # Check if the boost flag is still active (will be cleared at end of turn)
            if flag_key not in gs.players[cid].current_turn_effects:
                return False
            # Check if this is arcane damage from an Action card
            if evt.get("type") != "damage" or evt.get("damage_type") != "arcane":
                return False
            source = evt.get("source")
            if source is None or "Action" not in (source.types or []):
                return False
            # Check that the source is controlled by the same player
            return _controller_id(source) == cid
        
        def _replace(evt, gs):
            # Add bonus damage
            evt["amount"] = evt.get("amount", 0) + boost_amount
            return evt
        
        state.effect_manager.add_replacement(ReplacementEffect(
            source_card=card,
            replacement_type=ReplacementType.STANDARD,
            condition_fn=_condition,
            replace_fn=_replace,
            owner_id=cid,
            consumed=False,  # Persists for all arcane damage this turn
        ))

CARD_TRIGGERS["aether_wildfire_red"] = [
    TriggerDef(event_type="on_play", effect_fn=_aether_wildfire_on_play),
]


# -- consign_to_cosmos__shock (meld) --
# TOP  (Consign): "Banish X instant/aura cards from any graveyard, X = arcane damage dealt this turn."
# BOTTOM (Shock): "Deal 1 arcane damage to any target."
def _consign_top_effect(card, state):
    from engine.card_effects.ability_keywords import _ask_player
    cid = _controller_id(card)
    arcane_amount = state.players[cid].current_turn_effects.count("dealt_arcane")
    for _ in range(arcane_amount):
        valid = [(pid, c)
                 for pid, p in state.players.items()
                 for c in p.graveyard.cards
                 if any(t in (c.types or []) for t in ("Instant", "Aura"))]
        if not valid:
            break
        options = [c.slug for _, c in valid]
        pick = _ask_player(state, cid, options,
                           context="Consign to Cosmos // Shock: choose an instant or aura to banish from any graveyard")
        chosen = next(((pid, c) for pid, c in valid if c.slug == pick), None)
        if chosen:
            pid, chosen_card = chosen
            state.players[pid].graveyard.remove(chosen_card)
            effect_banish(state, chosen_card, face_up=True, banisher_id=cid)

def _consign_to_cosmos_on_play(card, event, state):
    cid = _controller_id(card)
    ms = getattr(card, 'meld_side', None)
    if ms == 'both':
        return  # effects handled at layer resolution time (CR 5.3.4d) via MELD_EFFECT_REGISTRY
    if ms == 'bottom':
        _deal_arcane(state, 3 - cid, 1, card)
    else:
        _consign_top_effect(card, state)

CARD_TRIGGERS["consign_to_cosmos__shock"] = [
    TriggerDef(event_type="on_play", effect_fn=_consign_to_cosmos_on_play),
]


# -- null__shock (meld) --
# TOP  (Null):    "Negate target instant with cost < total arcane damage dealt this turn."
# BOTTOM (Shock): "Deal 1 arcane damage to any target."
def _null_top_effect(card, state, resolving_entry=None):
    cid = _controller_id(card)
    declared_targets: list[str] = []

    # During meld second resolution, resolve_stack passes the card layer's StackEntry.
    # During normal top-side play, the card layer is still on stack while on_play resolves.
    pending_entry = None
    for e in (state.stack_entries or []):
        if e.card is card and e.layer_type == 'card':
            pending_entry = e
            break
    if pending_entry and pending_entry.declared_targets:
        declared_targets.extend([str(t) for t in pending_entry.declared_targets])

    # During meld 'both' second-pass resolution, the card layer is popped and provided explicitly.
    if not declared_targets and resolving_entry and resolving_entry.declared_targets:
        declared_targets.extend([str(t) for t in resolving_entry.declared_targets])

    target_entry = None
    for raw in declared_targets:
        target_key = str(raw)
        if target_key.startswith("oid:"):
            try:
                target_oid = int(target_key.split(":", 1)[1])
            except (TypeError, ValueError):
                continue
            target_entry = next((e for e in state.stack_entries if e.card and e.card.object_id == target_oid), None)
        else:
            target_entry = next((e for e in state.stack_entries if e.card and e.card.slug == target_key), None)
        if target_entry is not None:
            break

    if target_entry is None or target_entry.card is None:
        return
    if "Instant" not in (target_entry.card.types or []):
        return

    # Null checks arcane damage dealt to opposing heroes this turn.
    arcane_count = state.players[cid].current_turn_effects.count("dealt_arcane_to_opp_hero")
    target_base_cost = 0 if target_entry.card.base_cost is None else target_entry.card.base_cost
    if target_base_cost < arcane_count:
        effect_negate(state, target_entry)

def _null_shock_on_play(card, event, state):
    cid = _controller_id(card)
    ms = getattr(card, 'meld_side', None)
    if ms == 'both':
        return  # effects handled at layer resolution time (CR 5.3.4d) via MELD_EFFECT_REGISTRY
    if ms == 'bottom':
        _deal_arcane(state, 3 - cid, 1, card)
    else:
        _null_top_effect(card, state)

CARD_TRIGGERS["null__shock"] = [
    TriggerDef(event_type="on_play", effect_fn=_null_shock_on_play),
]


# ---------------------------------------------------------------------------
# Meld resolution registry
# resolve_stack dispatches here for two-pass resolution (CR 5.3.4d).
# For meld_side='both': first pass fires bottom (Shock), second fires top.
# ---------------------------------------------------------------------------

def _comet_storm_top_resolve(card, state):
    """Left-side (Comet Storm) at second resolution: 5 arcane damage."""
    _deal_arcane(state, 3 - _controller_id(card), 5, card)


def _meld_shock_resolve(card, state):
    """Right-side (Shock) at first resolution: 1 arcane damage. Shared by all three meld cards."""
    _deal_arcane(state, 3 - _controller_id(card), 1, card)


MELD_EFFECT_REGISTRY: dict = {
    'comet_storm__shock':       {'bottom': _meld_shock_resolve, 'top': _comet_storm_top_resolve},
    'consign_to_cosmos__shock': {'bottom': _meld_shock_resolve, 'top': _consign_top_effect},
    'null__shock':              {'bottom': _meld_shock_resolve, 'top': _null_top_effect},
}


# -- aether_bindings_of_the_third_age --
# "Whenever a Sigil aura permanent you control leaves the arena this turn, amp 1."
def _aether_bindings_sigil_leave(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    if "aether_bindings_sigil_amp" not in player.current_turn_effects:
        return
    if not (hasattr(event, 'data') and event.data.get('card')):
        return
    leaving = event.data['card']
    # CR 1.3.3: a deck-card is a permanent while in the arena (not combat chain)
    # Check by prev_zone to distinguish a sigil aura in permanents vs on combat chain
    is_permanent = leaving.prev_zone == "permanents"
    is_sigil_aura = (
        "sigil" in (leaving.name or "").lower()
        and "Aura" in (leaving.subtypes or [])
    )
    if is_sigil_aura and is_permanent and _controller_id(leaving) == cid:
        effect_amp(state, cid, 1)

CARD_TRIGGERS["aether_bindings_of_the_third_age"] = [
    TriggerDef(event_type="leaves_arena", effect_fn=_aether_bindings_sigil_leave),
]


# -- channel_lightning_valley --
# "First time damage dealt to a hero each turn, draw a card."
def _channel_lightning_damage(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    if card not in player.auras.cards:
        return
    if "channel_lightning_drawn" not in player.current_turn_effects:
        player.current_turn_effects.append("channel_lightning_drawn")
        effect_draw(state, cid, 1)

CARD_TRIGGERS["channel_lightning_valley"] = [
    TriggerDef(event_type="damage_dealt", effect_fn=_channel_lightning_damage),
    TriggerDef(
        event_type="start_of_end_phase",
        condition_fn=lambda c, e, s: c in s.players[_controller_id(c)].auras.cards,
        effect_fn=lambda c, e, s: channel_upkeep(c, "Lightning", s),
    ),
]


# -- Oscilio turn-effect listeners --
# Track Lightning/instant cards played for Volzar, current_funnel, etc.
def _oscilio_track_lightning(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    if not (hasattr(event, 'data') and event.data.get('card')):
        return
    played = event.data['card']
    if _controller_id(played) != cid:
        return
    if "Lightning" in (played.types or []):
        player.current_turn_effects.append("played_lightning")
    if played.is_instant and state.combat is not None:
        # Only track within an active chain link; out-of-combat instants don't count
        player.current_turn_effects.append("played_instant_this_link")
        # Lightning Greaves: grant go again to instants played this turn
        if "lightning_greaves_instants_go_again" in player.current_turn_effects:
            played.keywords = list(played.keywords or [])
            if "Go again" not in played.keywords:
                played.keywords.append("Go again")
        # Blast to Oblivion: return aura permanent (cost ≤1) OR any aura token to owner's hand
        if "blast_oblivion_next_instant_bounce" in player.current_turn_effects:
            player.current_turn_effects.remove("blast_oblivion_next_instant_bounce")
            from engine.card_effects.ability_keywords import _ask_player
            auras = [c for c in player.auras.cards
                     if "Token" in (c.types or []) or (c.cost or 0) <= 1]
            if auras:
                pick = _ask_player(state, cid, [c.slug for c in auras],
                                   context="Blast to Oblivion: choose an aura permanent (cost ≤1) or aura token to return to hand")
                chosen = next((c for c in auras if c.slug == pick), None)
                if chosen:
                    player.auras.remove(chosen)
                    player.hand.add(chosen)
        # Gone in a Flash: return it from the graveyard to hand
        if "gone_flash_next_instant_bounce" in player.current_turn_effects:
            player.current_turn_effects.remove("gone_flash_next_instant_bounce")
            gone_card = next(
                (c for c in player.graveyard.cards if c.slug.startswith("gone_in_a_flash")),
                None
            )
            if gone_card:
                player.graveyard.remove(gone_card)
                player.hand.add(gone_card)
    # Current Funnel: grant go again to next non-instant action card played
    if "current_funnel_next_go_again" in player.current_turn_effects:
        if "Action" in (played.types or []) and "Instant" not in (played.types or []):
            player.current_turn_effects.remove("current_funnel_next_go_again")
            played.keywords = list(played.keywords or [])
            if "Go again" not in played.keywords:
                played.keywords.append("Go again")

def _oscilio_chain_close_cleanup(card, event, state):
    """Clear per-chain-link tracking flags at chain close (e.g. played_instant_this_link)."""
    cid = _controller_id(card)
    player = state.players[cid]
    while "played_instant_this_link" in player.current_turn_effects:
        player.current_turn_effects.remove("played_instant_this_link")

CARD_TRIGGERS["oscilio_constella_intelligence"] = [
    TriggerDef(event_type="on_play", effect_fn=_oscilio_track_lightning),
    TriggerDef(event_type="combat_chain_close", effect_fn=_oscilio_chain_close_cleanup),
]


# ---------------------------------------------------------------------------
# Arakni, Marionette — hero ability (continuous + end phase)
# ---------------------------------------------------------------------------

# Continuous: stealth attacks vs marked hero get +1{p} and "on hit go again"
def _arakni_marionette_attack_buff(card, event, state):
    """Hero continuous ability: stealth attacks vs marked hero get +1{p} + on-hit go again.
    Only active while in Arakni, Marionette form (not transformed to a demi-hero)."""
    if card.slug != "arakni_marionette":
        return  # Transformed — ability inactive
    if not state.combat:
        return
    attack = state.combat.attack_card
    if not attack:
        return
    cid = _controller_id(card)
    if _controller_id(attack) != cid:
        return
    is_stealth = "Stealth" in (attack.keywords or [])
    if not is_stealth:
        return
    target_id = 3 - cid
    if not _is_marked(state, target_id):
        return
    # +1{p}
    attack.effects.append(CardEffect(prop="power", stage=7, substage=5, fn=lambda val: val + 1))
    # "When this hits, this gets go again" — add hit-triggered go again
    state.players[cid].current_turn_effects.append("arakni_stealth_hit_go_again")

# On-hit: grant go again to stealth attack that hit a marked hero
def _arakni_marionette_hit_go_again(card, event, state):
    if card.slug != "arakni_marionette":
        return  # Transformed — ability inactive
    if not state.combat:
        return
    attack = state.combat.attack_card
    if not attack:
        return
    cid = _controller_id(card)
    if _controller_id(attack) != cid:
        return
    if "arakni_stealth_hit_go_again" in state.players[cid].current_turn_effects:
        state.players[cid].current_turn_effects.remove("arakni_stealth_hit_go_again")
        attack.keywords = list(attack.keywords or [])
        if "Go again" not in attack.keywords:
            attack.keywords.append("Go again")

# Combat chain close: clean up any unconsumed stealth buff flag (attack missed — flag never consumed by hit)
def _arakni_marionette_chain_close_cleanup(card, event, state):
    if card.slug != "arakni_marionette":
        return
    cid = _controller_id(card)
    player = state.players[cid]
    if "arakni_stealth_hit_go_again" in player.current_turn_effects:
        player.current_turn_effects.remove("arakni_stealth_hit_go_again")

# Agent of Chaos demi-hero slugs
AGENT_OF_CHAOS_SLUGS = [
    "arakni_black_widow", "arakni_funnel_web", "arakni_orbweaver",
    "arakni_redback", "arakni_tarantula", "arakni_trapdoor",
]

def _become_agent_of_chaos(state, player_id, choose=False):
    """Transform hero into a random (or chosen) Agent of Chaos demi-hero."""
    import random as rng
    from engine.card_effects.ability_keywords import _ask_player
    player = state.players[player_id]
    if choose:
        pick = _ask_player(state, player_id, AGENT_OF_CHAOS_SLUGS,
                           context="Choose which Agent of Chaos form to become (Mask of Deceit)")
        slug = pick if pick in AGENT_OF_CHAOS_SLUGS else rng.choice(AGENT_OF_CHAOS_SLUGS)
    else:
        slug = rng.choice(AGENT_OF_CHAOS_SLUGS)
    # Replace hero identity but keep life total
    player.hero.slug = slug
    player.hero.name = slug.replace("_", " ").title()
    player.hero.types = ["Chaos", "Assassin", "Demi-Hero"]  # Agent of Chaos cards are Demi-Hero type

def _return_to_brood(player):
    """Restore hero card to Arakni, Marionette identity."""
    player.hero.slug = "arakni_marionette"
    player.hero.name = "Arakni, Marionette"
    player.hero.types = ["Chaos", "Assassin", "Hero"]  # Marionette's printed type includes "Chaos"

# End phase trigger handles both:
#   1. Demi-hero form: "return to the brood" (restore Marionette identity)
#   2. Marionette form: if opponent is marked, become random Agent of Chaos
def _arakni_marionette_end_phase(card, event, state):
    cid = _controller_id(card)
    if cid != state.active_player:
        return
    player = state.players[cid]
    # If currently a demi-hero, return to brood first
    if card.slug in AGENT_OF_CHAOS_SLUGS:
        _return_to_brood(player)
        return  # Done for this end phase — don't also transform back out
    # Now in Marionette form: check if opponent is marked to transform
    opp_id = 3 - cid
    if _is_marked(state, opp_id):
        _become_agent_of_chaos(state, cid, choose=False)

CARD_TRIGGERS["arakni_marionette"] = [
    TriggerDef(event_type="attacking", effect_fn=_arakni_marionette_attack_buff),
    TriggerDef(event_type="hit", effect_fn=_arakni_marionette_hit_go_again),
    TriggerDef(event_type="combat_chain_close", effect_fn=_arakni_marionette_chain_close_cleanup),
    TriggerDef(event_type="start_of_end_phase", effect_fn=_arakni_marionette_end_phase),
]


# ---------------------------------------------------------------------------
# Mask of Deceit — equipment (head)
# ---------------------------------------------------------------------------

# "When this defends, become a random Agent of Chaos.
#  If the attacking hero is marked, instead choose the Agent of Chaos."
def _mask_of_deceit_defend(card, event, state):
    if not state.combat:
        return
    if card not in (state.combat.defending_cards or []):
        return
    cid = _controller_id(card)
    attacker_id = state.combat.attacker_id
    choose = _is_marked(state, attacker_id)
    _become_agent_of_chaos(state, cid, choose=choose)

CARD_TRIGGERS["mask_of_deceit"] = [
    TriggerDef(event_type="defend", effect_fn=_mask_of_deceit_defend),
]


# ---------------------------------------------------------------------------
# Blacktek Whisperers — equipment (legs)
# ---------------------------------------------------------------------------

# Graveyard ability: start of turn, may destroy 2 Silvers to re-equip.
def _blacktek_whisperers_start_turn(card, event, state):
    cid = card.owner  # use owner since it's in graveyard
    player = state.players[cid]
    if cid != state.active_player:
        return
    # Only triggers while in graveyard
    if card not in player.graveyard.cards:
        return
    silvers = [c for c in player.items.cards if "silver" in c.slug.lower() and "Token" in c.types]
    if len(silvers) < 2:
        return
    from engine.card_effects.ability_keywords import _ask_player
    choice = _ask_player(state, cid, [True, False],
                         context="Destroy 2 Silver tokens to re-equip Blacktek Whisperers from graveyard?")
    if not choice:
        return
    # Destroy 2 silvers
    for s in silvers[:2]:
        player.items.remove(s)
        player.graveyard.add(s)
    # Re-equip from graveyard
    player.graveyard.remove(card)
    player.legs.add(card, is_public=True)

# Attack Reaction handled in registry.py ATTACK_REACTION_CONDITIONS.
# On-hit go again check handled in _dagger_turn_hit_effects.

CARD_TRIGGERS["blacktek_whisperers"] = [
    TriggerDef(event_type="start_of_turn", effect_fn=_blacktek_whisperers_start_turn),
]


# ---------------------------------------------------------------------------
# Schism of Chaos — pitch trigger
# ---------------------------------------------------------------------------

# "When this is pitched: Each hero shuffles, then puts the top card of their
#  deck facedown into their arsenal."
def _schism_of_chaos_pitched(card, event, state):
    if not hasattr(event, 'data'):
        return
    pitched_card = event.data.get('card')
    if pitched_card is not card:
        return
    for pid in state.players:
        player = state.players[pid]
        effect_shuffle(state, pid)
        top = player.deck.top
        if top and player.arsenal.top is None:
            player.deck.remove(top)
            player.arsenal.add(top, is_public=False)

CARD_TRIGGERS["schism_of_chaos"] = [
    TriggerDef(event_type="card_pitched", effect_fn=_schism_of_chaos_pitched),
]


# ---------------------------------------------------------------------------
# Riches of Tropal-Dhani — pitch trigger
# ---------------------------------------------------------------------------

# "When this is pitched: Create a Gold token."
def _riches_pitched(card, event, state):
    if not hasattr(event, 'data'):
        return
    pitched_card = event.data.get('card')
    if pitched_card is not card:
        return
    pitcher_id = event.data.get('pitcher_id')
    create_token(state, pitcher_id, "gold")

CARD_TRIGGERS["riches_of_tropal_dhani"] = [
    TriggerDef(event_type="card_pitched", effect_fn=_riches_pitched),
]


# ---------------------------------------------------------------------------
# Cheating Scoundrel — action card
# ---------------------------------------------------------------------------

# "The next attack action card you play this turn gets +3{p} and wagers with
#  the defending hero. The winner creates a Gold token. The next time you would
#  lose a wager this turn, instead you may discard a card. If you do, you win
#  the wager. Go again"
def _cheating_scoundrel_on_play(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    player.current_turn_effects.append("cheating_scoundrel_next_attack_+3")
    player.current_turn_effects.append("cheating_scoundrel_wager")
    player.current_turn_effects.append("cheating_scoundrel_cheat_wager")
    player.action_points += 1  # Go again

CARD_TRIGGERS["cheating_scoundrel"] = [
    TriggerDef(event_type="on_play", effect_fn=_cheating_scoundrel_on_play),
]


# ---------------------------------------------------------------------------
# Throw Caution to the Wind — instant, damage prevention
# ---------------------------------------------------------------------------

# "Reveal the top card of your deck. The next time you would be dealt damage
#  this turn, prevent X of that damage, where X is the pitch value of the
#  card revealed this way."
def _throw_caution_on_play(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    top = player.deck.top
    if not top:
        return
    prevent_amount = top.pitch or 0
    state.set_card_visibility(top, True)
    # Register one-shot damage prevention
    from engine.effects import ReplacementEffect, ReplacementType
    def _condition(evt, gs):
        return (evt.get("type") == "damage"
                and evt.get("amount", 0) > 0
                and evt.get("target_player_id") == cid)
    def _replace(evt, gs):
        prevented = min(prevent_amount, evt.get("amount", 0))
        evt["amount"] = evt.get("amount", 0) - prevented
        return evt
    state.effect_manager.add_replacement(ReplacementEffect(
        source_card=card,
        replacement_type=ReplacementType.PREVENTION,
        condition_fn=_condition,
        replace_fn=_replace,
        owner_id=cid,
        prevention_amount=prevent_amount,
    ))

CARD_TRIGGERS["throw_caution_to_the_wind"] = [
    TriggerDef(event_type="on_play", effect_fn=_throw_caution_on_play),
]


# ---------------------------------------------------------------------------
# Cloud Cover — instant, damage prevention
# ---------------------------------------------------------------------------

# "The next time you would be dealt damage this turn, prevent 3/2/1 of that
#  damage." (red=3, yellow=2, blue=1)
def _cloud_cover_on_play(card, event, state):
    cid = _controller_id(card)
    # Determine prevention amount from pitch color
    if card.pitch == 1:
        prevent_amount = 3  # red
    elif card.pitch == 2:
        prevent_amount = 2  # yellow
    else:
        prevent_amount = 1  # blue
    from engine.effects import ReplacementEffect, ReplacementType
    def _condition(evt, gs):
        return (evt.get("type") == "damage"
                and evt.get("amount", 0) > 0
                and evt.get("target_player_id") == cid)
    def _replace(evt, gs):
        prevented = min(prevent_amount, evt.get("amount", 0))
        evt["amount"] = evt.get("amount", 0) - prevented
        return evt
    state.effect_manager.add_replacement(ReplacementEffect(
        source_card=card,
        replacement_type=ReplacementType.PREVENTION,
        condition_fn=_condition,
        replace_fn=_replace,
        owner_id=cid,
        prevention_amount=prevent_amount,
    ))

CARD_TRIGGERS["cloud_cover"] = [
    TriggerDef(event_type="on_play", effect_fn=_cloud_cover_on_play),
]

def steam_counter_trigger(counter_amount):
    """Factory: on enters_arena trigger that puts N steam counters on the card."""
    return TriggerDef(
        event_type="enters_arena",
        effect_fn=lambda c, e, s, _n=counter_amount: _put_counter(s, c, "steam", _n),
    )

EFFECT_MAP = {
    "dissolving_shield_red":   [steam_counter_trigger(3)],
    "dissolving_shield_yellow": [steam_counter_trigger(2)],
    "dissolving_shield_blue":  [steam_counter_trigger(1)],
    "backup_protocol":         [steam_counter_trigger(1)],
    "hyper_driver_red":        [steam_counter_trigger(3)],
    "hyper_driver_yellow":     [steam_counter_trigger(2)],
    "hyper_driver_blue":       [steam_counter_trigger(1)],
    "assembly_module_blue":    [steam_counter_trigger(1)],
    "teklo_core_blue":         [steam_counter_trigger(2)],
    "boom_grenade":            [steam_counter_trigger(1)],
    "teklo_pounder_blue":      [steam_counter_trigger(2)],
}

CARD_TRIGGERS.update(EFFECT_MAP)

# ---------------------------------------------------------------------------
# Ripple Away — instant, discard-from-hand activation
# ---------------------------------------------------------------------------

# "Instant - Discard this: If an action card effect would create 1 or more
#  tokens this turn, instead it creates that many minus 1 of each of those
#  tokens."
# Handled as an on_play trigger (the discard-to-activate is the play cost).
# Ripple Away is a Generic Action - Attack (4 power, cost 2).
# Its "Instant - Discard this:" ability is a hand-discard activation — it doesn't
# fire on_play. Discard-from-hand activations require a separate ActionType not
# yet implemented; the card is playable as a normal 4-power attack.
# (No CARD_TRIGGERS entry needed for the attack — it has no on-play or on-hit text.)


# ---------------------------------------------------------------------------
# Under the Trap-Door — instant, discard-from-hand activation
# ---------------------------------------------------------------------------

# "Instant - Discard this: Banish target trap from your graveyard. If you do,
#  you may play it this turn and if it would be put into the graveyard this
#  turn, instead banish it."
def _under_the_trap_door_on_play(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    from engine.card_effects.ability_keywords import _ask_player
    traps = [c for c in player.graveyard.cards if "Trap" in (c.types or [])]
    if not traps:
        return
    options = [c.slug for c in traps]
    pick = _ask_player(state, cid, options,
                       context="Under the Trap-Door: choose a Trap from graveyard to banish and play this turn")
    target = next((c for c in traps if c.slug == pick), None)
    if target:
        effect_banish(state, target, face_up=True, banisher_id=cid)
        # Mark trap as playable this turn (from banish zone)
        player.current_turn_effects.append(f"trap_door_playable_{target.slug}")
        # Mark it so if it goes to graveyard, it gets banished instead
        player.current_turn_effects.append(f"trap_door_banish_on_gy_{target.slug}")

# under_the_trap_door discard activation is handled via DISCARD_ACTIVATE_EFFECTS in registry.py
# (not an on_play trigger — the effect fires when discarded from hand, not when played as an attack)


# ---------------------------------------------------------------------------
# Registry — builds triggers for a card from keywords + card-specific
# ---------------------------------------------------------------------------

def get_triggers_for_card(card: Card) -> list[TriggerDef]:
    """Get all trigger definitions for a card.
    Combines keyword-derived triggers, data-driven text-parsed triggers,
    and card-specific triggers.  Manual CARD_TRIGGERS entries take precedence
    over text-parsed triggers."""
    triggers = build_keyword_triggers(card)

    # Add card-specific triggers (manual overrides)
    slug = card.slug
    has_manual = slug in CARD_TRIGGERS

    # Also check base name (without color suffix) for shared triggers
    base_slug = re.sub(r'_(red|yellow|blue)$', '', slug)
    if base_slug != slug and base_slug in CARD_TRIGGERS:
        has_manual = True

    if has_manual:
        # Manual CARD_TRIGGERS entries take precedence — skip text parsing
        if slug in CARD_TRIGGERS:
            triggers.extend(CARD_TRIGGERS[slug])
        if base_slug != slug and base_slug in CARD_TRIGGERS:
            triggers.extend(CARD_TRIGGERS[base_slug])
    else:
        pass  # text_trigger_parser removed; DSL loader will handle these

    # Set source slug on all triggers
    for t in triggers:
        t.source_slug = slug

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


import engine.card_effects.triggers.card_triggers_extended  # noqa: F401 — registers all extended triggers on import
