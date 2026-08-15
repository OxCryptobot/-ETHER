# ETHER host recovery -- one shot (hardened)
#
# Use when Grok reports stale heartbeat + pending jobs not consumed,
# or after live-spam / MERGE_HEAD / broken venv.
# This is the ONLY manual recovery step. After it succeeds, leave the
# window open; start_ether_host.ps1 keeps the process alive forever.
#
#   cd C:\Users\Otcde\ETHER
#   powershell -ExecutionPolicy Bypass -File .\scripts\recover_host.ps1
#   powershell -ExecutionPolicy Bypass -File .\scripts\recover_host.ps1 -Hard
#
# -Hard: also recreate .venv + pip install -e ".[dev]" (ModuleNotFound / corrupt env)
#
# What this does (in order):
#   1. Resolve root, process-scoped Bypass
#   2. Kill stale ether_host / host_agent python (and broader under -Hard)
#   3. git merge --abort + fetch + reset --hard origin/main
#   4. Quarantine stuck live/ledger pending jobs (FAST-first hygiene)
#   5. Optional -Hard: recreate venv
#   6. Hand off to start_ether_host.ps1 self-healing loop

param(
    [switch]$Hard
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

# --- resolve root ---
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir

if (-not (Test-Path (Join-Path $Root "core"))) {
    $Root = "C:\Users\Otcde\ETHER"
}
if (-not (Test-Path (Join-Path $Root "core"))) {
    Write-Error "ETHER root not found. Expected core/ under $Root"
    exit 1
}

Set-Location -LiteralPath $Root
$env:ETHER_ROOT = $Root
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = $Root

# Host model lock (GTX 1650 4GB) -- explicit Q4_K_M
if (-not $env:ETHER_PRIMARY_MODEL) {
    $env:ETHER_PRIMARY_MODEL = "qwen3.5:4b-q4_K_M"
}
if (-not $env:ETHER_HW_PROFILE) {
    $env:ETHER_HW_PROFILE = "host"
}

function Write-Banner {
    param([string]$msg, [string]$color = "Cyan")
    Write-Host $msg -ForegroundColor $color
}

function Write-Ok {
    param([string]$msg)
    Write-Host "  OK   $msg" -ForegroundColor Green
}

function Write-Warn {
    param([string]$msg)
    Write-Host "  WARN $msg" -ForegroundColor Yellow
}

function Write-Fail {
    param([string]$msg)
    Write-Host "  FAIL $msg" -ForegroundColor Red
}

Write-Banner "========================================" "Green"
Write-Banner " ETHER HOST RECOVERY" "Green"
Write-Banner " root=$Root" "DarkGray"
if ($Hard) {
    Write-Banner " mode=HARD (venv rebuild)" "Yellow"
}
Write-Banner "========================================" "Green"
Write-Host ""

# Process-scoped execution policy (no admin)
try {
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force -ErrorAction SilentlyContinue
} catch {}

# --- 1. Stop stale host processes ---
Write-Banner "[1/5] kill stale host python" "Cyan"
$patterns = @(
    "ether_host.py",
    "host_agent.py",
    "scripts\ether_host",
    "scripts/ether_host",
    "scripts\host_agent",
    "scripts/host_agent",
    "cli.main dashboard",
    "uvicorn.*dashboard"
)
$killed = 0
$procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue
foreach ($p in $procs) {
    if ($p.Name -match "python" -and $p.CommandLine) {
        $cmd = $p.CommandLine
        $hit = $false
        foreach ($pat in $patterns) {
            if ($cmd -like "*$pat*") {
                $hit = $true
                break
            }
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

if ($Hard) {
    # Broader kill under -Hard only
    $allPy = Get-Process -Name python -ErrorAction SilentlyContinue
    foreach ($p in $allPy) {
        try {
            Stop-Process -Id $p.Id -Force -ErrorAction Stop
            $killed++
            Write-Warn "HARD killed python pid=$($p.Id)"
        } catch {}
    }
}

if ($killed -eq 0) {
    Write-Ok "no stale host python found"
} else {
    Write-Ok "killed $killed process(es)"
}
Start-Sleep -Seconds 1

# --- 2. Git clean ---
Write-Banner "[2/5] git clean (merge-abort + hard reset)" "Cyan"
try {
    git merge --abort 2>$null | Out-Null
} catch {}
git fetch origin 2>&1 | Out-Null
$resetOut = git reset --hard origin/main 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Fail "git reset failed: $resetOut"
    exit 1
}
$head = (git rev-parse --short HEAD 2>$null)
Write-Ok "HEAD=$head  origin/main"

# --- 3. Quarantine live spam from pending ---
Write-Banner "[3/5] quarantine live/ledger pending (FAST-first)" "Cyan"
$pendingDir = Join-Path $Root "artifacts\jobs\pending"
$failedDir  = Join-Path $Root "artifacts\jobs\failed"
New-Item -ItemType Directory -Force -Path $failedDir | Out-Null

$quarantined = 0
if (Test-Path -LiteralPath $pendingDir) {
    $files = Get-ChildItem -LiteralPath $pendingDir -Filter "*.json" -ErrorAction SilentlyContinue
    foreach ($f in $files) {
        $name = $f.Name
        $idLower = $name.ToLowerInvariant()
        $isLiveSpam = $false
        $reason = ""

        if ($idLower -match "live" -or $idLower -match "ledger" -or $idLower -match "_live_") {
            $isLiveSpam = $true
            $reason = "name_match"
        }

        if (-not $isLiveSpam) {
            try {
                $raw = Get-Content -LiteralPath $f.FullName -Raw -ErrorAction Stop
                $hasLongTimeout = $raw -match '"timeout"\s*:\s*(3\d{2}|[4-9]\d{2}|\d{4,})'
                $hasLiveSignal = ($raw -match "live") -or ($raw -match "ledger") -or ($raw -match '"class"\s*:\s*"live"')
                if ($hasLongTimeout -and $hasLiveSignal) {
                    $isLiveSpam = $true
                    $reason = "content_timeout_live"
                }
            } catch {}
        }

        if ($isLiveSpam) {
            $dest = Join-Path $failedDir $name
            try {
                Move-Item -LiteralPath $f.FullName -Destination $dest -Force
                $quarantined++
                Write-Warn "quarantined $name ($reason) -> failed/"
            } catch {
                Write-Fail "could not move $name : $_"
            }
        }
    }
}

if ($quarantined -eq 0) {
    Write-Ok "no live/ledger pending to quarantine"
} else {
    Write-Ok "quarantined $quarantined job(s) to artifacts/jobs/failed/"
}

# --- 4. Venv health / optional rebuild ---
Write-Banner "[4/5] venv" "Cyan"
$Py = Join-Path $Root ".venv\Scripts\python.exe"
$needVenv = $Hard -or -not (Test-Path -LiteralPath $Py)

if ($needVenv) {
    if (Test-Path (Join-Path $Root ".venv")) {
        Write-Warn "removing existing .venv"
        Remove-Item -Recurse -Force (Join-Path $Root ".venv") -ErrorAction SilentlyContinue
    }
    Write-Banner "  creating .venv + editable install..." "DarkGray"
    python -m venv .venv
    if (-not (Test-Path -LiteralPath $Py)) {
        Write-Fail "venv create failed -- python not found on PATH?"
        exit 1
    }
    & $Py -m pip install -U pip -q
    & $Py -m pip install -e ".[dev]" -q
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "pip install -e .[dev] failed"
        exit 1
    }
    Write-Ok "venv rebuilt + editable install"
} else {
    $probe = & $Py -c "import sys; print(sys.executable)" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "python probe failed: $probe -- re-run with -Hard"
        exit 1
    }
    Write-Ok "venv ok ($probe)"
}

# --- 5. Hand off to self-healing launcher ---
Write-Banner "[5/5] start self-healing host loop" "Cyan"
$Launcher = Join-Path $Root "scripts\start_ether_host.ps1"
if (-not (Test-Path -LiteralPath $Launcher)) {
    Write-Fail "Missing $Launcher -- origin/main incomplete?"
    exit 1
}

Write-Host ""
Write-Banner "========================================" "Green"
Write-Banner " RECOVERY COMPLETE -- entering launcher" "Green"
Write-Banner " dashboard  http://127.0.0.1:8787/agent" "DarkGray"
Write-Banner " model      $($env:ETHER_PRIMARY_MODEL)" "DarkGray"
Write-Banner " Ctrl+C     stop permanently" "DarkGray"
Write-Banner "========================================" "Green"
Write-Host ""

# Recovery steps already performed; -Recover is still passed so the
# launcher re-syncs and enters its self-healing loop cleanly.
& powershell -NoProfile -ExecutionPolicy Bypass -File $Launcher -Recover
exit $LASTEXITCODE
