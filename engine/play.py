"""Card playability checks and action application for the FAB game engine."""

import re
from typing import Optional

from engine.actions import Action, ActionType
from engine.card_effects.costs.activation_conditions import ADDITIONAL_CONDITIONS
from engine.card_effects.costs.mandatory_play_costs import ADDITIONAL_COSTS
from engine.card_effects.costs.effect_costs import KEYWORD_COSTS
from engine.card_effects.costs.alt_costs import ALTERNATE_COSTS
from engine.card import Card
from engine.state import GameState, Player, Event, StackEntry, Step

def available_actions(state, player_id) -> list[Action]:
    """ Finds all legal card activations/plays, builds an action list from those cards,
    then returns the list of the affordable and legal actions.
    Always returns at least PASS"""

    # First find all cards that are theoretically possible to be play/activated
    # Check for continuous effects that affect playability like gravy's watery grave check or bounding demigon's NAA requirement
    recalculate_playable(state, player_id)
    recalculate_activatable(state, player_id)

    player = state.players[player_id]
    playable_cards = [c for c in player.all_cards if c.playable]
    activatable_cards = [c for c in player.all_cards if c.activatable]

    # 2nd, filter down based on keyword type requirements
    legal_playable_cards = []
    legal_activatable_cards = []
    for card in playable_cards:
        if _legality_check(state, card, player_id):
            legal_playable_cards.append(card)
    for card in activatable_cards:
        if _legality_check(state, card, player_id):
            legal_activatable_cards.append(card)

    # 3rd, filter down based on what cards are actually affordable, and playable/activatable based on card specific conditions

    affordable_actions = []
    for card in legal_playable_cards:
        action = Action(ActionType.PLAY_CARD, player_id, card, from_arsenal=True if card.zone == 'arsenal' else None)
        can_play, action = _cost_check(state, card, player_id, action, playable=True)
        if can_play:
            affordable_actions.append(action)
    for card in activatable_cards:
        if not _legality_check(state, card, player_id):
            continue
        # Build a fresh Action per card (reusing the playable-loop action object
        # here previously produced wrong/unbound actions).
        action = Action(ActionType.ACTIVATE_CARD, player_id, card)
        can_activate, action = _cost_check(state, card, player_id, action, playable=False)
        if can_activate:
            affordable_actions.append(action)

    # Weapon attacks (CR 1.6.2b): offered from the weapon zones during the
    # turn player's action phase.
    _add_weapon_attacks(state, player_id, affordable_actions)

    # Hero activated/instant abilities defined in the DSL (e.g. Kayo's Instant).
    _add_hero_dsl_activations(state, player_id, affordable_actions)

    # "Instant - Discard this:" abilities usable from hand (e.g. Ripple Away).
    _add_hand_instant_activations(state, player_id, affordable_actions)

    affordable_actions.append(Action(ActionType.PASS)) #can always choose to pass

    return affordable_actions


def _add_weapon_attacks(state, player_id, affordable_actions) -> None:
    """Offer weapon attacks from the weapon zones (CR 1.6.2b).

    Legal when: it's this player's action phase with an empty stack, they have
    an action point, no weapon has attacked yet this turn (weapon_exhausted),
    and the weapon is untapped with a per-turn activation remaining. Cost is the
    weapon's activation cost (hero COST_MODIFIER deltas applied), payable from
    resources plus pitch.
    """
    from engine.actions import can_pay_cost
    player = state.players[player_id]
    if state.active_player != player_id:
        return
    if state.step != Step.ACTION or state.stack_entries:
        return
    if player.action_points <= 0 or getattr(player, 'weapon_exhausted', False):
        return

    seen: set[int] = set()
    for zone in (player.weapon1, player.weapon2):
        for wc in zone.cards:
            if id(wc) in seen:
                continue  # a 2H weapon occupies both zones as the same object
            seen.add(id(wc))
            # Attackable weapon: printed power and a parsed activation cost.
            if not (wc.is_weapon and wc.raw_power is not None
                    and wc.activation_cost is not None):
                continue
            if getattr(wc, 'tapped', False) or getattr(wc, 'exhausted', False):
                continue
            if wc.has_per_turn_limit and (wc.activations or 0) <= 0:
                continue
            action = Action(type=ActionType.ACTIVATE_CARD, player_id=player_id,
                            card=wc, attack_source=wc, is_attack_proxy=True)
            cost = _calculate_resource_cost(state, action)
            if can_pay_cost(player.hand.cards, cost, player.resources):
                affordable_actions.append(action)


def _add_hero_dsl_activations(state, player_id, affordable_actions) -> None:
    """Offer DSL activated abilities (ACTIVATE / INSTANT / ATTACK_REACTION) of
    the hero AND every arena permanent (equipment, weapons, items, auras,
    allies) as ACTIVATE_CARD actions.

    Timing per ability type:
      * INSTANT          — any priority window
      * ACTIVATE         — action phase, action point, empty stack
      * ATTACK_REACTION  — combat reaction step, with a legal attack to target
    An ability is offered only when its DSL costs, ability conditions (e.g. a
    "once per turn" NOT-FLAG_SET gate), per-turn activation limit, target
    filter, and resource affordability all pass. Abilities whose effect is an
    attack are offered via the weapon-attack path, not here.
    """
    from engine.card_effects.dsl.loader import get_card as _dsl_get_card
    player = state.players[player_id]

    in_action_phase = state.step == Step.ACTION and len(state.stack_entries) == 0
    in_reaction_step = state.step == Step.COMBAT_REACTION and state.combat is not None

    # Every source of activated abilities the player controls.
    sources = []
    if player.hero is not None:
        sources.append(player.hero)
    for zone in (player.head, player.chest, player.arms, player.legs,
                 player.weapon1, player.weapon2, player.items, player.auras,
                 player.allies, player.permanents):
        sources.extend(zone.cards)

    seen: set[int] = set()
    for card in sources:
        if id(card) in seen:
            continue  # a 2H weapon occupies both zones as the same object
        seen.add(id(card))
        cd = _dsl_get_card(card.slug)
        if cd is None:
            continue
        for ability in cd.abilities:
            atype = ability.ability_type.upper()
            if atype not in ("ACTIVATE", "INSTANT", "ATTACK_REACTION", "DEFENSE_REACTION"):
                continue
            # Attack activations are handled by _add_weapon_attacks (they must
            # create an attack-proxy on the chain, not dispatch ON_ACTIVATE).
            if any(getattr(e, 'effect_type', '').upper() in ("ATTACK", "ATTACKING")
                   for e in getattr(ability, 'effects', [])):
                continue
            if atype == "ACTIVATE" and not (in_action_phase and player.action_points > 0):
                continue
            if atype == "ATTACK_REACTION":
                # Only the attacker, in the reaction step (CR 8.1.2a).
                if not in_reaction_step or player_id != state.combat.attacker_id:
                    continue
            if atype == "DEFENSE_REACTION":
                # Only the defender (attack-target's controller), in the reaction
                # step, when defense reactions aren't prevented (CR 8.1.3a/7.4.2c).
                # An activated DR from equipment is not "from hand", so Dominate
                # (8.3.4b, hand-scoped) does not block it.
                if not in_reaction_step or player_id == state.combat.attacker_id:
                    continue
                if getattr(state.combat, 'no_defense_reactions', False):
                    continue
                _at = getattr(state.combat, 'attack_target', None)
                if (_at is not None and _at is not player
                        and _at is not getattr(player, 'hero', None)):
                    continue
            # CR 4.4.3d: per-turn activation limit (e.g. "Once per Turn Action").
            if getattr(card, 'has_per_turn_limit', False) and (getattr(card, 'activations', 0) or 0) <= 0:
                continue
            # Ability conditions (e.g. once-per-turn NOT FLAG_SET) must hold.
            if any(cond.fn is not None and not cond.fn(card, None, state)
                   for cond in getattr(ability, 'conditions', [])):
                continue
            # Ability's own DSL costs (TAP_SELF, remove counters, …) payable.
            if any(cost.check_fn is not None and not cost.check_fn(card, None, state)
                   for cost in getattr(ability, 'costs', [])):
                continue
            # Target filter (CR 1.8.5): only offer if a legal target exists.
            if any(cond.fn is not None and not cond.fn(card, None, state)
                   for cond in getattr(ability, 'target_filter', [])):
                continue
            # Determine the ability's legal target(s). An ability that targets
            # an "attack action card you control" (CONTROLS_ATTACK_ACTION)
            # enumerates those specific cards (the active attack you control
            # and/or attack action cards you're defending with) — one action
            # per legal target. Other combat abilities default to the active
            # attack; non-combat abilities have no target.
            _uses_caa = any(getattr(c, 'condition_type', '') == 'CONTROLS_ATTACK_ACTION'
                            for c in getattr(ability, 'target_filter', []))
            if _uses_caa:
                from engine.card_effects.ability_keywords import controlled_attack_action_cards
                _targets = controlled_attack_action_cards(state, player_id)
            elif state.combat is not None:
                _targets = [state.combat.attack_card]
            else:
                _targets = [None]
            # Resource affordability (activation_cost) via the shared cost gate.
            for _tgt in (_targets or [None]):
                action = Action(type=ActionType.ACTIVATE_CARD, player_id=player_id,
                                card=card, target=_tgt)
                can_activate, action = _cost_check(state, card, player_id, action, playable=False)
                if can_activate:
                    affordable_actions.append(action)

