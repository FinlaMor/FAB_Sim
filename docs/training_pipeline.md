# FAB Sim — Full Training Pipeline

End-to-end guide for training both the **Deck Bot** (evolutionary deck evaluator) and the **Player Bot** (IQL game-playing agent) from zero.

```
[Docker 32×]  →  [Collect games]  →  [Train Deck Bot]  →  [Evolve pools]
                       ↓                                        ↓
               [Train Player Bot]  ←←←←←←←←←←←←←  [Generate decks from pools]
                       ↓
               [Benchmark & iterate]
```

---

## Part 0 — One-Time Setup

Run these once per machine (or after a clean clone).

### 0.1 Clone and init submodule

```bash
git clone https://github.com/FinlaMor/FAB_Sim.git
cd FAB_Sim
git submodule update --init --recursive
```

### 0.2 Python environment

```bash
python -m venv venv
venv\Scripts\activate

# Core deps (CPU-only)
pip install requests beautifulsoup4 h5py

# PyTorch — pick one:
pip install torch --index-url https://download.pytorch.org/whl/cu121   # CUDA 12.1
pip install torch                                                        # CPU
pip install torch-directml                                               # AMD/DirectML
```

### 0.3 Build the Docker image (first time only)

```bash
cd third_party/Talishar_official
docker compose -f docker-compose.multi.yml build
cd ../..
```

This compiles the PHP/Apache image (~3–5 min). Subsequent starts use the cached image.

---

## Part 1 — Start 32 Docker Containers

**Always start from the repo root.**

```bash
cd third_party/Talishar_official
docker compose -f docker-compose.multi.yml up -d \
  web-0 web-1 web-2 web-3 web-4 web-5 web-6 web-7 \
  web-8 web-9 web-10 web-11 web-12 web-13 web-14 web-15 \
  web-16 web-17 web-18 web-19 web-20 web-21 web-22 web-23 \
  web-24 web-25 web-26 web-27 web-28 web-29 web-30 web-31
cd ../..
```

This starts `web-0` through `web-31` on ports **8080–8111**, along with their MySQL and Redis dependencies (32 of each — 96 containers total). Uses ~3 GB RAM.

**Verify:**

```bash
docker ps --format "{{.Names}}" | grep "talishar_official-web" | wc -l
# Should print: 32
```

Wait ~30 seconds on first boot for MySQL to import the schema before sending games.

---

## Part 2 — Collect Game Data

### 2.1 The 32-container collection command

Run from the **repo root** with venv active:

```bash
python scripts/run_talishar_games.py \
  --base-url "http://localhost:8080/game,http://localhost:8081/game,http://localhost:8082/game,http://localhost:8083/game,http://localhost:8084/game,http://localhost:8085/game,http://localhost:8086/game,http://localhost:8087/game,http://localhost:8088/game,http://localhost:8089/game,http://localhost:8090/game,http://localhost:8091/game,http://localhost:8092/game,http://localhost:8093/game,http://localhost:8094/game,http://localhost:8095/game,http://localhost:8096/game,http://localhost:8097/game,http://localhost:8098/game,http://localhost:8099/game,http://localhost:8100/game,http://localhost:8101/game,http://localhost:8102/game,http://localhost:8103/game,http://localhost:8104/game,http://localhost:8105/game,http://localhost:8106/game,http://localhost:8107/game,http://localhost:8108/game,http://localhost:8109/game,http://localhost:8110/game,http://localhost:8111/game" \
  --workers 32 \
  --num-games 1000 \
  --random-decks \
  --max-turns 30 \
  --benchmark
```

**Output:** `data/talishar_games.db` — each row stores both decklists (JSON) + winner + HP + turn count.

### 2.2 Data targets

| Games | Use |
|-------|-----|
| 100   | Validate pipeline end-to-end |
| 1 000 | Minimum signal for deck evaluator fine-tuning |
| 5 000 | Minimum for IQL player bot training |
| 10 000+ | Robust fine-tuning for both bots |

### 2.3 Collecting IQL training data (engine-based, no Docker required)

