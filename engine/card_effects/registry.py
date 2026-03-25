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

# ---------------------------------------------------------------------------
# Hero ability helper functions for new entries
# ---------------------------------------------------------------------------

def _bravo_dominate_effect(action, player, state):
    """Bravo: Until end of turn, attack action cards with cost 3+ get dominate. Go again."""
    player.current_turn_effects.append("bravo_dominate_cost3")
    player.action_points += 1


def _bravo_flattering_effect(action, player, state):
    """Bravo, Flattering Showman: Turn face-down arsenal face-up. If crush, +2 power and dominate. Go again."""
    if player.arsenal.top is not None and not player.arsenal_face_up:
        player.arsenal_face_up = True
        card = player.arsenal.top
        if "Crush" in (card.card_keywords or []):
            player.current_turn_effects.append("bravo_flattering_crush_bonus")
    player.action_points += 1


def _dorinthea_weapon_hit_effect(action, player, state):
    """Dorinthea: When weapon hits, may attack additional time with it this turn."""
    player.current_turn_effects.append("dorinthea_extra_weapon_attack")


def _chane_soul_shackle_effect(action, player, state):
    """Chane: Create Soul Shackle token, next Runeblade/Shadow action gets go again. Go again."""
    from engine.card_effects.keywords import create_token_card
    token = create_token_card("soul_shackle", player.player_id)
    player.auras.add(token)
    player.current_turn_effects.append("chane_next_action_go_again")
    player.action_points += 1


def _chane_pay_cost(player, state):
    """Chane's cost: Create a Soul Shackle token (the token IS the cost)."""
    return True  # Token creation is the cost+effect combined


def _azalea_arsenal_swap_effect(action, player, state):
    """Azalea: Put arsenal card on bottom of deck, put top of deck face-up into arsenal."""
    if player.arsenal.top is not None:
        old_card = player.arsenal.top
        player.arsenal.remove(old_card)
        player.deck.add_bottom(old_card)
        if len(player.deck.cards) > 0:
            new_card = player.deck.draw_top()
            player.arsenal.add(new_card)
            player.arsenal_face_up = True
            # If it's an arrow, it gets +1 power this turn
            if "Arrow" in (new_card.types or []):
                player.current_turn_effects.append("azalea_arrow_bonus")


def _aurora_create_embodiment_effect(action, player, state):
    """Aurora: Create an Embodiment of Lightning token."""
    from engine.card_effects.keywords import create_token_card
    token = create_token_card("embodiment_of_lightning", player.player_id)
    player.auras.add(token)
    player.current_turn_effects.append("aurora_used")


def _kayo_strongarm_effect(action, player, state):
    """Kayo, Strongarm: Same as Kayo — set target attack action card's base power to 6."""
    _kayo_set_6_base_power(action, player, state)


def _lexi_arsenal_faceup_effect(action, player, state):
    """Lexi: Turn face-down arsenal card face-up. If it's an arrow, it gets +1 power. Go again."""
    if player.arsenal.top is not None and not player.arsenal_face_up:
        player.arsenal_face_up = True
        card = player.arsenal.top
        if "Arrow" in (card.types or []):
            player.current_turn_effects.append("lexi_arrow_bonus")
    player.action_points += 1


def _fai_phoenix_flame_effect(action, player, state):
    """Fai: Return a Phoenix Flame from graveyard to hand."""
    phoenix_flames = [c for c in player.graveyard.cards if c.slug == "phoenix_flame"]
    if phoenix_flames:
        flame = phoenix_flames[0]
        player.graveyard.remove(flame)
        player.hand.add(flame)
    player.current_turn_effects.append("fai_used")


def _kano_look_and_banish_effect(action, player, state):
    """Kano: Look at top card of deck. If it's a non-attack action, banish it and may play it this turn."""
    if len(player.deck.cards) > 0:
        top_card = player.deck.cards[-1]  # peek
        types = top_card.types or []
        if "Action" in types and "Attack" not in types:
            player.deck.draw_top()
            player.banished.add(top_card)
            player.current_turn_effects.append(("kano_banished_playable", top_card.slug))
    player.current_turn_effects.append("kano_used")


