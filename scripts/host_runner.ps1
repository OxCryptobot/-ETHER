#Requires -Version 5.1
<#
.SYNOPSIS
  ETHER host runner - execute sprint batch, capture report.
  NEVER rewrites python paths by string replace (that triple-stacked paths).
  Sets $env:ETHER_PY once; sprint files must use & $env:ETHER_PY ...
#>
param(
    [string]$Sprint = "phaseg_verify",
    [string]$CommandsFile = "",
    [switch]$PushReport,
    [switch]$StopOnFail
)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not (Test-Path (Join-Path $Root "core"))) {
    $Root = (Get-Location).Path
}
Set-Location $Root

# Resolve Python once - prefer .venv
$Py = $null
foreach ($c in @(
    (Join-Path $Root ".venv\Scripts\python.exe"),
    (Join-Path $Root "venv\Scripts\python.exe")
)) {
    if (Test-Path -LiteralPath $c) {
        $Py = (Resolve-Path -LiteralPath $c).Path
        break
    }
}
if (-not $Py) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { $Py = $cmd.Source }
}
if (-not $Py -or -not (Test-Path -LiteralPath $Py)) {
    Write-Error "QC FAIL: python not found under $Root\.venv\Scripts\python.exe"
    exit 3
}

# CRITICAL: only injection mechanism. No string rewrite of bodies.
$env:ETHER_PY = $Py
$env:ETHER_ROOT = $Root

# Preflight - must run or abort entire sprint
$pre = & $Py -c "import sys; print(sys.executable)" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "QC FAIL: python preflight failed: $pre"
    exit 3
}
Write-Host "python:  $Py" -ForegroundColor Green
Write-Host "preflight: $pre" -ForegroundColor DarkGray

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$artDir = Join-Path $Root "artifacts"
New-Item -ItemType Directory -Force -Path $artDir | Out-Null

if (-not $CommandsFile) {
    $CommandsFile = Join-Path $Root "scripts\sprints\$Sprint.ps1"
}
if (-not (Test-Path -LiteralPath $CommandsFile)) {
    Write-Error "Sprint file not found: $CommandsFile"
    exit 2
}

Write-Host "=== ETHER host_runner ===" -ForegroundColor Cyan
Write-Host "root:    $Root"
Write-Host "sprint:  $CommandsFile"
Write-Host "stamp:   $stamp"
Write-Host ""

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
        $current = @{ name = "setup"; lines = @() }
    }
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

    # Guard: refuse bodies that still use relative venv paths (must use `$env:ETHER_PY)
    if ($body -match '\\\.venv\\Scripts\\python' -or $body -match '\\venv\\Scripts\\python') {
        Write-Host "QC FAIL step $name: sprint must use `$env:ETHER_PY not relative venv path" -ForegroundColor Red
        $failed++
        $results += [ordered]@{
            step = $i; name = $name; command = $body; exit = 2; elapsed_s = 0
            stdout = ""; stderr = "QC: relative venv path forbidden; use `$env:ETHER_PY"; ok = $false
        }
        if ($StopOnFail) { break }
        continue
    }

    Write-Host "----- STEP $i/$($steps.Count): $name -----" -ForegroundColor Yellow
    Write-Host $body -ForegroundColor DarkGray

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $stdout = ""
    $stderr = ""
    $code = 0
    try {
        $out = Invoke-Expression $body 2>&1
        if ($out) {
            $stdout = ($out | ForEach-Object { "$_" }) -join "`n"
        }
        if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
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
    $color = if ($code -eq 0) { "Green" } else { "Red" }
    Write-Host "[$status] exit=$code elapsed=${elapsed}s" -ForegroundColor $color
    Write-Host ""

    $results += [ordered]@{
        step      = $i
        name      = $name
        command   = $body
        exit      = $code
        elapsed_s = $elapsed
        stdout    = $stdout
        stderr    = $stderr
        ok        = ($code -eq 0)
    }

    if ($StopOnFail -and $code -ne 0) { break }
}

$report = [ordered]@{
    stamp   = $stamp
    sprint  = $Sprint
    root    = $Root
    python  = $Py
    host    = $env:COMPUTERNAME
    user    = $env:USERNAME
    passed  = @($results | Where-Object { $_.ok }).Count
    failed  = $failed
    total   = $results.Count
    results = $results
}

$jsonPath = Join-Path $artDir "host_report_$stamp.json"
$mdPath   = Join-Path $artDir "host_report_$stamp.md"
$latest   = Join-Path $artDir "host_report_latest.md"
$latestJ  = Join-Path $artDir "host_report_latest.json"

($report | ConvertTo-Json -Depth 8) | Set-Content -Path $jsonPath -Encoding UTF8

$md = New-Object System.Collections.Generic.List[string]
[void]$md.Add("# Host report - $stamp")
[void]$md.Add("")
[void]$md.Add("| field | value |")
[void]$md.Add("|---|---|")
[void]$md.Add("| sprint | $Sprint |")
[void]$md.Add("| python | $Py |")
[void]$md.Add("| host | $($report.host) |")
[void]$md.Add("| passed | $($report.passed)/$($report.total) |")
[void]$md.Add("| failed | $failed |")
[void]$md.Add("")

foreach ($r in $results) {
    $st = if ($r.ok) { "PASS" } else { "FAIL" }
    [void]$md.Add("## STEP $($r.step): $($r.name) - $st (exit=$($r.exit), $($r.elapsed_s)s)")
    [void]$md.Add("")
    [void]$md.Add('```powershell')
    [void]$md.Add($r.command)
    [void]$md.Add('```')
    [void]$md.Add("")
    if ($r.stdout) {
        [void]$md.Add('```')
        $lines = $r.stdout -split "`n"
        if ($lines.Count -gt 80) {
            [void]$md.Add("... ($($lines.Count - 80) lines truncated) ...")
            [void]$md.Add(($lines[-80..-1] -join "`n"))
        } else {
            [void]$md.Add($r.stdout)
        }
        [void]$md.Add('```')
        [void]$md.Add("")
    }
    if ($r.stderr) {
        [void]$md.Add("**stderr**")
        [void]$md.Add('```')
        [void]$md.Add($r.stderr)
        [void]$md.Add('```')
        [void]$md.Add("")
    }
}

$mdText = $md -join "`n"
Set-Content -Path $mdPath -Value $mdText -Encoding UTF8
Copy-Item $mdPath $latest -Force
Copy-Item $jsonPath $latestJ -Force

Write-Host "=== summary: $($report.passed)/$($report.total) passed, $failed failed ===" -ForegroundColor Cyan
Write-Host "report: $mdPath"

if ($PushReport) {
    git add -f -- "artifacts/host_report_$stamp.md" "artifacts/host_report_$stamp.json" "artifacts/host_report_latest.md" "artifacts/host_report_latest.json" 2>$null
    $msg = "host report: $Sprint $($report.passed)/$($report.total) [$stamp]"
    git commit -m $msg 2>&1 | Out-Host
    git push origin main 2>&1 | Out-Host
}

if ($failed -gt 0) { exit 1 } else { exit 0 }
