"""FAST p3_44: unaided --policy model jobs get the measurement wall, not 90s production."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MOD = Path(__file__).resolve().parents[1] / "core" / "live_budget.py"
_SPEC = importlib.util.spec_from_file_location("ether_live_budget", _MOD)
assert _SPEC and _SPEC.loader
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)
apply_to_job = mod.apply_to_job


def test_unaided_policy_model_gets_measurement_wall() -> None:
    job = {
        "id": "p3_44_merge_unaided",
        "class": "fast",
        "note": "MEASURE: unaided merge LIVE --policy model",
        "steps": [
            {
                "argv": [
                    ".venv/Scripts/python.exe",
                    "-m",
                    "scripts.measure_tool_runtime",
                    "--live",
                    "--fixture",
                    "merge",
                    "--policy",
                    "model",
                ],
                "timeout": 560,
            }
        ],
    }
    out = apply_to_job(job)
    budget = out.get("live_budget") or {}
    assert budget.get("budget_class") == "measurement"
    assert int(budget.get("max_wall_s") or 0) >= 300
    assert int(out["steps"][0]["timeout"]) >= 300


def test_plain_fast_pytest_untouched() -> None:
    job = {
        "id": "p3_41_unaided_wrap",
        "class": "fast",
        "note": "FAST pytest wrap",
        "steps": [{"argv": [".venv/Scripts/python.exe", "-m", "pytest", "x.py"], "timeout": 90}],
    }
    out = apply_to_job(job)
    assert "live_budget" not in out
    assert out["steps"][0]["timeout"] == 90
