# @ETHER Status

**Dual profile live:** Linux cousin (Qwen 3.6, `ETHER_SANDBOX_BACKEND=local`) + Windows partner (Docker/auto).

### Cousin (Linux)
```bash
git fetch origin && git reset --hard origin/main
source .venv/bin/activate && pip install -e ".[dev]" -q
# .env: ETHER_PRIMARY_MODEL=<ollama list tag>  ETHER_SANDBOX_BACKEND=local
python -m cli.main doctor
python -m cli.main run "write a python function is_even(n) with assert is_even(4)"
./scripts/start_daemon_linux.sh
```

### Partner (Windows)
```powershell
git fetch origin; git reset --hard origin/main
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" -q
.\.venv\Scripts\python.exe -m cli.main doctor
```

Docs: `COUSIN.md` · `ONBOARDING.md` · `SCOREBOARD.md`
