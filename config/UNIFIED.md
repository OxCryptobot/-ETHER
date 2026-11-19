# Unified architecture (do not grow this)

```
Matrix  --read-->  origin
Ubuntu  --FAST-->  origin   (never attach)
1650    --LIVE-->  origin   (only attach writer)
```

LIVE is **one** function: `scripts.host_main.tick` on the 1650.
There is no `ETHER.exe`. The writer loop is `scripts/host_supervisor.py` (venv `pythonw`), started only by the one
Scheduled Task `ETHER-Host` (`scripts\install_host.cmd`, control: `scripts\host.cmd start|stop|status`).
GitHub `autonomy-host` is optional: it only ensures ETHER-Host is running. Queued Actions is not LIVE.

**Never again (Sept 12 class failure):**
- An open window is not a heartbeat.
- `app_alive.ts` older than **6 hours** = `live_status.stale=true` = LIVE FAIL.
- Ubuntu writes `live_status.json` only. Never `host_attach` / `app_alive`.
- Do not disable a working host until the new writer produces a today attach.
- Do not freeze the writer inside a PyInstaller binary; always exec disk `host_main.py`.

Verified: Ubuntu observe-only does not write attach.
Verified from origin: the 1650 pushed `1650 host_main` commits on 2026-11-19 (runner path).
Not verified: the ETHER-Host supervisor on the 1650 (needs `install_host.cmd` run there).
