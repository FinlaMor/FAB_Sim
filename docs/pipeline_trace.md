# Pipeline Execution Trace: `run_local_pipeline.py`

Complete execution trace of one loop iteration of the FAB Sim local-engine
training and evolution pipeline. The pipeline orchestrates a 7-stage cycle:
validate decks, simulate games, verify data, train player bot (IQL), train deck
evaluator, evolve decks, and benchmark.

**Entry point:** `scripts/run_local_pipeline.py`

**Usage:**
```bash
python scripts/run_local_pipeline.py --games-per-loop 200
python scripts/run_local_pipeline.py --loops 5 --games-per-loop 200
python scripts/run_local_pipeline.py --loop-forever --games-per-loop 100
```

---

## Pre-Loop Initialization

These functions execute during `main()` before the loop begins. The loop
depends on their outputs.

| # | Function / Program | File | Purpose | Input | Output |
|---|-------------------|------|---------|-------|--------|
| 0a | `build_parser()` / `argparse` | `run_local_pipeline.py` | Parse CLI args | `sys.argv` | `args` namespace with `games_per_loop`, `max_turns`, `iql_steps`, `iql_device`, `loops`, `seed`, skip flags |
| 0b | `GameDataStore(db_path=...)` | `rl_agents/game_data.py` | Create/open SQLite DB for deck metadata | `str` path `data/game_data.db` | `GameDataStore` instance (creates tables if needed) |
| 0c | `ReplayDB(db_path=...)` | `data_collection/replay_db.py` | Create/open SQLite DB for replay transitions & embeddings | `str` path `data/replay.db` | `ReplayDB` instance (creates `games`, `transitions`, `embeddings` tables) |
| 0d | `load_embedder_bundle(path)` **OR** fresh creation | `rl_agents/embedder_bundle.py` | Load or build the shared embedder weights | Path `checkpoints/embedder_bundle.pt` (if exists) OR CardDB + SlugVocab + d_model=128 | `dict` bundle with keys: `d_model`, `action_output_dim`, `state_output_dim`, `slug_vocab_size`, `card_embedder_state_dict`, `action_embedder_state_dict`, `state_embedder_state_dict` |
| 0d.1 | `CardDB(slug_index_path)` | `engine/card.py` | Load card database from JSON | Path to `card_data/slug_index.json` | `CardDB` instance with `.get(slug)` -> `Card` lookup |
| 0d.2 | `SlugVocab.from_card_db(card_db)` | `encoder/card_embedder.py` | Build slug-to-index vocabulary | `CardDB` instance | `SlugVocab` with `.size` (int), `.encode(slug)` -> int |
| 0d.3 | `ActionEmbedder(d_model, slug_vocab_size, slug_vocab)` | `encoder/action_embedder.py` | Instantiate action embedding model | `d_model=128`, vocab size, vocab | `ActionEmbedder` nn.Module |
| 0d.4 | `GameStateEmbedder(d_model, slug_vocab_size, slug_vocab)` | `encoder/gamestate_embedder.py` | Instantiate state embedding model | `d_model=128`, vocab size, vocab | `GameStateEmbedder` nn.Module |
| 0d.5 | `build_embedder_bundle(action_embedder, state_embedder)` | `rl_agents/embedder_bundle.py` | Serialize both embedder state dicts into a dict | Two nn.Modules | Bundle dict (see 0d output) |
| 0d.6 | `save_embedder_bundle(path, action_embedder, state_embedder)` | `rl_agents/embedder_bundle.py` | `torch.save()` the bundle to disk | Path, two nn.Modules | File at `checkpoints/embedder_bundle.pt` |

---

## Stage 1: Validate Decks

**Function:** `step_validate_decks(args)`

**Purpose:** Check every `.txt` deck file in `decks/generated/` for FAB legality
(class/talent rules, weapon presence, equipment presence). Filter down to valid
decks only.

