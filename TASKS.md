# @ETHER Task Board

**Updated:** 2026-07-26

## Shipped
- Dual profile docs (Linux Qwen 3.6 local sandbox / Windows Docker)
- sandbox auto + local backend + doctor aware
- linux_bootstrap.sh + start_daemon_linux.sh + deploy/ether.service
- tests: test_sandbox_local, test_burst_policy
- weekly/measurement scoreboard stack
- experience vault + failure graph + BM25 RAG

## Next ops (machines, not code)
1. Cousin: set real `qwen3.6:*` tag → weekly_scoreboard
2. Partner: pytest green + flywheel
3. Optional burst_ablation with keys in .env only
