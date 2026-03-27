# RocM Setup Tools - Complete Guide

## Overview
You have an **AMD Radeon RX 7700 XT GPU** that's currently not configured for PyTorch.

This package contains everything needed to set up GPU acceleration for your system.

**Current Status:**
- ✅ GPU Detected: AMD Radeon RX 7700 XT
- ❌ HIP SDK: NOT INSTALLED
- ❌ Environment Variables: NOT SET
- ❌ PyTorch GPU: CPU-only mode

---

## Getting Started - Choose Your Path

### 🎯 Path 1: Interactive Setup (Recommended for First-Time Users)

**Best for:** Users who want guided step-by-step setup

```powershell
cd C:\Users\Joseph\Desktop\FAB_Sim
python rocm_wizard.py
```

**What it does:**
1. Checks if HIP SDK is installed
2. Guides you to download HIP SDK if needed  
3. Verifies HIP installation
4. Sets environment variables automatically
5. Tests PyTorch GPU access
6. Shows setup status and next steps

**Time required:** ~5-10 minutes (mostly waiting for your input)

---

### 📖 Path 2: Manual Setup (Complete Control)

**Best for:** Users who prefer reading and understanding each step

1. **Read the guide:**
   ```powershell
   notepad ROCM_QUICK_START.md
   ```
   (~2 min read, then 3 min installation)

2. **Or for detailed troubleshooting:**
   ```powershell
   notepad ROCM_SETUP_GUIDE.md
   ```
   (Complete reference guide with all options)

---

### 🔧 Path 3: Post-Installation Configuration

**Use after manually installing HIP SDK:**

```powershell
python configure_rocm_after_install.py
```

**What it does:**
1. Detects HIP SDK installation
2. Verifies all HIP tools
3. Sets environment variables
4. Tests GPU access
5. Advises on next steps

---

## Tools Reference

### Scripts in This Package

| Script | Purpose | How to Use |
|--------|---------|-----------|
| `rocm_wizard.py` | Interactive setup wizard | `python rocm_wizard.py` |
| `check_gpu.py` | GPU status checker | `python check_gpu.py` |
| `configure_rocm_after_install.py` | Post-install config | `python configure_rocm_after_install.py` |
| `setup_rocm_windows.ps1` | PowerShell setup (reference) | Reference only |
| `setup_rocm_automated.py` | Auto-downloader (may fail) | For troubleshooting |

### Documentation in This Package

| Document | Purpose | Read Time |
|----------|---------|-----------|
| `ROCM_QUICK_START.md` | Quick 5-minute setup | 2 min |
| `ROCM_SETUP_GUIDE.md` | Complete reference guide | 10 min |
| `ROCM_SETUP_TOOLS.md` | This file | 5 min |

---

## Quick Decision Tree

```
Have you installed HIP SDK yet?
│
├─ NO: Run rocm_wizard.py
│      It will guide you through download and installation
│
└─ YES: Run configure_rocm_after_install.py
        It will set up environment and test GPU
```

---

## Step-by-Step Instructions

### Option A: Use the Wizard (Easiest)

```powershell
# Open PowerShell, go to project directory
cd C:\Users\Joseph\Desktop\FAB_Sim

# Run the wizard
python rocm_wizard.py

# Follow on-screen prompts
# The wizard will handle downloading/installing HIP SDK
```

### Option B: Manual 5-Minute Setup

```powershell
# 1. Download HIP SDK
# Visit: https://rocmdocs.amd.com/en/latest/deploy/windows/install/
# Download and save HIP installer

# 2. Install HIP SDK
# Right-click installer → Run as Administrator → Accept defaults → Finish

# 3. Set Environment Variables (run as Administrator)
setx HIP_PATH "C:\Program Files\AMD\HIP"
setx ROCM_HOME "C:\Program Files\AMD\HIP"
setx HIP_DEVICE_ORDER "PCI"
setx HIP_VISIBLE_DEVICES "0"

# 4. Verify
# Close and reopen PowerShell, then:
cd C:\Users\Joseph\Desktop\FAB_Sim
python check_gpu.py
```

