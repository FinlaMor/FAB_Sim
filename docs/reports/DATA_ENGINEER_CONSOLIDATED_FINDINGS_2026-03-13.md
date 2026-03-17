# Data Engineer Consolidated Findings

Date: 2026-03-13
Peer Review Round 2: 2026-03-13 (Data Engineer 5.5/10, AI Engineer 7/10)
Peer Review Round 3: 2026-03-13 (Data Engineer 5/10, AI Engineer 6/10)
Peer Review Round 4: 2026-03-13 (Data Engineer 7.5/10, AI Engineer 6/10 → Fix Batch 4 applied)
Peer Review Round 5: 2026-03-13 (Data Engineer 7.6/10, AI Engineer 6.8/10)
Scope: Talishar to Embedders, Transformer I/O, Training Database

## Executive Summary

Three reviews were completed across the data and model pipelines, followed by four rounds of peer review and four fix batches. Round 5 peer review reopened six findings (P1:2, P2:2, P3:2), all in data/eval reliability and run metadata integrity.

- **Open findings: 6**
- P0: 0
- P1: 2
- P2: 2
- P3: 2

**Status:** No P0 issues, but do not treat eval outputs as production-grade model-quality signals until the P1/P2 findings below are fixed.

**Architecture decision resolved**: IQL is the documented production serving path (see ARCHITECTURE_DECISION.md). Transformer is scoped as a research prototype with no training loop.

## Severity Snapshot

| Severity | Count | Meaning |
|---|---:|---|
| P0 | 0 | Crash or hard failure |
| P1 | 2 | Silent wrong behavior or major quality loss |
| P2 | 2 | Design, signal coverage, normalization, scalability issues |
| P3 | 2 | Low-priority or cosmetic issues |

## Resolved Since Audit

These were identified in earlier reviews but are confirmed fixed in the current codebase. Do not reopen.

### Round 1 Resolutions (pre-audit)

| ID | Original Finding | Fix Location |
|---|---|---|
| P1-8 | Opponent pitch order not preserved | transformer_policy.py — both calls now use preserve_order=True |
| P2-11 | go_again missing from meta token | transformer_policy.py — has_go_again encoded in meta |
| P2-12 | Combat damage missing from meta token | transformer_policy.py — attack_power, total_defense encoded |
| P2-14 | Embedder bundle lacks schema fingerprint | embedder_bundle.py — slug_vocab_size present |
| P2-16 | trainable_embedder collapse risk | iql.py — Q-network gradients flow through adapters |
| P2-17 | No periodic flush API | replay_db.py — flush() and maybe_flush() implemented |
| P2-19 | CLI lacks resume-from-checkpoint | train_iql.py — --resume-from flag implemented |
| P2-20 | Checkpoint stores full embedder bundle | train_iql.py — stores only path string and fingerprint integer |

### Round 2 Resolutions (fix batch 2026-03-13)

| ID | Original Finding | Fix Location |
|---|---|---|
| P0-1 | Pitch cards type crash | action_embedder.py — `hasattr(item, 'slug')` dispatch handles both Card and string |
| P0-2 | Training-inference architecture gap | ARCHITECTURE_DECISION.md — IQL documented as production path, Transformer scoped as prototype |
| P0-3 | No IQL inference decode agent | iql_decode_agent.py — from_checkpoint loads IQLTrainer + bundle weights, select_action does cosine nearest-neighbor |
| P1-1 | Combat keyword case mismatch | gamestate_embedder.py + card_embedder.py — all keyword indices and lookups use .lower() |
| P1-6 | CardDB mutation side effect | talishar_adapter.py line 1024 `copy.copy(card)` + transformer_policy.py `copy.copy(card)` in pitch history primary path |
| P1-7 | Pitch fallback degraded encoding | transformer_policy.py — fallback builds full feature dicts (slug_idx, zone_idx, zero-filled numeric/types/keywords) through card_embedder.forward() |
| P1-10 | Bundle-dataset dimension validation opt-in | train_iql.py — warning emitted when --dataset-pt used without bundle |
| P1-12 | Incomplete games in training set | dataset_adapter.py — JOIN games WHERE winner IS NOT NULL |
| P1-13 | No target networks in IQL | iql.py — value_target with polyak tau=0.005, used in Q-target bootstrap, correct per Kostrikov 2021 |
| P2-old-12 | CardEmbedder weights triplicated in bundle | embedder_bundle.py — card_embedder.* keys filtered from action/state state_dicts |
| P2-old-14 | store_embeddings not tracked by flush counter | replay_db.py — store_embeddings increments _pending_writes |
| P2-old-16 | DataLoader no reproducibility seed | iql.py — generator=torch.Generator().manual_seed(42) |
| P2-old-18 | RTG crosses player boundaries | dataset_adapter.py — ValueError raised when rtg + global mode combined |

