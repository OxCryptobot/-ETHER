# @ETHER Windows bootstrap — venv only, never touch Program Files ether.exe
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
Write-Host "@ETHER bootstrap" -ForegroundColor Cyan

Stop-Process -Name python -Force -ErrorAction SilentlyContinue

if (Test-Path .git\MERGE_HEAD) {
  Write-Host "Aborting unfinished merge..."
  git merge --abort 2>$null
}

git fetch origin
git status --porcelain
if ($env:ETHER_GIT_RESET_OK -eq "1") {
  Write-Host "ETHER_GIT_RESET_OK=1 → reset --hard origin/main"
  git reset --hard origin/main
} else {
  git pull --ff-only origin main
}

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
if (-not (Test-Path .\.venv)) {
  python -m venv .venv
}
& .\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[dev]"

Write-Host "doctor:" -ForegroundColor Cyan
python -m cli.main doctor
Write-Host "Done. Use: .\.venv\Scripts\Activate.ps1 ; python -m cli.main ..." -ForegroundColor Green
