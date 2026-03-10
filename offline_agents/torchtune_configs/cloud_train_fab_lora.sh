#!/usr/bin/env bash
# cloud_train_fab_lora.sh
#
# One-command setup + training for FAB LoRA models on a CUDA-capable Linux host.
#
# Usage:
#   bash offline_agents/torchtune_configs/cloud_train_fab_lora.sh rules
#   bash offline_agents/torchtune_configs/cloud_train_fab_lora.sh cards

set -euo pipefail

ROLE="${1:-rules}"
ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv-cloud"
PYTORCH_INDEX_URL="${PYTORCH_INDEX_URL:-https://download.pytorch.org/whl/cu124}"

if [[ "$ROLE" == "rules" ]]; then
  CONFIG_PATH="offline_agents/torchtune_configs/fab_rules_lora.yaml"
elif [[ "$ROLE" == "cards" ]]; then
  CONFIG_PATH="offline_agents/torchtune_configs/fab_cards_lora.yaml"
else
  echo "Usage: $0 [rules|cards]"
  exit 1
fi

cd "$ROOT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required but not found on PATH."
  exit 1
fi

if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

python -m pip install --upgrade pip setuptools wheel

# Install CUDA-enabled PyTorch first.
python -m pip install --upgrade --index-url "$PYTORCH_INDEX_URL" torch torchvision torchaudio

# Install torchtune training stack.
python -m pip install --upgrade torchao torchtune sentencepiece huggingface_hub datasets

if ! command -v tune >/dev/null 2>&1; then
  echo "torchtune CLI (tune) is not available after installation."
  echo "Try: python -m pip install --upgrade torchtune"
  exit 1
fi

python - <<'PY'
import torch

print('torch_version', torch.__version__)
print('cuda_available', torch.cuda.is_available())
if not torch.cuda.is_available():
    raise SystemExit('CUDA not available. Use an NVIDIA GPU cloud instance (A10/A100/L4/4090).')
print('gpu_name', torch.cuda.get_device_name(0))
PY

if [[ ! -f "${ROOT_DIR}/models/qwen2.5-7b/model-00001-of-00004.safetensors" ]]; then
  echo "Base model not found at models/qwen2.5-7b. Downloading..."
  tune download Qwen/Qwen2.5-7B-Instruct --output-dir "${ROOT_DIR}/models/qwen2.5-7b"
fi

echo "Starting training with config: ${CONFIG_PATH}"
tune run lora_finetune_single_device --config "$CONFIG_PATH"

echo
echo "Training finished for role: ${ROLE}"
echo "Next step (export to Ollama GGUF):"
echo "  bash offline_agents/torchtune_configs/export_to_ollama.sh ${ROLE}"