The IQL player bot needs state/action/reward transitions, not just game outcomes. These come from `rl_agents/collect_iql_mixed_data.py`, which runs games through the Python engine (no Docker needed):

```bash
python -m rl_agents.collect_iql_mixed_data \
  --num-games 500 \
  --backend engine
```

**Output:** `data_collection/replay_*.db` — per-step transitions with full embedded state.

---

## Part 3 — Train the Deck Bot

### 3.1 Scrape meta data (do this first, and after each new set)

```bash
python scripts/scrape_fablazing.py
# or for specific heroes:
python scripts/scrape_fablazing.py --heroes kayo-underhanded-cheat oscilio-constella-intelligence
```

**Output:** `data/fablazing_meta.db`

### 3.2 Generate heuristic decks

```bash
python scripts/generate_heuristic_decks.py --all --mutate 3
```

**Output:** `decks/generated/*.txt` (currently ~144 decks)

### 3.3 Bootstrap training (no game data needed)

```bash
python scripts/train_deck_evaluator.py \
  --bootstrap \
  --model set_transformer \
  --epochs 100 \
  --device cuda
```

**Output:** `checkpoints/deck_eval_bootstrap_best.pt`

Healthy training: accuracy reaches 70–85%. >90% means the labels are overfitting noise.

### 3.4 Fine-tune on real game data

Requires at least ~100 games in `data/talishar_games.db`:

```bash
python scripts/train_deck_evaluator.py \
  --games-db data/talishar_games.db \
  --resume checkpoints/deck_eval_bootstrap_best.pt \
  --epochs 50 \
  --device cuda
```

**Output:** `checkpoints/deck_eval_finetune_best.pt`

### 3.5 Evolutionary deck search (optional, improves deck pool quality)

```bash
python -m rl_agents.deck_search search \
  --hero kayo-underhanded-cheat \
  --checkpoint checkpoints/deck_eval_finetune_best.pt \
  --pop-size 100 \
  --generations 50
```

### 3.6 Tournament benchmark

```bash
python -m rl_agents.deck_search tournament \
  --checkpoint checkpoints/deck_eval_finetune_best.pt \
  --players 256 \
  --rounds 5
```

---

## Part 4 — Train the Player Bot (IQL)

The player bot learns to play FAB from recorded game transitions via Implicit Q-Learning.

### 4.1 Collect transition data

```bash
python -m rl_agents.collect_iql_mixed_data --num-games 500 --backend engine
```

Or via Talishar (slower per game but uses real PHP engine):

```bash
python scripts/run_talishar_games.py \
  --base-url "http://localhost:8080/game,...(32 URLs)" \
  --workers 32 --num-games 1000 --random-decks --max-turns 30
```

### 4.2 Train IQL

```bash
python -m rl_agents.train_iql \
  --db-path data_collection/replay_latest.db \
  --steps 10000 \
  --batch-size 256 \
  --hidden-dim 512 \
  --device cuda \
  --out-dir data_collection/iql_runs \
  --run-name v1
```

**Output:** `data_collection/iql_runs/v1/checkpoint_best.pt`

Resume from checkpoint:

```bash
python -m rl_agents.train_iql \
  --db-path data_collection/replay_latest.db \
  --resume-from data_collection/iql_runs/v1/checkpoint_best.pt \
  --steps 5000
```

### 4.3 Benchmark player bot vs random agent

```bash
python scripts/bench_player_bot.py \
  --checkpoint data_collection/iql_runs/v1/checkpoint_best.pt \
  --base-url "http://localhost:8080/game" \
  --num-games 100
```

**Output:** prints `PLAYER_BOT_WIN_RATE 0.xxx`. A win rate >0.55 against pure random is the first meaningful signal.

---

## Part 5 — Automated Pipeline (recommended for regular runs)

`scripts/run_pipeline.py` orchestrates both bots end-to-end. It auto-integrates IQL training after each game collection loop.

### 5.1 Standard multi-loop run

