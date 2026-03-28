# Deck Bot Pipeline: End-to-End Guide

Build tournament-quality FAB decks with ML-guided evolutionary search.

```
Scrape meta data  -->  Train deck evaluator  -->  Evolve deck pools  -->  Simulate tournaments
       |                       ^                                               |
       v                       |                                               v
   Generate decks  -->  Run Talishar games  --->  Fine-tune evaluator  -->  Benchmark
```

---

## Prerequisites

- Python 3.10+ with venv
- Docker Desktop (for Talishar game sim)
- GPU recommended (CUDA) but CPU works

```bash
cd C:\Users\Joseph\Desktop\FAB_Sim
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/Mac
pip install torch --index-url https://download.pytorch.org/whl/cu121  # or cpu
pip install requests beautifulsoup4
```

---

## Phase 1: Collect Meta Data

Scrape card play rates, win rates, and hero statistics from fablazing.com. This data is used **only during bootstrapping** (Phase 2.1) and heuristic deck generation — it is not referenced by fine-tuning, deck search, or tournament phases.

### 1.1 Scrape Fablazing

```bash
# Scrape all Classic Constructed heroes (~36 heroes, takes ~2 minutes)
python scripts/scrape_fablazing.py

# Or scrape specific heroes
python scripts/scrape_fablazing.py --heroes kayo-underhanded-cheat oscilio-constella-intelligence

# List available hero slugs
python scripts/scrape_fablazing.py --list-heroes

# Check what was collected
python scripts/scrape_fablazing.py --summary
```

**Output:** `data/fablazing_meta.db` — SQLite with:
- `heroes` table: hero_slug, win_rate, total_matches
- `card_stats` table: card_slug, hero_slug, frequency, avg_copies, win_rate

### 1.2 Generate Heuristic Decks

Build starter decks from play-rate data. These seed the game runner and evolutionary search.

```bash
# Generate decks for all heroes
python scripts/generate_heuristic_decks.py --all

# Generate with mutated variants (for diversity in game data)
python scripts/generate_heuristic_decks.py --all --mutate 3

# Single hero
python scripts/generate_heuristic_decks.py --hero kayo-underhanded-cheat
```

**Output:** `decks/generated/*.txt` — FaBrary-format deck files.

---

## Phase 2: Train the Deck Evaluator

The evaluator is a neural network that scores decks: given (hero, card_set, opponent_hero), it predicts P(win). Accepts both 80-card pools and 60-card match decks. Two architectures are available:

| Model | Strengths |
|-------|-----------|
| DeepSets | Fast, good baseline, mean/max pooling |
| Set Transformer | Captures card synergies via self-attention, hero skip connection |

Exact parameter counts depend on vocabulary size. Run bootstrap training to see the count logged at startup.

### 2.1 Bootstrap Training (No Game Data Needed)

Train on synthetic labels derived from fablazing play rates (from `data/fablazing_meta.db`). "Good" decks (high-frequency cards) get high labels; "bad" decks (random cards) get low labels. This is the **only** training phase that uses fablazing data.

```bash
# DeepSets (faster, start here)
python scripts/train_deck_evaluator.py --bootstrap --model deepsets --epochs 50

# Set Transformer (better synergy modeling)
python scripts/train_deck_evaluator.py --bootstrap --model set_transformer --epochs 50

# Tune hyperparameters
python scripts/train_deck_evaluator.py --bootstrap \
    --model set_transformer \
    --embed-dim 64 \
    --hidden-dim 128 \
    --n-heads 4 \
    --n-layers 2 \
    --dropout 0.1 \
    --lr 3e-4 \
    --batch-size 64 \
    --samples-per-hero 200 \
    --epochs 100 \
    --device cuda
```

**Output:** `checkpoints/deck_eval_bootstrap_best.pt`, `checkpoints/deck_eval_bootstrap_final.pt`

**What to look for:**
- Train accuracy should reach 70-85% (not 95%+ — labels are soft/noisy by design)
- Val loss should decrease steadily; early stopping triggers after 10 epochs without improvement
- Bootstrap labels use a 4-tier system (0.75 / 0.60 / 0.40 / 0.20) with hero win-rate modulation

