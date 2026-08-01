"""Phase D slice 1b — Clear Quartz multifile / project-pytest path."""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from core.schemas import ClearQuartzRequest, Envelope
from gems.clear_quartz.sandbox import ClearQuartz

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "fixtures" / "repo_oracle_ledger"
FIXED = ROOT / "fixtures" / "_fixed_solutions" / "ledger" / "ledger.py"


@pytest.mark.skipif(not LEDGER.is_dir(), reason="ledger fixture missing")
def test_multifile_files_dict_fixed_passes():
    files = {
        "account.py": (LEDGER / "account.py").read_text(encoding="utf-8"),
        "ledger.py": FIXED.read_text(encoding="utf-8"),
    }
    cq = ClearQuartz()
    res = cq.execute(
        Envelope(
            task_id=uuid4(),
            target_gem="clear-quartz",
            payload=ClearQuartzRequest(
                files=files,
                fixture_root=str(LEDGER),
                test_args=["tests"],
                prepare_code=False,
            ),
            timeout_seconds=30,
        )
    )
    assert res.error is None
    assert res.payload is not None
    assert res.payload.exit_code == 0
    assert res.payload.tests_passed == res.payload.total_tests
    assert "multifile:project_pytest" in res.payload.security_flags


@pytest.mark.skipif(not LEDGER.is_dir(), reason="ledger fixture missing")
def test_multifile_hash_file_markers():
    account = (LEDGER / "account.py").read_text(encoding="utf-8")
    ledger = FIXED.read_text(encoding="utf-8")
    code = f"# file: account.py\n{account}\n\n# file: ledger.py\n{ledger}\n"
    cq = ClearQuartz()
    res = cq.execute(
        Envelope(
            task_id=uuid4(),
            target_gem="clear-quartz",
            payload=ClearQuartzRequest(
                code=code,
                fixture_root=str(LEDGER),
                prepare_code=False,
            ),
            timeout_seconds=30,
        )
    )
    assert res.error is None
    assert res.payload.exit_code == 0


@pytest.mark.skipif(not LEDGER.is_dir(), reason="ledger fixture missing")
def test_multifile_broken_fails():
    files = {
        "account.py": (LEDGER / "account.py").read_text(encoding="utf-8"),
        "ledger.py": (LEDGER / "ledger.py").read_text(encoding="utf-8"),
    }
    cq = ClearQuartz()
    res = cq.execute(
        Envelope(
            task_id=uuid4(),
            target_gem="clear-quartz",
            payload=ClearQuartzRequest(
                files=files,
                fixture_root=str(LEDGER),
                prepare_code=False,
            ),
            timeout_seconds=30,
        )
    )
    assert res.error is None
    assert res.payload.exit_code != 0
