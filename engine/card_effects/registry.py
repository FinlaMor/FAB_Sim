"""Card effect registry for FAB self-play engine (OO rewrite).

Talishar reference: CardDictionaries/PlayAbilities.php, CardDictionaries/HitEffects.php,
GameLogic.php (AddCurrentTurnEffect, CheckCurrentTurnEffect).

Design: each card slug maps to a callable in one of the registries.
Effect functions receive (state, player_id, card_db) and mutate state in place.
"""

# At the top of actions.py or in a separate file
# Non-resource activation conditions (resource checks are handled by pitch sequence finder)
EQUIPMENT_ACTIVATION_CONDITIONS = {
    "fyendals_spring_tunic": lambda player, slot_name, equip_card: player.counters.get((equip_card.slug, 'chest', 'energy'), 0) >= 3,
    "skullbone_crosswrap": lambda player, slot_name, equip_card: player.arsenal_face_up == False,
    # Hammerhead: requires not tapped (tap is cost)
    "hammerhead_harpoon_cannon": lambda player, slot_name, equip_card: not equip_card.tapped,
    # Volzar: once per turn
    "volzar_the_lightning_rod": lambda player, slot_name, equip_card: (
        "volzar_used" not in player.current_turn_effects
    ),
    # Gold-Baited Hook: requires not tapped (tap is cost)
    "goldbaited_hook": lambda player, slot_name, equip_card: not equip_card.tapped,
    # Quiver: no extra condition (destroy is cost, resources handled by pitch finder)
    "quiver_of_abyssal_depths": lambda player, slot_name, equip_card: True,
    # Sealace Sarong: requires not tapped + blue arrow in arsenal
    "sealace_sarong": lambda player, slot_name, equip_card: (
        not equip_card.tapped
        and player.arsenal.top is not None
        and "Arrow" in player.arsenal.top.types
        and player.arsenal.top.pitch == 3
    ),
    # Aether Bindings: no extra condition (destroy is cost)
    "aether_bindings_of_the_third_age": lambda player, slot_name, equip_card: True,
    # Lightning Greaves: no extra condition (destroy + {r} are cost, resources handled by pitch finder)
    "lightning_greaves": lambda player, slot_name, equip_card: True,
    # Old Knocker: requires hero not tapped (tap hero is cost)
    "old_knocker": lambda player, slot_name, equip_card: not player.hero.tapped,
}

# Override activation costs for equipment whose cost is in functional text, not the cost field.
# Used by actions.py pitch sequence finder instead of equip_card.cost.
# Values can be int (static) or callable(player) -> int (dynamic).
def _volzar_activation_cost(player):
    """Volzar costs {r}, but {r} less if you control an aura with Sigil in its name."""
    has_sigil = any("sigil" in c.name.lower() for c in player.auras.cards)
    return 0 if has_sigil else 1

EQUIPMENT_ACTIVATION_COST = {
    "hammerhead_harpoon_cannon": 4,       # {r}{r}{r}{r}
    "quiver_of_abyssal_depths": 3,        # {r}{r}{r}
    "lightning_greaves": 1,                # {r}
    "volzar_the_lightning_rod": _volzar_activation_cost,  # {r} or 0
}

def _kayo_find_targets(player, state):
    """Find attack action cards controlled by this player in the arena or on the stack."""
    targets = []
    # Cards on the combat chain (attacking or defending)
    if state.combat:
        if state.combat.attack_card and state.combat.attack_card.controller == player.player_id:
            ac = state.combat.attack_card
            if "Attack" in (ac.types or "") and "Action" in (ac.types or ""):
                targets.append(ac)
        for dc in (state.combat.defending_cards or []):
            if dc.controller == player.player_id and "Attack" in (dc.types or "") and "Action" in (dc.types or ""):
                targets.append(dc)
    # Cards on the stack
    for entry in (state.stack_entries or []):
        c = entry.card
        if c and c.controller == player.player_id and "Attack" in (c.types or "") and "Action" in (c.types or ""):
            if c not in targets:
                targets.append(c)
    return targets

def _kayo_set_6_base_power(action, player, state):
    """Set target attack action card's base power to 6."""
    if action.target:
        action.target.base_power = 6
        action.target.effects = [
            (t, fn) for t, fn in getattr(action.target, 'effects', [])
            if t != "base_power"
        ]