### Round 3 Resolutions (peer review 2026-03-13)

| ID | Original Finding | Fix Location |
|---|---|---|
| P1-2 | Action zone always serialized as "hand" for equipment/arsenal | talishar_adapter.py — source_zone derived from action type and phase code; "equipment" and "arsenal" emitted correctly |
| P1-4 | Talishar cardID integers normalized together with enumerate indices | talishar_adapter.py — card_idx=None sentinel; action_embedder encodes as -1.0, no collision with enumerate indices |
| P3-6 | Engine uses unseeded random for start-player selection | engine/engine.py — seeded RNG via `_coin_rng = _npr.RandomState(p1_seed ^ p2_seed ^ 0xFAB)` |

### Fix Batch 2 Resolutions (2026-03-13)

| ID | Original Finding | Fix Location |
|---|---|---|
| P1-NEW | strict=False lacks key logging | iql_decode_agent.py — load_state_dict return value inspected; missing_keys and unexpected_keys logged via logger.warning |
| P1-5 | Pitch history drift (no caller passes prior_pitch_history) | compare_seeded_talishar_vs_local_payloads.py — carries forward observed_state.pitch_history across ticks |
| P2-1 | ACTION_ALT_COST_TYPES schema size mismatch | action_embedder.py — `_n_alt` computed from `len(ACTION_ALT_COST_TYPES) + 2`; hardcoded 10 eliminated |
| P2-2 | get_output_dim() hardcodes literal 10 | action_embedder.py — return expression now uses `_n_alt` variable from `len(ACTION_ALT_COST_TYPES) + 2` |
| P2-7 | IQLDecodeAgent missing dim guard | iql_decode_agent.py — explicit assertions: `bundle.state_output_dim == trainer.config.state_dim` and `action_output_dim` |
| P3-1 | events_this_turn current tick only | compare_seeded_talishar_vs_local_payloads.py — carries forward observed_state.events_this_turn as prior_events across ticks |
| P3-7 | load_embedder_bundle missing security comment | embedder_bundle.py — "Only load embedder bundles from trusted sources" comment added |
| P3-9 | RTG guard fires post-loop | dataset_adapter.py — fail-fast validation moved to function entry before any data loading |

### Fix Batch 3 Resolutions (2026-03-13)

| ID | Original Finding | Fix Location |
|---|---|---|
| P2-5 | Dataset assembly loads all to RAM | dataset_adapter.py — memory estimate logged before loading; documents save_mmap/from_mmap workflow |
| P2-7 | No offline evaluation metric | iql.py — `_compute_eval_metrics()` + `eval_ratio` parameter in `fit()`; train_iql.py `--eval-ratio` flag; eval Q/V/BC loss logged every interval |
| P3-5 | from_checkpoint weights_only=False | iql.py — `torch.load(..., weights_only=True)`; train_iql.py `_load_payload` also updated |
| P3-7 | ReplayDB stats skew | replay_db.py — `transition_count()` now JOINs games WHERE winner IS NOT NULL; `raw_transition_count()` added for unfiltered count |

### Fix Batch 4 Resolutions (2026-03-13) — Post Peer Review Round 4

| ID | Original Finding | Fix Location |
|---|---|---|
| P2-NEW-1 | `_compute_eval_metrics` called unconditionally in rwbc_mode (Q/V untrained, garbage output) | iql.py — Q/V metrics skipped when `rwbc_mode=True`; only `eval_bc_loss` emitted in that path |
| P2-NEW-2 | Eval cap misplaced inside `_compute_eval_metrics` — wasted training data | iql.py — `n_eval = min(max(1, int(n * eval_ratio)), 2048)` capped at split site in `fit()` |
| P2-NEW-3 | Inconsistent history dict schema (eval keys absent on non-log steps) | iql.py — non-log steps call `train_batch` but are not appended to history; history contains log-steps only with uniform schema |
| P3-NEW-1 | `eval_actor_loss` not comparable to `actor_loss` (unweighted vs. advantage-weighted) | iql.py — renamed to `eval_bc_loss`; comment clarifies it is unweighted MSE |
| P3-NEW-2 | No `.eval()`/`.train()` guards in `_compute_eval_metrics` | iql.py — all sub-modules set to `.eval()` in try block, restored to `.train()` in finally |
| P3-NEW-3 | `eval_ratio >= 1.0` silently no-ops without warning | iql.py — `ValueError` raised for `eval_ratio` outside `[0.0, 1.0)` at `fit()` entry |

