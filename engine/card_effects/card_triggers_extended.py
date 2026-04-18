"""Extended card trigger implementations for FAB simulator.

Covers all 647 cards from the card_effects_gap_report that were not yet
registered in CARD_TRIGGERS.  Effects are simplified where necessary for
ML training (see SIMPLIFICATION RULES in the task spec).

Import this module AFTER triggers.py to merge into CARD_TRIGGERS.
"""
from __future__ import annotations
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.state import GameState
    from engine.card import Card

from engine.card_effects.triggers import CARD_TRIGGERS, TriggerDef
from engine.card_effects.card_keywords import (
    _controller_id, _get_controller, _get_opponent_of, _ask_player,
    _move_to_graveyard, _draw_cards, _remove_from_current_zone,
    effect_draw, effect_discard, effect_banish, effect_banish_top_deck,
    effect_deal_damage, effect_deal_arcane, effect_deal_arcane_to_target,
    effect_gain_life, effect_lose_life,
    effect_gain_action_point, effect_gain_resources,
    effect_destroy, effect_opt, effect_intimidate,
    effect_put_counter, effect_remove_counter,
    effect_search_deck, effect_shuffle, effect_amp, effect_charge,
    effect_mark, is_marked, create_token, effect_crowd_boos, has_been_booed,
    effect_banish_from_soul, effect_banish_from_hand, effect_move_to_soul,
    effect_retrieve_dagger, effect_reveal_top, effect_look_top,
    effect_put_top_deck, effect_put_bottom_deck, effect_return_to_hand,
    effect_put_arsenal, roll_die, effect_steal_token,
    effect_negate, effect_reload,
    crush_check, reprise_check, combo_check, surge_check, rupture_check,
    fusion, _pitch_for_cost,
)
from engine.card_effects.registry import TURN_ATTACK_EFFECTS
from engine.effect_keywords import gets, gets_property, turn, GetsKind, EventType

# ============================================================
# Register additional TURN_ATTACK_EFFECTS sizes
# ============================================================
def _make_nap(n):
    """Factory: next_attack_+N apply function."""
    def apply_fn(attack_card, player, state):
        attack_card.base_power = (attack_card.base_power or 0) + n
    return apply_fn

for _n in [1, 2, 3, 4, 5, 6]:
    _key = f"next_attack_+{_n}"
    if _key not in TURN_ATTACK_EFFECTS:
        TURN_ATTACK_EFFECTS[_key] = {"apply_fn": _make_nap(_n)}

# all_attacks_+N: persistent (not consumed), applies to every attack this turn
for _n in [1, 2, 3, 4, 5]:
    _key = f"all_attacks_+{_n}"
    if _key not in TURN_ATTACK_EFFECTS:
        TURN_ATTACK_EFFECTS[_key] = {"apply_fn": _make_nap(_n), "persistent": True}

# next_brute_attack_+2: only applies to Brute class attack cards
if "next_brute_attack_+2" not in TURN_ATTACK_EFFECTS:
    TURN_ATTACK_EFFECTS["next_brute_attack_+2"] = {
        "condition_fn": lambda ac, pl, st: "Brute" in (ac.subtypes or []),
        "apply_fn": _make_nap(2),
    }


# ============================================================
# SECTION 1: Shared helper functions / factories
# ============================================================

def _is_this_attacking(card, event, state):
    """Condition: this card is the current attacker."""
    if not state.combat:
        return False
    ac = state.combat.attack_card
    return ac is card or (ac is not None and ac.slug == card.slug)


def _is_this_defending(card, event, state):
    """Condition: this card is in the defending cards."""
    return state.combat is not None and card in state.combat.defending_cards


# --- factories for common patterns ---

def _factory_on_hit_draw(count=1):
    """Factory: on-hit draw N cards."""
    def effect(card, event, state):
        if not _is_this_attacking(card, event, state):
            return
        effect_draw(state, _controller_id(card), count)
    return effect


def _factory_on_hit_next_attack_plus(n):
    """Factory: on-hit, next attack this turn gets +n power."""
    def effect(card, event, state):
        if not _is_this_attacking(card, event, state):
            return
        cid = _controller_id(card)
        state.players[cid].current_turn_effects.append(f"next_attack_+{n}")
    return effect


def _factory_on_play_draw(count=1):
    """Factory: on-play draw N cards."""
    def effect(card, event, state):
        effect_draw(state, _controller_id(card), count)
    return effect


def _factory_on_play_create_token(token_slug, count=1):
    """Factory: on-play create N tokens."""
    def effect(card, event, state):
        cid = _controller_id(card)
        for _ in range(count):
            create_token(state, cid, token_slug)
    return effect


def _factory_on_play_gain_life(amount):
    def effect(card, event, state):
        effect_gain_life(state, _controller_id(card), amount)
    return effect


def _factory_on_play_deal_arcane(amount):
    def effect(card, event, state):
        target_id = 3 - _controller_id(card)
        effect_deal_arcane(state, target_id, amount, source=card)
    return effect


def _factory_on_play_next_attack_plus(n):
    """Factory: on-play, next attack this turn gets +n{p}."""
    def effect(card, event, state):
        cid = _controller_id(card)
        state.players[cid].current_turn_effects.append(f"next_attack_+{n}")
    return effect


def _factory_on_hit_create_token(token_slug, count=1):
    def effect(card, event, state):
        if not _is_this_attacking(card, event, state):
            return
        cid = _controller_id(card)
        for _ in range(count):
            create_token(state, cid, token_slug)
    return effect


def _factory_on_hit_lose_life(amount):
    def effect(card, event, state):
        if not _is_this_attacking(card, event, state):
            return
        target_id = 3 - _controller_id(card)
        effect_lose_life(state, target_id, amount)
    return effect


def _factory_on_hit_mark():
    def effect(card, event, state):
        if not _is_this_attacking(card, event, state):
            return
        target_id = 3 - _controller_id(card)
        effect_mark(state, target_id)
    return effect


def _factory_on_hit_discard(count=1):
    def effect(card, event, state):
        if not _is_this_attacking(card, event, state):
            return
        target_id = 3 - _controller_id(card)
        effect_discard(state, target_id, count)
    return effect


def _factory_on_hit_banish_top_deck(count=1):
    def effect(card, event, state):
        if not _is_this_attacking(card, event, state):
            return
        target_id = 3 - _controller_id(card)
        effect_banish_top_deck(state, target_id, count, face_up=True)
    return effect


def _factory_on_hit_create_token_under_opponent(token_slug, count=1):
    def effect(card, event, state):
        if not _is_this_attacking(card, event, state):
            return
        target_id = 3 - _controller_id(card)
        for _ in range(count):
            create_token(state, target_id, token_slug)
    return effect


def _factory_attacking_go_again_if(condition_fn):
    """Factory: when this attacks, if condition met, gain go again."""
    def effect(card, event, state):
        if not _is_this_attacking(card, event, state):
            return
        if condition_fn(card, state):
            if state.combat and "Go Again" not in state.combat.keywords:
                state.combat.grant_keyword("Go Again")
    return effect


def _factory_on_hit_go_again():
    def effect(card, event, state):
        if not _is_this_attacking(card, event, state):
            return
        if state.combat and "Go Again" not in state.combat.keywords:
            state.combat.grant_keyword("Go Again")
    return effect


def _factory_attacking_plus_power(n):
    """Factory: when this attacks, +N power."""
    def effect(card, event, state):
        if not _is_this_attacking(card, event, state):
            return
        if state.combat:
            state.combat.attack_power += n
    return effect


def _factory_crush_on_hit(effect_fn):
    """Factory: crush -- if 4+ damage, apply effect."""
    def effect(card, event, state):
        if not _is_this_attacking(card, event, state):
            return
        if state.combat and crush_check(event, state):
            effect_fn(card, event, state)
    return effect


def _factory_ar_power_bonus(n):
    """Factory: attack reaction giving +N power."""
    def effect(card, event, state):
        if state.combat:
            state.combat.attack_power += n
    return effect


def _factory_ar_go_again():
    """Factory: attack reaction giving go again."""
    def effect(card, event, state):
        if state.combat and "Go Again" not in state.combat.keywords:
            state.combat.grant_keyword("Go Again")
    return effect


def _factory_on_defend_clash_winner_token(token_slug):
    """Factory: clash on defend, winner creates token.

    CR 8.4.5: Both players reveal top card. Card with greater power wins.
    Equal power = both fail (no winner, no token). No card = power 0.
    """
    def effect(card, event, state):
        if not _is_this_defending(card, event, state):
            return
        cid = _controller_id(card)
        opp_id = 3 - cid
        my_cards = effect_look_top(state, cid, 1)
        opp_cards = effect_look_top(state, opp_id, 1)
        my_power = (my_cards[0].base_power or 0) if my_cards else 0
        opp_power = (opp_cards[0].base_power or 0) if opp_cards else 0
        if my_power > opp_power:
            create_token(state, cid, token_slug)
        elif opp_power > my_power:
            create_token(state, opp_id, token_slug)
        # Equal power = both fail, no token created
    return effect


def _factory_on_play_mark():
    def effect(card, event, state):
        target_id = 3 - _controller_id(card)
        effect_mark(state, target_id)
    return effect


def _fabricate_on_play(card, event, state):
    """Fabricate: choose 2 modes, resolving in printed order."""
    cid = _controller_id(card)
    player = state.players[cid]

    mode_labels = [
        "equip_proto_from_inventory",
        "evo_permanents_get_+1d",
        "put_this_under_evo_permanent",
        "banish_evo_from_hand_draw_1",
    ]
    selected = _ask_player(
        state,
        cid,
        mode_labels,
        context="Fabricate: choose 2 modes",
    )
    if not isinstance(selected, list):
        selected = [selected] if selected in mode_labels else []
    selected = [m for m in selected if m in mode_labels]
    # CR 1.7.5b: cannot choose same mode more than once unless specified.
    selected = list(dict.fromkeys(selected))[:2]
    if not selected:
        selected = mode_labels[:2]

    # Mode 1: Equip a base equipment with Proto in its name from inventory.
    if "equip_proto_from_inventory" in selected:
        proto_cards = [
            c for c in player.inventory.cards
            if ("Equipment" in (c.types or []))
            and ("proto" in (c.slug or "").lower() or "proto" in ((c.raw_name or c.name or "").lower()))
        ]
        if proto_cards:
            equip = proto_cards[0]
            destination = None
            for slot in ("head", "chest", "arms", "legs"):
                z = player.zone_by_name(slot)
                if z is not None and not z.cards:
                    destination = z
                    break
            if destination is not None:
                player.inventory.remove(equip)
                destination.add(equip)

    # Mode 2: Evo permanents you control get +1{d} this turn.
    if "evo_permanents_get_+1d" in selected:
        for perm in list(player.permanents.cards):
            if "evo" in (perm.slug or "").lower() or "evo" in ((perm.raw_name or perm.name or "").lower()):
                gets(
                    state,
                    prop="defense",
                    kind=GetsKind.ADD,
                    amount=1,
                    source_card=card,
                    target_card=perm,
                    until_condition=EventType.EOT,
                )

    # Mode 3: Put this under an Evo permanent you control.
    if "put_this_under_evo_permanent" in selected:
        evo_perms = [
            p for p in player.permanents.cards
            if "evo" in (p.slug or "").lower() or "evo" in ((p.raw_name or p.name or "").lower())
        ]
        if evo_perms:
            host = evo_perms[0]
            if card not in host.cards_underneath:
                host.cards_underneath.append(card)
                card.is_sub_card = True
                card.zone = host.zone

    # Mode 4: You may banish an Evo from hand. If you do, draw a card.
    if "banish_evo_from_hand_draw_1" in selected:
        evo_hand = [
            c for c in player.hand.cards
            if "evo" in (c.slug or "").lower() or "evo" in ((c.raw_name or c.name or "").lower())
        ]
        if evo_hand:
            banished = evo_hand[0]
            effect_banish(state, banished, face_up=True, banisher_id=cid)
            effect_draw(state, cid, 1)


def _fearless_confrontation_on_play(card, event, state):
    """Target attack gets -1 power and loses dominate this turn."""
    if state.combat is None:
        return
    attack = state.combat.attack_card
    if attack is None:
        return
    gets(
        state,
        prop="power",
        kind=GetsKind.SUBTRACT,
        amount=1,
        source_card=card,
        target_card=attack,
        until_condition=EventType.EOT,
    )
    gets_property(
        state,
        prop="keywords",
        value="Dominate",
        source_card=card,
        target_card=attack,
        remove=True,
        until_condition=EventType.EOT,
    )


def _figment_of_judgment_enters_arena(card, event, state):
    """Turn a card in any banished zone face-down."""
    cid = _controller_id(card)
    candidates = []
    for player in state.players.values():
        candidates.extend([c for c in player.banished.cards if c.is_public])
    if not candidates:
        return
    choice = _ask_player(
        state,
        cid,
        [c.slug for c in candidates],
        context="Figment of Judgment: choose a banished card to turn face-down",
    )
    chosen = next((c for c in candidates if c.slug == choice), candidates[0])
    turn(state, chosen, face_up=False, source_player_id=cid)


def _figment_of_rebirth_enters_arena(card, event, state):
    """Put a yellow action card from graveyard on top of deck."""
    cid = _controller_id(card)
    player = state.players[cid]
    yellow_actions = [
        c for c in player.graveyard.cards
        if ("Action" in (c.types or [])) and int(getattr(c, "pitch", 0) or 0) == 2
    ]
    if not yellow_actions:
        return
    choice = _ask_player(
        state,
        cid,
        [c.slug for c in yellow_actions],
        context="Figment of Rebirth: choose a yellow action card in your graveyard",
    )
    target = next((c for c in yellow_actions if c.slug == choice), yellow_actions[0])
    effect_put_top_deck(state, target, cid)


def _factory_on_play_action_point():
    def effect(card, event, state):
        effect_gain_action_point(state, _controller_id(card), 1)
    return effect


def _factory_on_hit_to_soul():
    """Factory: on-hit put this into your soul."""
    def effect(card, event, state):
        if not _is_this_attacking(card, event, state):
            return
        cid = _controller_id(card)
        effect_move_to_soul(state, card, cid)
    return effect


def _factory_on_attacking_draw_discard_random_6p_bonus(bonus_fn):
    """Brute pattern: draw 1, discard random. If 6+p discarded, apply bonus_fn."""
    def effect(card, event, state):
        if not _is_this_attacking(card, event, state):
            return
        cid = _controller_id(card)
        effect_draw(state, cid, 1)
        discarded = effect_discard(state, cid, 1, random_discard=True)
        if discarded and discarded[0].power is not None and discarded[0].power >= 6:
            bonus_fn(card, state)
    return effect


def _factory_rune_gate_on_close(effect_fn):
    """Rune Gate: when combat chain closes, create runechants + custom effect."""
    def effect(card, event, state):
        cid = _controller_id(card)
        # Create Runechant tokens (Rune Gate base)
        create_token(state, cid, "runechant")
        # Apply additional effect
        effect_fn(card, state)
    return effect


def _factory_contract_hit(banish_condition_desc):
    """Contract: on hit banish top of deck, if condition met create Silver.
    Simplified: always banish top, always create Silver on hit."""
    def effect(card, event, state):
        if not _is_this_attacking(card, event, state):
            return
        cid = _controller_id(card)
        target_id = 3 - cid
        banished = effect_banish_top_deck(state, target_id, 1, face_up=True)
        if banished:
            create_token(state, cid, "silver")
    return effect


def _factory_on_play_charge_optional():
    """On play, optionally charge soul."""
    def effect(card, event, state):
        cid = _controller_id(card)
        player = state.players[cid]
        yellow_cards = [c for c in player.hand.cards
                        if c.pitch == 2 and c.slug != card.slug]
        if yellow_cards:
            choice = _ask_player(state, cid, [True, False],
                                 context="Charge your hero's soul?")
            if choice:
                target = yellow_cards[0]
                effect_charge(state, cid, target)
                return True
        return False
    return effect


def _has_draconic_chain_links(state, count=2):
    """Check if controller has N+ Draconic chain links."""
    if not state.combat:
        return False
    draconic_count = 0
    for link in getattr(state, 'chain_links', []):
        ac = getattr(link, 'attack_card', None)
        if ac and any('Draconic' in (t or '') for t in (ac.types if hasattr(ac, 'types') else [])):
            draconic_count += 1
    # Also check current attack
    if state.combat.attack_card:
        ac = state.combat.attack_card
        if any('Draconic' in (t or '') for t in (ac.types if hasattr(ac, 'types') else [])):
            draconic_count += 1
    return draconic_count >= count


def _played_red_this_turn(state, player_id):
    """Check if player has played another red card this turn."""
    player = state.players[player_id]
    return any("played_red" in eff for eff in player.current_turn_effects)


def _has_6p_in_pitch(state, player_id):
    """Check if there's a card with 6+ power in the pitch zone."""
    player = state.players[player_id]
    return any(c.power is not None and c.power >= 6 for c in player.pitch.cards)


def _register(slug, triggers_list):
    """Register triggers only if slug not already registered."""
    if slug not in CARD_TRIGGERS:
        CARD_TRIGGERS[slug] = triggers_list


# ============================================================
# SECTION 2: Per-card implementations
# Grouped by pattern for efficiency, then alphabetical.
# ============================================================

# ---------------------------------------------------------------
# ACTION cards (440)
# ---------------------------------------------------------------

# -- aegis_archangel_of_protection --
# Ally. Once per Turn Action - {r}{r}: Attack.
# Ward 4 static ability (card_keywords has 'Ward' without number — registered manually).
# On attack trigger: may banish a card from soul → create 2 Spectral Shields.
# If Aegis ceases to exist before the trigger resolves, it fails (check in effect_fn).
def _aegis_enters_arena(card, event, state):
    """Register Ward 4 as a replacement effect on the effect_manager."""
    if state.effect_manager is not None:
        from engine.effects import _make_ward
        state.effect_manager.add_replacement(_make_ward(card, 4))

def _aegis_on_attack(card, event, state):
    """When Aegis attacks: optionally banish a soul card to create 2 Spectral Shields."""
    cid = _controller_id(card)
    player = state.players[cid]
    # Fail silently if Aegis has left the arena (destroyed, banished, etc.)
    _arena_zones = {"permanents", "combat_chain", "head", "chest", "arms",
                    "legs", "weapon1", "weapon2", "hero"}
    if card.zone not in _arena_zones:
        return
    if not player.soul.cards:
        return
    choice = _ask_player(state, cid, [True, False],
                         context="Aegis: banish a card from your hero's soul to create 2 Spectral Shields?")
    if not choice:
        return
    # Choose which soul card to banish (player choice if multiple)
    if len(player.soul.cards) > 1:
        pick = _ask_player(state, cid, [c.slug for c in player.soul.cards],
                           context="Aegis: choose a card from your soul to banish")
        soul_card = next((c for c in player.soul.cards if c.slug == str(pick)),
                         player.soul.cards[0])
    else:
        soul_card = player.soul.cards[0]
    effect_banish(state, cid, soul_card)
    create_token(state, cid, "spectral_shield")
    create_token(state, cid, "spectral_shield")

_register("aegis_archangel_of_protection", [
    TriggerDef(event_type="enters_arena", effect_fn=_aegis_enters_arena),
    TriggerDef(event_type="attacking", condition_fn=_is_this_attacking,
               effect_fn=_aegis_on_attack),
])


# -- aether_arc_blue --
# Cost: 0{r}, 1AP. Deal 1 arcane damage to each opposing hero.
# Create a Ponder token for each hero dealt damage this way.
# In 1v1: one opponent, one potential Ponder.
# Ponder is only created if damage actually went through (effect_deal_arcane returns > 0).
def _aether_arc_play(card, event, state):
    cid = _controller_id(card)
    opp_id = 3 - cid
    damage_dealt = effect_deal_arcane(state, opp_id, 1, source=card)
    if damage_dealt > 0:
        create_token(state, cid, "ponder")

_register("aether_arc_blue", [
    TriggerDef(event_type="on_play", effect_fn=_aether_arc_play),
])


# -- aether_dart (red/yellow/blue) --
# "Deal N arcane damage to any target."
# 'any target' = heroes (either player) OR allies (either player) — anything with a {l} value.
# The target is declared at play time and stored in action.target → event.data['target'].
_AETHER_DART_DAMAGE = {"aether_dart_red": 3, "aether_dart_yellow": 2, "aether_dart_blue": 1}

def _aether_dart_play(card, event, state):
    cid = _controller_id(card)
    target = event.data.get('target') if hasattr(event, 'data') else None
    amount = _AETHER_DART_DAMAGE.get(card.slug, 0)
    if target is None:
        # Fallback: no target declared, deal to opposing hero
        effect_deal_arcane(state, 3 - cid, amount, source=card)
        return
    effect_deal_arcane_to_target(state, target, amount, source=card)

for _slug in ("aether_dart_red", "aether_dart_yellow", "aether_dart_blue"):
    _register(_slug, [
        TriggerDef(event_type="on_play", effect_fn=_aether_dart_play),
    ])


# -- aether_hail (red/yellow/blue) --
# "Deal N arcane damage to any target." (cost: 1{r}, 1AP)
# Identical targeting logic to aether_dart — any living object with {l}.
_AETHER_HAIL_DAMAGE = {"aether_hail_red": 4, "aether_hail_yellow": 3, "aether_hail_blue": 2}

def _aether_hail_play(card, event, state):
    cid = _controller_id(card)
    target = event.data.get('target') if hasattr(event, 'data') else None
    amount = _AETHER_HAIL_DAMAGE.get(card.slug, 0)
    if target is None:
        effect_deal_arcane(state, 3 - cid, amount, source=card)
        return
    effect_deal_arcane_to_target(state, target, amount, source=card)

for _slug in ("aether_hail_red", "aether_hail_yellow", "aether_hail_blue"):
    _register(_slug, [
        TriggerDef(event_type="on_play", effect_fn=_aether_hail_play),
    ])


# -- aether_icevein (red/yellow/blue) --
# Cost: 3{r}, 1AP. Optional additional cost: Ice Fusion (reveal an Elemental card from hand).
# Effect: Deal N arcane damage to any target.
# If fused and dealt damage to a hero: that hero's controller discards a card unless they pay {r}{r}.
#   - If hand is empty: skip the choice entirely.
#   - If they can afford {r}{r} (resources + pitching): offer the choice.
#   - If they cannot afford {r}{r}: force discard (agent chooses which card).
_AETHER_ICEVEIN_DAMAGE = {"aether_icevein_red": 5, "aether_icevein_yellow": 4, "aether_icevein_blue": 3}

def _aether_icevein_play(card, event, state):
    cid = _controller_id(card)
    opp_id = 3 - cid

    # Ice Fusion: optional reveal of an Elemental card from hand
    was_fused = fusion(card, "Elemental", state)
    card._was_fused = was_fused

    # Deal arcane damage to any target
    target = event.data.get('target') if hasattr(event, 'data') else None
    amount = _AETHER_ICEVEIN_DAMAGE.get(card.slug, 0)

    if target is None:
        damage_dealt = effect_deal_arcane(state, opp_id, amount, source=card)
        target_is_hero = True
        hit_player_id = opp_id
    else:
        _types = target.types or []
        _subtypes = target.subtypes or []
        target_is_hero = "Hero" in _types
        target_owner = target.controller if target.controller is not None else target.owner
        hit_player_id = target_owner
        damage_dealt = effect_deal_arcane_to_target(state, target, amount, source=card)

    # Fused + hit a hero: discard a card or pay {r}{r}
    if not was_fused or not target_is_hero or damage_dealt <= 0:
        return

    hit_player = state.players[hit_player_id]
    if not hit_player.hand.cards:
        return  # hand empty: skip entirely

    # Check if the player can afford 2{r} (resources + pitching)
    from engine.actions import find_all_valid_pitch_sequences
    hand_for_pitch = list(hit_player.hand.cards)
    needed = max(0, 2 - hit_player.resources)
    can_pay = (hit_player.resources >= 2) or bool(
        find_all_valid_pitch_sequences(hand_for_pitch, needed, hit_player.resources)
    )

    paid = False
    if can_pay:
        choice = _ask_player(state, hit_player_id, [True, False],
                             context="Aether Icevein (fused): pay {r}{r} or discard a card?")
        if choice:
            _pitch_for_cost(hit_player, 2, state)
            paid = True

    if not paid:
        # Force discard: agent chooses which card
        slugs = [c.slug for c in hit_player.hand.cards]
        pick = _ask_player(state, hit_player_id, slugs,
                           context="Aether Icevein (fused): choose a card to discard")
        chosen = hit_player.hand.find(str(pick))
        if chosen is None:
            chosen = hit_player.hand.cards[0]
        hit_player.hand.remove(chosen)
        hit_player.graveyard.add(chosen)

for _slug in ("aether_icevein_red", "aether_icevein_yellow", "aether_icevein_blue"):
    _register(_slug, [
        TriggerDef(event_type="on_play", effect_fn=_aether_icevein_play),
    ])


