"""p3_53: resume_if_any round-trips a checkpoint. Pipeline.run still does not call it."""
from core.checkpoint import AgentCheckpoint, resume_if_any, save_checkpoint


def test_resume_if_any_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("core.checkpoint.CKPT_DIR", tmp_path)
    save_checkpoint(
        AgentCheckpoint(run_id="p3_53", stage="act", objective="resume brick", n_steps=2)
    )
    ckpt = resume_if_any("p3_53")
    assert ckpt is not None
    assert ckpt.stage == "act"
    assert ckpt.n_steps == 2


def test_resume_if_any_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("core.checkpoint.CKPT_DIR", tmp_path)
    assert resume_if_any("nope") is None
