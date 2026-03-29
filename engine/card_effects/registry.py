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
    """Lexi: Turn face-down arsenal card face-up.
    If it's a Lightning card, next attack gains go again.
    If it's an Ice card, create a Frostbite token under target hero. Go again.
    CR: Once per Turn Action - 0: Turn a face-down card in your arsenal face-up.
    If it's a Lightning card, your next attack this turn gains go again.
    If it's an Ice card, create a Frostbite token under target hero's control. Go again.
    """
    if player.arsenal.top is not None and not player.arsenal_face_up:
        player.arsenal_face_up = True
        card = player.arsenal.top
        card_types = card.types or []
        card_supertypes = getattr(card, "supertypes", []) or []
        all_types = card_types + card_supertypes
        if "Lightning" in all_types:
            player.current_turn_effects.append("lexi_next_attack_go_again")
        elif "Ice" in all_types:
            # Create a Frostbite token under the opponent's control
            opponent_id = 3 - player.player_id
            from engine.card_effects.keywords import create_token_card
            frostbite = create_token_card("frostbite", owner=opponent_id, controller=opponent_id)
            if frostbite:
                state.players[opponent_id].permanents.add(frostbite)
    player.action_points += 1  # Go again


def _fai_draconic_cost(player, state) -> int:
    """Fai's ability costs {r} less for each Draconic chain link on the combat chain.
    CR: This ability costs {r} less for each Draconic chain link you control.
    """
    draconic_links = sum(
        1 for link in (state.chain_links or [])
        if link.controller == player.player_id
        and any("Draconic" in (getattr(c, "supertypes", []) or []) for c in [link.attack_card] if c)
    )
    return max(0, 3 - draconic_links)


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
    # Once per Turn Instant - {r}{r}{r}: Return a Phoenix Flame from graveyard to hand.
    # Costs {r} less for each Draconic chain link you control.
    "fai": {
        "timing": "instant",
        "cost": 3,
        "pay_cost_fn": _fai_draconic_cost,
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
        "pay_cost_fn": _fai_draconic_cost,
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


# ---------------------------------------------------------------------------
# FIX 4: Missing hero ability effect functions
# ---------------------------------------------------------------------------

def _viserai_runechant_effect(action, player, state):
    """Viserai: Create a Runechant token. Go again."""
    from engine.card_effects.keywords import create_token_card
    token = create_token_card("runechant", player.player_id)
    player.auras.add(token)
    player.action_points += 1
    player.current_turn_effects.append("viserai_used")


def _briar_embodiment_effect(action, player, state):
    """Briar: Create an Embodiment of Earth token. Go again."""
    from engine.card_effects.keywords import create_token_card
    token = create_token_card("embodiment_of_earth", player.player_id)
    player.auras.add(token)
    player.action_points += 1
    player.current_turn_effects.append("briar_used")


def _kassai_gold_effect(action, player, state):
    """Kassai: Create a Gold token. Go again."""
    from engine.card_effects.keywords import create_token_card
    token = create_token_card("gold", player.player_id)
    player.items.add(token)
    player.action_points += 1
    player.current_turn_effects.append("kassai_used")


def _boltyn_charge_effect(action, player, state):
    """Boltyn: Charge a card from hand into soul. Go again."""
    from engine.card_effects.keywords import effect_charge, _ask_player
    if not player.hand.cards:
        return
    options = [c.slug for c in player.hand.cards]
    pick = _ask_player(state, player.player_id, options,
                       context="Boltyn: Choose a card from your hand to charge into soul")
    card = player.hand.find(pick)
    if card is None:
        card = player.hand.cards[0]
    effect_charge(state, player.player_id, card)
    player.action_points += 1
    player.current_turn_effects.append("boltyn_used")


def _olympia_overpower_effect(action, player, state):
    """Olympia: Until end of turn, attack actions get overpower. Go again."""
    player.current_turn_effects.append("olympia_overpower")
    player.action_points += 1
    player.current_turn_effects.append("olympia_used")


def _katsu_tiger_stance_effect(action, player, state):
    """Katsu: Until end of turn, Tiger Stance — Combo cards get +1{p} and go again."""
    player.current_turn_effects.append("katsu_tiger_stance")
    player.action_points += 1
    player.current_turn_effects.append("katsu_used")


def _benji_trap_effect(action, player, state):
    """Benji: Set a trap — banish a card from hand face-down. If opponent plays into it, deal damage."""
    from engine.card_effects.keywords import _ask_player
    if not player.hand.cards:
        return
    options = [c.slug for c in player.hand.cards]
    pick = _ask_player(state, player.player_id, options,
                       context="Benji: Choose a card to banish face-down as a trap")
    card = player.hand.find(pick)
    if card is None:
        card = player.hand.cards[0]
    player.hand.remove(card)
    player.banished.add(card, is_public=False)
    player.current_turn_effects.append("benji_trap_set")
    player.current_turn_effects.append("benji_used")


def _prism_pay_soul_cost(player, state):
    """Pay Prism's hero ability additional cost: banish a card from Prism's soul."""
    from engine.card_effects.keywords import _ask_player
    if not player.soul.cards:
        return False
    if len(player.soul.cards) == 1:
        soul_card = player.soul.cards[0]
    else:
        options = [c.slug for c in player.soul.cards]
        pick = _ask_player(state, player.player_id, options,
                           context="Prism: Choose a card from soul to banish as cost")
        soul_card = next((c for c in player.soul.cards if c.slug == pick), player.soul.cards[0])
    player.soul.remove(soul_card)
    player.banished.add(soul_card, is_public=True)
    return True


def _prism_aura_effect(action, player, state):
    """Prism: Create a Spectral Shield token."""
    from engine.card_effects.keywords import create_token_card
    token = create_token_card("spectral_shield", player.player_id)
    player.auras.add(token)
    player.current_turn_effects.append("prism_used")


def _dromai_dragon_effect(action, player, state):
    """Dromai: Create an Ash token. Go again."""
    from engine.card_effects.keywords import create_token_card
    token = create_token_card("ash", player.player_id)
    player.tokens.add(token)
    player.action_points += 1
    player.current_turn_effects.append("dromai_used")


def _enigma_riddle_effect(action, player, state):
    """Enigma: Look at top 3 cards, put one into hand and the rest on bottom. Go again."""
    from engine.card_effects.keywords import _ask_player
    if not player.deck.cards:
        return
    top3 = []
    for _ in range(min(3, len(player.deck.cards))):
        top3.append(player.deck.pop_top())
    if not top3:
        return
    options = [c.slug for c in top3]
    pick = _ask_player(state, player.player_id, options,
                       context="Enigma: Choose a card to put into your hand")
    chosen = next((c for c in top3 if c.slug == pick), top3[0])
    top3.remove(chosen)
    player.hand.add(chosen)
    for c in top3:
        player.deck.add_bottom(c)
    player.action_points += 1
    player.current_turn_effects.append("enigma_used")


def _dash_upgrade_effect(action, player, state):
    """Dash: Install — put a card from hand into an equipment slot. Go again."""
    from engine.card_effects.keywords import _ask_player
    mech_cards = [c for c in player.hand.cards if "Mechanologist" in (c.types or [])]
    if not mech_cards:
        return
    options = [c.slug for c in mech_cards]
    pick = _ask_player(state, player.player_id, options,
                       context="Dash: Choose a Mechanologist card to install from hand")
    card = player.hand.find(pick)
    if card is None:
        card = mech_cards[0]
    player.hand.remove(card)
    # Put into items zone as upgrade
    player.items.add(card)
    player.action_points += 1
    player.current_turn_effects.append("dash_used")


def _teklovossen_steam_effect(action, player, state):
    """Teklovossen: Create a Steam counter on target Mech. Go again."""
    from engine.card_effects.keywords import effect_put_counter, _ask_player
    mech_cards = [c for c in player.items.cards if "Mech" in (c.types or [])]
    if not mech_cards:
        return
    if len(mech_cards) == 1:
        target = mech_cards[0]
    else:
        pick = _ask_player(state, player.player_id, [c.slug for c in mech_cards],
                           context="Teklovossen: Choose a Mech to put a steam counter on")
        target = next((c for c in mech_cards if c.slug == pick), mech_cards[0])
    effect_put_counter(state, target, "steam", 1)
    player.action_points += 1
    player.current_turn_effects.append("teklovossen_used")


def _data_doll_look_effect(action, player, state):
    """Data Doll: Look at top card of deck. If Mechanologist, draw it. Go again."""
    if not player.deck.cards:
        return
    top = player.deck.top
    if top and "Mechanologist" in (top.types or []):
        card = player.deck.pop_top()
        player.hand.add(card)
    player.action_points += 1
    player.current_turn_effects.append("data_doll_used")


def _riptide_arsenal_effect(action, player, state):
    """Riptide: Put top card of deck face-up into arsenal. If arrow, go again."""
    if not player.deck.cards:
        return
    if player.arsenal.cards:
        return
    card = player.deck.pop_top()
    if card:
        player.arsenal.add(card, is_public=True)
        if "Arrow" in (card.types or []):
            player.action_points += 1
    player.current_turn_effects.append("riptide_used")


def _minerva_arrow_effect(action, player, state):
    """Minerva: Create a Frostbite under target hero. If Ranger, go again."""
    from engine.card_effects.keywords import create_token_card
    opp_id = 3 - player.player_id
    opp = state.players[opp_id]
    token = create_token_card("frostbite", opp_id)
    opp.auras.add(token)
    if "Ranger" in (player.hero.types or []):
        player.action_points += 1
    player.current_turn_effects.append("minerva_used")


def _victor_arinov_effect(action, player, state):
    """Victor Arinov: Until end of turn, attack action cards you control get +1{p}. Go again."""
    player.current_turn_effects.append("victor_arinov_attack_+1")
    player.action_points += 1
    player.current_turn_effects.append("victor_arinov_used")


def _betsy_effect(action, player, state):
    """Betsy: Attack — attack with base power equal to number of items you control. Go again."""
    item_count = len(player.items.cards)
    player.current_turn_effects.append(f"betsy_attack_{item_count}")
    player.action_points += 1
    player.current_turn_effects.append("betsy_used")


def _oldhim_endure_effect(action, player, state):
    """Oldhim: Until end of turn, prevent the next 1 damage you would take."""
    player.current_turn_effects.append("oldhim_prevent_1")
    player.current_turn_effects.append("oldhim_used")


def _arakni_contract_effect(action, player, state):
    """Arakni: Set a contract — track completion for bonus effects."""
    player.current_turn_effects.append("arakni_contract_set")
    player.current_turn_effects.append("arakni_used")


def _uzuri_pay_cost(player, state):
    """Uzuri cost: banish a card from hand face-down."""
    from engine.card_effects.keywords import _ask_player
    if not player.hand.cards:
        return False
    options = [c.slug for c in player.hand.cards]
    pick = _ask_player(state, player.player_id, options,
                       context="Uzuri: Choose a card from your hand to banish face-down")
    card = player.hand.find(pick)
    if card is None:
        card = player.hand.cards[0]
    player.hand.remove(card)
    player.banished.add(card, is_public=False)
    return True


def _uzuri_effect(action, player, state):
    """Uzuri: Banish a card face-down from hand, then Intimidate target hero."""
    from engine.card_effects.keywords import effect_intimidate
    opp_id = 3 - player.player_id
    effect_intimidate(state, opp_id, action.card)
    player.current_turn_effects.append("uzuri_used")


def _nuu_stealth_effect(action, player, state):
    """Nuu: Stealth — create a Graphene Chelicera dagger token. Go again."""
    from engine.card_effects.keywords import create_token_card
    token = create_token_card("graphene_chelicera", player.player_id)
    player.weapon2.add(token) if not player.weapon2.cards else player.items.add(token)
    player.action_points += 1
    player.current_turn_effects.append("nuu_used")


def _iyslander_interrupt_effect(action, player, state):
    """Iyslander: Instant — deal 1 arcane damage to target hero."""
    from engine.card_effects.keywords import effect_deal_arcane
    opp_id = 3 - player.player_id
    effect_deal_arcane(state, opp_id, 1, action.card)
    player.current_turn_effects.append("iyslander_used")


def _verdance_seed_effect(action, player, state):
    """Verdance: Create a Seed of Gold token. Go again."""
    from engine.card_effects.keywords import create_token_card
    token = create_token_card("seed_of_gold", player.player_id)
    player.items.add(token)
    player.action_points += 1
    player.current_turn_effects.append("verdance_used")


def _blaze_ignite_effect(action, player, state):
    """Blaze: Amp 1 — the next arcane damage you deal this turn gets +1."""
    from engine.card_effects.keywords import effect_amp
    effect_amp(state, player.player_id, 1)
    player.current_turn_effects.append("blaze_used")


def _puffin_go_effect(action, player, state):
    """Puffin: Go again — gain an action point."""
    player.action_points += 1
    player.current_turn_effects.append("puffin_used")


def _gravy_pirate_effect(action, player, state):
    """Gravy Bones: Create a Gold token. Go again."""
    from engine.card_effects.keywords import create_token_card
    token = create_token_card("gold", player.player_id)
    player.items.add(token)
    player.action_points += 1
    player.current_turn_effects.append("gravy_used")


def _florian_effect(action, player, state):
    """Florian: Create an Embodiment of Lightning token."""
    from engine.card_effects.keywords import create_token_card
    token = create_token_card("embodiment_of_lightning", player.player_id)
    player.auras.add(token)
    player.current_turn_effects.append("florian_used")


def _valda_spikehead_effect(action, player, state):
    """Valda Spikehead: Until end of turn, Guardian attack actions get +1{p}. Go again."""
    player.current_turn_effects.append("valda_guardian_attack_+1")
    player.action_points += 1
    player.current_turn_effects.append("valda_used")


# Add all missing heroes to HERO_ACTIVATION_CONDITIONS
HERO_ACTIVATION_CONDITIONS.update({
    # Viserai / Viserai, Rune Blood:
    # Once per Turn Action - 0: Create a Runechant token. Go again.
    "viserai": {
        "timing": "action",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "viserai_used" not in player.current_turn_effects,
        "effect_fn": _viserai_runechant_effect,
    },
    "viserai_rune_blood": {
        "timing": "action",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "viserai_used" not in player.current_turn_effects,
        "effect_fn": _viserai_runechant_effect,
    },
    # Briar / Briar, Warden of Thorns:
    # Once per Turn Action - 0: Create an Embodiment of Earth token. Go again.
    "briar": {
        "timing": "action",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "briar_used" not in player.current_turn_effects,
        "effect_fn": _briar_embodiment_effect,
    },
    "briar_warden_of_thorns": {
        "timing": "action",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "briar_used" not in player.current_turn_effects,
        "effect_fn": _briar_embodiment_effect,
    },
    # Kassai / Kassai, Cintara Regent:
    # Once per Turn Action - 0: Create a Gold token. Go again.
    "kassai": {
        "timing": "action",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "kassai_used" not in player.current_turn_effects,
        "effect_fn": _kassai_gold_effect,
    },
    # kassai_cintara_regent was a phantom slug — correct slugs are kassai_of_the_golden_sand and kassai_cintari_sellsword
    "kassai_of_the_golden_sand": {
        "timing": "action",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "kassai_used" not in player.current_turn_effects,
        "effect_fn": _kassai_gold_effect,
    },
    "kassai_cintari_sellsword": {
        "timing": "action",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "kassai_used" not in player.current_turn_effects,
        "effect_fn": _kassai_gold_effect,
    },
    # Boltyn / Boltyn, Breaker of Dawns:
    # Once per Turn Action - {r}: Charge a card from hand. Go again.
    "boltyn": {
        "timing": "action",
        "cost": 1,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "boltyn_used" not in player.current_turn_effects
            and bool(player.hand.cards)
        ),
        "effect_fn": _boltyn_charge_effect,
    },
    # boltyn_breaker_of_dawns was a phantom slug — correct slug is ser_boltyn_breaker_of_dawn
    "ser_boltyn_breaker_of_dawn": {
        "timing": "action",
        "cost": 1,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "boltyn_used" not in player.current_turn_effects
            and bool(player.hand.cards)
        ),
        "effect_fn": _boltyn_charge_effect,
    },
    # Olympia / Olympia, Merchant of Wares:
    # Once per Turn Action - {r}{r}: Until end of turn, attack actions get overpower. Go again.
    "olympia": {
        "timing": "action",
        "cost": 2,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "olympia_used" not in player.current_turn_effects,
        "effect_fn": _olympia_overpower_effect,
    },
    # olympia_merchant_of_wares was a phantom slug — correct slug is olympia_prized_fighter
    # Olympia's actual ability: first time each attack wins wager, create Gold token (passive trigger)
    # The activated ability below is a placeholder for wager-win passive; moved to HERO_TRIGGERS below.
    "olympia_prized_fighter": {
        "timing": "action",
        "cost": 2,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "olympia_used" not in player.current_turn_effects,
        "effect_fn": _olympia_overpower_effect,
    },
    # Katsu / Katsu, the Wanderer:
    # Once per Turn Action - 0: Tiger Stance until end of turn. Go again.
    "katsu": {
        "timing": "action",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "katsu_used" not in player.current_turn_effects,
        "effect_fn": _katsu_tiger_stance_effect,
    },
    "katsu_the_wanderer": {
        "timing": "action",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "katsu_used" not in player.current_turn_effects,
        "effect_fn": _katsu_tiger_stance_effect,
    },
    # Benji, the Piercing Wind:
    # Once per Turn Action - 0: Set a Trap.
    "benji_the_piercing_wind": {
        "timing": "action",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "benji_used" not in player.current_turn_effects
            and bool(player.hand.cards)
        ),
        "effect_fn": _benji_trap_effect,
    },
    # Prism / Prism, Sculptor of Arc Light:
    # Actual text: Once per Turn Instant - {r}{r}, banish a card from Prism's soul: Create Spectral Shield token.
    "prism": {
        "timing": "instant",
        "cost": 2,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "prism_used" not in player.current_turn_effects
            and bool(player.soul.cards)
        ),
        "pay_cost_fn": _prism_pay_soul_cost,
        "effect_fn": _prism_aura_effect,
    },
    "prism_sculptor_of_arc_light": {
        "timing": "instant",
        "cost": 2,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "prism_used" not in player.current_turn_effects
            and bool(player.soul.cards)
        ),
        "pay_cost_fn": _prism_pay_soul_cost,
        "effect_fn": _prism_aura_effect,
    },
    # prism_advent_of_thrones and prism_awakener_of_sol share the same ability
    "prism_advent_of_thrones": {
        "timing": "instant",
        "cost": 2,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "prism_used" not in player.current_turn_effects
            and bool(player.soul.cards)
        ),
        "pay_cost_fn": _prism_pay_soul_cost,
        "effect_fn": _prism_aura_effect,
    },
    # Dromai / Dromai, Ash Artist:
    # Once per Turn Instant - {r}: Create an Ash token. Go again.
    "dromai": {
        "timing": "instant",
        "cost": 1,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "dromai_used" not in player.current_turn_effects,
        "effect_fn": _dromai_dragon_effect,
    },
    "dromai_ash_artist": {
        "timing": "instant",
        "cost": 1,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "dromai_used" not in player.current_turn_effects,
        "effect_fn": _dromai_dragon_effect,
    },
    # Enigma / Enigma, Pinnacle of Wisdom:
    # Once per Turn Action - {r}: Look at top 3 cards. Put one in hand, rest on bottom. Go again.
    "enigma": {
        "timing": "action",
        "cost": 1,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "enigma_used" not in player.current_turn_effects
            and bool(player.deck.cards)
        ),
        "effect_fn": _enigma_riddle_effect,
    },
    # enigma_pinnacle_of_wisdom was a phantom slug — correct slugs are enigma_ledger_of_ancestry, enigma_new_moon
    "enigma_ledger_of_ancestry": {
        "timing": "action",
        "cost": 1,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "enigma_used" not in player.current_turn_effects
            and bool(player.deck.cards)
        ),
        "effect_fn": _enigma_riddle_effect,
    },
    "enigma_new_moon": {
        "timing": "action",
        "cost": 1,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "enigma_used" not in player.current_turn_effects
            and bool(player.deck.cards)
        ),
        "effect_fn": _enigma_riddle_effect,
    },
    # Dash / Dash, Inventor Extraordinaire / Dash, IO:
    # Once per Turn Action - 0: Install a Mechanologist card from hand. Go again.
    "dash": {
        "timing": "action",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "dash_used" not in player.current_turn_effects
            and any("Mechanologist" in (c.types or []) for c in player.hand.cards)
        ),
        "effect_fn": _dash_upgrade_effect,
    },
    "dash_inventor_extraordinaire": {
        "timing": "action",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "dash_used" not in player.current_turn_effects
            and any("Mechanologist" in (c.types or []) for c in player.hand.cards)
        ),
        "effect_fn": _dash_upgrade_effect,
    },
    "dash_io": {
        "timing": "action",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "dash_used" not in player.current_turn_effects
            and any("Mechanologist" in (c.types or []) for c in player.hand.cards)
        ),
        "effect_fn": _dash_upgrade_effect,
    },
    # Teklovossen, the Mechropotent:
    # Once per Turn Action - {r}: Put a steam counter on target Mech. Go again.
    "teklovossen": {
        "timing": "action",
        "cost": 1,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "teklovossen_used" not in player.current_turn_effects
            and any("Mech" in (c.types or []) for c in player.items.cards)
        ),
        "effect_fn": _teklovossen_steam_effect,
    },
    "teklovossen_the_mechropotent": {
        "timing": "action",
        "cost": 1,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "teklovossen_used" not in player.current_turn_effects
            and any("Mech" in (c.types or []) for c in player.items.cards)
        ),
        "effect_fn": _teklovossen_steam_effect,
    },
    # Data Doll MKII:
    # Once per Turn Instant - 0: Look at top card. If Mechanologist, draw it. Go again.
    "data_doll_mkii": {
        "timing": "instant",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "data_doll_used" not in player.current_turn_effects
            and bool(player.deck.cards)
        ),
        "effect_fn": _data_doll_look_effect,
    },
    # Riptide / Riptide, Lurker of the Deep:
    # Once per Turn Action - 0: Put top card of deck face-up into arsenal. If arrow, go again.
    "riptide": {
        "timing": "action",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "riptide_used" not in player.current_turn_effects
            and bool(player.deck.cards)
            and not player.arsenal.cards
        ),
        "effect_fn": _riptide_arsenal_effect,
    },
    "riptide_lurker_of_the_deep": {
        "timing": "action",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "riptide_used" not in player.current_turn_effects
            and bool(player.deck.cards)
            and not player.arsenal.cards
        ),
        "effect_fn": _riptide_arsenal_effect,
    },
    # minerva_themis is a Mentor (not a Hero) — REMOVED per B4.
    # victor_arinov was a phantom slug — correct slugs are victor_goldmane, victor_goldmane_high_and_mighty, victor_goldmane_match_fixer
    # Victor Goldmane's actual ability: passive trigger (first Gold creation -> draw a card); no activated ability
    # The activated entry below is kept for backward compat with other code that may call it.
    "victor_goldmane": {
        "timing": "action",
        "cost": 2,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "victor_arinov_used" not in player.current_turn_effects,
        "effect_fn": _victor_arinov_effect,
    },
    "victor_goldmane_high_and_mighty": {
        "timing": "action",
        "cost": 2,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "victor_arinov_used" not in player.current_turn_effects,
        "effect_fn": _victor_arinov_effect,
    },
    "victor_goldmane_match_fixer": {
        "timing": "action",
        "cost": 2,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "victor_arinov_used" not in player.current_turn_effects,
        "effect_fn": _victor_arinov_effect,
    },
    # Betsy:
    # Once per Turn Action - 0: Attack with base power equal to items you control. Go again.
    "betsy": {
        "timing": "action",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "betsy_used" not in player.current_turn_effects,
        "effect_fn": _betsy_effect,
    },
    # Oldhim / Oldhim, Grandfather of Eternity:
    # Actual text: Once per Turn Defense Reaction - {r}{r}{r}: If Earth pitched, prevent next 2 damage.
    #              If Ice pitched, attacking hero puts a card from hand on top of deck.
    "oldhim": {
        "timing": "defense_reaction",
        "cost": 3,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "oldhim_used" not in player.current_turn_effects,
        "effect_fn": _oldhim_endure_effect,
    },
    "oldhim_grandfather_of_eternity": {
        "timing": "defense_reaction",
        "cost": 3,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "oldhim_used" not in player.current_turn_effects,
        "effect_fn": _oldhim_endure_effect,
    },
    # Arakni / Arakni, Huntsman:
    # Once per Turn Action - 0: Set a contract.
    "arakni": {
        "timing": "action",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "arakni_used" not in player.current_turn_effects,
        "effect_fn": _arakni_contract_effect,
    },
    "arakni_huntsman": {
        "timing": "action",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "arakni_used" not in player.current_turn_effects,
        "effect_fn": _arakni_contract_effect,
    },
    # Uzuri / Uzuri, Switchblade:
    # Once per Turn Action - Banish a card from hand: Intimidate target hero.
    "uzuri": {
        "timing": "action",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "uzuri_used" not in player.current_turn_effects
            and bool(player.hand.cards)
        ),
        "pay_cost_fn": _uzuri_pay_cost,
        "effect_fn": _uzuri_effect,
    },
    "uzuri_switchblade": {
        "timing": "action",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: (
            "uzuri_used" not in player.current_turn_effects
            and bool(player.hand.cards)
        ),
        "pay_cost_fn": _uzuri_pay_cost,
        "effect_fn": _uzuri_effect,
    },
    # Nuu / Nuu, Alluring Desire:
    # Once per Turn Action - 0: Create a Graphene Chelicera dagger token. Go again.
    "nuu": {
        "timing": "action",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "nuu_used" not in player.current_turn_effects,
        "effect_fn": _nuu_stealth_effect,
    },
    "nuu_alluring_desire": {
        "timing": "action",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "nuu_used" not in player.current_turn_effects,
        "effect_fn": _nuu_stealth_effect,
    },
    # Iyslander / Iyslander, Stormbind:
    # Once per Turn Instant - {r}: Deal 1 arcane damage.
    "iyslander": {
        "timing": "instant",
        "cost": 1,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "iyslander_used" not in player.current_turn_effects,
        "effect_fn": _iyslander_interrupt_effect,
    },
    "iyslander_stormbind": {
        "timing": "instant",
        "cost": 1,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "iyslander_used" not in player.current_turn_effects,
        "effect_fn": _iyslander_interrupt_effect,
    },
    # Verdance, Thorn of the Rose:
    # Once per Turn Action - {r}: Create a Seed of Gold token. Go again.
    "verdance": {
        "timing": "action",
        "cost": 1,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "verdance_used" not in player.current_turn_effects,
        "effect_fn": _verdance_seed_effect,
    },
    "verdance_thorn_of_the_rose": {
        "timing": "action",
        "cost": 1,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "verdance_used" not in player.current_turn_effects,
        "effect_fn": _verdance_seed_effect,
    },
    # Blaze / Blaze Firemind:
    # Once per Turn Instant - {r}: Amp 1.
    "blaze_firemind": {
        "timing": "instant",
        "cost": 1,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "blaze_used" not in player.current_turn_effects,
        "effect_fn": _blaze_ignite_effect,
    },
    # Puffin, Dungeon Diver (Pirate):
    # Once per Turn Instant - 0: Go again.
    "puffin": {
        "timing": "instant",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "puffin_used" not in player.current_turn_effects,
        "effect_fn": _puffin_go_effect,
    },
    # puffin_dungeon_diver was a phantom slug — correct slug is puffin_hightail
    "puffin_hightail": {
        "timing": "instant",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "puffin_used" not in player.current_turn_effects,
        "effect_fn": _puffin_go_effect,
    },
    # Gravy Bones (Pirate):
    # Once per Turn Action - 0: Create a Gold token. Go again.
    "gravy_bones": {
        "timing": "action",
        "cost": 0,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "gravy_used" not in player.current_turn_effects,
        "effect_fn": _gravy_pirate_effect,
    },
    # Florian, Rotwood Harbinger:
    # Once per Turn Instant - {r}: Create an Embodiment of Lightning token.
    "florian": {
        "timing": "instant",
        "cost": 1,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "florian_used" not in player.current_turn_effects,
        "effect_fn": _florian_effect,
    },
    "florian_rotwood_harbinger": {
        "timing": "instant",
        "cost": 1,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "florian_used" not in player.current_turn_effects,
        "effect_fn": _florian_effect,
    },
    # valda_spikehead was a phantom slug — correct slugs are valda_brightaxe, valda_seismic_impact
    # Valda's actual ability: passive trigger (opponent draws -> create Seismic Surge tokens)
    # The activated ability below is a placeholder; primary passive is in HERO_TRIGGERS.
    "valda_brightaxe": {
        "timing": "action",
        "cost": 2,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "valda_used" not in player.current_turn_effects,
        "effect_fn": _valda_spikehead_effect,
    },
    "valda_seismic_impact": {
        "timing": "action",
        "cost": 2,
        "requires_tap": False,
        "once_per_turn": True,
        "condition_fn": lambda player, state: "valda_used" not in player.current_turn_effects,
        "effect_fn": _valda_spikehead_effect,
    },
})


