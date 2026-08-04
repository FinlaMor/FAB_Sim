"""Game recording hooks — one place to observe everything that happens in a game.

Attach any number of GameRecorder instances to a GameState (via
``new_game(..., recorders=[...])`` or ``recorder.attach(state, rec)``) and the
engine notifies them at every observable moment:

- ``on_game_start(state)``        — after setup, before the first turn
- ``on_event(state, event)``      — EVERY EventManager event (draw, hit, boo, …)
- ``on_decision(state, player_id, options, chosen, context)``
                                  — EVERY agent invocation: the full list of
                                    options presented to the model AND the
                                    choice it made (main actions, defend
                                    declarations, pitch ordering, _ask_player
                                    sub-decisions — everything)
- ``on_action_applied(state, action)`` — after play.apply_action mutates state
- ``on_step_change(state, old, new)``  — every Step transition
- ``on_layer_resolved(state, entry)``  — after each stack layer resolves
- ``on_game_end(state)``          — when the game finishes

``snapshot_state(state)`` serializes the complete game state to a JSON-able
dict at any moment (all zones, stats, combat, stack, chain links).

Built-in recorders:
- ``MemoryRecorder`` — keeps structured records in a list (tests, IQL feature
  extraction, debugging in a REPL)
- ``JsonlRecorder``  — streams every record as a JSON line to a file
  (troubleshooting a full game after the fact)

For IQL data collection, subclass GameRecorder and implement ``on_decision``
(state features + options + chosen index) and ``on_game_end`` (reward).

Hooks must never break a game: every notification site swallows recorder
exceptions.
"""
from __future__ import annotations

import json
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from engine.state import GameState


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _slug(obj: Any) -> Any:
    """Card-like object → slug; everything else unchanged."""
    return getattr(obj, "slug", obj)


