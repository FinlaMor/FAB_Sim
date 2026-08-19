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

Effect Keywords available from engine.effect_keywords:
- banish: banish a card
- create_token: creates a token object and places in the arena
- deal_damage: deals damage to a living object of type generic, physical, or arcane.
- destroy: destroys a target object
- discard: discards a card from hand
- draw: places the top card of the deck into the players hand
- gain: gains an asset (AssetType: LIFE, RESOURCES, ACTION_POINTS, CHI)
- gets: modifies a numerical property of a card. continuous effect.
- gets_property: target card gains a non-numerical property (keyword/type/subtype)
- intimidate: banishes a card from hand face_down. returned at start of end phase before arsenal choice
- lose: lose asset (AssetType: LIFE, RESOURCES, ACTION_POINTS, CHI)
- look: specified players look at a private card. (card does NOT become public)
- put_counter: put one or more counters on an object
- remove_counter: opposite of put_counter
- reveal: a card is made public and either stays that way or is flipped back down.
- put_object: move an object to a specified zone
- roll: rolls one or more dice
- search: search for a card in a set of zones
- shuffle: shuffles cards in a specified zone
- name: stores a named card
- opt: look at top N cards, choose any number to put on top or bottom.
- reload: option to move a card from hand to arsenal face-down. all arsenal zones must be empty.
- turn: flip a card up (become public) or down (become private)
- negate: remove a layer from the stack
- repeat: execute a callable repeatly
- reroll: reroll a die. returns potentially new results
- charge: move a card from hand to soul 
  
  """

from __future__ import annotations
from typing import TYPE_CHECKING

from engine.card import Card, CardEffect
from engine.effect_keywords import (
    destroy as _ek_destroy,
    banish as _ek_banish,
    draw as _ek_draw,
    discard as _ek_discard,
    deal_damage as _ek_deal_damage,
    gain as _ek_gain,
    lose as _ek_lose,
    opt as _ek_opt,
    intimidate as _ek_intimidate,
    put_counter as _ek_put_counter,
    remove_counter as _ek_remove_counter,
    amp as _ek_amp,
    charge as _ek_charge,
    mark as _ek_mark,
    reload as _ek_reload,
    DamageType as _DamageType,
    AssetType as _AssetType,
)

if TYPE_CHECKING:
    from engine.state import GameState, Event, Player, Zone
    from engine.card import CardDB

# Per rules 3.0.5 — zones that comprise the arena.
ARENA_ZONE_NAMES = frozenset({
    "head", "chest", "arms", "legs", "weapon",
    "hero", "permanents", "allies",
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


def _is_attack_action_card(card: Card) -> bool:
    t = [x.lower() for x in (card.types or [])]
    s = [x.lower() for x in (card.subtypes or [])]
    return "action" in t and "attack" in s


def controlled_attack_action_cards(state: GameState, controller_id: int) -> list:
    """CR: "attack action card you control" during combat. This is the active
    attack if you control it, PLUS any card you control that is defending on the
    chain with type Action + subtype Attack (defending with an attack action
    card still counts as controlling that attack action card)."""
    combat = getattr(state, "combat", None)
    if not combat:
        return []
    out, seen = [], set()
    ac = getattr(combat, "attack_card", None)
    if (ac is not None and getattr(ac, "controller", None) == controller_id
            and _is_attack_action_card(ac)):
        out.append(ac)
        seen.add(id(ac))
    for d in (getattr(combat, "defending_cards", None) or []):
        if id(d) in seen:
            continue
        if getattr(d, "controller", None) == controller_id and _is_attack_action_card(d):
            out.append(d)
    return out


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


# --- Canonical decision vocabulary -------------------------------------------
# One set of sentinel tokens for player decisions so agents, tests, and
# decision records never have to know per-effect strings. Real options always
# come BEFORE a sentinel, because default agents take the first option — so the
# default is to act, not to opt out.
YES, NO = "yes", "no"          # binary "you may" decisions
DECLINE = "decline"            # opt out of an optional card choice
FAIL_TO_FIND = "fail_to_find"  # CR 8.5.19 — declining to find on a search is a
                               # distinct named game action, kept as its own
                               # label so decision records stay rules-accurate
STOP = "done"                  # stop after taking 1+ in a bounded multi-select


def ask_yes_no(state: GameState, player_id: int, context: str = "") -> bool:
    """A binary 'you may' decision. Returns True to act. `yes` is offered first
    so a default agent acts."""
    return str(_ask_player(state, player_id, [YES, NO], context=context)) == YES


def ask_optional(state: GameState, player_id: int, options, context: str = "",
                 sentinel: str = DECLINE):
    """Choose one of *options* or opt out. Returns the chosen option, or None if
    the player took the sentinel. Pass sentinel=FAIL_TO_FIND for searches."""
    choice = _ask_player(state, player_id, list(options) + [sentinel], context=context)
    return None if choice == sentinel else choice


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




def _apply_defense_counter(card: Card, state: GameState, count: int = 1) -> None:
    """Apply -1{d} counters to a card. Manages the effect list cleanly."""
    controller = _get_controller(state, card)
    key = (card.slug, card.zone, "minus_defense")
    controller.counters[key] = controller.counters.get(key, 0) + count
    # Remove stale counter effect, add fresh one (card.effects holds CardEffect objects)
    card.effects = [e for e in card.effects
                    if not (getattr(e, 'prop', None) == "defense"
                            and getattr(getattr(e, 'fn', None), '_counter_key', None) == key)]
    def _apply(base, k=key, p=controller):
        return base - p.counters.get(k, 0)
    _apply._counter_key = key
    card.effects.append(CardEffect(prop="defense", stage=7, substage=5, fn=_apply))
    # Also update card.defense immediately so keyword tests and out-of-engine
    # callers see the correct value without waiting for the engine recalc pass.
    if card.base_defense is not None:
        card.defense = _apply(card.base_defense)


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
    _ek_destroy(state, card, None)


def temper(card: Card, event: Event, state: GameState) -> None:
    """8.3.10: When combat chain closes, if this defended, put a -1{d} counter on it,
    then destroy it if it has zero {d}."""
    _apply_defense_counter(card, state, 1)
    if card.defense is not None and max(card.defense, 0) == 0:
        _ek_destroy(state, card, None)


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
    return sum(1 for c in state.combat.defending_cards if "Action" in c.types or "action" in c.types) >= 1


def go_again(card: Card, state: GameState) -> None:
    """8.3.5: Gain 1 action point on resolution (turn player only, 8.5.7b)."""
    cid = _controller_id(card)
    if cid == state.active_player:
        state.players[cid].action_points += 1


def piercing(card: Card, amount: int, state: GameState) -> None:
    """CR 8.3.23: Piercing — now a static ability evaluated in _recalculate_attack_power.
    This triggered path is intentionally a noop to avoid double-counting."""
    pass


# ---------------------------------------------------------------------------
# 8.3 Ability Keywords — Triggered static abilities
# ---------------------------------------------------------------------------

def phantasm_check(card: Card, event: Event, state: GameState) -> bool:
    """8.3.13: Check if a non-Illusionist attack action card with 6+ power is defending."""
    if not state.combat:
        return False
    for d in state.combat.defending_cards:
        if (d.is_attack and d.is_action and
            "Illusionist" not in [c for c in d.classes or []] and
            d.power is not None and d.power >= 6):
            return True
    return False


def phantasm_destroy(card: Card, event: Event, state: GameState) -> None:
    """8.3.13: Destroy the phantasm attack (state-trigger re-checked on resolve)."""
    if phantasm_check(card, event, state):
        _ek_destroy(state, card, None)
        from engine.engine import _close_step
        _close_step(state)
        


def spectra_destroy(card: Card, event: Event, state: GameState) -> None:
    """8.3.14: When this becomes target of an attack, destroy it. Combat chain immediately closes."""
    _ek_destroy(state, card, None)
    from engine.engine import _close_step
    _close_step(state)


def blood_debt(card: Card, event: Event, state: GameState) -> None:
    """8.3.11: While in banished zone (public), at beginning of end phase, lose 1 life."""
    if card.zone == "banished" and card.is_public:
        controller = _get_controller(state, card)
        controller.life -= 1


def suspense_remove_counter(card: Card, event: Event, state: GameState) -> None:
    """CR 8.3.42: At start of turn, remove a suspense counter.
    When the counter reaches 0, push a triggered-layer onto the stack with
    destruction as its resolution effect so both players receive priority
    before the aura is destroyed (CR 6.6.6 / CR 5.3)."""
    from engine.state import StackEntry, Event as _Event
    controller = _get_controller(state, card)
    key = (card.slug, card.zone, "suspense")
    current = controller.counters.get(key, 0)
    if current > 0:
        controller.counters[key] = current - 1
    if controller.counters.get(key, 0) <= 0:
        # Capture card reference for the closure
        _card = card
        def _destroy_suspense_aura(c, gs):
            _ek_destroy(gs, _card, None)
        entry = StackEntry(
            player_id=controller.player_id,
            card=card,
            layer_type='triggered',
            layer_position=len(state.stack_entries) + 1,
            is_triggered=True,
            trigger_event='suspense_expired',
            effect_fn=_destroy_suspense_aura,
        )
        state.stack_entries.append(entry)


def suspense_enter(card: Card, state: GameState) -> None:
    """8.3.42: Enters arena with 2 suspense counters."""
    controller = _get_controller(state, card)
    key = (card.slug, card.zone, "suspense")
    controller.counters[key] = 2


def watery_grave(card: Card, event: Event, state: GameState) -> None:
    """8.3.41: When put into graveyard from the arena, turn face-down.
    Arena includes combat chain, allies zone, permanents per rules 3.0.5 / 7.0.3f."""
    if card.zone == "graveyard" and _was_in_arena(card):
        card.face_down = True
        card.is_public = False


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
        _ek_banish(state, top, controller.player_id, None)
        # Track each boost in current_turn_effects.
        # "boosted_this_turn" is appended once per boost so:
        #   - boolean check: "boosted_this_turn" in player.current_turn_effects
        #   - count check:   sum(1 for e in current_turn_effects if e == "boosted_this_turn")
        # Also set class_counters flag for legacy checks (Maxx hero condition etc.)
        controller.current_turn_effects.append("boosted_this_turn")
        controller.class_counters["boosted_this_turn"] = True
        # ... and a CHAIN-scoped tally. "this combat chain" is narrower than
        # "this turn": a second attack in the same turn must not inherit the
        # first attack's boosts. Cleared at chain close (engine._close_step).
        controller.boosts_this_chain = getattr(controller, "boosts_this_chain", 0) + 1
        # Emit event so items/abilities can react to each boost (e.g. Absorbtion Zone)
        from engine.state import Event
        state.event_manager.emit(
            Event(type='boosted', data={'player_id': cid, 'banished_card': top}),
            state)
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
    create_token(state, cid, "seismic_surge", amount)
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
    state.players[cid].current_turn_effects.append("cranked_this_turn")
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
    # Record that this card was fused this turn, so a "if <card> was fused"
    # ability can gate on it (generic marker: any DSL ability may test
    # FLAG_SET "fused_<slug>"). Cleared with current_turn_effects at end of turn.
    marker = f"fused_{card.slug}"
    if marker not in controller.current_turn_effects:
        controller.current_turn_effects.append(marker)
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
    _ek_destroy(state, card, None)
    return amount


def ward(card: Card, amount: int, state: GameState) -> int:
    """8.3.20: Destroy this to prevent N damage. NOT optional per rules —
    activates automatically when damage would be dealt. Returns amount prevented."""
    _ek_destroy(state, card, None)
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
    _ek_destroy(state, card, None)
    return amount


# ---------------------------------------------------------------------------
# 8.4 Label Keywords — Conditional triggers
# ---------------------------------------------------------------------------

def crush_check(event: Event, state: GameState) -> bool:
    """8.4.2: Check if attack dealt 4+ damage."""
    data = event.data if isinstance(event.data, dict) else {}
    return data.get("damage", 0) >= 4


def reprise_check(state: GameState) -> bool:
    """8.4.3: Defending hero defended with a card from hand this chain link."""
    if not state.combat:
        return False
    return state.combat.defender_used_hand_card


def combo_check(state: GameState, combo_names: list) -> bool:
    """8.4.1: One of the named cards was the last attack this combat chain.

    Accepts either full slugs (``surging_strike_red``) or base slugs
    (``surging_strike``) in *combo_names* — both match correctly.
    """
    if not state.chain_links:
        return False
    import re
    last_slug = state.chain_links[-1].attack_slug
    last_base = re.sub(r'_(red|yellow|blue)$', '', last_slug)
    return last_slug in combo_names or last_base in combo_names


def surge_check(event: Event, amount: int) -> bool:
    """8.4.8: Check if this dealt N+ damage."""
    data = event.data if isinstance(event.data, dict) else {}
    return data.get("damage", 0) >= amount


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
    _ek_destroy(state, card, None)


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
        _ek_destroy(state, item, None)
        return True
    return False


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


def create_token_card(token_slug: str, owner_id: int, **kwargs) -> Card:
    """Create a Card instance from a token definition.

    Looks up WEAPON_TOKENS first for detailed definitions, then falls back
    to the slug_index CardDB, and finally creates a minimal token from the
    slug name alone.
    """
    defn = WEAPON_TOKENS.get(token_slug)
    if defn is not None:
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
    else:
        # Fall back to slug_index via CardDB
        from engine.card import CardDB
        from config import SLUG_INDEX_PATH
        db = CardDB(str(SLUG_INDEX_PATH))
        card = db.get(token_slug)
        if card is None:
            # Last resort: create a minimal token from the slug
            card = Card(
                slug=token_slug,
                name=token_slug.replace("_", " ").title(),
                types=["Token"],
            )

    card.owner = kwargs.get("controller", owner_id)
    card.controller = kwargs.get("controller", owner_id)
    card.is_public = True
    return card


def effect_crowd_boos(state: GameState, player_id: int) -> None:
    """The crowd boos you — tracks that this player has been booed this turn.

    Also routes through the CR 8.5.57 keyword (effect_keywords.boo), which
    emits a BooEvent that replacement effects can intercept and sets
    class_counters['booed_this_turn']. Without that call the CR-level function
    was dead code and no replacement could ever see a boo.
    """
    from engine.state import Event
    from engine.effect_keywords import boo as _cr_boo
    player = state.players[player_id]
    player.current_turn_effects.append("crowd_booed")
    _cr_boo(state, player_id)
    state.event_manager.emit(
        Event(type='crowd_boos', data={'player_id': player_id}),
        state
    )


def effect_crowd_cheers(state: GameState, player_id: int) -> None:
    """The crowd cheers you — the counterpart of effect_crowd_boos (CR 8.5.57).

    Cheer previously had no working path at all: effect_keywords.cheer() was
    called by nothing, the "the crowd cheers" keyword handler appended a flag
    nothing read, and cards hand-rolled a private SET_FLAG. This is the single
    entry point for all three.
    """
    from engine.state import Event
    from engine.effect_keywords import cheer as _cr_cheer
    player = state.players[player_id]
    player.current_turn_effects.append("crowd_cheered")
    _cr_cheer(state, player_id)
    state.event_manager.emit(
        Event(type='crowd_cheers', data={'player_id': player_id}),
        state
    )


def has_been_booed(state: GameState, player_id: int) -> bool:
    """Check if player has been booed this turn."""
    return "crowd_booed" in state.players[player_id].current_turn_effects


# Spellings that have all meant "was cheered this turn" at some point: the
# canonical flag, the one the keyword-text handler writes, and the private flag
# hand-rolled by cards before CROWD_CHEER existed. Accepting all three keeps a
# cheer from one path visible to a card written against another.
_CHEERED_FLAGS = ("crowd_cheered", "crowd_cheers", "CROWD_CHEERS")


def has_been_cheered(state: GameState, player_id: int) -> bool:
    """Check if player has been cheered this turn."""
    player = state.players[player_id]
    if player.class_counters.get("cheered_this_turn"):
        return True
    return any(f in player.current_turn_effects for f in _CHEERED_FLAGS)


def roll_die(state: GameState, player_id: int, faces: int = 6) -> int:
    """Roll a single die and return the integer result (CR 8.5.18)."""
    from engine.effect_keywords import roll
    event = roll(state, num_dice=1, faces=faces, source_player_id=player_id)
    return event.total


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
    # "if you haven't created or stolen a Gold this turn" (Loan Shark). Creating
    # is already recorded inside the create-token keyword; stealing is the other
    # half of that sentence and had no record at all, so the check could only
    # ever see half the game.
    from engine.effect_keywords import _record_turn_event
    _record_turn_event(state, stealer_id, "steal",
                       getattr(token, "slug", None),
                       getattr(token, "name", None),
                       getattr(token, "subtypes", None) or [])
    return True


def effect_reveal_top(state: GameState, player_id: int, count: int = 1) -> list:
    """Reveal the top N cards of a player's deck. Returns list of revealed cards."""
    player = state.players[player_id]
    revealed = []
    for i in range(min(count, len(player.deck.cards))):
        card = player.deck.cards[i]
        card.is_public = True
        revealed.append(card)
    return revealed


