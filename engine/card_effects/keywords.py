"""Keyword ability implementations for FAB engine.

Each keyword function implements the game mechanic per the comprehensive rules (8.3/8.4/8.5).
Functions are registered as triggers or replacement effects by the trigger registry.

Rules reference:
  8.3 — Ability Keywords (Battleworn, Blade Break, Temper, Go again, etc.)
  8.4 — Label Keywords (Combo, Crush, Reprise, Surge, etc.)
  8.5 — Effect Keywords (Banish, Draw, Deal damage, etc.)

Owner vs Controller (rules 1.3):
  owner  — immutable, the player who brought the card to the game (set at game start)
  controller — who currently controls the card; changes via gain-control effects
  All effect logic uses controller (falling back to owner if controller is None).

Arena zones (rules 3.0.5):
  arms, chest, combat chain, head, hero, legs, permanent (items/auras/allies/tokens), weapon

Optional abilities:
  Use state.player_agents[player_id](state, options) to present choices.
  Agent returns one of the options.

Zone tracking:
  Every Zone.remove() must be followed by a Zone.add() to keep card.zone / card.prev_zone
  consistent. Zone.add() sets prev_zone = old zone and zone = new zone name.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from engine.card import Card

if TYPE_CHECKING:
    from engine.state import GameState, Event, Player, Zone
    from engine.card import CardDB

# Per rules 3.0.5 — zones that comprise the arena.
ARENA_ZONE_NAMES = frozenset({
    "head", "chest", "arms", "legs", "weapon",
    "hero", "permanents",
    "combat chain",
})


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _controller_id(card: Card) -> int:
    """Get the controlling player's id, falling back to owner."""
    return card.controller if card.controller is not None else card.owner


def _get_controller(state: GameState, card: Card) -> Player:
    return state.players[_controller_id(card)]


def _get_owner(state: GameState, card: Card) -> Player:
    return state.players[card.owner]


def _get_opponent_of(state: GameState, player_id: int) -> Player:
    return state.players[3 - player_id]


def _was_in_arena(card: Card) -> bool:
    """Check if card's previous zone was in the arena."""
    return card.prev_zone in ARENA_ZONE_NAMES


def _ask_player(state: GameState, player_id: int, options, context: str = "") -> object:
    """Present options to the player agent and return their choice.
    context: human-readable description of what the player is deciding."""
    return state.player_agents[player_id](state, options, context=context)


def _remove_from_current_zone(card: Card, state: GameState) -> bool:
    """Remove card from whatever zone it currently sits in.
    MUST be followed by a Zone.add() call to maintain zone tracking."""
    state.remember_last_known(card, overwrite=False)
    cid = _controller_id(card)
    players_to_search = []
    if cid in state.players:
        players_to_search.append(state.players[cid])
    for player in state.players.values():
        if player not in players_to_search:
            players_to_search.append(player)

    for player in players_to_search:
        for zone in player.all_zones():
            if zone.remove(card):
                return True
    # Shared zones
    if state.combat_chain.remove(card):
        return True
    if state.stack.remove(card):
        return True
    return False


def _move_to_graveyard(card: Card, state: GameState) -> None:
    """Destroy a card — move it to its OWNER's graveyard (8.5.4).
    Emits leaves_arena if card was in an arena zone, and card_destroyed."""
    was_arena = _was_in_arena(card) or card.zone in ARENA_ZONE_NAMES
    state.process_cease_to_exist(card)
    _remove_from_current_zone(card, state)
    owner = _get_owner(state, card)
    owner.graveyard.add(card)  # add() updates card.prev_zone and card.zone
    if was_arena:
        state.event_manager.emit(
            type('Event', (), {'type': 'leaves_arena', 'data': {'card': card}})(),
            state)
    state.event_manager.emit(
        type('Event', (), {'type': 'card_destroyed', 'data': {'card': card}})(),
        state)


def _draw_cards(player: Player, count: int) -> list:
    drawn = []
    for _ in range(count):
        if not player.deck.cards:
            break
        card = player.deck.pop_top()
        if card is not None:
            player.hand.add(card)  # add() updates zone tracking
            drawn.append(card)
    return drawn


def _deal_damage(state: GameState, target_player: Player, amount: int,
                 source: Card = None, damage_type: str = "generic") -> int:
    """Deal damage to a player. Returns actual damage dealt after prevention."""
    if amount <= 0:
        return 0
    event = {
        "type": "damage",
        "damage_type": damage_type,
        "amount": amount,
        "target_player_id": target_player.player_id,
        "source": source,
    }
    if hasattr(state, 'effect_manager') and state.effect_manager:
        event = state.effect_manager.apply_replacements(event, state)
    actual = event.get("amount", 0)
    if actual > 0:
        target_player.health -= actual
    return actual