def _marlynn_create_harpoon(action, player, state):
    """Marlynn hero ability effect: Create Goldfin Harpoon in hand. Go again.
    Cost (Gold destruction + tap) is paid before this resolves."""
    from engine.card_effects.keywords import create_token_card
    harpoon = create_token_card("goldfin_harpoon_yellow", player.player_id)
    player.hand.add(harpoon)
    player.action_points += 1


def _marlynn_pay_cost(player, state):
    """Pay Marlynn's hero ability cost: destroy a Gold you control ({t} handled by engine requires_tap)."""
    # Destroy a Gold token from items zone
    golds = [c for c in player.items.cards if "Gold" in c.types and "Token" in c.types]
    if not golds:
        return False
    from engine.card_effects.keywords import _ask_player
    if len(golds) == 1:
        gold = golds[0]
    else:
        pick = _ask_player(state, player.player_id, [g.slug for g in golds],
                           context="Choose a Gold token to destroy for Marlynn's ability")
        gold = next((g for g in golds if g.slug == pick), golds[0])
    player.items.remove(gold)
    player.graveyard.add(gold)
    return True


def _oscilio_discard_instant_draw(action, player, state):
    """Oscilio hero ability effect: draw a card.
    Cost (discard instant) is paid before this resolves."""
    from engine.card_effects.keywords import effect_draw
    effect_draw(state, player.player_id, 1)
    player.current_turn_effects.append("oscilio_used")


def _oscilio_pay_cost(player, state):
    """Pay Oscilio's hero ability cost: discard an instant."""
    from engine.card_effects.keywords import _ask_player
    instants = [c for c in player.hand.cards if c.is_instant]
    if not instants:
        return False
    options = [c.slug for c in instants]
    pick = _ask_player(state, player.player_id, options,
                       context="Choose an Instant card to discard for Oscilio's ability")
    target = next((c for c in instants if c.slug == pick), instants[0])
    player.hand.remove(target)
    player.graveyard.add(target)
    return True


HERO_ACTIVATION_CONDITIONS = {
    "kayo_underhanded_cheat": {
        "timing": "instant",  # Instant speed
        "cost": 4,            # {r}{r}{r}{r}
        "requires_tap": True, # {t}
        "condition_fn": lambda player, state: not player.hero.tapped,
        "target_fn": _kayo_find_targets,
        "effect_fn": _kayo_set_6_base_power,
    },
    # Marlynn, Treasure Hunter:
    # Action - {t}, destroy a Gold you control: Create a Goldfin Harpoon in your hand. Go again
    "marlynn_treasure_hunter": {
        "timing": "action",
        "cost": 0,
        "requires_tap": True,
        "condition_fn": lambda player, state: (
            not player.hero.tapped
            and any("Gold" in c.types and "Token" in c.types for c in player.items.cards)
        ),
        "pay_cost_fn": _marlynn_pay_cost,
        "effect_fn": _marlynn_create_harpoon,
    },
    # Oscilio (young hero) — same ability as adult form
    # Once per Turn Instant - Discard an instant: Draw a card.
    "oscilio": {
        "timing": "instant",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            any(c.is_instant for c in player.hand.cards)
            and "oscilio_used" not in player.current_turn_effects
        ),
        "pay_cost_fn": _oscilio_pay_cost,
        "effect_fn": _oscilio_discard_instant_draw,
    },
    # Oscilio, Constella Intelligence:
    # Once per Turn Instant - Discard an instant: Draw a card.
    "oscilio_constella_intelligence": {
        "timing": "instant",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            any(c.is_instant for c in player.hand.cards)
            and "oscilio_used" not in player.current_turn_effects
        ),
        "pay_cost_fn": _oscilio_pay_cost,
        "effect_fn": _oscilio_discard_instant_draw,
    },
}

def _scabskin_roll_d6(action, player, state):
    """Once per turn Action - 0: Roll d6, gain AP equal to half rounded down."""
    import random as rng
    roll = rng.randint(1, 6)
    player.action_points += roll // 2

def _fst_spend_energy(action, player, state):
    """Instant - Spend 3 energy counters: gain 1 resource."""
    counter_key = (action.card.slug, 'chest', 'energy')
    energy = player.counters.get(counter_key, 0)
    if energy >= 3:
        player.counters[counter_key] = energy - 3
        player.resources += 1

