# WSL2 + ROCm Setup for AMD RX 7700 XT

Training on DML is ~2x slower than CPU due to unsupported op fallbacks
(lerp, std, log_sigmoid, etc.) that cause GPU<->CPU round trips.

ROCm is AMD's native CUDA equivalent — no op fallbacks, full PyTorch support.

## Prerequisites

- Windows 11 (you have this)
- AMD Adrenalin driver 23.40+ (likely already installed)
- WSL2 with Ubuntu 22.04

## Step 1: Install WSL2 + Ubuntu

```powershell
# In PowerShell (admin) — skip if you already have WSL2
wsl --install -d Ubuntu-22.04
```

Reboot if prompted, then launch Ubuntu and set up user/password.

## Step 2: Install ROCm in WSL2

```bash
# Add AMD ROCm repo
wget https://repo.radeon.com/rocm/rocm.gpg.key -O - | \
  gpg --dearmor | sudo tee /etc/apt/keyrings/rocm.gpg > /dev/null

echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/rocm.gpg] \
  https://repo.radeon.com/rocm/apt/6.3 jammy main" | \
  sudo tee /etc/apt/sources.list.d/rocm.list

sudo apt update
sudo apt install -y rocm-hip-runtime rocm-libs
```

## Step 3: Install PyTorch with ROCm

```bash
# Create venv
python3 -m venv ~/fab_venv
source ~/fab_venv/bin/activate

# PyTorch ROCm build (check pytorch.org for latest)
pip install torch torchvision torchaudio \
  --index-url https://download.pytorch.org/whl/rocm6.2

# Verify
python -c "import torch; print(torch.cuda.is_available())"
# Should print: True  (ROCm presents as CUDA to PyTorch)

python -c "import torch; print(torch.cuda.get_device_name(0))"
# Should print: AMD Radeon RX 7700 XT
```

## Step 4: Install project dependencies

```bash
# Mount your Windows project directory
cd /mnt/c/Users/Joseph/Desktop/FAB_Sim

# Install remaining deps
pip install h5py numpy
# (add whatever else requirements.txt needs)
```

## Step 5: Train with --device cuda

```bash
cd /mnt/c/Users/Joseph/Desktop/FAB_Sim

python -m rl_agents.train_transformer_iql \
  --talishar-db data/talishar_games.db \
  --slug-index card_data/slug_index.json \
  --steps 20000 --device cuda
```

ROCm exposes itself as "cuda" to PyTorch — no code changes needed.

## Expected Speedup

| Backend | Approx time/step | vs CPU |
|---------|-------------------|--------|
| CPU     | ~1.8s             | 1x     |
| DML     | ~3.5s             | 0.5x (slower!) |
| ROCm    | ~0.3-0.5s         | 4-6x faster |

The 7700 XT has 54 CUs and 12GB VRAM — more than enough for this model.
Batch size 512 with d_model=128 uses ~1-2 GB VRAM.
