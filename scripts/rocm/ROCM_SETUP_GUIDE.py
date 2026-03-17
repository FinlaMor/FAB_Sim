#!/usr/bin/env python3
"""
RocM + PyTorch GPU Setup Guide for AMD Radeon RX 7700 XT
Run this script to verify RocM installation and test GPU compatibility
"""

import subprocess
import sys
import os

print("=" * 80)
print("RocM + PyTorch GPU Setup Guide")
print("=" * 80)
print()

print("STEP 1: Install RocM Toolkit (Windows)")
print("-" * 80)
print()
print("Option A: Windows Installer (Recommended)")
print("  1. Go to https://rocmdocs.amd.com/en/docs/deploy/windows/")
print("  2. Download AMD ROCm SDK for Windows")
print("  3. Run installer and follow prompts")
print("  4. Restart computer after installation")
print()
print("Option B: Windows Store")
print("  1. Open Microsoft Store")
print("  2. Search for 'AMD ROCm'")
print("  3. Install from official AMD app")
print()
print("Option C: Official AMD GitHub")
print("  https://github.com/RadeonOpenCompute/ROCm/releases")
print()
print()

print("STEP 2: Uninstall Current PyTorch")
print("-" * 80)
print()
print("Run in your .venv:")
print("  pip uninstall torch torchvision torchaudio -y")
print()
print()

print("STEP 3: Install PyTorch with RocM Support")
print("-" * 80)
print()
print("Run in your .venv:")
print("  pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm5.7")
print()
print("Or for Navi 3 (RX 7700 XT optimal):")
print("  pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.0")
print()
print()

print("STEP 4: Verify RocM Installation")
print("-" * 80)
print()

# Check ROCM_HOME
rocm_home = os.environ.get("ROCM_HOME")
if rocm_home:
    print(f"✓ ROCM_HOME is set: {rocm_home}")
else:
    print("✗ ROCM_HOME not set")
    print("  Set manually in PowerShell:")
    print("    [Environment]::SetEnvironmentVariable('ROCM_HOME', 'C:\\Program Files\\AMD\\ROCm', 'Machine')")
    print("    Then restart PowerShell")

print()

# Check hipcc
try:
    result = subprocess.run(
        ["hipcc", "--version"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode == 0:
        print(f"✓ HIP Compiler available:")
        print(f"  {result.stdout.strip()}")
    else:
        print("✗ hipcc not found in PATH")
except FileNotFoundError:
    print("✗ hipcc not found in PATH")
    print("  After RocM installation, restart PowerShell and try again")

print()

# Check rocm-smi
try:
    result = subprocess.run(
        ["rocm-smi"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode == 0:
        print(f"✓ AMD GPU detected:")
        for line in result.stdout.split("\n")[:20]:
            if line.strip() and ("GPU" in line or "ID" in line or "RX" in line):
                print(f"  {line}")
    else:
        print("✗ rocm-smi error or GPU not detected")
except FileNotFoundError:
    print("✗ rocm-smi not found in PATH")
    print("  After RocM installation, restart PowerShell and try again")

print()
print()

print("STEP 5: Verify PyTorch HIP Support")
print("-" * 80)
print()

try:
    import torch
    print(f"PyTorch Version: {torch.__version__}")
    print(f"CUDA Available: {torch.cuda.is_available()}")
    
    if hasattr(torch, 'hip') or 'rocm' in torch.__version__.lower():
        print("✓ PyTorch built with HIP/RocM support")
        if torch.cuda.is_available():
            print(f"✓ GPU detected: {torch.cuda.get_device_name(0)}")
            print(f"✓ GPU memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
    else:
        print("✗ PyTorch NOT built with HIP/RocM support")
        print("  Run: pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm5.7")
except Exception as e:
    print(f"Error: {e}")

print()
print()

print("STEP 6: Update Training Scripts")
print("-" * 80)
print()
print("The following scripts will be updated to support GPU:")
print("  • rl_agents/train_iql.py")
print("  • rl_agents/evaluate_iql_vs_random.py")
print("  • temp_iterative_selfplay_bootstrap.py")
print("  • temp_collect_iql_selfplay.py")
print()
print("Change --device from 'cpu' to 'cuda' to use GPU:")
print()
print("Example:")
print("  FROM: --device cpu")
print("  TO:   --device cuda")
print()
print("Or use environment variable:")
print("  $env:FAB_DEVICE='cuda'")
print()
print()

print("STEP 7: Test with Small Training Run")
print("-" * 80)
print()
print("Run a quick smoke test:")
print()
print("  C:/Users/Joseph/Desktop/FAB_Sim/.venv/Scripts/python.exe -m rl_agents.train_iql \\")
print("    --db-path data_collection/iql_kayoonly_120g_seed42_penalty_v1/mixed_seeded_replay.db \\")
print("    --run-name test_gpu_smoke \\")
print("    --steps 10 \\")
print("    --batch-size 256 \\")
print("    --device cuda \\")
print("    --log-every 1")
print()
print("If you see GPU utilization increasing, RocM is working!")
print()
print()

print("=" * 80)
print("Troubleshooting")
print("=" * 80)
print()
print("Issue: 'ROCM_HOME not found'")
print("  → Set environment variable (see Step 4)")
print()
print("Issue: 'hipcc not found'")
print("  → Restart PowerShell after RocM installation")
print()
print("Issue: 'No HIP devices detected'")
print("  → Check Device Manager for AMD Radeon RX 7700 XT")
print("  → Update AMD GPU drivers to latest version")
print()
print("Issue: PyTorch still CPU-only after reinstall")
print("  → Make sure to use correct wheel index URL (rocm5.7 or rocm6.0)")
print()
print()