def _add_hand_instant_activations(state, player_id, affordable_actions) -> None:
    """Offer "Instant - Discard this:" abilities of cards in hand.

    These are INSTANT abilities whose cost is DISCARD_SELF (the card is discarded
    from hand as the activation cost). Instant speed, so no action point. Offered
    when the ability's conditions and target filter are satisfied.
    """
    from engine.card_effects.dsl.loader import get_card as _dsl_get_card
    player = state.players[player_id]
    for card in list(player.hand.cards):
        cd = _dsl_get_card(card.slug)
        if cd is None:
            continue
        for ability in cd.abilities:
            if ability.ability_type.upper() != "INSTANT":
                continue
            if not any(getattr(c, 'cost_type', '') == "DISCARD_SELF"
                       for c in getattr(ability, 'costs', [])):
                continue
            if any(cond.fn is not None and not cond.fn(card, None, state)
                   for cond in getattr(ability, 'conditions', [])):
                continue
            if any(cond.fn is not None and not cond.fn(card, None, state)
                   for cond in getattr(ability, 'target_filter', [])):
                continue
            action = Action(type=ActionType.DISCARD_ACTIVATE, player_id=player_id, card=card)
            affordable_actions.append(action)
            break  # one activation per card

def _legality_check(state, card, player_id) -> bool:
    if card is None:
        return True
    types = card.types or []

    # card.types (parsed from the printed type line) is authoritative. Do NOT
    # supplement with functional-text scans: rules text like "Target attack
    # action card…" and the substring 'action' inside 'reaction' produce false
    # type flags that make reactions illegal to play.
    _types_lower = {t.lower().replace(" ", "_") for t in types}
    is_ar  = "attackreaction" in _types_lower or "attack_reaction" in _types_lower
    is_dr  = "defensereaction" in _types_lower or "defense_reaction" in _types_lower
    is_act = "action" in _types_lower
    is_ins = "instant" in _types_lower

    legal_flag = True
    if is_act:
        legal_flag &= _action_legal_check(state, card, player_id)
    if is_ar:
        legal_flag &= _attack_reaction_legal_check(state, card, player_id)
    if is_dr:
        legal_flag &= _defense_reaction_legal_check(state, card, player_id)
    if is_ins:
        legal_flag &= _instant_legal_check(state, card, player_id)

    # CR 1.8.5 / 5.1.4: a targeted ability is only legal to play if a legal
    # target exists at announce. DSL `target.filter` conditions evaluate
    # against the current state (AR/DR filters read state.combat — e.g.
    # "Target attack with stealth" is unplayable against a non-stealth attack).
    if legal_flag:
        from engine.card_effects.dsl.loader import get_card as _dsl_get_card
        cd = _dsl_get_card(card.slug)
        if cd is not None:
            for ability in cd.abilities:
                if ability.ability_type.upper() not in (
                        "PLAY", "ACTION", "MODAL",
                        "ATTACK_REACTION", "DEFENSE_REACTION"):
                    continue
                if any(cond.fn is not None and not cond.fn(card, None, state)
                       for cond in getattr(ability, 'target_filter', None) or []):
                    return False

    return legal_flag

def _cost_check(state, card, player_id, action, playable) -> tuple[bool, Action]:
    """Unified cost gate for playing a card or activating an ability.

        Implements the full CR 5.1 cost sequence in one place so that the
        legality check (_legality_check) and the payment (_apply_action) always
        use identical logic.

        check=True  (CR 5.1.5 / 5.1.8a):
            Verify ALL costs are payable without changing any game state.
            Returns True if the action is affordable, False if it should be
            excluded from the legal-action list.

        check=False (CR 5.1.7 / 5.1.9):
            Deduct ALL costs from the game state.  Returns True unconditionally
            (caller is responsible for having called check=True first).

        Cost sequence per CR 5.1.6 / 1.14.2:
        1. Resource asset-cost
            • Base = card.cost (CR 2.2.2)
            • Alternative cost declared → base set to 0 (CR 5.1.6c)
            • Continuous-effect modifiers applied (CR 5.1.6a): set → increase → decrease, floor 0
            • Chi drains into resources before spending (CR 1.14.2d)
            • Pitch cards from hand to cover shortfall (CR 1.14.2d / 5.1.7)
        2. Action-point asset-cost
            • 0 for Instant-speed; 1 for action-speed (CR 5.1.6b)
            • Continuous-effect modifiers applied (CR 5.1.6a)
        3. Life asset-cost  (CR 1.14.2e)
            • Hero activations may carry a life cost registered in HERO_ACTIVATION_CONDITIONS
        4. Effect-costs  (CR 5.1.8–5.1.9)
            • Slug-registered in EFFECT_COSTS; keyword-driven (Scrap, Beat Chest)
            • check=True evaluates payability without paying
            • check=False pays them (irreversible side-effects happen here)
        """    # Turn card into action
    player = state.players[player_id]
    can_afford = True
    exclude = card if card is not None else None

    # CR 8.3.27 — rune gating plays the card from the banished zone WITHOUT
    # PAYING its {r} cost. The permission alone is not the keyword; a rune-gated
    # card that still had to be paid for would almost never be worth playing.
    if (playable and card is not None and getattr(card, 'zone', None) == 'banished'
            and rune_gate_available(state, player, card)):
        setattr(action, 'resource_cost', 0)
        setattr(action, 'rune_gated', True)
        return True, action

    x_in_cost = False  # True when the printed cost contains an X (e.g. '3X'); action carries the raw string
    cost_with_x = None
    if playable: # play cards are evaluated with the properties cost and special_cost
        if card.raw_cost is not None:
            resource_cost = _calculate_resource_cost(state, action)
        elif card.special_cost is not None:
            cost_with_x = card.special_cost
            # ie 'X3' cost on imposing visage means 'pay at least 3'. A bare 'X'
            # (Reel In) strips to the empty string, and int('') RAISES — the
            # card was unplayable-by-crash rather than free. A bare X has no
            # minimum, so it is 0.
            _min_text = str(cost_with_x).strip('Xx \t')
            min_cost = int(_min_text) if _min_text else 0
            if min_cost < 0:
                return False, action
            resource_cost = min_cost
            x_in_cost = True
        else:
            return False, action # cards without costs are not playable
    else:
        # Activated abilities: resource cost parsed from the ability text (CR 5.1.6b)
        resource_cost = card.activation_cost or 0

    
    effective_resources = player.resources

    # --- 1. Resource cost ---
    if not can_pay_resource_cost(player.hand.cards, resource_cost, effective_resources, exclude_card=exclude):
            
            # Alternative-cost effect-cost checks (CR 5.1.3c / 5.1.8)
            # Check alternate costs if resource cost can't be paid.
            if getattr(card, 'alternate_costs', None) is not None:
                 if ALTERNATE_COSTS.get(card.slug) is not None:
                    cost_fn = ALTERNATE_COSTS.get(card.slug)
                    if cost_fn and cost_fn(state, action, check=True):
                        can_afford &= True  
                        setattr(action, 'alternate_cost', True)
                        setattr(action, 'resource_cost', 0)
                    else:
                        can_afford &= False
            else:
                # Check DSL-defined alternative costs
                _dsl_alt_ok = False
                if card is not None:
                    from engine.card_effects.dsl.loader import get_card as _dsl_get_card
                    _dsl_cd = _dsl_get_card(card.slug)
                    if _dsl_cd:
                        for _ab in _dsl_cd.abilities:
                            for _ac in getattr(_ab, 'alternative_costs', []):
                                if _ac.check_fn is None or _ac.check_fn(card, None, state):
                                    setattr(action, 'use_dsl_alt_cost', True)
                                    setattr(action, 'resource_cost', 0)
                                    _dsl_alt_ok = True
                                    break
                            if _dsl_alt_ok:
                                break
                if not _dsl_alt_ok:
                    can_afford &= False
    else:
        can_afford &= True
        setattr(action, 'resource_cost', cost_with_x if x_in_cost else resource_cost)


    # --- 2. Life cost ---
    if hasattr(card, 'life_cost')and (card.life_cost or 0) > 0 and player.hero is not None:
        life_cost = card.life_cost
        setattr(action, 'life_cost', life_cost)
        if life_cost > 0 and player.health <= life_cost:
            can_afford &= False
        else:
            can_afford &= True

    # --- 3. effect-costs ---
    if getattr(card, 'mandatory_additional_costs', None) is not None:
        if card is not None:
            from engine.card_effects.costs.mandatory_play_costs import ADDITIONAL_COSTS
            if card.slug in ADDITIONAL_COSTS.keys():
                cost_func = ADDITIONAL_COSTS[card.slug]
                can_afford &= cost_func(state, player_id, check=True)
                setattr(action, 'additional_costs', True)

    # Check DSL-defined play cost and ability additional costs (mandatory; block play if unpayable)
    if card is not None:
        from engine.card_effects.dsl.loader import get_card as _dsl_get_card
        _dsl_cd = _dsl_get_card(card.slug)
        if _dsl_cd:
            if _dsl_cd.play_cost and _dsl_cd.play_cost.check_fn is not None:
                if not _dsl_cd.play_cost.check_fn(card, None, state):
                    can_afford &= False
            for _ab in _dsl_cd.abilities:
                for _ac in getattr(_ab, 'additional_costs', []):
                    if _ac.check_fn is not None and not _ac.check_fn(card, None, state):
                        can_afford &= False

    # --- 4. additional conditions ---
    if playable:
        add_cond = getattr(card, 'play_conditions', None) is not None
    else:
        add_cond = getattr(card, 'activation_conditions', None) is not None
    
    if add_cond:
        from engine.card_effects.costs.activation_conditions import ADDITIONAL_CONDITIONS
        cond_func = ADDITIONAL_CONDITIONS.get(card.slug)
        if cond_func is not None:
            can_afford &= cond_func(state, player_id, check=True)
            setattr(action, 'additional_conditions', True)
    
    return can_afford, action

