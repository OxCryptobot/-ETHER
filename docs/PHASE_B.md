# Phase B — Repo oracle

## Goal

Score agent edits with **the repository's own tests**, not only holdout asserts.
This is the honest scoreboard for the self-improving hypothesis.

## API

```python
from core.repo_oracle import score_repo_edit, score_from_marked_code, parse_file_markers

# Multi-file model output
result = score_from_marked_code(
    code,                          # contains `# file: path` markers
    fixture_root=Path("fixtures/repo_oracle_toy"),
    test_args=["tests"],
    timeout=60,
)
# result["ok"], result["score"] in [0,1], result["oracle"] == "project_pytest"
```

## Safety

- Default path uses a **temp staging** copy of the fixture — never the live tree.
- Blocked: `.git`, `.venv`, `memory`, parent `..`, secret-ish filenames.
- Pytest is timeout-bounded.

## Toy fixture

`fixtures/repo_oracle_toy/` ships a deliberate bug (`greeter.py` missing comma).
Project tests under `tests/` fail until the agent (or a human) writes the fix.

## CLI

```bash
ether repo-score --fixture fixtures/repo_oracle_toy --code-file fixed.py
# or pipe marked multi-file source:
ether repo-score --fixture fixtures/repo_oracle_toy --markers-file out.txt
```

## Not in this slice

- Live `git apply` onto main (use tools/persistent/apply_patch only under explicit operator control)
- Full tool-first agent loop (Phase C)
- Curriculum/bandit rewire (Phase E — needs this oracle first)