def _apply_defense_counter(card: Card, state: GameState, count: int = 1) -> None:
    """Apply -1{d} counters to a card. Manages the effect list cleanly."""
    controller = _get_controller(state, card)
    key = (card.slug, card.zone, "minus_defense")
    controller.counters[key] = controller.counters.get(key, 0) + count
    # Remove stale counter effect, add fresh one
    card.effects = [(tag, fn) for tag, fn in card.effects
                    if not (tag == "base_defense" and getattr(fn, '_counter_key', None) == key)]
    def _apply(base, k=key, p=controller):
        return base - p.counters.get(k, 0)
    _apply._counter_key = key
    card.effects.append(("base_defense", _apply))


def _pitch_for_cost(controller: Player, amount: int, state: GameState,
                    exclude_card: Card = None) -> bool:
    """Attempt to pitch cards from hand to pay a resource cost.
    Uses find_all_valid_pitch_sequences to find valid options,
    then asks the agent to choose. Returns True if cost was paid."""
    from engine.actions import find_all_valid_pitch_sequences
    cid = controller.player_id
    hand_cards = [c for c in controller.hand.cards
                  if exclude_card is None or c.slug != exclude_card.slug]
    needed = amount - controller.resources
    if needed <= 0:
        controller.resources -= amount
        return True
    sequences = find_all_valid_pitch_sequences(hand_cards, needed, controller.resources)
    if not sequences:
        return False
    # Let agent choose which pitch sequence
    choice = _ask_player(state, cid, list(range(len(sequences))),
                         context="Choose pitch order for suspense cost")
    seq = sequences[choice]
    for item in seq:
        # find_all_valid_pitch_sequences currently returns Card objects.
        # Keep backward compatibility with older index-based sequences.
        if isinstance(item, int):
            card = hand_cards[item]
        else:
            card = item
        if card not in controller.hand.cards:
            continue
        controller.hand.remove(card)
        controller.pitch.add(card)  # add() updates zone tracking
        controller.resources += card.pitch or 0
    controller.resources -= amount
    return True


# ---------------------------------------------------------------------------
# 8.3 Ability Keywords — Triggered on combat chain close
# ---------------------------------------------------------------------------

def battleworn(card: Card, event: Event, state: GameState) -> None:
    """8.3.2: When combat chain closes, if this defended, put a -1{d} counter on it."""
    _apply_defense_counter(card, state, 1)


def blade_break(card: Card, event: Event, state: GameState) -> None:
    """8.3.3: When combat chain closes, if this defended, destroy it."""
    _move_to_graveyard(card, state)


def temper(card: Card, event: Event, state: GameState) -> None:
    """8.3.10: When combat chain closes, if this defended, put a -1{d} counter on it,
    then destroy it if it has zero {d}."""
    _apply_defense_counter(card, state, 1)
    if card.defense is not None and card.defense <= 0:
        _move_to_graveyard(card, state)


def guardwell(card: Card, event: Event, state: GameState) -> None:
    """8.3.34: When combat chain closes, if this defended, put -1{d} counters
    on it equal to its {d} (modified defense, not base)."""
    current_def = card.defense
    if current_def is not None and current_def > 0:
        _apply_defense_counter(card, state, current_def)


# ---------------------------------------------------------------------------
# 8.3 Ability Keywords — Static / Continuous
# ---------------------------------------------------------------------------

def dominate_check(card: Card, state: GameState) -> bool:
    """8.3.4: Can't be defended by more than one card from hand."""
    if not state.combat:
        return False
    return sum(1 for c in state.combat.defending_cards if c.prev_zone == "hand") >= 1


def overpower_check(card: Card, state: GameState) -> bool:
    """8.3.22: Can't be defended by more than one action card."""
    if not state.combat:
        return False
    return sum(1 for c in state.combat.defending_cards if "Action" in c.types) >= 1


def go_again(card: Card, state: GameState) -> None:
    """8.3.5: Gain 1 action point on resolution (turn player only, 8.5.7b)."""
    cid = _controller_id(card)
    if cid == state.active_player:
        state.players[cid].action_points += 1


def piercing(card: Card, amount: int, state: GameState) -> None:
    """8.3.23: If defended by equipment, gets +N{p}."""
    if state.combat and any(c.is_equipment for c in state.combat.defending_cards):
        card.effects.append(("base_power", lambda base, n=amount: base + n))


# ---------------------------------------------------------------------------
# 8.3 Ability Keywords — Triggered static abilities
# ---------------------------------------------------------------------------

def phantasm_check(card: Card, event: Event, state: GameState) -> bool:
    """8.3.13: Check if a non-Illusionist attack action card with 6+ power is defending."""
    if not state.combat:
        return False
    for d in state.combat.defending_cards:
        if (d.is_attack and d.is_action and
            "Illusionist" not in d.types and
            d.power is not None and d.power >= 6):
            return True
    return False


