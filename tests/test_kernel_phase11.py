"""Phase-11 plan persist, provider classify, lang detect, jsonl GC."""
from pathlib import Path
from core.kernel.gc import trim_jsonl
from core.kernel.lang import detect
from core.kernel.plan import Node, PlanGraph
from core.kernel.plan_store import dump, load, replan_low, save
from core.kernel.provider import classify

def test_plan_roundtrip_and_replan(tmp_path: Path) -> None:
    plan = PlanGraph(goal="fix add")
    plan.add(Node(id="t", goal="tests", class_="fast"))
    plan.add(Node(id="e", goal="edit", depends_on=["t"], confidence=0.2))
    plan.resolve("t", True)
    live = plan.next_live()
    assert live is not None and live.id == "e"
    assert replan_low(plan, "e") is True
    path = save(plan, tmp_path / "plan.json")
    again = load(dump(plan))
    assert again.goal == "fix add"
    assert path.is_file()

def test_provider_timeout_vs_empty() -> None:
    assert classify(TimeoutError("x"))["error"] == "provider_timeout"
    assert classify(text="")["error"] == "empty_model"
    assert classify(text="{ }")["ok"] is True

def test_lang_and_gc(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    assert "python" in detect(tmp_path)
    log = tmp_path / "t.jsonl"
    log.write_text("\n".join(f'{{"i":{i}}}' for i in range(12)) + "\n", encoding="utf-8")
    n = trim_jsonl(log, max_lines=5)
    assert n == 7
    assert len(log.read_text(encoding="utf-8").splitlines()) == 5
