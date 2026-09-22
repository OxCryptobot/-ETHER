# Unified architecture (do not grow this)

```
Matrix  --read-->  origin
Ubuntu  --FAST-->  origin   (never attach)
1650    --LIVE-->  origin   (only attach writer)
```

One disk function on Windows: `scripts.host_main.tick`.
Keepalive, exe loop, and week tick call that. Nothing else starts Ollama or writes `host_attach.json`.

Verified here: Ubuntu observe-only does not write attach.
Not verified here: 1650 `git push` (last exe commit 2026-09-11).