def json_safe(obj: Any, _depth: int = 0) -> Any:
    """Best-effort conversion of any engine object into JSON-able data."""
    if _depth > 6:
        return str(obj)
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if hasattr(obj, "slug"):
        return obj.slug
    if isinstance(obj, dict):
        return {str(k): json_safe(v, _depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [json_safe(v, _depth + 1) for v in obj]
    if hasattr(obj, "value") and obj.__class__.__module__ == "enum":
        return obj.value
    to_dict = getattr(obj, "to_dict", None)
    if callable(to_dict):
        try:
            return json_safe(to_dict(), _depth + 1)
        except Exception:
            return str(obj)
    return str(obj)


def serialize_action(action: Any) -> dict:
    """Serialize an engine Action (or any option object) to a compact dict."""
    if action is None:
        return {"type": None}
    atype = getattr(action, "type", None)
    out: dict = {"type": getattr(atype, "value", str(atype)) if atype is not None else None}
    for attr in ("player_id", "from_arsenal", "meld_side", "choose_index",
                 "is_attack_proxy", "played_as_instant"):
        val = getattr(action, attr, None)
        if val is not None:
            out[attr] = json_safe(val)
    card = getattr(action, "card", None)
    if card is not None:
        out["card"] = _slug(card)
    card_list = getattr(action, "card_list", None)
    if card_list:
        out["card_list"] = [_slug(c) for c in card_list]
    target = getattr(action, "target", None)
    if target is not None:
        out["target"] = json_safe(target)
    targets = getattr(action, "targets", None)
    if targets:
        out["targets"] = [json_safe(t) for t in targets]
    pitch = getattr(action, "pitch_cards", None) or getattr(action, "pitched_cards", None)
    if pitch:
        out["pitch"] = [_slug(c) for c in pitch]
    modes = getattr(action, "modes_selected", None)
    if modes:
        out["modes"] = [json_safe(m) for m in modes]
    return out


def serialize_option(option: Any) -> Any:
    """Serialize one option presented to an agent (Action, Card, or scalar)."""
    if hasattr(option, "type") and hasattr(option, "card"):
        return serialize_action(option)
    return json_safe(option)


def serialize_event(event: Any) -> dict:
    return {
        "type": getattr(event, "type", str(event)),
        "card": json_safe(getattr(event, "card", None)),
        "target": json_safe(getattr(event, "target", None)),
        "data": json_safe(getattr(event, "data", None)),
    }


def _counters_by_slug(player) -> dict:
    """Aggregate a player's counters into {slug: {counter_type: count}}.

    player.counters is keyed by (slug, zone, counter_type). Sums across zones
    and drops entries that net to zero."""
    out: dict = {}
    for key, count in (getattr(player, "counters", None) or {}).items():
        if not count:
            continue
        try:
            slug, _zone, ctype = key
        except (ValueError, TypeError):
            continue
        bucket = out.setdefault(str(slug), {})
        bucket[str(ctype)] = bucket.get(str(ctype), 0) + count
    return {s: {t: n for t, n in types.items() if n} for s, types in out.items()
            if any(types.values())}


def snapshot_state(state: "GameState") -> dict:
    """Full JSON-able snapshot of a GameState (all zones, stats, combat, stack)."""
    def zone_slugs(zone) -> list:
        return [c.slug for c in zone.cards]

    players = {}
    for pid, p in state.players.items():
        # items / auras / allies / tokens are typed views over the permanent
        # zone. List them separately, and give "permanents" only the cards NOT
        # in a typed view so an aura/item token isn't shown twice.
        typed_ids = {id(c) for view in (p.items, p.auras, p.allies, p.tokens)
                     for c in view.cards}
        players[pid] = {
            "hero": getattr(p.hero, "slug", None),
            "life": getattr(p, "health", None),
            "resources": getattr(p, "resources", 0),
            "chi": getattr(p, "chi", 0),
            "action_points": getattr(p, "action_points", 0),
            "intellect": getattr(p, "intellect", None),
            "hand": zone_slugs(p.hand),
            "deck_count": len(p.deck.cards),
            # Reviled placeholders start here (CR 4.1.6); recording it lets a
            # conservation audit track cards that begin outside deck/hand.
            "inventory": zone_slugs(p.inventory),
            "graveyard": zone_slugs(p.graveyard),
            "pitch": zone_slugs(p.pitch),
            "arsenal": zone_slugs(p.arsenal),
            "banished": zone_slugs(p.banished),
            "permanents": [c.slug for c in p.permanents.cards if id(c) not in typed_ids],
            "items": zone_slugs(p.items),
            "auras": zone_slugs(p.auras),
            "allies": zone_slugs(p.allies),
            "tokens": zone_slugs(p.tokens),
            "equipment": {slot: zone_slugs(getattr(p, slot))
                          for slot in ("head", "chest", "arms", "legs",
                                       "weapon1", "weapon2")},
            "current_turn_effects": list(getattr(p, "current_turn_effects", []) or []),
            "class_counters": json_safe(getattr(p, "class_counters", {}) or {}),
            # Counters on this player's cards, keyed by slug -> {type: count}
            # (e.g. Fyendal's Spring Tunic energy counters). Aggregated across
            # zones; zero/negative totals dropped.
            "counters": _counters_by_slug(p),
        }

    combat = None
    if state.combat is not None:
        try:
            combat = json_safe(state.combat.to_dict())
        except Exception:
            c = state.combat
            combat = {
                "attacker_id": c.attacker_id,
                "attack_card": _slug(getattr(c, "attack_card", None)),
                "attack_power": getattr(c, "attack_power", None),
                "total_defense": getattr(c, "total_defense", None),
                "defending": [_slug(d) for d in (c.defending_cards or [])],
                "keywords": list(getattr(c, "keywords", []) or []),
            }

    return {
        "turn_number": state.turn_number,
        "individual_turns": state.individual_turns,
        "step": getattr(state.step, "value", str(state.step)),
        "active_player": state.active_player,
        "priority_player": state.priority_player,
        "done": state.done,
        "winner": state.winner,
        "players": players,
        "combat": combat,
        "stack": [c.slug for c in state.stack.cards],
        "stack_entries": [json_safe(e.to_dict()) for e in state.stack_entries],
        "chain_links": [json_safe(cl.to_dict()) for cl in state.chain_links],
        "events_this_turn": sorted(state.events_this_turn),
    }


# ---------------------------------------------------------------------------
# Recorder interface
# ---------------------------------------------------------------------------

class GameRecorder:
    """Base class — override any subset of hooks. All hooks are no-ops here."""

    def on_game_start(self, state: "GameState") -> None: ...
    def on_event(self, state: "GameState", event) -> None: ...
    def on_decision(self, state: "GameState", player_id: int,
                    options: list, chosen, context) -> None: ...
    def on_action_applied(self, state: "GameState", action) -> None: ...
    def on_step_change(self, state: "GameState", old, new) -> None: ...
    def on_layer_resolved(self, state: "GameState", entry) -> None: ...
    def on_game_end(self, state: "GameState") -> None: ...


def notify(state: "GameState", hook: str, *args) -> None:
    """Call one hook on every attached recorder; recorder errors never
    propagate into the game."""
    for rec in getattr(state, "recorders", ()) or ():
        try:
            getattr(rec, hook)(state, *args)
        except Exception:  # noqa: BLE001 — observability must not break games
            pass


# ---------------------------------------------------------------------------
# Agent wrapping — captures EVERY decision (options + choice + context)
# ---------------------------------------------------------------------------

class _RecordingAgent:
    """Transparent proxy around a player agent. Notifies recorders with the
    exact options list presented to the model and the option it chose."""

    def __init__(self, player_id: int, inner):
        self._player_id = player_id
        self._inner = inner

    def __getattr__(self, name):  # pass through agent attributes (seed, model, …)
        return getattr(self._inner, name)

    def __call__(self, state, options, *args, **kwargs):
        chosen = self._inner(state, options, *args, **kwargs)
        context = args[0] if args else kwargs.get("context")
        notify(state, "on_decision", self._player_id, options, chosen, context)
        return chosen


def attach(state: "GameState", recorder: GameRecorder) -> GameRecorder:
    """Attach a recorder to a game state (idempotent agent wrapping)."""
    if not hasattr(state, "recorders") or state.recorders is None:
        state.recorders = []
    state.recorders.append(recorder)
    for pid, agent in list(state.player_agents.items()):
        if not isinstance(agent, _RecordingAgent):
            state.player_agents[pid] = _RecordingAgent(pid, agent)
    return recorder


def detach(state: "GameState", recorder: GameRecorder) -> None:
    if getattr(state, "recorders", None) and recorder in state.recorders:
        state.recorders.remove(recorder)


# ---------------------------------------------------------------------------
# Built-in recorders
# ---------------------------------------------------------------------------

class MemoryRecorder(GameRecorder):
    """Keeps every record as a (kind, payload) dict in ``self.records``.

    ``snapshot_on`` (set of hook kinds, e.g. {"decision"}) additionally embeds
    a full state snapshot into those records.
    """

    def __init__(self, snapshot_on: Optional[set] = None):
        self.records: list[dict] = []
        self.snapshot_on = snapshot_on or set()

    def _add(self, state, kind: str, payload: dict) -> None:
        rec = {"kind": kind,
               "turn": state.turn_number,
               "step": getattr(state.step, "value", str(state.step)),
               **payload}
        if kind in self.snapshot_on:
            rec["snapshot"] = snapshot_state(state)
        self.records.append(rec)

    def of_kind(self, kind: str) -> list[dict]:
        return [r for r in self.records if r["kind"] == kind]

    def on_game_start(self, state):
        self._add(state, "game_start", {"snapshot": snapshot_state(state)})

    def on_event(self, state, event):
        self._add(state, "event", {"event": serialize_event(event)})

    def on_decision(self, state, player_id, options, chosen, context):
        opts = [serialize_option(o) for o in options]
        chosen_ser = serialize_option(chosen)
        try:
            chosen_idx = next(i for i, o in enumerate(options) if o is chosen)
        except StopIteration:
            chosen_idx = None
        self._add(state, "decision", {
            "player_id": player_id,
            "context": json_safe(context),
            "options": opts,
            "chosen": chosen_ser,
            "chosen_index": chosen_idx,
            "legal_actions_count": len(options),
        })

    def on_action_applied(self, state, action):
        self._add(state, "action_applied", {"action": serialize_action(action)})

    def on_step_change(self, state, old, new):
        self._add(state, "step_change", {
            "from": getattr(old, "value", str(old)),
            "to": getattr(new, "value", str(new)),
        })

    def on_layer_resolved(self, state, entry):
        self._add(state, "layer_resolved", {
            "layer_type": getattr(entry, "layer_type", None),
            "card": _slug(getattr(entry, "card", None)),
            "player_id": getattr(entry, "player_id", None),
        })

    def on_game_end(self, state):
        self._add(state, "game_end", {
            "winner": state.winner,
            "individual_turns": state.individual_turns,
            # True when the game stopped because it reached the turn cap rather
            # than a decisive result; transcript audits use this to avoid flagging
            # a capped game's winner-vs-live-loser as an invariant violation.
            "ended_on_turn_cap": state.turn_number >= state.max_turns,
            "snapshot": snapshot_state(state),
        })


class JsonlRecorder(MemoryRecorder):
    """Streams every record to ``path`` as one JSON object per line."""

    def __init__(self, path: str, snapshot_on: Optional[set] = None):
        super().__init__(snapshot_on=snapshot_on)
        self.path = path
        self._fh = open(path, "w", encoding="utf-8")

    def _add(self, state, kind, payload):
        super()._add(state, kind, payload)
        rec = self.records[-1]
        self._fh.write(json.dumps(rec, default=str) + "\n")
        if kind == "game_end":
            self.close()
        else:
            self._fh.flush()

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.close()
