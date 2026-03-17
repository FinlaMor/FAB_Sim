#!/usr/bin/env python3
"""
Automated RocM/HIP Setup for Windows AMD GPU
Downloads and installs HIP SDK for AMD RX 7700 XT
"""

import os
import sys
import subprocess
import json
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
import tempfile
import time

def log(msg, level="INFO"):
    """Colored logging"""
    colors = {"INFO": "\033[94m", "OK": "\033[92m", "WARN": "\033[93m", "ERROR": "\033[91m"}
    reset = "\033[0m"
    pid = f"[{os.getpid()}]"
    print(f"{colors.get(level, '')}{level:5} {pid}: {msg}{reset}")
def log(msg, level="INFO"):
    """Colored logging"""
    colors = {"INFO": "\033[94m", "OK": "\033[92m", "WARN": "\033[93m", "ERROR": "\033[91m"}
    reset = "\033[0m"
    pid = f"[{os.getpid()}]"
    # Fix for Windows encoding issues
    try:
        safe_msg = msg.replace("✓", "[OK]").replace("✗", "[FAIL]").replace("⚠", "[WARN]")
        print(f"{level:5} {pid}: {safe_msg}")
    except:
        print(f"{level:5} {pid}: {repr(msg)}")

def check_internet():
    """Test internet connectivity"""
    log("Checking internet connectivity...", "INFO")
    try:
        urlopen("https://www.google.com", timeout=2)
        log("✓ Internet connection OK", "OK")
        return True
    except URLError:
        log("✗ No internet connection", "ERROR")
        return False