def effect_look_top(state: GameState, player_id: int, count: int = 1) -> list:
    """Look at the top N cards of a player's deck. Returns list of cards (not public)."""
    player = state.players[player_id]
    return player.deck.cards[:min(count, len(player.deck.cards))]


def effect_put_top_deck(state: GameState, card: Card, player_id: int) -> None:
    """Put a card on top of a player's deck."""
    _remove_from_current_zone(card, state)
    player = state.players[player_id]
    player.deck.cards.insert(0, card)
    card.zone = "deck"
    card.is_public = False


def effect_put_bottom_deck(state: GameState, card: Card, player_id: int) -> None:
    """Put a card on the bottom of a player's deck."""
    _remove_from_current_zone(card, state)
    player = state.players[player_id]
    player.deck.cards.append(card)
    card.zone = "deck"
    card.is_public = False


def effect_return_to_hand(state: GameState, card: Card, player_id: int) -> None:
    """Return a card to a player's hand."""
    _remove_from_current_zone(card, state)
    player = state.players[player_id]
    player.hand.add(card)


def effect_put_arsenal(state: GameState, card: Card, player_id: int,
                       face_up: bool = False) -> None:
    """Put a card into a player's arsenal."""
    _remove_from_current_zone(card, state)
    player = state.players[player_id]
    player.arsenal.add(card)
    card.face_down = not face_up
    card.is_public = face_up


