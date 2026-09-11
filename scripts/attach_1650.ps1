# Hidden 1650 attach. No UI. Run once on the Windows box.
# Registers nothing visible. Starts Ollama + ether daemon if present.
$ErrorActionPreference = "Stop"
$root = "C:\Users\Otcde\ETHER"
if (-not (Test-Path $root)) { throw "ETHER_ROOT missing" }
Set-Location $root
git fetch origin
git reset --hard origin/main
if (Get-Command ollama -ErrorAction SilentlyContinue) {
  Start-Process -WindowStyle Hidden ollama -ArgumentList "serve"
}
if (Test-Path ".\scripts\ensure_daemon.ps1") {
  powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File .\scripts\ensure_daemon.ps1
}
if (Test-Path ".\venv\Scripts\python.exe") {
  .\.venv\Scripts\python.exe -m core.loop.live_attach
} elseif (Test-Path ".venv\Scripts\python.exe") {
  .\.venv\Scripts\python.exe -m core.loop.live_attach
}
