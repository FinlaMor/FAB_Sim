from __future__ import annotations

import copy
from typing import Any, Optional

from engine.actions import Action, ActionType
from engine.card import Card, CardDB
from engine.state import ChainLink, CombatState, GameState, Player, StackEntry, Step


_PRIVATE_ZONES = {"hand", "deck", "arsenal", "inventory"}
_HIDDEN_CARD_SLUG = "card_back"

_COMBAT_KEYWORD_FLAGS = {
    "goAgain": "Go Again",
    "dominate": "Dominate",
    "overpower": "Overpower",
    "confidence": "Confidence",
    "activeOnHits": "On Hit",
    "wager": "Wager",
    "phantasm": "Phantasm",
    "fusion": "Fusion",
    "fused": "Fused",
    "tower": "Tower",
    "piercing": "Piercing",
    "combo": "Combo",
    "highTide": "High Tide",
    "isDraconic": "Draconic",
}


_ACTION_SPEED_TYPES = {
    ActionType.PLAY_CARD,
    ActionType.PLAY_ARSENAL,
    ActionType.PLAY_BANISH,
    ActionType.STORE_ARSENAL,
    ActionType.ATTACK_WEAPON,
    ActionType.ATTACK_ALLY,
    ActionType.ACTIVATE_ITEM,
    ActionType.ACTIVATE_EQUIPMENT,
    ActionType.ACTIVATE_WEAPON,
    ActionType.ACTIVATE_HERO,
    ActionType.DISCARD_ACTIVATE,
}


_REACTION_SPEED_TYPES = {
    ActionType.PLAY_ATTACK_REACTION,
    ActionType.PLAY_DEFENSE_REACTION,
    ActionType.REACTION_PASS,
}


from rl_agents.utils.card_helpers import safe_int as _safe_int


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _talishar_face_down(card_view: dict[str, Any]) -> bool:
    return str(card_view.get("facing") or "").upper() == "DOWN"


def _zone_default_public(zone_name: str) -> bool:
    return zone_name not in _PRIVATE_ZONES


def _resolve_card_visibility(
    card_view: dict[str, Any],
    zone_name: str,
    is_public: Optional[bool],
) -> bool:
    facing = str(card_view.get("facing") or "").upper()
    if facing == "DOWN":
        return False
    if facing == "UP" and zone_name in {"arsenal", "banished", "deck"}:
        return True
    if is_public is not None:
        return is_public
    return _zone_default_public(zone_name)


def _normalize_counter_name(raw_name: Any) -> str:
    name = str(raw_name or "").strip().lower().replace(" ", "_")
    return {
        "attack": "plus_power",
        "power": "plus_power",
        "defense": "plus_defense",
    }.get(name, name)


def _extract_talishar_counters(card_view: dict[str, Any]) -> dict[str, int]:
    counters: dict[str, int] = {}

    counters_map = card_view.get("countersMap")
    if isinstance(counters_map, dict):
        for raw_name, raw_value in counters_map.items():
            value = _safe_int(raw_value, default=0)
            if value != 0:
                counters[_normalize_counter_name(raw_name)] = value

    fallback_fields = {
        "powerCounters": "plus_power",
        "defCounters": "plus_defense",
        "lifeCounters": "life",
        "counters": "counters",
    }
    for raw_field, counter_name in fallback_fields.items():
        value = _safe_int(card_view.get(raw_field), default=0)
        if value != 0 and counter_name not in counters:
            counters[counter_name] = value

    if _safe_bool(card_view.get("holoCounters")):
        counters.setdefault("holo", 1)

    return counters


def _extract_talishar_object_id(card_view: dict[str, Any]) -> Optional[int]:
    unique_id = str(card_view.get("uniqueID") or "")
    if not unique_id:
        return None
    tail = unique_id.rsplit(";", 1)[-1]
    object_id = _safe_int(tail, default=0)
    return object_id if object_id > 0 else None


def _extract_card_slug(raw_card: Any) -> Optional[str]:
    if isinstance(raw_card, dict):
        slug = _safe_str(raw_card.get("cardNumber"))
    elif isinstance(raw_card, str):
        slug = _safe_str(raw_card)
    else:
        return None
    if not slug or slug == "CardBack":
        return None
    return slug


def _extract_effect_slugs(raw_effects: Any) -> list[str]:
    slugs: list[str] = []
    if not isinstance(raw_effects, list):
        return slugs

    for raw in raw_effects:
        slug = _extract_card_slug(raw)
        if slug is None and isinstance(raw, dict):
            slug = _extract_card_slug(raw.get("card"))
        if slug is not None:
            slugs.append(slug)

    return slugs


def _placeholder_hidden_card(owner_id: int, zone_name: str) -> Card:
    card = Card(slug=_HIDDEN_CARD_SLUG, name="Card Back")
    card.owner = owner_id
    card.controller = owner_id
    card.zone = zone_name
    card.prev_zone = zone_name
    card.is_public = False
    card.face_down = True
    return card


def _fill_hidden_zone_cards(
    known_cards: list[Card],
    *,
    owner_id: int,
    zone_name: str,
    total_count: int,
) -> list[Card]:
    cards = list(known_cards)
    for _ in range(max(0, total_count - len(cards))):
        cards.append(_placeholder_hidden_card(owner_id, zone_name))
    return cards


# Map Talishar event type strings → engine tracked event constants.
# The engine's gamestate_embedder tracks these 15 events:
#   card_pitched, on_play, attacking, defend, hit, damage_dealt,
#   arcane_damage_dealt, card_banished, card_destroyed, gold_created,
#   die_roll, crowd_boos, start_of_turn, start_of_action_phase, start_of_end_phase
_TALISHAR_EVENT_MAP: dict[str, str] = {
    # Talishar raw (lowered, spaces→underscores) → engine constant
    "pitch": "card_pitched",
    "card_pitched": "card_pitched",
    "pitched": "card_pitched",
    "play": "on_play",
    "play_card": "on_play",
    "on_play": "on_play",
    "played": "on_play",
    "attack": "attacking",
    "attacking": "attacking",
    "defend": "defend",
    "defense": "defend",
    "block": "defend",
    "hit": "hit",
    "on_hit": "hit",
    "damage": "damage_dealt",
    "damage_dealt": "damage_dealt",
    "arcane_damage": "arcane_damage_dealt",
    "arcane_damage_dealt": "arcane_damage_dealt",
    "banish": "card_banished",
    "card_banished": "card_banished",
    "banished": "card_banished",
    "destroy": "card_destroyed",
    "card_destroyed": "card_destroyed",
    "destroyed": "card_destroyed",
    "gold": "gold_created",
    "gold_created": "gold_created",
    "create_gold": "gold_created",
    "die_roll": "die_roll",
    "roll": "die_roll",
    "crowd_boos": "crowd_boos",
    "start_of_turn": "start_of_turn",
    "start_turn": "start_of_turn",
    "start_of_action_phase": "start_of_action_phase",
    "action_phase": "start_of_action_phase",
    "start_of_end_phase": "start_of_end_phase",
    "end_phase": "start_of_end_phase",
}


def _extract_event_types(raw_events: Any) -> set[str]:
    event_types: set[str] = set()
    if not isinstance(raw_events, dict):
        return event_types

    for raw_event in raw_events.get("eventArray", []):
        if not isinstance(raw_event, dict):
            continue
        raw_type = _safe_str(raw_event.get("eventType")).lower().replace(" ", "_")
        if not raw_type:
            continue
        mapped = _TALISHAR_EVENT_MAP.get(raw_type, raw_type)
        event_types.add(mapped)

    return event_types


