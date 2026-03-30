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

def _head_destroy_pay_cost(action, player, state):
    """Cost: destroy self from head slot."""
    player.head.remove(action.card)
    player.graveyard.add(action.card)

def _achilles_accelerator_pay_cost(action, player, state):
    """Cost: destroy self from legs slot."""
    player.legs.remove(action.card)
    player.graveyard.add(action.card)

def _achilles_accelerator_condition(player, slot_name, equip_card, state=None) -> bool:
    """Only activatable if the player has boosted this turn."""
    return bool(player.class_counters.get("boosted_this_turn"))

def _storm_striders_effect(action, player, state):
    """Effect: next Wizard non-attack action card this turn costs {r} less."""
    player.current_turn_effects.append("storm_striders_cost_reduction")

def _halo_of_illumination_effect(action, player, state):
    """Effect: put a card from hand into soul; if Light, draw a card."""
    if not player.hand.cards:
        return
    card = player.hand.cards[0]
    player.hand.remove(card)
    player.soul.add(card)
    if "Light" in (card.types or []) and player.deck.cards:
        drawn = player.deck.cards[0]
        player.deck.remove(drawn)
        player.hand.add(drawn)

def _achilles_accelerator_effect(action, player, state):
    """Effect: gain 1 action point."""
    player.action_points += 1

# ---------------------------------------------------------------------------
# Radiant-* equipment: "Instant – Banish this and a card from hero's soul"
# Condition: soul must have a card. Pay: banish self from slot + banish soul card.
# ---------------------------------------------------------------------------

def _radiant_condition(player, slot_name, equip_card, state=None) -> bool:
    return bool(player.soul.cards)

def _radiant_head_pay_cost(action, player, state):
    """Banish self from head + banish top soul card."""
    player.head.remove(action.card)
    player.banished.add(action.card)
    if player.soul.cards:
        soul_card = player.soul.cards[0]
        player.soul.remove(soul_card)
        player.banished.add(soul_card)

def _radiant_chest_pay_cost(action, player, state):
    player.chest.remove(action.card)
    player.banished.add(action.card)
    if player.soul.cards:
        soul_card = player.soul.cards[0]
        player.soul.remove(soul_card)
        player.banished.add(soul_card)

def _radiant_arms_pay_cost(action, player, state):
    player.arms.remove(action.card)
    player.banished.add(action.card)
    if player.soul.cards:
        soul_card = player.soul.cards[0]
        player.soul.remove(soul_card)
        player.banished.add(soul_card)

def _radiant_legs_pay_cost(action, player, state):
    player.legs.remove(action.card)
    player.banished.add(action.card)
    if player.soul.cards:
        soul_card = player.soul.cards[0]
        player.soul.remove(soul_card)
        player.banished.add(soul_card)

# Ragamuffin's Hat: "Instant – Destroy Ragamuffin's Hat"  (head slot)
# _head_destroy_pay_cost already exists — reused.

# compass_of_sunken_depths / iris_of_the_blossom: {t} cost = exhaust self
def _exhaust_self_pay_cost(action, player, state):
    """Cost: {t} — exhaust this equipment (prevents re-use until start of next turn)."""
    action.card.exhausted = True

# iris_of_the_blossom: {t} + discard a card; condition: hand not empty
def _iris_condition(player, slot_name, equip_card, state=None) -> bool:
    return bool(player.hand.cards)

def _iris_pay_cost(action, player, state):
    """Cost: {t}, discard a card from hand."""
    action.card.exhausted = True
    if player.hand.cards:
        card = player.hand.cards[0]
        player.hand.remove(card)
        player.graveyard.add(card)

# alluvion_constellas: "Instant – Remove 2 energy counters"
# Counter not yet fully modelled; condition blocks activation unless 2+ counters present.
def _alluvion_condition(player, slot_name, equip_card, state=None) -> bool:
    return player.class_counters.get("alluvion_energy", 0) >= 2

def _alluvion_pay_cost(action, player, state):
    player.class_counters["alluvion_energy"] = max(0, player.class_counters.get("alluvion_energy", 0) - 2)

EQUIPMENT_PAY_COSTS = {
    "hammerhead_harpoon_cannon": _hammerhead_pay_cost,
    "goldbaited_hook": _goldbaited_hook_pay_cost,
    "quiver_of_abyssal_depths": _quiver_pay_cost,
    "sealace_sarong": _sealace_pay_cost,
    "aether_bindings_of_the_third_age": _aether_bindings_pay_cost,
    "lightning_greaves": _lightning_greaves_pay_cost,
    "old_knocker": _old_knocker_pay_cost,
    "halo_of_illumination": _head_destroy_pay_cost,
    "storm_striders": _lightning_greaves_pay_cost,   # same: {r} + destroy from legs
    "achilles_accelerator": _achilles_accelerator_pay_cost,
    # Radiant-* (banish self + soul card)
    "radiant_view": _radiant_head_pay_cost,
    "radiant_raiment": _radiant_chest_pay_cost,
    "radiant_touch": _radiant_arms_pay_cost,
    "radiant_flow": _radiant_legs_pay_cost,
    # Ragamuffin's Hat (head destroy)
    "ragamuffins_hat": _head_destroy_pay_cost,
    # {t}-cost Instants — exhaust self
    "compass_of_sunken_depths": _exhaust_self_pay_cost,
    "iris_of_the_blossom": _iris_pay_cost,
    # alluvion_constellas — remove 2 energy counters
    "alluvion_constellas": _alluvion_pay_cost,
}

