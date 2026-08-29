# ONE command: pull, install, register ensure-watchdog, start daemon.
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
Write-Host " @ETHER autonomy start"
Write-Host " root: $Root"
Write-Host "========================================"

$stopScript = Join-Path $Root "scripts\stop_daemon.ps1"
if (Test-Path $stopScript) {
  & powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File $stopScript
}
Start-Sleep -Seconds 1

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
$env:ETHER_CURRICULUM = "1"
$env:ETHER_AUTO_ENQUEUE = "1"
$env:ETHER_GUARDIAN_AUTO_BASELINE = "1"
$env:PYTHONIOENCODING = "utf-8"
if ($NoDashboard) { $env:ETHER_DAEMON_DASHBOARD = "0" } else { $env:ETHER_DAEMON_DASHBOARD = "1" }
$env:ETHER_DAEMON_FLYWHEEL = "1"
$env:ETHER_DAEMON_BATCH = "1"

if (-not $NoPull) {
  Write-Host "[git] fetch + reset origin/main"
  git fetch origin 2>&1 | Out-Host
  git reset --hard origin/main 2>&1 | Out-Host
}

$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Py)) {
  Write-Host "[venv] creating..."
  python -m venv .venv
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

# Always register OS-level ensure so process survives without chat
$inst = Join-Path $Root "scripts\install_windows_daemon.ps1"
if (Test-Path $inst) {
  Write-Host "[autonomy] registering ETHER-Daemon + ETHER-Ensure"
  & powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File $inst
}

if ($Background) {
  Write-Host "[start] background via ensure"
  $ensure = Join-Path $Root "scripts\ensure_daemon.ps1"
  & powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File $ensure
  Start-Sleep -Seconds 6
  $hb = Join-Path $Root "memory\daemon\heartbeat.txt"
  if (Test-Path $hb) {
    Write-Host "[ok] heartbeat: $(Get-Content $hb -Raw)"
    Write-Host "Dashboard: http://127.0.0.1:8787"
  } else {
    Write-Host "[warn] no heartbeat yet — ETHER-Ensure will retry every 5 min"
  }
  exit 0
}

Write-Host "[start] FOREGROUND daemon (Ctrl+C stops this window; Ensure will restart)"
Write-Host "  Dashboard: http://127.0.0.1:8787"
& $Py $Daemon
exit $LASTEXITCODE
