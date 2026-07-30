# One-window launcher from PowerShell
$ErrorActionPreference = "Continue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force

$env:ETHER_ROOT = $Root
$env:ETHER_GIT_RESET_OK = "1"
$env:ETHER_PULL_SOFT = "1"
# MEAS-005: report pushes are operator opt-in (ETHER_FLYWHEEL_PUSH=1 in .env); default off.
# The .env peek keeps the opt-in alive here: core/dotenv.py never overrides an
# already-set variable, so a launcher-set "0" would silently shadow a .env "1".
if (-not $env:ETHER_FLYWHEEL_PUSH) {
  $env:ETHER_FLYWHEEL_PUSH = "0"
  $dotenv = Join-Path $Root ".env"
  if ((Test-Path -LiteralPath $dotenv) -and (Select-String -LiteralPath $dotenv -Pattern '^\s*ETHER_FLYWHEEL_PUSH\s*=\s*1\s*(#.*)?$' -Quiet)) {
    $env:ETHER_FLYWHEEL_PUSH = "1"
  }
}
$env:ETHER_OPEN_BROWSER = "1"
$env:PYTHONIOENCODING = "utf-8"

if (-not (Test-Path .\.venv\Scripts\python.exe)) {
  Write-Host "Creating venv..."
  python -m venv .venv
  .\.venv\Scripts\python.exe -m pip install -U pip
  .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
}

& .\.venv\Scripts\python.exe .\scripts\desktop_runtime.py
