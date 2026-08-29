"""P3: bug_comments observation carries suggested replace_once from comments."""
from __future__ import annotations

from pathlib import Path

from core.hard_live_playbook import mutations_from_bug_comments
from core.tool_runtime import ToolRuntime


def test_ledger_comments_derive_debit_and_total():
    src = (
        Path(__file__).resolve().parents[1] / "fixtures" / "repo_oracle_ledger" / "ledger.py"
    ).read_text(encoding="utf-8")
    steps = mutations_from_bug_comments("ledger.py", src)
    news = [s["args"]["new"] for s in steps]
    assert any("a.debit(amount)" in n for n in news)
    assert any(n.strip() == "return s" or n.endswith("return s") for n in news)


def test_merge_comments_derive_remainder():
    src = (
        Path(__file__).resolve().parents[1] / "fixtures" / "repo_oracle_merge" / "merge.py"
    ).read_text(encoding="utf-8")
    steps = mutations_from_bug_comments("merge.py", src)
    assert len(steps) == 3
    news = [s["args"]["new"] for s in steps]
    assert any("list(b)" in n for n in news)
    assert any("list(a)" in n for n in news)
    assert any("out.extend(b[j:])" in n for n in news)


def test_bug_comments_tool_attaches_suggested():
    root = Path(__file__).resolve().parents[1]
    fixture = root / "fixtures" / "repo_oracle_merge"
    plan = [
        {"tool": "bug_comments", "args": {"path": "merge.py"}},
        {"tool": "done", "args": {"reason": "stop"}},
    ]
    it = iter(plan)

    def decide(_m):
        return next(it)

    rt = ToolRuntime(
        fixture_root=fixture,
        decide_fn=decide,
        max_steps=4,
        timeout_s=20,
        run_id="p3_33_suggest",
    )
    result = rt.run("inspect comments")
    assert result.n_steps >= 1
    obs = result.steps[0].observation
    assert obs.get("ok") is True
    sug = obs.get("suggested") or []
    assert len(sug) >= 3
    tools = {s.get("tool") for s in sug}
    assert "replace_once" in tools
