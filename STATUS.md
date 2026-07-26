# @ETHER Status

**Automated health checks are live.**

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

### Windows partner
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
