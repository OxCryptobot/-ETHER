"""Matrix and the exe window read one snapshot. Neither writes app_alive."""
import json
from pathlib import Path

from scripts.unison import snapshot


def test_snapshot_is_read_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ETHER_ROOT", str(tmp_path))
    art = tmp_path / "artifacts"
    art.mkdir()
    (art / "app_alive.json").write_text(
        json.dumps({"alive": True, "ts": "2026-09-12T04:09:05+00:00", "ollama": True}) + "\n",
        encoding="utf-8",
    )
    (art / "evolve.json").write_text(
        json.dumps({"generation": 3, "walk_ok": True, "goal": {"id": "restore_1650_writer"}, "skills": {"learn": {"kind": "infra"}}}) + "\n",
        encoding="utf-8",
    )
    before = (art / "app_alive.json").read_text(encoding="utf-8")
    row = snapshot()
    assert row["face"] == "matrix"
    assert row["hands"] == "exe"
    assert row["writer"] == "exe"
    assert row["mutates"] is False
    assert row["stale"] is True
    assert row["goal"] == "restore_1650_writer"
    assert row["generation"] == 3
    assert "app_alive_stale" in row["gaps"]
    assert row["ports"] == {"watch": 7843, "retired": 8787}
    assert (art / "app_alive.json").read_text(encoding="utf-8") == before


def test_exe_status_uses_the_same_contract(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ETHER_ROOT", str(tmp_path))
    (tmp_path / "artifacts").mkdir()
    from scripts.ether_app import dashboard_status
    row = dashboard_status()
    assert row["face"] == "matrix"
    assert row["hands"] == "exe"
    assert row["mutates"] is False


def test_retired_face_exposes_the_same_api() -> None:
    import ast
    tree = ast.parse(Path("dashboard/app.py").read_text(encoding="utf-8"))
    names = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    assert "unison_api" in names
    assert "index" in names
