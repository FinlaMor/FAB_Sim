# FAB Sim

A rules-accurate game engine for the **Flesh and Blood** trading card game, built as a platform for training reinforcement learning agents.

---

## Overview

FAB Sim implements the FAB Comprehensive Rules as a Python game engine — turn structure, combat chain, priority system, stack resolution, card effects, and keywords. The engine exposes a clean interface for agents to observe game state and submit actions, making it suitable as an RL training environment.

Alongside the engine, an offline AI assistant pipeline (RAG + fine-tuned LLM) helps validate rules compliance and card implementations during development.

---

## Architecture

```
FAB_Sim/
├── engine/               # Core game engine
│   ├── engine.py         # Game loop, phase management, priority system
│   ├── state.py          # GameState, StackEntry, Zone, CombatState
│   ├── actions.py        # Legal action generation
│   ├── effects.py        # ContinuousEffect, ReplacementEffect, EffectManager
│   ├── card.py           # Card object model
│   ├── deck.py           # Deck loading and shuffling
│   └── card_effects/
│       ├── triggers.py   # Per-card triggered ability definitions (~3,200 lines)
│       ├── keywords.py   # Keyword mechanic implementations
│       ├── registry.py   # Trigger registration at game start
│       └── db/           # SQLite card effects database + seed data
│
├── agents/               # Game-playing agents
│   └── random_agent.py   # Baseline: uniform random over legal actions
│
├── offline_agents/       # Development assistant pipeline
│   ├── rag/              # ChromaDB vector store (rules + card text)
│   ├── agents/           # RulesAgent, CardAgent (RAG + local LLM)
│   ├── distillation/     # 332 reviewed FAB Q&A pairs + dataset generator
│   └── torchtune_configs/ # LoRA fine-tuning configs for Qwen2.5 7B
│
├── decks/                # Sample deck lists (4 heroes)
├── ref/                  # FAB Comprehensive Rules + 20 set release notes
└── tests/                # Game simulation tests
```

---

## Game Engine

The engine implements the FAB turn structure and rules flow:

- **Turn structure**: start phase, action phase, end phase with all sub-steps per CR 4.x
- **Combat chain**: attack declaration, layer step, defend step, reaction windows, resolution step, chain link closing
- **Stack**: LIFO resolution, triggered ability queuing, priority passing between players
- **Effects system**: continuous effects, replacement effects, duration tracking (end-of-turn cleanup)
- **Keywords**: Go Again, Dominate, Phantasm, Blood Debt, Ward, Arcane Barrier, Boost, Scrap, Crush, Intimidate, Wager, Guardwell, and more
- **Legal action generation**: pitch sequences, play from hand/arsenal, attacks, defenses, reactions, passing

Four hero decks are implemented: **Kayo**, **Arakni**, **Oscillio**, and **Marlynn**.

---

## Offline Development Agents

A local AI assistant pipeline helps validate rules compliance during development without requiring an internet connection or API key.

### Components

| Component | Description |
|---|---|
| `rag/embedder.py` | One-time script: embeds all ref/ docs + card data into ChromaDB |
| `rag/retriever.py` | Semantic search over 5,126 rules chunks and 4,561 cards |
| `agents/rules_agent.py` | Answers rules questions, reviews engine code against CR |
| `agents/card_agent.py` | Validates card implementations against official card text |
| `distillation/` | 332 reviewed Q&A pairs + LoRA fine-tuning pipeline for Qwen2.5 7B |

### Setup

```bash
pip install sentence-transformers chromadb ollama

# Build the vector store (one-time, ~2-5 min)
python -m offline_agents.rag.embedder

# Pull a base model via Ollama
ollama pull qwen2.5:7b
```

### Usage

```python
from offline_agents.agents.rules_agent import RulesAgent
from offline_agents.agents.card_agent import CardAgent

rules = RulesAgent()
rules.ask("When does Arcane Barrier trigger relative to damage prevention?")
rules.review_code(open("engine/card_effects/keywords.py").read(), "Check CR 8.3.8 compliance")

cards = CardAgent()
cards.validate("big_bully", implementation_code)
cards.sniff_test_all()  # breadth-first pass over all implemented cards
```

### Fine-Tuning (optional)

Adapts Qwen2.5 7B to FAB-specific vocabulary using LoRA via torchtune. Requires a CUDA GPU with ≥14GB VRAM, run under WSL2.

```bash
tune run lora_finetune_single_device --config offline_agents/torchtune_configs/fab_rules_lora.yaml
bash offline_agents/torchtune_configs/export_to_ollama.sh rules
```

See [`offline_agents/LOCAL_AGENTS.md`](offline_agents/LOCAL_AGENTS.md) for full fine-tuning instructions.

---

## Running a Game

```python
from tests.test_random_game import run_random_game

run_random_game()  # two random agents play a full game, result logged to random_game_output.txt
```

---

## Roadmap

1. **Complete card implementations** for all four hero decks
2. **Data collection** — run random-agent games to build a game state database (70% mirror matches, 30% cross-matchup)
3. **State encoder** — transformer with attention over hand, public board state, and deck composition
4. **RL training** — Implicit Q-Learning (IQL) per hero, benchmarked against random agent baseline

---

## Notes

- Card data (`card_data/slug_index.json`) is excluded from this repo — it is derived from LSS intellectual property and is not redistributable.
- The `ref/` folder contains the FAB Comprehensive Rules documents, used here for non-commercial engine development.