# ADR 0004: Day-3 GitHub-hosted PR CI, Audit-Pack Activation + Dataset Policy (ETHER roadmap, day 3 of 5)

## Status

Accepted — Day 3 of 5 of the security hardening roadmap. Closes audit anchors
**MEAS-003** (no PR CI — only the self-hosted `autonomy-host.yml` existed),
**MEAS-004** (published ablation rows lacked raw-data provenance) and **A-8**
(tracked eval data under the gitignored `memory/` violated the runtime-state
boundary).

## Context

- The audit pack (`ether-audit-pack/`) was the *designed* CI: its
  `ci/audit-gates.yml` implements the P2 §3 DAG
  `lint → (audit-rules ∥ contracts) → pytest → gate`. Day 3 activates it
  in-repo rather than hand-rolling a separate `pr.yml`.
- The seeded findings baseline (`208993a`) predated Days 1–2, so SEC-001…005,
  SEC-008 and MEAS-005 findings already fixed showed as stale-open, and the
  budget registers (790/188) no longer matched audited-repo reality.
- The four `memory/quizzes/*.json` eval files and
  `memory/datasets/mbpp_lite.json` were tracked in git even though `memory/`
  is gitignored runtime state; fresh clones shipped hidden quizzes.

## Decisions

1. **Pack-as-CI adoption.** The pack's workflow, audit engine
   (`tools/audit/`), rules register (`config/audit-rules.yaml`),
   import-linter config, contract tests (`tests/test_audit_contracts.py`,
   8 tests joining the pytest suite), pre-commit config and dashboard panel
   (`dashboard/static/audit_panel.html`) are installed per the pack README,
   with the Day-3 adaptations below. SHA-pinned actions, the `lint` DAG root
   and the `gate` job are unchanged.
2. **Ruff warn-mode + deferred ruff-ether.toml merge.** Both ruff steps carry
   `continue-on-error: true`: the repo carries 6 pre-existing F401 in `core/`
   plus pre-existing format drift at `819bc92`; the audit engine is the
   blocking gate until the ruff baseline burns down (same philosophy as the
   mypy step). **Deviation from the pack README:** `config/ruff-ether.toml` is
   deliberately NOT merged into `pyproject.toml` — its expanded select
   (UP/B/SIM/PL) would produce hundreds of findings and drown the signal.
   The merge + burn-down is a residual (below).
3. **Pytest matrix + shadow gate.** The single pytest job became a 2×2 matrix
   (python 3.11/3.12 × `ETHER_LOOP_RUNNER` 0/1), `timeout-minutes: 30`, a
   `scripts/shadow_runner.py --selftest` step, and a plain
   `pytest -q --tb=short` — no `--timeout` (pytest-timeout is not a
   dependency) and no `-x`: the floor is the full suite.
4. **Baseline reseed = the human-PR act of this series.** This patch series
   IS the human PR authorized to move the baseline; the flywheel bot never
   merges baseline bumps, and the CI regression_tracker step runs WITHOUT
   `--update-baseline` (**D-01 preserved**). Reseed procedure:
   `regression_tracker --violations <full-run.jsonl> --commit 819bc92
   --update-baseline`. Findings resolved by Days 1–2 (SEC-001/002/003/004/
   005/008, MEAS-005 et al.) were promoted `fixed` with
   `fixed_commit=819bc92`, so reappearance classifies as TRUE_REGRESSION and
   fails the P3 gate. Only genuinely-absent sites were promoted: the tracker
   initially marked 81 entries by a QUAL-002 pattern fingerprint shared
   across ~100 sites; the 64 still-present sites were reverted to open.
5. **Budget ratchets, kept in sync in both registers**
   (`config/audit-rules.yaml` + `tools/audit/findings_baseline.json`):
   - `pipeline_run_lines` 790 → **710** (ARCH-003 is a may-only-lower
     ratchet). Note: the rule measures `Pipeline.run` at 718 lines at
     `819bc92` (def line to `end_lineno`) — the SPEC premise of "702
     post-stage-1" did not match the rule's measurement — so the 718 site is
     baselined open under the new 710 budget; any growth changes the
     fingerprint and blocks, a refactor below 710 resolves it.
   - `env_getenv_sites` 188 → **191** (post-Day-2 reality; the +3 are the two
     `ETHER_BATCH_COMMANDS` gates + the stage-1 loop flag — ADRs 0001/0002).
