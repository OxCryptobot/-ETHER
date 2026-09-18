"""Phase-2 kernel wiring."""
from pathlib import Path
from core.kernel.briefing import compile_briefing
from core.kernel.critique import may_second_hypothesis, valid_critique
from core.kernel.permissions import allow
from core.kernel.score_write import write_result

def test_critique_blocks_second_hyp() -> None:
    assert valid_critique({}) is False
    row = {"root_cause": "no_progress", "evidence": "read_file a.py twice", "smallest_experiment": "apply_patch then run_tests", "confidence": 0.7}
    assert valid_critique(row) is True
    assert may_second_hypothesis(fail_is_infra=True, critique=row) is False
    assert may_second_hypothesis(fail_is_infra=False, critique=row) is True

def test_permissions() -> None:
    assert allow("read_file") is True
    assert allow("apply_patch", writes_enabled=False) is False
    assert allow("shell") is False

def test_briefing_cap() -> None:
    text = compile_briefing([{"kind": "JobStarted", "job_id": "a"}] * 40, max_chars=120)
    assert len(text) <= 120

def test_score_write_rejects_generate(tmp_path: Path) -> None:
    row = write_result(tmp_path / "score.json", {"ok": True, "strategy": "generate"})
    assert row["ok"] is False and row["honest"] is False