# Add new hero activation conditions
HERO_ACTIVATION_CONDITIONS.update({
    # Bravo / Bravo, Showstopper:
    # Action - {r}{r}: Until end of turn, attack action cards with cost 3+ get dominate. Go again
    "bravo": {
        "timing": "action",
        "cost": 2,
        "requires_tap": False,
        "condition_fn": lambda player, state: True,
        "effect_fn": _bravo_dominate_effect,
    },
    "bravo_showstopper": {
        "timing": "action",
        "cost": 2,
        "requires_tap": False,
        "condition_fn": lambda player, state: True,
        "effect_fn": _bravo_dominate_effect,
    },
    # Bravo, Flattering Showman:
    # Action - {r}{r}, {t}: Turn face-down arsenal face-up. If crush, +2 power and dominate. Go again
    "bravo_flattering_showman": {
        "timing": "action",
        "cost": 2,
        "requires_tap": True,
        "condition_fn": lambda player, state: (
            not player.hero.tapped
            and player.arsenal.top is not None
            and not player.arsenal_face_up
        ),
        "effect_fn": _bravo_flattering_effect,
    },
    # Dorinthea / Dorinthea, Ironsong:
    # Once per turn Effect - When weapon hits, may attack additional time with it this turn
    "dorinthea": {
        "timing": "instant",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "dorinthea_used" not in player.current_turn_effects
        ),
        "effect_fn": _dorinthea_weapon_hit_effect,
    },
    "dorinthea_ironsong": {
        "timing": "instant",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "dorinthea_used" not in player.current_turn_effects
        ),
        "effect_fn": _dorinthea_weapon_hit_effect,
    },
    # Chane / Chane, Bound by Shadow:
    # Once per Turn Action - Create a Soul Shackle token: Next Runeblade/Shadow action gets go again. Go again
    "chane": {
        "timing": "action",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "chane_used" not in player.current_turn_effects
        ),
        "effect_fn": _chane_soul_shackle_effect,
    },
    "chane_bound_by_shadow": {
        "timing": "action",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "chane_used" not in player.current_turn_effects
        ),
        "effect_fn": _chane_soul_shackle_effect,
    },
    # Azalea / Azalea, Ace in the Hole:
    # Once per Turn Action - 0: Arsenal swap (bottom old, face-up new from deck top)
    "azalea": {
        "timing": "action",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "azalea_used" not in player.current_turn_effects
            and player.arsenal.top is not None
        ),
        "effect_fn": _azalea_arsenal_swap_effect,
    },
    "azalea_ace_in_the_hole": {
        "timing": "action",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "azalea_used" not in player.current_turn_effects
            and player.arsenal.top is not None
        ),
        "effect_fn": _azalea_arsenal_swap_effect,
    },
    # Aurora / Aurora, Shooting Star:
    # Once per Turn Instant - {r}{r}: Create Embodiment of Lightning token (if played Lightning this turn)
    "aurora": {
        "timing": "instant",
        "cost": 2,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "aurora_used" not in player.current_turn_effects
            and any("lightning_played" in str(e) for e in player.current_turn_effects)
        ),
        "effect_fn": _aurora_create_embodiment_effect,
    },
    "aurora_shooting_star": {
        "timing": "instant",
        "cost": 2,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "aurora_used" not in player.current_turn_effects
            and any("lightning_played" in str(e) for e in player.current_turn_effects)
        ),
        "effect_fn": _aurora_create_embodiment_effect,
    },
    # Kayo, Strongarm (young hero):
    # Instant - {r}{r}{r}{r}, {t}: Set target attack action card's base power to 6
    "kayo_strongarm": {
        "timing": "instant",
        "cost": 4,
        "requires_tap": True,
        "condition_fn": lambda player, state: not player.hero.tapped,
        "target_fn": _kayo_find_targets,
        "effect_fn": _kayo_strongarm_effect,
    },
    # Lexi / Lexi, Livewire:
    # Once per Turn Action - 0: Turn face-down arsenal face-up. If arrow, +1 power. Go again
    "lexi": {
        "timing": "action",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "lexi_used" not in player.current_turn_effects
            and player.arsenal.top is not None
            and not player.arsenal_face_up
        ),
        "effect_fn": _lexi_arsenal_faceup_effect,
    },
    "lexi_livewire": {
        "timing": "action",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "lexi_used" not in player.current_turn_effects
            and player.arsenal.top is not None
            and not player.arsenal_face_up
        ),
        "effect_fn": _lexi_arsenal_faceup_effect,
    },
    # Fai / Fai, Rising Rebellion:
    # Once per Turn Instant - {r}{r}{r}: Return a Phoenix Flame from graveyard to hand
    "fai": {
        "timing": "instant",
        "cost": 3,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "fai_used" not in player.current_turn_effects
            and any(c.slug == "phoenix_flame" for c in player.graveyard.cards)
        ),
        "effect_fn": _fai_phoenix_flame_effect,
    },
    "fai_rising_rebellion": {
        "timing": "instant",
        "cost": 3,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "fai_used" not in player.current_turn_effects
            and any(c.slug == "phoenix_flame" for c in player.graveyard.cards)
        ),
        "effect_fn": _fai_phoenix_flame_effect,
    },
    # Kano / Kano, Dracai of Aether:
    # Once per Turn Instant - {r}{r}{r}: Look at top card, if non-attack action banish it (may play this turn)
    "kano": {
        "timing": "instant",
        "cost": 3,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "kano_used" not in player.current_turn_effects
            and len(player.deck.cards) > 0
        ),
        "effect_fn": _kano_look_and_banish_effect,
    },
    "kano_dracai_of_aether": {
        "timing": "instant",
        "cost": 3,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "kano_used" not in player.current_turn_effects
            and len(player.deck.cards) > 0
        ),
        "effect_fn": _kano_look_and_banish_effect,
    },
})


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
# Template-based equipment activation builders
# These generate effect/pay-cost/condition functions for common equipment patterns.
# ---------------------------------------------------------------------------

