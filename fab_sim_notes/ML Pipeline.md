# ML Pipeline

See also: [[Architecture Hub]] | [[Engine Overview]]

## Goal
AlphaZero-style self-play. Current approach: IQL (Independent Q-Learning) with shaped rewards.

## Components

### `encoder/`
Converts `GameState` → tensors for the neural network.
- `gamestate_embedder.py` — main entry: state → feature vector
- `action_embedder.py` — action → embedding
- `card_embedder.py` — card → embedding
- `feature_schema.py` — defines feature columns (~45 numerical + ~10 JSON zone fields)
- `game_transformer.py` — transformer architecture over game state
- `pretrain_masked.py` — masked pretraining for card embeddings

### `rl_agents/`
- `iql.py` — IQL model definition
- `train_iql.py` — training loop
- `random_agent.py` — baseline agent
- `heuristic_bot.py` — hand-crafted heuristic baseline
- `game_backends.py` — adapter: engine `GameState` → RL environment interface
- `local_game_runner.py` — run games locally
- `evaluate_iql_vs_random.py` — evaluation script
- `play_vs_iql.py` — human vs IQL
- `deck_evaluator.py`, `deck_search.py`, `deck_validator.py` — deck tools
- `collect_iql_mixed_data.py` — data collection with mixed agents

### `data_collection/`
- `replay_db.py` — SQLite replay storage

### Scripts
- `scripts/collect_data.py` — batch game runner, --games / --db / --matchup flags
- `scripts/build_slug_index.py` — rebuild slug index from card CSV

## IQL Training History
| Version | Steps | Reward | Notes |
|---------|-------|--------|-------|
| v1 | ~500k | binary win/loss | baseline |
| v2 | 1,579,531 | shaped | 98.2% vs random |
| v3 | 3,365,841 | turn_penalty (α=0.001) | v3 lost 78.8% vs v2 — needs H2H re-eval |

## Data Schema (steps table)
- `my_*` / `opp_*` — player stats (life, resources, hand_size, etc.)
- `in_combat`, `combat_*` — combat state fields
- `action_type`, `action_json`, `chosen_action_idx` — decision data
- `legal_actions_count`, `legal_action_types` — action mask info
- `reward`, `is_terminal` — RL labels
- `j_*` — JSON zone snapshots

## IQL Assembly
`(s, a, r, s', done)` assembled at query time: `s'` = next step for same player in same game.

## Next Steps
- [ ] Run fresh v3 vs v2 H2H after turn_penalty retraining
- [ ] Expand training once Victor/Mario decks implemented
- [ ] Implement `build_winrate_deck()` once win-rate data exists