def phantasm_destroy(card: Card, event: Event, state: GameState) -> None:
    """8.3.13: Destroy the phantasm attack (state-trigger re-checked on resolve)."""
    if phantasm_check(card, event, state):
        _move_to_graveyard(card, state)


def spectra_destroy(card: Card, event: Event, state: GameState) -> None:
    """8.3.14: When this becomes target of an attack, destroy it."""
    _move_to_graveyard(card, state)


def blood_debt(card: Card, event: Event, state: GameState) -> None:
    """8.3.11: While in banished zone (public), at beginning of end phase, lose 1 life."""
    if card.zone == "banished" and card.is_public:
        owner = _get_owner(state, card)
        owner.health -= 1


def suspense_remove_counter(card: Card, event: Event, state: GameState) -> None:
    """8.3.42: At start of turn, remove a suspense counter. Destroy when 0."""
    controller = _get_controller(state, card)
    key = (card.slug, card.zone, "suspense")
    current = controller.counters.get(key, 0)
    if current > 0:
        controller.counters[key] = current - 1
    if controller.counters.get(key, 0) <= 0:
        _move_to_graveyard(card, state)


def suspense_enter(card: Card, state: GameState) -> None:
    """8.3.42: Enters arena with 2 suspense counters."""
    controller = _get_controller(state, card)
    key = (card.slug, card.zone, "suspense")
    controller.counters[key] = 2


def watery_grave(card: Card, event: Event, state: GameState) -> None:
    """8.3.41: When put into graveyard from the arena, turn face-down.
    Arena includes combat chain per rules 3.0.5 / 7.0.3f."""
    if card.zone == "graveyard" and _was_in_arena(card):
        state.set_card_visibility(card, False)


# ---------------------------------------------------------------------------
# 8.3 Ability Keywords — Optional play-static / cost modifiers
# All optional abilities present choices to the agent via _ask_player.
# ---------------------------------------------------------------------------

def boost(card: Card, state: GameState) -> bool:
    """8.3.9: Optional additional cost — banish top of deck.
    If Mechanologist, gain go again. Returns True if boosted Mech card."""
    controller = _get_controller(state, card)
    cid = _controller_id(card)
    if not controller.deck.cards:
        return False
    choice = _ask_player(state, cid, [True, False],
                         context="Boost: banish top of deck to gain go again? (Mechanologist)")
    if not choice:
        return False
    top = controller.deck.pop_top()
    if top:
        controller.banished.add(top)  # add() updates zone tracking
        if "Mechanologist" in top.types:
            if "Go again" not in card.keywords:
                card.keywords.append("Go again")
            return True
    return False


def heave(card: Card, amount: int, state: GameState) -> bool:
    """8.3.18: Hidden triggered ability — while in hand, at beginning of end phase,
    may pay N resources and put into arsenal face-up. Creates N Seismic Surge tokens.
    Player can pitch cards from hand to pay the cost."""
    controller = _get_controller(state, card)
    cid = _controller_id(card)
    if card.zone != "hand":
        return False
    if controller.arsenal.cards:
        return False
    # Check if player can afford (resources + pitchable cards)
    from engine.actions import find_all_valid_pitch_sequences
    hand_cards = [c for c in controller.hand.cards if c.slug != card.slug]
    needed = amount - controller.resources
    if needed > 0:
        sequences = find_all_valid_pitch_sequences(hand_cards, needed, controller.resources)
        if not sequences:
            return False
    # Ask if player wants to heave
    choice = _ask_player(state, cid, [True, False],
                         context=f"Heave {amount}: Pay {amount} resource(s) to put this card face-up into your arsenal and create {amount} Seismic Surge token(s)?")
    if not choice:
        return False
    # Pay the cost (pitch if needed)
    if not _pitch_for_cost(controller, amount, state, exclude_card=card):
        return False
    controller.hand.remove(card)
    controller.arsenal.add(card, is_public=True)  # add() updates zone tracking
    for _ in range(amount):
        _create_token(state, controller, "seismic_surge")
    return True


def crank(card: Card, state: GameState) -> bool:
    """8.3.29: As this enters arena, may remove a steam counter. Gain action point."""
    controller = _get_controller(state, card)
    cid = _controller_id(card)
    key = (card.slug, card.zone, "steam")
    current = controller.counters.get(key, 0)
    if current <= 0:
        return False
    choice = _ask_player(state, cid, [True, False],
                         context="Remove a steam counter to gain action point? (Crank)")
    if not choice:
        return False
    controller.counters[key] = current - 1
    effect_gain_action_point(state, cid)
    return True