def _extract_landmarks(raw_landmarks: Any) -> list[tuple[int, str]]:
    landmarks: list[tuple[int, str]] = []
    if not isinstance(raw_landmarks, list):
        return landmarks

    for raw in raw_landmarks:
        if isinstance(raw, dict):
            player_id = _safe_int(
                raw.get("playerID") or raw.get("player") or raw.get("controller"),
                default=0,
            )
            text = _safe_str(
                raw.get("landmark")
                or raw.get("name")
                or raw.get("caption")
                or raw.get("eventType")
                or raw.get("type")
            )
            if text:
                landmarks.append((player_id, text))
        elif isinstance(raw, str):
            text = _safe_str(raw)
            if text:
                landmarks.append((0, text))

    return landmarks


def _extract_combat_keywords(*raw_links: Any) -> list[str]:
    keywords: list[str] = []
    seen: set[str] = set()

    def _add(keyword: str) -> None:
        if keyword and keyword not in seen:
            keywords.append(keyword)
            seen.add(keyword)

    for raw in raw_links:
        if not isinstance(raw, dict):
            continue

        raw_keywords = raw.get("keywords")
        if isinstance(raw_keywords, list):
            for keyword in raw_keywords:
                k = _safe_str(keyword).lower()
                if k:
                    _add(k)

        for raw_flag, keyword in _COMBAT_KEYWORD_FLAGS.items():
            if _safe_bool(raw.get(raw_flag)):
                _add(keyword)

    return keywords


def _build_chain_links(
    raw_chain_links: Any,
    raw_active_chain_link: Any,
    *,
    fallback_attacker_id: int,
) -> list[ChainLink]:
    chain_links: list[ChainLink] = []
    if not isinstance(raw_chain_links, list):
        return chain_links

    active_attack_slug = None
    if isinstance(raw_active_chain_link, dict):
        active_attack_slug = _extract_card_slug(raw_active_chain_link.get("attackingCard"))

    for idx, raw_link in enumerate(raw_chain_links):
        if not isinstance(raw_link, dict):
            continue

        result = _safe_str(raw_link.get("result")).lower()
        hit = _safe_bool(raw_link.get("hit")) or result == "hit"

        attacker_id = _safe_int(
            raw_link.get("attackerID") or raw_link.get("attacker") or raw_link.get("controller"),
            default=fallback_attacker_id,
        )
        if attacker_id not in (1, 2):
            attacker_id = fallback_attacker_id

        attack_slug = (
            _extract_card_slug(raw_link.get("attackingCard"))
            or _extract_card_slug(raw_link.get("attackCard"))
            or _extract_card_slug(raw_link.get("card"))
            or _extract_card_slug(raw_link)
        )
        if not attack_slug and idx == len(raw_chain_links) - 1:
            attack_slug = active_attack_slug
        if not attack_slug:
            attack_slug = "unknown_attack"

        attack_power = _safe_int(
            raw_link.get("attackPower") or raw_link.get("power") or raw_link.get("totalPower"),
            default=0,
        )
        net_damage = _safe_int(raw_link.get("netDamage") or raw_link.get("damage"), default=0)
        if net_damage == 0 and hit:
            net_damage = 1

        keywords = _extract_combat_keywords(raw_link)

        chain_links.append(
            ChainLink(
                chainlink_id=idx + 1,
                attacker_id=attacker_id,
                attack_slug=attack_slug,
                attack_power=attack_power,
                net_damage=net_damage,
                keywords=keywords,
                from_weapon=_safe_bool(raw_link.get("fromWeapon") or raw_link.get("isWeapon")),
                hit=hit,
            )
        )

    return chain_links


def _build_combat_state(
    raw_active_chain_link: Any,
    card_db: CardDB,
    *,
    fallback_attacker_id: int,
    chain_link_count: int,
) -> Optional[CombatState]:
    if not isinstance(raw_active_chain_link, dict):
        return None

    attack_card_raw = raw_active_chain_link.get("attackingCard")
    attacker_id = _safe_int(
        (attack_card_raw or {}).get("controller") if isinstance(attack_card_raw, dict) else None,
        default=fallback_attacker_id,
    )
    if attacker_id not in (1, 2):
        attacker_id = fallback_attacker_id

    attack_card = talishar_card_to_card(
        attack_card_raw if isinstance(attack_card_raw, dict) else None,
        card_db,
        owner_id=attacker_id,
        controller_id=attacker_id,
        zone_name="combat chain",
        is_public=True,
        allow_hidden_identity=False,
    )

    total_power = _safe_int(raw_active_chain_link.get("totalPower"), default=0)
    total_defense = _safe_int(raw_active_chain_link.get("totalDefense"), default=0)
    has_reactions = bool(raw_active_chain_link.get("reactions"))

    has_combat_signal = attack_card is not None or total_power != 0 or total_defense != 0 or has_reactions
    if not has_combat_signal:
        return None

    if attack_card is None:
        attack_card = Card(slug="unknown_attack", name="Unknown Attack", types=["Attack"])
        attack_card.owner = attacker_id
        attack_card.controller = attacker_id
        attack_card.zone = "combat chain"
        attack_card.prev_zone = "combat chain"
        attack_card.is_public = True

    defending_cards: list[Card] = []
    defending_equipment_zones: list[str] = []
    for raw_reaction in raw_active_chain_link.get("reactions", []):
        if not isinstance(raw_reaction, dict):
            continue
        defender_id = _safe_int(raw_reaction.get("controller"), default=3 - attacker_id)
        if defender_id not in (1, 2):
            defender_id = 3 - attacker_id
        reaction_card = talishar_card_to_card(
            raw_reaction,
            card_db,
            owner_id=defender_id,
            controller_id=defender_id,
            zone_name="combat chain",
            is_public=True,
            allow_hidden_identity=False,
        )
        if reaction_card is None:
            continue
        defending_cards.append(reaction_card)

        if reaction_card.is_equipment:
            subtypes = set(reaction_card.subtypes or [])
            raw_slot = _safe_str(raw_reaction.get("sType"))
            if raw_slot:
                subtypes.add(raw_slot)
            for slot_name in ("Head", "Chest", "Arms", "Legs"):
                if slot_name in subtypes:
                    defending_equipment_zones.append(slot_name.lower())
                    break

    keywords = _extract_combat_keywords(raw_active_chain_link)

    return CombatState(
        attacker_id=attacker_id,
        link_id=max(1, chain_link_count + 1),
        attack_power=total_power,
        attack_card=attack_card,
        keywords=keywords,
        base_attack_power=attack_card.base_power if attack_card.base_power is not None else total_power,
        from_weapon=attack_card.is_weapon,
        attack_source=attack_card,
        defending_cards=defending_cards,
        total_defense=total_defense,
        defending_equipment_defense=sum(
            card.defense or 0 for card in defending_cards if card.is_equipment
        ),
        defender_used_hand_card=any(not card.is_equipment for card in defending_cards),
        defending_declared=bool(defending_cards) or total_defense > 0,
        defending_equipment_zones=defending_equipment_zones,
    )