def can_pay_resource_cost(hand_cards: list[Card], target_cost: int, current_resources: int = 0, exclude_card: Card | None = None) -> bool:
    """Return True if total pitchable value in hand can cover the cost.

    This is the fast-path check used during legal-action enumeration.  The actual
    pitch cards are chosen later at apply-time via sequential binary decisions.
    """
    if target_cost is None or target_cost <= 0:
        return True
    needed = target_cost - current_resources
    if needed <= 0:
        return True
    total_pitch = sum(
        (c.pitch or 0)
        for c in hand_cards
        if c is not exclude_card and c.pitch is not None and c.pitch > 0
    )
    return total_pitch >= needed

def _cost_mod_matches(state, mod, card) -> bool:
    """Does a queued one-shot cost reduction apply to this card?

    The filter holds raw DSL condition specs evaluated against the card being
    played, so "the next BLUE card", "the next Runeblade card" and "the next
    attack action" are all the same mechanism rather than one regex each.
    """
    from engine.card_effects.dsl.condition_types import compile_condition as _cc
    for spec in mod.get('filter', []) or []:
        fn = _cc(spec.get('type', 'none'), spec)
        if fn is not None and not fn(card, None, state):
            return False
    return True


def _apply_queued_defense_mods(state, card, player) -> None:
    """Consume a one-shot "the next card you defend with gets +/-N{d}".

    The attack queue is consumed by attacks and the play-time queue by cards
    being played; a card used to DEFEND passes through neither, so this text had
    no queue at all — "the next action card they defend with gets -1{d}" could
    only be written as a turn-long effect that weakens every block instead of
    one.

    Applied where the defending card's {d} is actually consumed, so the mod
    lands on the value that reaches total_defense.
    """
    queued = getattr(player, 'dsl_queued_defense_mods', None)
    if not queued:
        return
    from engine.card_effects.dsl.condition_types import compile_condition as _cc
    for mod in list(queued):
        ok = True
        for spec in mod.get('filter', []) or []:
            fn = _cc(spec.get('type', 'none'), spec)
            if fn is not None and not fn(card, None, state):
                ok = False
                break
        if not ok:
            continue
        queued.remove(mod)
        delta = int(mod.get('amount', 0) or 0)
        card.defense = max(0, (card.defense or 0) + delta)
        break


def _apply_dynamic_defense(state, card) -> None:
    """Recompute a card whose printed {d} is an expression, before it is read.

    "Grandstand Legplates' {d} is equal to the number of opposing heroes with
    greater {h} than you" — the value changes with the game state, so it cannot
    be a fixed number on the card. There is no defense-recalculation layer to
    hang this on (the continuous-effect manager documents prop='defense' but
    nothing ever recalculates it), so it is applied at the one point a defending
    card's {d} is actually consumed. Declared as
    {"ability_type":"STATIC","effects":[{"type":"DEFENSE_EQUALS","amount":...}]}.
    """
    slug = getattr(card, "slug", None)
    if not slug:
        return
    from engine.card_effects.dsl.loader import get_card
    card_def = get_card(slug)
    if card_def is None:
        return
    for ability in card_def.abilities:
        if (ability.ability_type or "").upper() != "STATIC":
            continue
        for eff in ability.effects:
            if (getattr(eff, "effect_type", "") or "").upper() != "DEFENSE_EQUALS":
                continue
            from engine.card_effects.dsl.effect_types import _resolve_amount
            try:
                value = int(_resolve_amount(eff.params.get("amount", 0), state, card))
            except (TypeError, ValueError):
                value = 0
            card.defense = card.base_defense = value
            return


def _record_reaction_on_link(state, player_id, kinds) -> None:
    """Record that a reaction was played or activated on THIS chain link.

    "the attacking hero has played or activated an attack reaction THIS CHAIN
    LINK" (Hunted or Hunter) is narrower than anything turn-scoped: a second
    attack in the same turn must not inherit the first link's reactions. A new
    CombatState is built per attack, so the list is link-scoped by construction.
    """
    combat = getattr(state, "combat", None)
    if combat is None or player_id is None:
        return
    for kind in kinds:
        combat.reactions_this_link.append((player_id, kind))


def _reaction_kinds(card=None, ability_type=None) -> list[str]:
    """Which reaction kinds a card (by type) or an ability (by ability_type) is."""
    names = set()
    if ability_type:
        names.add(str(ability_type).upper())
    for t in ((getattr(card, "types", None) or [])
              + (getattr(card, "subtypes", None) or [])) if card is not None else []:
        names.add(str(t).upper())
    flat = {"".join(ch for ch in n if ch.isalnum()) for n in names}
    out = []
    if "ATTACKREACTION" in flat:
        out.append("attack_reaction")
    if "DEFENSEREACTION" in flat:
        out.append("defense_reaction")
    return out


def _static_effect_types(card) -> set[str]:
    """Effect types declared by this card's STATIC abilities, from the CardDef.

    Read from the definition rather than a Card attribute so a declaration holds
    for any copy, including one that reached its zone before any ability of
    theirs ever ran.
    """
    slug = getattr(card, "slug", None)
    if not slug:
        return set()
    from engine.card_effects.dsl.loader import get_card
    card_def = get_card(slug)
    if card_def is None:
        return set()
    return {(getattr(eff, "effect_type", "") or "").upper()
            for ability in card_def.abilities
            if (ability.ability_type or "").upper() == "STATIC"
            for eff in ability.effects}


def _runechant_count(player) -> int:
    return sum(1 for c in player.permanents.cards
               if "runechant" in (getattr(c, "slug", "") or "").lower())


