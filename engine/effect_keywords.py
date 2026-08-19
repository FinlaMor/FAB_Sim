"""Centralized effect keyword functions (CR 8.5).

Each function here represents a named effect keyword from CR 8.5. All game
actions that involve these keywords should route through these functions so
that replacement effects (effect_manager) and triggers (event_manager) fire
consistently from a single callsite.

Functions accept `state: GameState` and any required targets/values.
Replacement effects are applied via `state.effect_manager.apply_replacements`
before execution. Triggers are emitted via `state.event_manager.emit` after.

CR 8.5 Effect Keywords implemented here

Event object expected attributes per apply_replacements:
"""
from __future__ import annotations

import dataclasses
import random
from typing import TYPE_CHECKING, Optional, Callable, Literal
from dataclasses import dataclass, field
from enum import Enum

from engine.state import GameState, Event, StackEntry, Step
from engine.context import effect_context
from engine.card import Card
from engine.continuous_effects import ContinuousEffect, next_timestamp

if TYPE_CHECKING:
    from engine.effects import EffectManager

# in effect_keywords.py

#helpers
def coo(card: Card, return_owner: bool=False) -> int|None:
    """Takes in card object. Returns Int of card's controller and falls back to card owner."""
    if card is None:
        return None
    return card.controller if card.controller is not None else card.owner

def create_emit_event(event) -> Event:
    return Event(
        type=event.type,
        card=event.card.slug if hasattr(event, 'card') and event.card is not None else getattr(event, 'target', None),
        target=event.target if hasattr(event, 'target') and getattr(event, 'target') is not None else None,
        data={k: v for k, v in vars(event).items() if k not in ('type', 'card', 'target')}
    )

class EventType(str, Enum):
    # Core keywords (CR 8.5 order)
    BANISH = "banish"
    CREATE_TOKEN = "create_token"
    DAMAGE = "damage"
    DESTROY = "destroy"
    DISCARD = "discard"
    DRAW = "draw"
    TOTAL_DRAW = "total_draw"
    DECK_EMPTY = "deck_empty"
    GAIN = "gain"
    GETS = "gets"
    GETS_PROPERTY = "gets_property"
    INTIMIDATE = "intimidate"
    INTIMIDATE_RETURN = "intimidate_return"
    LOOK = "look"
    LOSE = "lose"
    PUT_COUNTER = "put_counter"
    REMOVE_COUNTER = "remove_counter"
    REVEAL = "reveal"
    PUT_OBJECT = "put_object"
    ROLL = "roll"
    SEARCH = "search"
    SHUFFLE = "shuffle"
    NAME = "name"
    OPT = "opt"
    RELOAD = "reload"
    TURN = "turn"
    BECOME_COPY = "become_copy"
    NEGATE = "negate"
    REPEAT = "repeat"
    REROLL = "reroll"
    CHARGE = "charge"
    DISTRIBUTE = "distribute"
    PAY = "pay"
    ADD_DEFEND = "add_defend"
    IGNORE = "ignore"
    FREEZE = "freeze"
    UNFREEZE = "unfreeze"
    GAIN_CONTROL = "gain_control"
    TRANSFORM = "transform"
    ATTACK = "attack"
    CONTRACT = "contract"
    CREATE_CARD = "create_card"
    EQUIP = "equip"
    MOVE_COUNTER = "move_counter"
    AWAKEN = "awaken"
    PITCH = "pitch"
    CLASH = "clash"
    WAGER = "wager"
    AMP = "amp"
    TRANSCEND = "transcend"
    EXCHANGE = "exchange"
    MARK = "mark"
    RETRIEVE = "retrieve"
    RETURN_TO_THE_BROOD = "return_to_the_brood"
    GIVE = "give"
    STEAL = "steal"
    TAP = "tap"
    UNTAP = "untap"
    CHEER = "cheer"
    BOO = "boo"
    # Secondary events emitted inline
    HIT = "hit"
    ALLY_DIED = "ally_died"
    RETURN_FROM_BANISH = "return_from_banish"
    # System events (used as until_condition strings)
    EOT = "end_of_turn"
    START_OF_TURN = "start_of_turn"
    END_PHASE_BEGINNING = "end_phase_beginning"

@dataclass
class BanishEvent:
    """CR 8.5.1 — move an object to the banished zone.
    
    Replacement effects can modify:
        destination  — e.g. redirect to graveyard instead (card still considered banished, CR 8.5.1b)
        cancelled    — prevent the banish entirely
    """
    type: str = EventType.BANISH
    target: Card = None
    source_player_id: int = None      # who is causing the banishing
    target_player_id: int = None      # who owns the card being banished
    origin_zone: str = None           # where the card came from ("hand", "deck", etc.)
    destination: str = "banished"     # replacement effects can change this
    until_condition: str = None       # e.g. "end_of_turn" for temporary banish (CR 8.5.1c)
    cancelled: bool = False


