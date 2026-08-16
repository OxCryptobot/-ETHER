"""Timeout retirement + pure oracle slice."""
from __future__ import annotations


def test_timeout_retirement_runs():
    from core.timeout_retirement import compute

    out = compute()
    assert "actions" in out
    assert "target_rate" in out
    assert out["target_rate"] == 0.25
    assert out.get("path")
    # Under current data, rate is usually high → keep_wheels_on expected
    assert isinstance(out["actions"], list)


def test_pipeline_oracle_inactive_when_disabled(monkeypatch=None):
    from core import pipeline_oracle as po

    # When hook returns disabled / None path — active False
    class Fake:
        @staticmethod
        def evaluate_after_sandbox(generated, objective):
            return {"enabled": False, "ok": True, "score": 1.0}

    import sys

    sys.modules["core.repo_oracle_hook"] = Fake  # type: ignore
    try:
        out = po.apply_repo_oracle_gate(
            "print(1)",
            "test",
            execution_score=1.0,
            verification_score=1.0,
            confidence=1.0,
        )
        assert out.get("active") is False
    finally:
        sys.modules.pop("core.repo_oracle_hook", None)


def test_live_fixture_policy_still_off_for_unknown():
    from core.live_fixture_policy import should_skip_live

    d = should_skip_live(fixture="unknown_green_fixture_zzz")
    assert d["skip"] is False
