from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import DECKS_DIR, SLUG_INDEX_PATH
from encoder.action_embedder import action_to_features
from encoder.gamestate_embedder import gamestate_to_features
from engine.actions import Action
from engine.card import CardDB
from engine.engine import new_game
from rl_agents.game_backends import (
    TalisharClient,
    _deck_file_to_talishar_slugs,
    _pick_talishar_random_fallback_action,
)
from rl_agents.talishar_adapter import talishar_actions_to_engine_actions, talishar_state_to_observed_game_state


@dataclass
class RunCapture:
    source: str
    seed: int
    deck_p1: str
    deck_p2: str
    max_turns: int
    decisions: list[dict[str, Any]]
    winner: int | None
    turn_number: int
    ended_on_turn_cap: bool
    elapsed_s: float


PASS_LIKE_ACTION_TYPES = {"pass", "reaction_pass"}


def _is_pass_like_action_type(action_type: str | None) -> bool:
    return str(action_type or "") in PASS_LIKE_ACTION_TYPES


def _decision_legal_action_types(decision: dict[str, Any]) -> list[str]:
    return [str(action.get("action_type") or "") for action in decision.get("legal_action_features", [])]


def _is_talishar_pass_only_decision(decision: dict[str, Any]) -> bool:
    chosen_type = str(decision.get("chosen_action_type") or "")
    legal_types = _decision_legal_action_types(decision)
    return bool(
        _is_pass_like_action_type(chosen_type)
        and legal_types
        and all(_is_pass_like_action_type(action_type) for action_type in legal_types)
    )


def _is_talishar_end_phase_ui_decision(decision: dict[str, Any]) -> bool:
    if str(decision.get("step") or "") == "end_phase_beginning":
        return True
    return str(decision.get("chosen_action_type") or "") == "store_arsenal"


