# @ETHER Live Status

> **Autonomous mode available** — no manual PowerShell after start

## Hands-off start (once)

```powershell
cd C:\Users\Otcde\ETHER
git pull origin main
copy .env.example .env   # only if .env missing
powershell -ExecutionPolicy Bypass -File .\scripts\autonomy.ps1
```

Or:

```powershell
ether flywheel --autonomous
```

## Behavior
- Loads `.env` automatically (model, thresholds, interval)
- Loop: pull → smoke → pytest → agentic pipeline → **push only if gates pass**
- Gates: sandbox exit 0 + audit approved + confidence ≥ 0.7
- Retries failed agentic runs until max retries
- Heartbeat: `memory/flywheel/heartbeat.txt`
- Last report: `memory/flywheel/latest.json`

## Check without touching the loop
```powershell
ether flywheel --status
```
