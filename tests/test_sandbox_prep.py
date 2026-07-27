"""Code-prep must not manufacture passes, and infrastructure is not a failure.

Every defect covered here was verified by executing real code through the
sandbox, not by inspecting the generated text:

  * a harness that swallowed the callee's exception, so code that crashed on
    every call exited 0 and scored `execution_score 1.0`
  * class-only, `_private`-only and `async def` solutions that were never
    called at all (they got a bare `print('ok')`)
  * substring tests over raw source, so `# TODO: assert the invariant` in a
    comment suppressed synthesis and the harness entirely
  * an objective hardcoded to "" at the sandbox call site, which disabled the
    only branch of test_synth that produces a falsifiable assertion
  * a Docker daemon outage scored as the program's own non-zero exit
  * held-out grading routed through code prep, which rewrote the artifact
    under test and wrote files to the host
"""

from __future__ import annotations

import subprocess
from uuid import uuid4

import pytest

from core.assert_harness import NO_CALLABLE_MARKER, ensure_harness, has_self_check
from core.confidence import compute_scores
from core.holdout import grade_against_holdout
from core.pipeline_hooks import no_code_prep, prepare_code_for_sandbox
from core.schemas import ClearQuartzRequest, Envelope, GemErrorType
from core.test_synth import has_assert, synthesize_asserts
from gems.clear_quartz.sandbox import (
    ClearQuartz,
    DockerUnavailable,
    RawCodeRequest,
    docker_failure_reason,
)


def run_in_sandbox(code: str, objective: str = ""):
    """Execute `code` the way the pipeline does, prep included."""
    response = ClearQuartz().execute(
        Envelope(
            task_id=uuid4(),
            target_gem="clear-quartz",
            payload=ClearQuartzRequest(code=code, objective=objective),
            timeout_seconds=60,
        )
    )
    assert response.error is None, response.error
    assert response.payload is not None
    return response.payload


# --------------------------------------------------------------------------
# 1. A crash must exit non-zero.
# --------------------------------------------------------------------------

CRASHERS = {
    "function_with_args": "def solve(n):\n    raise ValueError('boom')\n",
    "function_no_args": "def solve():\n    raise RuntimeError('boom')\n",
    "class_only": "class Solution:\n    def solve(self, n):\n        raise ValueError('boom')\n",
    "private_only": "def _solve(n):\n    raise ValueError('boom')\n",
    "async_only": "async def solve(n):\n    raise ValueError('boom')\n",
    "crash_with_assert_comment": (
        "def solve(n):\n    # TODO: assert the invariant\n    raise ValueError('boom')\n"
    ),
}


@pytest.mark.parametrize("code", CRASHERS.values(), ids=list(CRASHERS))
def test_code_that_always_crashes_exits_non_zero(code):
    """Previously every one of these exited 0 with execution_score 1.0."""
    payload = run_in_sandbox(code)
    assert payload.exit_code != 0, payload.stdout
    assert compute_scores(payload)["execution_score"] <= 0.2


WORKING = {
    "class_only": "class Solution:\n    def double(self, n):\n        return n * 2\n",
    "private_only": "def _double(n):\n    return n * 2\n",
    "async_only": "async def double(n):\n    return n * 2\n",
}


@pytest.mark.parametrize("code", WORKING.values(), ids=list(WORKING))
def test_working_code_is_actually_called(code):
    """`print('ok')` proved nothing; the callable must really be invoked."""
    payload = run_in_sandbox(code)
    assert payload.exit_code == 0, payload.stderr
    assert "4" in (payload.stdout or ""), payload.stdout
    assert NO_CALLABLE_MARKER not in (payload.stdout or "")


WORKING_SHAPES = {
    "annotated_list": "def total(values: list[int]) -> int:\n    return sum(values)\n",
    "two_dicts": "def merge(a, b):\n    return {**a, **b}\n",
    "list_of_dicts": "def names(rows):\n    return [r['name'] for r in rows]\n",
    "helper_plus_entry": "def render(tree):\n    return tree.value\n\ndef main():\n    return 42\n",
    "ctor_args": (
        "class Stack:\n    def __init__(self, items):\n        self.items = list(items)\n"
        "    def push(self, v):\n        self.items.append(v)\n        return self.items\n"
    ),
    "defaults_only": "def greet(name='world'):\n    return f'hi {name}'\n",
}


@pytest.mark.parametrize("code", WORKING_SHAPES.values(), ids=list(WORKING_SHAPES))
def test_correct_code_is_not_failed_by_argument_guessing(code):
    """Making crashes fatal must not turn ordinary solutions into failures."""
    payload = run_in_sandbox(code)
    assert payload.exit_code == 0, payload.stderr