def create_token(state: GameState, player_id: int, token_slug: str,
                 count: int = 1) -> list:
    """Thin wrapper — delegates to effect_keywords.create_token (canonical path).

    Signature kept identical so all existing registry.py / engine.py callers
    continue to work without changes during the DSL migration.
    Returns [] for backward compat; the canonical function returns CreateTokenEvent.
    """
    from engine.effect_keywords import create_token as _ek_create_token
    _ek_create_token(state, player_id, token_slug, count)
    return []


# ---------------------------------------------------------------------------
# FIX 7: Missing keyword implementations
# ---------------------------------------------------------------------------

def resolve_wager(state: GameState, attacker_id: int, source: Card = None) -> int:
    """CR 8.5.46: Wager — continuous effect on an attack resolved at chain link resolution.
    If the attack hit, the attack's controller (attacker_id) wins the wager.
    If it didn't hit, the other player wins.
    Returns the winner's player_id.
    The prize effect is card-specific; this function only determines who won."""
    if not state.combat:
        return attacker_id  # default to attacker if no combat state
    # The hit flag is set on the chain link after damage calculation
    # Look at the most recently closed chain link
    if state.chain_links:
        last_link = state.chain_links[-1]
        winner_id = attacker_id if last_link.hit else (3 - attacker_id)
    else:
        # Fallback: check combat state directly
        winner_id = attacker_id
    state.event_manager.emit(
        type('Event', (), {'type': 'wager_resolved',
                           'data': {'winner': winner_id, 'source': source}})(),
        state)
    return winner_id


