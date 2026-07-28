"""Ensure project root is importable even if pytest is invoked without -e install."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# Module-level state paths that tests would otherwise write to for real.
# (module path, attribute name, "file" | "dir")
_STATE_TARGETS = [
    ("core.learning", "BANDIT_PATH", "file"),
    ("core.learning", "EXP_PATH", "file"),
    ("core.experience", "VAULT_DIR", "dir"),
    ("core.experience", "PASS_PATH", "file"),
    ("core.experience", "FAIL_PATH", "file"),
    ("core.fail_streak", "STATE_PATH", "file"),
    # sample_objective() -> sync_from_vault() writes here, so a test run was
    # promoting the REAL curriculum tier (observed 0 -> 3) off mock outcomes.
    ("core.curriculum", "STATE_PATH", "file"),
    ("core.curriculum", "PASS_PATH", "file"),
    ("core.curriculum", "FAIL_PATH", "file"),
    # Any test reaching core.repair.repair_prompt writes here, so the live
    # failure graph was accumulating nodes from mock stderr.
    ("core.failure_graph", "GRAPH_PATH", "file"),
    ("core.bench_guardian", "GUARD_PATH", "file"),
    ("gems.grandidierite.fabricate", "QUARANTINE", "dir"),
    ("gems.grandidierite.fabricate", "FABRICATE_LOG", "file"),
    # Mock pipeline runs were landing in the real history: 54 of 88 records
    # were test artifacts ("plan boom" / "ollama down"), which then fed the
    # dashboard's success rate and verified-fraction metrics.
    ("core.pipeline", "RUNS_DIR", "dir"),
]


@pytest.fixture(autouse=True)
def _deterministic_rng():
    """Seed the RNG so probabilistic tests cannot fail intermittently.

    The bandit samples when it selects, so tests asserting "this context picks
    that arm" were failing roughly 1 run in 4. That is worse than a plain bug:
    the flywheel runs `pytest` as a static gate every cycle, so a flaky test
    randomly takes a machine out of the loop with a failure that does not
    reproduce — exactly the kind of noise that trains people to ignore red.
    """
    import random

    state = random.getstate()
    random.seed(20260727)
    try:
        yield
    finally:
        random.setstate(state)


@pytest.fixture(autouse=True)
def isolate_persistent_state(monkeypatch, tmp_path):
    """Redirect the learning/experience/tool stores into a temp dir.

    Without this, `pytest -q` mutates production state: it wrote fake rewards
    into `memory/learning/bandit.json` (the live contextual bandit that picks
    generation strategies) and appended mock pipeline output to
    `memory/experience/pass.jsonl`, which is re-injected into real prompts as
    few-shot "success examples". The test suite was training the system.

    Verified before this fixture existed: a single `pytest -q` changed
    bandit.json and grew pass.jsonl by 305 bytes.
    """
    import importlib
    import shutil

    # Rooted under memory/ (gitignored) rather than /tmp, because some code
    # legitimately computes paths relative to ROOT and rejects anything
    # outside the repo.
    sandbox_root = ROOT / "memory" / "_pytest" / tmp_path.name
    sandbox_root.mkdir(parents=True, exist_ok=True)

    # save_success_pattern / few_shot_pack run as SUBPROCESSES, so patching a
    # module attribute cannot reach them — they take the path from the
    # environment. few_shot_pack replays this store into real prompts, and 84
    # of its 101 rows were "write hello" test artifacts being served to the
    # model as worked examples.
    monkeypatch.setenv(
        "ETHER_SUCCESS_PATTERNS_PATH", str(sandbox_root / "success_patterns.jsonl")
    )

    for module_name, attr, kind in _STATE_TARGETS:
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        if not hasattr(module, attr):
            continue
        target = sandbox_root / module_name.replace(".", "_") / attr.lower()
        if kind == "dir":
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(module, attr, target, raising=False)

    try:
        yield
    finally:
        shutil.rmtree(sandbox_root, ignore_errors=True)
