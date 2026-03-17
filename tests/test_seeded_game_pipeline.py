"""tests/test_seeded_game_pipeline.py

Seeded end-to-end pipeline:
  1. Run a complete game (Oscillio vs Kayo, seed 42)
  2. Record every decision to a ReplayDB SQLite file
  3. Translate every recorded transition through all three embedders
  4. Print a summary with per-layer dimension checks

Usage:
    python tests/test_seeded_game_pipeline.py
    # or
    pytest tests/test_seeded_game_pipeline.py -s
"""
from __future__ import annotations

import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch

from config import DECKS_DIR, SLUG_INDEX_PATH
from data_collection.replay_db import ReplayDB
from engine.actions import Action, ActionType
from engine.card import CardDB
from engine.engine import new_game
from engine.state import GameState, Step
from encoder.action_embedder import ActionEmbedder
from encoder.card_embedder import SlugVocab
from encoder.gamestate_embedder import GameStateEmbedder

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
DB_PATH = os.path.join(_ROOT, "data_collection", "seeded_test_game.db")


# ---------------------------------------------------------------------------
# Recording agent wrapper
# ---------------------------------------------------------------------------

def _card_to_slug(c) -> str | None:
    """Safely extract a slug from a Card object or a bare string slug."""
    if c is None:
        return None
    if hasattr(c, "slug"):
        return c.slug
    return str(c)


def _serialise_action(action: Action) -> dict:
    """Convert an Action to a JSON-safe dict."""
    return {
        "type": action.type.value,
        "player_id": action.player_id,
        "card": _card_to_slug(action.card),
        "card_idx": action.card_idx,
        "pitch_cards": [_card_to_slug(c) for c in action.pitch_cards] if action.pitch_cards else [],
        "from_arsenal": action.from_arsenal,
        "slot": action.slot,
        "card_list": [_card_to_slug(c) for c in action.card_list] if action.card_list else [],
        "target": _card_to_slug(action.target),
        "targets": [_card_to_slug(t) for t in action.targets] if action.targets else [],
        "modes_selected": list(action.modes_selected) if action.modes_selected else [],
        "x_value_declared": action.x_value_declared,
        "is_melded": bool(action.is_melded) if action.is_melded is not None else False,
        "alternative_cost_used": action.alternative_cost_used,
        "is_attack_proxy": bool(action.is_attack_proxy) if action.is_attack_proxy is not None else False,
        "is_attack_layer": bool(action.is_attack_layer) if action.is_attack_layer is not None else False,
        "attack_source": _card_to_slug(action.attack_source),
    }


def _serialise_obs(state: GameState, player_id: int) -> dict:
    """Lightweight observation snapshot — enough to reconstruct context."""
    p = state.players[player_id]
    opp = state.players[3 - player_id]
    return {
        "turn": state.turn_number,
        "step": state.step.value if hasattr(state.step, "value") else str(state.step),
        "active_player": state.active_player,
        "priority_player": state.priority_player,
        "my_health": p.health,
        "opp_health": opp.health,
        "my_resources": p.resources,
        "my_action_points": p.action_points,
        "my_hand_size": len(p.hand),
        "opp_hand_size": len(opp.hand),
        "my_hand": [c.slug for c in p.hand.cards],
        "my_deck_size": len(p.deck),
        "my_pitch": [c.slug for c in p.pitch.cards],
        "my_graveyard": [c.slug for c in p.graveyard.cards],
        "stack_size": len(state.stack_entries),
        "combat_active": state.combat is not None,
        "combat": state.combat.to_dict() if state.combat else None,
    }


class RecordingAgent:
    """Wraps a base agent; records every decision to a ReplayDB."""

    def __init__(
        self,
        player_id: int,
        base_agent,
        db: ReplayDB,
        game_id: int,
        step_counter: list[int],  # mutable shared counter [idx]
    ):
        self.player_id = player_id
        self.base = base_agent
        self.db = db
        self.game_id = game_id
        self._step = step_counter

    def __call__(self, state: GameState, options, context=None):
        # Only record proper Action decisions (skip ordering/who-goes-first prompts)
        is_action_choice = (
            isinstance(options, (list, tuple))
            and len(options) > 0
            and isinstance(options[0], Action)
        )

        choice = self.base(state, options, context)

        if is_action_choice and isinstance(choice, Action):
            obs = _serialise_obs(state, self.player_id)
            act = _serialise_action(choice)
            phase = state.step.value if hasattr(state.step, "value") else str(state.step)
            self.db.insert_transition(
                game_id=self.game_id,
                step_idx=self._step[0],
                player_id=self.player_id,
                phase=phase,
                obs=obs,
                action=act,
            )
            self._step[0] += 1

        return choice


# ---------------------------------------------------------------------------
# Run the seeded game
# ---------------------------------------------------------------------------