| # | Function / Program | File | Purpose | Input | Output |
|---|-------------------|------|---------|-------|--------|
| 1.1 | `CardDB(slug_index_path)` | `engine/card.py` | Load card database (if not already cached on `args._card_db`) | `SLUG_INDEX_PATH` string | `CardDB` instance |
| 1.2 | `json.load(SLUG_INDEX_PATH)` | stdlib | Load raw slug index JSON for validation | File path | `dict` with `by_slug` key -> `{slug: {types, subtypes, card_keywords, name, ...}}` |
| 1.3 | `validate_all_decks(deck_dir, card_db, slug_index)` | `rl_agents/deck_validator.py` | Iterate all `.txt` files, validate each | `deck_dir` str, `CardDB`, slug_index dict | `(valid_paths: list[str], invalid_report: dict[str, list[str]])` |
| 1.3.1 | `validate_single_deck(deck_path, card_db, slug_index)` xN per deck | `rl_agents/deck_validator.py` | Validate one deck: legality + weapon + equipment checks | Deck file path, CardDB, slug_index | `(is_valid: bool, violations: list[str])` |
| 1.3.1a | `load_banned_cards(fmt="cc")` | `rl_agents/fab_constants.py` | Load banned card slugs for the format | Format string `"cc"` | `frozenset[str]` of banned slugs |
| 1.3.1b | `load_deck(deck_path, card_db)` | `engine/deck.py` | Parse a deck `.txt` file into structured data | File path, CardDB | `dict` with keys: `hero` (slug), `weapon` (slug), `weapons` (list), `equipment` (dict), `cards` (list of slugs) |
| 1.3.1c | `validate_deck_legality(deck_cards, equipment, hero_types, slug_index, ...)` | `rl_agents/fab_constants.py` | Check class/talent legality of every card vs hero | Card dicts, hero types, slug_index, banned_slugs | `list[str]` of violation strings (empty = legal) |
| 1.4 | `print_summary(label, items)` | `run_local_pipeline.py` | Print formatted summary block | Label str, dict of key-value pairs | Console output |

**Stage 1 Output:** `valid_decks: list[str]` -- file paths of all decks that passed validation.

---

## Stage 2: Run Games

**Function:** `step_run_games(args, valid_decks, loop_num, opponent_pool)`

**Purpose:** Simulate `games_per_loop` FAB card games using the local engine,
recording state/action embeddings and game results to the replay database.

### Pre-game setup (once per stage)

| # | Function / Program | File | Purpose | Input | Output |
|---|-------------------|------|---------|-------|--------|
| 2.0 | `OpponentPool(heuristic_seed, checkpoint_paths, device, embedder_bundle)` | `rl_agents/local_game_runner.py` | Create pool of opponent agents (heuristic + random, optionally IQL policy) | Seed int, optional checkpoint paths, device str, bundle dict | `OpponentPool` instance with `._agents` list |
| 2.1 | `MatchupScheduler()` | `rl_agents/local_game_runner.py` | Instantiate matchup scheduler | None | `MatchupScheduler` instance |
| 2.2 | `scheduler.schedule_matchups(valid_decks, games_per_loop)` | `rl_agents/local_game_runner.py` | Generate deck pairings ensuring round-robin coverage, then random fill | `list[str]` deck paths, `int` count | `list[tuple[str, str]]` of (p1_deck_path, p2_deck_path) pairs |
| 2.3 | `run_games(deck_pairs, opponent_pool, card_db, replay_db, game_data_store, embedder_bundle, max_turns, seed)` | `rl_agents/local_game_runner.py` | Orchestrate full batch of games | Deck pairs, OpponentPool, CardDB, ReplayDB, GameDataStore, bundle dict, max_turns int, seed int | `GameResults` dataclass with `.completed`, `.failed`, `.results` |

### Per-game inner loop (xN where N = `games_per_loop`, recorded once)

