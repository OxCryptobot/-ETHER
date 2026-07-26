# @ETHER — one process only

You need **1 window max**, not 4.

## Recommended (always works)

```powershell
cd C:\Users\Otcde\ETHER
powershell -ExecutionPolicy Bypass -File .\scripts\start_daemon.ps1
```

- Pulls latest from git
- Stops old processes
- Runs **one** Python: flywheel + batch + dashboard
- Leave that window open (or minimize)

Dashboard: http://127.0.0.1:8787

## Stop

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop_daemon.ps1
```

## Optional background (0 windows)

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_daemon.ps1 -Background
```

If background fails, use the default foreground command above.
