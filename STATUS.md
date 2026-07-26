# @ETHER Status

## One command (bring-up)

```powershell
cd C:\Users\Otcde\ETHER
git fetch origin
git reset --hard origin/main
powershell -ExecutionPolicy Bypass -File .\scripts\stabilize.ps1
```

That script, in order:
1. Sync `main`
2. venv + `pip install -e ".[dev]"`
3. Host model profile (**qwen2.5-coder:3b** only - GTX 1650 4GB / 12GB RAM)
4. Offline self-test
5. Register **ETHER-Daemon** + **ETHER-Ensure** and start Control Matrix
6. Optionally start GitHub runner keep-alive if `C:\actions-runner` is configured

## What actually matters

| Piece | Role |
|-------|------|
| **ether_daemon.py** | Local autonomy loop (flywheel, batch, recovery, dashboard) |
| **ETHER-Ensure** task | Restarts daemon if dead or :8787 closed |
| **Control Matrix** | http://127.0.0.1:8787 |
| **GitHub runner** | Optional remote dispatch only - **not required** for local autonomy |

## Hardware (host)

- GPU: GTX 1650 4GB
- RAM: 12GB
- Model cap: **3B** (`config/hardware_profile.json` profile=`host`)
- Do **not** pull 7B/14B on this machine

## Verify

```powershell
Get-ScheduledTask | Where-Object TaskName -like 'ETHER*'
Get-Content C:\Users\Otcde\ETHER\memory\daemon\ensure.log -Tail 20
# browser
start http://127.0.0.1:8787
```
