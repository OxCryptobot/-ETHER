"""Phase B slice 2 — optional project-pytest oracle after sandbox.

Enabled when ETHER_REPO_ORACLE=1 (or fixture env is set). Failures force the
pipeline retry path even if sandbox exit_code was 0, so repair runs on real
project-test signal rather than only on non-zero exit.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional


def repo_oracle_enabled() -> bool:
    if (os.getenv("ETHER_REPO_ORACLE") or "").strip() == "1":
        return True
    if (os.getenv("ETHER_REPO_ORACLE_FIXTURE") or "").strip():
        return True
    return False


def _fixture_root() -> Optional[Path]:
    raw = (os.getenv("ETHER_REPO_ORACLE_FIXTURE") or "fixtures/repo_oracle_toy").strip()
    p = Path(raw)
    if not p.is_absolute():
        # repo root = parents[1] of this file (core/)
        p = Path(__file__).resolve().parents[1] / p
    return p if p.exists() else None


def evaluate_after_sandbox(generated: str, objective: str = "") -> Optional[Dict[str, Any]]:
    """Return oracle dict or None when disabled / unavailable.

    Never raises — pipeline must stay up if fixture missing.
    """
    if not repo_oracle_enabled():
        return None
    code = generated or ""
    if not code.strip():
        return {
            "ok": False,
            "score": 0.0,
            "error": "empty generated code",
            "oracle": "project_pytest",
            "enabled": True,
        }
    fixture = _fixture_root()
    if fixture is None:
        return {
            "ok": False,
            "score": 0.0,
            "error": "ETHER_REPO_ORACLE_FIXTURE path missing",
            "oracle": "project_pytest",
            "enabled": True,
        }
    test_args = (os.getenv("ETHER_REPO_ORACLE_TEST_ARGS") or "tests").split()
    timeout = int(os.getenv("ETHER_REPO_ORACLE_TIMEOUT", "60"))
    as_path = (os.getenv("ETHER_REPO_ORACLE_AS_PATH") or "greeter.py").strip() or "greeter.py"
    try:
        from core.repo_oracle import parse_file_markers, score_from_marked_code, score_repo_edit

        markers = parse_file_markers(code)
        if markers:
            result = score_from_marked_code(
                code, fixture_root=fixture, test_args=test_args, timeout=timeout
            )
        else:
            result = score_repo_edit(
                {as_path: code},
                fixture_root=fixture,
                test_args=test_args,
                timeout=timeout,
            )
        result["enabled"] = True
        result["fixture"] = str(fixture)
        return result
    except Exception as e:
        return {
            "ok": False,
            "score": 0.0,
            "error": f"repo_oracle hook: {type(e).__name__}: {e}"[:300],
            "oracle": "project_pytest",
            "enabled": True,
        }
