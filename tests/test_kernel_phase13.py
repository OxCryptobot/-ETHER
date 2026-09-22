"""Phase-13 self-learn + self-state. Grok not in the loop."""
from core.kernel.self_learn import lesson_from_fail
from core.kernel.self_state import snapshot

def test_infra_fail_is_not_a_lesson() -> None:
    assert lesson_from_fail({"ok": False, "error": "provider_timeout", "tail": "Timeout"}) is None

def test_code_fail_becomes_lesson() -> None:
    row = lesson_from_fail({"ok": False, "job_id": "x", "tail": "parse error in tool json"})
    assert row is not None
    assert row["root_cause"] == "parse_fail"
    assert row["schema"] == "ether_mem_v1"

def test_self_state_marks_waiting_off_box() -> None:
    row = snapshot(ollama=False, pending_live=1, last={"job_id": "p", "ok": True})
    assert row["grok_required"] is False
    assert row["pending_live"] == 1
