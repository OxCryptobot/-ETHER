"""The experience vault is replayed into prompts, so its contents matter.

Before this, `retrieve()` for almost any objective returned three copies of the
same trivial `write hello` stub as "success examples", plus three copies of
"ollama down" as "related failures to avoid" — i.e. the model was being shown
an infrastructure outage as a code pattern to avoid. 13 of 22 pass rows were
one duplicated stub and all 26 fail rows were outages.
"""

from __future__ import annotations

import pathlib

import pytest


@pytest.fixture
def vault(monkeypatch, tmp_path):
    import core.experience as ex

    monkeypatch.setenv("ETHER_EXPERIENCE", "1")
    monkeypatch.setattr(ex, "VAULT_DIR", tmp_path)
    monkeypatch.setattr(ex, "PASS_PATH", tmp_path / "pass.jsonl")
    monkeypatch.setattr(ex, "FAIL_PATH", tmp_path / "fail.jsonl")
    return ex


def _rows(path: pathlib.Path) -> int:
    return len(path.read_text().splitlines()) if path.exists() else 0


def test_identical_runs_are_deduplicated(vault):
    for _ in range(3):
        vault.record(objective="write hello", code="def h():\n    return 'hi'", success=True)
    assert _rows(vault.PASS_PATH) == 1


def test_same_objective_different_code_is_kept(vault):
    vault.record(objective="write hello", code="def h():\n    return 'hi'", success=True)
    vault.record(objective="write hello", code="def h():\n    return 'HI'", success=True)
    assert _rows(vault.PASS_PATH) == 2


@pytest.mark.parametrize(
    "stderr,fail_kind",
    [
        ("Cannot connect to the Docker daemon at unix:///var/run/docker.sock", "runtime"),
        ("ollama down", "code"),
        ("HTTPConnectionPool: Max retries exceeded", "runtime"),
        ("", "exception"),
        ("", "plan"),
        ("", "dependency"),
    ],
)
def test_infrastructure_outages_are_not_stored_as_code_failures(vault, stderr, fail_kind):
    vault.record(
        objective="x", code="y", success=False, stderr=stderr, fail_kind=fail_kind
    )
    assert _rows(vault.FAIL_PATH) == 0


def test_a_real_code_failure_is_still_recorded(vault):
    vault.record(
        objective="divide",
        code="def f():\n    return 1 / 0",
        success=False,
        stderr="ZeroDivisionError: division by zero",
        fail_kind="runtime",
    )
    assert _rows(vault.FAIL_PATH) == 1


def test_vault_is_bounded(vault):
    """It was appended to forever and fully re-read on every retrieval."""
    for i in range(60):
        vault.record(objective=f"task {i}", code=f"def f{i}():\n    return {i}", success=True)
    vault._rotate(vault.PASS_PATH, max_rows=25)
    assert _rows(vault.PASS_PATH) == 25
