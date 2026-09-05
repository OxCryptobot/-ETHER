"""p2_01 FAST: resume skips completed pipeline stages; prefixed ids load."""
from __future__ import annotations

from core.checkpoint import AgentCheckpoint, resume_if_any, save_checkpoint
from core.loop.resume import should_skip, skipped_stages


def test_skip_up_to_plan() -> None:
    prior = AgentCheckpoint(run_id="t", stage="pipeline:plan")
    skipped = skipped_stages(prior)
    assert "start" in skipped
    assert "plan" in skipped
    assert "sandbox" not in skipped
    assert should_skip("plan", prior) is True
    assert should_skip("verify", prior) is False


def test_empty_prior_skips_nothing() -> None:
    assert skipped_stages(None) == frozenset()


def test_resume_if_any_finds_pipeline_prefix(tmp_path, monkeypatch) -> None:
    from core import checkpoint as ck

    monkeypatch.setattr(ck, "CKPT_DIR", tmp_path)
    save_checkpoint(AgentCheckpoint(run_id="pipeline-abc", stage="pipeline:gems", objective="x"))
    found = resume_if_any("abc")
    assert found is not None
    assert found.stage.endswith("gems")
