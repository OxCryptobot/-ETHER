# Hidden 1650 attach. No second UI. MUST push attach state or Matrix stays blind.
$ErrorActionPreference = "Continue"
$root = "C:\Users\Otcde\ETHER"
if (-not (Test-Path $root)) { throw "ETHER_ROOT missing" }
Set-Location $root
$env:ETHER_ROOT = $root
$env:ETHER_FLYWHEEL_PUSH = "1"
$env:ETHER_GIT_RESET_OK = "1"
git fetch origin
git reset --hard origin/main
if (Get-Command ollama -ErrorAction SilentlyContinue) {
  Start-Process -WindowStyle Hidden ollama -ArgumentList "serve"
  Start-Sleep -Seconds 4
}
$py = $null
foreach ($c in @(".\.venv\Scripts\python.exe", ".\venv\Scripts\python.exe")) {
  if (Test-Path $c) { $py = $c; break }
}
if (-not $py) { throw "python venv missing" }
& $py -m core.loop.live_attach
if (Test-Path ".\scripts\ensure_daemon.ps1") {
  powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File .\scripts\ensure_daemon.ps1
}
git add artifacts/host_attach.json artifacts/host_health.json artifacts/host_agent_status.json 2>$null
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
  git commit -m "host attach check-in from 1650"
  git push origin main
}
