#!/usr/bin/env python3
"""
Interactive RocM Setup Wizard for Windows AMD GPU
Guides user through the entire setup process
"""

import os
import sys
import subprocess
from pathlib import Path

class Colors:
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

def print_header(title):
    """Print formatted header"""
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'=' * 70}{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}{title:^70}{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}{'=' * 70}{Colors.RESET}\n")

def print_info(msg):
    """Print info message"""
    print(f"{Colors.CYAN}[INFO]{Colors.RESET} {msg}")

def print_success(msg):
    """Print success message"""
    print(f"{Colors.GREEN}[OK]{Colors.RESET} {msg}")

def print_warn(msg):
    """Print warning message"""
    print(f"{Colors.YELLOW}[!]{Colors.RESET} {msg}")

def print_error(msg):
    """Print error message"""
    print(f"{Colors.RED}[ERROR]{Colors.RESET} {msg}")

def prompt_continue():
    """Prompt user to continue"""
    input(f"\n{Colors.GREEN}Press Enter to continue...{Colors.RESET}")

def prompt_yes_no(question):
    """Prompt for yes/no"""
    while True:
        response = input(f"\n{Colors.BOLD}{question} (y/n): {Colors.RESET}").lower()
        if response in ['y', 'yes']:
            return True
        elif response in ['n', 'no']:
            return False
        else:
            print_warn("Please enter 'y' or 'n'")

def check_admin():
    """Check if script is running with admin privileges"""
    try:
        return os.getuid() == 0
    except AttributeError:
        # Windows
        import ctypes
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False

def detect_hip():
    """Detect if HIP SDK is installed"""
    hip_paths = [
        Path("C:\\Program Files\\AMD\\ROCm\\7.1"),
        Path("C:\\Program Files\\AMD\\ROCm\\7.0"),
        Path("C:\\Program Files\\AMD\\ROCm\\6.2"),
        Path("C:\\Program Files\\AMD\\ROCm\\6.1"),
        Path("C:\\Program Files\\AMD\\ROCm\\6.0"),
        Path("C:\\Program Files\\AMD\\HIP"),
        Path("C:\\Program Files (x86)\\AMD\\HIP"),
    ]
    
    for path in hip_paths:
        if path.exists():
            return path
    return None

def step_1_welcome():
    """Step 1: Welcome"""
    print_header("Welcome to RocM Setup Wizard")
    print(f"{Colors.BOLD}This wizard will configure your AMD RX 7700 XT GPU for PyTorch.{Colors.RESET}\n")
    print_info("System Information:")
    print_info(f"  GPU: AMD Radeon RX 7700 XT")
    print_info(f"  Target: RocM/HIP with CUDA backend")
    print_info(f"  OS: Windows")
    print("\n" + Colors.YELLOW + "Prerequisites:" + Colors.RESET)
    print_info("  1. HIP SDK installer downloaded (or will download now)")
    print_info("  2. Administrator password (for environment setup)")
    print_info("  3. Internet connection (already verified)")
    prompt_continue()

def step_2_check_hip():
    """Step 2: Check HIP installation"""
    print_header("Checking HIP SDK Installation")
    
    hip_path = detect_hip()
    
    if hip_path:
        print_success(f"HIP SDK found at: {hip_path}")
        return hip_path
    else:
        print_warn("HIP SDK not found on system")
        print("\n" + Colors.BOLD + "You need to install HIP SDK:" + Colors.RESET)
        print_info("1. Download from: https://rocmdocs.amd.com/en/latest/deploy/windows/install/")
        print_info("2. Look for 'HIP SDK for Windows'")
        print_info("3. Run installer as Administrator")
        print_info("4. Use default installation path (C:\\Program Files\\AMD\\HIP)")
        print_info("5. Re-run this wizard after installation")
        
        if prompt_yes_no("\nDo you need help downloading HIP SDK?"):
            print("\nOpening AMD ROCm documentation...")
            os.system('start https://rocmdocs.amd.com/en/latest/deploy/windows/install/')
        
        return None

def step_3_verify_hip(hip_path):
    """Step 3: Verify HIP installation"""
    print_header("Verifying HIP SDK Installation")
    
    critical_files = [
        hip_path / "bin" / "hipcc.exe",
        hip_path / "bin" / "hipconfig.exe",
        hip_path / "bin" / "hipInfo.exe",
    ]
    
    all_good = True
    for file_path in critical_files:
        if file_path.exists():
            print_success(f"Found: {file_path.name}")
        else:
            print_error(f"Missing: {file_path}")
            all_good = False
    
    if not all_good:
        print_error("\nHIP installation appears incomplete!")
        if prompt_yes_no("Reinstall HIP SDK?"):
            print_info("Please reinstall HIP SDK from:")
            print_info("  https://rocmdocs.amd.com/en/latest/deploy/windows/install/")
            return False
    
    print_success("HIP SDK installation verified!")
    prompt_continue()
    return True

