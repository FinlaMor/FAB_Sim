"""Run a seeded game with an embedder middle-man tap.

This script does two things at decision time:
1. Pass the live engine state and each legal action through embedders (model-like path)
2. Record the exact embedder inputs (state/action fields actually consumed)

It is designed to answer fidelity questions by logging what the model path really sees.

Usage:
    C:/Users/Joseph/Desktop/FAB_Sim/.venv/Scripts/python.exe tests/test_seeded_game_embedder_middleman.py
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import sys
import time
from dataclasses import is_dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import torch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DECKS_DIR, SLUG_INDEX_PATH
from data_collection.replay_db import ReplayDB
from engine.actions import Action
from engine.card import CardDB
from engine.engine import new_game
from engine.state import GameState
from encoder.action_embedder import ActionEmbedder, action_to_features
from encoder.card_embedder import SlugVocab
from encoder.gamestate_embedder import GameStateEmbedder, gamestate_to_features


SEED = 42
ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data_collection" / "embedder_middleman_seed42"
TAP_JSONL_PATH = OUT_DIR / "embedder_tap_decisions.jsonl"
SUMMARY_JSON_PATH = OUT_DIR / "embedder_tap_summary.json"
REPLAY_DB_PATH = OUT_DIR / "seeded_model_like_replay.db"


def _enum_to_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    return value


def _json_safe(value: Any) -> Any:
    """Recursively convert objects into JSON-safe values."""
    value = _enum_to_value(value)

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]

    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if isinstance(k, tuple):
                key = "|".join(str(x) for x in k)
            else:
                key = str(k)
            out[key] = _json_safe(v)
        return out

    if hasattr(value, "snapshot_state"):
        return _json_safe(value.snapshot_state())

    if is_dataclass(value):
        return _json_safe(value.__dict__)

    if callable(value):
        return f"<callable:{getattr(value, '__name__', type(value).__name__)}>"

    return str(value)


def _card_snapshot(card: Any) -> Optional[dict]:
    """Capture card identity/state for logs."""
    if card is None:
        return None

    if isinstance(card, str):
        return {"slug": card}

    if hasattr(card, "snapshot_state"):
        snap = card.snapshot_state()
        return {
            "object_id": snap.get("object_id"),
            "slug": snap.get("slug"),
            "name": snap.get("name"),
            "zone": snap.get("zone"),
            "owner": snap.get("owner"),
            "controller": snap.get("controller"),
            "tapped": snap.get("tapped"),
            "exhausted": snap.get("exhausted"),
            "is_public": snap.get("is_public"),
            "power": snap.get("power"),
            "defense": snap.get("defense"),
            "keywords": snap.get("keywords"),
        }

    return {"repr": str(card)}


def _zone_cards(zone) -> list[dict]:
    return [_card_snapshot(c) for c in getattr(zone, "cards", [])]


def serialise_action_for_embedder(action: Action) -> dict:
    """Capture all Action fields consumed by ActionEmbedder."""
    return {
        "type": action.type.value,
        "player_id": action.player_id,
        "card": _card_snapshot(action.card),
        "card_idx": action.card_idx,
        "pitch_cards": [_card_snapshot(c) for c in (action.pitch_cards or [])],
        "from_arsenal": action.from_arsenal,
        "slot": action.slot,
        "card_list": [_card_snapshot(c) for c in (action.card_list or [])],
        "target": _card_snapshot(action.target),
        "targets": [_card_snapshot(t) for t in (action.targets or [])],
        "attack_source": _card_snapshot(action.attack_source),
        "is_attack_proxy": action.is_attack_proxy,
        "is_attack_layer": action.is_attack_layer,
        "phase": action.phase,
        "step": action.step.value if getattr(action, "step", None) else None,
        "chain_link_number": action.chain_link_number,
        "priority_player": action.priority_player,
        "action_points_available": action.action_points_available,
        "resources_available": action.resources_available,
        "action_cost": action.action_cost,
        "resource_cost": action.resource_cost,
        "has_go_again": action.has_go_again,
        "is_instant_speed": action.is_instant_speed,
        "is_action_speed": action.is_action_speed,
        "played_as_instant": action.played_as_instant,
        "modes_selected": list(action.modes_selected) if action.modes_selected else [],
        "x_value_declared": action.x_value_declared,
        "is_melded": action.is_melded,
        "meld_side": getattr(action, "meld_side", None),
        "alternative_cost_used": action.alternative_cost_used,
        "debug_features": action_to_features(action),
    }


def _slug_or_passthrough(value: Any) -> Any:
    """Return card.slug when value is a Card-like object, else value unchanged."""
    if value is None:
        return None
    if hasattr(value, "slug"):
        return value.slug
    return value


def _normalise_action_for_embedder(action: Action) -> Action:
    """Create an embedder-safe Action copy (slug lists for pitch/targets)."""
    pitch_cards = [_slug_or_passthrough(c) for c in (action.pitch_cards or [])]
    targets = [_slug_or_passthrough(t) for t in (action.targets or [])]
    return replace(action, pitch_cards=pitch_cards, targets=targets)


def _serialise_player_for_embedder(player) -> dict:
    equipment_zones = [
        ("head", player.head),
        ("chest", player.chest),
        ("arms", player.arms),
        ("legs", player.legs),
        ("weapon1", player.weapon1),
        ("weapon2", player.weapon2),
    ]

    equipment = {}
    for zone_name, zone in equipment_zones:
        card = zone.cards[0] if zone.cards else None
        equipment[zone_name] = {
            "card": _card_snapshot(card),
            "exhausted": bool(card.exhausted) if card else False,
            "tapped": bool(card.tapped) if card else False,
        }

    counters = []
    for key, count in player.counters.items():
        slug, zone, counter_type = key
        counters.append(
            {
                "slug": slug,
                "zone": zone,
                "counter_type": counter_type,
                "count": count,
            }
        )

    permanents = (
        _zone_cards(player.items)
        + _zone_cards(player.auras)
        + _zone_cards(player.allies)
        + _zone_cards(player.soul)
        + _zone_cards(player.tokens)
    )

    zone_sizes = {
        "hand": len(player.hand),
        "deck": len(player.deck),
        "graveyard": len(player.graveyard),
        "arsenal": len(player.arsenal),
        "banished": len(player.banished),
        "pitch": len(player.pitch),
        "inventory": len(player.inventory),
    }

    return {
        "player_id": player.player_id,
        "hero": _card_snapshot(player.hero),
        "health": player.health,
        "intellect": player.intellect,
        "resources": player.resources,
        "action_points": player.action_points,
        "weapon_exhausted": player.weapon_exhausted,
        "hero_power_exhausted": player.hero_power_exhausted,
        "arsenal_face_up": player.arsenal_face_up,
        "marked": bool(getattr(player, "marked", False)),
        "zone_sizes": zone_sizes,
        "counters": counters,
        "equipment": equipment,
        "permanents": permanents,
    }


def _serialise_combat_for_embedder(combat) -> Optional[dict]:
    if combat is None:
        return None

    attack_target = getattr(combat, "attack_target", None)
    attack_target_id = attack_target.player_id if hasattr(attack_target, "player_id") else None

    return {
        "attacker_id": combat.attacker_id,
        "attack_target_player_id": attack_target_id,
        "link_id": combat.link_id,
        "attack_power": combat.attack_power,
        "base_attack_power": combat.base_attack_power,
        "from_weapon": combat.from_weapon,
        "total_defense": combat.total_defense,
        "defending_equipment_defense": combat.defending_equipment_defense,
        "defender_used_hand_card": combat.defender_used_hand_card,
        "no_defense_reactions": combat.no_defense_reactions,
        "defending_declared": combat.defending_declared,
        "keywords": list(combat.keywords),
        "attack_card": _card_snapshot(combat.attack_card),
        "attack_source": _card_snapshot(getattr(combat, "attack_source", None)),
        "defending_cards": [_card_snapshot(c) for c in combat.defending_cards],
        "defending_equipment_zones": list(combat.defending_equipment_zones),
    }


def _serialise_effect_manager(effect_manager) -> dict:
    if effect_manager is None:
        return {"continuous_effects": [], "replacement_effects": []}

    continuous_effects = []
    for eff in getattr(effect_manager, "continuous_effects", []) or []:
        continuous_effects.append(
            {
                "source_card": _card_snapshot(getattr(eff, "source_card", None)),
                "source_type": _enum_to_value(getattr(eff, "source_type", None)),
                "stage": getattr(eff, "stage", None),
                "substage": getattr(eff, "substage", None),
                "mod_type": _enum_to_value(getattr(eff, "mod_type", None)),
                "target_property": getattr(eff, "target_property", None),
                "value": getattr(eff, "value", None),
                "duration": getattr(eff, "duration", None),
                "timestamp": getattr(eff, "timestamp", None),
                "consumed": bool(getattr(eff, "consumed", False)),
                "owner_id": getattr(eff, "owner_id", None),
            }
        )

    replacement_effects = []
    for eff in getattr(effect_manager, "replacement_effects", []) or []:
        replacement_effects.append(
            {
                "source_card": _card_snapshot(getattr(eff, "source_card", None)),
                "replacement_type": _enum_to_value(getattr(eff, "replacement_type", None)),
                "owner_id": getattr(eff, "owner_id", None),
                "consumed": bool(getattr(eff, "consumed", False)),
                "prevention_amount": getattr(eff, "prevention_amount", None),
                "is_shielding": bool(getattr(eff, "is_shielding", False)),
            }
        )

    return {
        "continuous_effects": continuous_effects,
        "replacement_effects": replacement_effects,
    }


def serialise_state_for_embedder(state: GameState) -> dict:
    """Capture all GameState fields consumed by GameStateEmbedder."""
    stack_entries = []
    for entry in getattr(state, "stack_entries", []) or []:
        stack_entries.append(
            {
                "player_id": entry.player_id,
                "card": _card_snapshot(entry.card),
                "layer_type": entry.layer_type,
                "layer_position": entry.layer_position,
                "from_arsenal": entry.from_arsenal,
                "declared_modes": list(entry.declared_modes),
                "declared_targets": list(entry.declared_targets),
                "declared_x": entry.declared_x,
                "is_triggered": entry.is_triggered,
                "trigger_event": entry.trigger_event,
            }
        )

    chain_links = []
    for link in getattr(state, "chain_links", []) or []:
        chain_links.append(
            {
                "chainlink_id": getattr(link, "chainlink_id", None),
                "attacker_id": getattr(link, "attacker_id", None),
                "attack_slug": getattr(link, "attack_slug", None),
                "attack_power": getattr(link, "attack_power", None),
                "net_damage": getattr(link, "net_damage", None),
                "hit": getattr(link, "hit", None),
            }
        )

    out = {
        "turn_number": state.turn_number,
        "step": state.step.value if hasattr(state.step, "value") else str(state.step),
        "active_player": state.active_player,
        "priority_player": state.priority_player,
        "consecutive_passes": state.consecutive_passes,
        "players": {
            "1": _serialise_player_for_embedder(state.players[1]),
            "2": _serialise_player_for_embedder(state.players[2]),
        },
        "combat": _serialise_combat_for_embedder(state.combat),
        "stack_entries": stack_entries,
        "chain_links": chain_links,
        "events_this_turn": sorted(list(getattr(state, "events_this_turn", set()) or [])),
        "effect_manager": _serialise_effect_manager(getattr(state, "effect_manager", None)),
        "gamestate_debug_features": gamestate_to_features(state),
    }

    state_json = json.dumps(_json_safe(out), sort_keys=True, separators=(",", ":"))
    out["state_fingerprint_sha1"] = hashlib.sha1(state_json.encode("utf-8")).hexdigest()
    return out


class EmbedderTapRecorder:
    """Streaming JSONL logger for decision-time embedder taps."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._f = open(path, "w", encoding="utf-8")
        self.count = 0

    def log(self, payload: dict) -> None:
        json.dump(_json_safe(payload), self._f, ensure_ascii=True)
        self._f.write("\n")
        self.count += 1

    def close(self) -> None:
        self._f.close()


