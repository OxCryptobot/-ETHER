# Raise learning quality: pull better coder weights into Ollama if missing.
# Safe to re-run. Does not remove 3b.

$ErrorActionPreference = "Continue"
Write-Host "[boost] checking ollama"
try { ollama list } catch { Write-Host "ollama not on PATH"; exit 1 }

# Prefer 14b then 7b — skip 32b unless user sets ETHER_PULL_32B=1
$candidates = @("qwen2.5-coder:7b", "qwen2.5-coder:14b")
if ($env:ETHER_PULL_32B -eq "1") { $candidates = @("qwen2.5-coder:14b", "qwen2.5-coder:32b") + $candidates }

$listed = (ollama list 2>$null | Out-String)
foreach ($m in $candidates) {
  if ($listed -match [regex]::Escape($m.Split(":")[0])) {
    Write-Host "[boost] family present for $m — pulling exact tag"
  }
  Write-Host "[boost] ollama pull $m"
  ollama pull $m
  if ($LASTEXITCODE -eq 0) {
    Write-Host "[boost] OK $m"
    # stop after first successful upgrade pull beyond 3b
    if ($m -notmatch ":3b") { break }
  }
}

$env:ETHER_AUTO_MODEL = "1"
$Root = if ($env:ETHER_ROOT) { $env:ETHER_ROOT } else { "C:\Users\Otcde\ETHER" }
if (Test-Path "$Root\.venv\Scripts\python.exe") {
  & "$Root\.venv\Scripts\python.exe" -c "from core.model_select import select_primary_model; import json; print(json.dumps(select_primary_model(force_refresh=True), indent=2))"
}
Write-Host "[boost] done — restart daemon via ensure_daemon.ps1 to pick new model"