def _build_stack_entries(
    raw_layer_display: Any,
    card_db: CardDB,
    *,
    fallback_player_id: int,
) -> tuple[list[Card], list[StackEntry], str]:
    stack_cards: list[Card] = []
    stack_entries: list[StackEntry] = []
    stack_target = ""

    if not isinstance(raw_layer_display, dict):
        return stack_cards, stack_entries, stack_target

    stack_target = _safe_str(raw_layer_display.get("target"))
    layer_contents = raw_layer_display.get("layerContents")
    reorderable_layers = raw_layer_display.get("reorderableLayers")

    position_lookup: dict[tuple[str, int], tuple[int, bool]] = {}
    # P1-3: Extract layer metadata from reorderableLayers (target, additionalCosts, layerType)
    layer_metadata: dict[tuple[str, int], dict[str, Any]] = {}
    if isinstance(reorderable_layers, list):
        for raw_layer in reorderable_layers:
            if not isinstance(raw_layer, dict):
                continue
            raw_card = raw_layer.get("card")
            slug = _extract_card_slug(raw_card)
            if slug is None:
                continue
            controller = _safe_int((raw_card or {}).get("controller"), default=fallback_player_id)
            if controller not in (1, 2):
                controller = fallback_player_id
            layer_id = _safe_int(raw_layer.get("layerID"), default=0)
            position_lookup[(slug, controller)] = (layer_id + 1, _safe_bool(raw_layer.get("isReorderable")))
            layer_metadata[(slug, controller)] = {
                "layerType": raw_layer.get("layerType"),
                "target": raw_layer.get("target"),
                "additionalCosts": raw_layer.get("additionalCosts"),
                "parameter": raw_layer.get("parameter"),
                "uniqueID": raw_layer.get("uniqueID"),
            }

    if not isinstance(layer_contents, list):
        return stack_cards, stack_entries, stack_target

    for idx, raw_layer_card in enumerate(layer_contents):
        if not isinstance(raw_layer_card, dict):
            continue

        controller = _safe_int(raw_layer_card.get("controller"), default=fallback_player_id)
        if controller not in (1, 2):
            controller = fallback_player_id

        card = talishar_card_to_card(
            raw_layer_card,
            card_db,
            owner_id=controller,
            controller_id=controller,
            zone_name="stack",
            is_public=True,
            allow_hidden_identity=False,
        )
        if card is None:
            continue

        layer_position = idx + 1
        is_reorderable = False
        lookup_key = (card.slug, controller)
        if lookup_key in position_lookup:
            layer_position, is_reorderable = position_lookup[lookup_key]

        # P1-3: Use layer_metadata from reorderableLayers when available
        meta = layer_metadata.get(lookup_key, {})

        # Layer type: prefer Talishar's explicit layerType, fall back to inference
        raw_layer_type = meta.get("layerType")
        if raw_layer_type == "TRIGGER":
            layer_type = "triggered"
        elif raw_layer_type == "ABILITY":
            layer_type = "activated"
        elif raw_layer_type is not None:
            layer_type = "card"
        else:
            # Infer layer_type from card properties
            layer_type = "card"
            if card.is_equipment or card.is_weapon:
                layer_type = "activated"
            elif card.has_triggered_ability and not card.is_action and not card.is_attack:
                layer_type = "triggered"

        # Infer from_arsenal: check if raw card has arsenal indicators
        from_arsenal = _safe_bool(raw_layer_card.get("fromArsenal", False))

        # Extract declared metadata — prefer reorderableLayers metadata, fall back to layerContents fields
        declared_x = None
        # Talishar stores X/parameter values in additionalCosts or parameter
        raw_x = (
            raw_layer_card.get("declaredX")
            or raw_layer_card.get("xValue")
            or meta.get("additionalCosts")
            or meta.get("parameter")
        )
        if raw_x is not None:
            declared_x = _safe_int(raw_x, default=None)

        declared_modes: list[str] = []
        raw_modes = raw_layer_card.get("declaredModes") or raw_layer_card.get("modes")
        if isinstance(raw_modes, list):
            declared_modes = [str(m) for m in raw_modes if m]
        # additionalCosts can encode a mode choice (e.g. "Option_A" from BUTTONINPUT)
        if not declared_modes and declared_x is None:
            raw_ac = meta.get("additionalCosts")
            if isinstance(raw_ac, str) and raw_ac and not raw_ac.lstrip("-").isdigit():
                declared_modes = [raw_ac]

        declared_targets: list[str] = []
        raw_targets = (
            raw_layer_card.get("declaredTargets")
            or raw_layer_card.get("targets")
            or meta.get("target")
        )
        if isinstance(raw_targets, list):
            declared_targets = [str(t) for t in raw_targets if t]
        elif isinstance(raw_targets, str) and raw_targets and raw_targets != "-":
            declared_targets = [raw_targets]

        stack_cards.append(card)
        entry = StackEntry(
            player_id=controller,
            card=card,
            layer_type=layer_type,
            layer_position=layer_position,
            from_arsenal=from_arsenal,
            declared_x=declared_x,
            declared_modes=declared_modes,
            declared_targets=declared_targets,
        )
        entry.talishar_reorderable = is_reorderable
        stack_entries.append(entry)

    stack_entries.sort(key=lambda e: e.layer_position)
    return stack_cards, stack_entries, stack_target


def _infer_consecutive_passes(
    *,
    has_priority: bool,
    has_stack_entries: bool,
    state_view: dict[str, Any] | None = None,
) -> int:
    # Try to extract an explicit pass count from Talishar state
    if state_view is not None:
        raw_passes = state_view.get("consecutivePasses") or state_view.get("numPasses")
        if raw_passes is not None:
            return _safe_int(raw_passes, default=0)

    # P2-4: Infer from tracker position — damage/resolution/close means both passed (2)
    if state_view is not None:
        tracker = state_view.get("tracker") or {}
        tracker_pos = _safe_str(tracker.get("position")).lower()
        if tracker_pos in ("damage", "resolution", "close"):
            return 2

    if not has_stack_entries:
        return 0
    # Stack entries exist: if we have priority, opponent likely passed (1); otherwise 0
    return 0 if has_priority else 1


def _phase_from_step(step: Step) -> str:
    if step in {Step.START_PHASE, Step.BEGIN_GAME}:
        return "start"
    if step in {Step.END_PHASE_BEGINNING, Step.END_PHASE_CLEANUP, Step.END_TURN, Step.END_GAME}:
        return "end"
    return "action"


def _extract_prompt_text(state_view: dict[str, Any]) -> str:
    turn_phase = _safe_str((state_view.get("turnPhase") or {}).get("caption"))
    prompt_help = _safe_str((state_view.get("playerPrompt") or {}).get("helpText"))
    popup = (state_view.get("playerInputPopUp") or {}).get("popup") or {}
    popup_title = _safe_str(popup.get("title")) if isinstance(popup, dict) else ""
    text_parts = [part for part in (turn_phase, prompt_help, popup_title) if part]
    return "\n".join(text_parts)


def _is_target_selection_phase(phase_code: str) -> bool:
    return phase_code in {"MAYCHOOSEHAND", "MAYCHOOSEMULTIZONE", "BUTTONINPUT", "YESNO"}


def _infer_priority_player(state_view: dict[str, Any], player_id: int) -> int:
    if _safe_bool(state_view.get("havePriority")):
        return player_id
    other_player = _safe_int(state_view.get("otherPlayer"), default=0)
    if other_player in (1, 2):
        return other_player
    turn_player = _safe_int(state_view.get("turnPlayer"), default=0)
    if turn_player in (1, 2):
        return turn_player
    return player_id


def _infer_chain_link_number(state_view: dict[str, Any]) -> int:
    chain_links = state_view.get("combatChainLinks")
    count = len(chain_links) if isinstance(chain_links, list) else 0
    active_chain = state_view.get("activeChainLink")
    if isinstance(active_chain, dict) and active_chain.get("attackingCard"):
        return count + 1
    return count


