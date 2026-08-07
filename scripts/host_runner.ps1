#Requires -Version 5.1
<#
.SYNOPSIS
  ETHER host runner — execute a sprint batch, capture structured report for Grok review.

.DESCRIPTION
  Runs scripts/sprints/<name>.ps1 (or -CommandsFile), logs every command with
  exit code / stdout / stderr / duration, writes:
    artifacts/host_report_<stamp>.json
    artifacts/host_report_<stamp>.md
    artifacts/host_report_latest.md   (symlink-style copy)
  Optional: git add + commit + push the report so the next chat turn can fetch it.

.EXAMPLE
  .\scripts\host_runner.ps1 -Sprint phaseg_wire
  .\scripts\host_runner.ps1 -Sprint phaseg_wire -PushReport
  .\scripts\host_runner.ps1 -CommandsFile .\scripts\sprints\custom.ps1 -PushReport
#>
param(
    [string]$Sprint = "phaseg_wire",
    [string]$CommandsFile = "",
    [switch]$PushReport,
    [switch]$StopOnFail,
    [int]$TimeoutSec = 0
)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not (Test-Path (Join-Path $Root "core"))) {
    $Root = (Get-Location).Path
}
Set-Location $Root

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$artDir = Join-Path $Root "artifacts"
New-Item -ItemType Directory -Force -Path $artDir | Out-Null

if (-not $CommandsFile) {
    $CommandsFile = Join-Path $Root "scripts\sprints\$Sprint.ps1"
}
if (-not (Test-Path $CommandsFile)) {
    Write-Error "Sprint file not found: $CommandsFile"
    exit 2
}

Write-Host "=== ETHER host_runner ===" -ForegroundColor Cyan
Write-Host "root:    $Root"
Write-Host "sprint:  $CommandsFile"
Write-Host "stamp:   $stamp"
Write-Host ""

# Parse sprint file into labeled steps.
# Format:
#   # STEP: name
#   command line
#   command line
#   # STEP: next
$raw = Get-Content -Path $CommandsFile -Raw -Encoding UTF8
$steps = @()
$current = $null
foreach ($line in ($raw -split "`r?`n")) {
    if ($line -match '^\s*#\s*STEP:\s*(.+)$') {
        if ($null -ne $current) { $steps += $current }
        $current = @{ name = $Matches[1].Trim(); lines = @() }
        continue
    }
    if ($null -eq $current) {
        # preamble without STEP — collect as "setup"
        $current = @{ name = "setup"; lines = @() }
    }
    # skip pure comments and blanks for execution, but keep non-comment code
    if ($line -match '^\s*#' -or $line -match '^\s*$') { continue }
    $current.lines += $line
}
if ($null -ne $current) { $steps += $current }

$results = @()
$failed = 0
$i = 0
foreach ($step in $steps) {
    $i++
    $name = $step.name
    $body = ($step.lines -join "`n").Trim()
    if (-not $body) { continue }

    Write-Host "----- STEP $i/$($steps.Count): $name -----" -ForegroundColor Yellow
    Write-Host $body -ForegroundColor DarkGray

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $stdout = ""
    $stderr = ""
    $code = 0
    try {
        # Run as a scriptblock in this process so env vars persist across steps
        $out = & {
            param($codeText)
            Invoke-Expression $codeText 2>&1
        } $body
        if ($out) {
            $stdout = ($out | ForEach-Object { "$_" }) -join "`n"
        }
        if ($LASTEXITCODE -ne $null -and $LASTEXITCODE -ne 0) {
            $code = [int]$LASTEXITCODE
        }
    }
    catch {
        $code = 1
        $stderr = "$_"
        Write-Host "EXCEPTION: $_" -ForegroundColor Red
    }
    $sw.Stop()
    $elapsed = [math]::Round($sw.Elapsed.TotalSeconds, 3)

    if ($stdout) { Write-Host $stdout }
    if ($stderr) { Write-Host $stderr -ForegroundColor Red }

    $status = if ($code -eq 0) { "PASS" } else { "FAIL" }
    if ($code -ne 0) { $failed++ }
    Write-Host "[$status] exit=$code elapsed=${elapsed}s" -ForegroundColor $(if ($code -eq 0) { "Green" } else { "Red" })
    Write-Host ""

    $results += [ordered]@{
        step     = $i
        name     = $name
        command  = $body
        exit     = $code
        elapsed_s = $elapsed
        stdout   = $stdout
        stderr   = $stderr
        ok       = ($code -eq 0)
    }

    if ($StopOnFail -and $code -ne 0) {
        Write-Host "StopOnFail: aborting remaining steps" -ForegroundColor Red
        break
    }
}