| # | Function / Program | File | Purpose | Input | Output |
|---|-------------------|------|---------|-------|--------|
| 2.3.1 | `_build_embedders(embedder_bundle)` | `rl_agents/local_game_runner.py` | Reconstruct ActionEmbedder + GameStateEmbedder from bundle dict, load weights | Bundle dict | `(ActionEmbedder, GameStateEmbedder)` -- both in eval mode |
| 2.3.2 | `_extract_hero_from_deck(deck_path)` x2 per game | `rl_agents/local_game_runner.py` | Read hero name from deck file header line `Hero: ...` | Deck file path str | Hero name `str` |
| 2.3.3 | `replay_db.start_game(p1_hero, p2_hero)` | `data_collection/replay_db.py` | Insert new game row into `games` table | Two hero name strings | `game_id: int` (auto-increment PK) |
| 2.3.4 | `opponent_pool.sample_agent(rng, player_id, seed)` x2 | `rl_agents/local_game_runner.py` | Randomly select and instantiate an agent from the pool | RNG, player_id int, seed int | Agent instance: `RandomAgent`, `LocalHeuristicAgent`, or `IQLPolicyAgent` |
| 2.3.5 | `EmbeddingRecorderAgent(base_agent, player_id, game_id, replay_db, action_embedder, state_embedder, step_counter, combat_log)` x2 | `rl_agents/local_game_runner.py` | Wrap base agent to intercept decisions and record embeddings | Base agent, IDs, ReplayDB, embedders, shared step_counter list, shared combat_log dict | `EmbeddingRecorderAgent` instance (callable) |
| 2.3.6 | `GameRunRequest(p1_deck, p2_deck, p1_agent, p2_agent, card_db, p1_seed, p2_seed, max_turns)` | `rl_agents/game_backends.py` | Frozen dataclass bundling all game parameters | Deck paths, agents, CardDB, seeds, max_turns | `GameRunRequest` instance |
| 2.3.7 | `LocalEngineBackend().run_game(req)` | `rl_agents/game_backends.py` | Delegate to `engine.engine.new_game()` | `GameRunRequest` | `GameState` -- final state with `.winner`, `.turn_number`, `.players`, `.done` |
| 2.3.7a | `new_game(p1_deck_path, p2_deck_path, p1_agent, p2_agent, card_db, p1_seed, p2_seed, max_turns)` | `engine/engine.py` | Core game simulation: load decks -> create players -> run turn loop until done/turn cap | Deck paths, agent callables, CardDB, seeds, max_turns | `GameState` with final HP, winner, turn count |
| 2.3.7a.i | `load_deck(path, card_db)` x2 | `engine/deck.py` | Parse deck txt -> structured dict | Path, CardDB | Dict with hero, weapons, equipment, cards |
| 2.3.7a.ii | `create_player(deck_data, player_id, card_db, seed)` x2 | `engine/deck.py` | Build a `Player` state object from deck data | Deck dict, ID, CardDB, seed | `Player` instance with health, hand, deck zones |
| 2.3.7a.iii | `legal_actions(state)` xM per game turn | `engine/actions.py` | Compute all legal actions for current game state | `GameState` | `list[Action]` -- legal moves for the priority player |
| 2.3.7a.iv | `agent(state, options, context)` xM per decision | (wrapped agents) | EmbeddingRecorderAgent delegates to base agent, records embeddings | GameState, list[Action] | Chosen `Action` |

### Inside EmbeddingRecorderAgent.\_\_call\_\_ (xM per decision point, recorded once)

| # | Function / Program | File | Purpose | Input | Output |
|---|-------------------|------|---------|-------|--------|
| 2.3.8 | `base_agent(state, options, context)` | (RandomAgent or LocalHeuristicAgent) | Make the actual game decision | GameState, options list | Chosen option |
| 2.3.9 | `state_embedder(state, perspective_player)` | `encoder/gamestate_embedder.py` | Encode current game state into embedding vector | GameState, player_id | `torch.Tensor` state embedding |
| 2.3.10 | `_normalise_action_for_embedder(choice)` | `rl_agents/utils/card_helpers.py` | Normalize action fields for the embedder | `Action` object | Normalized `Action` (or dict) |
| 2.3.11 | `action_embedder(action, player_counters)` | `encoder/action_embedder.py` | Encode chosen action into embedding vector | Normalized action, counter dict | `torch.Tensor` action embedding |
| 2.3.12 | `gamestate_to_features(state)` | `encoder/gamestate_embedder.py` | Extract raw feature dict from state (for debug/obs) | GameState | `dict` with numeric features |
| 2.3.13 | `_serialise_action(choice)` | `rl_agents/local_game_runner.py` | Serialize Action to JSON-safe dict | `Action` object | `dict` with `selected_action` key containing type, card slug, pitch_cards, defend_cards, etc. |
| 2.3.14 | `replay_db.insert_transition(game_id, step_idx, player_id, phase, obs, action)` | `data_collection/replay_db.py` | Insert one transition row into `transitions` table | game_id int, step int, player int, phase str, obs dict (JSON), action dict (JSON) | `row_id: int` (transition PK) |
| 2.3.15 | `replay_db.store_embeddings(row_id, state_emb, action_emb)` | `data_collection/replay_db.py` | Store embedding tensors as BLOBs in `embeddings` table | transition_id, two `torch.Tensor`s | None (writes to DB) |
| 2.3.16 | `replay_db.flush()` (every 50 steps) | `data_collection/replay_db.py` | Commit pending DB writes | None | None (SQLite commit) |

### Post-game finalization (xN per game, recorded once)

