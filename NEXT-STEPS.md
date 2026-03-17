# FAB TCG AI System — Next Steps & Implementation Plan

---

## Overview

This document tracks the development roadmap for the Flesh and Blood TCG AI system. The system currently consists of:

- **Game engine** — local `engine.py` + Talishar PHP backend adapter (Docker, multi-container)
- **Data collection** — automated PvP game runner with parallel Docker containers, SQLite storage
- **IQL offline RL** — Implicit Q-Learning trainer with transformer policy network
- **Card/gamestate/action embedders** — encode game state for the policy network
- **Fablazing scraper** — per-hero card play rates, win rates, and meta data from 74K+ CC matches
- **ReplayDB** — HDF5-based preprocessed transition storage

---

## Completed Work

### Data Collection Pipeline (done)

- Multi-container Docker setup (`docker-compose.multi.yml`) — 4 independent Talishar instances on ports 8080-8083
- `scripts/run_talishar_games.py` — parallel game runner with round-robin container assignment
- HTTP optimizations: fused ProcessInput+GetState calls (1 round-trip per action)
- SQLite game storage with full game metadata
- `--random-decks` mode for diverse data generation across 7 deck files
- Fixed: PHP display_errors, Docker Games/ permissions, action cap bug, Windows signal handling

### IQL Training Pipeline (done)

- `rl_agents/talishar_iql.py` — IQL trainer with transformer policy
- `scripts/preprocess_talishar.py` — HDF5 chunked preprocessing with vocab metadata
- Signal-based graceful interruption (Ctrl+C stops after current step)
- Checkpoint save on interruption

### Fablazing Meta Scraper (done)

- `scripts/scrape_fablazing.py` — scrapes per-hero card stats from fablazing.com
- 33 CC heroes scraped, 619 unique cards, 831 card-hero stat entries
- Data stored in `data/fablazing_meta.db` with play rate, avg copies, win rate per card per hero
- Available data: frequency (0.0-1.0), avg_copies, win_rate, match_count

---

## Phase 1: Train a Player Bot That Beats Random (in progress)

### Status

Data collection is running (200-game batches via multi-container). IQL training pipeline is functional but needs sufficient training data volume (target: 10K+ games).

### Remaining Steps

1. Collect 10K+ game transitions via multi-container setup (~100 games/hour with 4 containers)
2. Preprocess collected data to HDF5 format
3. Train IQL to convergence, monitor TD loss and Q-value stability
4. Evaluate trained policy vs random bot over 500+ games per hero matchup
5. Tune reward shaping if win rate plateaus below 50%

### Success Criteria

- Policy wins >50% (p < 0.05) against random bot across 3+ hero matchups
- No degenerate behaviors (always passing, always pitching same card)

---

## Phase 2: Self-Play Training Loop

### What It Means

Once the policy beats random play, shift to self-play: current policy plays against a lagged checkpoint, producing higher-quality transitions. Required for both the draft bot and deck builder — they need a competent player bot to evaluate deck quality.

### Key Steps

1. Self-play runner with lagged opponent (updated every N games)
2. Diversity mechanisms: epsilon-greedy, temperature scaling, random-bot injection
3. Elo tracking across checkpoints
4. Regression suite confirming policy still beats random after each cycle

---

## Phase 3: Deck Builder (`deck_bot`)

### Two-Stage Architecture

Rather than generating decks directly (combinatorial explosion: C(2000,60)), the approach mirrors real tournament play:

**Stage 1 — Pool Builder:** Select all 80 cards for a hero (tournament registration). An evaluative scorer predicts P(win | hero, card_pool) and evolutionary search optimizes the pool.

**Stage 2 — Matchup Selector:** Before each match, given your 80-card pool + opponent's hero, select which ~60 deck cards + equipment to actually play. Enables matchup-specific sideboarding.

### Tournament Simulation

- **200-300 simulated players**, hero distribution sampled from fablazing meta percentages (e.g., Vynnset 7.5%, Oscilio 6.1%, Arakni 5.7%, ...)
- Each player builds an 80-card pool via Stage 1 evolutionary search
- Swiss pairings for N rounds
- Before each round: Stage 2 matchup-specific deck selection
- Model scores determine match outcomes

### Model Progression