def _make_destroy_equip_pay_cost(slot):
    """Template: pay cost by destroying equipment from its slot zone."""
    def _pay_cost(action, player, state):
        zone = player.zone_by_name(slot)
        if zone and action.card in zone.cards:
            zone.remove(action.card)
            player.graveyard.add(action.card)
    return _pay_cost


def _make_gain_resources_effect(amount, go_again=False):
    """Template: gain {r} resources (optionally go again)."""
    def _effect(action, player, state):
        player.resources += amount
        if go_again:
            player.action_points += 1
    return _effect


def _make_gain_ap_effect(amount):
    """Template: gain N action points."""
    def _effect(action, player, state):
        player.action_points += amount
    return _effect


def _make_draw_effect(count=1, go_again=False):
    """Template: draw N cards (optionally go again)."""
    def _effect(action, player, state):
        from engine.card_effects.keywords import effect_draw
        effect_draw(state, player.player_id, count)
        if go_again:
            player.action_points += 1
    return _effect


def _make_next_attack_bonus_effect(bonus, go_again=False):
    """Template: next attack action card gets +N{p} (optionally go again)."""
    def _effect(action, player, state):
        player.current_turn_effects.append(f"equip_next_attack_+{bonus}")
        if go_again:
            player.action_points += 1
    return _effect


def _make_prevent_damage_effect(amount):
    """Template: prevent the next N damage this turn."""
    def _effect(action, player, state):
        player.current_turn_effects.append(f"prevent_damage_{amount}")
    return _effect


def _make_roll_d6_gain_resources_effect():
    """Template: roll d6, gain {r} equal to half rounded down."""
    def _effect(action, player, state):
        import random as rng
        roll = rng.randint(1, 6)
        player.resources += roll // 2
    return _effect