# ---------------------------------------------------------------------------
# Equipment pay-cost functions — costs before the colon (destroy, tap, etc.)
# Called BEFORE the effect resolves. Signature: (action, player, state) -> None
# Note: resource costs & "once per turn" exhaustion handled by engine _apply_activate.
# Note: equipment tap/exhaustion for "Once per Turn" handled by engine.
# ---------------------------------------------------------------------------

def _hammerhead_pay_cost(action, player, state):
    """Cost: {r}{r}{r}{r}, {t} — resources handled by engine, tap weapon here."""
    action.card.tapped = True

def _goldbaited_hook_pay_cost(action, player, state):
    """Cost: {t}"""
    action.card.tapped = True

def _quiver_pay_cost(action, player, state):
    """Cost: {r}{r}{r}, destroy — resources handled by engine, destroy here."""
    player.weapon.remove(action.card)
    player.graveyard.add(action.card)

def _sealace_pay_cost(action, player, state):
    """Cost: {t}"""
    action.card.tapped = True

def _aether_bindings_pay_cost(action, player, state):
    """Cost: destroy this"""
    player.arms.remove(action.card)
    player.graveyard.add(action.card)

def _lightning_greaves_pay_cost(action, player, state):
    """Cost: {r}, destroy — resources handled by engine, destroy here."""
    player.legs.remove(action.card)
    player.graveyard.add(action.card)

def _old_knocker_pay_cost(action, player, state):
    """Cost: {t} hero, destroy this"""
    player.hero.tapped = True
    player.chest.remove(action.card)
    player.graveyard.add(action.card)

EQUIPMENT_PAY_COSTS = {
    "hammerhead_harpoon_cannon": _hammerhead_pay_cost,
    "goldbaited_hook": _goldbaited_hook_pay_cost,
    "quiver_of_abyssal_depths": _quiver_pay_cost,
    "sealace_sarong": _sealace_pay_cost,
    "aether_bindings_of_the_third_age": _aether_bindings_pay_cost,
    "lightning_greaves": _lightning_greaves_pay_cost,
    "old_knocker": _old_knocker_pay_cost,
}

# ---------------------------------------------------------------------------
# Equipment activation effects — what happens AFTER costs are paid (after the colon)
# ---------------------------------------------------------------------------

def _hammerhead_effect(action, player, state):
    """Effect: next arrow attack +4{p}, harpoon gets overpower. Go again."""
    player.current_turn_effects.append("hammerhead_next_arrow_+4")
    player.current_turn_effects.append("activated_cannon")
    player.action_points += 1

def _volzar_effect(action, player, state):
    """Effect: Amp X where X = number of Lightning cards played this turn."""
    from engine.card_effects.keywords import effect_amp
    lightning_count = player.current_turn_effects.count("played_lightning")
    if lightning_count > 0:
        effect_amp(state, player.player_id, lightning_count)
    player.current_turn_effects.append("volzar_used")

def _goldbaited_hook_effect(action, player, state):
    """Effect: next Pirate attack gets on-hit steal/create Gold. Go again."""
    player.current_turn_effects.append("goldbaited_hook_next_pirate_hit_gold")
    player.current_turn_effects.append("goldbaited_hook_activated_this_turn")
    player.action_points += 1

def _quiver_effect(action, player, state):
    """Effect: shuffle up to 3 arrows with different names from graveyard into deck."""
    from engine.card_effects.keywords import _ask_player, effect_shuffle
    arrows = [c for c in player.graveyard.cards if "Arrow" in c.types]
    selected_names = set()
    for _ in range(3):
        available = [c for c in arrows if c.name not in selected_names and c in player.graveyard.cards]
        if not available:
            break
        options = [c.slug for c in available] + ["done"]
        pick = _ask_player(state, player.player_id, options,
                           context="Choose an Arrow to return to deck (Quiver of Abyssal Depths)")
        if pick == "done":
            break
        target = next((c for c in available if c.slug == pick), None)
        if target:
            selected_names.add(target.name)
            player.graveyard.remove(target)
            player.deck.add_bottom(target)
    effect_shuffle(state, player.player_id)

def _sealace_effect(action, player, state):
    """Effect: turn blue arrow in arsenal face-up, it gets go again this turn."""
    card = player.arsenal.top
    if card and "Arrow" in card.types and card.pitch == 3:
        state.set_card_visibility(card, True)
        card.keywords = list(card.keywords or [])
        if "Go again" not in card.keywords:
            card.keywords.append("Go again")