| # | Function / Program | File | Purpose | Input | Output |
|---|-------------------|------|---------|-------|--------|
| 2.3.17 | `replay_db.finalize_game(game_id, winner, turn_number, ended_on_cap)` | `data_collection/replay_db.py` | Update `games` row with final results | game_id, winner (1/2/None), turns int, bool | None (SQL UPDATE) |
| 2.3.18 | `_assign_game_rewards(replay_db, game_id, combat_log, winner)` | `rl_agents/local_game_runner.py` | Compute damage-scaled rewards per turn, back-propagate to transitions, assign terminal +/-1 | ReplayDB, game_id, combat_log dict `{turn: [link_dicts]}`, winner | None (batch-updates `reward` and `done` columns) |
| 2.3.18a | `replay_db.get_game_transitions(game_id)` | `data_collection/replay_db.py` | Fetch all transitions for reward assignment | game_id | `list[sqlite3.Row]` with id, step_idx, player_id, phase, obs, reward, done |
| 2.3.18b | `replay_db.batch_update_rewards(updates)` | `data_collection/replay_db.py` | Batch-update reward column | `list[tuple[float, int]]` (reward, tid) | None |
| 2.3.18c | `replay_db.batch_update_done(updates)` | `data_collection/replay_db.py` | Batch-update done flag column | `list[tuple[int, int]]` (done, tid) | None |
| 2.3.19 | `game_data_store.record_local_game(collector, game_state, p1_deck_file, p2_deck_file, seed, game_id)` | `rl_agents/game_data.py` | Record game outcome + deck metadata to secondary DB | None collector, GameState, deck paths, seed, game_id | None (writes to `data/game_data.db`) |

**Stage 2 Output:** `n_games: int` -- total game count in replay DB (from `replay_db.game_count()`).

---

## Stage 3: Verify Data Upload

**Function:** `step_upload_data(args)`

**Purpose:** Sanity-check that games and transitions were actually recorded to
the replay database. This is a verification-only step (data was written during
Stage 2).

| # | Function / Program | File | Purpose | Input | Output |
|---|-------------------|------|---------|-------|--------|
| 3.1 | `replay_db.game_count()` | `data_collection/replay_db.py` | Count total game rows | None | `int` -- `SELECT COUNT(*) FROM games` |
| 3.2 | `replay_db.transition_count()` | `data_collection/replay_db.py` | Count total transition rows | None | `int` -- `SELECT COUNT(*) FROM transitions` |
| 3.3 | `print_summary(...)` | `run_local_pipeline.py` | Display counts and DB path | Label, dict | Console output |

**Stage 3 Output:** Console verification. No data mutation.

---

## Stage 4: Train Player Bot (IQL)

**Function:** `step_train_player_bot(args, loop_num)`

**Purpose:** Train an Implicit Q-Learning (IQL) agent on collected game
transitions. Requires >= 500 transitions; otherwise skips.

**Skip guard:** `replay_db.transition_count() < 500` -> stage is skipped entirely.

| # | Function / Program | File | Purpose | Input | Output |
|---|-------------------|------|---------|-------|--------|
| 4.1 | `replay_db.transition_count()` | `data_collection/replay_db.py` | Check threshold (min 500) | None | `int` count |
| 4.2 | `run_step(label, cmd)` | `run_local_pipeline.py` | Execute subprocess | Description str, command list | `int` exit code |
| 4.2a | **Subprocess:** `python -m rl_agents.train_iql --db-path <replay.db> --steps <iql_steps> --batch-size 256 --device <device> --out-dir <checkpoint_dir>` | `rl_agents/train_iql.py` | IQL training: loads replay DB -> builds tensor dataset -> trains actor/critic/value networks -> saves checkpoint | CLI args (db path, steps, batch size, device, output dir) | Checkpoint file `checkpoint_final.pt` in `checkpoints/iql/loop{N}/` |
| 4.3 | `find_best_checkpoint(prefix)` (implicit post-check) | `run_local_pipeline.py` | Look for `_best.pt` or `_final.pt` | Prefix string | `Path | None` |

**Stage 4 Output:** Checkpoint file at `checkpoints/iql/loop{N}/checkpoint_final.pt` (or skip if insufficient data).

---

## Stage 5: Train Deck Evaluator

**Function:** `step_train_deck_bot(args, loop_num)`

**Purpose:** Train a deck quality evaluator (DeepSets/Set Transformer) on game
outcomes. Requires >= 10 games; otherwise skips.

**Skip guard:** `replay_db.game_count() < 10` -> stage is skipped entirely.

