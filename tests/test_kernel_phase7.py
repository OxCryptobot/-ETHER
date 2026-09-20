"""Phase-7 argv allowlist, ownership, crash journal, strangle, parse_fail."""
from core.kernel.argv_allow import argv_allowed
from core.kernel.crash import last, record
from core.kernel.job_schema import validate_job
from core.kernel.ownership import may_write, owner_of
from core.kernel.parse_fail import parse_fail
from core.kernel.strangle import finalize

def test_argv_blocks_shell() -> None:
    assert argv_allowed([".venv/Scripts/python.exe", "-m", "pytest", "tests/test_kernel_phase7.py"]) is True
    assert argv_allowed(["powershell", "-Command", "calc"]) is False
    assert argv_allowed(["cmd.exe", "/c", "echo hi"]) is False

def test_job_schema_denies_shell() -> None:
    ok, errs = validate_job({"id": "bad", "class": "fast", "steps": [{"argv": ["powershell", "-File", "x.ps1"], "timeout": 10}]})
    assert ok is False and any("argv_denied" in e for e in errs)

def test_ownership_attach_is_exe() -> None:
    assert owner_of("artifacts/host_attach.json") == "exe"
    assert may_write("artifacts/host_attach.json", writer="fast") is False
    assert may_write("artifacts/host_attach.json", writer="exe") is True

def test_parse_fail_and_strangle() -> None:
    fail = parse_fail("garbage")
    assert fail["ok"] is False and fail["error"] == "parse_fail"
    row = finalize({"ok": True, "tools": ["write_file"]}, path="generate")
    assert row["ok"] is False

def test_crash_journal_observe_on_non_nt() -> None:
    row = record("unit")
    assert "reason" in row
    _ = last()