def run_seeded_game(db_path: str = DB_PATH) -> tuple[GameState, int, ReplayDB]:
    """Run one full game and return (final_state, game_id, db)."""
    SEED = 42
    rng1 = random.Random(SEED)
    rng2 = random.Random(SEED + 1)

    card_db = CardDB(SLUG_INDEX_PATH)
    db = ReplayDB(db_path)

    # Hero slugs from deck headings (for the games table)
    p1_hero_slug = "oscilio_constella_intelligence"
    p2_hero_slug = "kayo_underhanded_cheat"

    game_id = db.start_game(p1_hero_slug, p2_hero_slug)
    step_counter = [0]  # shared mutable counter

    base1 = lambda state, opts, ctx=None: rng1.choice(opts) if isinstance(opts, (list, tuple)) else opts
    base2 = lambda state, opts, ctx=None: rng2.choice(opts) if isinstance(opts, (list, tuple)) else opts

    agent1 = RecordingAgent(1, base1, db, game_id, step_counter)
    agent2 = RecordingAgent(2, base2, db, game_id, step_counter)

    p1_deck = os.path.join(DECKS_DIR, "oscillio_constella_intelligence_CC_lite.txt")
    p2_deck = os.path.join(DECKS_DIR, "kayo_underhanded_cheat_CC_lite.txt")

    print(f"[game] Starting seeded game (seed={SEED})")
    print(f"[game] P1 deck : {os.path.basename(p1_deck)}")
    print(f"[game] P2 deck : {os.path.basename(p2_deck)}")

    t0 = time.time()
    final_state = new_game(
        p1_deck, p2_deck, agent1, agent2,
        card_db=card_db, p1_seed=SEED, p2_seed=SEED + 1,
    )
    elapsed = time.time() - t0

    winner = final_state.winner or 0
    turns = final_state.turn_number

    db.finalize_game(
        game_id,
        winner,
        turns,
        ended_on_turn_cap=bool(getattr(final_state, "ended_on_turn_cap", False)),
    )

    print(f"[game] Finished in {elapsed:.1f}s — winner: P{winner}, turns: {turns}")
    print(f"[game] Transitions recorded: {db.transition_count()}")

    return final_state, game_id, db


# ---------------------------------------------------------------------------
# Embedder translation pass
# ---------------------------------------------------------------------------