def _infer_slot(card: Optional[Card], raw_action: dict[str, Any]) -> Optional[str]:
    raw_slot = _safe_str(raw_action.get("sType"))
    if raw_slot:
        for slot_name in ("Head", "Chest", "Arms", "Legs"):
            if raw_slot.lower() == slot_name.lower():
                return slot_name

    if card is None:
        return None
    subtypes = set(card.subtypes or [])
    for slot_name in ("Head", "Chest", "Arms", "Legs"):
        if slot_name in subtypes:
            return slot_name
    return None


_ALT_COST_ALIASES: dict[str, str] = {
    "rune gate": "rune_gate",
    "runegate": "rune_gate",
    "cash in": "cash_in",
    "cashin": "cash_in",
    "rise above": "rise_above",
    "riseabove": "rise_above",
    "life of party": "life_of_party",
    "life of the party": "life_of_party",
    "double down": "double_down",
    "doubledown": "double_down",
    "reunion": "reunion",
    "soul reaping": "soul_reaping",
    "soulreaping": "soul_reaping",
    "meld": "meld",
}


def _infer_alternative_cost(raw_action: dict[str, Any]) -> Optional[str]:
    # Prefer structured field if present
    explicit = raw_action.get("alternativeCost") or raw_action.get("altCost")
    if explicit:
        return str(explicit)

    raw_text = _safe_str(raw_action.get("restriction") or raw_action.get("label"))
    if not raw_text:
        return None
    normalized = raw_text.lower().replace("-", " ").replace("_", " ").strip()
    # Try known aliases first
    for alias, canonical in _ALT_COST_ALIASES.items():
        if alias in normalized:
            return canonical
    # Fallback: normalize free text
    result = "_".join(part for part in normalized.split() if part)
    return result or None


def _infer_declared_x(state_view: dict[str, Any], raw_action: dict[str, Any]) -> Optional[int]:
    prompt_text = _extract_prompt_text(state_view).lower()
    if "x" not in prompt_text:
        return None

    button_input = _safe_str(raw_action.get("buttonInput"))
    if button_input.isdigit():
        return _safe_int(button_input)

    card_id = _safe_str(raw_action.get("cardID"))
    if card_id.isdigit() and "choose" in prompt_text:
        return _safe_int(card_id)

    return None


def _infer_action_cost(
    *,
    action_type: ActionType,
    card: Optional[Card],
    phase_code: str,
) -> int:
    if action_type in {
        ActionType.PASS,
        ActionType.REACTION_PASS,
        ActionType.DEFEND_CARDS,
        ActionType.DEFEND_EQUIPMENT,
        ActionType.STORE_ARSENAL,
    }:
        return 0

    if action_type in _REACTION_SPEED_TYPES:
        return 0

    if card is None:
        return 0

    if action_type in {ActionType.ACTIVATE_EQUIPMENT, ActionType.ACTIVATE_WEAPON, ActionType.ACTIVATE_HERO, ActionType.ACTIVATE_ITEM}:
        if card.has_action_activation:
            return 1
        if card.has_instant_activation:
            return 0

    if "Instant" in (card.types or []) or "Attack Reaction" in (card.types or []) or "Defense Reaction" in (card.types or []):
        return 0

    if phase_code in {"INSTANT", "A", "D"}:
        return 0

    return 1


def _infer_resource_cost(
    *,
    action_type: ActionType,
    card: Optional[Card],
) -> int:
    if action_type in {
        ActionType.PASS,
        ActionType.REACTION_PASS,
        ActionType.DEFEND_CARDS,
        ActionType.DEFEND_EQUIPMENT,
        ActionType.STORE_ARSENAL,
    }:
        return 0

    if card is None:
        return 0

    if action_type in {ActionType.ACTIVATE_EQUIPMENT, ActionType.ACTIVATE_WEAPON, ActionType.ACTIVATE_HERO, ActionType.ACTIVATE_ITEM}:
        return card.activation_cost or 0

    return card.cost or 0


def _infer_speed_flags(
    *,
    action_type: ActionType,
    card: Optional[Card],
    phase_code: str,
) -> tuple[bool, bool, bool]:
    if action_type in {
        ActionType.PASS,
        ActionType.STORE_ARSENAL,
        ActionType.DEFEND_CARDS,
        ActionType.DEFEND_EQUIPMENT,
    }:
        return False, False, False

    if action_type in _REACTION_SPEED_TYPES:
        return True, False, False

    instantish = False
    if card is not None:
        instantish = (
            "Instant" in (card.types or [])
            or "Attack Reaction" in (card.types or [])
            or "Defense Reaction" in (card.types or [])
            or card.has_instant_activation
        )

    actionish = action_type in _ACTION_SPEED_TYPES
    if card is not None and card.is_action:
        actionish = True

    played_as_instant = bool(actionish and not instantish and phase_code == "INSTANT")
    return bool(instantish), bool(actionish), played_as_instant


def _infer_has_go_again(action_type: ActionType, card: Optional[Card], state_view: dict[str, Any]) -> bool:
    if card is not None and card.has_go_again:
        return True
    if action_type in {ActionType.ATTACK_WEAPON, ActionType.PLAY_CARD, ActionType.PLAY_ARSENAL}:
        active_chain = state_view.get("activeChainLink") or {}
        return _safe_bool(active_chain.get("goAgain"))
    return False


def _classify_hand_action(
    *,
    card: Optional[Card],
    step: Step,
    phase_code: str,
    mode: int,
    raw_action: dict[str, Any],
) -> ActionType:
    if phase_code == "ARS" or mode == 4:
        return ActionType.STORE_ARSENAL

    if step == Step.COMBAT_DEFEND:
        if card is not None and card.is_equipment:
            return ActionType.DEFEND_EQUIPMENT
        return ActionType.DEFEND_CARDS

    if step == Step.COMBAT_REACTION:
        if card is not None and "Defense Reaction" in (card.types or []):
            return ActionType.PLAY_DEFENSE_REACTION
        return ActionType.PLAY_ATTACK_REACTION

    if card is not None and card.is_defense_reaction:
        return ActionType.PLAY_DEFENSE_REACTION

    return ActionType.PLAY_CARD


def _classify_equipment_action(card: Optional[Card], step: Step) -> ActionType:
    if step == Step.COMBAT_DEFEND:
        return ActionType.DEFEND_EQUIPMENT

    if card is not None and card.is_weapon:
        text = (card.functional_text or "").lower()
        if "attack" in text:
            return ActionType.ATTACK_WEAPON
        return ActionType.ACTIVATE_WEAPON

    return ActionType.ACTIVATE_EQUIPMENT


