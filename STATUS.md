# @ETHER Status

## Keep-alive (do once)

```powershell
# 1) Runner as Windows SERVICE (close run.cmd safely)
cd C:\actions-runner
powershell -ExecutionPolicy Bypass -File C:\Users\Otcde\ETHER\scripts\install_runner_service.ps1

# 2) OS ensure every 5 min already via install_windows_daemon.ps1
powershell -ExecutionPolicy Bypass -File C:\Users\Otcde\ETHER\scripts\install_windows_daemon.ps1

# 3) Learning quality — pull 7b/14b coder
powershell -ExecutionPolicy Bypass -File C:\Users\Otcde\ETHER\scripts\boost_learning.ps1

# 4) Force daemon + dashboard now
powershell -ExecutionPolicy Bypass -File C:\Users\Otcde\ETHER\scripts\ensure_daemon.ps1
```

Control Matrix: http://127.0.0.1:8787  
Infra API: http://127.0.0.1:8787/api/infra  
Snapshots include `infra.alerts` (daemon / dashboard / ollama / runner).

## Auto-heal stack
| Component | Recovery |
|-----------|----------|
| ETHER daemon | `ensure_daemon.ps1` + ETHER-Ensure task + Actions every 15m |
| Dashboard :8787 | ensure restarts daemon if port closed |
| GitHub runner | `svc.cmd` service + ETHER-RunnerService task |
| Model | `ETHER_AUTO_MODEL=1` picks strongest installed coder |
