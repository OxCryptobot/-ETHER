# One-shot: pull latest, install task if needed, start daemon (foreground OR scheduled)
param(
    [switch]$Foreground,
    [switch]$NoPull
)

$ErrorActionPreference = "Continue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force

$env:ETHER_GIT_RESET_OK = "1"
$env:ETHER_PULL_SOFT = "1"
$env:ETHER_FLYWHEEL_PUSH = "1"
$env:PYTHONIOENCODING = "utf-8"

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

if ($Foreground) {
    Write-Host "Starting daemon in FOREGROUND (Ctrl+C to stop)..."
    & $Py (Join-Path $Root "scripts\ether_daemon.py")
    exit $LASTEXITCODE
}

# Background via Scheduled Task
& powershell -ExecutionPolicy Bypass -File (Join-Path $Root "scripts\install_windows_daemon.ps1")
if ($LASTEXITCODE -ne 0 -and -not (Get-ScheduledTask -TaskName "ETHER-Daemon" -ErrorAction SilentlyContinue)) {
    Write-Host "Scheduled task install failed — falling back to foreground."
    & $Py (Join-Path $Root "scripts\ether_daemon.py")
    exit $LASTEXITCODE
}

Start-ScheduledTask -TaskName "ETHER-Daemon" -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3
$info = Get-ScheduledTaskInfo -TaskName "ETHER-Daemon" -ErrorAction SilentlyContinue
Write-Host "Task last result: $($info.LastTaskResult)  last run: $($info.LastRunTime)"
$hb = Join-Path $Root "memory\daemon\heartbeat.txt"
if (Test-Path $hb) {
    Write-Host "Heartbeat: $(Get-Content $hb -Raw)"
} else {
    Write-Host "No heartbeat yet — check memory\daemon\daemon.log"
}