def step_4_environment_vars(hip_path):
    """Step 4: Set environment variables"""
    print_header("Setting Environment Variables")
    
    print_warn("You may be prompted for Administrator privileges")
    print_info("Environment variables to set:")
    
    env_vars = {
        "HIP_PATH": str(hip_path),
        "ROCM_HOME": str(hip_path),
        "HIP_DEVICE_ORDER": "PCI",
        "HIP_VISIBLE_DEVICES": "0",
    }
    
    for key, value in env_vars.items():
        print_info(f"  {key} = {value}")
    
    if not prompt_yes_no("\nProceed with setting environment variables?"):
        print_warn("Skipped environment variable setup")
        return False
    
    # Set environment variables
    for key, value in env_vars.items():
        try:
            subprocess.run(
                ["setx", key, value],
                capture_output=True,
                check=True
            )
            print_success(f"Set: {key}")
        except subprocess.CalledProcessError:
            print_error(f"Failed to set {key} (may need Administrator)")
    
    # Add HIP to PATH
    try:
        current_path_result = subprocess.run(
            ["powershell", "-Command", 
             '[Environment]::GetEnvironmentVariable("PATH", "User")'],
            capture_output=True,
            text=True
        )
        current_path = current_path_result.stdout.strip()
        hip_bin = str(hip_path / "bin")
        
        if hip_bin not in current_path:
            new_path = f"{hip_bin};{current_path}"
            subprocess.run(
                ["setx", "PATH", new_path],
                capture_output=True,
                check=True
            )
            print_success("Added HIP to PATH")
    except Exception as e:
        print_warn(f"Could not add HIP to PATH: {e}")
    
    prompt_continue()
    return True

def step_5_restart():
    """Step 5: Restart advice"""
    print_header("Restart Required")
    
    print_warn("Windows environment variables require a restart to take effect.")
    print("\n" + Colors.BOLD + "Please do one of the following:" + Colors.RESET)
    print_info("  Option 1: Restart your computer (recommended)")
    print_info("  Option 2: Close and reopen PowerShell/VS Code")
    print_info("  Option 3: Logout and login to your Windows account")
    
    prompt_continue()

def step_6_test_torch(hip_path):
    """Step 6: Test PyTorch GPU"""
    print_header("Testing PyTorch GPU Access")
    
    print_info("Testing GPU access with PyTorch...\n")
    
    try:
        import torch
        print_success(f"PyTorch version: {torch.__version__}")
        
        if torch.cuda.is_available():
            print_success("GPU (CUDA) is available!")
            
            try:
                device_name = torch.cuda.get_device_name(0)
                print_success(f"Device 0: {device_name}")
                
                # Quick computation test
                print_info("\nRunning GPU computation test...")
                x = torch.randn(100, 100, device='cuda')
                y = torch.randn(100, 100, device='cuda')
                z = torch.matmul(x, y)
                
                print_success("GPU computation successful!")
                print_success(f"Result device: {z.device}")
                return True
                
            except Exception as e:
                print_error(f"GPU computation failed: {e}")
                return False
        else:
            print_warn("CUDA/GPU not available in PyTorch")
            print_warn("This is expected if:")
            print_info("  • You haven't restarted PowerShell/computer yet")
            print_info("  • AMD GPU driver needs update")
            print_info("  • PyTorch needs reinstallation")
            return False
            
    except ImportError:
        print_error("PyTorch not installed")
        print_info("Install with: pip install torch")
        return False
    except Exception as e:
        print_error(f"PyTorch test failed: {e}")
        return False

def step_7_summary(success):
    """Step 7: Summary"""
    print_header("Setup Complete")
    
    if success:
        print_success("GPU is ready for PyTorch!")
        print("\n" + Colors.BOLD + "Next steps:" + Colors.RESET)
        print_info("  1. Update training scripts to use GPU")
        print_info("  2. Test with: python -m rl_agents.collect_iql_mixed_data --device cuda ...")
        print_info("  3. Monitor performance (expect 20-100x speedup)")
    else:
        print_warn("GPU setup incomplete or needs verification")
        print("\n" + Colors.BOLD + "Next steps:" + Colors.RESET)
        print_info("  1. Restart PowerShell/Computer")
        print_info("  2. Run: python check_gpu.py")
        print_info("  3. If still not working:")
        print_info("     - Check GPU drivers: https://www.amd.com/en/support")
        print_info("     - Review: ROCM_SETUP_GUIDE.md")
    
    print()

def main():
    """Main wizard"""
    try:
        # Step 1: Welcome
        step_1_welcome()
        
        # Step 2: Check HIP
        hip_path = step_2_check_hip()
        if not hip_path:
            return 1
        
        # Step 3: Verify HIP
        if not step_3_verify_hip(hip_path):
            return 1
        
        # Step 4: Environment variables
        if not step_4_environment_vars(hip_path):
            return 1
        
        # Step 5: Restart advice
        step_5_restart()
        
        # Step 6: Test PyTorch
        gpu_works = step_6_test_torch(hip_path)
        
        # Step 7: Summary
        step_7_summary(gpu_works)
        
        return 0
        
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Setup cancelled by user{Colors.RESET}")
        return 1
    except Exception as e:
        print(f"\n{Colors.RED}Unexpected error: {e}{Colors.RESET}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