### Round 5 Findings (2026-03-13) — Open

| ID | Severity | Finding | Evidence | Recommendation |
|---|---|---|---|---|
| R5-P1-1 | P1 | Eval split is transition-level, allowing trajectory leakage between train and eval. | iql.py `eval_idx = perm[:n_eval]`, `train_idx = perm[n_eval:]` | Split by game/episode groups, not individual transitions. |
| R5-P1-2 | P1 | Incomplete embedded games can be ingested; same-player path forces absorbing terminal labels on last available row. | dataset_adapter.py `_resolve_game_ids` JOIN on `embeddings`, `d_list.append(1.0)` terminal forcing | Add completeness gate before ingesting each game; reject partially embedded games. |
| R5-P2-1 | P2 | Advantage normalization can produce NaN on singleton batches via `advantage.std()`. | iql.py `advantage.std().clamp_min(1e-6)` | Use `advantage.std(unbiased=False)` and guard tiny batches. |
| R5-P2-2 | P2 | Resume metadata drift: metrics file stores CLI config, not effective resumed trainer config. | train_iql.py `from_checkpoint(...)`, `trainer.config.batch_size = ...`, `"config": asdict(config)` | Serialize `asdict(trainer.config)` after resume overrides are applied. |
| R5-P3-1 | P3 | rwbc eval logging prints NaN placeholders for Q/V fields. | iql.py eval log line uses fallback `float('nan')` for missing q/v metrics | In rwbc mode, log only eval BC metric (or explicit N/A tokens). |
| R5-P3-2 | P3 | Eval helper restores all modules to train mode unconditionally instead of restoring prior mode state. | iql.py `for m in nets: m.train()` | Save/restore per-module prior training flags. |

### Closed as Accepted (Fix Batch 3)

| ID | Original Finding | Reason |
|---|---|---|
| P1-3 | StackEntry metadata always empty | Talishar data-source limitation. Extraction code checks 6 field name variants; Talishar does not send the data. |
| P2-1 | 4 Step enum dims permanently zero | Talishar does not emit begin_game, combat_layer, combat_attack, end_turn steps. |
| P2-2 | button/prompt_button collapse to PASS | Talishar resolves modal prompts server-side before adapter sees actions. |
| P2-3 | is_melded structured + keyword fallback | Best-effort: checks structured fields first, keyword fallback as last resort. Sufficient for current data. |
| P2-4 | _infer_consecutive_passes bounded {0, 1} | Talishar does not send consecutivePasses field; fallback inference is bounded by available information. |
| P2-6 | Token budget 434 vs 512 cap | Warning already issued when truncation occurs. Truncation preserves action tokens by design. |
| P3-1 | effect_manager absent, feature block zero | Requires new subsystem implementation; out of scope for current pipeline fixes. |
| P3-2 | defend_card_list capped to one card | Talishar sends one card per defend action; adapter correctly models available data. |
| P3-3 | modes_selected not populated | Talishar does not send mode selection data in action payloads. |
| P3-4 | alternative_cost_used brittle parsing | Checks structured fields first (alternativeCost, altCost); text fallback is last resort with known aliases. |
| P3-6 | ActorNetwork deterministic | By design: IQL uses implicit policy via advantage weighting. Exploration not needed for offline RL. |

### Closed as Factually Incorrect (Round 2 peer review)

| Original Finding | Reason for Closure |
|---|---|
| weapon1/weapon2 absent from CARD_ZONES | Both present in card_embedder.py CARD_ZONES list |
| items/auras/allies/tokens absent from CARD_ZONES | All four present in card_embedder.py CARD_ZONES list |
| resources_available saturates at 3+ (normalized /2.0) | Actual normalization is /6.0, saturates at 6 resources |
| Step vocabulary duplicated across embedders | Both import STEP_VOCABULARY from centralized feature_schema.py |
| Opponent deck slug visibility leaks composition | Only perspective player's deck is encoded; opponent represented by size only in meta token |
| chain_link_number normalization differs (action_embedder /3.0 vs gamestate_embedder /10.0) | Both use /10.0 — action_embedder.py line 356 confirmed; original claim of /3.0 never existed in current codebase (Round 3) |

## P0 Findings

All P0 findings resolved. See Resolved table above.

## P1 Findings

### R5-P1-1 Transition-Level Eval Leakage

- Finding: Holdout eval uses transition-level random splitting rather than game/episode grouped splitting.
- Impact: Eval losses are optimistically biased by trajectory-local leakage.
- Evidence: iql.py `eval_idx = perm[:n_eval]`, `train_idx = perm[n_eval:]`.