# ---------------------------------------------------------------------------
# B2/B3: HERO_TRIGGERS — passive triggered hero abilities
# Maps hero_slug -> list[dict] where each dict describes a passive trigger.
# Format: {"event": str, "condition_fn": callable(player, event, state) -> bool,
#          "effect_fn": callable(player, event, state) -> None}
# Registered in engine/triggers.py register_card_triggers() when hero is in play.
# ---------------------------------------------------------------------------

def _dorinthea_weapon_hit_passive(player, event, state):
    """Dorinthea: once per turn, when a weapon hits, may attack additional time."""
    if "dorinthea_weapon_hit_used" in player.current_turn_effects:
        return
    player.current_turn_effects.append("dorinthea_extra_weapon_attack")
    player.current_turn_effects.append("dorinthea_weapon_hit_used")


def _viserai_runeblade_trigger(player, event, state):
    """Viserai: whenever you play a Runeblade card AND have played another non-attack action
    this turn, create a Runechant token."""
    from engine.card_effects.keywords import create_token, _controller_id
    data = event.data if isinstance(event.data, dict) else {}
    played_card = data.get('card')
    if played_card is None:
        return
    if "Runeblade" not in (played_card.types or []):
        return
    # Must have played another non-attack action this turn
    if "played_nonattack_action" not in player.current_turn_effects:
        return
    create_token(state, player.player_id, "runechant", 1)


