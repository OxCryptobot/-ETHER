# @ETHER Task Board

**Updated:** 2026-07-26

## Shipped
- Dual profile docs (Linux Qwen 3.6 local sandbox / Windows Docker)
- sandbox auto + local backend + doctor aware
- linux_bootstrap.sh + start_daemon_linux.sh + deploy/ether.service
- tests: test_sandbox_local, test_burst_policy, health_check, list_gems, batch_queue
- weekly/measurement scoreboard stack
- experience vault + failure graph + BM25 RAG
- **QA 2026-07-26**: pytest collection, registry list_gems, tool JSON coerce for PowerShell
- **Pipeline 2026-07-26**: force_burst via `decide_burst` + verification_score into experience
- **Batch 2026-07-26**: `core/batch_queue.py`, multi-item drain, CLI `ether batch *`, smoke seed

## Batch usage
```powershell
# status
.\.venv\Scripts\python.exe -m cli.main batch status

# seed smoke tasks (if empty)
.\.venv\Scripts\python.exe -m cli.main batch seed

# process N items
.\.venv\Scripts\python.exe -m cli.main batch run --limit 3

# or via script
.\.venv\Scripts\python.exe .\scripts\batch_worker.py --status
.\.venv\Scripts\python.exe .\scripts\batch_worker.py --limit 3
```

## Next ops (machines)
1. Partner: pull → install → `pytest -q` → `batch seed` → `batch run --limit 3`
2. Cousin: qwen3.6 tag + weekly_scoreboard
3. Optional burst_ablation with keys in .env only

## Code next
- Surface curriculum tier into `decide_burst(..., tier=...)`
- Dashboard panel for batch queue pending/done
- Auto-enqueue from curriculum failures
