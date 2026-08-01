# Phase B — Repo oracle

## Goal

Score agent edits with **the repository's own tests**, not only holdout asserts.
This is the honest scoreboard for the self-improving hypothesis.

## Status

| Slice | Content | Status |
|-------|---------|--------|
| 1 | `core/repo_oracle.py`, greeter fixture, unit tests, `ether repo-score` | **CLOSED** (host-verified 2026-07-31) |
| 2 | Wire oracle into pipeline repair path | **CLOSED** (host-verified 2026-07-31, `dba09ff`) |
| 3 | Expand task set + gate e2e (no LLM) | **CLOSED** (2026-07-31) |

## API

```python
from core.repo_oracle import score_repo_edit, score_from_marked_code, parse_file_markers

result = score_from_marked_code(
    code,                          # contains `# file: path` markers
    fixture_root=Path("fixtures/repo_oracle_toy"),
    test_args=["tests"],
    timeout=60,
)
# result["ok"], result["score"] in [0,1], result["oracle"] == "project_pytest"
```

## Pipeline integration (slice 2)

When `ETHER_REPO_ORACLE=1` (or `ETHER_REPO_ORACLE_FIXTURE` is set):

1. After Clear Quartz sandbox reports `exit_code == 0`, `apply_repo_oracle_gate` runs.
2. Generated code is applied into a **temp staging** copy of the fixture.
3. Project pytest is executed. Failure sets `repo_oracle_ok=False`, forces `ok=False`, sets `fail_kind="repo_oracle"`, and continues the repair/retry loop.
4. Final status becomes `"error"` if `repo_oracle_ok is False`, even when sandbox exit was 0.

Env vars (see `.env.example`):

- `ETHER_REPO_ORACLE=1` — master enable
- `ETHER_REPO_ORACLE_FIXTURE=fixtures/repo_oracle_toy` (or `fixtures/repo_oracle_wallet`)
- `ETHER_REPO_ORACLE_TEST_ARGS=tests`
- `ETHER_REPO_ORACLE_TIMEOUT=60`
- `ETHER_REPO_ORACLE_AS_PATH=greeter.py` (or `wallet.py`)

## Safety

- Default path uses a **temp staging** copy of the fixture — never the live tree.
- Blocked: `.git`, `.venv`, `memory`, parent `..`, secret-ish filenames.
- Pytest is timeout-bounded.
- Hook never raises into the pipeline (returns safe error dict).

## Task set (fixtures)

| Fixture | Path | Bug class | Baseline score |
|---------|------|-----------|----------------|
| greeter | `fixtures/repo_oracle_toy/` | pure function format string | 0.0 |
| wallet | `fixtures/repo_oracle_wallet/` | class state (deposit overwrite + missing insufficient check) | ~0.6 |

Both: fixed code → `ok=True score=1.0`.

## CLI

```bash
ether repo-score --fixture fixtures/repo_oracle_toy --code-file fixed.py
ether repo-score --fixture fixtures/repo_oracle_wallet --as-path wallet.py --code-file fixed_wallet.py
```

## Gate e2e (no LLM)

`tests/test_repo_oracle_gate.py` exercises `apply_repo_oracle_gate` on both fixtures:
- disabled → inactive
- broken → `fail_kind=repo_oracle`, `repo_oracle_ok=False`
- fixed → `ok=True score=1.0`

## Next

Phase C: tool-first agent runtime (Observe → tool act → Observe).
Phase E only after honest repo-suite metrics exist.
