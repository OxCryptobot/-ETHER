# ETHER host recovery -- one shot (hardened + error handling)
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
# Exit codes:
#   0  = handed off to launcher successfully
#   1  = root not found / git reset failed / launcher missing
#   2  = venv create or pip install failed
#   3  = python not on PATH
#   4  = launcher itself failed to start

param(
    [switch]$Hard
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
$script:ExitCode = 0

# --- helpers ---
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
function Fail-Exit {
    param([string]$msg, [int]$code = 1)
    Write-Fail $msg
    Write-Host ""
    Write-Banner "RECOVERY ABORTED (exit $code)" "Red"
    Write-Host "  Fix the error above, then re-run:" -ForegroundColor DarkGray
    Write-Host "  .\scripts\recover_host.ps1 -Hard" -ForegroundColor DarkGray
    exit $code
}

# Global trap for unexpected terminating errors
trap {
    Write-Fail "Unhandled error: $_"
    Write-Banner "RECOVERY ABORTED (trap)" "Red"
    exit 1
}

# --- resolve root ---
$ScriptDir = $null
try {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
} catch {
    $ScriptDir = $PSScriptRoot
}
if (-not $ScriptDir) {
    $ScriptDir = (Get-Location).Path
}
$Root = Split-Path -Parent $ScriptDir

if (-not (Test-Path (Join-Path $Root "core"))) {
    $Root = "C:\Users\Otcde\ETHER"
}
if (-not (Test-Path (Join-Path $Root "core"))) {
    Fail-Exit "ETHER root not found. Expected core/ under $Root" 1
}

try {
    Set-Location -LiteralPath $Root -ErrorAction Stop
} catch {
    Fail-Exit "Cannot Set-Location to $Root : $_" 1
}

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
try {
    $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue
    if ($procs) {
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
                    } catch {
                        Write-Warn "could not kill pid=$($p.ProcessId): $_"
                    }
                }
            }
        }
    }
} catch {
    Write-Warn "Get-CimInstance failed (non-fatal): $_"
}

