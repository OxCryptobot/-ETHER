"""Skill pass is honest: stale writer stays a gap, app_alive is not rewritten."""
import json
from pathlib import Path

from scripts.skills import run_skills

def test_skills_name_the_alive_gap() -> None:
    alive = Path("artifacts/app_alive.json")
    before = alive.read_text(encoding="utf-8") if alive.is_file() else ""
    row = run_skills({"weak": []})
    for name in ("batchphase", "goal", "host-agent-live", "keep-pushing", "pep8-python-reviewer", "super-auditor"):
        assert name in row
    assert row["keep-pushing"]["pushed"] is False
    assert row["pep8-python-reviewer"]["ok"] is True
    gaps = row["super-auditor"]["gaps"]
    stale = bool(row["host-agent-live"].get("stale"))
    if stale:
        assert row["goal"]["id"] == "restore_1650_writer"
        assert "app_alive_stale" in gaps
        assert row["super-auditor"]["ok"] is False
    else:
        assert row["goal"]["id"] in {"drain_and_learn", "heal_weak"}
        assert "app_alive_stale" not in gaps
    if row["host-agent-live"]["runners"] == 0:
        assert "no_github_runner" in gaps
    assert "token" not in json.dumps(row)
    if alive.is_file():
        assert alive.read_text(encoding="utf-8") == before
    assert row["learn"]["stored"] is False
    if gaps:
        assert row["learn"]["kind"] == "infra"
    else:
        assert row["learn"]["kind"] == "none"


def test_offline_runner_is_infra() -> None:
    from scripts.skills import learn, super_auditor
    audit = super_auditor({"host-agent-live": {"stale": True, "runners": 1, "online": 0}, "pep8-python-reviewer": {"ok": True}})
    assert "runner_offline" in audit["gaps"]
    assert learn(audit)["kind"] == "infra"
    from scripts.skills import learn, super_auditor
    audit = super_auditor({"host-agent-live": {"stale": True, "runners": None}, "pep8-python-reviewer": {"ok": True}})
    assert "runner_count_unknown" in audit["gaps"]
    assert learn(audit)["kind"] == "infra"
    from core.train_gates import may_record_fail

    ok, reason = may_record_fail(success=False, stderr="app_alive stale no_github_runner")
    assert ok is False
    assert reason == "infra_stderr"


def test_tools_stay_on_when_wheels_off(monkeypatch) -> None:
    monkeypatch.delenv("ETHER_TOOL_RUNTIME", raising=False)
    monkeypatch.setenv("ETHER_TRAINING_WHEELS", "0")
    from core.tool_runtime import tool_runtime_enabled

    assert tool_runtime_enabled() is True
