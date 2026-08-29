# Ensures @ETHER daemon + Control Matrix port are alive on ETHER_ROOT.

$ErrorActionPreference = "Continue"

function Resolve-EtherRoot {
  if ($env:ETHER_ROOT -and (Test-Path -LiteralPath $env:ETHER_ROOT)) {
    return (Resolve-Path -LiteralPath $env:ETHER_ROOT).Path
  }
  foreach ($c in @("C:\Users\Otcde\ETHER", "C:\ETHER", (Join-Path $PSScriptRoot ".."))) {
    if (Test-Path -LiteralPath $c) {
      $p = (Resolve-Path -LiteralPath $c).Path
      if (Test-Path -LiteralPath (Join-Path $p "scripts\ether_daemon.py")) { return $p }
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
$DashPort = 8787
if ($env:ETHER_DASH_PORT) { $DashPort = [int]$env:ETHER_DASH_PORT }

function Write-Log([string]$msg) {
  $line = "[{0}] {1}" -f (Get-Date).ToUniversalTime().ToString("o"), $msg
  try {
    $dir = Split-Path $Log -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    Add-Content -LiteralPath $Log -Value $line -Encoding UTF8
  } catch {}
  Write-Host $line
}

function Test-PortOpen([int]$Port) {
  try {
    $c = New-Object System.Net.Sockets.TcpClient
    $iar = $c.BeginConnect("127.0.0.1", $Port, $null, $null)
    $ok = $iar.AsyncWaitHandle.WaitOne(400)
    if (-not $ok) { $c.Close(); return $false }
    $c.EndConnect($iar)
    $c.Close()
    return $true
  } catch { return $false }
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

function Start-EtherDaemon {
  Write-Log "starting ether_daemon.py"
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
  $env:ETHER_AUTO_MODEL = "1"
  $env:ETHER_HW_PROFILE = "host"
  $env:ETHER_DAEMON_DASHBOARD = "1"
  $env:ETHER_DAEMON_FLYWHEEL = "1"
  $env:ETHER_DAEMON_BATCH = "1"
  if (-not $env:ETHER_DAEMON_INTERVAL) { $env:ETHER_DAEMON_INTERVAL = "300" }
  if (-not $env:ETHER_BATCH_INTERVAL) { $env:ETHER_BATCH_INTERVAL = "300" }
  if (-not $env:ETHER_PRIMARY_MODEL) { $env:ETHER_PRIMARY_MODEL = "qwen2.5-coder:3b" }
  $env:PYTHONIOENCODING = "utf-8"
  $env:ETHER_ROOT = $Root
  try {
    & $Py -c "from core.model_select import ensure_model_env; print(ensure_model_env())" 2>$null | ForEach-Object {
      if ($_) { $env:ETHER_PRIMARY_MODEL = "$_".Trim(); Write-Log "model=$env:ETHER_PRIMARY_MODEL" }
    }
  } catch {}
  $PyW = Join-Path $Root ".venv\Scripts\pythonw.exe"
  $exe = if (Test-Path -LiteralPath $PyW) { $PyW } else { $Py }
  Start-Process -FilePath $exe -ArgumentList "`"$Daemon`"" -WorkingDirectory $Root -WindowStyle Hidden
}

Write-Log "ETHER_ROOT=$Root"

$wake = Join-Path $Root "artifacts\host\matrix_wake.json"
if (Test-Path -LiteralPath $wake) {
  try {
    $raw = Get-Content -LiteralPath $wake -Raw
    if ($raw -match '"action"\s*:\s*"boot"' -and $raw -notmatch '"status"\s*:\s*"consumed"') {
      Write-Log "matrix wake present — hidden boot requested by Control Matrix"
    }
  } catch {}
}

if (-not (Test-Path -LiteralPath $Py)) {
  Write-Log "MISSING venv - creating"
  python -m venv .venv
  & $Py -m pip install -U pip -q
  & $Py -m pip install -e ".[dev]" -q
}

if (-not (Test-Path -LiteralPath $Daemon)) {
  git fetch origin 2>&1 | Out-Null
  git reset --hard origin/main 2>&1 | Out-Null
}

$alive = Test-DaemonAlive
$fresh = Test-HeartbeatFresh 180
$dash = Test-PortOpen $DashPort
Write-Log "state alive=$alive fresh=$fresh dash=$dash port=$DashPort"

if ($alive -and $fresh -and $dash) {
  Write-Log "OK daemon + dashboard"
  exit 0
}

try {
  git fetch origin 2>&1 | Out-Null
  git reset --hard origin/main 2>&1 | Out-Null
  & $Py -m pip install -e ".[dev]" -q 2>&1 | Out-Null
} catch {}

if ($alive -and -not $dash) {
  Write-Log "dashboard down - restarting daemon"
  try {
    $pidVal = [int]((Get-Content -LiteralPath $PidFile -Raw).Trim())
    Stop-Process -Id $pidVal -Force -ErrorAction SilentlyContinue
  } catch {}
  Start-Sleep -Seconds 2
  $alive = $false
}

if (-not $alive) {
  if (Test-Path $PidFile) { Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue }
  Start-EtherDaemon
  Start-Sleep -Seconds 12
}

$alive2 = Test-DaemonAlive
$dash2 = Test-PortOpen $DashPort
Write-Log "after ensure alive=$alive2 dash=$dash2"
if ($alive2 -or $dash2) { exit 0 }
Write-Log "WARN still down - scheduler will retry"
exit 0
