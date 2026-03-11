#!/usr/bin/env bash
# cloud_train_fab_lora.sh
#
# One-command setup + training for FAB LoRA models on a CUDA-capable Linux host.
# Clone the repo into /workspace/FAB_Sim before running so model checkpoints,
# Hugging Face cache files, and temp files stay on the mounted workspace volume.
#
# Usage:
#   bash offline_agents/torchtune_configs/cloud_train_fab_lora.sh rules
#   bash offline_agents/torchtune_configs/cloud_train_fab_lora.sh cards

set -euo pipefail

ROLE="${1:-rules}"
ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv-cloud"
WORKSPACE_DIR="${WORKSPACE_DIR:-/workspace}"
MODELS_DIR="${ROOT_DIR}/models"
HF_HOME_DIR="${HF_HOME:-${WORKSPACE_DIR}/hf_cache}"
HF_HUB_CACHE_DIR="${HF_HUB_CACHE:-${HF_HOME_DIR}/hub}"
TRANSFORMERS_CACHE_DIR="${TRANSFORMERS_CACHE:-${HF_HOME_DIR}/transformers}"
TORCH_HOME_DIR="${TORCH_HOME:-${HF_HOME_DIR}/torch}"
TMP_DIR="${TMPDIR:-${WORKSPACE_DIR}/tmp}"
PYTORCH_INDEX_URL="${PYTORCH_INDEX_URL:-https://download.pytorch.org/whl/cu124}"
TORCH_VERSION="${TORCH_VERSION:-2.5.1}"
TORCHVISION_VERSION="${TORCHVISION_VERSION:-0.20.1}"
TORCHAUDIO_VERSION="${TORCHAUDIO_VERSION:-2.5.1}"
TORCHAO_VERSION="${TORCHAO_VERSION:-0.6.1}"
TORCHTUNE_VERSION="${TORCHTUNE_VERSION:-0.6.1}"

if [[ "$ROLE" == "rules" ]]; then
  CONFIG_PATH="offline_agents/torchtune_configs/fab_rules_lora.yaml"
elif [[ "$ROLE" == "cards" ]]; then
  CONFIG_PATH="offline_agents/torchtune_configs/fab_cards_lora.yaml"
else
  echo "Usage: $0 [rules|cards]"
  exit 1
fi

cd "$ROOT_DIR"

if [[ "$ROOT_DIR" != "$WORKSPACE_DIR" && "$ROOT_DIR" != "$WORKSPACE_DIR"/* ]]; then
  echo "This script must run from a repo cloned under ${WORKSPACE_DIR}."
  echo "Clone with: git clone https://github.com/FinlaMor/FAB_Sim.git ${WORKSPACE_DIR}/FAB_Sim"
  echo "Then run it from: ${WORKSPACE_DIR}/FAB_Sim"
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required but not found on PATH."
  exit 1
fi

if [[ ! -d "$VENV_DIR" ]]; then
  if ! python3 -m venv "$VENV_DIR"; then
    echo "python3 -m venv failed. On Debian/Ubuntu install python3-venv first:"
    echo "  apt update && apt install -y python3-venv"
    exit 1
  fi
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

mkdir -p "$HF_HUB_CACHE_DIR" "$TRANSFORMERS_CACHE_DIR" "$TORCH_HOME_DIR" "$TMP_DIR" "$MODELS_DIR"

export HF_HOME="$HF_HOME_DIR"
export HF_HUB_CACHE="$HF_HUB_CACHE_DIR"
export TRANSFORMERS_CACHE="$TRANSFORMERS_CACHE_DIR"
export TORCH_HOME="$TORCH_HOME_DIR"
export TMPDIR="$TMP_DIR"
export HF_HUB_DISABLE_XET="${HF_HUB_DISABLE_XET:-1}"

python -m pip install --upgrade pip setuptools wheel

# Install CUDA-enabled PyTorch first.
python -m pip install --upgrade --index-url "$PYTORCH_INDEX_URL" \
  "torch==${TORCH_VERSION}" \
  "torchvision==${TORCHVISION_VERSION}" \
  "torchaudio==${TORCHAUDIO_VERSION}"

# Install torchtune training stack.
python -m pip install --upgrade \
  "torchao==${TORCHAO_VERSION}" \
  "torchtune==${TORCHTUNE_VERSION}" \
  sentencepiece huggingface_hub datasets

if ! command -v tune >/dev/null 2>&1; then
  echo "torchtune CLI (tune) is not available after installation."
  echo "Try: python -m pip install --upgrade torchtune"
  exit 1
fi

if [[ ! -f "${ROOT_DIR}/offline_agents/distillation/training_data.jsonl" ]]; then
  echo "Missing offline_agents/distillation/training_data.jsonl"
  echo "Upload it from local WSL with:"
  echo "  bash offline_agents/torchtune_configs/runpod_sync.sh upload-data <ssh-target> [--port PORT]"
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

if [[ ! -f "${MODELS_DIR}/qwen2.5-7b/model-00001-of-00004.safetensors" ]]; then
  echo "Base model not found at models/qwen2.5-7b. Downloading..."
  tune download Qwen/Qwen2.5-7B-Instruct --output-dir "${MODELS_DIR}/qwen2.5-7b"
fi

echo "Starting training with config: ${CONFIG_PATH}"
tune run lora_finetune_single_device --config "$CONFIG_PATH"

echo
echo "Training finished for role: ${ROLE}"
echo "Next step (export to Ollama GGUF):"
echo "  bash offline_agents/torchtune_configs/export_to_ollama.sh ${ROLE}"