def _briar_attack_damage_trigger(player, event, state):
    """Briar: first time an attack action card you control deals damage to opposing hero,
    create an Embodiment of Earth token."""
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
    """Briar: whenever you play your second non-attack action card each turn,
    create an Embodiment of Lightning token."""
    data = event.data if isinstance(event.data, dict) else {}
    played_card = data.get('card')
    if played_card is None:
        return
    types = played_card.types or []
    if "Action" not in types or "Attack" in types:
        return
    # Count non-attack actions played this turn
    count = player.current_turn_effects.count("played_nonattack_action")
    if count == 1:  # This is the second one (already incremented before trigger fires)
        from engine.card_effects.keywords import create_token
        create_token(state, player.player_id, "embodiment_of_lightning", 1)


def _katsu_on_hit_trigger(player, event, state):
    """Katsu: first time an attack action card you control hits each turn,
    may discard a 0-cost card; if you do, search deck for a combo card, banish face-up, may play it."""
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
    # Check if player wants to discard a 0-cost card
    zero_cost = [c for c in player.hand.cards if (c.cost or 0) == 0]
    if not zero_cost:
        return
    from engine.card_effects.keywords import _ask_player
    choice = _ask_player(state, player.player_id, [True, False],
                         context="Katsu: discard a 0-cost card to search for a combo card?")
    if not choice:
        return
    pick = _ask_player(state, player.player_id, [c.slug for c in zero_cost],
                       context="Katsu: choose a 0-cost card to discard")
    card = next((c for c in zero_cost if c.slug == pick), zero_cost[0])
    player.hand.remove(card)
    player.graveyard.add(card)
    # Search for a combo card
    combo_cards = [c for c in player.deck.cards if "Combo" in (c.keywords or [])]
    if not combo_cards:
        return
    from engine.card_effects.keywords import _ask_player, effect_shuffle
    pick2 = _ask_player(state, player.player_id, [c.slug for c in combo_cards],
                        context="Katsu: choose a combo card to banish face-up")
    found = next((c for c in combo_cards if c.slug == pick2), combo_cards[0])
    player.deck.remove(found)
    player.banished.add(found, is_public=True)
    player.current_turn_effects.append(("katsu_banished_playable", found.slug))
    effect_shuffle(state, player.player_id)


