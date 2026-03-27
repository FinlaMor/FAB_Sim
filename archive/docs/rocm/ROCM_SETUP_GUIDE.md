# RocM Setup Guide for Windows AMD RX 7700 XT

## Current Status
- **GPU Detected**: ✓ AMD Radeon RX 7700 XT (RDNA 3)
- **HIP SDK Installed**: ✗ NOT YET
- **Environment Variables**: ✗ NOT SET
- **PyTorch GPU Ready**: ✗ CPU-only mode (2.10.0+cpu)

---

## Option 1: Manual HIP SDK Installation (Recommended)

### Step 1: Download HIP SDK Installer
1. Visit: **https://rocmdocs.amd.com/en/latest/deploy/windows/install/**
2. Look for the **HIP SDK for Windows** installer
3. Download the `.exe` file (usually named `HIP-*.exe`)

### Step 2: Install HIP SDK
1. **Run the installer as Administrator**
   - Right-click the `.exe` → "Run as administrator"
   - Follow the installation wizard (accept defaults)
   - Installation path: typically `C:\Program Files\AMD\HIP`

2. **During installation, ensure you select:**
   - HIP Runtime
   - HIP Development Tools
   - Device Support (auto-selected for RX 7700 XT)

### Step 3: Install AMD GPU Driver
The HIP SDK includes GPU drivers. If you need the latest:
- Visit: **https://www.amd.com/en/support**
- Search for "Radeon RX 7700 XT"
- Download latest driver
- Run as Administrator

### Step 4: Set Environment Variables
After installation, run these commands in PowerShell (as Administrator):

```powershell
# Set HIP environment variables permanently
setx HIP_PATH "C:\Program Files\AMD\HIP"
setx ROCM_HOME "C:\Program Files\AMD\HIP"
setx HIP_DEVICE_ORDER "PCI"
setx HIP_VISIBLE_DEVICES "0"

# Add HIP to PATH
$currentPath = [Environment]::GetEnvironmentVariable("PATH", "User")
$hipBin = "C:\Program Files\AMD\HIP\bin"
if ($currentPath -notmatch [regex]::Escape($hipBin)) {
    [Environment]::SetEnvironmentVariable("PATH", "$hipBin;$currentPath", "User")
}

Write-Host "Environment variables set. Please restart PowerShell/VS Code."
```

### Step 5: Restart PowerShell
Close and reopen PowerShell to apply environment variables.

### Step 6: Verify Installation
```powershell
cd C:\Users\Joseph\Desktop\FAB_Sim
C:/.venv/Scripts/python.exe check_gpu.py
```

Should show:
```
✓ AMD GPU DETECTED
✓ HIP SDK found at: C:\Program Files\AMD\HIP
✓ CUDA Available: True  (via HIP)
```

---

## Option 2: WSL2 + RocM (Alternative if Manual Installation Fails)

If you encounter issues with Windows RocM, WSL2 provides better RocM support:

### Prerequisites
- Windows 11 or Windows 10 with WSL2 support
- ~20GB disk space for Ubuntu + RocM

### Setup WSL2
```powershell
# Run as Administrator
wsl --install -d Ubuntu-22.04
```

### Install RocM in WSL2
```bash
# Inside WSL2
wget -q -O - https://repo.radeon.com/rocm/rocm.gpg.key | sudo apt-key add -
echo 'deb [arch=amd64] https://repo.radeon.com/rocm/apt/ubuntu focal main' | sudo tee /etc/apt/sources.list.d/rocm.list
sudo apt update
sudo apt install -y rocm-dkms

# Add user to video group
sudo usermod -aG video $USER
sudo usermod -aG render $USER

# Logout and login to apply group changes
exit
```

### Clone FAB_Sim to WSL
```bash
cd ~
git clone /mnt/c/Users/Joseph/Desktop/FAB_Sim fab_sim_wsl
cd fab_sim_wsl
python -m venv .venv_wsl
source .venv_wsl/bin/activate
pip install torch torchvision torchaudio
```

---

## Troubleshooting

### Problem: HIP SDK installer not found at Microsoft site
**Solution**: Use AMD's official page instead
- URL: https://rocmdocs.amd.com/en/latest/deploy/windows/install/
- Look for "HIP SDK" (not just documentation)

### Problem: GPU still not detected after HIP installation
**Solution**: 
1. Ensure AMD GPU drivers are installed and up-to-date
2. Check Device Manager: Settings → Device Manager → Display adapters
3. Restart computer (not just PowerShell)
4. Verify GPU is not disabled in BIOS

### Problem: PyTorch still shows CPU-only after HIP install
**Solutions**:
1. Reinstall PyTorch to pick up new HIP setup:
   ```powershell
   pip uninstall torch -y
   pip install torch torchvision torchaudio
   ```
2. Add HIP libraries to environment:
   ```powershell
   setx ROCM_HOME "C:\Program Files\AMD\HIP"
   setx LD_LIBRARY_PATH "$env:ROCM_HOME\lib"
   ```

### Problem: hipcc or other HIP tools not found
**Solution**: Verify HIP installation:
```powershell
Get-ChildItem "C:\Program Files\AMD\HIP\bin" | Where-Object {$_.Name -like "hip*"}
```

If empty, reinstall HIP SDK.

---

## Verification Scripts

### Quick Check
```powershell
cd C:\Users\Joseph\Desktop\FAB_Sim
python check_gpu.py
```

### PyTorch GPU Test
```python
import torch
print("PyTorch version:", torch.__version__)
print("GPU available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("GPU name:", torch.cuda.get_device_name(0))
    x = torch.randn(1000, 1000, device='cuda')
    y = torch.randn(1000, 1000, device='cuda')
    z = torch.matmul(x, y)
    print("GPU computation successful!")
```

---

## References
- AMD RocM Documentation: https://rocmdocs.amd.com/
- PyTorch RocM Support: https://pytorch.org/get-started/locally/
- HIP Documentation: https://rocmdocs.amd.com/en/latest/reference/hipcc/
- RX 7700 XT Specs: https://www.amd.com/en/products/specifications/graphics/19555

---

## After RocM Setup is Complete

Once HIP SDK is installed and verified, you can:

1. **Update training scripts** to use GPU:
   ```python
   device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
   model.to(device)
   ```

2. **Fast-track model training** (20-100x speedup)

3. **Run inference benchmarks** to validate GPU acceleration

---

**Last Updated**: March 12, 2026
**GPU Target**: AMD Radeon RX 7700 XT
**OS**: Windows 11/10
