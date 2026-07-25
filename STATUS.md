# @ETHER Live Status

> **Last heartbeat**: 2026-07-25 16:15 (UTC-5)
> **Agent state**: ACTIVE
> **Overall**: **agentic flywheel gated by confidence + audit**

## Flywheel policy
- No timer-based blind push
- Retries until confidence/audit pass (or max retries)
- **Push blocked** unless:
  - smoke + pytest pass
  - sandbox exit 0
  - audit approved
  - confidence ≥ min (default 0.7)

```powershell
git pull origin main
.\scripts\flywheel.ps1 -Push -MinConfidence 0.7 -MaxRetries 3
```

## Stack verified
- Nitro 5 · GTX 1650 4GB · `qwen2.5-coder:3b`
- Pipeline confidence can hit 1.0 on clean runs

## v0.2 open
- Citrine chunking · multi-file context · benchmarks · streaming · promote UX