$report = [ordered]@{
    stamp     = $stamp
    sprint    = $Sprint
    root      = $Root
    host      = $env:COMPUTERNAME
    user      = $env:USERNAME
    passed    = @($results | Where-Object { $_.ok }).Count
    failed    = $failed
    total     = $results.Count
    results   = $results
}

$jsonPath = Join-Path $artDir "host_report_$stamp.json"
$mdPath   = Join-Path $artDir "host_report_$stamp.md"
$latest   = Join-Path $artDir "host_report_latest.md"
$latestJ  = Join-Path $artDir "host_report_latest.json"

($report | ConvertTo-Json -Depth 8) | Set-Content -Path $jsonPath -Encoding UTF8

$md = @()
$md += "# Host report — $stamp"
$md += ""
$md += "| field | value |"
$md += "|---|---|"
$md += "| sprint | $Sprint |"
$md += "| host | $($report.host) |"
$md += "| passed | $($report.passed)/$($report.total) |"
$md += "| failed | $failed |"
$md += ""
foreach ($r in $results) {
    $st = if ($r.ok) { "PASS" } else { "FAIL" }
    $md += "## STEP $($r.step): $($r.name) — $st (exit=$($r.exit), $($r.elapsed_s)s)"
    $md += ""
    $md += '```powershell'
    $md += $r.command
    $md += '```'
    $md += ""
    if ($r.stdout) {
        $md += '```'
        # trim huge pytest noise to last 80 lines
        $lines = $r.stdout -split "`n"
        if ($lines.Count -gt 80) {
            $md += "... ($($lines.Count - 80) lines truncated) ..."
            $md += ($lines[-80..-1] -join "`n")
        } else {
            $md += $r.stdout
        }
        $md += '```'
        $md += ""
    }
    if ($r.stderr) {
        $md += "**stderr**"
        $md += '```'
        $md += $r.stderr
        $md += '```'
        $md += ""
    }
}
$mdText = $md -join "`n"
Set-Content -Path $mdPath -Value $mdText -Encoding UTF8
Copy-Item $mdPath $latest -Force
Copy-Item $jsonPath $latestJ -Force

Write-Host "=== summary: $($report.passed)/$($report.total) passed, $failed failed ===" -ForegroundColor Cyan
Write-Host "report: $mdPath"
Write-Host "latest: $latest"

if ($PushReport) {
    Write-Host "Pushing report to origin..." -ForegroundColor Cyan
    git add -- "artifacts/host_report_$stamp.md" "artifacts/host_report_$stamp.json" "artifacts/host_report_latest.md" "artifacts/host_report_latest.json" 2>$null
    # ensure artifacts not fully gitignored for reports
    git add -f -- "artifacts/host_report_latest.md" "artifacts/host_report_latest.json" 2>$null
    git add -f -- "artifacts/host_report_$stamp.md" "artifacts/host_report_$stamp.json" 2>$null
    $msg = "host report: $Sprint $($report.passed)/$($report.total) [$stamp]"
    git commit -m $msg 2>&1 | Out-Host
    git push origin main 2>&1 | Out-Host
    Write-Host "Pushed. Grok can fetch artifacts/host_report_latest.md on next turn." -ForegroundColor Green
}

if ($failed -gt 0) { exit 1 } else { exit 0 }
