# @ETHER STABILIZE - ignition + keep-alive + PROVE learning cycle
# Host profile only (GTX 1650 4GB / 12GB RAM -> qwen2.5-coder:3b)
#
#   powershell -ExecutionPolicy Bypass -File C:\Users\Otcde\ETHER\scripts\stabilize.ps1
#
# What this does:
#   1-4  sync, venv, model, offline tests
#   5    daemon + ETHER-Ensure (self-heal process/dashboard)
#   6    one smart cycle (curriculum -> sandbox -> learn/enqueue)
#   7    optional GitHub runner keep-alive
# After this, ether_daemon keeps cycling every ETHER_DAEMON_INTERVAL (default 300s).

$ErrorActionPreference = "Continue"
$Root = "C:\Users\Otcde\ETHER"
if (-not (Test-Path -LiteralPath $Root)) {
  $Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
Set-Location -LiteralPath $Root
$env:ETHER_ROOT = $Root
$env:ETHER_HW_PROFILE = "host"
$env:ETHER_AUTO_MODEL = "1"
$env:ETHER_PRIMARY_MODEL = "qwen2.5-coder:3b"
$env:ETHER_CURRICULUM = "1"
$env:ETHER_EXPERIENCE = "1"
$env:ETHER_AUTO_ENQUEUE = "1"
$env:ETHER_GUARDIAN_AUTO_BASELINE = "1"
$env:ETHER_FLYWHEEL_PUSH = "1"
$env:ETHER_GIT_RESET_OK = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = $Root

function Step([string]$n, [string]$m) { Write-Host ""; Write-Host "=== [$n] $m ===" -ForegroundColor Cyan }
function Ok([string]$m) { Write-Host "  OK  $m" -ForegroundColor Green }
function Warn([string]$m) { Write-Host "  WARN $m" -ForegroundColor Yellow }
function Bad([string]$m) { Write-Host "  FAIL $m" -ForegroundColor Red }

Write-Host "========================================"
Write-Host " @ETHER STABILIZE + LEARN PROOF"
Write-Host " root=$Root  profile=host  model=3B"
Write-Host "========================================"

# --- 1 git ---
Step "1/7" "git sync origin/main"
try {
  git fetch origin 2>&1 | Out-Host
  git reset --hard origin/main 2>&1 | Out-Host
  Ok "HEAD $(git rev-parse --short HEAD)"
} catch { Bad "git: $_" }

# --- 2 venv ---
Step "2/7" "venv + editable install"
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Py)) {
  python -m venv .venv
  & $Py -m pip install -U pip
}
& $Py -m pip install -e ".[dev]" -q
if ($LASTEXITCODE -ne 0) { Bad "pip install failed"; exit 1 } else { Ok "pip editable" }

# --- 3 model ---
Step "3/7" "host model select (cap 3B)"
try {
  $out = & $Py -c "from core.model_select import select_primary_model; import json; print(json.dumps(select_primary_model(force_refresh=True)))"
  Write-Host "  $out"
  Ok "model selected"
} catch { Warn "model_select: $_" }

# --- 4 offline self-test ---
Step "4/7" "offline autonomy substrate"
$st = Join-Path $Root "scripts\self_test_autonomy.py"
if (Test-Path $st) {
  & $Py $st
  if ($LASTEXITCODE -eq 0) { Ok "self-test passed" } else { Warn "self-test exit=$LASTEXITCODE" }
} else { Warn "self_test missing" }

# --- 5 daemon keep-alive ---
Step "5/7" "daemon + ETHER-Ensure (self-heal)"
$inst = Join-Path $Root "scripts\install_windows_daemon.ps1"
$ens = Join-Path $Root "scripts\ensure_daemon.ps1"
if (Test-Path $inst) {
  & powershell -NoProfile -ExecutionPolicy Bypass -File $inst
} elseif (Test-Path $ens) {
  & powershell -NoProfile -ExecutionPolicy Bypass -File $ens
} else { Bad "ensure scripts missing"; exit 1 }
Start-Sleep -Seconds 5
$dash = $false
try {
  $c = New-Object System.Net.Sockets.TcpClient
  $iar = $c.BeginConnect("127.0.0.1", 8787, $null, $null)
  $dash = $iar.AsyncWaitHandle.WaitOne(1000)
  if ($dash) { $c.EndConnect($iar) }
  $c.Close()
} catch { $dash = $false }
if ($dash) { Ok "Control Matrix http://127.0.0.1:8787" } else { Warn "port 8787 not open - check memory\daemon\ensure.log" }

# --- 6 PROVE learning (one full smart cycle) ---
Step "6/7" "one smart cycle (curriculum + verify + learn)"
$cycle = Join-Path $Root "scripts\run_smart_cycle.py"
if (Test-Path $cycle) {
  Write-Host "  (may take several minutes on 3B - wait)"
  & $Py $cycle
  $code = $LASTEXITCODE
  $latest = Join-Path $Root "memory\flywheel\latest.json"
  if (Test-Path $latest) {
    Write-Host "  --- latest flywheel ---"
    Get-Content $latest -TotalCount 40
    Ok "cycle finished exit=$code (0=gate pass, 1=gate fail still trains)"
  } else {
    Warn "no memory\flywheel\latest.json - cycle may have crashed"
  }
  # seed recovery metrics if never benched
  $bench = Join-Path $Root "memory\bench\latest.json"
  if (-not (Test-Path $bench)) {
    Write-Host "  no bench yet - running fast bench for health baseline"
    & $Py (Join-Path $Root "scripts\bench.py") --fast
  }
} else {
  Bad "run_smart_cycle.py missing"
}

# --- 7 runner optional ---
Step "7/7" "GitHub runner (optional remote only)"
$runInst = Join-Path $Root "scripts\install_runner_service.ps1"
if (Test-Path "C:\actions-runner\run.cmd") {
  & powershell -NoProfile -ExecutionPolicy Bypass -File $runInst
  if (Get-Process -Name "Runner.Listener" -ErrorAction SilentlyContinue) {
    Ok "Runner.Listener running"
  } else {
    Warn "Runner not up - LOCAL autonomy still active without it"
  }
} else {
  Warn "no C:\actions-runner - skip (not required for grow/learn on this PC)"
}

Write-Host ""
Write-Host "========================================"
Write-Host " RESULT"
Write-Host "========================================"
Write-Host "Self-heal : ETHER-Daemon + ETHER-Ensure (restart if dead / :8787 down)"
Write-Host "Grow/learn: daemon flywheel every ~5 min + batch drain + recovery_cycle"
Write-Host "Proof     : memory\flywheel\latest.json + http://127.0.0.1:8787"
Write-Host "Tasks     : Get-ScheduledTask | ? TaskName -like 'ETHER*'"
Write-Host ""
