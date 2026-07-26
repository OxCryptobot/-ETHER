# @ETHER Flywheel — rinse & repeat

## Loop (git ↔ local ↔ sandbox ↔ git)

```
origin/main
    │ pull (self-heal)
    ▼
local tree + pip install -e .[dev]
    │
    ├─ daemon_smoke
    ├─ smoke + pytest + doctor
    ├─ batch_tick (soft)
    ├─ agentic: plan → code → sandbox → audit → confidence gate
    │
    ▼
commit + push PASS/FAIL report → origin/main
    │ sleep interval
    └─ repeat
```

## Start continuous (local)

```powershell
cd C:\Users\Otcde\ETHER
$env:ETHER_GIT_RESET_OK = "1"
$env:ETHER_FLYWHEEL_PUSH = "1"
$env:ETHER_PRIMARY_MODEL = "qwen2.5-coder:3b"

# one cycle
.\.venv\Scripts\python.exe -m cli.main flywheel --push

# rinse and repeat forever
.\.venv\Scripts\python.exe -m cli.main flywheel --autonomous --interval 900 --push
```

Or install the Windows daemon (`scripts\install_windows_daemon.ps1`) so this survives logout of the chat.
