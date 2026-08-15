"""Phase 2.5 — LoRA dry tick must never touch weights."""
from __future__ import annotations

import json
import os
from pathlib import Path

from core.lora_dry_tick import dry_tick
from core.lora_train import dry_run_report, train_adapter


def test_dry_run_report_always_safe():
    r = dry_run_report()
    assert "may_train" in r
    assert "n_preference_pairs" in r
    assert r["doctrine"] == "offline_rlhf_then_gated_lora"


def test_train_adapter_forced_dry_under_wheels(monkeypatch):
    monkeypatch.setenv("ETHER_TRAINING_WHEELS", "1")
    monkeypatch.delenv("ETHER_LORA_TRAIN", raising=False)
    monkeypatch.delenv("ETHER_LORA_PROMOTE", raising=False)
    out = train_adapter(dry_run=False)  # caller lies — wheels win
    assert out.get("dry_run") is True
    assert out.get("ok") is True
    assert out.get("adapter_path") in (None, "")


def test_dry_tick_never_trains(monkeypatch, tmp_path):
    monkeypatch.setenv("ETHER_TRAINING_WHEELS", "1")
    # Even if someone leaves promote on, dry_tick must strip it
    monkeypatch.setenv("ETHER_LORA_TRAIN", "1")
    monkeypatch.setenv("ETHER_LORA_PROMOTE", "1")
    out = dry_tick(force=True)
    assert out["ok"] is True
    assert out["dry_run"] is True
    assert out["trained"] is False
    assert out["adapter_written"] is False
    assert out["train_adapter"]["dry_run"] is True


def test_dry_tick_writes_artifact(monkeypatch):
    monkeypatch.setenv("ETHER_TRAINING_WHEELS", "1")
    monkeypatch.setenv("ETHER_LORA_TRAIN", "0")
    out = dry_tick()
    path = Path(out["path"])
    # path is relative to repo root
    root = Path(__file__).resolve().parents[1]
    full = root / path
    assert full.is_file()
    data = json.loads(full.read_text(encoding="utf-8"))
    assert data["trained"] is False
    assert data["dry_run"] is True


def test_pipeline_still_imports():
    from core.pipeline import Pipeline

    assert Pipeline is not None