EQUIPMENT_ACTIVATION_COST["halo_of_illumination"] = 1    # {r} from card text
EQUIPMENT_ACTIVATION_COST["storm_striders"] = 1           # {r} from card text
EQUIPMENT_ACTIVATION_COST["waning_moon"] = 2              # {r}{r} from card text
EQUIPMENT_ACTIVATION_COST["meridian_pathway"] = 3         # {c}{c}{c} treated as 3 generic resources
EQUIPMENT_ACTIVATION_CONDITIONS["achilles_accelerator"] = _achilles_accelerator_condition
EQUIPMENT_ACTIVATION_CONDITIONS["radiant_view"] = _radiant_condition
EQUIPMENT_ACTIVATION_CONDITIONS["radiant_raiment"] = _radiant_condition
EQUIPMENT_ACTIVATION_CONDITIONS["radiant_touch"] = _radiant_condition
EQUIPMENT_ACTIVATION_CONDITIONS["radiant_flow"] = _radiant_condition
EQUIPMENT_ACTIVATION_CONDITIONS["iris_of_the_blossom"] = _iris_condition
EQUIPMENT_ACTIVATION_CONDITIONS["alluvion_constellas"] = _alluvion_condition

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
    "halo_of_illumination": _halo_of_illumination_effect,
    "storm_striders": _storm_striders_effect,
    "achilles_accelerator": _achilles_accelerator_effect,
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

def _pummel_combat_condition(combat) -> bool:
    """Pummel is legal only when the current chain attack is a Club/Hammer weapon
    attack, or an Attack Action with cost >= 2.  Mirrors Talishar IsPlayRestricted."""
    if not combat or not combat.attack_card:
        return False
    attack = combat.attack_card
    # Club or Hammer weapon attack
    if combat.from_weapon:
        subtypes = getattr(attack, "subtypes", None) or []
        if "Club" in subtypes or "Hammer" in subtypes:
            return True
    # Attack Action with cost >= 2 (Talishar: CardType=="AA" && CardCost>=2)
    if "Action" in (attack.types or []) and attack.cost is not None and attack.cost >= 2:
        return True
    return False


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
    "pummel_red": _pummel_combat_condition,
    "pummel_yellow": _pummel_combat_condition,
    "pummel_blue": _pummel_combat_condition,
}

DEFENSE_REACTION_CONDITIONS = {

}