### 2.2 Resume From Checkpoint

```bash
python scripts/train_deck_evaluator.py --bootstrap \
    --resume checkpoints/deck_eval_bootstrap_best.pt \
    --epochs 30
```

---

## Phase 3: Run Talishar Games (Optional — Improves Model)

Play actual games through the Talishar PHP engine to collect real win/loss data. This is optional for initial exploration but critical for model accuracy.

### 3.1 Start Talishar (Docker)

```bash
# Single instance
cd third_party/Talishar_official
docker compose up -d
# Accessible at http://localhost:8080/game

# Multi-instance (4 parallel containers, ~4x throughput)
docker compose -f docker-compose.multi.yml up -d
# Ports 8080, 8081, 8082, 8083
```

### 3.2 Run Games

```bash
# Single game with specific decks
python scripts/run_talishar_games.py \
    --p1-deck decks/kayo_underhanded_cheat_CC_lite.txt \
    --p2-deck decks/arakni_marionette_CC_lite.txt

# Batch of random-deck games (best for data diversity)
python scripts/run_talishar_games.py \
    --random-decks \
    --num-games 100 \
    --workers 4

# Multi-container parallel collection
python scripts/run_talishar_games.py \
    --base-url "http://localhost:8080/game,http://localhost:8081/game,http://localhost:8082/game,http://localhost:8083/game" \
    --random-decks \
    --num-games 200 \
    --workers 4

# With custom timeout and turn cap
python scripts/run_talishar_games.py \
    --random-decks \
    --num-games 200 \
    --workers 4 \
    --max-turns 50 \
    --game-timeout 300

# Practice dummy mode (single player, no P2 deck needed)
python scripts/run_talishar_games.py --mode dummy

# Dry run without saving to DB
python scripts/run_talishar_games.py --random-decks --no-save
```

**Output:** `data/talishar_games.db` — each game stores both decklists (JSON) + winner + HP + turn count in the `decks` table.

**Data targets:**
- 100 games: enough to validate fine-tuning pipeline
- 1K games: minimum for meaningful signal
- 10K+ games: target for robust fine-tuning

### 3.3 Fine-Tune on Game Data

```bash
# Fine-tune the bootstrap model on real game outcomes
python scripts/train_deck_evaluator.py \
    --games-db data/talishar_games.db \
    --resume checkpoints/deck_eval_bootstrap_best.pt \
    --epochs 50

# Or bootstrap + fine-tune in one run
python scripts/train_deck_evaluator.py \
    --bootstrap \
    --games-db data/talishar_games.db \
    --model set_transformer \
    --epochs 50
```

> **Note:** Fine-tuning uses only game outcome data from `talishar_games.db` — no external meta data is referenced during this phase.

Fine-tuning uses 0.1x the base learning rate. Each game produces two training samples: (hero_1, deck_1, hero_2, won) and (hero_2, deck_2, hero_1, won).

**Output:** `checkpoints/deck_eval_finetune_best.pt`

---

## Phase 4: Evolutionary Deck Search

Use the trained evaluator to evolve optimal 80-card pools via genetic algorithm.

### 4.1 Single Hero Search

```bash
# Find the best pool(s) for a specific hero
python -m rl_agents.deck_search search \
    --hero kayo-underhanded-cheat \
    --checkpoint checkpoints/deck_eval_bootstrap_best.pt \
    --pop-size 100 \
    --generations 50
```

**What happens:**
1. Initializes 100 pools with diverse `flex_depth` values (0-20)
2. Scores each pool through Stage 2 matchup selection against ~20 meta-sampled opponents
3. Selects top 20% as elite, fills rest via crossover + mutation
4. After 50 generations, returns a **Pareto front** of 1-4 diverse pools

**Output explains:**
- `flex_depth=0-5`: aggro — locked 60-card core, no sideboarding
- `flex_depth=6-14`: midrange — balanced core + flex slots
- `flex_depth=15-20`: control/fatigue — maximum matchup adaptation

