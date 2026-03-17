param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliArgs
)

$RepoRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    throw "Missing virtual environment python at $PythonExe"
}

if (-not $CliArgs -or $CliArgs.Count -eq 0) {
    $CliArgs = @("--help")
}

Push-Location $RepoRoot
try {
    & $PythonExe -m offline_agents.cli @CliArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
