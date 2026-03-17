#!/usr/bin/env python3
"""
RocM/HIP Post-Installation Configuration Script
Run this AFTER manually installing HIP SDK for Windows AMD GPU
"""

import os
import sys
import subprocess
from pathlib import Path

def main():
    print("=" * 70)
    print("RocM/HIP Post-Installation Configuration")
    print("=" * 70)
    print()
    
    # Step 1: Detect HIP Installation
    print("[Step 1] Detecting HIP SDK Installation...")
    
    hip_paths = [
        Path("C:\\Program Files\\AMD\\ROCm\\7.1"),
        Path("C:\\Program Files\\AMD\\ROCm\\7.0"),
        Path("C:\\Program Files\\AMD\\ROCm\\6.2"),
        Path("C:\\Program Files\\AMD\\ROCm\\6.1"),
        Path("C:\\Program Files\\AMD\\ROCm\\6.0"),
        Path("C:\\Program Files\\AMD\\HIP"),
        Path("C:\\Program Files (x86)\\AMD\\HIP"),
        Path(os.path.expanduser("~")) / "AppData" / "Local" / "AMD" / "HIP",
    ]
    
    hip_path = None
    for path in hip_paths:
        if path.exists():
            print(f"  ✓ Found HIP at: {path}")
            hip_path = path
            break
    
    if not hip_path:
        print("  ✗ HIP SDK not found!")
        print("\n  Please install HIP SDK first:")
        print("  1. Download from: https://rocmdocs.amd.com/en/latest/deploy/windows/install/")
        print("  2. Run installer as Administrator")
        print("  3. Re-run this script")
        return 1
    
    print()
    
    # Step 2: Verify HIP Binaries
    print("[Step 2] Verifying HIP Tools...")
    
    hip_bin_path = hip_path / "bin"
    critical_tools = ["hipcc.exe", "hipconfig.exe", "hipInfo.exe"]
    
    all_found = True
    for tool in critical_tools:
        tool_path = hip_bin_path / tool
        if tool_path.exists():
            print(f"  ✓ Found {tool}")
        else:
            print(f"  ✗ Missing {tool}")
            all_found = False
    
    if not all_found:
        print("\n  ⚠ HIP installation appears incomplete")
        print("  Please reinstall HIP SDK")
        return 1
    
    print()
    
    # Step 3: Set Environment Variables
    print("[Step 3] Setting Environment Variables...")
    
    env_vars = {
        "HIP_PATH": str(hip_path),
        "ROCM_HOME": str(hip_path),
        "HIP_DEVICE_ORDER": "PCI",
        "HIP_VISIBLE_DEVICES": "0",
        "GPU_DEVICE_ORDINAL": "0",
    }
    
    # Set for current process
    for key, value in env_vars.items():
        os.environ[key] = value
        print(f"  Set: {key}={value}")
    
    # Permanently set (User scope)
    print("\n  Setting permanent environment variables...")
    for key, value in env_vars.items():
        try:
            subprocess.run(
                ["setx", key, value],
                capture_output=True,
                check=True
            )
            print(f"    ✓ setx {key}")
        except Exception as e:
            print(f"    ⚠ setx {key} failed: {e}")
    
    # Add HIP bin to PATH
    hip_bin_str = str(hip_bin_path)
    current_path = os.environ.get("PATH", "")
    
    if hip_bin_str not in current_path:
        print(f"\n  Adding HIP to PATH: {hip_bin_str}")
        new_path = f"{hip_bin_str};{current_path}"
        os.environ["PATH"] = new_path
        
        try:
            # Also set permanently
            user_path = subprocess.run(
                ["powershell", "-Command", 
                 f'[Environment]::GetEnvironmentVariable("PATH", "User")'],
                capture_output=True,
                text=True
            ).stdout.strip()
            
            if hip_bin_str not in user_path:
                new_user_path = f"{hip_bin_str};{user_path}"
                subprocess.run(
                    ["setx", "PATH", new_user_path],
                    capture_output=True,
                    check=False
                )
                print(f"    ✓ Added HIP to permanent PATH")
        except Exception as e:
            print(f"    ⚠ PATH update failed: {e}")
    
    print()
    
    # Step 4: Test HIP Device Access
    print("[Step 4] Testing HIP Device Access...")
    
    try:
        result = subprocess.run(
            [str(hip_bin_path / "hipdevicecount.exe")],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            device_count = result.stdout.strip()
            print(f"  ✓ HIP Found {device_count} GPU device(s)")
        else:
            print(f"  ⚠ hipdevicecount error: {result.stderr}")
    except Exception as e:
        print(f"  ✗ Could not run hipdevicecount: {e}")
        print("     Ensure AMD GPU drivers are installed")
    
    print()
    
    # Step 5: Test PyTorch GPU Access
    print("[Step 5] Testing PyTorch GPU Access...")
    
    try:
        import torch
        print(f"  PyTorch version: {torch.__version__}")
        
        cuda_available = torch.cuda.is_available()
        print(f"  CUDA/GPU available: {cuda_available}")
        
        if cuda_available:
            device_count = torch.cuda.device_count()
            print(f"  GPU count: {device_count}")
            
            try:
                device_name = torch.cuda.get_device_name(0)
                print(f"  Device 0: {device_name}")
                
                # Try actual computation
                print("\n  Running GPU computation test...")
                x = torch.randn(1000, 1000, device='cuda')
                y = torch.randn(1000, 1000, device='cuda')
                z = torch.matmul(x, y)
                print(f"  ✓ GPU computation successful!")
                print(f"    Result shape: {z.shape}")
                print(f"    Result device: {z.device}")
                
            except Exception as e:
                print(f"  ⚠ GPU computation test failed: {e}")
        else:
            print(f"\n  ⚠ CUDA/GPU not available in PyTorch")
            print(f"    This may be normal if:")
            print(f"    1. HIP drivers need system restart")
            print(f"    2. AMD GPU driver not installed")
            print(f"    3. PyTorch needs reinstallation with HIP support")
            
    except ImportError:
        print("  ✗ PyTorch not installed")
        print("    Install with: pip install torch torchvision torchaudio")
        return 1
    except Exception as e:
        print(f"  ✗ PyTorch GPU test failed: {e}")
        return 1
    
    print()
    
    # Summary
    print("=" * 70)
    print("Configuration Complete")
    print("=" * 70)
    print()
    print("Next Steps:")
    print("  1. Restart PowerShell/VS Code for full environment reload")
    print("  2. Verify with: python check_gpu.py")
    print("  3. Test training with: python -m rl_agents.collect_iql_mixed_data ...")
    print()
    print("If GPU is still not detected:")
    print("  1. Restart your computer (not just PowerShell)")
    print("  2. Check Device Manager for GPU errors")
    print("  3. Verify AMD GPU drivers are installed and up-to-date")
    print("  4. Reinstall PyTorch: pip uninstall torch -y && pip install torch")
    print()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