6. **Pack self-scan grandfathered.** `tools/audit/` is the auditor, not the
   audited, but no global/per-rule exclusion mechanism exists
   (`exclude_files` is honored only by QUAL-002), so the pack's own findings
   (QUAL-003 `audit_runner.py` FP — `run(` there is the runner's own
   function; QUAL-005 getenv sites incl. the count 200 vs the 191
   audited-repo budget; QUAL-006 the fence-stripper detection pattern
   matching itself) are baselined with the note "pack self-scan
   grandfathered at activation (Day-3)" instead of excluded.
7. **Dataset policy (A-8).** The four `memory/quizzes/*.json` files and
   `memory/datasets/mbpp_lite.json` are untracked (`git rm --cached`; files
   stay on disk). `scripts/fetch_datasets.py` regenerates `mbpp_lite.json`
   deterministically from embedded canonical bytes (provenance: lite subset
   derived from MBPP; embedded so fresh clones reproduce offline) with a
   `--check` drift/missing mode. Fresh-clone consumers degrade gracefully
   (`dataset_quiz.py`, `compare_run.py`, `compare_runners.py` print a
   one-line "run scripts/fetch_datasets.py" and exit 2;
   `tests/test_bench_integrity.py` skips rather than auditing vacuously).
   SEC-007's shrink-only tracked whitelist was pruned to match.
8. **`memory/batch_queue.json` stays tracked** — deliberate exception: it is
   the seeded smoke queue (3 pipeline items, no eval data) and part of the
   fresh-clone out-of-box experience. (`memory/__init__.py`,
   `memory/curriculum/*` and the `.gitkeep` files were already tracked
   runtime scaffolding, not eval data; untracking them was out of scope for
   A-8.)
9. **Raw-rows policy (MEAS-004).** `docs/results/README.md` records the
   provenance: `ablation_qwen2.5-3b.json` = raw rows of the contaminated run
   (kept, retracted numbers stay on the record), `ablation_qwen2.5-3b_clean.json`
   = the leak-guarded re-run behind the published numbers; published numbers
   MUST ship raw rows alongside going forward.

## Consequences

- PR CI runs on free GitHub runners: 4-job pytest matrix ≈ 4×~7 min parallel,
  plus lint/audit-rules/contracts/gate.
- Fresh clones no longer carry the quizzes or mbpp_lite — the
  `dataset_quiz` / `compare_run*` flows need `scripts/fetch_datasets.py`
  (dataset) or local copies (quizzes); consumers degrade with a one-line
  pointer instead of `FileNotFoundError`.
- The pre-commit config is installed but opt-in (developers run
  `pre-commit install`); CI does not depend on it.
- Contract tests join the pytest suite: 8 tests (3 pass / 5 XPASS under
  `xfail(strict=False)` at `819bc92`); total suite = 842 + 8 + 5 day3 tests.

## Residuals / follow-ups

- **Ruff full-select burn-down**: merge `config/ruff-ether.toml` into
  `pyproject.toml` incrementally (rule family per PR), then drop the
  `continue-on-error` warn-mode from both ruff steps.
- **Posture test**: `test_posture_is_quiet_when_everything_is_off` is red on
  dockerless dev machines but expected green on ubuntu-latest where docker
  exists. If the first CI run proves otherwise, the follow-up is a
  docker-presence-aware skip — deliberately NOT pre-empted.
- **Pack self-scan**: per decision 6, the pack's own findings are baselined;
  a future runner-level `exclude_paths` mechanism would let `tools/audit/`
  drop out of scope instead.
- **import-linter**: `config/importlinter.ini` is installed but not yet wired
  into CI — follow-up.
