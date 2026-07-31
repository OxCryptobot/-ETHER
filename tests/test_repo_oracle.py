"""Phase B — repo oracle unit tests (no LLM, no live tree writes)."""

from __future__ import annotations

from pathlib import Path

from core.repo_oracle import (
    apply_file_map,
    parse_file_markers,
    score_from_marked_code,
    score_repo_edit,
    validate_file_map,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "repo_oracle_toy"


def test_parse_file_markers_two_files():
    code = """# file: a.py
def a():
    return 1

# file: b.py
def b():
    return 2
"""
    m = parse_file_markers(code)
    assert set(m) == {"a.py", "b.py"}
    assert "def a" in m["a.py"]
    assert "def b" in m["b.py"]


def test_validate_blocks_parent_and_venv():
    assert validate_file_map({"../x.py": "x"})["ok"] is False
    assert validate_file_map({".venv/x.py": "x"})["ok"] is False
    assert validate_file_map({"memory/x.py": "x"})["ok"] is False
    assert validate_file_map({"ok.py": "x"})["ok"] is True


def test_toy_fixture_fails_before_fix():
    """Broken greeter must fail project tests — oracle has teeth."""
    # empty apply: only seed fixture as-is
    result = score_repo_edit(
        {"greeter.py": (FIXTURE / "greeter.py").read_text(encoding="utf-8")},
        fixture_root=FIXTURE,
        test_args=["tests"],
        timeout=30,
    )
    assert result["ok"] is False
    assert result["score"] < 1.0
    assert result["oracle"] == "project_pytest"


def test_toy_fixture_passes_after_fix():
    fixed = '''"""Fixed greeter."""

def greet(name: str) -> str:
    return f"Hello, {name}!"
'''
    result = score_repo_edit(
        {"greeter.py": fixed},
        fixture_root=FIXTURE,
        test_args=["tests"],
        timeout=30,
    )
    assert result["ok"] is True
    assert result["score"] == 1.0
    assert "greeter.py" in (result.get("written") or [])


def test_score_from_marked_code_fixed():
    code = '''# file: greeter.py
def greet(name: str) -> str:
    return f"Hello, {name}!"
'''
    result = score_from_marked_code(
        code,
        fixture_root=FIXTURE,
        test_args=["tests"],
        timeout=30,
    )
    assert result["ok"] is True
    assert result["score"] == 1.0