# -- adrenaline_rush (red/yellow/blue) --
# When you play this, if you have less {h} than an opposing hero, this gets +3{p}.
def _adrenaline_rush_play(card, event, state):
    cid = _controller_id(card)
    opp_id = 3 - cid
    my_health = state.players[cid].health
    opp_health = state.players[opp_id].health
    if my_health < opp_health:
        card.effects.append(("base_power", lambda base: base + 3))

for _slug in ("adrenaline_rush_red", "adrenaline_rush_yellow", "adrenaline_rush_blue"):
    _register(_slug, [
        TriggerDef(event_type="on_play", effect_fn=_adrenaline_rush_play),
    ])


# -- aftershock_blue --
# When this attacks, if you've controlled a Seismic Surge token this turn, create one.
def _aftershock_attacking(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    cid = _controller_id(card)
    # Check either the turn effect flag OR an existing aura (not both)
    has_surge = (
        any("seismic_surge" in eff for eff in state.players[cid].current_turn_effects)
        or any("seismic_surge" in c.slug for c in state.players[cid].auras.cards)
    )
    if has_surge:
        create_token(state, cid, "seismic_surge")

_register("aftershock", [
    TriggerDef(event_type="attacking", effect_fn=_aftershock_attacking),
])

# -- aggressive_pounce --
# If you've intimidated an opponent this turn, this gets go again.
_register("aggressive_pounce", [
    TriggerDef(event_type="attacking",
               effect_fn=_factory_attacking_go_again_if(
                   lambda c, s: any("intimidated" in e for e in
                                    s.players[_controller_id(c)].current_turn_effects))),
])

# -- agile_windup_yellow --
# Instant - Discard this: Create an Agility token.
# This is a discard-activated instant; simplified to on_play create token
_register("agile_windup", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_create_token("agility")),
])

# -- alpha_instinct_blue --
# When this is discarded to beat chest, create a Might token.
# Simplified: on_play create Might
_register("alpha_instinct", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_create_token("might")),
])

# -- ancestral_harmony_blue --
# Your attacks with combo get +1p this turn. Banish top card. Go again.
def _ancestral_harmony_play(card, event, state):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("combo_attacks_+1")
    effect_banish_top_deck(state, cid, 1, face_up=True)

_register("ancestral_harmony", [
    TriggerDef(event_type="on_play", effect_fn=_ancestral_harmony_play),
])

# -- angelic_attendant_yellow --
# Awaken target figment. Put this into soul. Go again.
_register("angelic_attendant", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: effect_move_to_soul(s, c, _controller_id(c))),
])

# -- angelic_wrath (red: +4p, yellow: +3p, blue: +2p) --
# Target attack action card with Herald in its name gets +Np
_register("angelic_wrath_red", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_next_attack_plus(4)),
])
_register("angelic_wrath_yellow", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_next_attack_plus(3)),
])
_register("angelic_wrath_blue", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_next_attack_plus(2)),
])

# -- annihilate_the_armed --
# Contract: on hit banish from top deck, create Silver
_register("annihilate_the_armed", [
    TriggerDef(event_type="hit", effect_fn=_factory_contract_hit("attack_action")),
])

# -- art_of_the_dragon_blood_red --
# When this attacks, if it is Draconic, it gets go again
def _art_dragon_blood_attacking(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    if state.combat and "Go Again" not in state.combat.keywords:
        state.combat.grant_keyword("Go Again")

_register("art_of_the_dragon_blood", [
    TriggerDef(event_type="attacking", effect_fn=_art_dragon_blood_attacking),
])

# -- art_of_the_phoenix_war_red --
# Draconic attack action cards get +1p this turn. Draw 2 cards.
def _art_phoenix_war_play(card, event, state):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("draconic_attacks_+1")
    effect_draw(state, cid, 2)

_register("art_of_the_phoenix_war", [
    TriggerDef(event_type="on_play", effect_fn=_art_phoenix_war_play),
])

# -- assault_and_battery_yellow --
# When this attacks, if you've beaten chest this turn, create Agility
def _assault_battery_attacking(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    cid = _controller_id(card)
    if any("beat_chest" in e for e in state.players[cid].current_turn_effects):
        create_token(state, cid, "agility")

_register("assault_and_battery", [
    TriggerDef(event_type="attacking", effect_fn=_assault_battery_attacking),
])

# -- astral_strike_red --
# When attacks, if destroyed Lightning Flow, choose: draw/+2p/go again. Simplified: +2p
_register("astral_strike", [
    TriggerDef(event_type="attacking", effect_fn=_factory_attacking_plus_power(2)),
])

# -- authority_of_ataya_blue --
# When pitched, DR cards cost opponents additional r. Simplified: noop (pitch trigger)
_register("authority_of_ataya", [
    TriggerDef(event_type="card_pitched",
               effect_fn=lambda c, e, s: None),  # Simplified
])

# -- avast_ye_blue --
# Next Pirate ally attack gets go again and hit-create-Gold. Go again.
_register("avast_ye", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: s.players[_controller_id(c)].current_turn_effects.append(
                   "next_attack_go_again")),
])

# -- back_alley_breakline_blue --
# If put face up into zone from deck, gain 1 AP. Simplified: noop
_register("back_alley_breakline", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_action_point()),
])

# -- backspin_thrust_red --
# Instant: tap cog: +1p or go again. Simplified: +1p on current attack if in combat
def _backspin_thrust_play(card, event, state):
    if state.combat:
        state.combat.attack_power += 1

_register("backspin_thrust", [
    TriggerDef(event_type="on_play", effect_fn=_backspin_thrust_play),
])

# -- banneret_of_courage_yellow --
# Solflare: when charged to soul, create Courage token
_register("banneret_of_courage", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_create_token("courage")),
])

# -- banneret_of_gallantry_yellow --
# Solflare: when charged to soul, create Quicken token
_register("banneret_of_gallantry", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_create_token("quicken")),
])

# -- bare_destruction_red --
# Beat Chest; when attacks, if beaten chest and no chest equipment, go again + next Brute attack +2p
def _bare_destruction_attacking(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    cid = _controller_id(card)
    player = state.players[cid]
    if not any("beat_chest" in e for e in player.current_turn_effects):
        return
    if state.combat and "Go Again" not in state.combat.keywords:
        state.combat.grant_keyword("Go Again")
    player.current_turn_effects.append("next_brute_attack_+2")

_register("bare_destruction", [
    TriggerDef(event_type="attacking", effect_fn=_bare_destruction_attacking),
])

# -- bare_fangs_red --
# When attacks, draw then discard random. If 6+p discarded, +2p.
def _bare_fangs_bonus(card, state):
    if state.combat:
        state.combat.attack_power += 2

_register("bare_fangs", [
    TriggerDef(event_type="attacking",
               effect_fn=_factory_on_attacking_draw_discard_random_6p_bonus(_bare_fangs_bonus)),
])

# -- battered_beaten_and_broken_yellow --
# When attacks a hero, intimidate. If 3+ auras, +3p and on-hit destroy.
def _battered_attacking(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    target_id = 3 - _controller_id(card)
    effect_intimidate(state, target_id)
    cid = _controller_id(card)
    aura_count = len(state.players[cid].auras.cards)
    if aura_count >= 3 and state.combat:
        state.combat.attack_power += 3

_register("battered_beaten_and_broken", [
    TriggerDef(event_type="attacking", effect_fn=_battered_attacking),
])

# -- battlefield_beacon_yellow --
# When attacks, create tokens based on cards banished from soul. Simplified: create Courage.
_register("battlefield_beacon", [
    TriggerDef(event_type="attacking",
               effect_fn=lambda c, e, s: create_token(s, _controller_id(c), "courage")
               if _is_this_attacking(c, e, s) else None),
])

# -- be_like_water_red --
# On hit, go again. Simplified.
_register("be_like_water", [
    TriggerDef(event_type="hit", effect_fn=_factory_on_hit_go_again()),
])

# -- beaming_bravado_red / yellow --
# Optional charge; if yellow charged, +1p
def _beaming_bravado_play(card, event, state):
    cid = _controller_id(card)
    charged = _factory_on_play_charge_optional()(card, event, state)
    if charged and state.combat:
        state.combat.attack_power += 1

_register("beaming_bravado", [
    TriggerDef(event_type="on_play", effect_fn=_beaming_bravado_play, is_optional=True),
])

# -- beast_within_yellow --
# If put into GY from non-combat-chain, banish top deck and lose 1h. Simplified: noop
_register("beast_within", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- become_the_bottle_red --
# When attacks, choose card on combat chain, get its name. Go again. Simplified: noop
_register("become_the_bottle", [
    TriggerDef(event_type="attacking", effect_fn=lambda c, e, s: None),
])

# -- beseech_the_demigon_red --
# Choose attack action in banish, +3p. Go again.
_register("beseech_the_demigon", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_next_attack_plus(3)),
])

# -- bet_big_red --
# "When this attacks a hero, you may wager a Gold, Might, and Vigor token with them."
def _bet_big_attacking(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    from engine.card_effects.card_keywords import add_wager
    cid = _controller_id(card)
    add_wager(state, cid, "gold")
    add_wager(state, cid, "might")
    add_wager(state, cid, "vigor")

_register("bet_big", [
    TriggerDef(event_type="attacking", effect_fn=_bet_big_attacking),
])

# -- big_bertha_blue --
# Boost; when banished from boosting, put steam counter. Simplified: noop
_register("big_bertha", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- bios_update_red --
# Next attack action you boost gets +3p. Simplified: next attack +3p.
_register("bios_update", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_next_attack_plus(3)),
])

# -- bittering_thorns (red/yellow/blue all share: on-hit +1p next attack, go again)
_register("bittering_thorns", [
    TriggerDef(event_type="hit", effect_fn=_factory_on_hit_next_attack_plus(1)),
])

# -- blast_rig_red --
# Evo Upgrade: +1p per Evo equipped. Simplified: +1p
_register("blast_rig", [
    TriggerDef(event_type="attacking", effect_fn=_factory_attacking_plus_power(1)),
])

# -- blaze_headlong_red --
# If you've played another red card this turn, this gets go again.
_register("blaze_headlong", [
    TriggerDef(event_type="attacking",
               effect_fn=_factory_attacking_go_again_if(
                   lambda c, s: _played_red_this_turn(s, _controller_id(c)))),
])

# -- blood_on_her_hands_yellow --
# Kassai Specialization: destroy Coppers for modes. Simplified: +2p.
_register("blood_on_her_hands", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_next_attack_plus(2)),
])

# -- bloodrush_bellow (red: +3p, yellow: +2p, blue: +1p) --
# Discard random, ALL Brute attacks get +Np this turn, if 6+p draw 2 and go again.
def _bloodrush_bellow_play(card, event, state, bonus=2):
    cid = _controller_id(card)
    discarded = effect_discard(state, cid, 1, random_discard=True)
    # "all_attacks_+N" persists for the entire turn (not consumed on first attack)
    state.players[cid].current_turn_effects.append(f"all_attacks_+{bonus}")
    if discarded and discarded[0].power is not None and discarded[0].power >= 6:
        effect_draw(state, cid, 2)
        effect_gain_action_point(state, cid)

_register("bloodrush_bellow_red", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: _bloodrush_bellow_play(c, e, s, bonus=3)),
])
_register("bloodrush_bellow_yellow", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: _bloodrush_bellow_play(c, e, s, bonus=2)),
])
_register("bloodrush_bellow_blue", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: _bloodrush_bellow_play(c, e, s, bonus=1)),
])

# -- bolt_of_courage (red/yellow/blue) --
# Optional charge; if charged this turn, on-hit deal 1 arcane damage.
def _bolt_of_courage_play(card, event, state):
    charged = _factory_on_play_charge_optional()(card, event, state)
    if charged:
        cid = _controller_id(card)
        state.players[cid].class_counters["bolt_of_courage_charged"] = True

def _bolt_of_courage_hit(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    cid = _controller_id(card)
    if state.players[cid].class_counters.pop("bolt_of_courage_charged", False):
        effect_deal_arcane(state, 3 - cid, 1, source=card)

_register("bolt_of_courage", [
    TriggerDef(event_type="on_play", effect_fn=_bolt_of_courage_play, is_optional=True),
    TriggerDef(event_type="hit", effect_fn=_bolt_of_courage_hit),
])

# -- boltn_shot (red/yellow/blue) --
# If power > base, go again and on-hit reload.
def _boltn_shot_attacking(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    if state.combat and state.combat.attack_power > (card.power or 0):
        if "Go Again" not in state.combat.keywords:
            state.combat.grant_keyword("Go Again")

_register("boltn_shot", [
    TriggerDef(event_type="attacking", effect_fn=_boltn_shot_attacking),
])

# -- bonds_of_ancestry_red --
# Combo: if Gustwave was last attack, costs less, go again, on-hit draw.
def _bonds_of_ancestry_play(card, event, state):
    if combo_check(state, ["gustwave"]):
        if state.combat and "Go Again" not in state.combat.keywords:
            state.combat.grant_keyword("Go Again")

_register("bonds_of_ancestry", [
    TriggerDef(event_type="on_play", effect_fn=_bonds_of_ancestry_play),
    TriggerDef(event_type="hit", effect_fn=_factory_on_hit_draw(1)),
])

# -- boneyard_marauder_red --
# Banish 3 random from graveyard. Blood Debt.
_register("boneyard_marauder", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: None),  # Cost handled by engine
])

# -- boulder_drop_red --
# Crush: 4+ dmg, they put card from hand on top of deck (defender chooses).
def _boulder_drop_crush(card, event, state):
    from engine.card_effects.card_keywords import _ask_player
    target_id = 3 - _controller_id(card)
    player = state.players[target_id]
    if player.hand.cards:
        options = [c.slug for c in player.hand.cards]
        choice = _ask_player(state, target_id, options,
                             context="Boulder Drop: choose a card to put on top of your deck")
        idx = options.index(choice) if choice in options else 0
        chosen = player.hand.cards[idx]
        player.hand.remove(chosen)
        player.deck.cards.insert(0, chosen)
        chosen.zone = "deck"

_register("boulder_drop", [
    TriggerDef(event_type="hit", effect_fn=_factory_crush_on_hit(_boulder_drop_crush)),
])

# -- buckwild (red/yellow/blue) --
# If 6+p card in pitch zone, go again.
_register("buckwild", [
    TriggerDef(event_type="attacking",
               effect_fn=_factory_attacking_go_again_if(
                   lambda c, s: _has_6p_in_pitch(s, _controller_id(c)))),
])

# -- burning_blade_dance_red --
# If 2+ Draconic chain links, go again and on-hit dagger deals 1.
def _burning_blade_dance_attacking(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    if _has_draconic_chain_links(state, 2):
        if state.combat and "Go Again" not in state.combat.keywords:
            state.combat.grant_keyword("Go Again")

_register("burning_blade_dance", [
    TriggerDef(event_type="attacking", effect_fn=_burning_blade_dance_attacking),
    TriggerDef(event_type="hit",
               effect_fn=lambda c, e, s: effect_deal_damage(s, 3 - _controller_id(c), 1)
               if _is_this_attacking(c, e, s) and _has_draconic_chain_links(s, 2) else None),
])

# -- call_to_the_grave_blue -- (already may be registered but in gap report)
if "call_to_the_grave" not in CARD_TRIGGERS:
    def _call_to_grave_play(card, event, state):
        cid = _controller_id(card)
        if state.players[cid].deck.cards:
            top = state.players[cid].deck.pop_top()
            state.players[cid].graveyard.add(top)
        effect_shuffle(state, cid)

    _register("call_to_the_grave", [
        TriggerDef(event_type="on_play", effect_fn=_call_to_grave_play),
    ])

# -- celestial_cataclysm_yellow --
# Banish 3 from soul. Go again.
_register("celestial_cataclysm", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: effect_banish_from_soul(s, _controller_id(c), count=3)),
])

# -- censor_red --
# On hit, name a card. Simplified: noop (naming too complex).
_register("censor", [
    TriggerDef(event_type="hit", effect_fn=lambda c, e, s: None),
])

# -- chokeslam (red/blue) --
# Crush: 4+ dmg, attack actions can't gain power next action phase.
_register("chokeslam", [
    TriggerDef(event_type="hit", effect_fn=_factory_crush_on_hit(
        lambda c, e, s: s.players[3 - _controller_id(c)].current_turn_effects.append(
            "cant_gain_power_next_turn"))),
])

# -- cinderskin_devotion_blue --
# If 2+ Draconic chain links, go again.
_register("cinderskin_devotion", [
    TriggerDef(event_type="attacking",
               effect_fn=_factory_attacking_go_again_if(
                   lambda c, s: _has_draconic_chain_links(s, 2))),
])

# -- clash_of_bravado_yellow --
# When defends, clash. Winner destroys an aura. Simplified: clash winner creates token.
_register("clash_of_bravado", [
    TriggerDef(event_type="defend",
               effect_fn=_factory_on_defend_clash_winner_token("might")),
])

# -- cleave_red --
# "Target Axe attack gets +4{p}."
if "next_axe_attack_+4" not in TURN_ATTACK_EFFECTS:
    TURN_ATTACK_EFFECTS["next_axe_attack_+4"] = {
        "condition_fn": lambda ac, pl, st: "Axe" in getattr(ac, 'subtypes', []) or "Axe" in getattr(ac, 'types', []),
        "apply_fn": _make_nap(4),
    }
_register("cleave", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: s.players[_controller_id(c)].current_turn_effects.append("next_axe_attack_+4")),
])

