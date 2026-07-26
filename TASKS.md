# @ETHER Task Board

**Updated:** 2026-07-26

## Shipped
- Dual profile docs (Linux Qwen 3.6 local sandbox / Windows Docker)
- sandbox auto + local backend + doctor aware
- linux_bootstrap.sh + start_daemon_linux.sh + deploy/ether.service
- tests: test_sandbox_local, test_burst_policy, health_check, list_gems
- weekly/measurement scoreboard stack
- experience vault + failure graph + BM25 RAG
- **QA 2026-07-26**: pytest collection, registry list_gems, tool JSON coerce for PowerShell
- **Pipeline 2026-07-26**: force_burst fully routed through `core.pipeline_burst.decide_burst`
- **Pipeline 2026-07-26**: every `experience_record` call now receives `verification_score` + `total_tests`

## Next ops (machines, not code)
1. Partner: pull → `pip install -e ".[dev]"` → `pytest -q` + health_check
2. Cousin: set real `qwen3.6:*` tag → weekly_scoreboard
3. Optional burst_ablation with keys in .env only

## Code next
- Full holdout quiz numbers on both profiles
- Optional: surface tier from curriculum into `decide_burst(..., tier=...)`
- Linux systemd smoke on cousin machine
