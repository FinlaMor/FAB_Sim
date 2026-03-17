# RocM GPU Setup - Quick Start Instructions

## ⚡ TL;DR - 5 Minutes

You have an **AMD Radeon RX 7700 XT GPU** that's not yet configured. Here's what to do:

### Step 1: Download HIP SDK (2 min)
1. Go to: https://rocmdocs.amd.com/en/latest/deploy/windows/install/
2. Download the **HIP SDK for Windows** installer
3. Save to `Downloads` folder

### Step 2: Install HIP SDK (2 min)
1. Right-click the HIP installer → **Run as Administrator**
2. Click **Next** → **Install** (accept all defaults)
3. Wait for completion (~30 seconds)
4. Click **Finish**

### Step 3: Configure Environment (30 sec)
Open PowerShell **as Administrator** and run:

```powershell
# Copy-paste this entire block at once
setx HIP_PATH "C:\Program Files\AMD\HIP"
setx ROCM_HOME "C:\Program Files\AMD\HIP"
setx HIP_DEVICE_ORDER "PCI"
setx HIP_VISIBLE_DEVICES "0"

$currentPath = [Environment]::GetEnvironmentVariable("PATH", "User")
$hipBin = "C:\Program Files\AMD\HIP\bin"
if ($currentPath -notmatch [regex]::Escape($hipBin)) {
    [Environment]::SetEnvironmentVariable("PATH", "$hipBin;$currentPath", "User")
}

Write-Host "Done! Restart PowerShell to apply changes."
```

### Step 4: Verify (30 sec)
Close PowerShell and reopen it, then run:

```powershell
cd C:\Users\Joseph\Desktop\FAB_Sim
python check_gpu.py
```

**You should see:**
```
✓ AMD GPU DETECTED
✓ HIP SDK found at: C:\Program Files\AMD\HIP
✓ CUDA Available: True
```

### Done! 🎉
Your GPU is now ready. Training will be 20-100x faster.

---

## If Something Goes Wrong

### "HIP SDK not found after installation"
1. Verify manual installation: Check if `C:\Program Files\AMD\HIP\bin` exists
2. If missing, download and re-install from the link above
3. Run PowerShell **as Administrator** for setup commands

### "GPU still not detected"
1. Restart your **computer** (not just PowerShell)
2. Check: Settings → Device Manager → Display adapters
3. Update AMD drivers: https://www.amd.com/en/support

### "hipdevicecount says no devices"
1. Ensure AMD GPU drivers are installed
2. Check Device Manager for errors (yellow exclamation marks)
3. Restart computer if there are errors

---

## Helper Scripts

After HIP SDK is installed manually, you can use these scripts:

```powershell
# Run configuration script to set everything up
python configure_rocm_after_install.py

# Check GPU status anytime
python check_gpu.py

# See full setup guide
notepad ROCM_SETUP_GUIDE.md
```

---

## Important Notes

- **Installation takes ~2-3 minutes total**
- **You must use Administrator** for installation and setx commands
- **Restart computer** if GPU still not detected after all steps
- **PyTorch GPU support** requires HIP SDK installed (not optional)

---

## Next Steps After GPU Setup

Once GPU is verified working:

1. **Update training scripts** to use GPU device
2. **Test with small batch** before full training
3. **Monitor performance** - should see 20-100x speedup for models with 100M+ parameters

---

**Issues? Check:** ROCM_SETUP_GUIDE.md for detailed troubleshooting
