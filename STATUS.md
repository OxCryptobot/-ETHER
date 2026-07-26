# @ETHER Status — P0 measurement stack

**Brand line:** A local verified coding agent that learns from its own gated runs and calls a frontier model only when the local path fails — with public holdout scores.

## Pull

```powershell
cd C:\Users\Otcde\ETHER
$env:ETHER_GIT_RESET_OK = "1"
git fetch origin
git reset --hard origin/main
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" -q
```

## Measurement day (do this)

```powershell
.\.venv\Scripts\python.exe .\scripts\measurement_day.py
Get-Content .\SCOREBOARD.md
Get-Content .\memory\bench\health.json
```

## Optional burst ablation (needs key in .env only)

```powershell
$env:ETHER_BURST = "1"
$env:ETHER_BURST_URL = "https://api.groq.com/openai/v1"
$env:ETHER_BURST_MODEL = "llama-3.3-70b-versatile"
# $env:ETHER_BURST_API_KEY from .env — do not paste keys in chat
.\.venv\Scripts\python.exe .\scripts\burst_ablation.py --limit 10
.\.venv\Scripts\python.exe .\scripts\hidden_quiz.py --limit 5
.\.venv\Scripts\python.exe .\scripts\git_curriculum_miner.py
```

Healthy = bench **and** quiz both <24h stale, pass_rate≥0.4, guardian not frozen.