def effect_wager(state: GameState, player_id: int, source: Card = None) -> bool:
    """CR 8.5.46: Wager wrapper — resolves wager and returns True if player_id won.
    Called at chain_link_resolve event. Prize effect is card-specific."""
    winner = resolve_wager(state, player_id, source)
    return winner == player_id


def add_wager(state: GameState, controller_id: int, prize_slug: str | None = None,
              source: Card | None = None) -> None:
    """Add a wager to the current combat chain link.

    The wager resolves automatically at chain link resolution via
    ``_resolve_wagers`` in engine.py: if the attack hits, the controller
    wins and creates the prize token; otherwise the opponent wins it.

    `source` is the card that created the wager. A token prize was the only
    outcome the wager could have, so a card whose payoff is anything else
    ("the winner loses 1{h}") had no way to express it; recording the source
    lets _resolve_wagers dispatch ON_WAGER_RESOLVED back to that card.
    """
    if state.combat is not None:
        state.combat.wagers.append((controller_id, prize_slug, source))
        state.event_manager.emit(
            type('Event', (), {'type': 'wagered',
                               'data': {'controller': controller_id, 'prize': prize_slug}})(),
            state)


def check_decompose(state: GameState, player_id: int) -> bool:
    """CR 8.4.14: Decompose — check if the player can pay the cost.
    Cost: banish 2 Earth cards and an action card from graveyard.
    Returns True if the player has 2+ Earth cards and 1+ action card in graveyard."""
    player = state.players[player_id]
    earth_count = sum(1 for c in player.graveyard.cards if "Earth" in (c.types or []))
    action_count = sum(1 for c in player.graveyard.cards
                       if "Action" in (c.types or []) and "Earth" not in (c.types or []))
    # Need at least 2 Earth + 1 non-Earth Action (to avoid double-counting)
    # More lenient: 2+ Earth cards and at least 1 action card total
    action_any = sum(1 for c in player.graveyard.cards if "Action" in (c.types or []))
    return earth_count >= 2 and action_any >= 1


def effect_decompose(state: GameState, card: Card, player_id: int) -> bool:
    """CR 8.4.14: Decompose — optional cost/condition.
    You may banish 2 Earth cards and an action card from your graveyard.
    If you do, the card-specific effect fires (returns True).
    Returns True if cost was paid."""
    if not check_decompose(state, player_id):
        return False
    player = state.players[player_id]
    choice = _ask_player(state, player_id, [True, False],
                         context="Decompose: Banish 2 Earth cards and an action card from graveyard?")
    if not choice:
        return False
    # Banish 2 Earth cards from graveyard
    earth_cards = [c for c in player.graveyard.cards if "Earth" in (c.types or [])]
    for i in range(min(2, len(earth_cards))):
        if len(earth_cards) > i:
            c = earth_cards[i]
            player.graveyard.remove(c)
            _ek_banish(state, c, player.player_id, None)
    # Banish 1 action card from graveyard
    action_cards = [c for c in player.graveyard.cards if "Action" in (c.types or [])]
    if action_cards:
        c = action_cards[0]
        player.graveyard.remove(c)
        _ek_banish(state, c, player.player_id, None)
    return True