# ---------------------------------------------------------------------------
# Register template-expandable equipment cards
# Pattern: destroy self, gain resources
# ---------------------------------------------------------------------------

_DESTROY_GAIN_R_EQUIPMENT = {
    # slug: (slot, resource_cost, gain_amount, go_again)
    "bloodtorn_bodice": ("chest", 0, 1, True),
    "blossom_of_spring": ("chest", 0, 1, True),
    "buccaneers_bounty": ("chest", 0, 1, True),
    "garland_of_spring": ("chest", 0, 1, True),
    "popped_collar_polo": ("chest", 0, 1, True),
    "shock_frock": ("chest", 0, 1, True),
    "captains_coat": ("chest", 0, 1, True),
    "coat_of_allegiance": ("chest", 0, 1, True),
    "deep_blue": ("chest", 0, 3, True),
    "robe_of_rapture": ("chest", 0, 3, False),
    "rust_belt": ("chest", 0, 1, False),
    "spellfire_cloak": ("chest", 0, 1, False),
    "threadbare_tunic": ("chest", 0, 1, False),
    "predatory_plating": ("chest", 0, 1, False),
    "double_cross_strap": ("chest", 0, 1, False),
    "inklined_cloak": ("chest", 0, 1, False),
    "sash_of_sandikai": ("chest", 0, 1, False),
    "blood_drop_brocade": ("chest", 0, 1, False),
    "blood_scent": ("chest", 0, 1, False),
    "aether_ironweave": ("chest", 0, 2, True),
}

for _slug, (_slot, _rc, _gain, _ga) in _DESTROY_GAIN_R_EQUIPMENT.items():
    EQUIPMENT_ACTIVATION_CONDITIONS[_slug] = lambda player, slot_name, equip_card: True
    EQUIPMENT_PAY_COSTS[_slug] = _make_destroy_equip_pay_cost(_slot)
    EQUIPMENT_ACTIVATION_EFFECTS[_slug] = _make_gain_resources_effect(_gain, go_again=_ga)
    if _rc > 0:
        EQUIPMENT_ACTIVATION_COST[_slug] = _rc

# Pattern: destroy self, gain action points
_DESTROY_GAIN_AP_EQUIPMENT = {
    # slug: (slot, resource_cost, ap_amount)
    "bloodied_boots": ("legs", 0, 2),
    "time_skippers": ("legs", 3, 2),
    "achilles_accelerator": ("legs", 0, 1),
    "heavy_industry_gear_shift": ("legs", 0, 1),
}

for _slug, (_slot, _rc, _ap) in _DESTROY_GAIN_AP_EQUIPMENT.items():
    EQUIPMENT_ACTIVATION_CONDITIONS[_slug] = lambda player, slot_name, equip_card: True
    EQUIPMENT_PAY_COSTS[_slug] = _make_destroy_equip_pay_cost(_slot)
    EQUIPMENT_ACTIVATION_EFFECTS[_slug] = _make_gain_ap_effect(_ap)
    if _rc > 0:
        EQUIPMENT_ACTIVATION_COST[_slug] = _rc

# Pattern: destroy self, draw a card
_DESTROY_DRAW_EQUIPMENT = {
    # slug: (slot, resource_cost, go_again)
    "glory_seeker": ("head", 3, False),
    "blue_sea_tricorn": ("head", 3, True),
    "carrion_crown": ("head", 0, True),
    "skullhorn": ("head", 0, True),
    "monstrous_veil": ("head", 0, True),
}

for _slug, (_slot, _rc, _ga) in _DESTROY_DRAW_EQUIPMENT.items():
    EQUIPMENT_ACTIVATION_CONDITIONS[_slug] = lambda player, slot_name, equip_card: True
    EQUIPMENT_PAY_COSTS[_slug] = _make_destroy_equip_pay_cost(_slot)
    EQUIPMENT_ACTIVATION_EFFECTS[_slug] = _make_draw_effect(1, go_again=_ga)
    if _rc > 0:
        EQUIPMENT_ACTIVATION_COST[_slug] = _rc

