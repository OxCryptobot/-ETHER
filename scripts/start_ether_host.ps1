# ETHER host launcher - restarts on any crash, stops only on Ctrl+C
#
#   powershell -ExecutionPolicy Bypass -File .\scripts\start_ether_host.ps1

$ErrorActionPreference = "Continue"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not (Test-Path (Join-Path $Root "core"))) { $Root = (Get-Location).Path }
Set-Location $Root

$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { Write-Error "Missing $Py"; exit 1 }

Write-Host "ETHER HOST | http://127.0.0.1:8787/agent" -ForegroundColor Green
Write-Host "Ctrl+C to stop" -ForegroundColor DarkGray
Write-Host ""

while ($true) {
    Write-Host "Sync origin/main..." -ForegroundColor Cyan
    git fetch origin 2>$null | Out-Null
    git reset --hard origin/main 2>&1 | Out-Host

    Write-Host "Starting..." -ForegroundColor Cyan
    & $Py "scripts\ether_host.py"
    $code = $LASTEXITCODE
    if ($null -eq $code) { $code = 1 }

    if ($code -eq 0) {
        Write-Host "Stopped." -ForegroundColor Green
        break
    }

    Write-Host "Exited $code - restarting in 3s..." -ForegroundColor Yellow
    Start-Sleep -Seconds 3
}