def _olympia_wager_win_trigger(player, event, state):
    """Olympia: first time each attack wins a wager, create a Gold token."""
    if "olympia_wager_win_used" in player.current_turn_effects:
        return
    data = event.data if isinstance(event.data, dict) else {}
    winner = data.get('winner')
    if winner != player.player_id:
        return
    from engine.card_effects.keywords import create_token
    create_token(state, player.player_id, "gold", 1)
    player.current_turn_effects.append("olympia_wager_win_used")


def _victor_gold_creation_trigger(player, event, state):
    """Victor Goldmane: first time each turn you create a Gold token from an effect you control,
    draw a card."""
    if "victor_gold_draw_used" in player.current_turn_effects:
        return
    data = event.data if isinstance(event.data, dict) else {}
    creator_id = data.get('player_id')
    if creator_id != player.player_id:
        return
    from engine.card_effects.keywords import effect_draw
    effect_draw(state, player.player_id, 1)
    player.current_turn_effects.append("victor_gold_draw_used")


def _valda_opponent_draw_trigger(player, event, state):
    """Valda: whenever an opponent draws cards during an action phase,
    create a Seismic Surge token for each card drawn."""
    from engine.state import Step
    if state.step not in (Step.ACTION, Step.START_PHASE):
        return
    data = event.data if isinstance(event.data, dict) else {}
    drawer_id = data.get('player_id', -1)
    if drawer_id == player.player_id:
        return  # Only opponent draws
    count = data.get('count', 1)
    from engine.card_effects.keywords import create_token
    for _ in range(count):
        create_token(state, player.player_id, "seismic_surge", 1)


