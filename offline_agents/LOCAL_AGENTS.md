# Local Agents — FAB Sim v2

Two offline AI agents assist with development: a **Rules Agent** that answers rules questions and reviews engine code against the FAB Comprehensive Rules, and a **Card Agent** that validates card implementations against official card text. Both run locally via Ollama (no API cost) with an optional Claude API fallback.

---

## Why Local Agents?

The FAB Comprehensive Rules span ~50,000 lines across 9 documents plus 20+ set release notes. The card database has 4,561 cards (at time of writing). Manually cross-referencing either during development is slow and error-prone.

The agents solve this by:
- **Retrieving relevant rules/card text automatically** (RAG) before answering — no need to know which CR section applies
- **Running fully offline** once set up — no API key required for day-to-day use
- **Being fine-tuned on FAB-specific data** — a base Qwen2.5 7B model adapted on ~330 reviewed Q&A pairs covering FAB rules and card mechanics
- **Falling back to Claude** if Ollama is unavailable, using the same RAG context

---

## Architecture

```
Your question / code snippet
        │
        ▼
┌─────────────────────┐
│   RAG Retriever     │  ChromaDB vector store
│  (offline_agents/   │  ├─ fab_rules   (5,126 chunks from ref/)
│   rag/retriever.py) │  └─ fab_cards   (4,561 cards from card_data/)
└─────────────────────┘
        │  top-K relevant excerpts
        ▼
┌─────────────────────┐
│  RulesAgent /       │  System prompt + RAG context + your question
│  CardAgent          │──────────────────────────────────────────────►
│  (agents/*.py)      │
└─────────────────────┘
        │
        ▼
   Ollama (local)          ◄── preferred: fab-rules-ft / fab-cards-ft
        or
   Claude API (fallback)   ◄── used if Ollama is not running
```

### Components

| File | Purpose |
|---|---|
| `rag/embedder.py` | One-time script: embeds all ref/ docs + cards into ChromaDB |
| `rag/retriever.py` | Query interface: `query_rules()`, `query_cards()`, `query_all()` |
| `agents/rules_agent.py` | Rules Q&A + code review against CR |
| `agents/card_agent.py` | Card implementation validator |
| `distillation/rules_qa.jsonl` | 150 reviewed Q&A pairs — FAB rules |
| `distillation/cards_qa.jsonl` | 179 reviewed Q&A pairs — FAB card mechanics |
| `distillation/training_data.jsonl` | Combined dataset used for fine-tuning |
| `torchtune_configs/fab_rules_lora.yaml` | LoRA fine-tuning config for rules model |
| `torchtune_configs/fab_cards_lora.yaml` | LoRA fine-tuning config for cards model |
| `torchtune_configs/export_to_ollama.sh` | Converts fine-tuned model → GGUF → Ollama |

---

## Setup

### 1. Install dependencies

```bash
pip install sentence-transformers chromadb ollama anthropic
```

### 2. Build the RAG vector store (one-time)

This embeds all rules docs and cards into ChromaDB. Takes ~2–5 minutes.

```bash
cd FAB_Sim_v2
python -m offline_agents.rag.embedder
```

Output: `offline_agents/rag/chroma_db/` — ~200MB, do not delete.

If the ref/ docs or card_data/ change, re-run this command to rebuild.

### 3. Install and start Ollama

