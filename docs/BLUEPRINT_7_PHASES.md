# ETHER 7-Phase SOTA Blueprint

Build **in order**. Each phase has a host-agent job in `artifacts/jobs/pending/`.
No phase starts until the previous phase job reports PASS (agent runs queue FIFO).

| # | Name | Outcome |
|---|------|---------|
| 1 | Tool surface & fail-closed | grep/glob/apply_patch/rollback + ruff gate + tests green |
| 2 | Verification spine | CQ multifile + repo_oracle + score>=1 honesty |
| 3 | Context & memory (no leak) | RAG/experience stripped of answer leak; prompt_guard on |
| 4 | Planning & interleaved think | Structured plan + preserved reasoning blocks |
| 5 | Repo-scale edits | Multi-file apply_patch chains; workspace truth |
| 6 | Swarm (gated) | Supervisor + workers; offline default |
| 7 | Controlled evolution | Template tools + offline flywheel only |

## Status

- Phase 1 core tools: **DONE** (job 003 + land_runtime_001)
- Phase 1 ruff gate + closeout: **queued**
- Phases 2–7: **queued** as scaffold + measure jobs

## Operating rules

1. Direct `argv` jobs only for Python (no PS path rewrite).
2. Failed job → immediate fix + requeue (no idle wait on chat).
3. Poll idle = 3s; jobs in queue run back-to-back with **zero** idle between them.
4. Flywheel / BoN stay off until honest benchmarks say otherwise (FINDINGS).
