"""The 4B probe must parse a function and must not claim an honest PASS."""
from scripts.live_generate_probe import extract_code, function_ok


def test_extracts_function_after_think_block() -> None:
    text = "<think>draft</think>\n```python\ndef add(a, b):\n    return a + b\n```"
    code = extract_code(text)
    assert function_ok(code) is True


def test_rejects_imports() -> None:
    assert function_ok("import os\ndef add(a, b):\n    return a + b\n") is False


def test_probe_source_never_sets_honest_true() -> None:
    from pathlib import Path
    text = Path("scripts/live_generate_probe.py").read_text(encoding="utf-8")
    assert '"honest": False' in text
    assert "honest tool-path PASS" in text
