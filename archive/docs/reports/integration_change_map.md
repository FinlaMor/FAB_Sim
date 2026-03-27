# Integration Change Map: LocalEngineBackend Migration

## Overview

This document maps every file outside `engine/` that would need modification if `LocalEngineBackend` becomes the primary game backend, replacing the Talishar Docker PHP backend.

**Key finding:** The encoders (`gamestate_embedder.py`, `action_embedder.py`) have **zero Talishar dependency** — they operate on native `engine.state.GameState` and `engine.actions.Action` objects. The migration impact is concentrated in the backend selection layer (`game_backends.py`), data collection scripts, and training pipeline entry points.

---

## File-by-File Change Map

### Tier 1: Core Backend Layer (Must Change)

#### 1. `rl_agents/game_backends.py`
- **Talishar dependency:** Contains `TalisharClient` (HTTP client), `TalisharBackend`, `TalisharIQLAgent`, `_run_talishar_pvp_game()`, `_run_talishar_random_game()`, `_pick_talishar_action()`, `_pick_talishar_random_fallback_action()`, plus `TalisharGameResult` dataclass. Also `add_game_backend_args()` adds Talishar-specific CLI flags (`--talishar-base-url`, `--talishar-api-key`, `--talishar-mode`, `--talishar-request-timeout`). `build_game_backend()` factory defaults to creating `TalisharBackend`.
- **Changes needed:** (a) Change `build_game_backend()` default from Talishar to Local. (b) Keep Talishar code for backward compat but make it opt-in. (c) `LocalEngineBackend.run_game()` already exists and works — no new code needed for the backend itself.
- **Effort:** ~2 hours (change defaults, update CLI help text, add deprecation warnings)
- **Risk:** Low — `LocalEngineBackend` already exists and is functional

