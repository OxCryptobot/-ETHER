"""job_class must not treat pytest units as LIVE just because id contains live."""
from __future__ import annotations

from core.job_class import FAST, LIVE, MEASURE, job_class


def test_pytest_argv_is_fast_even_if_id_contains_live():
    job = {
        "id": "p1_243_hard_live_tools_unit",
        "note": "retest numbered read + edit_lines",
        "steps": [
            {
                "argv": [
                    ".venv/Scripts/python.exe",
                    "-m",
                    "pytest",
                    "tests/test_hard_live_tools.py",
                    "-q",
                ]
            }
        ],
    }
    assert job_class(job) == FAST


def test_explicit_measure_stays_measure():
    job = {
        "id": "p1_247_ledger_canary",
        "class": "measure",
        "note": "HARD ledger canary",
        "steps": [
            {
                "argv": [
                    ".venv/Scripts/python.exe",
                    "-m",
                    "scripts.batch_phase_d",
                    "--mode",
                    "live",
                    "--fixture",
                    "ledger",
                ]
            }
        ],
    }
    assert job_class(job) == MEASURE


def test_live_without_pytest_is_live():
    job = {
        "id": "p1_99_eligible_live_merge_direct",
        "note": "live merge direct",
        "steps": [
            {
                "argv": [
                    ".venv/Scripts/python.exe",
                    "-m",
                    "scripts.batch_phase_d",
                    "--mode",
                    "live",
                    "--fixture",
                    "merge",
                ]
            }
        ],
    }
    assert job_class(job) == LIVE