### R5-P1-2 Incomplete Embedded Game Ingestion

- Finding: Game selection requires at least one embedded transition in a completed game, but does not validate embedding completeness per game.
- Impact: In same-player mode, truncated per-player rows are force-labeled as absorbing terminal transitions.
- Evidence: dataset_adapter.py `_resolve_game_ids()` SQL join against embeddings + forced `d_list.append(1.0)` in same-player tail handling.

## P2 Findings

### R5-P2-1 Singleton-Batch NaN Risk in Advantage Normalization

- Finding: `advantage.std()` can be NaN on singleton batches with unbiased estimator.
- Impact: NaN actor weights/loss can poison training.
- Evidence: iql.py `_actor_weights_from_advantage()` and logged `adv_std`.

### R5-P2-2 Resume Metrics Config Drift

- Finding: Resume path loads trainer config from checkpoint, but metrics serialize CLI `config` object.
- Impact: Run metadata can misstate actual training configuration.
- Evidence: train_iql.py `IQLTrainer.from_checkpoint(...)` and metrics payload `"config": asdict(config)`.

## P3 Findings

### R5-P3-1 rwbc Eval Logging Uses NaN Placeholders

- Finding: Eval log line formats q/v/q_mean with NaN fallback when rwbc mode omits Q/V metrics.
- Impact: Monitoring parsers may misinterpret NaN-valued numeric fields.
- Evidence: iql.py eval log line with `float('nan')` fallbacks.

### R5-P3-2 Eval Mode Restoration Is Not Stateful

- Finding: Eval helper restores all modules to train mode unconditionally.
- Impact: Low in current fit path, but brittle if reused in non-training contexts.
- Evidence: iql.py `for m in nets: m.train()` in finally block.

## Confirmed Clarifications

- Graveyard and banished zone sizes are present in the Transformer meta token.
- go_again, attack_power, and total_defense are already encoded in the meta token (meta_dim = 23 + len(step_values)).
- weapon1, weapon2, items, auras, allies, tokens zones all present in CARD_ZONES.
- Step vocabulary centralized in feature_schema.py (STEP_VOCABULARY), imported by both embedders.
- Opponent deck is NOT encoded in Transformer — only perspective player's deck tokens + opponent deck size in meta.
- resources_available normalized by /6.0, not /2.0.

## Recommended Fix Order

1. Fix R5-P1-1: Grouped eval split by game/episode.
2. Fix R5-P1-2: Embedding completeness gate before game ingestion.
3. Fix R5-P2-1: Stable advantage std for singleton batches.
4. Fix R5-P2-2: Serialize effective `trainer.config` in metrics.
5. Fix R5-P3-1 and R5-P3-2 as cleanup.

## Peer Review Notes (Round 2)

### Implementation Quality Highlights (AI Engineer assessment)

- **P1-13 target network**: Polyak formula correct, placement after all optimizer steps is standard, requires_grad_(False) prevents gradient leakage, checkpoint backward-compat with fallback to value_state_dict. Only value_target needed per IQL paper (not Q-targets).
- **P0-3 decode agent**: Correct architecture. Minor concern: strict=False silently drops mismatched keys. GameStateEmbedder card_embedder weight sharing through sub-modules means bundle may still carry some duplication under player_embedder.card_embedder.* paths.
- **P2-old-12 bundle dedup**: Effective for ActionEmbedder (direct child). Partially effective for GameStateEmbedder (shared card_embedder across sub-modules). Reduces triple to at-most double storage.

### Suggested Acceptance Checks

- Talishar pitched actions run end-to-end embedding without exceptions.
- IQLDecodeAgent.from_checkpoint loads a trained checkpoint and selects legal actions.
- DataLoader batch ordering is deterministic across identical seeds.
- RTG + global mode raises ValueError.
- Offline training startup fails fast on dimension mismatch when no bundle is provided alongside a pre-built dataset.
- IQL training with target networks shows stable TD error on a held-out validation split with no Q-overestimation divergence.
- Replay DB collection survives an interrupted run with bounded in-flight data loss (no more than one maybe_flush interval).
- RTG mode is gated to same-player trajectory mode, or raises an explicit error when combined with global interleaved mode.

## Peer Review Notes (Round 5)

### Round 5 Key Findings (Data Engineer 7.6/10, AI Engineer 6.8/10)