class DeterministicScoringModel:
    """Small fixed-weight scorer to mimic a trained policy head."""

    def __init__(self, state_dim: int, action_dim: int, hidden_dim: int = 96, seed: int = 42):
        g = torch.Generator().manual_seed(seed)
        self.ws = torch.randn(hidden_dim, state_dim, generator=g)
        self.wa = torch.randn(hidden_dim, action_dim, generator=g)
        self.b = torch.randn(hidden_dim, generator=g)
        self.v = torch.randn(hidden_dim, generator=g)

    def score(self, state_emb: torch.Tensor, action_emb: torch.Tensor) -> float:
        hidden = torch.tanh(self.ws.mv(state_emb) + self.wa.mv(action_emb) + self.b)
        return float(torch.dot(self.v, hidden))


class EmbedderMiddlemanAgent:
    """Middle-man between engine and action choice: embed, log, then choose."""

    def __init__(
        self,
        player_id: int,
        fallback_rng_seed: int,
        game_id: int,
        replay_db: ReplayDB,
        step_counter: list[int],
        action_embedder: ActionEmbedder,
        state_embedder: GameStateEmbedder,
        recorder: EmbedderTapRecorder,
    ):
        self.player_id = player_id
        self.rng = random.Random(fallback_rng_seed)
        self.game_id = game_id
        self.replay_db = replay_db
        self.step_counter = step_counter
        self.action_embedder = action_embedder
        self.state_embedder = state_embedder
        self.recorder = recorder

    def _fallback_choice(self, options):
        if isinstance(options, (list, tuple)) and options:
            return self.rng.choice(options)
        return options

    def __call__(self, state: GameState, options, context=None):
        is_action_choice = (
            isinstance(options, (list, tuple))
            and len(options) > 0
            and isinstance(options[0], Action)
        )

        if not is_action_choice:
            return self._fallback_choice(options)

        decision_idx = self.step_counter[0]
        self.step_counter[0] += 1

        with torch.no_grad():
            state_input = serialise_state_for_embedder(state)
            state_emb = self.state_embedder(state, perspective_player=self.player_id)

            legal_actions = list(options)

            # Pick action via seeded RNG — we only embed the chosen action.
            # Scoring all legal actions with a fake fixed-weight model adds no
            # training value and balloons runtime ~10x (one fwd pass per action).
            chosen_idx = self.rng.randint(0, len(legal_actions) - 1)
            chosen_action = legal_actions[chosen_idx]

            # Embed only the chosen action
            chosen_action_input = serialise_action_for_embedder(chosen_action)
            chosen_action_for_embedder = _normalise_action_for_embedder(chosen_action)
            chosen_action_emb = self.action_embedder(
                chosen_action_for_embedder,
                player_counters=state.players[self.player_id].counters,
            )

            # Build compact lists for logging (no per-action embedding)
            action_inputs = [serialise_action_for_embedder(a) for a in legal_actions]
            action_scores = [0.0] * len(legal_actions)   # no scoring pass
            action_norms  = [0.0] * len(legal_actions)
            action_scores[chosen_idx] = float(torch.norm(chosen_action_emb).item())

            phase = state.step.value if hasattr(state.step, "value") else str(state.step)
            gs_feats = gamestate_to_features(state)
            transition_obs = {
                "turn": state.turn_number,
                "step": phase,
                "active_player": state.active_player,
                "priority_player": state.priority_player,
                "p1_health": gs_feats["p1_health"],
                "p2_health": gs_feats["p2_health"],
                "p1_hand_size": gs_feats["p1_hand_size"],
                "p2_hand_size": gs_feats["p2_hand_size"],
                "p1_resources": gs_feats["p1_resources"],
                "p2_resources": gs_feats["p2_resources"],
                "combat_active": gs_feats["combat_active"],
                "stack_size": gs_feats["stack_size"],
                "chain_length": gs_feats["chain_length"],
                "state_fingerprint_sha1": state_input["state_fingerprint_sha1"],
                "state_embedding_norm": float(torch.norm(state_emb).item()),
            }
            transition_action = {
                "selected_index": chosen_idx,
                "selected_action": action_inputs[chosen_idx],
                "score": action_scores[chosen_idx],
            }
            row_id = self.replay_db.insert_transition(
                game_id=self.game_id,
                step_idx=decision_idx,
                player_id=self.player_id,
                phase=phase,
                obs=transition_obs,
                action=transition_action,
            )
            # Save live embeddings so offline pre-embed pass is exact
            self.replay_db.store_embeddings(row_id, state_emb, chosen_action_emb)
            # Batch commits every 50 decisions to avoid per-row fsync overhead
            if decision_idx % 50 == 0:
                self.replay_db.flush()


            self.recorder.log(
                {
                    "decision_idx": decision_idx,
                    "game_id": self.game_id,
                    "player_id": self.player_id,
                    "context": context,
                    "turn": state.turn_number,
                    "step": phase,
                    "active_player": state.active_player,
                    "priority_player": state.priority_player,
                    "num_legal_actions": len(legal_actions),
                    # Full state snapshot (equipment, counters, stack, combat, etc.)
                    "state_input": state_input,
                    "state_embedding_dim": int(state_emb.shape[0]),
                    "state_embedding_norm": float(torch.norm(state_emb).item()),
                    # Compact summary for all legal actions (no full dumps)
                    "action_scores": action_scores,
                    "action_embedding_norms": action_norms,
                    "action_types": [a["type"] for a in action_inputs],
                    "action_cards": [
                        a["card"]["slug"] if a["card"] else None
                        for a in action_inputs
                    ],
                    "action_embedding_dim": int(chosen_action_emb.shape[0]),
                    # Top-5 summary (based on chosen position only; no scoring pass)
                    "top_5_indices": [chosen_idx],
                    "top_5_scores": [action_scores[chosen_idx]],
                    "top_5_types": [action_inputs[chosen_idx]["type"]],
                    "top_5_cards": [
                        action_inputs[chosen_idx]["card"]["slug"] if action_inputs[chosen_idx]["card"] else None
                    ],
                    # Full detail for the chosen action only
                    "chosen_action_index": chosen_idx,
                    "chosen_action": action_inputs[chosen_idx],
                }
            )

        return chosen_action