def rune_gate_available(state, player, card) -> bool:
    """CR 8.3.27 — may this card be rune gated from the banished zone right now?

    "If you control Runechants equal to or greater than this's {r} cost, you may
    play it from your banished zone WITHOUT PAYING its {r} cost." Both halves
    matter: the permission AND the free cost. 26 corpus cards carry the keyword.
    """
    if "RUNE_GATE" not in _static_effect_types(card):
        return False
    cost = getattr(card, "raw_cost", None)
    if cost is None:
        cost = getattr(card, "cost", None)
    try:
        cost = int(cost)
    except (TypeError, ValueError):
        return False
    return _runechant_count(player) >= cost


def _self_playable_from_banished(card, state=None, player=None) -> bool:
    """Does this card's own JSON say it may be played from the banished zone?

    Declared as {"ability_type":"STATIC","effects":[{"type":"PLAYABLE_FROM_BANISHED"}]},
    or as RUNE_GATE, whose permission is conditional on Runechants.
    """
    statics = _static_effect_types(card)
    if "PLAYABLE_FROM_BANISHED" in statics:
        return True
    if "RUNE_GATE" in statics and state is not None and player is not None:
        return rune_gate_available(state, player, card)
    return False


def recalculate_playable(state, player_id):
    player = state.players[player_id]
    mgr = state.continuous_effect_manager

    for card in player.hand.cards + player.arsenal.cards:
        # Block cards have no play cost (raw_cost is None) — they can only be used for blocking.
        if card.raw_cost is not None:
            card.playable = True

    # Cards granted temporary play-from-banished (e.g. trap_door's trap).
    # Identity comparison: the grant applies to that exact card object. The
    # grant may point at a card in ANOTHER player's banished zone — Infiltrate
    # banishes the top of the opponent's deck and lets YOU play it — so scan
    # every banished zone, not just this player's.
    _all_banished = list(player.banished.cards)
    for _other in state.players.values():
        if _other is not player:
            _all_banished += list(_other.banished.cards)
    _banish_playable = [c for c in _all_banished
                        if any(c is g for g in player.playable_from_banished)
                        and c.raw_cost is not None]
    # Cards that grant themselves the permission permanently ("You may play Rift
    # Bind from your banished zone"). Unlike a trap_door grant this is not a
    # timed effect on some OTHER card — the card carries it while it sits in the
    # zone, so there is no moment at which anything could push it onto
    # playable_from_banished. Declared as a STATIC PLAYABLE_FROM_BANISHED
    # effect, and only from the controller's OWN banished zone.
    _banish_playable += [c for c in player.banished.cards
                         if c.raw_cost is not None
                         and c not in _banish_playable
                         and _self_playable_from_banished(c, state, player)]
    for card in _banish_playable:
        card.playable = True

    _playable_pool = player.hand.cards + player.arsenal.cards + _banish_playable
    for card in player.all_cards:
        if card not in _playable_pool:
            card.playable = False
        mgr.recalculate(state, card, 'playable', card.playable)
    state.event_manager.emit('recalculate_playable', state)

def recalculate_activatable(state, player_id):
    player = state.players[player_id]
    mgr = state.continuous_effect_manager

    arena_cards = player.arena_cards
    for card in arena_cards:
        card.activatable = card.base_activatable

    for card in player.all_cards:
        if card not in arena_cards:
            card.activatable = False
        mgr.recalculate(state, card, 'activatable', card.activatable)
    state.event_manager.emit('recalculate_activatable', state)

def _action_legal_check(state, card, player_id) -> bool:
    # CR 8.1.1: Requirements for playing/activating a card with the "action" keyword
    step_val = state.step.value if hasattr(state.step, 'value') else str(state.step)

    # 8.1.1a: Stack must be empty
    if len(state.stack.slugs) > 0:
        return False

    # 8.1.1b: Actions can't be played/activated during combat (except resolution with play_as_instant)
    if 'combat' in step_val:
        if 'play_as_instant' not in state.effect_manager.continuous_effects:
            return False
        if not step_val.endswith('resolution'):
            return False
        # 7.6.3a: During resolution, only attacker may play attack actions
        if 'attack' in card.base_text_box or 'attack' in card.base_functional_text:
            if state.combat and player_id != state.combat.attacker_id:
                return False

    # 8.1.1c: Actions require one action-point
    if state.players[player_id].action_points < 1:
        return False

    return True

def _attack_reaction_legal_check(state, card, player_id) -> bool:
    # CR 8.1.2: Requirements for playing/activating a card with the "attack reaction" keyword
    can_play_or_activate = True
    # 8.1.2a An attack reaction card/activated ability can only be played/activated by a player who controls the attack during the Reaction Step of combat
    if not hasattr(state, 'combat') or state.combat is None:
        return False
    if state.step != Step.COMBAT_REACTION:
        can_play_or_activate = False
    if player_id != state.combat.attacker_id:
        can_play_or_activate = False
    
    # 8.1.2b: When an attack reaction card resolves as a layer on the stack, it is cleared.

    # 8.1.2c: An attack reaction card/activated ability is considered to be a reaction card/ability.

    return can_play_or_activate

def _defense_reaction_legal_check(state, card, player_id) -> bool:
    # CR 8.1.3: Requirements for playing/activating a card with the "defense reaction" keyword
    # 8.1.3a A defense reaction card/activated ability can only be played/activated by a player who controls a hero as an attack-target during the Reaction Step of combat.
    if not hasattr(state, 'combat') or state.combat is None:
        return False
    combat = state.combat
    if state.step != Step.COMBAT_REACTION:
        return False
    if player_id == combat.attacker_id:
        return False
    # attack_target is None when the attack targets the defending hero (the
    # default); otherwise it must be this player (or their hero) to allow DRs.
    # (Engine code stores the Player; some tests store the hero Card.)
    attack_target = getattr(combat, 'attack_target', None)
    defender = state.players[player_id]
    if (attack_target is not None and attack_target is not defender
            and attack_target is not getattr(defender, 'hero', None)):
        return False
    # CR 7.4.2c: an effect may prevent defense reactions this chain link.
    if getattr(combat, 'no_defense_reactions', False):
        return False
    # CR 8.3.4b: Dominate — once a hand card has defended, DRs can't be played from hand.
    if ("Dominate" in combat.keywords and combat.defender_used_hand_card
            and card in state.players[player_id].hand.cards):
        return False

    # 8.1.3b When a defense reaction card resolves as a layer on the stack, it becomes a defending card on the active chain link.
    # 8.1.3c A defense reaction card/activated ability is considered to be a reaction card/ability.
    return True

def _instant_legal_check(state, card, player_id) -> bool:
    # CR 8.1.6: Requirements for playing/activating a card with the "instant" keyword
    can_play_or_activate = True

    # 8.1.6a A card/activated ability with the type instant can be played/activated any time the player has priority.
    if state.priority_player != player_id:
        can_play_or_activate = False

    return can_play_or_activate

# Apply chosen actions to a Gamestate

def apply_action(state: GameState, action: Action) -> None:
    """Apply a player action to the game state."""
    # Sequential pitch: ask model which cards to pitch before dispatching
    _no_pitch_types = (ActionType.PASS, ActionType.DEFEND_CARDS,
                       ActionType.STORE_ARSENAL, ActionType.CHOOSE,
                       ActionType.DISCARD_ACTIVATE)
    if action.type not in _no_pitch_types:
        # CR 5.1.5: Verify legality BEFORE any cost payment (declare → check → pay).
        if not _legality_check(state, action.card, action.player_id):
            return
        # CR 5.1.6–5.1.9: Pay all costs (resource, chi, pitch, life, effect-costs).
        if not _pay_costs(state, action.player_id, action):
            return

    if action.type == ActionType.PLAY_CARD:
        _apply_play_card(state, action)
    elif action.type == ActionType.ACTIVATE_CARD:
        _apply_activate(state, action)
    elif action.type == ActionType.DEFEND_CARDS:
        _apply_defend(state, action)
    elif action.type == ActionType.DISCARD_ACTIVATE:
        _apply_discard_activate(state, action)
    elif action.type == ActionType.CHOOSE:
        pass  # Choice is conveyed by selection of this Action object; no state mutation needed

    # Observability: recorders see every successfully applied action.
    if getattr(state, 'recorders', None):
        from engine.recorder import notify as _rec_notify
        _rec_notify(state, 'on_action_applied', action)


