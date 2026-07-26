# ONE entry point. Closes old instances, then starts a single daemon.
param(
    [switch]$Foreground,
    [switch]$NoPull,
    [switch]$NoDashboard
)

$ErrorActionPreference = "Continue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force

# Always stop duplicates first
& powershell -ExecutionPolicy Bypass -File (Join-Path $Root "scripts\stop_daemon.ps1")
Start-Sleep -Seconds 1

$env:ETHER_GIT_RESET_OK = "1"
$env:ETHER_PULL_SOFT = "1"
$env:ETHER_FLYWHEEL_PUSH = "1"
$env:PYTHONIOENCODING = "utf-8"
if ($NoDashboard) { $env:ETHER_DAEMON_DASHBOARD = "0" }

if (-not $NoPull) {
    git fetch origin 2>$null
    if ($env:ETHER_GIT_RESET_OK -eq "1") {
        git reset --hard origin/main 2>$null
    }
}

$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Host "Creating venv..."
    python -m venv .venv
    & $Py -m pip install -U pip
    & $Py -m pip install -e ".[dev]"
} else {
    & $Py -m pip install -e ".[dev]" -q
}

Write-Host ""
Write-Host "Starting SINGLE @ETHER daemon process..." -ForegroundColor Green
Write-Host "  (flywheel + batch + optional dashboard inside one Python process)"
Write-Host ""

if ($Foreground) {
    & $Py (Join-Path $Root "scripts\ether_daemon.py")
    exit $LASTEXITCODE
}

# Prefer scheduled task (zero windows after start)
& powershell -ExecutionPolicy Bypass -File (Join-Path $Root "scripts\install_windows_daemon.ps1")
$t = Get-ScheduledTask -TaskName "ETHER-Daemon" -ErrorAction SilentlyContinue
if ($null -eq $t) {
    Write-Host "Task install failed — using foreground instead."
    & $Py (Join-Path $Root "scripts\ether_daemon.py")
    exit $LASTEXITCODE
}

Start-ScheduledTask -TaskName "ETHER-Daemon" -ErrorAction SilentlyContinue
Start-Sleep -Seconds 5
$info = Get-ScheduledTaskInfo -TaskName "ETHER-Daemon" -ErrorAction SilentlyContinue
Write-Host "Scheduled Task LastTaskResult=$($info.LastTaskResult) LastRun=$($info.LastRunTime)"
$hb = Join-Path $Root "memory\daemon\heartbeat.txt"
if (Test-Path $hb) {
    Write-Host "Heartbeat: $(Get-Content $hb -Raw)"
} else {
    Write-Host "No heartbeat yet — open: $Root\memory\daemon\daemon.log"
}
Write-Host ""
Write-Host "You can CLOSE this PowerShell window. Daemon runs in the background."
Write-Host "Dashboard: http://127.0.0.1:8787"
Write-Host "Stop later: powershell -File .\scripts\stop_daemon.ps1"
