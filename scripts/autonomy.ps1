# @ETHER fully autonomous launcher — no manual commands after start
# Double-click or run once:
#   powershell -ExecutionPolicy Bypass -File .\scripts\autonomy.ps1
#
# It will:
#   - activate venv
#   - load .env automatically (via Python)
#   - loop forever: pull → test → agentic pipeline → push ONLY if gates pass

$ErrorActionPreference = "Continue"
Set-Location (Split-Path $PSScriptRoot -Parent)

# Ensure venv
if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "Creating venv..." -ForegroundColor Yellow
    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
}

# Execution policy for this process only
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
}

# Seed .env from example if missing
if (-not (Test-Path ".\.env") -and (Test-Path ".\.env.example")) {
    Copy-Item ".\.env.example" ".\.env"
    Write-Host "Created .env from .env.example" -ForegroundColor Yellow
}

Write-Host "@ETHER AUTONOMY starting (Ctrl+C to stop)" -ForegroundColor Cyan
Write-Host "Reports: memory\flywheel\latest.json  |  heartbeat: memory\flywheel\heartbeat.txt"

# Hands-off loop — all config from .env
& .\.venv\Scripts\python.exe scripts\flywheel.py --autonomous
exit $LASTEXITCODE
