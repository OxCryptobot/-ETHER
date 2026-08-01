# Phase C — Tool-first agent runtime

## Goal

Replace generate-only best-of-N (`core/agent_loop.py`, measured net negative)
with **Observe → tool act → Observe** against a real fixture / project tests.

## Why

FINDINGS §11: agent loop 0.083 vs bare+sys 0.333. Temperature varies phrasing,
not understanding. Headroom on pass@3 is ~5.8pp — not worth the cost.

Phase B gave an honest oracle (project pytest). Phase C uses it as the stop
condition for a tool loop.

## Slice 1 (landed)

`core/tool_runtime.py` — thin runtime, default **off** (`ETHER_TOOL_RUNTIME=1`).

Tools:

| tool | purpose |
|------|---------|
| `list_files` | observe workspace |
| `read_file` | read source |
| `write_file` | edit source (staging only) |
| `run_tests` | project pytest via repo_oracle |
| `done` | terminate |

Contract:

- One JSON tool call per step: `{"tool": "...", "args": {...}}`
- Staging copy of fixture — never live tree
- Path blocks: `.git`, `.venv`, `memory`, parent `..`
- Injectible `decide_fn` for tests without a model
- Success = `run_tests` returns `ok=True`

## Not in slice 1

- Pipeline wiring (`ether run` path)
- LLM-backed decide_fn (Rose Quartz bridge)
- Shell / arbitrary subprocess
- Curriculum / bandit / flywheel re-enable

## Tests

`tests/test_tool_runtime.py` — scripted decide_fn fixes greeter + wallet.

## Next slices

2. LLM decide_fn bridge (structured output from primary model)
3. Wire into pipeline behind `ETHER_TOOL_RUNTIME=1` for repo-edit objectives
4. Measure against Phase B fixtures before touching learning stack