if ($Hard) {
    try {
        $allPy = Get-Process -Name python -ErrorAction SilentlyContinue
        foreach ($p in $allPy) {
            try {
                Stop-Process -Id $p.Id -Force -ErrorAction Stop
                $killed++
                Write-Warn "HARD killed python pid=$($p.Id)"
            } catch {
                Write-Warn "HARD could not kill pid=$($p.Id): $_"
            }
        }
    } catch {
        Write-Warn "Get-Process python failed (non-fatal): $_"
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

$fetchOk = $true
try {
    $fetchOut = git fetch origin 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "git fetch returned $LASTEXITCODE : $fetchOut"
        $fetchOk = $false
    }
} catch {
    Write-Warn "git fetch exception: $_"
    $fetchOk = $false
}

$resetOut = $null
try {
    $resetOut = git reset --hard origin/main 2>&1
    if ($LASTEXITCODE -ne 0) {
        Fail-Exit "git reset failed: $resetOut" 1
    }
} catch {
    Fail-Exit "git reset exception: $_" 1
}

try {
    $head = (git rev-parse --short HEAD 2>$null)
    if (-not $head) { $head = "?" }
    Write-Ok "HEAD=$head  origin/main"
} catch {
    Write-Ok "git reset done (could not read HEAD)"
}

# --- 3. Quarantine live spam from pending ---
Write-Banner "[3/5] quarantine live/ledger pending (FAST-first)" "Cyan"
$pendingDir = Join-Path $Root "artifacts\jobs\pending"
$failedDir  = Join-Path $Root "artifacts\jobs\failed"

try {
    New-Item -ItemType Directory -Force -Path $failedDir -ErrorAction Stop | Out-Null
} catch {
    Write-Warn "could not create failed/ dir: $_"
}

$quarantined = 0
if (Test-Path -LiteralPath $pendingDir) {
    try {
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
                } catch {
                    # unreadable job file -- leave it
                }
            }

            if ($isLiveSpam) {
                $dest = Join-Path $failedDir $name
                try {
                    Move-Item -LiteralPath $f.FullName -Destination $dest -Force -ErrorAction Stop
                    $quarantined++
                    Write-Warn "quarantined $name ($reason) -> failed/"
                } catch {
                    Write-Fail "could not move $name : $_"
                }
            }
        }
    } catch {
        Write-Warn "quarantine scan failed (non-fatal): $_"
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
    # Check system python exists before destroying .venv
    $sysPy = $null
    try {
        $sysPy = (Get-Command python -ErrorAction Stop).Source
    } catch {
        Fail-Exit "python not found on PATH -- install Python 3.11+ and re-run" 3
    }
    Write-Ok "system python: $sysPy"

    if (Test-Path (Join-Path $Root ".venv")) {
        Write-Warn "removing existing .venv"
        try {
            Remove-Item -Recurse -Force (Join-Path $Root ".venv") -ErrorAction Stop
        } catch {
            Write-Warn "partial .venv remove: $_ (continuing)"
        }
    }

    Write-Banner "  creating .venv + editable install..." "DarkGray"
    try {
        & python -m venv .venv
        if ($LASTEXITCODE -ne 0) {
            Fail-Exit "python -m venv failed (exit $LASTEXITCODE)" 2
        }
    } catch {
        Fail-Exit "python -m venv exception: $_" 2
    }

    if (-not (Test-Path -LiteralPath $Py)) {
        Fail-Exit "venv create left no $Py" 2
    }

    try {
        & $Py -m pip install -U pip -q
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "pip self-upgrade returned $LASTEXITCODE (continuing)"
        }
    } catch {
        Write-Warn "pip self-upgrade exception: $_ (continuing)"
    }

    try {
        & $Py -m pip install -e ".[dev]" -q
        if ($LASTEXITCODE -ne 0) {
            Fail-Exit "pip install -e .[dev] failed (exit $LASTEXITCODE)" 2
        }
    } catch {
        Fail-Exit "pip install -e .[dev] exception: $_" 2
    }
    Write-Ok "venv rebuilt + editable install"
} else {
    try {
        $probe = & $Py -c "import sys; print(sys.executable)" 2>&1
        if ($LASTEXITCODE -ne 0) {
            Fail-Exit "python probe failed: $probe -- re-run with -Hard" 2
        }
        Write-Ok "venv ok ($probe)"
    } catch {
        Fail-Exit "python probe exception: $_ -- re-run with -Hard" 2
    }
}

# Final sanity: python must exist
if (-not (Test-Path -LiteralPath $Py)) {
    Fail-Exit "No usable python at $Py after venv step" 2
}

# --- 5. Hand off to self-healing launcher ---
Write-Banner "[5/5] start self-healing host loop" "Cyan"
$Launcher = Join-Path $Root "scripts\start_ether_host.ps1"
if (-not (Test-Path -LiteralPath $Launcher)) {
    Fail-Exit "Missing $Launcher -- origin/main incomplete?" 1
}

Write-Host ""
Write-Banner "========================================" "Green"
Write-Banner " RECOVERY COMPLETE -- entering launcher" "Green"
Write-Banner " dashboard  http://127.0.0.1:8787/agent" "DarkGray"
Write-Banner " model      $($env:ETHER_PRIMARY_MODEL)" "DarkGray"
Write-Banner " Ctrl+C     stop permanently" "DarkGray"
Write-Banner "========================================" "Green"
Write-Host ""

# Hand off -- capture launcher failure
try {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $Launcher -Recover
    $launcherCode = $LASTEXITCODE
    if ($null -eq $launcherCode) { $launcherCode = 0 }
    if ($launcherCode -ne 0) {
        Write-Fail "launcher exited with code $launcherCode"
        exit 4
    }
    exit 0
} catch {
    Fail-Exit "launcher failed to start: $_" 4
}
