#!/usr/bin/env bash
# Train FAB LoRA model in WSL.
# Usage:
#   bash offline_agents/torchtune_configs/wsl_train_fab_lora.sh rules
#   bash offline_agents/torchtune_configs/wsl_train_fab_lora.sh cards

set -euo pipefail

ROLE="${1:-rules}"
ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv-wsl"

if [[ ! -d "$VENV_DIR" ]]; then
  echo "Missing ${VENV_DIR}. Run setup first:"
  echo "  bash offline_agents/torchtune_configs/wsl_setup_torchtune.sh"
  exit 1
fi

if [[ "$ROLE" == "rules" ]]; then
  CONFIG_PATH="offline_agents/torchtune_configs/fab_rules_lora.yaml"
elif [[ "$ROLE" == "cards" ]]; then
  CONFIG_PATH="offline_agents/torchtune_configs/fab_cards_lora.yaml"
else
  echo "Usage: $0 [rules|cards]"
  exit 1
fi

cd "$ROOT_DIR"
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

python - <<'PY'
import torch
if not torch.cuda.is_available():
  raise SystemExit(
    'CUDA is not available in WSL. '
    'torchtune single-device LoRA requires an NVIDIA CUDA GPU for this 7B setup. '
    'If this machine uses AMD or non-CUDA graphics, run on a cloud NVIDIA instance with '
    'offline_agents/torchtune_configs/cloud_train_fab_lora.sh.'
  )
print('Training on:', torch.cuda.get_device_name(0))
PY

tune run lora_finetune_single_device --config "$CONFIG_PATH"
