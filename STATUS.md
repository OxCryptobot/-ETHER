# @ETHER Live Status

> **Last heartbeat**: 2026-07-25 15:55 (UTC-5)
> **Agent state**: ACTIVE
> **Overall**: **v0.2 batch 21 progressing**

## Progress

| Layer | % |
|-------|---|
| Foundation | 100% |
| Gems basic | 100% |
| End-to-end pipeline | 100% (verified Windows) |
| v0.1.x | 100% |
| **v0.2** | **~35%** |

## Batch 21 done so far
1. Hardware-aware `.env.example` (3B default)
2. Sandbox auto-retry on failure
3. Fairer confidence for exit=0 demo runs (no longer stuck at 0.35)
4. Informal test credit (print stdout / asserts)
5. Optional LangGraph path (`ETHER_LANGGRAPH=1`) + shared intent catalog

## Verified hardware
- Nitro 5 · GTX 1650 4GB · 12GB RAM · `qwen2.5-coder:3b`

## Still open
- Citrine smarter chunking
- Multi-file context
- Benchmark harness
- Streaming tokens
- Human approval UX for promote
- Stronger pytest injection in sandbox

## Pull
```powershell
git pull origin main
$env:ETHER_PRIMARY_MODEL = "qwen2.5-coder:3b"
ether run "write a python function is_even(n) and print(is_even(4))"
# expect Confidence closer to ~0.55–0.60 now on clean demo runs
```
