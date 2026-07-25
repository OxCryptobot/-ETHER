# @ETHER Flywheel (agentic)

> Overwritten each cycle by `scripts/flywheel.py`.

## Policy (non-negotiable)
1. **smoke + pytest must pass**
2. **pipeline sandbox exit = 0**
3. **audit.approved = true**
4. **confidence >= threshold** (default **0.7**)
5. If gates fail → **retry** (self-heal) up to N times
6. **`--push` only commits/pushes when all gates pass**

## PowerShell

```powershell
cd C:\Users\Otcde\ETHER
git pull origin main

# verify only (no push)
.\scripts\flywheel.ps1

# push ONLY if confidence+audit clean
.\scripts\flywheel.ps1 -Push

# stricter gate + more self-heal attempts
.\scripts\flywheel.ps1 -Push -MinConfidence 0.8 -MaxRetries 5
```

## Env knobs
```env
ETHER_FLYWHEEL_MIN_CONFIDENCE=0.7
ETHER_FLYWHEEL_MAX_RETRIES=3
ETHER_FLYWHEEL_PUSH=0
ETHER_PRIMARY_MODEL=qwen2.5-coder:3b
ETHER_SANDBOX_RETRY=1
```