# -- cog_in_the_machine_red --
# Create 2 Golden Cog tokens. Simplified: noop (cog tokens not modeled).
_register("cog_in_the_machine", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- cogwerx_dovetail_red --
# On hit, untap all cogs. Simplified: noop.
_register("cogwerx_dovetail", [
    TriggerDef(event_type="hit", effect_fn=lambda c, e, s: None),
])

# -- cogwerx_workshop_blue --
# Create Golden Cog. Simplified: noop.
_register("cogwerx_workshop", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- cogwerx_zeppelin (red/yellow/blue) --
# On hit, create Golden Cog. Simplified: noop.
_register("cogwerx_zeppelin", [
    TriggerDef(event_type="hit", effect_fn=lambda c, e, s: None),
])

# -- colors_of_aria_red --
# While face-up, it's Earth, Ice, and Lightning. Simplified: noop.
_register("colors_of_aria", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- conqueror_of_the_high_seas_red --
# On hit, destroy arsenal, create Gold per card destroyed.
def _conqueror_hit(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    cid = _controller_id(card)
    target_id = 3 - cid
    target = state.players[target_id]
    count = len(target.arsenal.cards)
    for c in list(target.arsenal.cards):
        target.arsenal.remove(c)
        target.graveyard.add(c)
    for _ in range(count):
        create_token(state, cid, "gold")

_register("conqueror_of_the_high_seas", [
    TriggerDef(event_type="hit", effect_fn=_conqueror_hit),
])

# -- construct_nitro_mechanoid_yellow --
# Transform mechanic. Simplified: noop.
_register("construct_nitro_mechanoid", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- cosmic_duality (red/yellow/blue) --
# Instant discard: deal 1 arcane, create Lightning Flow. Simplified: on_play deal arcane + token.
def _cosmic_duality_play(card, event, state):
    cid = _controller_id(card)
    target_id = 3 - cid
    effect_deal_arcane(state, target_id, 1, source=card)
    create_token(state, cid, "lightning_flow")

_register("cosmic_duality", [
    TriggerDef(event_type="on_play", effect_fn=_cosmic_duality_play),
])

# -- cranial_crush_blue --
# Crush: can't draw next action phase.
_register("cranial_crush", [
    TriggerDef(event_type="hit", effect_fn=_factory_crush_on_hit(
        lambda c, e, s: s.players[3 - _controller_id(c)].current_turn_effects.append(
            "cant_draw_next_turn"))),
])

# -- crash_and_bash_red --
# When defends, if you reveal a card with crush, create Seismic Surge.
def _crash_and_bash_defend(card, event, state):
    if not _is_this_defending(card, event, state):
        return
    cid = _controller_id(card)
    has_crush = any("Crush" in (c.keywords or []) for c in state.players[cid].hand.cards)
    if has_crush:
        create_token(state, cid, "seismic_surge")

_register("crash_and_bash", [
    TriggerDef(event_type="defend", effect_fn=_crash_and_bash_defend),
])

# -- crippling_crush_red --
# Crush: 4+ dmg, discard 2 random.
_register("crippling_crush", [
    TriggerDef(event_type="hit", effect_fn=_factory_crush_on_hit(
        lambda c, e, s: effect_discard(s, 3 - _controller_id(c), 2, random_discard=True))),
])

# -- crowd_goes_wild_yellow --
# If cheered this turn, costs less. Simplified: noop (cost reduction at play time).
_register("crowd_goes_wild", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- cruel_ambition_red --
# Create 3 Might tokens. Go again.
_register("cruel_ambition", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_create_token("might", 3)),
])

# -- cull_red --
# Each hero banishes a card from hand. Go again.
def _cull_play(card, event, state):
    for pid in state.players:
        effect_banish_from_hand(state, pid)

_register("cull", [
    TriggerDef(event_type="on_play", effect_fn=_cull_play),
])

# -- cut_a_long_story_short_yellow --
# If power > base, +1p. Tower: if 13+ power, on-hit discard hand.
def _cut_long_story_attacking(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    if state.combat and state.combat.attack_power > (card.power or 0):
        state.combat.attack_power += 1

_register("cut_a_long_story_short", [
    TriggerDef(event_type="attacking", effect_fn=_cut_long_story_attacking),
])

# -- cut_through_red --
# If hit with dagger this combat chain, +1p and go again.
def _cut_through_attacking(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    cid = _controller_id(card)
    dagger_hit = any("dagger_hit" in e for e in state.players[cid].current_turn_effects)
    if dagger_hit and state.combat:
        state.combat.attack_power += 1
        if "Go Again" not in state.combat.keywords:
            state.combat.grant_keyword("Go Again")

_register("cut_through", [
    TriggerDef(event_type="attacking", effect_fn=_cut_through_attacking),
])

# -- deadwood_dirge_red --
# Destroy an aura you control (player chooses). Create 3 Runechant tokens. Go again.
# CR 5.1.4a: unplayable without an aura (enforced by PLAY_TARGET_CONDITIONS in registry.py)
def _deadwood_dirge_play(card, event, state):
    from engine.card_effects.card_keywords import _ask_player
    cid = _controller_id(card)
    player = state.players[cid]
    if not player.auras.cards:
        return
    options = [c.slug for c in player.auras.cards]
    choice = _ask_player(state, cid, options,
                         context="Deadwood Dirge: choose an aura to destroy")
    idx = options.index(choice) if choice in options else 0
    aura = player.auras.cards[idx]
    _move_to_graveyard(aura, state)
    for _ in range(3):
        create_token(state, cid, "runechant")

_register("deadwood_dirge", [
    TriggerDef(event_type="on_play", effect_fn=_deadwood_dirge_play),
])

# -- deadwood_rumbler_blue --
# Draw then discard random. If 6+p, banish card from a graveyard. Blood Debt.
def _deadwood_rumbler_bonus(card, state):
    pass  # Simplified: banishing from GY not critical for ML

_register("deadwood_rumbler", [
    TriggerDef(event_type="attacking",
               effect_fn=_factory_on_attacking_draw_discard_random_6p_bonus(_deadwood_rumbler_bonus)),
])

# -- deathly_wail (red/yellow/blue) --
# Rune Gate: when combat chain closes, create Runechants.
def _deathly_wail_close(card, event, state):
    cid = _controller_id(card)
    create_token(state, cid, "runechant")

_register("deathly_wail", [
    TriggerDef(event_type="combat_chain_close", effect_fn=_deathly_wail_close),
])

# -- debilitate (red/blue) --
# Crush: 4+ dmg, first attack next turn gets -2p.
_register("debilitate", [
    TriggerDef(event_type="hit", effect_fn=_factory_crush_on_hit(
        lambda c, e, s: s.players[3 - _controller_id(c)].current_turn_effects.append(
            "first_attack_-2p_next_turn"))),
])

# -- deep_recesses_of_existence_blue --
# Rune Gate: combat chain close, banish and create runechant.
_register("deep_recesses_of_existence", [
    TriggerDef(event_type="combat_chain_close",
               effect_fn=lambda c, e, s: create_token(s, _controller_id(c), "runechant")),
])

# -- deep_rooted_evil_yellow --
# Play from banish if 6+p banished this turn. Blood Debt. Simplified: noop.
_register("deep_rooted_evil", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- demonstrate_devotion_red --
# If 2+ Draconic chain links, go again and on-attack create Fealty.
def _demonstrate_devotion_attacking(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    if _has_draconic_chain_links(state, 2):
        if state.combat and "Go Again" not in state.combat.keywords:
            state.combat.grant_keyword("Go Again")
        create_token(state, _controller_id(card), "fealty")

_register("demonstrate_devotion", [
    TriggerDef(event_type="attacking", effect_fn=_demonstrate_devotion_attacking),
])

# -- descendent_gustwave (red/yellow/blue) --
# Combo: if Surging Strike was last, +2p. Go again.
def _descendent_gustwave_play(card, event, state):
    if combo_check(state, ["surging_strike"]):
        if state.combat:
            state.combat.attack_power += 2

_register("descendent_gustwave", [
    TriggerDef(event_type="on_play", effect_fn=_descendent_gustwave_play),
])

# -- diabolic_offering_blue --
# If 6+p banished this turn, power/defense = 6 else 0. Blood Debt. Simplified: noop.
_register("diabolic_offering", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- disable (red/yellow/blue) --
# Crush: 4+ dmg, put arsenal card on bottom of deck.
def _disable_crush(card, event, state):
    target_id = 3 - _controller_id(card)
    target = state.players[target_id]
    if target.arsenal.cards:
        c = target.arsenal.cards[0]
        target.arsenal.remove(c)
        target.deck.cards.append(c)
        c.zone = "deck"

_register("disable", [
    TriggerDef(event_type="hit", effect_fn=_factory_crush_on_hit(_disable_crush)),
])

# -- dishonor_blue --
# Combo: if Bonds of Ancestry was last, +2p. On hit conditional draw.
def _dishonor_play(card, event, state):
    if combo_check(state, ["bonds_of_ancestry"]):
        if state.combat:
            state.combat.attack_power += 2

_register("dishonor", [
    TriggerDef(event_type="on_play", effect_fn=_dishonor_play),
])

# -- display_loyalty_red --
# If 2+ Draconic chain links, go again and create Fealty.
_register("display_loyalty", [
    TriggerDef(event_type="attacking", effect_fn=_demonstrate_devotion_attacking),
])

# -- doomsday_blue --
# Legendary Levia. Play only if 6+ blood debt in banish. Simplified: noop.
_register("doomsday", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- dragon_power_blue --
# When attacks, if Draconic, +3p.
_register("dragon_power", [
    TriggerDef(event_type="attacking", effect_fn=_factory_attacking_plus_power(3)),
])

# -- draw_swords_red --
# Next Warrior attack +3p. Draw. Go again.
def _draw_swords_play(card, event, state):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("next_attack_+3")
    effect_draw(state, cid, 1)

_register("draw_swords", [
    TriggerDef(event_type="on_play", effect_fn=_draw_swords_play),
])

# -- dread_screamer (red/yellow) --
# Banish 3 random from GY. If 6+p banished, +3p and go again.
def _dread_screamer_play(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    import random as rng
    gy_cards = list(player.graveyard.cards)
    if len(gy_cards) >= 3:
        banished_cards = rng.sample(gy_cards, 3)
        has_6p = False
        for c in banished_cards:
            player.graveyard.remove(c)
            effect_banish(state, c, face_up=True)
            if c.power is not None and c.power >= 6:
                has_6p = True
        if has_6p and state.combat:
            state.combat.attack_power += 3
            if "Go Again" not in state.combat.keywords:
                state.combat.grant_keyword("Go Again")

_register("dread_screamer", [
    TriggerDef(event_type="on_play", effect_fn=_dread_screamer_play),
])

# -- drill_shot (red/yellow/blue) --
# If has aim counter, piercing 1. On hit, put -1d counter on equipment.
_register("drill_shot", [
    TriggerDef(event_type="hit",
               effect_fn=lambda c, e, s: None),  # Equipment counter too complex for now
])

# -- drink_em_under_the_table_red --
# "When this attacks a hero, you may wager with them. The winner draws a card."
def _drink_em_attacking(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    from engine.card_effects.card_keywords import add_wager
    cid = _controller_id(card)
    # Wager with no prize token — winner draws determined at resolution
    add_wager(state, cid, None)
    # Simplified: both players get the "winner draws" via the wager_resolved event
    # For now, just draw 1 for the attacker as approximation
    effect_draw(state, cid, 1)

_register("drink_em_under_the_table", [
    TriggerDef(event_type="attacking", effect_fn=_drink_em_attacking),
])

# -- duty_bound_blitz (red/yellow) --
# Play only if yellow card charged this turn. Go again. Simplified: noop.
_register("duty_bound_blitz", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- edict_of_steel_red --
# Sharpen target sword, create Flurry token. Go again.
_register("edict_of_steel", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_create_token("flurry")),
])

# -- elemental_strike_red --
# Banish from hand as cost. Earth: +2p, Lightning: go again, Ice: dominate.
# Simplified: +2p.
_register("elemental_strike", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: (
                   setattr(s.combat, 'attack_power', s.combat.attack_power + 2)
                   if s.combat else None)),
])

# -- eloquent_eulogy_red --
# Rune Gate: on close, if hero lost h, create Eloquence token.
_register("eloquent_eulogy", [
    TriggerDef(event_type="combat_chain_close",
               effect_fn=lambda c, e, s: create_token(s, _controller_id(c), "eloquence")),
])

# -- emboldened_blade_blue --
# Turn face-down arsenal face-up. Simplified: next weapon attack +1p.
_register("emboldened_blade", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_next_attack_plus(1)),
])

# -- endless_arrow_red --
# When this hits, put it back to hand.
def _endless_arrow_hit(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    cid = _controller_id(card)
    effect_return_to_hand(state, card, cid)

_register("endless_arrow", [
    TriggerDef(event_type="hit", effect_fn=_endless_arrow_hit),
])

# -- endless_maw_red --
# Banish 3 from GY. If 6+p, gets dominate.
_register("endless_maw", [
    TriggerDef(event_type="on_play", effect_fn=_dread_screamer_play),
])

# -- enflame_the_firebrand_red --
# If 2+ Draconic chain links, go again. 3+, attacks are Draconic. 4+, +3p.
def _enflame_attacking(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    if _has_draconic_chain_links(state, 2):
        if state.combat and "Go Again" not in state.combat.keywords:
            state.combat.grant_keyword("Go Again")
    if _has_draconic_chain_links(state, 4):
        if state.combat:
            state.combat.attack_power += 3

_register("enflame_the_firebrand", [
    TriggerDef(event_type="attacking", effect_fn=_enflame_attacking),
])

# -- engulfing_light (red) --
# Optional charge; if charged, on-hit deal 1 arcane.
_register("engulfing_light", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_charge_optional(), is_optional=True),
    TriggerDef(event_type="hit",
               effect_fn=lambda c, e, s: effect_deal_arcane(s, 3 - _controller_id(c), 1, source=c)
               if _is_this_attacking(c, e, s) else None),
])

# -- engulfing_shadows_yellow --
# If put into GY, banish instead. Blood Debt. Simplified: noop.
_register("engulfing_shadows", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- enlightened_strike_red --
# Put card from hand on bottom of deck. Choose: +2p or go again or draw. Simplified: +2p.
def _enlightened_strike_play(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    if player.hand.cards:
        c = player.hand.cards[-1]
        player.hand.remove(c)
        player.deck.cards.append(c)
        c.zone = "deck"
    if state.combat:
        state.combat.attack_power += 2

_register("enlightened_strike", [
    TriggerDef(event_type="on_play", effect_fn=_enlightened_strike_play),
])

# -- envelop_in_darkness_red --
# Create Runechant. Next rune gate attack +3p. Go again.
def _envelop_play(card, event, state):
    cid = _controller_id(card)
    create_token(state, cid, "runechant")
    state.players[cid].current_turn_effects.append("next_attack_+3")

_register("envelop_in_darkness", [
    TriggerDef(event_type="on_play", effect_fn=_envelop_play),
])

# -- escalate_violence_blue --
# When attacks, if you control Might, create 3 more.
def _escalate_violence_attacking(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    cid = _controller_id(card)
    has_might = any("might" in c.slug for c in state.players[cid].auras.cards)
    if has_might:
        for _ in range(3):
            create_token(state, cid, "might")

_register("escalate_violence", [
    TriggerDef(event_type="attacking", effect_fn=_escalate_violence_attacking),
])

# -- excessive_bloodloss_red --
# Contract: on hit banish, create Silver.
_register("excessive_bloodloss", [
    TriggerDef(event_type="hit", effect_fn=_factory_contract_hit("red")),
])

# -- express_lightning_red --
# Optional charge.
_register("express_lightning", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_charge_optional(), is_optional=True),
])

# -- eye_of_ophidia_blue --
# When pitched, opt 2. Simplified: noop (pitch trigger).
_register("eye_of_ophidia", [
    TriggerDef(event_type="card_pitched",
               effect_fn=lambda c, e, s: effect_opt(s, _controller_id(c), 2)),
])

# -- fabricate_red --
# Choose 2 modes.
_register("fabricate", [
    TriggerDef(event_type="on_play", effect_fn=_fabricate_on_play),
])

# -- fast_and_furious_red --
# Boost; if cranked, +1p. Simplified: noop.
_register("fast_and_furious", [
    TriggerDef(event_type="attacking", effect_fn=_factory_attacking_plus_power(1)),
])

# -- fearless_confrontation_blue --
# Instant discard: target attack -1p, loses dominate.
_register("fearless_confrontation", [
    TriggerDef(event_type="on_play", effect_fn=_fearless_confrontation_on_play),
])

# -- felling_of_the_crown_red --
# If 4+ Earth in banish, +4p. Decompose.
_register("felling_of_the_crown", [
    TriggerDef(event_type="attacking", effect_fn=_factory_attacking_plus_power(4)),
])

# -- fiddlers_green_red --
# When put into GY from anywhere, gain 3h.
_register("fiddlers_green", [
    TriggerDef(event_type="card_destroyed",
               effect_fn=lambda c, e, s: effect_gain_life(s, _controller_id(c), 3)),
])

# -- figment_of_erudition_yellow --
# When enters arena, create Ponder token.
_register("figment_of_erudition", [
    TriggerDef(event_type="enters_arena", effect_fn=_factory_on_play_create_token("ponder")),
])

# -- figment_of_judgment_yellow --
# When enters arena, turn a card in banish face-down.
_register("figment_of_judgment", [
    TriggerDef(event_type="enters_arena", effect_fn=_figment_of_judgment_enters_arena),
])

# -- figment_of_protection_yellow --
# When enters arena, create Spectral Shield.
_register("figment_of_protection", [
    TriggerDef(event_type="enters_arena",
               effect_fn=lambda c, e, s: create_token(s, _controller_id(c), "spectral_shield")),
])

# -- figment_of_ravages_yellow --
# When enters arena, deal 1 arcane damage.
_register("figment_of_ravages", [
    TriggerDef(event_type="enters_arena",
               effect_fn=lambda c, e, s: effect_deal_arcane(s, 3 - _controller_id(c), 1, source=c)),
])

# -- figment_of_rebirth_yellow --
# When enters arena, put yellow action from GY on top of deck.
_register("figment_of_rebirth", [
    TriggerDef(event_type="enters_arena", effect_fn=_figment_of_rebirth_enters_arena),
])

# -- figment_of_triumph_yellow --
# When enters arena, opponent attack actions -1p this turn.
_register("figment_of_triumph", [
    TriggerDef(event_type="enters_arena",
               effect_fn=lambda c, e, s: s.players[3 - _controller_id(c)].current_turn_effects.append(
                   "attack_actions_-1p")),
])

# -- figment_of_war_yellow --
# When enters arena, create Courage token.
_register("figment_of_war", [
    TriggerDef(event_type="enters_arena",
               effect_fn=lambda c, e, s: create_token(s, _controller_id(c), "courage")),
])

# -- fire_tenet_strike_first_red --
# When attacks, next Draconic attack +1p. Go again.
_register("fire_tenet_strike_first", [
    TriggerDef(event_type="attacking",
               effect_fn=lambda c, e, s: s.players[_controller_id(c)].current_turn_effects.append(
                   "next_attack_+1") if _is_this_attacking(c, e, s) else None),
])

# -- fire_that_burns_within_red --
# When attacks, discard Phoenix Flame for draw +2p. Go again.
def _fire_burns_within_attacking(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    cid = _controller_id(card)
    player = state.players[cid]
    phoenix = next((c for c in player.hand.cards if "phoenix_flame" in c.slug), None)
    if phoenix:
        player.hand.remove(phoenix)
        player.graveyard.add(phoenix)
        effect_draw(state, cid, 1)
        if state.combat:
            state.combat.attack_power += 2
            if "Go Again" not in state.combat.keywords:
                state.combat.grant_keyword("Go Again")

_register("fire_that_burns_within", [
    TriggerDef(event_type="attacking", effect_fn=_fire_burns_within_attacking, is_optional=True),
])

# -- flamecall_awakening_red --
# If played another red, search for Phoenix Flame. Simplified: draw 1 if played red.
_register("flamecall_awakening", [
    TriggerDef(event_type="attacking",
               effect_fn=lambda c, e, s: effect_draw(s, _controller_id(c), 1)
               if _is_this_attacking(c, e, s) and _played_red_this_turn(s, _controller_id(c)) else None),
])

# -- flex_strength_blue --
# If 6+ power, gets +3p.
def _flex_strength_attacking(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    if state.combat and state.combat.attack_power >= 6:
        state.combat.attack_power += 3

_register("flex_strength", [
    TriggerDef(event_type="attacking", effect_fn=_flex_strength_attacking),
])

# -- flowing_stormstrike / meteoric_rise / voltic_impact (shared pattern) --
# Twice per turn instant r: +1p. On hit create Lightning Flow. Simplified: on-hit create token.
for _slug in ["flowing_stormstrike", "meteoric_rise", "voltic_impact"]:
    _register(_slug, [
        TriggerDef(event_type="hit",
                   effect_fn=_factory_on_hit_create_token("lightning_flow")),
    ])

# -- flowstate_embodiment_red --
# Whenever you play an instant this chain link, create Lightning Flow. Simplified: create 1.
_register("flowstate_embodiment", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: create_token(s, _controller_id(c), "lightning_flow")),
])

# -- fluster_fist (red/blue) --
# Combo: if Open the Center was last, +1p per hit this combat chain.
def _fluster_fist_play(card, event, state):
    if combo_check(state, ["open_the_center"]):
        hits = sum(1 for l in getattr(state, 'chain_links', []) if getattr(l, 'hit', False))
        if state.combat and hits > 0:
            state.combat.attack_power += hits

_register("fluster_fist", [
    TriggerDef(event_type="on_play", effect_fn=_fluster_fist_play),
])

# -- for_the_dracai_red --
# When attacks a marked hero, create Fealty.
def _for_the_dracai_attacking(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    target_id = 3 - _controller_id(card)
    if is_marked(state, target_id):
        create_token(state, _controller_id(card), "fealty")

_register("for_the_dracai", [
    TriggerDef(event_type="attacking", effect_fn=_for_the_dracai_attacking),
])

# -- frozen_to_death_blue --
# Ice Fusion: destroy equipment with -1d counter. Create Frostbite. Simplified: noop.
_register("frozen_to_death", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- fruits_of_the_forest (red/yellow/blue) --
# Instant discard: gain 2h. Simplified: on_play gain 2h.
_register("fruits_of_the_forest", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_gain_life(2)),
])

# -- funeral_moon_red --
# Play from banish. Create Runechant. Go again. Blood Debt.
_register("funeral_moon", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_create_token("runechant")),
])

# -- ghost_protocol_architect_red --
# Evo Upgrade. Simplified: noop.
_register("ghost_protocol_architect", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- ghost_protocol_mainframe_blue --
# Evo Upgrade: +1p per Evo. Simplified: +1p.
_register("ghost_protocol_mainframe", [
    TriggerDef(event_type="attacking", effect_fn=_factory_attacking_plus_power(1)),
])

# -- glacial_footsteps_blue --
# Ice Fusion: gains dominate. Simplified: noop (dominate handled by keywords).
_register("glacial_footsteps", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- glistening_steelblade_yellow --
# Next Dawnblade attack has go again. Whenever Dawnblade hits, +1p counter.
_register("glistening_steelblade", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: s.players[_controller_id(c)].current_turn_effects.append(
                   "next_attack_go_again")),
])

# -- golden_skywarden_yellow / skywarden_no161803_yellow --
# Galvanize: when defends, destroy item for +1d. Simplified: noop.
for _slug in ["golden_skywarden", "skywarden_no161803"]:
    _register(_slug, [
        TriggerDef(event_type="defend", effect_fn=lambda c, e, s: None),
    ])

# -- gone_in_a_flash_red -- (already registered, skip)
# -- good_natured_brutality_yellow --
# When defends, if no cards in hand, +6d and crowd cheers.
def _good_natured_defend(card, event, state):
    if not _is_this_defending(card, event, state):
        return
    cid = _controller_id(card)
    if not state.players[cid].hand.cards:
        card.effects.append(("base_defense", lambda base: base + 6))

_register("good_natured_brutality", [
    TriggerDef(event_type="defend", effect_fn=_good_natured_defend),
])

# -- goon_beatdown_blue --
# If 3+ auras, +3p and on-hit crowd boos.
def _goon_beatdown_attacking(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    cid = _controller_id(card)
    if len(state.players[cid].auras.cards) >= 3 and state.combat:
        state.combat.attack_power += 3

_register("goon_beatdown", [
    TriggerDef(event_type="attacking", effect_fn=_goon_beatdown_attacking),
    TriggerDef(event_type="hit",
               effect_fn=lambda c, e, s: effect_crowd_boos(s, _controller_id(c))
               if _is_this_attacking(c, e, s) and len(s.players[_controller_id(c)].auras.cards) >= 3 else None),
])

# -- gorganian_tome --
# Draw X cards where X = 1 + Gorganian Tomes in all graveyards. Go again.
def _gorganian_tome_play(card, event, state):
    cid = _controller_id(card)
    count = 1
    for pid in state.players:
        count += sum(1 for c in state.players[pid].graveyard.cards if "gorganian_tome" in c.slug)
    effect_draw(state, cid, count)

_register("gorganian_tome", [
    TriggerDef(event_type="on_play", effect_fn=_gorganian_tome_play),
])

# -- grandeur_of_valahai_blue --
# When pitched, create Seismic Surge.
_register("grandeur_of_valahai", [
    TriggerDef(event_type="card_pitched",
               effect_fn=lambda c, e, s: create_token(s, _controller_id(c), "seismic_surge")),
])

# -- graveling_growl_yellow --
# Play only if 6+p banished this turn. Blood Debt. Simplified: noop.
_register("graveling_growl", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- gustwave_of_the_second_wind_red --
# Combo: if Surging Strike was last, go again.
_register("gustwave_of_the_second_wind", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: (
                   s.combat.grant_keyword("Go Again")
                   if combo_check(s, ["surging_strike"]) and s.combat and "Go Again" not in s.combat.keywords
                   else None)),
])

# -- headbutt_blue --
# Can't be defended by non-head equipment. Crush: 4+ dmg, discard. Simplified.
_register("headbutt", [
    TriggerDef(event_type="hit", effect_fn=_factory_crush_on_hit(
        lambda c, e, s: effect_discard(s, 3 - _controller_id(c), 1))),
])

# -- heart_of_fyendal_blue --
# When pitched, if less h than opponent, gain 1h.
def _heart_fyendal_pitched(card, event, state):
    cid = _controller_id(card)
    opp_id = 3 - cid
    if state.players[cid].health < state.players[opp_id].health:
        effect_gain_life(state, cid, 1)

_register("heart_of_fyendal", [
    TriggerDef(event_type="card_pitched", effect_fn=_heart_fyendal_pitched),
])

# -- heist_red --
# Boost. On hit, put item from banish into arena. Simplified: noop.
_register("heist", [
    TriggerDef(event_type="hit", effect_fn=lambda c, e, s: None),
])

# -- herald_of_erudition_yellow --
# Dominate. If hits, put into soul and draw 2. Phantasm.
_register("herald_of_erudition", [
    TriggerDef(event_type="hit",
               effect_fn=lambda c, e, s: (
                   effect_move_to_soul(s, c, _controller_id(c)),
                   effect_draw(s, _controller_id(c), 2),
               ) if _is_this_attacking(c, e, s) else None),
])

# -- herald_of_protection (red/yellow/blue) --
# On hit, put into soul and create Spectral Shield.
def _herald_protection_hit(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    cid = _controller_id(card)
    effect_move_to_soul(state, card, cid)
    create_token(state, cid, "spectral_shield")

_register("herald_of_protection", [
    TriggerDef(event_type="hit", effect_fn=_herald_protection_hit),
])

# -- herald_of_ravages_yellow --
# On hit, put into soul and deal 1 arcane.
def _herald_ravages_hit(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    cid = _controller_id(card)
    effect_move_to_soul(state, card, cid)
    effect_deal_arcane(state, 3 - cid, 1, source=card)

_register("herald_of_ravages", [
    TriggerDef(event_type="hit", effect_fn=_herald_ravages_hit),
])

# -- herald_of_rebirth_yellow --
# On hit, put into soul. Simplified.
_register("herald_of_rebirth", [
    TriggerDef(event_type="hit", effect_fn=_factory_on_hit_to_soul()),
])

# -- herald_of_triumph (red/yellow/blue) --
# Attack actions have -1p while defending this. On hit, put into soul.
_register("herald_of_triumph", [
    TriggerDef(event_type="hit", effect_fn=_factory_on_hit_to_soul()),
])

# -- herald_of_victoria_yellow --
# Instant discard: attack actions get -1p. Simplified: noop.
_register("herald_of_victoria", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- hit_and_run (red: +3p, yellow: +2p, blue: +1p) --
# "Your next attack this turn gains go again. If you've attacked with a weapon
#  this turn, your next attack gets +Np."
def _hit_and_run_play(card, event, state, bonus):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("next_attack_go_again")
    # Only add the power bonus if we've attacked with a weapon this turn
    attacked_with_weapon = any(cl.from_weapon for cl in state.chain_links)
    if attacked_with_weapon:
        state.players[cid].current_turn_effects.append(f"next_attack_+{bonus}")

_register("hit_and_run_red", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: _hit_and_run_play(c, e, s, 3)),
])
_register("hit_and_run_yellow", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: _hit_and_run_play(c, e, s, 2)),
])
_register("hit_and_run_blue", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: _hit_and_run_play(c, e, s, 1)),
])

# -- hit_the_gas_blue --
# Maxx: turn Hyper Drivers face-down for AP. Simplified: gain 1 AP.
_register("hit_the_gas", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_action_point()),
])

# -- hold_em (red: +3p, yellow: +2p, blue: +1p) --
# "Next Warrior attack +Np and 'wager a Vigor token with them.'"
if "next_attack_wager_vigor" not in TURN_ATTACK_EFFECTS:
    def _apply_wager_vigor(attack_card, player, state):
        from engine.card_effects.card_keywords import add_wager
        add_wager(state, player.player_id, "vigor")
    TURN_ATTACK_EFFECTS["next_attack_wager_vigor"] = {"apply_fn": _apply_wager_vigor}

def _hold_em_play(card, event, state, bonus):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append(f"next_attack_+{bonus}")
    state.players[cid].current_turn_effects.append("next_attack_wager_vigor")

for _slug, _n in [("hold_em_red", 3), ("hold_em_yellow", 2), ("hold_em_blue", 1)]:
    _register(_slug, [
        TriggerDef(event_type="on_play",
                   effect_fn=(lambda n: lambda c, e, s: _hold_em_play(c, e, s, n))(_n)),
    ])

# -- hostile_encroachment_red --
# On attack, they draw. Crush: 4+ dmg, they discard.
def _hostile_encroachment_attacking(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    target_id = 3 - _controller_id(card)
    effect_draw(state, target_id, 1)

_register("hostile_encroachment", [
    TriggerDef(event_type="attacking", effect_fn=_hostile_encroachment_attacking),
    TriggerDef(event_type="hit", effect_fn=_factory_crush_on_hit(
        lambda c, e, s: effect_discard(s, 3 - _controller_id(c), 1))),
])

# -- hot_on_their_heels_red --
# If 2+ Draconic chain links, go again and on-hit mark.
def _hot_on_heels_attacking(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    if _has_draconic_chain_links(state, 2):
        if state.combat and "Go Again" not in state.combat.keywords:
            state.combat.grant_keyword("Go Again")

_register("hot_on_their_heels", [
    TriggerDef(event_type="attacking", effect_fn=_hot_on_heels_attacking),
    TriggerDef(event_type="hit",
               effect_fn=lambda c, e, s: effect_mark(s, 3 - _controller_id(c))
               if _is_this_attacking(c, e, s) and _has_draconic_chain_links(s, 2) else None),
])

# -- howl_from_beyond_red --
# Play from banish. Next attack +3p. Go again. Blood Debt.
_register("howl_from_beyond", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_next_attack_plus(3)),
])

# -- hulk_up_blue --
# If less h than each other hero, costs r less. Simplified: noop.
_register("hulk_up", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- hundred_winds_red --
# Combo: if Hundred Winds was last, +1p per other Hundred Winds on chain.
_register("hundred_winds", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: (
                   s.combat.__setattr__('attack_power', s.combat.attack_power + 1)
                   if combo_check(s, ["hundred_winds"]) and s.combat else None)),
])