### 4.2 Understanding Multi-Pool Output

The search returns multiple pools when a hero has viable archetypes at different flex depths. For example, Kayo might produce:
```
Pool 1/3 (fitness=0.6234, flex_depth=3, archetype=aggro)
Pool 2/3 (fitness=0.6180, flex_depth=12, archetype=midrange)
Pool 3/3 (fitness=0.6050, flex_depth=18, archetype=control)
```

Pools are filtered by:
- **Fitness gap**: dropped if >0.03 below the best
- **Jaccard distance**: collapsed if Jaccard distance < 0.10 from a better pool (nearly identical card lists)

---

## Phase 5: Tournament Simulation (Benchmarking)

Simulate a full Swiss tournament to benchmark the evaluator and compare archetypes.

### 5.1 Run a Tournament

```bash
# Standard tournament (per-round pool selection)
python -m rl_agents.deck_search tournament \
    --checkpoint checkpoints/deck_eval_bootstrap_best.pt \
    --players 256 \
    --rounds 5 \
    --pool-pop 50 \
    --pool-gens 20

# Locked strategy (choose one pool at registration, like real tournaments)
python -m rl_agents.deck_search tournament \
    --checkpoint checkpoints/deck_eval_bootstrap_best.pt \
    --players 256 \
    --rounds 5 \
    --strategy locked
```

### 5.2 Pool Selection Strategies

| Strategy | Flag | Behavior |
|----------|------|----------|
| **per_round** | `--strategy per_round` | Before each round, pick the best pool + 60-card deck for the specific opponent. Maximum adaptation. |
| **locked** | `--strategy locked` | Pick one pool at registration. Select 60-card decks from that pool each round. Standard tournament rules. |

### 5.3 Reading Tournament Results

```
Rank   Hero                                Archetype    Pools  Flex   W  -  L    Pts
--------------------------------------------------------------------------------
1      vynnset-iron-maiden                 midrange         2    10   5  -  0    5.0
2      kayo-underhanded-cheat              aggro            3     3   4  -  1    4.0
3      oscilio-constella-intelligence      control          1    17   4  -  1    4.0
...

Archetype distribution (top 20):
  midrange          8
  aggro             7
  control           3
  fatigue           2

Hero archetypes (top 20):
  kayo-underhanded-cheat              aggro, aggro
  oscilio-constella-intelligence      control
  vynnset-iron-maiden                 midrange
```

**Key metrics to watch:**
- Is the hero distribution diverse across archetypes? (Heroes are sampled uniformly.)
- Are diverse archetypes emerging, or does one flex_depth dominate?
- Do fine-tuned models produce different standings than bootstrap-only models?

---

## Phase 6: Iteration Loop

The system improves through a cycle of play, train, evolve, benchmark. After the initial bootstrap, the iteration loop is entirely self-improving — it relies only on game outcomes:

```
1. Train evaluator (bootstrap)
         |
2. Evolve pools with evaluator
         |
3. Export top pools as deck files
         |
4. Play those decks in Talishar  -->  data/talishar_games.db
         |
5. Fine-tune evaluator on game outcomes
         |
6. Re-evolve pools with improved evaluator
         |
7. Re-simulate tournament  -->  compare standings
         |
   Repeat from step 4
```

### Export Evolved Pools as Playable Decks

The evolved pools aren't directly in FaBrary format yet. To play them in Talishar, generate heuristic decks seeded from the pool data, or manually create deck files from the search output.

### Compare Tournament Runs

Run tournaments after each fine-tuning round with the same seed to compare:

```bash
# Before fine-tuning
python -m rl_agents.deck_search tournament \
    --checkpoint checkpoints/deck_eval_bootstrap_best.pt \
    --players 128 --rounds 5 --seed 42

# After fine-tuning
python -m rl_agents.deck_search tournament \
    --checkpoint checkpoints/deck_eval_finetune_best.pt \
    --players 128 --rounds 5 --seed 42
```

