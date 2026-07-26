# Restart dashboard if health fails
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot\..
$port = if ($env:ETHER_DASH_PORT) { $env:ETHER_DASH_PORT } else { "8787" }
$url = "http://127.0.0.1:$port/api/health"
$interval = 30

function Test-Health {
  try {
    $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3
    return $r.StatusCode -eq 200
  } catch { return $false }
}

Write-Host "@ETHER watchdog on $url every ${interval}s"
while ($true) {
  if (-not (Test-Health)) {
    Write-Host "$(Get-Date -Format o) health FAIL → restart dashboard"
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
      $_.CommandLine -match 'cli.main dashboard|uvicorn.*dashboard'
    } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "-m","cli.main","dashboard" -WindowStyle Minimized
    Start-Sleep -Seconds 5
  }
  Start-Sleep -Seconds $interval
}