def _aether_bindings_effect(action, player, state):
    """Effect: Until end of turn, whenever Sigil aura leaves arena, amp 1."""
    player.current_turn_effects.append("aether_bindings_sigil_amp")

def _lightning_greaves_effect(action, player, state):
    """Effect: Instant cards you play this turn get go again."""
    player.current_turn_effects.append("lightning_greaves_instants_go_again")

def _old_knocker_effect(action, player, state):
    """Effect: Gain {r}."""
    player.resources += 1

EQUIPMENT_ACTIVATION_EFFECTS = {
    "scabskin_leathers": _scabskin_roll_d6,
    "fyendals_spring_tunic": _fst_spend_energy,
    "hammerhead_harpoon_cannon": _hammerhead_effect,
    "volzar_the_lightning_rod": _volzar_effect,
    "goldbaited_hook": _goldbaited_hook_effect,
    "quiver_of_abyssal_depths": _quiver_effect,
    "sealace_sarong": _sealace_effect,
    "aether_bindings_of_the_third_age": _aether_bindings_effect,
    "lightning_greaves": _lightning_greaves_effect,
    "old_knocker": _old_knocker_effect,
}

# ---------------------------------------------------------------------------
# Turn attack effects — consumed when the next attack is declared
# Each entry: effect_key -> { "condition_fn": (attack_card, player, state) -> bool,
#                              "apply_fn": (attack_card, player, state) -> None }
# condition_fn is optional (defaults to always apply).
# ---------------------------------------------------------------------------

def _next_attack_6_base_power_apply(attack_card, player, state):
    attack_card.base_power = 6
    attack_card.effects = [
        (t, fn) for t, fn in getattr(attack_card, 'effects', [])
        if t != "base_power"
    ]

def _nimblism_next_attack_plus1_apply(attack_card, player, state):
    attack_card.effects.append(("base_power", lambda base: base + 1))

def _hammerhead_next_arrow_apply(attack_card, player, state):
    """Hammerhead: next arrow attack +4{p}, harpoon gets overpower."""
    if "Arrow" not in attack_card.types:
        return  # Only applies to arrow attacks
    attack_card.effects.append(("base_power", lambda base: base + 4))
    if "harpoon" in attack_card.name.lower():
        attack_card.keywords = list(attack_card.keywords or [])
        if "Overpower" not in attack_card.keywords:
            attack_card.keywords.append("Overpower")

def _goldbaited_hook_next_pirate_apply(attack_card, player, state):
    """Gold-Baited Hook: next Pirate attack gets on-hit steal/create Gold."""
    if "Pirate" not in attack_card.types:
        return
    player.current_turn_effects.append("goldbaited_hook_on_hit_gold")

def _cheating_scoundrel_next_attack_apply(attack_card, player, state):
    """Cheating Scoundrel: next attack action +3{p}, wagers with defender."""
    attack_card.effects.append(("base_power", lambda base: base + 3))
    player.current_turn_effects.append("cheating_scoundrel_wager_active")

def _electrostatic_next_attack_apply(attack_card, player, state):
    """Electrostatic Discharge: next attack action with cost ≤1 gets +3{p}."""
    attack_card.effects.append(("base_power", lambda base: base + 3))

TURN_ATTACK_EFFECTS = {
    "next_attack_6_base_power": {
        "apply_fn": _next_attack_6_base_power_apply,
    },
    "nimblism_next_attack_plus1": {
        "condition_fn": lambda attack_card, player, state: (
            attack_card.is_action and (attack_card.cost or 0) <= 1
        ),
        "apply_fn": _nimblism_next_attack_plus1_apply,
    },
    "hammerhead_next_arrow_+4": {
        "condition_fn": lambda attack_card, player, state: "Arrow" in attack_card.types,
        "apply_fn": _hammerhead_next_arrow_apply,
    },
    "goldbaited_hook_next_pirate_hit_gold": {
        "condition_fn": lambda attack_card, player, state: "Pirate" in attack_card.types,
        "apply_fn": _goldbaited_hook_next_pirate_apply,
    },
    "cheating_scoundrel_next_attack_+3": {
        "condition_fn": lambda attack_card, player, state: (
            "Attack" in attack_card.types and "Action" in attack_card.types
        ),
        "apply_fn": _cheating_scoundrel_next_attack_apply,
    },
    "electrostatic_next_attack_+3": {
        "condition_fn": lambda attack_card, player, state: (
            "Attack" in attack_card.types and "Action" in attack_card.types
            and (attack_card.cost or 0) <= 1
        ),
        "apply_fn": _electrostatic_next_attack_apply,
    },
}