# -- hungering_slaughterbeast_yellow --
# Banish 3 from GY. Blood Debt. Simplified: noop.
_register("hungering_slaughterbeast", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- hunt_the_hunter_red --
# When attacks, if played another red, mark them.
_register("hunt_the_hunter", [
    TriggerDef(event_type="attacking",
               effect_fn=lambda c, e, s: effect_mark(s, 3 - _controller_id(c))
               if _is_this_attacking(c, e, s) and _played_red_this_turn(s, _controller_id(c)) else None),
])

# -- hyper_scrapper_blue --
# Banish X items from GY, +Xp. Simplified: +1p.
_register("hyper_scrapper", [
    TriggerDef(event_type="attacking", effect_fn=_factory_attacking_plus_power(1)),
])

# -- ignite_red --
# When attacks, next Draconic costs r less. Go again.
_register("ignite", [
    TriggerDef(event_type="attacking",
               effect_fn=lambda c, e, s: s.players[_controller_id(c)].current_turn_effects.append(
                   "draconic_cost_-1") if _is_this_attacking(c, e, s) else None),
])

# -- imposing_visage_blue --
# Search deck for aura, put into arena. Shuffle. Go again. Simplified: shuffle.
_register("imposing_visage", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: effect_shuffle(s, _controller_id(c))),
])

# -- infect_red --
# Stealth. On hit, create Bloodrot Pox under opponent.
_register("infect", [
    TriggerDef(event_type="hit", effect_fn=_factory_on_hit_create_token_under_opponent("bloodrot_pox")),
])

# -- inflame_red --
# If played another red, return Phoenix Flame from GY to hand. Go again.
_register("inflame", [
    TriggerDef(event_type="attacking",
               effect_fn=lambda c, e, s: None),  # Simplified
])

# -- insult_to_injury_blue -- (same as base insult_to_injury, already registered for base)
# Re-register with _blue suffix just in case
_register("insult_to_injury_blue", [
    TriggerDef(event_type="attacking",
               effect_fn=lambda c, e, s: (
                   s.combat.grant_keyword("Go Again")
                   if _is_this_attacking(c, e, s) and s.combat
                   and s.players[_controller_id(c)].health > s.players[3 - _controller_id(c)].health
                   and "Go Again" not in s.combat.keywords
                   else None)),
])

# -- ironsong_determination_yellow --
# Target weapon's attacks get +1p and dominate until end of turn. Go again.
_register("ironsong_determination", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_next_attack_plus(1)),
])

# -- isolate (red/yellow/blue) --
# Stealth. Dominate. Both handled by keywords; no extra triggers needed.
_register("isolate", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- jaws_of_victory_red --
# When attacks, if less h, crowd cheers. If cheered, go again.
def _jaws_of_victory_attacking(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    cid = _controller_id(card)
    opp_id = 3 - cid
    if state.players[cid].health < state.players[opp_id].health:
        state.players[cid].current_turn_effects.append("crowd_cheered")
    if any("crowd_cheered" in e for e in state.players[cid].current_turn_effects):
        if state.combat and "Go Again" not in state.combat.keywords:
            state.combat.grant_keyword("Go Again")

_register("jaws_of_victory", [
    TriggerDef(event_type="attacking", effect_fn=_jaws_of_victory_attacking),
])

# -- jittery_bones_blue --
# When attacks, discard/destroy top. If watery grave, go again. Simplified: noop.
_register("jittery_bones", [
    TriggerDef(event_type="attacking", effect_fn=lambda c, e, s: None),
])

# -- jump_start_red --
# If control Hyper Driver, costs r less. Boost. Simplified: noop.
_register("jump_start", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- knife_through (red/yellow/blue) --
# Stealth. If hit with dagger this combat chain, go again.
_register("knife_through", [
    TriggerDef(event_type="attacking",
               effect_fn=_factory_attacking_go_again_if(
                   lambda c, s: any("dagger_hit" in e for e in
                                    s.players[_controller_id(c)].current_turn_effects))),
])

# -- lace_with_bloodrot_red --
# Next arrow attack +3p and on-hit create Bloodrot Pox. Go again.
def _lace_bloodrot_play(card, event, state):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("next_attack_+3")
    state.players[cid].current_turn_effects.append("next_hit_bloodrot_pox")

_register("lace_with_bloodrot", [
    TriggerDef(event_type="on_play", effect_fn=_lace_bloodrot_play),
])

# -- lava_burst_red --
# Rupture: if chain link 4+, +3p.
_register("lava_burst", [
    TriggerDef(event_type="attacking",
               effect_fn=lambda c, e, s: (
                   setattr(s.combat, 'attack_power', s.combat.attack_power + 3)
                   if _is_this_attacking(c, e, s) and s.combat and rupture_check(s) else None)),
])

# -- lava_vein_loyalty_blue --
# If 2+ Draconic chain links, go again.
_register("lava_vein_loyalty", [
    TriggerDef(event_type="attacking",
               effect_fn=_factory_attacking_go_again_if(
                   lambda c, s: _has_draconic_chain_links(s, 2))),
])

# -- lead_with_speed_red --
# Next Brute/Warrior attack +3p. Create Agility. Go again.
def _lead_with_speed_play(card, event, state):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("next_attack_+3")
    create_token(state, cid, "agility")

_register("lead_with_speed", [
    TriggerDef(event_type="on_play", effect_fn=_lead_with_speed_play),
])

# -- light_of_sol_yellow --
# When pitched, reveal top. If yellow, put into soul. Simplified: noop.
_register("light_of_sol", [
    TriggerDef(event_type="card_pitched", effect_fn=lambda c, e, s: None),
])

# -- lightning_press_red --
# Target attack action with cost <=1 gets +3p.
_register("lightning_press", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_next_attack_plus(3)),
])

# -- lobotomy_red --
# Stealth. On attack equip Orbitoclast. On hit if control Orbitoclast, lose hero abilities.
# Card text: "they lose all hero card abilities during their next action phase."
# Simplified: noop (hero ability suppression too complex for ML sim).
_register("lobotomy", [
    TriggerDef(event_type="hit",
               effect_fn=lambda c, e, s: None),
])

# -- loot_the_hold_blue --
# Next Pirate ally attack gets on-hit discard + Gold. Go again. Simplified: next attack +1p.
_register("loot_the_hold", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_next_attack_plus(1)),
])

# -- lumina_ascension_yellow --
# Boltyn: weapons +1p, on-hit charge-if-Light. Go again. Simplified: next attack +1p.
_register("lumina_ascension", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_next_attack_plus(1)),
])

# -- machinations_of_dominion_blue --
# Next Runeblade attack gets overpower and conditional go again.
_register("machinations_of_dominion", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: s.players[_controller_id(c)].current_turn_effects.append(
                   "next_attack_overpower")),
])

# -- mark_of_the_beast_yellow --
# If put into GY, banish instead. Blood Debt. Simplified: noop.
_register("mark_of_the_beast", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- mauvrion_skies_red --
# Next runeblade attack gets go again and on-hit 3 Runechants.
def _mauvrion_skies_play(card, event, state):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("next_attack_go_again")
    state.players[cid].current_turn_effects.append("next_hit_3_runechants")

_register("mauvrion_skies", [
    TriggerDef(event_type="on_play", effect_fn=_mauvrion_skies_play),
])

# -- maximum_velocity_red --
# Play only if boosted 3+ times. Simplified: noop.
_register("maximum_velocity", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- meet_madness_red --
# Stealth. On hit, random: banish from hand or arsenal. Simplified: banish from hand.
_register("meet_madness", [
    TriggerDef(event_type="hit",
               effect_fn=lambda c, e, s: effect_banish_from_hand(s, 3 - _controller_id(c))
               if _is_this_attacking(c, e, s) else None),
])

# -- minnowism_red --
# Next attack with base <=3 gets +3p. Go again.
_register("minnowism", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_next_attack_plus(3)),
])

# -- money_where_ya_mouth_is (red: +3p, yellow: +2p, blue: +1p) --
# "Next attack gets +Np and 'When this attacks a hero, you may wager a Gold token with them.'"
def _money_where_play(card, event, state, bonus):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append(f"next_attack_+{bonus}")
    state.players[cid].current_turn_effects.append("next_attack_wager_gold")

# Register a TURN_ATTACK_EFFECTS entry for the wager
if "next_attack_wager_gold" not in TURN_ATTACK_EFFECTS:
    def _apply_wager_gold(attack_card, player, state):
        from engine.card_effects.card_keywords import add_wager
        add_wager(state, player.player_id, "gold")
    TURN_ATTACK_EFFECTS["next_attack_wager_gold"] = {"apply_fn": _apply_wager_gold}

_register("money_where_ya_mouth_is_red", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: _money_where_play(c, e, s, 3)),
])
_register("money_where_ya_mouth_is_yellow", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: _money_where_play(c, e, s, 2)),
])
_register("money_where_ya_mouth_is_blue", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: _money_where_play(c, e, s, 1)),
])

# -- mordred_tide_red --
# Until end of turn, Runechant creation +1. Go again. Simplified: create 1 Runechant.
_register("mordred_tide", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: (
                   create_token(s, _controller_id(c), "runechant"),
                   s.players[_controller_id(c)].current_turn_effects.append("runechant_+1"),
               )),
])

# -- murky_water_red --
# Riptide: if aim counter, +1p and dominate. On hit, banish traps.
_register("murky_water", [
    TriggerDef(event_type="attacking", effect_fn=_factory_attacking_plus_power(1)),
])

# -- nebula_duality (red/yellow/blue) --
# Deal arcane damage. Instant discard: deal 1 arcane + Lightning Flow.
for _slug, _dmg in [("nebula_duality_red", 3), ("nebula_duality_yellow", 2), ("nebula_duality_blue", 1)]:
    _register(_slug, [
        TriggerDef(event_type="on_play",
                   effect_fn=_factory_on_play_deal_arcane(_dmg)),
    ])

# -- no_hero_stands_alone_yellow --
# If Toughness this turn, +3d and ambush. On defend, clash. Simplified: noop.
_register("no_hero_stands_alone", [
    TriggerDef(event_type="defend", effect_fn=lambda c, e, s: None),
])

# -- oaken_old_red --
# Earth/Ice Fusion: +2p, dominate, on-hit opponent puts 2 from hand to top deck.
_register("oaken_old", [
    TriggerDef(event_type="attacking", effect_fn=_factory_attacking_plus_power(2)),
])

# -- oasis_respite_red --
# Prevent 4 damage. If less life, also gain 2h. Simplified: gain 2h.
_register("oasis_respite", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_gain_life(2)),
])

# -- oath_of_loyalty_red --
# First action of turn only. Only play Draconic. Go again. Simplified: noop.
_register("oath_of_loyalty", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- oblivion_blue --
# Legendary Vynnset. Create Nasreth token. Simplified: noop.
_register("oblivion", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- out_pace_red --
# Boost. Can't be defended by equipment. Simplified: noop.
_register("out_pace", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- outland_skirmish_red --
# Next 1H weapon +3p. On weapon hit, create Copper. Go again.
def _outland_skirmish_play(card, event, state):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("next_attack_+3")

_register("outland_skirmish", [
    TriggerDef(event_type="on_play", effect_fn=_outland_skirmish_play),
])

# -- outside_interference_blue --
# Instant discard: reveal Reviled from inventory to hand. Simplified: draw 1.
_register("outside_interference", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_draw(1)),
])

# -- pain_in_the_backside_red -- (already registered)

# -- palantir_aeronought_red --
# Must defend with equipment. Cog taps for +1p. Simplified: noop.
_register("palantir_aeronought", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- persuasive_prognosis_blue --
# Stealth. On hit, banish top of deck then banish matching color from hand. Simplified.
_register("persuasive_prognosis", [
    TriggerDef(event_type="hit", effect_fn=_factory_on_hit_banish_top_deck(1)),
])

# -- phoenix_bannerman_head_red --
# Search for Phoenix Flame, create Ponder. Go again.
def _phoenix_bannerman_play(card, event, state):
    cid = _controller_id(card)
    create_token(state, cid, "ponder")

_register("phoenix_bannerman_head", [
    TriggerDef(event_type="on_play", effect_fn=_phoenix_bannerman_play),
])

# -- phoenix_flame_red --
# If 2+ Draconic chain links, Phoenix Flame has go again.
_register("phoenix_flame", [
    TriggerDef(event_type="attacking",
               effect_fn=_factory_attacking_go_again_if(
                   lambda c, s: _has_draconic_chain_links(s, 2))),
])

# -- pledge_fealty_red --
# Create a Fealty token.
_register("pledge_fealty", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_create_token("fealty")),
])

# -- plunder_the_poor_red --
# Contract: on hit banish, create Silver.
_register("plunder_the_poor", [
    TriggerDef(event_type="hit", effect_fn=_factory_contract_hit("cost_1_or_less")),
])

# -- pound_of_flesh_blue --
# Each hero banishes from hand. If not 6+p, lose 1h. Go again.
def _pound_of_flesh_play(card, event, state):
    for pid in state.players:
        banished_list = effect_banish_from_hand(state, pid)
        for banished in banished_list:
            if banished.power is None or banished.power < 6:
                effect_lose_life(state, pid, 1)

_register("pound_of_flesh", [
    TriggerDef(event_type="on_play", effect_fn=_pound_of_flesh_play),
])

# -- power_play_blue --
# If played from arsenal, +5p.
def _power_play_attacking(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    cid = _controller_id(card)
    if any("from_arsenal" in e for e in state.players[cid].current_turn_effects):
        if state.combat:
            state.combat.attack_power += 5

_register("power_play", [
    TriggerDef(event_type="attacking", effect_fn=_power_play_attacking),
])

# -- premeditate_red --
# Next hit creates Ponder. Next from arsenal +3p. Go again.
def _premeditate_play(card, event, state):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("next_hit_ponder")
    state.players[cid].current_turn_effects.append("next_attack_+3")

_register("premeditate", [
    TriggerDef(event_type="on_play", effect_fn=_premeditate_play),
])

# -- prismatic_leyline_yellow --
# Next red attack +1p, yellow +2p, blue +3p. Go again. Simplified: next attack +2p.
_register("prismatic_leyline", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_next_attack_plus(2)),
])

# -- pulping_red --
# When attacks, draw then discard random. If 6+p, dominate. Simplified.
def _pulping_bonus(card, state):
    if state.combat:
        state.combat.grant_keyword("Dominate") if "Dominate" not in state.combat.keywords else None

_register("pulping", [
    TriggerDef(event_type="attacking",
               effect_fn=_factory_on_attacking_draw_discard_random_6p_bonus(_pulping_bonus)),
])

# -- pulsewave_harpoon_red --
# When attacks, reveal X cards (boost count). Simplified: noop.
_register("pulsewave_harpoon", [
    TriggerDef(event_type="attacking", effect_fn=lambda c, e, s: None),
])

# -- pulverize_red --
# Heave 3. If hits, first attack next turn -4p. Simplified.
_register("pulverize", [
    TriggerDef(event_type="hit",
               effect_fn=lambda c, e, s: s.players[3 - _controller_id(c)].current_turn_effects.append(
                   "first_attack_-4p_next_turn") if _is_this_attacking(c, e, s) else None),
])

# -- put_em_in_their_place_red --
# Crush: discard hand then draw that many.
def _put_em_crush(card, event, state):
    target_id = 3 - _controller_id(card)
    target = state.players[target_id]
    count = len(target.hand.cards)
    for c in list(target.hand.cards):
        target.hand.remove(c)
        target.graveyard.add(c)
    effect_draw(state, target_id, count)

_register("put_em_in_their_place", [
    TriggerDef(event_type="hit", effect_fn=_factory_crush_on_hit(_put_em_crush)),
])

# -- quickening_sand_blue --
# Create Quicken under target hero. Go again.
_register("quickening_sand", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_create_token("quicken")),
])

# -- raise_an_army_yellow --
# Kassai: destroy X Gold, create X Cintari Sellsword. Simplified: noop.
_register("raise_an_army", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- ravenous_rabble_red --
# When attacks, reveal top, -Xp where X = pitch value.
def _ravenous_rabble_attacking(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    cid = _controller_id(card)
    cards = effect_look_top(state, cid, 1)
    if cards and cards[0].pitch and state.combat:
        state.combat.attack_power -= cards[0].pitch

_register("ravenous_rabble", [
    TriggerDef(event_type="attacking", effect_fn=_ravenous_rabble_attacking),
])

# -- reapers_call_blue --
# Stealth Instant discard: Mark target. Simplified: on_play mark.
_register("reapers_call", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_mark()),
])

# -- relentless_pursuit_blue --
# Mark target. If attacked them, put to bottom of deck. Go again. Simplified: mark.
_register("relentless_pursuit", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_mark()),
])

# -- remembrance_yellow --
# Shuffle up to 3 action cards from GY into deck. Banish this.
def _remembrance_play(card, event, state):
    cid = _controller_id(card)
    effect_shuffle(state, cid)
    effect_banish(state, card, face_up=True)

_register("remembrance", [
    TriggerDef(event_type="on_play", effect_fn=_remembrance_play),
])

# -- remorseless_red --
# If put face up in arsenal, DR cards can't be played from arsenal. Simplified: noop.
_register("remorseless", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- retrace_the_past_blue --
# Katsu Combo: name card, search for it. Simplified: draw 1 if combo.
_register("retrace_the_past", [
    TriggerDef(event_type="attacking",
               effect_fn=lambda c, e, s: effect_draw(s, _controller_id(c), 1)
               if _is_this_attacking(c, e, s) and combo_check(s, ["gustwave"]) else None),
])

# -- return_fire_red --
# When defends, banish arrow from hand. Next turn it goes to arsenal +3p. Simplified: noop.
_register("return_fire", [
    TriggerDef(event_type="defend", effect_fn=lambda c, e, s: None),
])

# -- right_behind_you_blue --
# When defends with another from hand, +1d and opt 1.
def _right_behind_you_defend(card, event, state):
    if not _is_this_defending(card, event, state):
        return
    if state.combat and len(state.combat.defending_cards) >= 2:
        card.effects.append(("base_defense", lambda base: base + 1))

_register("right_behind_you", [
    TriggerDef(event_type="defend", effect_fn=_right_behind_you_defend),
])

# -- righteous_cleansing_yellow --
# Crush: look at top 5 of their deck, banish same-name. Simplified: crush banish top 1.
_register("righteous_cleansing", [
    TriggerDef(event_type="hit", effect_fn=_factory_crush_on_hit(
        lambda c, e, s: effect_banish_top_deck(s, 3 - _controller_id(c), 1, face_up=True))),
])

# -- rip_off_the_top_yellow --
# Draw, pitch random. If 6+p, next attack +3p. Go again.
def _rip_off_top_play(card, event, state):
    cid = _controller_id(card)
    effect_draw(state, cid, 1)
    discarded = effect_discard(state, cid, 1, random_discard=True)
    if discarded and discarded[0].power is not None and discarded[0].power >= 6:
        state.players[cid].current_turn_effects.append("next_attack_+3")

_register("rip_off_the_top", [
    TriggerDef(event_type="on_play", effect_fn=_rip_off_top_play),
])

# -- ripple_away_blue --
# Instant discard: token creation -1. Simplified: noop.
_register("ripple_away", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- rise_from_the_ashes (red: +3p, blue: +1p) --
# Next Draconic/Ninja attack +Np. Return Phoenix Flame from GY. Go again.
_register("rise_from_the_ashes_red", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_next_attack_plus(3)),
])
_register("rise_from_the_ashes_blue", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_next_attack_plus(1)),
])

# -- rising_resentment (red/yellow/blue) --
# On hit, may banish attack action from hand. Simplified: noop.
_register("rising_resentment", [
    TriggerDef(event_type="hit", effect_fn=lambda c, e, s: None),
])

# -- roaring_beam_yellow --
# Create Courage. If no cards in soul, return to hand then charge. Simplified: create Courage.
_register("roaring_beam", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_create_token("courage")),
])

# -- rockyard_rodeo_blue --
# Power = highest base power of weapons you control. Simplified: noop (set at play).
_register("rockyard_rodeo", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- rouse_the_ancients_blue --
# Reveal attack actions from hand with 13+ total power. Conditional. Simplified: noop.
_register("rouse_the_ancients", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- rowdy_locals_blue --
# "If Rowdy Locals is defended by an attack action card, it gets +2{p}."
# On hit, each player discards a card.
def _rowdy_locals_defend_bonus(card, event, state):
    """Apply +2{p} only if defended by an attack action card."""
    if not state.combat or state.combat.attack_card is not card:
        return
    if any(c.is_action and "Attack" in getattr(c, 'types', []) for c in state.combat.defending_cards):
        state.combat.attack_power += 2

_register("rowdy_locals", [
    TriggerDef(event_type="defend",
               effect_fn=_rowdy_locals_defend_bonus),
    TriggerDef(event_type="hit",
               effect_fn=lambda c, e, s: (
                   effect_discard(s, _controller_id(c), 1),
                   effect_discard(s, 3 - _controller_id(c), 1),
               ) if _is_this_attacking(c, e, s) else None),
])

# -- sack_the_shifty_red --
# Contract: on hit banish, create Silver.
_register("sack_the_shifty", [
    TriggerDef(event_type="hit", effect_fn=_factory_contract_hit("go_again")),
])

# -- salt_the_wound_yellow --
# +1p per hit this combat chain.
def _salt_wound_attacking(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    hits = sum(1 for l in getattr(state, 'chain_links', []) if getattr(l, 'hit', False))
    if state.combat and hits > 0:
        state.combat.attack_power += hits

_register("salt_the_wound", [
    TriggerDef(event_type="attacking", effect_fn=_salt_wound_attacking),
])

# -- saltwater_swell (red/blue) --
# When attacks, reveal top. If blue, pitch it. Go again.
def _saltwater_swell_attacking(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    cid = _controller_id(card)
    cards = effect_look_top(state, cid, 1)
    if cards and cards[0].pitch == 3:  # Blue = pitch 3
        top = state.players[cid].deck.pop_top()
        if top:
            state.players[cid].pitch.add(top)
            state.players[cid].resources += top.pitch or 0

_register("saltwater_swell", [
    TriggerDef(event_type="attacking", effect_fn=_saltwater_swell_attacking),
])

# -- sand_sketched_plan_blue --
# Rhinar: search for card, put to hand, discard random, shuffle. Simplified: draw 1.
_register("sand_sketched_plan", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_draw(1)),
])

# -- savage_feast_red --
# Discard random cost. If 6+p discarded, +2p and go again.
def _savage_feast_play(card, event, state):
    cid = _controller_id(card)
    discarded = effect_discard(state, cid, 1, random_discard=True)
    if discarded and discarded[0].power is not None and discarded[0].power >= 6:
        if state.combat:
            state.combat.attack_power += 2
            if "Go Again" not in state.combat.keywords:
                state.combat.grant_keyword("Go Again")

_register("savage_feast", [
    TriggerDef(event_type="on_play", effect_fn=_savage_feast_play),
])

# -- sea_legs_yellow --
# When discarded, create Goldkiss Rum token. Simplified: noop (discard trigger).
_register("sea_legs", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- searing_shot (red/yellow/blue) --
# If hits, they lose 1h.
_register("searing_shot", [
    TriggerDef(event_type="hit", effect_fn=_factory_on_hit_lose_life(1)),
])

# -- seek_and_destroy_red --
# Next arrow +3p, on hit at next end phase discard all. Simplified: next attack +3p.
_register("seek_and_destroy", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_next_attack_plus(3)),
])

# -- seismic_eruption_yellow --
# Create 3 Seismic Surge tokens.
_register("seismic_eruption", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_create_token("seismic_surge", 3)),
])

# -- send_packing_yellow --
# On attack, banish from their arsenal. If miss, return it. Simplified: noop.
_register("send_packing", [
    TriggerDef(event_type="attacking",
               effect_fn=lambda c, e, s: None),
])

# -- shadow_puppetry_red --
# Next attack +1p, go again, on-hit look at top then banish face down. Go again.
def _shadow_puppetry_play(card, event, state):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("next_attack_+1")
    state.players[cid].current_turn_effects.append("next_attack_go_again")

_register("shadow_puppetry", [
    TriggerDef(event_type="on_play", effect_fn=_shadow_puppetry_play),
])

# -- shadowrealm_horror_red --
# Banish 3 from GY. If 6+p banished, +3p. Blood Debt.
_register("shadowrealm_horror", [
    TriggerDef(event_type="on_play", effect_fn=_dread_screamer_play),
])

# -- shake_down_red --
# Uzuri: if played AR this chain link, on-hit name a color, banish revealed. Simplified.
_register("shake_down", [
    TriggerDef(event_type="hit", effect_fn=_factory_on_hit_banish_top_deck(1)),
])

# -- sharpen_steel_red --
# Next weapon attack +3p. Go again.
_register("sharpen_steel", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_next_attack_plus(3)),
])

