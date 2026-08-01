# Phase C — Tool-first agent runtime

## Goal

Replace generate-only best-of-N (`core/agent_loop.py`, measured net negative)
with **Observe → tool act → Observe** against a real fixture / project tests.

## Why

FINDINGS §11: agent loop 0.083 vs bare+sys 0.333. Temperature varies phrasing,
not understanding. Headroom on pass@3 is ~5.8pp — not worth the cost.

Phase B gave an honest oracle (project pytest). Phase C uses it as the stop
condition for a tool loop.

## Slice 1 — runtime (CLOSED)

`core/tool_runtime.py` — thin runtime, default **off** (`ETHER_TOOL_RUNTIME=1`).

| tool | purpose |
|------|---------|
| `list_files` | observe workspace |
| `read_file` | read source |
| `write_file` | edit source (staging only) |
| `run_tests` | project pytest via repo_oracle |
| `done` | terminate |

- One JSON tool call per step
- Staging copy — never live tree
- Path blocks: `.git`, `.venv`, `memory`, parent `..`
- Injectible `decide_fn` for tests without a model

## Slice 2 — LLM decide_fn bridge (CLOSED)

`make_llm_decide_fn(call_fn=None)`:

- Injectible `call_fn(messages) -> str` for tests / offline
- Default routes through Rose Quartz (Ollama primary, low temperature)
- Always `parse_action` — fail closed on unparseable output

```python
from core.tool_runtime import ToolRuntime, make_llm_decide_fn

decide = make_llm_decide_fn()  # live model
# or
decide = make_llm_decide_fn(call_fn=my_mock)

rt = ToolRuntime(fixture_root=Path("fixtures/repo_oracle_toy"), decide_fn=decide)
result = rt.run("fix greeter so project tests pass")
```

## Not yet

- Pipeline wiring (`ether run` path)
- Shell / arbitrary subprocess
- Curriculum / bandit / flywheel re-enable

## Tests

`tests/test_tool_runtime.py` — scripted + mock-LLM decide_fn fixes greeter/wallet.

## Next

Slice 3: wire into pipeline behind `ETHER_TOOL_RUNTIME=1` for repo-edit objectives.
Measure against Phase B fixtures before touching learning stack.
