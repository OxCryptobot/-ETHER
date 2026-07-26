#!/usr/bin/env python3
"""Cluster recent FAIL stderr signatures from experience/runs."""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import emit, repo_root


def sig(text: str) -> str:
    text = (text or "").strip().splitlines()[-1] if text else ""
    text = re.sub(r"0x[0-9a-fA-F]+", "HEX", text)
    text = re.sub(r"\d+", "N", text)
    return text[:120] or "empty"


def main() -> None:
    c: Counter[str] = Counter()
    runs = repo_root() / "memory" / "runs"
    if runs.exists():
        for f in runs.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if data.get("status") == "error":
                c[sig(data.get("error") or "")] += 1
            sand = data.get("sandbox") or {}
            if sand.get("exit_code") not in (None, 0):
                c[sig(sand.get("stderr") or "")] += 1
    emit(True, clusters=[{"signature": k, "count": v} for k, v in c.most_common(20)])


if __name__ == "__main__":
    main()
