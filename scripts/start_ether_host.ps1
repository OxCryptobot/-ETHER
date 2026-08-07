# ONE window ETHER host (dashboard + agent + foreman)
#   powershell -ExecutionPolicy Bypass -File .\scripts\start_ether_host.ps1

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not (Test-Path (Join-Path $Root "core"))) { $Root = (Get-Location).Path }
Set-Location $Root

$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { Write-Error "Missing $Py"; exit 1 }

Write-Host "Sync origin/main..." -ForegroundColor Cyan
git fetch origin 2>&1 | Out-Null
git reset --hard origin/main 2>&1 | Out-Host

Write-Host "ETHER HOST — one window | dashboard http://127.0.0.1:8787/agent" -ForegroundColor Green
& $Py scripts\ether_host.py