def fusion(card: Card, supertype: str, state: GameState) -> bool:
    """8.3.17: Optional additional cost — reveal a card with the specified supertype
    from hand. Returns True if fused."""
    controller = _get_controller(state, card)
    cid = _controller_id(card)
    matching = [c for c in controller.hand.cards
                if supertype in c.types and c.slug != card.slug]
    if not matching:
        return False
    choice = _ask_player(state, cid, [True, False],
                         context=f"Fuse: reveal a {supertype} card from hand as additional cost?")
    if not choice:
        return False
    reveal_choice = _ask_player(state, cid,
                                [c.slug for c in matching],
                                context=f"Choose which {supertype} card to reveal for Fusion")
    revealed = controller.hand.find(reveal_choice)
    if revealed:
        state.set_card_visibility(revealed, True)
    return True


def arcane_barrier(card: Card, amount: int, state: GameState,
                   ) -> int:
    """8.3.8: Optional — pay N resources to prevent N arcane damage.
    Player can pitch to pay. Returns amount prevented."""
    controller = _get_controller(state, card)
    cid = _controller_id(card)
    # Check affordability including pitching
    from engine.actions import find_all_valid_pitch_sequences
    hand_cards = list(controller.hand.cards)
    needed = amount - controller.resources
    if needed > 0:
        sequences = find_all_valid_pitch_sequences(hand_cards, needed, controller.resources)
        if not sequences:
            return 0
    choice = _ask_player(state, cid, [True, False],
                         context="Activate Arcane Barrier to prevent arcane damage?")
    if not choice:
        return 0
    if not _pitch_for_cost(controller, amount, state):
        return 0
    return amount


def spellvoid(card: Card, amount: int, state: GameState,
              ) -> int:
    """8.3.15: Optional — destroy this to prevent N arcane damage.
    Returns amount prevented."""
    cid = _controller_id(card)
    choice = _ask_player(state, cid, [True, False],
                         context="Destroy this to activate Spellvoid and prevent arcane damage?")
    if not choice:
        return 0
    _move_to_graveyard(card, state)
    return amount


def ward(card: Card, amount: int, state: GameState) -> int:
    """8.3.20: Destroy this to prevent N damage. NOT optional per rules —
    activates automatically when damage would be dealt. Returns amount prevented."""
    _move_to_graveyard(card, state)
    return amount


def quell(card: Card, amount: int, state: GameState,
          ) -> int:
    """8.3.19: Optional — pay N resources to prevent N damage.
    Destroyed at beginning of end phase if used. Returns amount prevented."""
    controller = _get_controller(state, card)
    cid = _controller_id(card)
    # Check affordability including pitching
    from engine.actions import find_all_valid_pitch_sequences
    hand_cards = list(controller.hand.cards)
    needed = amount - controller.resources
    if needed > 0:
        sequences = find_all_valid_pitch_sequences(hand_cards, needed, controller.resources)
        if not sequences:
            return 0
    choice = _ask_player(state, cid, [True, False],
                         context="Activate Quell to prevent damage? (pay resources)")
    if not choice:
        return 0
    if not _pitch_for_cost(controller, amount, state):
        return 0
    controller.current_turn_effects.append(f"quell_destroy_{card.slug}")
    return amount


def arcane_shelter(card: Card, amount: int, state: GameState) -> int:
    """8.3.37: Destroy this to prevent N arcane damage. NOT optional.
    Returns amount prevented."""
    _move_to_graveyard(card, state)
    return amount


# ---------------------------------------------------------------------------
# 8.4 Label Keywords — Conditional triggers
# ---------------------------------------------------------------------------

def crush_check(event: Event, state: GameState) -> bool:
    """8.4.2: Check if attack dealt 4+ damage."""
    data = event.data if isinstance(event.data, dict) else {}
    return data.get("damage_dealt", 0) >= 4


def reprise_check(state: GameState) -> bool:
    """8.4.3: Defending hero defended with a card from hand this chain link."""
    if not state.combat:
        return False
    return any(c.prev_zone == "hand" for c in state.combat.defending_cards)


def combo_check(state: GameState, combo_names: list) -> bool:
    """8.4.1: One of the named cards was the last attack this combat chain."""
    if not state.chain_links:
        return False
    return state.chain_links[-1].attack_slug in combo_names


def surge_check(event: Event, amount: int) -> bool:
    """8.4.8: Check if this dealt N+ damage."""
    data = event.data if isinstance(event.data, dict) else {}
    return data.get("damage_dealt", 0) >= amount


def rupture_check(state: GameState) -> bool:
    """8.4.6: Played at chain link 4 or higher."""
    return len(state.chain_links) >= 3