def _apply_play_card(state: GameState, action: Action) -> None:
    """Play a card from hand: pitch for cost, place on stack."""
    player = state.players[action.player_id]
    card = action.card
    declared_modes, declared_targets, declared_x = _stack_declarations_from_action(action)

    # Meld-side-aware resource deduction.
    # Pitch sequences were already generated for the correct effective cost per side.
    _meld_side = getattr(action, 'meld_side', None)
    # Resource cost already deducted by evaluate_play_cost in apply_action.
    # Remove from the card's current zone (hand normally; arsenal or banished for
    # cards played from those zones, e.g. trap_door's "play from banished").
    _from_hand = (getattr(card, 'zone', None) or 'hand') == 'hand'
    # CR 1.3.1b: the controller of a card is the player who played it. Set it
    # here so conditions that read card.controller directly (e.g. "attack action
    # card you control") see the right player — including a card that goes on to
    # defend on a chain link.
    card.controller = action.player_id

    # Lightning Flow: "if you've played a Lightning card this turn".
    # ability_keywords.check_lightning_flow and every Lightning Flow card read
    # "played_lightning" out of current_turn_effects, but NOTHING ever wrote it,
    # so the whole mechanic was inert. This is the one place a card is played
    # from hand, so record it here.
    if any("lightning" in str(t).lower()
           for t in ((getattr(card, 'talents', None) or [])
                     + (getattr(card, 'types', None) or []))):
        if "played_lightning" not in player.current_turn_effects:
            player.current_turn_effects.append("played_lightning")

    # "if you've played a blue card / an attack action / a non-attack action this
    # turn". The Lightning case above is one hand-rolled instance of this pattern;
    # cards asked the same question about colours, types, classes and talents via
    # a dozen private flags nothing wrote. Record the play generically so those
    # ask through EVENT_THIS_TURN instead of each inventing a flag.
    from engine.effect_keywords import _record_turn_event
    # "Attack" is a SUBTYPE, not a type (an attack action is types=['Action'],
    # subtypes=['Attack']), so both lists are recorded and the attack/non-attack
    # split uses the card's own is_attack/is_action properties rather than
    # re-deriving it from types alone.
    _is_attack = bool(getattr(card, 'is_attack', False))
    _is_action = bool(getattr(card, 'is_action', False))
    _PLAY_COLOUR = {1: "red", 2: "yellow", 3: "blue"}
    _record_turn_event(
        state, action.player_id, "play",
        getattr(card, 'slug', None),
        # Name as well as slug: "if you've played a Nimblism this turn" names the
        # CARD, which spans every colour variant (nimblism_red/yellow/blue), so a
        # slug-only marker would miss two thirds of them.
        getattr(card, 'name', None),
        getattr(card, 'types', None) or [],
        getattr(card, 'subtypes', None) or [],
        getattr(card, 'classes', None) or [],
        getattr(card, 'talents', None) or [],
        getattr(card, 'color', None) or _PLAY_COLOUR.get(getattr(card, 'pitch', None)),
        # Derived compounds the card text names directly; "non-attack action"
        # is a real category in FAB and is not expressible as a single type.
        "attack_action" if (_is_attack and _is_action) else None,
        "non_attack_action" if (_is_action and not _is_attack) else None,
    )

    _record_reaction_on_link(state, action.player_id, _reaction_kinds(card=card))

    # CR 8.3.27a: a card played from the banished zone using rune gate is
    # considered RUNE GATED, and its controller to have rune gated. Both are
    # recorded — "the next attack action card you rune gate this turn gets
    # +3{p}" (Envelop in Darkness) asks about the CARD, other cards ask about
    # the player.
    if getattr(action, 'rune_gated', False):
        card.rune_gated = True
        from engine.effect_keywords import _record_turn_event as _rec_rg
        _rec_rg(state, action.player_id, "rune_gate",
                getattr(card, 'slug', None),
                getattr(card, 'types', None) or [],
                getattr(card, 'subtypes', None) or [])

    _src_zone = player.zone_by_name(getattr(card, 'zone', None) or 'hand')
    # Where it was played FROM, captured before the move. "If you play this from
    # your banished zone, ..." / "...from your arsenal" is a real and recurring
    # template, and by the time the play ability resolves the card has already
    # left, so asking "is it in the banished zone" then is always false.
    card.played_from_zone = (getattr(_src_zone, 'name', None)
                             if _src_zone is not None else 'hand') or 'hand'
    # X for a card with an X in its cost ("search for an aura with cost X or
    # less", "look at the top X+1 cards"). Costs are paid before this point, so
    # action.resource_cost is what the player actually chose to pay. The engine
    # has carried X costs since Imposing Visage, but the DSL had no way to READ
    # the paid amount, so every X card either hard-coded a number or invented an
    # amount that resolved to 0.
    if getattr(card, 'special_cost', None) is not None:
        card.x_paid = int(getattr(action, 'resource_cost', 0) or 0)
    if _src_zone is not None and card in _src_zone.cards:
        _src_zone.remove(card)
    else:
        player.hand.remove(card)
    player.playable_from_banished = [g for g in player.playable_from_banished
                                     if g is not card]

    # Pay DSL-defined play cost and any ability-level additional costs.
    from engine.card_effects.dsl.loader import get_card as _dsl_get_card
    _dsl_cd = _dsl_get_card(card.slug)
    if _dsl_cd:
        if _dsl_cd.play_cost and _dsl_cd.play_cost.pay_fn:
            _dsl_cd.play_cost.pay_fn(card, None, state)
        for _ab in _dsl_cd.abilities:
            for _ac in getattr(_ab, 'additional_costs', []):
                if _ac.pay_fn:
                    _ac.pay_fn(card, None, state)

    # Tag the card so on_play triggers know which side is resolving
    # (AP deduction is handled in _pay_costs — not here)
    card.meld_side = _meld_side

    # CR 3.0.1 / CR 5.3.4c: card enters stack zone (Zone.add keeps card.zone in sync)
    if card is not None:
        state.stack.add(card)

    # CR 5.1.2 / CR 3.15.4: card enters stack, on_play triggers sit above it (LIFO)
    entry = StackEntry(
        player_id=action.player_id,
        card=card,
        layer_type='card',
        layer_position=len(state.stack_entries) + 1,
        declared_modes=declared_modes,
        declared_targets=declared_targets,
        declared_x=declared_x,
    )
    if _meld_side == 'both':
        from engine.card_effects.triggers import MELD_EFFECT_REGISTRY
        _slug_base = re.sub(r'_(red|yellow|blue)$', '', card.slug)
        _meld_effs = MELD_EFFECT_REGISTRY.get(_slug_base, {})
        entry.meld_effect_bottom = _meld_effs.get('bottom')
        entry.meld_effect_top = _meld_effs.get('top')

    # CR 5.3.4: the card's resolution abilities generate their effects when the
    # card-layer RESOLVES on the stack (both players have passed priority) —
    # not at announce. Attacks are the exception: their resolution abilities
    # fire at the Attack Step (CR 7.2.3, dispatched by engine._attack_step).
    if not entry.is_attack:
        _play_event = Event(type='on_play', card=card.slug,
                            data={'card': card, 'meld_side': _meld_side,
                                  'target': action.target})

        def _resolve_card_layer(c, gs, _event=_play_event, _hand=_from_hand):
            from engine.card_effects.dsl import dispatch as _dsl_dispatch
            _dsl_dispatch(gs, "ON_PLAY", c.slug, card=c, event=_event)
            # CR 5.3.6b / 8.1.3b / 7.4.2d: a resolved defense reaction card
            # becomes a defending card on the active chain link.
            if c.is_defense_reaction and gs.combat is not None:
                from engine.effect_keywords import add_defend
                if _hand:
                    # CR 8.3.4b: track hand-card defense for Dominate/Reprise
                    # (the card left the hand at announce, so add_defend can't see it).
                    gs.combat.defender_used_hand_card = True
                    gs.combat.hand_defender_ids.add(c.object_id)
                # Leave the stack zone (add_defend can't resolve the shared
                # 'stack' zone); resolve_stack then sees it moved and does not
                # clear it to the graveyard.
                gs.stack.remove(c)
                add_defend(gs, c)

        entry.effect_fn = _resolve_card_layer

    state.stack_entries.append(entry)
    player.cards_played_this_turn.append(card)
    # "When a player plays a card" triggers fire at announce (CR 5.1.2a); the
    # card's own resolution abilities do NOT ride this event (see effect_fn).
    state.event_manager.emit(Event(type='on_play', card=card.slug, data={'card': card, 'meld_side': _meld_side, 'target': action.target}), state)

