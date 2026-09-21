"""Phase-12 autonomy: Grok optional, honest gate stays."""
from core.kernel.autonomy import decide
from core.kernel.operator_intent import grok_required

def test_grok_not_required() -> None:
    assert grok_required() is False

def test_nt_ollama_is_operator() -> None:
    row = decide(ollama=True, pending_live=1, last_ok=True, writer_nt=True)
    assert row["grok_required"] is False
    assert row["honest_gate"] is True
    assert row["soft_launch"] is False
    assert "4b_is_operator" in row["actions"]
    assert "drain_live" in row["actions"]

def test_ubuntu_does_not_run_live() -> None:
    row = decide(ollama=False, pending_live=1, last_ok=True, writer_nt=False)
    assert "observe_only" in row["actions"]
    assert "live_stays_pending" in row["actions"]
    assert "4b_is_operator" not in row["actions"]

def test_fail_requires_critique() -> None:
    row = decide(ollama=True, pending_live=0, last_ok=False, writer_nt=True)
    assert "critique_then_one_hyp" in row["actions"]
