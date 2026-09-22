# Unified architecture (do not grow this)

```
Matrix  --read-->  origin
Ubuntu  --FAST-->  origin   (never attach)
1650    --LIVE-->  origin   (only attach writer)
```

LIVE is **one** function: `scripts.host_main.tick` on the 1650.
The frozen `ETHER.exe` is a **window**. Writer is detached venv `pythonw` spawned by the exe (`spawn_writer`).
GitHub `autonomy-host` is optional. Queued Actions is not LIVE.

**Never again (Sept 12 class failure):**
- An open window is not a heartbeat.
- `app_alive.ts` older than **6 hours** = `live_status.stale=true` = LIVE FAIL.
- Ubuntu writes `live_status.json` only. Never `host_attach` / `app_alive`.
- Do not disable a working host until the new writer produces a today attach.
- Do not freeze the writer inside a PyInstaller binary; always exec disk `host_main.py`.

Verified: Ubuntu observe-only does not write attach.
Not verified: 1650 `git push` (last exe commit 2026-09-11).
