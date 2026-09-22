# Unified architecture (do not grow this)

```
Matrix  --read-->  origin
Ubuntu  --FAST-->  origin   (never attach)
1650    --LIVE-->  origin   (only attach writer)
```

LIVE is **one** function: `scripts.host_main.tick` on the 1650.
GitHub `autonomy-host` (self-hosted runner) is **optional**. Queued Actions is not LIVE.
Keepalive / HKCU Run / Startup arm that tick. Matrix does not start it.

Verified: Ubuntu observe-only does not write attach.
Not verified: 1650 `git push` (last exe commit 2026-09-11).
