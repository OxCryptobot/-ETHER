# @ETHER Status

**Updated:** 2026-08-15 18:48Z — Phase 2.4 symbol index v0 landed. Soft launch **BLOCKED**.

## Law
**Test after every build. Do not break working paths.**
- `ETHER_LOOP_RUNNER` default `0`
- `ETHER_SYMBOL_INDEX` default `0` (opt-in only)

## Host
Alive. Verification job `p2_4_symbol_index_verify` enqueued.

## Phase map

| Phase | Item | Status |
|-------|------|--------|
| 2.1 | PlanState replan | done |
| 2.2 | Multi-file AST tx | done |
| 2.3 | Orchestration slice | done |
| **2.4** | **Symbol/file index v0** | **done (opt-in)** |
| **2.5** | LoRA dry tick only | **NEXT** |

## Verify
```powershell
.venv\Scripts\python.exe -m pytest tests/test_symbol_index.py tests/test_pipeline_orchestration_slice.py tests/test_multifile_ast_tx.py tests/test_plan_state.py tests/test_tool_runtime.py -q --tb=line
```
