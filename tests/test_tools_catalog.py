from pathlib import Path

from gems.grandidierite.registry import list_tools, run_tool


def test_persistent_catalog_non_empty():
    cat = list_tools()
    assert len(cat["persistent"]) >= 15


def test_repo_map_runs():
    res = run_tool("repo_map", {"max_files": 5})
    assert res["ok"] is True
    assert "result" in res


def test_secret_scan_clean():
    res = run_tool("secret_scan", {"text": "hello world"})
    assert res["ok"] is True
    assert res["result"].get("clean") is True


def test_strip_fences():
    res = run_tool("strip_markdown_fences", {"text": "```python\nx=1\n```"})
    assert res["ok"] is True
    assert "x=1" in res["result"].get("text", "")