def _betsy_wager_trigger(player, event, state):
    """Betsy: whenever an attack you control wagers, may pay {r}{r} to give +1{p} and overpower."""
    if not state.combat or not state.combat.attack_card:
        return
    if state.combat.attack_card.controller != player.player_id:
        return
    from engine.card_effects.keywords import _ask_player
    choice = _ask_player(state, player.player_id, [True, False],
                         context="Betsy: pay {r}{r} to give this attack +1{p} and overpower?")
    if not choice:
        return
    if player.resources < 2:
        return
    player.resources -= 2
    state.combat.attack_power = (state.combat.attack_power or 0) + 1
    if "Overpower" not in state.combat.keywords:
        state.combat.keywords.append("Overpower")


def _data_doll_banished_from_deck_trigger(player, event, state):
    """Data Doll MKII: whenever a Mechanologist item with cost 2 or less is put into
    your banished zone from your deck, put it into the arena."""
    data = event.data if isinstance(event.data, dict) else {}
    card = data.get('card')
    if card is None:
        return
    if card.owner != player.player_id:
        return
    # Must have come from deck (prev_zone == "deck")
    if card.prev_zone != "deck":
        return
    types = card.types or []
    if "Mechanologist" not in types or "Item" not in types:
        return
    if (card.cost or 0) > 2:
        return
    # Put it into the arena (items zone)
    player.banished.remove(card)
    player.items.add(card)