# Pattern: non-destroy, draw a card (resource cost only)
_NONDESTROY_DRAW_EQUIPMENT = {
    # slug: (slot, resource_cost, go_again)
    "aqua_seeing_shell": ("head", 3, False),
}

for _slug, (_slot, _rc, _ga) in _NONDESTROY_DRAW_EQUIPMENT.items():
    EQUIPMENT_ACTIVATION_CONDITIONS[_slug] = lambda player, slot_name, equip_card: True
    EQUIPMENT_ACTIVATION_EFFECTS[_slug] = _make_draw_effect(1, go_again=_ga)
    if _rc > 0:
        EQUIPMENT_ACTIVATION_COST[_slug] = _rc

# Pattern: destroy self, next attack gets +N{p}. Go again
_DESTROY_NEXT_ATK_EQUIPMENT = {
    # slug: (slot, resource_cost, bonus, go_again)
    "bloodied_gauntlet": ("arms", 0, 2, True),
    "cracker_jax": ("arms", 0, 1, True),
    "gauntlet_of_boulderhold": ("arms", 3, 2, True),
    "goliath_gauntlet": ("arms", 0, 2, True),
}

for _slug, (_slot, _rc, _bonus, _ga) in _DESTROY_NEXT_ATK_EQUIPMENT.items():
    EQUIPMENT_ACTIVATION_CONDITIONS[_slug] = lambda player, slot_name, equip_card: True
    EQUIPMENT_PAY_COSTS[_slug] = _make_destroy_equip_pay_cost(_slot)
    EQUIPMENT_ACTIVATION_EFFECTS[_slug] = _make_next_attack_bonus_effect(_bonus, go_again=_ga)
    if _rc > 0:
        EQUIPMENT_ACTIVATION_COST[_slug] = _rc

# Pattern: destroy self, prevent N damage
_DESTROY_PREVENT_EQUIPMENT = {
    # slug: (slot, resource_cost)
    "bruised_leather": ("chest", 0),
    "four_finger_gloves": ("arms", 0),
    "heartened_cross_strap": ("chest", 0),
    "ironhide_plate": ("chest", 0),
    "ironrot_helm": ("head", 0),
    "ironrot_legs": ("legs", 0),
    "ironrot_gauntlet": ("arms", 0),
    "nullrune_boots": ("legs", 0),
    "nullrune_gloves": ("arms", 0),
    "nullrune_hood": ("head", 0),
    "nullrune_robe": ("chest", 0),
    "enchanted_quiver": ("arms", 0),
}

for _slug, (_slot, _rc) in _DESTROY_PREVENT_EQUIPMENT.items():
    EQUIPMENT_ACTIVATION_CONDITIONS[_slug] = lambda player, slot_name, equip_card: True
    EQUIPMENT_PAY_COSTS[_slug] = _make_destroy_equip_pay_cost(_slot)
    EQUIPMENT_ACTIVATION_EFFECTS[_slug] = _make_prevent_damage_effect(1)
    if _rc > 0:
        EQUIPMENT_ACTIVATION_COST[_slug] = _rc

# Pattern: destroy self, roll d6 gain resources
_DESTROY_ROLL_EQUIPMENT = {
    # slug: (slot, resource_cost)
    "barkbone_strapping": ("chest", 0),
}

for _slug, (_slot, _rc) in _DESTROY_ROLL_EQUIPMENT.items():
    EQUIPMENT_ACTIVATION_CONDITIONS[_slug] = lambda player, slot_name, equip_card: True
    EQUIPMENT_PAY_COSTS[_slug] = _make_destroy_equip_pay_cost(_slot)
    EQUIPMENT_ACTIVATION_EFFECTS[_slug] = _make_roll_d6_gain_resources_effect()