# -- short_shrift_yellow --
# If power > base, +1p. Crush: 4+ dmg, discard.
def _short_shrift_attacking(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    if state.combat and state.combat.attack_power > (card.power or 0):
        state.combat.attack_power += 1

_register("short_shrift", [
    TriggerDef(event_type="attacking", effect_fn=_short_shrift_attacking),
    TriggerDef(event_type="hit", effect_fn=_factory_crush_on_hit(
        lambda c, e, s: effect_discard(s, 3 - _controller_id(c), 1))),
])

# -- sigil_of_solace_red -- (same as sigil_of_solace, already base registered, this is red variant)
_register("sigil_of_solace_red", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: effect_gain_life(s, _controller_id(c), 3)),
])

# -- singularity_red --
# Legendary Teklovossen. Transform mechanic. Simplified: noop.
_register("singularity", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- sirens_of_safe_harbor (red/yellow/blue) --
# When put into GY from anywhere, gain 1h.
_register("sirens_of_safe_harbor", [
    TriggerDef(event_type="card_destroyed",
               effect_fn=lambda c, e, s: effect_gain_life(s, _controller_id(c), 1)),
])

# -- sky_skimmer (red/yellow/blue) --
# Cog tap: +1p or go again. Simplified: noop.
_register("sky_skimmer", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- slice_and_dice (red/yellow/blue) --
# First weapon attack +1p, second +1p, third +1p. Simplified: next attack +1p.
_register("slice_and_dice", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_next_attack_plus(1)),
])

# -- slay_the_scholars_red --
# Contract: on hit banish, create Silver.
_register("slay_the_scholars", [
    TriggerDef(event_type="hit", effect_fn=_factory_contract_hit("non_attack_action")),
])

# -- smoldering_steel_red --
# Target dagger +1p, on-hit deal 1. Simplified: on-hit deal 1.
_register("smoldering_steel", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: s.players[_controller_id(c)].current_turn_effects.append(
                   "next_attack_+1")),
])

# -- snatch_red --
# On hit, draw a card.
_register("snatch", [
    TriggerDef(event_type="hit", effect_fn=_factory_on_hit_draw(1)),
])

# -- sonata_galaxia_red --
# Costs r less per Runechant. Search for Runeblade aura. Go again. Simplified: shuffle.
_register("sonata_galaxia", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: effect_shuffle(s, _controller_id(c))),
])

# -- song_of_sinew_yellow --
# Reveal top 4. Next attack +Xp where X = count of 6+p cards. Simplified: +1p.
_register("song_of_sinew", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_next_attack_plus(1)),
])

# -- soul_harvest_blue --
# Legendary Levia. Banish 6 from GY. +1p per 6+p banished. Blood Debt. Simplified: noop.
_register("soul_harvest", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- soup_up (red/yellow/blue) --
# If item destroyed, go again. Galvanize: destroy item for +1d. Simplified: noop.
_register("soup_up", [
    TriggerDef(event_type="defend", effect_fn=lambda c, e, s: None),
])

# -- spark_of_genius_yellow --
# Dash: search for Mech item. Boost. Simplified: noop.
_register("spark_of_genius", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- speed_demon_red --
# If Hyper Driver, +1p. If scrapped HD, create HD token. Simplified: +1p.
_register("speed_demon", [
    TriggerDef(event_type="attacking", effect_fn=_factory_attacking_plus_power(1)),
])

# -- spinal_crush_red --
# Crush: attacks lose go again next turn.
_register("spinal_crush", [
    TriggerDef(event_type="hit", effect_fn=_factory_crush_on_hit(
        lambda c, e, s: s.players[3 - _controller_id(c)].current_turn_effects.append(
            "cant_go_again_next_turn"))),
])

# -- spirit_of_war_red --
# Optional charge. If yellow charged, weapon hits create Courage. Simplified: charge.
_register("spirit_of_war", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_charge_optional(), is_optional=True),
])

# -- splatter_skull_red --
# On hit, choose face-down intimidated card, put into GY. Simplified: noop.
_register("splatter_skull", [
    TriggerDef(event_type="hit", effect_fn=lambda c, e, s: None),
])

# -- spoils_of_war_red --
# Next weapon attack +2p and go again. Whenever weapon hits, create 2 Copper. Go again.
def _spoils_of_war_play(card, event, state):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("next_attack_+2")
    state.players[cid].current_turn_effects.append("next_attack_go_again")

_register("spoils_of_war", [
    TriggerDef(event_type="on_play", effect_fn=_spoils_of_war_play),
])

# -- spreading_flames_red --
# Draconic attacks +1p while base < Draconic chain links. Go again. Simplified: noop.
_register("spreading_flames", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: s.players[_controller_id(c)].current_turn_effects.append(
                   "draconic_attacks_+1")),
])

# -- sprocket_rocket_red --
# Boost. If item/equip banished from boosting, +1p. Simplified: +1p.
_register("sprocket_rocket", [
    TriggerDef(event_type="attacking", effect_fn=_factory_attacking_plus_power(1)),
])

# -- standing_ovation_blue --
# If 3+ suspense auras left arena, on-hit extra turn. Simplified: noop.
_register("standing_ovation", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- star_struck_yellow --
# Crush: only attacks are actions with Bravo. Simplified: crush effect noop.
_register("star_struck", [
    TriggerDef(event_type="hit", effect_fn=_factory_crush_on_hit(lambda c, e, s: None)),
])

# -- steel_street_enforcement_blue --
# Evo Upgrade: +Xd where X = Evos equipped. Simplified: +1d while defending.
_register("steel_street_enforcement", [
    TriggerDef(event_type="defend",
               effect_fn=lambda c, e, s: c.effects.append(("base_defense", lambda base: base + 1))
               if _is_this_defending(c, e, s) else None),
])

# -- steelblade_supremacy_red --
# Dorinthea: weapon +2p, on-hit draw. Go again.
def _steelblade_supremacy_play(card, event, state):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("next_attack_+2")
    state.players[cid].current_turn_effects.append("weapon_hit_draw")

_register("steelblade_supremacy", [
    TriggerDef(event_type="on_play", effect_fn=_steelblade_supremacy_play),
])

# -- strongest_survive_yellow --
# On hit, discard unless reveal card with power > damage dealt. Simplified: on-hit discard 1.
_register("strongest_survive", [
    TriggerDef(event_type="hit", effect_fn=_factory_on_hit_discard(1)),
])

# -- succumb_to_temptation_yellow --
# If dealt arcane, play as instant. Next runeblade hit creates 2 Runechants. Simplified: create 2.
_register("succumb_to_temptation", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: (
                   create_token(s, _controller_id(c), "runechant"),
                   create_token(s, _controller_id(c), "runechant"),
               )),
])

# -- supercell_blue --
# Put X steam counters on X Hyper Drivers. Create Hyper Driver token. Simplified: noop.
_register("supercell", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- surgical_extraction_blue --
# Contract: on hit banish, create Silver.
_register("surgical_extraction", [
    TriggerDef(event_type="hit", effect_fn=_factory_contract_hit("blue")),
])

# -- swordmasters_shine_red --
# Costs r less per +1p counter on swords. Target weapon +5p. Simplified: next attack +5p.
_register("swordmasters_shine", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_next_attack_plus(5)),
])

# -- tbone_red --
# If boosted on chain, must defend with equipment. Boost. Simplified: noop.
_register("tbone", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- tear_asunder_blue --
# Next Guardian attack +1p, dominate, on-hit discard 2. Go again.
def _tear_asunder_play(card, event, state):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("next_attack_+1")

_register("tear_asunder", [
    TriggerDef(event_type="on_play", effect_fn=_tear_asunder_play),
])

# -- tectonic_instability_blue --
# Each hero puts arsenal on bottom. Draw if they do. Create Seismic Surge per card.
def _tectonic_instability_play(card, event, state):
    count = 0
    for pid in state.players:
        player = state.players[pid]
        if player.arsenal.cards:
            c = player.arsenal.cards[0]
            player.arsenal.remove(c)
            player.deck.cards.append(c)
            c.zone = "deck"
            effect_draw(state, pid, 1)
            count += 1
    cid = _controller_id(card)
    for _ in range(count):
        create_token(state, cid, "seismic_surge")

_register("tectonic_instability", [
    TriggerDef(event_type="on_play", effect_fn=_tectonic_instability_play),
])

# -- teklo_trebuchet_2000_blue --
# When attacks, next boost this chain +2p. Boost. Simplified: noop.
_register("teklo_trebuchet_2000", [
    TriggerDef(event_type="attacking", effect_fn=lambda c, e, s: None),
])

# -- tempest_palm_gustwave_yellow --
# Combo: if Surging Strike was last, +2p. If chain link 3+, go again.
def _tempest_palm_play(card, event, state):
    if combo_check(state, ["surging_strike"]):
        if state.combat:
            state.combat.attack_power += 2
    chain_len = len(getattr(state, 'chain_links', [])) + 1
    if chain_len >= 3 and state.combat and "Go Again" not in state.combat.keywords:
        state.combat.grant_keyword("Go Again")

_register("tempest_palm_gustwave", [
    TriggerDef(event_type="on_play", effect_fn=_tempest_palm_play),
])

# -- terminator_tank_red --
# Evo-based bonuses. Simplified: on-hit discard 1.
_register("terminator_tank", [
    TriggerDef(event_type="hit", effect_fn=_factory_on_hit_discard(1)),
])

# -- the_golden_son_yellow --
# Victor: destroy Gold for +3p and overpower. On hit, create Gold. Simplified: +3p.
def _golden_son_play(card, event, state):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("next_attack_+3")

_register("the_golden_son", [
    TriggerDef(event_type="on_play", effect_fn=_golden_son_play),
    TriggerDef(event_type="hit", effect_fn=_factory_on_hit_create_token("gold")),
])

# -- thick_hide_hunter_yellow --
# When attacks or defends, discard random.
_register("thick_hide_hunter", [
    TriggerDef(event_type="attacking",
               effect_fn=lambda c, e, s: effect_discard(s, _controller_id(c), 1, random_discard=True)
               if _is_this_attacking(c, e, s) else None),
    TriggerDef(event_type="defend",
               effect_fn=lambda c, e, s: effect_discard(s, _controller_id(c), 1, random_discard=True)
               if _is_this_defending(c, e, s) else None),
])

# -- thump_blue --
# If power > base, gains dominate and on-hit discard.
def _thump_attacking(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    if state.combat and state.combat.attack_power > (card.power or 0):
        if "Dominate" not in state.combat.keywords:
            state.combat.grant_keyword("Dominate")

_register("thump", [
    TriggerDef(event_type="attacking", effect_fn=_thump_attacking),
    TriggerDef(event_type="hit",
               effect_fn=lambda c, e, s: effect_discard(s, 3 - _controller_id(c), 1)
               if _is_this_attacking(c, e, s) and s.combat and s.combat.attack_power > (c.power or 0) else None),
])

# -- thunk_blue --
# When you win a clash revealing this, create Might. Simplified: noop.
_register("thunk", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- tigerine_reflex_red --
# Combo: if Crouching Tiger was last, +1p and go again. AR discard: Ninja attack +2p.
_register("tigerine_reflex", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: (
                   (s.combat.__setattr__('attack_power', s.combat.attack_power + 1),
                    s.combat.grant_keyword("Go Again") if "Go Again" not in s.combat.keywords else None)
                   if combo_check(s, ["crouching_tiger"]) and s.combat else None)),
])

# -- tip_the_barkeep_blue --
# Create Goldkiss Rum. May give Gold to another hero. Go again. Simplified: noop.
_register("tip_the_barkeep", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- tooth_of_the_dragon_red --
# Next Draconic attack +3p.
_register("tooth_of_the_dragon", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_next_attack_plus(3)),
])

# -- torrent_of_tempo (red/yellow/blue) --
# When hits, go again.
_register("torrent_of_tempo", [
    TriggerDef(event_type="hit", effect_fn=_factory_on_hit_go_again()),
])

# -- tough_as_a_rok_blue --
# If less h than each other hero, base power 6, else 0. Simplified: noop (set at play).
_register("tough_as_a_rok", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- tough_smashup (red/yellow/blue) --
# On defend, clash. Winner creates Toughness. Simplified.
_register("tough_smashup", [
    TriggerDef(event_type="defend",
               effect_fn=_factory_on_defend_clash_winner_token("toughness")),
])

# -- trot_along_blue --
# Next attack with base <=3 gets go again. Go again.
_register("trot_along", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: s.players[_controller_id(c)].current_turn_effects.append(
                   "next_attack_go_again")),
])

# -- turning_point_blue --
# When defends, if less h, crowd cheers. If cheered, +4d. Simplified: +2d.
_register("turning_point", [
    TriggerDef(event_type="defend",
               effect_fn=lambda c, e, s: c.effects.append(("base_defense", lambda base: base + 2))
               if _is_this_defending(c, e, s) else None),
])

# -- under_the_trapdoor_blue --
# Stealth Instant discard: banish trap from GY, play it. Simplified: noop.
_register("under_the_trapdoor", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- unsheathed_red --
# Next sword attack +3p, if power > 2x base, go again. Go again.
_register("unsheathed", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_next_attack_plus(3)),
])

# -- v_of_the_vanguard_yellow --
# Boltyn: charge any number of times. Attacks on combat chain get +1p per card in soul.
_register("v_of_the_vanguard", [
    TriggerDef(event_type="on_play", effect_fn=_factory_on_play_charge_optional(), is_optional=True),
])

# -- valahai_riven_yellow --
# When defends, pay up to rrr. Create that many Seismic Surge.
_register("valahai_riven", [
    TriggerDef(event_type="defend",
               effect_fn=lambda c, e, s: create_token(s, _controller_id(c), "seismic_surge")
               if _is_this_defending(c, e, s) else None),
])

# -- vigorous_smashup (blue/yellow) --
# On defend, clash. Winner creates Vigor.
_register("vigorous_smashup", [
    TriggerDef(event_type="defend",
               effect_fn=_factory_on_defend_clash_winner_token("vigor")),
])

# -- visit_goldmane_estate_blue --
# Victor: create Gold. If 3+ Gold, create that many Might. Go again.
def _visit_goldmane_play(card, event, state):
    cid = _controller_id(card)
    create_token(state, cid, "gold")
    golds = sum(1 for c in state.players[cid].auras.cards if "gold" in c.slug)
    golds += sum(1 for c in state.players[cid].items.cards if "gold" in c.slug)
    if golds >= 3:
        for _ in range(golds):
            create_token(state, cid, "might")

_register("visit_goldmane_estate", [
    TriggerDef(event_type="on_play", effect_fn=_visit_goldmane_play),
])

# -- visit_the_golden_anvil_blue --
# Olympia: destroy X Gold, equip X from inventory. Simplified: noop.
_register("visit_the_golden_anvil", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- voltbound_duality (red/yellow/blue) --
# Instant discard: deal 1 arcane, create Lightning Flow.
_register("voltbound_duality", [
    TriggerDef(event_type="on_play", effect_fn=_cosmic_duality_play),
])

# -- war_machine_red --
# Evo-based: on-hit destroy arsenal, cost reduction, go again. Simplified: on-hit noop.
_register("war_machine", [
    TriggerDef(event_type="hit",
               effect_fn=lambda c, e, s: None),
])

# -- warmongers_diplomacy_blue --
# Each hero chooses war or peace. Simplified: noop.
_register("warmongers_diplomacy", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- warriors_valor_red --
# Next weapon attack +3p, on-hit go again. Go again.
def _warriors_valor_play(card, event, state):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("next_attack_+3")
    state.players[cid].current_turn_effects.append("next_attack_go_again")

_register("warriors_valor", [
    TriggerDef(event_type="on_play", effect_fn=_warriors_valor_play),
])

# -- wartune_herald (red/yellow/blue) --
# On hit, put into soul. Phantasm.
_register("wartune_herald", [
    TriggerDef(event_type="hit", effect_fn=_factory_on_hit_to_soul()),
])

# -- whelming_gustwave (red/blue) --
# Combo: if Surging Strike was last, +1p, go again, on-hit draw.
def _whelming_gustwave_play(card, event, state):
    if combo_check(state, ["surging_strike"]):
        if state.combat:
            state.combat.attack_power += 1
            if "Go Again" not in state.combat.keywords:
                state.combat.grant_keyword("Go Again")

_register("whelming_gustwave", [
    TriggerDef(event_type="on_play", effect_fn=_whelming_gustwave_play),
    TriggerDef(event_type="hit",
               effect_fn=lambda c, e, s: effect_draw(s, _controller_id(c), 1)
               if _is_this_attacking(c, e, s) and combo_check(s, ["surging_strike"]) else None),
])

# -- whittle_from_bone_blue --
# Stealth. On attack marked hero, equip Graphene Chelicera. Simplified: noop.
_register("whittle_from_bone", [
    TriggerDef(event_type="attacking", effect_fn=lambda c, e, s: None),
])

# -- widespread_annihilation_blue --
# Rune Gate: on close, each hero who lost h banishes from hand. Blood Debt.
def _widespread_annihilation_close(card, event, state):
    cid = _controller_id(card)
    create_token(state, cid, "runechant")
    for pid in state.players:
        effect_banish_from_hand(state, pid)

_register("widespread_annihilation", [
    TriggerDef(event_type="combat_chain_close", effect_fn=_widespread_annihilation_close),
])

# -- widespread_destruction_yellow --
# Rune Gate: on close, each hero who lost h banishes from arsenal. Blood Debt.
def _widespread_destruction_close(card, event, state):
    cid = _controller_id(card)
    create_token(state, cid, "runechant")

_register("widespread_destruction", [
    TriggerDef(event_type="combat_chain_close", effect_fn=_widespread_destruction_close),
])

# -- widespread_ruin_red --
# Rune Gate: on close, each hero who lost h banishes top of deck. Blood Debt.
def _widespread_ruin_close(card, event, state):
    cid = _controller_id(card)
    create_token(state, cid, "runechant")
    for pid in state.players:
        effect_banish_top_deck(state, pid, 1, face_up=True)

_register("widespread_ruin", [
    TriggerDef(event_type="combat_chain_close", effect_fn=_widespread_ruin_close),
])

# -- wild_ride_red --
# When attacks, draw then discard random. If 6+p, go again.
def _wild_ride_bonus(card, state):
    if state.combat and "Go Again" not in state.combat.keywords:
        state.combat.grant_keyword("Go Again")

_register("wild_ride", [
    TriggerDef(event_type="attacking",
               effect_fn=_factory_on_attacking_draw_discard_random_6p_bonus(_wild_ride_bonus)),
])

# -- wind_up_the_crowd_blue --
# Instant discard: create Toughness and Vigor. Simplified: on_play.
def _wind_up_crowd_play(card, event, state):
    cid = _controller_id(card)
    create_token(state, cid, "toughness")
    create_token(state, cid, "vigor")

_register("wind_up_the_crowd", [
    TriggerDef(event_type="on_play", effect_fn=_wind_up_crowd_play),
])

# -- winters_bite_blue --
# "Target hero discards a card unless they pay {r}." Go again.
def _winters_bite_play(card, event, state):
    from engine.card_effects.card_keywords import _ask_player
    target_id = 3 - _controller_id(card)
    target = state.players[target_id]
    if target.resources >= 1:
        choice = _ask_player(state, target_id, ["pay_r", "discard"],
                             context="Winter's Bite: pay {r} or discard a card")
        if choice == "pay_r":
            target.resources -= 1
            return
    effect_discard(state, target_id, 1)

_register("winters_bite", [
    TriggerDef(event_type="on_play", effect_fn=_winters_bite_play),
])

# -- wrecker_romp (red/blue) --
# Discard random as cost.
_register("wrecker_romp", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: effect_discard(s, _controller_id(c), 1, random_discard=True)),
])

# -- catch_of_the_day_blue -- (already registered, skip if exists)
# -- cloud_cover_red -- (already registered, skip if exists)
# -- current_funnel_blue -- (already registered)
# -- flittering_charge_red -- (already registered)
# -- electrostatic_discharge_red -- (already registered)

# -- test_of_iron_grip_red --
# When defends, clash. Loser discards. Simplified: clash winner token.
_register("test_of_iron_grip", [
    TriggerDef(event_type="defend",
               effect_fn=lambda c, e, s: effect_discard(s, 3 - _controller_id(c), 1)
               if _is_this_defending(c, e, s) else None),
])

# -- test_of_strength_red --
# When defends, clash. Winner creates Gold.
_register("test_of_strength", [
    TriggerDef(event_type="defend",
               effect_fn=_factory_on_defend_clash_winner_token("gold")),
])

# -- trounce_red --
# When defends, clash twice. Winner creates Might. Simplified: clash once.
_register("trounce", [
    TriggerDef(event_type="defend",
               effect_fn=_factory_on_defend_clash_winner_token("might")),
])


# ---------------------------------------------------------------
# EQUIPMENT cards (97)
# ---------------------------------------------------------------

# -- aether_crackers --
# "When an attack you control hits a hero, you may destroy this. If you do, deal 1 arcane damage to them."
# Trigger: hit (fires only for hero hits in _resolve_damage — no ally-hit path exists)
# Condition: the controller of aether_crackers is the attacker
# Optional: ask player yes/no
def _aether_crackers_hit(card, event, state):
    if not state.combat:
        return
    cid = _controller_id(card)
    # Only fires when an attack the controller controls hits
    if state.combat.attacker_id != cid:
        return
    # Card must still be in the arms zone (not already destroyed this combat)
    player = state.players[cid]
    if card not in player.arms.cards:
        return
    choice = _ask_player(state, cid, [True, False],
                         context="Destroy Aether Crackers to deal 1 arcane damage to the hero that was hit?")
    if not choice:
        return
    # Destroy: remove from arms, move to graveyard
    _move_to_graveyard(card, state)
    # Deal 1 arcane to the hit hero (always the defender in a hero-targeting attack)
    defender_id = 3 - cid
    effect_deal_arcane(state, defender_id, 1, source=card)

_register("aether_crackers", [
    TriggerDef(event_type="hit_hero", effect_fn=_aether_crackers_hit, is_optional=True),
])

# -- anothos --
# "While there are 2 or more cards with cost 3 or greater in your pitch zone, Anothos has +2{p}."
def _anothos_attacking(card, event, state):
    if not _is_this_attacking(card, event, state) or not state.combat:
        return
    cid = _controller_id(card)
    cost3_in_pitch = sum(1 for c in state.players[cid].pitch.cards if (c.cost or 0) >= 3)
    if cost3_in_pitch >= 2:
        state.combat.attack_power += 2

_register("anothos", [
    TriggerDef(event_type="attacking", effect_fn=_anothos_attacking),
])

# -- aphrodias --
# Instant r, q: deal 2 arcane. Simplified: noop.
_register("aphrodias", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- arcanite_skullcap --
# "If you have less {h} than your opponent, Arcanite Skullcap gains +1{d} and Arcane Barrier 3."
def _arcanite_skullcap_defend(card, event, state):
    if not _is_this_defending(card, event, state):
        return
    cid = _controller_id(card)
    if state.players[cid].health < state.players[3 - cid].health:
        if state.combat:
            state.combat.total_defense += 1
        # Arcane Barrier 3 flag for this turn
        state.players[cid].current_turn_effects.append("arcanite_skullcap_ab3")

_register("arcanite_skullcap", [
    TriggerDef(event_type="defend", effect_fn=_arcanite_skullcap_defend),
])

# -- attention_grabbers --
# On defend, remove suspense counter for +2d. Blade Break.
_register("attention_grabbers", [
    TriggerDef(event_type="defend",
               effect_fn=lambda c, e, s: c.effects.append(("base_defense", lambda base: base + 2))
               if _is_this_defending(c, e, s) else None),
])

# -- banksy --
# Maxx: Once per Turn. On hit, put cog on bottom of deck. Simplified: noop.
_register("banksy", [
    TriggerDef(event_type="hit", effect_fn=lambda c, e, s: None),
])

# -- basalt_boots --
# If Seismic Surge, +1d. Temper.
_register("basalt_boots", [
    TriggerDef(event_type="defend",
               effect_fn=lambda c, e, s: c.effects.append(("base_defense", lambda base: base + 1))
               if _is_this_defending(c, e, s) and any("seismic_surge" in t.slug for t in s.players[_controller_id(c)].auras.cards)
               else None),
])

# -- blackstone_greaves --
# If dealt arcane this turn, +1d. Temper.
_register("blackstone_greaves", [
    TriggerDef(event_type="defend",
               effect_fn=lambda c, e, s: c.effects.append(("base_defense", lambda base: base + 1))
               if _is_this_defending(c, e, s) and any("dealt_arcane" in eff for eff in s.players[_controller_id(c)].current_turn_effects)
               else None),
])

# -- boltn_boots --
# AR destroy: target arrow with power > base gets go again. Battleworn.
_register("boltn_boots", [
    TriggerDef(event_type="on_play", effect_fn=_factory_ar_go_again()),
])

# -- bone_puppetry --
# On defend, return ally from GY. Simplified: noop.
_register("bone_puppetry", [
    TriggerDef(event_type="defend", effect_fn=lambda c, e, s: None),
])

# -- boots_to_the_boards --
# On defend, pay up to rrr, create Toughness. Temper. Simplified: create 1 token.
_register("boots_to_the_boards", [
    TriggerDef(event_type="defend",
               effect_fn=lambda c, e, s: create_token(s, _controller_id(c), "toughness")
               if _is_this_defending(c, e, s) else None),
])

# -- braveforge_bracers --
# "Once per turn Action - {r}: Your next weapon attack this turn gains +1{p}.
#  Activate only if a weapon you control has hit this turn. Go again. Battleworn."
def _braveforge_bracers_activate(card, event, state):
    cid = _controller_id(card)
    # Check if a weapon has hit this turn
    weapon_hit = any(cl.from_weapon and cl.hit for cl in state.chain_links)
    if not weapon_hit:
        return
    state.players[cid].current_turn_effects.append("next_attack_+1")

_register("braveforge_bracers", [
    TriggerDef(event_type="on_play", effect_fn=_braveforge_bracers_activate),
])

# -- breaker_helm_protos --
# On defend, discard Hyper Driver for draw and +1d. Temper. Simplified: noop.
_register("breaker_helm_protos", [
    TriggerDef(event_type="defend", effect_fn=lambda c, e, s: None),
])

# -- breaking_scales --
# AR destroy: target combo attack +1p. Battleworn.
_register("breaking_scales", [
    TriggerDef(event_type="on_play", effect_fn=_factory_ar_power_bonus(1)),
])

# -- breakwater_undertow --
# AR destroy: Pirate ally gets go again. Blade Break.
_register("breakwater_undertow", [
    TriggerDef(event_type="on_play", effect_fn=_factory_ar_go_again()),
])

# -- breeze_rider_boots --
# When Ninja attack hits, destroy for go again on combo cards. Battleworn. Simplified: noop.
_register("breeze_rider_boots", [
    TriggerDef(event_type="hit", effect_fn=lambda c, e, s: None),
])

# -- bulls_eye_bracers --
# Destroy: put arrow from hand into arsenal with aim counter. Battleworn. Simplified: noop.
_register("bulls_eye_bracers", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- calming_gesture --
# Instant r destroy: create Spectral Shield. AB1.
_register("calming_gesture", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: create_token(s, _controller_id(c), "spectral_shield")),
])

