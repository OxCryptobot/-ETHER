# ETHER host launcher -- SINGLE WINDOW, self-healing, never silent
#
#   powershell -ExecutionPolicy Bypass -File .\scripts\start_ether_host.ps1
#   powershell -ExecutionPolicy Bypass -File .\scripts\start_ether_host.ps1 -Recover
#   powershell -ExecutionPolicy Bypass -File .\scripts\start_ether_host.ps1 -Hard
#
# Exit codes from ether_host.py:
#   0  = clean stop (Ctrl+C) -> exit permanently
#   42 = source updated on origin -> restart in 1s (NO nuclear git — already current)
#   other = crash -> restart with backoff + nuclear clean
#
# -Recover / -Hard: kill stale, abort rebase/merge, hard-reset to origin/main,
# optional venv rebuild, then self-healing loop in THIS process.
#
# 2026-08-22g: exit-42 path skips nuclear clean (was causing reload death-spiral).

param(
    [switch]$Recover,
    [switch]$Hard
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function Write-Banner {
    param([string]$msg, [string]$color = "Cyan")
    Write-Host $msg -ForegroundColor $color
}
function Write-Ok  { param([string]$msg) Write-Host "  OK   $msg" -ForegroundColor Green }
function Write-Warn { param([string]$msg) Write-Host "  WARN $msg" -ForegroundColor Yellow }
function Write-Fail { param([string]$msg) Write-Host "  FAIL $msg" -ForegroundColor Red }

function Clear-GitState {
    try { git rebase --abort 2>$null | Out-Null } catch {}
    try { git merge --abort 2>$null | Out-Null } catch {}
    try { git reset --mixed HEAD 2>$null | Out-Null } catch {}
    $fetchOut = git fetch origin 2>&1
    if ($LASTEXITCODE -ne 0) { Write-Warn "git fetch rc=$LASTEXITCODE : $fetchOut" }
    $resetOut = git reset --hard origin/main 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "git reset failed: $resetOut"
        return $false
    }
    $head = (git rev-parse --short HEAD 2>$null)
    if (-not $head) { $head = "?" }
    Write-Ok "HEAD=$head (clean slate)"
    return $true
}

function Clear-Port8787 {
    Write-Banner "[port] free 8787" "Cyan"
    $killed = 0
    try {
        $lines = netstat -ano 2>$null
        foreach ($line in $lines) {
            if ($line -notmatch ":8787") { continue }
            if ($line -notmatch "LISTENING") { continue }
            $parts = ($line -split "\s+") | Where-Object { $_ -ne "" }
            if ($parts.Count -lt 1) { continue }
            $pid = $parts[-1]
            if ($pid -match "^\d+$" -and [int]$pid -gt 0) {
                try {
                    Stop-Process -Id ([int]$pid) -Force -ErrorAction Stop
                    $killed++
                    Write-Warn "killed pid=$pid on :8787"
                } catch {
                    try {
                        taskkill /F /PID $pid 2>$null | Out-Null
                        $killed++
                        Write-Warn "taskkill pid=$pid on :8787"
                    } catch {}
                }
            }
        }
    } catch { Write-Warn "Clear-Port8787 non-fatal: $_" }
    if ($killed -eq 0) { Write-Ok "8787 free" } else { Write-Ok "freed 8787 ($killed)" }
    Start-Sleep -Milliseconds 400
}

# --- resolve repo root ---
$Root = $null
try {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $Root = Split-Path -Parent $ScriptDir
} catch {
    $Root = (Get-Location).Path
}
if (-not (Test-Path (Join-Path $Root "core"))) {
    $Root = "C:\Users\Otcde\ETHER"
}
if (-not (Test-Path (Join-Path $Root "core"))) {
    Write-Fail "Cannot find ETHER root (no core/). cd to C:\Users\Otcde\ETHER first."
    exit 1
}
Set-Location -LiteralPath $Root
$env:ETHER_ROOT = $Root
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = $Root

if (-not $env:ETHER_PRIMARY_MODEL) { $env:ETHER_PRIMARY_MODEL = "qwen3.5:4b-q4_K_M" }
if (-not $env:ETHER_HW_PROFILE)    { $env:ETHER_HW_PROFILE    = "host" }

Write-Banner "========================================" "Green"
Write-Banner " ETHER HOST LAUNCHER" "Green"
Write-Banner " root=$Root" "DarkGray"
Write-Banner " model=$($env:ETHER_PRIMARY_MODEL)" "DarkGray"
if ($Hard)    { Write-Banner " mode=HARD (venv rebuild)" "Yellow" }
if ($Recover) { Write-Banner " mode=RECOVER" "Yellow" }
Write-Banner "========================================" "Green"
Write-Host ""

try { Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force -ErrorAction SilentlyContinue } catch {}

# --- 1. Kill stale host python ---
Write-Banner "[1] kill stale host python" "Cyan"
$patterns = @("ether_host.py", "host_agent.py", "scripts\ether_host", "scripts/ether_host", "scripts\host_agent", "scripts/host_agent", "uvicorn.*dashboard", "dashboard.app")
$killed = 0
try {
    $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue
    if ($procs) {
        foreach ($p in $procs) {
            if ($p.Name -match "python" -and $p.CommandLine) {
                $cmd = $p.CommandLine
                $hit = $false
                foreach ($pat in $patterns) {
                    if ($cmd -like "*$pat*") { $hit = $true; break }
                }
                if ($hit) {
                    try {
                        Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
                        $killed++
                        Write-Warn "killed pid=$($p.ProcessId)"
                    } catch {}
                }
            }
        }
    }
} catch { Write-Warn "Get-CimInstance non-fatal: $_" }

