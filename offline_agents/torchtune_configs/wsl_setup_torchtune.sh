#!/usr/bin/env bash
# WSL bootstrap for FAB torchtune training.
# Usage:
#   bash offline_agents/torchtune_configs/wsl_setup_torchtune.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv-wsl"

if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

python -m pip install --upgrade pip setuptools wheel

# Install CUDA-enabled PyTorch wheels first.
python -m pip install --upgrade --index-url https://download.pytorch.org/whl/cu124 torch torchvision torchaudio

# Install torchtune stack.
python -m pip install --upgrade torchao torchtune sentencepiece huggingface_hub datasets

python - <<'PY'
import torch
print('torch_version', torch.__version__)
print('cuda_available', torch.cuda.is_available())
if torch.cuda.is_available():
    print('gpu_name', torch.cuda.get_device_name(0))
else:
    print('gpu_name', 'none')
PY

echo
echo "WSL torchtune environment is ready at: ${VENV_DIR}"
echo "Activate with: source ${VENV_DIR}/bin/activate"
echo "Run training with: bash offline_agents/torchtune_configs/wsl_train_fab_lora.sh rules"
