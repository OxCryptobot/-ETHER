"""FAST drain rewrites Windows python.exe and skips LIVE class."""
from scripts.drain_fast_fifo import _rewrite_argv, is_fast


def test_rewrite_windows_python() -> None:
    argv = _rewrite_argv([".venv/Scripts/python.exe", "-m", "pytest"])
    assert not argv[0].endswith("python.exe")
    assert argv[1:] == ["-m", "pytest"]


def test_skip_live_class() -> None:
    assert is_fast({"class": "fast", "steps": []}) is True
    assert is_fast({"class": "live", "steps": []}) is False
    assert is_fast({"class": "fast", "note": "keep card attached", "steps": []}) is True
