# @ETHER Intelligence Layer

## What shipped

| Module | Role |
|--------|------|
| `core/curriculum.py` + `memory/curriculum/tiers.json` | Graded tasks; promote/demote difficulty |
| `core/experience.py` | PASS/FAIL vault + similarity retrieval into prompts |
| `core/bench_guardian.py` | Freeze fabricate/promote on bench regression |
| Pipeline wiring | Retrieves experience; records every run; respects guardian |
| Flywheel helper | Samples curriculum objective each cycle |

## Enable (default ON)

```text
ETHER_CURRICULUM=1
ETHER_EXPERIENCE=1
ETHER_BENCH_GUARDIAN=1
ETHER_LEARNING=1
```

## Local loop

```powershell
cd C:\Users\Otcde\ETHER
$env:ETHER_GIT_RESET_OK = "1"
git fetch origin
git reset --hard origin/main
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" -q

# baseline bench (sets guardian baseline on first run)
.\.venv\Scripts\python.exe .\scripts\bench.py

# autonomous intelligence cycles
$env:ETHER_CURRICULUM = "1"
$env:ETHER_EXPERIENCE = "1"
$env:ETHER_FLYWHEEL_PUSH = "1"
.\.venv\Scripts\python.exe -m cli.main flywheel --autonomous --interval 900 --push
```

Or single process:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_daemon.ps1 -Foreground
```

## How it gets smarter

1. Curriculum picks harder tasks after consecutive wins  
2. Experience vault injects similar past PASS/FAIL into the next prompt  
3. Bandit learns which strategy arms earn reward  
4. Bench guardian freezes risky self-modification if pass_rate collapses  

Primary metric: `memory/bench/latest.json` → `pass_rate`