def banish(state: GameState, card: Card, source_player_id: int,
           origin_zone: Optional[str] = None, until_condition: str = None) -> BanishEvent:
    """CR 8.5.1 — banish a card.
    
    Returns the event so callers can inspect what actually happened
    (e.g. was it redirected? cancelled?).
    """
    target_player_id = card.owner

    event = BanishEvent(
        target=card,
        source_player_id=source_player_id,
        target_player_id=target_player_id,
        origin_zone=origin_zone,
        until_condition=until_condition,
    )

    # replacement effects fire before the move (CR 6.5)
    event_dict = state.effect_manager.apply_replacements(vars(event).copy(), state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.cancelled:
        return event

    # execute the move
    player = state.players[event.target_player_id]
    card = event.target
    if event.origin_zone is not None:
        z = getattr(player, event.origin_zone, None)
        if z is not None:
            z.remove(card)
    getattr(player, event.destination).add(card)

    # "if you've banished an Earth card this turn" and similar.
    _record_turn_event(state, event.source_player_id, "banish",
                       getattr(card, "slug", None),
                       getattr(card, "types", None) or [],
                       getattr(card, "subtypes", None) or [],
                       getattr(card, "talents", None) or [],
                       getattr(card, "classes", None) or [])

    # trigger: "when a card is banished" listeners fire after (CR 8.5.1)
    state.event_manager.emit(event=create_emit_event(event=event), game_state=state)

    # CR 8.5.1c: register delayed return effect if temporary
    if event.until_condition:
        _register_return_from_banish(state, card=event.target, target_player_id=event.target_player_id, origin_zone=event.origin_zone, until_condition=event.until_condition)

    return event

def _register_return_from_banish(state, card, target_player_id, origin_zone, until_condition):
    
    def handler(event, s: GameState) -> None:
        player = s.players[target_player_id]
        s.event_manager.unregister(until_condition, handler)

        # find where the card is now
        if card in player.banished.cards:
            player.banished.remove(card)
        elif card.is_in_arena or card.zone == 'stack':
            # CR 3.0.9b: still referenceable, return it from wherever it is
            getattr(player, card.zone).remove(card)
        else:
            # CR 3.0.9: card entered a non-arena/non-stack zone — ceased to exist, return fails
            return

        getattr(player, origin_zone).add(card)
        s.event_manager.emit(Event(type=EventType.RETURN_FROM_BANISH, card=card.slug), s)

    state.event_manager.register(until_condition, handler)


# ---------------------------------------------------------------------------
# Token metadata (CR 8.5.2) lives in engine/card_effects/token_meta.py so this
# file stays free of card-specific data. Zone routing is derived from the card
# DB template; token_meta provides numbered keywords, ally stats, per-token
# entry hooks, and a slug-table fallback for card-DB-less test states.
# ---------------------------------------------------------------------------


@dataclass
class CreateTokenEvent:
    """CR 8.5.2 — create a token and put it in the arena under the control of player_id.
    
    Replacement effects can modify:
        number of tokens created - increase or decrease (mordred tide, ripple away)
    """
    card: Card                              # token to be created (required)
    source_player_id: int = None             # who is causing the tokens to be created
    target_player_id: int = None             # who controls the token. Per 8.5.2c
    type: str = EventType.CREATE_TOKEN
    destination: str = "tokens"              # replacement effects can change this
    number: int = 1                          # number to create; can be modified
    canceled: bool = False


def create_token(state: GameState, target_player_id: int = None, token_slug: str = None,
                 number: int = 1, source_player_id: int | None = None,
                 token: str | None = None, destination: str | None = None) -> CreateTokenEvent:
    """CR 8.5.2 — Create token(s) in the arena under target_player_id's control.

    Replacement effects can intercept CreateTokenEvent to modify event.number
    (increase or decrease), change event.destination, or cancel creation
    entirely before execution. Tokens receive keyword registration and
    prevention effects before zone entry (CR 8.5.2b) so arena-entry triggers
    find prevention already active.

    `token` is an alias for token_slug. `destination` names an explicit player
    zone (e.g. "weapon1") overriding type-based routing — needed for tokens
    whose zone cannot be inferred (a weapon token can go to either weapon slot).
    """
    if token is not None:
        token_slug = token
    if token_slug is None or target_player_id is None:
        raise TypeError("create_token requires target_player_id and token_slug")
    _src = source_player_id if source_player_id is not None else target_player_id

    # Tokens entering play must have a DSL definition, same as deck cards.
    from engine.card_effects.dsl.loader import require_card, get_card
    # Token slugs are canonical lowercase_underscore ("seismic_surge"); tolerate a
    # display-cased / spaced value ("Seismic Surge", "Silver") by falling back to
    # its slugified form. Pure fallback: a valid slug is never altered.
    if token_slug and get_card(token_slug) is None:
        import re as _re
        alt = _re.sub(r"[^a-z0-9]+", "_", token_slug.strip().lower()).strip("_")
        if alt and get_card(alt) is not None:
            token_slug = alt
    require_card(token_slug)

    # card_db lookup provides a template slug; fresh Card objects are built per token below.
    template = state.card_db.get(token_slug) if hasattr(state, "card_db") else None

    event = CreateTokenEvent(
        card=template,
        source_player_id=_src,
        target_player_id=target_player_id,
        number=number,
        destination=destination or "tokens",
    )

    event_dict = state.effect_manager.apply_replacements(vars(event).copy(), state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.number == 0 or event.canceled:
        return event

    _slug = (event.card.slug if event.card is not None else token_slug)
    controller = state.players[event.target_player_id]
    effect_mngr = getattr(state, "effect_manager", None)

    for _ in range(event.number):
        # CR 3.0.9: each token is a distinct Card object with its own identity.
        token = Card(slug=_slug, name=_slug.replace("_", " ").title())
        token.owner = event.target_player_id
        token.controller = event.target_player_id
        token.is_public = True
        # Inherit the printed type line from the card DB template so zone
        # entry checks see the real types (e.g. weapon tokens need "Weapon").
        if template is not None and (template.types or template.subtypes):
            token.types = list(template.types or [])
            token.subtypes = list(template.subtypes or [])
            if "Token" not in token.types:
                token.types.append("Token")
        else:
            token.types = ["Token"]

        # Set token keywords before zone entry (CR 8.5.2b): explicit override
        # first (restores numbers the card DB drops, e.g. "Ward 1"), else
        # inherit the printed keywords from the card DB template
        # (e.g. a Graphene Chelicera weapon token carries Stealth).
        from engine.card_effects.token_meta import (
            TOKEN_KEYWORDS, TOKEN_ENTRY_HOOKS, ALLY_TOKEN_STATS,
            AURA_TOKENS, ITEM_TOKENS, ALLY_TOKENS,
        )
        if _slug in TOKEN_KEYWORDS:
            token.keywords = list(TOKEN_KEYWORDS[_slug])
        elif template is not None and getattr(template, 'keywords', None):
            token.keywords = list(template.keywords)

        # Inherit printed stats/activation fields so ability tokens function
        # (a Graphene Chelicera weapon token has power 1 and a "Once per Turn
        # Action — {r}: Attack" activation).
        if template is not None:
            for attr in ("raw_power", "base_power", "power", "activation_cost",
                         "base_activations", "activations", "has_per_turn_limit"):
                val = getattr(template, attr, None)
                if val is not None and getattr(token, attr, None) in (None, False):
                    setattr(token, attr, val)

        # Register keyword-based prevention effects before zone entry so that
        # any arena-entry trigger that immediately deals damage already finds them.
        if effect_mngr is not None:
            effect_mngr.register_prevention_effects(token, state)
            # Token text that isn't a keyword (e.g. Zen State's prevention)
            # is registered via per-token entry hooks in token_meta.
            entry_hook = TOKEN_ENTRY_HOOKS.get(_slug)
            if entry_hook is not None:
                entry_hook(state, token)

        # Route to the correct arena zone. An explicit destination (from the
        # caller or a replacement effect) wins; otherwise route by the token's
        # printed subtypes from the card DB template. The token_meta slug
        # tables are only a fallback for minimal test states without a card DB.
        _printed_subtypes = list(getattr(template, "subtypes", None) or [])
        if _printed_subtypes:
            _is_aura = "Aura" in _printed_subtypes
            _is_item = "Item" in _printed_subtypes
            _is_ally = "Ally" in _printed_subtypes
        else:
            _is_aura = _slug in AURA_TOKENS
            _is_item = _slug in ITEM_TOKENS
            _is_ally = _slug in ALLY_TOKENS
        if event.destination == "weapon_slot":
            # Equip a weapon token into an available weapon zone (respects a
            # hero's weapon-zone count, e.g. 1 for some heroes).
            slots = [controller.weapon1]
            if getattr(controller, "weapon_zone_count", 2) >= 2:
                slots.append(controller.weapon2)
            dest_zone = next((z for z in slots if not z.cards), None)
            if dest_zone is not None:
                dest_zone.add(token)
            # No free weapon zone → the token cannot be equipped (CR: it would
            # cease to exist); drop it.
        elif event.destination and event.destination != "tokens":
            dest_zone = getattr(controller, event.destination, None)
            if dest_zone is None:
                raise ValueError(f"create_token: unknown destination zone {event.destination!r}")
            dest_zone.add(token)
        elif _is_aura:
            token.types.append("Aura")
            controller.auras.add(token)
        elif _is_item:
            token.types.append("Item")
            controller.items.add(token)
        elif _is_ally:
            # Stats: token_meta override first, then the card DB template.
            _stats = ALLY_TOKEN_STATS.get(_slug, {})
            if not token.subtypes:
                token.subtypes = ["Ally"]
            token.base_power = _stats.get(
                "power",
                getattr(template, "base_power", None) or getattr(template, "power", None))
            token.base_life = _stats.get("life", getattr(template, "base_life", None))
            token.current_life = token.base_life
            token.permanent_subtype = "Ally"
            controller.allies.add(token)
            # Keep allies_exhausted list in sync with allies zone length.
            while len(controller.allies_exhausted) < len(controller.allies.cards):
                controller.allies_exhausted.append(False)
        else:
            controller.tokens.add(token)

    # Generic token-creation event: DSL triggers (e.g. "the first time each
    # turn you create a Gold token") and listeners filter by data["slug"].
    from engine.state import Event as _StateEvent
    state.event_manager.emit(
        _StateEvent(type="token_created",
                    data={"player_id": event.target_player_id,
                          "slug": _slug, "count": event.number}),
        state,
    )

    # "if you've created a Gold this turn" / "an aura was created this turn".
    # One marker per token created, so "the FIRST Gold created this turn" is a
    # count check rather than needing its own flag. Subtypes and types are
    # recorded alongside the slug so a card can ask by category ("an aura")
    # rather than having to name every token that happens to be one.
    _created = locals().get("token")
    for _ in range(max(1, event.number or 1)):
        _record_turn_event(state, event.target_player_id, "create", _slug,
                           getattr(_created, "subtypes", None) or [],
                           getattr(_created, "types", None) or [],
                           getattr(_created, "permanent_subtype", None))

    # CR 8.5.2b: "when {token} enters the arena" triggers fire after creation.
    state.event_manager.emit(create_emit_event(event), state)

    return event

class DamageType:
    GENERIC = "generic"
    PHYSICAL = "physical"
    ARCANE = "arcane"

@dataclass
class DamageEvent:
    """CR 8.5.3 Deal (damage) is a discrete effect. To deal damage to an object, that
    object loses {h} equal to the damage dealt. Only living objects may be targeted.
    All living cards in slug_index have in their types or subtypes either 'ally' or
    'hero' (including the 'demi-hero' subtype)
    """
    target: Card
    target_type: str
    type: str = EventType.DAMAGE
    amount: int = 0
    damage_type: str = DamageType.GENERIC
    source_player_id: int | None = None
    target_player_id: int | None = None
    damage_source: str | None = None
    damage_source_card: Card | None = None
    unpreventable: bool = False
    canceled: bool = False


def deal_damage(state: GameState, amount: int, damage_type: str, source_player_id: int, damage_target: Card, damage_source: str,
                damage_source_card=None, canceled=False):
    """deals damage of 'amount' amount and 'damage_type' type to 'damage_target'.
    If dealing damage to a player, damage_target should be set to player.hero Card object"""

    is_hero = any('hero' in t.lower() for t in [t.lower() for t in (damage_target.types or []) + (damage_target.subtypes or [])])
    target_type = 'hero' if is_hero else 'ally'

    event = DamageEvent(
        target=damage_target,
        amount=amount,
        damage_type=damage_type,
        target_type = target_type,
        source_player_id=source_player_id,
        damage_source=damage_source,
        damage_source_card=damage_source_card,
        canceled=canceled
    )

    # CR 8.5.3c: non-living targets cannot be damaged
    is_living = hasattr(damage_target, 'life') and (getattr(damage_target, 'life') or 0) > 0
    if not is_living:
        event.canceled = True
        return event


    if is_hero:
        event.target_player_id = coo(damage_target)

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.amount == 0 or event.canceled:
        return event

    # CR 8.5.47: consume amp counter for arcane damage (next arcane damage this turn +N)
    if event.damage_type == DamageType.ARCANE and event.source_player_id is not None:
        src_player = state.players.get(event.source_player_id)
        if src_player is not None:
            amp_bonus = src_player.class_counters.pop('amp', 0)
            if amp_bonus:
                event = dataclasses.replace(event, amount=event.amount + amp_bonus)

    # reinitialize variables after replacement effects fire
    damage_target = event.target

    is_hero = any('hero' in t.lower() for t in [t.lower() for t in (damage_target.types or []) + (damage_target.subtypes or [])])
    target_type = 'hero' if is_hero else 'ally'

    # "if you've dealt arcane damage this turn" and friends. Recorded once the
    # damage is final (past replacements/cancellation), against the DEALING
    # player, with the damage type as the qualifier.
    if event.amount > 0:
        _dtype = getattr(event.damage_type, "value", event.damage_type)
        _kind = "hero" if is_hero else "ally"
        _record_turn_event(state, event.source_player_id, "damage", _dtype, _kind)
        # The marker above answers "have you dealt arcane damage this turn";
        # this tally answers "how much", which the markers cannot — see
        # Player.damage_dealt_this_turn.
        # "with cost equal to or less than the DAMAGE DEALT by this card"
        # (Lesson in Lava). The printed number is not the answer — prevention
        # and replacement effects can change it — so the last actually-dealt
        # amount is published for the LAST_DAMAGE_DEALT amount expression.
        state._last_damage_dealt = event.amount
        _src = state.players.get(event.source_player_id) if event.source_player_id is not None else None
        if _src is not None:
            tally = getattr(_src, "damage_dealt_this_turn", None)
            if tally is None:
                tally = _src.damage_dealt_this_turn = {}
            for key in ("total", str(_dtype).lower(), _kind,
                        f"{str(_dtype).lower()}:{_kind}"):
                tally[key] = tally.get(key, 0) + event.amount

    # execute the damage
    if is_hero:
        target_player = state.players[coo(damage_target)]
        target_player.life -= event.amount
        state.event_manager.emit(create_emit_event(event), state)
        if event.damage_type == DamageType.PHYSICAL and event.amount > 0 and state.step == Step.COMBAT_DAMAGE: # 'Hits' occur during the damage step of combat and only if the damage is physical type
            state.event_manager.emit(Event(type=EventType.HIT, data={"amount": event.amount, "damage_type": event.damage_type, "target": damage_target.slug, 'target_type': target_type}), state)
    else:
        # ally damage
        damage_target.life = max(0, (damage_target.life or 0) - event.amount)
        state.event_manager.emit(create_emit_event(event), state)
        if event.damage_type == DamageType.PHYSICAL and event.amount > 0 and state.step == Step.COMBAT_DAMAGE:
            state.event_manager.emit(Event(type=EventType.HIT, data={"amount": event.amount, "damage_type": event.damage_type, "target": damage_target.slug, 'target_type': target_type}), state)
        if damage_target.life == 0:
            controller = state.players[coo(damage_target)]
            controller.allies.remove(damage_target)
            controller.graveyard.add(damage_target)
            state.event_manager.emit(Event(type=EventType.ALLY_DIED, data={"ally": damage_target.slug}), state)

    return event

_ARENA_ZONES = frozenset({
    "head", "chest", "arms", "legs", "weapon", "hero",
    "permanents", "allies", "combat chain",
})


@dataclass
class DestroyEvent:
    """ CR 8.5.4 Destroy is a discrete effect. To destroy an object, put it into its owner's graveyard.
    """
    target: Card
    destroy_source: Optional[Card] = None
    source_player_id: Optional[int] = None
    type: str = EventType.DESTROY
    canceled: bool = False


TURN_EVENT_MARKER = "did_this_turn:"


def _norm_ident(value) -> str:
    return "".join(ch for ch in str(value) if ch.isalnum()).lower()


def record_turn_event_for_player(player, event: str, *qualifiers) -> None:
    """Same as _record_turn_event but keyed on a Player object rather than a
    GameState + id.

    Zone.add is the single choke point for a card entering the graveyard — 11
    call sites across 3 files reach it, and future ones will too — but it has
    only a `player` back-reference, no state. Recording there instead of at each
    call site is what makes "an instant was put into your graveyard this turn"
    (Starfall, 16 cards) reliable rather than a list of paths someone remembered.
    """
    if player is None:
        return
    event = _norm_ident(event)
    if not event:
        return
    markers = [f"{TURN_EVENT_MARKER}{event}"]
    seen: set[str] = set()
    for qual in qualifiers:
        values = qual if isinstance(qual, (list, tuple, set)) else [qual]
        for value in values:
            ident = _norm_ident(value) if value is not None else ""
            if ident and ident not in seen:
                seen.add(ident)
                markers.append(f"{TURN_EVENT_MARKER}{event}:{ident}")
    player.current_turn_effects.extend(markers)


def _record_turn_event(state: GameState, player_id, event: str, *qualifiers) -> None:
    """Record "you did <event> (to/with a <qualifier>) this turn".

    The generic backing for cards that ask "if you've dealt arcane damage this
    turn", "if you've pitched a blue card", "if you've attacked with a weapon
    twice". Those were each hand-rolled as a private flag nobody set — 154 such
    flags across 169 cards, every one an ability that could never fire — and
    they fragment badly: "arcane damage dealt this turn" alone appeared under
    seven different spellings.

    One marker is written for the bare event and one per qualifier, so a card
    can ask coarsely ("dealt damage") or precisely ("dealt arcane damage").
    Markers are appended on EVERY occurrence, never deduplicated, so a count
    check ("attacked with a weapon twice") is just counting them — the same
    convention boost uses.
    """
    # Deduplicate WITHIN one call but never across calls: a single token can
    # answer to "aura" via subtypes, types and permanent_subtype at once, and
    # writing it three times would make one creation look like three to a count
    # check. One occurrence must contribute exactly one marker per identity.
    # (That dedupe now lives in record_turn_event_for_player, which this wraps.)
    player = state.players.get(player_id) if player_id is not None else None
    record_turn_event_for_player(player, event, *qualifiers)


DESTROYED_MARKER = "destroyed_this_turn:"


def _destroyed_identifiers(card) -> set[str]:
    """Every name a card could be referred to by in "destroyed a X this turn".

    A Might token answers to its slug ("might") and its type ("token"); an item
    answers to "item"; an aura to "aura". Folded to lowercase alphanumerics so
    "Lightning Flow" and "lightning_flow" are the same identifier.
    """
    out = set()
    def _add(v):
        n = "".join(ch for ch in str(v) if ch.isalnum()).lower()
        if n:
            out.add(n)
    _add(getattr(card, "slug", ""))
    _add(getattr(card, "name", "") or getattr(card, "raw_name", ""))
    for attr in ("subtypes", "types", "raw_subtypes", "raw_types"):
        for v in (getattr(card, attr, None) or []):
            _add(v)
    return out


def _record_destroyed_this_turn(state: GameState, card) -> None:
    """Record that this player destroyed such-a-thing this turn (CR turn-scoped).

    Generic replacement for the per-card flags cards used to invent
    (MIGHT_TOKEN_DESTROYED_THIS_TURN, ITEM_DESTROYED_THIS_TURN, ...), none of
    which anything ever set. Attributed to the destroyed card's controller,
    which is who "destroyed a Might token" in every card that asks — those
    tokens are destroyed by their own controller for the benefit.
    """
    pid = coo(card)
    player = state.players.get(pid) if pid is not None else None
    if player is None:
        return
    for ident in _destroyed_identifiers(card):
        marker = f"{DESTROYED_MARKER}{ident}"
        if marker not in player.current_turn_effects:
            player.current_turn_effects.append(marker)


def destroy(state: GameState, destroy_target: Card, destroy_source: Optional[Card] = None):
    """CR 8.5.4 Destroy is a discrete effect. To destroy an object, put it into its owner's graveyard.

    Handles:
    - Replacement effects (e.g. indestructible)
    - Ephemeral (CR 8.3.21): ceases to exist instead of going to graveyard
    - leaves_arena event if card was in an arena zone
    - process_cease_to_exist (LKI snapshot)
    - Multi-zone search: works even when card is controlled by a different player
    """
    source_player_id = coo(destroy_source)

    event = DestroyEvent(
        target=destroy_target,
        destroy_source=destroy_source,
        source_player_id=source_player_id,
        canceled=False,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    destroy_target = event.target
    _record_destroyed_this_turn(state, destroy_target)
    zone = destroy_target.zone
    was_arena = zone in _ARENA_ZONES or getattr(destroy_target, 'prev_zone', None) in _ARENA_ZONES

    # Snapshot LKI before any zone change (CR 1.2.3c)
    state.process_cease_to_exist(destroy_target)

    # Remove from current zone — search controller first, then all players, then shared zones
    removed = False
    controller_id = coo(destroy_target)
    if controller_id is not None and controller_id in state.players:
        z = state.players[controller_id].zone_by_name(zone)
        if z is not None:
            removed = z.remove(destroy_target)
    if not removed:
        for player in state.players.values():
            z = player.zone_by_name(zone)
            if z is not None and z.remove(destroy_target):
                removed = True
                break
    if not removed:
        for shared in (getattr(state, 'combat_chain', None), getattr(state, 'stack', None)):
            if shared is not None and hasattr(shared, 'remove') and shared.remove(destroy_target):
                removed = True
                break
    if not removed:
        # Name-based lookup can miss the target when its .zone attribute is stale
        # or generic — e.g. an equipped weapon whose .zone is "weapon" (which maps
        # to the weapon1 slot) while it actually sits in weapon2. Fall back to an
        # identity sweep across every zone so the card is removed from wherever it
        # really is; without this the graveyard add below would DUPLICATE it
        # (leaving the original in its slot). CR 8.5.4.
        for player in state.players.values():
            for z in (player.all_zones() + [player.items, player.auras,
                                            player.allies, player.tokens, player.soul]):
                if destroy_target in z.cards and z.remove(destroy_target):
                    removed = True
                    break
            if removed:
                break

    # CR 8.3.21 Ephemeral: ceases to exist instead of entering the graveyard
    is_ephemeral = any(
        kw.lower() == 'ephemeral'
        for kw in (getattr(destroy_target, 'keywords', None) or [])
    )
    if is_ephemeral:
        if was_arena:
            state.event_manager.emit(
                Event(type='leaves_arena', data={'card': destroy_target}), state)
        state.event_manager.emit(
            Event(type='card_ceased_to_exist', data={'card': destroy_target}), state)
        return event

    if not removed:
        # The target could not be located in any zone — it is already gone.
        # Adding it to the graveyard now would materialise a phantom copy, so
        # stop here rather than duplicate the card.
        return event

    # Card-specific 'if this would be put into a graveyard, instead remove it from
    # the game' (e.g. Goldfin Harpoon) — like Ephemeral but declared per card via a
    # REPLACEMENT ability rather than the keyword. Skip the graveyard add so it
    # ceases to exist.
    from engine.card_effects.replacement_abilities import card_has_replacement
    if card_has_replacement(getattr(destroy_target, 'slug', ''),
                            "remove_from_game_instead_of_graveyard"):
        state.event_manager.emit(
            Event(type='card_ceased_to_exist', data={'card': destroy_target}), state)
        return event

    # Move to owner's graveyard
    state.players[destroy_target.owner].graveyard.add(destroy_target)

    if was_arena:
        state.event_manager.emit(
            Event(type='leaves_arena', data={'card': destroy_target}), state)
    state.event_manager.emit(create_emit_event(event), state)

    return event

@dataclass
class DiscardEvent:
    type: str = EventType.DISCARD
    target: Optional[Card] = None
    discard_player: int | None = None
    discard_source: Optional[Card] = None
    discard_source_player: int | None = None
    origin: str = "hand"
    destination: str = "graveyard"
    canceled: bool = False


def discard(state: GameState, discard_target: Card, discard_source: Card | None,
            origin: str = "hand") -> DiscardEvent:
    discard_player_id = coo(discard_target)
    source_player = coo(discard_source) if discard_source is not None else None

    event = DiscardEvent(
        target=discard_target,
        discard_source=discard_source,
        discard_source_player=source_player,
        discard_player=discard_player_id,
        origin=origin,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    # CR 8.5.5b: if player has no cards in the origin zone, discard effect fails
    # (checked AFTER replacement effects which may redirect origin or cancel)
    origin_zone = getattr(state.players[event.discard_player], event.origin, None)
    if origin_zone is None or len(origin_zone.cards) == 0:
        event.canceled = True
        return event

    # execute the discard
    assert event.target is not None and event.discard_player is not None
    target = event.target
    player = state.players[event.discard_player]
    source = event.discard_source

    getattr(player, event.origin).remove(target)
    getattr(player, event.destination).add(target)
    state.event_manager.emit(create_emit_event(event), state)

    return event

@dataclass
class DrawEvent:
    type: str = EventType.DRAW
    draw_player: int | None = None
    source: Optional[Card] = None
    source_player: int | None = None
    origin: str = "deck"
    destination: str = "hand"
    number: int = 1
    canceled: bool = False


def draw(state: GameState, draw_player: int, source: Optional[Card] = None,
         number: int = 1) -> DrawEvent:
    """CR 8.5.6 — draw a card (or number of cards).

    Moves the top card(s) of the deck to the player's hand.
    If the deck is empty, emits a 'deck_empty' event (loss condition per CR 8.5.6).
    """
    source_player = coo(source) if source is not None else None

    event = DrawEvent(
        draw_player=draw_player,
        source=source,
        source_player=source_player,
        number=number,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    player = state.players[event.draw_player]

    # Cranial Crush (WTR): "they can't draw cards during their next action phase."
    # The end-phase draw-to-intellect uses _draw_cards() (a separate path), so this
    # only suppresses action-phase / effect-driven draws, as the card intends.
    if "cant_draw" in getattr(player, "current_turn_effects", []):
        return event

    # "if you've drawn a card this turn" / "drawn 2 or more".
    _record_turn_event(state, event.draw_player, "draw")

    drawn = 0

    for _ in range(event.number):
        card = getattr(player, event.origin).pop_top()
        if card is None:
            # CR 8.5.6b: deck empty — draw fails, emit loss condition signal
            state.event_manager.emit(Event(type=EventType.DECK_EMPTY, data={"player_id": event.draw_player}), state)
            break
        from engine.state import ZoneEntryResult
        if getattr(player, event.destination).add(card) == ZoneEntryResult.FAIL:
            # Destination refused the card (CR 3.0.11) — undo the pop so the
            # card is not silently lost from the game.
            getattr(player, event.origin).cards.insert(0, card)
            break
        drawn += 1
        state.event_manager.emit(Event(type=EventType.DRAW, data={
            "draw_player": event.draw_player,
            "source": event.source.slug if event.source is not None else None,
            "source_player": event.source_player,
            "destination": event.destination,
            "origin": event.origin,
        }), state)

    # CR 8.5.6b: total_draw only fires if at least one card was actually drawn
    if drawn > 0:
        state.event_manager.emit(Event(type=EventType.TOTAL_DRAW, data={
            "draw_player": event.draw_player,
            "source": event.source.slug if event.source is not None else None,
            "source_player": event.source_player,
            "destination": event.destination,
            "origin": event.origin,
            "number": drawn,
        }), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.7 — gain (asset)
# ---------------------------------------------------------------------------

class AssetType:
    LIFE = "life"           # {h} — increases life total of player or living object
    RESOURCES = "resources" # {r} — increases player's resource points
    ACTION_POINTS = "action_points"  # {a} — CR 8.5.7b: only for turn player
    CHI = "chi"             # {c} — increases player's chi points (CR 1.13.5)


@dataclass
class GainEvent:
    type: str = EventType.GAIN
    asset_type: str = AssetType.LIFE
    amount: int = 0
    source_player_id: int | None = None
    target_player_id: int | None = None   # set when target is a player
    target_card: Optional[Card] = None    # set when target is a living object (ally)
    canceled: bool = False


def gain(state: GameState, asset_type: str, amount: int, source_player_id: int,
         target_player_id: int | None = None,
         target_card: Optional[Card] = None) -> GainEvent:
    """CR 8.5.7 — gain an asset.

    Exactly one of target_player_id or target_card must be provided.
    Returns a GainEvent; check event.canceled if the gain was rejected.
    """
    event = GainEvent(
        asset_type=asset_type,
        amount=amount,
        source_player_id=source_player_id,
        target_player_id=target_player_id,
        target_card=target_card,
    )

    # CR 8.5.7b: non-turn-player cannot gain action points
    if asset_type == AssetType.ACTION_POINTS:
        if target_player_id is not None and target_player_id != state.active_player:
            event.canceled = True
            return event

    # CR 8.5.7a: gaining {h} on an object without the life property fails
    if asset_type == AssetType.LIFE and target_card is not None:
        is_living = True if getattr(target_card, 'life') != None else False
        if not is_living:
            event.canceled = True
            return event

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled or event.amount <= 0:
        return event

    # execute the gain
    if event.asset_type == AssetType.LIFE:
        if event.target_card is not None:
            event.target_card.life = (event.target_card.life or 0) + event.amount
        else:
            state.players[event.target_player_id].life += event.amount
            # Tallied here, at the single point life actually rises, rather than
            # at call sites — the same reason the graveyard turn-event hooks
            # Zone.add. A magnitude, not an occurrence count.
            player = state.players[event.target_player_id]
            player.life_gained_this_turn = getattr(
                player, "life_gained_this_turn", 0) + event.amount
    elif event.asset_type == AssetType.RESOURCES:
        state.players[event.target_player_id].resources += event.amount
    elif event.asset_type == AssetType.ACTION_POINTS:
        state.players[event.target_player_id].action_points += event.amount
    elif event.asset_type == AssetType.CHI:
        state.players[event.target_player_id].chi += event.amount

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.8 — gets (numerical property)
# ---------------------------------------------------------------------------

class GetsKind:
    ADD = "add"         # +N  — stage 8 substage 5
    SUBTRACT = "sub"    # -N  — stage 8 substage 6
    SET = "set"         # base = N — stage 8 substage 2


_GETS_SUBSTAGE = {
    GetsKind.SET: 2,
    GetsKind.ADD: 5,
    GetsKind.SUBTRACT: 6,
}

# Supported numerical properties (CR 8.5.8)
_GETS_VALID_PROPS = frozenset({"power", "defense", "cost", "life"})


@dataclass
class GetsEvent:
    type: str = EventType.GETS
    prop: str = ""                          # "power", "defense", "cost", "life"
    kind: str = GetsKind.ADD               # GetsKind constant
    amount: int = 0
    source_card: Optional[Card] = None
    source_player_id: int | None = None
    target_card: Optional[Card] = None      # card being modified
    effect_id: str = ""                     # for later removal
    until_condition: str | None = None      # e.g. "end_of_turn"; None = persistent
    canceled: bool = False


def gets(state: GameState, prop: str, kind: str, amount: int,
         source_card: Optional[Card], target_card: Card,
         until_condition: str | None = None,
         effect_id: str = "") -> GetsEvent:
    """CR 8.5.8 — modify a numerical property of an object as a continuous effect.

    Registers a ContinuousEffect with the state's continuous_effect_manager.
    If until_condition is set, automatically removes the effect when that event fires.
    """
    source_player_id = coo(source_card) if source_card is not None else None

    event = GetsEvent(
        prop=prop,
        kind=kind,
        amount=amount,
        source_card=source_card,
        source_player_id=source_player_id,
        target_card=target_card,
        effect_id=effect_id or f"gets_{prop}_{id(target_card)}_{next_timestamp()}",
        until_condition=until_condition,
    )

    # CR 8.5.8a: property must exist on the object
    if prop not in _GETS_VALID_PROPS:
        event.canceled = True
        return event
    if getattr(target_card, prop, None) is None and kind != GetsKind.SET:
        event.canceled = True
        return event

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    substage = _GETS_SUBSTAGE[event.kind]
    eid = event.effect_id
    slug = source_card.slug if source_card is not None else "unknown"
    target = event.target_card
    amt = event.amount
    k = event.kind

    def apply_fn(current_value, s, card):
        if card is not target:
            return current_value
        if k == GetsKind.SET:
            return amt
        if k == GetsKind.ADD:
            return (current_value or 0) + amt
        if k == GetsKind.SUBTRACT:
            return max(0, (current_value or 0) - amt)
        return current_value

    ce = ContinuousEffect(
        stage=8,
        substage=substage,
        timestamp=next_timestamp(),
        prop=event.prop,
        source_slug=slug,
        apply_fn=apply_fn,
        effect_id=eid,
        persistent=True,
        condition_fn=lambda s, card: card is target,
    )
    state.continuous_effect_manager.add(ce)

    # register automatic removal if temporary
    if event.until_condition:
        def _remove_handler(ev, s: GameState) -> None:
            s.continuous_effect_manager.remove_by_id(eid)
            s.event_manager.unregister(event.until_condition, _remove_handler)
        state.event_manager.register(event.until_condition, _remove_handler)
    else:
        # No duration: clean up when the target card leaves the arena (prevents leak)
        _eid = eid
        _target = target
        def _cleanup_on_arena_exit(ev, s: GameState) -> None:
            if ev.data is not None and ev.data.get('card') is _target:
                s.continuous_effect_manager.remove_by_id(_eid)
                s.event_manager.unregister('leaves_arena', _cleanup_on_arena_exit)
        state.event_manager.register('leaves_arena', _cleanup_on_arena_exit)

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.9 — gets/is (non-numerical property)
# CR 8.5.13 — loses (non-numerical property)
# ---------------------------------------------------------------------------

# Supported non-numerical properties and their CR stage mappings
_PROP_STAGE = {
    "keywords": 6,   # CR 6.3 stage 6
    "types": 4,      # CR 6.3 stage 4
    "subtypes": 4,   # CR 6.3 stage 4
}


@dataclass
class GetsPropertyEvent:
    """CR 8.5.9 / 8.5.13 — add or remove a non-numerical property on a card."""
    type: str = EventType.GETS_PROPERTY
    prop: str = ""                          # "keywords", "types", "subtypes"
    value: str = ""                         # the property value to add/remove
    remove: bool = False                    # True = loses (CR 8.5.13), False = gets (CR 8.5.9)
    source_card: Optional[Card] = None
    source_player_id: int | None = None
    target_card: Optional[Card] = None
    effect_id: str = ""
    until_condition: str | None = None
    canceled: bool = False


def gets_property(state: GameState, prop: str, value: str,
                source_card: Optional[Card], target_card: Card,
                remove: bool = False,
                until_condition: str | None = None,
                effect_id: str = "") -> GetsPropertyEvent:
    """CR 8.5.9 — target card gains the specified non-numerical property (keyword/type/subtype).
    CR 8.5.13 — set remove=True to make the card lose the property instead.

    Registers a ContinuousEffect with the appropriate stage.
    If until_condition is set, automatically removes the effect when that event fires.
    """
    source_player_id = coo(source_card) if source_card is not None else None

    event = GetsPropertyEvent(
        prop=prop,
        value=value,
        remove=remove,
        source_card=source_card,
        source_player_id=source_player_id,
        target_card=target_card,
        effect_id=effect_id or f"is_property_{prop}_{value}_{id(target_card)}_{next_timestamp()}",
        until_condition=until_condition,
    )

    if prop not in _PROP_STAGE:
        event.canceled = True
        return event

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    stage = _PROP_STAGE[event.prop]
    eid = event.effect_id
    slug = source_card.slug if source_card is not None else "unknown"
    target = event.target_card
    v = event.value
    is_remove = event.remove

    def apply_fn(current_value, s, card):
        if card is not target:
            return current_value
        # current_value is a set for keywords, list for types/subtypes
        if isinstance(current_value, set):
            result = set(current_value)
            if is_remove:
                result.discard(v)
            else:
                result.add(v)
            return result
        else:
            result = list(current_value) if current_value else []
            if is_remove:
                return [x for x in result if x != v]
            else:
                return result if v in result else result + [v]

    ce = ContinuousEffect(
        stage=stage,
        substage=1,
        timestamp=next_timestamp(),
        prop=event.prop,
        source_slug=slug,
        apply_fn=apply_fn,
        effect_id=eid,
        persistent=True,
        condition_fn=lambda s, card: card is target,
    )
    state.continuous_effect_manager.add(ce)

    if event.until_condition:
        def _remove_handler(ev, s: GameState) -> None:
            s.continuous_effect_manager.remove_by_id(eid)
            s.event_manager.unregister(event.until_condition, _remove_handler)
        state.event_manager.register(event.until_condition, _remove_handler)
    else:
        # No duration: clean up when the target card leaves the arena (prevents leak)
        _eid = eid
        _target = target
        def _cleanup_on_arena_exit(ev, s: GameState) -> None:
            if ev.data is not None and ev.data.get('card') is _target:
                s.continuous_effect_manager.remove_by_id(_eid)
                s.event_manager.unregister('leaves_arena', _cleanup_on_arena_exit)
        state.event_manager.register('leaves_arena', _cleanup_on_arena_exit)

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.10 — intimidate
# ---------------------------------------------------------------------------

@dataclass
class IntimidateEvent:
    """CR 8.5.10 — banish a random card from target's hand face-down; return at end phase.

    Player is considered intimidated even if hand was empty (CR 8.5.10a).
    Each intimidate instance tracks only its own banished card (CR 8.5.10c).
    """
    type: str = EventType.INTIMIDATE
    source_player_id: int | None = None
    target_player_id: int | None = None
    banished_card: Optional[Card] = None   # None if hand was empty (still intimidated)
    canceled: bool = False


def intimidate(state: GameState, source_player_id: int,
               target_player_id: int) -> IntimidateEvent:
    """CR 8.5.10 — intimidate target player.

    Banishes a random card from their hand face-down.
    Registers a delayed trigger to return it at beginning of end phase.
    """
    event = IntimidateEvent(
        source_player_id=source_player_id,
        target_player_id=target_player_id,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    target_player = state.players[event.target_player_id]
    hand = target_player.hand.cards

    banished_card = None
    if hand:
        # CR 8.5.10: random card from hand, banished face-down
        banished_card = random.choice(hand)
        target_player.hand.remove(banished_card)
        target_player.banished.add(banished_card, is_public=False)

    event.banished_card = banished_card

    # CR 8.5.10c: register delayed return — each instance tracks its own card
    if banished_card is not None:
        def _return_handler(ev, s: GameState) -> None:
            s.event_manager.unregister(EventType.END_PHASE_BEGINNING, _return_handler)
            p = s.players[event.target_player_id]
            # Only return if still in banished zone (CR 8.5.10c)
            if banished_card in p.banished.cards:
                p.banished.remove(banished_card)
                p.hand.add(banished_card)
                s.event_manager.emit(Event(type=EventType.INTIMIDATE_RETURN, data={
                    "target_player_id": event.target_player_id,
                    "card": banished_card.slug,
                }), s)

        state.event_manager.register(EventType.END_PHASE_BEGINNING, _return_handler)

    # CR 8.5.10a: emit intimidated event regardless of whether a card was banished
    state.event_manager.emit(Event(type=EventType.INTIMIDATE, data={
        "source_player_id": event.source_player_id,
        "target_player_id": event.target_player_id,
        #"banished_card": banished_card.slug if banished_card is not None else None, # I'm concerened that including the slug in the banish event will make tht info public
    }), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.12 — lose (asset)
# ---------------------------------------------------------------------------

@dataclass
class LoseEvent:
    type: str = EventType.LOSE
    asset_type: str = AssetType.LIFE
    amount: int = 0
    source_player_id: int | None = None
    target_player_id: int | None = None   # set when target is a player
    target_card: Optional[Card] = None    # set when target is a living object (ally)
    canceled: bool = False


def lose(state: GameState, asset_type: str, amount: int,
         source_player_id: int | None = None,
         target_player_id: int | None = None,
         target_card: Optional[Card] = None) -> "LoseEvent":
    """CR 8.5.12 — lose an asset (decrease a player's or object's asset by amount).

    Exactly one of target_player_id or target_card should be provided.
    CR 8.5.12a: losing {h} on an object without the life property fails.
    CR 8.5.12b: losing life is not considered damage.
    """
    event = LoseEvent(
        asset_type=asset_type,
        amount=amount,
        source_player_id=source_player_id,
        target_player_id=target_player_id,
        target_card=target_card,
    )

    # CR 8.5.12a: losing {h} on an object without the life property fails
    if asset_type == AssetType.LIFE and target_card is not None:
        if getattr(target_card, 'life', None) is None:
            event.canceled = True
            return event

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled or event.amount <= 0:
        return event

    pid = event.target_player_id

    # execute the loss
    if event.asset_type == AssetType.LIFE:
        if event.target_card is not None:
            event.target_card.life = max(0, (event.target_card.life or 0) - event.amount)
        elif pid is not None:
            # CR: life CAN go negative; game loss is checked separately
            state.players[pid].life -= event.amount
    elif event.asset_type == AssetType.RESOURCES and pid is not None:
        state.players[pid].resources = max(0, state.players[pid].resources - event.amount)
    elif event.asset_type == AssetType.ACTION_POINTS and pid is not None:
        state.players[pid].action_points = max(0, state.players[pid].action_points - event.amount)
    elif event.asset_type == AssetType.CHI and pid is not None:
        state.players[pid].chi = max(0, state.players[pid].chi - event.amount)

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.11 — look
# ---------------------------------------------------------------------------

@dataclass
class LookEvent:
    """CR 8.5.11 — grant one or more players visibility into a private card.

    Discrete (no until_condition): caller is responsible for revoking visibility
    after the viewing window ends (e.g. end of an effect resolution).
    Continuous (until_condition set): visibility auto-revoked when event fires.

    CR 8.5.11b: card does not become public — is_public stays False.
    CR 8.5.11c: if card is already public, look fails.
    """
    type: str = EventType.LOOK
    looker_ids: tuple = ()
    target_card: Optional[Card] = None
    source_player_id: int | None = None
    until_condition: str | None = None
    canceled: bool = False


def look(state: GameState, target_card: Card, looker_ids: tuple | list,
         source_player_id: int | None = None,
         until_condition: str | None = None) -> LookEvent:
    """CR 8.5.11 — let specified players look at a private card.

    Adds player IDs to card.known_by. If until_condition is set, removes them
    automatically when that event fires.
    """
    event = LookEvent(
        looker_ids=tuple(looker_ids),
        target_card=target_card,
        source_player_id=source_player_id,
        until_condition=until_condition,
    )

    # CR 8.5.11c: already public — look fails
    if target_card.is_public:
        event.canceled = True
        return event

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    # Grant visibility (CR 8.5.11b: card does not become public)
    for pid in event.looker_ids:
        event.target_card.known_by.add(pid)

    if event.until_condition:
        def _remove_handler(ev, s: GameState) -> None:
            s.event_manager.unregister(event.until_condition, _remove_handler)
            for pid in event.looker_ids:
                event.target_card.known_by.discard(pid)
        state.event_manager.register(event.until_condition, _remove_handler)

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.14 — put (counter)
# ---------------------------------------------------------------------------

@dataclass
class PutCounterEvent:
    type: str = EventType.PUT_COUNTER
    counter_type: str = ""
    amount: int = 1
    target_card: Optional[Card] = None
    source_player_id: int | None = None
    canceled: bool = False


def put_counter(state: GameState, counter_type: str, target_card: Card,
                amount: int = 1,
                source_player_id: int | None = None) -> PutCounterEvent:
    """CR 8.5.14 — put one or more counters of a given type onto an object.

    Counters are stored in card.counters: dict[str, int].
    amount defaults to 1; pass a larger value to put multiple in one event
    (all counters placed simultaneously as a single discrete effect).
    """
    event = PutCounterEvent(
        counter_type=counter_type,
        amount=amount,
        target_card=target_card,
        source_player_id=source_player_id,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled or event.amount <= 0 or event.target_card is None:
        return event

    card: Card = event.target_card
    card.counters[event.counter_type] = card.counters.get(event.counter_type, 0) + event.amount

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.16 — remove (counter)
# ---------------------------------------------------------------------------

@dataclass
class RemoveCounterEvent:
    type: str = EventType.REMOVE_COUNTER
    counter_type: str = ""
    amount: int = 1
    target_card: Optional[Card] = None
    source_player_id: int | None = None
    actual_removed: int = 0   # how many were actually removed (may be < amount if not enough)
    canceled: bool = False


def remove_counter(state: GameState, counter_type: str, target_card: Card,
                   amount: int = 1,
                   source_player_id: int | None = None) -> RemoveCounterEvent:
    """CR 8.5.16 — remove one or more counters of a given type from an object.

    CR 8.5.16a: when multiple identical counters exist, it is irrelevant which
    is removed — we simply decrement the count.
    CR 8.5.16b: multiple counters are removed simultaneously (single event).

    If the card has fewer counters than requested, removes as many as exist
    (caller must check event.actual_removed if the exact count matters).
    """
    event = RemoveCounterEvent(
        counter_type=counter_type,
        amount=amount,
        target_card=target_card,
        source_player_id=source_player_id,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled or event.amount <= 0 or event.target_card is None:
        return event

    card: Card = event.target_card
    current = card.counters.get(event.counter_type, 0)
    removed = min(current, event.amount)
    event.actual_removed = removed

    if removed > 0:
        new_count = current - removed
        if new_count == 0:
            card.counters.pop(event.counter_type, None)
        else:
            card.counters[event.counter_type] = new_count

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.17 — reveal
# ---------------------------------------------------------------------------

@dataclass
class RevealEvent:
    type: str = EventType.REVEAL
    target_cards: tuple = field(default_factory=tuple)   # cards revealed (CR 8.5.17e: may be N)
    source_player_id: int | None = None
    until_condition: str | None = None   # None = discrete; set = continuous
    canceled: bool = False


def reveal(state: GameState, target_cards: list | tuple,
           source_player_id: int | None = None,
           until_condition: str | None = None) -> RevealEvent:
    """CR 8.5.17 — reveal one or more private cards.

    Discrete (no until_condition): each card is made public, event emitted,
    then immediately made private again (CR 8.5.17b).
    Continuous (until_condition set): cards remain public until that event fires.
    CR 8.5.17d: if any target card is already public, the reveal for that card fails.
    CR 8.5.17c: position/zone unchanged.
    """
    # filter to only non-public cards (CR 8.5.17d per-card)
    eligible = [c for c in target_cards if not c.is_public]

    event = RevealEvent(
        target_cards=tuple(eligible),
        source_player_id=source_player_id,
        until_condition=until_condition,
    )

    # if ALL targets are already public, whole effect fails
    if not eligible:
        event.canceled = True
        return event

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    cards: tuple = event.target_cards

    # make cards public
    for card in cards:
        card.is_public = True

    state.event_manager.emit(create_emit_event(event), state)

    if event.until_condition:
        # continuous: restore privacy when condition fires
        condition: str = event.until_condition
        def _restore_handler(ev, s: GameState) -> None:
            s.event_manager.unregister(condition, _restore_handler)
            for card in cards:
                card.is_public = False
        state.event_manager.register(condition, _restore_handler)
    else:
        # discrete: immediately make private again (CR 8.5.17b)
        for card in cards:
            card.is_public = False

    return event


# ---------------------------------------------------------------------------
# CR 8.5.15 — put / return (object)
# ---------------------------------------------------------------------------

@dataclass
class PutObjectEvent:
    type: str = EventType.PUT_OBJECT
    target_card: Optional[Card] = None
    destination_zone: str = ""
    destination_player_id: int | None = None
    source_player_id: int | None = None
    is_public: bool | None = None       # None = use zone default
    position: int | None = None         # None/"bottom" = zone default (append); 0/"top" = top; N = Nth from top
    canceled: bool = False


def put_object(state: GameState, target_card: Card, destination_zone: str,
               destination_player_id: int | None = None,
               source_player_id: int | None = None,
               is_public: bool | None = None,
               position: int | str | None = None) -> PutObjectEvent:
    """CR 8.5.15 — move an object from its current zone to a specified zone.

    destination_player_id: whose zone to target; defaults to card.owner.
    is_public: override the destination zone's default visibility.
    position: where in the zone to place the card.
        None / "bottom" → zone default (append to bottom, cards[-1]).
        0 / "top"       → top of zone (cards[0]).
        N (int)         → Nth from top (0-indexed).
    Move goes through Zone.add() so zone entry rules are respected.
    """
    # Normalise position to int | None before storing in event.
    # zone.add() always appends → bottom (cards[-1]); None means "use that default".
    _pos: int | None
    if isinstance(position, str):
        _pos = 0 if position.lower() == "top" else None   # "bottom" → None
    else:
        _pos = position  # already int or None

    dest_pid = destination_player_id if destination_player_id is not None else target_card.owner

    event = PutObjectEvent(
        target_card=target_card,
        destination_zone=destination_zone,
        destination_player_id=dest_pid,
        source_player_id=source_player_id,
        is_public=is_public,
        position=_pos,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled or event.target_card is None:
        return event

    card: Card = event.target_card

    # remove from current zone (use controller, not owner — card may have changed control)
    src_zone = state.get_zone(card.zone, coo(card))
    if src_zone is not None:
        src_zone.remove(card)

    # add to destination zone (effect context so zone entry uses FAIL not CLEAR)
    dest_zone = state.get_zone(event.destination_zone, event.destination_player_id)
    if dest_zone is None:
        if src_zone is not None:
            src_zone.add(card)
        event.canceled = True
        return event

    from engine.state import ZoneEntryResult
    with effect_context():
        result = dest_zone.add(card, event.is_public)

    if result == ZoneEntryResult.FAIL:
        # destination rejected the card — return to source
        if src_zone is not None:
            src_zone.add(card)
        event.canceled = True
        return event

    # Reposition within zone if a specific index was requested.
    # zone.add() always appends (bottom = cards[-1]); pop and re-insert for any other position.
    if event.position is not None:
        target_idx = event.position
        current_idx = len(dest_zone.cards) - 1   # just appended → always the last index
        if target_idx != current_idx:
            dest_zone.cards.pop()                 # remove from bottom
            # Clamp to valid range so callers don't have to guard against over-large N.
            target_idx = max(0, min(target_idx, len(dest_zone.cards)))
            dest_zone.cards.insert(target_idx, card)

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.18 — roll (die)
# ---------------------------------------------------------------------------

@dataclass
class RollEvent:
    type: str = EventType.ROLL
    num_dice: int = 1
    faces: int = 6
    results: tuple = field(default_factory=tuple)   # one int per die (CR 8.5.18a: simultaneous)
    total: int = 0
    source_player_id: int | None = None
    canceled: bool = False


def roll(state: GameState, num_dice: int = 1, faces: int = 6,
         source_player_id: int | None = None,
         rng=None) -> RollEvent:
    """CR 8.5.18 — roll one or more dice.

    CR 8.5.18a: multiple dice are rolled simultaneously (single event).
    CR 8.5.18b: die faces are 1..faces with equal probability.

    rng: optional random.Random instance for deterministic tests.
    """
    event = RollEvent(
        num_dice=num_dice,
        faces=faces,
        source_player_id=source_player_id,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    _rng = rng if rng is not None else random
    results = tuple(_rng.randint(1, event.faces) for _ in range(event.num_dice))
    event.results = results
    event.total = sum(results)

    # "If you have rolled a 5 or 6 on a die this turn" (High Roller). One marker
    # per distinct die FACE, so a card can ask about any value. Recorded here
    # rather than at the ability that rolled, so every rolling effect feeds it.
    # Note the markers answer "did you roll an N", not "how many": a single call
    # rolling two 5s dedupes to one "roll:5", which is what the printed wording
    # asks. A count of dice rolled would need its own tally.
    _record_turn_event(state, event.source_player_id, "roll",
                       *[str(r) for r in results])

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.19 — search
# ---------------------------------------------------------------------------

@dataclass
class SearchEvent:
    type: str = EventType.SEARCH
    search_player_id: int | None = None
    source_player_id: int | None = None
    zones: tuple = field(default_factory=tuple)        # zone names searched
    eligible_cards: tuple = field(default_factory=tuple)
    chosen_card: Optional[Card] = None                 # None = search failed/declined
    failed: bool = False   # True when zone empty (CR 8.5.19d) or failed legitimately
    canceled: bool = False


def search(state: GameState,
           search_player_id: int,
           zone_names: list[str],
           selector: Callable[[list[Card], bool], Optional[Card]],
           filter_fn: Callable[[Card], bool] | None = None,
           source_player_id: int | None = None) -> SearchEvent:
    """CR 8.5.19 — search for a card in a set of zones.

    search_player_id: the player doing the searching.
    zone_names: list of zone name strings (e.g. ["deck"]) on search_player_id's side.
    filter_fn: optional predicate — only cards that pass are eligible.
               If None, all cards in the zones are eligible (CR 8.5.19c).
    selector: callback(eligible_cards, can_fail) -> Card | None.
              can_fail=True means the player is allowed to return None (fail the search).
              The engine / AI agent implements this callback.

    CR 8.5.19d: if all specified zones are empty, the effect fails immediately.
    CR 8.5.19a: filter given + no public matches → can_fail=True.
    CR 8.5.19b: filter given + public matches exist → can_fail=False.
    CR 8.5.19c: no filter + zone non-empty → can_fail=False.
    """
    # gather all cards from the specified zones
    all_cards: list[Card] = []
    for zone_name in zone_names:
        zone = state.get_zone(zone_name, search_player_id)
        if zone is not None:
            all_cards.extend(zone.cards)

    event = SearchEvent(
        search_player_id=search_player_id,
        zones=tuple(zone_names),
        source_player_id=source_player_id,
    )

    # CR 8.5.19d: empty zone — fail immediately
    if not all_cards:
        event.failed = True
        return event

    # apply filter
    eligible = [c for c in all_cards if filter_fn is None or filter_fn(c)]

    # no eligible cards after filter — fail
    if not eligible:
        event.failed = True
        return event

    event.eligible_cards = tuple(eligible)

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    # determine if the player can decline (CR 8.5.19a)
    if filter_fn is not None:
        has_public_match = any(c.is_public for c in event.eligible_cards)
        can_fail = not has_public_match   # 8.5.19a: may fail if no public match
    else:
        can_fail = False   # CR 8.5.19c: must choose when no filter

    chosen = selector(list(event.eligible_cards), can_fail)

    if chosen is None:
        # player declined (only legal when can_fail=True)
        event.failed = True
    else:
        event.chosen_card = chosen

    state.event_manager.emit(create_emit_event(event), state)

    # CR 8.5.19: shuffle the deck after any search that included it
    if 'deck' in event.zones and not event.canceled:
        shuffle(state, search_player_id, zone_name='deck')

    return event


# ---------------------------------------------------------------------------
# CR 8.5.20 — shuffle
# ---------------------------------------------------------------------------

@dataclass
class ShuffleEvent:
    type: str = EventType.SHUFFLE
    zone_name: str = "deck"
    target_player_id: int | None = None
    cards_added: tuple = field(default_factory=tuple)  # CR 8.5.20b: cards shuffled in
    source_player_id: int | None = None
    canceled: bool = False


def shuffle(state: GameState,
            target_player_id: int,
            zone_name: str = "deck",
            cards_to_add: list | None = None,
            source_player_id: int | None = None,
            rng=None) -> ShuffleEvent:
    """CR 8.5.20 — shuffle a zone (default: the player's deck).

    CR 8.5.20a: shuffling an empty zone is still considered shuffled.
    CR 8.5.20b: cards_to_add are placed into the zone first, then the zone is shuffled.
    CR 8.5.20c: if no zone specified, defaults to the player's deck.

    rng: optional random.Random for deterministic tests.
    """
    event = ShuffleEvent(
        zone_name=zone_name,
        target_player_id=target_player_id,
        cards_added=tuple(cards_to_add) if cards_to_add else (),
        source_player_id=source_player_id,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled or event.target_player_id is None:
        return event

    zone = state.get_zone(event.zone_name, event.target_player_id)
    if zone is None:
        event.canceled = True
        return event

    # CR 8.5.20b: add cards first
    for card in event.cards_added:
        zone.cards.append(card)
        card.prev_zone = card.zone
        card.zone = zone.name

    # shuffle in place (CR 8.5.20a: even empty zones are "shuffled")
    _rng = rng if rng is not None else random
    _rng.shuffle(zone.cards)
    state.players[event.target_player_id].pitch_history = [] # pitch history is erased after shuffle. this is the players known order of cards.
    state.pitch_history[event.target_player_id] = {} # pitch history is erased after shuffle. this is the opponents knowledge of the shuffler's pitch stack.


    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.21 — name
# ---------------------------------------------------------------------------

@dataclass
class NameEvent:
    type: str = EventType.NAME
    named_value: str = ""
    source_player_id: int | None = None
    canceled: bool = False


def name(state: GameState, named_value: str,
         source_player_id: int | None = None) -> NameEvent:
    """CR 8.5.21 — store a named string.

    Just records the chosen name; no state change beyond the event.
    """
    event = NameEvent(
        named_value=named_value,
        source_player_id=source_player_id,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.22 — opt
# ---------------------------------------------------------------------------

@dataclass
class OptEvent:
    type: str = EventType.OPT
    n: int = 1
    top_cards: tuple = field(default_factory=tuple)
    bottom_cards: tuple = field(default_factory=tuple)
    target_player_id: int | None = None
    source_player_id: int | None = None
    canceled: bool = False


def opt(state: GameState, n: int, target_player_id: int,
        selector: Callable[[list], tuple[list, list]],
        source_player_id: int | None = None) -> OptEvent:
    """CR 8.5.22 — look at top N cards, put any back top or bottom in any order.

    CR 8.5.22a: if deck has fewer than N cards, use all available.
    CR 8.5.22b: if deck is empty, opt fails.

    selector: Callable[[list[Card]], tuple[list[Card], list[Card]]]
        Returns (cards_to_put_on_top, cards_to_put_on_bottom).
    """
    event = OptEvent(
        n=n,
        target_player_id=target_player_id,
        source_player_id=source_player_id,
    )

    deck = state.get_zone("deck", target_player_id)

    # CR 8.5.22b: empty deck fails
    if deck is None or len(deck.cards) == 0:
        event.canceled = True
        return event

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    # CR 8.5.22a: if deck < N, use all
    actual_n = min(event.n, len(deck.cards))
    looked = deck.cards[:actual_n]  # top N cards (cards[0] = top)

    top_cards, bottom_cards = selector(list(looked))

    # Remove looked cards from deck
    for c in looked:
        deck.cards.remove(c)

    # Put top cards: top_cards[0] = topmost; insert reversed so [0] lands at deck[0]
    for c in reversed(top_cards):
        deck.cards.insert(0, c)

    # Put bottom cards: bottom_cards[0] = absolute bottom; append reversed so [0] lands at deck[-1]
    for c in reversed(bottom_cards):
        deck.cards.append(c)

    event = dataclasses.replace(event,
        top_cards=tuple(top_cards),
        bottom_cards=tuple(bottom_cards),
    )

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.23 — reload
# ---------------------------------------------------------------------------

@dataclass
class ReloadEvent:
    type: str = EventType.RELOAD
    card: Optional[Card] = None
    player_id: int | None = None
    chose_to_reload: bool = False
    source_player_id: int | None = None
    canceled: bool = False


def reload(state: GameState, card: Card, player_id: int,
           chose_to_reload: bool = False,
           source_player_id: int | None = None) -> ReloadEvent:
    """CR 8.5.23 — optionally move a card from hand to arsenal face-down.

    CR 8.5.23a: all arsenal zones must be empty for reload to succeed.
    If chose_to_reload is False, no move happens (event not canceled, just no-op).
    """
    event = ReloadEvent(
        card=card,
        player_id=player_id,
        chose_to_reload=chose_to_reload,
        source_player_id=source_player_id,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    if not event.chose_to_reload:
        # Player declined; event succeeds but nothing moves
        return event

    # CR 8.5.23a: arsenal must be empty
    arsenal = state.get_zone("arsenal", event.player_id)
    if arsenal is None or len(arsenal.cards) > 0:
        event.canceled = True
        return event

    # Move card from hand to arsenal face-down
    hand = state.get_zone("hand", event.player_id)
    if hand is not None and event.card in hand.cards:
        hand.remove(event.card)
    event.card.is_public = False
    arsenal.add(event.card, is_public=False)

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.24 — turn (face-up / face-down)
# ---------------------------------------------------------------------------

@dataclass
class TurnEvent:
    type: str = EventType.TURN
    card: Optional[Card] = None
    face_up: bool = True
    source_player_id: int | None = None
    canceled: bool = False


def turn(state: GameState, card: Card, face_up: bool,
         source_player_id: int | None = None) -> TurnEvent:
    """CR 8.5.24 — flip a card face-up (public) or face-down (private).

    CR 8.5.24a: fails if already at target visibility.
    """
    event = TurnEvent(
        card=card,
        face_up=face_up,
        source_player_id=source_player_id,
    )

    # CR 8.5.24a: already at target state — fail
    if face_up and card.is_public:
        event.canceled = True
        return event
    if not face_up and not card.is_public:
        event.canceled = True
        return event

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    event.card.is_public = event.face_up

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.26 — negate
# ---------------------------------------------------------------------------

@dataclass
class NegateEvent:
    type: str = EventType.NEGATE
    layer: object = None
    source_player_id: int | None = None
    canceled: bool = False


def negate(state: GameState, layer, source_player_id: int | None = None) -> NegateEvent:
    """CR 8.5.26 — remove a layer from the stack.

    If the layer is not on the stack, the negate is canceled.
    """
    event = NegateEvent(
        layer=layer,
        source_player_id=source_player_id,
    )

    # Check if state has a stack
    if not hasattr(state, 'stack') or not hasattr(state.stack, 'cards'):
        event.canceled = True
        return event

    # Layer must be on the stack
    if layer not in state.stack.cards:
        event.canceled = True
        return event

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event
    
    layer = event.layer
    
    # CR 8.5.26: the layer is cleared from the stack and it does not resolve
    setattr(layer, 'negated', True)

    state.stack.remove(layer)
    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.27 — repeat
# ---------------------------------------------------------------------------

@dataclass
class RepeatEvent:
    type: str = EventType.REPEAT
    source_player_id: int | None = None
    canceled: bool = False


_REPEAT_MAX_ITERATIONS = 1000


def repeat(state: GameState, process: Callable[[], bool],
           source_player_id: int | None = None,
           max_iterations: int = _REPEAT_MAX_ITERATIONS) -> RepeatEvent:
    """CR 8.5.27 — execute a callable repeatedly.

    CR 8.5.27b: stops when the instructions fail to advance the game state.
    The callable should return True if it advanced state, False otherwise.
    Also enforces a hard cap (max_iterations) to prevent infinite loops.
    """
    event = RepeatEvent(
        source_player_id=source_player_id,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    # CR 8.5.27b: repeat until process fails to advance or hard cap hit
    # process() must return a truthy value if it advanced state, falsy otherwise
    for _ in range(max_iterations):
        result = process()
        if not result:
            break

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.28 — reroll
# ---------------------------------------------------------------------------

@dataclass
class RerollEvent:
    type: str = EventType.REROLL
    original_results: tuple = field(default_factory=tuple)
    new_results: tuple = field(default_factory=tuple)
    faces: int = 6
    source_player_id: int | None = None
    canceled: bool = False


def reroll(state: GameState, dice_results: list[int], faces: int = 6,
           rng=None,
           source_player_id: int | None = None) -> RerollEvent:
    """CR 8.5.28 — reroll specified dice. Returns new results.

    CR 8.5.28: Reroll is a replacement effect that replaces a die roll result.
    The reroll event passes through apply_replacements so other replacement
    effects can interact with/modify the new results.
    """

    event = RerollEvent(
        original_results=tuple(dice_results),
        faces=faces,
        source_player_id=source_player_id,
    )

    # CR 8.5.28: reroll IS a replacement effect — pass through the pipeline
    # so other replacements can modify the new results
    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event
    
    _rng = rng if rng is not None else random
    event.new_results = tuple(_rng.randint(1, event.faces) for _ in event.original_results)

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.29 — charge
# ---------------------------------------------------------------------------

@dataclass
class ChargeEvent:
    player_id: int
    card: Card
    type: str = EventType.CHARGE
    source_player_id: int | None = None
    origin: str='hand'
    destination: str='soul'
    canceled: bool = False


def charge(state: GameState, card: Card, player_id: int,
           source_player_id: int | None = None) -> ChargeEvent:
    """CR 8.5.29 — move a card from hand to soul.

    CR 8.5.29b: only via this effect counts as 'charged'.
    """
    event = ChargeEvent(
        card=card,
        player_id=player_id,
        source_player_id=source_player_id,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event
    
    origin = state.get_zone(event.origin, event.player_id)
    if origin is not None and event.card in origin.cards:
        origin.remove(event.card)

    # Soul is a SubZoneView over hero_zone. Direct add via SubZoneView
    # sets permanent_subtype and delegates to parent. Use effect_context
    # so zone entry uses FAIL (not CLEAR/graveyard redirect).
    
    player_id = event.player_id
    player = state.players[player_id]
    card = event.card
    zone = getattr(player, event.destination)
    zone.add(card)
    if zone.name == 'soul':
        card.reset_to_base_state()
        card.is_sub_card = True
        card.top_card = player.hero
        player.hero.cards_underneath.append(card)

    # CR 8.5.29a: "the player that controls the effect is considered to have
    # charged a card". Recorded inside the canonical function and AFTER the
    # replacement/cancel checks, so a cancelled charge does not count — 8.5.29b
    # is explicit that only this effect counts as charging, so a card reaching
    # the soul any other way must not set it either.
    _record_turn_event(state, event.player_id, "charge",
                       getattr(card, "slug", None),
                       getattr(card, "types", None) or [],
                       getattr(card, "classes", None) or [],
                       getattr(card, "talents", None) or [])

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.30 — distribute
# ---------------------------------------------------------------------------

@dataclass
class DistributeEvent:
    type: str = EventType.DISTRIBUTE
    counter_type: str = ""
    distribution: list = field(default_factory=list)  # list of (Card, int) tuples
    source_player_id: int | None = None
    canceled: bool = False


def distribute(state: GameState, counter_type: str, distribution: list,
               source_player_id: int | None = None) -> DistributeEvent:
    """CR 8.5.30 — put N counters total across a set of target cards.

    distribution: list of (Card, int) tuples mapping each target card to its counter count.
    Uses put_counter internally for each target.
    """
    event = DistributeEvent(
        counter_type=counter_type,
        distribution=distribution,
        source_player_id=source_player_id,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    for target_card, amount in event.distribution:
        if amount > 0:
            put_counter(state, counter_type=event.counter_type,
                        target_card=target_card, amount=amount,
                        source_player_id=event.source_player_id)

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.31 — pay
# ---------------------------------------------------------------------------

@dataclass
class PayEvent:
    type: str = EventType.PAY
    asset_type: str = AssetType.RESOURCES
    amount: int = 0
    player_id: int | None = None
    chose_to_pay: bool = True
    source_player_id: int | None = None
    canceled: bool = False


def pay(state: GameState, asset_type: str, amount: int, player_id: int,
        chose_to_pay: bool = True,
        source_player_id: int | None = None) -> PayEvent:
    """CR 8.5.31 — pay an asset cost.

    CR 8.5.31a: optional — player can refuse (chose_to_pay=False).
    Deducts from the player's resources/life/action_points.
    """
    event = PayEvent(
        asset_type=asset_type,
        amount=amount,
        player_id=player_id,
        chose_to_pay=chose_to_pay,
        source_player_id=source_player_id,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    if not event.chose_to_pay:
        # Player declined to pay
        return event

    player = state.players[event.player_id]
    if event.asset_type == AssetType.LIFE:
        player.life -= event.amount
    elif event.asset_type == AssetType.RESOURCES:
        player.resources = max(0, player.resources - event.amount)
    elif event.asset_type == AssetType.ACTION_POINTS:
        player.action_points = max(0, player.action_points - event.amount)

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.34 — freeze
# ---------------------------------------------------------------------------

@dataclass
class FreezeEvent:
    type: str = EventType.FREEZE
    target_card: Optional[Card] = None
    until_condition: str | None = None
    source_player_id: int | None = None
    canceled: bool = False


def freeze(state: GameState, target_card: Card,
           until_condition: str | None = None,
           source_player_id: int | None = None) -> FreezeEvent:
    """CR 8.5.34 — freeze a card (cannot be played/activated).

    Tracked via card.counters['__frozen__']. Duration handled by event subscription.
    """
    event = FreezeEvent(
        target_card=target_card,
        until_condition=until_condition,
        source_player_id=source_player_id,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    event.target_card.counters["__frozen__"] = event.target_card.counters.get("__frozen__", 0) + 1

    # CR 8.5.34b: if no duration is specified, freeze until start of controller's next turn
    effective_condition = event.until_condition
    if effective_condition is None:
        effective_condition = EventType.START_OF_TURN
        controller_id = coo(event.target_card)
        _frozen_card = event.target_card

        def _unfreeze_on_turn_start(ev, s: GameState) -> None:
            # Only unfreeze if it's the frozen card's controller's turn
            if s.active_player == controller_id:
                s.event_manager.unregister(EventType.START_OF_TURN, _unfreeze_on_turn_start)
                _frozen_card.counters["__frozen__"] = max(0, _frozen_card.counters.get("__frozen__", 0) - 1)

        state.event_manager.register(EventType.START_OF_TURN, _unfreeze_on_turn_start)

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.37 — unfreeze
# ---------------------------------------------------------------------------

@dataclass
class UnfreezeEvent:
    type: str = EventType.UNFREEZE
    target_card: Optional[Card] = None
    source_player_id: int | None = None
    canceled: bool = False


def unfreeze(state: GameState, target_card: Card,
             source_player_id: int | None = None) -> UnfreezeEvent:
    """CR 8.5.37 — remove all freeze effects from a card.

    CR 8.5.37b: fails if card is not frozen.
    """
    event = UnfreezeEvent(
        target_card=target_card,
        source_player_id=source_player_id,
    )

    # CR 8.5.37b: not frozen — fail
    if target_card.counters.get("__frozen__", 0) <= 0:
        event.canceled = True
        return event

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    event.target_card.counters.pop("__frozen__", None)

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.41 — equip
# ---------------------------------------------------------------------------

@dataclass
class EquipEvent:
    type: str = EventType.EQUIP
    card: Optional[Card] = None
    zone_name: str = ""
    player_id: int | None = None
    source_player_id: int | None = None
    canceled: bool = False


def equip(state: GameState, card: Card, zone_name: str, player_id: int,
          source_player_id: int | None = None) -> EquipEvent:
    """CR 8.5.41 — put a card into an equipment/weapon zone.

    Uses put_object internally. Zone entry rules validate equipment subtype.
    """
    event = EquipEvent(
        card=card,
        zone_name=zone_name,
        player_id=player_id,
        source_player_id=source_player_id,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    result = put_object(state, target_card=event.card,
                        destination_zone=event.zone_name,
                        destination_player_id=event.player_id,
                        source_player_id=event.source_player_id)

    if result.canceled:
        event.canceled = True
        return event

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.42 — move counter
# ---------------------------------------------------------------------------

@dataclass
class MoveCounterEvent:
    type: str = EventType.MOVE_COUNTER
    counter_type: str = ""
    from_card: Optional[Card] = None
    to_card: Optional[Card] = None
    source_player_id: int | None = None
    canceled: bool = False


def move_counter(state: GameState, counter_type: str, from_card: Card,
                 to_card: Card,
                 source_player_id: int | None = None) -> MoveCounterEvent:
    """CR 8.5.42 — remove a counter from one card and put it on another.

    CR 8.5.42a: if no counter of the specified type exists on from_card, nothing happens.
    Uses remove_counter + put_counter internally.
    """
    event = MoveCounterEvent(
        counter_type=counter_type,
        from_card=from_card,
        to_card=to_card,
        source_player_id=source_player_id,
    )

    # CR 8.5.42a: no counter to move
    if from_card.counters.get(counter_type, 0) <= 0:
        event.canceled = True
        return event

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    rem = remove_counter(state, counter_type=event.counter_type,
                         target_card=event.from_card, amount=1,
                         source_player_id=event.source_player_id)

    if rem.actual_removed > 0:
        put_counter(state, counter_type=event.counter_type,
                    target_card=event.to_card, amount=1,
                    source_player_id=event.source_player_id)

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.44 — pitch
# ---------------------------------------------------------------------------

@dataclass
class PitchEvent:
    type: str = EventType.PITCH
    card: Optional[Card] = None
    player_id: int | None = None
    pitch_value: int = 0
    source_player_id: int | None = None
    canceled: bool = False


def pitch(state: GameState, card: Card, player_id: int,
          source_player_id: int | None = None) -> PitchEvent:
    """CR 8.5.44 — put card in pitch zone, gain resources equal to pitch value.

    Uses put_object to move to 'pitch' zone, then gain(resources, pitch_value).
    """
    pv = getattr(card, 'pitch', None) or getattr(card, 'raw_pitch', None) or 0

    event = PitchEvent(
        card=card,
        player_id=player_id,
        pitch_value=pv,
        source_player_id=source_player_id,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    # "if you've pitched a blue card this turn" — colour, class and talent are
    # all recorded so a card can key off whichever its text names.
    _PITCH_COLOUR = {1: "red", 2: "yellow", 3: "blue"}
    _record_turn_event(
        state, event.player_id, "pitch",
        getattr(event.card, "color", None) or _PITCH_COLOUR.get(
            getattr(event.card, "pitch", None)),
        getattr(event.card, "classes", None) or [],
        getattr(event.card, "talents", None) or [],
    )

    put_object(state, target_card=event.card, destination_zone="pitch",
               destination_player_id=event.player_id,
               source_player_id=event.source_player_id)

    if event.pitch_value > 0:
        gain(state, asset_type=AssetType.RESOURCES, amount=event.pitch_value,
             source_player_id=event.source_player_id or event.player_id, target_player_id=event.player_id)

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.45 — clash
# ---------------------------------------------------------------------------

@dataclass
class ClashEvent:
    type: str = EventType.CLASH
    player1_id: int | None = None
    player2_id: int | None = None
    card1: Optional[Card] = None
    card2: Optional[Card] = None
    power1: int | None = None
    power2: int | None = None
    winner_id: int | None = None
    source_player_id: int | None = None
    canceled: bool = False


def clash(state: GameState, player1_id: int, player2_id: int,
          source_player_id: int | None = None) -> ClashEvent:
    """CR 8.5.45 — both players reveal top deck card; highest power wins.

    CR 8.5.45b: if a player has no deck card, they lose the clash.
    CR 8.5.45c: if tied, no winner (winner_id=None).
    """
    event = ClashEvent(
        player1_id=player1_id,
        player2_id=player2_id,
        source_player_id=source_player_id,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    deck1 = state.get_zone("deck", event.player1_id)
    deck2 = state.get_zone("deck", event.player2_id)

    card1 = deck1.cards[0] if deck1 and len(deck1.cards) > 0 else None
    card2 = deck2.cards[0] if deck2 and len(deck2.cards) > 0 else None

    # Reveal the cards via reveal() so replacement effects on reveal can fire
    cards_to_reveal = [c for c in (card1, card2) if c is not None]
    if cards_to_reveal:
        reveal(state, cards_to_reveal, source_player_id=source_player_id)

    power1 = getattr(card1, 'power', None) or 0 if card1 else 0
    power2 = getattr(card2, 'power', None) or 0 if card2 else 0

    # CR 8.5.45b: no deck card = lose
    if card1 is None and card2 is not None:
        winner = event.player2_id
    elif card2 is None and card1 is not None:
        winner = event.player1_id
    elif card1 is None and card2 is None:
        winner = None
    elif power1 > power2:
        winner = event.player1_id
    elif power2 > power1:
        winner = event.player2_id
    else:
        # CR 8.5.45c: tie — no winner
        winner = None

    # Fail-clash replacement abilities: a clasher who did NOT win may have a
    # DSL REPLACEMENT ability (registered at game start) that modifies the
    # decks and re-clashes. Handlers live in card_effects.replacement_abilities.
    retry = getattr(state, "clash_fail_retry", {})
    for pid in (event.player1_id, event.player2_id):
        if pid == winner or retry.get(pid) is None:
            continue
        from engine.card_effects.replacement_abilities import REPLACEMENT_ABILITIES
        handler = REPLACEMENT_ABILITIES.get(retry[pid])
        if handler is not None and handler(state, pid, {event.player1_id: card1,
                                                        event.player2_id: card2}):
            return clash(state, event.player1_id, event.player2_id,
                         source_player_id=source_player_id)

    event = dataclasses.replace(event,
        card1=card1, card2=card2,
        power1=power1, power2=power2,
        winner_id=winner,
    )

    state.event_manager.emit(create_emit_event(event), state)

    # "When you win a clash revealing this" (Thunk, Golden Son): dispatch to the
    # winner's revealed card so its ON_CLASH_WIN_REVEALED ability can fire.
    if winner is not None:
        winner_card = card1 if winner == event.player1_id else card2
        state.event_manager.emit(Event(type='clash_resolved', data={
            'winner_id': winner,
            'winner_card': winner_card,
            'revealed': {event.player1_id: card1, event.player2_id: card2},
        }), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.47 — amp
# ---------------------------------------------------------------------------

@dataclass
class AmpEvent:
    type: str = EventType.AMP
    amount: int = 0
    player_id: int | None = None
    source_player_id: int | None = None
    canceled: bool = False


def amp(state: GameState, amount: int, player_id: int,
        source_player_id: int | None = None) -> AmpEvent:
    """CR 8.5.47 — next arcane damage this turn deals +N.

    Stored in player.class_counters['amp'].
    """
    event = AmpEvent(
        amount=amount,
        player_id=player_id,
        source_player_id=source_player_id,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    player = state.players[event.player_id]
    player.class_counters["amp"] = player.class_counters.get("amp", 0) + event.amount

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.49 — exchange
# ---------------------------------------------------------------------------

@dataclass
class ExchangeEvent:
    type: str = EventType.EXCHANGE
    card_a: Optional[Card] = None
    card_b: Optional[Card] = None
    source_player_id: int | None = None
    canceled: bool = False


def exchange(state: GameState, card_a: Card, card_b: Card,
             source_player_id: int | None = None) -> ExchangeEvent:
    """CR 8.5.49 — swap two cards' zones.

    CR 8.5.49a: simultaneous; fails if either move fails.
    """
    event = ExchangeEvent(
        card_a=card_a,
        card_b=card_b,
        source_player_id=source_player_id,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    # Record original locations
    zone_a_name = event.card_a.zone
    owner_a = event.card_a.owner
    controller_a = coo(event.card_a)
    public_a = event.card_a.is_public
    zone_b_name = event.card_b.zone
    owner_b = event.card_b.owner
    controller_b = coo(event.card_b)
    public_b = event.card_b.is_public

    # Remove both from their zones
    zone_a = state.get_zone(zone_a_name, controller_a)
    zone_b = state.get_zone(zone_b_name, controller_b)

    if zone_a is None or zone_b is None:
        event.canceled = True
        return event

    zone_a.remove(event.card_a)
    zone_b.remove(event.card_b)

    # CR 8.5.49: swap zone, visibility, AND control
    event.card_a.controller = controller_b
    event.card_b.controller = controller_a

    # Swap: put card_a in card_b's zone and vice versa
    zone_b.add(event.card_a, public_b)
    zone_a.add(event.card_b, public_a)

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.50 — mark
# ---------------------------------------------------------------------------

@dataclass
class MarkEvent:
    type: str = EventType.MARK
    target_player_id: int | None = None
    source_player_id: int | None = None
    canceled: bool = False


def mark(state: GameState, target_player_id: int,
         source_player_id: int | None = None) -> MarkEvent:
    """CR 8.5.50 — give hero the marked condition.

    Sets class_counters['marked'] = 1 on the target player.
    """
    event = MarkEvent(
        target_player_id=target_player_id,
        source_player_id=source_player_id,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    state.players[event.target_player_id].class_counters["marked"] = 1

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.55 — tap
# ---------------------------------------------------------------------------

@dataclass
class TapEvent:
    type: str = EventType.TAP
    card: Optional[Card] = None
    source_player_id: int | None = None
    canceled: bool = False


def tap(state: GameState, card: Card,
        source_player_id: int | None = None) -> TapEvent:
    """CR 8.5.55 — change untapped to tapped.

    CR 8.5.55a: fails if already tapped.
    """
    event = TapEvent(
        card=card,
        source_player_id=source_player_id,
    )

    # CR 8.5.55a: already tapped — fail
    if card.tapped:
        event.canceled = True
        return event

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    event.card.tapped = True

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.56 — untap
# ---------------------------------------------------------------------------

@dataclass
class UntapEvent:
    type: str = EventType.UNTAP
    card: Optional[Card] = None
    source_player_id: int | None = None
    canceled: bool = False


def untap(state: GameState, card: Card,
          source_player_id: int | None = None) -> UntapEvent:
    """CR 8.5.56 — change tapped to untapped.

    CR 8.5.56a: fails if already untapped.
    """
    event = UntapEvent(
        card=card,
        source_player_id=source_player_id,
    )

    # CR 8.5.56a: already untapped — fail
    if not card.tapped:
        event.canceled = True
        return event

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    event.card.tapped = False

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.57 — crowd cheers / boos
# ---------------------------------------------------------------------------

@dataclass
class CheerEvent:
    type: str = EventType.CHEER
    target_player_id: int | None = None
    source_player_id: int | None = None
    canceled: bool = False


def cheer(state: GameState, target_player_id: int,
          source_player_id: int | None = None) -> CheerEvent:
    """CR 8.5.57 — crowd cheers for a player.

    Sets class_counters['cheered_this_turn'] = 1 on the target player.
    """
    event = CheerEvent(
        target_player_id=target_player_id,
        source_player_id=source_player_id,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    state.players[event.target_player_id].class_counters["cheered_this_turn"] = 1

    state.event_manager.emit(create_emit_event(event), state)

    return event


@dataclass
class BooEvent:
    type: str = EventType.BOO
    target_player_id: int | None = None
    source_player_id: int | None = None
    canceled: bool = False


def boo(state: GameState, target_player_id: int,
        source_player_id: int | None = None) -> BooEvent:
    """CR 8.5.57 — crowd boos a player.

    Sets class_counters['booed_this_turn'] = 1 on the target player.
    """
    event = BooEvent(
        target_player_id=target_player_id,
        source_player_id=source_player_id,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    state.players[event.target_player_id].class_counters["booed_this_turn"] = 1

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.25 — become / copy
# ---------------------------------------------------------------------------

# Copyable properties: the base_* fields that define a card's modifiable printed stats.
# CR 8.5.25a: "copyable properties of a card are determined by the printed properties"
# raw_* fields are the card's immutable original print — they are NEVER changed by effects.
# base_* fields are the starting values that effects (including become/copy) can alter.
# The active name/power/etc. fields are derived from base_* + continuous effects.
_COPYABLE_FIELDS: tuple[str, ...] = (
    "base_name", "base_pitch", "base_cost", "base_x_cost", "base_power",
    "base_defense", "base_life", "base_intellect", "base_arcane", "base_color",
    "base_types", "base_text_box", "base_subtypes", "base_keywords",
    "base_functional_text", "base_type_text", "base_classes",
    "category", "raw_playable", "raw_activatable", "activation_cost",
    "abilities_and_effects", "effects",
    "talents", "shorthands", "meta", "metatypes", "traits",
    "fusions", "bonds", "flows", "specializations",
    "special_cost", "special_power", "special_defense",
    "special_life", "special_arcane",
)


@dataclass
class BecomeCopyEvent:
    type: str = EventType.BECOME_COPY
    subject_card: Optional[Card] = None    # card that becomes the copy
    reference_card: Optional[Card] = None  # card being copied
    source_player_id: int | None = None
    canceled: bool = False


def become_copy(state: GameState, subject_card: Card, reference_card: Card,
                source_player_id: int | None = None) -> BecomeCopyEvent:
    """CR 8.5.25 — subject_card becomes a copy of reference_card.

    CR 8.5.25a: only copyable (printed) properties are transferred.
    CR 8.5.25c: future changes to reference_card do not affect subject_card.
    CR 8.5.25d: if subject already IS reference, effect fails.

    Non-copyable properties (zone, owner, controller, counters, tapped,
    object_id, known_by, etc.) are preserved on the subject.
    """
    event = BecomeCopyEvent(
        subject_card=subject_card,
        reference_card=reference_card,
        source_player_id=source_player_id,
    )

    # CR 8.5.25d: already a copy of the same reference — fail
    if subject_card is reference_card:
        event.canceled = True
        return event

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled or event.subject_card is None or event.reference_card is None:
        return event

    subj: Card = event.subject_card
    ref: Card = event.reference_card

    # snapshot copyable properties from reference (CR 8.5.25c: snapshot, not live reference)
    import copy as _copy
    for field_name in _COPYABLE_FIELDS:
        if hasattr(ref, field_name):
            val = getattr(ref, field_name)
            # deep-copy mutable containers so changes to ref don't affect subj
            if isinstance(val, (list, dict, set)):
                val = _copy.deepcopy(val)
            setattr(subj, field_name, val)

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.33 — ignore
# ---------------------------------------------------------------------------

@dataclass
class IgnoreEvent:
    type: str = EventType.IGNORE
    source_player_id: int | None = None
    description: str = ""   # human-readable note on what is being ignored
    canceled: bool = False


def ignore(state: GameState, description: str = "",
           ignored_event_type: str | None = None,
           condition_fn: Callable | None = None,
           source_card: Card | None = None,
           source_player_id: int | None = None) -> IgnoreEvent:
    """CR 8.5.33 — ignore is a replacement effect.

    CR 8.5.33: Registers a replacement effect that cancels events matching
    ignored_event_type (and optional condition_fn). The replacement effect
    fires once and then removes itself.

    If ignored_event_type is None, this acts as a record-only call (for cards
    that implement their ignore logic directly in their card-effect functions).
    """
    event = IgnoreEvent(
        source_player_id=source_player_id,
        description=description,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    # CR 8.5.33: register a one-shot replacement effect that cancels the target event
    if ignored_event_type is not None:
        from engine.effects import ReplacementEffect, ReplacementType
        _source = source_card or Card(slug="__ignore_source__")

        def _ignore_condition(evt, s):
            if evt.get("type") != ignored_event_type:
                return False
            return condition_fn(evt, s) if condition_fn else True

        def _ignore_replace(evt, s):
            # Cancel the event and remove this one-shot replacement
            state.effect_manager.replacement_effects[:] = [
                r for r in state.effect_manager.replacement_effects
                if r is not _rep
            ]
            return {**evt, "canceled": True}

        _rep = ReplacementEffect(
            source_card=_source,
            replacement_type=ReplacementType.STANDARD,
            condition_fn=_ignore_condition,
            replace_fn=_ignore_replace,
        )
        state.effect_manager.replacement_effects.append(_rep)

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.35 — gain (control)
# ---------------------------------------------------------------------------

# Zones that correspond to equipment slots — CR 8.5.35a applies here
_EQUIPMENT_ZONES = {"head", "chest", "arms", "legs", "weapon", "weapon1", "weapon2"}


@dataclass
class GainControlEvent:
    type: str = EventType.GAIN_CONTROL
    target_card: Optional[Card] = None
    new_controller_id: int | None = None
    previous_controller_id: int | None = None
    source_player_id: int | None = None
    canceled: bool = False


def gain_control(state: GameState, target_card: Card, new_controller_id: int,
                 source_player_id: int | None = None) -> GainControlEvent:
    """CR 8.5.35 — new_controller_id gains control of target_card.

    The card moves to the same zone type on the new controller's side.
    CR 8.5.35a: if the card is in an equipment zone, the new controller must be
    able to equip it (zone entry rules apply); if not, the effect fails.

    card.controller is updated to new_controller_id.
    card.owner is NOT changed (ownership ≠ control).
    """
    prev_controller = target_card.controller if target_card.controller is not None else target_card.owner

    event = GainControlEvent(
        target_card=target_card,
        new_controller_id=new_controller_id,
        previous_controller_id=prev_controller,
        source_player_id=source_player_id,
    )

    # no-op if already controlled by new_controller
    if prev_controller == new_controller_id:
        event.canceled = True
        return event

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled or event.target_card is None or event.new_controller_id is None:
        return event

    card: Card = event.target_card
    zone_name = card.zone

    # locate and remove from current zone (keyed by prev_controller, not owner)
    src_zone = state.get_zone(zone_name, event.previous_controller_id)
    if src_zone is None:
        # try owner as fallback
        src_zone = state.get_zone(zone_name, card.owner)
    if src_zone is not None:
        src_zone.remove(card)

    # update controller
    card.controller = event.new_controller_id

    # CR 8.5.35a: move to same zone on new controller's side
    dest_zone = state.get_zone(zone_name, event.new_controller_id)
    if dest_zone is None:
        # zone doesn't exist for new controller — fail, restore
        card.controller = event.previous_controller_id
        if src_zone is not None:
            src_zone.add(card)
        event.canceled = True
        return event

    from engine.state import ZoneEntryResult
    with effect_context():
        result = dest_zone.add(card, card.is_public)

    if result == ZoneEntryResult.FAIL:
        # CR 8.5.35a: can't equip / zone rejected — fail, restore
        card.controller = event.previous_controller_id
        if src_zone is not None:
            src_zone.add(card)
        event.canceled = True
        return event

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.36 — transform
# ---------------------------------------------------------------------------

@dataclass
class TransformEvent:
    type: str = EventType.TRANSFORM
    objects: list = field(default_factory=list)   # card(s) transforming
    permanent: Optional[Card] = None              # the permanent they transform into
    source_player_id: int | None = None
    canceled: bool = False


def transform(state: GameState, objects: list[Card], permanent: Card,
              source_player_id: int | None = None) -> TransformEvent:
    """CR 8.5.36 — transform object(s) into a permanent by putting them under it.

    CR 8.5.36b: if permanent is not yet in play, it first becomes a permanent
    (placed in the correct arena zone), then objects are put under it.
    CR 8.5.36c: token permanent — create the token first.
    CR 8.5.36d: all objects must exist; if any is missing the effect fails.
    """
    event = TransformEvent(
        objects=list(objects),
        permanent=permanent,
        source_player_id=source_player_id,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    # CR 8.5.36d: all source objects must exist
    if not event.objects or any(o is None for o in event.objects):
        event.canceled = True
        return event

    perm: Card = event.permanent
    if perm is None:
        event.canceled = True
        return event

    # Determine controller for zone lookup
    controller_id = source_player_id or coo(perm)

    # CR 8.5.36b: if permanent is not yet in an arena zone, put it there
    perm_zone = state.get_zone(perm.zone, controller_id) if perm.zone else None
    if perm_zone is None or perm.zone not in ("permanents", "items", "allies", "auras", "layers", "hero"):
        dest_zone = state.get_zone("permanents", controller_id)
        if dest_zone is not None:
            dest_zone.add(perm)
            perm_zone = dest_zone

    if perm_zone is None:
        event.canceled = True
        return event

    # Put each object under the permanent
    for obj in event.objects:
        src_zone_name = obj.zone
        src_controller = coo(obj)
        src_zone = state.get_zone(src_zone_name, src_controller)
        if src_zone is not None:
            src_zone.remove(obj)
        success = perm_zone.add_under(obj)
        if not success:
            event.canceled = True
            return event

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.38 — attack
# ---------------------------------------------------------------------------

@dataclass
class AttackEvent:
    type: str = EventType.ATTACK
    attacking_card: Optional[Card] = None
    target_id: int | None = None   # player or permanent being attacked
    source_player_id: int | None = None
    canceled: bool = False


def attack(state: GameState, attacking_card: Card, target_id: int,
           source_player_id: int | None = None) -> AttackEvent:
    """CR 8.5.38 — generate the attack effect for an attacking card.

    This is a low-level event emitter. The full attack resolution logic lives
    in engine.py. This function exists so replacement/trigger effects on the
    attack event fire from a single callsite.
    """
    event = AttackEvent(
        attacking_card=attacking_card,
        target_id=target_id,
        source_player_id=source_player_id,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.39 — contract
# ---------------------------------------------------------------------------

@dataclass
class ContractEvent:
    type: str = EventType.CONTRACT
    player_id: int | None = None
    condition: str = ""    # human-readable contract condition text
    reward: str = ""       # human-readable reward text
    source_card_slug: str = ""
    canceled: bool = False


def contract(state: GameState, player_id: int, condition: str, reward: str,
             source_card_slug: str = "") -> ContractEvent:
    """CR 8.5.39 — give a player a contract (continuous effect).

    The contract is tracked in player.class_counters keyed by source_card_slug.
    Completion checking and reward triggers are handled by the card effect registry.
    """
    event = ContractEvent(
        player_id=player_id,
        condition=condition,
        reward=reward,
        source_card_slug=source_card_slug,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    player = state.players.get(event.player_id)
    if player is None:
        event.canceled = True
        return event

    # Record contract as a class_counter flag; card effect side handles progress
    player.class_counters[f"contract_{event.source_card_slug}"] = 1

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.40 — create (card)
# ---------------------------------------------------------------------------

@dataclass
class CreateCardEvent:
    type: str = EventType.CREATE_CARD
    slug: str = ""
    pitch: int | None = None          # optional pitch specifier
    dest_zone: str = "hand"           # zone the created card enters
    dest_player_id: int | None = None
    created_card: Optional[Card] = None   # populated after creation
    source_player_id: int | None = None
    canceled: bool = False


def create_card(state: GameState, slug: str, dest_player_id: int,
                dest_zone: str = "hand", pitch: int | None = None,
                source_player_id: int | None = None) -> CreateCardEvent:
    """CR 8.5.40 — create a card by name and put it in the specified zone.

    CR 8.5.40a: properties defined by the printed card (card database lookup).
    CR 8.5.40b: card need not be in the player's card-pool.
    """
    event = CreateCardEvent(
        slug=slug,
        pitch=pitch,
        dest_zone=dest_zone,
        dest_player_id=dest_player_id,
        source_player_id=source_player_id,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    dest_player = event.dest_player_id or 0

    # CR 8.5.40a: properties defined by the printed card (card database lookup)
    db_card = None
    if state.card_db is not None and hasattr(state.card_db, 'get'):
        db_card = state.card_db.get(event.slug)

    if db_card is not None:
        new_card = db_card
        new_card.owner = dest_player
    else:
        # Fallback when no card_db available — minimal card with Action type
        new_card = Card(slug=event.slug, owner=dest_player, raw_types=["Action"])

    event.created_card = new_card

    zone = state.get_zone(event.dest_zone, dest_player)
    if zone is not None:
        with effect_context():
            zone.add(new_card)

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.43 — awaken
# ---------------------------------------------------------------------------

@dataclass
class AwakenEvent:
    type: str = EventType.AWAKEN
    target_card: Optional[Card] = None
    source_player_id: int | None = None
    canceled: bool = False


def awaken(state: GameState, target_card: Card,
           source_player_id: int | None = None) -> AwakenEvent:
    """CR 8.5.43 — flip a double-faced card to its back face.

    CR 8.5.43a: fails if not a double-faced card, back face already active,
    or back face cannot be made active.
    Tracked via card.counters['__back_face_active__'].
    """
    event = AwakenEvent(
        target_card=target_card,
        source_player_id=source_player_id,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    card: Card = event.target_card
    if card is None:
        event.canceled = True
        return event

    # CR 8.5.43a: must be a double-faced card and not already awakened
    if not getattr(card, 'back_face_slug', None):
        event.canceled = True
        return event
    if card.counters.get('__back_face_active__'):
        event.canceled = True
        return event

    card.counters['__back_face_active__'] = 1

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.46 — wager
# ---------------------------------------------------------------------------

@dataclass
class WagerEvent:
    type: str = EventType.WAGER
    attack_card: Optional[Card] = None
    prize: str = ""            # token keyword or description of prize
    controller_id: int | None = None
    opponent_id: int | None = None
    canceled: bool = False


def wager(state: GameState, attack_card: Card, prize: str,
          controller_id: int | None = None,
          opponent_id: int | None = None) -> WagerEvent:
    """CR 8.5.46 — wager a prize on the current attack hitting.

    CR 8.5.46a: records the wager on the attack card and combat state.
    CR 8.5.46b: token prize creates the token for the winner.
    Resolution (hit/miss check) happens in the combat chain resolution.
    The wager is stored in combat.class_counters or card.counters.
    """
    event = WagerEvent(
        attack_card=attack_card,
        prize=prize,
        controller_id=controller_id,
        opponent_id=opponent_id,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    card: Card = event.attack_card
    if card is None:
        event.canceled = True
        return event

    # Store wager data on the card for resolution at end of chain link.
    # Use a dedicated wager_data dict (not counters which is dict[str, int]).
    if not hasattr(card, 'wager_data'):
        card.wager_data = {}
    card.wager_data['prize'] = event.prize
    card.wager_data['controller_id'] = event.controller_id
    card.wager_data['opponent_id'] = event.opponent_id

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.48 — transcend
# ---------------------------------------------------------------------------

@dataclass
class TranscendEvent:
    type: str = EventType.TRANSCEND
    source_card: Optional[Card] = None
    player_id: int | None = None
    canceled: bool = False


def transcend(state: GameState, source_card: Card,
              player_id: int | None = None) -> TranscendEvent:
    """CR 8.5.48 — put transcend source into owner's hand with back-face active.

    CR 8.5.48a: the player that controls the effect is considered to have transcended.
    The card moves from its current zone to the owner's hand with back-face active.
    """
    event = TranscendEvent(
        source_card=source_card,
        player_id=player_id or coo(source_card),
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    card: Card = event.source_card
    if card is None:
        event.canceled = True
        return event

    # Remove from current zone
    src_zone = state.get_zone(card.zone, coo(card))
    if src_zone is not None:
        src_zone.remove(card)

    # Put into owner's hand first (reset_to_base_state fires inside zone.add)
    hand = state.get_zone("hand", card.owner)
    if hand is not None:
        hand.add(card)

    # Activate back-face AFTER zone entry so counters aren't cleared
    card.counters['__back_face_active__'] = 1

    # CR 8.5.48a: "the player that controls the effect is considered to have
    # transcended". 13 cards ask "if you've transcended this turn" and each had
    # invented its own flag (TRANSCENDED / TRANSCEDED / TRANSCEDED_THIS_TURN —
    # two of them misspelled, so they could not even collide into working).
    _record_turn_event(state, event.player_id, "transcend")

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.51 — retrieve
# ---------------------------------------------------------------------------

@dataclass
class RetrieveEvent:
    type: str = EventType.RETRIEVE
    card: Optional[Card] = None
    player_id: int | None = None
    chose_to_pay: bool = True
    cost_paid: bool = False
    canceled: bool = False


def retrieve(state: GameState, card: Card, player_id: int,
             chose_to_pay: bool = True) -> RetrieveEvent:
    """CR 8.5.51 — pay {r} to equip a card from discard/banished.

    CR 8.5.51a: card must exist and be equippable; if not, effect fails.
    CR 8.5.51a: optional — player may decline (chose_to_pay=False), no equip occurs.
    The 1r cost is deducted from the player's resources.
    """
    event = RetrieveEvent(
        card=card,
        player_id=player_id,
        chose_to_pay=chose_to_pay,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    if not event.chose_to_pay:
        # Player declined; effect succeeds but no equip occurs (CR 8.5.51a: "may pay")
        return event

    player = state.players.get(event.player_id)
    if player is None or event.card is None:
        event.canceled = True
        return event

    # CR 8.5.51a: card must be equippable and player must have 1r
    if player.resources < 1:
        event.canceled = True
        return event

    # Determine equipment zone from card subtypes
    subtypes = getattr(event.card, 'raw_subtypes', []) or getattr(event.card, 'subtypes', [])
    zone_map = {
        "Head": "head", "Chest": "chest", "Arms": "arms", "Legs": "legs",
        "1H": "weapon", "2H": "weapon", "Off-Hand": "weapon",
    }
    equip_zone_name = next((zone_map[s] for s in subtypes if s in zone_map), None)
    if equip_zone_name is None:
        event.canceled = True
        return event

    equip_zone = state.get_zone(equip_zone_name, event.player_id)
    if equip_zone is None:
        event.canceled = True
        return event

    # Remove from source zone
    src_zone = state.get_zone(event.card.zone, event.player_id)
    if src_zone is not None:
        src_zone.remove(event.card)

    from engine.state import ZoneEntryResult
    with effect_context():
        result = equip_zone.add(event.card)

    if result == ZoneEntryResult.FAIL:
        # Can't equip — restore and fail
        if src_zone is not None:
            src_zone.add(event.card)
        event.canceled = True
        return event

    player.resources -= 1
    event.cost_paid = True

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.52 — return to the brood
# ---------------------------------------------------------------------------

@dataclass
class ReturnToTheBroodEvent:
    type: str = EventType.RETURN_TO_THE_BROOD
    player_id: int | None = None
    source_player_id: int | None = None
    canceled: bool = False


def return_to_the_brood(state: GameState, player_id: int,
                        source_player_id: int | None = None) -> ReturnToTheBroodEvent:
    """CR 8.5.52 — existing become/copy effects on the player's hero cease to exist.

    All ContinuousEffects with type 'become_copy' targeting the player's hero
    are removed from the effect manager.
    """
    event = ReturnToTheBroodEvent(
        player_id=player_id,
        source_player_id=source_player_id,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    player = state.players.get(event.player_id)
    if player is None:
        event.canceled = True
        return event

    # Remove all become_copy continuous effects that apply to this player's hero
    if hasattr(state.effect_manager, 'continuous_effects'):
        state.effect_manager.continuous_effects = [
            e for e in state.effect_manager.continuous_effects
            if not (getattr(e, 'effect_type', None) == 'become_copy'
                    and getattr(e, 'target_player_id', None) == event.player_id)
        ]

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.53 — give
# ---------------------------------------------------------------------------

@dataclass
class GiveEvent:
    type: str = EventType.GIVE
    target_card: Optional[Card] = None
    new_controller_id: int | None = None
    previous_controller_id: int | None = None
    source_player_id: int | None = None
    canceled: bool = False


def give(state: GameState, target_card: Card, new_controller_id: int,
         source_player_id: int | None = None) -> GiveEvent:
    """CR 8.5.53 — give an object to a player (source player gives it away).

    CR 8.5.53b: if equipped, the new controller equips it; fails if they can't.
    Mechanically identical to gain_control — delegates to gain_control().
    """
    prev_controller = target_card.controller if target_card.controller is not None else target_card.owner

    event = GiveEvent(
        target_card=target_card,
        new_controller_id=new_controller_id,
        previous_controller_id=prev_controller,
        source_player_id=source_player_id,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    # Delegate zone move to gain_control
    gc_event = gain_control(state, event.target_card, event.new_controller_id, event.source_player_id)
    if gc_event.canceled:
        event.canceled = True
        return event

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.54 — steal
# ---------------------------------------------------------------------------

@dataclass
class StealEvent:
    type: str = EventType.STEAL
    target_card: Optional[Card] = None
    new_controller_id: int | None = None
    previous_controller_id: int | None = None
    source_player_id: int | None = None
    canceled: bool = False


def steal(state: GameState, target_card: Card, new_controller_id: int,
          source_player_id: int | None = None) -> StealEvent:
    """CR 8.5.54 — steal an object (stealing player gains control).

    CR 8.5.54b: if equipped, new controller must be able to equip it.
    Mechanically identical to gain_control — delegates to gain_control().
    """
    prev_controller = target_card.controller if target_card.controller is not None else target_card.owner

    event = StealEvent(
        target_card=target_card,
        new_controller_id=new_controller_id,
        previous_controller_id=prev_controller,
        source_player_id=source_player_id,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    # Delegate zone move to gain_control
    gc_event = gain_control(state, event.target_card, event.new_controller_id, event.source_player_id)
    if gc_event.canceled:
        event.canceled = True
        return event

    state.event_manager.emit(create_emit_event(event), state)

    return event


# ---------------------------------------------------------------------------
# CR 8.5.32 — add (defend)
# ---------------------------------------------------------------------------

@dataclass
class AddDefendEvent:
    type: str = EventType.ADD_DEFEND
    card: Optional[Card] = None
    chain_link: int | None = None       # which chain link (None = current)
    source_player_id: int | None = None
    canceled: bool = False


def add_defend(state: GameState, card: Card,
               chain_link: int | None = None,
               source_player_id: int | None = None) -> AddDefendEvent:
    """CR 8.5.32 — add a card to the current chain link as a defender.

    CR 8.5.32a: if an effect prevents the card from defending on the specified
    chain link, the defend effect fails and the card is not moved.

    The card is removed from its current zone (typically hand) and added to
    combat.defending_cards. Defense value is credited to combat.total_defense.
    """
    event = AddDefendEvent(
        card=card,
        chain_link=chain_link,
        source_player_id=source_player_id,
    )

    event_dict = vars(event).copy()
    event_dict = state.effect_manager.apply_replacements(event_dict, state)
    event = dataclasses.replace(event, **{k: v for k, v in event_dict.items() if k in vars(event)})

    if event.canceled:
        return event

    combat = state.combat
    if combat is None:
        event.canceled = True
        return event

    c: Card = event.card
    if c is None:
        event.canceled = True
        return event

    # CR 8.5.32a: replacement effects may have canceled; also check combat is open
    # Remove from source zone (usually hand of defending player)
    defender_id = 3 - combat.attacker_id
    src_zone = state.get_zone(c.zone, defender_id)
    if src_zone is None:
        src_zone = state.get_zone(c.zone, coo(c))

    in_hand = c in (state.players[defender_id].hand.cards if defender_id in state.players else [])
    if src_zone is not None and c in src_zone.cards:
        src_zone.remove(c)

    # Track hand card usage for Dominate / Reprise
    if in_hand:
        combat.defender_used_hand_card = True

    # CR 1.3.1b: a defending card enters the combat chain (arena) under the
    # control of the defender who added it.
    c.controller = defender_id
    # Add to defending cards and credit defense value
    combat.defending_cards.append(c)
    defense_val = c.defense or 0
    combat.total_defense += defense_val
    if c.is_equipment:
        combat.defending_equipment_defense += defense_val

    state.event_manager.emit(create_emit_event(event), state)

    return event
