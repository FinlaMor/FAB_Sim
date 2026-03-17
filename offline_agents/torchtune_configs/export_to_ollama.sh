#!/usr/bin/env bash
# export_to_ollama.sh — Merge a FAB LoRA adapter into the local Qwen base model and load it into Ollama.
#
# Run from the repo root:
#   bash offline_agents/torchtune_configs/export_to_ollama.sh rules
#   bash offline_agents/torchtune_configs/export_to_ollama.sh cards
#
# This is a thin wrapper around export_to_ollama.py so the same workflow works for
# adapter-only downloads pulled back from cloud training.

set -euo pipefail

ROLE="${1:-rules}"
shift || true

python3 offline_agents/torchtune_configs/export_to_ollama.py "$ROLE" "$@"