---

## Verification

After any setup attempt, verify the configuration:

```powershell
# Check GPU status
python check_gpu.py

# Check PyTorch GPU access
python -c "import torch; print(f'GPU: {torch.cuda.is_available()}')"

# Run full verification
python configure_rocm_after_install.py
```

---

## Troubleshooting

### Problem: "HIP SDK not found"
**Solution:**
1. Download from: https://rocmdocs.amd.com/en/latest/deploy/windows/install/
2. Run as Administrator
3. Use default path: `C:\Program Files\AMD\HIP`

### Problem: "GPU still not detected"
**Solution:**
1. Restart PowerShell (close and reopen)
2. Or restart your computer
3. Check: Settings → Device Manager → Display adapters
4. Update AMD drivers if needed

### Problem: "PyTorch shows CPU-only"
**Solution:**
```powershell
# Reinstall PyTorch to pick up HIP
pip uninstall torch -y
pip install torch torchvision torchaudio

# Verify
python check_gpu.py
```

---

## Expected Output (Success)

When setup is complete, `python check_gpu.py` should show:

```
✓ AMD GPU DETECTED

✓ HIP SDK found at: C:\Program Files\AMD\HIP

✓ CUDA Available: True  
√ GPU Name: AMD Radeon RX 7700 XT

✓ Environment Variables:
    ✓ HIP_PATH: C:\Program Files\AMD\HIP
    ✓ HIP_VISIBLE_DEVICES: 0
    ✓ ROCM_HOME: C:\Program Files\AMD\HIP
    ✓ HIP_DEVICE_ORDER: PCI
```

And PyTorch test:

```python
>>> import torch
>>> torch.cuda.is_available()
True
>>> torch.cuda.get_device_name(0)
'AMD Radeon RX 7700 XT'
```

---

## Important Notes

⚠️ **Critical:**
- HIP SDK **must** be installed from official AMD source
- Environment variables require **Administrator** privileges
- Restart PowerShell after setting variables (or restart computer)
- GPU drivers must be installed (usually automatic with HIP)

✅ **Benefits after setup:**
- 20-100x faster training on large models
- GPU memory for larger batch sizes
- Parallel processing for multiple models

---

## Performance After Setup

Once GPU is configured, you can see speedups:

```python
# Before (CPU): ~0.5 MB/s
# After (GPU): ~50 MB/s (100x speedup!)

# Expected for your model types:
# - Small models (10M params): 20-30x speedup
# - Medium models (100M params): 50-100x speedup
# - Large models (1B+ params): 100x+ speedup
```

---

## Next Steps After Setup

1. **Test GPU training:**
   ```powershell
   python -m rl_agents.collect_iql_mixed_data --device cuda --games-per-matchup 5
   ```

2. **Monitor GPU usage:**
   ```powershell
   # Install GPU monitoring tool
   pip install gpustat
   
   # Check in another PowerShell:
   gpustat -i 1  # Updates every 1 second
   ```

3. **Update training scripts:**
   ```python
   # Use: device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
   # Instead of: device = 'cpu'
   ```

---

## References

- AMD RocM Docs: https://rocmdocs.amd.com/
- PyTorch Setup: https://pytorch.org/get-started/locally/
- HIP Documentation: https://rocmdocs.amd.com/en/latest/reference/hipcc/
- RX 7700 XT Specs: https://www.amd.com/en/products/specifications/graphics/19555

---

## Support

If you encounter issues not covered here:

1. **Check detailed guide:** `notepad ROCM_SETUP_GUIDE.md`
2. **Run wizard again:** `python rocm_wizard.py`
3. **Check GPU status:** `python check_gpu.py`
4. **AMD official docs:** https://rocmdocs.amd.com/

---

**Last Updated:** March 12, 2026
**GPU:** AMD Radeon RX 7700 XT  
**OS:** Windows 11/10
**Target:** RocM 6.0+ with HIP SDK
