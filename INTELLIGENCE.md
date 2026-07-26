# @ETHER Intelligence Layer (v2)

## Stack

| Module | Role |
|--------|------|
| `core/curriculum.py` | Graded tasks, promote/demote |
| `core/experience.py` | PASS/FAIL vault + retrieval |
| `core/rag_bm25.py` | Offline BM25 repo RAG (no Qdrant) |
| `core/failure_graph.py` | Stderr clusters → repair templates |
| `core/assert_harness.py` | Test-or-cap auto harness |
| `core/bench_guardian.py` | Freeze on pass_rate regression |
| `core/health_metric.py` | **Primary metric: bench pass_rate** |
| `core/learning.py` | Strict rewards + expanded arms + decay |
| `scripts/git_curriculum_miner.py` | Mine repo functions → curriculum |
| `scripts/run_smart_cycle.py` | One intelligent flywheel cycle |

## Strategy arms
`default`, `minimal`, `with_asserts`, `step_by_step`, `no_context`, `few_shot_on`, `repo_map_on`, `repair_heavy`, `rag_on`

## Run

```powershell
cd C:\Users\Otcde\ETHER
$env:ETHER_GIT_RESET_OK = "1"
git fetch origin
git reset --hard origin/main
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" -q

.\.venv\Scripts\python.exe .\scripts\git_curriculum_miner.py
.\.venv\Scripts\python.exe .\scripts\bench.py
.\.venv\Scripts\python.exe .\scripts\run_smart_cycle.py

powershell -ExecutionPolicy Bypass -File .\scripts\start_daemon.ps1 -Foreground
```

## Primary metric
`memory/bench/health.json` → `pass_rate` / `pass_rate_avg7` / `healthy`