def talishar_phase_to_step(state_view: dict[str, Any]) -> Step:
    """Best-effort mapping from Talishar phase codes to engine Step.

    Talishar exposes player-facing phase codes, not a full authoritative engine step.
    This adapter produces an observed GameState for agent consumption/debugging.
    """
    turn_phase = state_view.get("turnPhase") or {}
    code = _safe_str(turn_phase.get("turnPhase")).upper()
    layer_code = _safe_str(turn_phase.get("layer")).upper()
    tracker = state_view.get("tracker") or {}
    tracker_position = _safe_str(tracker.get("position")).lower()

    if code == "OVER":
        return Step.END_GAME

    # P2-1: Detect begin_game — Talishar uses CHOOSEFIRSTPLAYER phase for game setup
    if code == "CHOOSEFIRSTPLAYER":
        return Step.BEGIN_GAME

    # Tracker-based resolution (most reliable when present)
    if tracker_position == "defense":
        return Step.COMBAT_DEFEND
    if tracker_position == "reactions":
        return Step.COMBAT_REACTION
    if tracker_position == "damage":
        return Step.COMBAT_DAMAGE
    if tracker_position == "resolution":
        return Step.COMBAT_RESOLUTION
    if tracker_position == "close":
        return Step.COMBAT_CLOSE
    if tracker_position == "endturn":
        # P2-1: Distinguish END_TURN from END_PHASE_BEGINNING using layer code
        if layer_code == "ENDTURN":
            return Step.END_TURN
        return Step.END_PHASE_BEGINNING
    if tracker_position == "cleanup":
        return Step.END_PHASE_CLEANUP
    if tracker_position == "start":
        return Step.START_PHASE
    # P2-1: Tracker "combat" — distinguish COMBAT_ATTACK vs COMBAT_LAYER via layer code
    if tracker_position == "combat":
        if layer_code == "ATTACKSTEP":
            return Step.COMBAT_ATTACK
        return Step.COMBAT_LAYER

    # Phase-code fallbacks
    if code == "ARS":
        return Step.END_PHASE_BEGINNING
    if code == "B":
        return Step.COMBAT_DEFEND
    if code in {"A", "D"}:
        return Step.COMBAT_REACTION

    if code in {"BUTTONINPUT", "MAYCHOOSEHAND", "MAYCHOOSEMULTIZONE", "INSTANT"}:
        active_chain = state_view.get("activeChainLink") or {}
        if isinstance(active_chain, dict) and active_chain.get("attackingCard"):
            return Step.COMBAT_REACTION

    if code in {"M", "P", "PDECK", "INSTANT", "BUTTONINPUT", "MAYCHOOSEHAND", "MAYCHOOSEMULTIZONE"}:
        return Step.ACTION

    return Step.ACTION