def find_hip_installer():
    """Find available HIP SDK installers"""
    log("Searching for available HIP SDK versions...", "INFO")
    
    # AMD's official download URLs (as of March 2026)
    hip_urls = [
        "https://rocmdocs.amd.com/en/latest/deploy/windows/",  # Documentation page
        "https://github.com/ROCmSoftwarePlatform/HIP/releases",  # GitHub releases
    ]
    
    # Known direct installer URLs (may change)
    download_links = {
        "HIP SDK 6.1.0": "https://repo.radeon.com/rocm/hip/hip_6.1.0_windows.exe",
        "HIP SDK 6.0.0": "https://repo.radeon.com/rocm/hip/hip_6.0.0_windows.exe",
        "HIP SDK 5.7.0": "https://repo.radeon.com/rocm/hip/hip_5.7.0_windows.exe",
    }
    
    log("Attempting to download HIP SDK installer...", "INFO")
    
    for version, url in download_links.items():
        try:
            log(f"Trying {version}...", "INFO")
            req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urlopen(req, timeout=10) as response:
                if response.status == 200 or response.status == 302:
                    log(f"✓ Found {version}: {url}", "OK")
                    return url, version
        except (HTTPError, URLError, Exception) as e:
            log(f"✗ {version} not available: {e}", "WARN")
            continue
    
    log("✗ Could not find HIP SDK installer online", "ERROR")
    return None, None
    
    # Try GitHub API for latest HIP releases
    log("Querying GitHub for HIP releases...", "INFO")
    try:
        import json
        api_url = "https://api.github.com/repos/ROCmSoftwarePlatform/HIP/releases"
        req = Request(api_url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/vnd.github.v3+json'})
        
        with urlopen(req, timeout=10) as response:
            releases = json.loads(response.read().decode())
            
            # Look for Windows installer asset
            for release in releases[:10]:  # Check first 10 releases
                tag = release.get('tag_name', '')
                log(f"Checking release {tag}...", "INFO")
                
                for asset in release.get('assets', []):
                    name = asset.get('name', '').lower()
                    if 'windows' in name and ('.exe' in name or '.msi' in name or 'installer' in name):
                        url = asset.get('browser_download_url')
                        log(f"✓ Found HIP SDK {tag}: {name}", "OK")
                        return url, tag
    
    except Exception as e:
        log(f"⚠ GitHub API query failed: {e}", "WARN")
    
    log("✗ Could not find HIP SDK installer online", "ERROR")
    return None, None

def download_hip_installer(url, filename=None):
    """Download HIP installer"""
    if not filename:
        filename = f"hip_installer.exe"
    
    filepath = Path(tempfile.gettempdir()) / filename
    file_size_mb = None
    
    log(f"Downloading HIP installer to {filepath}...", "INFO")
    log(f"URL: {url}", "INFO")
    
    try:
        req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        
        with urlopen(req, timeout=60) as response:
            total_size = int(response.headers.get('content-length', 0))
            
            with open(filepath, 'wb') as f:
                chunk_size = 1024 * 1024  # 1MB chunks
                downloaded = 0
                
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        mb = downloaded / (1024 * 1024)
                        total_mb = total_size / (1024 * 1024)
                        log(f"Downloaded {mb:.1f}MB / {total_mb:.1f}MB ({percent:.0f}%)", "INFO")
        
        if filepath.exists():
            size_mb = filepath.stat().st_size / (1024 * 1024)
            log(f"✓ Download complete: {size_mb:.1f}MB", "OK")
            return str(filepath)
        else:
            log("✗ Download file not found", "ERROR")
            return None
            
    except Exception as e:
        log(f"✗ Download failed: {e}", "ERROR")
        return None

def install_hip_sdk(installer_path):
    """Install HIP SDK"""
    log(f"Installing HIP SDK from {installer_path}...", "INFO")
    log("Request: Run this installer as Administrator!", "WARN")
    
    try:
        # Try silent install first
        log("Attempting silent installation...", "INFO")
        result = subprocess.run(
            [installer_path, "/S"],
            capture_output=True,
            timeout=300
        )
        
        if result.returncode == 0:
            log("✓ Silent installation completed", "OK")
            return True
        else:
            log("⚠ Silent install failed or pending, launching interactive installer...", "WARN")
            # Launch interactive
            subprocess.Popen([installer_path])
            log("! Installer window opened. Please complete installation manually.", "WARN")
            input("Press Enter after HIP installation is complete...")
            return True
            
    except Exception as e:
        log(f"✗ Installation failed: {e}", "ERROR")
        return False

def verify_hip_installation():
    """Verify HIP SDK is installed"""
    log("Verifying HIP SDK installation...", "INFO")
    
    hip_paths = [
        Path("C:\\Program Files\\AMD\\HIP"),
        Path("C:\\Program Files (x86)\\AMD\\HIP"),
        Path(os.path.expanduser("~")) / "AppData" / "Local" / "AMD" / "HIP",
    ]
    
    for path in hip_paths:
        if path.exists():
            log(f"✓ Found HIP installation at: {path}", "OK")
            return str(path)
    
    log("✗ HIP SDK not found at standard locations", "ERROR")
    return None

def set_environment_variables(hip_path):
    """Set up HIP environment variables"""
    log("Setting environment variables...", "INFO")
    
    env_vars = {
        "HIP_PATH": hip_path,
        "ROCM_HOME": hip_path,
        "HIP_DEVICE_ORDER": "PCI",
        "HIP_VISIBLE_DEVICES": "0",
    }
    
    # Set for current process
    for key, value in env_vars.items():
        os.environ[key] = value
        log(f"  {key}={value}", "INFO")
    
    # Set permanently (User scope)
    try:
        for key, value in env_vars.items():
            subprocess.run(
                ["setx", key, value],
                capture_output=True,
                check=False
            )
    except Exception as e:
        log(f"⚠ Could not set permanent environment variables: {e}", "WARN")
    
    # Add HIP bin to PATH
    hip_bin = Path(hip_path) / "bin"
    if hip_bin.exists():
        os.environ["PATH"] = str(hip_bin) + ";" + os.environ.get("PATH", "")
        log(f"Added HIP bin to PATH: {hip_bin}", "INFO")
    
    log("✓ Environment variables set", "OK")

def test_torch_gpu():
    """Test PyTorch GPU access"""
    log("Testing PyTorch GPU access...", "INFO")
    
    try:
        import torch
        log(f"PyTorch version: {torch.__version__}", "INFO")
        
        if torch.cuda.is_available():
            log(f"✓ CUDA/GPU available!", "OK")
            log(f"  GPU count: {torch.cuda.device_count()}", "INFO")
            log(f"  Device 0: {torch.cuda.get_device_name(0)}", "INFO")
            
            # Simple compute test
            x = torch.randn(1000, 1000, device='cuda')
            y = torch.randn(1000, 1000, device='cuda')
            z = torch.matmul(x, y)
            log(f"✓ GPU computation successful!", "OK")
            return True
        else:
            log("✗ CUDA/GPU not available in PYTORCHC", "WARN")
            return False
    except Exception as e:
        log(f"✗ PyTorch GPU test failed: {e}", "ERROR")
        return False

def main():
    log("=" * 70, "INFO")
    log("RocM/HIP Automated Setup for Windows AMD GPU", "INFO")
    log("Target: AMD Radeon RX 7700 XT", "INFO")
    log("=" * 70, "INFO")
    
    print()
    
    # Check prerequisites
    if not check_internet():
        log("Cannot proceed without internet", "ERROR")
        return 1
    
    print()
    
    # Find HIP installer
    hip_url, hip_version = find_hip_installer()
    if not hip_url:
        log("\n⚠ Could not find HIP installer online.", "WARN")
        log("Manual Installation Required:", "WARN")
        log("  1. Visit: https://rocmdocs.amd.com/en/latest/deploy/windows/install/", "WARN")
        log("  2. Download HIP SDK installer", "WARN")
        log("  3. Run installer as Administrator", "WARN")
        log("  4. Re-run this script after installation", "WARN")
        return 1
    
    print()
    
    # Download
    installer_path = download_hip_installer(hip_url)
    if not installer_path:
        log("Failed to download HIP installer", "ERROR")
        return 1
    
    print()
    
    # Install
    if not install_hip_sdk(installer_path):
        log("HIP installation aborted or failed", "ERROR")
        return 1
    
    # Give system time to complete installation
    log("Waiting for installation to complete...", "INFO")
    time.sleep(10)
    
    print()
    
    # Verify
    hip_path = verify_hip_installation()
    if not hip_path:
        log("HIP installation could not be verified", "ERROR")
        log("Please verify installation manually and restart PowerShell", "WARN")
        return 1
    
    print()
    
    # Configure environment
    set_environment_variables(hip_path)
    
    print()
    
    # Test
    gpu_ok = test_torch_gpu()
    
    print()
    log("=" * 70, "INFO")
    if gpu_ok:
        log("✓ RocM/HIP Setup Complete - GPU Ready!", "OK")
    else:
        log("⚠ HIP installed but GPU access needs verification", "WARN")
        log("Next steps:", "INFO")
        log("  1. Restart PowerShell/VS Code", "INFO")
        log("  2. Run: python check_gpu.py", "INFO")
        log("  3. Check for driver updates if needed", "INFO")
    log("=" * 70, "INFO")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
def log(msg, level="INFO"):
    """Colored logging"""
    pid = f"[{os.getpid()}]"
    # Fix for Windows encoding issues
    safe_msg = msg.replace("✓", "[OK]").replace("✗", "[FAIL]").replace("⚠", "[WARN]")
    print(f"{level:5} {pid}: {safe_msg}")