def _blacktek_whisperers_ar_pay_cost(action, player, state):
    """Attack Reaction cost: Destroy Blacktek Whisperers."""
    card = action.card
    player.legs.remove(card)
    player.graveyard.add(card)

def _blacktek_whisperers_ar_effect(action, player, state):
    """Attack Reaction effect: target Assassin attack gets on-hit go again."""
    player.current_turn_effects.append("blacktek_hit_go_again")

# Wire Blacktek into the equipment activation dicts (functions defined above)
EQUIPMENT_PAY_COSTS["blacktek_whisperers"] = _blacktek_whisperers_ar_pay_cost
EQUIPMENT_ACTIVATION_EFFECTS["blacktek_whisperers"] = _blacktek_whisperers_ar_effect

ATTACK_REACTION_CONDITIONS = {
    "blacktek_whisperers": {
        "condition_fn": lambda player, state: (
            any(c.slug == "blacktek_whisperers" for c in player.legs.cards)
            and state.combat is not None
            and state.combat.attack_card is not None
            and "Assassin" in (state.combat.attack_card.types or [])
        ),
        "pay_cost_fn": _blacktek_whisperers_ar_pay_cost,
        "effect_fn": _blacktek_whisperers_ar_effect,
    },
}

DEFENSE_REACTION_CONDITIONS = {

}

# ---------------------------------------------------------------------------
# Discard-activate effects — "Instant - Discard this:" hand abilities
# Cost (discard) is handled by _apply_discard_activate in engine.py.
# Signature: (action, player, state) -> None
# ---------------------------------------------------------------------------

def _ripple_away_discard_effect(action, player, state):
    """Reduce token creation by 1 for any action card effect this turn."""
    player.current_turn_effects.append("ripple_away_reduce_tokens")

def _under_the_trap_door_discard_effect(action, player, state):
    """Instant - Discard this: Banish target trap from your graveyard.
    If you do, you may play it this turn and if it would be put into the graveyard this turn,
    instead banish it."""
    from engine.card_effects.keywords import _ask_player, effect_banish
    from engine.state import ReplacementEffect
    cid = player.player_id
    traps = [c for c in player.graveyard.cards if "Trap" in (c.types or [])]
    if not traps:
        return
    options = [c.slug for c in traps] + ["none"]
    pick = _ask_player(state, cid, options,
                       context="Under the Trap-Door: choose a Trap from your graveyard to banish (you may play it this turn)")
    if pick == "none":
        return
    target = next((c for c in traps if c.slug == pick), None)
    if not target:
        return
    effect_banish(state, target, face_up=True, banisher_id=cid)
    # Mark trap as playable this turn from the banish zone
    player.current_turn_effects.append(f"trap_door_playable_{target.slug}")
    # Register a replacement effect: if this trap would go to graveyard this turn, banish it instead
    def _trap_door_gy_replacement(event_data, gs):
        card = event_data.get("card")
        if card is None or card.slug != target.slug:
            return event_data
        if f"trap_door_banish_on_gy_{target.slug}" not in player.current_turn_effects:
            return event_data
        # Redirect: banish instead of graveyard
        event_data["destination"] = "banished"
        return event_data

    from engine.effects import ReplacementEffect as RE
    rep = RE(
        event_type="move_to_graveyard",
        condition_fn=lambda ed, gs: (
            ed.get("card") is not None and
            ed.get("card").slug == target.slug and
            f"trap_door_banish_on_gy_{target.slug}" in player.current_turn_effects
        ),
        replacement_fn=_trap_door_gy_replacement,
        duration="end_of_turn",
    )
    state.effect_manager.add_replacement(rep)
    player.current_turn_effects.append(f"trap_door_banish_on_gy_{target.slug}")

DISCARD_ACTIVATE_EFFECTS = {
    "ripple_away": _ripple_away_discard_effect,
    "under_the_trapdoor": _under_the_trap_door_discard_effect,
}