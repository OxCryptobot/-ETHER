"""Host push hygiene — log must never be in git light paths."""
from __future__ import annotations


def test_light_paths_exclude_log():
    from scripts import host_agent as ha

    paths = ha._light_paths()
    joined = " ".join(p.replace("\\", "/") for p in paths)
    assert "host_agent_log.txt" not in joined


def test_commit_and_push_filters_log(tmp_path, monkeypatch):
    from scripts import host_agent as ha

    calls = []

    def fake_run(cmd, timeout=3600):
        calls.append(cmd)
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()

    monkeypatch.setattr(ha, "run", fake_run)
    ok = ha._commit_and_push(
        ["artifacts/host_agent_status.json", "artifacts/host_agent_log.txt"],
        "test msg",
        "test",
    )
    assert ok is True
    # git add must not include the log
    add_cmds = [c for c in calls if c[:2] == ["git", "add"]]
    assert add_cmds, "expected git add"
    for c in add_cmds:
        assert not any(str(x).endswith("host_agent_log.txt") for x in c)


def test_rotate_log_threshold_constant():
    from scripts import host_agent as ha

    assert ha.LOG_MAX_BYTES >= 1024 * 1024  # at least 1MB
    assert ha.LOG_MAX_BYTES <= 50 * 1024 * 1024  # well under GitHub 100MB
