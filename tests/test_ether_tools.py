"""Allowlisted tools used by the desktop app."""
from scripts.ether_tools import list_tree, run_allowlisted


def test_list_tree() -> None:
    rows = list_tree(20)
    assert rows
    assert any(r.startswith("scripts/") for r in rows)


def test_run_allowlisted_denies_unknown() -> None:
    out = run_allowlisted("rm -rf")
    assert out["ok"] is False
    assert out["error"] == "denied"


def test_run_git_status() -> None:
    out = run_allowlisted("git-status")
    assert "kind" in out
