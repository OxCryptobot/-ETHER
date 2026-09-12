# Week autonomy (2026-09-12c)

Matrix face is READ-ONLY. This repo is the writer.

## Fixed this pass
- matrix-worker now commits gem_energy / board / role / week_tick (the 03:45 tick ran but energy was dropped on the floor).
- drain always idle-ticks week_tick even when pending is empty.
- class=fast always drains (notes may mention the card without being treated as LIVE).
- ubuntu live-host no longer overwrites a 1650 attach with grok_bus.
- worker cron every 4h so energy keeps moving while Grok is dark.

## Still true
- Ollama 4B stays false until the existing ETHER.exe is running on the 1650.
- Self-hosted autonomy-host runner is queued, not online.
- Soft launch BLOCKED. Wheels stay ON.
- No new installer. No Matrix writes.