def effect_transcend(state: GameState, player_id: int, source: Card = None) -> bool:
    """CR 8.5.48: Transcend — delegates to the canonical effect_keywords.transcend.

    This used to be a second, divergent implementation: it moved the card by hand,
    set a bespoke `source.transcended` attribute, did NOT activate the back face
    the way the canonical function does, did NOT emit the transcend event (so no
    "whenever you transcend" trigger could fire), and did NOT record the turn
    event. Neither version had any caller, so the split was invisible — but the
    first caller to pick this one would have got silently different behaviour.
    Returns True if transcend occurred.
    """
    if source is None:
        return False
    from engine.effect_keywords import transcend as _transcend
    event = _transcend(state, source, player_id)
    return not getattr(event, "canceled", False)


def effect_steal(state: GameState, stealer_id: int, victim_id: int,
                 steal_from: str = "hand") -> Card:
    """Steal: Take a card from opponent's hand or field and put it in stealer's hand/field.
    steal_from: 'hand' or 'field' (items/auras zone)."""
    stealer = state.players[stealer_id]
    victim = state.players[victim_id]

    if steal_from == "hand":
        if not victim.hand.cards:
            return None
        # Random steal from hand (face-down, so random)
        import random as rng
        card = rng.choice(victim.hand.cards)
        victim.hand.remove(card)
        card.controller = stealer_id
        stealer.hand.add(card)
        return card
    elif steal_from == "field":
        stealable = list(victim.items.cards) + list(victim.auras.cards)
        if not stealable:
            return None
        options = [c.slug for c in stealable]
        pick = _ask_player(state, stealer_id, options,
                           context="Steal: choose a card from opponent's field to take")
        card = next((c for c in stealable if c.slug == pick), stealable[0])
        _remove_from_current_zone(card, state)
        card.controller = stealer_id
        stealer.hand.add(card)
        return card
    return None


def check_high_tide(state: GameState, player_id: int) -> bool:
    """CR 8.4.18: High Tide — True if there are 2 or more blue (pitch value 3) cards
    in the player's pitch zone this turn."""
    player = state.players[player_id]
    blue_count = sum(1 for c in player.pitch.cards if (c.base_pitch or 0) == 3)
    return blue_count >= 2


def check_mirage(card: Card, event, state: GameState) -> bool:
    """CR 8.3.25: Mirage — check condition for triggering destruction.
    Condition: this card is defending a non-Illusionist attack with 6 or more power.
    Returns True if the Mirage card should be destroyed."""
    if not state.combat:
        return False
    # This card must be in the defending cards
    if card not in state.combat.defending_cards:
        return False
    # The attacking card must be non-Illusionist
    attack = state.combat.attack_card
    if attack is None:
        return False
    if "Illusionist" in (attack.types or []):
        return False
    # Attack power must be 6 or more
    return (state.combat.attack_power or 0) >= 6


def effect_mirage_destroy(card: Card, event, state: GameState) -> None:
    """CR 8.3.25: Mirage — destroy this defending card."""
    _ek_destroy(state, card, None)


def effect_mirage(state: GameState, player_id: int, source: Card) -> Card:
    """Mirage (CR 8.3.25): When this attacks, create an illusion token copy
    that is destroyed at end of turn.
    NOTE: This function is for the offensive illusion-copy flavor only.
    The actual Mirage keyword (defensive triggered ability) is handled by
    check_mirage() and effect_mirage_destroy()."""
    from engine.card import Card as CardClass
    player = state.players[player_id]
    # Create a token copy of the source card
    illusion = CardClass(
        slug=f"{source.slug}_illusion",
        name=f"{source.name} (Illusion)",
        types=list(source.types or []) + ["Token", "Illusion"],
        keywords=list(source.keywords or []) + ["Phantasm"],
        base_power=source.base_power,
        base_defense=source.base_defense,
        base_cost=source.base_cost,
        base_pitch=source.base_pitch,
    )
    illusion.owner = player_id
    illusion.controller = player_id
    illusion.is_public = True
    player.tokens.add(illusion)

    # Register end-of-turn destruction for the token
    def _destroy_illusion(event, game_state):
        listeners = game_state.event_manager.listeners.get('end_of_turn', [])
        if _destroy_illusion in listeners:
            listeners.remove(_destroy_illusion)
        if illusion in player.tokens.cards:
            player.tokens.remove(illusion)
            player.graveyard.add(illusion)

    state.event_manager.register('end_of_turn', _destroy_illusion)
    return illusion


def check_unity(state: GameState, card: Card) -> bool:
    """CR 8.4.10: Unity — True if this card is part of a DEFEND_CARDS action that
    includes at least one other hand card. This card must be in combat.defending_cards
    AND at least one other card from hand is also defending."""
    if not state.combat:
        return False
    defending = state.combat.defending_cards
    if card not in defending:
        return False
    # Count defending cards that came from hand (prev_zone == "hand")
    hand_defenders = [c for c in defending if c.prev_zone == "hand"]
    # This card + at least one other hand card
    return len(hand_defenders) >= 2


def check_material(card: Card, state: GameState) -> bool:
    """CR 8.4.5: Material — static condition: returns True if this card is currently
    'under' a permanent (i.e. some permanent is stacked on top of it).
    Implemented as: the card has a 'under_permanent' attribute set to True,
    or is in a zone where it was placed under another permanent."""
    return bool(getattr(card, 'under_permanent', False))


def effect_material(state: GameState, player_id: int, source: Card = None) -> bool:
    """CR 8.4.5: Material — static condition check (not a cost).
    Returns True if source card is currently under a permanent.
    The actual card effects are card-specific when this condition is True."""
    if source is None:
        return False
    return check_material(source, state)


def check_earth_bond(action, state: GameState) -> bool:
    """CR 8.4.15: Earth Bond — True if at least one card pitched to play this action
    has the 'Earth' supertype or type.
    action: an Action object with a pitch_cards attribute (list of Card)."""
    pitch_cards = getattr(action, 'pitch_cards', []) or []
    for card in pitch_cards:
        if "Earth" in (card.types or []) or "Earth" in (card.supertypes or []):
            return True
    return False


