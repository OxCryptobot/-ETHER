"""P3: ToolRuntime writes a checkpoint after each step."""
from __future__ import annotations

from pathlib import Path

from core.checkpoint import load_checkpoint
from core.tool_runtime import ToolRuntime


def test_runtime_writes_checkpoint(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # checkpoint.py writes under repo ROOT, not cwd. Point ROOT via env if needed.
    # Use a real fixture from the repo.
    root = Path(__file__).resolve().parents[1]
    fixture = root / "fixtures" / "repo_oracle_toy"
    plan = [
        {"tool": "list_files", "args": {}},
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
        run_id="p3_27_ckpt",
    )
    result = rt.run("noop")
    assert result.n_steps >= 1
    ckpt = load_checkpoint("p3_27_ckpt")
    assert ckpt is not None
    assert ckpt.n_steps >= 1
    assert ckpt.stage in {"list_files", "done"}
