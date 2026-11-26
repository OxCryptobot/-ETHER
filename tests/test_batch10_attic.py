"""Batch 10 item 1: unreachable code lives in attic/ (moved, not deleted) and nothing live imports it."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _manifest() -> list:
    return json.loads((ROOT / "attic" / "MANIFEST.json").read_text(encoding="utf-8"))["moved"]


def test_manifest_matches_tree() -> None:
    rows = _manifest()
    assert rows and len({m["from"] for m in rows}) == len(rows)
    for m in rows:
        assert m["to"] == "attic/" + m["from"]
        assert (ROOT / m["to"]).is_file(), m["to"]
        assert not (ROOT / m["from"]).exists(), m["from"]


def test_no_live_import_of_attic_modules() -> None:
    mods = [m["from"][:-3].replace("/", ".") for m in _manifest() if m["kind"] == "module"]
    pat = re.compile(r"^\s*(?:from|import)\s+(" + "|".join(re.escape(x) for x in mods) + r")\b", re.M)
    bad = []
    for d in ("core", "scripts", "gems", "tools", "tests", "cli", "dashboard"):
        for p in (ROOT / d).rglob("*.py"):
            if pat.search(p.read_text(encoding="utf-8", errors="ignore")):
                bad.append(p.relative_to(ROOT).as_posix())
    assert bad == []


def test_attic_is_skipped_by_scanners() -> None:
    from core.agent import goal_source as gs
    from core.kernel.ignore import SKIP

    assert "attic" in gs._SKIP_DIRS and "attic" in SKIP
