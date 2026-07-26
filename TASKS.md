# @ETHER Task Board

**Updated:** 2026-07-26 (QA integrity pass)

## Shipped
- Dual profile docs (Linux Qwen 3.6 local sandbox / Windows Docker)
- sandbox auto + local backend + doctor aware
- linux_bootstrap.sh + start_daemon_linux.sh + deploy/ether.service
- tests: test_sandbox_local, test_burst_policy, health_check
- weekly/measurement scoreboard stack
- experience vault + failure graph + BM25 RAG
- **QA 2026-07-26**: pytest collection (pythonpath + conftest), registry test, tool JSON coerce for PowerShell

## Next ops (machines, not code)
1. Partner: `git reset --hard origin/main` → `pip install -e ".[dev]"` → `pytest -q` + health_check must be green
2. Cousin: set real `qwen3.6:*` tag → weekly_scoreboard
3. Optional burst_ablation with keys in .env only

## Code next (when green)
- Wire pipeline force_burst fully through `core.pipeline_burst.decide_burst` (currently duplicated inline)
- Pass `verification_score` + `total_tests` from Pipeline into every `experience_record` call
- Full holdout quiz numbers on both profiles