# Pattern: destroy self, create token + go again
def _coat_of_frost_effect(action, player, state):
    """Create a Frostbite token under target hero's control. Go again."""
    from engine.card_effects.keywords import create_token_card
    # Default: create Frostbite under opponent
    opp_id = 1 - player.player_id
    opp = state.players[opp_id]
    fb = create_token_card("frostbite", opp_id)
    opp.auras.add(fb)
    player.action_points += 1

def _flat_trackers_effect(action, player, state):
    """Create an Agility token. Go again."""
    from engine.card_effects.keywords import create_token_card
    token = create_token_card("agility", player.player_id)
    player.auras.add(token)
    player.action_points += 1

def _fiddledee_effect(action, player, state):
    """Each hero creates a Might token. Go again."""
    from engine.card_effects.keywords import create_token_card
    for p in state.players:
        token = create_token_card("might", p.player_id)
        p.auras.add(token)
    player.action_points += 1

def _calming_gesture_effect(action, player, state):
    """Create a Spectral Shield token."""
    from engine.card_effects.keywords import create_token_card
    token = create_token_card("spectral_shield", player.player_id)
    player.auras.add(token)

# Register create-token equipment
for _slug, _slot, _effect_fn in [
    ("coat_of_frost", "chest", _coat_of_frost_effect),
    ("flat_trackers", "legs", _flat_trackers_effect),
    ("fiddledee", "arms", _fiddledee_effect),
    ("calming_gesture", "chest", _calming_gesture_effect),
]:
    EQUIPMENT_ACTIVATION_CONDITIONS[_slug] = lambda player, slot_name, equip_card: True
    EQUIPMENT_PAY_COSTS[_slug] = _make_destroy_equip_pay_cost(_slot)
    EQUIPMENT_ACTIVATION_EFFECTS[_slug] = _effect_fn

# Pattern: destroy self, next attack costs less. Go again
def _bloodied_strapping_effect(action, player, state):
    """Next attack action card costs {r}{r} less to play. Go again."""
    player.current_turn_effects.append("equip_next_attack_cost_-2")
    player.action_points += 1

EQUIPMENT_ACTIVATION_CONDITIONS["bloodied_strapping"] = lambda player, slot_name, equip_card: True
EQUIPMENT_PAY_COSTS["bloodied_strapping"] = _make_destroy_equip_pay_cost("chest")
EQUIPMENT_ACTIVATION_EFFECTS["bloodied_strapping"] = _bloodied_strapping_effect

# Pattern: destroy self, weapon attacks gain bonus. Go again
def _blade_cuff_effect(action, player, state):
    """Daggers gain +1{p} this turn. Go again."""
    player.current_turn_effects.append("blade_cuff_daggers_+1")
    player.action_points += 1

def _gallantry_gold_effect(action, player, state):
    """Weapon attacks gain +1{p} this turn. Go again."""
    player.current_turn_effects.append("gallantry_gold_weapons_+1")
    player.action_points += 1

def _courage_of_bladehold_effect(action, player, state):
    """Sword attacks cost {r} less this turn. Go again."""
    player.current_turn_effects.append("courage_bladehold_swords_cost_-1")
    player.action_points += 1

for _slug, _slot, _rc, _effect_fn in [
    ("blade_cuff", "arms", 2, _blade_cuff_effect),
    ("gallantry_gold", "arms", 1, _gallantry_gold_effect),
    ("courage_of_bladehold", "arms", 0, _courage_of_bladehold_effect),
]:
    EQUIPMENT_ACTIVATION_CONDITIONS[_slug] = lambda player, slot_name, equip_card: True
    EQUIPMENT_PAY_COSTS[_slug] = _make_destroy_equip_pay_cost(_slot)
    EQUIPMENT_ACTIVATION_EFFECTS[_slug] = _effect_fn
    if _rc > 0:
        EQUIPMENT_ACTIVATION_COST[_slug] = _rc

# Pattern: once per turn with resource cost (no destroy)
def _braveforge_bracers_effect(action, player, state):
    """Next weapon attack this turn gains +1{p}."""
    player.current_turn_effects.append("braveforge_next_weapon_+1")

