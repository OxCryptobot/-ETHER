# Start host_agent + dashboard. Always sync to origin/main first so git never starts stuck.
#   powershell -ExecutionPolicy Bypass -File .\scripts\start_agent_stack.ps1

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not (Test-Path (Join-Path $Root "core"))) { $Root = (Get-Location).Path }
Set-Location $Root

$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { Write-Error "Missing $Py"; exit 1 }

Write-Host "Syncing to origin/main..." -ForegroundColor Cyan
git fetch origin 2>&1 | Out-Host
git reset --hard origin/main 2>&1 | Out-Host

Write-Host "Starting dashboard on http://127.0.0.1:8787/agent" -ForegroundColor Cyan
Start-Process -FilePath $Py -ArgumentList "-m","uvicorn","dashboard.app:app","--host","127.0.0.1","--port","8787" -WorkingDirectory $Root -WindowStyle Normal

Start-Sleep -Seconds 2

Write-Host "Starting host_agent (auto-sync on boot+poll)" -ForegroundColor Cyan
Start-Process -FilePath $Py -ArgumentList "scripts\host_agent.py" -WorkingDirectory $Root -WindowStyle Normal

Write-Host ""
Write-Host "Open:  http://127.0.0.1:8787/agent" -ForegroundColor Green
Write-Host "Agent self-heals diverged git (reset --hard origin/main)" -ForegroundColor DarkGray