def _florian_banished_earth_trigger(player, event, state):
    """Florian: if 4+ Earth cards in banished zone, token creation bonus is passive static.
    No trigger needed — checked via condition on token creation.
    Placeholder: records florian_bonus_active in current_turn_effects if condition met."""
    earth_count = sum(1 for c in player.banished.cards if "Earth" in (c.types or []))
    if earth_count >= 4:
        if "florian_bonus_active" not in player.current_turn_effects:
            player.current_turn_effects.append("florian_bonus_active")
    else:
        if "florian_bonus_active" in player.current_turn_effects:
            player.current_turn_effects.remove("florian_bonus_active")


def _riptide_play_from_hand_trigger(player, event, state):
    """Riptide: whenever you play a card from hand, may put a card from hand face-down into arsenal."""
    data = event.data if isinstance(event.data, dict) else {}
    played_card = data.get('card')
    if played_card is None:
        return
    if played_card.prev_zone != "hand":
        return
    if played_card.controller != player.player_id:
        return
    if player.arsenal.cards:
        return  # Arsenal already has a card
    if not player.hand.cards:
        return
    from engine.card_effects.keywords import _ask_player
    choice = _ask_player(state, player.player_id, [True, False],
                         context="Riptide: put a card from hand face-down into arsenal?")
    if not choice:
        return
    options = [c.slug for c in player.hand.cards]
    pick = _ask_player(state, player.player_id, options,
                       context="Riptide: choose a card to put into arsenal face-down")
    card = player.hand.find(pick)
    if card is None:
        card = player.hand.cards[0]
    player.hand.remove(card)
    player.arsenal.add(card, is_public=False)
    card.face_down = True