def check_lightning_flow(state: GameState, player_id: int) -> bool:
    """Lightning Flow: True if the player has played a Lightning card this turn."""
    player = state.players[player_id]
    return "played_lightning" in player.current_turn_effects


def check_tower(card: Card, state: GameState) -> bool:
    """CR 8.4.13: Tower — returns True if the card's current attack power is 13 or more.
    This is a condition check only; actual effects are card-specific."""
    # Compute current power: base_power plus any counter modifiers
    controller = _get_controller(state, card)
    base = card.base_power or 0
    # Sum any power-modifying counters
    bonus = 0
    for (slug, zone, ctype), val in controller.counters.items():
        if slug == card.slug and ctype in ("plus_attack", "plus_power"):
            bonus += val
    return (base + bonus) >= 13


def check_solflare(event, state: GameState) -> bool:
    """CR 8.4.9: Solflare — triggered when a card with Solflare is charged to soul.
    Returns True when the event is a card_charged event for this card.
    event: the card_charged event; event.data['card'] should be the charged card."""
    data = event.data if isinstance(event.data, dict) else {}
    charged_card = data.get('card')
    if charged_card is None:
        return False
    return "Solflare" in (charged_card.keywords or [])


def _cannon_activated_this_turn(state: GameState, player_id: int) -> bool:
    """Return True if the player has activated a cannon this turn.
    The engine sets 'activated_cannon' in current_turn_effects when a cannon ability fires.
    """
    player = state.players[player_id]
    return "activated_cannon" in (player.current_turn_effects or [])


def effect_go_fish(event, state: GameState, condition_fn=None) -> Card:
    """CR 8.4.19: Go Fish — on-hit label ability.
    When this hits a hero, the defending hero chooses and reveals a card from their hand.
    If it meets condition_fn, they discard it and the attacker creates a Gold token.

    Cannon upgrade (on all Go Fish cards):
    If the attacker activated a cannon this turn, instead the attacker looks at the
    defender's full hand and CHOOSES which card to reveal (not the defender).

    condition_fn: callable(card) -> bool, card-specific condition. If None, always triggers.
    Returns the revealed card (or None)."""
    if not state.combat:
        return None
    attacker_id = state.combat.attacker_id
    defender_id = 3 - attacker_id
    defender = state.players[defender_id]
    if not defender.hand.cards:
        return None

    if _cannon_activated_this_turn(state, attacker_id):
        # Cannon upgrade: attacker sees all and chooses
        options = [c.slug for c in defender.hand.cards]
        pick = _ask_player(state, attacker_id, options,
                           context="Go Fish (cannon): Look at opponent's hand and choose a card")
    else:
        # Standard: defender chooses which card to reveal
        options = [c.slug for c in defender.hand.cards]
        pick = _ask_player(state, defender_id, options,
                           context="Go Fish: Choose a card from your hand to reveal")

    revealed = defender.hand.find(pick)
    if revealed is None:
        revealed = defender.hand.cards[0]
    revealed.is_public = True

    # If condition met, defender discards and attacker gets Gold
    if condition_fn is None or condition_fn(revealed):
        defender.hand.remove(revealed)
        defender.graveyard.add(revealed)
        create_token(state, attacker_id, "gold", 1)
    return revealed


def check_heavy(state: GameState, player_id: int) -> bool:
    """CR 8.4.17: Heavy — static condition: True if the player has exactly one weapon
    equipped and no other weapons. Used by cards with the Heavy label keyword."""
    player = state.players[player_id]
    weapons = list(player.weapon1.cards) + list(player.weapon2.cards)
    return len(weapons) == 1


def check_essence(state: GameState, player_id: int,
                  essence_type: str = None) -> bool:
    """Essence: True if player controls or has in hand a card with the given Essence.
    essence_type: 'Earth', 'Lightning', or None (any essence)."""
    player = state.players[player_id]
    all_cards = list(player.hand.cards) + player.arena_cards
    for card in all_cards:
        for kw in (card.keywords or []):
            kw_lower = kw.lower()
            if essence_type is None:
                if "essence" in kw_lower:
                    return True
            else:
                if f"essence ({essence_type.lower()})" in kw_lower or f"essence {essence_type.lower()}" in kw_lower:
                    return True
    return False


# ---------------------------------------------------------------------------
# Awaken keyword (CR 8.2.16) — transforms a Figment into its Angel Ally
# ---------------------------------------------------------------------------

# Figment slug -> corresponding Archangel (Angel Ally) slug
FIGMENT_TO_ANGEL = {
    "figment_of_erudition_yellow": "suraya_archangel_of_erudition",
    "figment_of_judgment_yellow": "themis_archangel_of_judgment",
    "figment_of_protection_yellow": "aegis_archangel_of_protection",
    "figment_of_ravages_yellow": "sekem_archangel_of_ravages",
    "figment_of_rebirth_yellow": "avalon_archangel_of_rebirth",
    "figment_of_tenacity_yellow": "metis_archangel_of_tenacity",
    "figment_of_triumph_yellow": "victoria_archangel_of_triumph",
    "figment_of_war_yellow": "bellona_archangel_of_war",
}


