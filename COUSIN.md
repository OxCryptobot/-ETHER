# @ETHER — Cousin velocity sheet (no chat required)

## Day-0 (30 min)

```powershell
cd C:\Users\Otcde\ETHER   # or your clone path
git fetch origin
git reset --hard origin/main   # only if agreed
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
# set ETHER_PRIMARY_MODEL=qwen2.5-coder:3b
ollama pull qwen2.5-coder:3b
docker pull python:3.12-slim
python scripts\smoke_test.py
pytest -q
python -m cli.main doctor
```

## Daily (one window)

```powershell
$env:ETHER_GIT_RESET_OK = "1"
powershell -ExecutionPolicy Bypass -File .\scripts\start_daemon.ps1 -Foreground
```

Dashboard: http://127.0.0.1:8787

## Weekly scoreboard (required)

```powershell
python scripts\weekly_scoreboard.py
Get-Content SCOREBOARD.md
```

## When something breaks

| Symptom | Fix |
|---------|-----|
| `MERGE_HEAD` | `git merge --abort` then `git reset --hard origin/main` |
| venv Activation policy | `Set-ExecutionPolicy -Scope Process Bypass` |
| ether not found | use `.\.venv\Scripts\python.exe -m cli.main ...` |
| Docker 500 | restart Docker Desktop |
| NOT HEALTHY | run `python scripts\measurement_day.py` |

## Do not

- Paste API keys in chat or commit `.env`
- Install ether into Program Files
- Claim superiority without SCOREBOARD numbers

## Split of labor

| You | Partner |
|-----|---------|
| Product / hard tasks | Windows ops / daemon |
| Burst key local only | Measurement day weekly |
| Review SCOREBOARD | Quarantine reconcile |
