# RocM GPU Setup for Windows - AMD Radeon RX 7700 XT
# This script installs HIP SDK, rocm-core, and configures PyTorch for GPU acceleration

param(
    [string]$HIPRelease = "6.1.0",
    [string]$InstallDir = "C:\Program Files\AMD"
)

Write-Host "=== RocM Setup for Windows (AMD RX 7700 XT) ===" -ForegroundColor Green
Write-Host "Target Release: HIP SDK v$HIPRelease" -ForegroundColor Cyan

# Step 1: Verify GPU is present
Write-Host "`n[Step 1] Verifying GPU..." -ForegroundColor Yellow
$gpu = Get-PnpDevice -Class Display | Where-Object { $_.Name -match "AMD Radeon" } | Select-Object -First 1
if ($gpu) {
    Write-Host "✓ GPU Found: $($gpu.Name)" -ForegroundColor Green
} else {
    Write-Host "✗ No AMD Radeon GPU found" -ForegroundColor Red
    exit 1
}

# Step 2: Download HIP SDK
Write-Host "`n[Step 2] Downloading HIP SDK..." -ForegroundColor Yellow
$hipUrl = "https://repo.radeon.com/rocm/hip/hip_6.1.0_windows.exe"
$hipInstaller = "$env:TEMP\hip_installer.exe"

try {
    Write-Host "Downloading from: $hipUrl"
    Invoke-WebRequest -Uri $hipUrl -OutFile $hipInstaller -ErrorAction Stop
    Write-Host "✓ Downloaded HIP SDK to: $hipInstaller" -ForegroundColor Green
} catch {
    Write-Host "✗ Download failed. Trying alternative URL..." -ForegroundColor Yellow
    $hipUrl = "https://rocmdocs.amd.com/en/latest/deploy/windows/install/"
    Write-Host "Please download HIP SDK manually from: https://rocmdocs.amd.com/en/latest/deploy/windows/install/" -ForegroundColor Yellow
    Write-Host "Then run the installer and re-run this script." -ForegroundColor Yellow
}

# Step 3: Install HIP SDK (if downloaded)
if (Test-Path $hipInstaller) {
    Write-Host "`n[Step 3] Installing HIP SDK..." -ForegroundColor Yellow
    Write-Host "Starting installer: $hipInstaller" -ForegroundColor Cyan
    
    Start-Process -FilePath $hipInstaller -Wait -ArgumentList "/S" -ErrorAction SilentlyContinue
    
    if ($LASTEXITCODE -eq 0 -or (Test-Path "C:\Program Files\AMD\HIP\bin\hipdevicecount.exe" -ErrorAction SilentlyContinue)) {
        Write-Host "✓ HIP SDK installed successfully" -ForegroundColor Green
    } else {
        Write-Host "! HIP SDK installer started. Please complete installation manually and press Enter..." -ForegroundColor Yellow
        Read-Host
    }
} else {
    Write-Host "! HIP SDK installer not found. Continuing with environment setup..." -ForegroundColor Yellow
}

# Step 4: Detect HIP installation
Write-Host "`n[Step 4] Detecting HIP installation..." -ForegroundColor Yellow
$hipPaths = @(
    "C:\Program Files\AMD\HIP",
    "C:\Program Files (x86)\AMD\HIP",
    "$env:LOCALAPPDATA\AMD\HIP"
)

$hipRoot = $null
foreach ($path in $hipPaths) {
    if (Test-Path $path -ErrorAction SilentlyContinue) {
        $hipRoot = $path
        Write-Host "✓ Found HIP at: $hipRoot" -ForegroundColor Green
        break
    }
}

if (-not $hipRoot) {
    Write-Host "! HIP installation not found. Make sure to install HIP SDK first." -ForegroundColor Yellow
    Write-Host "Download from: https://rocmdocs.amd.com/en/latest/deploy/windows/install/" -ForegroundColor Cyan
    $hipRoot = "C:\Program Files\AMD\HIP"
    Write-Host "Using expected path: $hipRoot (please install if not present)" -ForegroundColor Yellow
}

# Step 5: Detect GPU and set preferences
Write-Host "`n[Step 5] Configuring GPU device selection..." -ForegroundColor Yellow
$gpu_id = 0
Write-Host "Setting GPU Device ID: $gpu_id (AMD Radeon RX 7700 XT)" -ForegroundColor Cyan

# Step 6: Configure Environment Variables
Write-Host "`n[Step 6] Setting Environment Variables..." -ForegroundColor Yellow

$env_vars = @{
    "HIP_PATH" = $hipRoot
    "HIP_DEVICE_ORDER" = "PCI"
    "HIP_VISIBLE_DEVICES" = $gpu_id
    "ROCM_HOME" = $hipRoot
    "GPU_DEVICE_ORDINAL" = $gpu_id
}

foreach ($key in $env_vars.Keys) {
    $value = $env_vars[$key]
    Write-Host "Setting $key = $value"
    [Environment]::SetEnvironmentVariable($key, $value, "User")
    [Environment]::SetEnvironmentVariable($key, $value, "Process")
}

# Add HIP to PATH
$hipBinPath = Join-Path $hipRoot "bin"
if (Test-Path $hipBinPath) {
    if (-not $env:PATH.Contains($hipBinPath)) {
        Write-Host "Adding HIP bin to PATH: $hipBinPath"
        $env:PATH = "$hipBinPath;$env:PATH"
        [Environment]::SetEnvironmentVariable("PATH", "$hipBinPath;$([Environment]::GetEnvironmentVariable('PATH', 'User'))", "User")
    }
}

# Step 7: Verify PyTorch GPU detection
Write-Host "`n[Step 7] Verifying PyTorch GPU access..." -ForegroundColor Yellow

$pythonPath = "C:\Users\Joseph\Desktop\FAB_Sim\.venv\Scripts\python.exe"
if (Test-Path $pythonPath) {
    $testCode = @"
import torch
print("PyTorch version:", torch.__version__)
print("CUDA available:", torch.cuda.is_available())
print("GPU list:", torch.cuda.device_count() if torch.cuda.is_available() else "No GPU")
print("GPU Name:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "N/A")
print("HIP available:", hasattr(torch, 'is_hip') and torch.is_hip)
try:
    import torch.hip
    print("HIP module found:", True)
except:
    print("HIP module found:", False)
"@
    
    Write-Host "Running PyTorch GPU detection test..." -ForegroundColor Cyan
    & $pythonPath -c $testCode
} else {
    Write-Host "! Python venv not found at expected path" -ForegroundColor Yellow
}

# Step 8: Summary
Write-Host "`n=== Setup Complete ===" -ForegroundColor Green
Write-Host "Environment variables set:"
foreach ($key in $env_vars.Keys) {
    Write-Host "  $key = $($env_vars[$key])" -ForegroundColor Cyan
}

Write-Host "`nNext steps:" -ForegroundColor Yellow
Write-Host "1. Restart PowerShell/VS Code for environment changes to take effect" -ForegroundColor White
Write-Host "2. Run GPU tests: python check_gpu.py" -ForegroundColor White
Write-Host "3. Verify with: python -c 'import torch; print(torch.cuda.is_available())'" -ForegroundColor White

Write-Host "`nFor more info, visit: https://rocmdocs.amd.com/en/latest/deploy/windows/install/" -ForegroundColor Cyan