def effect_awaken(state: GameState, player_id: int, target_figment: Card) -> bool:
    """Awaken keyword (CR 8.2.16): transform a Figment in the arena into its Angel Ally.
    Removes the Figment from permanents, creates the corresponding Angel Ally card,
    puts it in permanents (allies sub-zone), and emits card_awakened event.
    Returns True if awakening succeeded."""
    if target_figment is None:
        return False
    player = state.players[player_id]
    angel_slug = FIGMENT_TO_ANGEL.get(target_figment.slug)
    if angel_slug is None:
        return False

    # Remove figment from permanents zone
    if not player.permanents.remove(target_figment):
        return False

    # Create the Angel Ally card from CardDB if available, else a minimal stub
    angel_card = None
    card_db = getattr(state, 'card_db', None)
    if card_db is not None:
        try:
            angel_card = card_db.get(angel_slug)
        except Exception:
            angel_card = None

    if angel_card is None:
        # Minimal stub so the engine doesn't crash
        angel_card = Card(slug=angel_slug, name=angel_slug.replace("_", " ").title())
        angel_card.types = ["Angel", "Ally"]

    angel_card.owner = player_id
    angel_card.controller = player_id
    angel_card.is_public = True
    angel_card.permanent_subtype = "Ally"
    player.permanents.add(angel_card)

    # Emit awakening event
    from engine.state import Event
    state.event_manager.emit(
        Event(type='card_awakened',
              data={'figment': target_figment, 'angel': angel_card,
                    'player_id': player_id}),
        state)
    return True


# ---------------------------------------------------------------------------
# Zone interaction helpers — recovered from deleted card_keywords.py
# ---------------------------------------------------------------------------

def effect_banish_from_soul(state, player_id: int,
                            count: int = 1, face_up: bool = True) -> list:
    """Banish card(s) from player's soul zone. Returns list of banished cards."""
    player = state.players[player_id]
    if not hasattr(player, 'soul') or not player.soul.cards:
        return []
    banished = []
    for _ in range(min(count, len(player.soul.cards))):
        if not player.soul.cards:
            break
        if len(player.soul.cards) == 1:
            target = player.soul.cards[0]
        else:
            pick = _ask_player(state, player_id,
                               [c.slug for c in player.soul.cards],
                               context="Choose a card from your soul to banish")
            target = next((c for c in player.soul.cards if c.slug == pick),
                          player.soul.cards[0])
        player.soul.remove(target)
        _ek_banish(state, target, player_id, None)
        banished.append(target)
    return banished


def effect_move_to_soul(state, card, player_id: int) -> None:
    """Move a card into a player's soul zone."""
    _remove_from_current_zone(card, state)
    player = state.players[player_id]
    player.soul.add(card)


def effect_banish_from_hand(state, player_id: int,
                            count: int = 1, face_up: bool = True,
                            banisher_id: int = None) -> list:
    """Banish card(s) from a player's hand. Returns list of banished cards."""
    player = state.players[player_id]
    banished = []
    for _ in range(min(count, len(player.hand.cards))):
        if not player.hand.cards:
            break
        if len(player.hand.cards) == 1:
            target = player.hand.cards[0]
        else:
            pick = _ask_player(state, player_id,
                               [c.slug for c in player.hand.cards],
                               context="Choose a card from your hand to banish")
            target = next((c for c in player.hand.cards if c.slug == pick),
                          player.hand.cards[0])
        player.hand.remove(target)
        _ek_banish(state, target, banisher_id or player_id, None)
        banished.append(target)
    return banished


# ---------------------------------------------------------------------------
# effect_* wrappers — thin delegates to effect_keywords, kept here so legacy
# files (db/loader.py, triggers/) can import from a single location.
# These will be removed when those callers are migrated to the DSL.
# ---------------------------------------------------------------------------

def effect_draw(state, player_id: int, n: int = 1):
    _ek_draw(state, player_id, number=n)


def _fire_on_discard(state, player_id: int, discarded_card=None) -> None:
    """Dispatch ON_DISCARD DSL event to all persistent cards controlled by player_id.

    discarded_card is passed as the event parameter so DISCARDED_CARD_POWER_GTE
    conditions can inspect it.
    """
    from engine.card_effects.dsl.loader import get_card as _get_dsl_card
    from engine.card_effects.dsl.interpreter import dispatch_event as _dispatch
    player = state.players[player_id]
    pairs = []
    for w_attr in ('weapon1', 'weapon2'):
        wz = getattr(player, w_attr, None)  # weapon ZONE — iterate its cards
        for w in list(getattr(wz, 'cards', None) or []):
            cd = _get_dsl_card(w.slug)
            if cd:
                pairs.append((cd, w))
    for zone_name in ('items', 'auras', 'allies', 'permanents'):
        zone = getattr(player, zone_name, None)
        if zone and hasattr(zone, 'cards'):
            for c in list(zone.cards):
                cd = _get_dsl_card(c.slug)
                if cd:
                    pairs.append((cd, c))
    hero = getattr(player, 'hero', None)
    if hero:
        cd = _get_dsl_card(hero.slug)
        if cd:
            pairs.append((cd, hero))
    for card_def, card_obj in pairs:
        try:
            _dispatch(card_def, "ON_DISCARD", card_obj, discarded_card, state)
        except Exception:
            pass


def effect_discard(state, player_id: int, count: int = 1, random_discard: bool = False) -> list:
    import random as _random
    discarded = []
    player = state.players[player_id]
    for _ in range(count):
        if not player.hand.cards:
            break
        card = _random.choice(player.hand.cards) if random_discard else player.hand.cards[0]
        _ek_discard(state, card, None, origin='hand')
        _fire_on_discard(state, player_id, card)
        discarded.append(card)
    return discarded


def effect_banish(state, arg2, arg3=None, face_up: bool = True):
    """Supports two call patterns:
    - effect_banish(state, player_id, card)
    - effect_banish(state, card)
    """
    if isinstance(arg2, int):
        pid, card = arg2, arg3
    else:
        card = arg2
        pid = _controller_id(card)
    origin = getattr(card, 'zone', None)
    _ek_banish(state, card, pid, origin)


def effect_banish_top_deck(state, player_id: int, count: int = 1, face_up: bool = True) -> list:
    banished = []
    player = state.players[player_id]
    for _ in range(count):
        top = player.deck.pop_top()
        if top is None:
            break
        if not top.owner:
            top.owner = player_id
        if not top.controller:
            top.controller = player_id
        _ek_banish(state, top, player_id, None)  # already removed from deck
        banished.append(top)
    return banished


