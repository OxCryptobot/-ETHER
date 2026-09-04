"""p3_74 batch: living loop grades toy/merge/ledger; pep8; babysit skip always."""
from pathlib import Path

from core.loop.living import FIXTURES, pep8_workspace, run_fixture, run_hard_pack, run_tests


def test_fixtures_exist():
    for name in ("toy", "merge", "ledger"):
        assert FIXTURES[name].exists(), name


def test_toy_pytest_green():
    out = run_fixture("toy", timeout=50)
    assert out["ok"] is True
    assert out["tests_ok"] is True, out["tests"]


def test_merge_and_ledger_are_graded():
    pack = run_hard_pack(timeout=50)
    assert pack["n"] == 3
    assert pack["ok"] is True  # graded, not crashed
    by = {r["name"]: r for r in pack["rows"]}
    assert "tests_ok" in by["merge"]
    assert "tests_ok" in by["ledger"]
    assert by["merge"]["pep8"]["via"] == "pep8_reviewer"


def test_pep8_on_living_module():
    report = pep8_workspace(Path(__file__).resolve().parents[1] / "core" / "loop" / "living.py")
    assert report["via"] == "pep8_reviewer"
    assert "ok" in report


def test_host_always_skips_babysit():
    src = (Path(__file__).resolve().parents[1] / "scripts" / "host_agent.py").read_text(encoding="utf-8")
    assert "launch: skip babysit job=" in src
    assert "if compute().get(\"medic_stand_down\")" not in src
