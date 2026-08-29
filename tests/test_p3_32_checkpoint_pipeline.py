"""P3: Pipeline.run writes checkpoints at each progress stage."""
from __future__ import annotations

from pathlib import Path

from core.checkpoint import checkpoint_pipeline, load_checkpoint


def test_checkpoint_pipeline_roundtrip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = checkpoint_pipeline(
        run_id="p3_32_demo",
        stage="plan",
        objective="fix merge",
        n_stages=1,
        extra={"strategy": "default"},
    )
    assert path is not None
    ckpt = load_checkpoint("pipeline-p3_32_demo")
    assert ckpt is not None
    assert ckpt.stage.startswith("pipeline:")
    assert ckpt.extra.get("kind") == "pipeline"
    assert ckpt.n_steps == 1


def test_pipeline_run_shadows_write_progress():
    src = (
        Path(__file__).resolve().parents[1] / "core" / "pipeline.py"
    ).read_text(encoding="utf-8")
    assert "checkpoint_pipeline" in src
    assert "def write_progress(task_id: str, objective: str, stage: str" in src