def _coronet_peak_effect(action, player, state):
    """Target hero discards a card unless they pay {r}."""
    opp_id = 1 - player.player_id
    opp = state.players[opp_id]
    if opp.resources >= 1:
        opp.resources -= 1
    elif opp.hand.cards:
        from engine.card_effects.keywords import effect_discard
        effect_discard(state, opp_id, 1)

def _compass_effect(action, player, state):
    """Look at top card of deck."""
    if player.deck.cards:
        top = player.deck.top
        state.set_card_visibility(top, True, viewer=player.player_id)

for _slug, _rc, _effect_fn in [
    ("braveforge_bracers", 1, _braveforge_bracers_effect),
    ("coronet_peak", 3, _coronet_peak_effect),
    ("compass_of_sunken_depths", 0, _compass_effect),
]:
    EQUIPMENT_ACTIVATION_CONDITIONS[_slug] = lambda player, slot_name, equip_card: True
    EQUIPMENT_ACTIVATION_EFFECTS[_slug] = _effect_fn
    if _rc > 0:
        EQUIPMENT_ACTIVATION_COST[_slug] = _rc

# Pattern: destroy self, gain {r}. Go again (various chest equipment)
def _blossom_effect(action, player, state):
    """Gain {r}. Go again."""
    player.resources += 1
    player.action_points += 1

for _slug in ["fish_fingers", "hope_merchants_hood"]:
    EQUIPMENT_ACTIVATION_CONDITIONS[_slug] = lambda player, slot_name, equip_card: True
    EQUIPMENT_PAY_COSTS[_slug] = _make_destroy_equip_pay_cost("arms" if "finger" in _slug or "glove" in _slug else "head")
    EQUIPMENT_ACTIVATION_EFFECTS[_slug] = _make_next_attack_bonus_effect(1, go_again=True)

# Pattern: destroy self, various effects with Go again
def _dream_weavers_effect(action, player, state):
    """Next Illusionist attack action loses and can't gain phantasm. Go again."""
    player.current_turn_effects.append("dream_weavers_no_phantasm")
    player.action_points += 1

def _crater_fist_effect(action, player, state):
    """Attacks with crush gain +2{p} this turn. Go again."""
    player.current_turn_effects.append("crater_fist_crush_+2")
    player.action_points += 1

def _craterhoof_effect(action, player, state):
    """Next Guardian attack action from arsenal gets dominate. Go again."""
    player.current_turn_effects.append("craterhoof_dominate")
    player.action_points += 1

for _slug, _slot, _rc, _effect_fn in [
    ("dream_weavers", "arms", 0, _dream_weavers_effect),
    ("crater_fist", "arms", 3, _crater_fist_effect),
    ("craterhoof", "legs", 3, _craterhoof_effect),
]:
    EQUIPMENT_ACTIVATION_CONDITIONS[_slug] = lambda player, slot_name, equip_card: True
    EQUIPMENT_PAY_COSTS[_slug] = _make_destroy_equip_pay_cost(_slot)
    EQUIPMENT_ACTIVATION_EFFECTS[_slug] = _effect_fn
    if _rc > 0:
        EQUIPMENT_ACTIVATION_COST[_slug] = _rc

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
    # Template-generated equipment next-attack bonus effects
    "equip_next_attack_+1": {
        "apply_fn": lambda attack_card, player, state: attack_card.effects.append(("base_power", lambda base: base + 1)),
    },
    "equip_next_attack_+2": {
        "condition_fn": lambda attack_card, player, state: (
            "Attack" in attack_card.types and "Action" in attack_card.types
        ),
        "apply_fn": lambda attack_card, player, state: attack_card.effects.append(("base_power", lambda base: base + 2)),
    },
    "equip_next_attack_+3": {
        "condition_fn": lambda attack_card, player, state: (
            "Attack" in attack_card.types and "Action" in attack_card.types
        ),
        "apply_fn": lambda attack_card, player, state: attack_card.effects.append(("base_power", lambda base: base + 3)),
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