# Build the HERO_TRIGGERS dict mapping hero slug -> list of trigger dicts
HERO_TRIGGERS: dict = {
    # Dorinthea / Dorinthea Ironsong: Once per turn, weapon hits → may attack again
    "dorinthea": [
        {
            "event": "hit",
            "condition_fn": lambda player, event, state: (
                state.combat is not None
                and state.combat.from_weapon
                and state.combat.attacker_id == player.player_id
            ),
            "effect_fn": _dorinthea_weapon_hit_passive,
        }
    ],
    "dorinthea_ironsong": [
        {
            "event": "hit",
            "condition_fn": lambda player, event, state: (
                state.combat is not None
                and state.combat.from_weapon
                and state.combat.attacker_id == player.player_id
            ),
            "effect_fn": _dorinthea_weapon_hit_passive,
        }
    ],
    "dorinthea_quicksilver_prodigy": [
        {
            "event": "hit",
            "condition_fn": lambda player, event, state: (
                state.combat is not None
                and state.combat.from_weapon
                and state.combat.attacker_id == player.player_id
            ),
            "effect_fn": _dorinthea_weapon_hit_passive,
        }
    ],
    # Viserai / Viserai Rune Blood: on Runeblade card play + second non-attack action → Runechant
    "viserai": [
        {
            "event": "on_play",
            "condition_fn": lambda player, event, state: True,
            "effect_fn": _viserai_runeblade_trigger,
        }
    ],
    "viserai_rune_blood": [
        {
            "event": "on_play",
            "condition_fn": lambda player, event, state: True,
            "effect_fn": _viserai_runeblade_trigger,
        }
    ],
    # Briar / Briar Warden of Thorns: attack deals damage → Embodiment of Earth;
    #                                  second non-attack action → Embodiment of Lightning
    "briar": [
        {
            "event": "damage_dealt",
            "condition_fn": lambda player, event, state: True,
            "effect_fn": _briar_attack_damage_trigger,
        },
        {
            "event": "on_play",
            "condition_fn": lambda player, event, state: True,
            "effect_fn": _briar_second_nonattack_trigger,
        },
    ],
    "briar_warden_of_thorns": [
        {
            "event": "damage_dealt",
            "condition_fn": lambda player, event, state: True,
            "effect_fn": _briar_attack_damage_trigger,
        },
        {
            "event": "on_play",
            "condition_fn": lambda player, event, state: True,
            "effect_fn": _briar_second_nonattack_trigger,
        },
    ],
    # Katsu / Katsu the Wanderer: first hit per turn → optional discard + search combo
    "katsu": [{"event": "hit", "condition_fn": lambda p, e, s: True, "effect_fn": _katsu_on_hit_trigger}],
    "katsu_the_wanderer": [{"event": "hit", "condition_fn": lambda p, e, s: True, "effect_fn": _katsu_on_hit_trigger}],
    # Olympia / Olympia Prized Fighter: first wager win per turn → Gold token
    "olympia": [{"event": "wager_resolved", "condition_fn": lambda p, e, s: True, "effect_fn": _olympia_wager_win_trigger}],
    "olympia_prized_fighter": [{"event": "wager_resolved", "condition_fn": lambda p, e, s: True, "effect_fn": _olympia_wager_win_trigger}],
    # Victor Goldmane: first Gold creation per turn → draw
    "victor_goldmane": [{"event": "gold_created", "condition_fn": lambda p, e, s: True, "effect_fn": _victor_gold_creation_trigger}],
    "victor_goldmane_high_and_mighty": [{"event": "gold_created", "condition_fn": lambda p, e, s: True, "effect_fn": _victor_gold_creation_trigger}],
    "victor_goldmane_match_fixer": [{"event": "gold_created", "condition_fn": lambda p, e, s: True, "effect_fn": _victor_gold_creation_trigger}],
    # Valda: opponent draws in action phase → create Seismic Surge tokens
    "valda_brightaxe": [{"event": "card_draw", "condition_fn": lambda p, e, s: True, "effect_fn": _valda_opponent_draw_trigger}],
    "valda_seismic_impact": [{"event": "card_draw", "condition_fn": lambda p, e, s: True, "effect_fn": _valda_opponent_draw_trigger}],
    # Betsy: attack wagers → optional {r}{r} for +1{p} and overpower
    "betsy": [{"event": "wager_resolved", "condition_fn": lambda p, e, s: True, "effect_fn": _betsy_wager_trigger}],
    "betsy_skin_in_the_game": [{"event": "wager_resolved", "condition_fn": lambda p, e, s: True, "effect_fn": _betsy_wager_trigger}],
    # Data Doll MKII: Mech item with cost ≤2 banished from deck → put into arena
    "data_doll_mkii": [{"event": "card_banished", "condition_fn": lambda p, e, s: True, "effect_fn": _data_doll_banished_from_deck_trigger}],
    # Florian: 4+ Earth in banished → check on card_banished events
    "florian": [{"event": "card_banished", "condition_fn": lambda p, e, s: True, "effect_fn": _florian_banished_earth_trigger}],
    "florian_rotwood_harbinger": [{"event": "card_banished", "condition_fn": lambda p, e, s: True, "effect_fn": _florian_banished_earth_trigger}],
    # Riptide: play from hand → optional arsenal storage
    "riptide": [{"event": "on_play", "condition_fn": lambda p, e, s: True, "effect_fn": _riptide_play_from_hand_trigger}],
    "riptide_lurker_of_the_deep": [{"event": "on_play", "condition_fn": lambda p, e, s: True, "effect_fn": _riptide_play_from_hand_trigger}],
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

def _next_attack_go_again_apply(attack_card, player, state):
    """Grant go again to the next attack."""
    if "Go again" not in (attack_card.keywords or []):
        if not hasattr(attack_card, 'keywords') or attack_card.keywords is None:
            attack_card.keywords = []
        attack_card.keywords.append("Go again")

def _next_attack_cost_1_less_apply(attack_card, player, state):
    """Reduce next attack's cost by 1."""
    attack_card.effects.append(("cost", lambda c: max(0, c - 1)))

def _equip_next_attack_cost_minus2_apply(attack_card, player, state):
    """Equipment effect: reduce next attack's cost by 2."""
    attack_card.effects.append(("cost", lambda c: max(0, c - 2)))

def _bravo_dominate_cost3_apply(attack_card, player, state):
    """Bravo: attack actions with cost 3+ gain dominate."""
    if "Action" in (attack_card.types or []) and (attack_card.cost or 0) >= 3:
        if "Dominate" not in (attack_card.keywords or []):
            if not hasattr(attack_card, 'keywords') or attack_card.keywords is None:
                attack_card.keywords = []
            attack_card.keywords.append("Dominate")

def _craterhoof_dominate_apply(attack_card, player, state):
    """Craterhoof: next attack gains dominate."""
    if "Dominate" not in (attack_card.keywords or []):
        if not hasattr(attack_card, 'keywords') or attack_card.keywords is None:
            attack_card.keywords = []
        attack_card.keywords.append("Dominate")

def _azalea_arrow_bonus_apply(attack_card, player, state):
    """Azalea: Arrow from arsenal gets +1 power."""
    if "Arrow" in (attack_card.types or []):
        attack_card.effects.append(("base_power", lambda base: base + 1))

def _lexi_arrow_bonus_apply(attack_card, player, state):
    """Lexi: Arrow gets +1 power."""
    if "Arrow" in (attack_card.types or []):
        attack_card.effects.append(("base_power", lambda base: base + 1))

def _chane_next_action_go_again_apply(attack_card, player, state):
    """Chane: next attack action gains go again."""
    if "Action" in (attack_card.types or []):
        if "Go again" not in (attack_card.keywords or []):
            if not hasattr(attack_card, 'keywords') or attack_card.keywords is None:
                attack_card.keywords = []
            attack_card.keywords.append("Go again")

def _dorinthea_extra_weapon_attack_apply(attack_card, player, state):
    """Dorinthea: grants an additional weapon attack this turn (flag consumed by engine)."""
    # This is a flag-based effect; the engine checks for it separately.
    pass

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
    "next_attack_go_again": {
        "apply_fn": _next_attack_go_again_apply,
    },
    "next_attack_cost_1_less": {
        "apply_fn": _next_attack_cost_1_less_apply,
    },
    "equip_next_attack_cost_-2": {
        "apply_fn": _equip_next_attack_cost_minus2_apply,
    },
    "bravo_dominate_cost3": {
        "condition_fn": lambda attack_card, player, state: (
            "Attack" in attack_card.types and "Action" in attack_card.types
            and (attack_card.cost or 0) >= 3
        ),
        "apply_fn": _bravo_dominate_cost3_apply,
    },
    "craterhoof_dominate": {
        "apply_fn": _craterhoof_dominate_apply,
    },
    "azalea_arrow_bonus": {
        "condition_fn": lambda attack_card, player, state: "Arrow" in attack_card.types,
        "apply_fn": _azalea_arrow_bonus_apply,
    },
    "lexi_arrow_bonus": {
        "condition_fn": lambda attack_card, player, state: "Arrow" in attack_card.types,
        "apply_fn": _lexi_arrow_bonus_apply,
    },
    "chane_next_action_go_again": {
        "condition_fn": lambda attack_card, player, state: (
            "Attack" in attack_card.types and "Action" in attack_card.types
        ),
        "apply_fn": _chane_next_action_go_again_apply,
    },
    "dorinthea_extra_weapon_attack": {
        "apply_fn": _dorinthea_extra_weapon_attack_apply,
    },
}