# -- carrion_husk --
# If defend, banish when chain closes. At start of turn, if 13- h, banish. +2d. Simplified: noop.
_register("carrion_husk", [
    TriggerDef(event_type="defend", effect_fn=lambda c, e, s: None),
])

# -- cintari_saber --
# "Whenever Cintari Saber is defended by 1 or more attack action cards, it gains go again."
def _cintari_saber_defend(card, event, state):
    if not state.combat or state.combat.attack_card is not card:
        return
    # Check if any defending card is an attack action card
    for dc in state.combat.defending_cards:
        types = dc.types or []
        if "Attack" in types and "Action" in types:
            if "Go Again" not in state.combat.keywords:
                state.combat.grant_keyword("Go Again")
            return

_register("cintari_saber", [
    TriggerDef(event_type="defend", effect_fn=_cintari_saber_defend),
])

# -- cogwerx_base_arms --
# Steam counter. Instant r, remove steam: next mech attack +1p. Simplified: noop.
_register("cogwerx_base_arms", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- cogwerx_tinker_rings --
# On defend, create Golden Cog. Blade Break. Simplified: noop.
_register("cogwerx_tinker_rings", [
    TriggerDef(event_type="defend", effect_fn=lambda c, e, s: None),
])

# -- crown_of_providence --
# "When you defend with this, you may put a card from your hand or arsenal
#  on the bottom of your deck. If you do, draw a card. Blade Break."
def _crown_prov_defend(card, event, state):
    if not _is_this_defending(card, event, state):
        return
    cid = _controller_id(card)
    player = state.players[cid]
    from engine.card_effects.card_keywords import _ask_player
    # Collect candidates from hand and arsenal
    candidates = [(c, "hand") for c in player.hand.cards] + \
                 [(c, "arsenal") for c in player.arsenal.cards]
    if not candidates:
        return
    options = [f"{c.slug}_{src}" for c, src in candidates] + ["decline"]
    choice = _ask_player(state, cid, options,
                         context="Crown of Providence: put a card from hand/arsenal on bottom of deck, then draw?")
    if choice == "decline":
        return
    # Find chosen card
    for c, src in candidates:
        if f"{c.slug}_{src}" == choice:
            if src == "hand":
                player.hand.remove(c)
            else:
                player.arsenal.remove(c)
            player.deck.cards.append(c)
            c.zone = "deck"
            effect_draw(state, cid, 1)
            return

_register("crown_of_providence", [
    TriggerDef(event_type="defend", effect_fn=_crown_prov_defend),
])

# -- dawnblade --
# "If Dawnblade hits, and it's the second time or more it has hit this turn,
#  put a +1{p} counter on it. At the beginning of your end phase, if Dawnblade
#  didn't hit this turn, remove all +1{p} counters from it."
def _dawnblade_hit(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    cid = _controller_id(card)
    # Track hits this turn
    hit_key = "dawnblade_hits_this_turn"
    hits = state.players[cid].class_counters.get(hit_key, 0) + 1
    state.players[cid].class_counters[hit_key] = hits
    if hits >= 2:
        # Put a +1{p} counter
        counter_key = (card.slug, "weapon", "power_plus")
        state.players[cid].counters[counter_key] = state.players[cid].counters.get(counter_key, 0) + 1
        card.base_power = (card.base_power or 0) + 1

def _dawnblade_end_phase(card, event, state):
    """If Dawnblade didn't hit this turn, remove all +1{p} counters."""
    cid = _controller_id(card)
    hit_key = "dawnblade_hits_this_turn"
    hits = state.players[cid].class_counters.get(hit_key, 0)
    if hits == 0:
        counter_key = (card.slug, "weapon", "power_plus")
        n_counters = state.players[cid].counters.get(counter_key, 0)
        if n_counters > 0:
            card.base_power = max(0, (card.base_power or 0) - n_counters)
            state.players[cid].counters[counter_key] = 0
    # Clear hit tracking
    state.players[cid].class_counters.pop(hit_key, None)

_register("dawnblade", [
    TriggerDef(event_type="hit", effect_fn=_dawnblade_hit),
    TriggerDef(event_type="start_of_end_phase", effect_fn=_dawnblade_end_phase),
])

# -- dead_threads --
# Instant t: gain r if ally in GY this turn. Blade Break. Simplified: noop.
_register("dead_threads", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- dreadbore --
# Once per turn: put arrow from hand into empty arsenal with +1p. Simplified: noop.
_register("dreadbore", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- empyrean_rapture --
# If Herald put into soul, first hero ability costs rr less. Simplified: noop.
_register("empyrean_rapture", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- evo_beta_base (arms/chest/head/legs) --
# Transform mechanic. Battleworn. Simplified: noop.
for _slug in ["evo_beta_base_arms", "evo_beta_base_chest",
              "evo_beta_base_head", "evo_beta_base_legs"]:
    _register(_slug, [
        TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
    ])

# -- evo_recall_blue --
# Transform head. On equip, put Mech action from banish to hand. Simplified: noop.
_register("evo_recall", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- evo_steel_soul (controller/memory/processor/tower) --
# Transform mechanic. Simplified: noop.
for _slug in ["evo_steel_soul_controller", "evo_steel_soul_memory",
              "evo_steel_soul_processor", "evo_steel_soul_tower"]:
    _register(_slug, [
        TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
    ])

# -- face_purgatory --
# On defend with attack action + non-attack action, opponent discards, you draw. Blade Break.
def _face_purgatory_defend(card, event, state):
    if not _is_this_defending(card, event, state):
        return
    if state.combat and len(state.combat.defending_cards) >= 3:
        cid = _controller_id(card)
        opp_id = 3 - cid
        effect_discard(state, opp_id, 1)
        effect_draw(state, cid, 1)

_register("face_purgatory", [
    TriggerDef(event_type="defend", effect_fn=_face_purgatory_defend),
])

# -- flail_of_agony --
# Vynnset weapon. On hit, create Runechant. Simplified.
_register("flail_of_agony", [
    TriggerDef(event_type="hit",
               effect_fn=lambda c, e, s: create_token(s, _controller_id(c), "runechant")
               if _is_this_attacking(c, e, s) else None),
])

# -- fluttersteps --
# On destroy, next aura plays as instant. Ward 1. Simplified: noop.
_register("fluttersteps", [
    TriggerDef(event_type="card_destroyed", effect_fn=lambda c, e, s: None),
])

# -- galvanic_bender --
# Material: while under a permanent, +1p. Battleworn. Simplified: noop.
_register("galvanic_bender", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- gauntlets_of_iron_will --
# "When this defends, the next time an attack would gain {p} this chain link,
#  instead it gains that much minus 1. Temper."
def _gauntlets_iron_will_defend(card, event, state):
    if not _is_this_defending(card, event, state):
        return
    cid = _controller_id(card)
    opp_id = 3 - cid
    # Set flag so power gains this chain link are reduced by 1
    state.players[opp_id].current_turn_effects.append("iron_will_power_gain_minus1")

_register("gauntlets_of_iron_will", [
    TriggerDef(event_type="defend", effect_fn=_gauntlets_iron_will_defend),
])

# -- gauntlets_of_tyrannical_rex --
# Action r, t: next attack +1p if 6+p in pitch. Go again. Simplified: noop.
_register("gauntlets_of_tyrannical_rex", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- golden_gait / golden_galea / golden_gauntlets / golden_heart_plate --
# Olympia: counts as Gold. Temper. Simplified: noop.
for _slug in ["golden_gait", "golden_galea", "golden_gauntlets", "golden_heart_plate"]:
    _register(_slug, [
        TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
    ])

# -- good_time_chapeau --
# Betsy: destroy Gold for wager Might+Vigor on next attack. Simplified: noop.
_register("good_time_chapeau", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- grains_of_bloodspill --
# Weapon hit: pay r to create Vigor. Temper. Simplified: noop.
_register("grains_of_bloodspill", [
    TriggerDef(event_type="hit", effect_fn=lambda c, e, s: None),
])

# -- graven_gloves --
# "While this is in your graveyard, at the start of your turn, you may destroy 2
#  Silver you control. If you do, equip this."
# Simplified: at start of turn, if in graveyard and 2+ Silver, auto-equip.
def _graven_gloves_start_of_turn(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    # Check if this card is in graveyard
    if card not in player.graveyard.cards:
        return
    # Check for 2 Silver tokens
    silvers = [c for c in player.items.cards if "silver" in c.slug]
    if len(silvers) < 2:
        return
    from engine.card_effects.card_keywords import _ask_player
    choice = _ask_player(state, cid, [True, False],
                         context="Graven Gloves: destroy 2 Silver to equip from graveyard?")
    if not choice:
        return
    # Destroy 2 Silver
    for s in silvers[:2]:
        player.items.remove(s)
        player.graveyard.add(s)
    # Equip to arms
    player.graveyard.remove(card)
    player.arms.add(card)

_register("graven_gloves", [
    TriggerDef(event_type="start_of_turn", effect_fn=_graven_gloves_start_of_turn),
])

# -- harmonized_kodachi --
# If cost 0 in pitch, attacks get go again.
_register("harmonized_kodachi", [
    TriggerDef(event_type="attacking",
               effect_fn=lambda c, e, s: (
                   s.combat.grant_keyword("Go Again")
                   if _is_this_attacking(c, e, s) and s.combat and "Go Again" not in s.combat.keywords
                   and any(cc.cost == 0 for cc in s.players[_controller_id(c)].pitch.cards)
                   else None)),
])

# -- heartened_cross_strap --
# "Action - Destroy: The next attack action card you play this turn costs {r}{r} less. Go again."
def _heartened_cross_strap_activate(card, event, state):
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("heartened_cross_strap_cost_reduction_2")
    effect_gain_action_point(state, cid)

_register("heartened_cross_strap", [
    TriggerDef(event_type="on_play", effect_fn=_heartened_cross_strap_activate),
])

# -- helm_of_halos_grace --
# On defend, charge. If yellow charged, draw. Blade Break.
_register("helm_of_halos_grace", [
    TriggerDef(event_type="defend", effect_fn=lambda c, e, s: None),
])

# -- hexagore_the_death_hydra --
# Deals damage to you equal to 6 minus blood debt in banish. Simplified: noop.
_register("hexagore_the_death_hydra", [
    TriggerDef(event_type="attacking", effect_fn=lambda c, e, s: None),
])

# -- ironfist_revelation --
# "When this defends, you may turn a face-down card with crush in your arsenal face-up.
#  If you do, put a +1{p} counter on it. Temper."
def _ironfist_defend(card, event, state):
    if not _is_this_defending(card, event, state):
        return
    cid = _controller_id(card)
    player = state.players[cid]
    # Check for face-down cards in arsenal with Crush keyword
    face_down_crush = [c for c in player.arsenal.cards
                       if getattr(c, 'face_down', False)
                       and any("Crush" in kw for kw in (c.keywords or []))]
    if not face_down_crush:
        return
    target = face_down_crush[0]
    target.face_down = False
    # Add +1{p} counter
    target.base_power = (target.base_power or 0) + 1

_register("ironfist_revelation", [
    TriggerDef(event_type="defend", effect_fn=_ironfist_defend),
])

# -- ironsong_versus --
# Once per turn: next sword gets on-hit create Courage. Go again. Temper.
_register("ironsong_versus", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: s.players[_controller_id(c)].current_turn_effects.append(
                   "next_hit_courage")),
])

# -- kunai_of_retribution --
# Once per turn: attack, destroy on chain close. Go again.
_register("kunai_of_retribution", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- luminaris_angels_glow --
# If yellow in pitch, first Herald attack and first angel attack don't require soul. Simplified: noop.
_register("luminaris_angels_glow", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- mask_of_momentum --
# "Once per Turn Effect – When an attack action card you control is the third or
#  higher chain link in a row to hit, draw a card."
#
# Implementation strategy:
#   • On ANY 'hit' event (covers both main-attack hits AND Flick Knives dagger
#     hits that occur before the main attack resolves): mark
#     player.class_counters["current_link_hit"] = True for the current chain
#     link position (len(state.chain_links) before this link is appended).
#   • On 'chain_link_resolves' (fires after the link is appended):
#     - link_hit = chain_links[-1].hit  OR  current_link_hit counter was set
#     - Update consecutive "hit_streak" counter
#     - If streak >= 3 and mask not yet exhausted this turn: draw, exhaust mask
#   • card.exhausted on mask_of_momentum is reset each turn by the engine's
#     start-of-turn equipment-exhausted reset (added alongside this fix).

def _mom_hit(card, event, state):
    """Any hit during this chain link: mark current_link_hit."""
    cid = _controller_id(card)
    state.players[cid].class_counters["current_link_hit"] = True

def _mom_chain_close(card, event, state):
    """Chain link resolved: update consecutive hit streak; draw if 3rd+ consecutive."""
    cid = _controller_id(card)
    player = state.players[cid]
    links = state.chain_links
    if not links:
        return
    last_link = links[-1]
    # A chain link "hit" if the main attack dealt damage OR any side-hit was recorded
    link_hit = last_link.hit or bool(player.class_counters.get("current_link_hit", False))
    # Clear per-link flag now that the link has resolved
    player.class_counters.pop("current_link_hit", None)

    if link_hit:
        player.class_counters["hit_streak"] = player.class_counters.get("hit_streak", 0) + 1
    else:
        player.class_counters["hit_streak"] = 0

    # Check once-per-turn draw condition
    mask = next((c for c in player.head.cards if c.slug == "mask_of_momentum"), None)
    if mask is None or mask.exhausted:
        return
    if player.class_counters.get("hit_streak", 0) >= 3:
        effect_draw(state, cid, 1)
        mask.exhausted = True  # once per turn

CARD_TRIGGERS["mask_of_momentum"] = [
    TriggerDef(event_type="hit",              effect_fn=_mom_hit),
    TriggerDef(event_type="chain_link_resolves", effect_fn=_mom_chain_close),
]

# -- mask_of_perdition --
# From GY: destroy 2 Silver to equip. On defend, mark attacker. Simplified: noop.
_register("mask_of_perdition", [
    TriggerDef(event_type="defend",
               effect_fn=lambda c, e, s: effect_mark(s, 3 - _controller_id(c))
               if _is_this_defending(c, e, s) and s.combat else None),
])

# -- mask_of_the_pouncing_lynx --
# On attack hit, destroy for search. Blade Break. Simplified: noop.
_register("mask_of_the_pouncing_lynx", [
    TriggerDef(event_type="hit", effect_fn=lambda c, e, s: None),
])

# -- millers_grindstone --
# "When this hits a hero, clash with them. If you win, destroy the top card of their deck.
#  If they win, put a -1{p} counter on Miller's Grindstone."
def _millers_grindstone_hit(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    cid = _controller_id(card)
    opp_id = 3 - cid
    # Clash: compare top card power
    my_cards = effect_look_top(state, cid, 1)
    opp_cards = effect_look_top(state, opp_id, 1)
    my_power = (my_cards[0].base_power or 0) if my_cards else 0
    opp_power = (opp_cards[0].base_power or 0) if opp_cards else 0
    if my_power > opp_power:
        # Win: destroy top of opponent's deck
        if state.players[opp_id].deck.cards:
            destroyed = state.players[opp_id].deck.cards.pop(0)
            state.players[opp_id].graveyard.add(destroyed)
    elif opp_power > my_power:
        # Lose: put -1{p} counter on this weapon
        key = (card.slug, "weapon", "power_minus")
        state.players[cid].counters[key] = state.players[cid].counters.get(key, 0) + 1

_register("millers_grindstone", [
    TriggerDef(event_type="hit", effect_fn=_millers_grindstone_hit),
])

# -- new_horizon --
# If face up in arsenal, additional arsenal zone. Blade Break. Simplified: noop.
_register("new_horizon", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- obsidian_fire_vein --
# "If you've played a Draconic card this chain link, this attack gets +1{p} and go again."
def _obsidian_fire_vein_attacking(card, event, state):
    if not _is_this_attacking(card, event, state) or not state.combat:
        return
    # Check if a Draconic card has been played this chain link
    cid = _controller_id(card)
    played_draconic = any("draconic" in eff.lower() for eff in state.players[cid].current_turn_effects
                          if "draconic_played_this_chain" in eff)
    # Simpler check: any Draconic chain link already exists
    if not played_draconic:
        played_draconic = any("Draconic" in (getattr(cl, 'keywords', []) or []) for cl in state.chain_links)
    if played_draconic:
        state.combat.attack_power += 1
        if "Go Again" not in state.combat.keywords:
            state.combat.grant_keyword("Go Again")

_register("obsidian_fire_vein", [
    TriggerDef(event_type="attacking", effect_fn=_obsidian_fire_vein_attacking),
])

# -- parry_blade --
# +2d while defending weapon attack. Blade Break.
_register("parry_blade", [
    TriggerDef(event_type="defend",
               effect_fn=lambda c, e, s: c.effects.append(("base_defense", lambda base: base + 2))
               if _is_this_defending(c, e, s) and s.combat and getattr(s.combat, 'from_weapon', False)
               else None),
])

# -- phantasmal_footsteps --
# Illusionist attack destroyed: pay r for 1 AP. On defend, if attack destroyed, +2d. Simplified: noop.
_register("phantasmal_footsteps", [
    TriggerDef(event_type="defend", effect_fn=lambda c, e, s: None),
])

# -- pillar_of_unity --
# Unity: defend with card from hand, +1d. Temper.
_register("pillar_of_unity", [
    TriggerDef(event_type="defend",
               effect_fn=lambda c, e, s: c.effects.append(("base_defense", lambda base: base + 1))
               if _is_this_defending(c, e, s) and s.combat and len(s.combat.defending_cards) >= 2
               else None),
])

# -- pouncing_paws --
# Instant destroy: create Crouching Tiger in banish, play this turn. Battleworn. Simplified: noop.
_register("pouncing_paws", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- quickdodge_flexors --
# DR r: add as defending card with 2d. At end phase, put into hand. Simplified: noop.
_register("quickdodge_flexors", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- ravenous_meataxe --
# On attack, draw then discard random. If 6+p discarded, +2p.
def _ravenous_meataxe_bonus(card, state):
    if state.combat:
        state.combat.attack_power += 2

_register("ravenous_meataxe", [
    TriggerDef(event_type="attacking",
               effect_fn=_factory_on_attacking_draw_discard_random_6p_bonus(_ravenous_meataxe_bonus)),
])

# -- raydn_duskbane --
# If charged this turn, +3p.
_register("raydn_duskbane", [
    TriggerDef(event_type="attacking",
               effect_fn=lambda c, e, s: (
                   setattr(s.combat, 'attack_power', s.combat.attack_power + 3)
                   if _is_this_attacking(c, e, s) and s.combat
                   and any("charged" in eff for eff in s.players[_controller_id(c)].current_turn_effects)
                   else None)),
])

# -- refraction_bolters -- (already handled by engine)
_register("refraction_bolters", [
    TriggerDef(event_type="hit", effect_fn=lambda c, e, s: None),
])

# -- rok --
# Activate only if no cards in hand. Damage can't be prevented.
_register("rok", [
    TriggerDef(event_type="attacking", effect_fn=lambda c, e, s: None),
])

# -- savage_claw --
# If 6+p pitched, attack +1p. Simplified: noop.
_register("savage_claw", [
    TriggerDef(event_type="attacking", effect_fn=lambda c, e, s: None),
])

# -- savage_sash --
# Destroy: 6+p attacks cost r less. Go again. Temper. Simplified: gain 1r.
_register("savage_sash", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: effect_gain_resources(s, _controller_id(c), 1)),
])

# -- scale_peeler --
# On hit, next time they defend with equipment, it gets -2d. Piercing 1. Simplified: noop.
_register("scale_peeler", [
    TriggerDef(event_type="hit", effect_fn=lambda c, e, s: None),
])

# -- searing_emberblade --
# If 2+ Draconic chain links, attacks get go again.
_register("searing_emberblade", [
    TriggerDef(event_type="attacking",
               effect_fn=_factory_attacking_go_again_if(
                   lambda c, s: _has_draconic_chain_links(s, 2))),
])

# -- sharp_shooters --
# Destroy: put arrow from hand into arsenal with aim counter. Go again. Battleworn. Simplified: noop.
_register("sharp_shooters", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- snapdragon_scalers --
# AR destroy: target cost <=1 gets go again. Simplified: AR go again.
_register("snapdragon_scalers", [
    TriggerDef(event_type="on_play", effect_fn=_factory_ar_go_again()),
])

# -- solforge_gauntlet --
# On defend chain close, put into soul. AB1.
_register("solforge_gauntlet", [
    TriggerDef(event_type="combat_chain_close",
               effect_fn=lambda c, e, s: effect_move_to_soul(s, c, _controller_id(c))
               if _is_this_defending(c, e, s) else None),
])

# -- spellbound_creepers --
# Once per turn instant r, bind counter: play next non-attack action as instant. Simplified: noop.
_register("spellbound_creepers", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- spiders_bite --
# "Piercing 1. When this hits a hero, the next time they defend with 1 or more
#  attack action cards this turn, those cards have -1{d} while defending."
def _spiders_bite_hit(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    target_id = 3 - _controller_id(card)
    state.players[target_id].current_turn_effects.append("spiders_bite_aa_minus1d")

_register("spiders_bite", [
    TriggerDef(event_type="hit", effect_fn=_spiders_bite_hit),
])

# -- spitfire --
# Action t, t cog: attack. On attack, t cog for +1p. Simplified: noop.
_register("spitfire", [
    TriggerDef(event_type="attacking", effect_fn=lambda c, e, s: None),
])

# -- symbiosis_shot --
# Dash: Mech item enters arena, put steam counter. On attack, remove steam for +1p. Simplified: noop.
_register("symbiosis_shot", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- synapse_sparkcap --
# Action t, banish Evo from hand: create Ponder. Battleworn. Simplified: noop.
_register("synapse_sparkcap", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- talishar_the_lost_prince --
# "Once per Turn Action - {r}{r}, put a rust counter: Attack.
#  At the beginning of your end phase, if this has 2 or more rust counters, destroy it."
def _talishar_attacking(card, event, state):
    if not _is_this_attacking(card, event, state):
        return
    cid = _controller_id(card)
    key = (card.slug, "weapon", "rust")
    state.players[cid].counters[key] = state.players[cid].counters.get(key, 0) + 1

def _talishar_end_phase(card, event, state):
    """At end phase, if 2+ rust counters, destroy Talishar."""
    cid = _controller_id(card)
    key = (card.slug, "weapon", "rust")
    rust = state.players[cid].counters.get(key, 0)
    if rust >= 2:
        player = state.players[cid]
        for wz in [player.weapon1, player.weapon2]:
            if card in wz.cards:
                wz.remove(card)
                player.graveyard.add(card)
                break

_register("talishar_the_lost_prince", [
    TriggerDef(event_type="attacking", effect_fn=_talishar_attacking),
    TriggerDef(event_type="start_of_end_phase", effect_fn=_talishar_end_phase),
])

# -- tectonic_plating --
# Once per turn r: create Seismic Surge. Go again. Battleworn.
_register("tectonic_plating", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: create_token(s, _controller_id(c), "seismic_surge")),
])

# -- teklo_foundry_heart --
# Once per turn r: banish top 2 deck, gain r per Mech. Activate only with boost. Simplified: noop.
_register("teklo_foundry_heart", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- teklo_leveler --
# Evo-based: scaling weapon. Simplified: noop.
_register("teklo_leveler", [
    TriggerDef(event_type="attacking", effect_fn=lambda c, e, s: None),
])

# -- tiger_stripe_shuko --
# Second attack with base <=2 each turn gets +1p and unpreventable. Blade Break. Simplified: noop.
_register("tiger_stripe_shuko", [
    TriggerDef(event_type="attacking", effect_fn=lambda c, e, s: None),
])

# -- titans_fist --
# If cost 3+ in pitch, +1p.
_register("titans_fist", [
    TriggerDef(event_type="attacking",
               effect_fn=lambda c, e, s: (
                   setattr(s.combat, 'attack_power', s.combat.attack_power + 1)
                   if _is_this_attacking(c, e, s) and s.combat
                   and any(cc.cost is not None and cc.cost >= 3 for cc in s.players[_controller_id(c)].pitch.cards)
                   else None)),
])

# -- unicycle --
# Instant destroy: untap a cog. Battleworn. Simplified: noop.
_register("unicycle", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- valiant_dynamo --
# At end phase, if attacked 2+ with weapons, remove -1d counter. Temper. Simplified: noop.
_register("valiant_dynamo", [
    TriggerDef(event_type="start_of_end_phase", effect_fn=lambda c, e, s: None),
])

# -- vexing_quillhand --
# Destroy: create 2 Runechants. Go again. AB1.
_register("vexing_quillhand", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: (
                   create_token(s, _controller_id(c), "runechant"),
                   create_token(s, _controller_id(c), "runechant"),
               )),
])

# -- warpath_of_winged_grace --
# On defend, charge. If yellow, create Quicken. Blade Break.
_register("warpath_of_winged_grace", [
    TriggerDef(event_type="defend",
               effect_fn=lambda c, e, s: create_token(s, _controller_id(c), "quicken")
               if _is_this_defending(c, e, s) else None),
])

# -- wind_cutter --
# AR r, t: search for Shuriken item. Only if hit 2+ times. Simplified: noop.
_register("wind_cutter", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- zenith_blade --
# Hala. If sharpened, first attack gets go again.
_register("zenith_blade", [
    TriggerDef(event_type="attacking",
               effect_fn=lambda c, e, s: (
                   s.combat.grant_keyword("Go Again")
                   if _is_this_attacking(c, e, s) and s.combat and "Go Again" not in s.combat.keywords
                   else None)),
])


# ---------------------------------------------------------------
# AURA / ALLY / ITEM cards (50)
# ---------------------------------------------------------------

# -- arc_light_sentinel_yellow --
# Prism: opponents must select this as target. Spectra.
_register("arc_light_sentinel", [
    TriggerDef(event_type="enters_arena", effect_fn=lambda c, e, s: None),
])

# -- backup_protocol_red_red --
# Crank: steam counter, destroy without. Simplified: noop.
_register("backup_protocol_red", [
    TriggerDef(event_type="start_of_turn", effect_fn=lambda c, e, s: None),
])

# -- blessing_of_bellona_yellow --
# Go again. Whenever card put into soul, create Courage. At start of turn, put into soul.
_register("blessing_of_bellona", [
    TriggerDef(event_type="start_of_turn",
               effect_fn=lambda c, e, s: effect_move_to_soul(s, c, _controller_id(c))
               if _controller_id(c) == s.active_player else None),
])

# -- boom_grenade (red/yellow) --
# Crank: steam counter. On Mech attack, deal arcane damage. Simplified: noop.
_register("boom_grenade", [
    TriggerDef(event_type="start_of_turn", effect_fn=lambda c, e, s: None),
])

# -- cerebellum_processor_blue --
# Crank: 2 steam counters. Once per turn: look at top deck. Simplified: noop.
_register("cerebellum_processor", [
    TriggerDef(event_type="start_of_turn", effect_fn=lambda c, e, s: None),
])

# -- channel_lake_frigid_blue --
# Cards cost opponents additional r. Channel Ice upkeep. Simplified: noop.
_register("channel_lake_frigid", [
    TriggerDef(event_type="start_of_turn", effect_fn=lambda c, e, s: None),
])

# -- chum_friendly_first_mate_yellow --
# Ally: attack, instant discard watery grave to force target. Simplified: noop.
_register("chum_friendly_first_mate", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- concealed_object_blue --
# On enter, crowd boos. Instant t: attack +1p. End phase destroy.
_register("concealed_object", [
    TriggerDef(event_type="enters_arena",
               effect_fn=lambda c, e, s: effect_crowd_boos(s, _controller_id(c))),
])

# -- copper_cog_blue --
# Unlimited. Crank: 2 steam counters. Simplified: noop.
_register("copper_cog", [
    TriggerDef(event_type="start_of_turn", effect_fn=lambda c, e, s: None),
])

# -- crumble_to_eternity_blue --
# Jarl: on enter, -1d counter on equipment. Destroy at action phase. Simplified: noop.
_register("crumble_to_eternity", [
    TriggerDef(event_type="enters_arena", effect_fn=lambda c, e, s: None),
])

# -- act_of_glory (red: +6p, yellow: +5p, blue: +4p) --
# Aura with Suspense (keyword triggers auto-registered via triggers.py keyword parser).
# Card-specific: when it leaves the arena, the next attack this turn gets +Np.
for _slug, _n in [("act_of_glory_red", 6), ("act_of_glory_yellow", 5), ("act_of_glory_blue", 4)]:
    _register(_slug, [
        TriggerDef(event_type="leaves_arena",
                   effect_fn=lambda c, e, s, n=_n: s.players[_controller_id(c)].current_turn_effects.append(
                       f"next_attack_+{n}")),
    ])

# -- edge_of_their_seats (red: +5p, yellow: +4p) --
# Suspense. When leaves arena, next attack +Np.
for _slug, _n in [("edge_of_their_seats_red", 5), ("edge_of_their_seats_yellow", 4)]:
    _register(_slug, [
        TriggerDef(event_type="leaves_arena",
                   effect_fn=lambda c, e, s, n=_n: s.players[_controller_id(c)].current_turn_effects.append(
                       f"next_attack_+{n}")),
    ])

# -- genesis_yellow --
# At start of turn, put card from hand into soul. If Illusionist, Spectral Shield.
_register("genesis", [
    TriggerDef(event_type="start_of_turn",
               effect_fn=lambda c, e, s: create_token(s, _controller_id(c), "spectral_shield")
               if _controller_id(c) == s.active_player else None),
])

# -- absorbtion_zone_yellow --
# Cost: 0. Item. Instant.
# Enters with 3 steam counters. Whenever controller boosts, remove a steam counter.
# When no steam counters remain, destroy this.
# Note: no start-of-turn counter loss (unlike most steam items).
def _absorbtion_zone_enters(card, event, state):
    cid = _controller_id(card)
    key = (card.slug, card.zone, "steam")
    state.players[cid].counters[key] = 3

def _absorbtion_zone_on_boost(card, event, state):
    cid = _controller_id(card)
    # Only react when this item's controller is the one who boosted
    if event.data.get("player_id") != cid:
        return
    player = state.players[cid]
    key = (card.slug, card.zone, "steam")
    current = player.counters.get(key, 0)
    if current <= 0:
        return
    player.counters[key] = current - 1
    if player.counters[key] == 0:
        effect_destroy(state, cid, card)

_register("absorbtion_zone_yellow", [
    TriggerDef(event_type="enters_arena", effect_fn=_absorbtion_zone_enters),
    TriggerDef(event_type="boosted", effect_fn=_absorbtion_zone_on_boost),
])

# -- hyper_driver (red: 3 steam, yellow: 2 steam) --
# Steam counters, destroy when empty. On boost, remove steam + boost card +1p. Simplified: noop.
_register("hyper_driver", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- in_the_palm_of_your_hand_red --
# Suspense. On enter/leave, draw.
_register("in_the_palm_of_your_hand", [
    TriggerDef(event_type="enters_arena",
               effect_fn=lambda c, e, s: effect_draw(s, _controller_id(c), 1)),
    TriggerDef(event_type="leaves_arena",
               effect_fn=lambda c, e, s: effect_draw(s, _controller_id(c), 1)),
])

# -- leave_them_hanging_red --
# Suspense. On enter/leave, intimidate. On leave, next attack +4p.
_register("leave_them_hanging", [
    TriggerDef(event_type="enters_arena",
               effect_fn=lambda c, e, s: effect_intimidate(s, 3 - _controller_id(c))),
    TriggerDef(event_type="leaves_arena",
               effect_fn=lambda c, e, s: (
                   effect_intimidate(s, 3 - _controller_id(c)),
                   s.players[_controller_id(c)].current_turn_effects.append("next_attack_+4"),
               )),
])

# -- ley_line_of_the_old_ones_blue --
# On enter and on damage, create Seismic Surge. At end phase, if 3+ surge, don't destroy.
_register("ley_line_of_the_old_ones", [
    TriggerDef(event_type="enters_arena",
               effect_fn=lambda c, e, s: create_token(s, _controller_id(c), "seismic_surge")),
])

# -- loan_shark_yellow --
# On enter, create 2 Gold. At end phase, if haven't created/stolen Gold, lose 2h.
def _loan_shark_enter(card, event, state):
    cid = _controller_id(card)
    create_token(state, cid, "gold")
    create_token(state, cid, "gold")

_register("loan_shark", [
    TriggerDef(event_type="enters_arena", effect_fn=_loan_shark_enter),
])

# -- malefic_incantation (red: 3 verse, yellow: 2 verse) --
# Verse counters. On attack action play, remove verse and create Runechant.
_register("malefic_incantation", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: create_token(s, _controller_id(c), "runechant")),
])

# -- merciful_retribution_yellow --
# When aura/attack destroyed, deal 1 arcane. If non-token Light, put into soul.
_register("merciful_retribution", [
    TriggerDef(event_type="card_destroyed",
               effect_fn=lambda c, e, s: effect_deal_arcane(s, 3 - _controller_id(c), 1, source=c)),
])

# -- null_time_zone_blue --
# Crank: 2 steam. On enter, negate instant. Simplified: noop.
_register("null_time_zone", [
    TriggerDef(event_type="enters_arena", effect_fn=lambda c, e, s: None),
])

# -- oysten_heart_of_gold_yellow --
# Ally attack. On death, create Gold. Watery Grave.
_register("oysten_heart_of_gold", [
    TriggerDef(event_type="card_destroyed",
               effect_fn=lambda c, e, s: create_token(s, _controller_id(c), "gold")),
])

# -- passing_mirage_blue --
# First Illusionist attack loses phantasm. Spectra.
_register("passing_mirage", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- pierce_reality_blue --
# First Illusionist attack each turn +2p. Spectra.
_register("pierce_reality", [
    TriggerDef(event_type="attacking",
               effect_fn=lambda c, e, s: None),  # Continuous effect, simplified
])

# -- promising_terrain_blue --
# If create Seismic Surge, create +1. Destroy at action phase.
_register("promising_terrain", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- riggermortis_yellow --
# Ally attack r, t. Watery Grave.
_register("riggermortis", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- runeblood_incantation_red --
# 3 verse counters. At action phase, remove verse; if opponent lost h, create Runechant.
_register("runeblood_incantation", [
    TriggerDef(event_type="start_of_turn",
               effect_fn=lambda c, e, s: create_token(s, _controller_id(c), "runechant")
               if _controller_id(c) == s.active_player else None),
])

# -- sawbones_dock_hand_yellow --
# Ally attack r, t. Instant t: prevent 1 damage. Simplified: noop.
_register("sawbones_dock_hand", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- scooba_salty_sea_dog_yellow --
# Ally attack rrr, t. On attack, put yellow from GY to bottom of deck for Gold. Simplified: noop.
_register("scooba_salty_sea_dog", [
    TriggerDef(event_type="attacking", effect_fn=lambda c, e, s: None),
])

# -- seeker_kunai_red --
# AR destroy: Assassin attack +1p. From GY: start of turn destroy 2 Silver to equip.
_register("seeker_kunai", [
    TriggerDef(event_type="on_play", effect_fn=_factory_ar_power_bonus(1)),
])

# -- sharpened_senses_yellow --
# Weapon attacks +1p. If > 2x base, go again. End phase destroy.
# This is an AURA, not an attack card. The trigger fires whenever any attack is made
# while this aura is in play. Do NOT check _is_this_attacking.
def _sharpened_senses_attacking(card, event, state):
    if not state.combat:
        return
    cid = _controller_id(card)
    # Only apply if this aura's controller is the attacker
    if state.combat.attacker_id != cid:
        return
    state.combat.attack_power += 1
    # If power > 2x base, go again
    base = state.combat.attack_card.power if state.combat.attack_card else 0
    if state.combat.attack_power > 2 * (base or 0):
        if "Go Again" not in state.combat.keywords:
            state.combat.grant_keyword("Go Again")

_register("sharpened_senses", [
    TriggerDef(event_type="attacking", effect_fn=_sharpened_senses_attacking),
])

# -- show_time_blue --
# Bravo: on enter, search for Guardian attack, put to hand, shuffle.
_register("show_time", [
    TriggerDef(event_type="enters_arena",
               effect_fn=lambda c, e, s: effect_draw(s, _controller_id(c), 1)),
])

# -- silverwind_shuriken_blue --
# AR destroy: combo attack +1p.
_register("silverwind_shuriken", [
    TriggerDef(event_type="on_play", effect_fn=_factory_ar_power_bonus(1)),
])

# -- spirit_of_eirina_yellow --
# If put into soul, instead put into arena. Play Lumina Ascension as instant. Simplified: noop.
_register("spirit_of_eirina", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- stardust_spike --
# On leave, gain resource and amp 1. Ward 2.
_register("stardust_spike", [
    TriggerDef(event_type="leaves_arena",
               effect_fn=lambda c, e, s: (
                   effect_gain_resources(s, _controller_id(c), 1),
                   effect_amp(s, _controller_id(c), 1),
               )),
])

# -- swabbie_yellow --
# Ally attack rr, t. Watery Grave.
_register("swabbie", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- teklo_core_blue --
# Dash: 2 steam counters. At start of turn, if boost, gain r. Simplified: noop.
_register("teklo_core", [
    TriggerDef(event_type="start_of_turn", effect_fn=lambda c, e, s: None),
])

# -- teklo_pounder_blue --
# 3 steam counters. Once per turn: on Mech attack, remove steam + deal 1 damage. Simplified: noop.
_register("teklo_pounder", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- to_be_continued_blue --
# Suspense. First damage each turn, prevent 1.
_register("to_be_continued", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- two_steps_ahead_blue --
# At start of turn, destroy this, create Confidence and 3 Might.
_register("two_steps_ahead", [
    TriggerDef(event_type="start_of_turn",
               effect_fn=lambda c, e, s: (
                   _move_to_graveyard(c, s),
                   create_token(s, _controller_id(c), "might"),
                   create_token(s, _controller_id(c), "might"),
                   create_token(s, _controller_id(c), "might"),
               ) if _controller_id(c) == s.active_player else None),
])

# -- up_on_a_pedestal_blue --
# Suspense. On enter/leave, put Guardian attack from GY on top of deck.
_register("up_on_a_pedestal", [
    TriggerDef(event_type="enters_arena", effect_fn=lambda c, e, s: None),
    TriggerDef(event_type="leaves_arena", effect_fn=lambda c, e, s: None),
])


# ---------------------------------------------------------------
# ATTACK REACTION cards (39)
# ---------------------------------------------------------------

# -- affirm_loyalty_red --
# Target dagger +2p. If 2+ Draconic chain links, create Fealty.
def _affirm_loyalty_effect(card, event, state):
    if state.combat:
        state.combat.attack_power += 2
    if _has_draconic_chain_links(state, 2):
        create_token(state, _controller_id(card), "fealty")

_register("affirm_loyalty", [
    TriggerDef(event_type="on_play", effect_fn=_affirm_loyalty_effect),
])

# -- ancestral_empowerment_red --
# Target Ninja attack +1p. Draw a card.
def _ancestral_empowerment_effect(card, event, state):
    if state.combat:
        state.combat.attack_power += 1
    effect_draw(state, _controller_id(card), 1)

_register("ancestral_empowerment", [
    TriggerDef(event_type="on_play", effect_fn=_ancestral_empowerment_effect),
])

# -- beacon_of_victory_yellow --
# Banish X from soul. Attack +Xp. If charged, go again. Simplified: +2p.
_register("beacon_of_victory", [
    TriggerDef(event_type="on_play", effect_fn=_factory_ar_power_bonus(2)),
])

# -- beat_of_the_ironsong_blue --
# Choose X+1 (Dawnblade counters): each mode is +1p or go again or draw.
_register("beat_of_the_ironsong", [
    TriggerDef(event_type="on_play", effect_fn=_factory_ar_power_bonus(1)),
])

# -- blade_flurry_red --
# Target weapon +2p. Next weapon attack +2p.
def _blade_flurry_effect(card, event, state):
    if state.combat:
        state.combat.attack_power += 2
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("next_attack_+2")

_register("blade_flurry", [
    TriggerDef(event_type="on_play", effect_fn=_blade_flurry_effect),
])

# -- blade_runner (red: +3p, blue: +1p) --
# Target 1H weapon gets go again. Next weapon +Np.
_register("blade_runner_red", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: (
                   (s.combat.grant_keyword("Go Again") if s.combat and "Go Again" not in s.combat.keywords else None),
                   s.players[_controller_id(c)].current_turn_effects.append("next_attack_+3"),
               )),
])
_register("blade_runner_blue", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: (
                   (s.combat.grant_keyword("Go Again") if s.combat and "Go Again" not in s.combat.keywords else None),
                   s.players[_controller_id(c)].current_turn_effects.append("next_attack_+1"),
               )),
])

# -- blistering_blade_red --
# Target dagger +2p. If 2+ Draconic chain links, +3p instead.
def _blistering_blade_effect(card, event, state):
    if state.combat:
        bonus = 3 if _has_draconic_chain_links(state, 2) else 2
        state.combat.attack_power += bonus

_register("blistering_blade", [
    TriggerDef(event_type="on_play", effect_fn=_blistering_blade_effect),
])

# -- blood_follows_blade_yellow --
# Kassai: target sword gets go again and on-hit create Cintari Sellsword. Simplified: go again.
_register("blood_follows_blade", [
    TriggerDef(event_type="on_play", effect_fn=_factory_ar_go_again()),
])

# -- coercive_tendency_blue --
# Arakni: look at top 3 of defender's deck, reorder, banish top. Target attack +1p.
def _coercive_tendency_effect(card, event, state):
    if state.combat:
        state.combat.attack_power += 1
    target_id = 3 - _controller_id(card)
    effect_banish_top_deck(state, target_id, 1, face_up=True)

_register("coercive_tendency", [
    TriggerDef(event_type="on_play", effect_fn=_coercive_tendency_effect),
])

# -- cut_to_the_chase_red --
# Target Assassin with contract +3p. Look at top of defender's deck.
_register("cut_to_the_chase", [
    TriggerDef(event_type="on_play", effect_fn=_factory_ar_power_bonus(3)),
])

# -- fire_and_brimstone_red --
# Legendary. Costs r less per Draconic chain link. Daggers +1p. Simplified: +2p.
_register("fire_and_brimstone", [
    TriggerDef(event_type="on_play", effect_fn=_factory_ar_power_bonus(2)),
])

# -- glint_the_quicksilver_blue --
# Target weapon gets go again. Reprise: draw.
def _glint_quicksilver_effect(card, event, state):
    if state.combat and "Go Again" not in state.combat.keywords:
        state.combat.grant_keyword("Go Again")
    if reprise_check(state):
        effect_draw(state, _controller_id(card), 1)

_register("glint_the_quicksilver", [
    TriggerDef(event_type="on_play", effect_fn=_glint_quicksilver_effect),
])

# -- hunts_end_red --
# Play only if 3+ Fealty tokens. Target dagger +4p.
_register("hunts_end", [
    TriggerDef(event_type="on_play", effect_fn=_factory_ar_power_bonus(4)),
])

# -- in_the_swing_red --
# Play only if attacked 2+ with weapons. Target weapon +3p.
_register("in_the_swing", [
    TriggerDef(event_type="on_play", effect_fn=_factory_ar_power_bonus(3)),
])

# -- ironsong_response_red -- (already registered if exists, but here for completeness)
_register("ironsong_response", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: (
                   setattr(s.combat, 'attack_power', s.combat.attack_power + 3)
                   if s.combat and reprise_check(s) else None)),
])

# -- jagged_edge_red --
# Target weapon +3p, damage can't be prevented.
_register("jagged_edge", [
    TriggerDef(event_type="on_play", effect_fn=_factory_ar_power_bonus(3)),
])

# -- legacy_of_ikaru_blue --
# Target Ninja +1p, on-hit if Edge of Autumn was last, draw.
_register("legacy_of_ikaru", [
    TriggerDef(event_type="on_play", effect_fn=_factory_ar_power_bonus(1)),
])

# -- long_whisker_loyalty_red --
# Per Draconic chain link: dagger +2p or additional attack. Simplified: +2p.
_register("long_whisker_loyalty", [
    TriggerDef(event_type="on_play", effect_fn=_factory_ar_power_bonus(2)),
])

# -- nip_at_the_heels_blue -- (may already exist)
_register("nip_at_the_heels", [
    TriggerDef(event_type="on_play", effect_fn=_factory_ar_power_bonus(1)),
])

# -- overpower (red/yellow/blue) -- Reprise variants
for _slug, _base, _reprise in [("overpower_red", 4, 6), ("overpower_yellow", 3, 5), ("overpower_blue", 2, 4)]:
    def _make_overpower_fn(base, reprise):
        def fn(card, event, state):
            if state.combat:
                bonus = reprise if reprise_check(state) else base
                state.combat.attack_power += bonus
        return fn
    _register(_slug, [
        TriggerDef(event_type="on_play", effect_fn=_make_overpower_fn(_base, _reprise)),
    ])

# -- provoke_blue --
# If weapon attack, defender reveals card from hand. If action, add as defender.
_register("provoke", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- puncture_red --
# Target sword/dagger +3p and piercing 1.
_register("puncture", [
    TriggerDef(event_type="on_play", effect_fn=_factory_ar_power_bonus(3)),
])

# -- razor_reflex_red --
# Choose: dagger/sword +3p, or cost<=1 attack +3p with on-hit go again.
_register("razor_reflex", [
    TriggerDef(event_type="on_play", effect_fn=_factory_ar_power_bonus(3)),
])

# -- razors_edge (red: +3p, yellow: +2p, blue: +1p) --
# Target stealth attack +Np.
for _slug, _n in [("razors_edge_red", 3), ("razors_edge_yellow", 2), ("razors_edge_blue", 1)]:
    _register(_slug, [
        TriggerDef(event_type="on_play", effect_fn=_factory_ar_power_bonus(_n)),
    ])

# -- run_through_yellow --
# Target sword gets go again. Next sword +2p.
def _run_through_effect(card, event, state):
    if state.combat and "Go Again" not in state.combat.keywords:
        state.combat.grant_keyword("Go Again")
    state.players[_controller_id(card)].current_turn_effects.append("next_attack_+2")

_register("run_through", [
    TriggerDef(event_type="on_play", effect_fn=_run_through_effect),
])

# -- searing_gaze_red --
# Target dagger +2p. If 2+ Draconic chain links, on-hit mark.
def _searing_gaze_effect(card, event, state):
    if state.combat:
        state.combat.attack_power += 2

_register("searing_gaze", [
    TriggerDef(event_type="on_play", effect_fn=_searing_gaze_effect),
])

# -- singing_steelblade_yellow --
# Dorinthea: weapon +1p. Reprise: +2p instead, go again.
def _singing_steelblade_effect(card, event, state):
    if state.combat:
        bonus = 2 if reprise_check(state) else 1
        state.combat.attack_power += bonus
        if reprise_check(state) and "Go Again" not in state.combat.keywords:
            state.combat.grant_keyword("Go Again")

_register("singing_steelblade", [
    TriggerDef(event_type="on_play", effect_fn=_singing_steelblade_effect),
])

# -- spike_with_bloodrot_red --
# Target stealth attack +3p, on-hit Bloodrot Pox.
def _spike_bloodrot_effect(card, event, state):
    if state.combat:
        state.combat.attack_power += 3
    cid = _controller_id(card)
    state.players[cid].current_turn_effects.append("next_hit_bloodrot_pox")

_register("spike_with_bloodrot", [
    TriggerDef(event_type="on_play", effect_fn=_spike_bloodrot_effect),
])

# -- throw_dagger_blue --
# Target dagger deals 1 damage. If damage dealt, dagger has hit.
_register("throw_dagger", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: effect_deal_damage(s, 3 - _controller_id(c), 1)),
])

# -- twinning_blade_yellow --
# May attack additional time with target sword.
_register("twinning_blade", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),  # Additional attack handled by engine
])

# -- up_the_ante_blue --
# Olympia: choose X+1 wager modes. Simplified: noop (wager).
_register("up_the_ante", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])


# ---------------------------------------------------------------
# DEFENSE REACTION cards (21)
# ---------------------------------------------------------------

# -- blood_in_the_water_red --
# On defend, discard/destroy top. If watery grave, +2d. Simplified: noop.
_register("blood_in_the_water", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- buzzsaw_trap_blue --
# Riptide: when defends attack with power > base, can't gain power.
_register("buzzsaw_trap", [
    TriggerDef(event_type="defend", effect_fn=lambda c, e, s: None),
])

# -- collapsing_trap_blue --
# Riptide: when defends attack with go again, attacker discards hand draws that many.
_register("collapsing_trap", [
    TriggerDef(event_type="defend", effect_fn=lambda c, e, s: None),
])

# -- flic_flak (red/yellow/blue) --
# Next card you defend with gains +2d if it has combo.
_register("flic_flak", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: s.players[_controller_id(c)].current_turn_effects.append(
                   "next_defend_combo_+2d")),
])

# -- hunter_or_hunted_blue --
# On defend, name card. Reveal top of attacker's deck. If match, banish and search for all copies.
_register("hunter_or_hunted", [
    TriggerDef(event_type="defend", effect_fn=lambda c, e, s: None),
])

# -- pulse_of_isenloft_blue --
# Legendary. Earth, Ice, Elemental action cards +1d defending this turn. Simplified: noop.
_register("pulse_of_isenloft", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- reckless_swing_blue --
# Discard random cost. If 6+p, deal 2 to attacker.
def _reckless_swing_play(card, event, state):
    cid = _controller_id(card)
    discarded = effect_discard(state, cid, 1, random_discard=True)
    if discarded and discarded[0].power is not None and discarded[0].power >= 6:
        if state.combat:
            attacker_id = state.combat.attacker_id
            effect_deal_damage(state, attacker_id, 2)

_register("reckless_swing", [
    TriggerDef(event_type="on_play", effect_fn=_reckless_swing_play),
])

# -- reduce_to_runechant_red --
# Costs r less per Runechant. Create Runechant.
_register("reduce_to_runechant", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: create_token(s, _controller_id(c), "runechant")),
])

# -- saving_grace_yellow --
# Optional charge. If charged, target attack -2p.
def _saving_grace_play(card, event, state):
    charged = _factory_on_play_charge_optional()(card, event, state)
    if charged and state.combat:
        state.combat.attack_power -= 2

_register("saving_grace", [
    TriggerDef(event_type="on_play", effect_fn=_saving_grace_play, is_optional=True),
])

# -- shelter_from_the_storm_red --
# Instant discard: prevent 3 damage this turn. Simplified: noop.
_register("shelter_from_the_storm", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- solid_ground_blue --
# Costs r less per Seismic Surge. Simplified: noop (cost reduction).
_register("solid_ground", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),
])

# -- soul_shield_yellow --
# Put into soul when chain closes.
_register("soul_shield", [
    TriggerDef(event_type="combat_chain_close",
               effect_fn=lambda c, e, s: effect_move_to_soul(s, c, _controller_id(c))),
])

# -- staunch_response_red -- (may already exist)
_register("staunch_response", [
    TriggerDef(event_type="on_play", effect_fn=lambda c, e, s: None),  # Handled by engine DR bonus
])

# -- tarpit_trap_yellow --
# When defends attack with go again, next hit effects don't trigger.
_register("tarpit_trap", [
    TriggerDef(event_type="defend", effect_fn=lambda c, e, s: None),
])


# ---------------------------------------------------------------
# Remaining cards from gap report not yet covered
# ---------------------------------------------------------------

# -- blue_fin_harpoon_blue -- (base already registered)
# -- red_fin_harpoon_blue -- (base already registered)
# -- yellow_fin_harpoon_blue -- (base already registered)
# -- king_kraken_harpoon_red -- (already registered)
# -- king_shark_harpoon_red -- (already registered)

# -- reckless_arithmetic_blue -- (base already registered)

# -- cheating_scoundrel_red -- (already registered)

# -- steal_victory_blue -- (base already registered)

# -- overcrowded_blue -- (base already registered)

# -- big_bully_red -- (base already registered)

# -- show_of_strength_red -- (base already registered)

# -- sigil_of_solace already registered

# -- swing_big_red -- (base already registered)

# -- looking_for_a_scrap_red -- (base already registered)

# -- codex_of_frailty_yellow -- (already registered)
# -- codex_of_inertia_yellow -- (already registered)

# -- portside_exchange_blue -- (already registered)
# -- sea_floor_salvage_blue -- (already registered)
# -- shallow_water_shark_harpoon_yellow -- (already registered)
# -- shifting_tides_blue -- (already registered)
# -- sunken_treasure_blue -- (already registered)
# -- three_of_a_kind_red -- (already registered)
# -- throw_caution_to_the_wind_blue -- (already registered)
# -- riches_of_trpaldhani_yellow -- (already registered)
# -- blink_blue -- (already registered)
# -- murderous_rabble_blue -- (already registered)
# -- golden_tipple_blue -- (already registered)
# -- big_game_trophy_shot_yellow -- (already registered)
# -- gold_the_tip_yellow -- (already registered)
# -- catch_of_the_day_blue -- (already registered)
# -- command_and_conquer_red -- (already registered)
# -- cloud_cover_red -- (already registered)
# -- electrostatic_discharge_red -- (already registered)
# -- current_funnel_blue -- (already registered)
# -- flittering_charge_red -- (already registered)
# -- etchings_of_arcana (red/yellow/blue) -- (already registered)
# -- mind_warp_yellow -- (already registered)
# -- blast_to_oblivion (red/yellow) -- (already registered)
# -- gone_in_a_flash_red -- (already registered)

# -- death_touch_red -- (already registered)
# -- art_of_desire_body_red -- (already registered)
# -- kiss_of_death_red -- (already registered)
# -- mark_of_the_black_widow (red/yellow) -- (already registered)
# -- pain_in_the_backside_red -- (already registered)
# -- leave_no_witnesses_red -- (already registered)
# -- pick_up_the_point_red -- (already registered)
# -- savor_bloodshed_red -- (already registered)
# -- inertia_trap_red -- (already registered)
# -- lair_of_the_spider_red -- (already registered)
# -- tarantula_toxin_red -- (already registered)
# -- take_up_the_mantle_yellow -- (already registered)
# -- pummel_red -- (already registered)
# -- sink_below (red/yellow/blue) -- (already registered)
# -- fiddlers_green_red -- already covered above

# -- comet_storm__shock_red -- (already registered)
# -- consign_to_cosmos__shock_yellow -- (already registered)
# -- null__shock_yellow -- (already registered)

# -- drink_em_under_the_table_red -- already covered above
# -- bet_big_red -- already covered above

# Fill in any remaining per-color slugs that might need separate entries
# Most share a base slug and are already covered.

# -- trench_of_sunken_treasure -- (already registered)


# ============================================================
# SECTION: Missing weapons and equipment for active deck pool
# ============================================================

# -- scepter_of_pain --
# "Once per Turn Action - {r}{r}: Deal 1 arcane damage to any opposing target.
#  Create a Runechant token for each damage dealt this way."
def _scepter_of_pain_activate(card, event, state):
    from engine.card_effects.card_keywords import effect_deal_damage, create_token
    cid = _controller_id(card)
    target_id = 3 - cid
    dmg = effect_deal_damage(state, target_id, 1, card, "arcane")
    dealt = dmg or 0
    for _ in range(dealt):
        create_token(state, cid, "runechant")

_register("scepter_of_pain", [
    TriggerDef(event_type="on_play", effect_fn=_scepter_of_pain_activate),
])

# -- nitro_mechanoid --
# "Action - Banish a card from under Nitro Mechanoid: Attack. Overpower. Temper."
# Cost: banish a CARD from under (card objects in weapon.cards_underneath, NOT counters).
# _weapon_can_attack in actions.py blocks attack if cards_underneath is empty.
# _apply_weapon_attack in engine.py banishes the card as cost.
# This trigger just adds Overpower to the attack keywords.
def _nitro_mechanoid_attacking(card, event, state):
    if not _is_this_attacking(card, event, state) or not state.combat:
        return
    if "Overpower" not in state.combat.keywords:
        state.combat.grant_keyword("Overpower")

_register("nitro_mechanoid", [
    TriggerDef(event_type="attacking", effect_fn=_nitro_mechanoid_attacking),
])

# -- spell_fray_tiara --
# "Spellvoid 1" — prevent 1 arcane damage by destroying this
# Handled by generic Spellvoid processing; register as defend trigger that signals spellvoid
_register("spell_fray_tiara", [
    TriggerDef(event_type="defend",
               effect_fn=lambda c, e, s: None),  # Spellvoid is a prevention replacement, not trigger
])

# -- ironrot_plate --
# "Blade Break" — no special effect, just has defense and blade break keyword.
# Already handled by the generic keyword system. No trigger needed.

# -- bracers_of_belief --
# "Action - Destroy: Reveal top card. Next AA you play this turn gets +X{p},
#  where X = 3 minus the pitch value of the revealed card. Go again."
def _bracers_of_belief_activate(card, event, state):
    cid = _controller_id(card)
    top = effect_look_top(state, cid, 1)
    if not top:
        return
    card_top = top[0]
    pitch_val = card_top.pitch or 0
    bonus = max(0, 3 - pitch_val)
    if bonus > 0:
        state.players[cid].current_turn_effects.append(f"next_attack_+{bonus}")

_register("bracers_of_belief", [
    TriggerDef(event_type="on_play", effect_fn=_bracers_of_belief_activate),
])

# -- bloodied_gauntlet --
# "Action - Destroy: Next attack action card gets +2{p}. Go again."
_register("bloodied_gauntlet", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: (
                   s.players[_controller_id(c)].current_turn_effects.append("next_attack_+2"),
                   effect_gain_action_point(s, _controller_id(c)),
               )),
])

# -- time_skippers --
# "Action - {r}{r}{r}, destroy: Gain 2 action points."
_register("time_skippers", [
    TriggerDef(event_type="on_play",
               effect_fn=lambda c, e, s: effect_gain_action_point(s, _controller_id(c), 2)),
])

# -- face_adversity --
# "This may only defend an attack if the attack's controller has drawn a card this turn."
# This is a defend restriction, not a trigger. It should be checked in _legal_defend_step.
# For now, register as a noop since the restriction is complex to enforce.
_register("face_adversity", [
    TriggerDef(event_type="defend", effect_fn=lambda c, e, s: None),
])

# -- threadbare_tunic --
# "Instant - Destroy: Gain {r}. Activate only if you have no cards in hand."
def _threadbare_tunic_activate(card, event, state):
    cid = _controller_id(card)
    player = state.players[cid]
    if player.hand.cards:
        return  # Can only activate with empty hand
    player.resources += 1

_register("threadbare_tunic", [
    TriggerDef(event_type="on_play", effect_fn=_threadbare_tunic_activate),
])

# -- grandstand_legplates --
# "{d} equals number of opposing heroes with greater {h}." 1v1 = 0 or 1.
# This is a continuous effect. Register as defend trigger to adjust defense.
def _grandstand_defend(card, event, state):
    if not _is_this_defending(card, event, state):
        return
    cid = _controller_id(card)
    opp = state.players[3 - cid]
    my_hp = state.players[cid].health
    # Adjust combat total_defense based on dynamic defense value
    if state.combat:
        old_def = card.base_defense or 0
        new_def = 1 if opp.health > my_hp else 0
        state.combat.total_defense += (new_def - old_def)

_register("grandstand_legplates", [
    TriggerDef(event_type="defend", effect_fn=_grandstand_defend),
])

# -- ironhide_helm --
# "When you defend with this, you may pay {r}. If you do, it gains +2{d} and Blade Break."
def _ironhide_helm_defend(card, event, state):
    if not _is_this_defending(card, event, state):
        return
    cid = _controller_id(card)
    player = state.players[cid]
    if player.resources >= 1:
        from engine.card_effects.card_keywords import _ask_player
        choice = _ask_player(state, cid, [True, False],
                             context="Ironhide Helm: pay {r} for +2{d}? (destroyed when chain closes)")
        if choice:
            player.resources -= 1
            if state.combat:
                state.combat.total_defense += 2
            # Flag for destruction when combat chain closes
            player.current_turn_effects.append("ironhide_helm_destroy_on_close")

def _ironhide_helm_close(card, event, state):
    """Destroy Ironhide Helm when combat chain closes if paid for +2{d}."""
    cid = _controller_id(card)
    player = state.players[cid]
    if "ironhide_helm_destroy_on_close" not in player.current_turn_effects:
        return
    player.current_turn_effects.remove("ironhide_helm_destroy_on_close")
    if card in player.head.cards:
        player.head.remove(card)
        player.graveyard.add(card)

_register("ironhide_helm", [
    TriggerDef(event_type="defend", effect_fn=_ironhide_helm_defend),
    TriggerDef(event_type="combat_chain_close", effect_fn=_ironhide_helm_close),
])

# -- quick_clicks --
# "Action - Destroy: Next attack gets go again. Activate only if you've played a Nimblism this turn."
def _quick_clicks_activate(card, event, state):
    cid = _controller_id(card)
    # Check if a Nimblism card was played this turn
    nimblism_played = any("nimblism" in eff for eff in state.players[cid].current_turn_effects)
    if not nimblism_played:
        return
    state.players[cid].current_turn_effects.append("next_attack_go_again")

_register("quick_clicks", [
    TriggerDef(event_type="on_play", effect_fn=_quick_clicks_activate),
])


# -- 10000_year_reunion_red --
# Cost: 8{r} OR remove 3 +1{p} counters from auras (alt cost handled in actions.py + engine.py).
# Aura. Enters arena with Ward 10.
# Ward can stack: each enters_arena registers a fresh Ward 10 directly on the effect manager,
# independent of card.keywords, so multiple copies in play each provide their own Ward 10.
def _10000_year_enters_arena(card, event, state):
    """On enters_arena: register a Ward 10 replacement effect for this card instance."""
    if state.effect_manager is not None:
        from engine.effects import _make_ward
        state.effect_manager.add_replacement(_make_ward(card, 10))

_register("10000_year_reunion_red", [
    TriggerDef(event_type="enters_arena", effect_fn=_10000_year_enters_arena),
])


# -- a_good_clean_fight_red --
# Cost: 3{r}. Attack Action.
# While attacking: opponent's public non-equipment cards have functional text blanked
# and their triggers suppressed.
# Restoration happens when the combat chain closes.

def _agcf_get_targets(state, attacker_id):
    """Return opponent's public, non-equipment cards that should be suppressed."""
    opp = state.players[3 - attacker_id]
    targets = []
    for zone in (opp.hand, opp.head, opp.chest, opp.arms, opp.legs,
                 opp.weapon1, opp.weapon2, opp.permanents, opp.hero_zone):
        for card in list(zone.cards):
            if not card.is_public:
                continue
            if "Equipment" in (card.types or []):
                continue
            targets.append(card)
    return targets


def _agcf_attacking(card, event, state):
    """Apply suppression when A Good Clean Fight enters the combat chain."""
    if not state.combat or state.combat.attack_card is not card:
        return
    attacker_id = _controller_id(card)
    targets = _agcf_get_targets(state, attacker_id)

    # Unique suppression function — identity used for later removal
    def _suppress_text(base):
        return ''

    for c in targets:
        c._triggers_suppressed = True
        c.effects.append(('base_functional_text', _suppress_text))

    # Store on the attack card for restoration at chain close
    card._agcf_suppressed_cards = targets
    card._agcf_suppress_fn = _suppress_text


def _agcf_chain_close(card, event, state):
    """Restore suppressed cards when the combat chain closes."""
    suppressed = getattr(card, '_agcf_suppressed_cards', [])
    suppress_fn = getattr(card, '_agcf_suppress_fn', None)

    for c in suppressed:
        # Remove trigger suppression flag
        c._triggers_suppressed = False
        # Remove the functional_text blanker by identity
        if suppress_fn is not None:
            c.effects = [(tag, fn) for tag, fn in c.effects
                         if not (tag == 'base_functional_text' and fn is suppress_fn)]

    # Clean up
    card._agcf_suppressed_cards = []
    card._agcf_suppress_fn = None


_register("a_good_clean_fight_red", [
    TriggerDef(event_type="attacking", effect_fn=_agcf_attacking),
    TriggerDef(event_type="combat_chain_close", effect_fn=_agcf_chain_close),
])


# -- a_drop_in_the_ocean_blue --
# Cost 0{r}. Instant.
# Targets: any attack card currently on the combat chain (current attack OR a previous
# chain link's attack card that is still physically on the chain zone).
# Effect: chosen attack gets -1{p} permanently (added to card.effects).
# Transcend: if a blue card was played this turn (other than this card), flip to hand
# as "inner_chi" (transcended state). Otherwise goes to graveyard normally.
#
# inner_chi: the back face. Pitches for 3{r} OR 3{c} (chi). Implemented as a card
# in the DB with base_pitch=3 and a pitch_gives_chi flag. The choice between chi and
# resource is made at pitch time in _pitch_for_cost (for_chi=True path).

def _a_drop_in_the_ocean_play(card, event, state):
    from engine.card_effects.card_keywords import _ask_player, _remove_from_current_zone, effect_transcend
    cid = _controller_id(card)

    # Build target list: all attack cards currently on the combat chain
    targets = [c for c in state.combat_chain.cards if c.is_attack or "Attack" in (c.types or [])]
    # Also include the current attack card if it exists and isn't already in combat_chain
    if state.combat and state.combat.attack_card:
        ac = state.combat.attack_card
        if ac not in targets:
            targets.append(ac)

    if not targets:
        return  # no valid targets (shouldn't happen — PLAY_TARGET_CONDITIONS guards this)

    # Ask player to choose which attack to debuff
    pick = _ask_player(state, cid, [c.slug for c in targets],
                       context="A Drop in the Ocean: choose an attack on the combat chain to give -1{p}")
    chosen = next((c for c in targets if c.slug == str(pick)), targets[0])

    # Apply -1{p} as a persistent card effect
    chosen.effects.append(("base_power", lambda base: base - 1))
    # Immediately recalculate combat power if this is the current attack
    if state.combat and state.combat.attack_card is chosen:
        from engine.engine import _recalculate_attack_power
        _recalculate_attack_power(state)

    # Transcend check: if a blue card was played this turn, flip to hand as inner_chi
    player = state.players[cid]
    if any(c.base_color == 'blue' for c in player.cards_played_this_turn):
        effect_transcend(state, cid, source=card)
    # else: normal resolution — card goes to graveyard (engine handles this for non-aura instants)


def _a_drop_in_the_ocean_target_condition(state, pid):
    """Legal only when there is at least one attack card on the combat chain."""
    targets = [c for c in state.combat_chain.cards
               if c.is_attack or "Attack" in (c.types or [])]
    if not targets and state.combat and state.combat.attack_card:
        return True
    return bool(targets)


_register("a_drop_in_the_ocean_blue", [
    TriggerDef(event_type="on_play", effect_fn=_a_drop_in_the_ocean_play),
])

# Register play target condition so the card can't be played with no valid target
from engine.card_effects.registry import PLAY_TARGET_CONDITIONS
PLAY_TARGET_CONDITIONS["a_drop_in_the_ocean"] = _a_drop_in_the_ocean_target_condition

# inner_chi: back face of A Drop in the Ocean.
# Pitches for 3{r} or 3{c}. The pitch choice is a player decision at pitch time.
# The card DB should have base_pitch=3. We flag it with pitch_gives_chi=True so
# _pitch_for_cost can offer the chi option when it's among the pitchable cards.
# No on_play effect — inner_chi is purely a pitch resource card.
def _inner_chi_entered_hand(card, event, state):
    """Mark inner_chi so pitch logic knows it can give chi instead of resources."""
    card.pitch_gives_chi = True  # picked up by _pitch_for_cost

_register("inner_chi", [
    # No gameplay trigger — pitch effect handled by engine
])


# ============================================================
# absorb_in_aether (red/yellow/blue)
# DR, cost 1{r}. Printed defense: 4/3/2.
# On resolution: the next non-permanent card PLAYED this turn that deals
# arcane damage deals +2 more on ALL its arcane damage instances.
#
# Unlike amp_N (which buffs only the next arcane damage EVENT), arcane_play_amp
# replaces the card's text — all arcane damage on that card is buffed.
# e.g. Forked Lightning (two arcane damage hits) would deal +2 on BOTH.
#
# Implementation: register a one-shot on_play listener that stamps the next
# non-permanent played card with _arcane_play_amp=2. effect_deal_arcane reads
# the stamp but does NOT consume it, so all instances on the same card benefit.
# ============================================================
_ARCANE_PLAY_AMP_PERMANENT_TYPES = {
    "Aura", "Item", "Ally", "Equipment", "Figment", "Token", "Landmark"
}

def _absorb_in_aether_play(card, event, state):
    cid = _controller_id(card)

    def _stamp_next_arcane_card(ev, gs):
        played = ev.data.get("card") if ev.data else None
        if played is None or played is card:
            return
        played_cid = _controller_id(played)
        if played_cid != cid:
            return
        if set(played.types or []) & _ARCANE_PLAY_AMP_PERMANENT_TYPES:
            return  # auras/items already in play don't benefit
        # Stamp the card instance: ALL arcane damage from it gets +2
        played._arcane_play_amp = getattr(played, '_arcane_play_amp', 0) + 2
        # One-shot: unregister both listeners
        gs.event_manager.unregister('on_play', _stamp_next_arcane_card)
        gs.event_manager.unregister('end_of_turn', _cleanup)

    def _cleanup(ev, gs):
        gs.event_manager.unregister('on_play', _stamp_next_arcane_card)
        gs.event_manager.unregister('end_of_turn', _cleanup)

    state.event_manager.register('on_play', _stamp_next_arcane_card)
    state.event_manager.register('end_of_turn', _cleanup)

for _slug in ("absorb_in_aether_red", "absorb_in_aether_yellow", "absorb_in_aether_blue"):
    _register(_slug, [
        TriggerDef(event_type="on_play", effect_fn=_absorb_in_aether_play),
    ])


# ============================================================
# aether_flare (red/yellow/blue)
# Cost: 1{r}, 1AP. Deal N arcane damage to target opposing hero.
# Then: the next card YOU play this turn with base_arcane_damage > 0
#   stamps _arcane_play_amp = X (actual damage dealt after prevention).
#   This means ALL arcane damage events on that card are each increased by X.
# Listener is cleaned up at end of turn if no qualifying card is played.
# ============================================================
_AETHER_FLARE_BASE = {"aether_flare_red": 3, "aether_flare_yellow": 2, "aether_flare_blue": 1}

def _aether_flare_play(card, event, state):
    cid = _controller_id(card)
    opp_id = 3 - cid
    base = _AETHER_FLARE_BASE.get(card.slug, 0)

    # Deal arcane damage to opposing hero; capture actual amount after prevention
    x = effect_deal_arcane(state, opp_id, base, source=card)
    if x <= 0:
        return  # all damage was prevented; no buff to register

    # One-shot on_play listener: stamp the next arcane card played this turn
    def _stamp_next_arcane(ev, gs):
        played = ev.data.get("card") if ev.data else None
        if played is None or played is card:
            return
        played_cid = _controller_id(played)
        if played_cid != cid:
            return
        # Only cards that intrinsically deal arcane damage
        if not (played.base_arcane_damage or 0) > 0:
            return
        # Stamp: ALL arcane damage events on this card get +X
        played._arcane_play_amp = getattr(played, '_arcane_play_amp', 0) + x
        # One-shot: unregister both listeners
        gs.event_manager.unregister('on_play', _stamp_next_arcane)
        gs.event_manager.unregister('end_of_turn', _cleanup)

    # End-of-turn cleanup in case no qualifying card was played
    def _cleanup(ev, gs):
        gs.event_manager.unregister('on_play', _stamp_next_arcane)
        gs.event_manager.unregister('end_of_turn', _cleanup)

    state.event_manager.register('on_play', _stamp_next_arcane)
    state.event_manager.register('end_of_turn', _cleanup)

for _slug in ("aether_flare_red", "aether_flare_yellow", "aether_flare_blue"):
    _register(_slug, [
        TriggerDef(event_type="on_play", effect_fn=_aether_flare_play),
    ])


# ============================================================
# Final verification: count registered triggers
# ============================================================
_new_count = sum(1 for k in CARD_TRIGGERS if k not in {
    # Don't count these as "new" -- they were pre-existing
})
