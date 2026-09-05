"""FAST: deploy pipeline lists real gates."""
from __future__ import annotations

from pathlib import Path

from scripts.deploy_pipeline import GATES, OUT


def test_gates_are_real_files() -> None:
    root = Path(__file__).resolve().parents[1]
    assert len(GATES) >= 4
    for rel in GATES:
        assert (root / rel).is_file(), rel


def test_last_json_path() -> None:
    assert OUT.name == "last.json"
    assert "pipeline" in str(OUT)
