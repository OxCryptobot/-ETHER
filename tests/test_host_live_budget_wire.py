"""Phase 1D host wiring — live_budget applied; FAST unchanged."""
from __future__ import annotations


def test_apply_to_job_clamps_live_only():
    from core.live_budget import apply_to_job, limits

    lim = limits()
    live = {
        "id": "x_live",
        "class": "live",
        "note": "pipeline live",
        "steps": [{"argv": ["a"], "timeout": 900}],
    }
    out = apply_to_job(live)
    assert out["steps"][0]["timeout"] <= lim["max_wall_s"]
    assert out["live_budget"]["max_wall_s"] == lim["max_wall_s"]

    fast = {
        "id": "x_fast",
        "class": "fast",
        "steps": [{"argv": ["b"], "timeout": 300}],
    }
    out_f = apply_to_job(fast)
    assert out_f["steps"][0]["timeout"] == 300
    assert "live_budget" not in out_f


def test_run_steps_respects_live_budget_cap(monkeypatch=None):
    """run_steps min() with live_budget.max_wall_s without executing real commands."""
    from scripts import host_agent as ha

    calls = []

    def fake_run(cmd, timeout=3600):
        calls.append(timeout)

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    ha.run = fake_run  # type: ignore
    job = {
        "id": "t",
        "class": "live",
        "live_budget": {"max_wall_s": 90, "max_steps": 12, "step_timeout_s": 25},
        "steps": [{"argv": [".venv/Scripts/python.exe", "-c", "print(1)"], "timeout": 900}],
    }
    rc, ft = ha.run_steps(job["steps"], job=job)
    assert rc == 0
    assert ft is None
    assert calls and calls[0] <= 90
