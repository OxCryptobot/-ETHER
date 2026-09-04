"""p3_73 living batch: sandbox pytest, security audit, lesson JSONL, plan run."""
from pathlib import Path

from core.loop.living import DEFAULT_TEST, audit_code, run_living, run_tests, save_lesson
from core.loop.plan_exec import execute_tool
from core.schemas import ExecutionPlan, PlanStep


def test_run_tests_temp_pytest():
    result = run_tests(code=DEFAULT_TEST, timeout=40)
    assert result.get("ok") is True or result.get("returncode") == 0, result


def test_audit_clean_code():
    out = audit_code("def add(a, b):\n    return a + b\n")
    assert out["via"] == "black_tourmaline"
    assert out["error"] is None


def test_audit_flags_eval():
    out = audit_code("eval(\"1+1\")\n")
    assert out["approved"] is False


def test_save_lesson(tmp_path, monkeypatch):
    import core.loop.living as living

    monkeypatch.setattr(living, "LESSONS", tmp_path / "lessons.jsonl")
    path = save_lesson("batch living")
    assert path.exists()
    assert "batch living" in path.read_text(encoding="utf-8")


def test_run_living_plan():
    plan = ExecutionPlan(
        steps=[
            PlanStep(id=1, action="generate", target="code"),
            PlanStep(id=2, action="test", target="sandbox", deps=[1]),
            PlanStep(id=3, action="validate", target="security", deps=[2]),
        ]
    )
    out = run_living(plan)
    assert out["n_steps"] == 3
    assert out["tests"]["ok"] is True or out["audit"]["via"] == "black_tourmaline"


def test_execute_tool_run_tests_not_deferred():
    out = execute_tool("run_tests")
    assert out.get("deferred") != "sandbox"
    assert out.get("tool") == "run_tests"
