"""The monitor publishes a snapshot. It does not change anything."""
from __future__ import annotations

import json
from pathlib import Path

from core.agent.env import snapshot, write


def test_the_snapshot_has_the_machine(tmp_path: Path) -> None:
    art = tmp_path / "artifacts"
    art.mkdir()
    (art / "app_alive.json").write_text('{"ollama": true, "ts": "2026-11-07"}', encoding="utf-8")
    (art / "sota.json").write_text('{"goals": ["a", "b"], "last": {"goal": "b", "kept": true}}', encoding="utf-8")
    row = snapshot(tmp_path)
    assert row["ollama"] is True
    assert row["kept"] == 2
    assert row["last_goal"] == "b"
    written = write(tmp_path)
    assert (art / "env.json").is_file()
    assert written["kept"] == 2
    write(tmp_path)
    history = json.loads((art / "env_history.json").read_text(encoding="utf-8"))
    assert len(history) == 2
    assert history[-1]["kept"] == 2
