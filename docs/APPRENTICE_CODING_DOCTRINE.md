# Apprentice Coding Doctrine

**Audience:** ETHER (apprentice) + GEMS + ToolRuntime agents  
**Mentor contract:** Prefer measured truth over narrative. Prefer small green steps over large guesses.

---

## 1. The only reliable loop

```
Observe → Act (one tool) → Observe → … → done when tests pass
```

Never: write a wall of code, then hope.  
Always: `list_files` / `read_file` tests + source → smallest fix → `run_tests`.

If `run_tests` fails three times without score gain → **stop** (`no_progress`). Do not burn the budget.

---

## 2. Read before write

1. Read the **failing test** first (ground truth).
2. Read the **minimal source** under test.
3. Form one hypothesis.
4. Apply **one** surgical change (`apply_patch` preferred; `write_file` if new file).
5. Re-run tests.

Forbidden: rewriting whole files when one function is wrong.

---

## 3. AST gate is law

- Never write Python that does not parse.
- Prefer `apply_patch` with exact unique `old` string.
- If patch matches 0 or >1 times → stop and re-read; do not force.

---

## 4. Tool surface discipline

| Tool | When |
|------|------|
| `list_files` | First step in unknown workspace |
| `read_file` | Before every non-trivial write |
| `grep` / `glob` | Locate symbols / files fast |
| `apply_patch` | Surgical edit (preferred) |
| `write_file` | New file or full legitimate rewrite |
| `pep8_review` | After structural green, before done |
| `run_tests` | After every meaningful edit |
| `rollback` | Last write was wrong |
| `done` | Tests pass OR honest give-up with reason |

---

## 5. Failure taxonomy (typed)

Use these names; do not invent free-text only:

- `timeout` — wall clock exhausted
- `budget_exhaust` / `max_steps` — step budget gone
- `no_progress` — tests failing without score gain
- `tool_runtime_failed_terminal` — tool path failed; do **not** fall back to generate
- `step_fail` — command non-zero

On typed failure: critique → smallest experiment → requeue. Never silent drop.

---

## 6. Quality bar (best-in-class local agent)

- **Tests are the oracle** — not the model’s confidence.
- **Scoreboards are truth** — not chat summaries.
- **One hypothesis per cycle** — Labradorite on FAIL.
- **Style after structure** — pep8_review does not replace failing tests.
- **Small pure functions** — easier to sandbox-score.
- **Named entrypoints** — `def solve(...)` / clear API, not script soup.
- **No eval/exec** — Black Tourmaline rejects; do not emit.
- **Asserts prove correctness** before user-facing delivery.

---

## 7. Collaboration with the mentor (Grok)

When blocked:

1. State the **measured** failure (`failure_type`, scoreboard path, last tool).
2. State the **smallest experiment** that would falsify your hypothesis.
3. Do not ask for a full rewrite of working green paths.

When green:

1. Leave scoreboard + trace on disk.
2. Do not “improve” a 5/5 path without a new hypothesis and a new scoreboard.

---

## 8. Hardware honesty

Primary model ≤4B on this host. Prefer tool-runtime scripted verification over long live generate. Live lift is optional signal; scripted lift is the Phase 1 reliability bar.

---

## 9. Schema pointer

Machine-readable twin: `core/coding_method.py` (`CodingMethod`, `STEP_ORDER`, `SYSTEM_RULES`).
