# @ETHER Status — feedback-loop build

**Gaps closed in code:** dense scoreboard, ablation script, multifile scratch, BM25 RAG, MBPP-lite dataset quiz, failure-graph repair, COUSIN.md, weekly_scoreboard.

```powershell
cd C:\Users\Otcde\ETHER
$env:ETHER_GIT_RESET_OK = "1"
git fetch origin
git reset --hard origin/main
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" -q
.\.venv\Scripts\python.exe .\scripts\weekly_scoreboard.py
Get-Content .\SCOREBOARD.md
```

Optional: `burst_ablation.py` with keys only in `.env`.
Read `COUSIN.md` for partner ops.