#### 2. `rl_agents/talishar_adapter.py`
- **Talishar dependency:** Entire file (~1,700 lines) converts Talishar JSON → engine `GameState`/`Action` objects. Functions: `talishar_state_to_observed_game_state()`, `talishar_actions_to_engine_actions()`, `talishar_card_to_card()`.
- **Changes needed:** None for migration — this file becomes **unused** when LocalEngineBackend is primary. The local engine produces native `GameState` objects directly, so no adapter is needed.
- **Effort:** 0 hours (deprecate, don't modify)
- **Risk:** None — can be kept as dead code or removed later

### Tier 2: Data Collection Scripts (Must Rewrite/Replace)

#### 3. `scripts/run_talishar_games.py`
- **Talishar dependency:** Imports `TalisharBackend`, `TalisharClient`, `_deck_file_to_talishar_slugs`, `_run_talishar_pvp_game`, `_run_talishar_random_game`. Creates `TalisharClient`, converts decks to Talishar slug format, calls Talishar game runners. The entire script is Talishar-specific.
- **Changes needed:** Write a replacement `scripts/run_local_games.py` that uses `LocalEngineBackend` and `GameRunRequest`. The local engine takes deck file paths directly (no slug conversion needed), so the replacement is simpler.
- **Effort:** ~3 hours (new script, simpler than original since no HTTP/Docker concerns)
- **Risk:** Low — `LocalEngineBackend.run_game()` already handles deck loading

#### 4. `rl_agents/collect_iql_mixed_data.py`
- **Talishar dependency:** Imports `add_game_backend_args` and `build_game_backend` from `game_backends`. Passes Talishar-specific kwargs (`talishar_base_url`, `talishar_api_key`, `talishar_mode`, `talishar_request_timeout`) to `build_game_backend()`. Uses `GameRunRequest` (backend-agnostic).
- **Changes needed:** After `build_game_backend()` default is changed (item 1), this script works with local engine **without any code changes** — `build_game_backend()` will return `LocalEngineBackend` by default. The Talishar kwargs are simply ignored by LocalEngineBackend.
- **Effort:** ~0.5 hours (test that it works, update docstring)
- **Risk:** Low — already uses the backend-agnostic `GameRunRequest` interface

#### 5. `rl_agents/evaluate_iql_vs_random.py`
- **Talishar dependency:** Same pattern as `collect_iql_mixed_data.py` — imports `add_game_backend_args`, `build_game_backend`, uses `GameRunRequest`.
- **Changes needed:** Same as item 4 — works automatically after backend default change.
- **Effort:** ~0.5 hours (test and update docstring)
- **Risk:** Low

#### 6. `scripts/bench_player_bot.py`
- **Talishar dependency:** Directly imports `TalisharClient`, `TalisharGameResult`, `TalisharIQLAgent`, and Talishar helper functions. Hardcoded to Talishar.
- **Changes needed:** Rewrite to use `LocalEngineBackend` and `GameRunRequest`. Replace `TalisharIQLAgent` with native engine agent interface.
- **Effort:** ~2 hours
- **Risk:** Medium — `TalisharIQLAgent` has Talishar-specific action translation logic that needs a local equivalent

### Tier 3: Training Pipeline (Naming/Path Changes Only)

#### 7. `rl_agents/talishar_iql.py`
- **Talishar dependency:** Name only. The file implements `TransformerIQL` model and `TransformerIQLTrainer` — pure PyTorch code. Dataset class `TalisharHDF5Dataset` reads HDF5 files. No imports from Talishar adapter or backend. The "Talishar" in the name refers to the data source, not a code dependency.
- **Changes needed:** Rename file and classes for clarity (e.g., `iql_transformer.py`, `FABH5Dataset`). No functional changes.
- **Effort:** ~1 hour (rename + update all importers)
- **Risk:** Low — cosmetic change

#### 8. `rl_agents/train_transformer_iql.py`
- **Talishar dependency:** References `talishar_games.db` as default DB path. Imports from `rl_agents.talishar_iql`. CLI arg `--talishar-db`. Calls `build_transformer_hdf5_from_talishar_db()`.
- **Changes needed:** Rename CLI arg, update default path, update imports after talishar_iql.py rename.
- **Effort:** ~1 hour
- **Risk:** Low — string/path changes only

#### 9. `scripts/run_pipeline.py`
- **Talishar dependency:** `talishar_reachable()` health check, `--talishar-urls` CLI arg, subprocess call to `scripts/run_talishar_games.py`, references to `data/talishar_games.db`.
- **Changes needed:** Replace Talishar health check with local engine import check. Update subprocess call to use replacement script. Update DB path references.
- **Effort:** ~2 hours
- **Risk:** Medium — pipeline orchestration changes need careful testing

### Tier 4: Utility Scripts (Path/Name Changes)

#### 10. `scripts/preprocess_talishar.py`
- **Talishar dependency:** Reads `talishar_games.db` SQLite database. Name references Talishar.
- **Changes needed:** Rename, update default DB path. The SQLite schema is the same regardless of backend (set by `game_data.py`), so the preprocessing logic is unchanged.
- **Effort:** ~0.5 hours
- **Risk:** Low

#### 11. `scripts/compute_card_usage.py`
- **Talishar dependency:** Default `--games-db` path is `data/talishar_games.db`.
- **Changes needed:** Update default path.
- **Effort:** ~0.25 hours
- **Risk:** Low

#### 12. `scripts/fix_db_rewards.py`
- **Talishar dependency:** Default DB path `data/talishar_games.db`.
- **Changes needed:** Update default path.
- **Effort:** ~0.25 hours
- **Risk:** Low

#### 13. `scripts/train_deck_evaluator.py`
- **Talishar dependency:** Default `--games-db` path references talishar_games.db.
- **Changes needed:** Update default path.
- **Effort:** ~0.25 hours
- **Risk:** Low

### Tier 5: Tests (Update or Remove)

#### 14. `tests/test_talishar_adapter.py`
- **Talishar dependency:** Tests `talishar_adapter.py` conversion functions.
- **Changes needed:** Deprecate or remove — adapter tests are irrelevant when local engine is primary.
- **Effort:** ~0.25 hours
- **Risk:** Low

#### 15. `tests/test_talishar_autopass.py`
- **Talishar dependency:** Tests `_auto_pass_when_only_option`, `_pick_talishar_action`, Talishar game runners.
- **Changes needed:** Deprecate Talishar-specific tests. Auto-pass logic may need a local engine equivalent test.
- **Effort:** ~1 hour
- **Risk:** Low

#### 16. `tests/test_talishar_comparison_normalization.py`
- **Talishar dependency:** Tests decision normalization for Talishar comparison.
- **Changes needed:** Deprecate or remove.
- **Effort:** ~0.25 hours
- **Risk:** Low

### No Changes Needed (Confirmed Clean)

| File | Why Clean |
|------|-----------|
| `encoder/gamestate_embedder.py` | Imports only `engine.state.GameState`, `engine.card.Card` — native engine types. No Talishar dependency. |
| `encoder/action_embedder.py` | Imports only `engine.actions.Action`, `engine.card.Card` — native engine types. No Talishar dependency. |
| `encoder/card_embedder.py` | Pure card feature extraction from engine `Card` objects. |
| `rl_agents/iql.py` | Pure PyTorch IQL implementation. |
| `rl_agents/random_agent.py` | Uses native engine `GameState`/`Action`. |
| `rl_agents/heuristic_bot.py` | Uses native engine `GameState`/`Action`. |
| `rl_agents/fab_transformer.py` | Pure PyTorch transformer. |
| `rl_agents/game_data.py` | Backend-agnostic SQLite storage. Path default `data/talishar_games.db` is cosmetic only. |
| `rl_agents/dataset_adapter.py` | Reads SQLite DB — schema is backend-agnostic. |

---

## Summary Table

| Category | Files | Total Effort | Risk |
|----------|-------|-------------|------|
| Core backend layer | 2 | ~2 hrs | Low |
| Data collection scripts | 4 | ~6 hrs | Low-Medium |
| Training pipeline | 3 | ~4 hrs | Low |
| Utility scripts | 4 | ~1.25 hrs | Low |
| Tests | 3 | ~1.5 hrs | Low |
| **Total** | **16 files** | **~14.75 hrs** | **Low overall** |

## Dependencies Between Changes

```
1. game_backends.py (default change)
   ├── collect_iql_mixed_data.py (works automatically)
   ├── evaluate_iql_vs_random.py (works automatically)
   └── run_pipeline.py (needs script path update)

2. scripts/run_local_games.py (new replacement)
   └── run_pipeline.py (subprocess call update)

3. talishar_iql.py rename
   └── train_transformer_iql.py (import update)
```

## Key Finding: Embedder Compatibility

**The embedders are fully compatible with LocalEngineBackend.** Both `gamestate_embedder.py` and `action_embedder.py` operate on native engine types (`GameState`, `Player`, `Action`, `Card`) from `engine/state.py` and `engine/actions.py`. The Talishar adapter (`talishar_adapter.py`) exists precisely to convert Talishar JSON *into* these native types. When using `LocalEngineBackend`, the engine produces these types directly — the adapter is bypassed entirely.

## Key Finding: Deck Validation

Deck loading for the local engine is handled by `engine/deck.py` which reads the Fabrary text format directly. The Talishar backend requires an additional conversion step via `_deck_file_to_talishar_slugs()` in `game_backends.py`. Migration to local engine **simplifies** deck handling by removing this conversion layer.

## Recommendation

The integration migration is a **~2-day effort** (14.75 hours) with low risk. The critical path is:
1. Change `build_game_backend()` default (30 min)
2. Write `scripts/run_local_games.py` replacement (3 hrs)
3. Update `scripts/run_pipeline.py` (2 hrs)
4. Test the data collection pipeline end-to-end (2 hrs)

Everything else is cosmetic renaming that can be done incrementally.
