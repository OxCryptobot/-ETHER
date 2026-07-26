# Learning boost — HARDWARE AWARE
# Default profile=host (GTX 1650 4GB / 12GB RAM): ensure 3B only, NEVER pull 7B+.
# Cousin / high-end: set ETHER_HW_PROFILE=cousin before running.

$ErrorActionPreference = "Continue"
$Root = if ($env:ETHER_ROOT) { $env:ETHER_ROOT } else { "C:\Users\Otcde\ETHER" }
$ProfilePath = Join-Path $Root "config\hardware_profile.json"
$profile = "host"
if ($env:ETHER_HW_PROFILE) { $profile = $env:ETHER_HW_PROFILE.ToLowerInvariant() }
elseif (Test-Path $ProfilePath) {
  try {
    $j = Get-Content $ProfilePath -Raw | ConvertFrom-Json
    if ($j.profile) { $profile = [string]$j.profile }
  } catch {}
}

Write-Host "[boost] hardware profile=$profile"
try { ollama list } catch { Write-Host "ollama not on PATH"; exit 1 }

if ($profile -ne "cousin") {
  Write-Host "[boost] HOST mode — capped at 3B class (your GTX 1650 4GB / 12GB RAM)"
  Write-Host "[boost] will NOT pull 7b/14b/32b"
  $listed = (ollama list 2>$null | Out-String)
  if ($listed -notmatch "qwen2.5-coder:3b") {
    Write-Host "[boost] pulling qwen2.5-coder:3b (fits this machine)"
    ollama pull qwen2.5-coder:3b
  } else {
    Write-Host "[boost] qwen2.5-coder:3b already present — OK"
  }
  $env:ETHER_PRIMARY_MODEL = "qwen2.5-coder:3b"
  $env:ETHER_AUTO_MODEL = "1"
  $env:ETHER_HW_PROFILE = "host"
  if (Test-Path "$Root\.venv\Scripts\python.exe") {
    & "$Root\.venv\Scripts\python.exe" -c "from core.model_select import select_primary_model; import json; print(json.dumps(select_primary_model(force_refresh=True), indent=2))"
  }
  Write-Host "[boost] host done — learning gains come from curriculum/verify, not bigger weights"
  exit 0
}

# --- cousin / high-end only ---
Write-Host "[boost] COUSIN mode — may pull 7b/14b"
$candidates = @("qwen2.5-coder:7b", "qwen2.5-coder:14b")
if ($env:ETHER_PULL_32B -eq "1") { $candidates = @("qwen2.5-coder:14b", "qwen2.5-coder:32b") + $candidates }
foreach ($m in $candidates) {
  Write-Host "[boost] ollama pull $m"
  ollama pull $m
  if ($LASTEXITCODE -eq 0 -and $m -notmatch ":3b") { break }
}
$env:ETHER_AUTO_MODEL = "1"
$env:ETHER_HW_PROFILE = "cousin"
if (Test-Path "$Root\.venv\Scripts\python.exe") {
  & "$Root\.venv\Scripts\python.exe" -c "from core.model_select import select_primary_model; import json; print(json.dumps(select_primary_model(force_refresh=True), indent=2))"
}
Write-Host "[boost] cousin done"