def channel_upkeep(card: Card, supertype: str, state: GameState,
                   ) -> None:
    """8.4.4: Put flow counter, then destroy unless matching cards from pitch.
    Player chooses whether to pay."""
    controller = _get_controller(state, card)
    cid = _controller_id(card)
    key = (card.slug, card.zone, "flow")
    controller.counters[key] = controller.counters.get(key, 0) + 1
    flow_count = controller.counters[key]
    matching = [c for c in controller.pitch.cards if supertype in c.types]
    if len(matching) >= flow_count:
        choice = _ask_player(state, cid, [True, False],
                             context="Pay channel upkeep cost to keep this active?")
        if choice:
            for i in range(flow_count):
                c = matching[i]
                controller.pitch.remove(c)
                controller.deck.add(c)  # add() updates zone tracking
            return
    _move_to_graveyard(card, state)


def galvanize(card: Card, state: GameState) -> bool:
    """8.4.12: When this defends, may destroy an item you control."""
    controller = _get_controller(state, card)
    cid = _controller_id(card)
    if not controller.items.cards:
        return False
    choice = _ask_player(state, cid, [True, False],
                         context="Choose target for Galvanize")
    if not choice:
        return False
    item_slugs = [c.slug for c in controller.items.cards]
    item_choice = _ask_player(state, cid, item_slugs,
                              context="Choose item to destroy for Galvanize")
    item = controller.items.find(item_choice)
    if item:
        _move_to_graveyard(item, state)
        return True
    return False


# ---------------------------------------------------------------------------
# 8.5 Effect Keywords — Discrete effects
# ---------------------------------------------------------------------------

def effect_draw(state: GameState, player_id: int, count: int = 1) -> list:
    """8.5.6: Draw N cards."""
    return _draw_cards(state.players[player_id], count)


def effect_discard(state: GameState, player_id: int, count: int = 1,
                   random_discard: bool = False) -> list:
    """8.5.5: Discard N cards from hand to graveyard.
    If not random, agent chooses which cards."""
    player = state.players[player_id]
    discarded = []
    for _ in range(count):
        if not player.hand.cards:
            break
        if random_discard:
            import random as rng
            idx = rng.randint(0, len(player.hand.cards) - 1)
            card = player.hand.cards[idx]
        else:
            slugs = [c.slug for c in player.hand.cards]
            choice = _ask_player(state, player_id, slugs,
                                 context="Choose a card to discard")
            card = player.hand.find(choice)
            if card is None:
                card = player.hand.cards[0]
        player.hand.remove(card)
        player.graveyard.add(card)  # add() updates zone tracking
        discarded.append(card)
    return discarded


def effect_banish(state: GameState, card: Card, face_up: bool = True,
                  banisher_id: int = None) -> None:
    """8.5.1: Banish a card to OWNER's banished zone.
    banisher_id: player who caused the banish (for contract tracking)."""
    _remove_from_current_zone(card, state)
    owner = _get_owner(state, card)
    owner.banished.add(card, is_public=face_up)  # add() updates zone tracking
    # Emit card_banished event for contract mechanics (8.5.39)
    state.event_manager.emit(
        type('Event', (), {'type': 'card_banished',
                           'data': {'card': card, 'banisher_id': banisher_id}})(),
        state)


def effect_deal_damage(state: GameState, target_player_id: int, amount: int,
                       source: Card = None, damage_type: str = "generic") -> int:
    """8.5.3: Deal damage to a player."""
    return _deal_damage(state, state.players[target_player_id], amount, source, damage_type)


def effect_deal_arcane(state: GameState, target_player_id: int, amount: int,
                       source: Card = None) -> int:
    """8.5.3b: Deal arcane damage, applying amp before prevention."""
    # CR 8.5.47: consume the first amp_N effect owned by the source controller
    if source is not None:
        source_id = _controller_id(source)
        source_player = state.players.get(source_id)
        if source_player:
            for i, eff in enumerate(source_player.current_turn_effects):
                if isinstance(eff, str) and eff.startswith("amp_"):
                    try:
                        n = int(eff[4:])
                        amount += n
                        source_player.current_turn_effects.pop(i)
                    except ValueError:
                        pass
                    break
    result = effect_deal_damage(state, target_player_id, amount, source, "arcane")
    if result > 0 and source is not None:
        source_id = _controller_id(source)
        source_player = state.players.get(source_id)
        if source_player:
            # Track dealt_arcane for Consign to Cosmos // Shock and Null // Shock
            for _ in range(result):
                source_player.current_turn_effects.append("dealt_arcane")
                if target_player_id == (3 - source_id):
                    source_player.current_turn_effects.append("dealt_arcane_to_opp_hero")
            # Emit arcane_damage_dealt for any registered listeners
            from engine.state import Event
            state.event_manager.emit(
                Event(type='arcane_damage_dealt',
                      data={'amount': result, 'target_player_id': target_player_id,
                            'source': source}),
                state)
    return result


def effect_gain_life(state: GameState, player_id: int, amount: int) -> None:
    """8.5.7a: Gain life."""
    state.players[player_id].health += amount


