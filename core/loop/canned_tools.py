"""Five canned fabricate templates. Quarantine only. Promote on green elsewhere."""
from __future__ import annotations

from typing import Any, Dict, List

CANNED = (
    ("echo_tool", "JSON echo"),
    ("pytest_runner", "Run pytest in a workspace"),
    ("git_status_tool", "Read-only git status"),
    ("file_patch", "Single-file replace_once helper"),
    ("lesson_append", "Append a flywheel lesson line"),
)


def fabricate_canned() -> List[Dict[str, Any]]:
    from gems.grandidierite.fabricate import fabricate

    rows = []
    for name, purpose in CANNED:
        rows.append(fabricate({"name": name, "docstring": purpose, "stub_only": True}))
    return rows
