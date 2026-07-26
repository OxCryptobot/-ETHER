# @ETHER Status

**P0 scoreboard stack live:** holdout quiz, fast bench, vault-synced curriculum, honest test counts, optional Grok-class burst, SCOREBOARD.md.

```powershell
cd C:\Users\Otcde\ETHER
$env:ETHER_GIT_RESET_OK = "1"
git fetch origin
git reset --hard origin/main
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" -q

.\.venv\Scripts\python.exe .\scripts\bootstrap_intel.py
.\.venv\Scripts\python.exe .\scripts\bench.py --fast
.\.venv\Scripts\python.exe .\scripts\quiz.py --limit 5
Get-Content .\SCOREBOARD.md
Get-Content .\memory\curriculum\state.json
```

Optional burst:
```powershell
$env:ETHER_BURST="1"
$env:XAI_API_KEY="..."
$env:ETHER_BURST_MODEL="grok-3"
```