def effect_lose_life(state: GameState, player_id: int, amount: int) -> None:
    """8.5.12a: Lose life (not damage)."""
    state.players[player_id].health -= amount


def effect_gain_action_point(state: GameState, player_id: int, amount: int = 1) -> None:
    """8.5.7b: Gain action points (only turn player)."""
    if player_id == state.active_player:
        state.players[player_id].action_points += amount


def effect_gain_resources(state: GameState, player_id: int, amount: int = 1) -> None:
    state.players[player_id].resources += amount


def effect_destroy(state: GameState, card: Card) -> None:
    """8.5.4: Destroy a card (put into owner's graveyard)."""
    _move_to_graveyard(card, state)


def effect_opt(state: GameState, player_id: int, count: int,
               ) -> None:
    """8.5.22: Look at top N of deck, put any on top or bottom.
    Agent chooses ordering."""
    player = state.players[player_id]
    if not player.deck.cards:
        return
    top_cards = player.deck.cards[:count]
    for card in top_cards:
        choice = _ask_player(state, player_id, ["top", "bottom"],
                             context="Opt: put this card on top or bottom of deck?")
        player.deck.cards.remove(card)
        if choice == "top":
            player.deck.cards.insert(0, card)
        else:
            player.deck.cards.append(card)


def effect_intimidate(state: GameState, target_player_id: int,
                      source: Card = None) -> Card:
    """8.5.10: Banish a random card from target's hand face-down.
    Returns at beginning of end phase (delayed trigger)."""
    target = state.players[target_player_id]
    if not target.hand.cards:
        return None
    import random as rng
    idx = rng.randint(0, len(target.hand.cards) - 1)
    card = target.hand.cards[idx]
    target.hand.remove(card)
    target.banished.add(card, is_public=False)  # add() updates zone tracking
    return card


def effect_put_counter(state: GameState, card: Card, counter_type: str,
                       amount: int = 1) -> None:
    """8.5.14: Put counter(s) on a card."""
    controller = _get_controller(state, card)
    key = (card.slug, card.zone, counter_type)
    controller.counters[key] = controller.counters.get(key, 0) + amount


def effect_remove_counter(state: GameState, card: Card, counter_type: str,
                          amount: int = 1) -> int:
    """8.5.16: Remove counter(s). Returns amount removed."""
    controller = _get_controller(state, card)
    key = (card.slug, card.zone, counter_type)
    current = controller.counters.get(key, 0)
    removed = min(current, amount)
    controller.counters[key] = current - removed
    return removed


def effect_search_deck(state: GameState, player_id: int, condition=None,
                       ) -> Card:
    """8.5.19: Search deck. Agent chooses from matching cards."""
    player = state.players[player_id]
    if not player.deck.cards:
        return None
    if condition:
        matches = [c for c in player.deck.cards if condition(c)]
        if not matches:
            return None
        choice = _ask_player(state, player_id,
                             [c.slug for c in matches],
                             context="Search deck: choose a card to put into hand")
        return next((c for c in matches if c.slug == choice), matches[0])
    return None


def effect_shuffle(state: GameState, player_id: int) -> None:
    """8.5.20: Shuffle deck."""
    import random as rng
    rng.shuffle(state.players[player_id].deck.cards)
    state.invalidate_pitch_history(player_id)  # CR 8.5.20: order now unknown


def effect_amp(state: GameState, player_id: int, amount: int) -> None:
    """8.5.47: Next arcane damage this turn deals +N."""
    state.players[player_id].current_turn_effects.append(f"amp_{amount}")


def effect_freeze(state: GameState, card: Card) -> None:
    """8.5.34: Card can't be played or activated."""
    card.exhausted = True


def effect_charge(state: GameState, player_id: int, card: Card) -> None:
    """8.5.29: Move card from hand to hero's soul."""
    player = state.players[player_id]
    player.hand.remove(card)
    player.permanents.add(card)  # add() updates zone tracking


def effect_mark(state: GameState, target_player_id: int) -> None:
    """8.5.50: Mark a hero — gives them the marked condition (9.3).
    Cleared when hit by opponent (9.3.3) or hero ceases to exist."""
    state.players[target_player_id].marked = True


def is_marked(state: GameState, player_id: int) -> bool:
    """Check if a player's hero has the marked condition."""
    return state.players[player_id].marked


def effect_negate(state: GameState, target_entry) -> bool:
    """8.5.26: Negate a layer — clear it from the stack without resolving.
    target_entry is the StackEntry to negate."""
    if target_entry not in state.stack_entries:
        return False
    state.stack_entries.remove(target_entry)
    if target_entry.card:
        # CR 5.3.4c: negated layer ceases to exist without resolving; capture LKI at stack zone.
        if getattr(target_entry, 'layer_type', 'card') == 'card':
            state.process_cease_to_exist(target_entry.card)
        owner = state.players[target_entry.card.owner]
        owner.graveyard.add(target_entry.card)
    return True


