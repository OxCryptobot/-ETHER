# One-window launcher from PowerShell (no second windows)
$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..")
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force

$env:ETHER_GIT_RESET_OK = "1"
$env:ETHER_PULL_SOFT = "1"
$env:ETHER_FLYWHEEL_PUSH = "1"
$env:ETHER_OPEN_BROWSER = "1"
$env:PYTHONIOENCODING = "utf-8"

if (-not (Test-Path .\.venv\Scripts\python.exe)) {
  python -m venv .venv
  .\.venv\Scripts\python.exe -m pip install -U pip
  .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
}

& .\.venv\Scripts\python.exe .\scripts\desktop_runtime.py
