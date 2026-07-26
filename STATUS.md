# @ETHER Status

**Latest:** local sandbox tests · burst policy tests · Linux bootstrap/systemd · COUSIN Qwen 3.6 tags

### Linux cousin
```bash
git fetch origin && git reset --hard origin/main
bash scripts/linux_bootstrap.sh
# set ETHER_PRIMARY_MODEL from `ollama list` (e.g. qwen3.6:27b)
# ETHER_SANDBOX_BACKEND=local
python -m cli.main doctor
python -m cli.main run "write a python function is_even(n) with assert is_even(4)"
./scripts/start_daemon_linux.sh
```

### Windows partner
```powershell
git fetch origin; git reset --hard origin/main
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m cli.main doctor
```
