# FAB Sim

![Python](https://img.shields.io/badge/python-3.12%2B-blue)
![Tests](https://img.shields.io/badge/tests-pytest-green)
![Status](https://img.shields.io/badge/status-active%20development-orange)

A rules-accurate game engine for the **Flesh and Blood** trading card game, built as a research platform for training reinforcement learning agents.

---

## Overview

FAB Sim implements the FAB Comprehensive Rules as a Python game engine — turn structure, combat chain, priority system, LIFO stack resolution, card effects, and keywords. The engine exposes a clean interface for agents to observe game state and submit actions, making it suitable as an RL training environment.

Alongside the engine, a separate local AI assistant toolchain (RAG + fine-tuned Qwen2.5 7B) supports rules validation and card implementation during development. The RL pipeline uses a transformer-based state encoder and Implicit Q-Learning (IQL).

---

## Why Build This?

Reinforcement learning has proven highly effective for games of perfect information like chess and Go (see AlphaZero), but trading card games present a different challenge: hidden information, randomness, and vastly larger decision spaces.

Among TCGs, Flesh and Blood is particularly interesting for RL research:

- **Rich decision trees** — Nearly every card can be played as an attack, used to block, or pitched for resources, creating exponential branching at each turn
- **Object-oriented rules system** — FAB's Comprehensive Rules define everything as objects with properties and interactions, making it naturally suited to programmatic implementation
- **Accumulating deck knowledge** — Pitched cards return to the bottom of the deck in known order, creating a compounding information advantage that rewards long-term planning

This project explores whether transformer-based state encodings can capture the strategic patterns that distinguish expert play from random play, and whether IQL can learn effective policies across FAB's combinatorial action space.

---

## Architecture

```
FAB_Sim/
├── engine/                   # Core rules engine
│   ├── engine.py             # Game loop, phase management, priority system
│   ├── state.py              # GameState, StackEntry, Zone, CombatState data structures
│   ├── actions.py            # Legal action generation (all ActionTypes)
│   ├── play.py               # Card playability checks and action application
│   ├── effects.py            # ContinuousEffect, ReplacementEffect, EffectManager
│   ├── card.py               # Card object model and CardDB
│   ├── deck.py               # Deck loading and shuffling
│   └── card_effects/
│       ├── registry.py       # Static ability registries (conditions, costs, triggers)
│       ├── ability_keywords.py
│       ├── triggers/
│       │   ├── triggers.py              # Per-card triggered ability definitions
│       │   └── card_triggers_extended.py
│       ├── costs/            # 7 cost modules (mandatory, optional, alt, keyword costs)
│       ├── dsl/              # DSL interpreter: JSON ability definitions → runtime effects
│       ├── db/               # SQLite card effects database + seed data
│       └── json/             # Per-card JSON effect definitions (organised by set)
│
├── encoder/                  # State and action embeddings
│   ├── gamestate_embedder.py # GameState → fixed-size neural network input
│   ├── card_embedder.py      # Card slug → embedding (SlugVocab)
│   ├── action_embedder.py    # Action → embedding
│   ├── game_transformer.py   # Transformer policy architecture
│   └── feature_schema.py     # Feature definitions and constants
│
├── rl_agents/                # Game-playing agents and training
│   ├── random_agent.py       # Baseline: uniform random over legal actions
│   ├── iql.py                # Implicit Q-Learning implementation (IQLConfig, training loop)
│   ├── train_iql.py          # IQL training entry point
│   ├── evaluate_iql_vs_random.py
│   ├── local_game_runner.py  # Self-contained game runner for data collection
│   ├── game_data.py          # SQLite game data logger
│   ├── dataset_adapter.py    # Replay DB → (s, a, r, s', done) tensors for IQL
│   ├── heuristic_bot.py      # Rule-based heuristic baseline
│   └── utils/                # Device resolution, MLP builder, matchup configs, seeds
│
├── decks/                    # Sample deck lists (4 CC heroes)
│   ├── arakni_marionette_CC_lite.txt
│   ├── kayo_underhanded_cheat_CC_lite.txt
│   └── victor_goldmane_high_and_mighty_CC_lite.txt
│
├── scripts/                  # Utility and analysis scripts
│   ├── run_pipeline.py       # End-to-end training pipeline
│   ├── collect_iql_mixed_data.py
│   ├── audit_card_effects.py # Classify card implementation status
│   └── ...
│
├── docs/                     # Comprehensive Rules, architecture decisions, audit reports
│   └── ref/                  # FAB Comprehensive Rules + set release notes
│
└── tests/                    # 33 test files (mechanics, integration, RL)
```

---

## Game Engine

The engine implements the full FAB turn structure and rules flow:

- **Turn structure**: start phase, action phase, end phase with all sub-steps per CR 4.x
- **Combat chain**: attack declaration, layer step, defend step, reaction windows, resolution step, chain link closing
- **Stack**: LIFO resolution, triggered ability queuing, priority passing between players
- **Effects system**: continuous effects, replacement effects, duration tracking, end-of-turn cleanup
- **Keywords**: Go Again, Dominate, Overpower, Phantasm, Reprise, Blood Debt, Ward, Arcane Barrier, Boost, Crush, Intimidate, Stealth, and more (CR 8.x)
- **Legal action generation**: pitch sequences, play from hand/arsenal, attacks, defenses, reactions, passing
- **Card effect DSL**: JSON-defined per-card abilities interpreted at runtime — no scattered card-specific code in engine files

Four CC hero decks are implemented: **Kayo**, **Arakni**, **Oscillio**, and **Marlynn**.

---

## RL Pipeline

The training pipeline follows an offline RL approach:

1. **Data collection** — random-agent (and heuristic-agent) games logged to SQLite with full state/action/reward tuples
2. **State encoding** — `GameState` → fixed-size embedding via `GameStateEmbedder` (player stats, zone sizes, equipment, permanents, hero identity; global turn/combat state)
3. **Action encoding** — each legal action embedded independently, enabling variable-length action sets
4. **IQL training** — Implicit Q-Learning on pre-embedded `(s, a, r, s', done)` transitions; trained per hero

Current status: IQL v3 checkpoint trained on 3.3M steps; beats random baseline.

---

## Quick Start

### Prerequisites

```bash
pip install -r requirements.txt
```

> Card data (`card_data/slug_index.json`) is excluded from this repo — it is derived from LSS intellectual property and is not redistributable. The engine can be explored without it using the test suite.

### Run the test suite

```bash
pytest
```

### Run a game programmatically

```python
from engine.engine import new_game, run_game
from engine.card import CardDB
from rl_agents.random_agent import RandomAgent

card_db = CardDB("card_data/slug_index.json")
agent = RandomAgent()

state = new_game(
    p1_deck_path="decks/kayo_underhanded_cheat_CC_lite.txt",
    p2_deck_path="decks/arakni_marionette_CC_lite.txt",
    p1_agent=agent.ask,
    p2_agent=agent.ask,
    card_db=card_db,
)
final_state = run_game(state, card_db)
print(f"Winner: Player {final_state.winner}")
```

---

## Offline AI Development Assistant

A local AI assistant toolchain supports rules compliance validation during development, without requiring an internet connection or external API. This component is not included in the repository (it relies on locally downloaded model weights).

| Component | Description |
|---|---|
| RAG embedder | Embeds all `docs/ref/` rules documents + card data into ChromaDB |
| Rules agent | Answers rules questions, reviews engine code against the CR |
| Card agent | Validates card implementations against official card text |
| Fine-tuning | 332 reviewed FAB Q&A pairs + LoRA fine-tuning pipeline for Qwen2.5 7B |

**Optional dependencies** (for this component only):
```bash
pip install sentence-transformers chromadb ollama
```

Requires an NVIDIA CUDA GPU with ≥14 GB VRAM for fine-tuning. Inference runs locally via Ollama.

---

## Roadmap

See [ROADMAP.md](ROADMAP.md) for current status and planned work.

---

## Notes

- Card data (`card_data/slug_index.json`) is excluded from this repo — it is derived from LSS intellectual property and is not redistributable.
- The `docs/ref/` folder contains the FAB Comprehensive Rules documents, used here for non-commercial engine development.