def _apply_activate(state: GameState, action: Action) -> None:
    """Activate an equipment/item/weapon/ally/hero/card ability: pay cost, exhaust, apply effect.

    All costs (AP, resources, exhaustion) are paid by _pay_costs() before this function is called.
    This function handles only effects: once-per-turn tracking, additional cost side-effects, and
    dispatching to the effect registry.

    Attack activations (is_attack_proxy=True) create an activated-layer StackEntry so the engine's
    stack resolution loop (_combat_phase_iter → _attack_step) can handle combat.
    """
    if action.player_id is None or action.card is None:
        return
    player = state.players[action.player_id]
    card = action.card

    # CR 1.6.2b / CR 11.0: weapon and ally attacks go onto the chain as activated-layer entries.
    # All costs already paid by _pay_costs(). Just create the StackEntry.
    if getattr(action, 'is_attack_proxy', False):
        declared_modes, declared_targets, declared_x = _stack_declarations_from_action(action)
        entry = StackEntry(
            player_id=action.player_id,
            card=card,
            layer_type='activated',
            layer_position=len(state.stack_entries) + 1,
            declared_modes=declared_modes,
            declared_targets=declared_targets,
            declared_x=declared_x,
        )
        # Carry cards pitched for this attack through to the CombatState.
        entry.pitched_for_attack = list(getattr(action, 'pitched_cards', None) or [])
        state.stack_entries.append(entry)
        return

    # CR 4.4.3d: Mark exhausted for "X per turn" abilities.
    if card.has_per_turn_limit:
        card.activations -= 1
        assert card.activations >= 0

    # DSL-authoritative activation: pay the ability's own costs (the clause
    # before the colon, e.g. "Destroy this", "Remove 3 energy counters") then run
    # the effect via the DSL. Resource/AP/exhaust costs are already paid by _pay_costs.
    from engine.card_effects.dsl.loader import require_card
    cd = require_card(card.slug)
    activatable = [a for a in cd.abilities
                   if a.ability_type.upper() in
                   ("ACTIVATE", "INSTANT", "ATTACK_REACTION", "DEFENSE_REACTION")]
    if len(activatable) > 1:
        # The Action does not yet carry which ability was chosen; paying every
        # ability's costs and firing them all would be wrong. Fail loudly.
        raise NotImplementedError(
            f"{card.slug} has {len(activatable)} activated abilities; "
            "per-ability activation is not supported yet")
    for ability in activatable:
        # Cost must be payable before the effect resolves (legality normally
        # guarantees this; guard defensively so an unaffordable activation no-ops).
        for cost in getattr(ability, 'costs', []):
            if cost.check_fn is not None and not cost.check_fn(card, None, state):
                return
        for cost in getattr(ability, 'costs', []):
            if cost.pay_fn is not None:
                cost.pay_fn(card, None, state)
    ability = activatable[0] if activatable else None
    # Carry the target declared at activation (CR 5.1.4) so effects that act on
    # a chosen target (e.g. Kayo's "target attack action card you control")
    # apply to it rather than re-resolving.
    _ev = Event(type='ON_ACTIVATE', card=card.slug, data={})
    _ev.target = getattr(action, 'target', None)
    if ability is not None and ability.ability_type.upper() in (
            "ATTACK_REACTION", "DEFENSE_REACTION"):
        # Reaction abilities act on the current combat now — run the specific
        # ability (target filter + conditions + effects) directly rather than
        # broadcasting ON_ACTIVATE (which maps to ACTIVATE/INSTANT only).
        from engine.card_effects.dsl.interpreter import run_ability
        # "played OR ACTIVATED an attack reaction" — this is the activated half.
        _record_reaction_on_link(state, action.player_id,
                                 _reaction_kinds(ability_type=ability.ability_type))
        run_ability(ability, card, _ev, state)
    else:
        from engine.card_effects.dsl import dispatch as _dsl_dispatch
        _dsl_dispatch(state, "ON_ACTIVATE", card.slug, card=card, event=_ev)

def _apply_discard_activate(state: GameState, action: Action) -> None:
    """Resolve an "Instant - Discard this:" hand ability: pay the DISCARD_SELF
    cost (discard the card from hand to the graveyard), then run the INSTANT
    ability's effects."""
    if action.player_id is None or action.card is None:
        return
    from engine.card_effects.dsl.loader import require_card
    from engine.card_effects.dsl.interpreter import run_ability
    card = action.card
    cd = require_card(card.slug)
    ability = next((a for a in cd.abilities
                    if a.ability_type.upper() == "INSTANT"
                    and any(getattr(c, 'cost_type', '') == "DISCARD_SELF"
                            for c in getattr(a, 'costs', []))), None)
    if ability is None:
        return
    _ev = Event(type='ON_ACTIVATE', card=card.slug, data={})
    _ev.target = getattr(action, 'target', None)
    # Pay the ability's own costs (DISCARD_SELF discards the card); run_ability
    # only pays additional_costs, so the discard is paid here.
    for cost in ability.costs:
        if cost.check_fn is not None and not cost.check_fn(card, _ev, state):
            return
    for cost in ability.costs:
        if cost.pay_fn is not None:
            cost.pay_fn(card, _ev, state)
    run_ability(ability, card, _ev, state)

def _apply_defend(state: GameState, action: Action) -> None:
    """7.3.2: apply defend declaration — move chosen cards to defending_cards."""
    combat = state.combat
    if not combat:
        return
    if action.type == ActionType.PASS:
        return
    defender = state.players[3 - combat.attacker_id]
    # CR 7.3.2d: all declared cards become defending as a single compound event.
    # Add them all first, then fire the 'defend' events — so "defends together
    # with …" triggers (e.g. Apex Bonebreaker) can see every co-defender.
    for card in action.card_list:
        if card in defender.hand.cards:
            defender.hand.remove(card)
            # CR 8.3.4b: track that a hand card has been used to defend (Dominate/Reprise)
            combat.defender_used_hand_card = True
            # Per-card hand origin for "defends together with another card from
            # hand" triggers (Right Behind You).
            combat.hand_defender_ids.add(card.object_id)
        # CR 1.3.1b / 7.0.5a: a defending card enters the combat chain (arena)
        # under its controller — the defender who declared it.
        card.controller = defender.player_id
        combat.defending_cards.append(card)
        _apply_dynamic_defense(state, card)
        _apply_queued_defense_mods(state, card, defender)
        defense_val = card.defense or 0
        combat.total_defense += defense_val
        if card.is_equipment:
            combat.defending_equipment_defense += defense_val
    for card in action.card_list:
        # 7.0.5a: defend event (carry the defending card object for DSL ON_DEFEND)
        state.event_manager.emit(Event(type='defend', card=card.slug, data={'card': card}), state)

def _stack_declarations_from_action(action: Action) -> tuple[list[str], list[str], Optional[int]]:
    """Extract mode/target/X declarations for stack-layer metadata."""
    declared_modes = [str(mode) for mode in (action.modes_selected or [])]

    declared_targets: list[str] = []
    if action.targets:
        declared_targets.extend([str(t) for t in action.targets if t is not None])
    if action.target is not None and not action.targets:
        if hasattr(action.target, 'slug'):
            declared_targets.append(action.target.slug)
        else:
            declared_targets.append(str(action.target))

    declared_x = action.x_value_declared
    return declared_modes, declared_targets, declared_x