Download from [ollama.com](https://ollama.com). Then pull a base model to use before fine-tuning:

```bash
ollama pull qwen2.5:7b
```

The agents will automatically use this as a fallback if `fab-rules-ft` / `fab-cards-ft` are not yet installed.

---

## Using the Agents

### Rules Agent

Answers rules questions and reviews engine code for CR compliance.

```python
from offline_agents.agents.rules_agent import RulesAgent

agent = RulesAgent()

# Ask a rules question
answer = agent.ask("Can Arcane Barrier be used after damage has already been dealt?")
print(answer)

# Review a code snippet for rules compliance
code = open("engine/card_effects/keywords.py").read()
report = agent.review_code(code, "Check the arcane damage flow against CR 8.3.8 and CR 8.5.47")
print(report)
```

### Card Agent

Validates card implementations against official card text.

```python
from offline_agents.agents.card_agent import CardAgent

agent = CardAgent()

# Validate a specific card implementation
code = """
TriggerDef(
    event_type="attacking",
    condition_fn=None,
    effect_fn=_big_bully_effect,
    is_optional=False,
)
"""
report = agent.validate("big_bully", code)
print(report)

# Quick sniff-test of ALL implemented cards (breadth-first)
report = agent.sniff_test_all()
print(report)
```

### Direct RAG queries (no LLM)

```python
from offline_agents.rag.retriever import Retriever

r = Retriever()

# Get relevant rules text
chunks = r.query_rules("What does Crush do?", n=5)

# Get relevant card descriptions
cards = r.query_cards("Etchings of Arcana", n=3)

# Combined context string (ready to paste into any prompt)
context = r.query_all("How does amp interact with Arcane Barrier?", n_rules=6, n_cards=2)
```

---

## Fine-Tuning (Optional)

Fine-tuning adapts Qwen2.5 7B to FAB-specific vocabulary so it needs less RAG context and gives more precise answers. Requires a **CUDA GPU with ≥14GB VRAM**. No gated model access required.

### Training data

332 reviewed Q&A pairs are already written and corrected in `distillation/training_data.jsonl`:
- `distillation/rules_qa.jsonl` — 150 pairs covering CR 4–8 (turn structure, combat, keywords, tokens, prevention)
- `distillation/cards_qa.jsonl` — 179 pairs covering implemented cards (equipment, attacks, sigils, weapons, auras)

To regenerate or expand the dataset using a local LLM instead of the Claude API, modify `distillation/generate_dataset.py` to point at `http://localhost:11434` (Ollama's API endpoint) instead of the Anthropic client.

> **Windows note:** torchtune does not support Windows. All training commands must run under **WSL2** (Ubuntu).
> Enable WSL2: open PowerShell as admin and run `wsl --install`, then restart.
> Inside WSL2, the project is at `/mnt/c/Users/Joseph/Desktop/FAB_Sim_v2`.
> WSL2 has full CUDA GPU passthrough — training performance is the same as native Linux.

### Step 1: Download base model

No approval required — Qwen2.5 is fully open. Run from WSL2 or use Python directly on Windows:

```bash
# Windows (Python):
python -c "from huggingface_hub import snapshot_download; snapshot_download('Qwen/Qwen2.5-7B-Instruct', local_dir='models/qwen2.5-7b')"

# WSL2:
pip install torchtune torchao
tune download Qwen/Qwen2.5-7B-Instruct --output-dir ./models/qwen2.5-7b
```

### Step 2: Fine-tune (WSL2 only)

Both configs already point at `training_data.jsonl`. Run either or both:

```bash
tune run lora_finetune_single_device --config offline_agents/torchtune_configs/fab_rules_lora.yaml

tune run lora_finetune_single_device --config offline_agents/torchtune_configs/fab_cards_lora.yaml
```

Training takes ~1–2 hours depending on GPU. Checkpoints save to `models/fab-rules-ft/` and `models/fab-cards-ft/`.

### Step 4: Export to Ollama

Merges LoRA weights, quantizes to Q4_K_M GGUF (~4.5GB), and loads into Ollama.

```bash
bash offline_agents/torchtune_configs/export_to_ollama.sh rules
bash offline_agents/torchtune_configs/export_to_ollama.sh cards
```

After this, `RulesAgent()` and `CardAgent()` will automatically detect and use `fab-rules-ft` / `fab-cards-ft`.

### Verify

```bash
ollama run fab-rules-ft "What does Arcane Barrier N do per CR 8.3.8?"
ollama run fab-cards-ft "When does Big Bully's effect trigger?"
```

---

## Configuration

Both agents accept constructor arguments to override defaults:

```python
# Use a different local model
agent = RulesAgent(ollama_model="qwen2.5:7b")

# Retrieve more context chunks (slower but more thorough)
agent = RulesAgent(n_rules=10, n_cards=5)

# Disable Ollama, force Claude API
agent = RulesAgent(ollama_model="__none__")
```

The Claude API fallback reads `ANTHROPIC_API_KEY` from the environment automatically.

---

## Current Status

| Component | Status |
|---|---|
| RAG vector store | Built — 5,126 rules chunks + 4,561 cards |
| rules_qa.jsonl | 150 pairs, reviewed and corrected |
| cards_qa.jsonl | 179 pairs, reviewed and corrected |
| Fine-tuning configs | Written — Qwen2.5 7B, waiting on CUDA GPU |
| Ollama export script | Written — ready to run after fine-tuning |
| Fine-tuned models | Not yet trained |