def effect_retrieve_dagger(state: GameState, player_id: int) -> bool:
    """8.5.51: Retrieve a dagger from graveyard — pay {r} to equip to empty weapon zone.
    Player can pitch from hand to pay the {r} cost."""
    player = state.players[player_id]
    daggers = [c for c in player.graveyard.cards if "Dagger" in c.types and "Weapon" in c.types]
    if not daggers:
        return False
    # 8.5.51a: must have an empty weapon zone to equip to
    # A player with a 2H weapon has no room; with 0 or 1 1H weapons they may have room
    has_2h = any("2H" in c.types for c in player.weapon.cards)
    if has_2h or len(player.weapon.cards) >= 2:
        return False
    # Check if player can afford {r} (floating resources + pitchable hand cards)
    from engine.actions import find_all_valid_pitch_sequences
    needed = 1 - player.resources
    if needed > 0:
        sequences = find_all_valid_pitch_sequences(player.hand.cards, needed, player.resources)
        if not sequences:
            return False
    choice = _ask_player(state, player_id, [True, False],
                         context="Destroy target dagger?")
    if not choice:
        return False
    # Pay the cost (pitch if needed)
    if not _pitch_for_cost(player, 1, state):
        return False
    dagger_slugs = [d.slug for d in daggers]
    pick = _ask_player(state, player_id, dagger_slugs,
                       context="Choose dagger to destroy")
    dagger = next((d for d in daggers if d.slug == pick), daggers[0])
    player.graveyard.remove(dagger)
    dagger.controller = player_id
    player.weapon.add(dagger)
    return True


# ---------------------------------------------------------------------------
# Additional mechanics
# ---------------------------------------------------------------------------

def roll_die(state: GameState, player_id: int, sides: int = 6) -> int:
    """Roll a die with the given number of sides. Returns the result."""
    import random as rng
    result = rng.randint(1, sides)
    state.event_manager.emit(
        type('Event', (), {'type': 'die_roll', 'data': {'player_id': player_id, 'result': result}})(),
        state
    )
    return result


# ---------------------------------------------------------------------------
# Token definitions (from slug_index.json)
# ---------------------------------------------------------------------------

WEAPON_TOKENS = {
    "graphene_chelicera": {
        "name": "Graphene Chelicera",
        "slug": "graphene_chelicera",
        "color": "",
        "pitch": None,
        "cost": None,
        "power": 1,
        "defense": None,
        "types": ["Assassin", "Token", "Weapon", "Dagger", "1H"],
        "keywords": ["Stealth", "Go again"],
        "functional_text": "**Stealth**\n\n**Once per Turn Action** - {r}: **Attack**\n\nWhen this attacks a **marked** hero, the attack gets **go again**.",
    },
    "goldfin_harpoon_yellow": {
        "name": "Goldfin Harpoon",
        "slug": "goldfin_harpoon_yellow",
        "color": "Yellow",
        "pitch": None,
        "cost": 0,
        "power": 2,
        "defense": None,
        "types": ["Pirate", "Ranger", "Action", "Arrow", "Attack"],
        "keywords": [],
        "functional_text": "If this would be put into a graveyard, instead remove it from the game.",
    },
}


def create_token_card(token_slug: str, owner_id: int) -> Card:
    """Create a Card instance from a token definition."""
    defn = WEAPON_TOKENS.get(token_slug)
    if defn is None:
        raise ValueError(f"Unknown token: {token_slug}")
    card = Card(
        slug=defn["slug"],
        name=defn["name"],
        types=list(defn["types"]),
        keywords=list(defn["keywords"]),
        base_pitch=defn["pitch"],
        base_cost=defn["cost"],
        base_power=defn["power"],
        base_defense=defn["defense"],
        base_functional_text=defn["functional_text"],
    )
    card.owner = owner_id
    card.controller = owner_id
    card.is_public = True
    return card


def effect_crowd_boos(state: GameState, player_id: int) -> None:
    """The crowd boos you — tracks that this player has been booed this turn."""
    player = state.players[player_id]
    player.current_turn_effects.append("crowd_booed")
    state.event_manager.emit(
        type('Event', (), {'type': 'crowd_boos', 'data': {'player_id': player_id}})(),
        state
    )


def has_been_booed(state: GameState, player_id: int) -> bool:
    """Check if player has been booed this turn."""
    return "crowd_booed" in state.players[player_id].current_turn_effects