def translate_transitions(game_id: int, db: ReplayDB, card_db: CardDB) -> dict:
    """
    Re-hydrate each transition from the DB and run it through all three embedders.
    Returns summary stats.
    """
    slug_vocab = SlugVocab.from_card_db(card_db)

    action_embedder = ActionEmbedder(
        d_model=128, slug_vocab_size=slug_vocab.size, slug_vocab=slug_vocab
    )
    gs_embedder = GameStateEmbedder(
        d_model=128, slug_vocab_size=slug_vocab.size, slug_vocab=slug_vocab
    )

    action_embedder.eval()
    gs_embedder.eval()

    transitions = db.get_transitions(game_id)
    print(f"\n[embed] Translating {len(transitions)} transitions …")

    action_dims: set[int] = set()
    gs_dims: set[int] = set()
    errors: list[str] = 0
    errors = []
    phase_counts: dict[str, int] = {}

    t0 = time.time()
    with torch.no_grad():
        for tr in transitions:
            phase = tr["phase"]
            phase_counts[phase] = phase_counts.get(phase, 0) + 1

            act_dict = tr["action"]

            # --- Reconstruct a minimal Action for the action embedder ---
            try:
                action_type = ActionType(act_dict["type"])
            except (KeyError, ValueError) as exc:
                errors.append(f"step {tr['step_idx']}: bad action type — {exc}")
                continue

            action = Action(
                type=action_type,
                player_id=act_dict.get("player_id"),
                card_idx=act_dict.get("card_idx"),
                from_arsenal=bool(act_dict.get("from_arsenal", False)),
                slot=act_dict.get("slot"),
                pitch_cards=act_dict.get("pitch_cards") or [],
                targets=act_dict.get("targets") or [],
                modes_selected=act_dict.get("modes_selected") or [],
                x_value_declared=act_dict.get("x_value_declared"),
                is_melded=act_dict.get("is_melded", False),
                alternative_cost_used=act_dict.get("alternative_cost_used"),
                is_attack_proxy=act_dict.get("is_attack_proxy", False),
                is_attack_layer=act_dict.get("is_attack_layer", False),
            )

            # Resolve card objects from slugs
            if act_dict.get("card"):
                action.card = card_db.get(act_dict["card"])
            if act_dict.get("attack_source"):
                action.attack_source = card_db.get(act_dict["attack_source"])
            if act_dict.get("target"):
                action.target = card_db.get(act_dict["target"])
            if act_dict.get("card_list"):
                action.card_list = [card_db.get(s) for s in act_dict["card_list"] if s]

            try:
                a_emb = action_embedder(action)
                action_dims.add(a_emb.shape[0])
            except Exception as exc:
                errors.append(f"step {tr['step_idx']}: action_embedder — {exc}")

            # --- Reconstruct a minimal GameState for the gamestate embedder ---
            # We use the obs JSON for scalars and the final state slug vocab for cards.
            # This produces a structurally valid (but shallow) state for embedding.
            obs = tr["obs"]
            try:
                from engine.state import Player, CombatState, Step as EngStep
                hero1 = card_db.get("oscilio_constella_intelligence")
                hero2 = card_db.get("kayo_underhanded_cheat")
                if hero1 is None:
                    hero1 = card_db.get("bravo_showstopper")
                if hero2 is None:
                    hero2 = card_db.get("kayo_armed_and_dangerous")

                p1 = Player(1, hero1)
                p2 = Player(2, hero2)
                p1.health = obs.get("my_health", 40) if tr["player_id"] == 1 else obs.get("opp_health", 40)
                p2.health = obs.get("opp_health", 40) if tr["player_id"] == 1 else obs.get("my_health", 40)

                # Restore hand cards
                if tr["player_id"] == 1:
                    for slug in obs.get("my_hand", []):
                        c = card_db.get(slug)
                        if c:
                            p1.hand.add(c)
                else:
                    for slug in obs.get("my_hand", []):
                        c = card_db.get(slug)
                        if c:
                            p2.hand.add(c)

                try:
                    step_val = EngStep(obs.get("step", "action"))
                except ValueError:
                    step_val = EngStep.ACTION

                from engine.state import GameState as GS
                stub_state = GS(
                    players={1: p1, 2: p2},
                    active_player=obs.get("active_player", 1),
                    player_agents={1: lambda *a: None, 2: lambda *a: None},
                    step=step_val,
                    turn_number=obs.get("turn", 1),
                    combat=None,
                    done=False,
                    winner=None,
                    priority_player=obs.get("priority_player", 1),
                    consecutive_passes=0,
                )

                g_emb = gs_embedder(stub_state, perspective_player=tr["player_id"])
                gs_dims.add(g_emb.shape[0])
            except Exception as exc:
                errors.append(f"step {tr['step_idx']}: gs_embedder — {exc}")

    elapsed = time.time() - t0

    return {
        "total_transitions": len(transitions),
        "elapsed_s": round(elapsed, 2),
        "action_dims": sorted(action_dims),
        "gs_dims": sorted(gs_dims),
        "expected_action_dim": action_embedder.get_output_dim(),
        "expected_gs_dim": gs_embedder.get_output_dim(),
        "phase_counts": phase_counts,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print("=" * 65)
    print("SEEDED GAME PIPELINE: Oscillio vs Kayo (seed=42)")
    print("=" * 65)

    # Clean up any leftover DB from a previous run
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    card_db = CardDB(SLUG_INDEX_PATH)

    # 1. Run the game and record
    final_state, game_id, db = run_seeded_game(DB_PATH)

    # 2. Embed all transitions
    summary = translate_transitions(game_id, db, card_db)
    db.close()

    # 3. Print summary
    print("\n" + "=" * 65)
    print("EMBEDDING PASS SUMMARY")
    print("=" * 65)
    print(f"  Transitions embedded : {summary['total_transitions']}")
    print(f"  Embedding time       : {summary['elapsed_s']}s")
    print(f"  Action embed dims    : {summary['action_dims']}  (expected {summary['expected_action_dim']})")
    print(f"  GameState embed dims : {summary['gs_dims']}  (expected {summary['expected_gs_dim']})")
    print(f"  Errors               : {len(summary['errors'])}")
    if summary["errors"]:
        for e in summary["errors"][:10]:
            print(f"    WARN: {e}")
        if len(summary["errors"]) > 10:
            print(f"    … and {len(summary['errors']) - 10} more")

    print("\n  Phase breakdown:")
    for phase, cnt in sorted(summary["phase_counts"].items(), key=lambda x: -x[1]):
        print(f"    {phase:30s}  {cnt:4d}")

    # 4. Pass/fail
    dim_ok = (
        summary["action_dims"] == [summary["expected_action_dim"]]
        and summary["gs_dims"] == [summary["expected_gs_dim"]]
    )
    err_ok = len(summary["errors"]) == 0

    print()
    if dim_ok and err_ok:
        print("ALL CHECKS PASSED")
    else:
        if not dim_ok:
            print("FAIL: DIMENSION MISMATCH")
        if not err_ok:
            print("FAIL: EMBEDDING ERRORS PRESENT")
    print("=" * 65)
    print(f"\nReplay DB written to: {DB_PATH}")

    assert dim_ok, "Embedder dimension mismatch"
    assert err_ok, f"{len(summary['errors'])} embedding error(s) — see above"


if __name__ == "__main__":
    main()
