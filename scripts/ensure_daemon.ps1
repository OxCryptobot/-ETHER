# Ensures @ETHER daemon is alive on the REAL install path (not GH Actions _work).
# Prefer: $env:ETHER_ROOT > C:\Users\Otcde\ETHER > script parent repo

$ErrorActionPreference = "Continue"

function Resolve-EtherRoot {
  if ($env:ETHER_ROOT -and (Test-Path -LiteralPath $env:ETHER_ROOT)) {
    return (Resolve-Path -LiteralPath $env:ETHER_ROOT).Path
  }
  $candidates = @(
    "C:\Users\Otcde\ETHER",
    "C:\ETHER",
    (Join-Path $PSScriptRoot "..")
  )
  foreach ($c in $candidates) {
    if (Test-Path -LiteralPath $c) {
      $p = (Resolve-Path -LiteralPath $c).Path
      if (Test-Path -LiteralPath (Join-Path $p "scripts\ether_daemon.py")) { return $p }
      if (Test-Path -LiteralPath (Join-Path $p "pyproject.toml")) { return $p }
    }
  }
  return (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
}

$Root = Resolve-EtherRoot
Set-Location -LiteralPath $Root
$env:ETHER_ROOT = $Root

$Py = Join-Path $Root ".venv\Scripts\python.exe"
$Daemon = Join-Path $Root "scripts\ether_daemon.py"
$Hb = Join-Path $Root "memory\daemon\heartbeat.txt"
$PidFile = Join-Path $Root "memory\daemon\daemon.pid"
$Log = Join-Path $Root "memory\daemon\ensure.log"

function Write-Log([string]$msg) {
  $line = "[{0}] {1}" -f (Get-Date).ToUniversalTime().ToString("o"), $msg
  try {
    $dir = Split-Path $Log -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    Add-Content -LiteralPath $Log -Value $line -Encoding UTF8
  } catch {}
  Write-Host $line
}

Write-Log "ETHER_ROOT=$Root"

if (-not (Test-Path -LiteralPath $Py)) {
  Write-Log "MISSING venv — creating"
  try {
    python -m venv .venv
    & $Py -m pip install -U pip -q
    & $Py -m pip install -e ".[dev]" -q
  } catch {
    Write-Log "venv bootstrap failed: $_"
    exit 1
  }
}

if (-not (Test-Path -LiteralPath $Daemon)) {
  Write-Log "MISSING daemon — soft pull"
  try { git fetch origin 2>&1 | Out-Null; git reset --hard origin/main 2>&1 | Out-Null } catch {}
  if (-not (Test-Path -LiteralPath $Daemon)) { Write-Log "still missing daemon"; exit 1 }
}

function Test-DaemonAlive {
  if (-not (Test-Path -LiteralPath $PidFile)) { return $false }
  try { $pidVal = [int]((Get-Content -LiteralPath $PidFile -Raw).Trim()) } catch { return $false }
  if ($pidVal -le 0) { return $false }
  try { $p = Get-Process -Id $pidVal -ErrorAction Stop; if ($p) { return $true } } catch { return $false }
  return $false
}

function Test-HeartbeatFresh([int]$maxAgeSec = 180) {
  if (-not (Test-Path -LiteralPath $Hb)) { return $false }
  try {
    $raw = (Get-Content -LiteralPath $Hb -Raw).Trim()
    $dt = [datetime]::Parse($raw, $null, [System.Globalization.DateTimeStyles]::RoundtripKind)
    $age = ([datetime]::UtcNow - $dt.ToUniversalTime()).TotalSeconds
    return ($age -ge 0 -and $age -le $maxAgeSec)
  } catch { return $false }
}

$alive = Test-DaemonAlive
$fresh = Test-HeartbeatFresh 180

if ($alive -and $fresh) {
  Write-Log "OK daemon alive + heartbeat fresh"
  exit 0
}

Write-Log "daemon needs start (alive=$alive fresh=$fresh)"

try {
  $env:ETHER_GIT_RESET_OK = "1"
  git fetch origin 2>&1 | Out-Null
  git reset --hard origin/main 2>&1 | Out-Null
  & $Py -m pip install -e ".[dev]" -q 2>&1 | Out-Null
} catch {
  Write-Log "pull/install soft fail: $_"
}

if (-not $alive -and (Test-Path $PidFile)) {
  try { Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue } catch {}
}

$env:ETHER_GIT_RESET_OK = "1"
$env:ETHER_PULL_SOFT = "1"
$env:ETHER_FLYWHEEL_PUSH = "1"
$env:ETHER_CURRICULUM = "1"
$env:ETHER_AUTO_ENQUEUE = "1"
$env:ETHER_GUARDIAN_AUTO_BASELINE = "1"
$env:ETHER_DAEMON_DASHBOARD = "1"
$env:ETHER_DAEMON_FLYWHEEL = "1"
$env:ETHER_DAEMON_BATCH = "1"
if (-not $env:ETHER_DAEMON_INTERVAL) { $env:ETHER_DAEMON_INTERVAL = "300" }
if (-not $env:ETHER_BATCH_INTERVAL) { $env:ETHER_BATCH_INTERVAL = "300" }
$env:PYTHONIOENCODING = "utf-8"
$env:ETHER_ROOT = $Root

Write-Log "starting ether_daemon.py"
try {
  Start-Process -FilePath $Py -ArgumentList "`"$Daemon`"" -WorkingDirectory $Root -WindowStyle Hidden
} catch {
  Write-Log "Start-Process failed: $_"
  exit 1
}

Start-Sleep -Seconds 10
if (Test-DaemonAlive -or Test-HeartbeatFresh 60) {
  Write-Log "STARTED ok — dashboard http://127.0.0.1:8787"
  exit 0
}
Write-Log "start did not produce heartbeat yet — Ensure will retry"
exit 0