if ($Hard) {
    try {
        Get-Process -Name python -ErrorAction SilentlyContinue | ForEach-Object {
            try { Stop-Process -Id $_.Id -Force -ErrorAction Stop; $killed++; Write-Warn "HARD killed python pid=$($_.Id)" } catch {}
        }
    } catch {}
}
if ($killed -eq 0) { Write-Ok "no stale host python" } else { Write-Ok "killed $killed process(es)" }
Start-Sleep -Seconds 1

Clear-Port8787

# --- 2. Nuclear git clean slate (once at start) ---
Write-Banner "[2] git clean slate (abort rebase/merge + hard reset)" "Cyan"
if (-not (Clear-GitState)) { exit 1 }

# --- 3. Venv ---
Write-Banner "[3] venv" "Cyan"
$Py = Join-Path $Root ".venv\Scripts\python.exe"
$needVenv = $Hard -or -not (Test-Path -LiteralPath $Py)

if ($needVenv) {
    $sysPy = $null
    try { $sysPy = (Get-Command python -ErrorAction Stop).Source } catch {
        Write-Fail "python not on PATH -- install Python 3.11+ then re-run with -Hard"
        exit 3
    }
    Write-Ok "system python: $sysPy"
    if (Test-Path (Join-Path $Root ".venv")) {
        Write-Warn "removing existing .venv"
        try { Remove-Item -Recurse -Force (Join-Path $Root ".venv") -ErrorAction Stop } catch { Write-Warn "partial remove: $_" }
    }
    Write-Banner "  creating .venv + pip install -e .[dev] ..." "DarkGray"
    & python -m venv .venv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $Py)) {
        Write-Fail "venv create failed"
        exit 2
    }
    & $Py -m pip install -U pip -q 2>$null
    & $Py -m pip install -e ".[dev]" -q
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "pip install -e .[dev] failed (exit $LASTEXITCODE)"
        exit 2
    }
    Write-Ok "venv rebuilt"
} else {
    $probe = & $Py -c "import sys; print(sys.executable)" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "python probe failed: $probe -- re-run with -Hard"
        exit 2
    }
    Write-Ok "venv ok ($probe)"
}

if (-not (Test-Path -LiteralPath $Py)) {
    Write-Fail "No python at $Py"
    exit 2
}

# --- 4. Forced import probe ---
Write-Banner "[4] boot probe (import host_agent + foreman + dashboard)" "Cyan"
$probeCode = @"
import sys
sys.path.insert(0, r'$Root')
print('python', sys.executable)
print('cwd', __import__('os').getcwd())
try:
    import scripts.host_agent as agent
    print('host_agent OK')
except Exception as e:
    print('host_agent FAIL:', type(e).__name__, e)
    sys.exit(11)
try:
    from scripts import foreman
    print('foreman OK')
except Exception as e:
    print('foreman FAIL:', type(e).__name__, e)
    sys.exit(12)
try:
    from dashboard.app import app as dash_app
    print('dashboard.app OK', getattr(dash_app, 'title', ''))
except Exception as e:
    print('dashboard.app FAIL:', type(e).__name__, e)
    sys.exit(13)
from pathlib import Path
p = Path(r'$Root') / 'dashboard' / 'static' / 'agent.html'
if not p.is_file():
    print('agent.html MISSING', p)
    sys.exit(14)
print('agent.html OK', p.stat().st_size, 'bytes')
print('BOOT_PROBE_OK')
"@
$probeOut = & $Py -c $probeCode 2>&1
Write-Host $probeOut
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Boot probe failed (exit $LASTEXITCODE). Fix the import error above, then re-run with -Hard."
    exit 5
}
Write-Ok "boot probe passed"

# --- 5. Self-healing loop ---
Write-Host ""
Write-Banner "========================================" "Green"
Write-Banner " ENTERING SELF-HEALING LOOP" "Green"
Write-Banner " dashboard  http://127.0.0.1:8787/" "DarkGray"
Write-Banner " Ctrl+C     stop permanently" "DarkGray"
Write-Banner "========================================" "Green"
Write-Host ""

$backoff = 3
$maxBackoff = 30
$needNuclear = $true  # first start always nuclear (already done above; loop tracks)

while ($true) {
    if ($needNuclear) {
        Write-Banner "[sync] clean slate + free port + start" "Cyan"
        [void](Clear-GitState)
    } else {
        Write-Banner "[sync] light reload (skip nuclear) + free port + start" "Cyan"
    }
    Clear-Port8787

    Write-Banner "[start] scripts\ether_host.py" "Cyan"
    & $Py "scripts\ether_host.py"
    $code = $LASTEXITCODE
    if ($null -eq $code) { $code = 1 }

    if ($code -eq 0) {
        Write-Banner "[stop] clean exit (Ctrl+C)" "Green"
        break
    }
    if ($code -eq 42) {
        Write-Banner "[reload] source updated (exit 42) -- restart in 1s (no nuclear)" "Cyan"
        $backoff = 3
        $needNuclear = $false
        Start-Sleep -Seconds 1
        continue
    }

    Write-Banner "[crash] exit=$code -- nuclear + restart in ${backoff}s" "Yellow"
    $needNuclear = $true
    Start-Sleep -Seconds $backoff
    $backoff = [Math]::Min($backoff * 2, $maxBackoff)
}
