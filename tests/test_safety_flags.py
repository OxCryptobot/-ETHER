"""Every safety flag must actually gate the action it names.

Three flags were found today that did not control what their name implied:

  * ETHER_AUTO_PROMOTE — `tool_reconcile.reconcile()` copied quarantined tools
    into the trusted directory with no gate at all, on a daemon timer.
  * ETHER_FLYWHEEL_PUSH — the daemon launchers called `os.environ.setdefault`
    BEFORE loading .env, so an explicit 0 was ignored; and separately
    `run_smart_cycle.py` passed a hardcoded `do_push=True` into a
    `do_push or env` expression, which no env value can suppress. A cycle run
    with ETHER_FLYWHEEL_PUSH=0 pushed to the shared remote.
  * ETHER_AUTO_MODEL — a read-only dashboard probe overwrote an explicitly
    configured ETHER_PRIMARY_MODEL.

An operator has to be able to trust these. Each test drives the flag to its
safe value and asserts the dangerous action is refused.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _safe_defaults(monkeypatch):
    for flag in (
        "ETHER_FLYWHEEL_PUSH",
        "ETHER_GIT_RESET_OK",
        "ETHER_AUTO_PROMOTE",
        "ETHER_PATCH_LOOP",
        "ETHER_BURST",
        "ETHER_AUTO_FABRICATE_ON_FAIL",
        "ETHER_AUTO_ENQUEUE",
        "ETHER_AUTO_MODEL",
    ):
        monkeypatch.setenv(flag, "0")


def test_patch_loop_off_blocks_host_writes():
    """ETHER_PATCH_LOOP=0 must stop `git apply` against the working tree."""
    from core.patch_loop import maybe_patch_cycle

    diff = "--- a/memory/scratch/x.py\n+++ b/memory/scratch/x.py\n"
    report, _code = maybe_patch_cycle(diff)
    assert report is None, "patch loop ran with ETHER_PATCH_LOOP=0"


def test_auto_promote_off_blocks_tool_promotion(tmp_path):
    """ETHER_AUTO_PROMOTE=0 must stop quarantine -> trusted promotion."""
    from core.tool_reconcile import _promotion_gate

    tool = tmp_path / "t.py"
    tool.write_text("def main():\n    return 1\n", encoding="utf-8")
    gate = _promotion_gate(tool)
    assert gate["ok"] is False
    assert "ETHER_AUTO_PROMOTE" in gate["reason"]


def test_burst_off_blocks_sending_code_off_box():
    """ETHER_BURST=0 must stop cloud burst, including on retries."""
    from core.burst_policy import should_force_burst

    assert should_force_burst(attempt=2) is False
    assert should_force_burst(attempt=1) is False


def test_auto_fabricate_off_blocks_self_extension():
    from core.fail_streak import maybe_propose_fabricate

    assert maybe_propose_fabricate() is None


def test_auto_enqueue_off_blocks_requeue():
    from core.autonomy import enqueue_failure

    assert enqueue_failure(objective="x", fail_kind="runtime", task_id="t1") is None


def test_auto_model_off_preserves_explicit_model(monkeypatch):
    """A status probe must not repoint code generation at another model."""
    from core.model_select import select_primary_model

    monkeypatch.setenv("ETHER_PRIMARY_MODEL", "qwen3.6:35b-a3b-q8_0")
    select_primary_model()
    import os

    assert os.environ["ETHER_PRIMARY_MODEL"] == "qwen3.6:35b-a3b-q8_0"


def test_flywheel_push_off_cannot_be_overridden_by_a_hardcoded_argument():
    """The regression that pushed to shared main despite the flag being 0.

    `flywheel.cycle` computes `want_push = do_push or env == "1"`, so any
    caller passing a hardcoded True makes the flag inert. Callers must derive
    do_push from the environment.
    """
    import inspect
    import re

    import scripts.run_smart_cycle as rsc

    source = inspect.getsource(rsc)
    assert not re.search(r"do_push\s*=\s*True", source), (
        "run_smart_cycle passes a hardcoded do_push=True, which makes "
        "ETHER_FLYWHEEL_PUSH unable to suppress a push to the shared remote"
    )
    assert "ETHER_FLYWHEEL_PUSH" in source


def test_env_file_wins_over_launcher_defaults():
    """Launchers must load .env BEFORE os.environ.setdefault().

    core/dotenv.py never overrides an already-set variable, so a launcher that
    calls setdefault first silently ignores the operator's explicit choice.
    """
    import inspect

    for module_name in (
        "scripts.ether_daemon",
        "scripts.run_smart_cycle",
        "scripts.desktop_runtime",
    ):
        module = __import__(module_name, fromlist=["*"])
        source = inspect.getsource(module)
        load_at = source.find("load_dotenv(")
        setdefault_at = source.find("os.environ.setdefault")
        if setdefault_at == -1:
            continue
        assert load_at != -1 and load_at < setdefault_at, (
            f"{module_name} calls os.environ.setdefault before load_dotenv, so "
            f".env cannot override its defaults"
        )


def test_warm_sandbox_is_off_by_default():
    """It shares /tmp across programs, which let one run alter another's verdict."""
    import os

    from gems.clear_quartz.warm import warm_enabled

    os.environ.pop("ETHER_WARM_SANDBOX", None)
    assert warm_enabled() is False


def test_warm_sandbox_is_hardened_if_enabled():
    """If someone does turn it on, the code-execution paths must stay closed.

    A long-lived container shares /tmp, and a program was verified planting
    sitecustomize.py into the HOME-derived user-site directory where a later,
    unrelated program executed it. `-I` disables user site-packages and a
    per-run HOME stops anything being pre-planted.
    """
    import inspect

    from gems.clear_quartz import warm

    source = inspect.getsource(warm.run_in_warm)
    assert '"-I"' in source, "warm exec must use python -I (no user site-packages)"
    assert "HOME=" in source, "warm exec must set a per-run HOME"

    create = inspect.getsource(warm.ensure_warm)
    for flag in ("--read-only", "--cap-drop", "--user", "--pids-limit", "no-new-privileges"):
        assert flag in create, f"warm container missing {flag}"


def test_sandbox_docker_backend_does_not_degrade_to_host(monkeypatch):
    """An explicit docker backend is a security choice, not a preference."""
    monkeypatch.setenv("ETHER_SANDBOX_BACKEND", "docker")
    monkeypatch.setattr("dashboard.collector.shutil.which", lambda _n: None)
    from dashboard.collector import _sandbox_info

    info = _sandbox_info()
    assert info["isolated"] is False
    assert "fallback" not in info["effective"]