**Phase 3a — DeepSets baseline (done):**
- Card embeddings (learned + count projection) + mean/max pooling + MLP head
- Treats deck as unordered set (correct — card order doesn't matter)
- Inputs: hero_id, card_ids, counts, opponent_hero_id
- ~127K params, trainable on synthetic fablazing data
- Validates data pipeline and provides baseline

**Phase 3b — Set Transformer (done):**
- Self-attention between card embeddings: every card "sees" every other card
- Hero prepended as context token (card interactions are hero-conditioned)
- Captures synergies: "Mask of Momentum is strong with long attack chains"
- embed_dim=64, n_heads=4, n_layers=2, ~144K params

### Data Sources

| Source | What it provides | Status |
|--------|-----------------|--------|
| **fablazing.com** | Per-card play rate, win rate, avg copies for 36 heroes | Scraped (649 cards) |
| **Talishar game logs** | Full deck lists + win/loss outcomes (synergy signal) | Collecting |
| **Manual meta decks** | Known-good decklists for heuristic seeding | 7 decks in `decks/` |

### Training Strategy

**Phase 1 — Bootstrap on fablazing data:**
- Generate synthetic (deck, label) pairs from play-rate heuristics
- "Good" decks (top cards by frequency) get hero win rate as label
- "Bad" decks (random cards) get inverted label
- Opponent hero sampled from meta distribution
- Train with BCE loss, ~50 epochs

**Phase 2 — Fine-tune on game outcomes:**
- Each game produces TWO samples: (hero_1, deck_1, hero_2, won_1) and (hero_2, deck_2, hero_1, won_2)
- Lower LR (0.1x) for fine-tuning
- Data collection strategy: 30% random, 30% heuristic, 20% meta, 20% mutated

### Database Schema

Card and deck data stored in `data/fablazing_meta.db`:
- `heroes` — hero_slug, format, win_rate, total_matches
- `card_stats` — card_slug, hero_slug, frequency, avg_copies, win_rate, match_count

Game outcomes stored in `data/talishar_games.db`:
- Full deck lists (JSON) paired with win/loss per game

### Deck Search

**Stage 1 — Pool evolution (per hero):**
1. Initialize population: 50% heuristic (frequency-biased), 50% random
2. Score each pool against field of ~20 opponents (meta-sampled)
3. Select top 20% as elite
4. Crossover + mutate to fill next generation
5. Repeat 50 generations
6. Best pool = tournament registration

**Stage 2 — Matchup selection (per round):**
1. Generate ~50 candidate 60-card subsets from pool
2. Score each against specific opponent hero
3. Pick highest-scoring subset

### Self-Play Improvement Loop (endgame)

```
Train scorer -> evolutionary search for optimized pools
-> simulate tournament (Swiss, meta-weighted heroes)
-> play top decks in Talishar simulator
-> add results to training data -> retrain scorer -> repeat
```

### Implementation Files

- `rl_agents/deck_evaluator.py` — DeepSets + Set Transformer models, CardVocab, datasets (done)
- `rl_agents/deck_search.py` — evolutionary pool search, matchup selection, tournament sim (done)
- `scripts/generate_heuristic_decks.py` — build decks from fablazing play rates (done)
- `scripts/train_deck_evaluator.py` — bootstrap + fine-tune training loop (done)

---

## Phase 4: Draft Pod Simulation (`drafter_bot`)

### What It Means

Eight `drafter_bot` instances each receive card packs, select cards, and pass the remainder (standard FAB draft rotation). After drafting, each bot assembles a draft deck. The eight decks play a round-robin pod (3 rounds, 4 simultaneous games, 12 games total).

### Draft Reward Structure

| Record | Decks | Reward |
|--------|-------|--------|
| 3-0 | 1 | +1.00 |
| 2-1 | 3 | +0.33 |
| 1-2 | 3 | -0.33 |
| 0-3 | 1 | -1.00 |

### Dependencies

- Requires competent `player_bot` (Phase 2) to evaluate draft deck quality
- Pack generation files must be provided
- Card embedder must generalize across all draft-legal sets

---

## Dependency Graph

```
[Data Collection]  ──>  [IQL Offline Training]
        |                        |
        v                        v
[Fablazing Scraper]     [Beats Random Bot (>50% WR)]
        |                        |
        v                        v
[Deck Builder Data]     [Self-Play Loop Active]
        |                      / \
        v                     v   v
[Phase 3: deck_bot]   [Phase 4: drafter_bot]
                        (needs pack gen files)
```

Phase 3 (deck builder) can begin model architecture work now using fablazing data as the initial training signal, even before the player bot is fully trained. The evaluator can be bootstrapped on fablazing play-rate heuristics and refined with game outcome data as it accumulates.

---

## Cross-Cutting Concerns

### Hero Legality

Check fabtcg.com Living Legend page for hero legality status. Heroes that have rotated to Living Legend format are not legal in Classic Constructed and should be excluded from CC deck builder training.

### Embedding Space Consistency

All bots share the card embedder. Version embedder checkpoints independently. Any embedder architecture change requires revalidation of all downstream policies.

### Card Slug Mapping

Fablazing uses slugs like `run_roughshod_blue`. Talishar uses similar format. Mapping between the two must be validated before using fablazing data to seed Talishar game decks.