def effect_deal_damage(state, player_id: int, amount: int, source=None, damage_type: str = "generic") -> int:
    player = state.players[player_id]
    target_card = player.hero
    if target_card is None:
        return 0
    dtype = {
        "generic": _DamageType.GENERIC,
        "physical": _DamageType.PHYSICAL,
        "arcane": _DamageType.ARCANE,
    }.get(damage_type, _DamageType.GENERIC)
    evt = _ek_deal_damage(state, amount, dtype, 3 - player_id,
                          target_card, 'effect', damage_source_card=source)
    return 0 if evt.canceled else amount


def effect_deal_arcane(state, player_id: int, amount: int, source=None) -> int:
    player = state.players[player_id]
    target_card = player.hero
    if target_card is None:
        return 0
    evt = _ek_deal_damage(state, amount, _DamageType.ARCANE, 3 - player_id,
                          target_card, 'effect', damage_source_card=source)
    return 0 if evt.canceled else amount


def effect_gain_life(state, player_id: int, n: int):
    _ek_gain(state, _AssetType.LIFE, n, player_id, target_player_id=player_id)


def effect_lose_life(state, player_id: int, n: int):
    _ek_lose(state, _AssetType.LIFE, n, target_player_id=player_id)


def effect_gain_resources(state, player_id: int, n: int):
    _ek_gain(state, _AssetType.RESOURCES, n, player_id, target_player_id=player_id)


def effect_opt(state, player_id: int, n: int):
    def _selector(cards):
        return (list(cards), [])  # default: put all on top in original order
    _ek_opt(state, n, player_id, _selector)


def effect_intimidate(state, target_player_id: int):
    _ek_intimidate(state, 3 - target_player_id, target_player_id)


def effect_put_counter(state, card, counter_type: str, amount: int = 1):
    # Update player-level counter (keyed by slug/zone/type) for legacy compatibility
    cid = _controller_id(card)
    if cid is not None:
        key = (card.slug, card.zone, counter_type)
        state.players[cid].counters[key] = state.players[cid].counters.get(key, 0) + amount
    # Also update card-level counter for new DSL
    card.counters[counter_type] = card.counters.get(counter_type, 0) + amount


def effect_remove_counter(state, card, counter_type: str, amount: int = 1):
    cid = _controller_id(card)
    if cid is not None:
        key = (card.slug, card.zone, counter_type)
        current = state.players[cid].counters.get(key, 0)
        state.players[cid].counters[key] = max(0, current - amount)
    current_card = card.counters.get(counter_type, 0)
    card.counters[counter_type] = max(0, current_card - amount)


def effect_amp(state, player_id: int, n: int):
    _ek_amp(state, n, player_id)


def effect_charge(state, player_id: int, card):
    _ek_charge(state, card, player_id)


def effect_mark(state, target_player_id: int):
    _ek_mark(state, target_player_id)


# ── Arakni, Marionette — Agent of Chaos transform ────────────────────────────
# The Marionette hero transforms into a random Agent of Chaos demi-hero at the
# end of a turn in which an opponent is marked, and the demi-hero "returns to the
# brood" (reverts) at the beginning of a later end phase.
AGENT_OF_CHAOS_SLUGS = [
    "arakni_black_widow", "arakni_funnel_web", "arakni_orb_weaver",
    "arakni_redback", "arakni_tarantula", "arakni_trap_door",
]


def become_agent_of_chaos(state, player_id: int, choose: bool = False):
    """Transform the player's hero into a random (or chosen) Agent of Chaos.

    Keeps the hero's identity (life, zone) but swaps slug/name/types so the
    demi-hero's DSL abilities apply. No-op if the hero is already a demi-hero.
    """
    import random as _rng
    player = state.players[player_id]
    hero = player.hero
    if hero is None or hero.slug in AGENT_OF_CHAOS_SLUGS:
        return
    if choose:
        pick = _ask_player(state, player_id, AGENT_OF_CHAOS_SLUGS,
                           context="Choose which Agent of Chaos to become")
        slug = pick if pick in AGENT_OF_CHAOS_SLUGS else _rng.choice(AGENT_OF_CHAOS_SLUGS)
    else:
        slug = _rng.choice(AGENT_OF_CHAOS_SLUGS)
    hero.slug = slug
    hero.name = slug.replace("_", " ").title()
    hero.types = ["Chaos", "Assassin", "Demi-Hero"]
    # "When you become this ..." — fire the new form's on-become ability.
    from engine.card_effects.dsl import dispatch as _dsl_dispatch
    _dsl_dispatch(state, "ON_BECOME", hero.slug, card=hero)


def return_to_brood(state, player_id: int):
    """Revert an Agent of Chaos demi-hero back to Arakni, Marionette."""
    player = state.players[player_id]
    hero = player.hero
    if hero is None or hero.slug not in AGENT_OF_CHAOS_SLUGS:
        return
    hero.slug = "arakni_marionette"
    hero.name = "Arakni, Marionette"
    hero.types = ["Chaos", "Assassin", "Hero"]


def effect_reload(state, player_id: int, source_card=None):
    """Move source_card from hand to arsenal (arsenal must be empty). No-op if no card given."""
    if source_card is None:
        return False
    player = state.players[player_id]
    if player.arsenal.cards:
        return False
    if source_card not in player.hand.cards:
        return False
    choice = _ask_player(state, player_id, [True, False],
                         context="Reload: move this card to arsenal face-down?")
    if not choice:
        return False
    player.hand.remove(source_card)
    source_card.is_public = False
    player.arsenal.add(source_card)
    return True


def effect_dominate(state, player_id: int):
    """Grant Dominate to the current attack (adds 'Dominate' to combat keywords)."""
    if state.combat is not None:
        state.combat.keywords = list(state.combat.keywords or []) + ["Dominate"]
