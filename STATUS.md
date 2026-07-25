# @ETHER Live Status

> **Last heartbeat**: 2026-07-25 15:35 (UTC-5)
> **Agent state**: ACTIVE
> **Overall**: **v0.2 batch 21 started**

## Progress

| Layer | % |
|-------|---|
| Foundation | 100% |
| Gems basic | 100% |
| End-to-end pipeline | 100% (verified on Windows + Docker) |
| Docs/DX | 98% |
| **v0.1.x** | **100%** |
| **v0.2** | **~15%** |

## Verified on user hardware
- Acer Nitro 5 · GTX 1650 4GB · 12GB RAM
- Primary model: `qwen2.5-coder:3b`
- Fallback: `phi3:mini`
- Docker sandbox via stdin (Windows-safe)
- Full loop: plan → code → sandbox → audit → critique

## Batch 21 delivered
1. Hardware-aware `.env.example` (3B default, tier comments)
2. Pipeline **sandbox retry**: one auto-fix pass when exit != 0 (`ETHER_SANDBOX_RETRY=1`)
3. STATUS updated for v0.2

## Remaining batch 21 / v0.2
1. Real LangGraph planner path in Selenite
2. Clear Quartz pytest harness / better test counting
3. Citrine smarter chunking
4. Human approval UX for promote
5. Benchmark harness
6. Streaming tokens option
7. Multi-file context for coding prompts
8. Latency fields already partial — extend dashboard
9. ~~Hardware-aware defaults~~ done
10. ~~Retry on sandbox fail~~ done

## Pull & try retry
```powershell
git pull origin main
$env:ETHER_PRIMARY_MODEL = "qwen2.5-coder:3b"
$env:ETHER_SANDBOX_RETRY = "1"
ether run "write a python function is_even(n) and print(is_even(4))"
```
