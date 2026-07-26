# @ETHER Status

**QA integrity pass (2026-07-26).** pytest green. Registry `list_gems` restored.

### Run checks
```bash
# full (includes sandbox smoke)
python scripts/health_check.py

# fast (skip live sandbox)
python scripts/health_check.py --skip-sandbox

# JSON for tooling
python scripts/health_check.py --json --skip-sandbox
```

Writes:
- `memory/health/latest.json`
- `memory/health/history.jsonl`

API (dashboard running):
- `GET /api/health-check?skip_sandbox=true`
- `POST /api/health-check` `{"skip_sandbox": true}`

### Windows partner (after pull)
```powershell
git fetch origin; git reset --hard origin/main
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" -q
.\.venv\Scripts\python.exe .\scripts\health_check.py --skip-sandbox
.\.venv\Scripts\python.exe -m pytest -q
```

### Linux cousin
```bash
git fetch origin && git reset --hard origin/main
source .venv/bin/activate && pip install -e ".[dev]" -q
python scripts/health_check.py --skip-sandbox
```

### Known non-code gate
`intel_gates` reports **unhealthy** when guardian is frozen (regression 1.0 → 0.8 exceeded tol). That is intentional safety data, not a code defect.

Refresh:
```powershell
.\.venv\Scripts\python.exe .\scripts\weekly_scoreboard.py
```
Or, only if you intentionally accept the regression, delete `memory/bench/guardian.json` and re-run health.