# ---------------------------------------------------------------------------
# TURN_DEFEND_EFFECTS — consumed when a card is used to defend
# Signature: condition_fn(defend_card, player, state) -> bool
#            apply_fn(defend_card, player, state) -> None
# ---------------------------------------------------------------------------
TURN_DEFEND_EFFECTS = {
    "bravo_flattering_crush_bonus": {
        "condition_fn": lambda defend_card, player, state: (
            "Crush" in (defend_card.keywords or [])
        ),
        "apply_fn": lambda defend_card, player, state: defend_card.effects.append(
            ("base_defense", lambda base: base + 2)
        ),
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
    # Fate Foreseen: playable as defense reaction whenever there's an active attack
    "fate_foreseen_red": lambda combat: combat is not None and combat.attack_card is not None,
    "fate_foreseen_yellow": lambda combat: combat is not None and combat.attack_card is not None,
    "fate_foreseen_blue": lambda combat: combat is not None and combat.attack_card is not None,
    # Sink Below: standard defense reaction
    "sink_below_red": lambda combat: combat is not None and combat.attack_card is not None,
    "sink_below_yellow": lambda combat: combat is not None and combat.attack_card is not None,
    "sink_below_blue": lambda combat: combat is not None and combat.attack_card is not None,
    # Unmovable: standard defense reaction
    "unmovable_red": lambda combat: combat is not None and combat.attack_card is not None,
    "unmovable_yellow": lambda combat: combat is not None and combat.attack_card is not None,
    "unmovable_blue": lambda combat: combat is not None and combat.attack_card is not None,
    # Staunch Response: standard defense reaction
    "staunch_response_red": lambda combat: combat is not None and combat.attack_card is not None,
    "staunch_response_yellow": lambda combat: combat is not None and combat.attack_card is not None,
    "staunch_response_blue": lambda combat: combat is not None and combat.attack_card is not None,
    # Sigil of Solace: standard defense reaction (gain life)
    "sigil_of_solace_red": lambda combat: combat is not None and combat.attack_card is not None,
    "sigil_of_solace_yellow": lambda combat: combat is not None and combat.attack_card is not None,
    "sigil_of_solace_blue": lambda combat: combat is not None and combat.attack_card is not None,
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
# Dragonscaler Flight Path (Equipment - Legs)
# "Instant - {r}{r}{r}, destroy this: Target Draconic attack gets go again.
#  If it's a weapon or ally attack, you may attack with it an additional time
#  this turn. This ability costs {r} less for each Draconic chain link you
#  control."
# ---------------------------------------------------------------------------

def _dragonscaler_activation_cost(player, state) -> int:
    """Base cost 3, minus 1 per Draconic chain link the activating player controls.
    A Draconic chain link is one whose attack card had 'Draconic' in its types."""
    draconic_links = 0
    for link in (state.chain_links or []):
        if link.attacker_id != player.player_id:
            continue
        # Look up the attack card's types from LKI cache or CardDB
        lki_types = state.last_known_value(link.attack_slug, "types")
        if lki_types is None and hasattr(state, "card_db") and state.card_db is not None:
            card = state.card_db.get(link.attack_slug)
            lki_types = card.types if card else []
        if "Draconic" in (lki_types or []):
            draconic_links += 1
    return max(0, 3 - draconic_links)


def _dragonscaler_condition(player, slot_name, equip_card, state) -> bool:
    """Dragonscaler Flight Path: activatable as Instant only during combat when
    there is at least one Draconic attack on the chain (current or past link)."""
    if state.combat is None:
        return False
    # Current attack is Draconic
    if state.combat.attack_card and "Draconic" in (state.combat.attack_card.types or []):
        return True
    # A past chain link from this player is Draconic (weapon/ally re-attack target)
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
    The target can be the current chain-link attack OR a previous weapon/ally attack
    from this player's chain links — allowing a weapon or ally to swing again.
    If it's a weapon or ally attack, the player gains an extra attack with it this turn."""
    from engine.card_effects.keywords import _ask_player

    # Build list of targetable Draconic attacks: current + past links (weapon/ally from this player)
    targets = []
    if state.combat and state.combat.attack_card:
        ac = state.combat.attack_card
        if "Draconic" in (ac.types or []):
            targets.append(("current", ac, state.combat.from_weapon, "Ally" in (ac.types or [])))

    for link in (state.chain_links or []):
        if link.attacker_id != player.player_id:
            continue
        # Weapon/ally re-attack targets: look up card types
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

    # If multiple targets, ask player to choose; otherwise auto-select
    if len(targets) > 1:
        options = [f"{t[0]}:{t[1].attack_slug if hasattr(t[1], 'attack_slug') else t[1].slug}" for t in targets]
        choice_idx = _ask_player(state, player.player_id, list(range(len(targets))),
                                  context="Dragonscaler Flight Path: choose target Draconic attack")
        chosen = targets[choice_idx] if isinstance(choice_idx, int) and 0 <= choice_idx < len(targets) else targets[0]
    else:
        chosen = targets[0]

    target_type, target_obj, is_weapon, is_ally = chosen

    if target_type == "current":
        # Grant go again to the active chain link
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
        # Past link — grant extra weapon/ally attack this turn
        if is_weapon or is_ally:
            player.current_turn_effects.append("dragonscaler_extra_attack")


EQUIPMENT_ACTIVATION_CONDITIONS["dragonscaler_flight_path"] = _dragonscaler_condition
EQUIPMENT_ACTIVATION_COST["dragonscaler_flight_path"] = _dragonscaler_activation_cost
EQUIPMENT_PAY_COSTS["dragonscaler_flight_path"] = _dragonscaler_pay_cost
EQUIPMENT_ACTIVATION_EFFECTS["dragonscaler_flight_path"] = _dragonscaler_effect