def _same_decision_context(left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
    if left is None or right is None:
        return False
    return (
        left.get("actor") == right.get("actor")
        and left.get("turn") == right.get("turn")
        and left.get("step") == right.get("step")
    )


def _should_collapse_talishar_micro_decision(
    previous_kept: dict[str, Any] | None,
    decision: dict[str, Any],
    next_decision: dict[str, Any] | None,
) -> bool:
    chosen_type = str(decision.get("chosen_action_type") or "")
    if not _is_pass_like_action_type(chosen_type):
        return False

    raw_action = decision.get("chosen_raw_action") or {}
    raw_type = str(raw_action.get("type") or "")
    has_prev_non_pass = _same_decision_context(previous_kept, decision) and not _is_pass_like_action_type(
        previous_kept.get("chosen_action_type") if previous_kept else None
    )
    has_next_non_pass = _same_decision_context(decision, next_decision) and not _is_pass_like_action_type(
        next_decision.get("chosen_action_type") if next_decision else None
    )

    # Talishar defend selection is multi-click: card selections followed by a finalize pass.
    if str(decision.get("step") or "") == "combat_defend" and has_prev_non_pass:
        return True

    # Prompt/button passes sandwiched between real plays are UI confirmations, not new semantics.
    if raw_type in {"button", "prompt_button"} and has_prev_non_pass and has_next_non_pass:
        return True

    return False


def _normalize_talishar_decisions(
    decisions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    stats = {
        "removed_pass_only": 0,
        "removed_end_phase_ui": 0,
        "removed_micro_interactions": 0,
    }

    filtered: list[dict[str, Any]] = []
    for decision in decisions:
        if _is_talishar_end_phase_ui_decision(decision):
            stats["removed_end_phase_ui"] += 1
            continue
        if _is_talishar_pass_only_decision(decision):
            stats["removed_pass_only"] += 1
            continue
        filtered.append(decision)

    collapsed: list[dict[str, Any]] = []
    for idx, decision in enumerate(filtered):
        next_decision = filtered[idx + 1] if idx + 1 < len(filtered) else None
        previous_kept = collapsed[-1] if collapsed else None
        if _should_collapse_talishar_micro_decision(previous_kept, decision, next_decision):
            stats["removed_micro_interactions"] += 1
            continue
        collapsed.append(decision)

    return collapsed, stats


def _counter_cosine(a: Counter, b: Counter) -> float:
    keys = set(a.keys()) | set(b.keys())
    if not keys:
        return 1.0
    dot = sum(float(a.get(k, 0)) * float(b.get(k, 0)) for k in keys)
    an = math.sqrt(sum(float(v) * float(v) for v in a.values()))
    bn = math.sqrt(sum(float(v) * float(v) for v in b.values()))
    if an == 0.0 or bn == 0.0:
        return 0.0
    return dot / (an * bn)


def _jaccard(a: set, b: set) -> float:
    u = a | b
    if not u:
        return 1.0
    return len(a & b) / len(u)


def _safe_mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(statistics.mean(values))


def _resolve_card_name(card_db: CardDB, slug: str | None) -> str | None:
    if not slug:
        return None
    card = card_db.get(slug)
    if card is None:
        return None
    return card.name


def _raw_action_summary(card_db: CardDB, raw_action: dict[str, Any]) -> dict[str, Any]:
    slug = raw_action.get("cardNumber")
    return {
        "type": raw_action.get("type"),
        "mode": raw_action.get("mode"),
        "cardID": raw_action.get("cardID", ""),
        "buttonInput": raw_action.get("buttonInput", ""),
        "cardNumber": slug,
        "cardName": _resolve_card_name(card_db, slug),
    }


def _collect_local_capture(seed: int, deck_p1: str, deck_p2: str, max_turns: int) -> RunCapture:
    card_db = CardDB(SLUG_INDEX_PATH)
    decisions: list[dict[str, Any]] = []

    class RecordingAgent:
        def __init__(self, player_id: int, rng_seed: int):
            self.player_id = player_id
            self.rng = random.Random(rng_seed)

        def __call__(self, state, options, context=None):
            if isinstance(options, (list, tuple)) and options and isinstance(options[0], Action):
                state_feats = gamestate_to_features(state)
                legal_feats = [action_to_features(opt) for opt in options]
                idx = self.rng.randrange(len(options))
                decisions.append(
                    {
                        "source": "local",
                        "decision_idx": len(decisions),
                        "actor": self.player_id,
                        "turn": state.turn_number,
                        "step": state_feats.get("step"),
                        "state_features": state_feats,
                        "legal_action_features": legal_feats,
                        "chosen_idx": idx,
                        "chosen_action_type": legal_feats[idx].get("action_type"),
                    }
                )
                return options[idx]

            if isinstance(options, (list, tuple)) and options:
                return self.rng.choice(list(options))
            return options

    agent1 = RecordingAgent(1, seed)
    agent2 = RecordingAgent(2, seed + 1)

    t0 = time.time()
    final_state = new_game(
        deck_p1,
        deck_p2,
        agent1,
        agent2,
        card_db=card_db,
        p1_seed=seed,
        p2_seed=seed + 1,
        max_turns=max_turns,
    )
    elapsed = time.time() - t0

    return RunCapture(
        source="local",
        seed=seed,
        deck_p1=deck_p1,
        deck_p2=deck_p2,
        max_turns=max_turns,
        decisions=decisions,
        winner=final_state.winner,
        turn_number=final_state.turn_number,
        ended_on_turn_cap=bool(getattr(final_state, "ended_on_turn_cap", False)),
        elapsed_s=elapsed,
    )


def _collect_talishar_capture(seed: int, deck_p1: str, deck_p2: str, max_turns: int, timeout: float) -> RunCapture:
    card_db = CardDB(SLUG_INDEX_PATH)
    client = TalisharClient(request_timeout=timeout)

    p1_sub = _deck_file_to_talishar_slugs(deck_p1)
    p2_sub = _deck_file_to_talishar_slugs(deck_p2)

    game_name, p1_auth = client.create_game(p1_sub, deck_test_mode=False)
    p2_auth = client.join_game(game_name, p2_sub, player_id=2)
    if not client.start_game(game_name, p1_auth):
        raise RuntimeError("Talishar Start.php failed")

    rng1 = random.Random(seed)
    rng2 = random.Random(seed + 1)
    decisions: list[dict[str, Any]] = []
    # Cumulative history carried across ticks for P1-5 and P3-1
    _prior_pitch_history: dict[int, dict[int, list[str]]] | None = None
    _prior_events: set[str] | None = None

    t0 = time.time()
    final_winner: int | None = None
    final_turn = 0
    ended_on_turn_cap = False

    max_polls = max_turns * 80
    stalls = 0
    max_stalls = 200

    for _ in range(max_polls):
        s1 = client.get_state(game_name, p1_auth, player_id=1)
        s2 = client.get_state(game_name, p2_auth, player_id=2)

        final_turn = int(s1.get("turnNo", 0))
        over, winner = client.is_game_over(s1)
        if over:
            final_winner = winner
            break

        if final_turn >= max_turns:
            ended_on_turn_cap = True
            p1_hp = int(s1.get("playerHealth", 0))
            p2_hp = int(s1.get("opponentHealth", 0))
            final_winner = 1 if p1_hp > p2_hp else 2 if p2_hp > p1_hp else None
            break

        if bool(s1.get("havePriority")):
            actor = 1
            actor_state = s1
            opp_state = s2
            auth = p1_auth
            rng = rng1
        elif bool(s2.get("havePriority")):
            actor = 2
            actor_state = s2
            opp_state = s1
            auth = p2_auth
            rng = rng2
        else:
            stalls += 1
            if stalls > max_stalls:
                ended_on_turn_cap = True
                break
            time.sleep(0.05)
            continue

        stalls = 0

        raw_actions = client.get_available_actions(actor_state)
        if not raw_actions:
            if actor_state.get("canPassPhase"):
                client.process_input(game_name, auth, 99, player_id=actor)
                continue
            stalls += 1
            time.sleep(0.05)
            continue

        observed_state = talishar_state_to_observed_game_state(
            actor_state,
            player_id=actor,
            card_db=card_db,
            opponent_view=opp_state,
            prior_pitch_history=_prior_pitch_history,
            prior_events=_prior_events,
        )
        # Carry forward cumulative history for next tick (P1-5, P3-1)
        _prior_pitch_history = observed_state.pitch_history
        _prior_events = observed_state.events_this_turn
        engine_actions = talishar_actions_to_engine_actions(actor_state, card_db=card_db, player_id=actor)

        state_feats = gamestate_to_features(observed_state)
        legal_feats = [action_to_features(a) for a in engine_actions]

        chosen_raw_action = _pick_talishar_random_fallback_action(actor_state, raw_actions, rng)
        idx = raw_actions.index(chosen_raw_action)
        client.submit_action(game_name, auth, chosen_raw_action, player_id=actor)

        chosen_action_type = legal_feats[idx].get("action_type") if idx < len(legal_feats) else "unmapped"
        raw_action_summaries = [_raw_action_summary(card_db, a) for a in raw_actions]
        decisions.append(
            {
                "source": "talishar",
                "decision_idx": len(decisions),
                "actor": actor,
                "turn": final_turn,
                "step": state_feats.get("step"),
                "state_features": state_feats,
                "legal_action_features": legal_feats,
                "chosen_idx": idx,
                "chosen_action_type": chosen_action_type,
                "chosen_raw_action": raw_action_summaries[idx],
                "raw_legal_actions": raw_action_summaries,
                "raw_action_count": len(raw_actions),
                "mapped_action_count": len(legal_feats),
            }
        )

    elapsed = time.time() - t0

    return RunCapture(
        source="talishar",
        seed=seed,
        deck_p1=deck_p1,
        deck_p2=deck_p2,
        max_turns=max_turns,
        decisions=decisions,
        winner=final_winner,
        turn_number=final_turn,
        ended_on_turn_cap=ended_on_turn_cap,
        elapsed_s=elapsed,
    )


def _summarize_capture(run: RunCapture) -> dict[str, Any]:
    step_counter = Counter(d["step"] for d in run.decisions)
    chosen_counter = Counter(d["chosen_action_type"] for d in run.decisions)

    all_legal_types = []
    legal_sizes = []
    scalar_keys = [
        "turn",
        "p1_health",
        "p2_health",
        "p1_hand_size",
        "p2_hand_size",
        "p1_resources",
        "p2_resources",
        "stack_size",
        "chain_length",
    ]
    scalar_means: dict[str, float] = {}
    for key in scalar_keys:
        vals = [float(d["state_features"].get(key, 0.0)) for d in run.decisions]
        scalar_means[key] = _safe_mean(vals)

    for d in run.decisions:
        legal = d.get("legal_action_features", [])
        legal_sizes.append(len(legal))
        for a in legal:
            t = a.get("action_type", "unknown")
            all_legal_types.append(t)

    legal_counter = Counter(all_legal_types)

    return {
        "source": run.source,
        "seed": run.seed,
        "winner": run.winner,
        "turn_number": run.turn_number,
        "ended_on_turn_cap": run.ended_on_turn_cap,
        "elapsed_s": round(run.elapsed_s, 2),
        "decision_count": len(run.decisions),
        "avg_legal_action_count": round(_safe_mean([float(x) for x in legal_sizes]), 3),
        "step_distribution": dict(step_counter),
        "chosen_action_distribution": dict(chosen_counter),
        "legal_action_distribution": dict(legal_counter),
        "state_feature_means": scalar_means,
        "legal_action_type_set": sorted(set(all_legal_types)),
    }


def _compare_summaries(local_sum: dict[str, Any], tal_sum: dict[str, Any]) -> dict[str, Any]:
    step_cos = _counter_cosine(Counter(local_sum["step_distribution"]), Counter(tal_sum["step_distribution"]))
    chosen_cos = _counter_cosine(
        Counter(local_sum["chosen_action_distribution"]),
        Counter(tal_sum["chosen_action_distribution"]),
    )
    legal_cos = _counter_cosine(
        Counter(local_sum["legal_action_distribution"]),
        Counter(tal_sum["legal_action_distribution"]),
    )

    local_set = set(local_sum["legal_action_type_set"])
    tal_set = set(tal_sum["legal_action_type_set"])
    action_type_jaccard = _jaccard(local_set, tal_set)

    scalar_keys = sorted(local_sum["state_feature_means"].keys())
    scalar_sim = {}
    scalar_scores = []
    for key in scalar_keys:
        lv = float(local_sum["state_feature_means"].get(key, 0.0))
        tv = float(tal_sum["state_feature_means"].get(key, 0.0))
        denom = abs(lv) + abs(tv) + 1.0
        score = 1.0 - (abs(lv - tv) / denom)
        scalar_sim[key] = score
        scalar_scores.append(score)

    likeness_score = _safe_mean([
        step_cos,
        chosen_cos,
        legal_cos,
        action_type_jaccard,
        _safe_mean(scalar_scores),
    ])

    return {
        "likeness_score_0_to_1": likeness_score,
        "step_distribution_cosine": step_cos,
        "chosen_action_distribution_cosine": chosen_cos,
        "legal_action_distribution_cosine": legal_cos,
        "legal_action_type_jaccard": action_type_jaccard,
        "state_scalar_similarity": scalar_sim,
        "decision_count_ratio_talishar_to_local": (
            float(tal_sum["decision_count"]) / float(max(1, local_sum["decision_count"]))
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-turns", type=int, default=40)
    parser.add_argument(
        "--deck",
        type=str,
        default=str(Path(DECKS_DIR) / "kayo_underhanded_cheat_CC_lite.txt"),
        help="Use the same deck file for both players in both backends",
    )
    parser.add_argument("--talishar-timeout", type=float, default=20.0)
    parser.add_argument(
        "--out",
        type=str,
        default="data_collection/talishar_local_seed_compare_seed42.json",
    )
    args = parser.parse_args()

    deck_p1 = args.deck
    deck_p2 = args.deck

    print(f"[run] seed={args.seed} max_turns={args.max_turns}")
    print(f"[run] deck={deck_p1}")

    tal_capture = _collect_talishar_capture(
        seed=args.seed,
        deck_p1=deck_p1,
        deck_p2=deck_p2,
        max_turns=args.max_turns,
        timeout=args.talishar_timeout,
    )
    print(
        f"[talishar] decisions={len(tal_capture.decisions)} winner={tal_capture.winner} "
        f"turns={tal_capture.turn_number} elapsed_s={tal_capture.elapsed_s:.1f}"
    )

    local_capture = _collect_local_capture(
        seed=args.seed,
        deck_p1=deck_p1,
        deck_p2=deck_p2,
        max_turns=args.max_turns,
    )
    print(
        f"[local] decisions={len(local_capture.decisions)} winner={local_capture.winner} "
        f"turns={local_capture.turn_number} elapsed_s={local_capture.elapsed_s:.1f}"
    )

    tal_summary = _summarize_capture(tal_capture)
    local_summary = _summarize_capture(local_capture)
    comparison = _compare_summaries(local_summary, tal_summary)

    tal_normalized_decisions, normalization_stats = _normalize_talishar_decisions(tal_capture.decisions)
    tal_normalized_capture = RunCapture(
        source="talishar_normalized",
        seed=tal_capture.seed,
        deck_p1=tal_capture.deck_p1,
        deck_p2=tal_capture.deck_p2,
        max_turns=tal_capture.max_turns,
        decisions=tal_normalized_decisions,
        winner=tal_capture.winner,
        turn_number=tal_capture.turn_number,
        ended_on_turn_cap=tal_capture.ended_on_turn_cap,
        elapsed_s=tal_capture.elapsed_s,
    )
    tal_normalized_summary = _summarize_capture(tal_normalized_capture)
    normalized_comparison = _compare_summaries(local_summary, tal_normalized_summary)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "seed": args.seed,
        "max_turns": args.max_turns,
        "deck_p1": deck_p1,
        "deck_p2": deck_p2,
        "notes": "Pre-embedder payload comparison only; no ActionEmbedder/GameStateEmbedder forward calls. Includes raw and normalized Talishar views.",
        "talishar": {
            "summary": tal_summary,
            "sample_decisions": tal_capture.decisions[:5],
        },
        "talishar_normalized": {
            "summary": tal_normalized_summary,
            "sample_decisions": tal_normalized_capture.decisions[:5],
        },
        "local": {
            "summary": local_summary,
            "sample_decisions": local_capture.decisions[:5],
        },
        "comparison": comparison,
        "comparison_normalized": normalized_comparison,
        "normalization": {
            "raw_talishar_decisions": len(tal_capture.decisions),
            "normalized_talishar_decisions": len(tal_normalized_capture.decisions),
            **normalization_stats,
            "rules": [
                "exclude pass-only Talishar windows",
                "exclude end-phase UI windows and arsenal storage prompts",
                "collapse Talishar prompt/button micro-interactions between semantic actions",
            ],
        },
    }

    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("\n[comparison_raw]")
    print(json.dumps(comparison, indent=2))
    print("\n[comparison_normalized]")
    print(json.dumps(normalized_comparison, indent=2))
    print("\n[normalization]")
    print(json.dumps(payload["normalization"], indent=2))
    print(f"\n[write] {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
