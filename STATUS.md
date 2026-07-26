# @ETHER Status

**71–74 on main:** methodology protocol, test_synth, ONBOARDING.md, scratch patch_loop.

```powershell
cd C:\Users\Otcde\ETHER
$env:ETHER_GIT_RESET_OK = "1"
git fetch origin
git reset --hard origin/main
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" -q
.\.venv\Scripts\python.exe -m pytest -q
```

Read: `ONBOARDING.md`, `METHODOLOGY.md`, `SCOREBOARD.md`.