def _calculate_resource_cost(state: GameState, action: Action) -> int:
    """CR 5.1.6: Calculate final resource cost after all modifiers.

    Order per CR 5.1.6a:
    1. Base cost (from card/ability definition)
    2. CR 5.1.6c: alternative cost replaces base resource cost with 0
    3. SET effects applied in timestamp order      (substage 2)
    4. INCREASE effects applied in timestamp order (substage 5)
    5. DECREASE effects applied in timestamp order (substage 6)
    Floored at 0.

    Delegates to ContinuousEffectManager.recalculate() with prop='cost'
    and action= context so condition_fn(card, action, state) works correctly.
    """
    card = action.card

    # CR 5.1.3c: at most one alternative cost may be declared per play — enforced by
    # the Optional[str] field (single value only).  Validate no list was smuggled in.
    alt = getattr(action, 'alternative_cost_declared', None)
    assert not isinstance(alt, (list, tuple)), \
        f"CR 5.1.3c: only one alternative cost allowed per action; got {alt!r}"

    # CR 5.1.6c: alternative cost sets base resource cost to 0
    if alt:
        base_cost = 0
    else:
        base_cost = _get_base_resource_cost(state, action)

    mgr = state.continuous_effect_manager
    cost = mgr.recalculate(state, card, 'cost', base_cost, action=action)

    # DSL cost-reduction flags from current_turn_effects (seismic_surge, heartened_cross_strap, etc.)
    player = state.players[action.player_id] if action.player_id is not None else None
    if player is not None:
        card_types = [t.lower() for t in (getattr(card, 'types', None) or [])]
        card_classes = [c.lower() for c in (getattr(card, 'classes', None) or [])]
        is_attack_action = 'attack' in card_types
        for key in player.current_turn_effects:
            m = re.match(r'^next_attack_action_cost_-(\d+)$', key)
            if m and is_attack_action:
                cost -= int(m.group(1))
                break
            m2 = re.match(r'^next_guardian_attack_action_cost_-(\d+)$', key)
            if m2 and is_attack_action and 'guardian' in card_classes:
                cost -= int(m2.group(1))
                break

        # "The NEXT BLUE card you play this turn costs {r} less" and friends.
        # The two regexes above are hand-written special cases for attack
        # actions and Guardian attack actions; any other wording had no way to
        # express itself. This is the same queued-one-shot shape
        # dsl_queued_attack_mods already uses for "your next attack", with the
        # match expressed as ordinary DSL conditions over the card being played.
        for mod in (getattr(player, 'dsl_queued_card_mods', None)
                    or getattr(player, 'dsl_queued_cost_mods', None) or []):
            if _cost_mod_matches(state, mod, card):
                cost -= int(mod.get('amount', 0) or 0)
                break

    # DSL conditional cost modifiers on the card itself (CR 5.1.6, e.g. Stains
    # of the Redback: "if the defending hero is marked, this costs {r} less").
    # Evaluated at play time so the reduction affects play legality, not an
    # after-the-fact effect.
    from engine.card_effects.dsl.loader import get_card as _dsl_get_card
    cd = _dsl_get_card(card.slug) if card is not None else None
    for cm in (getattr(cd, "cost_modifiers", None) or []):
        cond = cm.get("cond")
        if cond is None or (cond.fn is not None and cond.fn(card, None, state)):
            cost += cm.get("delta", 0)

    return max(0, cost)  # CR 5.1.6a: floor at 0

def _activation_is_action_speed(card) -> bool:
    """True if *card*'s activated ability is action-speed and therefore costs an
    action point (CR 5.1.6b). Per the DSL contract (DSL_REFERENCE §ability_type),
    `ACTIVATE` is action-speed ("action phase, action point") while `INSTANT` and
    the reaction types are instant-speed (0 AP). The DSL type is authoritative;
    fall back to the printed-text "**… Action**" marker only when no DSL def
    exists (activatable cards always have one under the DSL-only engine).

    Note: cards with multiple distinct activated abilities of differing speed
    are not yet supported (_apply_activate raises for them), so inspecting the
    single activatable ability is sufficient today.
    """
    if card is None:
        return False
    from engine.card_effects.dsl.loader import get_card
    cd = get_card(card.slug)
    if cd is not None:
        return any(
            a.ability_type.upper() == "ACTIVATE"
            for a in cd.abilities
            if a.ability_type.upper() in
            ("ACTIVATE", "INSTANT", "ATTACK_REACTION", "DEFENSE_REACTION")
        )
    text = getattr(card, 'functional_text', None) or ''
    return bool(re.search(r'\*\*(?:[\w ]+ per \w+ )?[Aa]ction\*\*', text))


def _get_base_resource_cost(state: GameState, action: Action) -> int:
    """Compute the base resource cost for an action before any modifiers.

    Renamed from _get_action_resource_cost — call _calculate_resource_cost
    for the full CR 5.1.6a modifier pipeline.
    """
    card = action.card
    if action.type == ActionType.PLAY_CARD:
        ms = getattr(action, 'meld_side', None)
        if ms == 'bottom':
            return card.cost or 0
        elif ms == 'both':
            return card.meld_cost or 0
        else:
            return card.cost or 0
    elif action.type == ActionType.ACTIVATE_CARD:
        if getattr(action, 'is_attack_proxy', False) and card is not None:
            if card.is_weapon:
                # Prefer the DB-parsed activation cost; the text parser returns 0
                # on cards whose functional_text is empty in this database.
                if card.activation_cost is not None:
                    base = card.activation_cost
                else:
                    from engine.actions import _weapon_cost
                    base = _weapon_cost(card)
                base += _hero_activation_cost_delta(state, action.player_id, card)
                return max(0, base)
            else:  # ally attack
                return _ally_attack_resource_cost(card)
        base = (card.activation_cost or 0) if card else 0
        if card is not None:
            base += _hero_activation_cost_delta(state, action.player_id, card)
        return max(0, base)

    return 0


def _hero_activation_cost_delta(state: GameState, player_id, card) -> int:
    """Sum of activation-cost deltas granted by the player's hero (DSL).

    A hero JSON may declare COST_MODIFIER abilities, e.g. orb_weaver's
    "Graphene Chelicerae cost you {r} less to activate":
        {"ability_type": "COST_MODIFIER", "applies_to": "graphene_chelicera",
         "activation_delta": -1}
    """
    if player_id is None:
        return 0
    hero = state.players[player_id].hero
    if hero is None:
        return 0
    from engine.card_effects.dsl.loader import get_card as _dsl_get_card
    cd = _dsl_get_card(hero.slug)
    if cd is None:
        return 0
    delta = 0
    for ability in cd.abilities:
        if ability.ability_type.upper() != "COST_MODIFIER":
            continue
        applies_to = ability.params.get("applies_to", "")
        if applies_to and applies_to != card.slug:
            continue
        delta += int(ability.params.get("activation_delta", 0))
    return delta

def _pitch_for_cost(state: GameState, action: Action, needed_cost: int,
                    for_chi: bool = False) -> None:
    """Present pitchable hand cards and let the model choose which to pitch.

    Each iteration presents all remaining pitchable cards as options.  The model
    picks one, it is pitched, and the loop repeats until the pool >= needed_cost.
    The card being played is excluded from pitch candidates.

    for_chi=False (default): pitching fills player.resources.  Any card can be pitched.
    for_chi=True: pitching fills player.chi.  Only cards with the name 'inner_chi'
        (i.e. cards that generate chi when pitched) are eligible.  Resources CANNOT
        be pitched for chi costs (CR 1.14.2a).
    """
    player = state.players[action.player_id]
    if needed_cost is None or needed_cost <= 0:
        return

    pool = player.chi if for_chi else player.resources
    if pool >= needed_cost:
        return

    # Exclude the card being played from pitch candidates (it's still in hand at this point)
    exclude = action.card if hasattr(action, "card") else None

    pitched_slugs: list[str] = []
    while (player.chi if for_chi else player.resources) < needed_cost:
        pitchable = get_pitchable_cards(player.hand.cards, exclude_card=exclude)
        if for_chi:
            pitchable = [c for c in pitchable
                         if "Chi" in (c.types or []) or "Chi" in (c.subtypes or [])]
        if not pitchable:
            break  # nothing left to pitch
        context = 'Pitch for chi?' if for_chi else 'Pitch?'
        options = [Action(type=ActionType.CHOOSE, card=c) for c in pitchable]
        choice = state.player_agents[action.player_id](state, options, context)
        if isinstance(choice, Action):
            choice.player_id = action.player_id
        card = choice.card
        if card is None:
            break
        player.hand.remove(card)
        player.pitch.add(card)
        pitched_slugs.append(card.slug)
        # Track the actual Card objects pitched for THIS action's cost, so a
        # weapon attack can later know what was "pitched to attack with this"
        # (CR — e.g. Savage Claw). Distinct from turn-wide pitch history.
        if not hasattr(action, 'pitched_cards') or action.pitched_cards is None:
            action.pitched_cards = []
        action.pitched_cards.append(card)
        pitch_val = card.base_pitch or card.pitch or 0
        if for_chi:
            player.chi += pitch_val
        elif getattr(card, 'pitch_gives_chi', False) and action.player_id is not None:
            # Cards like inner_chi can fill either pool — ask the player
            from engine.card_effects.ability_keywords import _ask_player as _apk
            chi_choice = _apk(state, action.player_id, ['chi', 'resources'],
                              context=f"Pitch {card.slug} for {pitch_val} chi or {pitch_val} resources?")
            if str(chi_choice) == 'chi':
                player.chi += pitch_val
            else:
                player.resources += pitch_val
        else:
            player.resources += pitch_val
        state.event_manager.emit(
            Event(type='card_pitched', data={'card': card, 'pitcher_id': action.player_id}), state)

    if pitched_slugs:
        state.record_pitch(action.player_id, pitched_slugs)
