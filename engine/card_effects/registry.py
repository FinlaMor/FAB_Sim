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
    # Fix 17: Kayo, Underhanded Cheat — "1 weapon zone" is a deckbuilding constraint
    # restricting Kayo to a single weapon slot. This is NOT enforced in-game by
    # the engine (deck validation is external). The activation ability works the same.
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


def _bravo_dominate_apply(attack_card, player, state):
    """Bravo Showstopper: grant Dominate to cost-3+ attack action cards."""
    attack_card.keywords = list(attack_card.keywords or [])
    if "Dominate" not in attack_card.keywords:
        attack_card.keywords.append("Dominate")
    if state.combat and "Dominate" not in (state.combat.keywords or []):
        state.combat.keywords.append("Dominate")

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
    # Fix 1: Bravo, Showstopper — "bravo_showstopper_dominate" persistent effect
    # Until end of turn, attack action cards with cost 3+ gain Dominate.
    "bravo_showstopper_dominate": {
        "persistent": True,
        "condition_fn": lambda attack_card, player, state: (
            "Attack" in (attack_card.types or [])
            and "Action" in (attack_card.types or [])
            and (attack_card.cost or 0) >= 3
        ),
        "apply_fn": _bravo_dominate_apply,
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


# ---------------------------------------------------------------------------
# Hero ability helpers for HERO_TRIGGERS (passive) and HERO_ACTIVATION (active)
# ---------------------------------------------------------------------------

# 1. Rhinar, Reckless Rampage — card_discarded: if 6+{p}, intimidate
def _rhinar_reckless_discard_trigger(player, event, state):
    """Whenever you discard a card with 6+{p} during your action phase, intimidate."""
    if state.active_player != player.player_id:
        return
    data = event.data if isinstance(event.data, dict) else {}
    card = data.get('card')
    if card is None:
        return
    power = card.power if card.power is not None else 0
    if power >= 6:
        from engine.card_effects.keywords import effect_intimidate
        opp_id = 3 - player.player_id
        effect_intimidate(state, opp_id)


# 2. Ira, Scarlet Revenger — attacking: second attack each turn gets +1{p}
def _ira_second_attack_trigger(player, event, state):
    """Your second attack each turn gets +1{p}."""
    count = player.current_turn_effects.count("ira_attack_count")
    player.current_turn_effects.append("ira_attack_count")
    if count == 1:  # This is the second attack (count was 1 before append)
        if state.combat and state.combat.attack_card:
            ac = state.combat.attack_card
            if ac.controller == player.player_id:
                ac.effects = list(getattr(ac, 'effects', []))
                ac.effects.append(("base_power", lambda base: base + 1))


# 3. Bravo, Showstopper — Action {r}{r}: AAs with cost>=3 gain dominate
def _bravo_showstopper_activate(action, player, state):
    """Until end of turn, your attack action cards with cost 3+ gain dominate."""
    player.current_turn_effects.append("bravo_showstopper_dominate")
    player.action_points += 1  # Go again after hero activation


# 4. Kayo, Underhanded Cheat — activation already registered; passive crowd boos
# (kayo_underhanded_cheat activation already in HERO_ACTIVATION_CONDITIONS above)
# Add the passive "whenever booed, create Vigor" trigger
def _kayo_underhanded_boo_trigger(player, event, state):
    """When Kayo is booed (Reviled), create a Vigor token."""
    data = event.data if isinstance(event.data, dict) else {}
    if data.get('player_id') != player.player_id:
        return
    from engine.card_effects.keywords import create_token
    create_token(state, player.player_id, "vigor", 1)


# 5. Dash, I/O — start_of_turn: once per turn, play Mech item from top of deck
def _dash_io_start_of_turn_trigger(player, event, state):
    """Dash I/O: top card always visible + once per turn play Mech item cost 0-1."""
    # "You may look at the top card of your deck at any time."
    # Flag so the state embedder/agent knows top card is public to this player.
    player.class_counters["dash_io_top_card_visible"] = 1

    # "Once per turn, you may play a Mechanologist item with cost 0 or 1 from the
    #  top of your deck as though it were an instant."
    if "dash_io_used" in player.current_turn_effects:
        return
    if not player.deck.cards:
        return
    top = player.deck.cards[0]
    types = top.types or []
    if "Mechanologist" not in types or "Item" not in types:
        return
    if (top.cost or 0) > 1:
        return
    from engine.card_effects.keywords import _ask_player
    choice = _ask_player(state, player.player_id, [True, False],
                         context=f"Dash I/O: play {top.name} (cost {top.cost}) from top of deck?")
    if not choice:
        return
    player.current_turn_effects.append("dash_io_used")
    player.deck.remove(top)
    player.items.add(top)
    # Fix 2: Dash I/O — deduct the item's resource cost after playing from deck
    item_cost = top.cost or 0
    if item_cost > 0:
        player.resources -= item_cost


# 6. Oscilio, Constella Intelligence — activation already registered above


# 7. Kassai of the Golden Sand — Once per Turn Action:
# Cost: banish 2 red and 2 yellow cards from graveyard.
# Effect: next time weapon hits hero this turn, create Gold + go again.
def _kassai_pay_cost(player, state):
    """Pay Kassai cost: banish 2 red and 2 yellow cards from graveyard."""
    from engine.card_effects.keywords import _ask_player
    reds = [c for c in player.graveyard.cards if (c.pitch or 0) == 1]
    yellows = [c for c in player.graveyard.cards if (c.pitch or 0) == 2]
    if len(reds) < 2 or len(yellows) < 2:
        return False
    # Banish 2 reds
    for _ in range(2):
        avail = [c for c in player.graveyard.cards if (c.pitch or 0) == 1]
        if not avail:
            return False
        pick = _ask_player(state, player.player_id, [c.slug for c in avail],
                           context="Kassai: choose a red card from graveyard to banish")
        card = next((c for c in avail if c.slug == pick), avail[0])
        player.graveyard.remove(card)
        player.banished.add(card)
    # Banish 2 yellows
    for _ in range(2):
        avail = [c for c in player.graveyard.cards if (c.pitch or 0) == 2]
        if not avail:
            return False
        pick = _ask_player(state, player.player_id, [c.slug for c in avail],
                           context="Kassai: choose a yellow card from graveyard to banish")
        card = next((c for c in avail if c.slug == pick), avail[0])
        player.graveyard.remove(card)
        player.banished.add(card)
    return True

def _kassai_activate(action, player, state):
    """Next time weapon hits hero this turn, create Gold. Go again (on the activation, not the swing)."""
    player.current_turn_effects.append("kassai_weapon_hit_gold")
    player.current_turn_effects.append("kassai_used")
    # Go Again on the activation itself (grants +1 AP to continue the turn)
    player.action_points += 1


def _kassai_draw_trigger(player, event, state):
    """Fix 3: Kassai — If you've drawn a card this turn, sword attacks cost {r} less to activate."""
    data = event.data if isinstance(event.data, dict) else {}
    if data.get('player_id') != player.player_id:
        return
    if "kassai_sword_cost_reduction" not in player.current_turn_effects:
        player.current_turn_effects.append("kassai_sword_cost_reduction")


def _kassai_weapon_hit_trigger(player, event, state):
    """Kassai: when weapon hits hero and flag is set, create Gold."""
    if "kassai_weapon_hit_gold" not in player.current_turn_effects:
        return
    if not state.combat or state.combat.attacker_id != player.player_id:
        return
    if not state.combat.from_weapon:
        return
    player.current_turn_effects.remove("kassai_weapon_hit_gold")
    from engine.card_effects.keywords import create_token
    create_token(state, player.player_id, "gold", 1)


# 8. Marlynn, Treasure Hunter — passive: when you draw a card during action phase,
#    may put an arrow from hand face-up into arsenal.
def _marlynn_draw_arrow_arsenal_trigger(player, event, state):
    """Whenever you draw a card during action phase, may put arrow from hand into arsenal."""
    if state.active_player != player.player_id:
        return
    data = event.data if isinstance(event.data, dict) else {}
    if data.get('player_id') != player.player_id:
        return
    # Check if player has an Arrow in hand and arsenal is empty
    arrows = [c for c in player.hand.cards if "Arrow" in (c.types or [])]
    if not arrows or player.arsenal.cards:
        return
    from engine.card_effects.keywords import _ask_player
    choice = _ask_player(state, player.player_id, [True, False],
                         context="Marlynn: put an Arrow from hand face-up into arsenal?")
    if not choice:
        return
    options = [c.slug for c in arrows]
    pick = _ask_player(state, player.player_id, options,
                       context="Marlynn: choose an Arrow to put into arsenal")
    card = next((c for c in arrows if c.slug == pick), arrows[0])
    player.hand.remove(card)
    player.arsenal.add(card, is_public=True)


# 9. Ser Boltyn, Breaker of Dawn — attacking: if charged this turn and
#    attack is defended by an attack action card, +1{p}
# Uses class_counters["charged_this_turn"] flag set by the charge keyword in keywords.py.
def _boltyn_charged_attack_bonus(player, event, state):
    """If you've charged this turn, your attacks get +1{p} while defended by an AA card."""
    if not state.combat or state.combat.attacker_id != player.player_id:
        return
    # Check if player has charged this turn via the class counter flag
    if not player.class_counters.get("charged_this_turn", 0):
        return
    ac = state.combat.attack_card
    if ac is None or ac.controller != player.player_id:
        return
    # Check if defended by an attack action card
    for dc in (state.combat.defending_cards or []):
        types = dc.types or []
        if "Attack" in types and "Action" in types:
            ac.effects = list(getattr(ac, 'effects', []))
            ac.effects.append(("base_power", lambda base: base + 1))
            return  # Only apply once


# Fix 4: Ser Boltyn, Breaker of Dawn — Attack Reaction
# "Attack Reaction - Banish a card from Boltyn's soul: Target attack with {p} greater
#  than its base {p} gains go again."
def _boltyn_ar_pay_cost(player, state):
    """Pay Boltyn AR cost: banish a card from soul."""
    if not player.soul.cards:
        return False
    from engine.card_effects.keywords import _ask_player
    options = [c.slug for c in player.soul.cards]
    pick = _ask_player(state, player.player_id, options,
                       context="Boltyn AR: choose a card from soul to banish")
    card = next((c for c in player.soul.cards if c.slug == pick), player.soul.cards[0])
    player.soul.remove(card)
    player.banished.add(card)
    return True


def _boltyn_ar_effect(action, player, state):
    """Boltyn AR effect: target attack with {p} > base {p} gains go again."""
    if not state.combat or not state.combat.attack_card:
        return
    ac = state.combat.attack_card
    if ac.controller != player.player_id:
        return
    # Grant go again
    kw = ac.keywords or []
    if "Go again" not in kw:
        ac.keywords = list(kw) + ["Go again"]
    if "Go again" not in (state.combat.keywords or []):
        state.combat.keywords.append("Go again")


# 10. Fai, Rising Rebellion — Instant {r}{r}{r}: Return Phoenix Flame from graveyard
# Fix 5: "Return a Phoenix Flame from your graveyard to your hand.
#  This ability costs {r} less for each Draconic chain link you control."
def _fai_count_draconic_chain_links(player, state):
    """Count Draconic chain links controlled by this player."""
    count = 0
    for link in (state.chain_links or []):
        if link.attacker_id != player.player_id:
            continue
        lki_types = state.last_known_value(link.attack_slug, "types") if hasattr(state, 'last_known_value') else None
        if lki_types is None and hasattr(state, "card_db") and state.card_db is not None:
            card = state.card_db.get(link.attack_slug)
            lki_types = card.types if card else []
        if "Draconic" in (lki_types or []):
            count += 1
    # Also count the current combat attack if it's Draconic
    if state.combat and state.combat.attack_card and state.combat.attacker_id == player.player_id:
        if "Draconic" in (state.combat.attack_card.types or []):
            count += 1
    return count


def _fai_activate(action, player, state):
    """Return a Phoenix Flame from graveyard to hand."""
    flames = [c for c in player.graveyard.cards if "phoenix_flame" in c.slug]
    if flames:
        flame = flames[0]
        player.graveyard.remove(flame)
        player.hand.add(flame)
    else:
        # Fallback: create one if none in graveyard (shouldn't happen with correct condition)
        from engine.card_effects.keywords import create_token_card
        flame = create_token_card("phoenix_flame", player.player_id)
        player.hand.add(flame)
    player.current_turn_effects.append("fai_used")


# 11. Vynnset, Iron Maiden — start_of_turn: banish from hand, create Runechant
def _vynnset_start_of_turn_trigger(player, event, state):
    """At start of your turn, banish a card from hand. If you do, create Runechant."""
    if state.active_player != player.player_id:
        return
    if not player.hand.cards:
        return
    from engine.card_effects.keywords import _ask_player, effect_banish, create_token
    pick = _ask_player(state, player.player_id, [c.slug for c in player.hand.cards],
                       context="Vynnset: choose a card from hand to banish")
    card = player.hand.find(pick) or player.hand.cards[0]
    player.hand.remove(card)
    player.banished.add(card, is_public=True)
    create_token(state, player.player_id, "runechant", 1)


# Fix 6: Vynnset, Iron Maiden — on_play trigger for Shadow non-attack action
# "Whenever you play a Shadow non-attack action card, you may pay {h}.
#  If you do, the next Runechant effect that would deal damage this turn can't be prevented."
def _vynnset_shadow_naa_trigger(player, event, state):
    """Vynnset: when you play a Shadow non-attack action, may pay 1 life for unpreventable Runechant."""
    data = event.data if isinstance(event.data, dict) else {}
    played_card = data.get('card')
    if played_card is None:
        return
    if played_card.controller != player.player_id:
        return
    types = played_card.types or []
    # Must be Shadow + non-attack action (Action but not Attack)
    if "Shadow" not in types:
        return
    if "Attack" in types:
        return
    if "Action" not in types and "Instant" not in types:
        return
    from engine.card_effects.keywords import _ask_player
    choice = _ask_player(state, player.player_id, [True, False],
                         context="Vynnset: pay 1 life so next Runechant damage can't be prevented?")
    if not choice:
        return
    player.health -= 1
    player.current_turn_effects.append("vynnset_runechant_unpreventable")


# 12. Levia, Shadowborn Abomination — card_banished: track 6+{p} banished this turn
def _levia_banished_trigger(player, event, state):
    """If a card with 6+{p} has been put into your banished zone this turn,
    cards you own lose blood debt."""
    data = event.data if isinstance(event.data, dict) else {}
    card = data.get('card')
    if card is None or card.owner != player.player_id:
        return
    power = card.power if card.power is not None else 0
    if power >= 6:
        player.current_turn_effects.append("levia_blood_debt_removed")


# 13. Jarl Vetreii — on_play: when you play an Ice card, create Frostbite
# Fix 7: Frostbite targets an exposed (empty) equipment zone on the opponent.
# If no exposed zone exists, create as aura token on opponent.
def _jarl_ice_play_trigger(player, event, state):
    """Whenever you play an Ice card, create a Frostbite token in opponent's exposed equipment zone."""
    data = event.data if isinstance(event.data, dict) else {}
    played_card = data.get('card')
    if played_card is None:
        return
    if played_card.controller != player.player_id:
        return
    types = played_card.types or []
    if "Ice" not in types:
        return
    from engine.card_effects.keywords import create_token
    opp_id = 3 - player.player_id
    opp = state.players[opp_id]
    # Check for exposed (empty) equipment zones: head, chest, arms, legs
    exposed_zones = []
    for zone_name in ["head", "chest", "arms", "legs"]:
        zone = getattr(opp, zone_name, None)
        if zone is not None and not zone.cards:
            exposed_zones.append(zone)
    if exposed_zones:
        # Create frostbite token in the first empty equipment zone
        tokens = create_token(state, opp_id, "frostbite", 1)
        if tokens:
            frostbite = tokens[0]
            # Move from default zone (auras) to the exposed equipment zone
            opp.auras.remove(frostbite)
            exposed_zones[0].add(frostbite)
    else:
        # No exposed zones — create as aura token (simplified fallback)
        create_token(state, opp_id, "frostbite", 1)


# 14. Maxx, the Hype Nitro — Action {r}{r}: Create Hyper Driver with 2 steam counters
# Fix 8: Card text also says "Hyper Drivers you control get crank."
# Crank means "Action - tap this: [effect]". This is a passive granting ability
# that is hard to enforce generically without a per-item keyword check.
# Simplified: Hyper Driver steam counter usage already implements the core crank
# mechanic; the "get crank" text is a deckbuilding/rules reminder that Maxx's
# Hyper Drivers inherently have the crank ability. No additional code needed
# since Hyper Drivers are created with steam counters and the crank keyword
# handler in keywords.py already processes them.
def _maxx_activate(action, player, state):
    """Create a Hyper Driver token with 2 steam counters."""
    from engine.card_effects.keywords import create_token
    tokens = create_token(state, player.player_id, "hyper_driver", 1)
    if tokens:
        token = tokens[0]
        counter_key = (token.slug, 'items', 'steam')
        player.counters[counter_key] = player.counters.get(counter_key, 0) + 2
    player.current_turn_effects.append("maxx_used")


# 15. Hala, Bladesaint of the Vow — Action {r}{r}{r}, {t}: Sharpen target sword (+1 counter)
def _hala_activate(action, player, state):
    """Add a +1{p} counter to a weapon (sword). Go again."""
    from engine.card_effects.keywords import _ask_player
    weapons = []
    for zone in [player.weapon1, player.weapon2]:
        for c in getattr(zone, 'cards', []):
            weapons.append(c)
    if not weapons:
        return
    if len(weapons) == 1:
        target = weapons[0]
    else:
        pick = _ask_player(state, player.player_id, [w.slug for w in weapons],
                           context="Hala: choose a weapon to sharpen (+1{p} counter)")
        target = next((w for w in weapons if w.slug == pick), weapons[0])
    counter_key = (target.slug, target.zone or "weapon", "sharpen")
    player.counters[counter_key] = player.counters.get(counter_key, 0) + 1
    # Add a persistent power bonus effect
    target.effects = list(getattr(target, 'effects', []))
    target.effects.append(("base_power", lambda base: base + 1))
    player.action_points += 1  # Go again


# 16. Cindra, Dracai of Retribution
# Passive: whenever you hit a marked hero, create Fealty token
# Fix 9a: Check opp.class_counters.get("marked") instead of opp.marked
def _cindra_hit_marked_trigger(player, event, state):
    """Whenever you hit a marked hero, create a Fealty token."""
    if not state.combat or state.combat.attacker_id != player.player_id:
        return
    opp_id = 3 - player.player_id
    opp = state.players.get(opp_id)
    if opp and opp.class_counters.get("marked", 0) > 0:
        from engine.card_effects.keywords import create_token
        create_token(state, player.player_id, "fealty", 1)

# Cindra activation: Once per Turn Instant {r}{r}{r}: equip up to 2 Draconic daggers from graveyard
def _cindra_activate(action, player, state):
    """Equip up to 2 Draconic daggers from graveyard to weapon zones."""
    from engine.card_effects.keywords import _ask_player
    for _ in range(2):
        daggers = [c for c in player.graveyard.cards
                   if "Dagger" in (c.types or [] if isinstance(c.types, list) else [c.types] if c.types else [])
                   or "Dagger" in (getattr(c, 'subtypes', None) or [])
                   or "dagger" in c.slug.lower()]
        # Also filter for Draconic
        daggers = [c for c in daggers
                   if "Draconic" in (c.types or [] if isinstance(c.types, list) else [c.types] if c.types else [])
                   or "Draconic" in (getattr(c, 'subtypes', None) or [])
                   or "draconic" in c.slug.lower()
                   or "draconic" in (getattr(c, 'name', '') or '').lower()]
        if not daggers:
            break
        options = [c.slug for c in daggers] + ["done"]
        pick = _ask_player(state, player.player_id, options,
                           context="Cindra: choose a Draconic dagger from graveyard to equip")
        if pick == "done":
            break
        card = next((c for c in daggers if c.slug == pick), daggers[0])
        player.graveyard.remove(card)
        # Equip to weapon zone
        if not player.weapon1.cards:
            player.weapon1.add(card)
        elif hasattr(player, 'weapon2') and not player.weapon2.cards:
            player.weapon2.add(card)
        else:
            # No free weapon slot; put back
            player.graveyard.add(card)
            break
    player.current_turn_effects.append("cindra_used")


# ---------------------------------------------------------------------------
# Register hero activations for new heroes
# ---------------------------------------------------------------------------

# 3. Bravo, Showstopper — Action {r}{r}
HERO_ACTIVATION_CONDITIONS["bravo_showstopper"] = {
    "timing": "action",
    "cost": 2,
    "requires_tap": False,
    "condition_fn": lambda player, state: True,
    "effect_fn": _bravo_showstopper_activate,
}

# 7. Kassai of the Golden Sand — Once per Turn Action, banish 2R+2Y from GY
HERO_ACTIVATION_CONDITIONS["kassai_of_the_golden_sand"] = {
    "timing": "action",
    "cost": 0,
    "requires_tap": False,
    "once_per_turn": True,
    "condition_fn": lambda player, state: (
        "kassai_used" not in player.current_turn_effects
        and sum(1 for c in player.graveyard.cards if (c.pitch or 0) == 1) >= 2
        and sum(1 for c in player.graveyard.cards if (c.pitch or 0) == 2) >= 2
    ),
    "pay_cost_fn": _kassai_pay_cost,
    "effect_fn": _kassai_activate,
}

# Fix 4: Ser Boltyn, Breaker of Dawn — Attack Reaction (instant timing, costs soul card)
# "Attack Reaction - Banish a card from Boltyn's soul: Target attack with {p} > base {p} gains go again."
HERO_ACTIVATION_CONDITIONS["ser_boltyn_breaker_of_dawn"] = {
    "timing": "instant",
    "cost": 0,
    "requires_tap": False,
    "condition_fn": lambda player, state: (
        bool(player.soul.cards)
        and state.combat is not None
        and state.combat.attack_card is not None
        and state.combat.attacker_id == player.player_id
        # attack power must be greater than base power
        and (state.combat.attack_power or 0) > (state.combat.attack_card.base_power or 0)
    ),
    "pay_cost_fn": _boltyn_ar_pay_cost,
    "effect_fn": _boltyn_ar_effect,
}
HERO_ACTIVATION_CONDITIONS["ser_boltyn"] = HERO_ACTIVATION_CONDITIONS["ser_boltyn_breaker_of_dawn"]
HERO_ACTIVATION_CONDITIONS["boltyn"] = HERO_ACTIVATION_CONDITIONS["ser_boltyn_breaker_of_dawn"]

# 10. Fai, Rising Rebellion — Once per Turn Instant {r}{r}{r}
def _fai_activation_cost(player, state=None):
    """Fai activation cost: 3 minus Draconic chain links."""
    if state is None:
        return 3
    return max(0, 3 - _fai_count_draconic_chain_links(player, state))


HERO_ACTIVATION_CONDITIONS["fai_rising_rebellion"] = {
    "timing": "instant",
    "cost": _fai_activation_cost,  # Dynamic cost: 3 minus Draconic chain links
    "requires_tap": False,
    "once_per_turn": True,
    "condition_fn": lambda player, state: (
        "fai_used" not in player.current_turn_effects
        and any("phoenix_flame" in c.slug for c in player.graveyard.cards)
    ),
    "effect_fn": _fai_activate,
}
HERO_ACTIVATION_CONDITIONS["fai"] = HERO_ACTIVATION_CONDITIONS["fai_rising_rebellion"]

# 14. Maxx, the Hype Nitro — Once per Turn Action {r}{r} (requires boosted this turn)
HERO_ACTIVATION_CONDITIONS["maxx_the_hype_nitro"] = {
    "timing": "action",
    "cost": 2,
    "requires_tap": False,
    "once_per_turn": True,
    "condition_fn": lambda player, state: (
        "maxx_used" not in player.current_turn_effects
        and bool(player.class_counters.get("boosted_this_turn"))
    ),
    "effect_fn": _maxx_activate,
}
HERO_ACTIVATION_CONDITIONS["maxx_nitro"] = HERO_ACTIVATION_CONDITIONS["maxx_the_hype_nitro"]

# 15. Hala, Bladesaint of the Vow — Action {r}{r}{r}, {t}
HERO_ACTIVATION_CONDITIONS["hala_bladesaint_of_the_vow"] = {
    "timing": "action",
    "cost": 3,
    "requires_tap": True,
    "condition_fn": lambda player, state: not player.hero.tapped,
    "effect_fn": _hala_activate,
}
HERO_ACTIVATION_CONDITIONS["hala"] = HERO_ACTIVATION_CONDITIONS["hala_bladesaint_of_the_vow"]

# 16. Cindra, Dracai of Retribution — Once per Turn Instant {r}{r}{r}
# Fix 9b: Cost reduction per Draconic chain link (reuses Fai's helper)
def _cindra_activation_cost(player, state=None):
    """Cindra activation cost: 3 minus Draconic chain links."""
    if state is None:
        return 3
    return max(0, 3 - _fai_count_draconic_chain_links(player, state))


HERO_ACTIVATION_CONDITIONS["cindra_dracai_of_retribution"] = {
    "timing": "instant",
    "cost": _cindra_activation_cost,  # Dynamic cost: 3 minus Draconic chain links
    "requires_tap": False,
    "once_per_turn": True,
    "condition_fn": lambda player, state: "cindra_used" not in player.current_turn_effects,
    "effect_fn": _cindra_activate,
}
HERO_ACTIVATION_CONDITIONS["cindra"] = HERO_ACTIVATION_CONDITIONS["cindra_dracai_of_retribution"]


# ---------------------------------------------------------------------------
# B2/B3: HERO_TRIGGERS — passive triggered hero abilities
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Hero ability effect functions for 15 new heroes
# ---------------------------------------------------------------------------

# 1. Aurora, Legacy of Tempest — hero activation
# Instant - {r}{r}, {q}, destroy a Lightning Flow: Create Embodiment of Lightning token
def _aurora_pay_cost(player, state):
    """Pay Aurora cost: destroy a Lightning Flow aura."""
    lightning_flows = [c for c in player.auras.cards if "lightning_flow" in c.slug]
    if not lightning_flows:
        return False
    from engine.card_effects.keywords import _ask_player
    if len(lightning_flows) == 1:
        target = lightning_flows[0]
    else:
        pick = _ask_player(state, player.player_id, [c.slug for c in lightning_flows],
                           context="Aurora: choose a Lightning Flow to destroy")
        target = next((c for c in lightning_flows if c.slug == pick), lightning_flows[0])
    player.auras.remove(target)
    player.graveyard.add(target)
    return True

def _aurora_effect(action, player, state):
    """Aurora effect: create Embodiment of Lightning token."""
    from engine.card_effects.keywords import create_token
    create_token(state, player.player_id, "embodiment_of_lightning", 1)

HERO_ACTIVATION_CONDITIONS["aurora_legacy_of_tempest"] = {
    "timing": "instant",
    "cost": 2,
    "requires_tap": True,
    "condition_fn": lambda player, state: (
        not player.hero.tapped
        and any("lightning_flow" in c.slug for c in player.auras.cards)
    ),
    "pay_cost_fn": _aurora_pay_cost,
    "effect_fn": _aurora_effect,
}

# 2. Oscilio, Forked Continuum — hero activation
# Instant - {r}, {q}, destroy a Lightning Flow: Discard a card and create a Ponder token
def _oscilio_forked_pay_cost(player, state):
    """Pay Oscilio Forked cost: destroy a Lightning Flow + discard a card.
    Fix 10: Track if the discarded card was an Instant for play-from-graveyard."""
    lightning_flows = [c for c in player.auras.cards if "lightning_flow" in c.slug]
    if not lightning_flows or not player.hand.cards:
        return False
    from engine.card_effects.keywords import _ask_player
    # Destroy Lightning Flow
    if len(lightning_flows) == 1:
        target = lightning_flows[0]
    else:
        pick = _ask_player(state, player.player_id, [c.slug for c in lightning_flows],
                           context="Oscilio Forked: choose a Lightning Flow to destroy")
        target = next((c for c in lightning_flows if c.slug == pick), lightning_flows[0])
    player.auras.remove(target)
    player.graveyard.add(target)
    # Discard a card — track if it's an Instant
    from engine.card_effects.keywords import effect_discard
    discarded = effect_discard(state, player.player_id, 1)
    if discarded and discarded[0].is_instant:
        # Store on state temporarily so effect_fn can pick it up
        state._oscilio_forked_discarded_instant = discarded[0].slug
    else:
        state._oscilio_forked_discarded_instant = None
    return True

def _oscilio_forked_effect(action, player, state):
    """Oscilio Forked effect: create a Ponder token.
    Fix 10: If an instant was discarded, mark it as playable this turn."""
    from engine.card_effects.keywords import create_token
    create_token(state, player.player_id, "ponder", 1)
    # Check if the card discarded during pay_cost was an Instant
    discarded_slug = getattr(state, '_oscilio_forked_discarded_instant', None)
    if discarded_slug:
        player.current_turn_effects.append("oscilio_play_discarded_instant")
        player.current_turn_effects.append(("oscilio_playable_from_gy", discarded_slug))
        state._oscilio_forked_discarded_instant = None

HERO_ACTIVATION_CONDITIONS["oscilio_forked_continuum"] = {
    "timing": "instant",
    "cost": 1,
    "requires_tap": True,
    "condition_fn": lambda player, state: (
        not player.hero.tapped
        and any("lightning_flow" in c.slug for c in player.auras.cards)
        and bool(player.hand.cards)
    ),
    "pay_cost_fn": _oscilio_forked_pay_cost,
    "effect_fn": _oscilio_forked_effect,
}

# 3. Puffin, Hightail — hero activation
# Action - {t}, destroy a Gold: Create a Golden Cog token
# Passive: second crank each turn creates Gold (simplified: track crank count)
def _puffin_pay_cost(player, state):
    """Pay Puffin cost: destroy a Gold."""
    golds = [c for c in player.items.cards if "Gold" in c.types and "Token" in c.types]
    if not golds:
        return False
    from engine.card_effects.keywords import _ask_player
    if len(golds) == 1:
        gold = golds[0]
    else:
        pick = _ask_player(state, player.player_id, [g.slug for g in golds],
                           context="Puffin: choose a Gold to destroy")
        gold = next((g for g in golds if g.slug == pick), golds[0])
    player.items.remove(gold)
    player.graveyard.add(gold)
    return True

def _puffin_effect(action, player, state):
    """Puffin effect: create Golden Cog token."""
    from engine.card_effects.keywords import create_token
    create_token(state, player.player_id, "golden_cog", 1)

HERO_ACTIVATION_CONDITIONS["puffin_hightail"] = {
    "timing": "action",
    "cost": 0,
    "requires_tap": True,
    "condition_fn": lambda player, state: (
        not player.hero.tapped
        and any("Gold" in c.types and "Token" in c.types for c in player.items.cards)
    ),
    "pay_cost_fn": _puffin_pay_cost,
    "effect_fn": _puffin_effect,
}

# Puffin passive: second crank each turn draws a card
def _puffin_crank_trigger(player, event, state):
    """When a Cog is cranked, track count. On second crank, draw a card."""
    crank_count = player.current_turn_effects.count("cog_cranked")
    if crank_count == 1:  # This is the second crank (first was already appended)
        from engine.card_effects.keywords import effect_draw
        effect_draw(state, player.player_id, 1)

# 4. Tuffnut, Bumbling Hulkster — hero activation
# Instant - {t}: Pitch top card of deck. If 6+ power, crowd cheers; else crowd boos.
def _tuffnut_effect(action, player, state):
    """Tuffnut: pitch top deck card. If 6+ power, crowd cheers."""
    if not player.deck.cards:
        return
    card = player.deck.pop_top()
    if card is None:
        return
    player.pitch.add(card)
    player.resources += card.pitch or 0
    power = card.power if hasattr(card, 'power') and card.power is not None else (card.base_power if hasattr(card, 'base_power') else 0)
    if power is not None and power >= 6:
        player.current_turn_effects.append("crowd_cheers")
        state.event_manager.emit(
            type('Event', (), {'type': 'crowd_cheers', 'data': {'player_id': player.player_id}})(),
            state)


def _tuffnut_crowd_cheers_trigger(player, event, state):
    """Tuffnut: when crowd cheers, create a Toughness token."""
    data = event.data if isinstance(event.data, dict) else {}
    if data.get('player_id') != player.player_id:
        return
    from engine.card_effects.keywords import create_token
    create_token(state, player.player_id, "toughness", 1)

HERO_ACTIVATION_CONDITIONS["tuffnut_bumbling_hulkster"] = {
    "timing": "instant",
    "cost": 0,
    "requires_tap": True,
    "condition_fn": lambda player, state: (
        not player.hero.tapped and bool(player.deck.cards)
    ),
    "effect_fn": _tuffnut_effect,
}

# 5. Arakni, Marionette — passive on attacking
# Attacks with stealth attacking a marked hero get +1{p} and on-hit: defender puts card from hand on top of deck
def _arakni_marionette_attack_trigger(player, event, state):
    """Arakni Marionette: stealth attacks vs marked hero get +1{p} + on-hit hand-to-top-deck."""
    if not state.combat or not state.combat.attack_card:
        return
    if state.combat.attacker_id != player.player_id:
        return
    combat = state.combat
    is_stealth = "Stealth" in (combat.keywords or [])
    if not is_stealth:
        return
    opp = state.players[3 - player.player_id]
    is_marked = opp.class_counters.get("marked", 0) > 0
    if not is_marked:
        return
    # +1{p}
    combat.attack_card.effects = list(getattr(combat.attack_card, 'effects', []))
    combat.attack_card.effects.append(("base_power", lambda base: base + 1))
    # On-hit: this attack gains go again
    player.current_turn_effects.append("arakni_marionette_on_hit_go_again")

def _arakni_marionette_hit_trigger(player, event, state):
    """Arakni Marionette on-hit: attack gains go again."""
    if "arakni_marionette_on_hit_go_again" not in player.current_turn_effects:
        return
    player.current_turn_effects.remove("arakni_marionette_on_hit_go_again")
    if state.combat and state.combat.attack_card:
        ac = state.combat.attack_card
        kw = ac.keywords or []
        if "Go again" not in kw:
            ac.keywords = list(kw) + ["Go again"]
        if "Go again" not in (state.combat.keywords or []):
            state.combat.keywords.append("Go again")


# Fix 11: Arakni, Marionette — end phase trigger
# "At the beginning of your end phase, if an opponent is marked, you become
#  a random Agent of Chaos." Full hero transformation is very complex.
# Simplified: if opponent is marked at end phase, grant a bonus for next turn
# (+1{p} on first attack OR go again on first attack next turn).
def _arakni_marionette_end_phase_trigger(player, event, state):
    """Arakni Marionette: at end phase, if opponent marked, gain Agent of Chaos bonus."""
    if state.active_player != player.player_id:
        return
    opp = state.players[3 - player.player_id]
    if opp.class_counters.get("marked", 0) <= 0:
        return
    # Simplified Agent of Chaos: grant +1{p} on all attacks next turn
    # Use next_turn_effects if available, otherwise current_turn_effects
    # (current_turn_effects are cleared at start of turn, so use class_counters)
    player.class_counters["agent_of_chaos_bonus"] = 1

# 6. Gravy Bones, Shipwrecked Looter — hero activation + passive
# Instant - {t}, destroy Gold: Draw a card, then discard a card.
# Passive: if blue card put into graveyard this turn, Pirate attacks get go again.
def _gravy_pay_cost(player, state):
    """Pay Gravy Bones cost: destroy a Gold."""
    golds = [c for c in player.items.cards if "Gold" in c.types and "Token" in c.types]
    if not golds:
        return False
    from engine.card_effects.keywords import _ask_player
    if len(golds) == 1:
        gold = golds[0]
    else:
        pick = _ask_player(state, player.player_id, [g.slug for g in golds],
                           context="Gravy Bones: choose a Gold to destroy")
        gold = next((g for g in golds if g.slug == pick), golds[0])
    player.items.remove(gold)
    player.graveyard.add(gold)
    return True

def _gravy_effect(action, player, state):
    """Gravy Bones effect: draw a card, then discard a card."""
    from engine.card_effects.keywords import effect_draw, effect_discard
    effect_draw(state, player.player_id, 1)
    effect_discard(state, player.player_id, 1)

HERO_ACTIVATION_CONDITIONS["gravy_bones_shipwrecked_looter"] = {
    "timing": "instant",
    "cost": 0,
    "requires_tap": True,
    "condition_fn": lambda player, state: (
        not player.hero.tapped
        and any("Gold" in c.types and "Token" in c.types for c in player.items.cards)
    ),
    "pay_cost_fn": _gravy_pay_cost,
    "effect_fn": _gravy_effect,
}

# Passive: if blue in graveyard this turn, may play cards with watery grave from graveyard.
# Fix 12: When blue-in-graveyard flag is set, also set gravy_watery_grave_active
# for future action legality expansion (allowing watery_grave cards to be played from GY).
def _gravy_graveyard_trigger(player, event, state):
    """Track when blue cards enter the graveyard this turn (enables watery grave plays)."""
    data = event.data if isinstance(event.data, dict) else {}
    card = data.get('card')
    if card is None:
        return
    if card.owner != player.player_id:
        return
    if (card.pitch or 0) == 3:  # blue pitch = 3
        if "blue_entered_gy_this_turn" not in player.current_turn_effects:
            player.current_turn_effects.append("blue_entered_gy_this_turn")
        if "gravy_watery_grave_active" not in player.current_turn_effects:
            player.current_turn_effects.append("gravy_watery_grave_active")

# 7. Lyath Goldmane, Vile Savant — hero activation
# Instant - {r}{r}, {t}: The crowd boos you. Defending action cards you control get +1{d} this turn.
def _lyath_effect(action, player, state):
    """Lyath: crowd boos you, defending action cards get +1{d} this turn."""
    from engine.card_effects.keywords import effect_crowd_boos
    effect_crowd_boos(state, player.player_id)
    player.current_turn_effects.append("lyath_defending_actions_+1d")

def _lyath_crowd_boos_trigger(player, event, state):
    """Lyath: when crowd boos you, create a Might token."""
    data = event.data if isinstance(event.data, dict) else {}
    if data.get('player_id') != player.player_id:
        return
    from engine.card_effects.keywords import create_token
    create_token(state, player.player_id, "might", 1)

HERO_ACTIVATION_CONDITIONS["lyath_goldmane_vile_savant"] = {
    "timing": "instant",
    "cost": 2,
    "requires_tap": True,
    "condition_fn": lambda player, state: not player.hero.tapped,
    "effect_fn": _lyath_effect,
}

# 8. Pleiades, Superstar — hero activation
# Instant - {t}, remove suspense counter from aura: put aura from hand into arena with suspense counter
def _pleiades_pay_cost(player, state):
    """Pay Pleiades cost: remove a suspense counter from an aura."""
    from engine.card_effects.keywords import _ask_player
    auras_with_suspense = [c for c in player.auras.cards
                           if player.counters.get((c.slug, 'auras', 'suspense'), 0) > 0]
    if not auras_with_suspense:
        return False
    if len(auras_with_suspense) == 1:
        target = auras_with_suspense[0]
    else:
        pick = _ask_player(state, player.player_id, [c.slug for c in auras_with_suspense],
                           context="Pleiades: choose an aura to remove a suspense counter from")
        target = next((c for c in auras_with_suspense if c.slug == pick), auras_with_suspense[0])
    key = (target.slug, 'auras', 'suspense')
    player.counters[key] = max(0, player.counters.get(key, 0) - 1)
    return True

def _pleiades_effect(action, player, state):
    """Pleiades: put a suspense counter on an aura with Suspense you control.
    Fix 13: Filter target auras to only those with Suspense keyword/type."""
    from engine.card_effects.keywords import _ask_player
    # Filter auras to those with Suspense keyword or that already have suspense counters
    auras = [c for c in player.auras.cards
             if "Suspense" in (c.keywords or [])
             or "Suspense" in (c.types or [])
             or player.counters.get((c.slug, 'auras', 'suspense'), 0) > 0]
    if not auras:
        # Fallback to all auras if none have Suspense explicitly
        auras = list(player.auras.cards)
    if not auras:
        return
    options = [c.slug for c in auras]
    if len(options) == 1:
        pick = options[0]
    else:
        pick = _ask_player(state, player.player_id, options,
                           context="Pleiades: choose a Suspense aura to put a suspense counter on")
    card = next((c for c in auras if c.slug == pick), auras[0])
    key = (card.slug, 'auras', 'suspense')
    player.counters[key] = player.counters.get(key, 0) + 1

def _pleiades_crowd_cheers_trigger(player, event, state):
    """Pleiades: when crowd cheers, create a Confidence token."""
    data = event.data if isinstance(event.data, dict) else {}
    if data.get('player_id') != player.player_id:
        return
    from engine.card_effects.keywords import create_token
    create_token(state, player.player_id, "confidence", 1)

HERO_ACTIVATION_CONDITIONS["pleiades_superstar"] = {
    "timing": "instant",
    "cost": 0,
    "requires_tap": True,
    "pay_cost_fn": _pleiades_pay_cost,
    "condition_fn": lambda player, state: (
        not player.hero.tapped
        # Must have an aura with a suspense counter to remove
        and any(player.counters.get((c.slug, 'auras', 'suspense'), 0) > 0
                for c in player.auras.cards)
    ),
    "effect_fn": _pleiades_effect,
}

# 9. Prism, Awakener of Sol — passive on soul entry
# When Herald card enters soul during action phase, search deck for a Figment
def _prism_awakener_soul_trigger(player, event, state):
    """Prism: when Herald enters soul, search deck for Figment."""
    data = event.data if isinstance(event.data, dict) else {}
    card = data.get('card')
    if card is None:
        return
    if card.owner != player.player_id:
        return
    # Check for "Herald" in card name
    card_name = getattr(card, 'name', '') or ''
    if "herald" not in card_name.lower():
        return
    # Search for Figment
    from engine.card_effects.keywords import _ask_player
    figments = [c for c in player.deck.cards if "Figment" in (c.types or [])]
    if not figments:
        return
    options = [c.slug for c in figments] + ["none"]
    pick = _ask_player(state, player.player_id, options,
                       context="Prism Awakener: choose a Figment to search for")
    if pick == "none":
        return
    target = next((c for c in figments if c.slug == pick), figments[0])
    player.deck.remove(target)
    player.permanents.add(target)  # Put figment into arena (permanents zone)
    from engine.card_effects.keywords import effect_shuffle
    effect_shuffle(state, player.player_id)

# Fix 14: Prism, Awakener of Sol — Awaken activation
# "Once per Turn Instant - {r}{r}, banish a card from Prism's soul: Awaken target figment you control."
def _prism_awaken_pay_cost(player, state):
    """Pay Prism Awaken cost: banish a card from soul."""
    if not player.soul.cards:
        return False
    from engine.card_effects.keywords import _ask_player
    options = [c.slug for c in player.soul.cards]
    pick = _ask_player(state, player.player_id, options,
                       context="Prism Awaken: choose a card from soul to banish")
    card = next((c for c in player.soul.cards if c.slug == pick), player.soul.cards[0])
    player.soul.remove(card)
    player.banished.add(card)
    return True


def _prism_awaken_effect(action, player, state):
    """Prism Awaken effect: Awaken target figment you control."""
    from engine.card_effects.keywords import _ask_player, effect_awaken, FIGMENT_TO_ANGEL
    figments = [c for c in player.permanents.cards
                if "Figment" in (c.types or []) and c.slug in FIGMENT_TO_ANGEL]
    if not figments:
        return
    if len(figments) == 1:
        target = figments[0]
    else:
        options = [c.slug for c in figments]
        pick = _ask_player(state, player.player_id, options,
                           context="Prism Awaken: choose a Figment to awaken")
        target = next((c for c in figments if c.slug == pick), figments[0])
    effect_awaken(state, player.player_id, target)


HERO_ACTIVATION_CONDITIONS["prism_awakener_of_sol"] = {
    "timing": "instant",
    "cost": 2,
    "requires_tap": False,
    "once_per_turn": True,
    "condition_fn": lambda player, state: (
        "prism_awaken_used" not in player.current_turn_effects
        and bool(player.soul.cards)
        and any("Figment" in (c.types or []) for c in player.permanents.cards)
    ),
    "pay_cost_fn": _prism_awaken_pay_cost,
    "effect_fn": _prism_awaken_effect,
}

# 10. Teklovossen, Esteemed Magnate — hero activation
# Once per Turn Instant - {r}{r}{r}: play next Evo this turn as instant + draw a card.
# Fix 15: "You may play Evos from your banished zone." — set flag at start of turn.
def _teklovossen_start_of_turn_trigger(player, event, state):
    """Teklovossen: at start of turn, set flag allowing Evo plays from banished zone."""
    if state.active_player != player.player_id:
        return
    player.current_turn_effects.append("teklovossen_play_from_banish")


def _teklovossen_effect(action, player, state):
    """Teklovossen: next Evo this turn plays as instant. When you do, draw a card."""
    # The draw happens when the next Evo is actually played, not immediately.
    player.current_turn_effects.append("teklovossen_evo_instant_draw")
    player.current_turn_effects.append("teklovossen_used")

HERO_ACTIVATION_CONDITIONS["teklovossen_esteemed_magnate"] = {
    "timing": "instant",
    "cost": 3,
    "requires_tap": False,
    "once_per_turn": True,
    "condition_fn": lambda player, state: "teklovossen_used" not in player.current_turn_effects,
    "effect_fn": _teklovossen_effect,
}

# 11. Uzuri, Switchblade — Once per Turn Attack Reaction
# Cost: banish a card from hand face down.
# Effect: turn it face up. If it's an AA with cost <=2, put the stealth attacking card
# on bottom of deck, put the banished card onto the combat chain as the attacking card.
# If it's NOT an AA cost <=2, the card just stays banished face-up.
def _uzuri_attack_trigger(player, event, state):
    """Uzuri: once per turn AR — banish from hand face-down, reveal, maybe swap."""
    if "uzuri_switchblade_used" in player.current_turn_effects:
        return
    if not state.combat or state.combat.attacker_id != player.player_id:
        return
    # Must be a stealth attack
    if "Stealth" not in (state.combat.keywords or []):
        return
    if not player.hand.cards:
        return
    from engine.card_effects.keywords import _ask_player
    # Player can always banish ANY card from hand (not just AAs)
    choice = _ask_player(state, player.player_id, [True, False],
                         context="Uzuri: banish a card from hand face-down? (may swap into combat)")
    if not choice:
        return
    options = [c.slug for c in player.hand.cards]
    pick = _ask_player(state, player.player_id, options,
                       context="Uzuri: choose a card from hand to banish face-down")
    card = next((c for c in player.hand.cards if c.slug == pick), player.hand.cards[0])
    player.hand.remove(card)
    player.current_turn_effects.append("uzuri_switchblade_used")

    # Banish face-down (opponent gets response window here in full rules)
    card.face_down = True
    player.banished.add(card)

    # Turn face-up and check: is it an Attack Action with cost <= 2?
    card.face_down = False
    is_aa = "Attack" in (card.types or []) and "Action" in (card.types or [])
    cost_ok = (card.cost or 0) <= 2
    if is_aa and cost_ok:
        # Swap: put current stealth attack on bottom of deck, banished card becomes attack
        old_attack = state.combat.attack_card
        if old_attack:
            player.deck.cards.append(old_attack)
            old_attack.zone = "deck"
        player.banished.remove(card)
        state.combat.attack_card = card
        card.controller = player.player_id
        state.combat.base_attack_power = card.power or card.base_power or 0
    # If not AA cost<=2, card stays banished face-up (no swap)

# 12. Zyggy Starlight — hero activation
# Instant - {r}{r}, {q}: banish a Lightning aura with no holo counters, return it with a holo counter.
def _zyggy_pay_cost(player, state):
    """Zyggy cost: destroy a Lightning Flow you control."""
    flows = [c for c in player.auras.cards if "lightning_flow" in c.slug]
    if not flows:
        return False
    flow = flows[0]
    player.auras.remove(flow)
    player.graveyard.add(flow)
    return True

def _zyggy_effect(action, player, state):
    """Zyggy: banish a Lightning aura without holo counters, return it with one."""
    from engine.card_effects.keywords import _ask_player
    lightning_auras = [c for c in player.auras.cards
                       if "Lightning" in (c.types or [])
                       and player.counters.get((c.slug, 'auras', 'holo'), 0) == 0]
    if not lightning_auras:
        return
    if len(lightning_auras) == 1:
        target = lightning_auras[0]
    else:
        options = [c.slug for c in lightning_auras]
        pick = _ask_player(state, player.player_id, options,
                           context="Zyggy: choose a Lightning aura to banish and return with holo counter")
        target = next((c for c in lightning_auras if c.slug == pick), lightning_auras[0])
    # Banish and return with holo counter
    player.auras.remove(target)
    player.banished.add(target)
    player.banished.remove(target)
    player.auras.add(target)
    key = (target.slug, 'auras', 'holo')
    player.counters[key] = player.counters.get(key, 0) + 1

HERO_ACTIVATION_CONDITIONS["zyggy_starlight"] = {
    "timing": "instant",
    "cost": 2,
    "requires_tap": True,
    "pay_cost_fn": _zyggy_pay_cost,
    "condition_fn": lambda player, state: (
        not player.hero.tapped
        # Need a Lightning Flow to destroy AND a Lightning aura without holo counters
        and any("lightning_flow" in c.slug for c in player.auras.cards)
        and any("Lightning" in (c.types or [])
                and "lightning_flow" not in c.slug
                and player.counters.get((c.slug, 'auras', 'holo'), 0) == 0
                for c in player.auras.cards)
    ),
    "effect_fn": _zyggy_effect,
}

# 13. Arakni (5lp3d 7hru 7h3 cr4x) — passive
# First attack with stealth each turn gets go again
def _arakni_slipped_attack_trigger(player, event, state):
    """Arakni Slipped: first stealth attack each turn gets go again."""
    if "arakni_slipped_stealth_ga_used" in player.current_turn_effects:
        return
    if not state.combat or state.combat.attacker_id != player.player_id:
        return
    if "Stealth" not in (state.combat.keywords or []):
        return
    ac = state.combat.attack_card
    if ac is None:
        return
    kw = ac.keywords or []
    if "Go again" not in kw:
        ac.keywords = list(kw) + ["Go again"]
    if "Go again" not in (state.combat.keywords or []):
        state.combat.keywords.append("Go again")
    player.current_turn_effects.append("arakni_slipped_stealth_ga_used")

# 14. Arakni, Huntsman — passive on play
# Whenever you play a card with contract, look at top card of opponent's deck; may put it on bottom.
def _arakni_huntsman_play_trigger(player, event, state):
    """Arakni Huntsman: when playing a contract card, look at top of opponent deck; may put on bottom."""
    data = event.data if isinstance(event.data, dict) else {}
    played_card = data.get('card')
    if played_card is None:
        return
    if played_card.controller != player.player_id:
        return
    keywords = played_card.keywords or []
    has_contract = any("Contract" in str(k) or "contract" in str(k) for k in keywords)
    if not has_contract:
        # Also check types
        types = played_card.types or []
        has_contract = "Contract" in types
    if not has_contract:
        return
    # Look at top of opponent's deck
    opp_id = 3 - player.player_id
    opp = state.players[opp_id]
    if not opp.deck.cards:
        return
    from engine.card_effects.keywords import _ask_player, effect_look_top
    effect_look_top(state, opp_id, 1)
    # Offer to put it on the bottom
    top_card = opp.deck.cards[0] if opp.deck.cards else None
    if top_card is None:
        return
    choice = _ask_player(state, player.player_id, [True, False],
                         context=f"Arakni Huntsman: put opponent's top card ({top_card.slug}) on bottom of their deck?")
    if choice:
        opp.deck.remove(top_card)
        opp.deck.add_bottom(top_card)

# 15. Fang, Dracai of Blades — passive hit trigger
# When you hit a marked hero, create Fealty token. If 3+ Fealty tokens, dagger attacks cost {r} less.
# Fix 16: Always count Fealty and set/clear the flag as a continuous effect.
def _fang_count_fealty(player):
    """Count Fealty tokens across auras and items zones."""
    count = sum(1 for c in player.auras.cards if "fealty" in c.slug.lower())
    count += sum(1 for c in player.items.cards if "fealty" in c.slug.lower())
    return count


def _fang_hit_trigger(player, event, state):
    """Fang: on hit vs marked hero, create Fealty. Check 3+ Fealty for dagger cost reduction."""
    if not state.combat or state.combat.attacker_id != player.player_id:
        return
    opp = state.players[3 - player.player_id]
    if opp.class_counters.get("marked", 0) <= 0:
        return
    from engine.card_effects.keywords import create_token
    create_token(state, player.player_id, "fealty", 1)
    # Recheck Fealty count after creating the new token
    fealty_count = _fang_count_fealty(player)
    if fealty_count >= 3:
        if "fang_dagger_cost_0" not in player.current_turn_effects:
            player.current_turn_effects.append("fang_dagger_cost_0")
    else:
        # Clear flag if Fealty dropped below 3 (e.g., tokens were destroyed)
        while "fang_dagger_cost_0" in player.current_turn_effects:
            player.current_turn_effects.remove("fang_dagger_cost_0")





# Agent 2 hero activations are registered inside their effect functions above.

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
    # 1. Rhinar, Reckless Rampage — discard 6+{p} during action phase -> intimidate
    "rhinar_reckless_rampage": [{"event": "card_discarded", "condition_fn": lambda p, e, s: True, "effect_fn": _rhinar_reckless_discard_trigger}],
    "rhinar": [{"event": "card_discarded", "condition_fn": lambda p, e, s: True, "effect_fn": _rhinar_reckless_discard_trigger}],
    # 2. Ira, Scarlet Revenger — second attack each turn +1{p}
    "ira_scarlet_revenger": [{"event": "attacking", "condition_fn": lambda p, e, s: True, "effect_fn": _ira_second_attack_trigger}],
    "ira": [{"event": "attacking", "condition_fn": lambda p, e, s: True, "effect_fn": _ira_second_attack_trigger}],
    # 3. Bravo, Showstopper — passive component: none (activation only)
    "bravo_showstopper": [],
    # 4. Kayo, Underhanded Cheat — passive: when booed, create Vigor
    "kayo_underhanded_cheat": [{"event": "crowd_boos", "condition_fn": lambda p, e, s: True, "effect_fn": _kayo_underhanded_boo_trigger}],
    "kayo": [{"event": "crowd_boos", "condition_fn": lambda p, e, s: True, "effect_fn": _kayo_underhanded_boo_trigger}],
    # 5. Dash, I/O — once per turn, play Mech item from top of deck
    "dash_io": [{"event": "start_of_turn", "condition_fn": lambda p, e, s: s.active_player == p.player_id, "effect_fn": _dash_io_start_of_turn_trigger}],
    "dash": [{"event": "start_of_turn", "condition_fn": lambda p, e, s: s.active_player == p.player_id, "effect_fn": _dash_io_start_of_turn_trigger}],
    # 6. Oscilio, Constella Intelligence — activation only (registered above)
    "oscilio_constella_intelligence": [],
    # 7. Kassai of the Golden Sand — weapon hit gold trigger + card draw cost reduction
    "kassai_of_the_golden_sand": [
        {"event": "hit", "condition_fn": lambda p, e, s: True, "effect_fn": _kassai_weapon_hit_trigger},
        {"event": "card_draw", "condition_fn": lambda p, e, s: True, "effect_fn": _kassai_draw_trigger},
    ],
    "kassai": [
        {"event": "hit", "condition_fn": lambda p, e, s: True, "effect_fn": _kassai_weapon_hit_trigger},
        {"event": "card_draw", "condition_fn": lambda p, e, s: True, "effect_fn": _kassai_draw_trigger},
    ],
    # 8. Marlynn, Treasure Hunter — passive: card draw during action phase -> arrow to arsenal
    "marlynn_treasure_hunter": [{"event": "card_draw", "condition_fn": lambda p, e, s: True, "effect_fn": _marlynn_draw_arrow_arsenal_trigger}],
    "marlynn": [{"event": "card_draw", "condition_fn": lambda p, e, s: True, "effect_fn": _marlynn_draw_arrow_arsenal_trigger}],
    # 9. Ser Boltyn, Breaker of Dawn — attacks get +1{p} if charged & defended by AA
    "ser_boltyn_breaker_of_dawn": [{"event": "defend", "condition_fn": lambda p, e, s: True, "effect_fn": _boltyn_charged_attack_bonus}],
    "ser_boltyn": [{"event": "defend", "condition_fn": lambda p, e, s: True, "effect_fn": _boltyn_charged_attack_bonus}],
    "boltyn": [{"event": "defend", "condition_fn": lambda p, e, s: True, "effect_fn": _boltyn_charged_attack_bonus}],
    # 10. Fai, Rising Rebellion — activation only (registered above)
    "fai_rising_rebellion": [],
    "fai": [],
    # 11. Vynnset, Iron Maiden — start of turn + Shadow non-attack action trigger (Fix 6)
    "vynnset_iron_maiden": [
        {"event": "start_of_turn", "condition_fn": lambda p, e, s: s.active_player == p.player_id, "effect_fn": _vynnset_start_of_turn_trigger},
        {"event": "on_play", "condition_fn": lambda p, e, s: True, "effect_fn": _vynnset_shadow_naa_trigger},
    ],
    "vynnset": [
        {"event": "start_of_turn", "condition_fn": lambda p, e, s: s.active_player == p.player_id, "effect_fn": _vynnset_start_of_turn_trigger},
        {"event": "on_play", "condition_fn": lambda p, e, s: True, "effect_fn": _vynnset_shadow_naa_trigger},
    ],
    # 12. Levia, Shadowborn Abomination — card_banished: track 6+{p} to lose blood debt
    "levia_shadowborn_abomination": [{"event": "card_banished", "condition_fn": lambda p, e, s: True, "effect_fn": _levia_banished_trigger}],
    "levia": [{"event": "card_banished", "condition_fn": lambda p, e, s: True, "effect_fn": _levia_banished_trigger}],
    # 13. Jarl Vetreii — on_play: Ice card -> create Frostbite on opponent
    "jarl_vetreii": [{"event": "on_play", "condition_fn": lambda p, e, s: True, "effect_fn": _jarl_ice_play_trigger}],
    "jarl": [{"event": "on_play", "condition_fn": lambda p, e, s: True, "effect_fn": _jarl_ice_play_trigger}],
    # 14. Maxx, the Hype Nitro — activation only
    "maxx_the_hype_nitro": [],
    "maxx_nitro": [],
    "maxx": [],
    # 15. Hala, Bladesaint of the Vow — activation only
    "hala_bladesaint_of_the_vow": [],
    "hala": [],
    # 16. Cindra, Dracai of Retribution — passive: hit marked hero -> Fealty token
    "cindra_dracai_of_retribution": [{"event": "hit", "condition_fn": lambda p, e, s: True, "effect_fn": _cindra_hit_marked_trigger}],
    "cindra": [{"event": "hit", "condition_fn": lambda p, e, s: True, "effect_fn": _cindra_hit_marked_trigger}],
    # 3. Puffin, Hightail — passive crank trigger
    "puffin_hightail": [{"event": "cog_cranked", "condition_fn": lambda p, e, s: True, "effect_fn": _puffin_crank_trigger}],
    # 5. Arakni, Marionette — stealth+mark attack buff + on-hit + end phase Agent of Chaos (Fix 11)
    "arakni_marionette": [
        {"event": "attack_declared", "condition_fn": lambda p, e, s: True, "effect_fn": _arakni_marionette_attack_trigger},
        {"event": "hit", "condition_fn": lambda p, e, s: True, "effect_fn": _arakni_marionette_hit_trigger},
        {"event": "end_phase", "condition_fn": lambda p, e, s: True, "effect_fn": _arakni_marionette_end_phase_trigger},
    ],
    # 6. Gravy Bones — blue graveyard tracking (enables watery grave plays)
    "gravy_bones_shipwrecked_looter": [
        {"event": "card_enters_graveyard", "condition_fn": lambda p, e, s: True, "effect_fn": _gravy_graveyard_trigger},
    ],
    # 9. Prism, Awakener of Sol — Herald enters soul
    "prism_awakener_of_sol": [{"event": "card_enters_soul", "condition_fn": lambda p, e, s: True, "effect_fn": _prism_awakener_soul_trigger}],
    # 11. Uzuri, Switchblade — attack reaction (fires during combat)
    "uzuri_switchblade": [{"event": "attacking", "condition_fn": lambda p, e, s: True, "effect_fn": _uzuri_attack_trigger}],
    # 13. Arakni (5lp3d) — first stealth attack gets go again
    "arakni_5lp3d_7hru_7h3_cr4x": [{"event": "attack_declared", "condition_fn": lambda p, e, s: True, "effect_fn": _arakni_slipped_attack_trigger}],
    # 14. Arakni, Huntsman — contract play trigger
    "arakni_huntsman": [{"event": "on_play", "condition_fn": lambda p, e, s: True, "effect_fn": _arakni_huntsman_play_trigger}],
    # 15. Fang, Dracai of Blades — hit vs marked hero
    "fang_dracai_of_blades": [{"event": "hit", "condition_fn": lambda p, e, s: True, "effect_fn": _fang_hit_trigger}],
    # Tuffnut, Bumbling Hulkster — crowd cheers -> create Toughness token
    "tuffnut_bumbling_hulkster": [{"event": "crowd_cheers", "condition_fn": lambda p, e, s: True, "effect_fn": _tuffnut_crowd_cheers_trigger}],
    "tuffnut": [{"event": "crowd_cheers", "condition_fn": lambda p, e, s: True, "effect_fn": _tuffnut_crowd_cheers_trigger}],
    # Lyath Goldmane, Vile Savant — crowd boos -> create Might token
    "lyath_goldmane_vile_savant": [{"event": "crowd_boos", "condition_fn": lambda p, e, s: True, "effect_fn": _lyath_crowd_boos_trigger}],
    "lyath_goldmane": [{"event": "crowd_boos", "condition_fn": lambda p, e, s: True, "effect_fn": _lyath_crowd_boos_trigger}],
    "lyath": [{"event": "crowd_boos", "condition_fn": lambda p, e, s: True, "effect_fn": _lyath_crowd_boos_trigger}],
    # Pleiades, Superstar — crowd cheers -> create Confidence token
    "pleiades_superstar": [{"event": "crowd_cheers", "condition_fn": lambda p, e, s: True, "effect_fn": _pleiades_crowd_cheers_trigger}],
    "pleiades": [{"event": "crowd_cheers", "condition_fn": lambda p, e, s: True, "effect_fn": _pleiades_crowd_cheers_trigger}],
    # Fix 15: Teklovossen — start of turn: set play-from-banish flag for Evos
    "teklovossen_esteemed_magnate": [{"event": "start_of_turn", "condition_fn": lambda p, e, s: s.active_player == p.player_id, "effect_fn": _teklovossen_start_of_turn_trigger}],
    "teklovossen": [{"event": "start_of_turn", "condition_fn": lambda p, e, s: s.active_player == p.player_id, "effect_fn": _teklovossen_start_of_turn_trigger}],
}