"""Oracle delegation + whats_next retirement signal."""
from __future__ import annotations


def test_hooks_delegates_to_oracle():
    from core import pipeline_hooks
    from core import pipeline_oracle

    assert pipeline_hooks.apply_repo_oracle_gate is not None
    assert pipeline_oracle.apply_repo_oracle_gate is not None
    # Same pure module path for disabled hook
    class Fake:
        @staticmethod
        def evaluate_after_sandbox(generated, objective):
            return {"enabled": False, "ok": True, "score": 1.0}

    import sys

    sys.modules["core.repo_oracle_hook"] = Fake  # type: ignore
    try:
        out = pipeline_hooks.apply_repo_oracle_gate(
            "x=1",
            "obj",
            execution_score=1.0,
            verification_score=1.0,
            confidence=1.0,
        )
        assert out.get("active") is False
    finally:
        sys.modules.pop("core.repo_oracle_hook", None)


def test_whats_next_has_timeout_signal():
    from scripts.write_whats_next import main

    assert main() == 0
    from pathlib import Path
    import json

    data = json.loads(
        (Path(__file__).resolve().parents[1] / "artifacts" / "whats_next.json").read_text(
            encoding="utf-8"
        )
    )
    assert "timeout_retirement" in (data.get("signals") or {})