def get_pitchable_cards(hand_cards: list[Card], exclude_card: Card | None = None) -> list[Card]:
    """Return hand cards that can be pitched (pitch > 0), excluding *exclude_card*."""
    return [
        c for c in hand_cards
        if c is not exclude_card and c.pitch is not None and c.pitch > 0
    ]


def evaluate_play_cost(state: GameState, action: Action, check: bool) -> bool:
    """Check or pay the resource cost for an action (CR 5.1.6 / 1.14.2).

    check=True  — return True if the player can afford the action (no state change).
    check=False — pitch cards and deduct resources to pay the cost; return True.
    """
    from engine.actions import can_pay_cost
    if action.player_id is None:
        return True
    player = state.players[action.player_id]
    resource_cost = _calculate_resource_cost(state, action)
    if check:
        exclude = action.card if isinstance(getattr(action, 'card', None), Card) else None
        effective = player.resources + getattr(player, 'chi', 0)
        if effective >= resource_cost:
            return True
        return can_pay_cost(player.hand.cards, resource_cost, effective, exclude_card=exclude)
    else:
        _pitch_for_cost(state, action, resource_cost)
        action.resource_cost = resource_cost
        player.resources = max(0, player.resources - resource_cost)
        return True
def _ally_attack_resource_cost(ally_card) -> int:
    """Parse the resource cost of an ally's attack ability from functional text.
    Falls back to card.cost if set. Returns 0 if no cost found."""
    if ally_card.cost is not None:
        return int(ally_card.cost)
    text = ally_card.functional_text or ""
    # Match "Action - {r}{r}:" or "Once per Turn Action - {r}:" patterns
    match = re.search(r'\*\*(?:[\w\s]+ )?[Aa]ction\*\*\s*[-\u2014]\s*((?:\{[rR]\})*)', text)
    if match and match.group(1):
        return match.group(1).lower().count('{r}')
    return 0


def _pay_costs(state, player_id, action):
    if player_id is None:
        return
    player = state.players[player_id]
    resource_cost = _calculate_resource_cost(state, action)

    _pitch_for_cost(state, action, resource_cost)
    # Deduct final resource cost using the pre-calculated modified value
    action.resource_cost = resource_cost
    player.resources -= resource_cost

    # Consume one-shot DSL cost-reduction flags now that cost has been paid
    card = action.card
    card_types = [t.lower() for t in (getattr(card, 'types', None) or [])]
    card_classes = [c.lower() for c in (getattr(card, 'classes', None) or [])]
    is_attack_action = 'attack' in card_types
    for key in [k for k in player.current_turn_effects
                if re.match(r'^next_attack_action_cost_-\d+$', k)]:
        if is_attack_action:
            player.current_turn_effects.remove(key)
            break
    for key in [k for k in player.current_turn_effects
                if re.match(r'^next_guardian_attack_action_cost_-\d+$', k)]:
        if is_attack_action and 'guardian' in card_classes:
            player.current_turn_effects.remove(key)
            break
    # Consume the matching queued "next card you play" mod: apply whatever it
    # grants and run whatever the card said to do to the card that used it
    # ("...THAT card deals 1 more damage"). The target is not known until this
    # moment — it is whichever card consumed the mod — so the follow-up can only
    # be attached here.
    #
    # This queue exists because the ATTACK queue (dsl_queued_attack_mods) is
    # consumed in _apply_turn_attack_effects, which only runs for attacks. "The
    # next BLUE ACTION card you play this turn gets go again" names cards that
    # may never attack, so it could not be expressed there at all.
    _queued = getattr(player, 'dsl_queued_card_mods', None)
    if _queued is None:
        _queued = getattr(player, 'dsl_queued_cost_mods', None) or []
    for mod in list(_queued):
        if not _cost_mod_matches(state, mod, card):
            continue
        # Multi-use entries ("the next 3 Draconic cards") stay queued until
        # spent; only the last use removes the entry.
        remaining = int(mod.get('uses', 1) or 1) - 1
        if remaining > 0:
            mod['uses'] = remaining
        else:
            _queued.remove(mod)
        for kw in (mod.get('keywords') or ([mod['keyword']] if mod.get('keyword') else [])):
            existing = list(getattr(card, 'keywords', None) or [])
            if kw not in existing:
                card.keywords = existing + [kw]
        # "The next card you play this turn IS DRACONIC" — a class grant, which
        # is neither a keyword nor a number. Added rather than replaced: the
        # card keeps its own classes ("in addition to its other class types").
        for cls in (mod.get('grant_classes')
                    or ([mod['grant_class']] if mod.get('grant_class') else [])):
            have = list(getattr(card, 'classes', None) or [])
            if cls not in have:
                card.classes = have + [cls]
        from engine.card_effects.dsl.effect_types import compile_effect as _ce
        for spec in (mod.get('on_consume') or []):
            _ce((spec.get('type') or '').upper(),
                {k: v for k, v in spec.items() if k != 'type'})(card, None, state)
        break

    life_cost: int = 0
    if hasattr(action, "life_cost") and (action.life_cost or 0) > 0 and player.hero is not None:
        life_cost = action.life_cost
        player.health -= life_cost

    # CR 5.1.6b: the action asset-cost is 1 only when the card has the type
    # Action and is not played as an instant (0 otherwise). Instants, reactions,
    # and action cards played as instants cost 0 AP.
    _meld_side = getattr(action, 'meld_side', None)
    if action.type == ActionType.PLAY_CARD:
        _types = action.card.types or []
        if _meld_side in ('top', 'both'):
            player.action_points -= 1  # melded / top side is action-speed
        elif ("Action" in _types and "Instant" not in _types
              and not getattr(action, 'played_as_instant', False)):
            player.action_points -= 1
    elif action.type == ActionType.ACTIVATE_CARD:
        if getattr(action, 'is_attack_proxy', False):
            # Weapon and ally attacks always cost 1 AP (CR 1.6.2b, CR 11.0)
            player.action_points -= 1
        elif (not getattr(action, 'played_as_instant', False)
              and _activation_is_action_speed(action.card)):
            # CR 5.1.6b: an *action*-speed activated ability (DSL ACTIVATE) costs
            # 1 AP; instant-speed activated abilities (DSL INSTANT) and reactions
            # cost 0. The DSL ability_type is authoritative — the printed
            # functional_text is absent for many cards (e.g. Scabskin Leathers).
            player.action_points -= 1

    # CR 1.6.2b / CR 11.0: exhaust weapon or ally as part of the attack activation cost
    if action.type == ActionType.ACTIVATE_CARD and getattr(action, 'is_attack_proxy', False):
        card = action.card
        if card is not None and card.is_weapon:
            player.weapon_exhausted = True
            # "Once per Turn Action — Attack" weapons consume their per-turn use
            # (the attack-proxy path returns before _apply_activate's decrement).
            if card.has_per_turn_limit and card.activations:
                card.activations -= 1
        else:
            idx = getattr(action, 'choose_index', None)
            if idx is not None and idx < len(player.allies_exhausted):
                player.allies_exhausted[idx] = True

    _pay_effect_costs(state, action)
    return True

def _pay_effect_costs(state: GameState, action: Action) -> bool:
    """CR 5.1.8-5.1.9: Calculate and pay effect-costs before the card enters the stack.

    Returns True if all effect-costs were paid successfully (or there were none).
    Returns False if a mandatory effect-cost could not be paid (action cancelled).
    """
    card = action.card
    if card is None:
        return True
    # Slug-registered effect costs take priority
    cost_fn = ALTERNATE_COSTS.get(card.slug)
    if cost_fn is not None:
        cost_fn(state, action.player_id, action, check=False)
    # Keyword-based effect costs: Scrap and Beat Chest are additional costs on the card
    player_id = action.player_id
    if player_id is None:
        return True
    for keyword, fn in KEYWORD_COSTS.items():
        if keyword in (card.keywords or []) and hasattr(action, 'additional_costs') and keyword in action.additional_costs_declared:
            fn(state, player_id, action, check=False)
    return True