| # | Function / Program | File | Purpose | Input | Output |
|---|-------------------|------|---------|-------|--------|
| 5.1 | `replay_db.game_count()` | `data_collection/replay_db.py` | Check threshold (min 10) | None | `int` count |
| 5.2 | `find_best_checkpoint("deck_eval_finetune")` | `run_local_pipeline.py` | Find existing evaluator checkpoint to resume from | Prefix str | `Path | None` |
| 5.3 | `find_best_checkpoint("deck_eval_bootstrap")` | `run_local_pipeline.py` | Fallback: look for bootstrap checkpoint | Prefix str | `Path | None` |
| 5.4 | `run_step(label, cmd)` | `run_local_pipeline.py` | Execute subprocess | Description, command list | `int` exit code |
| 5.4a | **Subprocess:** `python scripts/train_deck_evaluator.py --games-db <replay.db> [--resume <checkpoint>]` | `scripts/train_deck_evaluator.py` | Train deck evaluator on game win/loss data; optionally resume from checkpoint | CLI args (games DB, optional resume path) | Updated checkpoint `checkpoints/deck_eval_finetune_best.pt` |

**Stage 5 Output:** Checkpoint file at `checkpoints/deck_eval_finetune_best.pt` (or skip if insufficient data).

---

## Stage 6: Evolve Decks

**Function:** `step_evolve_decks(args, loop_num)`

**Purpose:** Use the trained deck evaluator to evolve new deck compositions via
evolutionary search. Requires an evaluator checkpoint; otherwise skips.

**Skip guard:** No checkpoint found for `deck_eval_finetune` or `deck_eval_bootstrap` -> stage is skipped entirely.

| # | Function / Program | File | Purpose | Input | Output |
|---|-------------------|------|---------|-------|--------|
| 6.1 | `find_best_checkpoint("deck_eval_finetune")` / `("deck_eval_bootstrap")` | `run_local_pipeline.py` | Locate evaluator checkpoint | Prefix str | `Path | None` |
| 6.2 | `run_step(label, cmd)` | `run_local_pipeline.py` | Execute subprocess | Description, command list | `int` exit code |
| 6.2a | **Subprocess:** `python -m rl_agents.deck_search export --checkpoint <ckpt> --output-dir decks/generated/` | `rl_agents/deck_search.py` | Evolutionary search: for each hero, evolve card pools scored by the evaluator, export as deck `.txt` files | CLI args (checkpoint path, output dir) | New/updated `.txt` deck files in `decks/generated/` |
| 6.3 | `GENERATED_DIR.glob("*.txt")` | stdlib (Path) | Count generated deck files post-evolution | Directory path | `int` count of `.txt` files |

**Stage 6 Output:** Updated deck files in `decks/generated/` for next loop iteration (or skip if no evaluator exists).

---

## Stage 7: Benchmark

**Function:** `step_benchmark(args, loop_num)`

**Purpose:** Evaluate the trained IQL player bot against random, heuristic, and
previous-loop opponents. Requires an IQL checkpoint and >= 2 decks.

**Skip guard:** No IQL checkpoint at `checkpoints/iql/loop{N}/checkpoint_final.pt` or fewer than 2 deck files -> stage is skipped.

| # | Function / Program | File | Purpose | Input | Output |
|---|-------------------|------|---------|-------|--------|
| 7.1 | Check for IQL checkpoint at `checkpoints/iql/loop{N}/checkpoint_final.pt` | `run_local_pipeline.py` | Locate current player bot checkpoint | Path | `Path | None` (skip if missing) |
| 7.2 | `IQLPolicyAgent(checkpoint_path, player_id, device, seed, embedder_bundle)` | `rl_agents/evaluate_iql_vs_random.py` | Load trained IQL model as a callable agent | Checkpoint path, player_id=1, device, seed, bundle | `IQLPolicyAgent` instance |
| 7.3 | `RandomAgent(seed)` | `rl_agents/random_agent.py` | Create random baseline agent | Seed int | `RandomAgent` instance |
| 7.4 | `HeuristicBot(seed)` | `rl_agents/heuristic_bot.py` | Create heuristic baseline agent | Seed int | `HeuristicBot` instance |
| 7.5 | `_run_bench_games(p1_agent, p2_agent, label)` x3 opponent types | `run_local_pipeline.py` (inner function) | Run `n_bench=10` games and compute P1 win rate | Two agents, label str | `float` win rate |
| 7.5.1 | `GameRunRequest(...)` x10 per opponent | `rl_agents/game_backends.py` | Bundle game parameters | Deck paths, agents, CardDB, seeds, max_turns | `GameRunRequest` |
| 7.5.2 | `LocalEngineBackend().run_game(req)` x10 per opponent | `rl_agents/game_backends.py` -> `engine/engine.py` | Run one benchmark game | GameRunRequest | `GameState` with `.winner` |
| 7.6 | `IQLPolicyAgent(...)` for previous checkpoint (if `loop{N-1}` exists) | `rl_agents/evaluate_iql_vs_random.py` | Load previous-loop agent for comparison | Previous checkpoint path | `IQLPolicyAgent` or skip |

