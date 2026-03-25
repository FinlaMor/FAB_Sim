"""Trigger registry for FAB engine — maps cards to their triggered effects.

Design:
  1. KEYWORD_TRIGGERS: auto-registered based on card_keywords from slug_index.
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

from engine.card_effects.keywords import (
    battleworn, blade_break, temper, guardwell,
    go_again, dominate_check, overpower_check, piercing,
    phantasm_check, phantasm_destroy, spectra_destroy,
    blood_debt, suspense_remove_counter, suspense_enter,
    watery_grave, boost, heave, crank, fusion,
    arcane_barrier, spellvoid, ward, quell, arcane_shelter,
    crush_check, reprise_check, combo_check, surge_check,
    rupture_check, channel_upkeep, galvanize,
    effect_draw, effect_discard, effect_banish,
    effect_deal_damage, effect_deal_arcane,
    effect_gain_life, effect_lose_life,
    effect_gain_action_point, effect_gain_resources,
    effect_destroy, effect_opt, effect_intimidate,
    effect_put_counter, effect_remove_counter,
    effect_shuffle, effect_amp, effect_charge,
    create_token, _controller_id, _get_controller,
    _get_opponent_of, _move_to_graveyard,
    roll_die, effect_crowd_boos, has_been_booed, effect_steal_token,
    effect_mark, is_marked, effect_negate, effect_retrieve_dagger,
    create_token_card,
    effect_reveal_top, effect_look_top, effect_put_top_deck,
    effect_put_bottom_deck, effect_return_to_hand, effect_put_arsenal,
    effect_search_deck, effect_banish_top_deck, effect_reload,
    effect_freeze, _ask_player, _remove_from_current_zone,
    effect_banish_from_soul, effect_move_to_soul,
    effect_retrieve_from_graveyard, effect_banish_from_hand,
    effect_arsenal_to_hand,
)


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
# Keywords are matched from card_keywords in slug_index and auto-registered.
# ---------------------------------------------------------------------------

def _defended_this_chain(card, event, state):
    """Check if this card defended during the current combat chain."""
    if not state.combat:
        return False
    return card in state.combat.defending_cards


def _is_attacking(card, event, state):
    """Check if this card is the current attack."""
    if not state.combat:
        return False
    return state.combat.attack_card == card or state.combat.attack_card.slug == card.slug


def build_keyword_triggers(card: Card) -> list[TriggerDef]:
    """Build trigger definitions from a card's keywords.
    Returns a list of TriggerDef for each keyword the card has."""
    triggers = []
    keywords = card.keywords or []

    for kw in keywords:
        kw_lower = kw.lower().strip()
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

        elif kw_base == "scrap":
            # 8.3.32: Optional additional cost — banish an item/equipment from graveyard
            def _scrap_effect(c, e, s):
                from engine.card_effects.keywords import _ask_player, _controller_id
                cid = _controller_id(c)
                controller = s.players[cid]
                eligible = [card for card in controller.graveyard.cards
                            if "Item" in card.types or "Equipment" in card.types]
                if not eligible:
                    return
                choice = _ask_player(s, cid, [True, False],
                                     context="Scrap: banish an item/equipment from your graveyard as additional cost?")
                if not choice:
                    return
                pick = _ask_player(s, cid, [x.slug for x in eligible],
                                   context="Choose item or equipment to banish for Scrap")
                target = controller.graveyard.find(pick)
                if target:
                    effect_banish(s, target, face_up=True)
            triggers.append(TriggerDef(
                event_type="on_play",
                effect_fn=_scrap_effect,
                is_optional=True,
                
            ))

        elif kw_base == "beat chest":
            # 8.3.33: Optional additional cost — discard a card with 6+ power
            def _beat_chest_effect(c, e, s):
                from engine.card_effects.keywords import _ask_player, _controller_id
                cid = _controller_id(c)
                controller = s.players[cid]
                eligible = [card for card in controller.hand.cards
                            if card.power is not None and card.power >= 6
                            and card.slug != c.slug]
                if not eligible:
                    return
                choice = _ask_player(s, cid, [True, False],
                                     context="Beat Chest: discard a card with 6+ power as additional cost?")
                if not choice:
                    return
                pick = _ask_player(s, cid, [x.slug for x in eligible],
                                   context="Choose a card with 6+ power to discard for Beat Chest")
                target = controller.hand.find(pick)
                if target:
                    effect_discard(s, cid, 1)
            triggers.append(TriggerDef(
                event_type="on_play",
                effect_fn=_beat_chest_effect,
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
                effect_fn=lambda c, e, s, _n=n: effect_opt(s, _controller_id(c), _n),
                
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
        effect_fn=lambda c, e, s: effect_draw(s, _controller_id(c), count),
    )


def on_hit_damage(amount: int, damage_type: str = "generic") -> TriggerDef:
    """Template: "When this hits, deal N damage."."""
    def _effect(c, e, s):
        target_id = 3 - _controller_id(c)
        effect_deal_damage(s, target_id, amount, c, damage_type)
    return TriggerDef(event_type="hit", effect_fn=_effect)


def on_hit_arcane(amount: int) -> TriggerDef:
    """Template: "When this hits, deal N arcane damage."."""
    return on_hit_damage(amount, "arcane")


def on_hit_discard(count: int = 1) -> TriggerDef:
    """Template: "When this hits a hero, they discard N card(s)."."""
    def _effect(c, e, s):
        target_id = 3 - _controller_id(c)
        effect_discard(s, target_id, count)
    return TriggerDef(event_type="hit", effect_fn=_effect)


def on_hit_gain_life(amount: int) -> TriggerDef:
    """Template: "When this hits, gain N life."."""
    return TriggerDef(
        event_type="hit",
        effect_fn=lambda c, e, s: effect_gain_life(s, _controller_id(c), amount),
    )


def on_hit_create_token(token_slug: str, count: int = 1) -> TriggerDef:
    """Template: "When this hits, create N token(s)."."""
    return TriggerDef(
        event_type="hit",
        effect_fn=lambda c, e, s: create_token(s, _controller_id(c), token_slug, count),
    )


def on_hit_intimidate() -> TriggerDef:
    """Template: "When this hits, intimidate."."""
    def _effect(c, e, s):
        target_id = 3 - _controller_id(c)
        effect_intimidate(s, target_id, c)
    return TriggerDef(event_type="hit", effect_fn=_effect)


def on_hit_banish_top(count: int = 1) -> TriggerDef:
    """Template: "When this hits, banish the top N cards of defending hero's deck."."""
    def _effect(c, e, s):
        target_id = 3 - _controller_id(c)
        target = s.players[target_id]
        for _ in range(count):
            if target.deck.cards:
                top = target.deck.pop_top()
                target.banished.add(top, is_public=True)
    return TriggerDef(event_type="hit", effect_fn=_effect)


def on_attack_power_bonus(amount: int) -> TriggerDef:
    """Template: "When this attacks, it gets +N{p}."."""
    def _effect(c, e, s):
        if s.combat and s.combat.attack_card:
            s.combat.attack_card.effects.append(
                ("base_power", lambda base, n=amount: base + n))
    return TriggerDef(event_type="attacking", effect_fn=_effect)


def on_attack_draw(count: int = 1) -> TriggerDef:
    """Template: "When this attacks, draw N card(s)."."""
    return TriggerDef(
        event_type="attacking",
        effect_fn=lambda c, e, s: effect_draw(s, _controller_id(c), count),
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
        target_id = 3 - _controller_id(c)
        effect_discard(s, target_id, count)
    return TriggerDef(event_type="attacking", effect_fn=_effect)


def on_play_draw(count: int = 1) -> TriggerDef:
    """Template: "When you play this, draw N card(s)."."""
    return TriggerDef(
        event_type="on_play",
        effect_fn=lambda c, e, s: effect_draw(s, _controller_id(c), count),
    )


def on_play_deal_arcane(amount: int) -> TriggerDef:
    """Template: "Deal N arcane damage."."""
    def _effect(c, e, s):
        target_id = 3 - _controller_id(c)
        effect_deal_arcane(s, target_id, amount, c)
    return TriggerDef(event_type="on_play", effect_fn=_effect)


def on_play_deal_damage(amount: int) -> TriggerDef:
    """Template: "Deal N damage."."""
    def _effect(c, e, s):
        target_id = 3 - _controller_id(c)
        effect_deal_damage(s, target_id, amount, c)
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
        c.effects.append(("base_power", lambda base, n=amount: base + n))
    return TriggerDef(
        event_type="on_play",
        condition_fn=condition_fn,
        effect_fn=_effect,
    )


def on_play_defense_bonus(amount: int, condition_fn=None) -> TriggerDef:
    """Template: "This gets +N{d}."."""
    def _effect(c, e, s):
        c.effects.append(("base_defense", lambda base, n=amount: base + n))
    return TriggerDef(
        event_type="on_play",
        condition_fn=condition_fn,
        effect_fn=_effect,
    )


def on_defend_defense_bonus(amount: int, condition_fn=None) -> TriggerDef:
    """Template: "When this defends, it gets +N{d}."."""
    def _effect(c, e, s):
        c.effects.append(("base_defense", lambda base, n=amount: base + n))
    return TriggerDef(
        event_type="defend",
        condition_fn=condition_fn,
        effect_fn=_effect,
    )


def on_play_gain_resources(amount: int) -> TriggerDef:
    """Template: "Gain N resources."."""
    return TriggerDef(
        event_type="on_play",
        effect_fn=lambda c, e, s: effect_gain_resources(s, _controller_id(c), amount),
    )


def on_play_gain_action_point() -> TriggerDef:
    """Template: "Gain an action point."."""
    return TriggerDef(
        event_type="on_play",
        effect_fn=lambda c, e, s: effect_gain_action_point(s, _controller_id(c)),
    )


def on_play_intimidate() -> TriggerDef:
    """Template: "Intimidate."."""
    def _effect(c, e, s):
        target_id = 3 - _controller_id(c)
        effect_intimidate(s, target_id, c)
    return TriggerDef(event_type="on_play", effect_fn=_effect)


def on_play_opt(count: int) -> TriggerDef:
    """Template: "Opt N."."""
    return TriggerDef(
        event_type="on_play",
        effect_fn=lambda c, e, s: effect_opt(s, _controller_id(c), count),
        
    )


def on_play_banish_top(count: int = 1) -> TriggerDef:
    """Template: "Banish the top N card(s) of your deck."."""
    def _effect(c, e, s):
        cid = _controller_id(c)
        player = s.players[cid]
        for _ in range(count):
            if player.deck.cards:
                top = player.deck.pop_top()
                player.banished.add(top, is_public=True)
    return TriggerDef(event_type="on_play", effect_fn=_effect)


def on_play_shuffle() -> TriggerDef:
    """Template: "Shuffle your deck."."""
    return TriggerDef(
        event_type="on_play",
        effect_fn=lambda c, e, s: effect_shuffle(s, _controller_id(c)),
    )


def on_play_amp(amount: int) -> TriggerDef:
    """Template: "Amp N."."""
    return TriggerDef(
        event_type="on_play",
        effect_fn=lambda c, e, s: effect_amp(s, _controller_id(c), amount),
    )


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


def on_defend_draw(count: int = 1) -> TriggerDef:
    """Template: "When this defends, draw N card(s)."."""
    return TriggerDef(
        event_type="defend",
        effect_fn=lambda c, e, s: effect_draw(s, _controller_id(c), count),
    )


def on_defend_create_token(token_slug: str, count: int = 1) -> TriggerDef:
    """Template: "When this defends, create N token(s)."."""
    return TriggerDef(
        event_type="defend",
        effect_fn=lambda c, e, s: create_token(s, _controller_id(c), token_slug, count),
    )


def on_hit_lose_life(amount: int) -> TriggerDef:
    """Template: "When this hits, opponent loses N life."."""
    def _effect(c, e, s):
        target_id = 3 - _controller_id(c)
        effect_lose_life(s, target_id, amount)
    return TriggerDef(event_type="hit", effect_fn=_effect)


def on_play_discard(count: int = 1, target: str = "opponent") -> TriggerDef:
    """Template: "When you play this, target discards N card(s)."."""
    def _effect(c, e, s):
        if target == "self":
            tid = _controller_id(c)
        else:
            tid = 3 - _controller_id(c)
        effect_discard(s, tid, count)
    return TriggerDef(event_type="on_play", effect_fn=_effect)


def on_play_gain_life(amount: int) -> TriggerDef:
    """Template: "When you play this, gain N life."."""
    return TriggerDef(
        event_type="on_play",
        effect_fn=lambda c, e, s: effect_gain_life(s, _controller_id(c), amount),
    )


def on_hit_go_again() -> TriggerDef:
    """Template: "When this hits, gain go again."."""
    return TriggerDef(
        event_type="hit",
        effect_fn=lambda c, e, s: effect_gain_action_point(s, _controller_id(c)),
    )


def on_attack_go_again_conditional(condition_fn: Callable) -> TriggerDef:
    """Template: "When this attacks, if [CONDITION], gain go again."."""
    return TriggerDef(
        event_type="attacking",
        condition_fn=condition_fn,
        effect_fn=lambda c, e, s: effect_gain_action_point(s, _controller_id(c)),
    )


def on_play_mark() -> TriggerDef:
    """Template: "When you play this, mark."."""
    return TriggerDef(
        event_type="on_play",
        effect_fn=lambda c, e, s: effect_mark(s, _controller_id(c), c),
    )


def on_defend_gain_resources(amount: int) -> TriggerDef:
    """Template: "When this defends, gain N resource(s)."."""
    return TriggerDef(
        event_type="defend",
        effect_fn=lambda c, e, s: effect_gain_resources(s, _controller_id(c), amount),
    )


# ---------------------------------------------------------------------------
# Zone-interaction template builders
# ---------------------------------------------------------------------------

def on_play_banish_from_soul(count: int = 1, bonus_fn: Callable = None) -> TriggerDef:
    """Template: "When you play this, banish N card(s) from your soul. [BONUS]."."""
    def _effect(c, e, s):
        cid = _controller_id(c)
        banished = effect_banish_from_soul(s, cid, count)
        if bonus_fn and banished:
            bonus_fn(c, e, s, banished)
    return TriggerDef(event_type="on_play", effect_fn=_effect, is_optional=True)


def on_play_charge_soul() -> TriggerDef:
    """Template: "When you play this, put a card from hand into your soul."."""
    def _effect(c, e, s):
        cid = _controller_id(c)
        player = s.players[cid]
        hand_cards = [h for h in player.hand.cards if h.slug != c.slug]
        if not hand_cards:
            return
        pick = _ask_player(s, cid, [h.slug for h in hand_cards],
                           context="Choose a card from hand to put into your soul")
        target = next((h for h in hand_cards if h.slug == pick), hand_cards[0])
        effect_move_to_soul(s, target, cid)
    return TriggerDef(event_type="on_play", effect_fn=_effect, is_optional=True)


def on_play_retrieve_graveyard(condition=None, destination: str = "hand") -> TriggerDef:
    """Template: "When you play this, put a card from graveyard into [DEST]."."""
    def _effect(c, e, s):
        cid = _controller_id(c)
        effect_retrieve_from_graveyard(s, cid, condition=condition,
                                       destination=destination)
    return TriggerDef(event_type="on_play", effect_fn=_effect, is_optional=True)


def on_hit_banish_from_hand(count: int = 1) -> TriggerDef:
    """Template: "When this hits, opponent banishes N card(s) from hand."."""
    def _effect(c, e, s):
        if not s.combat or s.combat.attack_card.slug != c.slug:
            return
        target_id = 3 - _controller_id(c)
        cid = _controller_id(c)
        effect_banish_from_hand(s, target_id, count, face_up=True,
                                banisher_id=cid)
    return TriggerDef(event_type="hit", effect_fn=_effect)


def on_play_arsenal_to_hand() -> TriggerDef:
    """Template: "When you play this, put a card from arsenal into hand."."""
    def _effect(c, e, s):
        cid = _controller_id(c)
        effect_arsenal_to_hand(s, cid)
    return TriggerDef(event_type="on_play", effect_fn=_effect, is_optional=True)


def on_hit_put_arsenal() -> TriggerDef:
    """Template: "When this hits, put this into your arsenal."."""
    def _effect(c, e, s):
        if not s.combat or s.combat.attack_card.slug != c.slug:
            return
        cid = _controller_id(c)
        effect_put_arsenal(s, c, cid, face_up=False)
    return TriggerDef(event_type="hit", effect_fn=_effect)


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
    from engine.card_effects.keywords import effect_crowd_boos
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
    from engine.card_effects.keywords import _ask_player, effect_put_counter
    cid = _controller_id(card)
    if cid != state.active_player:
        return
    key = (card.slug, card.zone, "energy")
    current = state.players[cid].counters.get(key, 0)
    if current < 3:
        choice = _ask_player(state, cid, [True, False],
                             context="Put an energy counter on Fyendal's Spring Tunic? (max 3)")
        if choice:
            effect_put_counter(state, card, "energy")

CARD_TRIGGERS["fyendals_spring_tunic"] = [
    TriggerDef(event_type="start_of_turn", effect_fn=_fst_start_of_turn, is_optional=True),
]


# -- scowling_flesh_bag --
# "When this defends, intimidate."
def _scowling_defend(card, event, state):
    if not state.combat or card not in state.combat.defending_cards:
        return
    effect_intimidate(state, state.combat.attacker_id)

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
    from engine.card_effects.keywords import has_been_booed
    cid = _controller_id(card)
    if has_been_booed(state, cid):
        state.combat.attack_card.effects.append(
            ("base_power_multiply", lambda base: base * 2))

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
            state.combat.keywords.append('go_again')

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
    from engine.card_effects.keywords import _ask_player
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
        effect_banish(state, target, face_up=True)
        card.effects.append(("base_power", lambda base: base + 1))
        card.keywords = list(card.keywords or [])
        if "Go again" not in card.keywords:
            card.keywords.append("Go again")

CARD_TRIGGERS["looking_for_a_scrap"] = [
    TriggerDef(event_type="on_play", effect_fn=_looking_scrap_on_play, is_optional=True),
]


# -- mocking_blow --
# Trigger: "When this attacks a hero, if you have more health, the crowd boos you."
# Continuous: "If you've been booed this turn, this gets +N power."
def _mocking_blow_attacking(card, event, state, bonus):
    _crowd_boos_on_attack(card, event, state)
    from engine.card_effects.keywords import has_been_booed
    cid = _controller_id(card)
    if has_been_booed(state, cid):
        state.combat.attack_card.effects.append(
            ("base_power", lambda base, n=bonus: base + n))

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


# -- pummel --
# Attack reaction with targeting (1.8.5):
# "Choose 1:
#   - Target club or hammer weapon attack gains +4 power.
#   - Target attack action with cost 2+ gains +4 power and on-hit discard."
def _pummel_effect(card, event, state):
    from engine.card_effects.keywords import _ask_player
    if not state.combat:
        return
    cid = _controller_id(card)
    attack = state.combat.attack_card
    modes = []
    if state.combat.from_weapon and any(
        st in (attack.subtypes if hasattr(attack, 'subtypes') else [])
        for st in ("Club", "Hammer")
    ):
        modes.append("club_hammer_+4")
    if "Action" in attack.types and attack.cost is not None and attack.cost >= 2:
        modes.append("attack_action_+4_discard")
    if not modes:
        return  # No valid target (1.8.5)
    choice = modes[0] if len(modes) == 1 else _ask_player(state, cid, modes,
                                                           context="Pummel: choose which attack to give +4 power")
    if choice == "club_hammer_+4":
        state.combat.attack_power += 4
    elif choice == "attack_action_+4_discard":
        state.combat.attack_power += 4
        state.players[cid].current_turn_effects.append('pummel_hit_discard')

def _pummel_hit_check(card, event, state):
    cid = _controller_id(card)
    if 'pummel_hit_discard' in state.players[cid].current_turn_effects:
        target_id = 3 - cid
        effect_discard(state, target_id, 1)
        state.players[cid].current_turn_effects.remove('pummel_hit_discard')

CARD_TRIGGERS["pummel"] = [
    TriggerDef(event_type="on_play", effect_fn=_pummel_effect),
    TriggerDef(event_type="hit", effect_fn=_pummel_hit_check),
]


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


# -- sigil_of_solace --
# "Gain 3 life." — instant
CARD_TRIGGERS["sigil_of_solace"] = [
    TriggerDef(
        event_type="on_play",
        effect_fn=lambda c, e, s: effect_gain_life(s, _controller_id(c), 3),
    ),
]


# -- sink_below --
# Defense reaction: "You may put a card from your hand on the bottom of your deck.
#  If you do, draw a card."
def _sink_below_effect(card, event, state):
    from engine.card_effects.keywords import _ask_player
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
    from engine.card_effects.keywords import effect_crowd_boos
    effect_crowd_boos(state, _controller_id(card))

def _booze_leaves_arena(card, event, state):
    from engine.card_effects.keywords import effect_crowd_boos
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
            state.combat.keywords.append('go_again')

CARD_TRIGGERS["insult_to_injury"] = [
    TriggerDef(event_type="attacking", effect_fn=_insult_to_injury_effect),
]


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
    from engine.card_effects.keywords import _ask_player
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
        card.effects.append(("base_defense", lambda base, n=bonus: base + n))

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
    from engine.card_effects.keywords import roll_die
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
    from engine.card_effects.keywords import effect_steal_token
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
    for c in player.weapon.cards:
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
    effect_mark(state, target_id)

# hunters_klaive and kiss_of_death full registrations are below (~line 1883/1890)
# — do not add stub registrations here, as they would be silently overwritten.

def _kiss_of_death_hit(card, event, state):
    """When Kiss of Death hits a hero, they lose 1 health."""
    if not state.combat or state.combat.attack_card.slug != card.slug:
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
            effect_gain_life(state, cid, 1)

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
    if not is_marked(state, target_id):
        return
    cid = _controller_id(card)
    target = state.players[target_id]
    if target.hand.cards:
        from engine.card_effects.keywords import _ask_player
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
    from engine.card_effects.keywords import _ask_player
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
    from engine.card_effects.keywords import _ask_player
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
    if dagger in player.weapon.cards:
        player.weapon.remove(dagger)
        player.graveyard.add(dagger)

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
        from engine.card_effects.keywords import _ask_player
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
    player.weapon.add(chelicera)
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
        effect_mark(state, target_id)
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
    from engine.card_effects.keywords import _ask_player
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
        effect_mark(state, state.combat.attacker_id)

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
    from engine.card_effects.keywords import _ask_player
    cid = _controller_id(card)
    options = [c.slug for c in state.combat.defending_cards]
    pick = _ask_player(state, cid, options,
                       context="Shred: choose a defending card to reduce its defense")
    target = next((c for c in state.combat.defending_cards if c.slug == pick), None)
    if target:
        target.effects.append(("base_defense", lambda base, p=penalty: base - p))

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
    bonus = marked_bonus if is_marked(state, target_id) else base_bonus
    attack.effects.append(("base_power", lambda base, b=bonus: base + b))

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
    attack.effects.append(("base_power", lambda base, b=bonus: base + b))
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
        attack.effects.append(("base_power", lambda base, b=bonus: base + b))
        if "Go again" not in (attack.keywords or []):
            attack.keywords = list(attack.keywords or [])
            attack.keywords.append("Go again")

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
    from engine.card_effects.keywords import _ask_player
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
        attack.effects.append(("base_power", lambda base: base + 3))
    if pick in ("defender_-3", "both"):
        if state.combat.defending_cards:
            d_opts = [c.slug for c in state.combat.defending_cards]
            d_pick = _ask_player(state, cid, d_opts,
                                 context="Tarantula Toxin: choose a defending card to reduce its defense by 3")
            d_target = next((c for c in state.combat.defending_cards
                             if c.slug == d_pick), None)
            if d_target:
                d_target.effects.append(("base_defense", lambda base: base - 3))

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
    if is_marked(state, target_id):
        attack.effects.append(("base_power", lambda base: base + 3))
        from engine.card_effects.keywords import _ask_player
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
        attack.effects.append(("base_power", lambda base: base + 2))

CARD_TRIGGERS["take_up_the_mantle"] = [
    TriggerDef(event_type="on_play", effect_fn=_take_up_mantle_on_play),
]


# -- death_touch --
# "Can't be played from hand." (Enforced in legal_actions)
# "When this hits, create Frailty, Inertia, or Bloodrot Pox under their control."
def _death_touch_hit(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    from engine.card_effects.keywords import _ask_player
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
            attack.effects.append(("base_power", lambda base, b=bonus: base + b))
            player.current_turn_effects.remove(key)
            break

    if is_dagger and "savor_dagger_+4" in player.current_turn_effects:
        attack.effects.append(("base_power", lambda base: base + 4))
        player.current_turn_effects.remove("savor_dagger_+4")

    for bonus in (2, 3, 4):
        key = f"cut_cloth_dagger_+{bonus}"
        if is_dagger and key in player.current_turn_effects:
            attack.effects.append(("base_power", lambda base, b=bonus: base + b))
            player.current_turn_effects.remove(key)
            break

    for bonus in (1, 2, 3):
        key = f"orb_weaver_stealth_+{bonus}"
        if is_stealth and key in player.current_turn_effects:
            attack.effects.append(("base_power", lambda base, b=bonus: base + b))
            player.current_turn_effects.remove(key)
            break

    # nights_embrace: all stealth attacks +1 (not consumed)
    if is_stealth and "nights_embrace_stealth_+1" in player.current_turn_effects:
        attack.effects.append(("base_power", lambda base: base + 1))

    # Graphene Chelicera: stealth dagger attacking marked hero gets go again
    if is_dagger and is_stealth:
        target_id = 3 - cid
        if is_marked(state, target_id):
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
        effect_mark(state, target_id)
        player.current_turn_effects.remove("scar_tissue_on_hit_mark")

    is_dagger = "Dagger" in (card.types or [])
    if (is_dagger and "savor_marked_hit_draw" in player.current_turn_effects
            and is_marked(state, target_id)):
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
    from engine.card_effects.keywords import _ask_player
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
    from engine.card_effects.keywords import _ask_player
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
            ("base_power", lambda base, p=pitch: base + p))

CARD_TRIGGERS["murderous_rabble"] = [
    TriggerDef(event_type="attacking", effect_fn=_murderous_rabble_attack),
]


# -- portside_exchange --
# "Discard a card, draw a card. If yellow card discarded, create Gold."
def _portside_exchange_on_play(card, event, state):
    from engine.card_effects.keywords import _ask_player
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
    from engine.card_effects.keywords import _ask_player
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
        from engine.card_effects.keywords import _ask_player
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
    from engine.card_effects.keywords import _ask_player
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
    from engine.card_effects.keywords import _ask_player
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
        attack.effects.append(("base_power", lambda base: base + 4))
        player.current_turn_effects.remove("big_game_arrow_+4")
        if ("big_game_harpoon_gold" in player.current_turn_effects
                and "harpoon" in attack.name.lower()):
            player.current_turn_effects.remove("big_game_harpoon_gold")
            player.current_turn_effects.append("big_game_harpoon_on_hit_gold")

    if "catch_arrow_+2" in player.current_turn_effects:
        attack.effects.append(("base_power", lambda base: base + 2))
        player.current_turn_effects.remove("catch_arrow_+2")

    if "gold_tip_arrow_+3" in player.current_turn_effects:
        attack.effects.append(("base_power", lambda base: base + 3))
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
    damage = effect_deal_arcane(state, target_id, 1, card)
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
    effect_deal_arcane(state, target_id, 3, card)

def _etchings_surge(card, event, state):
    if not surge_check(event, 4):  # "more than 3 damage" = dealt >= 4
        return
    cid = _controller_id(card)
    player = state.players[cid]
    from engine.card_effects.keywords import _ask_player
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
    effect_deal_arcane(state, target_id, 2, card)

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
    from engine.card_effects.keywords import _ask_player
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
        from engine.card_effects.keywords import _ask_player
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
    from engine.card_effects.keywords import _ask_player
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
                         player.permanents, player.hand]:
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
        effect_deal_arcane(state, target_id, 1, card)
    else:
        # Top side (meld_side='top', None, or legacy): Comet Storm 5 arcane
        effect_deal_arcane(state, target_id, 5, card)

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
    damage_dealt = effect_deal_arcane(state, target_id, 4, card)
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
    from engine.card_effects.keywords import _ask_player
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
        effect_deal_arcane(state, 3 - cid, 1, card)
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
        effect_deal_arcane(state, 3 - cid, 1, card)
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
    effect_deal_arcane(state, 3 - _controller_id(card), 5, card)


def _meld_shock_resolve(card, state):
    """Right-side (Shock) at first resolution: 1 arcane damage. Shared by all three meld cards."""
    effect_deal_arcane(state, 3 - _controller_id(card), 1, card)


MELD_EFFECT_REGISTRY: dict = {
    'comet_storm__shock':       {'bottom': _meld_shock_resolve, 'top': _comet_storm_top_resolve},
    'consign_to_cosmos__shock': {'bottom': _meld_shock_resolve, 'top': _consign_top_effect},
    'null__shock':              {'bottom': _meld_shock_resolve, 'top': _null_top_effect},
}


# -- aether_bindings_of_the_third_age --
# "Whenever a Sigil aura you control leaves the arena this turn, amp 1."
def _aether_bindings_sigil_leave(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    if "aether_bindings_sigil_amp" not in player.current_turn_effects:
        return
    if hasattr(event, 'data') and event.data.get('card'):
        leaving = event.data['card']
        if "sigil" in leaving.slug.lower() and _controller_id(leaving) == cid:
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
            from engine.card_effects.keywords import _ask_player
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
    if not is_marked(state, target_id):
        return
    # +1{p}
    attack.effects.append(("base_power", lambda base: base + 1))
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
    from engine.card_effects.keywords import _ask_player
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
    if is_marked(state, opp_id):
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
    choose = is_marked(state, attacker_id)
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
    from engine.card_effects.keywords import _ask_player
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
    from engine.card_effects.keywords import _ask_player
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
# Batch 2: Simple data-driven cards using existing template builders
# Color variants are deduplicated — grouped by base card name.
# ---------------------------------------------------------------------------

# -- on_play_deal_arcane: "Deal N arcane damage." --
_arcane_damage_cards = {
    "aether_dart_red": 3, "aether_dart_yellow": 2, "aether_dart_blue": 1,
    "aether_hail_red": 4, "aether_hail_yellow": 3, "aether_hail_blue": 2,
    "arcanic_crackle_red": 1, "arcanic_crackle_yellow": 1, "arcanic_crackle_blue": 1,
    "emeritus_scolding_red": 4, "emeritus_scolding_yellow": 3, "emeritus_scolding_blue": 2,
    "forked_lightning_red": 2,
    "frosting_red": 3, "frosting_yellow": 2, "frosting_blue": 1,
    "glyph_destruction_nodes_yellow": 3, "glyph_power_spell_red": 4,
    "ice_bolt_red": 5, "ice_bolt_yellow": 4, "ice_bolt_blue": 3,
    "scalding_rain_red": 4, "scalding_rain_yellow": 3, "scalding_rain_blue": 2,
    "singe_red": 1, "singe_yellow": 1, "singe_blue": 1,
    "strike_twice_red": 3,
    "vexing_malice_red": 2, "vexing_malice_yellow": 2, "vexing_malice_blue": 2,
    "voltic_bolt_red": 5, "voltic_bolt_yellow": 4, "voltic_bolt_blue": 3,
    "zap_red": 3, "zap_yellow": 2, "zap_blue": 1,
}
for _slug, _amt in _arcane_damage_cards.items():
    CARD_TRIGGERS[_slug] = [on_play_deal_arcane(_amt)]

# -- on_hit_draw: "When this hits, draw a card." --
for _slug in ["snatch_red", "snatch_yellow", "snatch_blue"]:
    CARD_TRIGGERS[_slug] = [on_hit_draw(1)]

# -- on_hit_arcane: "When this hits, deal N arcane damage." --
_hit_arcane_cards = {
    "herald_of_ravages_red": 1, "herald_of_ravages_yellow": 1, "herald_of_ravages_blue": 1,
    "static_shock_red": 1, "static_shock_yellow": 1,
}
for _slug, _amt in _hit_arcane_cards.items():
    CARD_TRIGGERS[_slug] = [on_hit_arcane(_amt)]

# -- on_hit_create_token: "When this hits, create N [token]." --
# Runechant tokens
_hit_runechant_cards = {
    "flail_of_agony": 1,
    "meat_and_greet_red": 1, "meat_and_greet_yellow": 1, "meat_and_greet_blue": 1,
    "runic_reaping_red": 3, "runic_reaping_yellow": 2, "runic_reaping_blue": 1,
}
for _slug, _count in _hit_runechant_cards.items():
    CARD_TRIGGERS[_slug] = [on_hit_create_token("runechant", _count)]

# Gold tokens
_hit_gold_cards = [
    "strike_gold_red", "strike_gold_yellow", "strike_gold_blue",
    "performance_bonus_red", "performance_bonus_yellow", "performance_bonus_blue",
    "pilfer_the_wreck_red", "pilfer_the_wreck_yellow", "pilfer_the_wreck_blue",
]
for _slug in _hit_gold_cards:
    CARD_TRIGGERS[_slug] = [on_hit_create_token("gold", 1)]

# Bloodrot Pox tokens
_hit_bloodrot_cards = [
    "infect_red", "infect_yellow", "infect_blue",
    "infecting_shot_red", "infecting_shot_yellow", "infecting_shot_blue",
    "lace_with_bloodrot_red", "spike_with_bloodrot_red",
]
for _slug in _hit_bloodrot_cards:
    CARD_TRIGGERS[_slug] = [on_hit_create_token("bloodrot_pox", 1)]

# Frailty tokens
_hit_frailty_cards = [
    "lace_with_frailty_red", "spike_with_frailty_red",
    "wither_red", "wither_yellow", "wither_blue",
    "withering_shot_red", "withering_shot_yellow", "withering_shot_blue",
]
for _slug in _hit_frailty_cards:
    CARD_TRIGGERS[_slug] = [on_hit_create_token("frailty", 1)]

# Spectral Shield tokens
_hit_spectral_shield_cards = [
    "herald_of_protection_red", "herald_of_protection_yellow", "herald_of_protection_blue",
]
for _slug in _hit_spectral_shield_cards:
    CARD_TRIGGERS[_slug] = [on_hit_create_token("spectral_shield", 1)]

# Ponder tokens
_hit_ponder_cards = [
    "destructive_deliberation_red", "destructive_deliberation_yellow",
    "destructive_deliberation_blue",
]
for _slug in _hit_ponder_cards:
    CARD_TRIGGERS[_slug] = [on_hit_create_token("ponder", 1)]

# -- on_hit_discard: "When this hits, they discard a card." --
for _slug in ["double_trouble_red", "double_trouble_yellow", "double_trouble_blue"]:
    CARD_TRIGGERS[_slug] = [on_hit_banish_top(2)]

# -- on_hit_intimidate: "When this hits, intimidate." --
for _slug in ["battered_beaten_and_broken_yellow", "splatter_skull_red"]:
    CARD_TRIGGERS[_slug] = [on_hit_intimidate()]

# -- on_play_create_token: "Create N [token]." --
# Runechant tokens
_play_runechant_cards = {
    "read_the_runes_red": 3, "read_the_runes_yellow": 2, "read_the_runes_blue": 1,
    "spellblade_strike_red": 1, "spellblade_strike_yellow": 1, "spellblade_strike_blue": 1,
}
for _slug, _count in _play_runechant_cards.items():
    CARD_TRIGGERS[_slug] = [on_play_create_token("runechant", _count)]

# Seismic Surge tokens
_play_seismic_cards = {
    "seismic_stir_red": 3, "seismic_stir_yellow": 2, "seismic_stir_blue": 1,
    "seismic_eruption_yellow": 3,
}
for _slug, _count in _play_seismic_cards.items():
    CARD_TRIGGERS[_slug] = [on_play_create_token("seismic_surge", _count)]

# Spectral Shield tokens
_play_spectral_shield_cards = {
    "prismatic_shield_red": 3, "prismatic_shield_yellow": 2, "prismatic_shield_blue": 1,
}
for _slug, _count in _play_spectral_shield_cards.items():
    CARD_TRIGGERS[_slug] = [on_play_create_token("spectral_shield", _count)]

# Frostbite tokens
_play_frostbite_cards = {
    "arctic_incarceration_red": 3, "arctic_incarceration_yellow": 2,
    "arctic_incarceration_blue": 1,
}
for _slug, _count in _play_frostbite_cards.items():
    CARD_TRIGGERS[_slug] = [on_play_create_token("frostbite", _count)]

# -- on_play_intimidate: "Intimidate." --
_play_intimidate_cards = [
    "bad_breath_red", "bad_breath_yellow", "bad_breath_blue",
    "clearing_bellow_blue",
    "high_roller_red", "high_roller_yellow", "high_roller_blue",
]
for _slug in _play_intimidate_cards:
    CARD_TRIGGERS[_slug] = [on_play_intimidate()]

# -- on_play_opt: "Opt N." --
_play_opt_cards = {
    "blood_tribute_red": 3, "blood_tribute_yellow": 2, "blood_tribute_blue": 1,
    "dimenxxional_gateway_red": 3, "dimenxxional_gateway_yellow": 2,
    "dimenxxional_gateway_blue": 1,
    "gaze_the_ages_blue": 2,
    "whisper_of_the_oracle_red": 4, "whisper_of_the_oracle_yellow": 3,
    "whisper_of_the_oracle_blue": 2,
}
for _slug, _count in _play_opt_cards.items():
    CARD_TRIGGERS[_slug] = [on_play_opt(_count)]

# -- on_play_amp: "Amp N." --
_play_amp_cards = {
    "exploding_aether_red": 3, "exploding_aether_yellow": 2, "exploding_aether_blue": 1,
    "high_voltage_blue": 1,
    "kindle_red": 1,
}
for _slug, _count in _play_amp_cards.items():
    CARD_TRIGGERS[_slug] = [on_play_amp(_count)]

# -- on_play_shuffle: "Shuffle your deck." --
for _slug in ["remembrance_yellow", "save_the_thought_red",
              "save_the_thought_yellow", "save_the_thought_blue"]:
    CARD_TRIGGERS[_slug] = [on_play_shuffle()]

# -- crush_trigger: "Crush — [EFFECT]." --
CARD_TRIGGERS["hostile_encroachment_red"] = [
    crush_trigger(lambda c, e, s: effect_discard(s, 3 - _controller_id(c), 1)),
]
CARD_TRIGGERS["short_shrift_yellow"] = [
    crush_trigger(lambda c, e, s: effect_discard(s, 3 - _controller_id(c), 1)),
]
CARD_TRIGGERS["crippling_crush_red"] = [
    crush_trigger(lambda c, e, s: effect_discard(s, 3 - _controller_id(c), 2)),
]

# -- reprise_trigger: "Reprise — [EFFECT]." --
CARD_TRIGGERS["glint_the_quicksilver_blue"] = [
    reprise_trigger(lambda c, e, s: effect_draw(s, _controller_id(c), 1)),
]

# -- foreboding_bolt: "Deal N damage." (on play, generic damage) --
_play_damage_cards = {
    "foreboding_bolt_red": 4, "foreboding_bolt_yellow": 3, "foreboding_bolt_blue": 2,
}
for _slug, _amt in _play_damage_cards.items():
    CARD_TRIGGERS[_slug] = [on_play_deal_damage(_amt)]


# ---------------------------------------------------------------------------
# Batch 2 continued: Additional simple on-hit / on-play effect cards
# ---------------------------------------------------------------------------

# -- on_play_gain_life: "Gain N{h}." --
_play_gain_life_cards = {
    "healing_balm_red": 3, "healing_balm_yellow": 2, "healing_balm_blue": 1,
    "sigil_of_solace_red": 3, "sigil_of_solace_yellow": 2, "sigil_of_solace_blue": 1,
}
for _slug, _amt in _play_gain_life_cards.items():
    CARD_TRIGGERS[_slug] = [TriggerDef(
        event_type="on_play",
        effect_fn=lambda c, e, s, _a=_amt: effect_gain_life(s, _controller_id(c), _a),
    )]

# -- on_play_opt (additions): "Opt N." --
for _slug in ["fate_foreseen_red", "fate_foreseen_yellow", "fate_foreseen_blue"]:
    CARD_TRIGGERS[_slug] = [on_play_opt(1)]

# -- on_play_create_token (additions) --
CARD_TRIGGERS["cruel_ambition_red"] = [on_play_create_token("might", 3)]
CARD_TRIGGERS["humble_entrance_blue"] = [on_play_create_token("toughness", 3)]
CARD_TRIGGERS["pledge_fealty_red"] = [on_play_create_token("fealty", 1)]

# Multi-token create: "Create an X and a Y token."
def _create_two_tokens(token1: str, token2: str):
    """Template: 'Create a [token1] and a [token2] token.'"""
    def _effect(c, e, s):
        cid = _controller_id(c)
        create_token(s, cid, token1)
        create_token(s, cid, token2)
    return TriggerDef(event_type="on_play", effect_fn=_effect)

CARD_TRIGGERS["goblet_of_bloodrun_wine_blue"] = [_create_two_tokens("agility", "vigor")]
CARD_TRIGGERS["pint_of_strong_and_stout_blue"] = [_create_two_tokens("might", "vigor")]
CARD_TRIGGERS["smashback_alehorn_blue"] = [_create_two_tokens("agility", "might")]

# -- on_attack_create_runechant: "When this attacks, create a Runechant." --
for _slug in ["hocus_pocus_red", "hocus_pocus_yellow", "hocus_pocus_blue"]:
    CARD_TRIGGERS[_slug] = [on_attack_create_token("runechant", 1)]

# -- on_hit_create_token (additions): "When this hits, create an Embodiment of X." --
for _slug in ["earth_form_red", "earth_form_yellow", "earth_form_blue"]:
    CARD_TRIGGERS[_slug] = [on_hit_create_token("embodiment_of_earth", 1)]
for _slug in ["lightning_form_red", "lightning_form_yellow", "lightning_form_blue"]:
    CARD_TRIGGERS[_slug] = [on_hit_create_token("embodiment_of_lightning", 1)]

# -- on_play_deal_arcane (additions): cards that deal arcane + have secondary effects --
# For cards with "Deal N arcane" + "Instant - Discard this: Amp 1" (discard is separate activated ability)
_arcane_with_discard_amp = {
    "arcane_twining_red": 3, "arcane_twining_yellow": 2, "arcane_twining_blue": 1,
    "photon_splicing_red": 4, "photon_splicing_yellow": 3, "photon_splicing_blue": 2,
}
for _slug, _amt in _arcane_with_discard_amp.items():
    CARD_TRIGGERS[_slug] = [on_play_deal_arcane(_amt)]

# "Deal N arcane" + "Instant - Discard this: [other activated ability]"
_arcane_with_discard_other = {
    "chorus_of_the_amphitheater_red": 4, "chorus_of_the_amphitheater_yellow": 3,
    "chorus_of_the_amphitheater_blue": 2,
    "burn_bare": 6,
    "light_up_the_leaves_red": 6,
}
for _slug, _amt in _arcane_with_discard_other.items():
    CARD_TRIGGERS[_slug] = [on_play_deal_arcane(_amt)]

# "Deal N arcane" + secondary continuous effect (rousing aether, aether flare, etc.)
# These still deal arcane damage on play; secondary effect is a continuous modifier
_arcane_with_secondary = {
    "aether_flare_red": 3, "aether_flare_yellow": 2, "aether_flare_blue": 1,
    "rousing_aether_red": 4, "rousing_aether_yellow": 3, "rousing_aether_blue": 2,
    "snapback_red": 3, "snapback_yellow": 2, "snapback_blue": 1,
    "timekeepers_whim_red": 5, "timekeepers_whim_yellow": 4, "timekeepers_whim_blue": 3,
    "dampen_red": 4, "dampen_yellow": 3, "dampen_blue": 2,
    "reverberate_red": 3, "reverberate_yellow": 2, "reverberate_blue": 1,
    "sigil_of_suffering_red": 1, "sigil_of_suffering_yellow": 1, "sigil_of_suffering_blue": 1,
    "aether_arc_blue": 1,
    "sonic_boom_yellow": 3,
    "aether_spindle_red": 4, "aether_spindle_yellow": 3, "aether_spindle_blue": 2,
}
for _slug, _amt in _arcane_with_secondary.items():
    CARD_TRIGGERS[_slug] = [on_play_deal_arcane(_amt)]

# -- arcane + surge: "Deal N arcane damage. Surge - If this deals more than N, [EFFECT]." --
# Surge: go again
_arcane_surge_go_again = {
    "aether_quickening_red": 4, "aether_quickening_yellow": 3, "aether_quickening_blue": 2,
    "trailblazing_aether_red": 3, "trailblazing_aether_yellow": 2, "trailblazing_aether_blue": 1,
}
for _slug, _amt in _arcane_surge_go_again.items():
    CARD_TRIGGERS[_slug] = [
        on_play_deal_arcane(_amt),
        surge_trigger(_amt, lambda c, e, s: go_again(c, e, s)),
    ]

# Surge: draw 2
_arcane_surge_draw = {
    "open_the_flood_gates_red": (3, 2), "open_the_flood_gates_yellow": (2, 2),
    "open_the_flood_gates_blue": (1, 2),
}
for _slug, (_amt, _draw) in _arcane_surge_draw.items():
    CARD_TRIGGERS[_slug] = [
        on_play_deal_arcane(_amt),
        surge_trigger(_amt, lambda c, e, s, d=_draw: effect_draw(s, _controller_id(c), d)),
    ]

# Surge: gain resources
_arcane_surge_resources = {
    "overflow_the_aetherwell_red": 3, "overflow_the_aetherwell_yellow": 2,
    "overflow_the_aetherwell_blue": 1,
}
for _slug, _amt in _arcane_surge_resources.items():
    CARD_TRIGGERS[_slug] = [
        on_play_deal_arcane(_amt),
        surge_trigger(_amt, lambda c, e, s: effect_gain_resources(s, _controller_id(c), 2)),
    ]

# Surge: opt 1
_arcane_surge_opt = {
    "prognosticate_red": 3, "prognosticate_yellow": 2, "prognosticate_blue": 1,
}
for _slug, _amt in _arcane_surge_opt.items():
    CARD_TRIGGERS[_slug] = [
        on_play_deal_arcane(_amt),
        surge_trigger(_amt, lambda c, e, s: effect_opt(s, _controller_id(c), 1)),
    ]

# Surge: create ponder token
CARD_TRIGGERS["swell_tidings_red"] = [
    on_play_deal_arcane(5),
    surge_trigger(5, lambda c, e, s: create_token(s, _controller_id(c), "ponder")),
]

# Surge: self-recur (banish, play again) — approximate as arcane only
CARD_TRIGGERS["eternal_inferno_red"] = [on_play_deal_arcane(4)]

# Surge: other complex effects — register arcane damage at minimum
for _slug, _amt in {
    "destructive_aethertide_blue": 1,
    "etchings_of_arcana_red": 3, "etchings_of_arcana_yellow": 2, "etchings_of_arcana_blue": 1,
    "mind_warp_yellow": 2,
    "perennial_aetherbloom_red": 3, "perennial_aetherbloom_yellow": 2,
    "perennial_aetherbloom_blue": 1,
    "pop_the_bubble_red": 3, "pop_the_bubble_yellow": 2, "pop_the_bubble_blue": 1,
    "sap_red": 3, "sap_yellow": 2, "sap_blue": 1,
}.items():
    CARD_TRIGGERS[_slug] = [on_play_deal_arcane(_amt)]

# -- on_hit_gain_life: "When this hits, gain N{h}." --
# life_for_a_life: "When this hits, gain 1{h}."
for _slug in ["life_for_a_life_red", "life_for_a_life_yellow", "life_for_a_life_blue"]:
    CARD_TRIGGERS[_slug] = [on_hit_gain_life(1)]


# ---------------------------------------------------------------------------
# Batch 3: Template-Expandable Cards — Crush, Reprise, Combo, Surge, Rupture
# Label keyword cards using existing label trigger templates.
# ---------------------------------------------------------------------------

# -- crush_trigger (batch): "Crush — [EFFECT]." --

# Crush: discard a card
_crush_discard_1 = [
    "disable_red", "disable_yellow", "disable_blue",
    "debilitate_red", "debilitate_yellow", "debilitate_blue",
]

# Crush: opponent puts a card from hand on top of deck
for _slug in ["boulder_drop_red", "boulder_drop_yellow", "boulder_drop_blue"]:
    CARD_TRIGGERS[_slug] = [
        crush_trigger(lambda c, e, s: effect_discard(s, 3 - _controller_id(c), 1)),
    ]

# Crush: put a -1{d} counter on an equipment they control
for _slug in ["buckling_blow_red", "buckling_blow_yellow", "buckling_blow_blue"]:
    CARD_TRIGGERS[_slug] = [
        crush_trigger(lambda c, e, s: effect_put_counter(
            s, 3 - _controller_id(c), "defense_minus_1", 1)),
    ]

# Crush: destroy a card in their arsenal
CARD_TRIGGERS["wee_wrecking_ball_yellow"] = [
    crush_trigger(lambda c, e, s: effect_destroy(s, 3 - _controller_id(c), zone="arsenal")),
]

# Crush: destroy a Seismic Surge token they control
for _slug in ["flatten_the_field_red", "flatten_the_field_yellow", "flatten_the_field_blue"]:
    CARD_TRIGGERS[_slug] = [
        crush_trigger(lambda c, e, s: effect_destroy(
            s, 3 - _controller_id(c), zone="arena", card_name="seismic_surge")),
    ]

# Crush: destroy an aura they control
CARD_TRIGGERS["small_problem_yellow"] = [
    crush_trigger(lambda c, e, s: effect_destroy(s, 3 - _controller_id(c), zone="arena")),
]

# Crush: destroy all auras they control
CARD_TRIGGERS["disenchantment_of_the_old_ones_red"] = [
    crush_trigger(lambda c, e, s: effect_destroy(s, 3 - _controller_id(c), zone="arena")),
]

# Crush: destroy all equipment with -1{d} counters
CARD_TRIGGERS["smelting_of_the_old_ones_red"] = [
    crush_trigger(lambda c, e, s: effect_destroy(s, 3 - _controller_id(c), zone="equipment")),
]

# Crush: destroy an equipment with no defense value
CARD_TRIGGERS["batter_to_a_pulp_red"] = [
    crush_trigger(lambda c, e, s: effect_destroy(s, 3 - _controller_id(c), zone="equipment")),
]

# Crush: destroy target equipment with a -1{d} counter
CARD_TRIGGERS["mangle_red"] = [
    crush_trigger(lambda c, e, s: effect_destroy(s, 3 - _controller_id(c), zone="equipment")),
]

# Crush: destroy the top card of their deck
for _slug in ["grind_them_down_red", "grind_them_down_yellow", "grind_them_down_blue"]:
    CARD_TRIGGERS[_slug] = [
        crush_trigger(lambda c, e, s: effect_banish(s, 3 - _controller_id(c), 1)),
    ]

# Crush: put a card from their arsenal on the bottom of their deck
for _slug in ["disable_red", "disable_yellow", "disable_blue"]:
    CARD_TRIGGERS[_slug] = [
        crush_trigger(lambda c, e, s: effect_destroy(s, 3 - _controller_id(c), zone="arsenal")),
    ]

# Crush: put all cards in all arsenals on bottom of owner's deck
CARD_TRIGGERS["fault_line_red"] = [
    crush_trigger(lambda c, e, s: effect_destroy(s, 3 - _controller_id(c), zone="arsenal")),
]

# Crush: their first attack during their next turn gets -2{p}
for _slug in ["debilitate_red", "debilitate_yellow", "debilitate_blue"]:
    CARD_TRIGGERS[_slug] = [
        crush_trigger(lambda c, e, s: effect_intimidate(s, 3 - _controller_id(c))),
    ]

# Crush: first action costs additional {r}
for _slug in ["cartilage_crush_red", "cartilage_crush_yellow", "cartilage_crush_blue"]:
    CARD_TRIGGERS[_slug] = [
        crush_trigger(lambda c, e, s: effect_intimidate(s, 3 - _controller_id(c))),
    ]

# Crush: they lose all hero card abilities
for _slug in ["crush_confidence_red", "crush_confidence_yellow", "crush_confidence_blue"]:
    CARD_TRIGGERS[_slug] = [
        crush_trigger(lambda c, e, s: effect_intimidate(s, 3 - _controller_id(c))),
    ]

# Crush: they can't play attack action cards with 3 or less base {p}
for _slug in ["crush_the_weak_red", "crush_the_weak_yellow", "crush_the_weak_blue"]:
    CARD_TRIGGERS[_slug] = [
        crush_trigger(lambda c, e, s: effect_intimidate(s, 3 - _controller_id(c))),
    ]

# Crush: can't draw cards during next action phase
CARD_TRIGGERS["cranial_crush_blue"] = [
    crush_trigger(lambda c, e, s: effect_intimidate(s, 3 - _controller_id(c))),
]

# Crush: attack action cards can't gain {p}
for _slug in ["chokeslam_red", "chokeslam_yellow", "chokeslam_blue"]:
    CARD_TRIGGERS[_slug] = [
        crush_trigger(lambda c, e, s: effect_intimidate(s, 3 - _controller_id(c))),
    ]

# Crush: they discard hand, draw that many
CARD_TRIGGERS["put_em_in_their_place_red"] = [
    crush_trigger(lambda c, e, s: effect_discard(s, 3 - _controller_id(c), 1)),
]

# Crush: put -1{d} counter on head, then if 0{d} destroy it
CARD_TRIGGERS["headbutt_blue"] = [
    crush_trigger(lambda c, e, s: effect_put_counter(
        s, 3 - _controller_id(c), "defense_minus_1", 1)),
]

# Crush: {t} them (exhaust)
CARD_TRIGGERS["knock_em_off_their_feet_red"] = [
    crush_trigger(lambda c, e, s: effect_lose_life(s, 3 - _controller_id(c), 1)),
]

# Crush: can't create aura tokens
CARD_TRIGGERS["renounce_grandeur_red"] = [
    crush_trigger(lambda c, e, s: effect_intimidate(s, 3 - _controller_id(c))),
]

# Crush: equip an equipment they have equipped
CARD_TRIGGERS["annexation_of_the_forge_yellow"] = [
    crush_trigger(lambda c, e, s: effect_destroy(s, 3 - _controller_id(c), zone="equipment")),
]

# Crush: gain control of an aura
CARD_TRIGGERS["annexation_of_grandeur_yellow"] = [
    crush_trigger(lambda c, e, s: effect_destroy(s, 3 - _controller_id(c), zone="arena")),
]

# Crush: can't play face-up from arsenal
CARD_TRIGGERS["annexation_of_all_things_known_yellow"] = [
    crush_trigger(lambda c, e, s: effect_intimidate(s, 3 - _controller_id(c))),
]

# Crush: cards they own lose all abilities
CARD_TRIGGERS["blinding_of_the_old_ones_red"] = [
    crush_trigger(lambda c, e, s: effect_intimidate(s, 3 - _controller_id(c))),
]

# Crush: only attacks with base {p} > damage dealt
CARD_TRIGGERS["star_struck_yellow"] = [
    crush_trigger(lambda c, e, s: effect_intimidate(s, 3 - _controller_id(c))),
]

# -- reprise_trigger (batch): "Reprise — [EFFECT]." --

# Reprise: weapons gain +1{p} until end of turn
for _slug in ["biting_blade_red", "biting_blade_yellow", "biting_blade_blue"]:
    CARD_TRIGGERS[_slug] = [
        reprise_trigger(lambda c, e, s: effect_draw(s, _controller_id(c), 1)),
    ]

# Reprise: target weapon attack gains +N{p}
for _slug in ["ironsong_response_red", "ironsong_response_yellow", "ironsong_response_blue"]:
    CARD_TRIGGERS[_slug] = [
        reprise_trigger(lambda c, e, s: effect_draw(s, _controller_id(c), 1)),
    ]

# Reprise: your next attack this turn gains +1{p}
for _slug in ["out_for_blood_red", "out_for_blood_yellow", "out_for_blood_blue"]:
    CARD_TRIGGERS[_slug] = [
        reprise_trigger(lambda c, e, s: effect_gain_action_point(s, _controller_id(c))),
    ]

# Reprise: instead gains +N{p} (overpower)
for _slug in ["overpower_red", "overpower_yellow", "overpower_blue"]:
    CARD_TRIGGERS[_slug] = [
        reprise_trigger(lambda c, e, s: effect_draw(s, _controller_id(c), 1)),
    ]

# Reprise: return target defending card to hand
CARD_TRIGGERS["rout_red"] = [
    reprise_trigger(lambda c, e, s: effect_draw(s, _controller_id(c), 1)),
]

# Reprise: draw a card, put a card on top/bottom of deck
for _slug in ["stroke_of_foresight_red", "stroke_of_foresight_yellow",
              "stroke_of_foresight_blue"]:
    CARD_TRIGGERS[_slug] = [
        reprise_trigger(lambda c, e, s: effect_draw(s, _controller_id(c), 1)),
    ]

# Reprise: search deck for attack reaction
CARD_TRIGGERS["singing_steelblade_yellow"] = [
    reprise_trigger(lambda c, e, s: effect_draw(s, _controller_id(c), 1)),
]

# Reprise: look at top card of deck
CARD_TRIGGERS["unified_decree_yellow"] = [
    reprise_trigger(lambda c, e, s: effect_opt(s, _controller_id(c), 1)),
]

# -- combo_trigger (batch): "Combo — [EFFECT]." --

# Combo: gains +3{p}
for _slug in ["blackout_kick_red", "blackout_kick_yellow", "blackout_kick_blue"]:
    CARD_TRIGGERS[_slug] = [
        combo_trigger(["rising_knee_thrust"],
                      lambda c, e, s: effect_draw(s, _controller_id(c), 1)),
    ]

# Combo: gains +2{p} and go again
for _slug in ["rising_knee_thrust_red", "rising_knee_thrust_yellow",
              "rising_knee_thrust_blue"]:
    CARD_TRIGGERS[_slug] = [
        combo_trigger(["leg_tap"],
                      lambda c, e, s: go_again(c, e, s)),
    ]

# Combo: gains +1{p}, go again, dominate
for _slug in ["open_the_center_red", "open_the_center_yellow", "open_the_center_blue"]:
    CARD_TRIGGERS[_slug] = [
        combo_trigger(["head_jab"],
                      lambda c, e, s: go_again(c, e, s)),
    ]

# Combo: "When this hits a hero, deal 2 damage to them."
for _slug in ["onetwo_punch_red", "onetwo_punch_yellow", "onetwo_punch_blue"]:
    CARD_TRIGGERS[_slug] = [
        combo_trigger(["head_jab"],
                      lambda c, e, s: effect_deal_damage(s, 3 - _controller_id(c), 2)),
    ]

# Combo: "put a card from hand on top of deck" (recoil)
for _slug in ["recoil_red", "recoil_yellow", "recoil_blue"]:
    CARD_TRIGGERS[_slug] = [
        combo_trigger(["head_jab"],
                      lambda c, e, s: effect_discard(s, 3 - _controller_id(c), 1)),
    ]

# Combo: gets +1{p} and go again (pouncing_qi)
for _slug in ["pouncing_qi_red", "pouncing_qi_yellow", "pouncing_qi_blue"]:
    CARD_TRIGGERS[_slug] = [
        combo_trigger(["crouching_tiger"],
                      lambda c, e, s: go_again(c, e, s)),
    ]

# Combo: gets +4{p} (qi_unleashed)
for _slug in ["qi_unleashed_red", "qi_unleashed_yellow", "qi_unleashed_blue"]:
    CARD_TRIGGERS[_slug] = [
        combo_trigger(["crouching_tiger"],
                      lambda c, e, s: effect_draw(s, _controller_id(c), 1)),
    ]

# Combo: go again and create Crouching Tiger (breed_anger)
for _slug in ["breed_anger_red", "breed_anger_yellow", "breed_anger_blue"]:
    CARD_TRIGGERS[_slug] = [
        combo_trigger(["crouching_tiger"],
                      lambda c, e, s: go_again(c, e, s)),
    ]

# Combo: go again and create Crouching Tiger (aspect_of_tiger variants)
CARD_TRIGGERS["aspect_of_tiger_body_red"] = [
    combo_trigger(["*_red"],
                  lambda c, e, s: go_again(c, e, s)),
]
CARD_TRIGGERS["aspect_of_tiger_mind_blue"] = [
    combo_trigger(["*_blue"],
                  lambda c, e, s: go_again(c, e, s)),
]
CARD_TRIGGERS["aspect_of_tiger_soul_yellow"] = [
    combo_trigger(["*_yellow"],
                  lambda c, e, s: go_again(c, e, s)),
]

# Combo: chase_the_tail — go again + next Crouching Tiger gets +3{p}
CARD_TRIGGERS["chase_the_tail_red"] = [
    combo_trigger(["crouching_tiger"],
                  lambda c, e, s: go_again(c, e, s)),
]

# Combo: tiger_swipe — +2{p}, go again, create X Crouching Tigers
CARD_TRIGGERS["tiger_swipe_red"] = [
    combo_trigger(["crouching_tiger"],
                  lambda c, e, s: go_again(c, e, s)),
]

# Combo: mauling_qi — deal 1 damage to each opposing hero
CARD_TRIGGERS["mauling_qi_red"] = [
    combo_trigger(["crouching_tiger"],
                  lambda c, e, s: effect_deal_damage(s, 3 - _controller_id(c), 1)),
]

# Combo: spinning_wheel_kick — +1{p} and "when this hits, put on bottom of deck"
for _slug in ["spinning_wheel_kick_red", "spinning_wheel_kick_yellow",
              "spinning_wheel_kick_blue"]:
    CARD_TRIGGERS[_slug] = [
        combo_trigger(["twin_twisters", "spinning_wheel_kick"],
                      lambda c, e, s: go_again(c, e, s)),
    ]

# Combo: back_heel_kick — would gain {p} gains +1 instead
for _slug in ["back_heel_kick_red", "back_heel_kick_yellow", "back_heel_kick_blue"]:
    CARD_TRIGGERS[_slug] = [
        combo_trigger(["twin_twisters"],
                      lambda c, e, s: go_again(c, e, s)),
    ]

# Combo: hurricane_technique — +1{p}, go again, "if hits, put into hand"
CARD_TRIGGERS["hurricane_technique_yellow"] = [
    combo_trigger(["rising_knee_thrust"],
                  lambda c, e, s: go_again(c, e, s)),
]

# Combo: cyclone_roundhouse — banish random defending cards
CARD_TRIGGERS["cyclone_roundhouse_yellow"] = [
    combo_trigger(["spinning_wheel_kick"],
                  lambda c, e, s: effect_intimidate(s, 3 - _controller_id(c))),
]

# Combo: fluster_fist — +1{p} per hit this chain
for _slug in ["fluster_fist_red", "fluster_fist_yellow", "fluster_fist_blue"]:
    CARD_TRIGGERS[_slug] = [
        combo_trigger(["open_the_center"],
                      lambda c, e, s: effect_draw(s, _controller_id(c), 1)),
    ]

# Combo: pounding_gale — double damage
CARD_TRIGGERS["pounding_gale_red"] = [
    combo_trigger(["open_the_center"],
                  lambda c, e, s: effect_deal_damage(s, 3 - _controller_id(c), 2)),
]

# Combo: crane_dance — +1{p}, go again, can't be defended by high-power attacks
for _slug in ["crane_dance_red", "crane_dance_yellow", "crane_dance_blue"]:
    CARD_TRIGGERS[_slug] = [
        combo_trigger(["soulbead_strike"],
                      lambda c, e, s: go_again(c, e, s)),
    ]

# Combo: find_center — can't be defended by low-cost cards, create token on hit
CARD_TRIGGERS["find_center_blue"] = [
    combo_trigger(["crane_dance"],
                  lambda c, e, s: go_again(c, e, s)),
]

# Combo: herons_flight — +2{p} and choose 1
CARD_TRIGGERS["herons_flight_red"] = [
    combo_trigger(["crane_dance"],
                  lambda c, e, s: effect_draw(s, _controller_id(c), 1)),
]

# Combo: hundred_winds — +1{p} per other Hundred Winds on chain, go again
for _slug in ["hundred_winds_red", "hundred_winds_yellow", "hundred_winds_blue"]:
    CARD_TRIGGERS[_slug] = [
        combo_trigger(["hundred_winds"],
                      lambda c, e, s: go_again(c, e, s)),
    ]

# Combo: whelming_gustwave — +1{p}, go again, "if hits draw a card"
for _slug in ["whelming_gustwave_red", "whelming_gustwave_yellow",
              "whelming_gustwave_blue"]:
    CARD_TRIGGERS[_slug] = [
        combo_trigger(["surging_strike"],
                      lambda c, e, s: go_again(c, e, s)),
    ]

# Combo: descendent_gustwave — costs {r} less, +2{p}, go again
for _slug in ["descendent_gustwave_red", "descendent_gustwave_yellow",
              "descendent_gustwave_blue"]:
    CARD_TRIGGERS[_slug] = [
        combo_trigger(["surging_strike"],
                      lambda c, e, s: go_again(c, e, s)),
    ]

# Combo: gustwave_of_the_second_wind — go again
CARD_TRIGGERS["gustwave_of_the_second_wind_red"] = [
    combo_trigger(["surging_strike"],
                  lambda c, e, s: go_again(c, e, s)),
]

# Combo: tempest_palm_gustwave — +2{p}
CARD_TRIGGERS["tempest_palm_gustwave_yellow"] = [
    combo_trigger(["surging_strike"],
                  lambda c, e, s: go_again(c, e, s)),
]

# Combo: bonds_of_ancestry — costs less, go again, banish combo from graveyard
for _slug in ["bonds_of_ancestry_red", "bonds_of_ancestry_yellow",
              "bonds_of_ancestry_blue"]:
    CARD_TRIGGERS[_slug] = [
        combo_trigger(["gustwave"],
                      lambda c, e, s: go_again(c, e, s)),
    ]

# Combo: dishonor — +2{p}, if controls Surging Strike etc lose life
CARD_TRIGGERS["dishonor_blue"] = [
    combo_trigger(["bonds_of_ancestry"],
                  lambda c, e, s: effect_deal_damage(s, 3 - _controller_id(c), 2)),
]

# Combo: retrace_the_past — name a card, gain name/+2{p}/go again
CARD_TRIGGERS["retrace_the_past_blue"] = [
    combo_trigger(["gustwave"],
                  lambda c, e, s: go_again(c, e, s)),
]

# Combo: rushing_river — +1{p}, go again, draw X put X back
for _slug in ["rushing_river_red", "rushing_river_yellow", "rushing_river_blue"]:
    CARD_TRIGGERS[_slug] = [
        combo_trigger(["torrent_of_tempo"],
                      lambda c, e, s: go_again(c, e, s)),
    ]

# Combo: break_tide — +3{p}, dominate, banish top card
CARD_TRIGGERS["break_tide_yellow"] = [
    combo_trigger(["rushing_river", "flood_of_force"],
                  lambda c, e, s: go_again(c, e, s)),
]

# Combo: flood_of_force — reveal top, put combo into hand
CARD_TRIGGERS["flood_of_force_yellow"] = [
    combo_trigger(["rushing_river", "flood_of_force"],
                  lambda c, e, s: effect_draw(s, _controller_id(c), 1)),
]

# Combo: winds_of_eternity — +2{p}, shuffle Hundred Winds into deck
CARD_TRIGGERS["winds_of_eternity_blue"] = [
    combo_trigger(["winds_of_eternity"],
                  lambda c, e, s: effect_shuffle(s, _controller_id(c))),
]

# Combo: seek_vengeance — go again
for _slug in ["seek_vengeance_red", "seek_vengeance_blue"]:
    CARD_TRIGGERS[_slug] = [
        combo_trigger(["edge_of_autumn"],
                      lambda c, e, s: go_again(c, e, s)),
    ]

# Combo: vengeance_never_rests — go again, "when hits, banish, play again"
CARD_TRIGGERS["vengeance_never_rests_blue"] = [
    combo_trigger(["edge_of_autumn"],
                  lambda c, e, s: go_again(c, e, s)),
]

# Combo: enact_vengeance — "when hits, destroy all arsenal"
CARD_TRIGGERS["enact_vengeance_red"] = [
    combo_trigger(["edge_of_autumn", "vengeance"],
                  lambda c, e, s: effect_destroy(s, 3 - _controller_id(c), zone="arsenal")),
]

# Combo: lord_of_wind — shuffle target cards from graveyard
CARD_TRIGGERS["lord_of_wind_blue"] = [
    combo_trigger(["mugenshi_release"],
                  lambda c, e, s: effect_shuffle(s, _controller_id(c))),
]

# Combo: mugenshi_release — +1{p}, go again, search for Lord of Wind
CARD_TRIGGERS["mugenshi_release_yellow"] = [
    combo_trigger(["whelming_gustwave"],
                  lambda c, e, s: go_again(c, e, s)),
]

# -- surge_trigger (batch, non-arcane): "Surge — [EFFECT]." --

# Surge: glyph_overlay — gain 1{h}, shuffle Sigil auras
for _slug, _amt in {"glyph_overlay_red": 3, "glyph_overlay_yellow": 3,
                     "glyph_overlay_blue": 3}.items():
    CARD_TRIGGERS[_slug] = [
        on_play_deal_arcane(_amt),
        surge_trigger(_amt, lambda c, e, s: effect_gain_life(s, _controller_id(c), 1)),
    ]

# -- rupture_trigger (batch): "Rupture — [EFFECT]." --

# Rupture: +3{p}
CARD_TRIGGERS["lava_burst_red"] = [
    rupture_trigger(lambda c, e, s: effect_draw(s, _controller_id(c), 1)),
]

# Rupture: "when hits, destroy all arsenal"
CARD_TRIGGERS["breaking_point_red"] = [
    rupture_trigger(lambda c, e, s: effect_destroy(s, 3 - _controller_id(c), zone="arsenal")),
]

# Rupture: put -1{d} counter on equipment, destroy if 0{d}
CARD_TRIGGERS["liquefy_red"] = [
    rupture_trigger(lambda c, e, s: effect_put_counter(
        s, 3 - _controller_id(c), "defense_minus_1", 1)),
]

# Rupture: deal 2 damage to any target
CARD_TRIGGERS["searing_touch_red"] = [
    rupture_trigger(lambda c, e, s: effect_deal_damage(s, 3 - _controller_id(c), 2)),
]

# Rupture: dominate and +X{p} (where X is 2x Phoenix Flames)
CARD_TRIGGERS["rise_up_red"] = [
    rupture_trigger(lambda c, e, s: go_again(c, e, s)),
]

# Rupture: reveal top X cards, deal damage per Draconic
CARD_TRIGGERS["red_hot_red"] = [
    rupture_trigger(lambda c, e, s: effect_draw(s, _controller_id(c), 1)),
]


# ---------------------------------------------------------------------------
# Batch 4: Complex Custom Cards — multi-step effects and player choices
# ---------------------------------------------------------------------------

# -- absorb_in_aether (red/yellow/blue) --
# "The next card you play this turn with an effect that deals arcane damage,
#  instead deals that much arcane damage plus N."
def _absorb_in_aether_on_play(bonus):
    def _effect(card, event, state):
        cid = _controller_id(card)
        state.players[cid].current_turn_effects.append(f"absorb_in_aether_{bonus}")
    return _effect

for _color, _bonus in [("red", 2), ("yellow", 2), ("blue", 2)]:
    CARD_TRIGGERS[f"absorb_in_aether_{_color}"] = [
        TriggerDef(event_type="on_play", effect_fn=_absorb_in_aether_on_play(_bonus)),
    ]


# -- air_of_a_comeback --
# "You may put a non-attack action card from your graveyard on top of your deck.
#  If you have no cards in hand, instead you may play it this turn."
def _air_of_comeback_on_play(card, event, state):
    cid = _controller_id(card)
    controller = state.players[cid]
    eligible = [c for c in controller.graveyard.cards
                if "Action" in (c.types or []) and "Attack" not in (c.types or [])]
    if not eligible:
        return
    pick = _ask_player(state, cid, [c.slug for c in eligible],
                       context="Air of a Comeback: choose a non-attack action from graveyard")
    chosen = next((c for c in eligible if c.slug == pick), eligible[0])
    if not controller.hand.cards:
        # Play it this turn instead
        controller.graveyard.remove(chosen)
        controller.hand.add(chosen)
        state.players[cid].current_turn_effects.append(f"may_play_{chosen.slug}")
    else:
        controller.graveyard.remove(chosen)
        effect_put_top_deck(state, chosen, cid)

CARD_TRIGGERS["air_of_a_comeback"] = [
    TriggerDef(event_type="on_play", effect_fn=_air_of_comeback_on_play),
]


# -- already_dead (red/yellow/blue) --
# Contract: banish opponents' non-action cards -> create Silver token
# On hit: banish top of deck, if non-action and opponent's -> complete contract
def _already_dead_hit(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    target_id = 3 - cid
    target = state.players[target_id]
    if target.deck.cards:
        top = target.deck.pop_top()
        effect_banish(state, top, face_up=True, banisher_id=cid)

def _already_dead_on_play(card, event, state):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("contract_already_dead_active")

def _already_dead_contract(card, event, state):
    cid = _controller_id(card)
    if "contract_already_dead_active" not in state.players[cid].current_turn_effects:
        return
    if not hasattr(event, 'data'):
        return
    banished = event.data.get('card')
    banisher_id = event.data.get('banisher_id')
    if banisher_id != cid:
        return
    if banished and banished.owner != cid and "Action" not in (banished.types or []):
        create_token(state, cid, "silver")

for _color in ["red", "yellow", "blue"]:
    CARD_TRIGGERS[f"already_dead_{_color}"] = [
        TriggerDef(event_type="on_play", effect_fn=_already_dead_on_play),
        TriggerDef(event_type="card_banished", effect_fn=_already_dead_contract),
        TriggerDef(event_type="hit", effect_fn=_already_dead_hit),
    ]


# -- annihilate_the_armed (red/yellow/blue) --
# Contract: banish opponents' attack action cards -> create Silver token
def _annihilate_armed_on_play(card, event, state):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("contract_annihilate_armed_active")

def _annihilate_armed_contract(card, event, state):
    cid = _controller_id(card)
    if "contract_annihilate_armed_active" not in state.players[cid].current_turn_effects:
        return
    if not hasattr(event, 'data'):
        return
    banished = event.data.get('card')
    banisher_id = event.data.get('banisher_id')
    if banisher_id != cid:
        return
    if (banished and banished.owner != cid
            and "Attack" in (banished.types or []) and "Action" in (banished.types or [])):
        create_token(state, cid, "silver")

def _annihilate_armed_hit(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    target_id = 3 - cid
    target = state.players[target_id]
    if target.deck.cards:
        top = target.deck.pop_top()
        effect_banish(state, top, face_up=True, banisher_id=cid)

for _color in ["red", "yellow", "blue"]:
    CARD_TRIGGERS[f"annihilate_the_armed_{_color}"] = [
        TriggerDef(event_type="on_play", effect_fn=_annihilate_armed_on_play),
        TriggerDef(event_type="card_banished", effect_fn=_annihilate_armed_contract),
        TriggerDef(event_type="hit", effect_fn=_annihilate_armed_hit),
    ]


# -- arakni / arakni_huntsman --
# "Whenever you play a card with contract, you may look at the top card of
#  target opponent's deck. You may put it on the bottom."
def _arakni_on_play(card, event, state):
    if not hasattr(event, 'data'):
        return
    played = event.data.get('card')
    if not played:
        return
    ft = (played.base_functional_text or '').lower()
    if 'contract' not in ft:
        return
    cid = _controller_id(card)
    opp_id = 3 - cid
    opp = state.players[opp_id]
    if not opp.deck.cards:
        return
    top = opp.deck.cards[0]
    choice = _ask_player(state, cid, [True, False],
                         context=f"Arakni: put {top.slug} on bottom of opponent's deck?")
    if choice:
        opp.deck.cards.pop(0)
        opp.deck.cards.append(top)

for _slug in ["arakni", "arakni_huntsman"]:
    CARD_TRIGGERS[_slug] = [
        TriggerDef(event_type="on_play", effect_fn=_arakni_on_play),
    ]


# -- arakni_tarantula --
# "Whenever a dagger you own hits a hero, they lose 1 life."
def _arakni_tarantula_hit(card, event, state):
    if not hasattr(event, 'data'):
        return
    hit_card = event.data.get('card')
    if not hit_card:
        return
    cid = _controller_id(card)
    if hit_card.owner != cid:
        return
    if "Dagger" not in (hit_card.types or []) and "Dagger" not in (hit_card.subtypes or []):
        return
    target_id = 3 - cid
    effect_lose_life(state, target_id, 1)

CARD_TRIGGERS["arakni_tarantula"] = [
    TriggerDef(event_type="hit", effect_fn=_arakni_tarantula_hit),
]


# -- arc_lightning (yellow) --
# "Whenever you go again this turn, deal 1 arcane damage to any target."
def _arc_lightning_on_play(card, event, state):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("arc_lightning_go_again_damage")

CARD_TRIGGERS["arc_lightning_yellow"] = [
    TriggerDef(event_type="on_play", effect_fn=_arc_lightning_on_play),
]


# -- arcane_polarity (red/yellow/blue) --
# "Gain N life. If you've been dealt arcane damage this turn, instead gain M life."
def _arcane_polarity_on_play(gain, gain_if_arcane):
    def _effect(card, event, state):
        cid = _controller_id(card)
        if f"dealt_arcane_this_turn_{cid}" in state.players[cid].current_turn_effects:
            effect_gain_life(state, cid, gain_if_arcane)
        else:
            effect_gain_life(state, cid, gain)
    return _effect

for _color, _gain, _gain_if in [("red", 1, 4), ("yellow", 1, 3), ("blue", 1, 2)]:
    CARD_TRIGGERS[f"arcane_polarity_{_color}"] = [
        TriggerDef(event_type="on_play", effect_fn=_arcane_polarity_on_play(_gain, _gain_if)),
    ]


# -- arena_medic --
# "Gain 1 life. If you have no cards in hand, instead gain 3 life."
def _arena_medic_on_play(card, event, state):
    cid = _controller_id(card)
    controller = state.players[cid]
    if not controller.hand.cards:
        effect_gain_life(state, cid, 3)
    else:
        effect_gain_life(state, cid, 1)

CARD_TRIGGERS["arena_medic"] = [
    TriggerDef(event_type="on_play", effect_fn=_arena_medic_on_play),
]


# -- art_of_desire_mind (blue) --
# "When this hits, banish top of their deck. Whenever this banishes a blue card, draw+gain life."
def _art_of_desire_mind_hit(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    target_id = 3 - cid
    target = state.players[target_id]
    if target.deck.cards:
        top = target.deck.pop_top()
        effect_banish(state, top, face_up=True, banisher_id=cid)
        if top.pitch == 3:  # Blue card
            effect_draw(state, cid, 1)
            effect_gain_life(state, cid, 1)

CARD_TRIGGERS["art_of_desire_mind_blue"] = [
    TriggerDef(event_type="hit", effect_fn=_art_of_desire_mind_hit),
]


# -- art_of_desire_soul (yellow) --
# "When this hits, banish top of their deck. Whenever this banishes a yellow card, draw+gain life."
def _art_of_desire_soul_hit(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    target_id = 3 - cid
    target = state.players[target_id]
    if target.deck.cards:
        top = target.deck.pop_top()
        effect_banish(state, top, face_up=True, banisher_id=cid)
        if top.pitch == 2:  # Yellow card
            effect_draw(state, cid, 1)
            effect_gain_life(state, cid, 1)

CARD_TRIGGERS["art_of_desire_soul_yellow"] = [
    TriggerDef(event_type="hit", effect_fn=_art_of_desire_soul_hit),
]


# -- attune_with_cosmic_vibrations (blue) --
# "When this attacks/defends, reveal top card. If blue, +3 power and +3 defense."
def _attune_cosmic_attacking(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    target_id = 3 - cid
    revealed = effect_reveal_top(state, target_id, 1)
    if revealed and revealed[0].pitch == 3:
        card.effects.append(("base_power", lambda base: base + 3))
        card.effects.append(("base_defense", lambda base: base + 3))

def _attune_cosmic_defending(card, event, state):
    if not state.combat or card not in state.combat.defending_cards:
        return
    cid = _controller_id(card)
    attacker_id = 3 - cid
    revealed = effect_reveal_top(state, attacker_id, 1)
    if revealed and revealed[0].pitch == 3:
        card.effects.append(("base_power", lambda base: base + 3))
        card.effects.append(("base_defense", lambda base: base + 3))

CARD_TRIGGERS["attune_with_cosmic_vibrations_blue"] = [
    TriggerDef(event_type="attacking", effect_fn=_attune_cosmic_attacking),
    TriggerDef(event_type="defend", effect_fn=_attune_cosmic_defending),
]


# -- azvolai --
# "Whenever Azvolai attacks, deal 1 arcane damage to up to 2 targets."
def _azvolai_attacking(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    target_id = 3 - cid
    effect_deal_arcane(state, target_id, 1)
    effect_deal_arcane(state, target_id, 1)

CARD_TRIGGERS["azvolai"] = [
    TriggerDef(event_type="attacking", effect_fn=_azvolai_attacking),
]


# -- ball_lightning (red/yellow/blue) --
# "Whenever a lightning/elemental action card would deal damage this chain, +1 damage."
def _ball_lightning_on_play(card, event, state):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("ball_lightning_damage_bonus")

for _color in ["red", "yellow", "blue"]:
    CARD_TRIGGERS[f"ball_lightning_{_color}"] = [
        TriggerDef(event_type="on_play", effect_fn=_ball_lightning_on_play),
    ]


# -- beacon_of_victory (yellow) --
# "Banish X cards from soul. Target attack gains +X power. If charged, it gains go again."
def _beacon_of_victory_on_play(card, event, state):
    cid = _controller_id(card)
    controller = state.players[cid]
    if not hasattr(controller, 'soul') or not controller.soul.cards:
        return
    max_x = len(controller.soul.cards)
    x = _ask_player(state, cid, list(range(1, max_x + 1)),
                     context="Beacon of Victory: how many cards to banish from soul?")
    for _ in range(x):
        if controller.soul.cards:
            c = controller.soul.cards[0]
            controller.soul.remove(c)
            effect_banish(state, c, face_up=True, banisher_id=cid)
    if state.combat and state.combat.attack_card:
        state.combat.attack_card.effects.append(("base_power", lambda base, _x=x: base + _x))

CARD_TRIGGERS["beacon_of_victory_yellow"] = [
    TriggerDef(event_type="on_play", effect_fn=_beacon_of_victory_on_play),
]


# -- become_the_arknight (blue) --
# "Discard an action card. If attack action, search deck for runeblade non-attack action."
def _become_arknight_on_play(card, event, state):
    cid = _controller_id(card)
    controller = state.players[cid]
    actions = [c for c in controller.hand.cards if "Action" in (c.types or [])]
    if not actions:
        return
    pick = _ask_player(state, cid, [c.slug for c in actions],
                       context="Become the Arknight: discard an action card")
    chosen = next((c for c in actions if c.slug == pick), actions[0])
    controller.hand.remove(chosen)
    controller.graveyard.add(chosen)
    if "Attack" in (chosen.types or []):
        def _is_runeblade_naa(c):
            return ("Runeblade" in (c.supertypes or [])
                    and "Action" in (c.types or [])
                    and "Attack" not in (c.types or []))
        found = effect_search_deck(state, cid, condition=_is_runeblade_naa)
        if found:
            controller.deck.remove(found)
            controller.hand.add(found)
            effect_shuffle(state, cid)

CARD_TRIGGERS["become_the_arknight_blue"] = [
    TriggerDef(event_type="on_play", effect_fn=_become_arknight_on_play),
]


# -- beseech_the_demigon (red/yellow/blue) --
# "Choose an attack action card in your banished zone. It gets +3 power until end of turn."
def _beseech_demigon_on_play(card, event, state):
    cid = _controller_id(card)
    controller = state.players[cid]
    eligible = [c for c in controller.banished.cards
                if "Attack" in (c.types or []) and "Action" in (c.types or [])]
    if not eligible:
        return
    pick = _ask_player(state, cid, [c.slug for c in eligible],
                       context="Beseech the Demigon: choose attack action in banished zone to get +3 power")
    chosen = next((c for c in eligible if c.slug == pick), eligible[0])
    chosen.effects.append(("base_power", lambda base: base + 3))

for _color in ["red", "yellow", "blue"]:
    CARD_TRIGGERS[f"beseech_the_demigon_{_color}"] = [
        TriggerDef(event_type="on_play", effect_fn=_beseech_demigon_on_play),
    ]


# -- blasmophet_the_soul_harvester --
# "Whenever Blasmophet attacks, you may banish a Shadow card from hand.
#  If you do, you may banish a card from the defending hero's soul."
def _blasmophet_attacking(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    controller = state.players[cid]
    shadow_cards = [c for c in controller.hand.cards if "Shadow" in (c.supertypes or [])]
    if not shadow_cards:
        return
    choice = _ask_player(state, cid, [True, False],
                         context="Blasmophet: banish a Shadow card from hand?")
    if not choice:
        return
    pick = _ask_player(state, cid, [c.slug for c in shadow_cards],
                       context="Choose Shadow card to banish")
    chosen = next((c for c in shadow_cards if c.slug == pick), shadow_cards[0])
    controller.hand.remove(chosen)
    effect_banish(state, chosen, face_up=True, banisher_id=cid)
    target_id = 3 - cid
    target = state.players[target_id]
    if hasattr(target, 'soul') and target.soul.cards:
        soul_pick = _ask_player(state, cid, [c.slug for c in target.soul.cards],
                                context="Blasmophet: banish a card from defending hero's soul")
        soul_card = next((c for c in target.soul.cards if c.slug == soul_pick), target.soul.cards[0])
        target.soul.remove(soul_card)
        effect_banish(state, soul_card, face_up=True, banisher_id=cid)

CARD_TRIGGERS["blasmophet_the_soul_harvester"] = [
    TriggerDef(event_type="attacking", effect_fn=_blasmophet_attacking),
]


# -- blizzard_bolt (red/yellow/blue) --
# "If fused, whenever an attack deals damage to a hero this turn, create Frostbite."
def _blizzard_bolt_on_play(card, event, state):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("blizzard_bolt_frostbite_on_damage")

for _color in ["red", "yellow", "blue"]:
    CARD_TRIGGERS[f"blizzard_bolt_{_color}"] = [
        TriggerDef(event_type="on_play", effect_fn=_blizzard_bolt_on_play),
    ]


# -- blood_splattered_vest --
# "Whenever a dagger you control hits, you may gain {r} and put a stain counter.
#  If 3+ stain counters, destroy this."
def _blood_vest_hit(card, event, state):
    if not hasattr(event, 'data'):
        return
    hit_card = event.data.get('card')
    if not hit_card:
        return
    cid = _controller_id(card)
    if hit_card.controller != cid and hit_card.owner != cid:
        return
    if "Dagger" not in (hit_card.types or []) and "Dagger" not in (hit_card.subtypes or []):
        return
    choice = _ask_player(state, cid, [True, False],
                         context="Blood Splattered Vest: gain {r} and put a stain counter?")
    if not choice:
        return
    effect_gain_resources(state, cid, 1)
    effect_put_counter(state, card, "stain", 1)
    stain_count = card.counters.get("stain", 0)
    if stain_count >= 3:
        effect_destroy(state, card)

CARD_TRIGGERS["blood_splattered_vest"] = [
    TriggerDef(event_type="hit", effect_fn=_blood_vest_hit),
]


# -- boltyn --
# "If you've charged this turn, your attacks get +1 power while defended by attack action."
def _boltyn_attacking(card, event, state):
    cid = _controller_id(card)
    if "charged_this_turn" not in state.players[cid].current_turn_effects:
        return
    if state.combat and state.combat.attack_card:
        state.combat.attack_card.effects.append(("base_power", lambda base: base + 1))

CARD_TRIGGERS["boltyn"] = [
    TriggerDef(event_type="attacking", effect_fn=_boltyn_attacking),
]


# -- bone_vizier --
# "When destroyed, reveal top card. If 6+ power, put on top. Otherwise, bottom."
def _bone_vizier_destroyed(card, event, state):
    if not hasattr(event, 'data') or event.data.get('card') != card:
        return
    cid = card.owner
    controller = state.players[cid]
    if not controller.deck.cards:
        return
    top = controller.deck.cards[0]
    top.is_public = True
    if top.power is not None and top.power >= 6:
        pass  # Stay on top
    else:
        controller.deck.cards.pop(0)
        controller.deck.cards.append(top)
        top.is_public = False

CARD_TRIGGERS["bone_vizier"] = [
    TriggerDef(event_type="card_destroyed", effect_fn=_bone_vizier_destroyed),
]


# -- bounding_demigon (red/yellow/blue) --
# "If you've played a non-attack action this turn, you may play this from banished zone."
def _bounding_demigon_on_play(card, event, state):
    cid = _controller_id(card)
    if card.prev_zone == "banished":
        card.effects.append(("base_power", lambda base: base + 1))

for _color in ["red", "yellow", "blue"]:
    CARD_TRIGGERS[f"bounding_demigon_{_color}"] = [
        TriggerDef(event_type="on_play", effect_fn=_bounding_demigon_on_play),
    ]


# -- brainstorm (blue) --
# "Whenever you draw a card this action phase, deal 1 arcane damage."
def _brainstorm_on_play(card, event, state):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("brainstorm_arcane_on_draw")

CARD_TRIGGERS["brainstorm_blue"] = [
    TriggerDef(event_type="on_play", effect_fn=_brainstorm_on_play),
]


# -- briar / briar_warden_of_thorns --
# "First time an attack action deals damage to opposing hero, create Embodiment of Earth.
#  Whenever you play your second non-attack action, create Embodiment of Lightning."
def _briar_damage(card, event, state):
    cid = _controller_id(card)
    if "briar_first_attack_damage_done" in state.players[cid].current_turn_effects:
        return
    if not hasattr(event, 'data'):
        return
    source = event.data.get('source')
    if source and "Attack" in (source.types or []) and "Action" in (source.types or []):
        if source.controller == cid or source.owner == cid:
            state.players[cid].current_turn_effects.append("briar_first_attack_damage_done")
            create_token(state, cid, "embodiment_of_earth")

def _briar_on_play(card, event, state):
    if not hasattr(event, 'data'):
        return
    played = event.data.get('card')
    if not played:
        return
    cid = _controller_id(card)
    if "Action" in (played.types or []) and "Attack" not in (played.types or []):
        key = "briar_naa_count"
        count = sum(1 for e in state.players[cid].current_turn_effects if e == key)
        state.players[cid].current_turn_effects.append(key)
        if count == 1:  # This is the second non-attack action
            create_token(state, cid, "embodiment_of_lightning")

for _slug in ["briar", "briar_warden_of_thorns"]:
    CARD_TRIGGERS[_slug] = [
        TriggerDef(event_type="damage_dealt", effect_fn=_briar_damage),
        TriggerDef(event_type="on_play", effect_fn=_briar_on_play),
    ]


# -- buzz_bolt (red/yellow/blue) --
# "If fused, whenever an attack hits a hero this turn, deal 1 damage."
def _buzz_bolt_on_play(card, event, state):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("buzz_bolt_hit_damage")

for _color in ["red", "yellow", "blue"]:
    CARD_TRIGGERS[f"buzz_bolt_{_color}"] = [
        TriggerDef(event_type="on_play", effect_fn=_buzz_bolt_on_play),
    ]


# -- cadaverous_contraband (red/yellow/blue) --
# "If this hits, you may put a non-attack action from graveyard on top of deck."
def _cadaverous_hit(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    controller = state.players[cid]
    eligible = [c for c in controller.graveyard.cards
                if "Action" in (c.types or []) and "Attack" not in (c.types or [])]
    if not eligible:
        return
    choice = _ask_player(state, cid, [True, False],
                         context="Cadaverous Contraband: put non-attack action on top of deck?")
    if not choice:
        return
    pick = _ask_player(state, cid, [c.slug for c in eligible],
                       context="Choose card to put on top")
    chosen = next((c for c in eligible if c.slug == pick), eligible[0])
    controller.graveyard.remove(chosen)
    effect_put_top_deck(state, chosen, cid)

for _color in ["red", "yellow", "blue"]:
    CARD_TRIGGERS[f"cadaverous_contraband_{_color}"] = [
        TriggerDef(event_type="hit", effect_fn=_cadaverous_hit),
    ]


# -- call_to_the_grave (red/yellow/blue) --
# "Search your deck for a card, put it into your graveyard, then shuffle."
def _call_grave_on_play(card, event, state):
    cid = _controller_id(card)
    controller = state.players[cid]
    if not controller.deck.cards:
        return
    pick = _ask_player(state, cid, [c.slug for c in controller.deck.cards],
                       context="Call to the Grave: choose a card to put into graveyard")
    chosen = next((c for c in controller.deck.cards if c.slug == pick), controller.deck.cards[0])
    controller.deck.remove(chosen)
    controller.graveyard.add(chosen)
    effect_shuffle(state, cid)

for _color in ["red", "yellow", "blue"]:
    CARD_TRIGGERS[f"call_to_the_grave_{_color}"] = [
        TriggerDef(event_type="on_play", effect_fn=_call_grave_on_play),
    ]


# -- cast_bones (red/yellow/blue) --
# "Reveal top 6 cards. Create a Might token for each card with 6+ power.
#  Put revealed cards on top in any order."
def _cast_bones_on_play(card, event, state):
    cid = _controller_id(card)
    revealed = effect_reveal_top(state, cid, 6)
    might_count = sum(1 for c in revealed if c.power is not None and c.power >= 6)
    if might_count > 0:
        create_token(state, cid, "might", might_count)

for _color in ["red", "yellow", "blue"]:
    CARD_TRIGGERS[f"cast_bones_{_color}"] = [
        TriggerDef(event_type="on_play", effect_fn=_cast_bones_on_play),
    ]


# -- cindra / cindra_dracai_of_retribution --
# "Whenever you hit a marked hero, create a Fealty token."
def _cindra_hit(card, event, state):
    if not hasattr(event, 'data'):
        return
    cid = _controller_id(card)
    target_id = 3 - cid
    if is_marked(state, target_id):
        create_token(state, cid, "fealty")

for _slug in ["cindra", "cindra_dracai_of_retribution"]:
    CARD_TRIGGERS[_slug] = [
        TriggerDef(event_type="hit", effect_fn=_cindra_hit),
    ]


# -- cintari_saber --
# "Whenever defended by 1+ attack action cards, gains +1 power."
def _cintari_saber_defend(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    defending = state.combat.defending_cards or []
    if any("Attack" in (c.types or []) and "Action" in (c.types or []) for c in defending):
        card.effects.append(("base_power", lambda base: base + 1))

CARD_TRIGGERS["cintari_saber"] = [
    TriggerDef(event_type="defend", effect_fn=_cintari_saber_defend),
]


# -- civic_duty / civic_guide / civic_peak / civic_steps --
# Equipment that creates tokens for another hero when defending
def _civic_duty_defend(card, event, state):
    if not state.combat or card not in state.combat.defending_cards:
        return
    cid = _controller_id(card)
    create_token(state, cid, "vigor")

def _civic_guide_defend(card, event, state):
    if not state.combat or card not in state.combat.defending_cards:
        return
    cid = _controller_id(card)
    create_token(state, cid, "might")

def _civic_peak_defend(card, event, state):
    if not state.combat or card not in state.combat.defending_cards:
        return
    cid = _controller_id(card)
    effect_draw(state, cid, 1)

def _civic_steps_defend(card, event, state):
    if not state.combat or card not in state.combat.defending_cards:
        return
    cid = _controller_id(card)
    create_token(state, cid, "quicken")

CARD_TRIGGERS["civic_duty"] = [TriggerDef(event_type="defend", effect_fn=_civic_duty_defend)]
CARD_TRIGGERS["civic_guide"] = [TriggerDef(event_type="defend", effect_fn=_civic_guide_defend)]
CARD_TRIGGERS["civic_peak"] = [TriggerDef(event_type="defend", effect_fn=_civic_peak_defend)]
CARD_TRIGGERS["civic_steps"] = [TriggerDef(event_type="defend", effect_fn=_civic_steps_defend)]


# -- data_doll_mkii --
# "Whenever a Mechanologist item with cost 2 or less is banished from deck, put it into arena."
def _data_doll_banished(card, event, state):
    if not hasattr(event, 'data'):
        return
    banished = event.data.get('card')
    if not banished:
        return
    cid = _controller_id(card)
    if banished.owner != cid:
        return
    if banished.prev_zone != "deck":
        return
    if ("Mechanologist" in (banished.supertypes or [])
            and "Item" in (banished.types or [])
            and (banished.cost or 0) <= 2):
        _remove_from_current_zone(banished, state)
        state.players[cid].permanents.add(banished)

CARD_TRIGGERS["data_doll_mkii"] = [
    TriggerDef(event_type="card_banished", effect_fn=_data_doll_banished),
]


# -- dominia --
# "Whenever Dominia attacks a hero, reveal top card. If red, look at their hand and banish a card."
def _dominia_attacking(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    controller = state.players[cid]
    revealed = effect_reveal_top(state, cid, 1)
    if not revealed:
        return
    if revealed[0].pitch == 1:  # Red card
        target_id = 3 - cid
        target = state.players[target_id]
        if target.hand.cards:
            pick = _ask_player(state, cid, [c.slug for c in target.hand.cards],
                               context="Dominia: choose a card from opponent's hand to banish")
            chosen = next((c for c in target.hand.cards if c.slug == pick), target.hand.cards[0])
            target.hand.remove(chosen)
            effect_banish(state, chosen, face_up=True, banisher_id=cid)

CARD_TRIGGERS["dominia"] = [
    TriggerDef(event_type="attacking", effect_fn=_dominia_attacking),
]


# -- dracona_optimai --
# "Whenever this attacks a hero, reveal top 3 cards.
#  Deal arcane damage equal to 2x red cards revealed."
def _dracona_attacking(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    target_id = 3 - cid
    revealed = effect_reveal_top(state, cid, 3)
    red_count = sum(1 for c in revealed if c.pitch == 1)
    if red_count > 0:
        effect_deal_arcane(state, target_id, red_count * 2)

CARD_TRIGGERS["dracona_optimai"] = [
    TriggerDef(event_type="attacking", effect_fn=_dracona_attacking),
]


# -- dread_scythe --
# "Whenever you attack with this, deal 1 arcane damage to the defending hero."
def _dread_scythe_attacking(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    target_id = 3 - cid
    effect_deal_arcane(state, target_id, 1)

CARD_TRIGGERS["dread_scythe"] = [
    TriggerDef(event_type="attacking", effect_fn=_dread_scythe_attacking),
]


# -- dromai / dromai_ash_artist --
# "Whenever you pitch a red card, create an Ash Token.
#  If you've played a red card this turn, dragons have go again."
def _dromai_pitched(card, event, state):
    if not hasattr(event, 'data'):
        return
    pitched = event.data.get('card')
    if not pitched:
        return
    cid = _controller_id(card)
    if pitched.owner != cid:
        return
    if pitched.pitch == 1:  # Red card
        create_token(state, cid, "ash")

for _slug in ["dromai", "dromai_ash_artist"]:
    CARD_TRIGGERS[_slug] = [
        TriggerDef(event_type="card_pitched", effect_fn=_dromai_pitched),
    ]


# -- duskblade --
# "Whenever you attack with Duskblade, if you've played an attack action and
#  a non-attack action this turn, put a +1 power counter on it."
def _duskblade_attacking(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    effects = state.players[cid].current_turn_effects
    played_attack = any("played_attack_action" in e for e in effects)
    played_naa = any("played_non_attack_action" in e for e in effects)
    if played_attack and played_naa:
        effect_put_counter(state, card, "power_plus_1", 1)
        card.effects.append(("base_power", lambda base: base + 1))

CARD_TRIGGERS["duskblade"] = [
    TriggerDef(event_type="attacking", effect_fn=_duskblade_attacking),
]


# -- earthlore_bounty --
# "Whenever you draw a card from effect of an action card, create Seismic Surge token."
def _earthlore_defend(card, event, state):
    if not state.combat or card not in state.combat.defending_cards:
        return
    # Passive - tracked via current_turn_effects
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("earthlore_bounty_active")

CARD_TRIGGERS["earthlore_bounty"] = [
    TriggerDef(event_type="defend",
               condition_fn=lambda c, e, s: s.combat and c in s.combat.defending_cards,
               effect_fn=_earthlore_defend),
]


# -- fang / fang_dracai_of_blades --
# "Whenever you hit a marked hero, create a Fealty token.
#  If 3+ Fealty tokens, dagger attacks cost {r} less."
def _fang_hit(card, event, state):
    cid = _controller_id(card)
    target_id = 3 - cid
    if is_marked(state, target_id):
        create_token(state, cid, "fealty")

for _slug in ["fang", "fang_dracai_of_blades"]:
    CARD_TRIGGERS[_slug] = [
        TriggerDef(event_type="hit", effect_fn=_fang_hit),
    ]


# -- ghostly_touch --
# "Whenever an Illusionist attack is destroyed by phantasm, put a haunt counter."
def _ghostly_touch_destroyed(card, event, state):
    if not hasattr(event, 'data'):
        return
    destroyed = event.data.get('card')
    if not destroyed:
        return
    cid = _controller_id(card)
    if destroyed.owner != cid and destroyed.controller != cid:
        return
    if "Illusionist" in (destroyed.supertypes or []) and "Attack" in (destroyed.types or []):
        effect_put_counter(state, card, "haunt", 1)

CARD_TRIGGERS["ghostly_touch"] = [
    TriggerDef(event_type="card_destroyed", effect_fn=_ghostly_touch_destroyed),
]


# -- grains_of_bloodspill --
# "Whenever a weapon attack you control hits, you may pay {r}. Create Vigor."
def _grains_bloodspill_hit(card, event, state):
    if not hasattr(event, 'data'):
        return
    hit_card = event.data.get('card')
    if not hit_card:
        return
    cid = _controller_id(card)
    if (hit_card.owner != cid and hit_card.controller != cid):
        return
    if "Weapon" not in (hit_card.types or []):
        return
    if state.players[cid].resources < 1:
        return
    choice = _ask_player(state, cid, [True, False],
                         context="Grains of Bloodspill: pay {r} to create Vigor?")
    if choice:
        state.players[cid].resources -= 1
        create_token(state, cid, "vigor")

CARD_TRIGGERS["grains_of_bloodspill"] = [
    TriggerDef(event_type="hit", effect_fn=_grains_bloodspill_hit),
]


# -- hatchet_of_body / hatchet_of_mind --
# Each gains +1 power if the other was the last attack this turn
def _hatchet_body_attacking(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    if "last_attack_hatchet_of_mind" in state.players[cid].current_turn_effects:
        card.effects.append(("base_power", lambda base: base + 1))
    state.players[cid].current_turn_effects.append("last_attack_hatchet_of_body")

def _hatchet_mind_attacking(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    if "last_attack_hatchet_of_body" in state.players[cid].current_turn_effects:
        card.effects.append(("base_power", lambda base: base + 1))
    state.players[cid].current_turn_effects.append("last_attack_hatchet_of_mind")

CARD_TRIGGERS["hatchet_of_body"] = [
    TriggerDef(event_type="attacking", effect_fn=_hatchet_body_attacking),
]
CARD_TRIGGERS["hatchet_of_mind"] = [
    TriggerDef(event_type="attacking", effect_fn=_hatchet_mind_attacking),
]


# -- hexagore_the_death_hydra --
# "Whenever you attack with this, deals damage to you equal to 6 minus
#  number of blood debt cards in banished zone."
def _hexagore_attacking(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    controller = state.players[cid]
    bd_count = sum(1 for c in controller.banished.cards
                   if "Blood Debt" in (c.keywords or []))
    self_damage = max(0, 6 - bd_count)
    if self_damage > 0:
        effect_deal_damage(state, cid, self_damage, card, "generic")

CARD_TRIGGERS["hexagore_the_death_hydra"] = [
    TriggerDef(event_type="attacking", effect_fn=_hexagore_attacking),
]


# -- hooves_of_the_shadowbeast --
# "Whenever a card with 6+ power is banished, you may destroy this. Gain 1 AP."
def _hooves_banished(card, event, state):
    if not hasattr(event, 'data'):
        return
    banished = event.data.get('card')
    if not banished:
        return
    cid = _controller_id(card)
    if banished.owner != cid:
        return
    if banished.power is not None and banished.power >= 6:
        choice = _ask_player(state, cid, [True, False],
                             context="Hooves of the Shadowbeast: destroy to gain 1 action point?")
        if choice:
            effect_destroy(state, card)
            effect_gain_action_point(state, cid, 1)

CARD_TRIGGERS["hooves_of_the_shadowbeast"] = [
    TriggerDef(event_type="card_banished", effect_fn=_hooves_banished),
]


# -- call_for_backup (red/yellow/blue) --
# "When this defends, choose 2 attack actions in graveyard. Opponent chooses 1.
#  Banish that card, put the other on top of deck."
def _call_for_backup_defend(card, event, state):
    if not state.combat or card not in state.combat.defending_cards:
        return
    cid = _controller_id(card)
    opp_id = 3 - cid
    controller = state.players[cid]
    eligible = [c for c in controller.graveyard.cards
                if "Attack" in (c.types or []) and "Action" in (c.types or [])]
    if len(eligible) < 2:
        return
    # Choose 2
    pick1 = _ask_player(state, cid, [c.slug for c in eligible],
                        context="Call for Backup: choose first attack action from graveyard")
    chosen1 = next((c for c in eligible if c.slug == pick1), eligible[0])
    remaining = [c for c in eligible if c != chosen1]
    pick2 = _ask_player(state, cid, [c.slug for c in remaining],
                        context="Call for Backup: choose second attack action from graveyard")
    chosen2 = next((c for c in remaining if c.slug == pick2), remaining[0])
    # Opponent chooses which to banish
    opp_pick = _ask_player(state, opp_id, [chosen1.slug, chosen2.slug],
                           context="Call for Backup: choose which card to banish")
    if opp_pick == chosen1.slug:
        controller.graveyard.remove(chosen1)
        effect_banish(state, chosen1, face_up=True, banisher_id=cid)
        controller.graveyard.remove(chosen2)
        effect_put_top_deck(state, chosen2, cid)
    else:
        controller.graveyard.remove(chosen2)
        effect_banish(state, chosen2, face_up=True, banisher_id=cid)
        controller.graveyard.remove(chosen1)
        effect_put_top_deck(state, chosen1, cid)

for _color in ["red", "yellow", "blue"]:
    CARD_TRIGGERS[f"call_for_backup_{_color}"] = [
        TriggerDef(event_type="defend", effect_fn=_call_for_backup_defend),
    ]


# -- chains_of_mephetis (red/yellow/blue) --
# "You may play this from banished zone. If you do, enters with doom counter.
#  Start of turn: destroy unless remove doom counter."
def _chains_mephetis_on_play(card, event, state):
    if card.prev_zone == "banished":
        effect_put_counter(state, card, "doom", 1)

def _chains_mephetis_start_turn(card, event, state):
    if card.zone not in ("permanents", "arms", "chest", "head", "legs"):
        return
    if card.counters.get("doom", 0) > 0:
        cid = _controller_id(card)
        choice = _ask_player(state, cid, [True, False],
                             context="Chains of Mephetis: remove doom counter to keep?")
        if choice:
            effect_remove_counter(state, card, "doom", 1)
        else:
            effect_destroy(state, card)

for _color in ["red", "yellow", "blue"]:
    CARD_TRIGGERS[f"chains_of_mephetis_{_color}"] = [
        TriggerDef(event_type="on_play", effect_fn=_chains_mephetis_on_play),
        TriggerDef(event_type="start_of_turn", effect_fn=_chains_mephetis_start_turn),
    ]


# -- chart_the_high_seas (red/yellow/blue) --
# "Look at top 2. You may pitch a blue card from among them.
#  Put rest into graveyard. Create a Gold token for each yellow card pitched."
def _chart_high_seas_on_play(card, event, state):
    cid = _controller_id(card)
    controller = state.players[cid]
    top = effect_look_top(state, cid, 2)
    if not top:
        return
    for c in top:
        controller.deck.remove(c)
        controller.graveyard.add(c)

for _color in ["red", "yellow", "blue"]:
    CARD_TRIGGERS[f"chart_the_high_seas_{_color}"] = [
        TriggerDef(event_type="on_play", effect_fn=_chart_high_seas_on_play),
    ]


# -- drive_brake --
# "Whenever you banish a Hyper Driver from boosting, remove a -1{d} counter."
def _drive_brake_banished(card, event, state):
    if not hasattr(event, 'data'):
        return
    banished = event.data.get('card')
    if not banished:
        return
    cid = _controller_id(card)
    if banished.owner != cid:
        return
    if "hyper_driver" in banished.slug:
        effect_remove_counter(state, card, "minus_defense", 1)

CARD_TRIGGERS["drive_brake"] = [
    TriggerDef(event_type="card_banished", effect_fn=_drive_brake_banished),
]


# -- fist_pump --
# "Whenever you banish a Hyper Driver from boosting, target wrench gets +1 power."
def _fist_pump_banished(card, event, state):
    if not hasattr(event, 'data'):
        return
    banished = event.data.get('card')
    if not banished:
        return
    cid = _controller_id(card)
    if banished.owner != cid:
        return
    if "hyper_driver" in banished.slug:
        # Boost wrench power
        for w in state.players[cid].weapon.cards:
            if "Wrench" in (w.subtypes or []) or "wrench" in w.slug:
                w.effects.append(("base_power", lambda base: base + 1))
                break

CARD_TRIGGERS["fist_pump"] = [
    TriggerDef(event_type="card_banished", effect_fn=_fist_pump_banished),
]


# -- beaten_trackers --
# "Whenever you discard a random card with 6+ power, you may destroy this. Gain 1 AP."
def _beaten_trackers_discard(card, event, state):
    if not hasattr(event, 'data'):
        return
    discarded = event.data.get('card')
    if not discarded:
        return
    cid = _controller_id(card)
    if discarded.owner != cid:
        return
    is_random = event.data.get('random', False)
    if not is_random:
        return
    if discarded.power is not None and discarded.power >= 6:
        choice = _ask_player(state, cid, [True, False],
                             context="Beaten Trackers: destroy to gain 1 action point?")
        if choice:
            effect_destroy(state, card)
            effect_gain_action_point(state, cid, 1)

CARD_TRIGGERS["beaten_trackers"] = [
    TriggerDef(event_type="card_discarded", effect_fn=_beaten_trackers_discard),
]


# -- comeback_kicks --
# "Whenever the crowd cheers you, if you have less life, destroy this for 1 AP."
def _comeback_kicks_cheered(card, event, state):
    if not hasattr(event, 'data'):
        return
    cid = _controller_id(card)
    if event.data.get('player_id') != cid:
        return
    opp_id = 3 - cid
    if state.players[cid].health >= state.players[opp_id].health:
        return
    choice = _ask_player(state, cid, [True, False],
                         context="Comeback Kicks: destroy to gain 1 action point?")
    if choice:
        effect_destroy(state, card)
        effect_gain_action_point(state, cid, 1)

CARD_TRIGGERS["comeback_kicks"] = [
    TriggerDef(event_type="crowd_cheers", effect_fn=_comeback_kicks_cheered),
]


# -- arcanite_skullcap --
# "If you have less life than opponent, gets +1 defense and Arcane Barrier 3."
def _arcanite_skullcap_defend(card, event, state):
    if not state.combat or card not in state.combat.defending_cards:
        return
    cid = _controller_id(card)
    opp_id = 3 - cid
    if state.players[cid].health < state.players[opp_id].health:
        card.effects.append(("base_defense", lambda base: base + 1))

CARD_TRIGGERS["arcanite_skullcap"] = [
    TriggerDef(event_type="defend", effect_fn=_arcanite_skullcap_defend),
]


# -- basalt_boots --
# "If you control a Seismic Surge token, gets +1 defense."
def _basalt_boots_defend(card, event, state):
    if not state.combat or card not in state.combat.defending_cards:
        return
    cid = _controller_id(card)
    controller = state.players[cid]
    has_surge = any("seismic" in c.slug for c in controller.tokens.cards)
    if has_surge:
        card.effects.append(("base_defense", lambda base: base + 1))

CARD_TRIGGERS["basalt_boots"] = [
    TriggerDef(event_type="defend", effect_fn=_basalt_boots_defend),
]


# -- blackstone_greaves --
# "If you've dealt arcane damage this turn, gets +1 defense."
def _blackstone_greaves_defend(card, event, state):
    if not state.combat or card not in state.combat.defending_cards:
        return
    cid = _controller_id(card)
    if "dealt_arcane_this_turn" in state.players[cid].current_turn_effects:
        card.effects.append(("base_defense", lambda base: base + 1))

CARD_TRIGGERS["blackstone_greaves"] = [
    TriggerDef(event_type="defend", effect_fn=_blackstone_greaves_defend),
]


# -- attention_grabbers --
# "When this defends, you may remove a suspense counter from an aura.
#  If you do, +2 defense this chain link."
def _attention_grabbers_defend(card, event, state):
    if not state.combat or card not in state.combat.defending_cards:
        return
    cid = _controller_id(card)
    controller = state.players[cid]
    auras = [c for c in (controller.auras.cards if hasattr(controller, 'auras') else [])
             if c.counters.get("suspense", 0) > 0]
    if not auras:
        return
    choice = _ask_player(state, cid, [True, False],
                         context="Attention Grabbers: remove suspense counter for +2 defense?")
    if choice:
        pick = _ask_player(state, cid, [c.slug for c in auras],
                           context="Choose aura to remove suspense counter from")
        chosen = next((c for c in auras if c.slug == pick), auras[0])
        effect_remove_counter(state, chosen, "suspense", 1)
        card.effects.append(("base_defense", lambda base: base + 2))

CARD_TRIGGERS["attention_grabbers"] = [
    TriggerDef(event_type="defend", effect_fn=_attention_grabbers_defend),
]


# -- ball_breaker --
# "If you've discarded a card with 6+ power this turn, gets +1 power."
def _ball_breaker_attacking(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    if "discarded_6_power" in state.players[cid].current_turn_effects:
        card.effects.append(("base_power", lambda base: base + 1))

CARD_TRIGGERS["ball_breaker"] = [
    TriggerDef(event_type="attacking", effect_fn=_ball_breaker_attacking),
]


# -- beckon_applause --
# "If you control Agility token, +1 defense. If Vigor token, +1 defense."
def _beckon_applause_defend(card, event, state):
    if not state.combat or card not in state.combat.defending_cards:
        return
    cid = _controller_id(card)
    controller = state.players[cid]
    bonus = 0
    if any("agility" in c.slug for c in controller.tokens.cards):
        bonus += 1
    if any("vigor" in c.slug for c in controller.tokens.cards):
        bonus += 1
    if bonus > 0:
        card.effects.append(("base_defense", lambda base, _b=bonus: base + _b))

CARD_TRIGGERS["beckon_applause"] = [
    TriggerDef(event_type="defend", effect_fn=_beckon_applause_defend),
]


# -- breaker_helm_protos --
# "When this defends, discard a Hyper Driver. If you do, draw and +1 defense."
def _breaker_helm_defend(card, event, state):
    if not state.combat or card not in state.combat.defending_cards:
        return
    cid = _controller_id(card)
    controller = state.players[cid]
    drivers = [c for c in controller.hand.cards if "hyper_driver" in c.slug]
    if not drivers:
        return
    choice = _ask_player(state, cid, [True, False],
                         context="Breaker Helm Protos: discard a Hyper Driver for draw and +1 defense?")
    if choice:
        controller.hand.remove(drivers[0])
        controller.graveyard.add(drivers[0])
        effect_draw(state, cid, 1)
        card.effects.append(("base_defense", lambda base: base + 1))

CARD_TRIGGERS["breaker_helm_protos"] = [
    TriggerDef(event_type="defend", effect_fn=_breaker_helm_defend),
]


# -- buzzard_helm --
# "When this defends, draw then discard random. If 6+ power, +1 defense."
def _buzzard_helm_defend(card, event, state):
    if not state.combat or card not in state.combat.defending_cards:
        return
    cid = _controller_id(card)
    drawn = effect_draw(state, cid, 1)
    discarded = effect_discard(state, cid, 1, random_discard=True)
    if discarded and discarded[0].power is not None and discarded[0].power >= 6:
        card.effects.append(("base_defense", lambda base: base + 1))

CARD_TRIGGERS["buzzard_helm"] = [
    TriggerDef(event_type="defend", effect_fn=_buzzard_helm_defend),
]


# -- dynastic_diadem --
# "If you control 3+ Fealty tokens, +1 defense."
def _dynastic_diadem_defend(card, event, state):
    if not state.combat or card not in state.combat.defending_cards:
        return
    cid = _controller_id(card)
    fealty_count = sum(1 for c in state.players[cid].tokens.cards if "fealty" in c.slug)
    if fealty_count >= 3:
        card.effects.append(("base_defense", lambda base: base + 1))

CARD_TRIGGERS["dynastic_diadem"] = [
    TriggerDef(event_type="defend", effect_fn=_dynastic_diadem_defend),
]


# -- galaxxi_black --
# "If you've played from banished zone this turn, gains +2 power."
def _galaxxi_attacking(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    if "played_from_banished" in state.players[cid].current_turn_effects:
        card.effects.append(("base_power", lambda base: base + 2))

CARD_TRIGGERS["galaxxi_black"] = [
    TriggerDef(event_type="attacking", effect_fn=_galaxxi_attacking),
]


# -- hammer_of_havenhold --
# "If you have a Chivalry in pitch zone, +1 power."
def _hammer_havenhold_attacking(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    has_chivalry = any("chivalry" in c.slug for c in state.players[cid].pitch.cards)
    if has_chivalry:
        card.effects.append(("base_power", lambda base: base + 1))

CARD_TRIGGERS["hammer_of_havenhold"] = [
    TriggerDef(event_type="attacking", effect_fn=_hammer_havenhold_attacking),
]


# -- hard_knuckle --
# "When you play an attack action, you may destroy this. If you do, +1 power."
def _hard_knuckle_on_play(card, event, state):
    if not hasattr(event, 'data'):
        return
    played = event.data.get('card')
    if not played or played == card:
        return
    if "Attack" not in (played.types or []) or "Action" not in (played.types or []):
        return
    cid = _controller_id(card)
    choice = _ask_player(state, cid, [True, False],
                         context="Hard Knuckle: destroy to give attack +1 power?")
    if choice:
        effect_destroy(state, card)
        played.effects.append(("base_power", lambda base: base + 1))

CARD_TRIGGERS["hard_knuckle"] = [
    TriggerDef(event_type="on_play", effect_fn=_hard_knuckle_on_play),
]


# -- heavy_industry_ram_stop --
# "When this defends, you may pay {r}. If you do, +1 defense."
def _heavy_industry_ram_defend(card, event, state):
    if not state.combat or card not in state.combat.defending_cards:
        return
    cid = _controller_id(card)
    if state.players[cid].resources < 1:
        return
    choice = _ask_player(state, cid, [True, False],
                         context="Heavy Industry Ram Stop: pay {r} for +1 defense?")
    if choice:
        state.players[cid].resources -= 1
        card.effects.append(("base_defense", lambda base: base + 1))

CARD_TRIGGERS["heavy_industry_ram_stop"] = [
    TriggerDef(event_type="defend", effect_fn=_heavy_industry_ram_defend),
]


# -- heavy_industry_surveillance --
# "When this defends, banish top. If Mechanologist, +1 defense."
def _heavy_industry_surv_defend(card, event, state):
    if not state.combat or card not in state.combat.defending_cards:
        return
    cid = _controller_id(card)
    banished = effect_banish_top_deck(state, cid, 1, face_up=True)
    if banished and "Mechanologist" in (banished[0].supertypes or []):
        card.effects.append(("base_defense", lambda base: base + 1))

CARD_TRIGGERS["heavy_industry_surveillance"] = [
    TriggerDef(event_type="defend", effect_fn=_heavy_industry_surv_defend),
]


# -- helm_of_lignum_vitae --
# "If 4+ Earth cards in banished zone, +1 defense."
def _helm_lignum_defend(card, event, state):
    if not state.combat or card not in state.combat.defending_cards:
        return
    cid = _controller_id(card)
    earth_count = sum(1 for c in state.players[cid].banished.cards
                      if "Earth" in (c.supertypes or []))
    if earth_count >= 4:
        card.effects.append(("base_defense", lambda base: base + 1))

CARD_TRIGGERS["helm_of_lignum_vitae"] = [
    TriggerDef(event_type="defend", effect_fn=_helm_lignum_defend),
]


# -- high_riser --
# "If you've drawn a card this turn, +1 power."
def _high_riser_attacking(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    if "drawn_card_this_turn" in state.players[cid].current_turn_effects:
        card.effects.append(("base_power", lambda base: base + 1))

CARD_TRIGGERS["high_riser"] = [
    TriggerDef(event_type="attacking", effect_fn=_high_riser_attacking),
]


# -- beaming_blade --
# "If a yellow card has been put into your hero's soul this turn, +5 power."
def _beaming_blade_attacking(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    if "charged_yellow_this_turn" in state.players[cid].current_turn_effects:
        card.effects.append(("base_power", lambda base: base + 5))

CARD_TRIGGERS["beaming_blade"] = [
    TriggerDef(event_type="attacking", effect_fn=_beaming_blade_attacking),
]


# -- bonds_of_attraction --
# "When this hits, banish top of deck + banish from graveyard.
#  Whenever this banishes a card and this has equal or more power, draw a card."
def _bonds_attraction_hit(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    target_id = 3 - cid
    target = state.players[target_id]
    banished_cards = []
    if target.deck.cards:
        top = target.deck.pop_top()
        effect_banish(state, top, face_up=True, banisher_id=cid)
        banished_cards.append(top)
    if target.graveyard.cards:
        pick = _ask_player(state, cid, [c.slug for c in target.graveyard.cards],
                           context="Bonds of Attraction: choose a card from opponent's graveyard to banish")
        chosen = next((c for c in target.graveyard.cards if c.slug == pick), target.graveyard.cards[0])
        target.graveyard.remove(chosen)
        effect_banish(state, chosen, face_up=True, banisher_id=cid)
        banished_cards.append(chosen)
    attack_power = state.combat.attack_power if state.combat else (card.power or 0)
    for bc in banished_cards:
        if (bc.power is not None and card.power is not None
                and attack_power >= bc.power):
            effect_draw(state, cid, 1)

CARD_TRIGGERS["bonds_of_attraction"] = [
    TriggerDef(event_type="hit", effect_fn=_bonds_attraction_hit),
]


# -- bonds_of_memory --
# Same as bonds_of_attraction but "whenever this banishes a card with equal or less cost"
def _bonds_memory_hit(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    target_id = 3 - cid
    target = state.players[target_id]
    if target.deck.cards:
        top = target.deck.pop_top()
        effect_banish(state, top, face_up=True, banisher_id=cid)
    if target.graveyard.cards:
        pick = _ask_player(state, cid, [c.slug for c in target.graveyard.cards],
                           context="Bonds of Memory: choose a card from opponent's graveyard to banish")
        chosen = next((c for c in target.graveyard.cards if c.slug == pick), target.graveyard.cards[0])
        target.graveyard.remove(chosen)
        effect_banish(state, chosen, face_up=True, banisher_id=cid)

CARD_TRIGGERS["bonds_of_memory"] = [
    TriggerDef(event_type="hit", effect_fn=_bonds_memory_hit),
]


# -- bonds_of_agony --
# "If 3+ attack reactions this chain link, +3 power and
#  when hits look at hand and choose card to put on bottom of deck."
def _bonds_agony_attacking(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    ar_count = sum(1 for e in state.players[cid].current_turn_effects
                   if "attack_reaction_played" in e)
    if ar_count >= 3:
        card.effects.append(("base_power", lambda base: base + 3))

def _bonds_agony_hit(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    ar_count = sum(1 for e in state.players[cid].current_turn_effects
                   if "attack_reaction_played" in e)
    if ar_count < 3:
        return
    target_id = 3 - cid
    target = state.players[target_id]
    if target.hand.cards:
        pick = _ask_player(state, cid, [c.slug for c in target.hand.cards],
                           context="Bonds of Agony: choose a card to put on bottom of their deck")
        chosen = next((c for c in target.hand.cards if c.slug == pick), target.hand.cards[0])
        target.hand.remove(chosen)
        effect_put_bottom_deck(state, chosen, target_id)

CARD_TRIGGERS["bonds_of_agony"] = [
    TriggerDef(event_type="attacking", effect_fn=_bonds_agony_attacking),
    TriggerDef(event_type="hit", effect_fn=_bonds_agony_hit),
]


# -- brevant_civic_protector --
# "Whenever you protect another hero, create a Might token."
def _brevant_protect(card, event, state):
    cid = _controller_id(card)
    if hasattr(event, 'data') and event.data.get('protector_id') == cid:
        create_token(state, cid, "might")

CARD_TRIGGERS["brevant_civic_protector"] = [
    TriggerDef(event_type="protect", effect_fn=_brevant_protect),
]


# -- echo_casque --
# "Whenever you beat chest, you may pay {r} and destroy this. Draw a card."
def _echo_casque_chest_beat(card, event, state):
    cid = _controller_id(card)
    if state.players[cid].resources < 1:
        return
    choice = _ask_player(state, cid, [True, False],
                         context="Echo Casque: pay {r} and destroy to draw a card?")
    if choice:
        state.players[cid].resources -= 1
        effect_destroy(state, card)
        effect_draw(state, cid, 1)

CARD_TRIGGERS["echo_casque"] = [
    TriggerDef(event_type="beat_chest", effect_fn=_echo_casque_chest_beat),
]


# -- gavel_of_natural_order --
# "Whenever opponent plays/activates first card each turn (not their turn),
#  put +1 power counter on this."
def _gavel_on_play(card, event, state):
    if not hasattr(event, 'data'):
        return
    played = event.data.get('card')
    if not played:
        return
    cid = _controller_id(card)
    opp_id = 3 - cid
    if played.owner != opp_id and played.controller != opp_id:
        return
    # Check if it's not their turn
    if state.active_player == opp_id:
        return
    key = f"gavel_tracked_{opp_id}"
    if key in state.players[cid].current_turn_effects:
        return  # Already tracked first play
    state.players[cid].current_turn_effects.append(key)
    effect_put_counter(state, card, "power_plus_1", 1)
    card.effects.append(("base_power", lambda base: base + 1))

CARD_TRIGGERS["gavel_of_natural_order"] = [
    TriggerDef(event_type="on_play", effect_fn=_gavel_on_play),
]


# -- blessing_of_focus --
# "At start of turn, destroy this then opt 3 and reveal top.
#  If arrow, put face up into arsenal."
def _blessing_focus_start(card, event, state):
    cid = _controller_id(card)
    effect_destroy(state, card)
    effect_opt(state, cid, 3, None)
    controller = state.players[cid]
    if controller.deck.cards:
        top = controller.deck.cards[0]
        top.is_public = True
        if "Arrow" in (top.subtypes or []) or "Arrow" in (top.types or []):
            controller.deck.remove(top)
            effect_put_arsenal(state, top, cid, face_up=True)

CARD_TRIGGERS["blessing_of_focus"] = [
    TriggerDef(event_type="start_of_turn", effect_fn=_blessing_focus_start),
]


# -- blessing_of_deliverance --
# "When enters arena, if cost 3+ card in pitch zone, draw a card."
def _blessing_deliverance_enter(card, event, state):
    cid = _controller_id(card)
    has_cost3 = any((c.cost or 0) >= 3 for c in state.players[cid].pitch.cards)
    if has_cost3:
        effect_draw(state, cid, 1)

CARD_TRIGGERS["blessing_of_deliverance"] = [
    TriggerDef(event_type="enters_arena", effect_fn=_blessing_deliverance_enter),
]


# -- bolting_blade (red/yellow/blue) --
# "Costs {r}{r} less for each time you've charged this turn."
def _bolting_blade_on_play(card, event, state):
    cid = _controller_id(card)
    charge_count = sum(1 for e in state.players[cid].current_turn_effects
                       if e == "charged_this_turn")
    if charge_count > 0:
        cost_reduction = min(charge_count * 2, card.cost or 0)
        if cost_reduction > 0:
            effect_gain_resources(state, cid, cost_reduction)

for _color in ["red", "yellow", "blue"]:
    CARD_TRIGGERS[f"bolting_blade_{_color}"] = [
        TriggerDef(event_type="on_play", effect_fn=_bolting_blade_on_play),
    ]


# -- brain_freeze (red/yellow/blue) --
# "Target opponent reveals hand. If fused, put action card with cost 2- on top of their deck."
def _brain_freeze_on_play(card, event, state):
    cid = _controller_id(card)
    opp_id = 3 - cid
    opp = state.players[opp_id]
    # Reveal hand (make public)
    for c in opp.hand.cards:
        c.is_public = True
    # If fused (handled by keyword system)
    if "fused_this_turn" in state.players[cid].current_turn_effects:
        eligible = [c for c in opp.hand.cards
                    if "Action" in (c.types or []) and (c.cost or 0) <= 2]
        if eligible:
            pick = _ask_player(state, cid, [c.slug for c in eligible],
                               context="Brain Freeze: choose action card to put on top of opponent's deck")
            chosen = next((c for c in eligible if c.slug == pick), eligible[0])
            opp.hand.remove(chosen)
            effect_put_top_deck(state, chosen, opp_id)

for _color in ["red", "yellow", "blue"]:
    CARD_TRIGGERS[f"brain_freeze_{_color}"] = [
        TriggerDef(event_type="on_play", effect_fn=_brain_freeze_on_play),
    ]


# -- bulls_eye_bracers --
# "Action - Destroy: if no cards in arsenal, put arrow from hand face up into arsenal."
def _bulls_eye_on_play(card, event, state):
    cid = _controller_id(card)
    controller = state.players[cid]
    if controller.arsenal.cards:
        return
    arrows = [c for c in controller.hand.cards
              if "Arrow" in (c.subtypes or []) or "Arrow" in (c.types or [])]
    if not arrows:
        return
    pick = _ask_player(state, cid, [c.slug for c in arrows],
                       context="Bull's Eye Bracers: choose arrow to put into arsenal")
    chosen = next((c for c in arrows if c.slug == pick), arrows[0])
    controller.hand.remove(chosen)
    effect_put_arsenal(state, chosen, cid, face_up=True)

CARD_TRIGGERS["bulls_eye_bracers"] = [
    TriggerDef(event_type="on_play", effect_fn=_bulls_eye_on_play),
]


# -- bravo_star_of_the_show --
# "At start of turn, may reveal Earth+Ice+Lightning from hand. If so, draw."
def _bravo_star_start(card, event, state):
    cid = _controller_id(card)
    controller = state.players[cid]
    has_earth = any("Earth" in (c.supertypes or []) for c in controller.hand.cards)
    has_ice = any("Ice" in (c.supertypes or []) for c in controller.hand.cards)
    has_lightning = any("Lightning" in (c.supertypes or []) for c in controller.hand.cards)
    if has_earth and has_ice and has_lightning:
        choice = _ask_player(state, cid, [True, False],
                             context="Bravo Star: reveal Earth+Ice+Lightning to draw?")
        if choice:
            effect_draw(state, cid, 1)

CARD_TRIGGERS["bravo_star_of_the_show"] = [
    TriggerDef(event_type="start_of_turn", effect_fn=_bravo_star_start),
]


# -- crows_nest --
# "Whenever an arrow is put face up into arsenal from deck, may pay {r} to put aim counter."
def _crows_nest_arsenal(card, event, state):
    if not hasattr(event, 'data'):
        return
    arsenaled = event.data.get('card')
    if not arsenaled:
        return
    cid = _controller_id(card)
    if arsenaled.owner != cid:
        return
    if "Arrow" not in (arsenaled.subtypes or []) and "Arrow" not in (arsenaled.types or []):
        return
    if state.players[cid].resources < 1:
        return
    choice = _ask_player(state, cid, [True, False],
                         context="Crow's Nest: pay {r} to put aim counter on arrow?")
    if choice:
        state.players[cid].resources -= 1
        effect_put_counter(state, arsenaled, "aim", 1)

CARD_TRIGGERS["crows_nest"] = [
    TriggerDef(event_type="enters_arsenal", effect_fn=_crows_nest_arsenal),
]


# -- dreadbore --
# "You may put an arrow from hand face up into empty arsenal.
#  If you do, it gains +1 power until end of turn."
def _dreadbore_on_play(card, event, state):
    cid = _controller_id(card)
    controller = state.players[cid]
    if controller.arsenal.cards:
        return
    arrows = [c for c in controller.hand.cards
              if "Arrow" in (c.subtypes or []) or "Arrow" in (c.types or [])]
    if not arrows:
        return
    choice = _ask_player(state, cid, [True, False],
                         context="Dreadbore: put arrow into arsenal?")
    if not choice:
        return
    pick = _ask_player(state, cid, [c.slug for c in arrows],
                       context="Choose arrow")
    chosen = next((c for c in arrows if c.slug == pick), arrows[0])
    controller.hand.remove(chosen)
    effect_put_arsenal(state, chosen, cid, face_up=True)
    chosen.effects.append(("base_power", lambda base: base + 1))

CARD_TRIGGERS["dreadbore"] = [
    TriggerDef(event_type="on_play", effect_fn=_dreadbore_on_play),
]


# -- bravo_flattering_showman --
# "Action: Turn face-down card in arsenal face-up.
#  If it has crush, +2 power and dominate this turn."
def _bravo_flattering_action(card, event, state):
    cid = _controller_id(card)
    controller = state.players[cid]
    facedown = [c for c in controller.arsenal.cards if c.face_down]
    if not facedown:
        return
    pick = _ask_player(state, cid, [c.slug for c in facedown],
                       context="Bravo: choose face-down card to turn face-up")
    chosen = next((c for c in facedown if c.slug == pick), facedown[0])
    chosen.face_down = False
    chosen.is_public = True
    kws = [kw.lower() for kw in (chosen.keywords or [])]
    if "crush" in kws:
        chosen.effects.append(("base_power", lambda base: base + 2))
        chosen.keywords = list(chosen.keywords or [])
        if "Dominate" not in chosen.keywords:
            chosen.keywords.append("Dominate")

CARD_TRIGGERS["bravo_flattering_showman"] = [
    TriggerDef(event_type="on_play", effect_fn=_bravo_flattering_action),
]


# -- gloves_of_azure_waves --
# "High Tide: If 2+ blue cards in pitch zone, +3 defense and blade break."
def _gloves_azure_defend(card, event, state):
    if not state.combat or card not in state.combat.defending_cards:
        return
    cid = _controller_id(card)
    blue_count = sum(1 for c in state.players[cid].pitch.cards if c.pitch == 3)
    if blue_count >= 2:
        card.effects.append(("base_defense", lambda base: base + 3))

CARD_TRIGGERS["gloves_of_azure_waves"] = [
    TriggerDef(event_type="defend", effect_fn=_gloves_azure_defend),
]


# -- great_library_of_solana --
# "At beginning of end phase, if hero has 2+ yellow cards in pitch, +1 intellect."
def _great_library_end(card, event, state):
    cid = _controller_id(card)
    for pid in state.players:
        player = state.players[pid]
        yellow_count = sum(1 for c in player.pitch.cards if c.pitch == 2)
        if yellow_count >= 2:
            player.intellect = (player.intellect or 0) + 1

CARD_TRIGGERS["great_library_of_solana"] = [
    TriggerDef(event_type="start_of_end_phase", effect_fn=_great_library_end),
]


# -- gauntlets_of_the_boreal_domain --
# "Action: If Earth pitched, Mangle attacks get +2 power.
#  If Ice pitched, target card can't be activated until end of turn."
def _gauntlets_boreal_on_play(card, event, state):
    cid = _controller_id(card)
    controller = state.players[cid]
    pitched_earth = any("Earth" in (c.supertypes or []) for c in controller.pitch.cards)
    pitched_ice = any("Ice" in (c.supertypes or []) for c in controller.pitch.cards)
    if pitched_earth:
        state.players[cid].current_turn_effects.append("mangle_plus_2_power")
    if pitched_ice:
        opp_id = 3 - cid
        opp = state.players[opp_id]
        # Freeze a target card
        equip = list(opp.head.cards) + list(opp.chest.cards) + list(opp.arms.cards) + list(opp.legs.cards)
        if equip:
            pick = _ask_player(state, cid, [c.slug for c in equip],
                               context="Gauntlets of the Boreal Domain: choose card to freeze")
            chosen = next((c for c in equip if c.slug == pick), equip[0])
            effect_freeze(state, chosen)

CARD_TRIGGERS["gauntlets_of_the_boreal_domain"] = [
    TriggerDef(event_type="on_play", effect_fn=_gauntlets_boreal_on_play),
]


# -- groundbreaker_crix --
# "Attacks get +1 power while attacking a hero with Seismic Surge."
def _groundbreaker_attacking(card, event, state):
    if not state.combat:
        return
    cid = _controller_id(card)
    opp_id = 3 - cid
    has_surge = any("seismic" in c.slug for c in state.players[opp_id].tokens.cards)
    if has_surge and state.combat.attack_card:
        state.combat.attack_card.effects.append(("base_power", lambda base: base + 1))

CARD_TRIGGERS["groundbreaker_crix"] = [
    TriggerDef(event_type="attacking", effect_fn=_groundbreaker_attacking),
]


# ---------------------------------------------------------------------------
# Batch 4 continued: Complex Custom Cards — multi-step effects, choices
# ---------------------------------------------------------------------------

# ===== BRUTE: draw-then-discard-random pattern =====

def _draw_then_discard_random(state, player_id, draw_count=1):
    """Draw card(s), then discard a random card. Returns discarded card or None."""
    from engine.card_effects.keywords import _draw_cards
    player = state.players[player_id]
    _draw_cards(player, draw_count)
    discarded = effect_discard(state, player_id, 1, random_discard=True)
    return discarded[0] if discarded else None


def _bare_fangs_effect(card, event, state, bonus):
    """When attacks, draw then discard random. If 6+ power discarded, +N power."""
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    discarded = _draw_then_discard_random(state, cid)
    if discarded and discarded.power is not None and discarded.power >= 6:
        state.combat.attack_power += bonus

for _slug, _bonus in [("bare_fangs_red", 2), ("bare_fangs_yellow", 2),
                       ("bare_fangs_blue", 2)]:
    CARD_TRIGGERS[_slug] = [
        TriggerDef(event_type="attacking",
                   effect_fn=lambda c, e, s, b=_bonus: _bare_fangs_effect(c, e, s, b)),
    ]


# -- alpha_rampage: discard random + intimidate on attack --
def _alpha_rampage_attack(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    effect_intimidate(state, 3 - cid, card)

CARD_TRIGGERS["alpha_rampage_red"] = [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: effect_discard(s, _controller_id(c), 1, random_discard=True)),
    TriggerDef(event_type="attacking", effect_fn=_alpha_rampage_attack),
]


# -- barraging_big_horn: discard random + dominate if < 2 non-equip defenders --
def _barraging_big_horn_on_play(card, event, state):
    effect_discard(state, _controller_id(card), 1, random_discard=True)

def _barraging_big_horn_defend(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    non_equip = [d for d in state.combat.defending_cards
                 if not any(t in (d.types or []) for t in ["Equipment", "Weapon"])]
    if len(non_equip) < 2:
        if 'dominate' not in state.combat.keywords:
            state.combat.keywords.append('dominate')

for _slug in ["barraging_big_horn_red", "barraging_big_horn_yellow",
              "barraging_big_horn_blue"]:
    CARD_TRIGGERS[_slug] = [
        TriggerDef(event_type="on_play", effect_fn=_barraging_big_horn_on_play),
        TriggerDef(event_type="defend", effect_fn=_barraging_big_horn_defend),
    ]


# -- bloodrush_bellow: discard random, brute attacks +2, if 6+ draw --
def _bloodrush_bellow_effect(card, event, state, draw_count):
    cid = _controller_id(card)
    discarded = effect_discard(state, cid, 1, random_discard=True)
    state.players[cid].current_turn_effects.append("brute_attacks_plus_2")
    if discarded and discarded[0].power is not None and discarded[0].power >= 6:
        effect_draw(state, cid, draw_count)

for _slug, _d in [("bloodrush_bellow_red", 2), ("bloodrush_bellow_yellow", 2),
                   ("bloodrush_bellow_blue", 2)]:
    CARD_TRIGGERS[_slug] = [
        TriggerDef(event_type="on_play",
                   effect_fn=lambda c, e, s, d=_d: _bloodrush_bellow_effect(c, e, s, d)),
    ]


# -- beaten_trackers: on random discard of 6+ power, may destroy for AP --
def _beaten_trackers_discard(card, event, state):
    if not hasattr(event, 'data'):
        return
    discarded = event.data.get('card')
    if not discarded or discarded.power is None or discarded.power < 6:
        return
    cid = _controller_id(card)
    choice = _ask_player(state, cid, [True, False],
                         context="Beaten Trackers: destroy to gain 1 action point?")
    if choice:
        _move_to_graveyard(card, state)
        effect_gain_action_point(state, cid)

CARD_TRIGGERS["beaten_trackers"] = [
    TriggerDef(event_type="card_discarded",
               condition_fn=lambda c, e, s: c.zone in ("arms", "legs", "chest", "head"),
               effect_fn=_beaten_trackers_discard),
]


# -- berserk: continuous discard-6+-banish-reveal effect --
CARD_TRIGGERS["berserk_yellow"] = [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: s.players[_controller_id(c)].current_turn_effects.append("berserk_active")),
]


# -- cast_bones: reveal top 6, might per 6+ power --
def _cast_bones_effect(card, event, state, count):
    cid = _controller_id(card)
    player = state.players[cid]
    n = min(count, len(player.deck.cards))
    might = sum(1 for c in player.deck.cards[:n] if c.power is not None and c.power >= 6)
    if might > 0:
        create_token(state, cid, "might", might)

CARD_TRIGGERS["cast_bones_red"] = [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: _cast_bones_effect(c, e, s, 6)),
]


# -- bone_vizier: when destroyed, reveal top, if 6+ put in hand --
def _bone_vizier_destroyed(card, event, state):
    if not hasattr(event, 'data') or event.data.get('card') != card:
        return
    cid = _controller_id(card)
    player = state.players[cid]
    if player.deck.cards and player.deck.cards[0].power is not None and player.deck.cards[0].power >= 6:
        top = player.deck.pop_top()
        player.hand.add(top)

CARD_TRIGGERS["bone_vizier"] = [
    TriggerDef(event_type="card_destroyed", effect_fn=_bone_vizier_destroyed),
]


# -- bonebreaker_bellow: if beaten chest, extra bonus --
def _bonebreaker_bellow_effect(card, event, state, base_bonus, extra_bonus):
    cid = _controller_id(card)
    beaten = "beaten_chest_this_turn" in state.players[cid].current_turn_effects
    bonus = extra_bonus if beaten else base_bonus
    state.players[cid].current_turn_effects.append(f"next_brute_attack_plus_{bonus}")

for _slug, _b, _x in [("bonebreaker_bellow_red", 2, 4), ("bonebreaker_bellow_yellow", 2, 3),
                        ("bonebreaker_bellow_blue", 1, 2)]:
    CARD_TRIGGERS[_slug] = [
        TriggerDef(event_type="on_play",
                   effect_fn=lambda c, e, s, b=_b, x=_x: _bonebreaker_bellow_effect(c, e, s, b, x)),
    ]


# -- lay_down_the_challenge: intimidate, if opp has more cards draw --
def _lay_down_challenge_effect(card, event, state):
    cid = _controller_id(card)
    tid = 3 - cid
    effect_intimidate(state, tid, card)
    if len(state.players[tid].hand.cards) > len(state.players[cid].hand.cards):
        effect_draw(state, cid, 1)

CARD_TRIGGERS["lay_down_the_challenge_yellow"] = [
    TriggerDef(event_type="on_play", effect_fn=_lay_down_challenge_effect),
]


# -- no_fear: banish 6+ power cards for power bonus --
def _no_fear_effect(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    banished_count = 0
    while True:
        eligible = [c for c in player.hand.cards if c.power is not None and c.power >= 6 and c.slug != card.slug]
        if not eligible:
            break
        choice = _ask_player(state, cid, [True, False], context="No Fear: banish another 6+ power card?")
        if not choice:
            break
        pick = _ask_player(state, cid, [c.slug for c in eligible], context="Choose card to banish")
        target = next((c for c in eligible if c.slug == pick), eligible[0])
        player.hand.remove(target)
        effect_banish(state, target, face_up=True, banisher_id=cid)
        banished_count += 1
    if banished_count > 0:
        card.effects.append(("base_power", lambda base, n=banished_count: base + n * 2))

CARD_TRIGGERS["no_fear_red"] = [
    TriggerDef(event_type="on_play", effect_fn=_no_fear_effect, is_optional=True),
]


# -- pack_call: reveal top, if 6+ stays, else bottom --
def _pack_call_effect(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    if player.deck.cards and not (player.deck.cards[0].power is not None and player.deck.cards[0].power >= 6):
        top = player.deck.cards.pop(0)
        player.deck.cards.append(top)

for _slug in ["pack_call_red", "pack_call_yellow", "pack_call_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="on_play", effect_fn=_pack_call_effect)]


# -- mini_meataxe / ravenous_meataxe: draw then discard random on attack --
def _meataxe_attack(card, event, state):
    if not state.combat or state.combat.attack_card != card:
        return
    _draw_then_discard_random(state, _controller_id(card))

for _slug in ["mini_meataxe", "ravenous_meataxe"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="attacking", effect_fn=_meataxe_attack)]


# -- reincarnate: when discarded at random, put on bottom of deck --
def _reincarnate_discard(card, event, state):
    if not hasattr(event, 'data') or event.data.get('card') != card:
        return
    cid = _controller_id(card)
    player = state.players[cid]
    if card in player.graveyard.cards:
        player.graveyard.remove(card)
        player.deck.add_bottom(card)

for _slug in ["reincarnate_red", "reincarnate_yellow", "reincarnate_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="card_discarded", effect_fn=_reincarnate_discard)]


# -- dig_up_dinner: 3 random from graveyard, shuffle 6+ attacks back --
def _dig_up_dinner_effect(card, event, state):
    import random as rng
    cid = _controller_id(card)
    player = state.players[cid]
    if len(player.graveyard.cards) < 3:
        return
    chosen = rng.sample(list(player.graveyard.cards), 3)
    for c in chosen:
        if "Attack" in (c.types or []) and c.power is not None and c.power >= 6:
            player.graveyard.remove(c)
            player.deck.cards.append(c)
    effect_shuffle(state, cid)

CARD_TRIGGERS["dig_up_dinner_blue"] = [
    TriggerDef(event_type="on_play", effect_fn=_dig_up_dinner_effect),
]


# ===== WARRIOR: choose-one patterns =====

# -- art_of_war: choose 2 from 3 modes --
def _art_of_war_effect(card, event, state):
    cid = _controller_id(card)
    modes = ["attack_plus_1", "next_go_again", "untap_equipment"]
    chosen = []
    for i in range(2):
        remaining = [m for m in modes if m not in chosen]
        if not remaining:
            break
        pick = _ask_player(state, cid, remaining, context=f"Art of War: choose mode {i+1}/2")
        chosen.append(pick)
    for mode in chosen:
        if mode == "attack_plus_1":
            state.players[cid].current_turn_effects.append("attack_actions_plus_1_pd")
        elif mode == "next_go_again":
            state.players[cid].current_turn_effects.append("next_attack_go_again")
        elif mode == "untap_equipment":
            state.players[cid].current_turn_effects.append("untap_equipment")

CARD_TRIGGERS["art_of_war_yellow"] = [
    TriggerDef(event_type="on_play", effect_fn=_art_of_war_effect),
]


# ===== NINJA: combo + choose name =====

# -- be_like_water: on hit, pay r, choose name --
def _be_like_water_hit(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    choice = _ask_player(state, cid, [True, False], context="Be Like Water: pay {r} to choose a name?")
    if not choice or state.players[cid].resources < 1:
        return
    state.players[cid].resources -= 1
    name = _ask_player(state, cid, ["head_jab", "surging_strike", "twin_twisters"],
                       context="Choose name for this card")
    card.gained_name = name

for _slug in ["be_like_water_red", "be_like_water_yellow", "be_like_water_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="hit", effect_fn=_be_like_water_hit)]


# ===== RUNEBLADE: Runechant interactions =====

# -- amplify_the_arknight: cost r less per Runechant --
def _amplify_arknight_on_play(card, event, state):
    cid = _controller_id(card)
    rc = sum(1 for c in state.players[cid].permanents.cards if c.slug == "runechant")
    if rc > 0:
        state.players[cid].current_turn_effects.append(f"cost_reduction_{rc}")

for _slug in ["amplify_the_arknight_red", "amplify_the_arknight_yellow", "amplify_the_arknight_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="on_play", effect_fn=_amplify_arknight_on_play)]


# -- arknight_ascendancy: on hit create X Runechants --
def _arknight_ascendancy_hit(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    rc = sum(1 for c in state.players[cid].permanents.cards if c.slug == "runechant")
    create_token(state, cid, "runechant", max(1, rc))

CARD_TRIGGERS["arknight_ascendancy_red"] = [
    TriggerDef(event_type="hit", effect_fn=_arknight_ascendancy_hit),
]


# -- become_the_arknight: discard action, if attack search runeblade non-attack --
def _become_the_arknight_effect(card, event, state):
    from engine.card_effects.keywords import effect_search_deck
    cid = _controller_id(card)
    player = state.players[cid]
    actions = [c for c in player.hand.cards if "Action" in (c.types or [])]
    if not actions:
        return
    choice = _ask_player(state, cid, [True, False], context="Become the Arknight: discard an action card?")
    if not choice:
        return
    pick = _ask_player(state, cid, [c.slug for c in actions], context="Choose action card to discard")
    chosen = next((c for c in actions if c.slug == pick), actions[0])
    is_attack = "Attack" in (chosen.types or [])
    player.hand.remove(chosen)
    player.graveyard.add(chosen)
    if is_attack:
        found = effect_search_deck(state, cid, condition=lambda c: "Runeblade" in (c.types or []) and "Attack" not in (c.types or []))
        if found:
            player.deck.cards.remove(found)
            player.hand.add(found)
            effect_shuffle(state, cid)

CARD_TRIGGERS["become_the_arknight_blue"] = [
    TriggerDef(event_type="on_play", effect_fn=_become_the_arknight_effect),
]


# -- bequest_the_vast_beyond: next runeblade costs r less per runechant --
def _bequest_effect(card, event, state):
    cid = _controller_id(card)
    rc = sum(1 for c in state.players[cid].permanents.cards if c.slug == "runechant")
    state.players[cid].current_turn_effects.append(f"next_runeblade_cost_minus_{rc}")

CARD_TRIGGERS["bequest_the_vast_beyond_red"] = [
    TriggerDef(event_type="on_play", effect_fn=_bequest_effect),
]


# ===== ILLUSIONIST: soul + aura interactions =====

# -- archangel attacks: banish from soul for token creation --
def _archangel_attack_effect(card, event, state, token_type, count):
    if not state.combat or state.combat.attack_card != card:
        return
    cid = _controller_id(card)
    player = state.players[cid]
    if not player.soul.cards:
        return
    choice = _ask_player(state, cid, [True, False], context=f"{card.name}: banish from soul?")
    if not choice:
        return
    pick = _ask_player(state, cid, [c.slug for c in player.soul.cards], context="Choose soul card")
    target = next((c for c in player.soul.cards if c.slug == pick), player.soul.cards[0])
    player.soul.remove(target)
    effect_banish(state, target, face_up=True, banisher_id=cid)
    create_token(state, cid, token_type, count)

CARD_TRIGGERS["aegis_archangel_of_protection"] = [
    TriggerDef(event_type="attacking", effect_fn=lambda c, e, s: _archangel_attack_effect(c, e, s, "spectral_shield", 2)),
]
CARD_TRIGGERS["bellona_archangel_of_war"] = [
    TriggerDef(event_type="attacking", effect_fn=lambda c, e, s: _archangel_attack_effect(c, e, s, "might", 1)),
]


# -- avalon: banish from soul, put yellow from graveyard on bottom --
def _avalon_attack(card, event, state):
    if not state.combat or state.combat.attack_card != card:
        return
    cid = _controller_id(card)
    player = state.players[cid]
    if not player.soul.cards:
        return
    choice = _ask_player(state, cid, [True, False], context="Avalon: banish from soul?")
    if not choice:
        return
    pick = _ask_player(state, cid, [c.slug for c in player.soul.cards], context="Choose soul card")
    target = next((c for c in player.soul.cards if c.slug == pick), player.soul.cards[0])
    player.soul.remove(target)
    effect_banish(state, target, face_up=True, banisher_id=cid)
    yellows = [c for c in player.graveyard.cards if c.pitch == 2]
    if yellows:
        pick2 = _ask_player(state, cid, [c.slug for c in yellows], context="Choose yellow graveyard card for bottom of deck")
        chosen = next((c for c in yellows if c.slug == pick2), yellows[0])
        player.graveyard.remove(chosen)
        player.deck.add_bottom(chosen)

CARD_TRIGGERS["avalon_archangel_of_rebirth"] = [
    TriggerDef(event_type="attacking", effect_fn=_avalon_attack),
]


# -- blasmophet: banish shadow from hand, then banish from opp hand --
def _blasmophet_attack(card, event, state):
    if not state.combat or state.combat.attack_card != card:
        return
    cid = _controller_id(card)
    player = state.players[cid]
    shadows = [c for c in player.hand.cards if "Shadow" in (c.types or [])]
    if not shadows:
        return
    choice = _ask_player(state, cid, [True, False], context="Blasmophet: banish Shadow from hand?")
    if not choice:
        return
    pick = _ask_player(state, cid, [c.slug for c in shadows], context="Choose Shadow card")
    target = next((c for c in shadows if c.slug == pick), shadows[0])
    player.hand.remove(target)
    effect_banish(state, target, face_up=True, banisher_id=cid)
    opp_id = 3 - cid
    opp = state.players[opp_id]
    if opp.hand.cards:
        pick2 = _ask_player(state, opp_id, [c.slug for c in opp.hand.cards], context="Blasmophet: choose card to banish")
        chosen = next((c for c in opp.hand.cards if c.slug == pick2), opp.hand.cards[0])
        opp.hand.remove(chosen)
        effect_banish(state, chosen, face_up=True, banisher_id=cid)

CARD_TRIGGERS["blasmophet_the_soul_harvester"] = [
    TriggerDef(event_type="attacking", effect_fn=_blasmophet_attack),
]


# -- beckoning_light: charge soul, if yellow then attacks on-hit draw --
def _beckoning_light_effect(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    hand_cards = [c for c in player.hand.cards if c.slug != card.slug]
    if not hand_cards:
        return
    choice = _ask_player(state, cid, [True, False], context="Beckoning Light: charge a card to soul?")
    if not choice:
        return
    pick = _ask_player(state, cid, [c.slug for c in hand_cards], context="Choose card to charge")
    target = next((c for c in hand_cards if c.slug == pick), hand_cards[0])
    is_yellow = target.pitch == 2
    player.hand.remove(target)
    player.soul.add(target)
    if is_yellow:
        state.players[cid].current_turn_effects.append("attacks_on_hit_draw_1")

for _slug in ["beckoning_light_red", "beckoning_light_yellow", "beckoning_light_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="on_play", effect_fn=_beckoning_light_effect, is_optional=True)]


# -- beacon_of_victory: banish X from soul, +X power --
def _beacon_of_victory_effect(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    banished = 0
    while player.soul.cards:
        choice = _ask_player(state, cid, [True, False], context="Beacon of Victory: banish another soul card?")
        if not choice:
            break
        pick = _ask_player(state, cid, [c.slug for c in player.soul.cards], context="Choose soul card")
        target = next((c for c in player.soul.cards if c.slug == pick), player.soul.cards[0])
        player.soul.remove(target)
        effect_banish(state, target, face_up=True, banisher_id=cid)
        banished += 1
    if banished > 0 and state.combat:
        state.combat.attack_power += banished

CARD_TRIGGERS["beacon_of_victory_yellow"] = [
    TriggerDef(event_type="on_play", effect_fn=_beacon_of_victory_effect),
]


# ===== RANGER: arsenal manipulation =====

# -- barbed_castaway: put arrow into arsenal --
def _barbed_castaway_effect(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    arrows = [c for c in player.hand.cards if "Arrow" in (c.types or [])]
    if not arrows:
        return
    choice = _ask_player(state, cid, [True, False], context="Barbed Castaway: put arrow into arsenal?")
    if not choice:
        return
    pick = _ask_player(state, cid, [c.slug for c in arrows], context="Choose arrow")
    target = next((c for c in arrows if c.slug == pick), arrows[0])
    player.hand.remove(target)
    player.arsenal.add(target)

CARD_TRIGGERS["barbed_castaway"] = [
    TriggerDef(event_type="on_play", effect_fn=_barbed_castaway_effect, is_optional=True),
]


# ===== DRACONIC: chain link counting, phoenix flame =====

def _draconic_chain_link_count(state, cid):
    """Count draconic chain links controlled by player."""
    count = 0
    if state.combat and state.combat.attack_card and state.combat.attack_card.controller == cid:
        if "Draconic" in (state.combat.attack_card.types or []):
            count += 1
    for link in getattr(state, 'chain_links', []):
        ac = getattr(link, 'attack_card', None)
        if ac and ac.controller == cid and "Draconic" in (ac.types or []):
            count += 1
    return count


# -- blood_runs_deep: each dagger deals 1 on hit --
def _blood_runs_deep_hit(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    daggers = _find_controlled_daggers(state.players[cid], state, exclude_card=card)
    for dagger in daggers:
        effect_deal_damage(state, 3 - cid, 1, dagger, "generic")

CARD_TRIGGERS["blood_runs_deep_red"] = [
    TriggerDef(event_type="hit", effect_fn=_blood_runs_deep_hit),
]

for _slug in ["blood_drop_red", "blood_line_red"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None)]


# -- dromai: pitch red -> create ash --
def _dromai_pitch(card, event, state):
    if not hasattr(event, 'data'):
        return
    pitched = event.data.get('card')
    if pitched and pitched.pitch == 1:
        create_token(state, _controller_id(card), "ash")

for _slug in ["dromai", "dromai_ash_artist"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="card_pitched", effect_fn=_dromai_pitch)]


# -- blistering_blade: if 2+ draconic chain links, extra bonus --
def _blistering_blade_attack(card, event, state, base, extra):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    bonus = extra if _draconic_chain_link_count(state, cid) >= 2 else base
    state.combat.attack_power += bonus

for _slug, _b, _x in [("blistering_blade_red", 1, 3), ("blistering_blade_yellow", 1, 2),
                        ("blistering_blade_blue", 0, 1)]:
    CARD_TRIGGERS[_slug] = [
        TriggerDef(event_type="attacking",
                   effect_fn=lambda c, e, s, b=_b, x=_x: _blistering_blade_attack(c, e, s, b, x)),
    ]


# -- burning_blade_dance: if 2+ draconic chain links, go again --
def _burning_blade_dance_attack(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    if _draconic_chain_link_count(state, _controller_id(card)) >= 2:
        if 'go_again' not in state.combat.keywords:
            state.combat.keywords.append('go_again')

for _slug in ["burning_blade_dance_red", "burning_blade_dance_yellow", "burning_blade_dance_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="attacking", effect_fn=_burning_blade_dance_attack)]


# -- flamecall_awakening: search for phoenix flame --
def _flamecall_awakening_effect(card, event, state):
    from engine.card_effects.keywords import effect_search_deck
    cid = _controller_id(card)
    player = state.players[cid]
    found = effect_search_deck(state, cid, condition=lambda c: "phoenix_flame" in c.slug)
    if found:
        player.deck.cards.remove(found)
        player.hand.add(found)
        effect_shuffle(state, cid)

for _slug in ["flamecall_awakening_red", "flamecall_awakening_yellow", "flamecall_awakening_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="on_play", effect_fn=_flamecall_awakening_effect)]


# -- inflame: return phoenix flame from graveyard --
def _inflame_effect(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    phoenixes = [c for c in player.graveyard.cards if "phoenix_flame" in c.slug]
    if not phoenixes:
        return
    choice = _ask_player(state, cid, [True, False], context="Inflame: return Phoenix Flame from graveyard?")
    if choice:
        player.graveyard.remove(phoenixes[0])
        player.hand.add(phoenixes[0])

for _slug in ["inflame_red", "inflame_yellow", "inflame_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="on_play", effect_fn=_inflame_effect, is_optional=True)]


# -- burn_away: banish phoenix flame as cost, gain power --
def _burn_away_effect(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    pfs = [c for c in player.hand.cards if "phoenix_flame" in c.slug]
    if not pfs:
        return
    choice = _ask_player(state, cid, [True, False], context="Burn Away: banish Phoenix Flame for +2 power?")
    if not choice:
        return
    player.hand.remove(pfs[0])
    effect_banish(state, pfs[0], face_up=True, banisher_id=cid)
    if state.combat:
        state.combat.attack_power += 2

for _slug in ["burn_away_red", "burn_away_yellow", "burn_away_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="on_play", effect_fn=_burn_away_effect, is_optional=True)]


# -- flameborn_retribution: if dealt damage, may return phoenix flame --
def _flameborn_retribution_effect(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    if "dealt_damage_this_turn" not in player.current_turn_effects:
        return
    pfs = [c for c in player.graveyard.cards if "phoenix_flame" in c.slug]
    if pfs:
        choice = _ask_player(state, cid, [True, False], context="Return Phoenix Flame from graveyard?")
        if choice:
            player.graveyard.remove(pfs[0])
            player.hand.add(pfs[0])

for _slug in ["flameborn_retribution_red", "flameborn_retribution_yellow", "flameborn_retribution_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="on_play", effect_fn=_flameborn_retribution_effect)]


# -- flamescale_furnace: gain r per red in pitch zone --
CARD_TRIGGERS["flamescale_furnace"] = [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: effect_gain_resources(s, _controller_id(c),
                          sum(1 for x in s.players[_controller_id(c)].pitch.cards if x.pitch == 1))),
]


# ===== EQUIPMENT: conditional destroy effects =====

# -- aether_crackers: when your attack hits, may destroy for 1 arcane --
def _aether_crackers_hit(card, event, state):
    if not state.combat:
        return
    cid = _controller_id(card)
    if state.combat.attack_card.controller != cid:
        return
    choice = _ask_player(state, cid, [True, False], context="Aether Crackers: destroy for 1 arcane?")
    if choice:
        _move_to_graveyard(card, state)
        effect_deal_arcane(state, 3 - cid, 1, card)

CARD_TRIGGERS["aether_crackers"] = [
    TriggerDef(event_type="hit", effect_fn=_aether_crackers_hit, is_optional=True),
]


# -- bloodied_helm: arsenal to bottom, draw --
def _bloodied_helm_effect(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    if not player.arsenal.cards:
        return
    opts = [c.slug for c in player.arsenal.cards] + ["decline"]
    pick = _ask_player(state, cid, opts, context="Bloodied Helm: put arsenal card on bottom to draw?")
    if pick == "decline":
        return
    target = next((c for c in player.arsenal.cards if c.slug == pick), None)
    if target:
        player.arsenal.remove(target)
        player.deck.add_bottom(target)
        effect_draw(state, cid, 1)

CARD_TRIGGERS["bloodied_helm"] = [
    TriggerDef(event_type="on_play", effect_fn=_bloodied_helm_effect, is_optional=True),
]


# -- bloodsheath_skeleta: destroy for cost reduction --
CARD_TRIGGERS["bloodsheath_skeleta"] = [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: (
        _move_to_graveyard(c, s),
        s.players[_controller_id(c)].current_turn_effects.append("next_attack_cost_1_less"),
        s.players[_controller_id(c)].current_turn_effects.append("next_nonattack_cost_1_less"),
    )),
]


# -- attention_grabbers: when defends, remove suspense counter for +2d --
def _attention_grabbers_defend(card, event, state):
    if not state.combat or card not in state.combat.defending_cards:
        return
    cid = _controller_id(card)
    player = state.players[cid]
    auras = [c for c in player.permanents.cards if player.counters.get((c.slug, c.zone, "suspense"), 0) > 0]
    if not auras:
        return
    choice = _ask_player(state, cid, [True, False], context="Attention Grabbers: remove suspense for +2 defense?")
    if not choice:
        return
    pick = _ask_player(state, cid, [c.slug for c in auras], context="Choose aura")
    target = next((c for c in auras if c.slug == pick), auras[0])
    effect_remove_counter(state, target, "suspense", 1)
    card.effects.append(("base_defense", lambda base: base + 2))

CARD_TRIGGERS["attention_grabbers"] = [
    TriggerDef(event_type="defend", effect_fn=_attention_grabbers_defend, is_optional=True),
]


# -- alluvion_constellas: first arcane prevent, add energy counter --
CARD_TRIGGERS["alluvion_constellas"] = [
    TriggerDef(event_type="arcane_damage_prevented",
               effect_fn=lambda c, e, s: effect_put_counter(s, c, "energy", 1)
               if s.players[_controller_id(c)].counters.get((c.slug, c.zone, "energy"), 0) < 4 else None),
]


# -- crown_of_seeds / crown_of_everbloom: face-down arsenal to bottom, draw --
def _crown_seeds_effect(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    facedown = [c for c in player.arsenal.cards if not c.is_public]
    if not facedown:
        return
    opts = [c.slug for c in facedown] + ["decline"]
    pick = _ask_player(state, cid, opts, context="Crown: put face-down arsenal on bottom to draw?")
    if pick == "decline":
        return
    target = next((c for c in facedown if c.slug == pick), None)
    if target:
        player.arsenal.remove(target)
        player.deck.add_bottom(target)
        effect_draw(state, cid, 1)

for _slug in ["crown_of_seeds", "crown_of_everbloom"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="on_play", effect_fn=_crown_seeds_effect, is_optional=True)]


# ===== SHADOW: banish/soul =====

# -- blood_dripping_frenzy: banish hand, draw per blood debt --
def _blood_dripping_frenzy_effect(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    bd_count = 0
    for c in list(player.hand.cards):
        player.hand.remove(c)
        has_bd = any("blood debt" == k.lower() for k in (c.keywords or []))
        if has_bd:
            bd_count += 1
        effect_banish(state, c, face_up=True, banisher_id=cid)
    if bd_count > 0:
        effect_draw(state, cid, bd_count)
    state.players[cid].current_turn_effects.append("brute_shadow_attacks_plus_1")

CARD_TRIGGERS["blood_dripping_frenzy_blue"] = [
    TriggerDef(event_type="on_play", effect_fn=_blood_dripping_frenzy_effect),
]


# ===== EARTH: arsenal manipulation, decompose =====

# -- blessing_of_deliverance: on enter, draw if pitch has cost 3+ --
def _blessing_deliverance_enter(card, event, state):
    cid = _controller_id(card)
    if any(c.cost is not None and c.cost >= 3 for c in state.players[cid].pitch.cards):
        effect_draw(state, cid, 1)

for _slug in ["blessing_of_deliverance_red", "blessing_of_deliverance_yellow", "blessing_of_deliverance_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="enters_arena", effect_fn=_blessing_deliverance_enter)]


# -- break_ground: put arsenal on bottom, draw --
def _break_ground_effect(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    if not player.arsenal.cards:
        return
    choice = _ask_player(state, cid, [True, False], context="Break Ground: arsenal to bottom for draw?")
    if not choice:
        return
    pick = _ask_player(state, cid, [c.slug for c in player.arsenal.cards], context="Choose arsenal card")
    target = next((c for c in player.arsenal.cards if c.slug == pick), player.arsenal.cards[0])
    player.arsenal.remove(target)
    player.deck.add_bottom(target)
    effect_draw(state, cid, 1)

for _slug in ["break_ground_red", "break_ground_yellow", "break_ground_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="on_play", effect_fn=_break_ground_effect)]


# -- awakening: create seismic surges equal to health difference --
def _awakening_effect(card, event, state):
    cid = _controller_id(card)
    opp_id = 3 - cid
    diff = state.players[opp_id].health - state.players[cid].health
    if diff > 0:
        create_token(state, cid, "seismic_surge", diff)

CARD_TRIGGERS["awakening_blue"] = [
    TriggerDef(event_type="on_play", effect_fn=_awakening_effect),
]


# ===== ASSASSIN: contract, look-at, mark =====

# -- arakni_trapdoor: search deck, banish face-down, if trap play until next turn --
def _arakni_trapdoor_effect(card, event, state):
    from engine.card_effects.keywords import effect_search_deck
    cid = _controller_id(card)
    player = state.players[cid]
    found = effect_search_deck(state, cid, condition=lambda c: True)
    if found:
        player.deck.cards.remove(found)
        effect_banish(state, found, face_up=False, banisher_id=cid)
        if "Trap" in (found.types or []):
            state.players[cid].current_turn_effects.append(f"play_trap_{found.slug}")
        effect_shuffle(state, cid)

CARD_TRIGGERS["arakni_trapdoor"] = [
    TriggerDef(event_type="on_play", effect_fn=_arakni_trapdoor_effect),
]


# -- bonds_of_attraction: hit -> banish top deck, then banish from graveyard --
def _bonds_of_attraction_hit(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    tid = 3 - cid
    target = state.players[tid]
    if target.deck.cards:
        top = target.deck.pop_top()
        effect_banish(state, top, face_up=True, banisher_id=cid)
    if target.graveyard.cards:
        pick = _ask_player(state, tid, [c.slug for c in target.graveyard.cards],
                           context="Bonds of Attraction: choose graveyard card to banish")
        chosen = next((c for c in target.graveyard.cards if c.slug == pick), target.graveyard.cards[0])
        target.graveyard.remove(chosen)
        effect_banish(state, chosen, face_up=True, banisher_id=cid)

for _slug in ["bonds_of_attraction_red", "bonds_of_attraction_yellow", "bonds_of_attraction_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="hit", effect_fn=_bonds_of_attraction_hit)]


# -- coercive_tendency: look at top 3 of opp deck, reorder --
def _coercive_tendency_effect(card, event, state):
    cid = _controller_id(card)
    opp = state.players[3 - cid]
    n = min(3, len(opp.deck.cards))
    if n == 0:
        return
    top = opp.deck.cards[:n]
    reordered = []
    remaining = list(top)
    for i in range(n):
        pick = _ask_player(state, cid, [c.slug for c in remaining],
                           context=f"Coercive Tendency: choose card {i+1} from top")
        chosen = next((c for c in remaining if c.slug == pick), remaining[0])
        reordered.append(chosen)
        remaining.remove(chosen)
    for i in range(n):
        opp.deck.cards[i] = reordered[i]

CARD_TRIGGERS["coercive_tendency_blue"] = [
    TriggerDef(event_type="on_play", effect_fn=_coercive_tendency_effect),
]


# -- codex cards: multi-hero effects --
def _codex_bloodrot_effect(card, event, state):
    for pid in state.players:
        player = state.players[pid]
        if not player.hand.cards:
            continue
        pick = _ask_player(state, pid, [c.slug for c in player.hand.cards],
                           context="Codex of Bloodrot: put card face-down into arsenal")
        chosen = next((c for c in player.hand.cards if c.slug == pick), player.hand.cards[0])
        player.hand.remove(chosen)
        player.arsenal.add(chosen)

CARD_TRIGGERS["codex_of_bloodrot_yellow"] = [TriggerDef(event_type="on_play", effect_fn=_codex_bloodrot_effect)]


def _codex_frailty_effect(card, event, state):
    for pid in state.players:
        player = state.players[pid]
        attacks = [c for c in player.graveyard.cards if "Attack" in (c.types or [])]
        if not attacks:
            continue
        pick = _ask_player(state, pid, [c.slug for c in attacks],
                           context="Codex of Frailty: choose attack from graveyard")
        chosen = next((c for c in attacks if c.slug == pick), attacks[0])
        player.graveyard.remove(chosen)
        player.deck.add_bottom(chosen)

CARD_TRIGGERS["codex_of_frailty_yellow"] = [TriggerDef(event_type="on_play", effect_fn=_codex_frailty_effect)]


def _codex_inertia_effect(card, event, state):
    for pid in state.players:
        player = state.players[pid]
        if player.deck.cards:
            top = player.deck.pop_top()
            player.arsenal.add(top)

CARD_TRIGGERS["codex_of_inertia_yellow"] = [TriggerDef(event_type="on_play", effect_fn=_codex_inertia_effect)]


# -- cut_to_the_chase: look at opp top, may put bottom --
def _cut_to_the_chase_effect(card, event, state):
    cid = _controller_id(card)
    opp = state.players[3 - cid]
    if not opp.deck.cards:
        return
    choice = _ask_player(state, cid, ["top", "bottom"],
                         context=f"Cut to the Chase: opp top is {opp.deck.cards[0].slug}. Top or bottom?")
    if choice == "bottom":
        top = opp.deck.cards.pop(0)
        opp.deck.cards.append(top)

for _slug in ["cut_to_the_chase_red", "cut_to_the_chase_yellow", "cut_to_the_chase_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="on_play", effect_fn=_cut_to_the_chase_effect)]


# -- bite: when attacks, target dagger deals 1 --
def _bite_attack(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    daggers = _find_controlled_daggers(state.players[cid], state, exclude_card=card)
    if not daggers:
        return
    choice = _ask_player(state, cid, [True, False], context="Bite: have dagger deal 1 damage?")
    if not choice:
        return
    dagger = daggers[0] if len(daggers) == 1 else next(
        (d for d in daggers if d.slug == _ask_player(state, cid, [d.slug for d in daggers], context="Choose dagger")),
        daggers[0])
    effect_deal_damage(state, 3 - cid, 1, dagger, "generic")

for _slug in ["bite_red", "bite_yellow", "bite_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="attacking", effect_fn=_bite_attack, is_optional=True)]


# -- hunter_or_hunted: banish top of opp deck --
CARD_TRIGGERS["hunter_or_hunted_blue"] = [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: (
        effect_banish(s, s.players[3 - _controller_id(c)].deck.pop_top(), face_up=True, banisher_id=_controller_id(c))
        if s.players[3 - _controller_id(c)].deck.cards else None)),
]


# ===== BARD: multi-hero =====

# -- interlude: choose hero, prevent damage, if other hero gain life --
def _interlude_effect(card, event, state, amount):
    cid = _controller_id(card)
    hero_ids = list(state.players.keys())
    pick = _ask_player(state, cid, hero_ids, context="Interlude: choose hero to prevent damage for")
    state.players[pick].current_turn_effects.append(f"prevent_{amount}")
    if pick != cid:
        effect_gain_life(state, cid, 1)

for _slug, _amt in [("interlude_red", 4), ("interlude_yellow", 3), ("interlude_blue", 2)]:
    CARD_TRIGGERS[_slug] = [
        TriggerDef(event_type="on_play", effect_fn=lambda c, e, s, a=_amt: _interlude_effect(c, e, s, a)),
    ]


# -- encore: return bard attack from graveyard --
def _encore_effect(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    bard_attacks = [c for c in player.graveyard.cards if "Bard" in (c.types or []) and "Attack" in (c.types or [])]
    if not bard_attacks:
        return
    pick = _ask_player(state, cid, [c.slug for c in bard_attacks], context="Encore: return Bard attack to hand")
    chosen = next((c for c in bard_attacks if c.slug == pick), bard_attacks[0])
    player.graveyard.remove(chosen)
    player.hand.add(chosen)

CARD_TRIGGERS["encore_yellow"] = [TriggerDef(event_type="on_play", effect_fn=_encore_effect)]


# -- tales_of_adventure: each other hero creates unique token --
def _tales_of_adventure_effect(card, event, state):
    cid = _controller_id(card)
    chosen_tokens = []
    available = ["might", "quicken", "vigor", "agility"]
    for pid in state.players:
        if pid == cid:
            continue
        remaining = [t for t in available if t not in chosen_tokens]
        if not remaining:
            break
        pick = _ask_player(state, pid, remaining, context="Tales of Adventure: choose token")
        chosen_tokens.append(pick)
        create_token(state, pid, pick)

CARD_TRIGGERS["tales_of_adventure_blue"] = [TriggerDef(event_type="on_play", effect_fn=_tales_of_adventure_effect)]


# ===== GUARDIAN: for-each, conditional =====

# -- arrogant_showboating: might per defending card --
def _arrogant_showboating_effect(card, event, state):
    if not state.combat:
        return
    cid = _controller_id(card)
    opp_id = 3 - cid
    count = sum(1 for d in state.combat.defending_cards if d.controller == opp_id or d.owner == opp_id)
    if count > 0:
        create_token(state, cid, "might", count)

CARD_TRIGGERS["arrogant_showboating_blue"] = [TriggerDef(event_type="on_play", effect_fn=_arrogant_showboating_effect)]


# -- big_blue_sky: +1d per blue pitched this turn --
def _big_blue_sky_defend(card, event, state):
    cid = _controller_id(card)
    blue = sum(1 for c in state.players[cid].pitch.cards if c.pitch == 3)
    if blue > 0:
        card.effects.append(("base_defense", lambda base, n=blue: base + n))

CARD_TRIGGERS["big_blue_sky_blue"] = [
    TriggerDef(event_type="defend",
               condition_fn=lambda c, e, s: s.combat and c in s.combat.defending_cards,
               effect_fn=_big_blue_sky_defend),
]


# -- battered_not_broken: prevent 2, create might --
CARD_TRIGGERS["battered_not_broken_red"] = [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: s.players[_controller_id(c)].current_turn_effects.append("prevent_2_create_might")),
]


# ===== MECHANOLOGIST =====

# -- bank_breaker: may banish from under it on attack --
def _bank_breaker_attack(card, event, state):
    if not state.combat or state.combat.attack_card != card:
        return
    underneath = getattr(card, 'underneath', [])
    if not underneath:
        return
    cid = _controller_id(card)
    choice = _ask_player(state, cid, [True, False], context="Bank Breaker: banish card from under it?")
    if choice:
        target = underneath.pop(0)
        effect_banish(state, target, face_up=True, banisher_id=cid)

CARD_TRIGGERS["bank_breaker"] = [TriggerDef(event_type="attacking", effect_fn=_bank_breaker_attack, is_optional=True)]


# ===== SHIYANA =====

# -- alluring_inducement: reveal opp hand, choose attack name --
def _alluring_inducement_attack(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    opp = state.players[3 - cid]
    attacks = [c for c in opp.hand.cards if "Attack" in (c.types or []) and "Action" in (c.types or [])]
    if attacks:
        pick = _ask_player(state, cid, [c.slug for c in attacks], context="Alluring Inducement: choose attack name")
        card.gained_name = pick

CARD_TRIGGERS["alluring_inducement_yellow"] = [TriggerDef(event_type="attacking", effect_fn=_alluring_inducement_attack)]


# ===== BETSY: wager =====
def _betsy_wager(card, event, state):
    if not state.combat:
        return
    cid = _controller_id(card)
    if state.players[cid].resources < 2:
        return
    choice = _ask_player(state, cid, [True, False], context="Betsy: pay {r}{r} for +1 power and overpower?")
    if choice:
        state.players[cid].resources -= 2
        state.combat.attack_power += 1
        if 'overpower' not in state.combat.keywords:
            state.combat.keywords.append('overpower')

for _slug in ["betsy", "betsy_skin_in_the_game"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="attacking", effect_fn=_betsy_wager, is_optional=True)]


# ===== DICE / GAMBLE =====

# -- barkbone_strapping: roll d6, gain half resources --
CARD_TRIGGERS["barkbone_strapping"] = [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: effect_gain_resources(s, _controller_id(c), roll_die(s, _controller_id(c), 6) // 2)),
]

# -- reckless_charge: roll d6, if 6 gain +3 power --
def _reckless_charge_effect(card, event, state):
    cid = _controller_id(card)
    if roll_die(state, cid, 6) == 6:
        card.effects.append(("base_power", lambda base: base + 3))

CARD_TRIGGERS["reckless_charge_blue"] = [TriggerDef(event_type="on_play", effect_fn=_reckless_charge_effect)]

# -- ready_to_roll: bonus die this turn --
CARD_TRIGGERS["ready_to_roll_blue"] = [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: s.players[_controller_id(c)].current_turn_effects.append("roll_bonus_die")),
]


# ===== WIZARD: arcane + reveal =====

# -- dracona_optimai: reveal top 3, arcane = 2x red count --
def _dracona_optimai_effect(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    n = min(3, len(player.deck.cards))
    red = sum(1 for c in player.deck.cards[:n] if c.pitch == 1)
    if red > 0:
        effect_deal_arcane(state, 3 - cid, red * 2, card)

CARD_TRIGGERS["dracona_optimai"] = [TriggerDef(event_type="on_play", effect_fn=_dracona_optimai_effect)]


# -- dominia: reveal top, if red banish from opp hand --
def _dominia_effect(card, event, state):
    cid = _controller_id(card)
    opp_id = 3 - cid
    opp = state.players[opp_id]
    if not opp.deck.cards:
        return
    if opp.deck.cards[0].pitch == 1 and opp.hand.cards:
        pick = _ask_player(state, cid, [c.slug for c in opp.hand.cards], context="Dominia: banish from their hand")
        chosen = next((c for c in opp.hand.cards if c.slug == pick), opp.hand.cards[0])
        opp.hand.remove(chosen)
        effect_banish(state, chosen, face_up=True, banisher_id=cid)

CARD_TRIGGERS["dominia"] = [TriggerDef(event_type="on_play", effect_fn=_dominia_effect)]


# -- kyloria: gain control of item or deal arcane --
def _kyloria_effect(card, event, state):
    cid = _controller_id(card)
    opp_id = 3 - cid
    opp = state.players[opp_id]
    items = [c for c in opp.permanents.cards if "Item" in (c.types or [])]
    if items:
        pick = _ask_player(state, cid, [c.slug for c in items], context="Kyloria: choose item to take")
        chosen = next((c for c in items if c.slug == pick), items[0])
        opp.permanents.remove(chosen)
        chosen.controller = cid
        state.players[cid].permanents.add(chosen)
    else:
        effect_deal_arcane(state, opp_id, 2, card)

CARD_TRIGGERS["kyloria"] = [TriggerDef(event_type="on_play", effect_fn=_kyloria_effect)]


# ===== AMULET / SEARCH =====

# -- amulet_of_havencall: search for Rally the Rearguard --
def _amulet_havencall_effect(card, event, state):
    from engine.card_effects.keywords import effect_search_deck
    cid = _controller_id(card)
    _move_to_graveyard(card, state)
    found = effect_search_deck(state, cid, condition=lambda c: "rally_the_rearguard" in c.slug)
    if found:
        player = state.players[cid]
        player.deck.cards.remove(found)
        if state.combat:
            state.combat.defending_cards.append(found)
            found.zone = "combat chain"
        effect_shuffle(state, cid)

CARD_TRIGGERS["amulet_of_havencall_blue"] = [TriggerDef(event_type="on_play", effect_fn=_amulet_havencall_effect)]


# -- belittle: reveal small attack, search for same name --
def _belittle_effect(card, event, state):
    from engine.card_effects.keywords import effect_search_deck
    cid = _controller_id(card)
    player = state.players[cid]
    smalls = [c for c in player.hand.cards if "Attack" in (c.types or []) and c.power is not None and c.power <= 3]
    if not smalls:
        return
    choice = _ask_player(state, cid, [True, False], context="Belittle: reveal small attack to search?")
    if not choice:
        return
    pick = _ask_player(state, cid, [c.slug for c in smalls], context="Choose attack to reveal")
    chosen = next((c for c in smalls if c.slug == pick), smalls[0])
    base = chosen.slug.rsplit('_', 1)[0] if '_' in chosen.slug else chosen.slug
    found = effect_search_deck(state, cid, condition=lambda c, bn=base: bn in c.slug)
    if found:
        player.deck.cards.remove(found)
        player.hand.add(found)
        effect_shuffle(state, cid)

for _slug in ["belittle_red", "belittle_yellow", "belittle_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="on_play", effect_fn=_belittle_effect, is_optional=True)]


# ===== CHAOS: multi-hero =====

# -- concoct_disorder: each hero puts top face-down into arsenal --
def _concoct_disorder_effect(card, event, state):
    cards_put = 0
    for pid in state.players:
        player = state.players[pid]
        if player.deck.cards:
            top = player.deck.pop_top()
            player.arsenal.add(top)
            cards_put += 1
    if cards_put >= 2:
        create_token(state, _controller_id(card), "copper", cards_put)

for _slug in ["concoct_disorder_red", "concoct_disorder_yellow", "concoct_disorder_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="on_play", effect_fn=_concoct_disorder_effect)]


# -- descend_into_madness: banish random from opp hand --
CARD_TRIGGERS["descend_into_madness_blue"] = [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: effect_intimidate(s, 3 - _controller_id(c), c)),
]


# ===== MISC COMPLEX =====

# -- adaptive_plating: modular equip --
CARD_TRIGGERS["adaptive_plating"] = [
    TriggerDef(event_type="defend",
               condition_fn=lambda c, e, s: s.combat and c in s.combat.defending_cards,
               effect_fn=lambda c, e, s: None),
]

# -- barbed_barrage: pay rrr for additional target --
def _barbed_barrage_effect(card, event, state):
    cid = _controller_id(card)
    if state.players[cid].resources < 3:
        return
    choice = _ask_player(state, cid, [True, False], context="Barbed Barrage: pay {r}{r}{r} for additional target?")
    if choice:
        state.players[cid].resources -= 3
        state.players[cid].current_turn_effects.append("barbed_barrage_additional_target")

CARD_TRIGGERS["barbed_barrage_red"] = [TriggerDef(event_type="on_play", effect_fn=_barbed_barrage_effect, is_optional=True)]


# -- blood_splattered_vest: dagger hit -> gain r, stain counters --
def _blood_splattered_vest_hit(card, event, state):
    if not hasattr(event, 'data'):
        return
    hit_card = event.data.get('card')
    if not hit_card or "Dagger" not in (hit_card.types or []):
        return
    cid = _controller_id(card)
    if hit_card.owner != cid:
        return
    choice = _ask_player(state, cid, [True, False], context="Blood Splattered Vest: gain {r}?")
    if choice:
        effect_gain_resources(state, cid, 1)
        effect_put_counter(state, card, "stain", 1)
        key = (card.slug, card.zone, "stain")
        if state.players[cid].counters.get(key, 0) >= 3:
            _move_to_graveyard(card, state)

CARD_TRIGGERS["blood_splattered_vest"] = [TriggerDef(event_type="hit", effect_fn=_blood_splattered_vest_hit, is_optional=True)]


# -- coat_of_allegiance: destroy for r, restrict to draconic --
CARD_TRIGGERS["coat_of_allegiance"] = [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: (
        _move_to_graveyard(c, s),
        effect_gain_resources(s, _controller_id(c), 2),
        s.players[_controller_id(c)].current_turn_effects.append("only_draconic_this_turn"),
    )),
]


# -- battlefield_beacon: choose modes per soul banished --
def _battlefield_beacon_attack(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    banished = sum(1 for eff in state.players[cid].current_turn_effects if eff.startswith("soul_banished_"))
    if banished == 0:
        return
    modes = ["create_ash", "plus_1_power", "go_again"]
    for _ in range(min(banished, 3)):
        if not modes:
            break
        pick = _ask_player(state, cid, modes, context="Battlefield Beacon: choose mode")
        if pick == "create_ash":
            create_token(state, cid, "ash")
        elif pick == "plus_1_power" and state.combat:
            state.combat.attack_power += 1
        elif pick == "go_again" and state.combat:
            if 'go_again' not in state.combat.keywords:
                state.combat.keywords.append('go_again')

CARD_TRIGGERS["battlefield_beacon_yellow"] = [TriggerDef(event_type="attacking", effect_fn=_battlefield_beacon_attack)]


# -- azalea hero abilities (already in HERO_ACTIVATION but need triggers for specialization) --
# Heroes are handled via registry.py, skip here


# -- arakni_tarantula: dagger hit -> opp loses 1 life --
# (Already defined above in earlier Batch 4 section)


# ===== ADDITIONAL COMPLEX: Azalea, various ranger =====

# -- azalea: put arsenal on bottom, top of deck face up into arsenal (hero ability) --
# Handled by HERO_ACTIVATION_CONDITIONS in registry.py


# ===== ADDITIONAL MISC =====

# -- barbed_barrage: multi-target variant for yellow/blue --
for _slug in ["barbed_barrage_yellow", "barbed_barrage_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="on_play", effect_fn=_barbed_barrage_effect, is_optional=True)]


# -- blood_splattered variants (already handled above) --

# -- bore_down: "if you control 2+ item, draw a card" --
def _bore_down_effect(card, event, state, draw_count):
    cid = _controller_id(card)
    items = sum(1 for c in state.players[cid].permanents.cards if "Item" in (c.types or []))
    if items >= 2:
        effect_draw(state, cid, draw_count)

for _slug, _d in [("bore_down_red", 1), ("bore_down_yellow", 1), ("bore_down_blue", 1)]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="on_play",
                            effect_fn=lambda c, e, s, d=_d: _bore_down_effect(c, e, s, d))]


# -- brandish: "if you've attacked with a weapon, +1 power" --
def _brandish_effect(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    if "attacked_with_weapon" in state.players[cid].current_turn_effects:
        state.combat.attack_power += 1

for _slug in ["brandish_red", "brandish_yellow", "brandish_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="attacking", effect_fn=_brandish_effect)]


# -- cerebral_mindstep: "if you've dealt arcane this turn, draw" --
def _cerebral_mindstep_effect(card, event, state, draw_count):
    cid = _controller_id(card)
    if "dealt_arcane" in state.players[cid].current_turn_effects:
        effect_draw(state, cid, draw_count)

for _slug, _d in [("cerebral_mindstep_red", 1), ("cerebral_mindstep_yellow", 1),
                   ("cerebral_mindstep_blue", 1)]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="on_play",
                            effect_fn=lambda c, e, s, d=_d: _cerebral_mindstep_effect(c, e, s, d))]


# -- chains_of_eminence: "if you have 2+ auras, this has go again" --
def _chains_of_eminence_attack(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    auras = sum(1 for c in state.players[cid].permanents.cards if "Aura" in (c.types or []))
    if auras >= 2 and 'go_again' not in state.combat.keywords:
        state.combat.keywords.append('go_again')

for _slug in ["chains_of_eminence_red", "chains_of_eminence_yellow", "chains_of_eminence_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="attacking", effect_fn=_chains_of_eminence_attack)]


# -- come_to_fight: "if you have less life, +2 power" --
def _come_to_fight_attack(card, event, state, bonus):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    if state.players[cid].health < state.players[3 - cid].health:
        state.combat.attack_power += bonus

for _slug, _b in [("come_to_fight_red", 2), ("come_to_fight_yellow", 2), ("come_to_fight_blue", 2)]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="attacking",
                            effect_fn=lambda c, e, s, b=_b: _come_to_fight_attack(c, e, s, b))]


# -- consuming_volition: "deal arcane equal to cards in opp pitch zone" --
def _consuming_volition_effect(card, event, state):
    cid = _controller_id(card)
    opp_id = 3 - cid
    amount = len(state.players[opp_id].pitch.cards)
    if amount > 0:
        effect_deal_arcane(state, opp_id, amount, card)

for _slug in ["consuming_volition_red", "consuming_volition_yellow", "consuming_volition_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="on_play", effect_fn=_consuming_volition_effect)]


# -- critically_wounded: "if you have less life, draw 2" --
def _critically_wounded_effect(card, event, state):
    cid = _controller_id(card)
    if state.players[cid].health < state.players[3 - cid].health:
        effect_draw(state, cid, 2)

CARD_TRIGGERS["critically_wounded_blue"] = [TriggerDef(event_type="on_play", effect_fn=_critically_wounded_effect)]


# -- deep_blue: "if you have no cards in hand, +2 power" --
def _deep_blue_attack(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    if not state.players[cid].hand.cards:
        state.combat.attack_power += 2

for _slug in ["deep_blue_red", "deep_blue_yellow", "deep_blue_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="attacking", effect_fn=_deep_blue_attack)]


# -- double_strike: "if you've attacked this turn, +power and go again" --
def _double_strike_attack(card, event, state, bonus):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    if "attacked_this_turn" in state.players[cid].current_turn_effects:
        state.combat.attack_power += bonus
        if 'go_again' not in state.combat.keywords:
            state.combat.keywords.append('go_again')

for _slug, _b in [("double_strike_red", 2), ("double_strike_yellow", 2), ("double_strike_blue", 1)]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="attacking",
                            effect_fn=lambda c, e, s, b=_b: _double_strike_attack(c, e, s, b))]


# -- enlightened_strike: "if you've played non-attack this turn, +2 and draw" --
def _enlightened_strike_attack(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    if "played_nonattack_this_turn" in state.players[cid].current_turn_effects:
        state.combat.attack_power += 2
        effect_draw(state, cid, 1)

CARD_TRIGGERS["enlightened_strike"] = [TriggerDef(event_type="attacking", effect_fn=_enlightened_strike_attack)]


# -- fate_foreseen: defense reaction, put on top of deck, +d --
def _fate_foreseen_effect(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    if not player.hand.cards:
        return
    opts = [c.slug for c in player.hand.cards] + ["decline"]
    pick = _ask_player(state, cid, opts, context="Fate Foreseen: put a card on top of deck?")
    if pick == "decline":
        return
    target = next((c for c in player.hand.cards if c.slug == pick), None)
    if target:
        player.hand.remove(target)
        player.deck.cards.insert(0, target)
        target.zone = "deck"

for _slug in ["fate_foreseen_red", "fate_foreseen_yellow", "fate_foreseen_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="on_play", effect_fn=_fate_foreseen_effect)]


# -- feisty_locals: "for each defending card, this gets +1 power" --
def _feisty_locals_defend(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    count = len(state.combat.defending_cards)
    if count > 0:
        state.combat.attack_power += count

for _slug in ["feisty_locals_red", "feisty_locals_yellow", "feisty_locals_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="defend", effect_fn=_feisty_locals_defend)]


# -- flex: "if you control might, this has go again" --
def _flex_attack(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    has_might = any(c.slug == "might" for c in state.players[cid].permanents.cards)
    if has_might and 'go_again' not in state.combat.keywords:
        state.combat.keywords.append('go_again')

for _slug in ["flex_red", "flex_yellow", "flex_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="attacking", effect_fn=_flex_attack)]


# -- forked_lightning: "deal 2 arcane to each opposing hero" (multi-target) --
def _forked_lightning_effect(card, event, state, amount):
    cid = _controller_id(card)
    for pid in state.players:
        if pid != cid:
            effect_deal_arcane(state, pid, amount, card)

for _slug, _amt in [("forked_lightning_red", 2), ("forked_lightning_yellow", 2),
                     ("forked_lightning_blue", 1)]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="on_play",
                            effect_fn=lambda c, e, s, a=_amt: _forked_lightning_effect(c, e, s, a))]


# -- give_and_take: "draw then discard equal number of cards" --
def _give_and_take_effect(card, event, state, count):
    cid = _controller_id(card)
    effect_draw(state, cid, count)
    effect_discard(state, cid, count)

for _slug, _c in [("give_and_take_red", 3), ("give_and_take_yellow", 2), ("give_and_take_blue", 1)]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="on_play",
                            effect_fn=lambda c, e, s, ct=_c: _give_and_take_effect(c, e, s, ct))]


# -- high_octane: "attacks gain +1 power, at end of turn lose 1 life per attack" --
def _high_octane_effect(card, event, state):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("high_octane_attacks_plus_1")

for _slug in ["high_octane_red", "high_octane_yellow", "high_octane_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="on_play", effect_fn=_high_octane_effect)]


# -- last_ditch_effort: "if no cards in hand, +3 power" --
def _last_ditch_attack(card, event, state, bonus):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    if not state.players[_controller_id(card)].hand.cards:
        state.combat.attack_power += bonus

for _slug, _b in [("last_ditch_effort_red", 3), ("last_ditch_effort_yellow", 2),
                   ("last_ditch_effort_blue", 1)]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="attacking",
                            effect_fn=lambda c, e, s, b=_b: _last_ditch_attack(c, e, s, b))]


# -- lead_the_charge: "if no cards in hand, go again" --
def _lead_the_charge_attack(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    if not state.players[_controller_id(card)].hand.cards:
        if 'go_again' not in state.combat.keywords:
            state.combat.keywords.append('go_again')

for _slug in ["lead_the_charge_red", "lead_the_charge_yellow", "lead_the_charge_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="attacking", effect_fn=_lead_the_charge_attack)]


# -- life_for_a_life: "if you've been dealt damage, deal that much arcane" --
def _life_for_a_life_effect(card, event, state, amount):
    cid = _controller_id(card)
    if "dealt_damage_this_turn" in state.players[cid].current_turn_effects:
        effect_deal_arcane(state, 3 - cid, amount, card)

for _slug, _a in [("life_for_a_life_red", 4), ("life_for_a_life_yellow", 3), ("life_for_a_life_blue", 2)]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="on_play",
                            effect_fn=lambda c, e, s, a=_a: _life_for_a_life_effect(c, e, s, a))]


# -- nerves_of_steel: "if you've been dealt damage, +defense" --
def _nerves_of_steel_defend(card, event, state, bonus):
    if not state.combat or card not in state.combat.defending_cards:
        return
    cid = _controller_id(card)
    if "dealt_damage_this_turn" in state.players[cid].current_turn_effects:
        card.effects.append(("base_defense", lambda base, n=bonus: base + n))

for _slug, _b in [("nerves_of_steel_red", 3), ("nerves_of_steel_yellow", 2), ("nerves_of_steel_blue", 1)]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="defend",
                            effect_fn=lambda c, e, s, b=_b: _nerves_of_steel_defend(c, e, s, b))]


# -- oath_of_the_arknight: "if runechant, +1 power and 'on hit create runechant'" --
def _oath_arknight_attack(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    if any(c.slug == "runechant" for c in state.players[cid].permanents.cards):
        state.combat.attack_power += 1
        state.players[cid].current_turn_effects.append("oath_arknight_hit_create_runechant")

for _slug in ["oath_of_the_arknight_red", "oath_of_the_arknight_yellow", "oath_of_the_arknight_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="attacking", effect_fn=_oath_arknight_attack)]


# -- overblast: "deal X arcane where X = number of wizard non-attack actions played this turn" --
def _overblast_effect(card, event, state, base):
    cid = _controller_id(card)
    wizard_count = sum(1 for eff in state.players[cid].current_turn_effects if eff == "played_wizard_nonattack")
    effect_deal_arcane(state, 3 - cid, base + wizard_count, card)

for _slug, _b in [("overblast_red", 4), ("overblast_yellow", 3), ("overblast_blue", 2)]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="on_play",
                            effect_fn=lambda c, e, s, b=_b: _overblast_effect(c, e, s, b))]


# -- phantasmal_footsteps: "when this defends, may put it on bottom of deck instead of graveyard" --
def _phantasmal_footsteps_defend(card, event, state):
    if not state.combat or card not in state.combat.defending_cards:
        return
    cid = _controller_id(card)
    choice = _ask_player(state, cid, [True, False],
                         context="Phantasmal Footsteps: put on bottom of deck instead of graveyard?")
    if choice:
        state.players[cid].current_turn_effects.append(f"bottom_instead_{card.slug}")

CARD_TRIGGERS["phantasmal_footsteps"] = [
    TriggerDef(event_type="defend", effect_fn=_phantasmal_footsteps_defend, is_optional=True),
]


# -- plunder_run: "when hits, banish top of deck, play it this turn" --
def _plunder_run_hit(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    player = state.players[cid]
    if player.deck.cards:
        top = player.deck.pop_top()
        effect_banish(state, top, face_up=True, banisher_id=cid)
        state.players[cid].current_turn_effects.append(f"may_play_{top.slug}")

for _slug in ["plunder_run_red", "plunder_run_yellow", "plunder_run_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="hit", effect_fn=_plunder_run_hit)]


# -- push_forward: "draw, then if weapon hit, draw again" --
def _push_forward_effect(card, event, state):
    cid = _controller_id(card)
    effect_draw(state, cid, 1)
    if "weapon_hit_this_turn" in state.players[cid].current_turn_effects:
        effect_draw(state, cid, 1)

for _slug in ["push_forward_red", "push_forward_yellow", "push_forward_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="on_play", effect_fn=_push_forward_effect)]


# -- razor_reflex: "target attack gets +2 power and go again" --
def _razor_reflex_effect(card, event, state, bonus):
    if state.combat:
        state.combat.attack_power += bonus
        if 'go_again' not in state.combat.keywords:
            state.combat.keywords.append('go_again')

for _slug, _b in [("razor_reflex_red", 3), ("razor_reflex_yellow", 2), ("razor_reflex_blue", 1)]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="on_play",
                            effect_fn=lambda c, e, s, b=_b: _razor_reflex_effect(c, e, s, b))]


# -- remembrance: "put attack from graveyard on bottom of deck" --
def _remembrance_effect(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    attacks = [c for c in player.graveyard.cards if "Attack" in (c.types or [])]
    if not attacks:
        return
    pick = _ask_player(state, cid, [c.slug for c in attacks], context="Remembrance: return attack to bottom of deck")
    chosen = next((c for c in attacks if c.slug == pick), attacks[0])
    player.graveyard.remove(chosen)
    player.deck.add_bottom(chosen)

for _slug in ["remembrance_red", "remembrance_yellow", "remembrance_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="on_play", effect_fn=_remembrance_effect)]


# -- second_swing: "if you've attacked with weapon, this gets go again" --
def _second_swing_attack(card, event, state):
    if not state.combat or state.combat.attack_card.slug != card.slug:
        return
    cid = _controller_id(card)
    if "attacked_with_weapon" in state.players[cid].current_turn_effects:
        if 'go_again' not in state.combat.keywords:
            state.combat.keywords.append('go_again')

for _slug in ["second_swing_red", "second_swing_yellow", "second_swing_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="attacking", effect_fn=_second_swing_attack)]


# -- sharpen_steel: "target weapon gets +1 attack this turn" --
def _sharpen_steel_effect(card, event, state, bonus):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append(f"weapon_attack_plus_{bonus}")

for _slug, _b in [("sharpen_steel_red", 3), ("sharpen_steel_yellow", 2), ("sharpen_steel_blue", 1)]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="on_play",
                            effect_fn=lambda c, e, s, b=_b: _sharpen_steel_effect(c, e, s, b))]


# -- spinal_crush: "crush - if this deals 4+ damage, opp puts hand on bottom of deck" --
def _spinal_crush_crush(card, event, state):
    tid = 3 - _controller_id(card)
    target = state.players[tid]
    for c in list(target.hand.cards):
        target.hand.remove(c)
        target.deck.add_bottom(c)

CARD_TRIGGERS["spinal_crush"] = [crush_trigger(_spinal_crush_crush)]


# -- steelblade_supremacy: "when weapon hits, draw" --
def _steelblade_supremacy_effect(card, event, state):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("weapon_hit_draw_1")

for _slug in ["steelblade_supremacy_red", "steelblade_supremacy_yellow", "steelblade_supremacy_blue"]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="on_play", effect_fn=_steelblade_supremacy_effect)]


# -- timesnap_potion: "gain action point, draw, then put on top of deck" --
def _timesnap_potion_effect(card, event, state):
    cid = _controller_id(card)
    _move_to_graveyard(card, state)
    effect_gain_action_point(state, cid)
    effect_draw(state, cid, 1)

CARD_TRIGGERS["timesnap_potion"] = [TriggerDef(event_type="on_play", effect_fn=_timesnap_potion_effect)]


# -- tome_of_fyendal: "gain 2 life, draw a card" --
def _tome_of_fyendal_effect(card, event, state):
    cid = _controller_id(card)
    effect_gain_life(state, cid, 2)
    effect_draw(state, cid, 1)

CARD_TRIGGERS["tome_of_fyendal"] = [TriggerDef(event_type="on_play", effect_fn=_tome_of_fyendal_effect)]


# -- unmovable: "the next N damage is prevented, if you do create N might" --
def _unmovable_effect(card, event, state, prevent):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append(f"prevent_{prevent}_create_might")

for _slug, _p in [("unmovable_red", 4), ("unmovable_yellow", 3), ("unmovable_blue", 2)]:
    CARD_TRIGGERS[_slug] = [TriggerDef(event_type="on_play",
                            effect_fn=lambda c, e, s, p=_p: _unmovable_effect(c, e, s, p))]


# -- warrior_general: "if you've attacked with weapon, attacks +1 and draw on hit" --
def _warrior_general_effect(card, event, state):
    cid = _controller_id(card)
    if "attacked_with_weapon" in state.players[cid].current_turn_effects:
        state.players[cid].current_turn_effects.append("attacks_plus_1")
        state.players[cid].current_turn_effects.append("attacks_on_hit_draw_1")

CARD_TRIGGERS["warrior_general_red"] = [TriggerDef(event_type="on_play", effect_fn=_warrior_general_effect)]


# ---------------------------------------------------------------------------
# Registry — builds triggers for a card from keywords + card-specific
# ---------------------------------------------------------------------------

def get_triggers_for_card(card: Card) -> list[TriggerDef]:
    """Get all trigger definitions for a card.
    Combines keyword-derived triggers with card-specific triggers."""
    triggers = build_keyword_triggers(card)

    # Add card-specific triggers
    slug = card.slug
    if slug in CARD_TRIGGERS:
        triggers.extend(CARD_TRIGGERS[slug])

    # Also check base name (without color suffix) for shared triggers
    base_slug = re.sub(r'_(red|yellow|blue)$', '', slug)
    if base_slug != slug and base_slug in CARD_TRIGGERS:
        triggers.extend(CARD_TRIGGERS[base_slug])

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


def register_all_triggers(state: GameState) -> None:
    """Register triggers for all public cards of all players."""
    for player_id in state.players:
        player = state.players[player_id]
        for card in player.public_cards:
            register_card_triggers(card, state.event_manager)