def extract_talishar_actions(state_view: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract Talishar-native legal actions from a seat view."""
    actions: list[dict[str, Any]] = []

    phase_code = _safe_str((state_view.get("turnPhase") or {}).get("turnPhase")).upper()

    for card in state_view.get("playerHand", []):
        if isinstance(card, dict) and card.get("action") is not None:
            mode = card.get("action")
            if mode != 0:
                actions.append(
                    {
                        "type": "hand",
                        "mode": mode,
                        "cardID": str(card.get("actionDataOverride", "0")),
                        "cardNumber": card.get("cardNumber", ""),
                        "controller": card.get("controller"),
                        "restriction": card.get("restriction", ""),
                        "label": card.get("label", ""),
                        "borderColor": card.get("borderColor"),
                        "zone": "hand",
                        "phaseCode": phase_code,
                    }
                )

    for eq in state_view.get("playerEquipment", []):
        if isinstance(eq, dict):
            for act in eq.get("actions", []):
                if isinstance(act, dict):
                    actions.append(
                        {
                            "type": "equipment",
                            "mode": act.get("mode"),
                            "cardID": str(act.get("cardID", "")),
                            "cardNumber": eq.get("cardNumber", ""),
                            "controller": eq.get("controller"),
                            "restriction": act.get("restriction", eq.get("restriction", "")),
                            "label": act.get("label", eq.get("label", "")),
                            "sType": eq.get("sType", ""),
                            "zone": "equipment",
                            "phaseCode": phase_code,
                        }
                    )

    pip = state_view.get("playerInputPopUp", {})
    if isinstance(pip, dict) and pip.get("active"):
        for btn in pip.get("buttons", []):
            if isinstance(btn, dict):
                actions.append(
                    {
                        "type": "button",
                        "mode": btn.get("mode", ""),
                        "buttonInput": str(btn.get("buttonInput", "")),
                        "cardID": str(btn.get("cardID", "")),
                        "caption": btn.get("caption", ""),
                        "tooltip": btn.get("tooltip", ""),
                        "prompt": btn.get("prompt", ""),
                        "phaseCode": phase_code,
                    }
                )

    prompt = state_view.get("playerPrompt", {})
    if isinstance(prompt, dict):
        for btn in prompt.get("buttons", []):
            if isinstance(btn, dict):
                actions.append(
                    {
                        "type": "prompt_button",
                        "mode": btn.get("mode", ""),
                        "buttonInput": str(btn.get("buttonInput", "")),
                        "cardID": str(btn.get("cardID", "")),
                        "caption": btn.get("caption", ""),
                        "tooltip": btn.get("tooltip", ""),
                        "prompt": btn.get("prompt", ""),
                        "phaseCode": phase_code,
                    }
                )

    if state_view.get("canPassPhase") and state_view.get("havePriority"):
        actions.append(
            {
                "type": "pass_phase",
                "mode": 99,
                "cardID": "",
                "phaseCode": phase_code,
            }
        )

    return actions


def talishar_card_to_card(
    card_view: dict[str, Any] | None,
    card_db: CardDB,
    *,
    owner_id: int,
    controller_id: Optional[int] = None,
    zone_name: str,
    is_public: Optional[bool] = None,
    allow_hidden_identity: bool = True,
) -> Optional[Card]:
    if not isinstance(card_view, dict):
        return None

    slug = card_view.get("cardNumber")
    if not slug or slug == "CardBack":
        return None

    visibility = _resolve_card_visibility(card_view, zone_name, is_public)
    if not visibility and not allow_hidden_identity:
        return None

    card = card_db.get(slug)
    if card is None:
        return None

    card = copy.copy(card)  # Avoid mutating shared CardDB instances (P1-6)
    card.owner = owner_id
    raw_controller = _safe_int(card_view.get("controller"), default=0)
    if raw_controller > 0:
        card.controller = raw_controller
    else:
        card.controller = owner_id if controller_id is None else controller_id
    card.zone = zone_name
    card.prev_zone = "unknown"  # Talishar snapshots lack zone-transition history
    card.is_public = visibility
    card.face_down = _talishar_face_down(card_view)
    card.tapped = _safe_bool(card_view.get("tapped", False))
    card.exhausted = _safe_bool(card_view.get("exhausted", card.tapped))
    card.counters = _extract_talishar_counters(card_view)

    talishar_object_id = _extract_talishar_object_id(card_view)
    if talishar_object_id is not None:
        card.object_id = talishar_object_id

    return card


def _extract_hero_from_equipment(
    equipment_list: list[dict[str, Any]],
    card_db: CardDB,
    owner_id: int,
) -> tuple[Card, dict[str, Any]]:
    for item in equipment_list:
        card = talishar_card_to_card(item, card_db, owner_id=owner_id, zone_name="hero", is_public=True)
        if card is not None and "Hero" in (card.types or []):
            return card, item
    raise ValueError(f"Could not determine hero for player {owner_id} from Talishar payload")


def _load_zone_cards(
    raw_cards: Any,
    card_db: CardDB,
    owner_id: int,
    zone_name: str,
    is_public: Optional[bool] = None,
    allow_hidden_identity: bool = True,
) -> list[Card]:
    cards: list[Card] = []
    if not isinstance(raw_cards, list):
        return cards
    for raw_card in raw_cards:
        card = talishar_card_to_card(
            raw_card,
            card_db,
            owner_id=owner_id,
            zone_name=zone_name,
            is_public=is_public,
            allow_hidden_identity=allow_hidden_identity,
        )
        if card is not None:
            cards.append(card)
    return cards


def _aggregate_player_counters(player: Player) -> None:
    """Reconstruct Player.counters from card-level counters across all zones."""
    for zone in player.all_zones():
        for card in zone.cards:
            for counter_type, count in card.counters.items():
                key = (card.slug, card.zone, counter_type)
                player.counters[key] = player.counters.get(key, 0) + count


def _attach_equipment(player: Player, equipment_list: list[dict[str, Any]], card_db: CardDB) -> None:
    for raw_card in equipment_list:
        card = talishar_card_to_card(raw_card, card_db, owner_id=player.player_id, zone_name="inventory", is_public=True)
        if card is None or "Hero" in (card.types or []):
            continue
        subtypes = set(card.subtypes or [])
        raw_slot = str(raw_card.get("sType") or "").strip()
        if raw_slot:
            subtypes.add(raw_slot)
        if card.is_weapon:
            zone = player.weapon1 if len(player.weapon1.cards) == 0 else player.weapon2
            zone.add(card, is_public=True)
        elif "Head" in subtypes:
            player.head.add(card, is_public=True)
        elif "Chest" in subtypes:
            player.chest.add(card, is_public=True)
        elif "Arms" in subtypes:
            player.arms.add(card, is_public=True)
        elif "Legs" in subtypes:
            player.legs.add(card, is_public=True)
        elif "Aura" in (card.types or []):
            player.auras.add(card, is_public=True)
        elif "Ally" in (card.types or []):
            player.allies.add(card, is_public=True)
        else:
            player.items.add(card, is_public=True)


def talishar_state_to_observed_game_state(
    state_view: dict[str, Any],
    *,
    player_id: int,
    card_db: CardDB,
    opponent_view: dict[str, Any] | None = None,
    prior_pitch_history: dict[int, dict[int, list[str]]] | None = None,
    prior_events: set[str] | None = None,
) -> GameState:
    """Convert a Talishar player-view observation into a partial engine GameState.

    This is intentionally an observed state, not a rules-authoritative reconstruction.
    Hidden information stays hidden, and combat stack metadata is only partially available.

    Args:
        prior_pitch_history: Cumulative pitch history from prior turns. Structure:
            {player_id: {turn_number: [slug, ...], ...}, ...}
            Pass this from the previous GameState.pitch_history to maintain continuity
            across Talishar snapshots (which only reflect the current turn's pitch zone).
        prior_events: Accumulated event types from earlier ticks this turn.
            Merged with current tick's events to give full turn timeline (P3-1).
    """
    hero, player_hero_view = _extract_hero_from_equipment(
        state_view.get("playerEquipment", []),
        card_db,
        player_id,
    )

    if opponent_view is not None:
        opp_equipment = opponent_view.get("playerEquipment", [])
    else:
        opp_equipment = state_view.get("opponentEquipment", [])
    opp_player_id = 3 - player_id
    opp_hero, opp_hero_view = _extract_hero_from_equipment(opp_equipment, card_db, opp_player_id)

    player = Player(player_id=player_id, hero_card=hero)
    opponent = Player(player_id=opp_player_id, hero_card=opp_hero)

    player.health = _safe_int(state_view.get("playerHealth"), default=player.health)
    opponent.health = _safe_int(state_view.get("opponentHealth"), default=opponent.health)
    player.action_points = _safe_int(state_view.get("playerAP"), default=player.action_points)
    opponent.action_points = _safe_int(state_view.get("opponentAP"), default=opponent.action_points)
    # Talishar sends resource pool as playerPitchCount (total pitch value generated)
    player.resources = _safe_int(
        state_view.get("playerPitchCount") or state_view.get("playerResources"), default=0
    )
    opponent.resources = _safe_int(
        state_view.get("opponentPitchCount") or state_view.get("opponentResources"), default=0
    )
    player.marked = _safe_bool(player_hero_view.get("marked", False))
    opponent.marked = _safe_bool(opp_hero_view.get("marked", False))

    player_hand_cards = _load_zone_cards(
        state_view.get("playerHand", []),
        card_db,
        player.player_id,
        "hand",
        is_public=False,
    )
    for card in player_hand_cards:
        player.hand.add(card, is_public=False)

    opponent_hand_cards = _load_zone_cards(
        state_view.get("opponentHand", []),
        card_db,
        opponent.player_id,
        "hand",
        is_public=False,
        allow_hidden_identity=False,
    )
    opponent_hand_count = len(state_view.get("opponentHand", []))
    for card in _fill_hidden_zone_cards(
        opponent_hand_cards,
        owner_id=opponent.player_id,
        zone_name="hand",
        total_count=opponent_hand_count,
    ):
        opponent.hand.add(card, is_public=False)

    player_deck_cards = _load_zone_cards(
        state_view.get("playerDeck", []),
        card_db,
        player.player_id,
        "deck",
        is_public=False,
        allow_hidden_identity=False,
    )
    player_deck_count = _safe_int(state_view.get("playerDeckCount"), default=len(player_deck_cards))
    for card in _fill_hidden_zone_cards(
        player_deck_cards,
        owner_id=player.player_id,
        zone_name="deck",
        total_count=player_deck_count,
    ):
        player.deck.add(card, is_public=False)

    opponent_deck_cards = _load_zone_cards(
        state_view.get("opponentDeck", []),
        card_db,
        opponent.player_id,
        "deck",
        is_public=False,
        allow_hidden_identity=False,
    )
    opponent_deck_count = _safe_int(state_view.get("opponentDeckCount"), default=len(opponent_deck_cards))
    for card in _fill_hidden_zone_cards(
        opponent_deck_cards,
        owner_id=opponent.player_id,
        zone_name="deck",
        total_count=opponent_deck_count,
    ):
        opponent.deck.add(card, is_public=False)

    for card in _load_zone_cards(state_view.get("playerArse", []), card_db, player.player_id, "arsenal"):
        player.arsenal.add(card, is_public=card.is_public)

    opponent_arsenal_known_cards = _load_zone_cards(
        state_view.get("opponentArse", []),
        card_db,
        opponent.player_id,
        "arsenal",
        allow_hidden_identity=False,
    )
    for card in _fill_hidden_zone_cards(
        opponent_arsenal_known_cards,
        owner_id=opponent.player_id,
        zone_name="arsenal",
        total_count=len(state_view.get("opponentArse", [])),
    ):
        opponent.arsenal.add(card, is_public=card.is_public)

    for card in _load_zone_cards(state_view.get("playerDiscard", []), card_db, player.player_id, "graveyard", is_public=True):
        player.graveyard.add(card, is_public=True)
    for card in _load_zone_cards(state_view.get("opponentDiscard", []), card_db, opponent.player_id, "graveyard", is_public=True):
        opponent.graveyard.add(card, is_public=True)

    for card in _load_zone_cards(state_view.get("playerPitch", []), card_db, player.player_id, "pitch", is_public=True):
        player.pitch.add(card, is_public=True)
    for card in _load_zone_cards(state_view.get("opponentPitch", []), card_db, opponent.player_id, "pitch", is_public=True):
        opponent.pitch.add(card, is_public=True)

    for card in _load_zone_cards(state_view.get("playerBanish", []), card_db, player.player_id, "banished", is_public=True):
        player.banished.add(card, is_public=True)
    for card in _load_zone_cards(state_view.get("opponentBanish", []), card_db, opponent.player_id, "banished", is_public=True):
        opponent.banished.add(card, is_public=True)

    for card in _load_zone_cards(state_view.get("playerSoul", []), card_db, player.player_id, "soul", is_public=True):
        player.soul.add(card, is_public=True)
    for card in _load_zone_cards(state_view.get("opponentSoul", []), card_db, opponent.player_id, "soul", is_public=True):
        opponent.soul.add(card, is_public=True)

    for card in _load_zone_cards(state_view.get("playerInventory", []), card_db, player.player_id, "inventory", is_public=False):
        player.inventory.add(card, is_public=False)

    player_auras = state_view.get("playerAuras", [])
    opponent_auras = state_view.get("opponentAuras", [])
    player_items = state_view.get("playerItems", [])
    opponent_items = state_view.get("opponentItems", [])
    player_allies = state_view.get("playerAllies", [])
    opponent_allies = state_view.get("opponentAllies", [])

    if not any((player_auras, player_items, player_allies)) and isinstance(state_view.get("playerPermanents"), list):
        player_items = state_view.get("playerPermanents", [])
    if not any((opponent_auras, opponent_items, opponent_allies)) and isinstance(state_view.get("opponentPermanents"), list):
        opponent_items = state_view.get("opponentPermanents", [])

    for card in _load_zone_cards(player_auras, card_db, player.player_id, "permanents", is_public=True):
        player.auras.add(card, is_public=True)
    for card in _load_zone_cards(opponent_auras, card_db, opponent.player_id, "permanents", is_public=True):
        opponent.auras.add(card, is_public=True)

    for card in _load_zone_cards(player_items, card_db, player.player_id, "permanents", is_public=True):
        if "Token" in (card.types or []) or "Token" in (card.subtypes or []):
            player.tokens.add(card, is_public=True)
        else:
            player.items.add(card, is_public=True)
    for card in _load_zone_cards(opponent_items, card_db, opponent.player_id, "permanents", is_public=True):
        if "Token" in (card.types or []) or "Token" in (card.subtypes or []):
            opponent.tokens.add(card, is_public=True)
        else:
            opponent.items.add(card, is_public=True)

    for card in _load_zone_cards(player_allies, card_db, player.player_id, "permanents", is_public=True):
        player.allies.add(card, is_public=True)
    for card in _load_zone_cards(opponent_allies, card_db, opponent.player_id, "permanents", is_public=True):
        opponent.allies.add(card, is_public=True)

    _attach_equipment(player, state_view.get("playerEquipment", []), card_db)
    _attach_equipment(opponent, opp_equipment, card_db)

    player.weapon_exhausted = any(card.exhausted for card in (player.weapon1.cards + player.weapon2.cards))
    opponent.weapon_exhausted = any(card.exhausted for card in (opponent.weapon1.cards + opponent.weapon2.cards))
    player.hero_power_exhausted = bool(player.hero_zone.cards and player.hero_zone.cards[0].exhausted)
    opponent.hero_power_exhausted = bool(opponent.hero_zone.cards and opponent.hero_zone.cards[0].exhausted)
    player.allies_exhausted = [card.exhausted for card in player.allies.cards]
    opponent.allies_exhausted = [card.exhausted for card in opponent.allies.cards]

    # Reconstruct Player.counters from card-level counters for embedder consumption
    _aggregate_player_counters(player)
    _aggregate_player_counters(opponent)

    player_effect_slugs = _extract_effect_slugs(state_view.get("playerEffects"))
    opponent_effect_slugs = _extract_effect_slugs(state_view.get("opponentEffects"))
    player.current_turn_effects = list(player_effect_slugs)
    opponent.current_turn_effects = list(opponent_effect_slugs)

    active_player = _safe_int(state_view.get("turnPlayer"), default=0)
    if active_player not in (1, 2):
        active_player = player_id if _safe_bool(state_view.get("amIActivePlayer")) else opp_player_id

    other_player = _safe_int(state_view.get("otherPlayer"), default=opp_player_id)
    if other_player not in (1, 2):
        other_player = opp_player_id

    have_priority = _safe_bool(state_view.get("havePriority"))
    priority_player = player_id if have_priority else other_player
    if priority_player not in (1, 2):
        priority_player = active_player

    step = talishar_phase_to_step(state_view)
    turn_number = _safe_int(state_view.get("turnNo"), default=0)

    raw_active_chain_link = state_view.get("activeChainLink")
    raw_chain_links = state_view.get("combatChainLinks")
    chain_links = _build_chain_links(
        raw_chain_links,
        raw_active_chain_link,
        fallback_attacker_id=active_player,
    )
    combat = _build_combat_state(
        raw_active_chain_link,
        card_db,
        fallback_attacker_id=active_player,
        chain_link_count=len(chain_links),
    )

    # Enrich combat state with fields the adapter previously left at defaults
    if combat is not None:
        # attack_target: the defending player (used by gamestate_embedder)
        defender_id = 3 - combat.attacker_id
        if defender_id in {player.player_id, opponent.player_id}:
            combat.attack_target = player if defender_id == player.player_id else opponent
        # no_defense_reactions: infer from Dominate keyword
        if any(k.lower() == "dominate" for k in (combat.keywords or [])):
            combat.no_defense_reactions = True
        # Annotate per-card combat flags so card_embedder can distinguish attackers/defenders
        if combat.attack_card is not None:
            combat.attack_card._is_attacking = True
        for _def_card in (combat.defending_cards or []):
            _def_card._is_defending = True

    stack_cards, stack_entries, stack_target = _build_stack_entries(
        state_view.get("layerDisplay"),
        card_db,
        fallback_player_id=priority_player,
    )

    # Merge prior cumulative pitch history with current turn's pitch zone (P1-5)
    pitch_history: dict[int, dict[int, list[str]]] = {1: {}, 2: {}}
    if prior_pitch_history:
        for pid in (1, 2):
            if pid in prior_pitch_history:
                pitch_history[pid] = dict(prior_pitch_history[pid])
    # Current turn's pitch zone overwrites this turn's entry (snapshot is authoritative for current turn)
    if player.pitch.cards:
        pitch_history[player.player_id][turn_number] = [card.slug for card in player.pitch.cards]
    if opponent.pitch.cards:
        pitch_history[opponent.player_id][turn_number] = [card.slug for card in opponent.pitch.cards]

    events_this_turn = _extract_event_types(state_view.get("newEvents"))
    if prior_events:
        events_this_turn = events_this_turn | prior_events
    landmarks = _extract_landmarks(state_view.get("landmarks"))

    phase_code = _safe_str((state_view.get("turnPhase") or {}).get("turnPhase")).upper()
    done = phase_code == "OVER" or player.health <= 0 or opponent.health <= 0

    winner = None
    if player.health <= 0 and opponent.health <= 0:
        winner = None
    elif opponent.health <= 0:
        winner = player.player_id
    elif player.health <= 0:
        winner = opponent.player_id
    elif phase_code == "OVER":
        if player.health > opponent.health:
            winner = player.player_id
        elif opponent.health > player.health:
            winner = opponent.player_id

    observed = GameState(
        players={player.player_id: player, opponent.player_id: opponent},
        active_player=active_player,
        player_agents={1: lambda *_: None, 2: lambda *_: None},
        step=step,
        turn_number=turn_number,
        combat=combat,
        done=done,
        winner=winner,
        card_db=card_db,
        priority_player=priority_player,
        consecutive_passes=_infer_consecutive_passes(
            has_priority=have_priority,
            has_stack_entries=bool(stack_entries),
            state_view=state_view,
        ),
        events_this_turn=events_this_turn,
        chain_links=chain_links,
        pitch_history=pitch_history,
        stack_entries=stack_entries,
        landmarks=landmarks,
        last_acted_player=(3 - priority_player) if priority_player in (1, 2) else None,
    )

    for card in stack_cards:
        observed.stack.add(card, is_public=True)
    if combat is not None and combat.attack_card is not None:
        observed.combat_chain.add(combat.attack_card, is_public=True)

    observed.talishar_raw_state = state_view
    observed.observed_player_id = player_id
    observed.observed_player_hand_count = len(player.hand.cards)
    observed.observed_opponent_hand_count = len(opponent.hand.cards)
    observed.observed_player_deck_count = len(player.deck.cards)
    observed.observed_opponent_deck_count = len(opponent.deck.cards)
    observed.talishar_phase_code = phase_code
    observed.talishar_turn_phase = state_view.get("turnPhase")
    observed.talishar_tracker = state_view.get("tracker")
    observed.talishar_layer_target = stack_target
    observed.talishar_player_effects = player_effect_slugs
    observed.talishar_opponent_effects = opponent_effect_slugs

    return observed


def talishar_actions_to_engine_actions(
    state_view: dict[str, Any],
    *,
    card_db: CardDB,
    player_id: int,
) -> list[Action]:
    """Convert Talishar-native legal actions into first-pass engine Action objects."""
    step = talishar_phase_to_step(state_view)
    phase_code = _safe_str((state_view.get("turnPhase") or {}).get("turnPhase")).upper()
    engine_actions: list[Action] = []

    priority_player = _infer_priority_player(state_view, player_id)
    chain_link_number = _infer_chain_link_number(state_view)
    phase = _phase_from_step(step)
    player_ap = _safe_int(state_view.get("playerAP"), default=0)
    resources_available = _safe_int(
        state_view.get("playerPitchCount") or state_view.get("playerResources"), default=0
    )
    current_prompt_text = _extract_prompt_text(state_view)

    for raw_action in extract_talishar_actions(state_view):
        raw_mode = _safe_int(raw_action.get("mode"), default=0)
        raw_type = _safe_str(raw_action.get("type"))

        if raw_action["type"] == "pass_phase":
            action_type = ActionType.REACTION_PASS if step == Step.COMBAT_REACTION else ActionType.PASS
            engine_actions.append(
                Action(
                    type=action_type,
                    player_id=player_id,
                    step=step,
                    phase=phase,
                    chain_link_number=chain_link_number,
                    priority_player=priority_player,
                    action_points_available=player_ap,
                    resources_available=resources_available,
                    action_cost=0,
                    resource_cost=0,
                    has_go_again=False,
                    is_instant_speed=action_type == ActionType.REACTION_PASS,
                    is_action_speed=False,
                    played_as_instant=False,
                    modes_selected=[],
                    x_value_declared=None,
                    is_melded=False,
                    alternative_cost_used=None,
                )
            )
            continue

        # Derive the source zone from action metadata instead of hardcoding "hand"
        if raw_action.get("type") == "equipment":
            source_zone = raw_action.get("zone", "equipment")
        elif phase_code == "ARS" or raw_mode == 4:
            source_zone = "arsenal"
        else:
            source_zone = raw_action.get("zone", "hand")

        card = talishar_card_to_card(
            {"cardNumber": raw_action.get("cardNumber")},
            card_db,
            owner_id=player_id,
            controller_id=player_id,
            zone_name=source_zone,
            is_public=True,
        )

        slot = _infer_slot(card, raw_action)
        from_arsenal = phase_code == "ARS" or raw_mode == 4
        target = None
        targets = None

        if _is_target_selection_phase(phase_code) and card is not None and raw_type == "hand":
            target = card
            targets = [card.slug]

        if raw_action["type"] == "equipment":
            action_type = _classify_equipment_action(card, step)
        elif raw_action["type"] in ("button", "prompt_button"):
            # P2-2: Classify button actions by Talishar mode instead of collapsing to PASS
            # Modes 99/101 = pass, 10000 = cancel, 10001 = undo, 100007 = leave, 105 = skip
            _PASS_MODES = {99, 101, 105, 10000, 10001, 100007}
            if raw_mode in _PASS_MODES:
                action_type = ActionType.REACTION_PASS if step == Step.COMBAT_REACTION else ActionType.PASS
            elif raw_mode == 4 and card is not None:
                # Mode 4 with a card = arsenal action
                action_type = ActionType.STORE_ARSENAL
            elif raw_mode == 17:
                # Mode 17 = BUTTONINPUT modal choice (choosing a game option)
                action_type = ActionType.PLAY_CARD if card is not None else ActionType.PASS
            elif raw_mode == 20:
                # Mode 20 = Yes/No decision
                action_type = ActionType.PLAY_CARD if card is not None else ActionType.PASS
            elif raw_mode in (7, 8, 9, 12, 13, 23, 29):
                # Mode 7 = choose first player, 8/12 = top, 9/13 = bottom, 23 = choose card, 29 = opp top
                action_type = ActionType.PLAY_CARD if card is not None else ActionType.PASS
            elif step == Step.COMBAT_REACTION:
                action_type = ActionType.REACTION_PASS
            else:
                action_type = ActionType.PASS
        else:
            action_type = _classify_hand_action(
                card=card,
                step=step,
                phase_code=phase_code,
                mode=raw_mode,
                raw_action=raw_action,
            )

        action_cost = _infer_action_cost(action_type=action_type, card=card, phase_code=phase_code)
        resource_cost = _infer_resource_cost(action_type=action_type, card=card)
        is_instant_speed, is_action_speed, played_as_instant = _infer_speed_flags(
            action_type=action_type,
            card=card,
            phase_code=phase_code,
        )
        has_go_again = _infer_has_go_again(action_type, card, state_view)

        defend_card_list = None
        if action_type in {ActionType.DEFEND_CARDS, ActionType.DEFEND_EQUIPMENT} and card is not None:
            defend_card_list = [card]

        pitch_cards: list[str] = []
        if phase_code in {"P", "PDECK"} and raw_type == "hand" and card is not None:
            pitch_cards = [card.slug]

        alternative_cost_used = _infer_alternative_cost(raw_action)
        x_value_declared = _infer_declared_x(state_view, raw_action)

        mapped_action = Action(
            type=action_type,
            player_id=player_id,
            card=card,
            card_idx=None,  # Talishar cardID is unstable; card identity comes from slug embedding
            pitch_cards=pitch_cards,
            from_arsenal=from_arsenal,
            slot=slot,
            card_list=defend_card_list,
            target=target,
            targets=targets,
            attack_source=card if action_type == ActionType.ATTACK_WEAPON else None,
            is_attack_proxy=action_type == ActionType.ATTACK_WEAPON,
            is_attack_layer=False,
            phase=phase,
            step=step,
            chain_link_number=chain_link_number,
            priority_player=priority_player,
            action_points_available=player_ap,
            resources_available=resources_available,
            action_cost=action_cost,
            resource_cost=resource_cost,
            has_go_again=has_go_again,
            is_instant_speed=is_instant_speed,
            is_action_speed=is_action_speed,
            played_as_instant=played_as_instant,
            modes_selected=[str(m) for m in (raw_action.get("modes") or raw_action.get("selectedModes") or []) if m],
            x_value_declared=x_value_declared,
            is_melded=bool(
                _safe_bool(raw_action.get("melded", False))
                or _safe_bool(raw_action.get("isMelded", False))
                # P2-3: Check structured sType field for meld indicator
                or _safe_str(raw_action.get("sType")).lower() == "meld"
                # Fallback: card has Meld keyword and is being played (not just passed)
                or (card is not None and "Meld" in (card.keywords or [])
                    and action_type not in (ActionType.PASS, ActionType.REACTION_PASS))
            ),
            alternative_cost_used=alternative_cost_used,
        )

        mapped_action.talishar_raw_action = raw_action
        mapped_action.talishar_prompt_text = current_prompt_text
        mapped_action.talishar_phase_code = phase_code
        engine_actions.append(mapped_action)

    return engine_actions