**Stage 7 Output:** Console table of win rates: `{vs Random: X%, vs Heuristic: Y%, vs Previous: Z%}`.

---

## Data Flow Diagram

```
decks/generated/*.txt
        |
        v
+--- Stage 1: Validate ------+
|  validate_all_decks()       |---> valid_decks: list[str]
|  (per deck: load_deck,      |
|   validate_deck_legality)   |
+-----------------------------+
        |
        v
+--- Stage 2: Run Games -----+
|  MatchupScheduler           |---> deck_pairs: list[(str,str)]
|  run_games()                |
|    per game:                |
|      new_game()             |---> GameState
|      EmbeddingRecorder      |---> transitions + embeddings ---> replay.db
|      _assign_rewards()      |---> reward/done updates -------> replay.db
|      record_local_game()    |---> deck metadata -------------> game_data.db
+-----------------------------+
        |
        v
+--- Stage 3: Verify --------+
|  game_count()               |---> Console: N games, M transitions
|  transition_count()         |
+-----------------------------+
        |
        v
+--- Stage 4: Train IQL -----+
|  subprocess: train_iql      |---> checkpoints/iql/loop{N}/checkpoint_final.pt
|  (reads replay.db)          |
+-----------------------------+
        |
        v
+--- Stage 5: Train Deck ----+
|  subprocess: train_deck     |---> checkpoints/deck_eval_finetune_best.pt
|  evaluator (reads           |
|  replay.db game outcomes)   |
+-----------------------------+
        |
        v
+--- Stage 6: Evolve --------+
|  subprocess: deck_search    |---> decks/generated/*.txt (updated)
|  export (uses evaluator     |
|  checkpoint)                |
+-----------------------------+
        |
        v
+--- Stage 7: Benchmark -----+
|  IQLPolicyAgent vs          |---> Console: win rate table
|  Random / Heuristic /       |
|  Previous                   |
+-----------------------------+
        |
        v
   loop_num += 1 ---> back to Stage 1
```

---

## Database Schemas

### replay.db (ReplayDB)

| Table | Columns | Purpose |
|-------|---------|---------|
| `games` | `game_id` PK, `p1_hero`, `p2_hero`, `winner`, `turns`, `ended_on_turn_cap`, `created_at` | One row per simulated game |
| `transitions` | `id` PK, `game_id` FK, `step_idx`, `player_id`, `phase`, `obs` (JSON), `action` (JSON), `reward` (float), `done` (int) | One row per agent decision point |
| `embeddings` | `transition_id` PK/FK, `state_embedding` (BLOB), `action_embedding` (BLOB) | Tensor embeddings per transition |

### game_data.db (GameDataStore)

| Table | Key Columns | Purpose |
|-------|-------------|---------|
| `decks` | `game_id`, `p1_decklist`, `p2_decklist`, hero names, winner, turns | Deck metadata and outcome per game |
| `transitions` | `game_id`, `step`, `state`, `action`, `reward`, etc. | Secondary transition store (non-critical) |

---

## Conditional Skip Guards Summary

| Stage | Guard Condition | Behavior When Skipped |
|-------|----------------|----------------------|
| Stage 4: Train IQL | `transition_count() < 500` | Prints SKIPPED message, returns immediately |
| Stage 5: Train Deck Evaluator | `game_count() < 10` | Prints SKIPPED message, returns immediately |
| Stage 6: Evolve Decks | No evaluator checkpoint found | Prints SKIPPED message, returns immediately |
| Stage 7: Benchmark | No IQL checkpoint or < 2 deck files | Prints SKIP message, returns immediately |

Additionally, each stage can be disabled via CLI flags: `--skip-validate`,
`--skip-games`, `--skip-player-train`, `--skip-deck-train`, `--skip-evolve`,
`--skip-benchmark`.
