# ETHER host launcher — single window, self-healing
#
#   powershell -ExecutionPolicy Bypass -File .\scripts\start_ether_host.ps1
#   powershell -ExecutionPolicy Bypass -File .\scripts\start_ether_host.ps1 -Recover
#
# Exit codes from ether_host.py / host_agent:
#   0  = clean stop (Ctrl+C) → exit permanently
#   42 = source updated on origin → restart in 1s
#   other = crash → restart with backoff (never stays dead)
#
# -Recover: kill stale host python processes, hard-reset to origin/main, then start.

param(
    [switch]$Recover
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

# --- resolve repo root ---
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not (Test-Path (Join-Path $Root "core"))) {
    $Root = (Get-Location).Path
}
if (-not (Test-Path (Join-Path $Root "core"))) {
    Write-Error "Cannot find ETHER root (no core/). cd to repo or run from scripts/."
    exit 1
}
Set-Location -LiteralPath $Root
$env:ETHER_ROOT = $Root
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = $Root

# Host model lock (GTX 1650 4GB) — do not override if already set in .env via process
if (-not $env:ETHER_PRIMARY_MODEL) {
    $env:ETHER_PRIMARY_MODEL = "qwen3.5:4b-q4_K_M"
}
if (-not $env:ETHER_HW_PROFILE) {
    $env:ETHER_HW_PROFILE = "host"
}

$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Py)) {
    Write-Error "Missing $Py — create venv first: python -m venv .venv && .venv\Scripts\pip install -e ."
    exit 1
}

function Write-Banner([string]$msg, [string]$color = "Cyan") {
    Write-Host $msg -ForegroundColor $color
}

function Sync-Origin {
    Write-Banner "[sync] git fetch + reset --hard origin/main"
    git fetch origin 2>&1 | Out-Null
    $reset = git reset --hard origin/main 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Banner "[sync] reset failed: $reset" "Yellow"
        return $false
    }
    $head = (git rev-parse --short HEAD 2>$null)
    Write-Banner "[sync] HEAD=$head" "DarkGray"
    return $true
}

function Stop-StaleHost {
    # Kill only processes clearly running ether_host / host_agent under this root
    $patterns = @("ether_host.py", "host_agent.py", "scripts\\ether_host", "scripts/ether_host")
    $killed = 0
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match "python" -and
            $_.CommandLine -and
            ($patterns | Where-Object { $_.CommandLine -like "*$_*" })
        } |
        ForEach-Object {
            try {
                Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop
                $killed++
                Write-Banner "[recover] killed pid=$($_.ProcessId)" "Yellow"
            } catch {}
        }
    if ($killed -eq 0) {
        Write-Banner "[recover] no stale host python found" "DarkGray"
    }
    Start-Sleep -Seconds 1
}

# --- optional recovery path ---
if ($Recover) {
    Write-Banner "ETHER HOST RECOVER" "Green"
    Write-Banner "root=$Root" "DarkGray"
    Stop-StaleHost
    [void](Sync-Origin)
}

Write-Banner "ETHER HOST | http://127.0.0.1:8787/agent" "Green"
Write-Banner "model=$($env:ETHER_PRIMARY_MODEL)  profile=$($env:ETHER_HW_PROFILE)" "DarkGray"
Write-Banner "Ctrl+C to stop permanently" "DarkGray"
Write-Host ""

$backoff = 3
$maxBackoff = 30

while ($true) {
    [void](Sync-Origin)

    Write-Banner "[start] scripts\ether_host.py" "Cyan"
    & $Py "scripts\ether_host.py"
    $code = $LASTEXITCODE
    if ($null -eq $code) { $code = 1 }

    if ($code -eq 0) {
        Write-Banner "[stop] clean exit (Ctrl+C)" "Green"
        break
    }

    if ($code -eq 42) {
        Write-Banner "[reload] source updated (exit 42) — restart in 1s" "Cyan"
        $backoff = 3
        Start-Sleep -Seconds 1
        continue
    }

    Write-Banner "[crash] exit=$code — restart in ${backoff}s" "Yellow"
    Start-Sleep -Seconds $backoff
    $backoff = [Math]::Min($backoff * 2, $maxBackoff)
}