```bash
python scripts/run_pipeline.py \
  --loops 5 \
  --games-per-loop 200 \
  --talishar-urls "http://localhost:8080/game,http://localhost:8081/game,...(32 URLs)"
```

### 5.2 Skip flags (for resuming mid-pipeline)

```bash
# Skip scraping (already have meta DB)
python scripts/run_pipeline.py --skip-scrape --loops 3 --games-per-loop 200

# Skip bootstrap (already have a checkpoint)
python scripts/run_pipeline.py --skip-scrape --skip-bootstrap \
  --resume checkpoints/deck_eval_bootstrap_best.pt \
  --loops 3 --games-per-loop 500

# No Docker at all — benchmark bootstrap only
python scripts/run_pipeline.py --skip-games --skip-finetune
```

### 5.3 Full pipeline with 32 containers

```bash
python scripts/run_pipeline.py \
  --skip-scrape \
  --model set_transformer \
  --loops 5 \
  --games-per-loop 500 \
  --talishar-urls "http://localhost:8080/game,http://localhost:8081/game,http://localhost:8082/game,http://localhost:8083/game,http://localhost:8084/game,http://localhost:8085/game,http://localhost:8086/game,http://localhost:8087/game,http://localhost:8088/game,http://localhost:8089/game,http://localhost:8090/game,http://localhost:8091/game,http://localhost:8092/game,http://localhost:8093/game,http://localhost:8094/game,http://localhost:8095/game,http://localhost:8096/game,http://localhost:8097/game,http://localhost:8098/game,http://localhost:8099/game,http://localhost:8100/game,http://localhost:8101/game,http://localhost:8102/game,http://localhost:8103/game,http://localhost:8104/game,http://localhost:8105/game,http://localhost:8106/game,http://localhost:8107/game,http://localhost:8108/game,http://localhost:8109/game,http://localhost:8110/game,http://localhost:8111/game"
```

The pipeline runs Ctrl+C-safe — it finishes the current step before exiting cleanly.

---

## Part 6 — Iteration Loop

After an initial run, repeat this cycle to improve both bots:

```
1. Collect games (32 containers, --random-decks)
2. Fine-tune deck evaluator on new games
3. Evolve deck pools with updated evaluator
4. Export evolved pools as deck files → use in next collection round
5. Train IQL on new transition data
6. Benchmark IQL vs random agent
7. Run tournament simulation → compare standings vs previous run
8. Repeat
```

Checkpoints are cumulative — always `--resume` from the previous best to avoid throwing away prior learning.

---

## Part 7 — New Set Release Checklist

When a new FAB set releases (new cards, new heroes, rotation):

### 7.1 Update Talishar

```bash
cd third_party/Talishar_official
git pull origin main
cd ../..
git add third_party/Talishar_official
git commit -m "bump Talishar submodule to latest"
```

Rebuild the Docker image to pick up new PHP card logic:

```bash
cd third_party/Talishar_official
docker compose -f docker-compose.multi.yml build
cd ../..
```

### 7.2 Re-scrape fablazing

New set → new cards appear in play-rate data:

```bash
python scripts/scrape_fablazing.py
```

Check what changed:

```bash
python scripts/scrape_fablazing.py --summary
```

### 7.3 Regenerate heuristic decks

```bash
python scripts/generate_heuristic_decks.py --all --mutate 3
```

This rebuilds `decks/generated/` using updated fablazing play rates. Old decks with rotated cards will fail legality checks and be dropped automatically.

### 7.4 Re-bootstrap the deck evaluator

The card vocabulary grows with new cards. The old checkpoint's embedding layer won't match the new vocab size — start fresh:

```bash
python scripts/train_deck_evaluator.py \
  --bootstrap \
  --model set_transformer \
  --epochs 100 \
  --device cuda
```

Do **not** `--resume` an old checkpoint after a vocab-changing set release.

### 7.5 Collect fresh game data

Old `data/talishar_games.db` games played with pre-rotation decks are still valid for training, but you'll want new games using the updated card pool. Either:

- Run a fresh collection batch with the new decks (appends to the existing DB)
- Or delete `data/talishar_games.db` and start clean if the rotation was large

### 7.6 Retrain IQL from scratch (if rotation is large)

The IQL embedder encodes card slugs — if new cards appear, the embedder bundle is stale. Delete old IQL data and retrain:

```bash
rm -rf data_collection/replay_*.db
python -m rl_agents.collect_iql_mixed_data --num-games 500 --backend engine
python -m rl_agents.train_iql --db-path data_collection/replay_latest.db --steps 10000
```

---

## Part 8 — Common Issues

### "port is already allocated" on `docker compose up`

One or more web containers are already running (from a previous session). Check and start only what's missing:

```bash
docker ps --format "{{.Names}}" | grep "talishar_official-web" | wc -l
# If 32, all containers are already up — nothing to do
```

If a subset is running and you need to bring up the rest:

```bash
docker compose -f docker-compose.multi.yml up -d web-0 web-1 ...  # only missing ones
```

### MySQL keeps restarting on first boot

Schema import from `Database/` can take 30–60 seconds on cold start. Wait, then:

```bash
docker compose -f docker-compose.multi.yml ps | grep mysql
# Wait until all show "Up" (not "Restarting")
```

### Games hanging / hitting game-timeout

- Reduce `--max-turns` (30 is enough for decisive CC games)
- Add `--max-actions 1500` to hard-cap per-game iterations
- Increase `--game-timeout 600` if games are completing but slowly
- Check for PHP errors: `docker logs talishar_official-web-0-1`

### Most games skipped (e.g., 28/2000 completed)

Too many workers for one container. Rule: **never exceed 1 worker per container**. The 32-container command above uses exactly `--workers 32` matching 32 containers.

### `ModuleNotFoundError: No module named 'requests'`

Virtual environment is not active or deps weren't installed:

```bash
venv\Scripts\activate
pip install requests beautifulsoup4 h5py
```

### Deck evaluator accuracy >95% at bootstrap

Labels are soft (4-tier: 0.75/0.60/0.40/0.20). >90% accuracy means the model is memorising noise — reduce `--epochs` or increase `--dropout`.

### IQL win rate stuck at ~0.50 vs random

Normal until ~5 000 transitions. Below that threshold there isn't enough data for meaningful Q-function estimation. Collect more games and retrain.

### `ValueError: Dataset payload missing required keys`

The `.db` path passed to `train_iql` is a Talishar games DB (deck outcomes), not a replay transitions DB. IQL training needs a replay DB from `collect_iql_mixed_data`. These are separate databases.

### Docker image out of date after Talishar update

Always rebuild after pulling new Talishar PHP code:

```bash
cd third_party/Talishar_official
docker compose -f docker-compose.multi.yml build
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Start 32 containers | `docker compose -f docker-compose.multi.yml up -d web-{0..31}` (from `third_party/Talishar_official`) |
| Collect 1000 games (32 containers) | See Part 2.1 above |
| Scrape fablazing | `python scripts/scrape_fablazing.py` |
| Generate decks | `python scripts/generate_heuristic_decks.py --all --mutate 3` |
| Bootstrap deck bot | `python scripts/train_deck_evaluator.py --bootstrap --model set_transformer --epochs 100` |
| Fine-tune deck bot | `python scripts/train_deck_evaluator.py --games-db data/talishar_games.db --resume checkpoints/deck_eval_bootstrap_best.pt` |
| Collect IQL data | `python -m rl_agents.collect_iql_mixed_data --num-games 500 --backend engine` |
| Train player bot | `python -m rl_agents.train_iql --db-path data_collection/replay_latest.db --steps 10000` |
| Benchmark player bot | `python scripts/bench_player_bot.py --checkpoint <ckpt> --num-games 100` |
| Full automated pipeline | `python scripts/run_pipeline.py --skip-scrape --loops 5 --games-per-loop 500` |
| Stop all containers | `docker compose -f docker-compose.multi.yml down` (from `third_party/Talishar_official`) |