def test_uncallable_code_is_marked_rather_than_judged():
    """A function needing a domain object is neither proven good nor broken."""
    payload = run_in_sandbox("def area(shape):\n    return shape.width * shape.height\n")
    assert payload.exit_code == 0
    assert "__ETHER_UNCALLABLE__" in (payload.stdout or "")


def test_no_callable_is_reported_distinguishably():
    payload = run_in_sandbox("x = 1 + 1\n")
    assert payload.exit_code == 0
    assert NO_CALLABLE_MARKER in (payload.stdout or "")


def test_harness_is_not_appended_when_code_already_runs_itself():
    code = "def f():\n    return 1\n\nprint(f())\n"
    out, modified = ensure_harness(code)
    assert modified is False
    assert out == code


# --------------------------------------------------------------------------
# 2/3. Comments and docstrings are not self-checks.
# --------------------------------------------------------------------------


def test_comment_mentioning_assert_does_not_count_as_a_self_check():
    assert has_self_check("def f(x):\n    # TODO: assert the invariant\n    return x\n") is False
    assert has_assert("# TODO: assert the invariant\n") is False


def test_docstring_mentioning_print_does_not_count_as_a_self_check():
    code = 'def f(x):\n    """Call print( ) on the result."""\n    return x\n'
    assert has_self_check(code) is False


def test_real_assert_still_counts():
    assert has_self_check("def f(x):\n    return x\nassert f(1) == 1\n") is True
    assert has_assert("def f(x):\n    return x\nassert f(1) == 1\n") is True


def test_synthesis_is_not_suppressed_by_a_comment():
    code = "def add(a, b):\n    # assert something later\n    return a + b\n"
    _, modified = synthesize_asserts(code, objective="add(2, 3) == 5")
    assert modified is True


def test_swallowed_assert_does_not_count_as_verification():
    code = "def f(x):\n    return x\ntry:\n    assert f(1) == 2\nexcept Exception:\n    pass\n"
    assert has_assert(code) is False


# --------------------------------------------------------------------------
# 4. The objective reaches test_synth.
# --------------------------------------------------------------------------

RIGHT_ADD = "def add(a, b):\n    return a + b\n"
WRONG_ADD = "def add(a, b):\n    return a * b\n"
ADD_OBJECTIVE = "Write add(a, b). For example add(2, 3) == 5."


def test_objective_derived_assertion_fails_wrong_code():
    payload = run_in_sandbox(WRONG_ADD, objective=ADD_OBJECTIVE)
    assert payload.exit_code != 0
    assert payload.total_tests >= 1
    assert payload.tests_passed == 0


def test_objective_derived_assertion_passes_correct_code():
    payload = run_in_sandbox(RIGHT_ADD, objective=ADD_OBJECTIVE)
    assert payload.exit_code == 0, payload.stderr
    assert payload.total_tests >= 1
    assert payload.tests_passed == payload.total_tests


def test_without_the_objective_the_same_wrong_code_is_unverified():
    """Documents what the empty objective cost: no falsifiable assertion."""
    payload = run_in_sandbox(WRONG_ADD)
    assert payload.total_tests == 0


def test_objective_with_a_non_literal_expectation_is_ignored():
    """A half-parsed expectation would turn correct code into a SyntaxError."""
    payload = run_in_sandbox(RIGHT_ADD, objective="add(2, 3) == the sum of both")
    assert payload.exit_code == 0, payload.stderr
    assert "SyntaxError" not in (payload.stderr or "")


def test_boolean_named_function_still_uses_the_objective():
    """The is_/has_/can_ heuristics used to shadow the objective branch."""
    out, modified = synthesize_asserts(
        "def is_ready(n):\n    return n > 0\n", objective="is_ready(5) is True"
    )
    assert modified is True
    assert "assert is_ready(5) is True" in out


# --------------------------------------------------------------------------
# 5. Docker outages are dependency errors, not program failures.
# --------------------------------------------------------------------------


