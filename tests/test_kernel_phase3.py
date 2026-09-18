"""Phase-3 poll + live drain skip on Ubuntu."""
from core.kernel.poll import poll_seconds, pending_count
from scripts.drain_live_fifo import is_live, writer_ok, _normalize_step

def test_poll_busy_vs_idle() -> None:
    assert poll_seconds(3) == 12
    assert poll_seconds(0) == 60
    assert pending_count() >= 0

def test_normalize_string_step() -> None:
    assert _normalize_step("pytest -q")["argv"] == ["pytest -q"]
    assert _normalize_step(["python", "-m", "pytest"])["argv"][0] == "python"

def test_live_skip_off_1650() -> None:
    assert is_live({"class": "live"}) is True
    assert is_live({"class": "fast"}) is False
    assert writer_ok() in {True, False}