Compare the final standings — hero ordering, archetype distribution, and point spreads should shift as the model learns from real game data.

---

## Automated Pipeline

`scripts/run_pipeline.py` runs the entire process end-to-end as a single command. Each step is a subprocess — if one fails, the pipeline halts with a clear error. It auto-detects Talishar availability and skips game collection gracefully if Docker is down.

```bash
# Full pipeline with defaults
python scripts/run_pipeline.py

# Skip scraping (already have meta DB)
python scripts/run_pipeline.py --skip-scrape

# No Docker — skip games, just bootstrap + benchmark
python scripts/run_pipeline.py --skip-games --skip-finetune

# Multiple improvement loops (games -> finetune -> tournament, repeated)
python scripts/run_pipeline.py --skip-scrape --loops 3 --games-per-loop 200

# Set Transformer with multi-container Talishar
python scripts/run_pipeline.py --model set_transformer \
    --talishar-urls "http://localhost:8080/game,http://localhost:8081/game"

# Resume from existing checkpoint, skip early steps
python scripts/run_pipeline.py --skip-scrape --skip-bootstrap \
    --resume checkpoints/deck_eval_bootstrap_best.pt

# Smaller tournament for faster iteration
python scripts/run_pipeline.py --players 64 --rounds 3 --pool-pop 30 --pool-gens 10
```

**Skip flags:** `--skip-scrape`, `--skip-decks`, `--skip-bootstrap`, `--skip-games`, `--skip-finetune`, `--skip-tournament`

The pipeline supports Ctrl+C graceful interruption — it finishes the current step and prints a final summary.

---

## Quick Reference

| Task | Command |
|------|---------|
| **Full pipeline** | `python scripts/run_pipeline.py` |
| **Pipeline (no Docker)** | `python scripts/run_pipeline.py --skip-games --skip-finetune` |
| Scrape meta | `python scripts/scrape_fablazing.py` |
| List hero slugs | `python scripts/scrape_fablazing.py --list-heroes` |
| Generate decks | `python scripts/generate_heuristic_decks.py --all --mutate 3` |
| Bootstrap train | `python scripts/train_deck_evaluator.py --bootstrap` |
| Start Talishar | `cd third_party/Talishar_official && docker compose up -d` |
| Run games | `python scripts/run_talishar_games.py --random-decks --num-games 100` |
| Fine-tune | `python scripts/train_deck_evaluator.py --games-db data/talishar_games.db --resume checkpoints/deck_eval_bootstrap_best.pt` |
| Search (1 hero) | `python -m rl_agents.deck_search search --hero <slug> --checkpoint <ckpt>` |
| Tournament | `python -m rl_agents.deck_search tournament --checkpoint <ckpt> --players 256` |
| Check DB stats | `python scripts/scrape_fablazing.py --summary` |

---

## File Map

```
FAB_Sim/
  scripts/
    run_pipeline.py              # Automated end-to-end pipeline
    scrape_fablazing.py          # Step 1: scrape meta data
    generate_heuristic_decks.py  # Step 1: build starter decks
    train_deck_evaluator.py      # Step 2: bootstrap + fine-tune
    run_talishar_games.py        # Step 3: collect game data
    preprocess_talishar.py       # (IQL pipeline, not deck bot)
  rl_agents/
    deck_evaluator.py            # DeepSets / Set Transformer models, CardVocab, datasets
    deck_search.py               # Evolutionary search, tournament sim, CLI
  data/
    fablazing_meta.db            # Scraped card/hero stats
    talishar_games.db            # Game outcomes + decklists
  checkpoints/
    deck_eval_bootstrap_*.pt     # Bootstrap model checkpoints
    deck_eval_finetune_*.pt      # Fine-tuned model checkpoints
  decks/
    *.txt                        # Hand-written decks (FaBrary format)
    generated/                   # Heuristic-generated decks
  third_party/Talishar_official/
    docker-compose.yml           # Single Talishar instance
    docker-compose.multi.yml     # 4 parallel instances (ports 8080-8083)
```