def run_seeded_middleman_game():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if REPLAY_DB_PATH.exists():
        REPLAY_DB_PATH.unlink()
    if TAP_JSONL_PATH.exists():
        TAP_JSONL_PATH.unlink()

    card_db = CardDB(SLUG_INDEX_PATH)
    slug_vocab = SlugVocab.from_card_db(card_db)

    action_embedder = ActionEmbedder(d_model=128, slug_vocab_size=slug_vocab.size, slug_vocab=slug_vocab)
    state_embedder = GameStateEmbedder(d_model=128, slug_vocab_size=slug_vocab.size, slug_vocab=slug_vocab)
    action_embedder.eval()
    state_embedder.eval()

    replay_db = ReplayDB(str(REPLAY_DB_PATH))
    recorder = EmbedderTapRecorder(TAP_JSONL_PATH)

    game_id = replay_db.start_game("oscilio_constella_intelligence", "kayo_underhanded_cheat")
    step_counter = [0]

    p1_agent = EmbedderMiddlemanAgent(
        player_id=1,
        fallback_rng_seed=SEED + 1000,
        game_id=game_id,
        replay_db=replay_db,
        step_counter=step_counter,
        action_embedder=action_embedder,
        state_embedder=state_embedder,
        recorder=recorder,
    )
    p2_agent = EmbedderMiddlemanAgent(
        player_id=2,
        fallback_rng_seed=SEED + 2000,
        game_id=game_id,
        replay_db=replay_db,
        step_counter=step_counter,
        action_embedder=action_embedder,
        state_embedder=state_embedder,
        recorder=recorder,
    )

    p1_deck = os.path.join(DECKS_DIR, "oscillio_constella_intelligence_CC_lite.txt")
    p2_deck = os.path.join(DECKS_DIR, "kayo_underhanded_cheat_CC_lite.txt")

    print("=" * 72)
    print("SEEDED EMBEDDER MIDDLEMAN RUN")
    print("=" * 72)
    print(f"seed                : {SEED}")
    print(f"p1 deck             : {os.path.basename(p1_deck)}")
    print(f"p2 deck             : {os.path.basename(p2_deck)}")
    print(f"tap log             : {TAP_JSONL_PATH}")
    print(f"replay db           : {REPLAY_DB_PATH}")

    t0 = time.time()
    final_state = new_game(
        p1_deck,
        p2_deck,
        p1_agent,
        p2_agent,
        card_db=card_db,
        p1_seed=SEED,
        p2_seed=SEED + 1,
    )
    elapsed = time.time() - t0

    winner = int(final_state.winner or 0)
    turns = int(final_state.turn_number)
    replay_db.finalize_game(
        game_id,
        winner,
        turns,
        ended_on_turn_cap=bool(getattr(final_state, "ended_on_turn_cap", False)),
    )

    embeddings_count = replay_db.embedding_count()

    # --- Pre-embed pass: assemble IQL tensor dataset from live embeddings ---
    iql_dataset = build_iql_dataset(replay_db, game_id)
    iql_path = OUT_DIR / "iql_dataset_seed42.pt"
    torch.save(iql_dataset, str(iql_path))

    summary = {
        "seed": SEED,
        "winner": winner,
        "turns": turns,
        "elapsed_seconds": round(elapsed, 3),
        "decisions_tapped": recorder.count,
        "replay_transitions": replay_db.transition_count(),
        "embeddings_stored": embeddings_count,
        "state_embedder_dim": state_embedder.get_output_dim(),
        "action_embedder_dim": action_embedder.get_output_dim(),
        "iql_dataset": {
            "path": str(iql_path),
            "num_transitions": iql_dataset["num_transitions"],
            "state_dim": iql_dataset["state_dim"],
            "action_dim": iql_dataset["action_dim"],
        },
        "tap_jsonl": str(TAP_JSONL_PATH),
        "replay_db": str(REPLAY_DB_PATH),
    }

    with open(SUMMARY_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    recorder.close()
    replay_db.close()

    print("\nRUN SUMMARY")
    print("-" * 72)
    print(f"winner              : P{winner}")
    print(f"turns               : {turns}")
    print(f"elapsed             : {elapsed:.2f}s")
    print(f"decisions tapped    : {summary['decisions_tapped']}")
    print(f"embeddings stored   : {embeddings_count}")
    print(f"state embed dim     : {summary['state_embedder_dim']}")
    print(f"action embed dim    : {summary['action_embedder_dim']}")
    print(f"IQL dataset         : {iql_path.name}  ({iql_dataset['num_transitions']} transitions)")
    print(f"summary json        : {SUMMARY_JSON_PATH}")
    print("=" * 72)


def build_iql_dataset(replay_db: ReplayDB, game_id: int) -> dict:
    """Assemble (s, a, r, s', done) tensors from live-recorded embeddings.

    For each player, consecutive decisions are paired so that s' is the
    state embedding of that same player's next decision. Terminal last
    transitions get a zero s' vector.

    Returns a dict suitable for torch.save / torch.load.
    """
    rows = replay_db.load_embedding_dataset(game_id)
    if not rows:
        raise ValueError("No embedded transitions found — was store_embeddings called?")

    state_dim = rows[0]["state_emb"].shape[0]
    action_dim = rows[0]["action_emb"].shape[0]

    # Group by player preserving step order
    by_player: dict[int, list] = {1: [], 2: []}
    for row in rows:
        by_player[row["player_id"]].append(row)

    s_list, a_list, r_list, s_next_list, done_list = [], [], [], [], []

    for player_rows in by_player.values():
        for i, row in enumerate(player_rows):
            s_list.append(row["state_emb"])
            a_list.append(row["action_emb"])
            r_list.append(float(row["reward"]))
            done_list.append(float(row["done"]))
            # s' = next decision by same player; zero vector at episode end
            if i + 1 < len(player_rows):
                s_next_list.append(player_rows[i + 1]["state_emb"])
            else:
                s_next_list.append(torch.zeros(state_dim))

    return {
        "states":          torch.stack(s_list),       # (N, state_dim)
        "actions":         torch.stack(a_list),       # (N, action_dim)
        "rewards":         torch.tensor(r_list, dtype=torch.float32),       # (N,)
        "next_states":     torch.stack(s_next_list),  # (N, state_dim)
        "dones":           torch.tensor(done_list, dtype=torch.float32),    # (N,)
        "game_id":         game_id,
        "state_dim":       state_dim,
        "action_dim":      action_dim,
        "num_transitions": len(s_list),
    }


if __name__ == "__main__":
    run_seeded_middleman_game()
