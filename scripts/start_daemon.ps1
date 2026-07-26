# ONE command to run @ETHER. Default = FOREGROUND (most reliable).
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\scripts\start_daemon.ps1
#   powershell -ExecutionPolicy Bypass -File .\scripts\start_daemon.ps1 -Background
param(
    [switch]$Background,
    [switch]$NoPull,
    [switch]$NoDashboard
)

$ErrorActionPreference = "Continue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $Root
try { Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force } catch {}

Write-Host "========================================"
Write-Host " @ETHER single-process start"
Write-Host " root: $Root"
Write-Host "========================================"

# 1) stop duplicates
$stopScript = Join-Path $Root "scripts\stop_daemon.ps1"
if (Test-Path $stopScript) {
  & powershell -NoProfile -ExecutionPolicy Bypass -File $stopScript
}
Start-Sleep -Seconds 1

$env:ETHER_GIT_RESET_OK = "1"
$env:ETHER_PULL_SOFT = "1"
$env:ETHER_FLYWHEEL_PUSH = "1"
$env:PYTHONIOENCODING = "utf-8"
if ($NoDashboard) { $env:ETHER_DAEMON_DASHBOARD = "0" } else { $env:ETHER_DAEMON_DASHBOARD = "1" }

# 2) pull
if (-not $NoPull) {
  Write-Host "[git] fetch + reset origin/main"
  git fetch origin 2>&1 | Out-Host
  git reset --hard origin/main 2>&1 | Out-Host
}

# 3) venv
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Py)) {
  Write-Host "[venv] creating..."
  python -m venv .venv
  if (-not (Test-Path -LiteralPath $Py)) {
    Write-Error "Failed to create venv at $Py"
    exit 1
  }
  & $Py -m pip install -U pip
  & $Py -m pip install -e ".[dev]"
} else {
  Write-Host "[pip] editable install"
  & $Py -m pip install -e ".[dev]" -q
}

$Daemon = Join-Path $Root "scripts\ether_daemon.py"
if (-not (Test-Path -LiteralPath $Daemon)) {
  Write-Error "Missing $Daemon after pull"
  exit 1
}

# 4) start
if ($Background) {
  Write-Host "[start] trying Scheduled Task background mode..."
  $inst = Join-Path $Root "scripts\install_windows_daemon.ps1"
  & powershell -NoProfile -ExecutionPolicy Bypass -File $inst
  if ($LASTEXITCODE -ne 0) {
    Write-Host "[start] task failed - falling back to hidden background process"
    Start-Process -FilePath $Py -ArgumentList "`"$Daemon`"" -WorkingDirectory $Root -WindowStyle Hidden
  } else {
    Start-ScheduledTask -TaskName "ETHER-Daemon" -ErrorAction SilentlyContinue
  }
  Start-Sleep -Seconds 6
  $hb = Join-Path $Root "memory\daemon\heartbeat.txt"
  if (Test-Path $hb) {
    Write-Host "[ok] heartbeat: $(Get-Content $hb -Raw)"
    Write-Host "You may close this window."
    Write-Host "Dashboard: http://127.0.0.1:8787"
  } else {
    Write-Host "[warn] no heartbeat - run without -Background to see errors"
    exit 1
  }
  exit 0
}

Write-Host "[start] FOREGROUND daemon (Ctrl+C to stop)"
Write-Host "  This ONE window = flywheel + batch + dashboard"
Write-Host "  Dashboard: http://127.0.0.1:8787"
Write-Host ""
& $Py $Daemon
exit $LASTEXITCODE