def _completed(returncode: int, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(args=["docker"], returncode=returncode, stdout=stdout, stderr=stderr)


DAEMON_DOWN = (
    "docker: Cannot connect to the Docker daemon at unix:///var/run/docker.sock. "
    "Is the docker daemon running?"
)


@pytest.mark.parametrize(
    "result",
    [
        _completed(1, stderr=DAEMON_DOWN),
        _completed(125, stderr=DAEMON_DOWN),
        _completed(125, stderr="docker: Error response from daemon: no such image"),
        _completed(127, stderr="docker: failed to connect to the docker API"),
        _completed(125),
    ],
    ids=["exit1_daemon", "exit125_daemon", "exit125_image", "exit127_api", "exit125_silent"],
)
def test_docker_level_failures_are_detected(result):
    assert docker_failure_reason(result) is not None


@pytest.mark.parametrize(
    "result",
    [
        _completed(0, stdout="4\n"),
        _completed(1, stderr="Traceback (most recent call last):\nValueError: boom\n"),
        _completed(1, stderr="AssertionError"),
        _completed(127, stdout="done\n", stderr="my program said 127"),
        _completed(1, stderr="failed to connect to 10.0.0.1: Network is unreachable"),
    ],
    ids=["ok", "traceback", "assertion", "program_exit_127", "program_network_error"],
)
def test_program_failures_are_not_mistaken_for_docker_failures(result):
    assert docker_failure_reason(result) is None


def test_daemon_outage_returns_a_dependency_error_not_a_result(monkeypatch):
    """A dead daemon used to be scored as the artifact's own non-zero exit."""
    monkeypatch.setenv("ETHER_SANDBOX_BACKEND", "docker")
    monkeypatch.setattr(
        ClearQuartz,
        "_run_docker",
        lambda self, code, timeout: (_ for _ in ()).throw(DockerUnavailable("daemon down")),
    )
    response = ClearQuartz().execute(
        Envelope(
            task_id=uuid4(),
            target_gem="clear-quartz",
            payload=ClearQuartzRequest(code=RIGHT_ADD),
            timeout_seconds=30,
        )
    )
    assert response.payload is None
    assert response.error is not None
    assert response.error.type is GemErrorType.DEPENDENCY
    assert response.error.recoverable is True


def test_docker_runner_raises_on_daemon_outage(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _completed(1, stderr=DAEMON_DOWN))
    with pytest.raises(DockerUnavailable):
        ClearQuartz()._run_docker("print(1)", 10)


# --------------------------------------------------------------------------
# 6. Held-out grading bypasses code prep entirely.
# --------------------------------------------------------------------------

HOLDOUT = "assert is_even(4) is True\nassert is_even(5) is False\n"
IS_EVEN = "def is_even(n):\n    return n % 2 == 0\n"


@pytest.fixture()
def scratch(monkeypatch, tmp_path):
    """Point the multifile writer at a temp dir so a leak is observable."""
    import core.multifile

    target = tmp_path / "scratch"
    monkeypatch.setattr(core.multifile, "SCRATCH", target)
    return target


def test_grading_does_not_write_to_the_host(scratch):
    code = "# file: main.py\n" + IS_EVEN
    result = grade_against_holdout(code, HOLDOUT)
    assert result["ok"] is True, result["reason"]
    assert not scratch.exists(), sorted(p.name for p in scratch.iterdir())


def test_grading_runs_the_code_it_was_given(scratch):
    """With two `# file:` markers the holdout landed in a non-entry file."""
    code = (
        "# file: helper.py\ndef is_even(n):\n    return False\n\n"
        "# file: main.py\nprint('hello')\n"
    )
    result = grade_against_holdout(code, HOLDOUT)
    assert result["ok"] is False
    assert "AssertionError" in result["stderr"]
    assert not scratch.exists()


def test_grading_does_not_synthesize_or_harness(scratch):
    """A crashing implementation must fail on the holdout, not on a harness call."""
    result = grade_against_holdout("def is_even(n):\n    raise ValueError('boom')\n", HOLDOUT)
    assert result["ok"] is False
    assert "ValueError" in result["stderr"]


def test_raw_request_skips_prep():
    payload = ClearQuartz().execute(
        Envelope(
            task_id=uuid4(),
            target_gem="clear-quartz",
            payload=RawCodeRequest(code=WRONG_ADD),
            timeout_seconds=60,
        )
    ).payload
    assert payload is not None
    assert payload.exit_code == 0
    assert (payload.stdout or "").strip() == ""  # nothing was appended or called


def test_no_code_prep_context_is_a_passthrough(scratch):
    code = "# file: main.py\ndef f():\n    return 1\n"
    with no_code_prep():
        out, meta = prepare_code_for_sandbox(code, objective="refactor into a package")
    assert out == code
    assert meta.get("bypassed") is True

    # ... and outside the context the same input is still prepared.
    prepared, meta = prepare_code_for_sandbox(code, objective="")
    assert prepared != code
    assert meta.get("bypassed") is not True
