"""Allowlisted tools used by the desktop app."""
from scripts.ether_tools import list_tree, run_allowlisted


def test_list_tree() -> None:
    rows = list_tree(80)
    assert rows
    assert any("/" in r for r in rows)


def test_run_allowlisted_denies_unknown() -> None:
    out = run_allowlisted("rm -rf")
    assert out["ok"] is False
    assert out["error"] == "denied"


def test_run_git_status() -> None:
    out = run_allowlisted("git-status")
    assert "kind" in out


def test_apply_replace_and_search(tmp_path) -> None:
    from scripts.ether_tools import apply_replace, search
    f = tmp_path / "x.py"
    f.write_text("hello world\n", encoding="utf-8")
    # search uses ROOT not tmp; just assert search returns list
    assert isinstance(search("def "), list)
    # apply in repo artifact
    from scripts.ether_app import write_file, ROOT
    write_file("artifacts/tool_rep.txt", "hello")
    from scripts.ether_tools import apply_replace as ap
    assert ap("artifacts/tool_rep.txt", "hello", "world")["ok"] is True