def effect_steal_token(state: GameState, stealer_id: int, victim_id: int,
                       token_type: str = None) -> bool:
    """Steal a token from another player. Agent chooses which if multiple."""
    victim = state.players[victim_id]
    stealer = state.players[stealer_id]

    # Gather stealable aura tokens
    stealable = list(victim.auras.cards)
    if token_type:
        stealable = [t for t in stealable if token_type in t.slug]
    if not stealable:
        return False

    if len(stealable) == 1:
        token = stealable[0]
    else:
        choice = _ask_player(state, stealer_id, [t.slug for t in stealable],
                             context="Choose Gold token to steal")
        token = next((t for t in stealable if t.slug == choice), stealable[0])

    victim.auras.remove(token)
    token.controller = stealer_id
    stealer.auras.add(token)
    return True


# ---------------------------------------------------------------------------
# Token creation
# ---------------------------------------------------------------------------

AURA_TOKENS = frozenset({
    "runechant", "seismic_surge", "quicken", "spectral_shield",
    "frostbite", "bloodrot_pox", "soul_shackle", "ponder",
    "embodiment_of_earth", "embodiment_of_lightning", "inertia",
    "frailty", "courage", "might", "vigor", "agility",
    "eloquence", "confidence", "toughness", "fealty",
    "zen_state", "spellbane_aegis", "bait",
})

# Keywords carried by specific tokens — set before zone entry so prevention
# effects are registered with the correct keyword list (CR 8.5.2b).
TOKEN_KEYWORDS: dict[str, list[str]] = {
    "spectral_shield": ["Ward 1"],          # CR 8.6.8
    "spellbane_aegis": ["Spellvoid 1"],     # CR 8.6.18
    "aether_ashwing": ["Arcane Barrier 1"], # CR 8.6.15
}

ITEM_TOKENS = frozenset({
    "gold", "silver", "copper", "hyper_driver", "golden_cog", "goldkiss_rum",
})


def _create_token(state: GameState, player: Player, token_slug: str,
                  count: int = 1) -> list:
    """Create token(s) in player's aura/item/token zone.
    Tokens are created directly via Zone.add() — no remove needed since
    the token doesn't exist in any zone before creation.

    Keywords and prevention effects are registered BEFORE Zone.add() so that
    any arena-entry trigger that immediately deals damage finds the token's
    prevention effects already active (CR 8.5.2b).
    """
    from engine.card import Card as CardClass
    effect_mngr = getattr(state, 'effect_manager', None)
    tokens = []
    for _ in range(count):
        token = CardClass(slug=token_slug,
                          name=token_slug.replace("_", " ").title())
        token.owner = player.player_id
        token.controller = player.player_id
        token.is_public = True
        token.types = ["Token"]

        # Set token-specific keywords before zone entry
        if token_slug in TOKEN_KEYWORDS:
            token.keywords = list(TOKEN_KEYWORDS[token_slug])

        # Register keyword-based prevention effects before zone entry (5-A, 5-B fix)
        if effect_mngr is not None:
            effect_mngr.register_prevention_effects(token, state)
            # Zen State: text-based "prevent 1 damage" — not a keyword, handled specially
            if token_slug == "zen_state":
                from engine.effects import ReplacementEffect, ReplacementType
                def _zen_condition(event, _state, _card=token):
                    return (event.get("type") == "damage"
                            and event.get("amount", 0) > 0
                            and event.get("target_player_id") == _card.controller
                            and _card.zone in (
                                "auras", "items", "tokens", "allies",
                                "head", "chest", "arms", "legs", "weapon", "hero"))
                def _zen_replace(event, _state):
                    event["amount"] = max(0, event.get("amount", 0) - 1)
                    return event
                effect_mngr.add_replacement(ReplacementEffect(
                    source_card=token,
                    replacement_type=ReplacementType.PREVENTION,
                    condition_fn=_zen_condition,
                    replace_fn=_zen_replace,
                    owner_id=player.player_id,
                    prevention_amount=1,
                    is_shielding=True,  # persists until token is destroyed
                ))

        if token_slug in AURA_TOKENS:
            token.types.append("Aura")
        elif token_slug in ITEM_TOKENS:
            token.types.append("Item")
        player.permanents.add(token)

        tokens.append(token)
    return tokens


def create_token(state: GameState, player_id: int, token_slug: str,
                 count: int = 1) -> list:
    """Public interface for token creation."""
    # Ripple Away: reduce token creation by 1 when opponent activated it this turn
    opp_id = 3 - player_id
    opp = state.players.get(opp_id)
    if opp and "ripple_away_reduce_tokens" in opp.current_turn_effects:
        count = max(0, count - 1)
        if count == 0:
            return []
    tokens = _create_token(state, state.players[player_id], token_slug, count)
    # Prevention effects are registered inside _create_token (before Zone.add)
    # Emit gold_created event so Gold-Baited Hook can track any gold creation
    if token_slug == "gold" and tokens:
        from engine.state import Event
        state.event_manager.emit(
            Event(type='gold_created', data={'player_id': player_id, 'count': len(tokens)}),
            state)
    return tokens
