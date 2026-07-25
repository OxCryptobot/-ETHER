# @ETHER Flywheel

> Bootstrap file. Overwritten by `scripts/flywheel.py` each cycle.

## Quick start (PowerShell)

```powershell
cd C:\Users\Otcde\ETHER
.\scripts\flywheel.ps1
.\scripts\flywheel.ps1 -Push
.\scripts\flywheel.ps1 -Loop 300 -Push
```

Or pure Python:

```powershell
python scripts/flywheel.py
python scripts/flywheel.py --push
python scripts/flywheel.py --loop 300 --push
```

## What it does
1. `git pull --ff-only origin main`
2. smoke test + pytest
3. optional `ether doctor`
4. writes `memory/flywheel/latest.json` + appends history
5. updates this `FLYWHEEL.md`
6. with `--push` / `ETHER_FLYWHEEL_PUSH=1`: commits **only** flywheel artifacts and pushes

## Safety
- Never force-push
- Only stages `FLYWHEEL.md` and `memory/flywheel/*`
- Push is opt-in