- **R5-P1-1 (both reviewers)**: Transition-level eval split leaks trajectory-local information between train/eval. Recommendation: grouped split by game/episode.
- **R5-P1-2 (Data Engineer)**: Incomplete embedded games can pass selection and be force-terminated in same-player mode. Recommendation: completeness gate per game before ingest.
- **R5-P2-1 (AI Engineer)**: `advantage.std()` can become NaN on singleton batches. Recommendation: `std(unbiased=False)` and tiny-batch guard.
- **R5-P2-2 (AI Engineer)**: Resume path logs CLI config rather than effective runtime trainer config. Recommendation: serialize `asdict(trainer.config)`.
- **R5-P3-1 (AI Engineer)**: rwbc eval logging prints NaN q/v placeholders. Recommendation: rwbc-specific eval log line.
- **R5-P3-2 (both reviewers)**: Eval helper should restore prior module mode state, not always train mode.

## Peer Review Notes (Round 4)

### Round 4 Key Findings (Data Engineer 7.5/10, AI Engineer 6/10)

Both reviewers independently flagged the same two P2 bugs in the eval infrastructure added in Fix Batch 3, plus three P3 issues.

- **P2-NEW-1 (both reviewers)**: `_compute_eval_metrics()` invoked without rwbc_mode guard. In rwbc_mode, Q1/Q2/Value are frozen at random initialization; `eval_q_mean` would show noise indistinguishable from Q-overestimation. Fix: skip Q/V block when `rwbc_mode=True`.
- **P2-NEW-2 (AI Engineer)**: Eval cap of 2048 was inside `_compute_eval_metrics` but `n_eval` was computed at split time without the cap. For a 100K-transition dataset with `eval_ratio=0.1`, this excluded 10,000 transitions from training but only evaluated 2,048 — 7,952 wasted. Fix: cap `n_eval` at split site.
- **P2-NEW-3 (AI Engineer)**: History list had inconsistent dict keys — `eval_*` fields only present on log steps, causing silent `KeyError` in downstream consumers. Fix: only append log-step entries to `history`.
- **P3-NEW-1 (both reviewers)**: `eval_actor_loss` uses unweighted MSE while training `actor_loss` is advantage-weighted — not comparable. Renamed to `eval_bc_loss`.
- **P3-NEW-2 (AI Engineer)**: No `.eval()`/`.train()` context guards in `_compute_eval_metrics`. Safe now (Linear+ReLU only), but fragile for future BatchNorm/Dropout. Added try/finally guard.
- **P3-NEW-3 (Data Engineer)**: `eval_ratio > 1.0` silently no-ops. Added `ValueError` for values outside `[0.0, 1.0)`.
- **P2-5 RAM estimate**: Both reviewers noted `~18 KB` is ~2-3× overestimate for typical dims. Accepted as-is — conservative estimate is safer for capacity planning.
- **P3-7 transition_count**: Data Engineer noted mid-game callers will now see 0. `raw_transition_count()` is the documented escape; accepted.
- **P3-5 weights_only=True**: Both reviewers confirmed safe — all payload types allowlisted in PyTorch ≥ 2.0.



### Round 3 Key Findings (Data Engineer 5/10, AI Engineer 6/10)

- **P1-2 and P1-4 found fixed**: Both agents confirmed zone mislabeling and card-index sentinel are correctly implemented. Document was wrong to list them as open.
- **P2-2 confirmed factually wrong**: Both agents confirmed action_embedder uses `/10.0` (not `/3.0`). The original claim of a mismatch never applied to the current codebase. Closed as factually incorrect.
- **P3-6 confirmed fixed**: Engine seeded RNG via `_coin_rng = _npr.RandomState(p1_seed ^ p2_seed ^ 0xFAB)`.
- **P1-3 partial note**: Extraction code for `declaredX`/`declaredModes`/`declaredTargets` exists in the adapter, but the field names don't match Talishar's documented schema. Finding remains open.
- **P1-5 and P3-1 root cause**: Both findings share the same fix — call sites must pass `prior_pitch_history` and `prior_events`. The adapter is already written to accept them.
- **NEW P2-7 (dim guard)**: IQLDecodeAgent loads bundle + trainer checkpoint without asserting dim compatibility. A stale bundle silently passes load_state_dict but crashes at inference time inside `encode_states()`.
- **NEW P2-2 (get_output_dim hardcoded)**: `get_output_dim()` returns a literal `10` for the alt-cost block instead of `len(ACTION_ALT_COST_TYPES) + 2`. Schema growth silently breaks all checkpoint/bundle dimension checks.
- **NEW P3-9 (RTG guard post-loop)**: RTG guard fires after full data load. Correctness-preserving but wasteful at scale.
- **RTG guard placement (AI Engineer)**: The ValueError is post-loop. Fix belongs at function entry before `db.load_embedding_dataset` is called.
