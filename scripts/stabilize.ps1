# @ETHER STABILIZE - one ordered path. Run from anywhere.
# Does NOT pull 7B models. Host profile only (GTX 1650 / 12GB RAM).
#
#   powershell -ExecutionPolicy Bypass -File C:\Users\Otcde\ETHER\scripts\stabilize.ps1

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
$env:PYTHONIOENCODING = "utf-8"

function Step([string]$n, [string]$m) { Write-Host ""; Write-Host "=== [$n] $m ===" -ForegroundColor Cyan }
function Ok([string]$m) { Write-Host "  OK  $m" -ForegroundColor Green }
function Warn([string]$m) { Write-Host "  WARN $m" -ForegroundColor Yellow }
function Bad([string]$m) { Write-Host "  FAIL $m" -ForegroundColor Red }

Write-Host "========================================"
Write-Host " @ETHER STABILIZE"
Write-Host " root=$Root"
Write-Host " profile=host (3B max)"
Write-Host "========================================"

# --- 1 git ---
Step "1/6" "git sync origin/main"
try {
  git fetch origin 2>&1 | Out-Host
  git reset --hard origin/main 2>&1 | Out-Host
  Ok "HEAD $(git rev-parse --short HEAD)"
} catch { Bad "git: $_"; }

# --- 2 venv ---
Step "2/6" "venv + editable install"
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Py)) {
  python -m venv .venv
  & $Py -m pip install -U pip
}
& $Py -m pip install -e ".[dev]" -q
if ($LASTEXITCODE -ne 0) { Bad "pip install failed" } else { Ok "pip editable" }

# --- 3 model ---
Step "3/6" "model select (host = 3B)"
try {
  $out = & $Py -c "from core.model_select import select_primary_model; import json; print(json.dumps(select_primary_model(force_refresh=True)))"
  Write-Host "  $out"
  Ok "model selected"
} catch { Warn "model_select: $_" }

# --- 4 offline self-test ---
Step "4/6" "offline autonomy self-test"
$st = Join-Path $Root "scripts\self_test_autonomy.py"
if (Test-Path $st) {
  & $Py $st
  if ($LASTEXITCODE -eq 0) { Ok "self-test passed" } else { Warn "self-test exit=$LASTEXITCODE (non-fatal)" }
} else { Warn "self_test_autonomy.py missing" }

# --- 5 daemon + ensure task ---
Step "5/6" "daemon keep-alive (Control Matrix :8787)"
$ens = Join-Path $Root "scripts\ensure_daemon.ps1"
$inst = Join-Path $Root "scripts\install_windows_daemon.ps1"
if (Test-Path $inst) {
  & powershell -NoProfile -ExecutionPolicy Bypass -File $inst
} elseif (Test-Path $ens) {
  & powershell -NoProfile -ExecutionPolicy Bypass -File $ens
} else {
  Bad "ensure scripts missing"
}
Start-Sleep -Seconds 3
# port check
$dash = $false
try {
  $c = New-Object System.Net.Sockets.TcpClient
  $iar = $c.BeginConnect("127.0.0.1", 8787, $null, $null)
  $dash = $iar.AsyncWaitHandle.WaitOne(800)
  if ($dash) { $c.EndConnect($iar) }
  $c.Close()
} catch { $dash = $false }
if ($dash) { Ok "Control Matrix http://127.0.0.1:8787" } else { Warn "port 8787 not open yet - check memory\daemon\ensure.log" }

# --- 6 runner (optional, non-fatal) ---
Step "6/6" "GitHub runner keep-alive (optional)"
$runInst = Join-Path $Root "scripts\install_runner_service.ps1"
if (Test-Path "C:\actions-runner\run.cmd") {
  & powershell -NoProfile -ExecutionPolicy Bypass -File $runInst
  if (Get-Process -Name "Runner.Listener" -ErrorAction SilentlyContinue) {
    Ok "Runner.Listener running"
  } else {
    Warn "Runner not up - autonomy still works locally without it"
  }
} else {
  Warn "C:\actions-runner not configured - skip runner (daemon still autonomous on this PC)"
}

Write-Host ""
Write-Host "========================================"
Write-Host " VERIFY"
Write-Host "========================================"
Write-Host "1. Browser: http://127.0.0.1:8787"
Write-Host "2. Infra:   http://127.0.0.1:8787/api/infra"
Write-Host "3. Tasks:   Get-ScheduledTask | ? TaskName -like 'ETHER*'"
Write-Host "4. Log:     Get-Content $Root\memory\daemon\ensure.log -Tail 20"
Write-Host ""
Write-Host "Local autonomy does NOT need the GitHub runner."
Write-Host "Runner is only for remote dispatch from GitHub Actions."