# ---------------------------------------------------------------------------
# Play target conditions — CR 5.1.4a
# Cards with required targets that may not always exist.
# Signature: condition(state, player_id) -> bool
# Returns True if a valid target exists and the card may be played.
# Register slugs WITHOUT color suffix (_red/_yellow/_blue stripped by lookup).
# ---------------------------------------------------------------------------
PLAY_TARGET_CONDITIONS: dict = {
    # "Destroy an aura you control" — required effect, card cannot be played without an aura
    "deadwood_dirge": lambda state, pid: bool(state.players[pid].auras.cards),
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

# ---------------------------------------------------------------------------
# Item activation: destroy-cost items
# All items registered here have "Destroy this" as their activation cost.
# pay_cost_fn removes the item from player.items and moves it to graveyard.
# effect_fn fires after the cost is paid.
# EQUIPMENT_ACTIVATION_COST overrides are added for tokens/items whose resource
# cost is embedded in functional text rather than the card.cost field.
# ---------------------------------------------------------------------------

def _item_destroy_pay_cost(action, player, state):
    """Generic pay cost: destroy this item (remove from items zone → graveyard)."""
    player.items.remove(action.card)
    player.graveyard.add(action.card)

def _goldkiss_rum_item_pay_cost(action, player, state):
    """Goldkiss Rum: {t} hero, destroy this."""
    player.hero.tapped = True
    player.items.remove(action.card)
    player.graveyard.add(action.card)

# --- Resource cost overrides for tokens whose cost field is blank ---
EQUIPMENT_ACTIVATION_COST["gold"] = 2          # {r}{r}, destroy this: Draw a card.
EQUIPMENT_ACTIVATION_COST["silver"] = 3        # {r}{r}{r}, destroy this: Draw a card.
EQUIPMENT_ACTIVATION_COST["copper"] = 4        # {r}{r}{r}{r}, destroy this: Draw a card.
EQUIPMENT_ACTIVATION_COST["backup_protocol_blu_blue"] = 2   # {r}{r}, destroy this
EQUIPMENT_ACTIVATION_COST["backup_protocol_red_red"] = 2
EQUIPMENT_ACTIVATION_COST["backup_protocol_yel_yellow"] = 2
EQUIPMENT_ACTIVATION_COST["seeker_kunai_red"] = 1           # {r}, destroy this

# --- Add "next_attack_+2" key to TURN_ATTACK_EFFECTS (used by several items) ---
def _next_attack_plus2_apply(attack_card, player, state):
    attack_card.effects.append(("base_power", lambda base: base + 2))

TURN_ATTACK_EFFECTS["next_attack_+2"] = {
    "apply_fn": _next_attack_plus2_apply,
}

# ---------------------------------------------------------------------------
# Item effect functions
# ---------------------------------------------------------------------------

def _item_gain_2r(action, player, state):
    """Gain {r}{r}. (energy_potion_blue, ruby_amulet_blue)"""
    player.resources += 2

def _item_draw_go_again(action, player, state):
    """Draw a card and go again. (gold, silver, copper, diamond)"""
    from engine.card_effects.keywords import effect_draw
    effect_draw(state, player.player_id, 1)
    player.action_points += 1

def _item_gain_2h_go_again(action, player, state):
    """Gain 2{h} and go again. (healing_potion_blue, pounamu_amulet_blue)"""
    from engine.card_effects.keywords import effect_gain_life
    effect_gain_life(state, player.player_id, 2)
    player.action_points += 1

def _item_opt2(action, player, state):
    """Opt 2. (clarity_potion_blue, opal_amulet_blue)"""
    from engine.card_effects.keywords import effect_opt
    effect_opt(state, player.player_id, 2)

def _diamond_amulet_effect(action, player, state):
    """Gain 1 action point."""
    player.action_points += 1

def _timesnap_potion_effect(action, player, state):
    """Gain 2 action points."""
    player.action_points += 2

def _amethyst_amulet_effect(action, player, state):
    """Your next attack this turn gets +2{p}."""
    player.current_turn_effects.append("next_attack_+2")

def _potion_of_strength_effect(action, player, state):
    """Your next attack this turn gains +2{p}. Go again."""
    player.current_turn_effects.append("next_attack_+2")
    player.action_points += 1

def _potion_of_ironhide_effect(action, player, state):
    """Attack action cards you own gain +1{d} this turn (flag for future use)."""
    player.current_turn_effects.append("ironhide_aa_+1d_this_turn")

def _platinum_amulet_effect(action, player, state):
    """Target defending card gets +1{d} until end of turn."""
    if state.combat and state.combat.defending_cards:
        for dc in state.combat.defending_cards:
            if dc.defense is not None:
                dc.defense += 1
            else:
                dc.defense = 1

def _crazy_brew_effect(action, player, state):
    """Roll a d6. 1-2: lose 2{h} GA. 3-4: gain 2{h} GA. 5-6: gain {r}{r}, +2AP, next attack +2{p}."""
    import random as _rng
    from engine.card_effects.keywords import effect_gain_life, effect_lose_life
    roll = _rng.randint(1, 6)
    if roll <= 2:
        effect_lose_life(state, player.player_id, 2)
        player.action_points += 1
    elif roll <= 4:
        effect_gain_life(state, player.player_id, 2)
        player.action_points += 1
    else:
        player.resources += 2
        player.action_points += 2
        player.current_turn_effects.append("next_attack_+2")

def _potion_of_deja_vu_effect(action, player, state):
    """Put all cards from your pitch zone on top of your deck."""
    pitched = list(player.pitch.cards)
    for c in pitched:
        player.pitch.remove(c)
        player.deck.add_top(c)

def _potion_of_luck_effect(action, player, state):
    """Shuffle your hand and arsenal into your deck then draw that many cards."""
    from engine.card_effects.keywords import effect_draw, effect_shuffle
    total = len(player.hand.cards) + len(player.arsenal.cards)
    for c in list(player.hand.cards):
        player.hand.remove(c)
        player.deck.add_bottom(c)
    for c in list(player.arsenal.cards):
        player.arsenal.remove(c)
        player.deck.add_bottom(c)
    effect_shuffle(state, player.player_id)
    effect_draw(state, player.player_id, total)

def _potion_of_seeing_effect(action, player, state):
    """Look at target hero's hand (AI already has perfect information — no-op)."""
    pass

def _onyx_amulet_effect(action, player, state):
    """Tap all heroes and allies. Go again."""
    for p in state.players.values():
        if hasattr(p, 'hero') and p.hero is not None:
            p.hero.tapped = True
        for ally in list(getattr(getattr(p, 'allies', None), 'cards', [])):
            ally.tapped = True
    player.action_points += 1

def _pearl_amulet_effect(action, player, state):
    """Untap ({u}) target permanent. Go again."""
    # Untap own tapped permanents first (most useful); fall back to opponent hero
    untapped = False
    for zone in [player.head, player.chest, player.arms, player.legs,
                 player.weapon1, player.weapon2, player.permanents]:
        for card in getattr(zone, 'cards', []):
            if getattr(card, 'tapped', False):
                card.tapped = False
                untapped = True
                break
        if untapped:
            break
    if not untapped:
        opp = state.players[3 - player.player_id]
        if hasattr(opp, 'hero') and opp.hero is not None and getattr(opp.hero, 'tapped', False):
            opp.hero.tapped = False
    player.action_points += 1

def _sapphire_amulet_effect(action, player, state):
    """You get +1{i} this turn (flag — draw extra card in end-turn draw if implemented)."""
    player.current_turn_effects.append("sapphire_amulet_+1i")

def _goldkiss_rum_effect(action, player, state):
    """Your next action this turn gets go again."""
    player.current_turn_effects.append("goldkiss_rum_next_action_ga")

def _dissipation_shield_effect(action, player, state):
    """Prevent X damage this turn, where X = steam counters on this card before destruction."""
    counter_key = (action.card.slug, 'items', 'steam')
    steam = player.counters.get(counter_key, 0)
    if steam > 0:
        # Apply flat damage prevention via existing prevention mechanism
        if not hasattr(state, 'flat_prevention'):
            state.flat_prevention = {}
        pid = player.player_id
        state.flat_prevention[pid] = state.flat_prevention.get(pid, 0) + steam

def _imperial_seal_effect(action, player, state):
    """Defense reaction cards can't be played this turn. Go again."""
    player.current_turn_effects.append("imperial_seal_no_dr_this_turn")
    player.action_points += 1

def _imperial_edict_effect(action, player, state):
    """Name a card — it can't be played until your next turn. (Simplified: no-op for AI.)"""
    player.action_points += 1

def _imperial_warhorn_effect(action, player, state):
    """Destroy chosen permanents. (Complex multiplayer mechanic — no-op for 1v1 AI.) Go again."""
    player.action_points += 1

def _amulet_of_earth_effect(action, player, state):
    """If Earth fused this turn: your attack action cards get +1{p} and +1{d} this turn."""
    if "earth_fused" in player.current_turn_effects:
        player.current_turn_effects.append("amulet_earth_aa_buff")

def _amulet_of_echoes_effect(action, player, state):
    """If opponent played 2+ cards with same name this turn: they discard 2."""
    from engine.card_effects.keywords import effect_discard
    opp = state.players[3 - player.player_id]
    name_counts: dict = {}
    for slug in getattr(opp, 'cards_played_this_turn', []):
        name_counts[slug] = name_counts.get(slug, 0) + 1
    if any(v >= 2 for v in name_counts.values()):
        effect_discard(state, opp.player_id, 2)

def _amulet_of_ice_effect(action, player, state):
    """If Ice fused this turn: target opponent discards unless they pay {r}{r}."""
    if "ice_fused" in player.current_turn_effects:
        opp = state.players[3 - player.player_id]
        # AI opponents always pay the resource cost if able
        if opp.resources >= 2:
            opp.resources -= 2
        else:
            from engine.card_effects.keywords import effect_discard
            effect_discard(state, opp.player_id, 1)

def _amulet_of_ignition_effect(action, player, state):
    """If no card played/ability activated yet this turn: next ability costs {r} less."""
    player.current_turn_effects.append("amulet_ignition_next_ability_-1r")

def _amulet_of_intervention_effect(action, player, state):
    """Prevent the next 1 damage dealt to your hero this turn."""
    if not hasattr(state, 'flat_prevention'):
        state.flat_prevention = {}
    pid = player.player_id
    state.flat_prevention[pid] = state.flat_prevention.get(pid, 0) + 1

def _amulet_of_lightning_effect(action, player, state):
    """If Lightning fused this turn: target action card gains go again."""
    if "lightning_fused" in player.current_turn_effects and state.combat and state.combat.attack_card:
        kw = state.combat.attack_card.keywords or []
        if "Go again" not in kw:
            state.combat.attack_card.keywords = list(kw) + ["Go again"]

def _amulet_of_assertiveness_effect(action, player, state):
    """Target attack gains 'When this hits, banish top deck card; if AA, may play it.' """
    if state.combat and state.combat.attack_card:
        player.current_turn_effects.append("amulet_assertiveness_on_hit_banish_play")

def _amulet_of_oblation_effect(action, player, state):
    """If a card entered a GY this turn: target attack gains 'if GY-bound, put on bottom of deck'."""
    if "card_entered_gy_this_turn" in player.current_turn_effects and state.combat and state.combat.attack_card:
        player.current_turn_effects.append("amulet_oblation_active")

def _amulet_of_havencall_effect(action, player, state):
    """If no cards in hand: search deck for Rally the Rearguard and add to chain link. (Simplified: draw it.)"""
    from engine.card_effects.keywords import _ask_player
    cards = [c for c in player.deck.cards if c.slug == "rally_the_rearguard"]
    if cards:
        target = cards[0]
        player.deck.remove(target)
        # Add as defending card if in combat
        if state.combat:
            state.combat.defending_cards.append(target)
        else:
            player.hand.add(target)
        from engine.card_effects.keywords import effect_shuffle
        effect_shuffle(state, player.player_id)

def _backup_protocol_effect(color_pitch: int):
    """Return a Mech attack action card of the given pitch value from graveyard to hand."""
    def _effect(action, player, state):
        from engine.card_effects.keywords import _ask_player
        candidates = [c for c in player.graveyard.cards
                      if "Mechanologist" in (c.types or []) and "Attack" in (c.types or [])
                      and "Action" in (c.types or []) and (c.pitch or 0) == color_pitch]
        if not candidates:
            return
        options = [c.slug for c in candidates] + ["none"]
        pick = _ask_player(state, player.player_id, options,
                           context="Backup Protocol: choose a Mech AA card to return from graveyard")
        if pick == "none":
            return
        target = next((c for c in candidates if c.slug == pick), candidates[0])
        player.graveyard.remove(target)
        player.hand.add(target)
    return _effect

def _seeker_kunai_effect(action, player, state):
    """Target Assassin attack action card gets +1{p}."""
    if state.combat and state.combat.attack_card:
        if "Assassin" in (state.combat.attack_card.types or []):
            state.combat.attack_card.effects = list(getattr(state.combat.attack_card, 'effects', []))
            state.combat.attack_card.effects.append(("base_power", lambda base: base + 1))

def _silverwind_shuriken_effect(action, player, state):
    """Target attack action card with combo gains +1{p}."""
    if state.combat and state.combat.attack_card:
        if "Combo" in (state.combat.attack_card.keywords or []):
            state.combat.attack_card.effects = list(getattr(state.combat.attack_card, 'effects', []))
            state.combat.attack_card.effects.append(("base_power", lambda base: base + 1))

def _assembly_module_effect(action, player, state):
    """Search deck for a Hyper Driver and put it into the arena. (Simplified.)"""
    from engine.card_effects.keywords import effect_shuffle, create_token
    candidates = [c for c in player.deck.cards if c.slug == "hyper_driver"]
    if candidates:
        target = candidates[0]
        player.deck.remove(target)
        player.items.add(target)
        effect_shuffle(state, player.player_id)
    else:
        create_token(state, player.player_id, "hyper_driver", 1)

# ---------------------------------------------------------------------------
# Register all destroy-cost items in EQUIPMENT_PAY_COSTS and EQUIPMENT_ACTIVATION_EFFECTS
# ---------------------------------------------------------------------------

_SIMPLE_DRAW_GA = [
    "gold", "silver", "copper", "diamond",
]
_GAIN_2R = [
    "energy_potion_blue", "ruby_amulet_blue",
]
_GAIN_2H_GA = [
    "healing_potion_blue", "pounamu_amulet_blue",
]
_OPT2 = [
    "clarity_potion_blue", "opal_amulet_blue",
]

for _slug in (_SIMPLE_DRAW_GA + _GAIN_2R + _GAIN_2H_GA + _OPT2 + [
    "amethyst_amulet_blue", "amulet_of_assertiveness_yellow", "amulet_of_earth_blue",
    "amulet_of_echoes_blue", "amulet_of_havencall_blue", "amulet_of_ice_blue",
    "amulet_of_ignition_yellow", "amulet_of_intervention_blue", "amulet_of_lightning_blue",
    "amulet_of_oblation_blue", "assembly_module_blue",
    "backup_protocol_blu_blue", "backup_protocol_red_red", "backup_protocol_yel_yellow",
    "crazy_brew_blue", "diamond_amulet_blue", "dissipation_shield_yellow",
    "imperial_edict_red", "imperial_seal_of_command_red", "imperial_warhorn_red",
    "onyx_amulet_blue", "pearl_amulet_blue", "platinum_amulet_blue",
    "potion_of_dj_vu_blue", "potion_of_ironhide_blue", "potion_of_luck_blue",
    "potion_of_seeing_blue", "potion_of_strength_blue", "sapphire_amulet_blue",
    "seeker_kunai_red", "silverwind_shuriken_blue", "timesnap_potion_blue",
]):
    EQUIPMENT_PAY_COSTS[_slug] = _item_destroy_pay_cost

EQUIPMENT_PAY_COSTS["goldkiss_rum"] = _goldkiss_rum_item_pay_cost

_EFFECT_MAP = {
    **{s: _item_draw_go_again for s in _SIMPLE_DRAW_GA},
    **{s: _item_gain_2r for s in _GAIN_2R},
    **{s: _item_gain_2h_go_again for s in _GAIN_2H_GA},
    **{s: _item_opt2 for s in _OPT2},
    "amethyst_amulet_blue":           _amethyst_amulet_effect,
    "amulet_of_assertiveness_yellow": _amulet_of_assertiveness_effect,
    "amulet_of_earth_blue":           _amulet_of_earth_effect,
    "amulet_of_echoes_blue":          _amulet_of_echoes_effect,
    "amulet_of_havencall_blue":       _amulet_of_havencall_effect,
    "amulet_of_ice_blue":             _amulet_of_ice_effect,
    "amulet_of_ignition_yellow":      _amulet_of_ignition_effect,
    "amulet_of_intervention_blue":    _amulet_of_intervention_effect,
    "amulet_of_lightning_blue":       _amulet_of_lightning_effect,
    "amulet_of_oblation_blue":        _amulet_of_oblation_effect,
    "assembly_module_blue":           _assembly_module_effect,
    "backup_protocol_blu_blue":       _backup_protocol_effect(3),
    "backup_protocol_red_red":        _backup_protocol_effect(1),
    "backup_protocol_yel_yellow":     _backup_protocol_effect(2),
    "crazy_brew_blue":                _crazy_brew_effect,
    "diamond_amulet_blue":            _diamond_amulet_effect,
    "dissipation_shield_yellow":      _dissipation_shield_effect,
    "goldkiss_rum":                   _goldkiss_rum_effect,
    "imperial_edict_red":             _imperial_edict_effect,
    "imperial_seal_of_command_red":   _imperial_seal_effect,
    "imperial_warhorn_red":           _imperial_warhorn_effect,
    "onyx_amulet_blue":               _onyx_amulet_effect,
    "pearl_amulet_blue":              _pearl_amulet_effect,
    "platinum_amulet_blue":           _platinum_amulet_effect,
    "potion_of_dj_vu_blue":           _potion_of_deja_vu_effect,
    "potion_of_ironhide_blue":        _potion_of_ironhide_effect,
    "potion_of_luck_blue":            _potion_of_luck_effect,
    "potion_of_seeing_blue":          _potion_of_seeing_effect,
    "potion_of_strength_blue":        _potion_of_strength_effect,
    "sapphire_amulet_blue":           _sapphire_amulet_effect,
    "seeker_kunai_red":               _seeker_kunai_effect,
    "silverwind_shuriken_blue":       _silverwind_shuriken_effect,
    "timesnap_potion_blue":           _timesnap_potion_effect,
}
EQUIPMENT_ACTIVATION_EFFECTS.update(_EFFECT_MAP)


# ---------------------------------------------------------------------------
# Dragonscaler Flight Path (HNT — Fai legs equipment)
# ---------------------------------------------------------------------------

def _dragonscaler_activation_cost(player, state) -> int:
    """Base cost 3, minus 1 per Draconic chain link the activating player controls."""
    draconic_links = 0
    for link in (state.chain_links or []):
        if link.attacker_id != player.player_id:
            continue
        lki_types = state.last_known_value(link.attack_slug, "types")
        if lki_types is None and hasattr(state, "card_db") and state.card_db is not None:
            card = state.card_db.get(link.attack_slug)
            lki_types = card.types if card else []
        if "Draconic" in (lki_types or []):
            draconic_links += 1
    return max(0, 3 - draconic_links)


def _dragonscaler_condition(player, slot_name, equip_card, state) -> bool:
    """Legal only during combat when there is at least one Draconic attack on the chain."""
    if state.combat is None:
        return False
    if state.combat.attack_card and "Draconic" in (state.combat.attack_card.types or []):
        return True
    for link in (state.chain_links or []):
        if link.attacker_id != player.player_id:
            continue
        lki_types = state.last_known_value(link.attack_slug, "types")
        if lki_types is None and hasattr(state, "card_db") and state.card_db is not None:
            card = state.card_db.get(link.attack_slug)
            lki_types = card.types if card else []
        if "Draconic" in (lki_types or []):
            return True
    return False


def _dragonscaler_pay_cost(action, player, state) -> None:
    """Cost: destroy Dragonscaler Flight Path from legs."""
    zone = player.zone_by_name("legs")
    if zone and action.card in zone.cards:
        zone.remove(action.card)
        player.graveyard.add(action.card)


def _dragonscaler_effect(action, player, state) -> None:
    """Effect: target Draconic attack gets go again.
    Weapon/ally attacks also flag player for an extra attack this turn."""
    from engine.card_effects.keywords import _ask_player

    targets = []
    if state.combat and state.combat.attack_card:
        ac = state.combat.attack_card
        if "Draconic" in (ac.types or []):
            targets.append(("current", ac, state.combat.from_weapon, "Ally" in (ac.types or [])))

    for link in (state.chain_links or []):
        if link.attacker_id != player.player_id:
            continue
        lki_types = state.last_known_value(link.attack_slug, "types")
        if lki_types is None and hasattr(state, "card_db") and state.card_db is not None:
            card = state.card_db.get(link.attack_slug)
            lki_types = card.types if card else []
        if "Draconic" not in (lki_types or []):
            continue
        is_weapon = link.from_weapon
        is_ally = "Ally" in (lki_types or [])
        if is_weapon or is_ally:
            targets.append(("link", link, is_weapon, is_ally))

    if not targets:
        return

    if len(targets) > 1:
        choice_idx = _ask_player(state, player.player_id, list(range(len(targets))),
                                  context="Dragonscaler Flight Path: choose target Draconic attack")
        chosen = targets[choice_idx] if isinstance(choice_idx, int) and 0 <= choice_idx < len(targets) else targets[0]
    else:
        chosen = targets[0]

    target_type, target_obj, is_weapon, is_ally = chosen

    if target_type == "current":
        if "go_again" not in state.combat.keywords and "Go again" not in state.combat.keywords:
            state.combat.keywords.append("go_again")
        attack = target_obj
        if attack.keywords is None:
            attack.keywords = []
        if "Go again" not in attack.keywords:
            attack.keywords.append("Go again")
        if is_weapon or is_ally:
            player.current_turn_effects.append("dragonscaler_extra_attack")
    else:
        if is_weapon or is_ally:
            player.current_turn_effects.append("dragonscaler_extra_attack")


EQUIPMENT_ACTIVATION_CONDITIONS["dragonscaler_flight_path"] = _dragonscaler_condition
EQUIPMENT_ACTIVATION_COST["dragonscaler_flight_path"] = _dragonscaler_activation_cost
EQUIPMENT_PAY_COSTS["dragonscaler_flight_path"] = _dragonscaler_pay_cost
EQUIPMENT_ACTIVATION_EFFECTS["dragonscaler_flight_path"] = _dragonscaler_effect


# ---------------------------------------------------------------------------
# quickdodge_flexors
# "**Defense Reaction** - {r}: Add this to the active chain link as a
# defending card. It has 2 base {d} this chain link.
# At the beginning of the end phase, if this defended this turn, destroy it."
#
# Implementation:
#   Condition: only legal when combat is active (there is an active chain link).
#   Effect: give the card 2 base defense temporarily, add to combat.defending_cards,
#   and remove from the equipment slot → graveyard. Removing from the slot prevents
#   re-activation (slot is empty) and approximates the "destroy at end of phase"
#   result with no observable difference at random-agent level.
# ---------------------------------------------------------------------------

def _quickdodge_flexors_condition(_player, _slot_name, _equip_card, state):
    return state.combat is not None

def _quickdodge_flexors_effect(action, player, state):
    card = action.card
    slot = getattr(action, 'slot', None) or "legs"
    # Grant 2 base defense for this chain link
    card.base_defense = 2
    # Add to chain link defending cards so damage calculation includes it
    if state.combat is not None:
        if state.combat.defending_cards is None:
            state.combat.defending_cards = []
        if card not in state.combat.defending_cards:
            state.combat.defending_cards.append(card)
    # Remove from equipment slot (card has been committed; destroyed at end of phase)
    zone = player.zone_by_name(slot)
    if zone and card in zone.cards:
        zone.remove(card)
        player.graveyard.add(card)

EQUIPMENT_ACTIVATION_CONDITIONS["quickdodge_flexors"] = _quickdodge_flexors_condition
EQUIPMENT_ACTIVATION_EFFECTS["quickdodge_flexors"] = _quickdodge_flexors_effect


# ---------------------------------------------------------------------------
# B2/B3: HERO_TRIGGERS — passive triggered hero abilities
# Maps hero_slug -> list[dict] where each dict describes a passive trigger.
# Format: {"event": str, "condition_fn": callable(player, event, state) -> bool,
#          "effect_fn": callable(player, event, state) -> None}
# Registered in engine/triggers.py register_hero_triggers() when hero is in play.
# ---------------------------------------------------------------------------

def _dorinthea_weapon_hit_passive(player, event, state):
    if "dorinthea_weapon_hit_used" in player.current_turn_effects:
        return
    player.current_turn_effects.append("dorinthea_extra_weapon_attack")
    player.current_turn_effects.append("dorinthea_weapon_hit_used")


def _viserai_runeblade_trigger(player, event, state):
    from engine.card_effects.keywords import create_token
    data = event.data if isinstance(event.data, dict) else {}
    played_card = data.get('card')
    if played_card is None:
        return
    if "Runeblade" not in (played_card.types or []):
        return
    if "played_nonattack_action" not in player.current_turn_effects:
        return
    create_token(state, player.player_id, "runechant", 1)


def _briar_attack_damage_trigger(player, event, state):
    if "briar_earth_trigger_used" in player.current_turn_effects:
        return
    data = event.data if isinstance(event.data, dict) else {}
    damage = data.get('damage', 0)
    target_id = data.get('target', 3 - player.player_id)
    if damage > 0 and target_id != player.player_id:
        if state.combat and state.combat.attack_card:
            ac = state.combat.attack_card
            if ac.controller == player.player_id and "Attack" in (ac.types or []) and "Action" in (ac.types or []):
                from engine.card_effects.keywords import create_token
                create_token(state, player.player_id, "embodiment_of_earth", 1)
                player.current_turn_effects.append("briar_earth_trigger_used")


def _briar_second_nonattack_trigger(player, event, state):
    data = event.data if isinstance(event.data, dict) else {}
    played_card = data.get('card')
    if played_card is None:
        return
    types = played_card.types or []
    if "Action" not in types or "Attack" in types:
        return
    count = player.current_turn_effects.count("played_nonattack_action")
    if count == 1:
        from engine.card_effects.keywords import create_token
        create_token(state, player.player_id, "embodiment_of_lightning", 1)


def _katsu_on_hit_trigger(player, event, state):
    if "katsu_hit_trigger_used" in player.current_turn_effects:
        return
    if not state.combat or not state.combat.attack_card:
        return
    ac = state.combat.attack_card
    if ac.controller != player.player_id:
        return
    if "Attack" not in (ac.types or []) or "Action" not in (ac.types or []):
        return
    player.current_turn_effects.append("katsu_hit_trigger_used")
    zero_cost = [c for c in player.hand.cards if (c.cost or 0) == 0]
    if not zero_cost:
        return
    from engine.card_effects.keywords import _ask_player, effect_shuffle
    choice = _ask_player(state, player.player_id, [True, False],
                         context="Katsu: discard a 0-cost card to search for a combo card?")
    if not choice:
        return
    pick = _ask_player(state, player.player_id, [c.slug for c in zero_cost],
                       context="Katsu: choose a 0-cost card to discard")
    card = next((c for c in zero_cost if c.slug == pick), zero_cost[0])
    player.hand.remove(card)
    player.graveyard.add(card)
    combo_cards = [c for c in player.deck.cards if "Combo" in (c.keywords or [])]
    if not combo_cards:
        return
    pick2 = _ask_player(state, player.player_id, [c.slug for c in combo_cards],
                        context="Katsu: choose a combo card to banish face-up")
    found = next((c for c in combo_cards if c.slug == pick2), combo_cards[0])
    player.deck.remove(found)
    player.banished.add(found, is_public=True)
    player.current_turn_effects.append(("katsu_banished_playable", found.slug))
    effect_shuffle(state, player.player_id)


def _olympia_wager_win_trigger(player, event, state):
    if "olympia_wager_win_used" in player.current_turn_effects:
        return
    data = event.data if isinstance(event.data, dict) else {}
    if data.get('winner') != player.player_id:
        return
    from engine.card_effects.keywords import create_token
    create_token(state, player.player_id, "gold", 1)
    player.current_turn_effects.append("olympia_wager_win_used")


def _victor_gold_creation_trigger(player, event, state):
    if "victor_gold_draw_used" in player.current_turn_effects:
        return
    data = event.data if isinstance(event.data, dict) else {}
    if data.get('player_id') != player.player_id:
        return
    from engine.card_effects.keywords import effect_draw
    effect_draw(state, player.player_id, 1)
    player.current_turn_effects.append("victor_gold_draw_used")


def _valda_opponent_draw_trigger(player, event, state):
    from engine.state import Step
    if state.step not in (Step.ACTION, Step.START_PHASE):
        return
    data = event.data if isinstance(event.data, dict) else {}
    if data.get('player_id', -1) == player.player_id:
        return
    count = data.get('count', 1)
    from engine.card_effects.keywords import create_token
    for _ in range(count):
        create_token(state, player.player_id, "seismic_surge", 1)


def _betsy_wager_trigger(player, event, state):
    if not state.combat or not state.combat.attack_card:
        return
    if state.combat.attack_card.controller != player.player_id:
        return
    from engine.card_effects.keywords import _ask_player
    choice = _ask_player(state, player.player_id, [True, False],
                         context="Betsy: pay {r}{r} to give this attack +1{p} and overpower?")
    if not choice or player.resources < 2:
        return
    player.resources -= 2
    state.combat.attack_power = (state.combat.attack_power or 0) + 1
    if "Overpower" not in state.combat.keywords:
        state.combat.keywords.append("Overpower")


def _data_doll_banished_from_deck_trigger(player, event, state):
    data = event.data if isinstance(event.data, dict) else {}
    card = data.get('card')
    if card is None or card.owner != player.player_id:
        return
    if getattr(card, 'prev_zone', None) != "deck":
        return
    types = card.types or []
    if "Mechanologist" not in types or "Item" not in types:
        return
    if (card.cost or 0) > 2:
        return
    player.banished.remove(card)
    player.items.add(card)


def _florian_banished_earth_trigger(player, event, state):
    earth_count = sum(1 for c in player.banished.cards if "Earth" in (c.types or []))
    if earth_count >= 4:
        if "florian_bonus_active" not in player.current_turn_effects:
            player.current_turn_effects.append("florian_bonus_active")
    else:
        if "florian_bonus_active" in player.current_turn_effects:
            player.current_turn_effects.remove("florian_bonus_active")


def _riptide_play_from_hand_trigger(player, event, state):
    data = event.data if isinstance(event.data, dict) else {}
    played_card = data.get('card')
    if played_card is None:
        return
    if getattr(played_card, 'prev_zone', None) != "hand":
        return
    if played_card.controller != player.player_id:
        return
    if player.arsenal.cards or not player.hand.cards:
        return
    from engine.card_effects.keywords import _ask_player
    choice = _ask_player(state, player.player_id, [True, False],
                         context="Riptide: put a card from hand face-down into arsenal?")
    if not choice:
        return
    pick = _ask_player(state, player.player_id, [c.slug for c in player.hand.cards],
                       context="Riptide: choose a card to put into arsenal face-down")
    card = player.hand.find(pick) or player.hand.cards[0]
    player.hand.remove(card)
    player.arsenal.add(card, is_public=False)
    card.face_down = True


HERO_TRIGGERS: dict = {
    "dorinthea": [{"event": "hit", "condition_fn": lambda p, e, s: s.combat is not None and s.combat.from_weapon and s.combat.attacker_id == p.player_id, "effect_fn": _dorinthea_weapon_hit_passive}],
    "dorinthea_ironsong": [{"event": "hit", "condition_fn": lambda p, e, s: s.combat is not None and s.combat.from_weapon and s.combat.attacker_id == p.player_id, "effect_fn": _dorinthea_weapon_hit_passive}],
    "dorinthea_quicksilver_prodigy": [{"event": "hit", "condition_fn": lambda p, e, s: s.combat is not None and s.combat.from_weapon and s.combat.attacker_id == p.player_id, "effect_fn": _dorinthea_weapon_hit_passive}],
    "viserai": [{"event": "on_play", "condition_fn": lambda p, e, s: True, "effect_fn": _viserai_runeblade_trigger}],
    "viserai_rune_blood": [{"event": "on_play", "condition_fn": lambda p, e, s: True, "effect_fn": _viserai_runeblade_trigger}],
    "briar": [{"event": "damage_dealt", "condition_fn": lambda p, e, s: True, "effect_fn": _briar_attack_damage_trigger}, {"event": "on_play", "condition_fn": lambda p, e, s: True, "effect_fn": _briar_second_nonattack_trigger}],
    "briar_warden_of_thorns": [{"event": "damage_dealt", "condition_fn": lambda p, e, s: True, "effect_fn": _briar_attack_damage_trigger}, {"event": "on_play", "condition_fn": lambda p, e, s: True, "effect_fn": _briar_second_nonattack_trigger}],
    "katsu": [{"event": "hit", "condition_fn": lambda p, e, s: True, "effect_fn": _katsu_on_hit_trigger}],
    "katsu_the_wanderer": [{"event": "hit", "condition_fn": lambda p, e, s: True, "effect_fn": _katsu_on_hit_trigger}],
    "olympia": [{"event": "wager_resolved", "condition_fn": lambda p, e, s: True, "effect_fn": _olympia_wager_win_trigger}],
    "olympia_prized_fighter": [{"event": "wager_resolved", "condition_fn": lambda p, e, s: True, "effect_fn": _olympia_wager_win_trigger}],
    "victor_goldmane": [{"event": "gold_created", "condition_fn": lambda p, e, s: True, "effect_fn": _victor_gold_creation_trigger}],
    "victor_goldmane_high_and_mighty": [{"event": "gold_created", "condition_fn": lambda p, e, s: True, "effect_fn": _victor_gold_creation_trigger}],
    "victor_goldmane_match_fixer": [{"event": "gold_created", "condition_fn": lambda p, e, s: True, "effect_fn": _victor_gold_creation_trigger}],
    "valda_brightaxe": [{"event": "card_draw", "condition_fn": lambda p, e, s: True, "effect_fn": _valda_opponent_draw_trigger}],
    "valda_seismic_impact": [{"event": "card_draw", "condition_fn": lambda p, e, s: True, "effect_fn": _valda_opponent_draw_trigger}],
    "betsy": [{"event": "wagered", "condition_fn": lambda p, e, s: True, "effect_fn": _betsy_wager_trigger}],
    "betsy_skin_in_the_game": [{"event": "wagered", "condition_fn": lambda p, e, s: True, "effect_fn": _betsy_wager_trigger}],
    "data_doll_mkii": [{"event": "card_banished", "condition_fn": lambda p, e, s: True, "effect_fn": _data_doll_banished_from_deck_trigger}],
    "florian": [{"event": "card_banished", "condition_fn": lambda p, e, s: True, "effect_fn": _florian_banished_earth_trigger}],
    "florian_rotwood_harbinger": [{"event": "card_banished", "condition_fn": lambda p, e, s: True, "effect_fn": _florian_banished_earth_trigger}],
    "riptide": [{"event": "on_play", "condition_fn": lambda p, e, s: True, "effect_fn": _riptide_play_from_hand_trigger}],
    "riptide_lurker_of_the_deep": [{"event": "on_play", "condition_fn": lambda p, e, s: True, "effect_fn": _riptide_play_from_hand_trigger}],
}