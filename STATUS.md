# @ETHER Status — Intelligence v2

P0/P1 intelligence stack is on `main`:

- Curriculum + experience vault + bench guardian
- BM25 offline RAG
- Failure graph repair templates
- Assert harness (test-or-cap) inside Clear Quartz
- Strict rewards + expanded bandit arms
- Git curriculum miner
- Primary metric: `memory/bench/health.json`

```powershell
cd C:\Users\Otcde\ETHER
$env:ETHER_GIT_RESET_OK = "1"
git fetch origin
git reset --hard origin/main
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe .\scripts\git_curriculum_miner.py
.\.venv\Scripts\python.exe .\scripts\bench.py
.\.venv\Scripts\python.exe .\scripts\run_smart_cycle.py
powershell -ExecutionPolicy Bypass -File .\scripts\start_daemon.ps1 -Foreground
```
