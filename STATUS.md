# @ETHER Status

**Local 24/7 path:** Windows daemon (not the chat).

```powershell
cd C:\Users\Otcde\ETHER
$env:ETHER_GIT_RESET_OK = "1"
git fetch origin
git reset --hard origin/main
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" -q
powershell -ExecutionPolicy Bypass -File .\scripts\install_windows_daemon.ps1
schtasks /Run /TN ETHER-Daemon
```

See **DAEMON.md** for control, logs, and batch queue.

P3 deferred until **2026-08-01**.
